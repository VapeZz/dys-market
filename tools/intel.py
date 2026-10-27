"""Market Intel: daily brief, market indices, signals, top movers and deals.

    python tools/intel.py site

Reads site/data/set/*.json (+ site/data/buyer.json for deals) and writes site/data/intel.json
for the Intel page. Everything is computed from recorded TCGplayer market prices with plain,
explainable rules (no predictions): an index is a fixed basket's total value per day, and a signal
is a price trend that has been consistent over the last week.
"""
import glob
import json
import math
import os
import re
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gradecost  # noqa: E402

SKIP = re.compile(r"code card|\bjumbo\b|oversize|prerelease|\[staff\]|\bcase\b|display case", re.I)
MODERN_YEARS = 3


def load_sets(sd):
    out = []
    for p in glob.glob(os.path.join(sd, "set", "*.json")):
        try:
            out.append(json.load(open(p)))
        except (OSError, ValueError):
            pass
    return out


def filled(series):
    """Carry the last known price forward and the first known price back, so gaps don't move an index."""
    s = list(series or [])
    first = next((v for v in s if v), None)
    if first is None:
        return None
    out, last = [], first
    for v in s:
        last = v if v else last
        out.append(last)
    return out


def pct(a, b):
    return round((a - b) / b * 100, 2) if a and b else None


def change_at(dates, vals, days):
    """% change from the value on/just before (last date - days) to the last value."""
    if len(vals) < 2:
        return None
    t = date.fromisoformat(dates[-1]) - timedelta(days=days)
    j = max((i for i, d in enumerate(dates) if date.fromisoformat(d) <= t), default=None)
    return None if j is None else pct(vals[-1], vals[j])


def build_index(name, desc, rows, n):
    rows = sorted(rows, key=lambda r: -r[1]["p"])[:n]
    if not rows:
        return None
    dates = sorted({d for st, _ in rows for d in st.get("dates") or []})
    if len(dates) < 2:
        return None
    total = [0.0] * len(dates)
    for st, it in rows:
        sd = st.get("dates") or []
        f = filled(it.get("s"))
        if not f or len(f) != len(sd):
            f, sd = [it["p"]], [dates[-1]]
        m = dict(zip(sd, f))
        last = f[0]
        for i, d in enumerate(dates):
            last = m.get(d, last)
            total[i] += last
    vals = [round(v) for v in total]
    return {"name": name, "desc": desc, "n": len(rows), "v": vals[-1], "dates": dates, "s": vals,
            "d1": change_at(dates, vals, 1), "w1": change_at(dates, vals, 7), "m1": change_at(dates, vals, 30),
            "top": [{"id": it["id"], "g": st["id"], "n": it["n"], "p": it["p"]} for st, it in rows[:5]]}


def card(st, it, **extra):
    return {"id": it["id"], "g": st["id"], "n": it["n"], "sn": st["n"], "k": st["k"], "no": it.get("no"), "r": it.get("r"), "p": it["p"], **extra}


def clean_n(n):
    return re.sub(r" \((Holofoil|Normal|Foil)\)$", "", n)


