"""Pack the weekly off-GitHub backup of the market site's data (kept in "DYS Backup" on Keo's computer).

    python3 -I tools/backup_pack.py --out /path/out [--state /path/backup-state.json]

Reads GitHub only (a mirror clone plus public release files): no GitHub writes, no keys. Locked (.enc)
files are copied as they are and stay locked. It makes, inside --out:

    files/...            the files to copy into the backup folder, at the same relative paths
    backup-state.json    the new state file; copy it into the backup folder LAST, after the files check out
    plan.json            verdict, what to copy (dest, bytes, sha256), warnings

The backup keeps two weekly slots (weekly-1, weekly-2) and writes the older one each run, so the copy
from the week before always survives. A run whose data is much smaller than the last good run is a
"hold": nothing is packed, so a wiped or damaged data branch can never replace a good copy.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone

REPO = "VapeZz/dys-market"
UA = "dys-backup (market.driveyourstyle.net)"
MAX_FILE = 380_000_000          # the copy tool takes files up to 400 MB; bigger ones are split into parts
PART = 350_000_000
KEEP_RUNS = 60
# hold when the saved prices shrink to under 70% of the last good run, or everything to under 50%
MIN_PRICES, MIN_TOTAL = 0.70, 0.50


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def today_pt(override=None):
    if override:
        return date.fromisoformat(override)
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Los_Angeles")).date()
    except Exception:  # noqa: BLE001  (no timezone data: Pacific standard time is close enough)
        return (datetime.now(timezone.utc) - timedelta(hours=8)).date()


# ---------- the data branch ----------

def data_stats(git_dir):
    """Counts for the data branch, read from git without checking anything out. None when it's missing."""
    try:
        out = run(["git", "-C", git_dir, "ls-tree", "-r", "-l", "refs/heads/data"])
    except subprocess.CalledProcessError:
        return None
    files = total = price_bytes = 0
    days = set()
    for line in out.splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) < 4 or parts[1] != "blob":
            continue
        size = int(parts[3]) if parts[3].isdigit() else 0
        files += 1
        total += size
        m = re.match(r"data/(snapshots|history)/(\d{4}-\d{2}-\d{2})", path)
        if m:
            price_bytes += size
            days.add(m.group(2))
    return {
        "commit": run(["git", "-C", git_dir, "rev-parse", "--short", "refs/heads/data"]).strip(),
        "commit_date": run(["git", "-C", git_dir, "log", "-1", "--format=%cI", "refs/heads/data"]).strip(),
        "files": files, "bytes": total, "price_days": len(days), "price_bytes": price_bytes,
        "newest_day": max(days) if days else None,
    }


def guard(stats, last, today):
    """(hold reasons, warnings) for this run's data against the last good run."""
    hold, warn = [], []
    if stats is None:
        return ["the data branch is missing on GitHub"], warn
    if stats["files"] == 0 or stats["price_days"] == 0:
        hold.append("the data branch holds no saved prices")
    if last:
        for key, floor, label in (("price_days", MIN_PRICES, "saved price days"), ("price_bytes", MIN_PRICES, "saved price data"),
                                  ("bytes", MIN_TOTAL, "saved data in total"), ("files", MIN_TOTAL, "saved files")):
            was, now = last.get(key) or 0, stats[key]
            if was and now < was * floor:
                hold.append(f"{label} fell from {was:,} to {now:,}")
    if stats.get("newest_day"):
        age = (today - date.fromisoformat(stats["newest_day"])).days
        if age > 3:
            warn.append(f"the newest saved price day is {stats['newest_day']} ({age} days old): the nightly job may be stuck")
    return hold, warn


# ---------- release files (the monthly price archive) ----------

def _get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _api(path):
    """GitHub API, plain first, then the gh tool (some runs only have one of the two)."""
    try:
        return json.loads(_get(f"https://api.github.com/{path}"))
    except Exception:  # noqa: BLE001
        return json.loads(run(["gh", "api", path]))


def release_assets(repo, tag):
    """[(name, size or None, url)] for one release, or None when it can't be listed. [] when there's no such release."""
    try:
        rel = _api(f"repos/{repo}/releases/tags/{tag}")
        if not isinstance(rel, dict) or "id" not in rel:
            return []
        out, page = [], 1
        while True:
            rows = _api(f"repos/{repo}/releases/{rel['id']}/assets?per_page=100&page={page}")
            out += [(a["name"], a["size"], a["browser_download_url"]) for a in rows]
            if len(rows) < 100:
                return out
            page += 1
    except Exception:  # noqa: BLE001
        pass
    try:  # no API here: the public release page lists the same files
        html = _get(f"https://github.com/{repo}/releases/expanded_assets/{tag}").decode("utf-8", "replace")
        names = sorted(set(re.findall(rf'href="/{re.escape(repo)}/releases/download/{re.escape(tag)}/([^"]+)"', html)))
        return [(n, None, f"https://github.com/{repo}/releases/download/{tag}/{n}") for n in names]
    except urllib.error.HTTPError as e:
        return [] if e.code == 404 else None
    except Exception:  # noqa: BLE001
        return None


