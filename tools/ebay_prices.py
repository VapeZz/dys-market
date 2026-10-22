"""Live eBay Buy It Now prices for cards (eBay Browse API), cached and refreshed in rotation.

    python tools/ebay_prices.py site data/ebay

Needs EBAY_CLIENT_ID / EBAY_CLIENT_SECRET; without them it only republishes the cache.
Candidates come from site/data/grading.json (cards with trusted prices). For each card we search
eBay US fixed-price listings for the raw card and, for cards $30+, a PSA 10 copy, and keep only
listings whose title really matches (card number, name, language, no proxies/lots/other graders).
Writes site/data/ebay.json: {"updated", "cards": {"<id>": {"at", "r": [cents, n, url], "p10": [cents, n, url]}}}
Prices include shipping.
"""
import json
import os
import re
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ebay  # noqa: E402

PER_RUN = int(os.environ.get("EBAY_PER_RUN", "450"))
STALE_DAYS = int(os.environ.get("EBAY_STALE_DAYS", "5"))
BAD = re.compile(r"proxy|custom|orica|fan ?art|replica|reprint|digital|\bcode\b|\blot\b|bundle|choose|you pick|pick your|playset|\b\d+ ?x\b|\bx ?\d+\b|"
                 r"jumbo|oversize|metal|gold ?plated|art card|sticker|sleeve|empty|binder|display|booster|sealed|mystery|repack|\bread\b", re.I)
GRADED = re.compile(r"\b(psa|bgs|cgc|tag|beckett|sgc|ace|graded|slab|gem ?mint)\b", re.I)
ASIAN = re.compile(r"japanese|japan|\bjp\b|\bjpn\b|chinese|korean|\bkr\b|s-chinese|t-chinese", re.I)


def base_name(n):
    n = re.sub(r"\s*\([^)]*\)", "", n)                       # drop every (…) tag: printing, rarity, number
    return re.sub(r"\s+-\s+[\w/*-]+$", "", n).strip()


def num_rx(no):
    no = (no or "").replace("*", "").strip()
    if not no:
        return None
    if "/" in no:
        a, b = no.split("/", 1)
        a, b = a.lstrip("0") or "0", b.lstrip("0") or "0"
        if a.isdigit() and b.isdigit():
            return re.compile(rf"(?<![\d])0*{a}\s*/\s*0*{b}(?![\d])")
        return re.compile(rf"(?<![\w]){re.escape(a)}\s*/\s*{re.escape(b)}", re.I)
    return re.compile(rf"(?<![\w-]){re.escape(no)}(?![\w])", re.I)


def match(item, row, graded):
    t = item.get("title") or ""
    name, no, game = base_name(row[2]), row[6], row[7]
    nr = num_rx(no)
    if nr and not nr.search(t):
        return False
    first = re.split(r"[\s'’.,&-]+", name)[0]
    if len(first) >= 3 and first.lower() not in t.lower():
        return False
    if BAD.search(t):
        return False
    if game == "pokemon" and ASIAN.search(t):
        return False
    if game == "pokemon-jp" and not re.search(r"japanese|japan|\bjp\b|\bjpn\b", t, re.I):
        return False
    if graded:
        return bool(re.search(r"\bpsa\s*10(?![\d.])", t, re.I)) and not re.search(r"\b(bgs|cgc|tag|sgc|beckett)\b|psa\s*9", t, re.I)
    return not GRADED.search(t)


def best(items, row, graded):
    out = []
    for it in items:
        if not match(it, row, graded):
            continue
        try:
            p = float(it["price"]["value"])
            ship = (it.get("shippingOptions") or [{}])[0].get("shippingCost") or {}
            p += float(ship.get("value") or 0)
        except (KeyError, ValueError, TypeError):
            continue
        out.append((round(p * 100), it.get("itemWebUrl") or ""))
    out.sort()
    mkt = row[3]
    if graded:
        out = [x for x in out if x[0] >= mkt]                 # a PSA 10 under the raw price is a mislisting
    else:
        out = [x for x in out if 0.35 * mkt <= x[0] <= 4 * mkt]
    if not out:
        return None
    url = re.sub(r"\?.*$", "", out[0][1])
    return [out[0][0], len(out), url]


