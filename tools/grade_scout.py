"""Find cheap raw cards whose PSA 10 copies list on eBay for 10x+ raw (for the "Grade it?" social carousels).

    python tools/grade_scout.py SITE_DIR GAME [--max N] [--min-mult 10] [--out shortlist.json] [--history history.json]

GAME "auto" takes the next game in ROTATION (pointer in rotation.json next to history.json); if it has fewer than
6 candidates, it tries the next two games and keeps the one with the most. Benched games (BENCH) get a quick
look every 4 weeks and join the rotation once they have 6+ candidates.

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
                  r"holo|alternate|manga|leader|super rare|treasure|enchanted|legendary|epic|iconic|showcase|overnumbered|"
                  r"starlight|ghost|collector|quarter century|prismatic|god rare|\bSCR\b|\bSPR\b|\bSR\b|\bUR\b|\bSEC\b|\bAP\b", re.I)
# every TCG on the market site; Pokémon (the biggest audience) every third post. Posting Monday to Saturday = one full lap in about 2.5 weeks.
# Gundam taken out Nov 7, 2026: too few PSA 10 eBay sales for the sold-price check (0 of 15 cards passed). Add it back by hand later.
ROTATION = ["pokemon", "one-piece", "yugioh", "pokemon", "riftbound", "lorcana", "pokemon", "pokemon-jp",
            "dragon-ball-fusion-world"]
# games with almost no PSA 10 sales yet: re-checked every 4 weeks and added to the rotation once they have candidates
BENCH = ["union-arena", "palworld"]


def has_photo(pid):
    """True if TCGplayer serves a photo for this product (403/404 when there is none)."""
    import urllib.error
    import urllib.request
    u = f"https://tcgplayer-cdn.tcgplayer.com/product/{pid}_in_1000x1000.jpg"
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(u, method=method, headers={"User-Agent": "DriveYourStyleMarket/1.0 (+https://driveyourstyle.net)"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status == 200 and r.headers.get("Content-Type", "").startswith("image")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                return False
        except Exception:
            pass
    return True   # couldn't tell (network hiccup): the Grade it? build fails safely if the photo is really missing


def scan(rows, once, game, recent, mx, mm):
    """eBay PSA 10 asks for up to mx cheap cards of one game; returns (hits sorted best first, searches made)."""
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
    return hits, calls


def main(argv):
    site, game = argv[0], argv[1]
    mx = int(argv[argv.index("--max") + 1]) if "--max" in argv else 250
    mm = float(argv[argv.index("--min-mult") + 1]) if "--min-mult" in argv else 10
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    hp = argv[argv.index("--history") + 1] if "--history" in argv else None
    hist = {}
    try:
        hist = json.load(open(hp)) if hp else {}
    except (OSError, ValueError):
        hist = {}
    recent = {k for k, v in hist.items() if v >= (date.today() - timedelta(days=28)).isoformat()}
    d = os.path.join(site, "data")
    rows = json.load(open(os.path.join(d, "grading.json")))["rows"]
    try:
        rows += json.load(open(os.path.join(d, "grading-cheap.json")))["rows"]
    except OSError:
        pass
    once = {}
    for r in rows:
        once[r[0]] = once.get(r[0], 0) + 1
    # rotation pointer lives next to history.json (data/social-grade/rotation.json)
    rp = os.path.join(os.path.dirname(hp), "rotation.json") if hp else None
    try:
        rot = json.load(open(rp)) if rp else {}
    except (OSError, ValueError):
        rot = {}
    nxt = rot.get("next", len(set(hist.values())))
    added = [g for g in rot.get("added", []) if g in BENCH]
    if game == "auto" and rp and rot.get("bench_checked", "") <= (date.today() - timedelta(days=28)).isoformat():
        for g in [g for g in BENCH if g not in added]:   # monthly look at the benched games
            hits, calls = scan(rows, once, g, recent, 120, mm)
            print(f"::notice title=Grade scout bench {g}::{calls} cards checked, {len(hits)} candidates" + (" (added to the rotation)" if len(hits) >= 6 else ""))
            if len(hits) >= 6:
                added.append(g)
        rot["bench_checked"] = date.today().isoformat()
    order = ROTATION + [x for g in added for x in ("pokemon", g)]
    tries = [order[(nxt + t) % len(order)] for t in range(3)] if game == "auto" else [game]
    best_try = None
    for t, g in enumerate(tries):
        hits, calls = scan(rows, once, g, recent, mx, mm)
        print(f"::notice title=Grade scout {g}::{calls} cards checked, {len(hits)} with PSA 10 asks {mm:g}x+ raw")
        if best_try is None or len(hits) > len(best_try[1]):
            best_try = (g, hits, t)
        if len(hits) >= 6:     # enough to end up with 3-5 after the sold-price check
            best_try = (g, hits, t)
            break
    game, hits, t = best_try
    if game != "one-piece":   # One Piece slides use Bandai's official image instead of TCGplayer's watermarked one
        hits = [h for h in hits[:60] if has_photo(h["id"])]   # every card shown needs its own photo
    if game != tries[0]:
        print(f"::notice title=Grade scout::{tries[0]} had too few candidates; using {game}")
    if rp and len(tries) > 1:
        rot.update({"next": (nxt + t + 1) % len(order), "last": game, "date": date.today().isoformat(), "added": added})
        json.dump(rot, open(rp, "w"))
    if out:
        json.dump({"date": date.today().isoformat(), "game": game, "hits": hits[:40]}, open(out, "w"), ensure_ascii=False, indent=0)
    # one annotation (GitHub keeps only 10 per step): id|name|number|raw|cheapest PSA 10 ask|asks|x
    print("::notice title=hits::" + " ;; ".join(f"{h['id']}|{h['n']}|{h['no']}|{h['raw']}|{h['p10_ask']}|{h['asks']}|{h['x']}" for h in hits[:40]))


if __name__ == "__main__":
    main(sys.argv[1:])
