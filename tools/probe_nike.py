import json, urllib.request
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36", "Accept": "application/json", "nike-api-caller-id": "nike:snkrs:web:1.0"}
def get(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20); return r.status, r.read()
    except Exception as e:
        return getattr(e, "code", str(e)), b""
SN, DC = "010794e5-35fe-4e32-aaff-cd2c74f15d9f", "d9a5bc42-4b9c-4976-858a-f159cf99c647"
B = "https://api.nike.com/product_feed/threads/v3/?count=50&filter=marketplace(US)&filter=language(en)"
tests = {
 "v3 snkrs all": f"{B}&filter=channelId({SN})",
 "v3 snkrs upcoming": f"{B}&filter=channelId({SN})&filter=upcoming(true)",
 "v2 snkrs upcoming": f"https://api.nike.com/product_feed/threads/v2/?count=50&filter=marketplace(US)&filter=language(en)&filter=channelId({SN})&filter=upcoming(true)",
 "v2 style snkrs": f"https://api.nike.com/product_feed/threads/v2?filter=marketplace(US)&filter=language(en)&filter=channelId({SN})&filter=productInfo.merchProduct.styleColor(IO6260-800)",
 "v2 style dotcom": f"https://api.nike.com/product_feed/threads/v2?filter=marketplace(US)&filter=language(en)&filter=channelId({DC})&filter=productInfo.merchProduct.styleColor(HV6474-601)",
 "v2 style dotcom AJ1": f"https://api.nike.com/product_feed/threads/v2?filter=marketplace(US)&filter=language(en)&filter=channelId({DC})&filter=productInfo.merchProduct.styleColor(HQ6998-600)",
}
for k, u in tests.items():
    s, b = get(u)
    try:
        d = json.loads(b); objs = d.get("objects", [])
        out = []
        for o in objs[:40]:
            for pi in o.get("productInfo", []):
                out.append((pi.get("merchProduct", {}).get("styleColor"), (pi.get("imageUrls") or {}).get("productImageUrl"), (pi.get("launchView") or {}).get("startEntryDate", "")[:10]))
        print(k, s, "objs", len(objs), "pages", d.get("pages"), "|", "; ".join(f"{a} {c} {b2}" for a, b2, c in out[:6]))
        print(k, "codes:", ",".join(sorted({a for a, _, _ in out if a}))[:900])
    except Exception as e:
        print(k, s, "raw", b[:200])
