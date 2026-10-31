"""Official product photos for the sneaker release calendar (every release needs one).

Sources, all brand-owned, tried in order for each style code:
  Nike / Jordan   Nike.com product feed, then the SNKRS launch feed, then Nike's image server by style code
  New Balance     New Balance's image server (nb.scene7.com) by style code
  Vans            Vans' image server (assets.vans.com) by style code
  ASICS           ASICS' image server (images.asics.com) by style code
  adidas          adidas.com product API by article number
A URL only counts when it really returns a product photo (an image, big enough, and not the server's
"no image" placeholder). Found images are cached in data/sneaker-images.json (saved on the data branch)
so they stay after a shoe sells out; misses are retried every night. A release can also carry its own
"im" URL in site/sneakers.json (used for collabs no brand server has), which always wins.

    python tools/sneaker_images.py [--rel site/sneakers.json] [--report] [--add "CODE=url CODE=url"]
Writes site/data/sneaker-images.json = {"STYLE-CODE": image_url}. --report prints one annotation per brand
with what's still missing.
"""
import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REL = os.path.join(ROOT, "site", "sneakers.json")
CACHE = os.path.join(ROOT, "data", "sneaker-images.json")
MANUAL = os.path.join(ROOT, "data", "sneaker-images-manual.json")   # {"CODE": url} official photos added by hand (collabs)
OUT = os.path.join(ROOT, "site", "data", "sneaker-images.json")
NIKE_CODE = re.compile(r"^[A-Z0-9]{6}-\d{3}$")
IMG = re.compile(r'https://static\.nike\.com/a/images/[^"\\]+')
CHANNELS = {"nike.com": "d9a5bc42-4b9c-4976-858a-f159cf99c647", "snkrs": "010794e5-35fe-4e32-aaff-cd2c74f89d61"}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
      "Accept": "application/json,image/avif,image/webp,image/*,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}
_placeholder = {}


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def small(url):
    return url.replace("/t_default/", "/t_default/f_auto,q_auto,w_500/", 1)


def fetch(url, timeout=25):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except Exception as e:
        return getattr(e, "code", 0) or 0, "", b""


def real_image(url, host_key):
    """True when url serves an actual photo: an image of 6 KB+ that isn't the server's placeholder."""
    st, ct, body = fetch(url)
    if st != 200 or not ct.startswith("image/") or len(body) < 6000:
        return False
    if host_key not in _placeholder:   # what the server sends for a code that doesn't exist
        bogus = url.replace(host_key.split("|")[1], "ZZ9999-999") if "|" in host_key else None
        _placeholder[host_key] = hashlib.md5(fetch(bogus)[2]).hexdigest() if bogus else None
    return hashlib.md5(body).hexdigest() != _placeholder[host_key]


def nike_feed(codes, channel):
    found = {}
    for i in range(0, len(codes), 20):
        batch = codes[i:i + 20]
        url = ("https://api.nike.com/product_feed/threads/v2?count=50&filter=marketplace(US)&filter=language(en)"
               f"&filter=channelId({channel})&filter=productInfo.merchProduct.styleColor({','.join(batch)})")
        st, _, body = fetch(url, 30)
        if st != 200:
            print(f"sneaker images: Nike feed {st}")
            continue
        try:
            data = json.loads(body.decode("utf-8"))
        except ValueError:
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


