"""One-off, read-only test of the PkmnPrices API against our own cards (DYS Edge data test).

    python tools/pkmnprices_probe.py [path to Edge's graded.enc]

Asks PkmnPrices for about 40 of our cards by TCGplayer product id and reports: is each card found, does its
TCGplayer price agree with ours, and (on a paid plan) what it has for graded and raw eBay sales, population
and price history. When Edge's graded file can be opened it also compares PSA 10 and PSA 9 prices with what
Edge holds now, as totals only. It stores nothing and changes nothing. Needs PKMNPRICES_KEY.
"""
import gzip
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))

API = "https://api.pkmnprices.com"
KEY = (os.environ.get("PKMNPRICES_KEY") or "").strip()
# [tcgplayer product id, our item name, set, our TCGplayer market price in cents (Nov 14, 2026), card number, game]
CARDS = [
    [610516, "Umbreon ex - 161/131 (Holofoil)", "SV: Prismatic Evolutions", 118684, "161/131", "pokemon"],
    [610511, "Sylveon ex - 156/131 (Holofoil)", "SV: Prismatic Evolutions", 37622, "156/131", "pokemon"],
    [610499, "Leafeon ex - 144/131 (Holofoil)", "SV: Prismatic Evolutions", 26278, "144/131", "pokemon"],
    [610505, "Glaceon ex - 150/131 (Holofoil)", "SV: Prismatic Evolutions", 23594, "150/131", "pokemon"],
    [517045, "Charizard ex - 199/165 (Holofoil)", "SV: Scarlet & Violet 151", 29222, "199/165", "pokemon"],
    [517046, "Blastoise ex - 200/165 (Holofoil)", "SV: Scarlet & Violet 151", 10318, "200/165", "pokemon"],
    [517044, "Venusaur ex - 198/165 (Holofoil)", "SV: Scarlet & Violet 151", 8734, "198/165", "pokemon"],
    [502556, "Charmander - 168/165 (Holofoil)", "SV: Scarlet & Violet 151", 7744, "168/165", "pokemon"],
    [590027, "Pikachu ex - 238/191 (Holofoil)", "SV08: Surging Sparks", 22581, "238/191", "pokemon"],
    [589985, "Latias ex - 239/191 (Holofoil)", "SV08: Surging Sparks", 16141, "239/191", "pokemon"],
    [590006, "Milotic ex - 237/191 (Holofoil)", "SV08: Surging Sparks", 9812, "237/191", "pokemon"],
    [246723, "Umbreon VMAX (Alternate Art Secret) (Holofoil)", "SWSH07: Evolving Skies", 232494, "215/203", "pokemon"],
    [246733, "Rayquaza VMAX (Alternate Art Secret) (Holofoil)", "SWSH07: Evolving Skies", 122316, "218/203", "pokemon"],
    [246758, "Dragonite V (Alternate Full Art) (Holofoil)", "SWSH07: Evolving Skies", 47387, "192/203", "pokemon"],
    [534919, "Mew ex - 232/091 (Holofoil)", "SV: Paldean Fates", 81425, "232/091", "pokemon"],
    [535090, "Charizard ex - 234/091 (Holofoil)", "SV: Paldean Fates", 25921, "234/091", "pokemon"],
    [654527, "Mega Lucario ex - 188/132 (Holofoil)", "ME01: Mega Evolution", 19186, "188/132", "pokemon"],
    [654518, "Mega Lucario ex - 179/132 (Holofoil)", "ME01: Mega Evolution", 15839, "179/132", "pokemon"],
    [42382, "Charizard (Holofoil)", "Base Set", 98713, "004/102", "pokemon"],
    [42360, "Blastoise (Holofoil)", "Base Set", 23449, "002/102", "pokemon"],
    [42355, "Venusaur (Holofoil)", "Base Set", 13740, "015/102", "pokemon"],
    [45122, "Snorlax (11) (1st Edition Holofoil)", "Jungle", 45499, "11/64", "pokemon"],
    [106521, "Gengar (5) (1st Edition Holofoil)", "Fossil", 72500, "05/62", "pokemon"],
    [86903, "Lugia (1st Edition Holofoil)", "Neo Genesis", 130000, "009/111", "pokemon"],
    [90099, "Typhlosion (18) (1st Edition Holofoil)", "Neo Genesis", 59999, "018/111", "pokemon"],
    [84584, "Dark Dragonite (5) (1st Edition Holofoil)", "Team Rocket", 54865, "05/82", "pokemon"],
    [86658, "Latias Star (Holofoil)", "EX Deoxys", 180000, "105/107", "pokemon"],
    [84186, "Charizard (Reverse Holofoil)", "Skyridge", 299999, "146/144", "pokemon"],
    [610521, "Raging Bolt ex (Holofoil)", "SV: Prismatic Evolutions", 5855, "166/131", "pokemon"],
    [610679, "Umbreon (Master Ball Pattern) (Holofoil)", "SV: Prismatic Evolutions", 5030, "059/131", "pokemon"],
    [610638, "Exeggutor (Master Ball Pattern) (Holofoil)", "SV: Prismatic Evolutions", 984, "002/131", "pokemon"],
    [517047, "Alakazam ex - 201/165 (Holofoil)", "SV: Scarlet & Violet 151", 5442, "201/165", "pokemon"],
    [517018, "Charmeleon - 169/165 (Holofoil)", "SV: Scarlet & Violet 151", 5127, "169/165", "pokemon"],
    [516663, "Gengar (Reverse Holofoil)", "SV: Scarlet & Violet 151", 974, "094/165", "pokemon"],
    [589967, "Hydreigon ex - 240/191 (Holofoil)", "SV08: Surging Sparks", 2930, "240/191", "pokemon"],
    [589930, "Durant ex - 236/191 (Holofoil)", "SV08: Surging Sparks", 2763, "236/191", "pokemon"],
    [593859, "Night Stretcher - 251/191 (Holofoil)", "SV08: Surging Sparks", 978, "251/191", "pokemon"],
    [246727, "Rayquaza V (Full Art) (Holofoil)", "SWSH07: Evolving Skies", 5983, "193/203", "pokemon"],
    [246717, "Umbreon V (Full Art) (Holofoil)", "SWSH07: Evolving Skies", 5588, "188/203", "pokemon"],
    [246741, "Suicune V (Full Art) (Holofoil)", "SWSH07: Evolving Skies", 985, "173/203", "pokemon"]
]
SEALED = [[503313, "151 Elite Trainer Box"], [0, "Prismatic Evolutions Elite Trainer Box"], [0, "Evolving Skies Booster Box"]]
NOW = datetime.now(timezone.utc)
spent = {"credits": 0, "calls": 0, "limit": None}


