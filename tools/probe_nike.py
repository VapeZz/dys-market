import json, re, urllib.request
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36", "Accept": "application/json"}
def get(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20); return r.status, r.read()
    except Exception as e:
        return getattr(e, "code", str(e)), b""
DC = "d9a5bc42-4b9c-4976-858a-f159cf99c647"
codes = [r["c"] for r in json.load(open("site/sneakers.json"))["releases"] if r.get("c") and re.match(r"^[A-Z0-9]{6}-\d{3}$", r["c"])]
found = {}
for i in range(0, len(codes), 20):
    batch = codes[i:i+20]
    u = f"https://api.nike.com/product_feed/threads/v2?count=50&filter=marketplace(US)&filter=language(en)&filter=channelId({DC})&filter=productInfo.merchProduct.styleColor({','.join(batch)})"
    s, b = get(u)
    d = json.loads(b or b"{}")
    for o in d.get("objects", []):
        txt = json.dumps(o)
        for pi in o.get("productInfo", []):
            sc = pi.get("merchProduct", {}).get("styleColor")
            urls = re.findall(r'https://static\.nike\.com/a/images/[^"]+', json.dumps(pi)) or re.findall(r'https://static\.nike\.com/a/images/[^"]+', txt)
            if sc: found[sc] = urls[:2]
first = list(found.items())[:2]
print(f"lookup: {len(codes)} codes, found {len(found)}: {','.join(found)}")
print("sample", json.dumps(first)[:900])
s, b = get(first[0][1][0]) if first and first[0][1] else (None, b"")
print("img fetch", s, len(b))
