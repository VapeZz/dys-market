"""eBay store health check: active listings, item details, 30-day traffic and live comparable prices.

    python tools/ebay_store.py STORE OUT_FILE [PUBKEY_B64]

STORE holds the connected seller account (tools/ebay_user.py). The report holds private sales/traffic
numbers, so when PUBKEY_B64 (RSA public key, DER, base64) is given the JSON is encrypted to it
(RSA-OAEP wraps a random AES-256-GCM key) and only the key holder can read it.
"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ebay        # noqa: E402  (application token for comparable listings)
import ebay_user   # noqa: E402

NS = {"e": "urn:ebay:apis:eBLBaseComponents"}


def trading(tok, call, body):
    xml = f'<?xml version="1.0" encoding="utf-8"?><{call}Request xmlns="urn:ebay:apis:eBLBaseComponents">{body}</{call}Request>'
    req = urllib.request.Request("https://api.ebay.com/ws/api.dll", data=xml.encode(), headers={
        "X-EBAY-API-IAF-TOKEN": tok, "X-EBAY-API-CALL-NAME": call, "X-EBAY-API-SITEID": "0",
        "X-EBAY-API-COMPATIBILITY-LEVEL": "1225", "Content-Type": "text/xml"})
    with urllib.request.urlopen(req, timeout=60) as r:
        root = ET.fromstring(r.read())
    ack = root.findtext("e:Ack", namespaces=NS)
    if ack not in ("Success", "Warning"):
        errs = [e.findtext("e:LongMessage", namespaces=NS) for e in root.findall("e:Errors", NS)]
        raise RuntimeError(f"{call}: {ack} {errs}")
    return root


def t(el, path):
    x = el.find(path, NS)
    return x.text if x is not None else None


def active_listings(tok):
    out, page = [], 1
    while True:
        r = trading(tok, "GetMyeBaySelling", f"<ActiveList><Include>true</Include><IncludeWatchCount>true</IncludeWatchCount>"
                                             f"<Pagination><EntriesPerPage>200</EntriesPerPage><PageNumber>{page}</PageNumber></Pagination></ActiveList>"
                                             f"<SoldList><Include>true</Include><DurationInDays>60</DurationInDays></SoldList>")
        for it in r.findall(".//e:ActiveList/e:ItemArray/e:Item", NS):
            out.append(t(it, "e:ItemID"))
        pages = int(t(r, ".//e:ActiveList/e:PaginationResult/e:TotalNumberOfPages") or 1)
        sold = [{"title": t(x, ".//e:Item/e:Title"), "price": t(x, ".//e:TransactionPrice"), "date": t(x, ".//e:CreatedDate")}
                for x in r.findall(".//e:SoldList/e:OrderTransactionArray/e:OrderTransaction/e:Transaction", NS)]
        if page >= pages:
            return out, sold
        page += 1


def item_detail(tok, iid):
    r = trading(tok, "GetItem", f"<ItemID>{iid}</ItemID><DetailLevel>ReturnAll</DetailLevel><IncludeWatchCount>true</IncludeWatchCount><IncludeItemSpecifics>true</IncludeItemSpecifics>")
    it = r.find("e:Item", NS)
    specs = {nv.findtext("e:Name", namespaces=NS): [v.text for v in nv.findall("e:Value", NS)]
             for nv in it.findall("e:ItemSpecifics/e:NameValueList", NS)}
    sp = it.find("e:SellingStatus/e:CurrentPrice", NS)
    return {
        "id": iid, "title": t(it, "e:Title"), "price": float(sp.text) if sp is not None else None,
        "format": t(it, "e:ListingType"), "qty": int(t(it, "e:Quantity") or 0) - int(t(it, "e:SellingStatus/e:QuantitySold") or 0),
        "condition": t(it, "e:ConditionDisplayName"), "category": t(it, "e:PrimaryCategory/e:CategoryName"),
        "category_id": t(it, "e:PrimaryCategory/e:CategoryID"),
        "photos": len(it.findall("e:PictureDetails/e:PictureURL", NS)), "watchers": int(t(it, "e:WatchCount") or 0),
        "views": int(t(it, "e:HitCount") or 0), "start": t(it, "e:ListingDetails/e:StartTime"),
        "best_offer": t(it, "e:BestOfferDetails/e:BestOfferEnabled") == "true",
        "ship_free": any((s.findtext("e:FreeShipping", namespaces=NS) == "true") for s in it.findall("e:ShippingDetails/e:ShippingServiceOptions", NS)),
        "ship_cost": t(it, "e:ShippingDetails/e:ShippingServiceOptions/e:ShippingServiceCost"),
        "returns": t(it, "e:ReturnPolicy/e:ReturnsAcceptedOption"), "handling_days": t(it, "e:DispatchTimeMax"),
        "specifics": specs, "url": t(it, "e:ListingDetails/e:ViewItemURL"),
        "desc_len": len(re.sub(r"<[^>]+>", " ", t(it, "e:Description") or "").split()),
    }


def traffic(tok):
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=29)
    q = urllib.parse.urlencode({"dimension": "LISTING", "filter": f"marketplace_ids:{{EBAY_US}},date_range:[{start:%Y%m%d}..{end:%Y%m%d}]",
                                "metric": "LISTING_IMPRESSION_TOTAL,LISTING_VIEWS_TOTAL,CLICK_THROUGH_RATE,SALES_CONVERSION_RATE,TRANSACTION,LISTING_IMPRESSION_SEARCH_RESULTS_PAGE"})
    req = urllib.request.Request("https://api.ebay.com/sell/analytics/v1/traffic_report?" + q, headers={"Authorization": "Bearer " + tok})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.load(r)
    keys = [h["key"] for h in d.get("header", {}).get("metrics", [])]
    out = {}
    for rec in d.get("records", []):
        iid = rec["dimensionValues"][0]["value"]
        out[iid] = {k: (m.get("value") if isinstance(m, dict) else m) for k, m in zip(keys, rec.get("metricValues", []))}
    return {"from": str(start), "to": str(end), "listings": out}


def comps(item):
    """Live Buy It Now asks for the same shoe (style code if we have one, else the title), same size when known."""
    sp = item["specifics"]
    code = (sp.get("Style Code") or sp.get("Style Number") or sp.get("MPN") or [None])[0]
    size = (sp.get("US Shoe Size") or sp.get("US Shoe Size (Men's)") or sp.get("Size") or [None])[0]
    q = code or re.sub(r"\b(size|sz|men'?s|womens?|new|ds|brand|with box|og all)\b", " ", item["title"], flags=re.I)
    if size and code:
        q = f"{code} {size}"
    try:
        d = ebay.search(q, category=item["category_id"] or "", limit=50, filters="buyingOptions:{FIXED_PRICE},deliveryCountry:US")
    except Exception as e:
        return {"query": q, "error": str(e)}
    rows = []
    for it in d.get("itemSummaries") or []:
        if it.get("itemId", "").split("|")[1:2] == [item["id"]] or item["id"] in it.get("itemId", ""):
            continue
        try:
            p = float(it["price"]["value"]) + float(((it.get("shippingOptions") or [{}])[0].get("shippingCost") or {}).get("value") or 0)
        except (KeyError, ValueError, TypeError):
            continue
        rows.append({"p": round(p, 2), "title": it.get("title"), "cond": it.get("condition"), "seller_fb": (it.get("seller") or {}).get("feedbackScore")})
    rows.sort(key=lambda r: r["p"])
    return {"query": q, "size": size, "count": len(rows), "cheapest": rows[:8]}


def encrypt(obj, pub_b64):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    pub = serialization.load_der_public_key(base64.b64decode(pub_b64))
    k, iv = AESGCM.generate_key(256), os.urandom(12)
    wrapped = pub.encrypt(k, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    ct = AESGCM(k).encrypt(iv, json.dumps(obj).encode(), None)
    return json.dumps({"k": base64.b64encode(wrapped).decode(), "iv": base64.b64encode(iv).decode(), "ct": base64.b64encode(ct).decode()})


def main(argv):
    store, out = argv[0], argv[1]
    pub = argv[2] if len(argv) > 2 else ""
    tok = ebay_user.access_token(store)
    rep = {"made": date.today().isoformat(), "errors": []}
    try:
        ids, sold = active_listings(tok)
        rep["sold_60d"] = sold
    except Exception as e:
        ids, rep["sold_60d"] = [], []
        rep["errors"].append(f"listings: {e}")
    rep["listings"] = []
    for iid in ids:
        try:
            it = item_detail(tok, iid)
            it["comps"] = comps(it)
            rep["listings"].append(it)
        except Exception as e:
            rep["errors"].append(f"item {iid}: {e}")
    try:
        rep["traffic"] = traffic(tok)
    except urllib.error.HTTPError as e:
        rep["errors"].append(f"traffic: HTTP {e.code} {e.read()[:200]!r}")
    except Exception as e:
        rep["errors"].append(f"traffic: {e}")
    data = encrypt(rep, pub) if pub else json.dumps(rep)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    open(out, "w").write(data)
    print(f"::notice title=eBay store report::{len(rep['listings'])} active listings, {len(rep['sold_60d'])} sales in 60 days, "
          f"traffic {'ok' if 'traffic' in rep else 'missing'}, {len(rep['errors'])} errors{' (encrypted)' if pub else ''}")


if __name__ == "__main__":
    main(sys.argv[1:])
