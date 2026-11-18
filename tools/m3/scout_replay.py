"""M3 Step 2: replay Edge's Deals lists (Daily Scout Flips / Momentum / Dips and Under market) on archived TCGplayer
prices and score what buying them would have done. Hypothetical: listings are advertised prices and exits are market
price estimates, not sales. The plan and pass rule are frozen in tools/m3/STEP2_PLAN.md.

usage: python3 tools/m3/scout_replay.py <days dir> <meta.json> <out.json> <years: 2025 | 2025,2026> [--cache m.npz]
"""
import gzip, json, os, re, sys
from datetime import date, timedelta
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import scout   # the app's own code, unchanged  # noqa: E402

DAYS, META, OUT, YEARS = sys.argv[1], sys.argv[2], sys.argv[3], [int(y) for y in sys.argv[4].split(",")]
CACHE = sys.argv[sys.argv.index("--cache") + 1] if "--cache" in sys.argv else None
FIRST_DAY, LAST_DAY = date(2024, 12, 1), date(2026, 10, 11)
FIRST_DEC, LAST_DEC = date(2025, 1, 1), date(2026, 9, 9)
HOLDS = (7, 14, 30)
BUYER_SKIP = re.compile(r"prerelease|\[staff\]|code card|jumbo|oversize|\bdeck\b.*\bcard\b|world championships", re.I)
UNDER_N = 80

# ---------------- data: one int32 matrix per field, [day, key] ----------------
meta = json.load(open(META))["meta"]
days = []
d = FIRST_DAY
while d <= LAST_DAY: days.append(d); d += timedelta(days=1)
DIX = {x: i for i, x in enumerate(days)}

def load_matrix():
    if CACHE and os.path.exists(CACHE):
        z = np.load(CACHE, allow_pickle=True)
        return list(z["keys"]), z["M"], z["L"], z["D"]
    keyset = {}
    paths = [os.path.join(DAYS, f"{x.isoformat()}.json.gz") for x in days]
    snap = lambda p: json.load(gzip.open(p, "rt")) if os.path.exists(p) else None
    for p in paths:                     # pass 1: the keys (one day in memory at a time)
        s = snap(p)
        if s:
            for k in s:
                if k.split(":", 1)[0] in meta and k not in keyset: keyset[k] = len(keyset)
    keys = list(keyset)
    M = np.zeros((len(days), len(keys)), np.int32); L = np.zeros_like(M); D = np.zeros_like(M)
    for di, p in enumerate(paths):      # pass 2: the values
        s = snap(p)
        if not s: continue
        for k, (m, lo, md) in s.items():
            j = keyset.get(k)
            if j is not None: M[di, j], L[di, j], D[di, j] = m, lo, md
    if CACHE: np.savez(CACHE, keys=np.array(keys, dtype=object), M=M, L=L, D=D)
    return keys, M, L, D

KEYS, M, L, D = load_matrix()
missing_days = [days[i].isoformat() for i in range(len(days)) if not M[i].any()]
PID = [k.split(":", 1)[0] for k in KEYS]
T = np.array([meta[p][0] for p in PID])
PUB = [meta[p][2] for p in PID]
NAME = [meta[p][3] for p in PID]
SCOUT_OK = np.array([not scout.SKIP.search(n) for n in NAME])
BUYER_OK = np.array([not BUYER_SKIP.search(n) for n in NAME])
MINP = np.where(T == "s", scout.MIN_SEALED, scout.MIN_CARD)

