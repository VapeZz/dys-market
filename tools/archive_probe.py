"""One-off test: can this runner download ONE tcgcsv daily price archive, and what is inside it?

    PROBE_DAY=2025-11-11 python tools/archive_probe.py

Makes two requests to tcgcsv: last-updated.txt (the endpoint the nightly job already uses) and one
archive file. Saves nothing to the data branch and never fails the job: the answer is the RESULT line.
The downloaded file is left in probe-out/ so the workflow can keep it (tcgcsv asks that an archive is
never downloaded twice).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import config  # noqa: E402

DAY = os.environ.get("PROBE_DAY", "2025-11-11")
OUT = os.path.join(ROOT, "probe-out")
KEEP_HEADERS = ("content-length", "content-type", "server", "via", "x-cache", "x-amz-cf-pop", "cf-ray", "cf-mitigated", "retry-after")


def say(line):
    print(line, flush=True)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n\n")


def request(url):
    """(status, headers, body bytes or None, error text or None)."""
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return resp.status, dict(resp.headers), resp.read(), None
    except urllib.error.HTTPError as err:
        body = err.read()[:600].decode("utf-8", "replace")
        return err.code, dict(err.headers or {}), None, body
    except Exception as err:  # noqa: BLE001  (a network error is an answer too)
        return 0, {}, None, f"{type(err).__name__}: {err}"


def shown(headers):
    low = {k.lower(): v for k, v in headers.items()}
    return {k: low[k] for k in KEEP_HEADERS if k in low}


def main():
    say(f"Archive probe for {DAY}, User-Agent: {config.USER_AGENT}")

    status, headers, body, err = request(f"{config.BASE_URL}/last-updated.txt")
    say(f"daily endpoint (last-updated.txt): HTTP {status} {(body or b'').decode('utf-8', 'replace').strip()[:40]} {err or ''}".rstrip())

    url = f"{config.BASE_URL}/archive/tcgplayer/prices-{DAY}.ppmd.7z"
    status, headers, body, err = request(url)
    say(f"archive {url}: HTTP {status} {json.dumps(shown(headers))}")
    if status != 200 or not body:
        say(f"error body: {err}")
        say(f"RESULT: BLOCKED (HTTP {status}) for the archive from this runner")
        print(f"::notice title=Archive probe::BLOCKED, HTTP {status}")
        return

    os.makedirs(OUT, exist_ok=True)
    archive = os.path.join(OUT, f"prices-{DAY}.ppmd.7z")
    with open(archive, "wb") as f:
        f.write(body)
    say(f"downloaded {len(body) / 1e6:.2f} MB")

    work = tempfile.mkdtemp(prefix="dys-probe-")
    try:
        done = subprocess.run(["7z", "x", "-y", f"-o{work}", archive], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if done.returncode != 0:
            say(f"RESULT: DOWNLOADED but 7z could not open it: {done.stderr.decode('utf-8', 'replace')[:300]}")
            print("::notice title=Archive probe::downloaded, extract failed")
            return
        label = {str(g["category"]): g["label"] for g in config.GAMES}
        stats = {c: {"sets": 0, "rows": 0, "market": 0, "low": 0, "mid": 0} for c in label}
        other_cats = set()
        for dirpath, _dirs, files in os.walk(work):
            if "prices" not in files:
                continue
            parts = dirpath.replace("\\", "/").rstrip("/").split("/")
            cat = parts[-2] if len(parts) >= 2 else ""
            if cat not in stats:
                other_cats.add(cat)
                continue
            try:
                with open(os.path.join(dirpath, "prices"), encoding="utf-8") as f:
                    rows = json.load(f).get("results", [])
            except (OSError, ValueError):
                continue
            s = stats[cat]
            s["sets"] += 1
            s["rows"] += len(rows)
            for row in rows:
                for field, key in (("marketPrice", "market"), ("lowPrice", "low"), ("midPrice", "mid")):
                    try:
                        if float(row.get(field)) > 0:
                            s[key] += 1
                    except (TypeError, ValueError):
                        pass
        say("| Game | Sets with prices | Price rows | With market price | With lowest listing | With mid listing |")
        say("|---|---|---|---|---|---|")
        total = 0
        for cat, s in stats.items():
            total += s["market"]
            say(f"| {label[cat]} | {s['sets']} | {s['rows']} | {s['market']} | {s['low']} | {s['mid']} |")
        say(f"other categories in the archive (not on the site): {len(other_cats)}")
        say(f"RESULT: OK, {total} market prices for the site's games on {DAY}")
        print(f"::notice title=Archive probe::OK, {total} market prices on {DAY}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