def by_code(code, brand):
    """Brand image servers keyed by style code. Returns the first URL that serves a real photo."""
    c_ = code.replace("-", "_")
    cands = []
    if brand in ("Nike", "Jordan") and NIKE_CODE.match(code):
        cands = [(f"https://secure-images.nike.com/is/image/DotCom/{c_}_A_PREM?wid=1000&hei=1000&fmt=jpg", "nike|" + c_),
                 (f"https://secure-images.nike.com/is/image/DotCom/{c_}?wid=1000&hei=1000&fmt=jpg", "nike2|" + c_)]
    elif brand == "New Balance":
        lc = code.lower()
        cands = [(f"https://nb.scene7.com/is/image/NB/{lc}_nb_02_i?$pdpflexf2$&wid=1000&hei=1000", "nb|" + lc),
                 (f"https://nb.scene7.com/is/image/NB/{lc}_nb_05_i?$pdpflexf2$&wid=1000&hei=1000", "nb5|" + lc)]
    elif brand == "Vans":
        cands = [(f"https://assets.vans.com/images/t_img/c_fill,g_center,f_auto,h_1000,w_1000/dpr_2.0/v1/{code}-HERO.jpg", "vans|" + code)]
    elif brand == "ASICS":
        cands = [(f"https://images.asics.com/is/image/asics/{c_}_SR_RT_GLB?$zoom$", "asics|" + c_),
                 (f"https://images.asics.com/is/image/asics/{c_}_SR_RT_AJP?$zoom$", "asics2|" + c_)]
    elif brand == "adidas":
        st, _, body = fetch(f"https://www.adidas.com/api/products/{code}", 25)
        if st == 200:
            try:
                views = json.loads(body.decode("utf-8")).get("view_list") or []
                side = [v["image_url"] for v in views if v.get("image_url") and "side" in (v.get("type") or "").lower()]
                pick = (side or [v["image_url"] for v in views if v.get("image_url")] or [None])[0]
                if pick:
                    return pick
            except ValueError:
                pass
    for url, key in cands:
        if real_image(url, key):
            return url
    return None


def main(argv):
    rel_path = argv[argv.index("--rel") + 1] if "--rel" in argv else REL
    rel = load(rel_path, {}).get("releases", [])
    cache = load(CACHE, {})
    have = set(cache) | set(load(MANUAL, {}))
    todo = [r for r in rel if r.get("c") and not r.get("im") and r["c"] not in have]
    new = {}
    nike = [r["c"] for r in todo if NIKE_CODE.match(r["c"]) and r.get("b") in ("Nike", "Jordan")]
    for ch in ("nike.com", "snkrs"):
        left = [c for c in dict.fromkeys(nike) if c not in new]
        if left:
            new.update(nike_feed(left, CHANNELS[ch]))
    for r in todo:
        if r["c"] in new:
            continue
        url = by_code(r["c"], r.get("b"))
        if url:
            new[r["c"]] = url
    cache.update(new)
    keep = {r["c"] for r in rel if r.get("c")}
    cache = {k: v for k, v in cache.items() if k in keep}
    manual = load(MANUAL, {})
    if "--add" in argv:   # "CODE=url CODE=url": keep only URLs that really serve a photo
        for pair in argv[argv.index("--add") + 1].split():
            code, _, url = pair.partition("=")
            st, ct, body = fetch(url)
            if st == 200 and ct.startswith("image/") and len(body) >= 6000:
                manual[code.strip().upper()] = url
                print(f"sneaker images: added {code}")
            else:
                print(f"::warning title=Sneaker photo rejected::{code} {st} {ct} {len(body)} bytes")
        with open(MANUAL, "w", encoding="utf-8") as f:
            json.dump(manual, f, indent=0)
    out = dict(cache)
    out.update(manual)
    out.update({r["c"]: r["im"] for r in rel if r.get("c") and r.get("im")})
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=0)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    has = lambda r: bool(r.get("im") or (r.get("c") and r["c"] in out))
    missing = [r for r in rel if not has(r)]
    print(f"sneaker images: {len(rel) - len(missing)} of {len(rel)} releases have a photo ({len(new)} new tonight)")
    if "--report" in argv:
        by = {}
        for r in missing:
            by.setdefault(r.get("b") or "?", []).append(f"{r['d'][5:]} {r.get('c') or '-'} {r['n'][:38]}")
        for b, rows in sorted(by.items(), key=lambda kv: -len(kv[1])):
            print(f"::warning title=No photo: {b} ({len(rows)})::" + " ; ".join(rows)[:3500])


if __name__ == "__main__":
    main(sys.argv[1:])
