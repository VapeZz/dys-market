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


CODE = re.compile(r"\b[A-Z]{1,3}\d{3,5}[- ]?\d{3}\b|\b[A-Z]?\d{6}[- ]\d{3}\b")
FILTERS = "buyingOptions:{FIXED_PRICE},conditionIds:{1000|1500},deliveryCountry:US,itemLocationCountry:US"


def name_query(n, brand):
    """'Air Jordan 6 "White Infrared"' -> words that every real listing title has."""
    n = re.sub(r"[\"“”']", " ", n).replace("’", " ")
    n = re.sub(r"^(Nike|Jordan|adidas|New Balance|Vans|PUMA)\s+(?=\w)", "", n, flags=re.I) if brand != "Jordan" else n
    n = re.sub(r"\b(Men'?s|Women'?s|Wmns|Premium|Retro|OG|Low|Mid|High)\b", lambda m: m.group(0) if m.group(0).lower() in ("low", "mid", "high") else " ", n, flags=re.I)
    return [w for w in re.split(r"[^A-Za-z0-9.]+", n) if w and w.upper() not in ("X", "AND", "THE", "OF")]


def scout(row):
    code = row["c"]
    words = name_query(row.get("n") or "", row.get("b"))
    seen, asks = set(), []
    for q, by_code in ((code, True), (" ".join(words), False)):
        if not q.strip():
            continue
        d = ebay.search(q, category=None, limit=100, filters=FILTERS)
        for it in d.get("itemSummaries") or []:
            t = it.get("title", "")
            iid = it.get("itemId")
            if iid in seen or KIDS.search(t) or BAD.search(t) or not it.get("price"):
                continue
            has_code = norm(code) in norm(t)
            if by_code and not has_code:
                continue
            if not by_code and not has_code:
                other = [c for c in CODE.findall(t.upper()) if norm(c) != norm(code)]
                if other or not all(re.search(r"(?<![A-Z0-9])" + re.escape(w.upper()) + r"(?![A-Z0-9])", t.upper()) for w in words):
                    continue
            seen.add(iid)
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
