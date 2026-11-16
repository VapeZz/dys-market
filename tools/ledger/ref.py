"""An independent re-implementation of the ledger's math (edge-ledger.js compute), written from the rules in its
header comment, not from its code. Compares on random ledgers from random_ledgers.js.
    python3 tools/ledger/ref.py <seed> <count>"""
import json, subprocess, sys, os
from datetime import date
from fractions import Fraction as Q

BOOKS = ["Business", "Personal"]

def alloc(amount, weights):
    """split exactly by weight; leftover cents to the biggest fractional parts, ties to the earlier line"""
    n = len(weights)
    if not n: return []
    w = [max(0, x) for x in weights]; tot = sum(w)
    if not tot:
        base = int(amount / n); out = [base] * n; r = amount - base * n; i = 0
        while r: out[i] += 1 if r > 0 else -1; r -= 1 if r > 0 else -1; i += 1
        return out
    raw = [Q(amount) * x / tot for x in w]
    out = [int(x) for x in raw]          # toward zero, like Math.trunc
    rest = amount - sum(out)
    order = sorted(range(n), key=lambda i: (-abs(raw[i] - int(raw[i])), i))
    k = 0
    while rest:
        i = order[k % n]; step = 1 if rest > 0 else -1; out[i] += step; rest -= step; k += 1
    return out

def jsround(x):  # Math.round: half up
    from math import floor
    return int(floor(x + Q(1, 2)))

def ref(case):
    T, prices, year, as_of = case["T"], case["prices"], case["year"], case["asOf"]
    ok = lambda r: not r.get("void") and (not as_of or not r.get("day") or r["day"] <= as_of)
    buys = [b for b in T["buys"] if ok(b)]; items = [x for x in T["items"] if ok(x)]
    sales = sorted([s for s in T["sales"] if ok(s)], key=lambda s: (s["day"], s["id"]))
    costs = [c for c in T["costs"] if ok(c)]; cash = [c for c in T["cash"] if ok(c)]
    it = {x["id"]: dict(x, base=x["price"] * x["qty"], extra=0, added=0, sold=0, soldCost=0) for x in items}
    tot = {k: dict(cash=0, costHeld=0, value=0, realized=0, expenses=0, unreal=0) for k in BOOKS + ["All"]}
    def add(book, key, v):
        for k in (book if book in BOOKS else "Business", "All"): tot[k][key] += v
    for b in buys:
        lines = [x for x in it.values() if x["buy"] == b["id"]]
        parts = alloc(b["tax"] + b["ship"] + b["fees"], [x["base"] for x in lines])
        for x, p in zip(lines, parts): x["extra"] = p
        add(b["book"], "cash", -(sum(x["base"] for x in lines) + b["tax"] + b["ship"] + b["fees"]))
    for c in costs:
        if c["item"] and c["item"] in it: it[c["item"]]["added"] += c["amount"]
        add(c["book"], "cash", -c["amount"])
        if not c["item"] and c["day"][:4] == year: add(c["book"], "expenses", c["amount"])
    for x in it.values(): x["cost"] = x["base"] + x["extra"] + x["added"]
    out_sales = []
    for s in sales:
        x = it.get(s["item"]); q = max(0, s["qty"]) or 1
        net = s["price"] + s["shipIn"] - s["fees"] - s["shipOut"] - s["supplies"] - s["other"]
        cost, held = 0, None
        if x:
            sl = lambda k: jsround(Q(x["cost"]) * min(k, x["qty"]) / x["qty"]) if x["qty"] else 0
            cost = sl(x["sold"] + q) - sl(x["sold"]); x["sold"] += q; x["soldCost"] += cost
            held = (date.fromisoformat(s["day"]) - date.fromisoformat(x["day"])).days
        out_sales.append([s["id"], cost, net, net - cost, held])
        add(s["book"], "cash", net)
        if s["day"][:4] == year: add(s["book"], "realized", net - cost)
    for c in cash:
        a = c["amount"]
        if c["kind"] == "Money out": add(c["book"], "cash", -a)
        elif c["kind"] == "Move":
            if c.get("to") and c["to"] != c["book"]: add(c["book"], "cash", -a); add(c["to"], "cash", a)
        else: add(c["book"], "cash", a)
    out_items = []
    for x in it.values():
        left = max(0, x["qty"] - x["sold"]); cl = x["cost"] - x["soldCost"]
        each = prices.get(x["id"]) if left else None
        value = None if each is None else each * left
        out_items.append([x["id"], x["cost"], left, cl, value])
        if left:
            add(x["book"], "costHeld", cl)
            if value is not None: add(x["book"], "value", value); add(x["book"], "unreal", value - cl)
    return out_items, out_sales, tot

def main():
    seed, count = sys.argv[1], sys.argv[2]
    cases = json.loads(subprocess.check_output(["node", os.path.join(os.path.dirname(__file__), "random_ledgers.js"), seed, count]))
    diffs = 0
    for n, c in enumerate(cases):
        items, sales, tot = ref(c)
        e = c["edge"]
        if sorted(map(tuple, items)) != sorted(map(tuple, e["items"])): diffs += 1; print("items differ", n); continue
        if list(map(tuple, sales)) != list(map(tuple, e["sales"])): diffs += 1; print("sales differ", n); continue
        for k in BOOKS + ["All"]:
            for f in ("cash", "costHeld", "value", "realized", "expenses", "unreal"):
                if tot[k][f] != e["tot"][k][f]: diffs += 1; print("total differs", n, k, f, tot[k][f], e["tot"][k][f])
    print(f"{len(cases)} random ledgers, {diffs} differences")
    sys.exit(1 if diffs else 0)

main()
