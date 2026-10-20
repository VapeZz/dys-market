"""Daily Scout: the owner's ranked buy list -> site/data/scout.json (unlisted page scout.html).

    python pipeline/scout.py

Every card worth $10+ and sealed item worth $20+ is checked against three buy plans, and the
best plan wins. Everything comes from numbers the site already records, with plain rules:

  flip  Lowest TCGplayer listing is far enough under market that buying it and reselling at
        market clears a profit after fees and shipping.
  ride  Price has climbed steadily all week (not a one-day spike) and still trades often.
  dip   Price is well off its recent high, has stopped falling, and the set isn't brand new.

Each pick gets a 0-100 score, a verdict (buy / watch), plain-English reasons, risk flags and a
max buy price. Items falling steadily are listed separately as "avoid for now".

Inputs: site/data/set/*.json (market price + daily series), data/lows/latest.json (lowest and
median listing per product, saved by run.py), site/data/demand.json (collector want lists),
data/catalog/products.json. Fee and shipping defaults below; the page lets you change them.
"""
import glob
import json
import os
import re
from datetime import date

import config
from build import label

# ---- selling costs (defaults; the page has a settings panel to change them) ------------------
FEE_PCT = 13.25            # TCGplayer marketplace commission 10.75% + payment processing 2.5%
FEE_FLAT = 30              # payment processing, cents per order
SHIP_SELL = {"c": 100, "c50": 500, "s": 800, "s100": 1500}   # cents: card / card $50+ tracked / sealed / sealed $100+
SHIP_BUY = {"c": 150, "s": 600}                               # what you pay to have it shipped to you
TARGET_ROI = 20            # % profit a flip should clear; sets the max buy price

MIN_CARD, MIN_SEALED = 1000, 2000
SKIP = re.compile(r"prerelease|\[staff\]|code card|\bjumbo\b|oversize|\bdeck\b.*\bcard\b|world championships|display case", re.I)
PER_PLAN = 60              # picks kept per plan
AVOID_N = 20


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def money(c):
    return f"${c / 100:,.2f}" if c < 100000 else f"${c / 100:,.0f}"


def sell_net(p, t):
    ship = SHIP_SELL["s100" if p >= 10000 else "s"] if t == "s" else SHIP_SELL["c50" if p >= 5000 else "c"]
    return p * (1 - FEE_PCT / 100) - FEE_FLAT - ship


def max_buy(p, t):
    """Highest price to pay so reselling at market clears TARGET_ROI after all costs."""
    return max(0, int(sell_net(p, t) / (1 + TARGET_ROI / 100) - SHIP_BUY[t]))


def pct(a, b):
    return (a - b) / b * 100 if a and b else None


