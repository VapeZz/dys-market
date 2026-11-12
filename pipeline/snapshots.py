"""Daily price snapshots: one gzip JSON per date, {"pid:subtype": cents}.

Days before config.SEALED_BEFORE hold price history filled in from PokemonPriceTracker, which we may
store but not publish, so those files are encrypted (<day>.json.gz.enc, see sealed.py). Everything
here reads and writes both kinds; reading a sealed day without the key gives an empty snapshot.

Separate from those: data/history/<day>.json.gz holds days before SEALED_BEFORE rebuilt from tcgcsv's
own daily archives (tools/history_build.py). That is TCGplayer data like our nightly snapshots, with
nothing from PokemonPriceTracker in it, so the site may show it. It is never sealed and never mixed
into the snapshot files. The site reads days through site_days() and view(); the functions that
manage the snapshot files themselves (load, save, seal_old ...) are unchanged.
"""
import gzip
import json
import os
from datetime import date, timedelta

import config
import sealed

SNAP_DIR = os.path.join(config.DATA_DIR, "snapshots")
HIST_DIR = os.path.join(config.DATA_DIR, "history")
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


def _hist(day):
    return os.path.join(HIST_DIR, f"{day}.json.gz")


def history_days():
    if not os.path.isdir(HIST_DIR):
        return []
    return sorted({f[:10] for f in os.listdir(HIST_DIR) if f.endswith(".json.gz")})


def has_history(day):
    return os.path.exists(_hist(day))


def save_history(day, snap):
    """A day rebuilt from tcgcsv's archive. Only for days before our own tracking started."""
    if SEALED_BEFORE and day >= SEALED_BEFORE:
        raise ValueError(f"{day} is covered by our own nightly snapshots")
    os.makedirs(HIST_DIR, exist_ok=True)
    tmp = _hist(day) + ".tmp"
    with open(tmp, "wb") as f:
        f.write(gzip.compress(json.dumps(snap, separators=(",", ":")).encode("utf-8")))
    os.replace(tmp, _hist(day))


def load_history(day):
    if not os.path.exists(_hist(day)):
        return {}
    with gzip.open(_hist(day), "rt", encoding="utf-8") as f:
        return json.load(f)


def site_days():
    """Every day the site may show: our own snapshots plus the days rebuilt from tcgcsv's archives."""
    return sorted(set(available()) | set(history_days()))


def view(day):
    """Prices the site may show for one day. For a day before SEALED_BEFORE that is the tcgcsv rebuild;
    the PokemonPriceTracker-filled snapshot is added only on its Business plan, and only where the
    rebuild has no price."""
    snap = load_history(day)
    if not protected(day) or getattr(config, "PPT_BUSINESS_PLAN", True):
        for k, v in load(day).items():
            snap.setdefault(k, v)
    return snap


def keep_days(days, today, monthly=False):
    """Which of `days` the retention rule keeps: every day for KEEP_DAILY_DAYS, then the newest day of each
    week up to KEEP_WEEKLY_DAYS; with monthly=True, the newest day of each month after that."""
    t = date.fromisoformat(today)
    keep, weeks, months = set(), set(), set()
    for day in sorted(days, reverse=True):      # newest first, so the latest day of each old week or month wins
        d = date.fromisoformat(day)
        age = (t - d).days
        if age <= config.KEEP_DAILY_DAYS:
            keep.add(day)
        elif age <= config.KEEP_WEEKLY_DAYS:
            if d.isocalendar()[:2] not in weeks:
                weeks.add(d.isocalendar()[:2])
                keep.add(day)
        elif monthly and (d.year, d.month) not in months:
            months.add((d.year, d.month))
            keep.add(day)
    return keep


def prune_history(today):
    """Same thinning as the snapshots, plus one day a month kept for good (a few files a year), so the
    site's "All" view keeps reaching back to the first archive."""
    days = history_days()
    keep = keep_days(days, today, monthly=True)
    removed = 0
    for day in days:
        if day not in keep:
            os.remove(_hist(day))
            removed += 1
    return removed


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
