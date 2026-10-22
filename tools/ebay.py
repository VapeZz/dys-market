"""eBay Browse API helpers (application token, public listing data only).

    python tools/ebay.py probe            # check the keys work, print one search
Needs EBAY_CLIENT_ID and EBAY_CLIENT_SECRET (production keyset).
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.ebay.com"
CCG_SINGLES = "183454"      # Collectible Card Games > CCG Individual Cards
_tok = None


def token():
    global _tok
    if _tok:
        return _tok
    cid, sec = os.environ.get("EBAY_CLIENT_ID", "").strip(), os.environ.get("EBAY_CLIENT_SECRET", "").strip()
    if not cid or not sec:
        raise RuntimeError("EBAY_CLIENT_ID / EBAY_CLIENT_SECRET not set")
    req = urllib.request.Request(f"{API}/identity/v1/oauth2/token",
                                 data=urllib.parse.urlencode({"grant_type": "client_credentials",
                                                              "scope": "https://api.ebay.com/oauth/api_scope"}).encode(),
                                 headers={"Authorization": "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode(),
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        _tok = json.load(r)["access_token"]
    return _tok


def search(q, category=CCG_SINGLES, limit=50, filters="buyingOptions:{FIXED_PRICE},deliveryCountry:US,itemLocationCountry:US"):
    url = f"{API}/buy/browse/v1/item_summary/search?" + urllib.parse.urlencode(
        {"q": q, "category_ids": category, "limit": limit, "filter": filters, "sort": "price"})
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token(), "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


if __name__ == "__main__":
    if sys.argv[1:2] == ["probe"]:
        try:
            d = search("Umbreon ex 161/131 PSA 10")
            items = d.get("itemSummaries") or []
            prices = [float(i["price"]["value"]) for i in items if i.get("price")]
            print(f"::notice title=eBay probe::keys OK - {d.get('total', 0)} listings for 'Umbreon ex 161/131 PSA 10', "
                  f"cheapest ${min(prices):,.2f}" if prices else "::notice title=eBay probe::keys OK - no listings")
        except urllib.error.HTTPError as e:
            print(f"::error title=eBay probe::HTTP {e.code} {e.read()[:300]!r}")
            sys.exit(1)
        except Exception as e:
            print(f"::error title=eBay probe::{e}")
            sys.exit(1)
