"""Daily Card Scout files for the owner's private dashboard, built only from the site's own data.

    python3 tools/card_scout.py <gh-pages folder> --out <folder> [--date YYYY-MM-DD]

Reads the files the nightly job already publishes (data/scout.json, data/intel.json,
data/set/<id>.json, data/upcoming.json, data/announced.json) and writes hunt.json, avoid.json,
catalysts.json, pulse.json and brief.json in the shape the dashboard page reads. No web access,
no keys: every number is a TCGplayer market price the site recorded.

Exit code 2 = the site data is too old (the nightly job has not run for 3+ days); nothing is
written, so the dashboard keeps its last good data.
"""
import argparse
import json
import os
import re
import sys
from datetime import date, timedelta

GAMES = {"pokemon": "Pokémon", "one-piece": "One Piece"}
CAL_GAMES = {"pokemon": "Pokémon", "pokemon-jp": "Pokémon", "one-piece": "One Piece"}
SITE = "https://market.driveyourstyle.net"
MINUS = "−"
# staff / event / prize cards: thin markets a buyer won't find at a show
EVENT = re.compile(r"staff|prerelease|pre-release|winner|judge|finalist|champion|top player|tournament|"
                   r"event pack|placement|serial|trophy|illustration contest|sealed battle|regional|"
                   r"treasure cup|flagship|dodgers|stadium|x one piece", re.I)
STALE_DAYS = 3
HUNT_MAX, PER_GAME_MAX, AVOID_MAX = 6, 4, 6


def load(root, rel, default=None):
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def money(cents):
    v = cents / 100
    return f"${v:,.0f}" if v >= 1000 else f"${v:,.2f}"


def card_name(n, no):
    """TCGplayer name -> short unique label with the card number, e.g. 'Giratina XY184'."""
    base = n
    if no:
        base = re.sub(r"\s+-\s+" + re.escape(no) + r"(?=\s|$)", "", base)
    base = re.sub(r"\s*\((Holofoil|Foil|Normal)\)", "", base).strip()
    return f"{base} {no}".strip() if no and no not in base else base


def url(i):
    return f"{SITE}/product.html?id={i['id']}&set={i['g']}"


def changes(root, cache, i):
    """7/30/90-day % change for one product, from its set file."""
    g = i["g"]
    if g not in cache:
        doc = load(root, f"data/set/{g}.json", {}) or {}
        cache[g] = {x["id"]: x.get("ch") or {} for x in doc.get("items", [])}
    ch = cache[g].get(i["id"], {})
    r = lambda k: round(ch[k], 1) if isinstance(ch.get(k), (int, float)) else None
    return r("7"), r("30"), r("90")


def is_event(i):
    return bool(EVENT.search(i.get("n", "")) or EVENT.search(i.get("sn", "")))


def pounce(now, steady):
    v = now * (0.80 if steady else 0.75)
    step = 25 if v >= 1000 else 5 if v >= 200 else 1          # a clean number to say out loud
    return max(1, int(round(v / step) * step))


def build_hunt(root, scout, intel):
    cache, rows, seen = {}, [], set()

    def consider(i, why, steady, rank):
        if i["id"] in seen or i.get("k") not in GAMES or i.get("t", "c") != "c" or is_event(i):
            return
        c7, c30, c90 = changes(root, cache, i)
        if c7 is None and i.get("w7") is not None:
            c7 = round(i["w7"], 1)
        # a move that held: up over 30 days, and not giving it back this week
        if c30 is None or c30 <= 0 or (c7 is not None and c7 < 0):
            return
        seen.add(i["id"])
        now = round(i["p"] / 100, 2)
        rows.append({"_rank": rank, "_k": i["k"],
                     "card": card_name(i["n"], i.get("no")), "game": GAMES[i["k"]], "set": i.get("sn", ""),
                     "now": now, "chg7d": c7, "chg30d": c30, "chg90d": c90, "sales": None,
                     "pounce": pounce(now, steady), "why": why, "url": url(i)})

    for p in scout.get("picks", []):
        if p.get("plan") != "ride":
            continue
        reasons = [r for r in p.get("why", []) if not r.startswith("Hold while")]
        slow = any("few recent sales" in r or "hasn't moved" in r for r in p.get("risk", []))
        regular = any("sells regularly" in r for r in p.get("why", []))
        steady = regular and not slow and abs(p.get("w7") or 0) < 25
        why = ". ".join(reasons[:2]) + "."
        if p.get("risk"):
            why += " Risk: " + p["risk"][0] + "."
        if p.get("stop"):
            why += f" Trend is broken under {money(p['stop'])}."
        consider(p, why, steady, (0 if p.get("v") == "buy" else 1, -p.get("score", 0)))
    for s in (intel.get("signals") or {}).get("up", []):          # filler: steady week-long gainers
        consider(s, s.get("why", "Rising steadily this week."), False, (2, -s.get("strength", 0)))

    rows.sort(key=lambda r: r["_rank"])
    out, per = [], {}
    for r in rows:
        if len(out) >= HUNT_MAX:
            break
        if per.get(r["_k"], 0) >= PER_GAME_MAX:
            continue
        per[r["_k"]] = per.get(r["_k"], 0) + 1
        out.append(r)
    names = set()
    for r in out:
        if r["card"] in names:
            r["card"] += " #" + r["url"].split("id=")[1].split("&")[0]
        names.add(r["card"])
        r.pop("_rank"), r.pop("_k")
    return out


