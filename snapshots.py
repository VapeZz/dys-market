"""Daily price snapshots: one gzip JSON per date, {"pid:subtype": cents}."""
import gzip
import json
import os
from datetime import date, timedelta

import config

SNAP_DIR = os.path.join(config.DATA_DIR, "snapshots")


def path_for(day):
    return os.path.join(SNAP_DIR, f"{day}.json.gz")


def exists(day):
    return os.path.exists(path_for(day))


def save(day, snap):
    os.makedirs(SNAP_DIR, exist_ok=True)
    tmp = path_for(day) + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(snap, f, separators=(",", ":"))
    os.replace(tmp, path_for(day))


def load(day):
    with gzip.open(path_for(day), "rt", encoding="utf-8") as f:
        return json.load(f)


def available():
    if not os.path.isdir(SNAP_DIR):
        return []
    return sorted(f[:10] for f in os.listdir(SNAP_DIR) if f.endswith(".json.gz"))


def prune(today):
    """Keep every day for KEEP_DAILY_DAYS, then the newest snapshot of each week up to KEEP_WEEKLY_DAYS."""
    t = date.fromisoformat(today)
    removed = 0
    kept_weeks = set()
    for day in reversed(available()):  # newest first, so we keep the latest day of each old week
        d = date.fromisoformat(day)
        age = (t - d).days
        week = d.isocalendar()[:2]
        if age <= config.KEEP_DAILY_DAYS:
            keep = True
        elif age <= config.KEEP_WEEKLY_DAYS and week not in kept_weeks:
            keep = True
            kept_weeks.add(week)
        else:
            keep = False
        if not keep:
            os.remove(path_for(day))
            removed += 1
    return removed


def closest_on_or_before(days, target, tolerance=4):
    """Latest available date <= target, within `tolerance` days of it."""
    best = None
    for d in days:
        if d <= target:
            best = d
        else:
            break
    if best is None:
        return None
    gap = (date.fromisoformat(target) - date.fromisoformat(best)).days
    return best if gap <= tolerance else None


def minus_days(day, n):
    return (date.fromisoformat(day) - timedelta(days=n)).isoformat()
