"""Score each strategy rule on what run.js recorded, and write the result file Edge reads.

The pass rule was fixed here before any result was looked at:
  A rule makes a claim when its call has a direction: Buy zone expects the price to do BETTER than the average
  card, Sell and Trim expect it to do WORSE, and the two "wait" rules (Falling knife, Weak trend) expect WORSE too.
  Hold rules and the other Watch rules make no claim.
  PASS      at least MIN_N cases over at least MIN_MONTHS months, the average 30-day move beats (or trails) the same
            days' all-cards average by EDGE points or more, the move itself has the claimed sign, the edge has the
            claimed sign in OK_MONTHS of the months with MONTH_N+ cases, and in both halves of the period.
  FAIL      the edge has the wrong sign (or is zero), or the claimed sign in under BAD_MONTHS of the months.
  UNPROVEN  everything in between (too few cases, too small, or not steady).
The verdict uses decision days with a full year of prices behind them (the table starts 2024-02-08, so from
2025-02-07 on): that is what Edge holds for a card today. The earlier days (shorter history, so a "52-week" high
or low that is really "since February 2024") are reported beside it and do not decide anything.

By game: the same test is run inside each game (the rule's cases in that game against that game's all-items average on
the same days), where the rule has MIN_N cases over MIN_MONTHS months there. A card's verdict in Edge is the WORSE of the
all-games verdict and its own game's, so slicing by game can only take a claim away, never add one. (Added after the
all-games results were read, because the games move differently: English Pokemon rose about 5% a month over the period,
Lorcana fell. The thresholds are the same ones.)
usage: python3 tools/backtest/stats.py <signals dir> <out json>"""
import os as _os
ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
BT = _os.environ.get("BT_DIR") or _os.path.join(ROOT, "bt-work")            # working folder (not in git): days/, prices.i32, sig/
DATA = _os.environ.get("DATA_DIR") or _os.path.join(ROOT, "data")           # the data branch's data/ folder
import glob, json, math, os, sys
from datetime import date
import numpy as np

MIN_N, MIN_MONTHS, EDGE, OK_MONTHS, BAD_MONTHS, MONTH_N, HALF_N = 300, 6, 2.0, 0.60, 0.40, 30, 100
CLIP = (-0.9, 3.0)            # one move counts at most as -90% or +300% (price glitches, tiny bases)
PRIMARY = 30
NET_MIN = 2000                # cents: the after-fees line counts items of $20 and up
CLAIM = {"dip": 1, "breakout": 1, "turn": 1, "s-dip": 1, "stretched": -1, "breakdown": -1, "s-spike": -1, "s-down": -1, "knife": -1, "weak": -1}

sig, out = sys.argv[1], sys.argv[2]
infos = [json.load(open(p)) for p in sorted(glob.glob(os.path.join(sig, "info.*.json")))]
info = infos[0]
DT = {"Int32Array": np.int32, "Int16Array": np.int16, "Uint8Array": np.uint8, "Float32Array": np.float32}
col = {name: np.concatenate([np.fromfile(os.path.join(sig, f"{name}.{i['shard']}.bin"), dtype=DT[t]) for i in infos]) for name, t in info["types"].items()}
n_rows = len(col["key"])
assert n_rows == sum(i["n"] for i in infos)
days = json.load(open(os.path.join(BT, "days.json")))
keys = json.load(open(os.path.join(BT, "keys.json")))
meta = json.load(open(os.path.join(BT, "meta.json")))
setups = info["setups"]
ktype = np.array([1 if (meta.get(k.split(":", 1)[0]) or ["c"])[0] == "s" else 0 for k in keys], dtype=np.uint8)
typ = ktype[col["key"]]
month = np.array([int(d[:4]) * 12 + int(d[5:7]) - 1 for d in days])[col["day"]]
FULL = col["day"] >= 365                     # a full year of prices in the table before the decision day

# Edge's default money settings (eBay, 20%): the same numbers as edge.js and grade-fees.json
def net(p, t):
    fee = 40 + np.minimum(p, 750000) * 0.1325 + np.maximum(p - 750000, 0) * 0.0235
    ship = np.where(t == 1, np.where(p >= 10000, 1500, 800), np.where(p >= 5000, 500, 100))
    return np.maximum(0, p - fee) - ship
ship_in = np.where(typ == 1, 600, 150)

