"""Independent re-computation of the graded sold-price check (edge-graded.js), written from the spec, not the JS.
python3 tools/graded/ref.py /tmp/graded_cases.json  -> compares every case; break-even and target by brute-force scan."""
import json, math, sys

def jround(x): return math.floor(x + 0.5)          # JavaScript Math.round
def median(xs):
    if not xs: return None
    s = sorted(xs); m = len(s) // 2
    return s[m] if len(s) % 2 else jround((s[m-1] + s[m]) / 2)
def rank(xs, q):
    if not xs: return None
    s = sorted(xs); return s[min(len(s)-1, max(0, math.ceil(q*len(s)) - 1))]

def fee(sell, p):
    if not p: return 0
    base = jround(p * (1 + sell["buyerTax"]/100)); top = sell["topFrom"]
    return jround(sell["perOrder"] + min(base, top)*sell["feePct"]/100 + max(0, base-top)*sell["topPct"]/100)
def ship(sell, p): return sell["ship"] if sell["ship"] is not None else (500 if p >= 5000 else 100)
def net(sell, p): return p - fee(sell, p) - ship(sell, p) - sell["supplies"]

def lowest(sell, ok, limit):
    # brute force: walk every cent (with a coarse pre-scan to keep it quick: net never falls by more than the $4 shipping step)
    p = 0; step = 1000
    while p <= limit:
        if ok(net(sell, p + step)) or p + step > limit:
            for q in range(max(0, p - 2000), p + step + 1):
                if ok(net(sell, q)): return q
        p += step
    return None

def check(c):
    d, sell, cost, o, js = c["data"], c["sell"], c["cost"], c["opts"], c["js"]
    T, roi, mp = o["today"], o["roi"], o["minProfit"]
    rows = sorted([x for x in d["comps"] if x[2] == "PSA 10" and x[3] and T - 90 < x[0] <= T], key=lambda x: -x[0])
    w = lambda n: [x[1] for x in rows if x[0] > T - n]
    p14, p30, p90 = w(14), w(30), [x[1] for x in rows]
    errs = []
    be = lowest(sell, lambda n: n >= cost, 10**8)
    tg = lowest(sell, lambda n: n - cost >= mp and (n - cost)*100 >= cost*roi, 10**8)
    if be != js["breakEven"]: errs.append(("breakEven", be, js["breakEven"]))
    if tg != js["target"]: errs.append(("target", tg, js["target"]))
    if not d["comps"]:
        if js["verdict"] != "insufficient": errs.append(("verdict-empty", js["verdict"]))
        return errs
    s = js["s"]
    exp = dict(n14=len(p14), n30=len(p30), n90=len(p90), m14=median(p14), m30=median(p30), m90=median(p90), q1=rank(p30, .25), q3=rank(p30, .75),
               lo=min(p30) if p30 else None, hi=max(p30) if p30 else None, saleAge=(T - rows[0][0]) if rows else None)
    for k, v in exp.items():
        if s[k] != v: errs.append((k, v, s[k]))
    capped = "PSA 10" in d["capped"]; full30 = (not capped) or d["oldestRead"] is None or T - 30 + 1 >= d["oldestRead"]
    a = p14; b = [x[1] for x in rows if T - 30 < x[0] <= T - 14]
    tr = None
    if len(a) >= 3 and len(b) >= 3 and full30:
        ch = round((median(a) / median(b) - 1) * 10000) / 100
        tr = "lower" if ch <= -10 else "higher" if ch >= 10 else "steady"
    if tr != s["trend"]: errs.append(("trend", tr, s["trend"]))
    reasons = []
    if len(p90) < 5: reasons.append("evidence")
    if len(p30) < 3: reasons.append("liquidity")
    age = exp["saleAge"]
    if age is None or age > 21: reasons.append("fresh")
    m30 = exp["m30"]
    if m30 and (exp["q3"] - exp["q1"]) / 2 / m30 * 100 > 35: reasons.append("spread")
    if reasons != js["reasons"]: errs.append(("reasons", reasons, js["reasons"]))
    typ = m30
    if typ != js["typical"]: errs.append(("typical", typ, js["typical"]))
    if typ is not None:
        n = net(sell, typ)
        if n != js["net"]: errs.append(("net", n, js["net"]))
        if n - cost != js["profit"]: errs.append(("profit", n - cost, js["profit"]))
        v = "insufficient" if reasons else ("sell" if (n - cost) >= mp and (n - cost)*100 >= cost*roi else "hold")
    else: v = "insufficient"
    if v != js["verdict"]: errs.append(("verdict", v, js["verdict"]))
    return errs

cases = json.load(open(sys.argv[1]))
bad = [(i, e) for i, c in enumerate(cases) if (e := check(c))]
from collections import Counter
print(f"{len(cases)} cases, {len(cases) - len(bad)} match", dict(Counter(c['js']['verdict'] for c in cases)))
for i, e in bad[:10]: print(i, e)
sys.exit(1 if bad else 0)
