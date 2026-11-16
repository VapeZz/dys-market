"""Second, separately written Deal Check (M1), for the cross-check only.

Written from the rules in the header of site/assets/edge-deal.js, not from its code. It reads cases and the
app's answers (tools/deal/dump.js), works each case out again and reports every difference.
    node tools/deal/dump.js 20000 > /tmp/deal.json && python3 tools/deal/ref.py /tmp/deal.json
"""
import json
import math
import sys

SCOPE_MIN, MIN_COMPS, MIN_SALES_30, MAX_FETCH_AGE, MAX_SALE_AGE = 2000, 5, 3, 3, 21
MAX_SPREAD, MAX_DISAGREE, FALLING, MIN_PROFIT = 25, 25, 10, 500
GRADE_MIN_POP, GRADE_MIN_SALES_30, LOWER_GRADES = 100, 2, 0.9
COND = {"NM": 1, "LP": 0.85, "MP": 0.7, "HP": 0.55, "DMG": 0.4}

# settings as in tools/deal/synth.js cfg()
FEE_PCT, FEE_FLAT, BUYER_TAX, ROI, HOLD = 13.25, 40, 7.5, 20, 1
GRADE_FEE, GRADE_SHIP, GRADE_MONTHS = 2500, 1500, 3


def js_round(x):
    return math.floor(x + 0.5)


def ship_out(p, t):
    return (1500 if p >= 10000 else 800) if t == "s" else (500 if p >= 5000 else 100)


def supplies(t):
    return 150 if t == "s" else 50


def net(p, t):
    if not p:
        return 0
    fee = js_round(js_round(p * (1 + BUYER_TAX / 100)) * FEE_PCT / 100 + FEE_FLAT)
    return p - fee - ship_out(p, t) - supplies(t)


def cost_in(ask, offer):
    return ask + js_round(ask * (offer.get("taxIn") or 0) / 100) + (offer.get("shipIn") or 0)


