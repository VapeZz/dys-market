"""Grading candidates for the Grading Insights page.

    python tools/grading.py site

Writes site/data/grading.json: cards that people actually grade, with prices we trust.
Kept:  single cards $15-$5,000, not promos/events/prize cards/markers/tokens, whose price is
       backed by live listings (lowest listing within 0.5-1.6x market) and steady over the week
       (no single-day spike: week high <= 1.8x week low).
Each row: [id, set id, name, market cents, lowest listing cents, rarity, number, game, era]
era: "modern" (set from the last 5 years) or "vintage".
Also writes site/data/grading-cheap.json, same rows, for Pokémon (EN + JP) singles $1-$14.99 that pass the same
checks: the pool for finding cheap cards whose PSA 10 sells for 10x+ raw (graded prices come from tools/graded.py).
"""
import glob
import json
import os
import re
import sys
from datetime import date, timedelta

SKIP_NAME = re.compile(r"code card|jumbo|oversize|marker|token|\bcase\b|serial|prize|winner|stamp(ed)?\b|error|misprint|\bdeck\b|box|booster|bundle|sleeve|playmat|binder", re.I)
SKIP_SET = re.compile(r"promo|championship|regional|tournament|event|judge|prize|world finals|league|organized play|marker|token|staff|prerelease", re.I)
SKIP_RARITY = re.compile(r"promo|^pr$|don!!|action point", re.I)


def main(argv):
    site = argv[0]
    sd = os.path.join(site, "data")
    today = json.load(open(os.path.join(sd, "meta.json"))).get("updated") or date.today().isoformat()
    modern_from = (date.fromisoformat(today) - timedelta(days=365 * 5)).isoformat()
    rows, cheap, seen = [], [], set()
    for path in glob.glob(os.path.join(sd, "set", "*.json")):
        d = json.load(open(path))
        if (d.get("pub") or "") > today or SKIP_SET.search(d["n"]):
            continue
        for i in d["items"]:
            p, lo = i.get("p"), i.get("lo")
            if i["t"] != "c" or not p or not (100 <= p <= 500000) or SKIP_NAME.search(i["n"]) or SKIP_RARITY.search(i.get("r") or ""):
                continue
            if p < 1500 and d["k"] not in ("pokemon", "pokemon-jp"):   # cheap pool: only games with graded sold prices
                continue
            if not lo or not (0.5 * p <= lo <= 1.6 * p):            # no live listing near the market price: thin or stale
                continue
            s = [v for v in (i.get("s") or [])[-8:] if v]
            if len(s) >= 3 and max(s) > 1.8 * min(s):                 # spiked or crashed this week: wait for it to settle
                continue
            key = (i["id"], i["n"])
            if key in seen:
                continue
            seen.add(key)
            era = "modern" if (d.get("pub") or "") >= modern_from else "vintage"
            (rows if p >= 1500 else cheap).append([i["id"], d["id"], i["n"], p, lo, i.get("r") or "", i.get("no") or "", d["k"], era])
    rows.sort(key=lambda r: -r[3])
    cheap.sort(key=lambda r: -r[3])
    with open(os.path.join(sd, "grading-cheap.json"), "w", encoding="utf-8") as f:
        json.dump({"updated": today, "rows": cheap}, f, separators=(",", ":"), ensure_ascii=False)
    with open(os.path.join(sd, "grading.json"), "w", encoding="utf-8") as f:
        json.dump({"updated": today, "rows": rows}, f, separators=(",", ":"), ensure_ascii=False)
    print(f"grading: {len(rows)} cards with trusted prices, plus {len(cheap)} Pokémon singles $1-$15 for the 10x finder")


if __name__ == "__main__":
    main(sys.argv[1:])
