"""eBay Finding API client for completed slab sales (PSA / BGS / CGC).

Requires an eBay Developer App ID (client ID), stored as the environment
variable EBAY_APP_ID.  Read-only searches need no OAuth token.

eBay Finding API docs:
  https://developer.ebay.com/devzone/finding/callref/findCompletedItems.html
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

FINDING_API = "https://svcs.ebay.com/services/search/FindingService/v1"
USER_AGENT = "DriveYourStyleMarket/1.0 (+https://driveyourstyle.net)"
PAUSE = 0.3   # seconds between requests

# Graders we track
GRADERS = ["PSA", "BGS", "CGC"]

# Max sold listings to pull per query (eBay page max = 100, max offset = 10000)
PAGE_SIZE = 100
MAX_PAGES = 5   # 500 sold comps per query — plenty for daily price signals


def _app_id():
    app_id = os.environ.get("EBAY_APP_ID", "").strip()
    if not app_id:
        raise RuntimeError(
            "EBAY_APP_ID environment variable not set. "
            "Get a free App ID at https://developer.ebay.com/."
        )
    return app_id


def _request(params, retries=3):
    base = {
        "OPERATION-NAME": "findCompletedItems",
        "SERVICE-VERSION": "1.13.0",
        "SECURITY-APPNAME": _app_id(),
        "RESPONSE-DATA-FORMAT": "JSON",
        "REST-PAYLOAD": "",
        "itemFilter(0).name": "SoldItemsOnly",
        "itemFilter(0).value": "true",
        "itemFilter(1).name": "ListingType",
        "itemFilter(1).value(0)": "Auction",
        "itemFilter(1).value(1)": "AuctionWithBIN",
        "itemFilter(1).value(2)": "FixedPrice",
        "sortOrder": "EndTimeSoonest",
        "paginationInput.entriesPerPage": str(PAGE_SIZE),
    }
    base.update(params)
    url = FINDING_API + "?" + urllib.parse.urlencode(base)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
            time.sleep(PAUSE)
            data = json.loads(body)
            # eBay wraps the real response in a key like "findCompletedItemsResponse"
            wrapper = next(iter(data.values()))
            if isinstance(wrapper, list):
                wrapper = wrapper[0]
            return wrapper
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
            last_err = err
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"eBay API failed after {retries} attempts: {last_err}")


def _val(obj, *keys):
    """Safely traverse a nested dict/list structure from eBay's JSON."""
    for k in keys:
        if obj is None:
            return None
        if isinstance(obj, list):
            obj = obj[0] if obj else None
        if isinstance(obj, dict):
            obj = obj.get(k)
        else:
            return None
    if isinstance(obj, list):
        return obj[0] if obj else None
    return obj


def search_slabs(query, max_pages=MAX_PAGES, log=print):
    """Fetch completed slab sales matching `query`.

    Returns a list of dicts:
        {title, sold_price, currency, end_time, item_id, condition, url}
    """
    results = []
    for page in range(1, max_pages + 1):
        params = {
            "keywords": query,
            "paginationInput.pageNumber": str(page),
            "categoryId": "183454",   # Sports Trading Cards → also covers TCG slabs
        }
        try:
            resp = _request(params)
        except RuntimeError as err:
            log(f"ebay: query={query!r} page={page} error: {err}")
            break

        ack = _val(resp, "ack")
        if ack not in ("Success", "Warning"):
            log(f"ebay: ack={ack} for query={query!r}")
            break

        items = _val(resp, "searchResult", "item") or []
        if not isinstance(items, list):
            items = [items]

        for item in items:
            price_raw = _val(item, "sellingStatus", "convertedCurrentPrice")
            if price_raw is None:
                price_raw = _val(item, "sellingStatus", "currentPrice")
            try:
                price_usd = float(_val(price_raw, "__value__") or 0)
                currency = _val(price_raw, "@currencyId") or "USD"
            except (TypeError, ValueError):
                continue
            if price_usd <= 0:
                continue

            results.append({
                "title": _val(item, "title") or "",
                "sold_price": round(price_usd, 2),
                "currency": currency,
                "end_time": _val(item, "listingInfo", "endTime") or "",
                "item_id": _val(item, "itemId") or "",
                "condition": _val(item, "condition", "conditionDisplayName") or "",
                "url": _val(item, "viewItemURL") or "",
            })

        total_pages = int(_val(resp, "paginationOutput", "totalPages") or 1)
        if page >= total_pages:
            break

    return results


def fetch_slab_comps(card_name, set_name, graders=None, log=print):
    """Pull sold comps for a card across all graders.

    Returns dict keyed by grader:
        {"PSA": [...], "BGS": [...], "CGC": [...]}
    """
    if graders is None:
        graders = GRADERS
    comps = {}
    for grader in graders:
        query = f"{grader} {card_name} {set_name}".strip()
        sales = search_slabs(query, log=log)
        comps[grader] = sales
        log(f"ebay: {grader} '{card_name}' ({set_name}) → {len(sales)} comps")
    return comps


def summarize_comps(sales):
    """Return median, mean, low, high, count from a list of sale dicts."""
    prices = sorted(s["sold_price"] for s in sales if s["sold_price"] > 0)
    if not prices:
        return None
    n = len(prices)
    mid = n // 2
    median = (prices[mid] if n % 2 else (prices[mid - 1] + prices[mid]) / 2)
    return {
        "count": n,
        "median": round(median, 2),
        "mean": round(sum(prices) / n, 2),
        "low": prices[0],
        "high": prices[-1],
        "as_of": datetime.now(timezone.utc).date().isoformat(),
    }
