import json, urllib.request, hashlib, sys
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36", "Accept": "*/*"}
def get(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20)
        b = r.read(); return r.status, r.headers.get("content-type"), b
    except Exception as e:
        return getattr(e, "code", str(e)), None, b""
u = "https://api.nike.com/product_feed/threads/v3/?anchor=0&count=50&filter=marketplace(US)&filter=language(en)&filter=channelId(010794e5-35fe-4e32-aaff-cd2c74f15d9f)&filter=upcoming(true)&filter=exclusiveAccess(true,false)&sort=effectiveStartSellDateAsc"
s, ct, b = get(u); print("feed", s, ct, len(b))
try:
    d = json.loads(b); objs = d.get("objects", []); print("objects", len(objs), list(d.keys()))
    for o in objs[:3]:
        for pi in o.get("productInfo", [])[:1]:
            print(pi.get("merchProduct", {}).get("styleColor"), pi.get("imageUrls"), pi.get("launchView", {}).get("startEntryDate"))
        print(json.dumps(o.get("publishedContent", {}).get("properties", {}))[:300])
except Exception as e: print("parse", e, b[:200])
for code in ["IO6260-800", "CT8012-900", "HQ7978-001", "DD1391-100", "ZZ0000-000", "IX8180-001"]:
    sc = code.replace("-", "_")
    for t in [f"https://secure-images.nike.com/is/image/DotCom/{sc}", f"https://static.nike.com/a/images/t_default/{sc}.png"]:
        s, ct, b = get(t); print(code, t.split('/')[2], s, ct, len(b), hashlib.md5(b).hexdigest()[:8])
