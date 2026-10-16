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
        available = any(v.get("available") for v in variants)
        prices = [float(v["price"]) for v in variants if (v.get("available") or not available) and v.get("price")]
        entry = {
            "u": f"{config.STORE_URL}/products/{row['handle']}",
            "p": int(round(min(prices) * 100)) if prices else None,
            "a": available,
        }
        pid = None
        for v in variants:  # products added by our importer carry SKU TCGP-<id>
            m = re.match(r"^TCGP-(\d+)", v.get("sku") or "")
            if m and m.group(1) in products:
                pid = m.group(1)
                break
        if pid is None and row.get("handle") in overrides:
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
    log(f"store: {len(stock)} products matched to market data ({sum(1 for v in stock.values() if v['a'])} in stock)")
    return stock


STYLE_CODE = re.compile(r"Style code:\s*([A-Z0-9]{2,8}-?[A-Z0-9]{2,4})", re.I)


def sneaker_rows(store_rows):
    """Sneakers (product type Shoes/Sneakers) for the sneakers page and the store widget. "a" = in stock."""
    out = []
    for row in store_rows:
        if (row.get("product_type") or "").strip().lower() not in ("shoes", "sneakers", "shoe", "sneaker"):
            continue
        all_v = row.get("variants") or []
        variants = [v for v in all_v if v.get("available")] or all_v
        if not variants:
            continue
        body = re.sub(r"<[^>]+>", " ", row.get("body_html") or "")
        code = STYLE_CODE.search(body)
        imgs = row.get("images") or []
        out.append({
            "n": row.get("title"),
            "u": f"{config.STORE_URL}/products/{row['handle']}",
            "p": int(round(min(float(v["price"]) for v in variants) * 100)),
            "s": ", ".join(v.get("title") for v in variants if v.get("title") and v.get("title") != "Default Title"),
            "c": code.group(1).upper() if code else None,
            "im": imgs[0].get("src") if imgs else None,
            "at": (row.get("published_at") or row.get("created_at") or "")[:10],
            "a": any(v.get("available") for v in all_v),
        })
    out.sort(key=lambda r: r["at"], reverse=True)
    return out