def stats_for(h):
    r = col[f"r{h}"].astype(np.float64)
    have = ~np.isnan(r)                       # the day h days later is inside the data
    gone = have & (r <= -1.5)                 # no price any more
    ok = have & ~gone
    rc = np.clip(r, *CLIP)
    # the same day's all-cards average and up / down shares
    d = col["day"].astype(np.int64)
    nd = len(days)
    cnt = np.bincount(d[ok], minlength=nd).astype(np.float64)
    s_avg = np.bincount(d[ok], weights=rc[ok], minlength=nd)
    s_up = np.bincount(d[ok], weights=(r[ok] > 0).astype(float), minlength=nd)
    s_dn = np.bincount(d[ok], weights=(r[ok] < 0).astype(float), minlength=nd)
    with np.errstate(invalid="ignore", divide="ignore"):
        b_avg, b_up, b_dn = s_avg / cnt, s_up / cnt, s_dn / cnt
    return r, rc, ok, gone, have, b_avg, b_up, b_dn

def rule_stats(code, h, period=None):
    r, rc, ok, gone, have, b_avg, b_up, b_dn = stats_for(h)
    m = (col["setup"] == code) & (FULL if period is None else period)
    mo = m & ok
    n = int(mo.sum())
    if n == 0:
        return None
    d = col["day"][mo].astype(np.int64)
    res = {
        "n": n, "days": int(len(np.unique(d))),
        "avg": float(rc[mo].mean() * 100), "med": float(np.median(r[mo]) * 100),
        "up": float((r[mo] > 0).mean() * 100), "flat": float((r[mo] == 0).mean() * 100), "down": float((r[mo] < 0).mean() * 100),
        "baseAvg": float(b_avg[d].mean() * 100), "baseUp": float(b_up[d].mean() * 100), "baseDown": float(b_dn[d].mean() * 100),
        "gone": float(gone[m & have].mean() * 100) if (m & have).any() else 0.0,
    }
    res["edge"] = res["avg"] - res["baseAvg"]
    return res

def net20(m):
    m = m & (col["v"] >= NET_MIN)
    if m.sum() < 200:
        return None
    v = col["v"][m].astype(np.float64); t = typ[m]
    cost = v + ship_in[m]
    roi = (net(v * (1 + r30[m]), t) - cost) / cost
    return {"n": int(m.sum()), "avg": float(np.clip(roi, -1, 3).mean() * 100), "win": float((roi > 0).mean() * 100), "up20": float((r30[m] >= 0.2).mean() * 100), "down20": float((r30[m] <= -0.2).mean() * 100)}

def verdict_of(claim, n, n_months, avg, edge, ok_months, halves):
    if not claim:
        return "none"
    signed = edge * claim
    halves_ok = all(x is not None and x * claim > 0 for x in halves[:2]) and min(halves[2:]) >= HALF_N
    if signed <= 0 or (ok_months is not None and ok_months < BAD_MONTHS * 100):
        return "fail"
    if (n >= MIN_N and n_months >= MIN_MONTHS and signed >= EDGE and avg * claim > 0
            and ok_months is not None and ok_months >= OK_MONTHS * 100 and halves_ok):
        return "pass"
    return "unproven"