def call(path, **q):
    """(status, body, headers). Never raises on an HTTP error; keeps under 60 calls a minute."""
    url = API + path + ("?" + urllib.parse.urlencode({k: v for k, v in q.items() if v is not None}) if q else "")
    req = urllib.request.Request(url, headers={"X-API-Key": KEY, "Accept": "application/json", "User-Agent": "dys-market-probe"})
    time.sleep(1.1)
    spent["calls"] += 1
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            body, head, status = json.load(r), r.headers, r.status
    except urllib.error.HTTPError as e:
        head, status = e.headers, e.code
        try:
            body = json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            body = {}
    except Exception as e:  # network trouble
        return 0, {"error": str(e)[:120]}, {}
    try:
        spent["credits"] += int(float(head.get("x-credits-charged") or 0))
        if head.get("x-credits-limit"):
            spent["limit"] = int(float(head.get("x-credits-limit")))
    except ValueError:
        pass
    return status, body, head


def variant_of(name):
    for v in ("1st Edition Holofoil", "Reverse Holofoil", "Holofoil"):
        if name.endswith(f"({v})"):
            return v
    return "Normal"


def days_ago(ts):
    try:
        return (NOW - datetime.fromisoformat(ts.replace("Z", "+00:00"))).days
    except Exception:
        return None


def comps(card_id, **f):
    """Newest eBay sold comps for a card (one page). (status, rows, more)"""
    st, body, _ = call(f"/v1/cards/{card_id}/listings/ebay", limit=50, sort="date_desc", **f)
    if st != 200:
        return st, [], False
    return st, body.get("data") or [], bool((body.get("pagination") or {}).get("has_more"))


def digest(rows, more):
    ages = [a for a in (days_ago(r.get("sold_at") or "") for r in rows) if a is not None]
    usd = [r["price"] for r in rows if r.get("currency") in (None, "USD", "usd") and days_ago(r.get("sold_at") or "") is not None and days_ago(r["sold_at"]) <= 90]
    n30, n90 = sum(a <= 30 for a in ages), sum(a <= 90 for a in ages)
    full = more and ages and max(ages) <= 90
    return {"n": len(rows), "30d": f"{n30}{'+' if more and ages and max(ages) <= 30 else ''}", "90d": f"{n90}{'+' if full else ''}",
            "median90": round(statistics.median(usd), 2) if usd else None, "oldest_days": max(ages) if ages else None,
            "exact": sum(r.get("attribution") == "exact" for r in rows), "types": sorted({r.get("sale_type") or "?" for r in rows})}


