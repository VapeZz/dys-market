"""Picture for every button on the link-in-bio page (site/links.html), refreshed each night.

    python tools/links_thumbs.py SITE_DIR

Writes SITE_DIR/assets/links/<key>.jpg (600x400):
  shop      store products (sealed from data/stock.json + a sneaker from data/sneakers-stock.json)
  grade     cover of the newest "Grade it?" carousel (social-grade/latest.json)
  sneakers  cover of this week's sneaker drops carousel (social-sneakers/latest.json)
  report    cover of this week's trending cards carousel (social/latest.json)
  worth, sell, centering, collection   phone screenshots of those pages
Anything that can't be made keeps last night's picture (or the button simply shows no picture).
"""
import functools
import http.server
import io
import json
import os
import socketserver
import sys
import threading
import urllib.request

from PIL import Image

W, H = 600, 400
PAGES = {"worth": "index.html", "sell": "sell.html", "centering": "centering.html", "collection": "collection.html", "supplies": "supplies.html"}
FEEDS = {"grade": "social-grade", "sneakers": "social-sneakers", "report": "social"}


def fit(im, out, top=0.0, y0=0):
    """Crop to 3:2 (from y0 px, then `top` fraction further down) and save."""
    im = im.convert("RGB")
    if y0:
        im = im.crop((0, y0, im.size[0], im.size[1]))
    w, h = im.size
    ch = int(w * H / W)
    if ch > h:   # wider than 3:2: crop the sides
        cw = int(h * W / H)
        im = im.crop(((w - cw) // 2, 0, (w - cw) // 2 + cw, h))
    else:
        y = int((h - ch) * top)
        im = im.crop((0, y, w, y + ch))
    im.resize((W, H), Image.LANCZOS).save(out, "JPEG", quality=82, optimize=True)


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (DriveYourStyleMarket)"}), timeout=30).read()


def feed_cover(site, folder):
    try:
        d = json.load(open(os.path.join(site, folder, "latest.json")))
        rel = d["slides"][0].split("market.driveyourstyle.net/", 1)[1]
        return Image.open(os.path.join(site, rel))
    except Exception:
        return None


def shop(site, out, page):
    imgs = []
    try:
        for r in [x for x in json.load(open(os.path.join(site, "data", "stock.json"))) if x.get("t") == "s"][:2]:
            imgs.append(f"https://tcgplayer-cdn.tcgplayer.com/product/{r['id']}_in_1000x1000.jpg")
    except Exception:
        pass
    try:
        s = [x for x in json.load(open(os.path.join(site, "data", "sneakers-stock.json"))) if x.get("im") and x.get("a", True)]
        if s:
            imgs.insert(1, s[0]["im"])
    except Exception:
        pass
    if not imgs:
        return False
    tiles = "".join(f"<div class='t'><img src='{u}'></div>" for u in imgs[:3])
    page.set_viewport_size({"width": W, "height": H})
    page.set_content(f"""<html><body style="margin:0;width:{W}px;height:{H}px;overflow:hidden;background:radial-gradient(500px 300px at 90% 0%,rgba(124,92,255,.45),transparent 60%),#0b0d14;display:flex;align-items:center;justify-content:center;gap:14px">
<style>.t{{width:176px;height:300px;border-radius:18px;background:#fff;display:flex;align-items:center;justify-content:center;overflow:hidden;box-shadow:0 18px 40px rgba(0,0,0,.5)}}.t img{{max-width:92%;max-height:92%;object-fit:contain}}</style>{tiles}</body></html>""", wait_until="networkidle")
    page.screenshot(path=out, type="jpeg", quality=82)
    return True


def main(argv):
    site = argv[0]
    out_dir = os.path.join(site, "assets", "links")
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for key, folder in FEEDS.items():
        im = feed_cover(site, folder)
        if im:
            fit(im, os.path.join(out_dir, f"{key}.jpg"))
            made.append(key)
    from playwright.sync_api import sync_playwright
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=site)
    h.log_message = lambda *a: None
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    root = f"http://127.0.0.1:{srv.server_address[1]}/"
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 390, "height": 760}, device_scale_factor=2)
        for key, path in PAGES.items():
            try:
                pg.goto(root + path, wait_until="networkidle", timeout=45000)
                pg.wait_for_timeout(1500)
                pg.add_style_tag(content=".tabbar,.tabs,nav.tabs,.ticker,#ticker,.cookie,.toast{display:none!important}")
                fit(Image.open(io.BytesIO(pg.screenshot(type="png"))), os.path.join(out_dir, f"{key}.jpg"), y0=2 * 62)   # skip the site header
                made.append(key)
            except Exception as e:
                print(f"links thumbs: {key} failed: {e}")
        try:
            if shop(site, os.path.join(out_dir, "shop.jpg"), b.new_page()):
                made.append("shop")
        except Exception as e:
            print(f"links thumbs: shop failed: {e}")
        b.close()
    srv.shutdown()
    print(f"links thumbs: {len(made)} pictures ({', '.join(made)})")


if __name__ == "__main__":
    main(sys.argv[1:])