rules = {}
r30, rc30, ok30, gone30, have30, b_avg30, b_up30, b_dn30 = stats_for(PRIMARY)
first_m, last_m = int(month[ok30 & FULL].min()), int(month[ok30 & FULL].max())
mid_m = (first_m + last_m + 1) // 2
for code, sid in enumerate(setups):
    st = rule_stats(code, PRIMARY)
    if not st:
        continue
    m = (col["setup"] == code) & ok30 & FULL
    d = col["day"][m].astype(np.int64)
    ex = rc30[m] - b_avg30[d]                                     # each case's move minus its day's all-cards average
    mm = month[m]
    months = [(int(k), float(ex[mm == k].mean() * 100), int((mm == k).sum())) for k in np.unique(mm)]
    big = [e for _k, e, c in months if c >= MONTH_N]
    claim = CLAIM.get(sid, 0)
    st["months"] = len(months); st["monthsCounted"] = len(big)
    st["claim"] = claim
    st["okMonths"] = (sum(1 for e in big if e * claim > 0) / len(big) * 100) if (big and claim) else None
    h1, h2 = ex[mm < mid_m], ex[mm >= mid_m]
    st["halves"] = [float(h1.mean() * 100) if len(h1) else None, float(h2.mean() * 100) if len(h2) else None, int(len(h1)), int(len(h2))]
    early = rule_stats(code, PRIMARY, ~FULL)
    st["early"] = {k: early[k] for k in ("n", "avg", "baseAvg", "edge")} if early else None
    st["h"] = {}
    for h in info["horizons"]:
        if h == PRIMARY: continue
        x = rule_stats(code, h)
        if x: st["h"][str(h)] = {k: x[k] for k in ("n", "avg", "baseAvg", "edge", "up", "down")}
    # items of $20 and up, bought at the day's market price and sold on eBay 30 days later, after fees and shipping both ways
    # (under $20 the flat fee and shipping decide the result whatever the price does)
    st["net"] = net20(m)
    # which came first in the next 60 days: the first sell level or the cut level (rules with a ladder)
    tm = (col["setup"] == code) & (col["touch"] <= 2) & ~np.isnan(col["sell1"]) & FULL
    if tm.any():
        tt = col["touch"][tm]
        st["path"] = {"n": int(tm.sum()), "sell": float((tt == 1).mean() * 100), "cut": float((tt == 2).mean() * 100), "none": float((tt == 0).mean() * 100),
                      "sellAt": float(np.median(col["sell1"][tm])), "cutAt": float(np.median(col["cut"][tm]))}
    verdict = verdict_of(claim, st["n"], st["months"], st["avg"], st["edge"], st["okMonths"], st["halves"])
    st["verdict"] = verdict
    rules[sid] = st