def release_counts(repo):
    """{tag: number of files} for every release, or None when the list can't be read."""
    try:
        out, page = {}, 1
        while True:
            rows = _api(f"repos/{repo}/releases?per_page=100&page={page}")
            for r in rows:
                out[r["tag_name"]] = len(r.get("assets") or [])
            if len(rows) < 100:
                return out
            page += 1
    except Exception:  # noqa: BLE001
        return None


def pack_archive(repo, tag, work, dest):
    """Download one monthly archive release and pack it as one tar. Returns the number of files, or None on failure."""
    assets = release_assets(repo, tag)
    if not assets:
        return None if assets is None else 0
    folder = os.path.join(work, tag)
    os.makedirs(folder, exist_ok=True)
    for name, size, url in assets:
        if "/" in name or name.startswith("."):
            return None
        path = os.path.join(folder, name)
        for _try in range(3):
            try:
                with open(path, "wb") as f:
                    f.write(_get(url, timeout=300))
                if size is None or os.path.getsize(path) == size:
                    break
            except Exception:  # noqa: BLE001
                pass
        else:
            return None
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with tarfile.open(dest, "w") as tar:      # plain tar: the files inside are already compressed
        for name in sorted(n for n, _s, _u in assets):
            tar.add(os.path.join(folder, name), arcname=f"{tag}/{name}")
    with tarfile.open(dest) as tar:
        if len(tar.getnames()) != len(assets):
            return None
    shutil.rmtree(folder, ignore_errors=True)
    return len(assets)


# ---------- packing ----------