def graded_intel(sd, site, today):
    """Grading picks, PSA 10 movers and a PSA 10 index from data/graded.json (PokemonPriceTracker sold prices)."""
    try:
        fees = gradecost.load(site)
        graded = json.load(open(os.path.join(sd, "graded.json")))["cards"]
        allrows = json.load(open(os.path.join(sd, "grading.json")))["rows"]
        seen = {}
        for r in allrows:
            seen[r[0]] = seen.get(r[0], 0) + 1
        # graded sales are per product: skip cards with several printings (1st Edition/Unlimited, Holo/Reverse) under one id
        rows = {str(r[0]): r for r in allrows if seen[r[0]] == 1}
        groups = json.load(open(os.path.join(sd, "meta.json")))["groups"]
    except (OSError, ValueError, KeyError):
        return {}
    # picks use the site's default assumptions: PSA's cheapest open tier (with upcharges), shipping both ways,
    # sold on eBay after fees, 30% odds of a 10 and 50% of a 9 (pack-fresh modern), and a PSA 10 that sells at least weekly
    o10, o9 = 0.30, 0.50
    stale = (date.fromisoformat(today) - timedelta(days=gradecost.STALE_DAYS)).isoformat()
    psa = fees["graders"]["PSA"]["tiers"][0]
    top_cap = fees["graders"]["PSA"]["tiers"][-1][2] or float("inf")     # past PSA's top tracked tier the fee isn't known
    picks, moves, idx = [], [], []
    for pid, c in graded.items():
        r = rows.get(pid)
        g = c.get("g") or {}
        if not r or "psa10" not in g:
            continue
        _, gid, n, p, lo, rar, no, game, era = r
        g10, n10, vol10 = g["psa10"][0], g["psa10"][1], g["psa10"][2]
        g9 = g["psa9"][0] if "psa9" in g else p
        sn = (groups.get(str(gid)) or [""])[0]
        base = {"id": int(pid), "g": gid, "n": n, "sn": sn, "k": game, "p": p, "g10": g10, "g9": g9, "vol": vol10, "sales": n10}
        if not (1.1 * p <= g10 <= 60 * p):       # a PSA 10 below raw or 60x over it is a mismatched listing, not a real comp
            continue
        last = g["psa10"][6] if len(g["psa10"]) > 6 else None
        liq = gradecost.liquidity(g["psa10"])
        if era == "modern" and n10 >= 8 and liq != "slow" and not (last and last < stale) and g10 <= p * 20 and g10 <= top_cap:
            profit, cost = gradecost.expected(fees, min(p, lo or p), p, g10, g9, o10, o9)
            if profit > 0:
                picks.append({**base, "profit": round(profit), "roi": round(profit / cost * 100), "liq": liq})
        avg, p7 = (g["psa10"] + [None, None])[4:6]
        # weekly move needs real weekly volume, and a believable size (thin vintage sales swing wildly)
        if avg and p7 and n10 >= 15 and vol10 >= 0.3 and g10 >= 3000 and 0.5 <= p7 / g10 <= 2 and 0.5 <= avg / g10 <= 2:
            chg = (p7 - avg) / avg * 100
            if abs(chg) <= 60:
                moves.append({**base, "ch": round(chg, 1)})
        if era == "modern":
            idx.append((g10, avg, p7, base))
    picks.sort(key=lambda x: -x["profit"])
    up = sorted((m for m in moves if m["ch"] >= 5), key=lambda m: -m["ch"])[:6]
    down = sorted((m for m in moves if m["ch"] <= -5), key=lambda m: m["ch"])[:6]
    index = None
    top = sorted(idx, key=lambda x: -x[0])[:50]
    if len(top) >= 20:
        v = sum(t[0] for t in top)
        a = sum(t[1] or t[0] for t in top)
        w = sum(t[2] or t[0] for t in top)
        index = {"name": "PSA 10 Chase 50", "desc": "The 50 most valuable modern Pokémon cards in PSA 10, at recent sold prices", "n": len(top), "v": v,
                 "dates": [], "s": [], "d1": None, "w1": round((w - a) / a * 100, 2) if a else None, "m1": None, "vs90": True,
                 "top": [{"id": t[3]["id"], "g": t[3]["g"], "n": t[3]["n"], "p": t[0]} for t in top[:5]]}
    basis = (f"Modern Pokémon cards where a PSA 10 pays off best and sells at least weekly. Assumes raw at the lowest listing, "
             f"PSA {psa[0]} grading (${psa[1] / 100:.2f}, plus upcharges when a grade is worth more than the tier covers), "
             f"${gradecost.SHIP / 100:.0f} shipping, eBay selling fees, and 30% odds of a 10 and 50% of a 9.")
    return {"picks": picks[:8], "up": up, "down": down, "index": index, "n": len(graded), "basis": basis}


