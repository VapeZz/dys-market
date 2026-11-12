"""Turn the stored tcgcsv archives into the site's price history for the days before our own tracking.

    python tools/history_build.py            # build whatever the retention rule wants and is missing
    python tools/history_build.py 2025-11-11 # build these days only

Every tcgcsv daily archive from 2024-02-08 up to the day before config.SEALED_BEFORE is already stored
in this repo's "tcgcsv-<year>" releases (tools/history_pull.py downloaded each one once). This reads
them from there, never from tcgcsv, and writes data/history/<day>.json.gz in the same shape as a nightly
snapshot ({"productId:printing": cents}, TCGplayer market price, the site's games only).

Which days: the same thinning the snapshots use (every day for KEEP_DAILY_DAYS, then one a week up to
KEEP_WEEKLY_DAYS) plus one day a month before that. Days already built are skipped, so after the first
run this does next to nothing. Nothing from PokemonPriceTracker is read or written here.

Settings (environment): HISTORY_MAX = most days to build in one run (default all),
HISTORY_TODAY = pretend today is this date (tests), HISTORY_REPO = owner/repo holding the releases.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date, timedelta, timezone, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import config  # noqa: E402
import snapshots  # noqa: E402
import tcgcsv  # noqa: E402

REPO = os.environ.get("HISTORY_REPO") or os.environ.get("GITHUB_REPOSITORY") or "VapeZz/dys-market"
FIRST_ARCHIVE = "2024-02-08"
CATS = {str(g["category"]) for g in config.GAMES}
MAGIC = b"7z\xbc\xaf\x27\x1c"


def all_archive_days():
    last = date.fromisoformat(config.SEALED_BEFORE) - timedelta(days=1)
    d, out = date.fromisoformat(FIRST_ARCHIVE), []
    while d <= last:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def wanted_days(today):
    return sorted(snapshots.keep_days(all_archive_days(), today, monthly=True))


def fetch_archive(day, dest):
    """Download one stored archive from our own release. True when it is a real 7z file."""
    url = f"https://github.com/{REPO}/releases/download/tcgcsv-{day[:4]}/prices-{day}.ppmd.7z"
    req = urllib.request.Request(url, headers={"User-Agent": "dys-market-history-build"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=300) as resp, open(dest, "wb") as f:
                shutil.copyfileobj(resp, f)
            with open(dest, "rb") as f:
                return f.read(6) == MAGIC
        except urllib.error.HTTPError as err:
            if err.code == 404:
                return False
            time.sleep(5 * (attempt + 1))
        except Exception:  # noqa: BLE001
            time.sleep(5 * (attempt + 1))
    return False


def extract(archive, work):
    """Unpack the price files of the site's games. Uses the 7z program when there is one, else py7zr."""
    if shutil.which("7z"):
        subprocess.run(["7z", "x", "-y", f"-o{work}", archive], check=True, stdout=subprocess.DEVNULL)
        return
    import py7zr
    with py7zr.SevenZipFile(archive) as z:
        names = [n for n in z.getnames() if n.endswith("/prices") and len(n.split("/")) >= 3 and n.split("/")[-3] in CATS]
    with py7zr.SevenZipFile(archive) as z:
        z.extract(path=work, targets=names)


def snapshot_from(work):
    snap, sets = {}, 0
    for dirpath, _dirs, files in os.walk(work):
        if "prices" not in files:
            continue
        parts = dirpath.replace("\\", "/").rstrip("/").split("/")
        if len(parts) < 2 or parts[-2] not in CATS:
            continue
        try:
            with open(os.path.join(dirpath, "prices"), encoding="utf-8") as f:
                rows = json.load(f).get("results", [])
        except (OSError, ValueError):
            continue
        sets += 1
        for row in rows:
            tcgcsv.add_price(snap, row)
    return snap, sets


def build_day(day):
    """(number of prices, note). 0 prices means the day was not built."""
    work = tempfile.mkdtemp(prefix="dys-history-")
    try:
        archive = os.path.join(work, "prices.7z")
        if not fetch_archive(day, archive):
            return 0, "archive not in our releases"
        out = os.path.join(work, "x")
        os.makedirs(out)
        extract(archive, out)
        snap, sets = snapshot_from(out)
        if len(snap) < 1000:
            return 0, f"only {len(snap)} prices in {sets} sets, not saved"
        snapshots.save_history(day, snap)
        return len(snap), f"{sets} sets"
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv):
    today = os.environ.get("HISTORY_TODAY") or datetime.now(timezone.utc).date().isoformat()
    limit = int(os.environ.get("HISTORY_MAX") or 0)
    want = [d for d in argv if len(d) == 10] or wanted_days(today)
    have = set(snapshots.history_days())
    todo = sorted((d for d in want if d not in have), reverse=True)      # newest first: recent days matter most
    print(f"history: {len(want)} days wanted, {len(want) - len(todo)} already built, {len(todo)} to build"
          + (f" (this run: at most {limit})" if limit else ""), flush=True)
    built, failed, t0 = 0, [], time.time()
    for day in todo:
        if limit and built >= limit:
            break
        n, note = build_day(day)
        if n:
            built += 1
            if built <= 3 or built % 20 == 0:
                print(f"history {day}: {n} prices, {note} ({built} built, {time.time() - t0:.0f}s)", flush=True)
        else:
            failed.append(day)
            print(f"::warning title=Price history::{day} not built: {note}", flush=True)
            if len(failed) >= 5 and built == 0:
                print("::warning title=Price history::the first 5 days all failed; stopping", flush=True)
                break
    left = len(todo) - built - len(failed)
    days = snapshots.history_days()
    line = (f"history: built {built} days in {time.time() - t0:.0f}s; {len(days)} on hand"
            + (f" ({days[0]} to {days[-1]})" if days else "") + f"; failed {len(failed)}; left for later {max(left, 0)}")
    print(line, flush=True)
    print(f"::notice title=Price history::{line}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
