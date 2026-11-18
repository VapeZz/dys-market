"""Independent re-computation of the selling-option comparison (edge-channels.js), written from the spec.
python3 tools/channels/ref.py /tmp/ch_cases.json ; break-even, target and 'matches eBay' found by scanning prices."""
import json, math, re, sys

def jr(x): return math.floor(x + 0.5)
DEF = {"fb": dict(local=1, pricePct=90, feePct=0, feeFlat=0, pay="cash", ship=0, sup=0, travel=0, booth=0, boothSales=10, taxPct=0),
       "offerup": dict(local=1, pricePct=90, feePct=0, feeFlat=0, pay="cash", ship=0, sup=0, travel=0, booth=0, boothSales=10, taxPct=0),
       "show": dict(local=1, pricePct=90, feePct=0, feeFlat=0, pay="cash", ship=0, sup=0, travel=0, booth=0, boothSales=10, taxPct=0),
       "ebay": dict(local=0, pricePct=100, tiered=1, feePct=13.25, topPct=2.35, topFrom=750000, feeFlat=40, buyerTax=7.5, ship=None, sup=50, travel=0, booth=0, boothSales=10),
       "vinted": dict(local=0, pricePct=85, feePct=0, feeFlat=0, ship=0, sup=50, travel=0, booth=0, boothSales=10)}
PAY = {"cash": (0, 0), "venmo": (2.99, 0), "venmobiz": (1.9, 10), "paypal": (2.99, 0), "card": (2.6, 15), "custom": (0, 0)}

def chan(k, saved):
    c = dict(DEF[k]); c.update(saved.get(k, {}))
    if c["local"]:
        p = PAY.get(c.get("pay"), (0, 0))
        c.setdefault("payPct", p[0]); c.setdefault("payFlat", p[1])
        if c.get("payPct") is None: c["payPct"] = p[0]
        if c.get("payFlat") is None: c["payFlat"] = p[1]
    else: c["payPct"] = c["payFlat"] = 0; c["taxPct"] = 0
    return c

def net(c, p):
    tax = jr(p * c.get("taxPct", 0) / 100) if c["local"] and p else 0
    if not p: fee = 0
    elif c.get("tiered"):
        b = jr(p * (1 + c["buyerTax"] / 100)); top = c["topFrom"]
        fee = jr(c["feeFlat"] + min(b, top) * c["feePct"] / 100 + max(0, b - top) * c["topPct"] / 100)
    else: fee = jr(p * c["feePct"] / 100) + c["feeFlat"]
    pay = jr((p + tax) * c["payPct"] / 100) + c["payFlat"] if p and (c["payPct"] or c["payFlat"]) else 0
    ship = (500 if p >= 5000 else 100) if c["ship"] is None else c["ship"]
    booth = jr(c["booth"] / max(1, c["boothSales"] or 1)) if c["booth"] else 0
    return p - fee - pay - ship - c["sup"] - c["travel"] - booth, tax, pay, fee

def lowest(c, ok):
    # scan: coarse steps, then every cent around the first coarse hit (net falls at most ~$4 at the $50 shipping step)
    p, step = 0, 500
    while p < 10**9:
        if ok(net(c, p)[0]) or (p <= 5000 <= p + step):
            for q in range(max(0, p - step), p + step + 1):
                if ok(net(c, q)[0]): return q
        p += step
    return None

def elig(k, item):
    if k != "vinted": return True
    if item["kind"] == "graded": return False
    if item["kind"] == "sealed": return bool(re.search(r"booster (pack|box)|booster bundle|\bbooster\b", item["name"], re.I))
    return True

bad = 0
cases = json.load(open(sys.argv[1]))
for i, cs in enumerate(cases):
    o, js = cs["o"], cs["js"]; cost, roi, mp = o["cost"], o["roi"], o["minProfit"]
    rows = {}
    for k in ["fb", "offerup", "show", "ebay", "vinted"]:
        c = chan(k, o["saved"])
        price = o["prices"].get(k) if k in o["prices"] else (jr(o["ref"] * c["pricePct"] / 100) if o["ref"] is not None else None)
        n = t = pay = fee = None
        if price is not None: n, t, pay, fee = net(c, price)
        profit = n - cost if n is not None else None
        rows[k] = dict(k=k, price=price, net=n, tax=t, pay=pay, fee=fee, profit=profit,
                       clears=profit is not None and profit >= mp and profit * 100 >= cost * roi,
                       breakEven=lowest(c, lambda x: x >= cost), target=lowest(c, lambda x: x - cost >= mp and (x - cost) * 100 >= cost * roi),
                       ok=elig(k, o["item"]), c=c)
    for k, r in rows.items():
        r["matchEbay"] = lowest(r["c"], lambda x: x >= rows["ebay"]["net"]) if k != "ebay" and rows["ebay"]["net"] is not None else None
    ranked = sorted([r for r in rows.values() if r["profit"] is not None and r["ok"]], key=lambda r: -r["profit"])
    best = ranked[0]["k"] if ranked else None
    errs = [] if best == js["best"] else [("best", best, js["best"])]
    for jr_ in js["rows"]:
        r = rows[jr_["k"]]
        for f in ["price", "net", "tax", "pay", "fee", "profit", "clears", "breakEven", "target", "matchEbay", "ok"]:
            if r[f] != jr_[f]: errs.append((jr_["k"], f, r[f], jr_[f]))
    if errs:
        bad += 1
        if bad <= 5: print(i, errs[:4])
print(f"{len(cases)} cases, {len(cases) - bad} match")
sys.exit(1 if bad else 0)
