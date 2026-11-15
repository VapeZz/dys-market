"""One-off, read-only test: does eBay's official Browse API return PSA population for a PSA slab listing?

    python tools/ebay_pop_probe.py

eBay shows PSA population on graded card listings. This looks at what the API hands back for a few PSA
slab listings (the same API tools/psapop.py already uses to read cert numbers) and reports which fields
exist. It prints field names and the few values that bear on grading; it stores nothing.
Needs EBAY_CLIENT_ID and EBAY_CLIENT_SECRET.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ebay  # noqa: E402

QUERIES = ["Umbreon ex 161/131 PSA 10", "Charizard ex 199/165 PSA 10", "Pikachu ex 238/191 PSA 9"]
WORDS = re.compile(r"pop(ulation)?\b|census|higher|gem\s*rate|total\s*graded", re.I)
GRADE = re.compile(r"cert|grade|grader|pop|census", re.I)


def get(url, market="EBAY_US"):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + ebay.token(), "X-EBAY-C-MARKETPLACE-ID": market})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def walk(node, path=""):
    """(path, value) for every key or short text value that mentions population."""
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else k
            if WORDS.search(k):
                yield p, v if not isinstance(v, (dict, list)) else json.dumps(v)[:200]
            yield from walk(v, p)
    elif isinstance(node, list):
        for i, v in enumerate(node[:60]):
            yield from walk(v, f"{path}[{i}]")
    elif isinstance(node, str) and len(node) < 400 and WORDS.search(node) and not path.endswith(("description", "shortDescription", "title")):
        yield path, node


def main():
    report = []
    for q in QUERIES:
        try:
            d = ebay.search(q, filters="buyingOptions:{FIXED_PRICE|AUCTION}", limit=20)
        except urllib.error.HTTPError as e:
            report.append({"query": q, "error": f"search HTTP {e.code}"})
            continue
        items = [i for i in d.get("itemSummaries") or [] if "PSA" in (i.get("title") or "").upper()][:2]
        row = {"query": q, "listings found": d.get("total", 0), "summary fields": sorted((items[0] if items else {}).keys()), "items": []}
        for s in items:
            for fg in ("PRODUCT", "PRODUCT,ADDITIONAL_SELLER_DETAILS"):
                try:
                    full = get(f"{ebay.API}/buy/browse/v1/item/{urllib.parse.quote(s['itemId'])}?fieldgroups={fg}")
                    break
                except urllib.error.HTTPError as e:
                    full = {"_error": f"HTTP {e.code}"}
            aspects = full.get("localizedAspects") or []
            row["items"].append({
                "title": (full.get("title") or s.get("title") or "")[:90],
                "top-level fields": sorted(full.keys()),
                "condition": [full.get("condition"), full.get("conditionId")],
                "conditionDescriptors": full.get("conditionDescriptors"),
                "aspect names": [a.get("name") for a in aspects],
                "grading aspects": {a.get("name"): a.get("value") for a in aspects if GRADE.search(a.get("name") or "")},
                "product fields": sorted((full.get("product") or {}).keys()),
                "anything that mentions population": [[p, v] for p, v in walk(full)][:20],
            })
        report.append(row)
    print("=====EBAY-POP-PROBE-BEGIN=====")
    print(json.dumps(report, indent=1, ensure_ascii=False))
    print("=====EBAY-POP-PROBE-END=====")
    hits = sum(len(i["anything that mentions population"]) for r in report for i in r.get("items", []))
    n = sum(len(r.get("items", [])) for r in report)
    print(f"::notice title=eBay population probe::{n} PSA slab listings read; {hits} fields mention population")


if __name__ == "__main__":
    main()
