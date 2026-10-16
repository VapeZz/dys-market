import json, re, urllib.request, os, subprocess
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36", "Accept": "*/*"}
def get(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20); return r.status, r.headers.get("content-type"), r.read()
    except Exception as e:
        return getattr(e, "code", str(e)), None, b""
DC = "d9a5bc42-4b9c-4976-858a-f159cf99c647"
u = f"https://api.nike.com/product_feed/threads/v2?count=50&filter=marketplace(US)&filter=language(en)&filter=channelId({DC})&filter=productInfo.merchProduct.styleColor(CT8013-105,HQ7978-001,IO8766-800)"
d = json.loads(get(u)[2])
os.makedirs("probe-out", exist_ok=True)
for o in d["objects"]:
    for pi in o["productInfo"]:
        sc = pi["merchProduct"]["styleColor"]
        urls = re.findall(r'https://static\.nike\.com/a/images/[^"]+', json.dumps(pi))
        nodes = [n.get("properties", {}).get("squarishURL") for n in o.get("publishedContent", {}).get("nodes", [])[:1]]
        print(sc, "n_urls", len(urls), "node0", (nodes[0] or "")[:60])
        for i, x in enumerate(urls[:3]):
            s, ct, b = get(x); open(f"probe-out/{sc}-{i}.png", "wb").write(b)
        small = urls[0].replace("/t_default/", "/t_default/f_auto,q_auto,w_500/") if urls else ""
        s, ct, b = get(small); print(sc, "small", s, ct, len(b)); open(f"probe-out/{sc}-small", "wb").write(b)
        s, ct, b = get(urls[0]); print(sc, "full", s, ct, len(b))
