"""Daily price snapshots: one gzip JSON per date, {"pid:subtype": cents}.

Days before config.SEALED_BEFORE hold price history filled in from PokemonPriceTracker, which we may
store but not publish, so those files are encrypted (<day>.json.gz.enc, see sealed.py). Everything
here reads and writes both kinds; reading a sealed day without the key gives an empty snapshot.
"""
import gzip
import json
import os
from datetime import date, timedelta

import config
import sealed

SNAP_DIR = os.path.join(config.DATA_DIR, "snapshots")
SEALED_BEFORE = getattr(config, "SEALED_BEFORE", "")
_warned = []


def _plain(day):
    return os.path.join(SNAP_DIR, f"{day}.json.gz")


def _sealed(day):
    return _plain(day) + ".enc"


def path_for(day):
    return _sealed(day) if os.path.exists(_sealed(day)) else _plain(day)


def exists(day):
    return os.path.exists(_plain(day)) or os.path.exists(_sealed(day))


def protected(day):
    return bool(SEALED_BEFORE) and day < SEALED_BEFORE


def save(day, snap):
    os.makedirs(SNAP_DIR, exist_ok=True)
    raw = gzip.compress(json.dumps(snap, separators=(",", ":")).encode("utf-8"))
    if protected(day):
        sealed.write("ppt", _sealed(day), raw)          # raises sealed.Locked without the key: never store these in the clear
        if os.path.exists(_plain(day)):
            os.remove(_plain(day))
        return
    tmp = _plain(day) + ".tmp"
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, _plain(day))


def load(day):
    snap = {}
    if os.path.exists(_sealed(day)):
        try:
            snap = json.loads(gzip.decompress(sealed.read("ppt", _sealed(day))))
        except sealed.Locked as e:
            if not _warned:
                print(f"::warning title=Price history::older price history is encrypted and can't be read here ({e})")
                _warned.append(1)
    if os.path.exists(_plain(day)):
        with gzip.open(_plain(day), "rt", encoding="utf-8") as f:
            for k, v in json.load(f).items():
                snap.setdefault(k, v)
    return snap


def _days():
    if not os.path.isdir(SNAP_DIR):
        return []
    return sorted({f[:10] for f in os.listdir(SNAP_DIR) if f.endswith(".json.gz") or f.endswith(".json.gz.enc")})


def available():
    """Days the site may use. The PokemonPriceTracker-filled days count only on its Business plan."""
    days = _days()
    return days if getattr(config, "PPT_BUSINESS_PLAN", True) else [d for d in days if not protected(d)]


def seal_old():
    """Encrypt any day before SEALED_BEFORE still stored in the clear, and re-seal days that only open with an
    old key. Safe to run every night; does nothing without the key."""
    if not SEALED_BEFORE or not sealed.can_seal("ppt"):
        return 0
    n = 0
    for day in _days():
        if not protected(day):
            break
        restale = False
        if os.path.exists(_sealed(day)):
            try:
                with open(_sealed(day), "rb") as f:
                    restale = sealed.unseal("ppt", f.read())[1]
            except sealed.Locked:
                continue        # sealed with a key we no longer have: leave it untouched (it opens again if that key is restored)
        if os.path.exists(_plain(day)) or restale:
            save(day, load(day))
            n += 1
    return n


def prune(today):
    """Keep every day for KEEP_DAILY_DAYS, then the newest snapshot of each week up to KEEP_WEEKLY_DAYS."""
    t = date.fromisoformat(today)
    removed = 0
    kept_weeks = set()
    for day in reversed(_days()):  # newest first, so we keep the latest day of each old week
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
            for p in (_plain(day), _sealed(day)):
                if os.path.exists(p):
                    os.remove(p)
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
