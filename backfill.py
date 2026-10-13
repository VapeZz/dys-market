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
            log(f"backfill {day}: not available ({err})")
            return False
        subprocess.run(["7z", "x", "-y", f"-o{work}", archive],
                       check=True, stdout=subprocess.DEVNULL)
        snap = {}
        for cat in CATS:
            base = os.path.join(work, day, cat)
            if not os.path.isdir(base):
                continue
            for gid in os.listdir(base):
                pfile = os.path.join(base, gid, "prices")
                if os.path.exists(pfile):
                    with open(pfile, encoding="utf-8") as f:
                        for row in json.load(f).get("results", []):
                            tcgcsv.add_price(snap, row)
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
    for d in days:
        backfill_day(d)


if __name__ == "__main__":
    main(sys.argv[1:])