def query(row, graded):
    q = re.sub(r"[.*]|\s-\s", " ", f"{base_name(row[2])} {row[6] or ''}")
    q = re.sub(r"\s+", " ", q).strip()
    if row[7] == "pokemon-jp":
        q += " japanese"
    return q + (" PSA 10" if graded else "")


def main(argv):
    site, store = argv[0], argv[1]
    os.makedirs(store, exist_ok=True)
    cpath = os.path.join(store, "cache.json")
    try:
        cache = json.load(open(cpath))
    except (OSError, ValueError):
        cache = {"last_run": "", "cards": {}}
    today = date.today().isoformat()
    fetched = calls = 0
    have_keys = bool(os.environ.get("EBAY_CLIENT_ID") and os.environ.get("EBAY_CLIENT_SECRET"))
    if not have_keys:
        print("ebay: no keys here; republishing cached prices")
    else:
        rows = json.load(open(os.path.join(site, "data", "grading.json")))["rows"]
        once = {}
        for r in rows:
            once[r[0]] = once.get(r[0], 0) + 1
        cutoff = (date.today() - timedelta(days=STALE_DAYS)).isoformat()
        cands = [r for r in rows if once[r[0]] == 1 and r[6] and cache["cards"].get(str(r[0]), {}).get("at", "") <= cutoff]
        cands.sort(key=lambda r: (str(r[0]) in cache["cards"], cache["cards"].get(str(r[0]), {}).get("at", ""), -r[3]))
        for r in cands[:PER_RUN]:
            pid, ent = str(r[0]), {"at": today}
            try:
                for graded in ([False, True] if r[3] >= 3000 else [False]):
                    calls += 1
                    d = ebay.search(query(r, graded), filters="buyingOptions:{FIXED_PRICE},deliveryCountry:US,itemLocationCountry:US,"
                                    + ("conditionIds:{2750}" if graded else "conditionIds:{4000}"))
                    got = best(d.get("itemSummaries") or [], r, graded)
                    if got:
                        ent["p10" if graded else "r"] = got
                    time.sleep(0.25)
                cache["cards"][pid] = ent
                fetched += 1
            except ebay.urllib.error.HTTPError as e:
                if e.code in (401, 403, 429):
                    print(f"::warning title=eBay prices::stopped: HTTP {e.code} {e.read()[:160]!r}")
                    break
                cache["cards"][pid] = {"at": today}
            except Exception as e:  # network hiccup: try again next run
                print(f"ebay: {pid} failed: {e}")
        cache["last_run"] = today
        json.dump(cache, open(cpath, "w"), separators=(",", ":"))
        # daily history of eBay asking prices: cheapest raw / PSA 10 Buy It Now, for cards checked today
        hdir = os.path.join(store, "history")
        os.makedirs(hdir, exist_ok=True)
        hpath = os.path.join(hdir, f"{today}.json")
        try:
            hist = json.load(open(hpath))
        except (OSError, ValueError):
            hist = {}
        for pid, c in cache["cards"].items():
            if c.get("at") == today and (c.get("r") or c.get("p10")):
                hist[pid] = [(c.get("r") or [None])[0], (c.get("p10") or [None])[0]]
        json.dump(hist, open(hpath, "w"), separators=(",", ":"))
    cards = {pid: c for pid, c in cache["cards"].items() if c.get("r") or c.get("p10")}
    with open(os.path.join(site, "data", "ebay.json"), "w", encoding="utf-8") as f:
        json.dump({"updated": cache.get("last_run"), "cards": cards}, f, separators=(",", ":"))
    print(f"ebay: {fetched} cards refreshed ({calls} searches), {len(cards)} cards with eBay prices")


if __name__ == "__main__":
    main(sys.argv[1:])
