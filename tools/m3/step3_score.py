"""M3 Step 3: score the live listing check per STEP3_METHOD.md.
usage: python3 tools/m3/step3_score.py sample.json live.json out.json"""
import json, re, sys
S = {p["id"]: p for p in json.load(open(sys.argv[1]))}
live = json.load(open(sys.argv[2]))
NM8 = json.load(open(sys.argv[4])) if len(sys.argv) > 4 else {}
NOT_RAW_EN = re.compile(r"chinese|japanese|italian|korean|french|german|spanish|portuguese|\\b(bgs|cgc|psa|sgc|tag)\\b|slab|graded|proxy|custom art", re.I)
TAX = 0.08375
def tcg_net(r, sealed):
    ship = (15 if r >= 100 else 8) if sealed else (5 if r >= 50 else 1)
    return r * (1 - 0.1325) - 0.30 - ship
out = []
for x in live:
    e = S[x["id"]]; sealed = e["t"] == "s"
    elo, emk = e["lo"] / 100, e["p"] / 100
    if str(x["id"]) in NM8:   # 8 cheapest NM listings with photo-listing titles; titles naming another language or a slab are not raw English
        all8 = NM8[str(x["id"])]
        excluded = [l for l in all8 if NOT_RAW_EN.search(l[2])]
        nm = sorted([["NM", l[0], l[1], 1, l[3], "custom" if l[2] else ""] for l in all8 if not NOT_RAW_EN.search(l[2])], key=lambda l: l[1] + l[2])
    else:
        excluded = []
        nm = sorted(x["nm"], key=lambda l: l[1] + l[2])
    NM = x["NM"] or [0, 0, None, None, None]
    R = NM[4]
    best = nm[0] if nm else None
    row = {"n": len(out) + 1, "id": x["id"], "list": e["list"], "stratum": e["stratum"], "card": f'{x["name"]} · {x["set"]} · {x["no"]}',
           "printing": x["pr"], "edge_market": emk, "edge_lowest": elo, "edge_off": round((1 - elo / emk) * 100),
           "cheapest_any": x["any"][0] if x["any"] else None, "nm_listings": x["nmN"], "nm_best": best,
           "nm_sold_90": NM[0], "nm_sold_30": NM[1], "nm_range_30": [NM[2], NM[3]], "nm_market": R,
           "lp": x["LP"], "url": f'https://www.tcgplayer.com/product/{x["id"]}?Language=English'}
    if best and R:
        cost = best[1] * (1 + TAX) + best[2]
        p_tcg = tcg_net(R, sealed) - cost; p_loc = 0.9 * R - cost
        row.update({"all_in": round(cost, 2), "profit_tcg": round(p_tcg, 2), "roi_tcg": round(p_tcg / cost * 100, 1),
                    "profit_local90": round(p_loc, 2), "roi_local90": round(p_loc / cost * 100, 1)})
    # verdict (fixed in STEP3_METHOD.md)
    if NM[0] < 3: v = "UNCERTAIN"
    elif best and row.get("profit_tcg", -1) >= 5 and row["roi_tcg"] >= 20: v = "VERIFIED"
    else: v = "FAIL"
    row["verdict"] = v
    # flags
    nm_floor = min([b for b in [(best[1] + best[2]) if best else None, NM[2], R] if b] or [float("inf")])
    flags = []
    if elo < 0.9 * nm_floor: flags.append("condition mismatch")
    if R and emk > 1.15 * R or NM[1] == 0: flags.append("stale market")
    if not any(l[1] <= elo for l in x["any"]): flags.append("unavailable")
    if row["edge_off"] > 35: flags.append("suspicious discount")
    if best and best[5] == "custom" and R and best[1] < 0.6 * R: flags.append("NM claim below 60% of NM sales (photo listing)")
    if excluded and min(l[0] + l[1] for l in excluded) < (best[1] + best[2] if best else 1e9):
        flags.append(f"{len(excluded)} cheaper 'English NM' listing(s) were really " + "/".join(sorted({m.group(0).lower() for l in excluded for m in [NOT_RAW_EN.search(l[2])]})))
    row["excluded"] = excluded
    row["flags"] = flags
    out.append(row)
json.dump(out, open(sys.argv[3], "w"), indent=1)
from collections import Counter
print(Counter(r["verdict"] for r in out))
for r in out:
    b = r["nm_best"]
    print(f'{r["n"]:>2} {r["verdict"]:9} {r["card"][:45]:45} edge lo ${r["edge_lowest"]:>8.2f} mkt ${r["edge_market"]:>8.2f} | NM best {("$%.2f+%.2f %s" % (b[1], b[2], b[5])) if b else "none":>18} | NM sold 90/30 {r["nm_sold_90"]}/{r["nm_sold_30"]} mkt {r["nm_market"]} | all-in {r.get("all_in")} tcg {r.get("profit_tcg")} ({r.get("roi_tcg")}%) local {r.get("profit_local90")} | {", ".join(r["flags"])}')