def med(xs):
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else js_round((s[n // 2 - 1] + s[n // 2]) / 2)


def nearest_rank(xs, q):
    s = sorted(xs)
    k = math.ceil(q * len(s)) - 1
    return s[min(len(s) - 1, max(0, k))]


def r2(x):
    return js_round(x * 100) / 100


def evidence(comps, grade, day):
    w = [c for c in comps if c[2] == grade and c[3] and day - 90 < c[0] <= day]
    p90 = [c[1] for c in w]
    p30 = [c[1] for c in w if c[0] > day - 30]
    m90 = med(p90)
    m30 = med(p30) if len(p30) >= MIN_SALES_30 else None
    e = {"n90": len(p90), "n30": len(p30), "m90": m90, "m30": m30}
    e["sale_age"] = day - max(c[0] for c in w) if w else None
    if m90:
        e["spread"] = r2((nearest_rank(p90, 0.75) - nearest_rank(p90, 0.25)) / 2 / m90 * 100)
    else:
        e["spread"] = None
    e["change"] = r2((m30 / m90 - 1) * 100) if m30 and m90 else None
    e["exit"] = min(m30, m90) if (m30 is not None and m90 is not None) else m90
    return e


def ev_gates(e, item, data, day, second, warning):
    g = {}
    g["evidence"] = e["n90"] >= MIN_COMPS
    g["liquidity"] = e["n30"] >= MIN_SALES_30
    fa = None if data.get("asOf") is None else day - data["asOf"]
    g["fresh"] = fa is not None and fa <= MAX_FETCH_AGE and e["sale_age"] is not None and e["sale_age"] <= MAX_SALE_AGE
    g["spread"] = e["spread"] is not None and e["spread"] <= MAX_SPREAD
    if second:
        tcg, ta = item.get("tcg"), (None if item.get("tcgDay") is None else day - item["tcgDay"])
        d = r2((tcg / e["m90"] - 1) * 100) if tcg and e["m90"] else None
        g["agree"] = d is not None and abs(d) <= MAX_DISAGREE and ta is not None and ta <= MAX_FETCH_AGE
    flagged = bool(warning) and warning.get("id") in ("knife", "breakdown") and warning.get("verdict") == "pass"
    g["trend"] = not (e["change"] is not None and e["change"] <= -FALLING) and not flagged
    return g


def max_ask(proceeds, offer):
    """Highest whole-cent ask that clears both the ROI target and the minimum profit (by stepping down)."""
    if not proceeds or proceeds <= 0:
        return 0

    def ok(a):
        c = cost_in(a, offer)
        return proceeds - c >= MIN_PROFIT and (proceeds - c) * 100 >= c * ROI

    if not ok(0):
        return 0
    # profit falls as the ask rises, so a solved guess plus a short walk finds the edge
    a = max(0, int(proceeds / (1 + ROI / 100)) - 2000)
    while a > 0 and not ok(a):
        a -= 100
    while ok(a + 1):
        a += 1
    return a


def rise_needed(exit_, t, cost, months):
    """Lowest whole-cent sale price whose net (fee on that price; shipping and supplies at the exit's level) covers
    the cost plus the cost of money, found by walking up in shrinking steps."""
    target = js_round(cost * (1 + HOLD / 100 * months))
    fixed = ship_out(exit_, t) + supplies(t)

    def n(p):
        return p - js_round(js_round(p * (1 + BUYER_TAX / 100)) * FEE_PCT / 100 + FEE_FLAT) - fixed

    if n(exit_) >= target:
        return 0
    p, step = exit_, 1 << 30
    while step >= 1:
        while n(p + step) < target:
            p += step
        step //= 2
    return (p + 1 - exit_) / exit_ * 100


def check(case, day):
    item, data, offer, ctx = case["item"], case["data"] or {}, case["offer"], case.get("ctx") or {}
    warning = ctx.get("warning")
    comps = data.get("comps") or []
    t = item["t"]
    out = {}
    # resale
    e = evidence(comps, "sealed" if t == "s" else "raw", day)
    cm = 1 if t == "s" else COND.get(offer.get("cond"), 1)
    exit_ = js_round(e["exit"] * cm) if e["exit"] else None
    cost = cost_in(offer["ask"], offer)
    proceeds = net(exit_, t) if exit_ else None
    profit = proceeds - cost if proceeds is not None else None
    g = ev_gates(e, item, data, day, True, warning)
    g["margin"] = profit is not None and profit >= MIN_PROFIT and profit * 100 >= cost * ROI
    flip_pass = all(g.values())
    out["flip"] = {"exit": exit_, "profit": profit, "max": max_ask(proceeds, offer) if proceeds else 0, "gates": g, "pass": flip_pass}
    # grade
    grade = None
    if t == "c":
        pop = data.get("pop")
        pop_ok = bool(pop) and pop["total"] >= GRADE_MIN_POP
        e10, e9 = evidence(comps, "PSA 10", day), evidence(comps, "PSA 9", day)
        raw_exit = exit_  # the same raw exit, condition applied
        expected = None
        if offer.get("cond") == "NM" and pop_ok and e10["exit"] and e9["exit"] and raw_exit:
            p10, p9 = pop["g10"] / pop["total"], pop["g9"] / pop["total"]
            expected = js_round(p10 * net(e10["exit"], "c") + p9 * net(e9["exit"], "c") + (1 - p10 - p9) * net(js_round(raw_exit * LOWER_GRADES), "c"))
        gcost = cost + GRADE_FEE + GRADE_SHIP + js_round(offer["ask"] * HOLD / 100 * GRADE_MONTHS)
        gprofit = expected - gcost if expected is not None else None
        g10 = ev_gates(e10, item, data, day, False, warning)
        ok = (offer.get("cond") == "NM" and pop_ok and e10["n30"] >= GRADE_MIN_SALES_30 and e10["n90"] >= MIN_COMPS
              and g10["fresh"] and g10["trend"] and g10["spread"] and e9["n90"] >= MIN_COMPS
              and gprofit is not None and gprofit >= MIN_PROFIT and gprofit * 100 >= gcost * ROI)
        grade = {"expected": expected, "profit": gprofit, "pass": ok}
    out["grade"] = grade
    out["hold"] = None if not exit_ else {"m6": rise_needed(exit_, t, cost, 6), "m12": rise_needed(exit_, t, cost, 12)}
    # verdict
    scope = (e["m90"] or item.get("tcg") or 0) >= SCOPE_MIN
    cands = [r for r in (("flip", flip_pass, profit), ("grade", grade and grade["pass"], grade and grade["profit"])) if r[1]]
    cands.sort(key=lambda r: -r[2])
    if not scope or not cands:
        out["verdict"], out["route"] = "pass", None
    else:
        out["verdict"], out["route"] = "buy", cands[0][0]
    miss = sum(1 for k in ("evidence", "liquidity", "fresh", "spread", "agree") if not g[k])
    deep = e["n90"] >= MIN_COMPS * 3 and e["n30"] >= MIN_SALES_30 * 2
    out["confidence"] = ("A" if deep else "B") if miss == 0 else "C" if miss == 1 else "D"
    out["scope"] = scope
    return out


def main(path):
    doc = json.load(open(path))
    day, diffs, n = doc["today"], [], 0
    verdicts = {}
    for i, (case, app) in enumerate(zip(doc["cases"], doc["results"])):
        ref = check(case, day)
        n += 1
        verdicts[ref["verdict"]] = verdicts.get(ref["verdict"], 0) + 1

        def cmp(name, a, b, tol=0):
            if a is None or b is None:
                if a is not b and not (a is None and b is None):
                    diffs.append((i, name, a, b))
            elif abs(a - b) > tol if isinstance(a, (int, float)) and not isinstance(a, bool) else a != b:
                diffs.append((i, name, a, b))

        for k in ("verdict", "route", "confidence", "scope"):
            cmp(k, ref[k], app[k])
        for k in ("exit", "profit", "max", "pass"):
            cmp("flip." + k, ref["flip"][k], app["flip"][k])
        for k, v in ref["flip"]["gates"].items():
            cmp("gate." + k, v, app["flip"]["gates"].get(k))
        if (ref["grade"] is None) != (app["grade"] is None):
            diffs.append((i, "grade", ref["grade"], app["grade"]))
        elif ref["grade"]:
            for k in ("expected", "profit", "pass"):
                cmp("grade." + k, ref["grade"][k], app["grade"][k])
        if (ref["hold"] is None) != (app["hold"] is None):
            diffs.append((i, "hold", ref["hold"], app["hold"]))
        elif ref["hold"]:
            for k in ("m6", "m12"):
                cmp("hold." + k, ref["hold"][k], app["hold"][k], tol=1e-9)
    print(f"{n} cases, verdicts {verdicts}, {len(diffs)} differences")
    for d in diffs[:20]:
        print("  case", d)
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
