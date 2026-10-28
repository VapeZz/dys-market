"""Graded (slab) sold prices for Pokémon cards from PokemonPriceTracker, cached and refreshed in rotation.

    python tools/graded.py site data/graded

Needs PPT_API_KEY. The free plan gives 100 credits a day and each card with eBay graded data
costs 2, so we refresh up to PER_DAY cards per day: never-fetched cards first, then the oldest.
Only runs once per calendar day (dispatching the nightly job again doesn't spend credits).
The stored cache (STORE/cache.enc) is encrypted with a key from PPT_API_KEY (see pipeline/sealed.py).
Reads site/data/grading.json (tools/grading.py) for candidates; writes site/data/graded.json:
  {"updated", "cards": {"<tcgplayer id>": {"at": "YYYY-MM-DD", "g": {"psa10": [price_cents, sales, per_day, trend], ...}}}}
That public file is only filled with PPT_BUSINESS_PLAN on. With PPT_PERSONAL on, the same prices go to
site/data/edge/graded.enc for the owner's private DYS Edge app instead: gzip'd JSON
  {"u": updated, "c": {"<tcgplayer id>": ["YYYY-MM-DD", {"psa10": [price_cents, sales_90d, sales_per_day, last_sale], ...}]}}
sealed with a key from PPT_API_KEY (pipeline/sealed.py, purpose "edge"), which the app derives from the key the owner enters.
"""
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import config  # noqa: E402
import sealed  # noqa: E402  (the stored cache is encrypted: their terms let us store it, not publish it)

API = "https://www.pokemonpricetracker.com/api/v2/cards"
PER_RUN = int(os.environ.get("PPT_PER_RUN", "45"))       # cards per run (paid plan: hundreds; free plan: 45/day)
STALE_DAYS = int(os.environ.get("PPT_STALE_DAYS", "3"))   # refresh a card's graded prices this often
GRADES = ["psa10", "psa9", "psa8", "cgc10", "cgc9_5", "cgc9", "bgs10", "bgs9_5", "bgs9", "tag10", "tag9"]


