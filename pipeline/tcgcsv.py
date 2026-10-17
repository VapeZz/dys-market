"""Download the catalog and today's prices from TCGCSV."""
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import config


def get_json(path, retries=3):
    url = f"{config.BASE_URL}/{path.lstrip('/')}"
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8")
            time.sleep(config.REQUEST_PAUSE_SECONDS)
            return json.loads(body)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
            last_err = err
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def get_text(path):
    url = f"{config.BASE_URL}/{path.lstrip('/')}"
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8").strip()


def source_date():
    """Date (YYYY-MM-DD, UTC) of the latest TCGCSV update."""
    raw = get_text("last-updated.txt")
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        stamp = datetime.now(timezone.utc)
    return stamp.astimezone(timezone.utc).date().isoformat()


def _results(payload):
    if not payload.get("success", True) and payload.get("errors"):
        raise RuntimeError(f"TCGCSV error: {payload['errors']}")
    return payload.get("results", [])


def is_card(product):
    names = {e.get("name") for e in product.get("extendedData") or []}
    return "Number" in names or "Rarity" in names


def _ext(product, key):
    for e in product.get("extendedData") or []:
        if e.get("name") == key:
            return e.get("value")
    return None


def compact_product(p, game_slug):
    card = is_card(p)
    item = {
        "n": p.get("name") or p.get("cleanName") or "",
        "g": p["groupId"],
        "k": game_slug,
        "t": "c" if card else "s",
    }
    if card:
        num = _ext(p, "Number")
        rar = _ext(p, "Rarity")
        if num:
            item["no"] = num
        if rar:
            item["r"] = rar
    presale = p.get("presaleInfo") or {}
    if presale.get("isPresale"):
        item["pre"] = (presale.get("releasedOn") or "")[:10]
    return item


def sync_catalog(log=print):
    """Refresh groups (sets) and product lists. Product lists are cached and
    only re-downloaded when a set changes or the cache is old."""
    cat_dir = os.path.join(config.DATA_DIR, "catalog")
    os.makedirs(cat_dir, exist_ok=True)
    groups_path = os.path.join(cat_dir, "groups.json")
    products_path = os.path.join(cat_dir, "products.json")
    state_path = os.path.join(cat_dir, "state.json")

    groups = _load(groups_path, {})
    products = _load(products_path, {})
    state = _load(state_path, {})
    now = datetime.now(timezone.utc)
    stale_before = (now - timedelta(days=config.CATALOG_REFRESH_DAYS)).isoformat()

    fresh_groups = {}
    for game in config.GAMES:
        cat = game["category"]
        for g in _results(get_json(f"tcgplayer/{cat}/groups")):
            gid = str(g["groupId"])
            fresh_groups[gid] = {
                "name": g.get("name", ""),
                "abbr": g.get("abbreviation") or "",
                "k": game["slug"],
                "cat": cat,
                "pub": (g.get("publishedOn") or "")[:10],
                "mod": g.get("modifiedOn") or "",
            }

    cached_groups = {v["g"] for v in products.values()}
    by_group = {}
    for pid, v in products.items():
        by_group.setdefault(v["g"], []).append(pid)

    refreshed = 0
    for gid, g in fresh_groups.items():
        prev = state.get(gid, {})
        needs = (
            prev.get("mod") != g["mod"]
            or prev.get("synced", "") < stale_before
            or (int(gid) not in cached_groups and gid not in state)
        )
        if not needs:
            continue
        rows = _results(get_json(f"tcgplayer/{g['cat']}/{gid}/products"))
        for pid in by_group.get(int(gid), []):
            products.pop(pid, None)
        for p in rows:
            products[str(p["productId"])] = compact_product(p, g["k"])
        state[gid] = {"mod": g["mod"], "synced": now.isoformat()}
        refreshed += 1
    log(f"catalog: {len(fresh_groups)} sets, {refreshed} refreshed, {len(products)} products")

    _save(groups_path, fresh_groups)
    _save(products_path, products)
    _save(state_path, state)
    return fresh_groups, products


def load_catalog():
    cat_dir = os.path.join(config.DATA_DIR, "catalog")
    return (_load(os.path.join(cat_dir, "groups.json"), {}),
            _load(os.path.join(cat_dir, "products.json"), {}))


def fetch_prices(groups, log=print):
    """Return {"productId:subType": cents} for every set's market price."""
    snap, lows = {}, {}
    for i, (gid, g) in enumerate(groups.items()):
        for row in _results(get_json(f"tcgplayer/{g['cat']}/{gid}/prices")):
            add_price(snap, row, lows)
        if (i + 1) % 100 == 0:
            log(f"prices: {i + 1}/{len(groups)} sets")
    log(f"prices: {len(snap)} price points")
    fetch_prices.lows = lows   # lowest current listing per product (for the buyer dashboard)
    return snap


def add_price(snap, row, lows=None):
    if lows is not None:
        try:
            lo = int(round(float(row.get("lowPrice")) * 100))
            if lo > 0:
                lows[f"{row['productId']}:{row.get('subTypeName') or 'Normal'}"] = lo
        except (TypeError, ValueError):
            pass
    price = row.get("marketPrice")
    if price is None:
        return
    try:
        cents = int(round(float(price) * 100))
    except (TypeError, ValueError):
        return
    if cents <= 0:
        return
    sub = row.get("subTypeName") or "Normal"
    snap[f"{row['productId']}:{sub}"] = cents


def _load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def _save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
