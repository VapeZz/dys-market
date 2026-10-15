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
import urllib.request

import config
import snapshots

API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2026-01")
SKU_PREFIX = "TCGP-"
# Skip a price move bigger than this in one night (bad data protection).
MAX_CHANGE = float(os.environ.get("SYNC_MAX_CHANGE", "0.5"))

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


class Shopify:
    def __init__(self, shop):
        self.shop = shop
        self.token = os.environ.get("SHOPIFY_ADMIN_TOKEN") or self._client_credentials()

    def _post(self, url, body, headers):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())

    def _client_credentials(self):
        cid, secret = os.environ.get("SHOPIFY_CLIENT_ID"), os.environ.get("SHOPIFY_CLIENT_SECRET")
        if not (cid and secret):
            print("sync: no Shopify credentials set; skipping")
            raise SystemExit(0)
        out = self._post(f"https://{self.shop}/admin/oauth/access_token",
                         {"grant_type": "client_credentials", "client_id": cid, "client_secret": secret}, {})
        return out["access_token"]

    def gql(self, query, variables=None):
        for attempt in range(4):
            out = self._post(f"https://{self.shop}/admin/api/{API_VERSION}/graphql.json",
                             {"query": query, "variables": variables or {}}, {"X-Shopify-Access-Token": self.token})
            errs = out.get("errors")
            if errs and any("THROTTLED" in json.dumps(e) for e in errs):
                time.sleep(2 * (attempt + 1))
                continue
            if errs:
                raise RuntimeError(f"Shopify error: {errs}")
            return out["data"]
        raise RuntimeError("Shopify: throttled too many times")


VARIANTS_Q = """query($after: String) {
  productVariants(first: 250, after: $after, query: "sku:TCGP-*") {
    nodes { id sku price product { id title } }
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

    by_product, unchanged, missing, skipped = {}, 0, [], []
    for v in variants:
        pid, code = parse_sku(v["sku"])
        want = market_cents(latest, pid, code) if pid else None
        if want is None:
            missing.append(v["sku"])
            continue
        have = int(round(float(v["price"]) * 100))
        if have == want:
            unchanged += 1
            continue
        if have > 0 and abs(want - have) / have > MAX_CHANGE:
            skipped.append(f"{v['product']['title']} ({v['sku']}): ${have / 100:.2f} -> ${want / 100:.2f}")
            continue
        by_product.setdefault(v["product"]["id"], []).append({"id": v["id"], "price": f"{want / 100:.2f}"})

    changed = sum(len(x) for x in by_product.values())
    print(f"sync: {len(variants)} synced variants, {changed} to update, {unchanged} already at market, "
          f"{len(missing)} without a market price, {len(skipped)} skipped (moved more than {MAX_CHANGE:.0%})")
    for s in skipped:
        print("  skipped:", s)
    if dry:
        return
    for product_id, vs in by_product.items():
        errs = api.gql(UPDATE_M, {"productId": product_id, "variants": vs})["productVariantsBulkUpdate"]["userErrors"]
        if errs:
            print(f"  error on {product_id}: {errs}")
        time.sleep(0.3)
    with open(os.path.join(config.DATA_DIR, "sync-log.txt"), "a", encoding="utf-8") as f:
        f.write(f"{days[-1]}: {changed} updated, {unchanged} unchanged, {len(missing)} no price, {len(skipped)} skipped\n")


if __name__ == "__main__":
    main(sys.argv[1:])
