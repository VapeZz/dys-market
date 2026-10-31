"""eBay resale check for upcoming sneaker releases (eBay Browse API, live Buy It Now listings).

    python tools/sneaker_scout.py PAGES_DIR --from 2026-11-01 --to 2026-11-07 [--out scout.json]

Reads PAGES_DIR/sneakers.json (the release calendar). For every release with a style code in the
window, searches eBay US for new-with-box Buy It Now listings of that exact style code (presales
before release day) and keeps adult pairs only. Prints one annotation with the numbers and writes
{"at", "from", "to", "pairs": [{c, n, d, r, b, h, n_ask, low, p25, med}]} to --out.
These are ASKING prices: the posting task checks real eBay SOLD prices before anything is posted.
"""
import json
import os
import re
import statistics
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ebay  # noqa: E402

KIDS = re.compile(r"\b(gs|ps|td|grade ?school|pre-?school|toddler|kids?|youth|little kids|big kids|infant|baby|crib|[0-9]{1,2}(\.5)?c|[1-7](\.5)?y)\b", re.I)
BAD = re.compile(r"replica|\breps?\b|unauthori[sz]ed|\bua\b|laces?\b|box only|no box|insoles?|keychain|charm|sticker|poster|"
                 r"used|pre-?owned|worn|\bread\b|custom|\blot\b|bundle|raffle|\bdeposit\b|\bpreorder deposit\b", re.I)


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def total(it):
    p = float(it["price"]["value"])
    ship = (it.get("shippingOptions") or [{}])[0].get("shippingCost", {}).get("value")
    return p + (float(ship) if ship else 0.0)


def scout(row):
    code = row["c"]
    d = ebay.search(code, category=None, limit=100,
                    filters="buyingOptions:{FIXED_PRICE},conditionIds:{1000},deliveryCountry:US,itemLocationCountry:US")
    asks = []
    for it in d.get("itemSummaries") or []:
        t = it.get("title", "")
        if norm(code) not in norm(t) or KIDS.search(t) or BAD.search(t) or not it.get("price"):
            continue
        v = total(it)
        r = row.get("r") or 0
        if r and not (0.5 * r <= v <= 6 * r):   # scams, kids sizes or "make an offer" placeholders
            continue
        asks.append(v)
    asks.sort()
    if not asks:
        return dict(n_ask=0)
    q = statistics.quantiles(asks, n=4) if len(asks) >= 4 else [asks[0], statistics.median(asks), asks[-1]]
    return dict(n_ask=len(asks), low=round(asks[0], 2), p25=round(q[0], 2), med=round(statistics.median(asks), 2))


def main(argv):
    pages = argv[0]
    a, b = argv[argv.index("--from") + 1], argv[argv.index("--to") + 1]
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    cal = json.load(open(os.path.join(pages, "sneakers.json")))
    rows = [r for r in cal["releases"] if a <= r["d"] <= b and r.get("c")]
    pairs = []
    for r in rows:
        try:
            s = scout(r)
        except Exception as e:  # one bad search shouldn't stop the rest
            s = dict(n_ask=0, err=str(e)[:80])
        pairs.append(dict({k: r.get(k) for k in ("c", "n", "d", "r", "b", "h")}, **s))
    res = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "from": a, "to": b, "pairs": pairs}
    if out:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        json.dump(res, open(out, "w"), indent=1)
    # one compact annotation (the API only returns 10 per step): code|retail|asks|low|p25|med
    lines = [f"{p['d'][5:]} {p['c']} r{p.get('r') or '?'} n{p['n_ask']}" + (f" lo{p['low']:.0f} q{p['p25']:.0f} m{p['med']:.0f}" if p["n_ask"] else "")
             for p in sorted(pairs, key=lambda p: (p["d"], -(p.get("h") or 0)))]
    print("::notice title=Sneaker scout::" + " ; ".join(lines)[:3900])


if __name__ == "__main__":
    main(sys.argv[1:])
