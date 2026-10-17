"""Owner's buyer dashboard data -> site/data/buyer.json (unlisted page buyer.html).

    python pipeline/buyer.py

Built from data the site already has:
  * set files (market price, % changes, recent price series)
  * data/lows/latest.json (lowest current TCGplayer listing per product, saved by run.py)
  * site/data/stock.json (our Shopify price next to market)
Sections: listed under market, dips from recent highs, our store prices to fix, risers we hold.
Want-list demand is read live from data/demand.json by the page itself.
"""
import glob
import json
import os
import re
from datetime import date

import config
from build import label

SKIP = re.compile(r"prerelease|\[staff\]|code card|jumbo|oversize|\bdeck\b.*\bcard\b|world championships", re.I)
MIN_CARD, MIN_SEALED = 1000, 2000          # only items worth $10+ (cards) / $20+ (sealed)


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def main():
    out_dir = config.OUT_DIR
    today = date.today().isoformat()
    products = load(os.path.join(config.DATA_DIR, "catalog", "products.json"), {}) or {}
    lows_doc = load(os.path.join(config.DATA_DIR, "lows", "latest.json"), {}) or {}
    lows = lows_doc.get("lows", {})

    items = {}       # "id|name" -> (item, set)
    for path in glob.glob(os.path.join(out_dir, "set", "*.json")):
        d = load(path)
        if not d or (d.get("pub") or "") > today:
            continue
        s = {"id": d["id"], "n": d["n"], "k": d["k"], "pub": d.get("pub")}
        for i in d["items"]:
            if i.get("p"):
                items[f"{i['id']}|{i['n']}"] = (i, s)

    def row(i, s, **extra):
        r = {"id": i["id"], "n": i["n"], "t": i["t"], "g": s["id"], "sn": s["n"], "k": s["k"], "p": i["p"]}
        if i.get("dys"):
            r["dys"] = i["dys"]["p"]
        r.update(extra)
        return r

    def worth(i):
        return i["p"] >= (MIN_SEALED if i["t"] == "s" else MIN_CARD) and not SKIP.search(i["n"])

    # 1) listed under market right now (lowest TCGplayer listing well below market price)
    under = []
    for key, lo in lows.items():
        pid, _ = key.split(":", 1)
        if pid not in products:
            continue
        _, name = label(products, key)
        hit = items.get(f"{pid}|{name}")
        if not hit:
            continue
        i, s = hit
        if not worth(i) or lo >= i["p"] * 0.8 or lo < i["p"] * 0.25:   # <25% is almost always a wrong-condition/junk listing
            continue
        under.append(row(i, s, lo=lo, off=round((1 - lo / i["p"]) * 100, 1), save=i["p"] - lo))
    under.sort(key=lambda r: -r["save"])

    # 2) dips: well below the recent high in the price series
    dips = []
    for i, s in items.values():
        ser = [v for v in (i.get("s") or []) if v]
        if not worth(i) or len(ser) < 3:
            continue
        hi = max(ser)
        drop = (hi - i["p"]) / hi * 100 if hi else 0
        if drop >= 12:
            dips.append(row(i, s, hi=hi, drop=round(drop, 1)))
    dips.sort(key=lambda r: -(r["hi"] - r["p"]))

    # 3) our store: price vs market, and things we hold that are rising
    stock = load(os.path.join(out_dir, "stock.json"), []) or []
    fix, rising = [], []
    for st in stock:
        if not st.get("a", True) or not st.get("m") or not st.get("p"):
            continue
        hit = next((v for k, v in items.items() if k.startswith(f"{st['id']}|")), None)
        ch = (hit[0].get("ch") or {}) if hit else {}
        best = ch.get("7", ch.get("30", ch.get("a")))
        base = {"id": st["id"], "n": st["n"], "t": st["t"], "g": st["g"], "k": st["k"], "p": st["m"], "dys": st["p"], "u": st.get("u"),
                "sn": hit[1]["n"] if hit else ""}
        gap = (st["p"] - st["m"]) / st["m"] * 100
        if gap <= -5 or gap >= 15:
            fix.append(dict(base, gap=round(gap, 1)))
        if best is not None and best >= 8:
            rising.append(dict(base, ch=best))
    fix.sort(key=lambda r: r["gap"])
    rising.sort(key=lambda r: -r["ch"])

    doc = {"updated": today, "lows_day": lows_doc.get("day"), "under": under[:80], "dips": dips[:80], "fix": fix, "rising": rising[:40]}
    with open(os.path.join(out_dir, "buyer.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"buyer: {len(under)} under market, {len(dips)} dips, {len(fix)} store prices to check, {len(rising)} rising in stock")


if __name__ == "__main__":
    main()