def build_avoid(scout, intel):
    out, seen = [], set()

    def add(i, move, reason):
        if i["id"] in seen or i.get("k") not in GAMES or len(out) >= AVOID_MAX:
            return
        seen.add(i["id"])
        out.append({"card": card_name(i["n"], i.get("no")), "game": GAMES[i["k"]], "price": money(i["p"]),
                    "move": move, "reason": reason, "url": url(i)})

    spikes = [t for t in intel.get("ticker", []) if t.get("k") in GAMES and (t.get("d1") or 0) >= 40]
    for t in sorted(spikes, key=lambda t: -t["d1"])[:2]:
        add(t, f"+{t['d1']:.0f}% (1d)",
            f"Jumped from {money(t['was'])} in one day. One-day spikes often give it back; wait for it to hold a week.")
    for a in scout.get("avoid", []):
        add(a, f"{MINUS}{abs(a['w7']):.0f}% (7d)", a.get("why", "Falling steadily. Wait for it to stop."))
    for s in (intel.get("signals") or {}).get("down", []):
        add(s, f"{MINUS}{abs(s['w']):.0f}% (7d)", s.get("why", "Falling steadily. Wait for it to stop."))
    names = set()
    for r in out:
        if r["card"] in names:
            r["card"] += " #" + r["url"].split("id=")[1].split("&")[0]
        names.add(r["card"])
    return out


def build_catalysts(root, today):
    end, out, seen = today + timedelta(days=35), [], set()
    for s in (load(root, "data/upcoming.json", []) or []) + (load(root, "data/announced.json", []) or []):
        k, pub = s.get("k"), (s.get("pub") or "")[:10]
        if k not in CAL_GAMES or not pub or not (today.isoformat() <= pub <= end.isoformat()):
            continue
        event = f"{s['n']} release" + (" (Japan)" if k == "pokemon-jp" else "")
        if event in seen:
            continue
        seen.add(event)
        angle = ("Japanese set. Its chase cards show which English cards get hype next."
                 if k == "pokemon-jp" else
                 "New set. Prices start high and fall for 2 to 4 weeks, so wait on its chase cards. "
                 "Older singles often dip while buyers chase the new set.")
        out.append({"date": pub, "game": CAL_GAMES[k], "event": event, "angle": angle})
    return sorted(out, key=lambda r: r["date"])


def index_change(ix, days):
    """% change of an index over about N days, from its stored (not daily) history."""
    want = (date.fromisoformat(ix["dates"][-1]) - timedelta(days=days)).isoformat()
    past = [(d, v) for d, v in zip(ix["dates"], ix["s"]) if v and d <= want]
    if not past or not ix.get("v"):
        return None
    return round((ix["v"] - past[-1][1]) / past[-1][1] * 100, 1)


def build_pulse(intel):
    games = {g["k"]: g for g in (intel.get("pulse") or {}).get("games", [])}
    idx = {i["name"]: i for i in intel.get("indices", [])}
    out = []
    for market, k, label, name in (("pokemon", "pokemon", "Pokémon", "Chase 100"),
                                   ("onepiece", "one-piece", "One Piece", "One Piece 50")):
        ix, g = idx.get(name), games.get(k)
        if not ix or not g:
            continue
        c90 = index_change(ix, 90)
        out.append({"market": market, "label": label, "index": round(ix["v"] / 100),
                    "chg7d": round(ix["w1"], 1), "chg30d": round(ix["m1"], 1),
                    "chg90d": c90 if c90 is not None else 0,
                    "advancing": int(g["up"]), "tracked": int(g["n"]), "asof": intel["date"]})
    return out


