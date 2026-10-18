"""Slab price snapshot storage and daily fetch.

Saves daily eBay sold comps for graded cards (PSA / BGS / CGC) to
  data/slabs/YYYY-MM-DD.json

Each snapshot is a dict:
  {
    "date": "2026-10-18",
    "cards": {
      "<game_slug>:<card_key>": {
        "name": "Charizard",
        "set": "Base Set",
        "game": "pokemon",
        "PSA": {"count": 12, "median": 420.00, "mean": 438.50, "low": 310.00, "high": 720.00, "as_of": "2026-10-18"},
        "BGS": { ... },
        "CGC": { ... }
      }
    }
  }

SLAB_WATCHLIST in config controls which cards to track.
"""
import json
import os
from datetime import datetime, timezone

import config
import ebay


SLABS_DIR = os.path.join(config.DATA_DIR, "slabs")


# ---------------------------------------------------------------------------
# Watchlist helpers
# ---------------------------------------------------------------------------

def _watchlist():
    """Return SLAB_WATCHLIST from config, or [] if not defined."""
    return getattr(config, "SLAB_WATCHLIST", [])


# ---------------------------------------------------------------------------
# Snapshot I/O
# ---------------------------------------------------------------------------

def _path(date_str):
    return os.path.join(SLABS_DIR, f"{date_str}.json")


def exists(date_str):
    return os.path.exists(_path(date_str))


def load(date_str):
    with open(_path(date_str), encoding="utf-8") as f:
        return json.load(f)


def save(date_str, snapshot):
    os.makedirs(SLABS_DIR, exist_ok=True)
    tmp = _path(date_str) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, _path(date_str))


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_today(log=print):
    """Fetch eBay slab comps for every card in SLAB_WATCHLIST and save them."""
    watchlist = _watchlist()
    if not watchlist:
        log("slabs: SLAB_WATCHLIST is empty — nothing to fetch")
        return {}

    date_str = datetime.now(timezone.utc).date().isoformat()
    if exists(date_str):
        log(f"slabs: snapshot for {date_str} already saved; skipping")
        return load(date_str)

    cards = {}
    for entry in watchlist:
        name = entry.get("name", "")
        set_name = entry.get("set", "")
        game = entry.get("game", "pokemon")
        key = entry.get("key") or f"{name}-{set_name}".lower().replace(" ", "-")
        card_key = f"{game}:{key}"

        comps = ebay.fetch_slab_comps(name, set_name, log=log)
        record = {"name": name, "set": set_name, "game": game}
        for grader, sales in comps.items():
            summary = ebay.summarize_comps(sales)
            if summary:
                record[grader] = summary
        cards[card_key] = record

    snapshot = {"date": date_str, "cards": cards}
    save(date_str, snapshot)
    log(f"slabs: saved {len(cards)} card comps for {date_str}")
    return snapshot


# ---------------------------------------------------------------------------
# Build output for the site
# ---------------------------------------------------------------------------

def build_slab_index(out_dir, log=print):
    """Write site/data/slabs.json — the latest slab comps for the site."""
    snapshots = sorted(
        f for f in os.listdir(SLABS_DIR) if f.endswith(".json") and not f.endswith(".tmp")
    ) if os.path.isdir(SLABS_DIR) else []

    if not snapshots:
        log("slabs: no snapshots found; skipping site build")
        return

    latest_path = os.path.join(SLABS_DIR, snapshots[-1])
    with open(latest_path, encoding="utf-8") as f:
        latest = json.load(f)

    # Attach 30-day history for each card
    history_days = snapshots[-30:]
    history = {}   # card_key → [{date, PSA_median, BGS_median, CGC_median}]
    for fname in history_days:
        day = fname.replace(".json", "")
        with open(os.path.join(SLABS_DIR, fname), encoding="utf-8") as f:
            snap = json.load(f)
        for card_key, record in snap.get("cards", {}).items():
            row = {"date": day}
            for grader in ebay.GRADERS:
                summary = record.get(grader)
                if summary:
                    row[f"{grader}_median"] = summary.get("median")
            history.setdefault(card_key, []).append(row)

    out = {
        "updated": latest.get("date"),
        "cards": latest.get("cards", {}),
        "history": history,
    }

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "slabs.json")
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, out_path)
    log(f"slabs: wrote {out_path} ({len(out['cards'])} cards)")
