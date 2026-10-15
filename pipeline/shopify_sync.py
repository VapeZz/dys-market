"""Nightly price sync: set Shopify prices to today's TCGplayer market price.

Only touches variants whose SKU starts with "TCGP-" (products added with the
importer page). SKU format: TCGP-<tcgplayer product id>[-<printing code>].

Credentials (GitHub Actions secrets):
    SHOPIFY_SHOP           e.g. s11bjx-1e.myshopify.com
    SHOPIFY_CLIENT_ID      from the Dev Dashboard app
    SHOPIFY_CLIENT_SECRET  from the Dev Dashboard app
(or SHOPIFY_ADMIN_TOKEN instead of the client id/secret pair)

    python pipeline/shopify_sync.py            # update prices
    python pipeline/shopify_sync.py --dry-run  # show what would change
"""
import json
import os
import re
import sys
import time

import config
import snapshots
from shopify_api import Shopify

SKU_PREFIX = "TCGP-"
# Safety net. A price is HELD (left as is) instead of changed when:
#  - market dropped more than MAX_DROP since the current price (one night), or
#  - market jumped more than MAX_RISE (usually bad data).
# Prices also never go below the item's "Cost per item" in Shopify.
MAX_DROP = float(os.environ.get("SYNC_MAX_DROP", "0.15"))
MAX_RISE = float(os.environ.get("SYNC_MAX_RISE", "0.50"))

PRINTING_CODES = {"Normal": "", "Holofoil": "H", "Reverse Holofoil": "RH"}


def printing_code(sub):
    if sub in PRINTING_CODES:
        return PRINTING_CODES[sub]
    return re.sub(r"[^A-Za-z0-9]", "", sub).upper()[:12]


def parse_sku(sku):
    m = re.match(r"^TCGP-(\d+)(?:-([A-Z0-9]+))?$", (sku or "").strip())
    return (m.group(1), m.group(2) or "") if m else (None, None)


def market_cents(latest, pid, code):
    keys = [k for k in latest if k.startswith(pid + ":")]
    for k in keys:
        if printing_code(k.split(":", 1)[1]) == code:
            return latest[k]
    if not code and len(keys) == 1:
        return latest[keys[0]]
    return None


def decide(have, market, cost=None):
    """Return (new_price_cents or None, note). None means leave the price alone."""
    target, note = market, ""
    if cost and target < cost:
        target, note = cost, "at your cost (market is lower)"
    if target == have:
        return None, "unchanged"
    if have > 0:
        move = (target - have) / have
        if move < -MAX_DROP:
            return None, f"held: market dropped {-move:.0%} (limit {MAX_DROP:.0%})"
        if move > MAX_RISE:
            return None, f"held: market jumped {move:.0%} (limit {MAX_RISE:.0%})"
    return target, note


VARIANTS_Q = """query($after: String) {
  productVariants(first: 250, after: $after, query: "sku:TCGP-*") {
    nodes { id sku price product { id title } inventoryItem { unitCost { amount } } }
    pageInfo { hasNextPage endCursor }
  }
}"""

UPDATE_M = """mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) {
    userErrors { field message }
  }
}"""


def main(argv):
    shop = os.environ.get("SHOPIFY_SHOP", "").strip()
    if not shop:
        print("sync: SHOPIFY_SHOP not set; skipping")
        return
    days = snapshots.available()
    if not days:
        print("sync: no price snapshots; skipping")
        return
    latest = snapshots.load(days[-1])
    api = Shopify(shop)
    dry = "--dry-run" in argv

    variants, after = [], None
    while True:
        data = api.gql(VARIANTS_Q, {"after": after})["productVariants"]
        variants += [v for v in data["nodes"] if (v.get("sku") or "").startswith(SKU_PREFIX)]
        if not data["pageInfo"]["hasNextPage"]:
            break
        after = data["pageInfo"]["endCursor"]

    by_product, unchanged, missing, skipped, floored, held = {}, 0, [], [], 0, []
    for v in variants:
        pid, code = parse_sku(v["sku"])
        market = market_cents(latest, pid, code) if pid else None
        if market is None:
            missing.append(v["sku"])
            continue
        have = int(round(float(v["price"]) * 100))
        cost_amt = ((v.get("inventoryItem") or {}).get("unitCost") or {}).get("amount")
        cost = int(round(float(cost_amt) * 100)) if cost_amt else None
        new, note = decide(have, market, cost)
        if new is None:
            if note == "unchanged":
                unchanged += 1
            else:
                skipped.append(f"{v['product']['title']}: ${have / 100:.2f}, market ${market / 100:.2f} -> {note}")
                held.append({"t": v["product"]["title"], "pid": v["product"]["id"].rsplit("/", 1)[-1],
                             "have": have, "mkt": market, "why": note.split(": ", 1)[-1]})
            continue
        floored += note.startswith("at your cost")
        by_product.setdefault(v["product"]["id"], []).append({"id": v["id"], "price": f"{new / 100:.2f}"})

    changed = sum(len(x) for x in by_product.values())
    print(f"sync: {len(variants)} synced variants, {changed} updated ({floored} kept at cost), {unchanged} unchanged, "
          f"{len(missing)} without a market price, {len(skipped)} held by the safety net")
    for s in skipped:
        print("  held:", s)
    if dry:
        return
    os.makedirs(config.OUT_DIR, exist_ok=True)
    with open(os.path.join(config.OUT_DIR, "sync-report.json"), "w", encoding="utf-8") as f:
        json.dump({"day": days[-1], "synced": len(variants), "updated": changed, "held": held}, f, ensure_ascii=False)
    for product_id, vs in by_product.items():
        errs = api.gql(UPDATE_M, {"productId": product_id, "variants": vs})["productVariantsBulkUpdate"]["userErrors"]
        if errs:
            print(f"  error on {product_id}: {errs}")
        time.sleep(0.3)
    with open(os.path.join(config.DATA_DIR, "sync-log.txt"), "a", encoding="utf-8") as f:
        f.write(f"{days[-1]}: {changed} updated, {unchanged} unchanged, {len(missing)} no price, {len(skipped)} held\n")


if __name__ == "__main__":
    main(sys.argv[1:])