def edge_graded(path):
    """What Edge holds now from PokemonPriceTracker, or None when the file or its key isn't here."""
    try:
        import sealed
        return json.loads(gzip.decompress(sealed.read("edge", path)))["c"]
    except Exception as e:
        print(f"Edge's graded file not opened ({type(e).__name__}: {str(e)[:80]}); the comparison with Edge is skipped")
        return None


def main():
    if not KEY:
        print("::error title=PkmnPrices probe::no PKMNPRICES_KEY secret is set for this repository")
        return 0
    st, body, head = call("/v1/cards", tcg_player_id=CARDS[0][0])
    if st in (401, 403):
        print(f"::error title=PkmnPrices probe::the key was refused (HTTP {st}): {json.dumps(body)[:200]}")
        return 0
    plan = {500: "Free", 20000: "Pro", 75000: "Scale", 200000: "Business"}.get(spent["limit"], f"credits/day {spent['limit']}")
    print(f"PLAN: {plan} | first call HTTP {st} | headers: " + ", ".join(f"{k}={v}" for k, v in head.items() if k.lower().startswith("x-")))
    print("LIST SAMPLE:", json.dumps(body)[:700])
    paid = None
    edge = edge_graded(sys.argv[1]) if len(sys.argv) > 1 else None
    out, cmp10, cmp9, stopped = [], [], [], None
    for pid, name, setn, ours, number, game in CARDS:
        row = {"pid": pid, "name": name, "set": setn}
        st, body, _ = call("/v1/cards", tcg_player_id=pid)
        if st == 429:
            stopped = f"credit or rate limit at {name}: {json.dumps(body)[:160]}"
            break
        found = (body.get("data") or []) if st == 200 else []
        row["found"] = len(found)
        if not found:
            row["http"] = st
            out.append(row)
            continue
        c = found[0]
        row.update(id=c["id"], pk_name=c.get("name"), pk_no=f"{c.get('number')}/{c.get('total_set_number')}", pk_set=(c.get("set") or {}).get("name"))
        st, card, _ = call(f"/v1/cards/{c['id']}")
        prices = (card.get("prices") or []) if st == 200 else []
        v = variant_of(name)
        tcg = [p for p in prices if str(p.get("source", "")).lower().startswith("tcg")]
        mine = [p for p in tcg if (p.get("variant") or "Normal") == v] or tcg
        nm = next((p for p in mine if (p.get("condition") or "") == "Near Mint"), mine[0] if mine else None)
        row["price_rows"] = len(prices)
        row["sources"] = sorted({str(p.get("source")) for p in prices})
        if nm:
            row["pk_tcg"] = nm.get("market_price")
            row["tcg_diff_pct"] = round((float(nm["market_price"]) * 100 / ours - 1) * 100, 1) if ours else None
        if len(out) == 0:
            print("CARD SAMPLE:", json.dumps({k: card.get(k) for k in ("id", "tcg_player_id", "name", "number", "set")}), "PRICES:", json.dumps(prices[:6])[:900])
        if paid is not False:
            st, pop, _ = call(f"/v1/cards/{c['id']}/population")
            if st == 403:
                paid = False
                print(f"PAID FEATURES: not on this plan (population answered HTTP 403: {json.dumps(pop)[:160]})")
            elif st == 200:
                paid = True
                pv = pop.get("variants") or []
                mv = next((x for x in pv if x.get("variant") == v), pv[0] if pv else None)
                if mv:
                    psa = (mv.get("graders") or {}).get("PSA") or (mv.get("graders") or {}).get("psa") or {}
                    row["pop"] = {"total": mv.get("total_population"), "gem_rate": mv.get("gem_rate"), "psa_total": psa.get("total"), "psa10": (psa.get("grades") or {}).get("10"),
                                  "psa9": (psa.get("grades") or {}).get("9"), "spec_id": psa.get("spec_id"), "updated": (mv.get("updated_at") or "")[:10], "variants": len(pv)}
                    if not any("pop" in r for r in out):
                        print("POPULATION SAMPLE:", json.dumps(pop)[:1200])
                else:
                    row["pop"] = None
        if paid:
            for label, f in (("psa10", {"graded": "true", "grader": "PSA", "grade": "10"}), ("psa9", {"graded": "true", "grader": "PSA", "grade": "9"}), ("raw", {"graded": "false"})):
                st, rows, more = comps(c["id"], **f)
                row[label] = digest(rows, more) if st == 200 else {"http": st}
                if label == "psa10" and rows and not any("psa10" in r for r in out):
                    print("COMP SAMPLE:", json.dumps(rows[0])[:700])
            e = (edge or {}).get(str(pid))
            if e:
                for label, bucket in (("psa10", cmp10), ("psa9", cmp9)):
                    g, mine_ = e[1].get(label), row.get(label) or {}
                    if g and g[0] and mine_.get("median90"):
                        bucket.append((mine_["median90"] * 100 / g[0] - 1) * 100)
                row["in_edge"] = sorted(e[1].keys())
        out.append(row)
    print("=====PKMNPRICES-PROBE-BEGIN=====")
    for r in out:
        print(json.dumps(r, ensure_ascii=False))
    print("=====PKMNPRICES-PROBE-END=====")
    # price history: what comes back, how far, and what one row looks like
    if paid:
        for pid in (610516, 42382, 516663):
            r = next((x for x in out if x["pid"] == pid and x.get("id")), None)
            if not r:
                continue
            for q in ({"period": "1y", "limit": 400}, {"limit": 400}):
                st, h, head = call(f"/v1/cards/{r['id']}/prices/history", **q)
                rows = h.get("data") or []
                print(f"HISTORY {r['name']} {q}: HTTP {st}, rows {len(rows)}, credits {head.get('x-credits-charged') if head else None}, "
                      f"dates {rows[-1].get('date') if rows else None}..{rows[0].get('date') if rows else None}, sources {sorted({str(x.get('source')) for x in rows})}, "
                      f"pagination {json.dumps(h.get('pagination'))[:120]}, first {json.dumps(rows[:2])[:500]}" if st == 200 else f"HISTORY {r['name']} {q}: HTTP {st} {json.dumps(h)[:200]}")
                if st == 200 and rows:
                    break
    # sealed and Japanese
    for pid, name in SEALED:
        st, s, _ = call("/v1/sealed", name=name, per_page=5)
        print(f"SEALED '{name}': HTTP {st}", json.dumps([{k: x.get(k) for k in ("id", "tcg_player_id", "name")} for x in (s.get("data") or [])][:5]) if st == 200 else json.dumps(s)[:200])
    st, j, _ = call("/v1/cards", name="Umbreon ex", language="japanese", per_page=3)
    print(f"JAPANESE name search: HTTP {st}", json.dumps([{k: x.get(k) for k in ("id", "tcg_player_id", "name", "number")} for x in (j.get("data") or [])][:3]) if st == 200 else json.dumps(j)[:200])
    # totals
    n, hit = len(out), [r for r in out if r.get("found")]
    diffs = [abs(r["tcg_diff_pct"]) for r in hit if r.get("tcg_diff_pct") is not None]
    S = lambda a: (f"median {statistics.median(a):.1f}%, within 10%: {sum(x <= 10 for x in map(abs, a))} of {len(a)}, within 25%: {sum(x <= 25 for x in map(abs, a))} of {len(a)}" if a else "nothing to compare")
    print("=====TOTALS=====")
    print(f"plan {plan}; cards asked {n} of {len(CARDS)}; found by TCGplayer id {len(hit)}; more than one match {sum(r['found'] > 1 for r in hit)}; stopped early: {stopped}")
    print(f"TCGplayer price against ours: {S(diffs)}")
    if paid:
        has = lambda k: sum(1 for r in hit if isinstance(r.get(k), dict) and r[k].get("n"))
        print(f"with PSA 10 sales {has('psa10')}; with PSA 9 sales {has('psa9')}; with raw sales {has('raw')}; with population {sum(1 for r in hit if r.get('pop'))} (of {len(hit)})")
        print(f"PSA 10 price against Edge's (90-day medians): {S(cmp10)}")
        print(f"PSA 9 price against Edge's (90-day medians): {S(cmp9)}")
        print(f"cards Edge has graded data for: {sum(1 for r in hit if r.get('in_edge'))} of {len(hit)}" if edge is not None else "Edge comparison skipped")
    print(f"calls {spent['calls']}; credits charged {spent['credits']} of {spent['limit']} a day")
    print(f"::notice title=PkmnPrices probe::{plan}: found {len(hit)} of {n} cards by TCGplayer id; paid features {'on' if paid else 'off'}; {spent['credits']} credits used")
    return 0


if __name__ == "__main__":
    sys.exit(main())
