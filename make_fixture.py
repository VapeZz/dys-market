"""Build a fake TCGCSV tree + fake Shopify products.json for local testing,
and seed ~400 days of synthetic price history. Data is invented."""
import gzip
import json
import os
import random
import sys
from datetime import date, timedelta

ROOT = sys.argv[1]
DATA_DIR = sys.argv[2]
TODAY = date(2026, 10, 13)
random.seed(7)

SETS = {
    3: [("Pitch Black", "ME05", "2026-07-17"), ("Chaos Rising", "ME04", "2026-05-22"),
        ("Ascended Heroes", "ASC", "2026-01-30"), ("30th Celebration", "30TH", "2026-09-16"),
        ("Perfect Order", "ME03", "2026-03-27"), ("Prismatic Evolutions", "PRE", "2025-01-17"),
        ("Destined Rivals", "SV10", "2025-05-30"), ("Mega Evolution", "ME01", "2025-09-26")],
    85: [("Inferno X", "M2", "2025-09-26"), ("Mega Dream ex", "M2a", "2025-11-28"),
         ("Nihil Zero", "M3", "2026-01-23")],
    68: [("The World's Strongest Warriors", "OP17", "2026-08-28"), ("The Time of Battle", "OP16", "2026-06-13"),
         ("Carrying On His Will", "OP13", "2025-11-07")],
}
SEALED = ["Booster Box", "Elite Trainer Box", "Booster Bundle", "Sleeved Booster Pack",
          "Booster Box Case", "3 Pack Blister", "Mini Tin"]
OP_SEALED = ["Booster Box", "Booster Pack", "Booster Box Case"]
CARDS = ["Pikachu ex", "Charizard ex", "Mega Gengar ex", "Umbreon ex", "Mew ex", "Lucario",
         "Gardevoir ex", "Iono", "Clefairy", "Greninja ex", "Dragonite", "Lillie's Clefairy ex"]
OP_CARDS = ["Monkey.D.Luffy", "Shanks", "Rocks.D.Xebec", "Kaido", "Nami", "Roronoa Zoro"]
RAR = ["Special Illustration Rare", "Illustration Rare", "Ultra Rare", "Double Rare", "Common"]


def w(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj))


base = os.path.join(ROOT, "tcgplayer")
w(os.path.join(ROOT, "last-updated.txt"), f"{TODAY.isoformat()}T20:05:00+0000")
pid = 600000
gid = 24000
products_meta = {}  # key -> base cents
store_rows = []
for cat, sets in SETS.items():
    groups = []
    for name, abbr, pub in sets:
        gid += 1
        groups.append({"groupId": gid, "name": name, "abbreviation": abbr, "isSupplemental": False,
                       "publishedOn": pub + "T00:00:00", "modifiedOn": "2026-10-01T00:00:00", "categoryId": cat})
        prods, prices = [], []
        for s in (OP_SEALED if cat == 68 else SEALED):
            pid += 1
            nm = f"{name} {s}"
            prods.append({"productId": pid, "name": nm, "cleanName": nm, "groupId": gid, "categoryId": cat,
                          "imageUrl": f"https://tcgplayer-cdn.tcgplayer.com/product/{pid}_200w.jpg",
                          "url": f"https://www.tcgplayer.com/product/{pid}", "extendedData": []})
            basep = {"Booster Box": 22000, "Elite Trainer Box": 7500, "Booster Bundle": 4200,
                     "Sleeved Booster Pack": 700, "Booster Box Case": 130000, "3 Pack Blister": 1900,
                     "Mini Tin": 1500, "Booster Pack": 650}[s] * random.uniform(.6, 1.8)
            products_meta[f"{pid}:Normal"] = basep
            if s in ("Elite Trainer Box", "Booster Bundle") and len(store_rows) < 8:
                store_rows.append({"handle": nm.lower().replace(" ", "-"), "title": nm,
                                   "images": [{"src": f"https://cdn.shopify.com/s/files/1/x/files/{pid}_in_1000x1000_abc.jpg"}],
                                   "variants": [{"available": True, "price": f"{basep/100*1.05:.2f}"}]})
        cards = OP_CARDS if cat == 68 else CARDS
        for i in range(40):
            pid += 1
            nm = f"{random.choice(cards)} - {i + 1:03d}/{len(cards) * 15}"
            rar = random.choices(RAR, [1, 3, 4, 6, 20])[0]
            prods.append({"productId": pid, "name": nm, "cleanName": nm, "groupId": gid, "categoryId": cat,
                          "imageUrl": f"https://tcgplayer-cdn.tcgplayer.com/product/{pid}_200w.jpg",
                          "url": f"https://www.tcgplayer.com/product/{pid}",
                          "extendedData": [{"name": "Number", "value": f"{i + 1:03d}"}, {"name": "Rarity", "value": rar}]})
            basep = {"Special Illustration Rare": 25000, "Illustration Rare": 3000, "Ultra Rare": 1500,
                     "Double Rare": 300, "Common": 25}[rar] * random.uniform(.3, 3)
            subs = ["Holofoil"] if rar != "Common" else ["Normal", "Reverse Holofoil"]
            for sub in subs:
                products_meta[f"{pid}:{sub}"] = basep * (1.6 if sub == "Reverse Holofoil" else 1)
        w(os.path.join(base, str(cat), str(gid), "products"), {"totalItems": len(prods), "success": True, "errors": [], "results": prods})
        rows = [{"productId": int(k.split(":")[0]), "lowPrice": None, "midPrice": None, "highPrice": None,
                 "marketPrice": None, "directLowPrice": None, "subTypeName": k.split(":")[1]}
                for k in products_meta if int(k.split(":")[0]) in {p["productId"] for p in prods}]
        w(os.path.join(base, str(cat), str(gid), "prices"), {"success": True, "errors": [], "results": rows})
    w(os.path.join(base, str(cat), "groups"), {"totalItems": len(groups), "success": True, "errors": [], "results": groups})

# synthetic history: random walk with a trend per item; today's prices written into the feed
trend = {k: random.gauss(0, 0.0012) for k in products_meta}
hist = {}
for k, b in products_meta.items():
    price = b
    series = []
    for d in range(400, -1, -1):
        price *= 1 + trend[k] + random.gauss(0, 0.012)
        series.append(max(price, 10))
    hist[k] = series

snap_dir = os.path.join(DATA_DIR, "snapshots")
os.makedirs(snap_dir, exist_ok=True)
for back in range(400, 0, -1):
    day = TODAY - timedelta(days=back)
    if back > 120 and day.weekday() != 0:
        continue
    snap = {k: int(round(v[400 - back])) for k, v in hist.items()}
    with gzip.open(os.path.join(snap_dir, f"{day.isoformat()}.json.gz"), "wt") as f:
        json.dump(snap, f)

# today's prices go into the fake feed (the pipeline downloads them)
for cat in SETS:
    for g in json.load(open(os.path.join(base, str(cat), "groups")))["results"]:
        p = os.path.join(base, str(cat), str(g["groupId"]), "prices")
        d = json.load(open(p))
        for r in d["results"]:
            r["marketPrice"] = round(hist[f"{r['productId']}:{r['subTypeName']}"][-1] / 100, 2)
        w(p, d)

w(os.path.join(ROOT, "store", "products.json"), {"products": store_rows})
print(f"fixture: {len(products_meta)} price keys, {len(store_rows)} store products")
