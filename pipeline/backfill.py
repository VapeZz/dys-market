"""One-time backfill of past price snapshots from TCGCSV's daily archives
(available from 2024-02-08), so movers work from day one.

Usage:  python pipeline/backfill.py            # default: 7, 30, 90, 180, 365 days ago + last 14 days
        python pipeline/backfill.py 2026-01-01 2026-02-01
Needs 7-Zip on PATH (`7z`). GitHub's Ubuntu runners have it.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import date, timedelta

import config
import snapshots
import tcgcsv

CATS = {str(g["category"]) for g in config.GAMES}


def default_dates(today):
    t = date.fromisoformat(today)
    days = set(range(1, 15)) | {30, 60, 90, 180, 365}
    return sorted((t - timedelta(days=n)).isoformat() for n in days)


def backfill_day(day, log=print):
    if snapshots.exists(day):
        log(f"backfill {day}: already have it")
        return True
    url = f"{config.BASE_URL}/archive/tcgplayer/prices-{day}.ppmd.7z"
    work = tempfile.mkdtemp(prefix="dys-backfill-")
    try:
        archive = os.path.join(work, "prices.7z")
        req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp, open(archive, "wb") as f:
                shutil.copyfileobj(resp, f)
        except Exception as err:
            log(f"backfill {day}: download failed ({type(err).__name__}: {err})")
            return False
        log(f"backfill {day}: downloaded {os.path.getsize(archive) // 1024} KB")
        subprocess.run(["7z", "x", "-y", f"-o{work}", archive],
                       check=True, stdout=subprocess.DEVNULL)
        snap = {}
        found = 0
        for dirpath, _dirs, files in os.walk(work):
            if "prices" not in files:
                continue
            parts = dirpath.replace("\\", "/").rstrip("/").split("/")
            if len(parts) < 2 or parts[-2] not in CATS:
                continue
            found += 1
            with open(os.path.join(dirpath, "prices"), encoding="utf-8") as f:
                try:
                    rows = json.load(f).get("results", [])
                except json.JSONDecodeError:
                    continue
            for row in rows:
                tcgcsv.add_price(snap, row)
        if not found:
            sample = []
            for dirpath, _dirs, files in os.walk(work):
                sample.append(os.path.relpath(dirpath, work))
                if len(sample) > 8:
                    break
            log(f"backfill {day}: no price files for tracked games; archive layout sample: {sample}")
        if snap:
            snapshots.save(day, snap)
            log(f"backfill {day}: {len(snap)} prices")
            return True
        log(f"backfill {day}: archive had no prices for tracked games")
        return False
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv):
    today = date.today().isoformat()
    days = argv or default_dates(today)
    os.makedirs(config.DATA_DIR, exist_ok=True)
    log_path = os.path.join(config.DATA_DIR, "backfill-log.txt")
    with open(log_path, "w", encoding="utf-8") as logf:
        def log(msg):
            print(msg, flush=True)
            logf.write(msg + "\n")
            logf.flush()
        ok = 0
        for d in days:
            try:
                ok += bool(backfill_day(d, log))
            except Exception as err:  # keep going; record why
                log(f"backfill {d}: error ({type(err).__name__}: {err})")
        log(f"backfill done: {ok}/{len(days)} days saved")


if __name__ == "__main__":
    main(sys.argv[1:])