def main(argv):
    site = argv[0]
    sd = os.path.join(site, "data")
    sets = load_sets(sd)
    meta = json.load(open(os.path.join(sd, "meta.json")))
    today = meta.get("updated") or date.today().isoformat()
    modern_from = (date.fromisoformat(today) - timedelta(days=365 * MODERN_YEARS)).isoformat()
    live = [s for s in sets if (s.get("pub") or "") <= today]

    def items(pred_set, t, min_p=0):
        seen = {}
        for st in live:
            if not pred_set(st):
                continue
            for it in st["items"]:
                if it["t"] != t or not it.get("p") or it["p"] < min_p or SKIP.search(it["n"]):
                    continue
                if it["id"] not in seen or seen[it["id"]][1]["p"] < it["p"]:
                    seen[it["id"]] = (st, it)
        return list(seen.values())

    modern_pk = lambda s: s["k"] == "pokemon" and (s.get("pub") or "") >= modern_from
    indices = [x for x in [
        build_index("Chase 100", f"The 100 most valuable Pokémon cards from sets released since {modern_from[:4]}", items(modern_pk, "c"), 100),
        build_index("Modern Sealed 100", f"The 100 most valuable Pokémon sealed products (no cases) from sets released since {modern_from[:4]}", items(modern_pk, "s"), 100),
        build_index("One Piece 50", "The 50 most valuable One Piece cards", items(lambda s: s["k"] == "one-piece", "c"), 50),
    ] if x]

    # signals: a week of prices moving the same way, on cards worth $10+
    sig_up, sig_down, movers = [], [], []
    for st, it in items(lambda s: s["k"] in ("pokemon", "pokemon-jp", "one-piece", "lorcana", "riftbound", "gundam", "yugioh", "dragon-ball-fusion-world", "union-arena") and (s.get("pub") or "") >= modern_from, "c", 1000):
        f = [v for v in (it.get("s") or []) if v]
        if len(f) < 5:
            continue
        f = f[-8:]
        steps = [b - a for a, b in zip(f, f[1:])]
        moves = [x for x in steps if x]
        if len(f) >= 2 and f[-2]:
            d1 = pct(f[-1], f[-2])
            if d1 is not None and abs(d1) >= 1:
                movers.append(card(st, it, d1=d1, was=f[-2]))
        if len(moves) < 3:
            continue
        w = pct(f[-1], f[0])
        ups, downs = sum(x > 0 for x in moves) / len(moves), sum(x < 0 for x in moves) / len(moves)
        if w is not None and w >= 5 and ups >= 0.6 and f[-1] >= max(f[:-1]):
            strength = min(95, round(35 + min(w, 40) * 0.9 + ups * 25))
            sig_up.append(card(st, it, w=w, cons=round(ups * 100), strength=strength, why=f"Up {w:.0f}% over {len(f) - 1} days, rising on {sum(x > 0 for x in moves)} of {len(moves)} price changes and at its high for the week."))
        elif w is not None and w <= -5 and downs >= 0.6 and f[-1] <= min(f[:-1]):
            strength = min(95, round(35 + min(-w, 40) * 0.9 + downs * 25))
            sig_down.append(card(st, it, w=w, cons=round(downs * 100), strength=strength, why=f"Down {-w:.0f}% over {len(f) - 1} days, falling on {sum(x < 0 for x in moves)} of {len(moves)} price changes and at its low for the week."))
    GAME_ORDER = ["pokemon", "one-piece", "pokemon-jp", "yugioh", "lorcana", "dragon-ball-fusion-world", "gundam", "riftbound", "union-arena"]

    def spread(lst, n, per=8):
        """Up to `per` strongest per game, merged round-robin (Pokémon first) so every game shows,
        instead of the most volatile small games filling the whole list."""
        lst.sort(key=lambda c: (-c["strength"], -abs(c["w"]), -c["p"]))
        by = {}
        for c in lst:
            if len(by.setdefault(c["k"], [])) < per:
                by[c["k"]].append(c)
        order = sorted(by, key=lambda k: GAME_ORDER.index(k) if k in GAME_ORDER else 99)
        out = []
        for i in range(per):
            for k in order:
                if i < len(by[k]):
                    out.append(by[k][i])
        return out[:n]
    n_up, n_down = len(sig_up), len(sig_down)
    sig_up, sig_down = spread(sig_up, 80), spread(sig_down, 80)
    gainers = sorted((m for m in movers if m["d1"] > 0), key=lambda m: -m["d1"])[:10]
    losers = sorted((m for m in movers if m["d1"] < 0), key=lambda m: m["d1"])[:10]
    # top-of-page ticker: mostly Pokémon (what most visitors collect), a few from other games; $5+ cards, sane daily moves
    quota = {"pokemon": 10, "pokemon-jp": 3, "one-piece": 4}
    tick, seen_k = [], {}
    for m in sorted((m for m in movers if m["p"] >= 500 and 2 <= abs(m["d1"]) <= 80), key=lambda m: -abs(m["d1"]) * math.log10(m["p"])):
        if seen_k.get(m["k"], 0) < quota.get(m["k"], 1):
            seen_k[m["k"]] = seen_k.get(m["k"], 0) + 1
            tick.append(m)

    # market pulse: how each game's cards ($5+) moved over the last 7 days (falls back to all recorded days)
    labels = {g["slug"]: g["label"] for g in meta.get("games", [])}
    pulse, all_up, all_n = [], 0, 0
    for k in labels:
        chs = []
        for st, it in items(lambda s, k=k: s["k"] == k, "c", 500):
            c = (it.get("ch") or {})
            v = c.get("7") if c.get("7") is not None else c.get("a")
            if v is not None:
                chs.append(v)
        if len(chs) < 30:
            continue
        chs.sort()
        up = sum(1 for v in chs if v > 1)
        down = sum(1 for v in chs if v < -1)
        all_up += up
        all_n += up + down
        pulse.append({"k": k, "label": labels[k], "n": len(chs), "med": round(chs[len(chs) // 2], 1),
                      "up": round(up / len(chs) * 100), "down": round(down / len(chs) * 100)})
    pulse.sort(key=lambda g: -g["n"])
    breadth = round(all_up / all_n * 100) if all_n else None
    mood = None if breadth is None else ("Heating up" if breadth >= 55 else "Cooling off" if breadth <= 45 else "Mixed")

    deals = []
    try:
        b = json.load(open(os.path.join(sd, "buyer.json")))
        deals = [d for d in b.get("under") or [] if 1000 <= d.get("p", 0) <= 50000 and 15 <= d.get("off", 0) <= 45][:6]
    except (OSError, ValueError):
        pass

    # the brief: plain sentences from the numbers
    ix = {i["name"]: i for i in indices}
    ch, se = ix.get("Chase 100"), ix.get("Modern Sealed 100")

    def mv(i, k="w1"):
        v = i and i.get(k)
        if v is None:
            v = i and i.get("d1")
        return v

    def word(v, one=False):
        if v is None or abs(v) < 0.5:
            return "holds steady" if one else "hold steady"
        return ("climbs" if v > 0 else "slips") if one else ("climb" if v > 0 else "slip")
    cv, sv = mv(ch), mv(se)
    span = "this week" if ch and ch.get("w1") is not None else "today"
    if word(cv) == word(sv):
        head = f"A quiet market {span}: chase cards and sealed hold steady" if word(cv) == "hold steady" else f"Modern chase cards and sealed both {word(cv)} {span}"
    else:
        head = f"Chase cards {word(cv)} {span} while sealed {word(sv, True)}"
    parts = []
    if cv is not None:
        parts.append(f"The Chase 100 is {'up' if cv >= 0 else 'down'} {abs(cv):.1f}% {span} at ${ch['v'] / 100:,.0f}")
    if sv is not None:
        parts.append(f"Modern Sealed 100 is {'up' if sv >= 0 else 'down'} {abs(sv):.1f}%")
    body = ", and ".join(parts) + "." if parts else ""
    if gainers:
        g = gainers[0]
        body += f" Biggest jump today: {re.sub(r' [(](Holofoil|Normal|Foil)[)]$', '', g['n'])} ({g['sn']}), up {g['d1']:.0f}% to ${g['p'] / 100:,.2f}."
    if n_up:
        body += f" {n_up} card{'s' if n_up != 1 else ''} worth $10+ show steady week-long gains, {n_down} are cooling off."

    graded = graded_intel(sd, site, today)
    if graded.get("index"):
        indices.append(graded["index"])
    if graded.get("picks"):
        p0 = graded["picks"][0]
        body += f" Best grading pick: {clean_n(p0['n'])} ({p0['sn']}), PSA 10 sells for {p0['g10'] / p0['p']:.1f}x raw."
    out = {"date": today, "brief": {"head": head, "body": body.strip()}, "indices": indices, "graded": graded,
           "signals": {"up": sig_up, "down": sig_down, "n_up": n_up, "n_down": n_down}, "movers": {"up": gainers, "down": losers}, "ticker": tick, "deals": deals,
           "pulse": {"games": pulse, "breadth": breadth, "mood": mood},
           "history_days": len(indices[0]["dates"]) if indices else 0}
    with open(os.path.join(sd, "intel.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"), ensure_ascii=False)
    print(f"intel: {len(indices)} indices, {n_up} rising / {n_down} cooling signals, {len(gainers)} gainers, {len(deals)} deals · {head}")


if __name__ == "__main__":
    main(sys.argv[1:])