# ---------------- selection on day index di, reading rows <= di only ----------------
def lists_on(di, M=M, L=L, D=D):
    today = days[di].isoformat()
    dates = [days[i].isoformat() for i in range(di - 30, di + 1)]
    p_now = M[di]
    cand = np.nonzero((p_now >= MINP) & SCOUT_OK)[0]
    picks = []
    for j in cand:
        if (PUB[j] or "") > today: continue
        p = int(p_now[j]); ser = [int(v) or None for v in M[di - 30:di + 1, j]]
        a = scout.analyse(dates, ser, p)
        lo, md = int(L[di, j]) or None, int(D[di, j]) or None
        r = scout.score_item({"p": p, "t": T[j]}, {"pub": PUB[j]}, a, lo, md, None, today)
        if r: picks.append({"j": int(j), "p": p, "t": str(T[j]), **{k: r[k] for k in ("plan", "score", "v")}, "lo": lo, "profit": r.get("profit", 0)})
    rank = lambda r: (r["v"] != "buy", -r["score"], -r.get("profit", 0), -r["p"])
    out = {}
    for plan in ("flip", "ride", "dip"):
        out[plan] = sorted((r for r in picks if r["plan"] == plan), key=rank)[:scout.PER_PLAN]
    under = []
    for j in np.nonzero((p_now >= MINP) & BUYER_OK & (L[di] > 0))[0]:
        if (PUB[j] or "") > today: continue
        p, lo = int(p_now[j]), int(L[di, j])
        if lo >= p * 0.8 or lo < p * 0.25: continue
        under.append({"j": int(j), "p": p, "t": str(T[j]), "lo": lo, "v": "list", "save": p - lo})
    under.sort(key=lambda r: -r["save"])
    out["under"] = under[:UNDER_N]
    return out

# ---------------- money ----------------
def sell(ex, m, t):
    if ex == "E1": return scout.sell_net(m, t)
    if ex == "E3": return round(m * 0.90)
    if ex == "E4": return round(m * 0.80)
    price = round(m * 0.89)                                     # E2 eBay
    base = round(price * 1.075)
    fee = round(40 + min(base, 750000) * 0.1325 + max(base - 750000, 0) * 0.0235)
    ship = scout.SHIP_SELL[("s100" if price >= 10000 else "s") if t == "s" else ("c50" if price >= 5000 else "c")]
    return price - fee - ship - 50
EXITS = ("E1", "E2", "E3", "E4")