def build_brief(today, intel, hunt, avoid, pulse):
    b, sig = intel.get("brief") or {}, intel.get("signals") or {}
    idx = {i["name"]: i for i in intel.get("indices", [])}
    rows = [{"id": "asof", "section": "meta", "order": 0, "text": today.isoformat()}]
    chase = idx.get("Chase 100")
    head = (b.get("head") or "Market update").rstrip(".") + "."
    if chase:
        w = chase["w1"]
        head += f" The Chase 100 (top modern Pokémon cards) is {'up' if w >= 0 else 'down'} {abs(w):.1f}% this week at {money(chase['v'])}."
    rows.append({"id": "headline", "section": "headline", "order": 0, "text": head})

    plan = []
    for h in hunt[:2]:
        plan.append(f"Buy {h['card']} ({h['game']}) at ${h['pounce']:,} or less. Market is ${h['now']:,.2f}, up {h['chg30d']:.0f}% in 30 days.")
    other = next((h for h in hunt[2:] if plan and h["game"] != hunt[0]["game"]), None) or (hunt[2] if len(hunt) > 2 else None)
    if avoid:
        a = avoid[0]
        span = {"1d": "in one day", "7d": "this week"}.get(a["move"].split("(")[-1].rstrip(")"), "")
        plan.append(f"Skip {a['card']} at {a['price']}, {a['move'].split(' (')[0]} {span}. {a['reason'].split('. ')[-1]}")
    elif other:
        plan.append(f"Buy {other['card']} ({other['game']}) at ${other['pounce']:,} or less. Market is ${other['now']:,.2f}.")
    while len(plan) < 3:
        plan.append("No more clear buys today. Keep cash for cards that hold a gain for 30 days.")
    for n, t in enumerate(plan[:3], 1):
        rows.append({"id": f"plan{n}", "section": "plan", "order": n, "text": t})

    supply = []
    if sig.get("n_up") is not None:
        supply.append(f"{sig['n_up']} cards worth $10+ are rising steadily this week and {sig['n_down']} are cooling off.")
    sealed = idx.get("Modern Sealed 100")
    if sealed:
        supply.append(f"Modern Pokémon sealed (top 100 products) is {'up' if sealed['w1'] >= 0 else 'down'} {abs(sealed['w1']):.1f}% this week "
                      f"and {'up' if sealed['m1'] >= 0 else 'down'} {abs(sealed['m1']):.1f}% this month.")
    op = next((p for p in pulse if p["market"] == "onepiece"), None)
    if op:
        supply.append(f"One Piece top 50 cards are {'up' if op['chg7d'] >= 0 else 'down'} {abs(op['chg7d']):.1f}% this week; "
                      f"{op['advancing']}% of One Piece cards rose.")
    mood = (intel.get("pulse") or {}).get("mood")
    if mood:
        supply.append(f"Overall mood: {mood.lower()}. {(intel.get('pulse') or {}).get('breadth')}% of moving cards went up.")
    while len(supply) < 3:
        supply.append("Prices are TCGplayer market prices from market.driveyourstyle.net. Check live sold comps before a big buy.")
    for n, t in enumerate(supply[:5], 1):
        rows.append({"id": f"supply{n}", "section": "supply", "order": n, "text": t})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pages")
    ap.add_argument("--out", required=True)
    ap.add_argument("--date", default=date.today().isoformat())
    a = ap.parse_args()
    today = date.fromisoformat(a.date)

    scout, intel = load(a.pages, "data/scout.json"), load(a.pages, "data/intel.json")
    if not scout or not intel:
        sys.exit("card scout: data/scout.json or data/intel.json is missing")
    for name, doc in (("scout", scout), ("intel", intel)):
        age = (today - date.fromisoformat(doc["date"])).days
        if age > STALE_DAYS:
            print(f"card scout: STALE, {name} data is dated {doc['date']} ({age} days old)", file=sys.stderr)
            sys.exit(2)

    hunt, avoid = build_hunt(a.pages, scout, intel), build_avoid(scout, intel)
    pulse = build_pulse(intel)
    files = {"hunt": hunt, "avoid": avoid, "catalysts": build_catalysts(a.pages, today), "pulse": pulse,
             "brief": build_brief(today, intel, hunt, avoid, pulse)}
    if len(pulse) != 2:
        sys.exit("card scout: an index is missing from data/intel.json")
    os.makedirs(a.out, exist_ok=True)
    for name, rows in files.items():
        with open(os.path.join(a.out, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
    print(f"card scout: {len(hunt)} to hunt, {len(avoid)} to avoid, {len(files['catalysts'])} catalysts, "
          f"data dated {scout['date']}")
    if hunt:
        print(f"top pick: {hunt[0]['card']} at or under ${hunt[0]['pounce']:,}")


if __name__ == "__main__":
    main()
