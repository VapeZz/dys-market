"""M3 Step 1 — Quick Flip "how cheap must I buy?" analysis (read-only, hypothetical, TCGplayer market prices only).

For every 7th day from 2025-01-01 to 2026-09-09 and every English Pokémon single with a TCGplayer market price of $20+
that day: suppose it was bought at 60/65/70/75% of that day's market price, held 7, 14 or 30 days, then sold
  - locally for cash at 90% of that day's market price (checks: 85%, 80%; travel $0, check $3), no fees, or
  - on eBay at 89% of market (raw eBay sold prices ran a median 11% under TCGplayer Near Mint, Nov 14 check),
    less 13.25% of price + 7.5% buyer tax (2.35% above $7,500), $0.40 an order, $1 shipping under $50 or $5 at $50+,
    and $0.50 supplies.
A case MEETS the target when profit >= $5 and ROI >= 20%. Nothing here is a real sale: market prices are TCGplayer's
estimate from its own sales, and a buyer at that price within the hold is assumed, not shown.

Pass rule (fixed in the plan approved Nov 17, 8:14 PM, before any result): a buy level works for a price band and exit if,
in 2025 and in 2026 separately: at least 70% of cases meet the target, the median profit is at least $5, the worst 10%
lose no more than 10% (10th-percentile ROI >= -10%), with 300+ cards over 6+ months. To keep repeated cards and
overlapping weeks from inflating confidence, rates are card-weighted (each card counts once per year: the mean of its
own cases), the 300 is distinct cards, and a 95% interval comes from resampling whole cards.
Missing exit prices: base = left out (unknown, counted and shown); conservative = counted as not meeting the target and
as a total loss.
usage: python3 tools/m3/quickflip.py <days dir> <meta.json> <out.json>"""
import gzip, json, os, sys
from datetime import date, timedelta
import numpy as np

DAYS, META, OUT = sys.argv[1:4]
FIRST, LAST = date(2025, 1, 1), date(2026, 9, 9)
HOLDS, PCTS = (7, 14, 30), (60, 65, 70, 75)
BANDS = [("$20–50", 2000, 5000), ("$50–100", 5000, 10000), ("$100+", 10000, 10**12)]
MODERN = "2020-01-01"
EXITS = {"local90": ("local", 0.90, 0), "local85": ("local", 0.85, 0), "local80": ("local", 0.80, 0), "local90_travel3": ("local", 0.90, 300), "ebay": ("ebay", 0.89, 0)}
RULE = {"hit": 70.0, "median": 500, "p10": -10.0, "cards": 300, "months": 6}

meta = json.load(open(META))["meta"]
def snap(day):
    p = os.path.join(DAYS, f"{day}.json.gz")
    if not os.path.exists(p): return None
    with gzip.open(p, "rt") as f: return json.load(f)

# ---------- the cases ----------
decisions, d = [], FIRST
while d <= LAST: decisions.append(d); d += timedelta(days=7)
cache = {}
def get(day):
    k = day.isoformat()
    if k not in cache: cache[k] = snap(k)
    return cache[k]
keys, kidx = [], {}
rows = []            # key, decision index, year, month, m0, m1[7], m1[14], m1[30]
cover = {"keys_20plus": 0, "keys_card": 0, "keys_no_meta": 0, "keys_sealed": 0, "missing_days": []}
for di, d0 in enumerate(decisions):
    s0 = get(d0)
    if s0 is None: cover["missing_days"].append(d0.isoformat()); continue
    exits = [get(d0 + timedelta(days=h)) for h in HOLDS]
    for h, e in zip(HOLDS, exits):
        if e is None: cover["missing_days"].append((d0 + timedelta(days=h)).isoformat())
    for k, m0 in s0.items():
        if m0 < 2000: continue
        cover["keys_20plus"] += 1
        pid = k.split(":", 1)[0]
        mt = meta.get(pid)
        if mt is None: cover["keys_no_meta"] += 1; continue
        if mt[0] != "c": cover["keys_sealed"] += 1; continue
        cover["keys_card"] += 1
        i = kidx.get(k)
        if i is None: i = kidx[k] = len(keys); keys.append(k)
        m1 = [(e.get(k, 0) if e is not None else -1) for e in exits]
        rows.append((i, di, d0.year, d0.year * 12 + d0.month, m0, *m1, 1 if (mt[2] or "") >= MODERN else 0))
cover["missing_days"] = sorted(set(cover["missing_days"]))
R = np.array(rows, dtype=np.int64)
K, DI, YR, MON, M0 = R[:, 0], R[:, 1], R[:, 2], R[:, 3], R[:, 4].astype(np.float64)
M1 = {h: R[:, 5 + j].astype(np.float64) for j, h in enumerate(HOLDS)}
ERA = R[:, 8]
print(f"cases {len(R)}, cards {len(keys)}, decision days {len(decisions)}", flush=True)