# ---------------- run ----------------
if __name__ == "__main__":
    decisions = []
    d = FIRST_DEC
    while d <= LAST_DEC:
        if d.year in YEARS: decisions.append(d)
        d += timedelta(days=7)
    cases = []          # one per list entry per decision day
    counts = {}
    for d0 in decisions:
        di = DIX[d0]
        if not M[di].any(): continue
        for lst, rows in lists_on(di).items():
            counts.setdefault(f"{lst}|{d0.year}", []).append(len(rows))
            for r in rows:
                j, t = r["j"], r["t"]
                buy = (r["lo"] if lst in ("flip", "under") else r["p"]) + scout.SHIP_BUY[t]
                # diagnostics
                nxt = int(L[di + 1, j]) if di + 1 < len(days) else 0
                still = (nxt > 0 and nxt <= r["lo"]) if lst in ("flip", "under") else None
                prev = M[max(0, di - 14):di, j]
                stale = bool(len(prev) and (prev == r["p"]).all())
                fut = M[di + 1:di + 31, j]; fut = fut[fut > 0]
                fell = bool(r.get("lo") and len(fut) and fut.min() <= r["lo"] * 1.1) if lst in ("flip", "under") else None
                c = {"list": lst, "v": r["v"], "j": j, "key": KEYS[j], "day": d0.isoformat(), "y": d0.year, "mon": d0.year * 12 + d0.month,
                     "t": t, "p": r["p"], "lo": r.get("lo"), "buy": buy, "off": round((1 - r["lo"] / r["p"]) * 100, 1) if r.get("lo") else None,
                     "md": int(D[di, j]) or None, "still": still, "stale": stale, "fell": fell, "exit": {}}
                for h in HOLDS:
                    m1 = int(M[di + h, j])
                    c["exit"][h] = m1
                cases.append(c)
        print(d0, len(cases), flush=True)

    def stats(sel, ex, h):
        rows = [c for c in sel]
        known = [c for c in rows if c["exit"][h] > 0]
        out = {"cases": len(rows), "missing": len(rows) - len(known)}
        if not known: return out
        prof = np.array([sell(ex, c["exit"][h], c["t"]) - c["buy"] for c in known], float)
        cost = np.array([c["buy"] for c in known], float)
        roi = prof / cost * 100
        meets = (prof >= 500) & (roi >= 20)
        items = np.array([c["key"] for c in known])
        u, inv = np.unique(items, return_inverse=True)
        n = np.bincount(inv).astype(float)
        iw = lambda v: float((np.bincount(inv, weights=v.astype(float)) / n).mean() * 100)
        out.update({"items": int(len(u)), "months": len({c["mon"] for c in known}),
                    "hit": iw(meets), "loss": iw(prof < 0), "median": float(np.median(prof)), "mean": float(prof.mean()),
                    "p10": float(np.percentile(roi, 10)), "total": float(prof.sum()), "spent": float(cost.sum()),
                    "flat": float(np.mean([c["exit"][h] == c["p"] for c in known]) * 100)})
        # conservative: missing exit = total loss, misses target
        allp = np.array([(sell(ex, c["exit"][h], c["t"]) - c["buy"]) if c["exit"][h] > 0 else -c["buy"] for c in rows], float)
        allc = np.array([c["buy"] for c in rows], float); allr = allp / allc * 100
        am = (allp >= 500) & (allr >= 20)
        it2 = np.array([c["key"] for c in rows]); u2, i2 = np.unique(it2, return_inverse=True); n2 = np.bincount(i2).astype(float)
        out["hit_cons"] = float((np.bincount(i2, weights=am.astype(float)) / n2).mean() * 100)
        out["p10_cons"] = float(np.percentile(allr, 10))
        return out

    RULE = {"hit": 70.0, "median": 500, "p10": -10.0, "items": 100, "months": 6}
    def passes(s):
        return bool(s.get("items") and s["hit"] >= 70 and s["median"] >= 500 and s["p10"] >= -10 and s["items"] >= 100
                    and s["months"] >= 6 and s["hit_cons"] >= 70 and s["p10_cons"] >= -10)

    res = {"years": YEARS, "missing_days": missing_days, "keys": len(KEYS), "counts": {k: [len(v), int(sum(v))] for k, v in counts.items()},
           "cells": [], "diag": []}
    for lst in ("flip", "ride", "dip", "under"):
        for subset in ("all", "buy") if lst != "under" else ("all",):
            for y in YEARS:
                sel = [c for c in cases if c["list"] == lst and c["y"] == y and (subset == "all" or c["v"] == "buy")]
                for ex in EXITS:
                    for h in HOLDS:
                        s = stats(sel, ex, h)
                        res["cells"].append({"list": lst, "subset": subset, "y": y, "exit": ex, "hold": h, "pass": passes(s), **s})
            # diagnostics (flip / under), 30-day hold, local 90%
            if lst in ("flip", "under") and subset == "all":
                for y in YEARS:
                    base = [c for c in cases if c["list"] == lst and c["y"] == y]
                    groups = {"all": base, "still listed next day": [c for c in base if c["still"]],
                              "gone next day": [c for c in base if c["still"] is False],
                              "market moved in prior 14 days": [c for c in base if not c["stale"]],
                              "market unchanged prior 14 days": [c for c in base if c["stale"]],
                              "lowest >= 70% of median listing": [c for c in base if c["md"] and c["lo"] >= 0.7 * c["md"]],
                              "lowest < 70% of median listing": [c for c in base if c["md"] and c["lo"] < 0.7 * c["md"]],
                              "off under 35%": [c for c in base if c["off"] < 35], "off 35-55%": [c for c in base if 35 <= c["off"] < 55],
                              "off 55-75%": [c for c in base if c["off"] >= 55]}
                    for g, sel in groups.items():
                        s3 = stats(sel, "E3", 30); s2 = stats(sel, "E2", 30)
                        res["diag"].append({"list": lst, "y": y, "group": g, "n": len(sel),
                                            "fell_to_low": float(np.mean([c["fell"] for c in sel]) * 100) if sel else None,
                                            "E3_30": s3, "E2_30": s2})
    # cases for audit / recheck
    res["sample"] = [c for c in cases][::max(1, len(cases) // 400)]
    json.dump(res, open(OUT, "w"), default=str)
    json.dump(cases, gzip.open(OUT.replace(".json", "_cases.json.gz"), "wt"), default=str)
    print("cases", len(cases))
