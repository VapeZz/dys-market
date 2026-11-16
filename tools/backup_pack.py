"""Weekly off-GitHub backup of the market site's data (kept in "DYS Backup" on Keo's computer).

Three steps, run by the weekly task around its copy to the computer (the task prompt is in tools/BACKUP-TASK.md):

    python3 -I tools/backup_pack.py pack    --out OUT --state backup-state.json [--state-history DIR] --dest-listing before.json
    python3 -I tools/backup_pack.py verify  --out OUT --dest-listing after.json --staged staged.json [--attempt 2]
    python3 -I tools/backup_pack.py confirm --out OUT --dest-listing final.json --staged staged-commit.json

pack    reads GitHub only (a mirror clone plus public release files; no writes, no keys; locked .enc files stay
        locked) and writes OUT/plan.json: the files to copy ("transfer"), files already in the backup folder to
        read back and check ("verify_existing") and how to read them back ("stage_batches"). It records nothing.
verify  checks every copied file AS IT IS ON THE COMPUTER (read back into this session): size, SHA-256, and that
        each zip / tar / git bundle opens and holds what it should (split files are joined first). Only when all
        of it checks out does it write the new state into OUT/commit/. Anything wrong: no state, nothing recorded.
confirm checks the state files themselves landed intact.

The state ("backup-state.json") is the only record of what the backup holds. It is version 2, carries its own
SHA-256 ("integrity"), and every committed run also writes a never-overwritten copy into state-history\\ before
backup-state.json. Either intact copy records the run; the next run uses the newest intact one, so a torn or
half-written backup-state.json is recognised by its checksum and the history copy is used instead.

Rules the code enforces:
- The two weekly slots take turns. A run only ever writes into the slot that is NOT the newest verified one, so
  the last good weekly copy is never touched; an interrupted run is simply redone into the same slot.
- Monthly copies (monthly\\saved-data-YYYY-MM.zip) and monthly price archives (price-archives-monthly\\) are
  never overwritten: a file that already exists keeps its name and a new copy gets a new name.
- A month is recorded only with the files, sizes and checksums verified at the destination.
- A month an old (version 1) state lists but whose file is missing is NOT rebuilt automatically: it is reported
  every run until `pack --recover-month YYYY-MM` is run with Keo's approval (only possible during that month,
  because a later copy would not be that month's data). The recovered file is named ...-recovered-DATE.zip.
- A run whose data is much smaller than the last good run is a "hold": nothing is packed.
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone

REPO = "VapeZz/dys-market"
UA = "dys-backup (market.driveyourstyle.net)"
MAX_FILE = 380_000_000          # the copy tool takes files up to 400 MB; bigger ones are split into parts
PART = 350_000_000
STAGE_BATCH = 450_000_000       # reading files back from the computer: at most 500 MB and 50 files per call
STAGE_FILES = 50
KEEP_RUNS = 60
# hold when the saved prices shrink to under 70% of the last good run, or everything to under 50%
MIN_PRICES, MIN_TOTAL = 0.70, 0.50
STATE_VERSION = 2
SLOTS = ("weekly-1", "weekly-2")
HISTORY = "state-history"
LEGACY_SUFFIX = "-legacy-v1.json"       # the version-1 state, saved once as it was before the first new run
DEST_ROOT = "C:\\Users\\chris\\Documents\\DYS Backup"
LOCK = "backup.lock"                   # one run at a time: owner's run id and when its claim runs out
LOCK_TTL = timedelta(hours=2)          # a run normally takes 15-40 minutes; after this a lock counts as abandoned
WIN_MAX_PATH = 259
_WIN_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}


class Blocked(Exception):
    """A case the backup refuses to handle on its own; a person has to look."""


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


def atomic_write(path, data):
    """Write bytes so the file is either the old one or the complete new one, never half of each."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def now_utc():
    return datetime.now(timezone.utc)


def iso(t):
    return t.isoformat(timespec="seconds")


