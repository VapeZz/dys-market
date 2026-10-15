"""Add products straight to the Shopify store (run by the "Add to store" workflow).

ITEMS env var: JSON list from the importer page, each one of
    {"id": 692947, "sub": "Normal", "qty": 2, "cost": 54.00}   new product
    {"handle": "pitch-black-elite-trainer-box", "qty": 3}       restock existing
STATUS env var: ACTIVE or DRAFT.

Titles, descriptions, images and prices come from our own catalog and today's
market price, never from the request, so the page can only choose WHAT to add.
"""
import json
import os
import re
import sys

import config
import snapshots
import tcgcsv
from shopify_api import Shopify
from shopify_sync import market_cents, printing_code

MAX_ITEMS = 300
GAME = {
    "pokemon": ("The Pokémon Company", ["Pokemon"], "Pokémon Sealed", "Pokémon Single", "Pokémon"),
    "pokemon-jp": ("The Pokémon Company", ["Pokemon", "Pokemon Japan"], "Pokémon Japan Sealed", "Pokémon Japan Single", "Pokémon Japan"),
    "one-piece": ("Bandai", ["One Piece"], "One Piece Sealed", "One Piece Single", "One Piece"),
}

LOOKUP_Q = """query($q: String!, $h: String!) {
  bySku: productVariants(first: 1, query: $q) { nodes { id inventoryItem { id } product { title } } }
  byHandle: productByHandle(handle: $h) { id title variants(first: 1) { nodes { inventoryItem { id } } } }
}"""
SETUP_Q = """{
  locations(first: 10) { nodes { id name isActive } }
  publications(first: 20) { nodes { id name } }
}"""
SET_M = """mutation($input: ProductSetInput!) {
  productSet(input: $input, synchronous: true) {
    product { id handle }
    userErrors { field message }
  }
}"""
PUBLISH_M = """mutation($id: ID!, $pub: ID!) {
  publishablePublish(id: $id, input: [{publicationId: $pub}]) { userErrors { field message } }
}"""
ADJUST_M = """mutation($input: InventoryAdjustQuantitiesInput!) {
  inventoryAdjustQuantities(input: $input) { userErrors { field message } }
}"""


def slug(text):
    t = text.lower().replace("é", "e").replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:200]


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_product(pid, sub, products, groups, price, qty, cost, location, status):
    p = products[pid]
    g = groups.get(str(p["g"]), {})
    vendor, game_tags, sealed_type, single_type, game_label = GAME.get(p["k"], GAME["pokemon"])
    sealed = p["t"] == "s"
    title = p["n"] if sealed or sub == "Normal" else f"{p['n']} ({sub})"
    set_name = g.get("name", "")
    code = "" if sealed else printing_code(sub)
    sku = f"TCGP-{pid}" + (f"-{code}" if code else "")
    if sealed:
        desc = (f"<p>Factory-sealed {esc(title)} from the {esc(set_name)} set ({game_label}).</p>"
                "<p>All sealed product is sold factory sealed and ships from Las Vegas.</p>")
        seo = f"Shop factory-sealed {title} at Drive Your Style. Ships fast from Las Vegas."
    else:
        rarity = f" Rarity: {esc(p['r'])}." if p.get("r") else ""
        desc = (f"<p>{esc(title)} from {esc(set_name)} ({game_label}).{rarity}</p>"
                "<p>Condition: Near Mint. Ships sleeved and protected from Las Vegas.</p>")
        seo = f"Shop {title} ({set_name}), Near Mint, at Drive Your Style. Ships fast from Las Vegas."
    option = "Unopened" if sealed else "Near Mint"
    inv = {"tracked": True, "requiresShipping": True, "sku": sku}
    if cost:
        inv["cost"] = f"{cost:.2f}"
    return sku, {
        "title": title,
        "handle": slug(title),
        "descriptionHtml": desc,
        "vendor": vendor,
        "productType": sealed_type if sealed else single_type,
        "tags": game_tags + ["Sealed" if sealed else "Singles", "TCG"] + ([set_name] if set_name else []),
        "status": status,
        "seo": {"title": f"{title} | Drive Your Style", "description": seo[:320]},
        "productOptions": [{"name": "Condition", "values": [{"name": option}]}],
        "files": [{"originalSource": f"https://tcgplayer-cdn.tcgplayer.com/product/{pid}_in_1000x1000.jpg",
                   "contentType": "IMAGE", "alt": title}],
        "variants": [{
            "optionValues": [{"optionName": "Condition", "name": option}],
            "price": f"{price / 100:.2f}",
            "sku": sku,
            "taxable": True,
            "inventoryPolicy": "DENY",
            "inventoryItem": inv,
            "inventoryQuantities": [{"locationId": location, "name": "available", "quantity": qty}],
        }],
    }


