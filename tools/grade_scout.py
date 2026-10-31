"""Find cheap raw cards whose PSA 10 copies list on eBay for 10x+ raw (for the "Grade it?" social carousels).

    python tools/grade_scout.py SITE_DIR GAME [--max N] [--min-mult 10]

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ebay  # noqa: E402
from ebay_prices import best, query  # noqa: E402

GOOD = re.compile(r"illustration|art rare|character|trainer gallery|galarian gallery|shiny|secret|hyper|ultra|special|double|"
                  r"holo|alternate|manga|leader|super rare|enchanted|legendary|epic|showcase|overnumbered", re.I)


def main(argv):
    site, game = argv[0], argv[1]
    mx = int(argv[argv.index("--max") + 1]) if "--max" in argv else 250
    mm = float(argv[argv.index("--min-mult") + 1]) if "--min-mult" in argv else 10
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
    cands = [r for r in rows if r[7] in games and once[r[0]] == 1 and r[6] and 100 <= r[3] <= 2500
             and not re.search(r"\bBREAK\b|\bLEGEND\b|jumbo|oversize", r[2], re.I)]
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
        if got and got[1] >= 2 and got[0] >= mm * r[3]:
            hits.append({"id": r[0], "g": r[1], "n": r[2], "no": r[6], "r": r[5], "raw": r[3], "p10_ask": got[0], "asks": got[1], "x": round(got[0] / r[3], 1)})
        time.sleep(0.25)
    hits.sort(key=lambda h: -(h["p10_ask"] - h["raw"]))
    print(f"::notice title=Grade scout {game}::{calls} cards checked, {len(hits)} with PSA 10 asks {mm:g}x+ raw")
    for h in hits[:30]:
        print(f"::notice title=hit::{json.dumps(h, ensure_ascii=False)}")


if __name__ == "__main__":
    main(sys.argv[1:])