def parse_time(s):
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def write_json(path, obj):
    atomic_write(path, (json.dumps(obj, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))


def read_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


# ---------- the state file ----------

def _canonical(state):
    body = {k: v for k, v in state.items() if k != "integrity"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def seal(state):
    state = dict(state)
    state["integrity"] = hashlib.sha256(_canonical(state)).hexdigest()
    return state


def intact(state):
    return isinstance(state, dict) and state.get("integrity") == hashlib.sha256(_canonical(state)).hexdigest()


_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def migrate_v1(old):
    """Version 1 state (Nov 12-15, 2026). Its months were recorded before anything was checked at the
    destination, so they are all 'legacy-unverified' until a run finds and checks the file."""
    months = old.get("months") or []
    slot = old.get("newest_slot")
    archives = old.get("archives") or {}
    if (not isinstance(months, list) or not all(isinstance(m, str) and _MONTH.match(m) for m in months)
            or slot not in (None,) + SLOTS or not isinstance(archives, dict)
            or not isinstance(old.get("runs") or [], list) or not isinstance(old.get("last_good") or {}, dict)):
        raise Blocked("backup-state.json is an old (version 1) state in a shape this script doesn't know; a person has to look")
    new = {
        "version": STATE_VERSION, "seq": 0, "txn": None, "migrated_from": 1,
        "newest_slot": slot,
        "slots": {s: {"status": "legacy"} for s in SLOTS if s == slot},
        "monthly": {m: {"status": "legacy-unverified"} for m in months},
        "archives": {t: dict(v, status="legacy") for t, v in archives.items() if isinstance(v, dict)},
        "last_good": old.get("last_good") or {},
        "runs": old.get("runs") or [],
    }
    if old.get("tcgcsv_days"):
        new["tcgcsv_days"] = old["tcgcsv_days"]
    return new


def load_state(primary, history_paths=()):
    """(state, notes). The newest intact version-2 state among backup-state.json and the state-history copies;
    else the version-1 backup-state.json, migrated. Anything else is Blocked."""
    good, notes, legacy = [], [], None
    for path in [primary] + list(history_paths):
        if not path or not os.path.exists(path):
            continue
        name = os.path.basename(path)
        try:
            s = read_json(path)
        except (OSError, ValueError) as e:
            notes.append(f"{name} can't be read ({type(e).__name__}); not used")
            continue
        if not isinstance(s, dict):
            notes.append(f"{name} is not a state file; not used")
        elif s.get("version") == STATE_VERSION:
            if intact(s) and isinstance(s.get("seq"), int):
                good.append(s)
            else:
                notes.append(f"{name}: its checksum doesn't match (a torn or edited write); not used")
        elif (path == primary or name.lower().endswith(LEGACY_SUFFIX)) and (
                s.get("version") == 1 or ("version" not in s and ("months" in s or "runs" in s))):
            legacy = legacy if (legacy is not None and path != primary) else s
        else:
            notes.append(f"{name}: state version {s.get('version')!r} is not supported; not used")
    if good:
        best = max(good, key=lambda s: s["seq"])
        return best, notes
    if legacy is not None:
        return migrate_v1(legacy), notes + ["old (version 1) state found and upgraded; months it lists are checked before they count"]
    if not os.path.exists(primary) and not any(os.path.exists(p) for p in history_paths):
        raise Blocked("backup-state.json is missing (a new one is never made on its own)")
    raise Blocked("no usable backup state: " + "; ".join(notes))


# ---------- the backup folder as the computer lists it ----------

def key(dest):
    """Windows paths compare without regard to case or the kind of slash."""
    return dest.replace("/", "\\").strip("\\").lower()


def load_listing(path):
    """{key: (dest, bytes)} from device_list_dir's JSON (its {"entries": [...]} or the bare list)."""
    raw = read_json(path)
    entries = raw.get("entries") if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        raise Blocked(f"{os.path.basename(path)} is not a folder listing")
    if isinstance(raw, dict) and (raw.get("truncated") or raw.get("skeleton")):
        raise Blocked("the backup folder listing is incomplete, so files that already exist can't be protected")
    if any(isinstance(e, dict) and e.get("depthCapped") for e in entries):
        raise Blocked("the backup folder listing stopped at its depth limit, so files that already exist can't be protected")
    out = {}
    for e in entries:
        if not isinstance(e, dict) or "name" not in e or e.get("type", "file") != "file":
            continue
        dest = e["name"].replace("/", "\\").strip("\\")
        out[key(dest)] = (dest, int(e.get("size") or 0), e.get("mtimeMs"))
    return out


def win_name_ok(dest):
    full = DEST_ROOT + "\\" + dest
    if len(full) > WIN_MAX_PATH:
        return False
    for part in dest.split("\\"):
        if (not part or part != part.rstrip(" .") or re.search(r'[<>:"/|?*\x00-\x1f]', part)
                or part.split(".")[0].upper() in _WIN_RESERVED):
            return False
    return True


def free_name(dest, listing, taken):
    """dest if nothing is there yet, else dest with -2, -3... before the extension (never an existing file)."""
    stem, ext = re.match(r"^(.*?)((?:\.[A-Za-z0-9]+)?)$", dest).groups()
    n, cand = 1, dest

    def used(c):
        k = key(c)
        return k in taken or any(x == k or x.startswith(k + ".part") for x in listing)
    while used(cand):
        n += 1
        cand = f"{stem}-{n}{ext}"
    return cand


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
        for k, floor, label in (("price_days", MIN_PRICES, "saved price days"), ("price_bytes", MIN_PRICES, "saved price data"),
                                ("bytes", MIN_TOTAL, "saved data in total"), ("files", MIN_TOTAL, "saved files")):
            was, now = last.get(k) or 0, stats[k]
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
        if "/" in name or "\\" in name or name.startswith("."):
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


# ---------- checking a file ----------

def check_file(path, kind, expect):
    """None when the file opens and holds what it should, else what's wrong. kind: zip, tar, bundle, other."""
    try:
        if kind == "zip":
            with zipfile.ZipFile(path) as z:
                bad = z.testzip()               # reads every member and checks its CRC
                n = sum(1 for i in z.infolist() if not i.is_dir())
            if bad:
                return f"zip member {bad} is damaged"
            if expect is not None and n != expect:
                return f"zip holds {n} files, expected {expect}"
        elif kind == "tar":
            with tarfile.open(path) as t:
                members = t.getmembers()
                for m in members:                # read every member to the end
                    if m.isfile():
                        f = t.extractfile(m)
                        while f.read(1 << 20):
                            pass
            if expect is not None and len(members) != expect:
                return f"tar holds {len(members)} files, expected {expect}"
        elif kind == "bundle":
            # "git bundle verify" alone passes a bundle cut off half way; reading it into a scratch repository
            # makes git check every object and that every branch is complete
            with tempfile.TemporaryDirectory() as d:
                run(["git", "init", "-q", "--bare", d])
                run(["git", "-C", d, "bundle", "verify", "-q", path])
                heads = [ln for ln in run(["git", "-C", d, "bundle", "list-heads", path]).splitlines() if ln.strip()]
                if not heads:
                    return "bundle holds no branches"
                run(["git", "-C", d, "fetch", "-q", "--no-write-fetch-head", path, "refs/*:refs/check/*"])
                got = run(["git", "-C", d, "for-each-ref", "--format=%(refname)", "refs/check/"]).split()
                want = {ln.split()[1] for ln in heads if len(ln.split()) == 2 and ln.split()[1].startswith("refs/")}
                if len(got) != len(want):
                    return f"bundle gave {len(got)} of {len(want)} branches"
    except (zipfile.BadZipFile, tarfile.TarError, EOFError, OSError, subprocess.CalledProcessError, ValueError) as e:
        return f"{kind} doesn't open ({type(e).__name__})"
    return None


def kind_of(dest):
    d = re.sub(r"\.part\d+$", "", dest.lower())
    return "zip" if d.endswith(".zip") else "tar" if d.endswith(".tar") else "bundle" if d.endswith(".bundle") else "other"


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


# ---------- the run lock and the guards ----------

def _history_names(listing):
    return sorted(k for k in listing if k.startswith(key(HISTORY) + "\\"))


def lock_holder(lock_path, listing, now=None):
    """None when no other run may be writing; else a sentence saying who holds the lock and until when."""
    now = now or now_utc()
    if key(LOCK) not in listing:
        return None
    if not lock_path or not os.path.exists(lock_path):
        raise Blocked("backup.lock is on the computer but wasn't read back, so another run may be active")
    try:
        lock = read_json(lock_path)
        if not isinstance(lock, dict):
            raise ValueError("not a lock")
    except (OSError, ValueError):
        mtime = listing[key(LOCK)][2]
        until = (datetime.fromtimestamp(mtime / 1000, timezone.utc) + LOCK_TTL) if mtime else None
        if until and until > now:
            return f"an unreadable backup.lock written at {iso(until - LOCK_TTL)} (treated as held until {iso(until)})"
        return None                     # unreadable and old: an abandoned half-written lock
    if lock.get("state") != "active":
        return None
    until = parse_time(lock.get("expires"))
    if until and until > now:
        return f"backup run {lock.get('txn')} (started {lock.get('since')}) holds backup.lock until {lock.get('expires')}"
    return None                         # expired: that run was abandoned


def take_lock(out, txn, lock_path, listing, break_lock="", now=None):
    """Write the lock files for this run (the task copies them to the computer) after checking no one holds it."""
    now = now or now_utc()
    holder = lock_holder(lock_path, listing, now)
    if holder:
        held_txn = None
        try:
            held_txn = read_json(lock_path).get("txn")
        except (OSError, ValueError, AttributeError):
            pass
        if not (break_lock and break_lock == held_txn):
            raise Blocked("another backup run may be writing: " + holder +
                          ". Nothing was copied. If no run is active, wait until then, or (with Keo's OK) pass --break-lock with that run id")
    acquire = os.path.join(out, "lock", "acquire.json")
    release = os.path.join(out, "lock", "release.json")
    write_json(acquire, {"lock": "DYS backup", "state": "active", "txn": txn, "since": iso(now), "expires": iso(now + LOCK_TTL)})
    write_json(release, {"lock": "DYS backup", "state": "released", "txn": txn, "released": iso(now)})
    return {"dest": LOCK, "device_path": DEST_ROOT + "\\" + LOCK, "acquire": acquire, "release": release, "txn": txn,
            "expires": iso(now + LOCK_TTL)}


def base_info(state_path, listing):
    """What the record looked like when this run began; every later step checks it hasn't changed."""
    info = {"history": _history_names(listing), "pointer_sha": None, "pointer_bytes": None}
    if os.path.exists(state_path) and key("backup-state.json") in listing:
        info["pointer_sha"], info["pointer_bytes"] = sha256(state_path), listing[key("backup-state.json")][1]
    return info


def guard_checks(plan, listing, staged, phase, landed=None, now=None):
    """Problems that mean this run must not go on writing. phase: start, verify, commit or release."""
    now = now or now_utc()
    problems = []
    lk = key(LOCK)
    if lk not in listing or lk not in staged or not os.path.exists(staged[lk]):
        problems.append("backup.lock is missing or wasn't read back")
    else:
        try:
            lock = read_json(staged[lk])
        except (OSError, ValueError):
            lock = {}
        if not isinstance(lock, dict) or lock.get("txn") != plan["txn"] or lock.get("state") != "active":
            problems.append(f"backup.lock now belongs to another run ({lock.get('txn') if isinstance(lock, dict) else 'unreadable'})")
    if phase == "release":
        return problems
    made = parse_time(plan.get("created_at"))
    if not made or now - made > LOCK_TTL:
        problems.append("this run started more than 2 hours ago (a resumed or stalled run); it must start over")
    base = plan.get("base") or {}
    pk = key("backup-state.json")
    if base.get("pointer_sha"):
        if pk not in listing or pk not in staged or listing[pk][1] != base["pointer_bytes"] or sha256(staged[pk]) != base["pointer_sha"]:
            problems.append("backup-state.json changed since this run began (another run recorded a backup)")
    if _history_names(listing) != base.get("history", []):
        problems.append("state-history changed since this run began (another run recorded a backup)")
    if phase == "commit":
        for dest, (size, mtime) in (landed or {}).items():
            now_entry = listing.get(key(dest))
            if not now_entry or now_entry[1] != size or (mtime is not None and now_entry[2] != mtime):
                problems.append(f"{dest} changed on the computer after it was checked")
    return problems


def guard_cmd(args):
    out = os.path.abspath(args.out)
    plan = read_json(os.path.join(out, "plan.json"))
    listing = load_listing(args.dest_listing)
    staged = load_staged(args.staged) if args.staged else {}
    landed = None
    if args.phase == "commit":
        landed = (read_json(os.path.join(out, "verify.json")).get("landed") or {})
    problems = guard_checks(plan, listing, staged, args.phase, landed)
    write_json(os.path.join(out, f"guard-{args.phase}.json"), {"ok": not problems, "problems": problems})
    if problems:
        print("CONFLICT: " + "; ".join(problems))
        return 3
    print(f"GUARD OK ({args.phase}): this run holds backup.lock and nothing else has changed the backup")
    return 0


def _slot_mismatch(state, listing):
    """Why the newest weekly copy no longer matches its record, or None."""
    slot = state.get("newest_slot")
    rec = (state.get("slots") or {}).get(slot) or {}
    if rec.get("status") != "verified":
        return None
    landed = rec.get("landed") or {}
    for whole, f in (rec.get("files") or {}).items():
        parts = f.get("parts") or [whole]
        entries = [listing.get(key(p)) for p in parts]
        if any(e is None for e in entries):
            return f"{whole} is missing"
        if sum(e[1] for e in entries) != f["bytes"]:
            return f"{whole} is {sum(e[1] for e in entries):,} bytes, its record says {f['bytes']:,}"
        for p, e in zip(parts, entries):
            if p in landed and landed[p][1] is not None and e[2] != landed[p][1]:
                return f"{p} was rewritten after it was recorded"
    return None


# ---------- step 1: pack ----------

def _monthly_files_at(listing, prefix):
    """Files in the backup folder under monthly\\ whose name starts with prefix (zip or its parts)."""
    p = key("monthly\\" + prefix)
    return sorted(v[0] for k, v in listing.items() if k.startswith(p))


def _group_parts(dests):
    """{whole dest: [part dests in order]} for a list of destination names (unsplit files map to themselves)."""
    out = {}
    for d in sorted(dests):
        out.setdefault(re.sub(r"\.part\d+$", "", d), []).append(d)
    return out


def pack(args):
    out = os.path.abspath(args.out)
    files_dir, work = os.path.join(out, "files"), os.path.join(out, "_work")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(files_dir)
    os.makedirs(work)
    today = today_pt(args.today)
    month = today.strftime("%Y-%m")
    txn = f"{today:%Y%m%d}-{secrets.token_hex(3)}"

    history = []
    if args.state_history and os.path.isdir(args.state_history):
        history = [os.path.join(args.state_history, n) for n in sorted(os.listdir(args.state_history)) if n.lower().endswith(".json")]
    state, notes = load_state(args.state, history)
    listing = load_listing(args.dest_listing)
    bad_slot = _slot_mismatch(state, listing)
    if bad_slot:
        raise Blocked(f"the newest weekly copy ({state.get('newest_slot')}) no longer matches its record: {bad_slot}. "
                      "Nothing was copied, so it isn't replaced; a person has to look (reconcile with Keo's OK)")
    lock = take_lock(out, txn, args.lock, listing, args.break_lock)
    base = base_info(args.state, listing)
    legacy_raw = None
    if state.get("migrated_from") == 1 and state.get("seq") == 0:
        with open(args.state, encoding="utf-8-sig") as f:
            legacy_raw = f.read()
    last = state.get("last_good") or {}
    warn = []

    newest = state.get("newest_slot")
    slot = "weekly-2" if newest == "weekly-1" else "weekly-1"
    assert slot != newest
    old = ((state.get("slots") or {}).get(slot) or {}).get("files") or {}
    for whole, rec in old.items():
        for part in rec.get("parts") or [whole]:
            if key(part) not in listing:
                notes.append(f"{slot} no longer matches its last record (an unfinished run rewrote it); "
                             f"{newest or 'the other slot'} is the copy to restore from until this run commits")
                break
        else:
            continue
        break

    if args.recover_month:
        rm = args.recover_month
        entry = (state.get("monthly") or {}).get(rm) or {}
        if rm != month:
            raise Blocked(f"--recover-month {rm}: a recovered copy can only be made during {rm} (today is {today}); "
                          "a copy made now would not hold that month's data")
        if entry.get("status") not in ("needs-recovery", "legacy-unverified"):
            raise Blocked(f"--recover-month {rm}: that month isn't waiting for recovery (status {entry.get('status')!r})")

    git_dir = os.path.abspath(args.mirror) if args.mirror else os.path.join(work, "repo.git")
    if not args.mirror:
        run(["git", "clone", "-q", "--mirror", f"https://github.com/{args.repo}.git", git_dir])

    stats = data_stats(git_dir)
    hold, w = guard(stats, last, today)
    warn += w
    items, verify_existing, taken = [], [], set()
    monthly_plan, archive_plan = {}, {}

    def add(local, dest, kind, expect=None, role=None, extra=None):
        dest = dest.replace("/", "\\")
        if not win_name_ok(dest):
            raise Blocked(f"{dest} is not a safe Windows file name")
        taken.add(key(dest))
        items.append({"local": local, "dest": dest, "kind": kind, "expect": expect, "role": role, **(extra or {})})

    if not hold:
        slot_dir = os.path.join(files_dir, slot)
        os.makedirs(slot_dir)
        # 1) saved data, as a zip anyone can open
        zip_path = os.path.join(slot_dir, "saved-data.zip")
        run(["git", "-C", git_dir, "archive", "--format=zip", "-o", zip_path, "refs/heads/data"])
        bad = check_file(zip_path, "zip", stats["files"])
        if bad:
            hold.append(f"the saved-data zip didn't check out here ({bad})")
        # 2) the live site (it also holds the videos earlier posts point to), and 3) everything else in the repo
        refs = run(["git", "-C", git_dir, "for-each-ref", "--format=%(refname)"]).split()
        if "refs/heads/main" not in refs:
            hold.append("the main branch is missing on GitHub")
        rest = [r for r in refs if r not in ("refs/heads/data", "refs/heads/gh-pages")]
        bundles = [("repo-code.bundle", rest)]
        if "refs/heads/gh-pages" in refs:
            bundles.append(("repo-live-site.bundle", ["refs/heads/gh-pages"]))
        for name, which in bundles:
            path = os.path.join(slot_dir, name)
            run(["git", "-C", git_dir, "bundle", "create", "-q", path] + which)
            run(["git", "-C", git_dir, "bundle", "verify", "-q", path])

    if not hold:
        add(zip_path, f"{slot}\\saved-data.zip", "zip", stats["files"], "weekly")
        for name, _w in bundles:
            add(os.path.join(slot_dir, name), f"{slot}\\{name}", "bundle", None, "weekly")

        # 4) one dated copy of the saved data per month, kept for good and never overwritten
        monthly = state.get("monthly") or {}
        entry = monthly.get(month) or {}
        status = entry.get("status")
        here = _monthly_files_at(listing, f"saved-data-{month}")
        make_fresh, label = False, None
        if status == "verified":
            missing = [d for d, f in (entry.get("files") or {}).items() if listing.get(key(d), (None, -1))[1] != f["bytes"]]
            if missing:
                warn.append(f"monthly copy {month} was verified before but is now missing or changed on the computer: "
                            f"{', '.join(missing)}; it is not remade on its own")
        elif status in ("legacy-unverified", "needs-recovery"):
            if args.recover_month == month:
                make_fresh, label = True, f"saved-data-{month}-recovered-{today.isoformat()}.zip"
            elif here and status == "legacy-unverified":
                for d in here:
                    verify_existing.append({"dest": d, "kind": kind_of(d), "month": month, "bytes": listing[key(d)][1]})
                notes.append(f"monthly copy {month}: recorded by the old script, found on the computer; reading it back to check it")
            else:
                why = entry.get("why") or ("recorded by the old script but not on the computer" if not here else "")
                monthly_plan[month] = {"status": "needs-recovery", "why": why}
                warn.append(f"monthly copy {month} is listed in the backup record but {why or 'did not check out'}; "
                            f"it is NOT rebuilt automatically (a later copy is not the same data). "
                            f"With Keo's OK, run once with --recover-month {month} before the month ends")
        else:
            make_fresh, label = True, f"saved-data-{month}.zip"
            for d in here:   # left by an earlier run that never committed: check it, keep it, never overwrite it
                verify_existing.append({"dest": d, "kind": kind_of(d), "month": month, "bytes": listing[key(d)][1]})
        if make_fresh:
            mdir = os.path.join(files_dir, "monthly")
            os.makedirs(mdir, exist_ok=True)
            dest = free_name(f"monthly\\{label}", listing, taken)
            mpath = os.path.join(mdir, dest.split("\\")[-1])
            shutil.copyfile(zip_path, mpath)
            add(mpath, dest, "zip", stats["files"], "monthly", {"month": month, "recovered": args.recover_month == month})
        prev = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        if (monthly.get(prev) or {}).get("status") != "verified" and prev not in monthly_plan:
            notes.append(f"no verified monthly copy for {prev}")

        # 5) the monthly price archive releases: this month and, until it's final, last month (new name each time)
        archives = state.get("archives") or {}
        for m in (prev, month):
            tag = f"archive-{m}"
            if (archives.get(tag) or {}).get("final"):
                continue
            dest = free_name(f"price-archives-monthly\\{tag}.asof-{today.isoformat()}.tar", listing, taken)
            local = os.path.join(files_dir, "price-archives-monthly", dest.split("\\")[-1])
            n = pack_archive(args.repo, tag, work, local)
            had = (archives.get(tag) or {}).get("files") or 0
            if n is None:
                warn.append(f"{tag}: couldn't read the release files, kept the earlier copy")
            elif n == 0:
                notes.append(f"{tag}: no such release yet")
            elif n < had:
                warn.append(f"{tag}: GitHub has {n} files, the backup has {had}; kept the backup's copy")
                os.remove(local)
            else:
                add(local, dest, "tar", n, "archive", {"tag": tag, "final": m < month})
                archive_plan[tag] = {"files": n, "final": m < month}
        # 6) the raw tcgcsv days never change; say so if GitHub ever holds more than the backup
        counts = release_counts(args.repo)
        if counts is not None:
            raw = sum(c for t, c in counts.items() if t.startswith("tcgcsv-"))
            if state.get("tcgcsv_days") and raw != state["tcgcsv_days"]:
                warn.append(f"GitHub holds {raw} raw price days, the backup holds {state['tcgcsv_days']}: the backup needs a top-up")

    # split anything over the copy limit; every piece gets its own size and checksum, the whole file too
    transfer, wholes = [], {}
    for it in items:
        whole_sha, whole_bytes = sha256(it["local"]), os.path.getsize(it["local"])
        pieces = split_if_big(it["local"])
        wholes[it["dest"]] = {"sha256": whole_sha, "bytes": whole_bytes, "kind": it["kind"], "expect": it["expect"],
                              "role": it["role"], "parts": [], **{k: it[k] for k in ("month", "recovered", "tag", "final") if k in it}}
        for p in pieces:
            d = it["dest"] + p[len(it["local"]):]          # same name, plus .partNN when split
            if not win_name_ok(d):
                raise Blocked(f"{d} is not a safe Windows file name")
            transfer.append({"local": p, "dest": d, "bytes": os.path.getsize(p), "sha256": sha256(p), "whole": it["dest"]})
            wholes[it["dest"]]["parts"].append(d)

    # never overwrite anything outside the slot this run owns
    for t in transfer:
        k = key(t["dest"])
        if k in listing and not k.startswith(key(slot) + "\\"):
            raise Blocked(f"{t['dest']} already exists on the computer; this run would overwrite it")
    planned = {key(t["dest"]) for t in transfer} | {key(f"{slot}\\FILE-LIST.txt")}
    stale = sorted(v[0] for k, v in listing.items() if k.startswith(key(slot) + "\\") and k not in planned)
    if stale and not hold:
        notes.append(f"{len(stale)} older file(s) in {slot} are not part of this copy (FILE-LIST.txt says what is): " + ", ".join(stale))

    # reading back from the computer: batches under the staging limits
    to_read = [(t["dest"], t["bytes"]) for t in transfer] + [(v["dest"], v["bytes"]) for v in verify_existing]
    batches, cur, size = [], [], 0
    for d, b in to_read:
        if cur and (size + b > STAGE_BATCH or len(cur) >= STAGE_FILES):
            batches.append(cur)
            cur, size = [], 0
        cur.append(d)
        size += b
    if cur:
        batches.append(cur)
    guard_paths = [DEST_ROOT + "\\" + LOCK, DEST_ROOT + "\\backup-state.json"]

    verdict = "hold" if hold else "ok"
    total = sum(t["bytes"] for t in transfer)
    if hold:
        summary = "HOLD, nothing copied: " + "; ".join(hold)
    else:
        summary = (f"OK: {len(transfer)} files, {total / 1e6:.0f} MB into {slot}; saved data {stats['files']:,} files, "
                   f"{stats['price_days']} price days (newest {stats['newest_day']})")
    plan = {
        "plan_version": 2, "kind": "backup", "txn": txn, "date": today.isoformat(), "created_at": iso(now_utc()),
        "verdict": verdict, "summary": summary, "lock": lock, "base": base, "guard_paths": guard_paths,
        "hold": hold, "warnings": warn, "notes": notes, "slot": None if hold else slot, "dest_root": DEST_ROOT,
        "transfer": [dict({k: t[k] for k in ("local", "dest", "bytes", "sha256")}, device_path=DEST_ROOT + "\\" + t["dest"])
                     for t in transfer],
        "wholes": wholes, "verify_existing": verify_existing, "stage_batches": batches,
        "stage_paths": [[DEST_ROOT + "\\" + d for d in b] for b in batches] + [guard_paths],
        "stats": stats, "base_state": state, "monthly_plan": monthly_plan, "archive_plan": archive_plan,
        "legacy_raw": legacy_raw,
    }
    write_json(os.path.join(out, "plan.json"), plan)
    shutil.rmtree(work, ignore_errors=True)
    print(summary)
    for x in warn:
        print("WARNING: " + x)
    for x in notes:
        print("note: " + x)
    for t in transfer:
        print(f"  {t['bytes']:>12,}  {t['dest']}")
    print("plan: " + os.path.join(out, "plan.json"))
    return 0


# ---------- step 2: verify what landed ----------

def load_staged(path, root=DEST_ROOT):
    """{key(dest): staged path} from a list of {dest, stagedPath} or device_stage_files' own entries."""
    raw = read_json(path)
    batches = raw if isinstance(raw, list) else [raw]
    entries = []
    for b in batches:          # one device_stage_files result, several of them, or a plain list of entries
        if isinstance(b, dict) and isinstance(b.get("staged"), list):
            entries += b["staged"]
        elif isinstance(b, dict):
            entries.append(b)
    out, rk = {}, key(root)
    for e in entries:
        if not isinstance(e, dict) or not e.get("stagedPath") or e.get("ok") is False:
            continue
        dest = e.get("dest")
        if not dest and e.get("devicePath"):
            dp = key(e["devicePath"])
            if not dp.startswith(rk + "\\"):
                continue
            dest = e["devicePath"].replace("/", "\\")[len(root) + 1:]
        if dest:
            out[key(dest)] = e["stagedPath"]
    return out


def _join(paths, into):
    with open(into, "wb") as o:
        for p in paths:
            with open(p, "rb") as f:
                shutil.copyfileobj(f, o, 1 << 20)


def _check_landed(dest, want_bytes, want_sha, listing, staged):
    k = key(dest)
    if k not in listing:
        return "not on the computer"
    if listing[k][1] != want_bytes:
        return f"size on the computer is {listing[k][1]:,}, expected {want_bytes:,}"
    if k not in staged or not os.path.exists(staged[k]):
        return "not read back from the computer"
    if os.path.getsize(staged[k]) != want_bytes:
        return "read-back copy has the wrong size"
    if want_sha and sha256(staged[k]) != want_sha:
        return "SHA-256 on the computer doesn't match"
    return None


def _landed_listing(dests, listing):
    return {d: [listing[key(d)][1], listing[key(d)][2]] for d in dests if key(d) in listing}


def _new_state(base, txn):
    state = json.loads(json.dumps(base))
    state["version"], state["txn"] = STATE_VERSION, txn
    state["seq"] = int(base.get("seq") or 0) + 1
    state["committed_at"] = iso(now_utc())
    state.pop("integrity", None)
    return state


def _write_commit(out, plan, state, listing, filelist):
    """The record files, in the order they must be written: slot list, old record (once), history copy,
    backup-state.json, and last the lock release."""
    state = seal(state)
    txn = plan["txn"]
    cdir = os.path.join(out, "commit")
    shutil.rmtree(cdir, ignore_errors=True)
    commit = []
    body = (json.dumps(state, indent=1, ensure_ascii=False) + "\n").encode("utf-8")
    legacy_dest = f"{HISTORY}\\backup-state-000000{LEGACY_SUFFIX}"
    if plan.get("legacy_raw") and key(legacy_dest) not in listing:
        lp = os.path.join(cdir, "legacy-v1.json")
        atomic_write(lp, plan["legacy_raw"].encode("utf-8"))
        commit.append({"local": lp, "dest": legacy_dest})          # the old record, kept as it was
    if filelist:
        fl = os.path.join(cdir, "FILE-LIST.txt")
        atomic_write(fl, ("\r\n".join(filelist) + "\r\n").encode("utf-8"))
        commit.append({"local": fl, "dest": f"{plan['slot']}\\FILE-LIST.txt"})
    hist_dest = f"{HISTORY}\\backup-state-{state['seq']:06d}-{txn}.json"
    if key(hist_dest) in listing:
        raise Blocked(f"{hist_dest} already exists on the computer")
    hp = os.path.join(cdir, "history.json")
    atomic_write(hp, body)
    commit.append({"local": hp, "dest": hist_dest})
    sp = os.path.join(cdir, "backup-state.json")
    atomic_write(sp, body)
    commit.append({"local": sp, "dest": "backup-state.json"})
    rl = os.path.join(cdir, "lock-release.json")
    atomic_write(rl, (json.dumps({"lock": "DYS backup", "state": "released", "txn": txn, "released": iso(now_utc())}) + "\n").encode())
    commit.append({"local": rl, "dest": LOCK, "lock": True})
    for c in commit:
        c.update({"bytes": os.path.getsize(c["local"]), "sha256": sha256(c["local"])})
    write_json(os.path.join(out, "commit.json"), {"txn": txn, "seq": state["seq"], "files": commit})
    return commit


def _fail(out, verdict, problems, resend, attempt, extra=None):
    write_json(os.path.join(out, "verify.json"), {"verdict": verdict, "problems": problems, "resend": sorted(resend),
                                                  "attempt": attempt, **(extra or {})})
    print(("RETRY: " if verdict == "retry" else "FAILED: ") + "; ".join(problems))
    if verdict == "retry":
        print("resend: " + ", ".join(sorted(resend)))
    return 4


def verify(args):
    out = os.path.abspath(args.out)
    plan = read_json(os.path.join(out, "plan.json"))
    if plan.get("plan_version") != 2:
        raise Blocked("plan.json is not from this script version")
    listing = load_listing(args.dest_listing)
    staged = load_staged(args.staged) if args.staged else {}
    conflict = guard_checks(plan, listing, staged, "verify")
    if conflict:                                  # someone else is writing: never retry, never record
        return _fail(out, "failed", ["conflict: " + c for c in conflict], set(), args.attempt, {"conflict": True})
    if plan.get("kind") == "reconcile":
        return _verify_reconcile(out, plan, listing, staged, args.attempt)
    problems, resend = [], set()

    for t in plan["transfer"]:
        bad = _check_landed(t["dest"], t["bytes"], t["sha256"], listing, staged)
        if bad:
            problems.append(f"{t['dest']}: {bad}")
            resend.add(t["dest"])

    landed = {}
    with tempfile.TemporaryDirectory() as tmp:
        for whole, w in plan["wholes"].items():
            if any(p in resend for p in w["parts"]):
                continue
            paths = [staged[key(p)] for p in w["parts"]]
            path = paths[0]
            if len(paths) > 1:                        # a split file: join the pieces exactly as a restore would
                path = os.path.join(tmp, "joined")
                _join(paths, path)
            if sha256(path) != w["sha256"] or os.path.getsize(path) != w["bytes"]:
                problems.append(f"{whole}: the joined file doesn't match its checksum")
                resend.update(w["parts"])
                continue
            bad = check_file(path, w["kind"], w["expect"])
            if bad:
                problems.append(f"{whole}: {bad}")        # every piece matched, so the packed file itself is bad
                landed[whole] = "broken-at-source"
                continue
            landed[whole] = {"bytes": w["bytes"], "sha256": w["sha256"], "parts": w["parts"]}
            if len(paths) > 1:
                os.remove(path)

        adopted, kept, why_not = {}, [], {}
        for v in plan["verify_existing"]:
            k = key(v["dest"])
            if k not in listing or k not in staged:
                kept.append(f"{v['dest']} (not read back)")
                continue
            groups = _group_parts([v["dest"]])
            whole = next(iter(groups))
            if whole != v["dest"]:
                bad = "split copies from older runs are only kept, not adopted"
            elif os.path.getsize(staged[k]) != listing[k][1]:
                bad = "read-back copy has the wrong size"
            else:
                bad = check_file(staged[k], v["kind"], None)
            if bad:
                kept.append(f"{v['dest']} ({bad})")
                why_not.setdefault(v["month"], f"its file on the computer didn't check out ({bad})")
            else:
                adopted.setdefault(v["month"], {})[v["dest"]] = {"bytes": listing[k][1], "sha256": sha256(staged[k])}

    attempt = args.attempt
    if problems:
        source_broken = any(v == "broken-at-source" for v in landed.values())
        verdict = "failed" if (attempt >= 2 or source_broken or not resend) else "retry"
        return _fail(out, verdict, problems, resend, attempt)

    # everything checked out at the destination: build the new state
    base = plan["base_state"]
    today, txn, slot, stats = plan["date"], plan["txn"], plan["slot"], plan["stats"]
    state = _new_state(base, txn)
    monthly, archives = state.setdefault("monthly", {}), state.setdefault("archives", {})
    entry = {"date": today, "txn": txn, "verdict": plan["verdict"]}
    seen = _landed_listing([t["dest"] for t in plan["transfer"]], listing)
    if plan["verdict"] == "hold":
        entry["why"] = plan["hold"]
    else:
        files = {}
        for whole, rec in landed.items():
            w = plan["wholes"][whole]
            if w["role"] == "weekly":
                files[whole] = rec
            elif w["role"] == "monthly":
                m = w["month"]
                monthly[m] = {"status": "verified", "made": today, "txn": txn, "data_commit": stats["commit"],
                              "files": {whole: rec}, **({"recovered": True} if w.get("recovered") else {})}
            elif w["role"] == "archive":
                archives[w["tag"]] = {"files": w["expect"], "final": w["final"], "status": "verified",
                                      "dest": whole, "bytes": rec["bytes"], "sha256": rec["sha256"], "made": today}
        for m, found in adopted.items():
            if (monthly.get(m) or {}).get("status") != "verified":
                monthly[m] = {"status": "verified", "made": "before " + today, "txn": txn, "adopted": True, "files": found}
        for m, mp in (plan.get("monthly_plan") or {}).items():
            if (monthly.get(m) or {}).get("status") != "verified":
                monthly[m] = {"status": mp["status"], "why": mp["why"]}
        for v in plan["verify_existing"]:
            m = v["month"]
            if (monthly.get(m) or {}).get("status") == "legacy-unverified":   # it was there but didn't check out
                monthly[m] = {"status": "needs-recovery", "why": why_not.get(m) or "its file on the computer wasn't read back"}
        slot_parts = [p for whole in files for p in files[whole]["parts"]]
        state.setdefault("slots", {})[slot] = {"status": "verified", "txn": txn, "date": today, "data_commit": stats["commit"],
                                               "files": files, "landed": _landed_listing(slot_parts, listing)}
        state["newest_slot"] = slot
        state["last_good"] = {"date": today, **stats}
        entry.update({"slot": slot, "data_commit": stats["commit"], "files": stats["files"], "bytes": stats["bytes"],
                      "price_days": stats["price_days"], "copied_bytes": sum(t["bytes"] for t in plan["transfer"])})
        if kept:
            entry["kept_unverified"] = kept
    if plan["warnings"]:
        entry["warnings"] = plan["warnings"]
    state["runs"] = (list(state.get("runs") or []) + [entry])[-KEEP_RUNS:]

    filelist = None
    if plan["verdict"] == "ok":       # the slot's own list, written after its files checked out
        st = plan["stats"]
        filelist = ["DRIVE YOUR STYLE - DATA BACKUP: THIS WEEK'S COPY",
                    f"Made {today} from GitHub repo {REPO}, run {txn}. Every file below was read back from this computer and matched.",
                    f"Saved data: {st['files']:,} files, {st['bytes']:,} bytes, {st['price_days']} price days "
                    f"(newest {st['newest_day']}), data commit {st['commit']}.",
                    "Columns: SHA-256 checksum, size in bytes, file.", ""]
        filelist += [f"{t['sha256']}  {t['bytes']:12d}  {t['dest']}" for t in plan["transfer"]]
        if any(len(w["parts"]) > 1 for w in plan["wholes"].values()):
            filelist += ["", "Files ending in .part01, .part02... are one file cut into pieces: join them in order to restore.",
                         "Whole-file checksums: " + "; ".join(f"{d} {w['sha256']}" for d, w in plan["wholes"].items() if len(w["parts"]) > 1)]
        filelist += ["", "Only this list and backup-state.json say what this folder holds; anything else here is left from an earlier run."]
    commit = _write_commit(out, plan, state, listing, filelist)
    write_json(os.path.join(out, "verify.json"), {"verdict": "ready", "attempt": attempt, "kept_unverified": kept,
                                                   "adopted": adopted, "landed": seen})
    print(f"READY: every file matched on the computer; write the {len(commit)} files in commit.json in order")
    for c in commit:
        print(f"  {c['bytes']:>12,}  {c['dest']}")
    return 0


# ---------- correcting a record from the files on the computer ----------

def reconcile(args):
    """Plan to correct one weekly slot's record from the files actually there (read back and checked). Copies
    nothing. Only for a slot whose files are intact but whose record lists other checksums (Nov 15, 2026:
    two runs overlapped). Run with Keo's OK; never by the weekly task."""
    out = os.path.abspath(args.out)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    today = today_pt(args.today)
    txn = f"{today:%Y%m%d}-{secrets.token_hex(3)}"
    history = []
    if args.state_history and os.path.isdir(args.state_history):
        history = [os.path.join(args.state_history, n) for n in sorted(os.listdir(args.state_history)) if n.lower().endswith(".json")]
    state, notes = load_state(args.state, history)
    if state.get("migrated_from") == 1 and not state.get("seq"):
        raise Blocked("reconcile needs a version-2 record")
    listing = load_listing(args.dest_listing)
    rec = (state.get("slots") or {}).get(args.slot) or {}
    if rec.get("status") != "verified" or not rec.get("files"):
        raise Blocked(f"{args.slot} has no verified record to correct")
    run = next((r for r in reversed(state.get("runs") or []) if r.get("txn") == rec.get("txn")), {})
    lock = take_lock(out, txn, args.lock, listing, args.break_lock)
    dests = [p for whole, f in rec["files"].items() for p in (f.get("parts") or [whole])]
    sizes = {d: listing[key(d)][1] for d in dests if key(d) in listing}
    missing = [d for d in dests if d not in sizes]
    if missing:
        raise Blocked(f"{', '.join(missing)} not on the computer: nothing to reconcile from")
    batches, cur, size = [], [], 0
    for d in dests:
        if cur and (size + sizes[d] > STAGE_BATCH or len(cur) >= STAGE_FILES):
            batches.append(cur)
            cur, size = [], 0
        cur.append(d)
        size += sizes[d]
    batches.append(cur)
    guard_paths = [DEST_ROOT + "\\" + LOCK, DEST_ROOT + "\\backup-state.json"]
    plan = {"plan_version": 2, "kind": "reconcile", "txn": txn, "date": today.isoformat(), "created_at": iso(now_utc()),
            "verdict": "ok", "slot": args.slot, "summary": f"record of {args.slot} checked against the files on the computer",
            "hold": [], "warnings": [], "notes": notes, "transfer": [], "wholes": {}, "verify_existing": [],
            "lock": lock, "base": base_info(args.state, listing), "guard_paths": guard_paths, "base_state": state,
            "stage_paths": [[DEST_ROOT + "\\" + d for d in b] for b in batches] + [guard_paths],
            "expect_files": run.get("files"), "stats": state.get("last_good") or {}}
    write_json(os.path.join(out, "plan.json"), plan)
    print(f"RECONCILE PLAN: read back {len(dests)} file(s) of {args.slot}; nothing is copied")
    return 0


def _verify_reconcile(out, plan, listing, staged, attempt):
    slot = plan["slot"]
    state = _new_state(plan["base_state"], plan["txn"])
    rec = state["slots"][slot]
    problems, changed = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for whole, f in rec["files"].items():
            parts = f.get("parts") or [whole]
            if any(key(p) not in staged or key(p) not in listing or os.path.getsize(staged[key(p)]) != listing[key(p)][1] for p in parts):
                problems.append(f"{whole}: not read back intact")
                continue
            path = staged[key(parts[0])]
            if len(parts) > 1:
                path = os.path.join(tmp, "joined")
                _join([staged[key(p)] for p in parts], path)
            kind = kind_of(whole)
            bad = check_file(path, kind, plan.get("expect_files") if kind == "zip" else None)
            if bad:
                problems.append(f"{whole}: {bad}")
                continue
            digest, size = sha256(path), os.path.getsize(path)
            if digest != f["sha256"] or size != f["bytes"]:
                changed.append(whole)
                f["reconciled"] = {"date": plan["date"], "txn": plan["txn"], "was_sha256": f["sha256"], "was_bytes": f["bytes"]}
                f["sha256"], f["bytes"] = digest, size
    if problems:
        return _fail(out, "failed", problems, set(), attempt)
    parts = [p for whole, f in rec["files"].items() for p in (f.get("parts") or [whole])]
    rec["landed"] = _landed_listing(parts, listing)
    state["runs"] = (list(state.get("runs") or []) + [{"date": plan["date"], "txn": plan["txn"], "verdict": "reconciled",
                                                       "slot": slot, "changed": changed}])[-KEEP_RUNS:]
    filelist = ["DRIVE YOUR STYLE - DATA BACKUP: THIS WEEK'S COPY (RECORD CORRECTED)",
                f"Copy made {rec.get('date')} by run {rec.get('txn')}, data commit {rec.get('data_commit')}. "
                f"On {plan['date']} run {plan['txn']} read every file below back from this computer, checked that it opens, "
                f"and recorded its checksum.",
                "Columns: SHA-256 checksum, size in bytes, file.", ""]
    filelist += [f"{f['sha256']}  {f['bytes']:12d}  {whole}" for whole, f in rec["files"].items()]
    if changed:
        filelist += ["", "Corrected: " + ", ".join(changed) + " (two backup runs overlapped and the later one rewrote it; "
                     "the file was checked and is complete)."]
    filelist += ["", "Only this list and backup-state.json say what this folder holds; anything else here is left from an earlier run."]
    commit = _write_commit(out, plan, state, listing, filelist)
    write_json(os.path.join(out, "verify.json"), {"verdict": "ready", "attempt": attempt, "changed": changed,
                                                   "landed": _landed_listing(parts, listing)})
    print(f"READY: {len(rec['files'])} file(s) of {slot} checked; {len(changed)} record entr{'y' if len(changed) == 1 else 'ies'} to correct; "
          f"write the {len(commit)} files in commit.json in order")
    return 0


# ---------- step 3: confirm the record landed ----------

def confirm(args):
    out = os.path.abspath(args.out)
    plan = read_json(os.path.join(out, "plan.json"))
    commit = read_json(os.path.join(out, "commit.json"))
    landed = read_json(os.path.join(out, "verify.json")).get("landed") or {}
    listing = load_listing(args.dest_listing)
    staged = load_staged(args.staged) if args.staged else {}
    problems, ok = [], set()
    for c in commit["files"]:
        bad = _check_landed(c["dest"], c["bytes"], c["sha256"], listing, staged)
        if bad:
            problems.append(f"{c['dest']}: {bad}")
        else:
            ok.add(c["dest"])
    state_copies = [c["dest"] for c in commit["files"]
                    if c["dest"] == "backup-state.json" or (c["dest"].startswith(HISTORY) and not c["dest"].endswith(LEGACY_SUFFIX))]
    if not any(d in ok for d in state_copies):
        # neither copy of the new state is intact: this run is not recorded (the earlier state still stands)
        write_json(os.path.join(out, "confirm.json"), {"verdict": "failed", "problems": problems, "committed": False})
        print("DYS backup FAILED: the backup record didn't save (" + "; ".join(problems) + "); "
              "the files were copied and checked, but the next run will treat them as not done")
        return 5
    rewritten = [d for d, (size, mtime) in landed.items()
                 if key(d) not in listing or listing[key(d)][1] != size or (mtime is not None and listing[key(d)][2] != mtime)]
    if rewritten:
        write_json(os.path.join(out, "confirm.json"), {"verdict": "failed", "problems": problems, "committed": True, "rewritten": rewritten})
        print("DYS backup FAILED: these files changed on the computer after they were checked, so the record may not match them: "
              + ", ".join(rewritten) + ". The next run will refuse to start until a person looks")
        return 5
    warnings = list(plan["warnings"])
    for p in problems:
        if p.startswith(LOCK):
            warnings.append(f"backup.lock wasn't released ({p}); it lapses at {plan['lock']['expires']}")
        else:
            warnings.append(f"{p} (the run is still recorded: the other state copy is intact)")
    write_json(os.path.join(out, "confirm.json"), {"verdict": "ok", "committed": True, "problems": problems})
    head = "DYS backup HELD: " if plan["verdict"] == "hold" else "DYS backup OK: "
    print(head + plan["summary"] + ("" if not warnings else " | WARNINGS: " + "; ".join(warnings)))
    return 0


# ---------- audit: every recorded file against its checksum (read-only) ----------

def recorded_files(state):
    """{whole dest: (bytes, sha256, [parts], kind)} for every file the record calls verified."""
    out = {}
    for slot, rec in (state.get("slots") or {}).items():
        if rec.get("status") == "verified":
            for whole, f in (rec.get("files") or {}).items():
                out[whole] = (f["bytes"], f["sha256"], f.get("parts") or [whole])
    for m, rec in (state.get("monthly") or {}).items():
        if rec.get("status") == "verified":
            for whole, f in (rec.get("files") or {}).items():
                out[whole] = (f["bytes"], f["sha256"], f.get("parts") or [whole])
    for tag, rec in (state.get("archives") or {}).items():
        if rec.get("status") == "verified" and rec.get("dest"):
            out[rec["dest"]] = (rec["bytes"], rec["sha256"], [rec["dest"]])
    return out


def audit(args):
    """--plan: print the files to read back (as batches of computer paths). Otherwise check them all."""
    state = read_json(args.state)
    if not intact(state):
        print("AUDIT FAILED: backup-state.json doesn't match its own checksum")
        return 4
    files = recorded_files(state)
    listing = load_listing(args.dest_listing)
    if args.plan:
        batches, cur, size = [], [], 0
        for whole, (b, _sha, parts) in sorted(files.items()):
            for part in parts:
                sz = listing.get(key(part), (None, 0))[1]
                if cur and (size + sz > STAGE_BATCH or len(cur) >= STAGE_FILES):
                    batches.append(cur)
                    cur, size = [], 0
                cur.append(DEST_ROOT + "\\" + part)
                size += sz
        if cur:
            batches.append(cur)
        print(json.dumps(batches))
        return 0
    staged = load_staged(args.staged)
    bad = []
    with tempfile.TemporaryDirectory() as tmp:
        for whole, (b, sha, parts) in sorted(files.items()):
            if any(key(p) not in listing or key(p) not in staged for p in parts):
                bad.append(f"{whole}: missing or not read back")
                continue
            path = staged[key(parts[0])]
            if len(parts) > 1:
                path = os.path.join(tmp, "joined")
                _join([staged[key(p)] for p in parts], path)
            if os.path.getsize(path) != b or sha256(path) != sha:
                bad.append(f"{whole}: doesn't match its recorded checksum")
                continue
            problem = check_file(path, kind_of(whole), None)
            if problem:
                bad.append(f"{whole}: {problem}")
            else:
                print(f"  match  {b:>12,}  {whole}")
    if bad:
        print("AUDIT FAILED: " + "; ".join(bad))
        return 4
    print(f"AUDIT OK: all {len(files)} recorded files match their checksums and open")
    return 0


# ---------- command line ----------

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("pack", "guard", "verify", "confirm", "reconcile", "audit"):
        print("FAILED: backup_pack.py now runs in steps (pack, guard, verify, confirm) and records nothing until the copy "
              "is checked on the computer. The task needs the prompt in tools/BACKUP-TASK.md; nothing was done.")
        return 2
    ap = argparse.ArgumentParser(prog="backup_pack.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("pack", "reconcile"):
        p = sub.add_parser(name)
        p.add_argument("--out", required=True)
        p.add_argument("--state", required=True)
        p.add_argument("--state-history", default="")
        p.add_argument("--dest-listing", required=True)
        p.add_argument("--lock", default="", help="backup.lock as read back from the computer (if it is there)")
        p.add_argument("--break-lock", default="", help="with Keo's OK only: the run id of an abandoned lock to take over")
        p.add_argument("--today", default="")
        if name == "pack":
            p.add_argument("--repo", default=REPO)
            p.add_argument("--mirror", default="", help="use this existing mirror clone instead of cloning (tests)")
            p.add_argument("--recover-month", default="", help="with Keo's OK only: remake a recorded-but-missing monthly copy")
        else:
            p.add_argument("--slot", required=True, choices=SLOTS)
    a = sub.add_parser("audit")
    a.add_argument("--out", default=".")
    a.add_argument("--state", required=True)
    a.add_argument("--dest-listing", required=True)
    a.add_argument("--staged", default="")
    a.add_argument("--plan", action="store_true")
    g = sub.add_parser("guard")
    g.add_argument("--out", required=True)
    g.add_argument("--dest-listing", required=True)
    g.add_argument("--staged", default="")
    g.add_argument("--phase", required=True, choices=("start", "commit", "release"))
    for name in ("verify", "confirm"):
        q = sub.add_parser(name)
        q.add_argument("--out", required=True)
        q.add_argument("--dest-listing", required=True)
        q.add_argument("--staged", default="")
        q.add_argument("--attempt", type=int, default=1)
    args = ap.parse_args(argv)
    try:
        return {"pack": pack, "guard": guard_cmd, "verify": verify, "confirm": confirm, "reconcile": reconcile, "audit": audit}[args.cmd](args)
    except Blocked as e:
        print("BLOCKED: " + str(e))
        try:
            write_json(os.path.join(os.path.abspath(args.out), f"{args.cmd}-blocked.json"), {"verdict": "blocked", "why": str(e)})
        except OSError:
            pass
        return 3
    except OSError as e:
        print(f"FAILED: {args.cmd} stopped on a file error ({e.strerror or e}); nothing was recorded")
        return 1


if __name__ == "__main__":
    sys.exit(main())