def errors(payload):
    return payload.get("userErrors") or []


def main():
    items = json.loads(os.environ.get("ITEMS") or "[]")[:MAX_ITEMS]
    status = "DRAFT" if os.environ.get("STATUS", "").upper() == "DRAFT" else "ACTIVE"
    shop = os.environ.get("SHOPIFY_SHOP", "").strip()
    if not shop:
        sys.exit("Add the SHOPIFY_SHOP, SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET secrets first.")
    groups, products = tcgcsv.load_catalog()
    latest = snapshots.load(snapshots.available()[-1])
    api = Shopify(shop)
    setup = api.gql(SETUP_Q)
    location = next(l["id"] for l in setup["locations"]["nodes"] if l["isActive"])
    online = next((p["id"] for p in setup["publications"]["nodes"] if p["name"] == "Online Store"), None)

    added, restocked, problems = [], [], []

    def restock(inv_item, qty, label):
        if qty <= 0:
            return
        e = errors(api.gql(ADJUST_M, {"input": {"name": "available", "reason": "received", "changes": [
            {"inventoryItemId": inv_item, "locationId": location, "delta": qty}]}})["inventoryAdjustQuantities"])
        (problems.append(f"{label}: {e}") if e else restocked.append(f"{label} (+{qty})"))

    for it in items:
        qty = max(0, min(999, int(it.get("qty") or 0)))
        if it.get("handle"):  # restock something already in the store
            found = api.gql(LOOKUP_Q, {"q": "sku:__none__", "h": str(it["handle"])})["byHandle"]
            if not found or not found["variants"]["nodes"]:
                problems.append(f"{it['handle']}: not found in the store")
                continue
            restock(found["variants"]["nodes"][0]["inventoryItem"]["id"], qty, found["title"])
            continue

        pid, sub = str(it.get("id", "")), str(it.get("sub") or "Normal")
        if pid not in products:
            problems.append(f"{pid}: not in the catalog")
            continue
        price = market_cents(latest, pid, printing_code(sub) if products[pid]["t"] == "c" else "")
        if price is None:
            problems.append(f"{products[pid]['n']}: no market price today")
            continue
        cost = float(it["cost"]) if it.get("cost") not in (None, "") else None
        if cost and price < round(cost * 100):
            price = round(cost * 100)  # never list below what you paid
        sku, product = build_product(pid, sub, products, groups, price, qty, cost, location, status)

        existing = api.gql(LOOKUP_Q, {"q": f"sku:{sku}", "h": product["handle"]})
        if existing["bySku"]["nodes"]:  # already imported before: add stock instead of a duplicate
            v = existing["bySku"]["nodes"][0]
            restock(v["inventoryItem"]["id"], qty, v["product"]["title"])
            continue
        if existing["byHandle"]:
            product["handle"] = f"{product['handle']}-{pid}"
        out = api.gql(SET_M, {"input": product})["productSet"]
        if errors(out) or not out.get("product"):
            problems.append(f"{product['title']}: {errors(out)}")
            continue
        if online and status == "ACTIVE":
            e = errors(api.gql(PUBLISH_M, {"id": out["product"]["id"], "pub": online})["publishablePublish"])
            if e:
                problems.append(f"{product['title']}: added but not published ({e})")
        added.append(f"{product['title']} · ${price / 100:.2f} · qty {qty}")

    lines = [f"## Added {len(added)} · Restocked {len(restocked)} · Problems {len(problems)}", ""]
    lines += [f"- ✅ Added: {a}" for a in added] + [f"- ➕ Restocked: {r}" for r in restocked]
    lines += [f"- ⚠️ {p}" for p in problems]
    report = "\n".join(lines)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(report + "\n")
    if problems and not (added or restocked):
        sys.exit(1)


if __name__ == "__main__":
    main()
