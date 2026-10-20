"""Market Intel: daily brief, market indices, signals, top movers and deals.

    python tools/intel.py site

Reads site/data/set/*.json (+ site/data/buyer.json for deals) and writes site/data/intel.json
for the Intel page. Everything is computed from recorded TCGplayer market prices with plain,
explainable rules (no predictions): an index is a fixed basket's total value per day, and a signal
is a price trend that has been consistent over the last week.
"""
import glob
import json
import os
import re
import sys
from datetime import date, timedelta

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
    for st, it in items(lambda s: s["k"] in ("pokemon", "one-piece", "lorcana", "riftbound", "gundam") and (s.get("pub") or "") >= modern_from, "c", 1000):
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
    def spread(lst, n, per=2):
        """strongest first, at most `per` from one game so every game gets a look"""
        lst.sort(key=lambda c: (-c["strength"], -c["p"]))
        out, used = [], {}
        for c in lst:
            if used.get(c["k"], 0) < per:
                out.append(c)
                used[c["k"]] = used.get(c["k"], 0) + 1
        return (out + [c for c in lst if c not in out])[:n]
    n_up, n_down = len(sig_up), len(sig_down)
    sig_up, sig_down = spread(sig_up, 6), spread(sig_down, 4)
    gainers = sorted((m for m in movers if m["d1"] > 0), key=lambda m: -m["d1"])[:6]
    losers = sorted((m for m in movers if m["d1"] < 0), key=lambda m: m["d1"])[:6]

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

    out = {"date": today, "brief": {"head": head, "body": body.strip()}, "indices": indices,
           "signals": {"up": sig_up, "down": sig_down, "n_up": n_up, "n_down": n_down}, "movers": {"up": gainers, "down": losers}, "deals": deals,
           "history_days": len(indices[0]["dates"]) if indices else 0}
    with open(os.path.join(sd, "intel.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"), ensure_ascii=False)
    print(f"intel: {len(indices)} indices, {n_up} rising / {n_down} cooling signals, {len(gainers)} gainers, {len(deals)} deals · {head}")


if __name__ == "__main__":
    main(sys.argv[1:])