# ---------- money ----------
def ebay_net(price):
    base = np.round(price * 1.075)
    fee = np.round(40 + np.minimum(base, 750000) * 0.1325 + np.maximum(base - 750000, 0) * 0.0235)
    ship = np.where(price >= 5000, 500, 100)
    return price - fee - ship - 50
def outcome(pct, ex, m1):
    kind, share, travel = EXITS[ex]
    cost = np.round(M0 * pct / 100)
    price = np.round(m1 * share)
    net = price - travel if kind == "local" else ebay_net(price)
    profit = net - cost
    return cost, profit, profit / cost * 100

# ---------- one group's statistics ----------
rng = np.random.default_rng(17)
def stats(mask, pct, ex, h, boot=False):
    m1 = M1[h]
    known = mask & (m1 > 0)
    miss = mask & (m1 == 0)                 # no market price that day (the item still listed, no price)
    nodata = mask & (m1 < 0)                # the exit day's file is missing
    cost, profit, roi = outcome(pct, ex, m1)
    meets = (profit >= 500) & (roi >= 20)
    out = {"cases": int(known.sum()), "missing": int(miss.sum()), "no_file": int(nodata.sum())}
    if out["cases"] == 0: return out
    k = K[known]
    cards, inv = np.unique(k, return_inverse=True)
    cnt = np.bincount(inv).astype(np.float64)
    cw = lambda v: float((np.bincount(inv, weights=v.astype(np.float64)) / cnt).mean() * 100)
    out.update({"cards": int(len(cards)), "months": int(len(np.unique(MON[known]))),
        "hit": cw(meets[known]), "hit_cases": float(meets[known].mean() * 100),
        "loss": cw(profit[known] < 0), "median": float(np.median(profit[known])), "p10": float(np.percentile(roi[known], 10)),
        "median_cost": float(np.median(cost[known])),
        "flat": float((m1[known] == M0[known]).mean() * 100)})
    nf = known & (m1 != M0)                  # stale-price check: cases whose market price moved at all
    if nf.any():
        k2 = K[nf]; c2, i2 = np.unique(k2, return_inverse=True); n2 = np.bincount(i2).astype(np.float64)
        out["hit_moved"] = float((np.bincount(i2, weights=meets[nf].astype(np.float64)) / n2).mean() * 100)
    # conservative: a missing exit price is a total loss that misses the target
    allk = mask & (m1 >= 0)
    meets_c = np.where(m1 > 0, meets, False); roi_c = np.where(m1 > 0, roi, -100.0)
    ka = K[allk]; ca, ia = np.unique(ka, return_inverse=True); na = np.bincount(ia).astype(np.float64)
    out["hit_cons"] = float((np.bincount(ia, weights=meets_c[allk].astype(np.float64)) / na).mean() * 100)
    out["p10_cons"] = float(np.percentile(roi_c[allk], 10))
    if boot:
        per = np.bincount(inv, weights=meets[known].astype(np.float64)) / cnt
        bs = [per[rng.integers(0, len(per), len(per))].mean() * 100 for _ in range(400)]
        out["hit_ci"] = [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]
    return out

def works(s):
    return bool(s.get("cases") and s["hit"] >= RULE["hit"] and s["median"] >= RULE["median"] and s["p10"] >= RULE["p10"]
                and s["cards"] >= RULE["cards"] and s["months"] >= RULE["months"])
def works_cons(s):
    return bool(s.get("cases") and s["hit_cons"] >= RULE["hit"] and s["median"] >= RULE["median"] and s["p10_cons"] >= RULE["p10"]
                and s["cards"] >= RULE["cards"] and s["months"] >= RULE["months"])

res = {"made": date.today().isoformat(), "decisions": [decisions[0].isoformat(), decisions[-1].isoformat(), len(decisions)],
       "rule": RULE, "coverage": cover, "cases_total": int(len(R)), "cards_total": int(len(keys)), "cells": [], "max": {}}
for era_name, emask in (("all", np.ones(len(R), bool)), ("modern", ERA == 1), ("older", ERA == 0)):
    for bname, lo, hi in BANDS:
        bmask = emask & (M0 >= lo) & (M0 < hi)
        for ex in EXITS:
            for h in HOLDS:
                best, best_c = None, None
                for pct in PCTS:
                    per = {}
                    for yr in (2025, 2026):
                        per[yr] = stats(bmask & (YR == yr), pct, ex, h, boot=(era_name == "all"))
                    ok = all(works(per[y]) for y in per); okc = all(works_cons(per[y]) for y in per)
                    res["cells"].append({"era": era_name, "band": bname, "exit": ex, "hold": h, "pct": pct, "works": ok, "works_cons": okc,
                                         "y2025": per[2025], "y2026": per[2026]})
                    if ok: best = pct
                    if okc: best_c = pct
                res["max"][f"{era_name}|{bname}|{ex}|{h}"] = {"max": best, "max_cons": best_c}
        print(era_name, bname, "done", flush=True)
json.dump(res, open(OUT, "w"), indent=1)
print("written", OUT)
