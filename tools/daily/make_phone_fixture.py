"""A Daily deals test file: the phone extract (dys-research finder.phone_extract) of a real derived finder report, plus
two synthetic CANDIDATE rows and one UNCERTAIN row for cards in the local site copy, so Deal check links can be tested.
    python3 tools/daily/make_phone_fixture.py <finder-report.json> <site copy> <dys-research dir> <out.json>"""
import json, sys
rep_p, site, rdir, out = sys.argv[1:5]
sys.path.insert(0, f"{rdir}/research/finder"); sys.path.insert(0, f"{rdir}/research/stage4")
import finder as FF
rep = json.load(open(rep_p))
items = {it["id"]: (g, it) for g in (23821, 23237, 604) for it in json.load(open(f"{site}/data/set/{g}.json"))["items"]}
def fake(i, label, mx, prof, reason):
    g, it = items[i]
    return {"tcgplayer_id": i, "name": it["n"], "set": "SV: Prismatic Evolutions" if g == 23821 else str(g), "number": "", "printing": "Holofoil", "label": label,
            "reasons": [reason] if reason else [], "max_listing_price": mx, "allowed_all_in": round(mx * 1.1, 2), "profit_if_bought_at_max": prof,
            "tcgplayer_url": f"https://www.tcgplayer.com/product/{i}?Language=English&Condition=Near+Mint", "evidence": {"ebay_raw_sales_30d": "8–19", "ebay_median_vs_nm": "within 5%"}}
ph = FF.phone_extract(rep)
extra = [fake(610521, "CANDIDATE", 30.0, 9.5, ""), fake(610513, "CANDIDATE", 14.0, 5.2, ""), fake(610509, "UNCERTAIN", 12.0, 5.0, "fewer than 5 clean eBay sales")]
ph["cards"] = [x for x in extra if x["label"] == "CANDIDATE"] + [x for x in extra if x["label"] == "UNCERTAIN"] + ph["cards"]
ph["counts"]["candidates"] += 2; ph["counts"]["uncertain"] += 1; ph["data_day"] = __import__("datetime").date.today().isoformat()
json.dump(ph, open(out, "w"))
print(f"wrote {out}: {len(ph['cards'])} cards", ph["counts"])
