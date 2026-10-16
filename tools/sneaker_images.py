"""Official product photos for the sneaker release calendar.

Looks up each Nike / Jordan style code on Nike.com's public product feed and keeps
the first product image (Nike's own side-profile shot). Found images are cached in
data/sneaker-images.json (saved on the data branch) so they stay after a shoe sells
out. Shoes Nike hasn't listed yet are retried every night. A release can also carry
its own "im" URL in site/sneakers.json, which always wins.

    python tools/sneaker_images.py
Writes site/data/sneaker-images.json = {"STYLE-CODE": image_url}.
"""
import json
import os
import re
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REL = os.path.join(ROOT, "site", "sneakers.json")
CACHE = os.path.join(ROOT, "data", "sneaker-images.json")
OUT = os.path.join(ROOT, "site", "data", "sneaker-images.json")
NIKE_CODE = re.compile(r"^[A-Z0-9]{6}-\d{3}$")
IMG = re.compile(r'https://static\.nike\.com/a/images/[^"\\]+')
CHANNEL = "d9a5bc42-4b9c-4976-858a-f159cf99c647"  # Nike.com
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
      "Accept": "application/json"}


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def small(url):
    return url.replace("/t_default/", "/t_default/f_auto,q_auto,w_500/", 1)


def lookup(codes):
    found = {}
    for i in range(0, len(codes), 20):
        batch = codes[i:i + 20]
        url = ("https://api.nike.com/product_feed/threads/v2?count=50&filter=marketplace(US)&filter=language(en)"
               f"&filter=channelId({CHANNEL})&filter=productInfo.merchProduct.styleColor({','.join(batch)})")
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as err:  # Nike being down shouldn't break the nightly build
            print(f"sneaker images: lookup failed ({err})")
            continue
        for obj in data.get("objects", []):
            for pi in obj.get("productInfo", []):
                code = (pi.get("merchProduct") or {}).get("styleColor")
                if code not in batch or code in found:
                    continue
                urls = IMG.findall(json.dumps(pi)) or IMG.findall(json.dumps(obj.get("publishedContent") or {}))
                if urls:
                    found[code] = small(urls[0])
    return found


def main():
    rel = load(REL, {}).get("releases", [])
    cache = load(CACHE, {})
    codes = [r["c"] for r in rel if r.get("c") and NIKE_CODE.match(r["c"]) and not r.get("im")]
    missing = [c for c in dict.fromkeys(codes) if c not in cache]
    new = lookup(missing) if missing else {}
    cache.update(new)
    keep = set(codes)
    cache = {k: v for k, v in cache.items() if k in keep}
    out = dict(cache)
    out.update({r["c"]: r["im"] for r in rel if r.get("c") and r.get("im")})
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=0)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"sneaker images: {len(out)} of {len(rel)} releases have a photo ({len(new)} new tonight)")


if __name__ == "__main__":
    main()