# ---- the same test inside each game ----
game_of = {k: (meta.get(k.split(":", 1)[0]) or ["", "", "", ""])[3] for k in keys}
gnames = sorted({g for g in game_of.values() if g})
kgame = np.array([gnames.index(game_of[k]) if game_of[k] else -1 for k in keys], dtype=np.int16)
g_row = kgame[col["key"]]
nd = len(days)
d_all = col["day"].astype(np.int64)
games = {}
for gi, gname in enumerate(gnames):
    gm = (g_row == gi) & ok30 & FULL
    if gm.sum() < MIN_N:
        continue
    cnt = np.bincount(d_all[gm], minlength=nd).astype(np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        gb = np.bincount(d_all[gm], weights=rc30[gm], minlength=nd) / cnt             # this game's all-items average, per day
    grules = {}
    for code, sid in enumerate(setups):
        m = gm & (col["setup"] == code)
        n = int(m.sum())
        if n == 0:
            continue
        dd = d_all[m]; ex = rc30[m] - gb[dd]; mm = month[m]
        months = [(float(ex[mm == k].mean() * 100), int((mm == k).sum())) for k in np.unique(mm)]
        big = [e for e, c in months if c >= MONTH_N]
        claim = CLAIM.get(sid, 0)
        avg, base_avg = float(rc30[m].mean() * 100), float(gb[dd].mean() * 100)
        ok_m = (sum(1 for e in big if e * claim > 0) / len(big) * 100) if (big and claim) else None
        h1, h2 = ex[mm < mid_m], ex[mm >= mid_m]
        halves = [float(h1.mean() * 100) if len(h1) else None, float(h2.mean() * 100) if len(h2) else None, int(len(h1)), int(len(h2))]
        enough = n >= MIN_N and len(months) >= MIN_MONTHS                              # under that, the game says nothing about this rule
        grules[sid] = {"n": n, "months": len(months), "monthsCounted": len(big), "avg": avg, "baseAvg": base_avg, "edge": avg - base_avg,
                       "up": float((r30[m] > 0).mean() * 100), "flat": float((r30[m] == 0).mean() * 100), "down": float((r30[m] < 0).mean() * 100),
                       "okMonths": ok_m, "halves": halves, "claim": claim,
                       "verdict": verdict_of(claim, n, len(months), avg, avg - base_avg, ok_m, halves) if enough else None}
    games[gname] = {"cases": int(gm.sum()), "avg": float(rc30[gm].mean() * 100), "up": float((r30[gm] > 0).mean() * 100), "down": float((r30[gm] < 0).mean() * 100), "rules": grules}

dec = info["decide"]
okf = ok30 & FULL
used = sorted({days[int(x)] for x in np.unique(col["day"][okf])})
early_days = sorted({days[int(x)] for x in np.unique(col["day"][ok30 & ~FULL])})
base = {"n": int(okf.sum()), "avg": float(rc30[okf].mean() * 100), "up": float((r30[okf] > 0).mean() * 100), "flat": float((r30[okf] == 0).mean() * 100), "down": float((r30[okf] < 0).mean() * 100),
        "gone": float(gone30[have30 & FULL].mean() * 100)}
base["net"] = net20(okf)
result = {"v": 1, "made": date.today().isoformat(), "from": used[0], "to": used[-1], "dataTo": days[-1], "days": len(used), "step": info["step"], "horizon": PRIMARY, "path": info["path"],
          "cases": int(okf.sum()), "items": int(len(np.unique(col["key"][okf]))), "base": base, "early": {"from": early_days[0], "to": early_days[-1], "days": len(early_days), "cases": int((ok30 & ~FULL).sum())} if early_days else None,
          "netMin": NET_MIN, "claims": CLAIM,
          "rule": {"minN": MIN_N, "minMonths": MIN_MONTHS, "edge": EDGE, "okMonths": OK_MONTHS * 100, "badMonths": BAD_MONTHS * 100},
          "rules": rules, "games": games}
def rnd(o):
    if isinstance(o, float): return None if math.isnan(o) else round(o, 2)
    if isinstance(o, dict): return {k: rnd(v) for k, v in o.items()}
    if isinstance(o, list): return [rnd(v) for v in o]
    return o
json.dump(rnd(result), open(out, "w"), separators=(",", ":"))
print(f"rows {n_rows}; decision days {len(dec)} ({dec[0]} to {dec[-1]}); with a 30-day result: {len(used)} days ({used[0]} to {used[-1]}), {base['n']} cases, {result['items']} items")
print(f"all cards, 30 days later: avg {base['avg']:+.2f}%  up {base['up']:.1f}%  flat {base['flat']:.1f}%  down {base['down']:.1f}%  no price any more {base['gone']:.2f}%")
print(f"earlier days (shorter history, not part of the verdict): {result['early']}")
print(f"{'rule':<10} {'claim':>5} {'n':>8} {'mon':>4} {'avg':>7} {'base':>7} {'edge':>7} {'up':>5} {'flat':>5} {'down':>5} {'okMon':>6} {'half1':>6} {'half2':>6} {'net%':>6} {'win%':>5} {'sell1':>6} {'cut':>5} {'early':>6}  verdict")
for sid, s in sorted(rules.items(), key=lambda kv: (-abs(kv[1]['claim']), -kv[1]['claim'], kv[0])):
    p = s.get("path") or {}
    print(f"{sid:<10} {s['claim']:>5} {s['n']:>8} {s['months']:>4} {s['avg']:>+7.2f} {s['baseAvg']:>+7.2f} {s['edge']:>+7.2f} {s['up']:>5.1f} {s['flat']:>5.1f} {s['down']:>5.1f} "
          f"{(str(round(s['okMonths'])) if s['okMonths'] is not None else '-'):>6} {s['halves'][0] if s['halves'][0] is None else round(s['halves'][0], 1):>6} {s['halves'][1] if s['halves'][1] is None else round(s['halves'][1], 1):>6} "
          f"{(s['net'] or {}).get('avg', float('nan')):>+6.1f} {(s['net'] or {}).get('win', float('nan')):>5.1f} {p.get('sell', float('nan')):>6.1f} {p.get('cut', float('nan')):>5.1f} {(round(s['early']['edge'], 1) if s['early'] else '-'):>6}  {s['verdict']}")

RANK = {"fail": 0, "unproven": 1, "pass": 2}
print("\nby game: the same test inside each game; a card's verdict is the worse of all games and its own game")
for gname, G in games.items():
    print(f"{gname}: {G['cases']} cases, average 30-day move {G['avg']:+.1f}%")
    for sid in CLAIM:
        x = G["rules"].get(sid)
        if not x: continue
        allv = rules[sid]["verdict"]; final = allv if x["verdict"] is None else min(allv, x["verdict"], key=lambda v: RANK[v])
        print(f"   {sid:<10} n {x['n']:>7} avg {x['avg']:>+6.1f} game {x['baseAvg']:>+6.1f} edge {x['edge']:>+6.1f} months {('-' if x['okMonths'] is None else round(x['okMonths'])):>4}  in game: {str(x['verdict']):<9} all games: {allv:<9} -> {final}")
