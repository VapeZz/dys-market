"""Find cheap raw cards whose PSA 10 copies list on eBay for 10x+ raw (for the "Grade it?" social carousels).

    python tools/grade_scout.py SITE_DIR GAME [--max N] [--min-mult 10] [--out shortlist.json] [--history history.json]

GAME "auto" picks the next game in the rotation from history.json (one entry per posted card).

Uses only our own data (TCGplayer market prices we collect) and eBay's Browse API (live PSA 10 Buy It Now
listings), never PokemonPriceTracker. Candidates: single cards $1-$25 from grading.json / grading-cheap.json
(steady prices, live listings near market). For each, one eBay search for a PSA 10 copy; keeps cards whose
cheapest matching PSA 10 listing is at least --min-mult x raw with 2+ matching listings. Prints the shortlist;
the posted PSA 10 prices are then checked against recent eBay sold listings before anything goes out.
"""
import json
import os
import re
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ebay  # noqa: E402
from ebay_prices import best, query  # noqa: E402

GOOD = re.compile(r"illustration|art rare|character|trainer gallery|galarian gallery|shiny|secret|hyper|ultra|special|double|"
                  r"holo|alternate|manga|leader|super rare|treasure|enchanted|legendary|epic|iconic|showcase|overnumbered", re.I)
ROTATION = ["pokemon", "one-piece", "pokemon", "riftbound", "pokemon", "lorcana"]


def main(argv):
    site, game = argv[0], argv[1]
    mx = int(argv[argv.index("--max") + 1]) if "--max" in argv else 250
    mm = float(argv[argv.index("--min-mult") + 1]) if "--min-mult" in argv else 10
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    hist = {}
    if "--history" in argv:
        try:
            hist = json.load(open(argv[argv.index("--history") + 1]))
        except (OSError, ValueError):
            hist = {}
    if game == "auto":   # next in the rotation: one step per carousel already posted
        game = ROTATION[len(set(hist.values())) % len(ROTATION)]
    recent = {k for k, v in hist.items() if v >= (date.today() - timedelta(days=56)).isoformat()}
    d = os.path.join(site, "data")
    rows = json.load(open(os.path.join(d, "grading.json")))["rows"]
    try:
        rows += json.load(open(os.path.join(d, "grading-cheap.json")))["rows"]
    except OSError:
        pass
    once = {}
    for r in rows:
        once[r[0]] = once.get(r[0], 0) + 1
    games = {"pokemon": ("pokemon",), "pokemon-jp": ("pokemon-jp",)}.get(game, (game,))
    cands = [r for r in rows if r[7] in games and once[r[0]] == 1 and r[6] and 100 <= r[3] <= 2500 and str(r[0]) not in recent
             and not re.search(r"\bBREAK\b|\bLEGEND\b|jumbo|oversize", r[2], re.I)
             and not (r[7] == "one-piece" and re.search(r"\((parallel|alternate|manga|sp|full art|textured|box topper|pre-release|tournament)", r[2], re.I))]   # one art per number (official images)
    # likeliest 10x cards first: chase-style rarities, modern (one printing, easy comps), $3-$15 raw
    cands.sort(key=lambda r: (not GOOD.search(r[5] or ""), r[8] != "modern", not (300 <= r[3] <= 1500), -r[3]))
    hits, calls = [], 0
    for r in cands[:mx]:
        try:
            calls += 1
            res = ebay.search(query(r, True), filters="buyingOptions:{FIXED_PRICE},deliveryCountry:US,itemLocationCountry:US,conditionIds:{2750}")
            got = best(res.get("itemSummaries") or [], r, True)
        except ebay.urllib.error.HTTPError as e:
            if e.code in (401, 403, 429):
                print(f"::warning title=Grade scout::stopped: HTTP {e.code}")
                break
            continue
        except Exception as e:
            print(f"scout: {r[0]} failed: {e}")
            continue
        if got and got[1] >= 2 and mm * r[3] <= got[0] <= 80 * r[3]:   # 80x+ is nearly always a different printing
            hits.append({"id": r[0], "g": r[1], "n": r[2], "no": r[6], "r": r[5], "raw": r[3], "p10_ask": got[0], "asks": got[1], "x": round(got[0] / r[3], 1),
                         "game": r[7]})
        time.sleep(0.25)
    hits.sort(key=lambda h: -(h["p10_ask"] - h["raw"]))
    print(f"::notice title=Grade scout {game}::{calls} cards checked, {len(hits)} with PSA 10 asks {mm:g}x+ raw")
    # one annotation (GitHub keeps only 10 per step): id|name|number|raw|cheapest PSA 10 ask|asks|x
    if out:
        json.dump({"date": date.today().isoformat(), "game": game, "hits": hits[:40]}, open(out, "w"), ensure_ascii=False, indent=0)
    print("::notice title=hits::" + " ;; ".join(f"{h['id']}|{h['n']}|{h['no']}|{h['raw']}|{h['p10_ask']}|{h['asks']}|{h['x']}" for h in hits[:40]))


if __name__ == "__main__":
    main(sys.argv[1:])
