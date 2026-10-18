"""Monthly giveaway: entries from collectors' binders, public stats, and the monthly draw.

Entering is free: a signed-in collector ticks "Enter me in the monthly giveaway" on My Collection
(binder field gw) and has at least MIN_ITEMS items in their binder.
Entries: 1, +1 for a public binder, +1 per referred friend (binder field ref = referrer's pid)
who has MIN_ITEMS items too, up to REF_CAP. Entrants stay entered every month.

    python pipeline/giveaway.py draw     # on the 1st: draws last month's winner into site/giveaway-winners.json
write_public(binders, data) is called by showcase.py and writes data/giveaway.json.
"""
import json
import os
import re
import secrets
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINNERS = os.path.join(ROOT, "site", "giveaway-winners.json")
PRIZE = "1 Pokémon Elite Trainer Box"
MIN_ITEMS, REF_CAP = 5, 10
ALIAS = re.compile(r"^[A-Za-z0-9_. \-]{3,20}$")
PT = ZoneInfo("America/Los_Angeles")


def _items(b):
    n = 0
    for it in b.get("items") or []:
        try:
            n += max(1, int(it.get("qty") or 1))
        except (TypeError, ValueError, AttributeError):
            pass
    return n


def entries(binders, pid_of):
    by = {pid_of(gid): (gid, b) for gid, _, b in binders}
    refs = {}
    for pid, (_, b) in by.items():
        r = b.get("ref")
        if isinstance(r, str) and r in by and r != pid and _items(b) >= MIN_ITEMS:
            refs[r] = refs.get(r, 0) + 1
    out = {}
    for pid, (gid, b) in by.items():
        if not b.get("gw") or _items(b) < MIN_ITEMS:
            continue
        alias = (b.get("alias") or "").strip()
        pub = bool(b.get("pub")) and bool(ALIAS.match(alias))
        r = min(REF_CAP, refs.get(pid, 0))
        out[pid] = {"e": 1 + (1 if pub else 0) + r, "r": r, "alias": alias if ALIAS.match(alias) else "", "gid": gid}
    return out


def winners():
    try:
        return json.load(open(WINNERS))
    except (OSError, ValueError):
        return []


def month_now():
    now = datetime.now(PT)
    nxt = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
    return now.strftime("%Y-%m"), nxt.strftime("%Y-%m-%d")


def write_public(binders, data, pid_of):
    ent = entries(binders, pid_of)
    month, draw = month_now()
    pub_w = [{"month": w["month"], "alias": w["alias"]} for w in winners()]
    with open(os.path.join(data, "giveaway.json"), "w", encoding="utf-8") as f:
        json.dump({"month": month, "draw": draw, "prize": PRIZE, "min": MIN_ITEMS, "cap": REF_CAP,
                   "entrants": len(ent), "entries": sum(v["e"] for v in ent.values()),
                   "mine": {p: [v["e"], v["r"]] for p, v in ent.items()}, "winners": pub_w[-12:]},
                  f, separators=(",", ":"), ensure_ascii=False)
    print(f"giveaway: {len(ent)} entrants, {sum(v['e'] for v in ent.values())} entries")


def draw():
    from showcase import fetch_binders, pid_of
    from shopify_api import Shopify
    now = datetime.now(PT)
    month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")   # last month
    ws = winners()
    if any(w["month"] == month for w in ws):
        print(f"::notice title=Giveaway::{month} already drawn")
        return
    ent = entries(fetch_binders(Shopify(os.environ["SHOPIFY_SHOP"])), pid_of)
    if not ent:
        print(f"::warning title=Giveaway::No entrants for {month}; nothing drawn")
        return
    pool = [p for p, v in ent.items() for _ in range(v["e"])]
    pid = secrets.SystemRandom().choice(pool)
    w = {"month": month, "pid": pid, "alias": ent[pid]["alias"] or f"Collector {pid[:4]}",
         "entrants": len(ent), "entries": len(pool), "drawn": int(time.time() * 1000)}
    ws.append(w)
    with open(WINNERS, "w", encoding="utf-8") as f:
        json.dump(ws, f, indent=1, ensure_ascii=False)
    print(f"::notice title=Giveaway winner::{month}: {w['alias']} ({w['entries']} entries from {w['entrants']} collectors)")


if __name__ == "__main__":
    if sys.argv[1:] == ["draw"]:
        draw()