def split_if_big(path):
    """Files over the copy limit are cut into .part01, .part02... (join them back in order to restore)."""
    if os.path.getsize(path) <= MAX_FILE:
        return [path]
    parts = []
    with open(path, "rb") as f:
        i = 1
        while True:
            chunk = f.read(PART)
            if not chunk:
                break
            p = f"{path}.part{i:02d}"
            with open(p, "wb") as out:
                out.write(chunk)
            parts.append(p)
            i += 1
    os.remove(path)
    return parts


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--state", default="")
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--today", default="")
    ap.add_argument("--mirror", default="", help="use this existing mirror clone instead of cloning (tests)")
    args = ap.parse_args(argv)

    out = os.path.abspath(args.out)
    files_dir, work = os.path.join(out, "files"), os.path.join(out, "_work")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(files_dir)
    os.makedirs(work)
    today = today_pt(args.today)

    state = {}
    if args.state and os.path.exists(args.state):
        with open(args.state, encoding="utf-8-sig") as f:
            state = json.load(f)
    last = state.get("last_good") or {}

    git_dir = os.path.abspath(args.mirror) if args.mirror else os.path.join(work, "repo.git")
    if not args.mirror:
        run(["git", "clone", "-q", "--mirror", f"https://github.com/{args.repo}.git", git_dir])

    stats = data_stats(git_dir)
    hold, warn = guard(stats, last, today)
    notes, made = [], []
    slot = "weekly-2" if state.get("newest_slot") == "weekly-1" else "weekly-1"
    months = list(state.get("months") or [])
    archives = dict(state.get("archives") or {})
    month = today.strftime("%Y-%m")

    if not hold:
        slot_dir = os.path.join(files_dir, slot)
        os.makedirs(slot_dir)
        # 1) saved data, as a zip anyone can open
        zip_path = os.path.join(slot_dir, "saved-data.zip")
        run(["git", "-C", git_dir, "archive", "--format=zip", "-o", zip_path, "refs/heads/data"])
        with zipfile.ZipFile(zip_path) as z:
            bad = z.testzip()
            n_files = sum(1 for i in z.infolist() if not i.is_dir())
        if bad or n_files != stats["files"]:
            hold.append(f"the saved-data zip didn't check out ({n_files} of {stats['files']} files)")
        # 2) the live site (it also holds the videos earlier posts point to), and 3) everything else in the repo
        refs = run(["git", "-C", git_dir, "for-each-ref", "--format=%(refname)"]).split()
        rest = [r for r in refs if r not in ("refs/heads/data", "refs/heads/gh-pages")]
        bundles = [("repo-code.bundle", rest)]
        if "refs/heads/gh-pages" in refs:
            bundles.append(("repo-live-site.bundle", ["refs/heads/gh-pages"]))
        for name, which in bundles:
            path = os.path.join(slot_dir, name)
            run(["git", "-C", git_dir, "bundle", "create", "-q", path] + which)
            run(["git", "-C", git_dir, "bundle", "verify", "-q", path])
        if "refs/heads/main" not in refs:
            hold.append("the main branch is missing on GitHub")

    if not hold:
        made = [os.path.join(slot_dir, n) for n in sorted(os.listdir(slot_dir))]
        # 4) one dated copy of the saved data per month, kept for good
        if month not in months:
            mdir = os.path.join(files_dir, "monthly")
            os.makedirs(mdir)
            mpath = os.path.join(mdir, f"saved-data-{month}.zip")
            shutil.copyfile(zip_path, mpath)
            made.append(mpath)
            months.append(month)
        # 5) the monthly price archive releases: this month and, until it's final, last month
        prev = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        for m in (prev, month):
            tag = f"archive-{m}"
            if (archives.get(tag) or {}).get("final"):
                continue
            dest = os.path.join(files_dir, "price-archives-monthly", f"{tag}.tar")
            n = pack_archive(args.repo, tag, work, dest)
            had = (archives.get(tag) or {}).get("files") or 0
            if n is None:
                warn.append(f"{tag}: couldn't read the release files, kept the earlier copy")
            elif n == 0:
                notes.append(f"{tag}: no such release yet")
            elif n < had:
                warn.append(f"{tag}: GitHub has {n} files, the backup has {had}; kept the backup's copy")
                os.remove(dest)
            else:
                made.append(dest)
                archives[tag] = {"files": n, "final": m < month}
        # 6) the raw tcgcsv days never change; say so if GitHub ever holds more than the backup
        counts = release_counts(args.repo)
        if counts is not None:
            raw = sum(c for t, c in counts.items() if t.startswith("tcgcsv-"))
            if state.get("tcgcsv_days") and raw != state["tcgcsv_days"]:
                warn.append(f"GitHub holds {raw} raw price days, the backup holds {state['tcgcsv_days']}: the backup needs a top-up")

    # split anything over the copy limit, then list what to copy
    plan_files = []
    for path in made:
        for p in split_if_big(path):
            plan_files.append({"local": p, "dest": os.path.relpath(p, files_dir).replace("/", "\\"),
                               "bytes": os.path.getsize(p), "sha256": sha256(p)})
    if plan_files:
        lines = ["DRIVE YOUR STYLE - DATA BACKUP: THIS WEEK'S COPY",
                 f"Made {today.isoformat()} from GitHub repo {args.repo}.",
                 f"Saved data: {stats['files']:,} files, {stats['bytes']:,} bytes, {stats['price_days']} price days "
                 f"(newest {stats['newest_day']}), data commit {stats['commit']}.",
                 "Columns: SHA-256 checksum, size in bytes, file.", ""]
        lines += [f"{f['sha256']}  {f['bytes']:12d}  {f['dest']}" for f in plan_files]
        if any(".part" in f["dest"] for f in plan_files):
            lines += ["", "Files ending in .part01, .part02... are one file cut into pieces: join them in order to restore."]
        listing = os.path.join(files_dir, slot, "FILE-LIST.txt")
        with open(listing, "w", newline="") as f:
            f.write("\r\n".join(lines) + "\r\n")
        plan_files.append({"local": listing, "dest": f"{slot}\\FILE-LIST.txt", "bytes": os.path.getsize(listing), "sha256": sha256(listing)})

    verdict = "hold" if hold else "ok"
    entry = {"date": today.isoformat(), "verdict": verdict}
    if hold:
        entry["why"] = hold
    else:
        entry.update({"slot": slot, "data_commit": stats["commit"], "files": stats["files"], "bytes": stats["bytes"],
                      "price_days": stats["price_days"], "copied_bytes": sum(f["bytes"] for f in plan_files)})
    if warn:
        entry["warnings"] = warn
    new_state = dict(state)
    new_state["version"] = 1
    new_state["runs"] = ((state.get("runs") or []) + [entry])[-KEEP_RUNS:]
    if not hold:
        new_state.update({"newest_slot": slot, "months": months, "archives": archives,
                          "last_good": {"date": today.isoformat(), **stats}})
    state_path = os.path.join(out, "backup-state.json")
    with open(state_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(new_state, f, indent=1)

    shutil.rmtree(work, ignore_errors=True)
    total = sum(f["bytes"] for f in plan_files)
    if hold:
        summary = "HOLD, nothing copied: " + "; ".join(hold)
    else:
        summary = (f"OK: {len(plan_files)} files, {total / 1e6:.0f} MB into {slot}; saved data {stats['files']:,} files, "
                   f"{stats['price_days']} price days (newest {stats['newest_day']})")
    plan = {"verdict": verdict, "summary": summary, "hold": hold, "warnings": warn, "notes": notes, "slot": slot if not hold else None,
            "files": plan_files, "state_file": state_path, "state_dest": "backup-state.json"}
    with open(os.path.join(out, "plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=1)
    print(summary)
    for w in warn:
        print("WARNING: " + w)
    for n in notes:
        print("note: " + n)
    for f in plan_files:
        print(f"  {f['bytes']:>12,}  {f['dest']}")
    print("plan: " + os.path.join(out, "plan.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
