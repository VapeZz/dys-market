"""Match Drive Your Style Shopify products to TCGplayer product IDs.

Products synced by Synq use TCGplayer images named like
"692947_in_1000x1000_....jpg" — the leading number is the TCGplayer
product ID, so that's the primary match. Titles are a fallback, and
data/store-overrides.json can force a match:
    {"<shopify handle>": <tcgplayer productId>}
"""
import json
import os
import re
import urllib.request

import config

IMG_ID = re.compile(r"/(\d{4,8})_in_\d+x\d+")


def norm(s):
    s = s.lower().replace("pokémon", "pokemon").replace("&", "and")
    s = re.sub(r"\b(pokemon tcg|tcg|the pokemon company)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def fetch_store_products(log=print):
    out, page = [], 1
    while page <= 20:
        url = f"{config.STORE_URL}/products.json?limit=250&page={page}"
        req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if "/password" in resp.geturl():
                    log("store: storefront is password-protected; skipping in-stock badges")
                    return []
                rows = json.loads(resp.read().decode("utf-8")).get("products", [])
        except Exception as err:  # store unreachable shouldn't break the build
            log(f"store: could not read products ({err}); skipping in-stock badges")
            return []
        if not rows:
            break
        out.extend(rows)
        page += 1
    log(f"store: {len(out)} products")
    return out


def match_in_stock(products, store_rows, log=print):
    overrides = {}
    path = os.path.join(config.DATA_DIR, "store-overrides.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            overrides = json.load(f)

    by_name = {}
    for pid, p in products.items():
        if p["t"] == "s":
            by_name.setdefault(norm(p["n"]), pid)

    stock = {}
    for row in store_rows:
        variants = row.get("variants") or []
        if not any(v.get("available") for v in variants):
            continue
        prices = [float(v["price"]) for v in variants if v.get("available") and v.get("price")]
        entry = {
            "u": f"{config.STORE_URL}/products/{row['handle']}",
            "p": int(round(min(prices) * 100)) if prices else None,
        }
        pid = None
        if row.get("handle") in overrides:
            pid = str(overrides[row["handle"]])
        if pid is None:
            for img in row.get("images") or []:
                m = IMG_ID.search(img.get("src", ""))
                if m and m.group(1) in products:
                    pid = m.group(1)
                    break
        if pid is None:
            pid = by_name.get(norm(row.get("title", "")))
        if pid:
            stock[pid] = entry
    log(f"store: {len(stock)} products matched to market data")
    return stock