def analyse(dates, series, p):
    """Trend facts from the recorded daily prices (None-safe; works with a week of history)."""
    pts = [(d, v) for d, v in zip(dates, series or []) if v]
    if not pts or pts[-1][1] != p:
        pts.append((dates[-1] if dates else "", p))
    vals = [v for _, v in pts]
    last8 = vals[-8:]
    steps = [b - a for a, b in zip(last8, last8[1:])]
    moved = [x for x in steps if x]
    ups, downs = sum(x > 0 for x in moved), sum(x < 0 for x in moved)
    jumps = [pct(b, a) for a, b in zip(last8, last8[1:]) if a]
    prior = sorted(vals[-31:-1]) or [p]
    typical = prior[len(prior) // 2]          # median of the last month, so one odd sale isn't "the high"
    hi = max(vals[-31:])
    return {
        "n": len(vals),
        "w7": pct(last8[-1], last8[0]) if len(last8) >= 2 else None,
        "w30": pct(vals[-1], vals[-31]) if len(vals) >= 31 else None,
        "steps": len(steps), "moved": len(moved), "ups": ups, "downs": downs,
        "spike": max(jumps, default=0),
        "hi": hi, "typical": typical, "drop": (typical - p) / typical * 100 if typical else 0,
        "at_hi": p >= max(last8), "at_lo": p <= min(last8),
        "settled": len(vals) >= 3 and vals[-1] >= vals[-2] >= vals[-3] * 0.99 if len(vals) >= 3 else False,
        "w_start": last8[0],
        "spark": vals[-30:],
    }


def score_item(i, s, a, lo, mid, wants, today):
    p, t = i["p"], i["t"]
    age = (date.fromisoformat(today) - date.fromisoformat(s["pub"][:10])).days if s.get("pub") else None
    new_set = age is not None and age < (120 if t == "s" else 60)
    risk, common = [], []

    # how often it actually trades: the market price only moves when something sells
    if a["steps"] >= 4:
        ratio = a["moved"] / a["steps"]
        if ratio >= 0.5:
            liq = 12
            common.append(f"Market price moved on {a['moved']} of the last {a['steps']} days, so it sells regularly")
        elif ratio == 0:
            liq = -18
            risk.append(f"Market price hasn't moved in {a['steps']} days: few recent sales, may be slow to resell")
        else:
            liq = 0
    else:
        liq = 0
    if mid:
        spread = (mid - p) / p * 100
        if spread <= 20:
            liq += 6
        elif spread >= 60:
            liq -= 10
            risk.append(f"Listings are scattered (median listing {spread:.0f}% over market): hard to price")
    if a["spike"] >= 30:
        risk.append(f"Jumped {a['spike']:.0f}% in a single day this week: could be a pump or one odd sale")
    if new_set:
        risk.append(f"New set ({age} days out): prices usually slide while it's still being printed")
    if wants:
        common.append(f"{wants['c']} collector{'s' if wants['c'] != 1 else ''} on the site want{'s' if wants['c'] == 1 else ''} it"
                      + (f", paying up to {money(wants['mx'])}" if wants.get("mx") else ""))
    demand = min(10, 4 * wants["c"]) if wants else 0
    old = age is not None and age >= 730
    vintage = age is not None and age >= 365 * 15

    plans = []

    # ---- flip: lowest listing far under market ------------------------------------------------
    if lo and lo < p:
        off = (1 - lo / p) * 100
        cost = lo + SHIP_BUY[t]
        profit = sell_net(p, t) - cost
        roi = profit / cost * 100
        floor = 300 if t == "c" else 800
        if 12 <= off <= 55 and profit >= floor and roi >= 12:
            why = [f"Lowest listing {money(lo)} is {off:.0f}% under the {money(p)} market",
                   f"Resell at market clears about {money(profit)} ({roi:.0f}%) after TCGplayer fees and shipping"]
            r, hold = [], False
            sc = 40 + min(roi, 50) * 0.4 + min(profit / 500, 10) + liq + demand
            if off > 35 or (vintage and off > 20):
                sc -= 15
                hold = True
                r.append("Lowest listing covers any condition and this one is deep under market: open it and confirm Near Mint"
                         if not vintage else "Vintage card: the cheapest listing is usually played. Confirm condition before buying")
            if a["w7"] is not None and a["w7"] <= -8:
                sc -= 12
                r.append(f"Down {-a['w7']:.0f}% this week: market may keep falling before you resell")
            elif a["w7"] is not None and a["w7"] >= 3:
                sc += 4
                why.append(f"Up {a['w7']:.0f}% this week")
            if roi < TARGET_ROI:
                hold = True
                r.append(f"Under your {TARGET_ROI}% target after fees")
            plans.append(("flip", sc, why, r, hold, {"lo": lo, "off": round(off, 1), "profit": int(profit), "roi": round(roi, 1)}))

    # you can only ride or buy a dip if someone is selling near the market price
    buyable = lo is None or lo <= p * 1.12

    # ---- ride: steady climb ---------------------------------------------------------------------
    w = a["w7"]
    if buyable and w is not None and w >= 5 and a["moved"] >= 3 and a["ups"] / a["moved"] >= 0.6 and a["at_hi"] and a["spike"] < 30:
        cons = a["ups"] / a["moved"]
        eff = w if w <= 25 else max(0, 25 - (w - 25) * 0.8)     # reward a steady climb, not a run you'd be chasing
        sc = 30 + eff + cons * 15 + liq + demand - (12 if new_set else 0)
        why = [f"Up {w:.0f}% this week, rising on {a['ups']} of {a['moved']} price changes and at its weekly high"]
        r, hold = [], False
        if w > 30:
            hold = True
            r.append(f"Already up {w:.0f}% this week: late entry, these often cool off")
        if a["w30"] is not None and a["w30"] > 0:
            why.append(f"Up {a['w30']:.0f}% over 30 days too, so it's not just one week")
            sc += 5
        stop = a["w_start"]
        why.append(f"Hold while it trends; the trend is broken if it closes under {money(stop)} (last week's start)")
        plans.append(("ride", sc, why, r, hold, {"stop": stop}))

    # ---- dip: off its high, stopped falling, established set ------------------------------------
    if buyable and a["drop"] >= 12 and a["settled"] and not new_set and a["n"] >= 5 and a["moved"] >= 3:
        sc = 34 + min(a["drop"], 40) * 0.7 + liq + demand + (8 if old else 0) + (6 if a["at_lo"] is False else 0)
        why = [f"{a['drop']:.0f}% under its usual price of {money(a['typical'])} (median of recent days)",
               "Stopped falling: last few days flat or up",
               f"Back to its usual price would be +{money(a['typical'] - p)}"]
        if old:
            why.append(f"Set is {age // 365} years old and out of print, so no reprint pressure")
        plans.append(("dip", sc, why, [], False, {"hi": a["typical"]}))

    if not plans:
        return None
    plan, sc, why, r, hold, extra = max(plans, key=lambda x: x[1])
    sc = max(0, min(99, round(sc)))
    flags = r + risk
    # a likely pump, a late entry, a condition question or a thin margin never gets a straight "buy"
    hold = hold or a["spike"] >= 30
    verdict = "buy" if sc >= 68 and not hold else ("watch" if sc >= 50 else None)
    if not verdict:
        return None
    return {"plan": plan, "score": sc, "v": verdict, "why": why + common, "risk": flags, "age": age,
            "max": max_buy(p, t) if plan == "flip" else p, **extra}


def main():
    out_dir = config.OUT_DIR
    meta = load(os.path.join(out_dir, "meta.json"), {}) or {}
    today = meta.get("updated") or date.today().isoformat()
    products = load(os.path.join(config.DATA_DIR, "catalog", "products.json"), {}) or {}
    lows_doc = load(os.path.join(config.DATA_DIR, "lows", "latest.json"), {}) or {}
    lows, mids = {}, {}
    for key, v in (lows_doc.get("lows") or {}).items():
        pid = key.split(":", 1)[0]
        if pid in products:
            lows[f"{pid}|{label(products, key)[1]}"] = v
    for key, v in (lows_doc.get("mids") or {}).items():
        pid = key.split(":", 1)[0]
        if pid in products:
            mids[f"{pid}|{label(products, key)[1]}"] = v
    dem = load(os.path.join(out_dir, "demand.json"), {}) or {}
    wants = {str(w["id"]): w for w in dem.get("items") or [] if w.get("c")}

    picks, avoid, seen, hist = [], [], set(), 0
    for path in glob.glob(os.path.join(out_dir, "set", "*.json")):
        s = load(path)
        if not s or (s.get("pub") or "") > today:
            continue
        dates = s.get("dates") or []
        hist = max(hist, len(dates))
        for i in s["items"]:
            p = i.get("p")
            if not p or p < (MIN_SEALED if i["t"] == "s" else MIN_CARD) or SKIP.search(i["n"]):
                continue
            key = f"{i['id']}|{i['n']}"
            if key in seen:
                continue
            seen.add(key)
            a = analyse(dates, i.get("s"), p)
            base = {"id": i["id"], "n": i["n"], "t": i["t"], "g": s["id"], "sn": s["n"], "k": s["k"], "p": p,
                    "r": i.get("r"), "no": i.get("no"), "s": a["spark"], "w7": round(a["w7"], 1) if a["w7"] is not None else None}
            if i.get("dys"):
                base["dys"] = i["dys"]["p"]
            if lows.get(key):
                base["lo"] = lows[key]
            res = score_item(i, s, a, lows.get(key), mids.get(key), wants.get(str(i["id"])), today)
            if res:
                if mids.get(key):
                    res["mid"] = mids[key]
                picks.append({**base, **res})
            elif (a["w7"] is not None and a["w7"] <= -8 and a["moved"] >= 3 and a["downs"] / a["moved"] >= 0.6
                  and a["at_lo"] and p >= 2000):
                avoid.append({**base, "why": f"Down {-a['w7']:.0f}% this week on {a['downs']} of {a['moved']} price changes and still at its low. Wait for it to stop falling."})

    rank = lambda r: (r["v"] != "buy", -r["score"], -r.get("profit", 0), -r["p"])
    kept = []
    for plan in ("flip", "ride", "dip"):          # each plan keeps its own shortlist so no one plan crowds out the rest
        kept += sorted((r for r in picks if r["plan"] == plan), key=rank)[:PER_PLAN]
    picks = sorted(kept, key=rank)
    avoid.sort(key=lambda r: r["w7"])
    by = lambda k, v: sum(1 for r in picks if r[k] == v)
    doc = {"date": today, "lows_day": lows_doc.get("day"), "history_days": hist, "has_mids": bool(mids),
           "costs": {"fee_pct": FEE_PCT, "fee_flat": FEE_FLAT, "ship_sell": SHIP_SELL, "ship_buy": SHIP_BUY, "roi": TARGET_ROI},
           "counts": {"buy": by("v", "buy"), "watch": by("v", "watch"), "flip": by("plan", "flip"), "ride": by("plan", "ride"), "dip": by("plan", "dip")},
           "picks": picks, "avoid": avoid[:AVOID_N]}
    with open(os.path.join(out_dir, "scout.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    c = doc["counts"]
    print(f"scout: {c['buy']} buys, {c['watch']} to watch ({c['flip']} flips, {c['ride']} rides, {c['dip']} dips), {len(doc['avoid'])} to avoid")


if __name__ == "__main__":
    main()
