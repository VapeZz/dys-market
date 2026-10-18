"""Auto-pull eBay slab comps for today's top raw price movers.

After the TCGplayer snapshot is saved, this module:
  1. Finds the top N cards by 1-day raw price change (% gain, min $5 threshold)
  2. Queries eBay completed sales for each (PSA/BGS/CGC)
  3. Merges results into today's slab snapshot

This runs automatically inside pipeline/run.py when EBAY_APP_ID is set.
Settings are in pipeline/config.py under SLAB_AUTO_MOVERS_*.
"""
import os

import config
import ebay
import slabs
import snapshots


# Defaults (override in config.py)
_TOP_N = getattr(config, "SLAB_AUTO_MOVERS_TOP_N", 30)       # how many movers to pull
_MIN_USD = getattr(config, "SLAB_AUTO_MOVERS_MIN_USD", 10)    # skip cards under this price
_MIN_PCT = getattr(config, "SLAB_AUTO_MOVERS_MIN_PCT", 5.0)   # skip moves under this % change
_CARD_ONLY = getattr(config, "SLAB_AUTO_MOVERS_CARDS_ONLY", True)  # skip sealed products


def _card_name(product):
    """Return a clean card name string from a compact product dict."""
    name = product.get("n", "")
    num = product.get("no", "")
    return f"{name} #{num}" if num else name


def _set_name(groups, gid):
    """Return the set name for a group id."""
    g = groups.get(str(gid)) or groups.get(gid) or {}
    return g.get("name", "")


def top_movers(groups, products, n=_TOP_N, min_usd=_MIN_USD, min_pct=_MIN_PCT,
               cards_only=_CARD_ONLY, log=print):
    """Return the top N cards by 1-day price gain as a list of dicts.

    Each dict: {pid, sub, name, set, game, price_usd, change_pct}
    """
    days = snapshots.available()
    if len(days) < 2:
        log("slab_movers: need at least 2 snapshots; skipping")
        return []

    latest = snapshots.load(days[-1])
    prev_day = snapshots.closest_on_or_before(days[:-1], snapshots.minus_days(days[-1], 1))
    if not prev_day:
        log("slab_movers: no previous snapshot found; skipping")
        return []
    prev = snapshots.load(prev_day)

    movers = []
    for key, cents in latest.items():
        pid, sub = key.split(":", 1)
        p = products.get(pid)
        if not p:
            continue
        if cards_only and p.get("t") != "c":
            continue
        price_usd = cents / 100
        if price_usd < min_usd:
            continue
        old_cents = prev.get(key)
        if not old_cents or old_cents <= 0:
            continue
        pct = (cents - old_cents) / old_cents * 100
        if pct < min_pct:
            continue
        gid = p.get("g")
        movers.append({
            "pid": pid,
            "sub": sub,
            "key": key,
            "name": _card_name(p),
            "set": _set_name(groups, gid),
            "game": p.get("k", ""),
            "price_usd": round(price_usd, 2),
            "change_pct": round(pct, 1),
        })

    movers.sort(key=lambda x: x["change_pct"], reverse=True)
    top = movers[:n]
    log(f"slab_movers: {len(movers)} movers found, pulling comps for top {len(top)}")
    return top


def fetch_movers_slabs(groups, products, log=print):
    """Pull eBay slab comps for today's top movers and merge into slab snapshot."""
    if not os.environ.get("EBAY_APP_ID"):
        return

    movers = top_movers(groups, products, log=log)
    if not movers:
        return

    from datetime import datetime, timezone
    date_str = datetime.now(timezone.utc).date().isoformat()

    # Load existing snapshot so watchlist entries aren't overwritten
    existing = slabs.load(date_str) if slabs.exists(date_str) else {"date": date_str, "cards": {}}
    cards = existing.get("cards", {})

    fetched = 0
    for mover in movers:
        card_key = f"mover:{mover['game']}:{mover['pid']}"
        if card_key in cards:
            continue   # already pulled (e.g. also on watchlist)

        comps = ebay.fetch_slab_comps(mover["name"], mover["set"], log=log)
        record = {
            "name": mover["name"],
            "set": mover["set"],
            "game": mover["game"],
            "price_usd": mover["price_usd"],
            "change_pct": mover["change_pct"],
            "source": "auto-mover",
        }
        any_comps = False
        for grader, sales in comps.items():
            summary = ebay.summarize_comps(sales)
            if summary:
                record[grader] = summary
                any_comps = True

        if any_comps:
            cards[card_key] = record
            fetched += 1

    existing["cards"] = cards
    slabs.save(date_str, existing)
    slabs.build_slab_index(config.OUT_DIR, log=log)
    log(f"slab_movers: added comps for {fetched} movers to {date_str} snapshot")