def fetch(pid, key, jp=False):
    req = urllib.request.Request(f"{API}?tcgPlayerId={pid}&limit=1&includeEbay=true&days=90{'&language=japanese' if jp else ''}",
                                 headers={"Authorization": "Bearer " + key, "User-Agent": "dys-market"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r).get("data")


def summarize(card):
    out = {}
    for g, s in ((card or {}).get("ebay") or {}).get("salesByGrade", {}).items():
        if g not in GRADES or not isinstance(s, dict) or not s.get("count"):
            continue
        price = (s.get("smartMarketPrice") or {}).get("price") or s.get("medianPrice")
        if price:
            avg, p7 = s.get("averagePrice"), s.get("marketPrice7Day")
            last = str(s.get("lastSaleDate") or "")[:10]
            last = last if re.fullmatch(r"\d{4}-\d{2}-\d{2}", last) else None
            # [price, sales (90d), sales/day (7d), trend, 90-day average, 7-day market, last sale date]
            out[g] = [round(price * 100), int(s["count"]), round(s.get("dailyVolume7Day") or 0, 2), s.get("marketTrend") or "",
                      round(avg * 100) if avg else None, round(p7 * 100) if p7 else None, last]
    return out


def main(argv):
    site, store = argv[0], argv[1]
    if not (config.PPT_BUSINESS_PLAN or config.PPT_PERSONAL):
        # their terms need the Business plan for a site like ours: fetch nothing, show nothing, keep the stored cache
        with open(os.path.join(site, "data", "graded.json"), "w", encoding="utf-8") as f:
            json.dump({"updated": date.today().isoformat(), "cards": {}, "paused": True}, f, separators=(",", ":"))
        plain = os.path.join(store, "cache.json")
        if os.path.exists(plain) and sealed.can_seal("ppt"):        # still keep the stored copy encrypted
            with open(plain, "rb") as f:
                sealed.write("ppt", os.path.join(store, "cache.enc"), f.read())
            os.remove(plain)
        print("graded: paused (PPT_BUSINESS_PLAN is off in pipeline/config.py); graded prices hidden, stored cache kept")
        return
    key = (os.environ.get("PPT_API_KEY") or "").strip()
    os.makedirs(store, exist_ok=True)
    cpath, plain = os.path.join(store, "cache.enc"), os.path.join(store, "cache.json")
    cache = {"last_run": "", "cards": {}}
    try:
        if os.path.exists(cpath):
            cache = json.loads(sealed.read("ppt", cpath))
        elif os.path.exists(plain):               # older unencrypted cache: sealed below, then removed
            cache = json.load(open(plain))
    except sealed.Locked as e:
        print(f"::warning title=Graded prices::can't open the stored graded prices ({e}); leaving graded.json unchanged")
        return
    today = date.today().isoformat()
    fetched = 0
    if not key:
        print("::warning title=Graded prices::PPT_API_KEY not set; using cached prices only")
    else:
        rows = json.load(open(os.path.join(site, "data", "grading.json")))["rows"]
        cutoff = (date.today() - timedelta(days=STALE_DAYS)).isoformat()
        once = {}
        for r in rows:
            once[r[0]] = once.get(r[0], 0) + 1
        # graded sales are per product, so only cards with a single printing under their id give clean numbers
        cands = [r for r in rows if r[7] in ("pokemon", "pokemon-jp") and 2000 <= r[3] <= 500000 and once[r[0]] == 1      # Pokémon (EN + JP), $20+
                 and cache["cards"].get(str(r[0]), {}).get("at", "") <= cutoff]
        # never-fetched first, then oldest; within that, modern $30-$500 cards (what people grade most) before the rest
        cands.sort(key=lambda r: (str(r[0]) in cache["cards"], cache["cards"].get(str(r[0]), {}).get("at", ""),
                                  not (r[8] == "modern" and 3000 <= r[3] <= 50000), -r[3]))
        for r in cands[:PER_RUN]:
            pid = str(r[0])
            try:
                cache["cards"][pid] = {"at": today, "g": summarize(fetch(pid, key, r[7] == "pokemon-jp"))}
                fetched += 1
            except urllib.error.HTTPError as e:
                if e.code in (401, 402, 403, 429):
                    print(f"::warning title=Graded prices::stopped: HTTP {e.code} {e.read()[:160]!r}")
                    break
                cache["cards"][pid] = {"at": today, "g": {}}
            except Exception as e:  # network hiccup: try this card another day
                print(f"graded: {pid} failed: {e}")
            time.sleep(1.1)
        cache["last_run"] = today
    if key:
        sealed.write("ppt", cpath, json.dumps(cache, separators=(",", ":")).encode("utf-8"))
        if os.path.exists(plain):
            os.remove(plain)
    cards = {pid: c for pid, c in cache["cards"].items() if c.get("g")}
    with open(os.path.join(site, "data", "graded.json"), "w", encoding="utf-8") as f:
        if config.PPT_BUSINESS_PLAN:
            json.dump({"updated": cache.get("last_run"), "cards": cards}, f, separators=(",", ":"))
        else:   # personal use only: the public site shows none of it
            json.dump({"updated": today, "cards": {}, "paused": True}, f, separators=(",", ":"))
    where = "site"
    if config.PPT_PERSONAL and key:
        write_edge(site, cache.get("last_run"), cards)
        where = "site" if config.PPT_BUSINESS_PLAN else "DYS Edge only (encrypted)"
    print(f"graded: {fetched} refreshed today, {len(cards)} cards with graded prices, for {where}")


def write_edge(site, updated, cards):
    """The owner's private copy for DYS Edge: only someone holding PPT_API_KEY can read it."""
    slim = {pid: [c.get("at"), {g: [v[0], v[1], v[2], v[6] if len(v) > 6 else None] for g, v in c["g"].items()}]
            for pid, c in cards.items()}
    blob = gzip.compress(json.dumps({"u": updated, "c": slim}, separators=(",", ":")).encode("utf-8"), mtime=0)
    out = os.path.join(site, "data", "edge")
    os.makedirs(out, exist_ok=True)
    sealed.write("edge", os.path.join(out, "graded.enc"), blob)


if __name__ == "__main__":
    main(sys.argv[1:])
