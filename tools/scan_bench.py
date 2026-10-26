"""Benchmark the card scanner (site/assets/scan.js) on synthetic phone photos of real cards.

    python tools/scan_bench.py PAGES_DIR SCAN_JS [SCAN_JS ...] [--n 50] [--out dir]

PAGES_DIR is a checkout of the published site (gh-pages) for the data files. Each SCAN_JS is tested on the
same photos. Photos are made from TCGplayer card images: the card on a dark surface, slightly rotated and
tilted, with blur, noise, uneven light and JPEG compression, cropped like the scanner's camera frame.
Prints accuracy (right card first), "sure" answers that were right/wrong, and seconds per scan.
"""
import base64
import functools
import http.server
import io
import json
import os
import random
import re
import socketserver
import sys
import threading
import time
import urllib.request

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


def pick(pages, n, seed=7):
    rows = json.load(open(os.path.join(pages, "data", "search-all.json")))["rows"]
    groups = json.load(open(os.path.join(pages, "data", "meta.json")))["groups"]
    rnd = random.Random(seed)
    poke = [r for r in rows if r[3] == "c" and r[4] and r[4] >= 300 and r[5] and groups.get(str(r[2]), ["", ""])[1] == "pokemon"]
    op = [r for r in rows if r[3] == "c" and r[4] and r[4] >= 300 and r[5] and groups.get(str(r[2]), ["", ""])[1] == "one-piece"]
    modern = [r for r in poke if re.match(r"^(SV|ME|SWSH)", groups[str(r[2])][0])]
    rnd.shuffle(modern), rnd.shuffle(poke), rnd.shuffle(op)
    k = n // 10
    out, seen = [], set()
    for r in modern[:n - 3 * k] + poke[:2 * k] + op[:k]:
        if r[0] not in seen:
            seen.add(r[0])
            out.append(r)
    return out[:n], groups


def photo(card, rnd, hard=False):
    """A phone-ish photo of the card, framed like the scanner's capture box (card ~88% of the frame)."""
    card = card.convert("RGB")
    # TCGplayer images are padded squares: trim the white border to the card
    bg = Image.new("RGB", card.size, (255, 255, 255))
    from PIL import ImageChops
    box = ImageChops.difference(card, bg).convert("L").point(lambda v: 255 if v > 18 else 0).getbbox() or (0, 0, *card.size)
    card = card.crop(box).resize((630, 880))
    W, H = 760, 1020
    shade = rnd.randint(18, 60)
    canvas = Image.new("RGB", (W + 400, H + 400), (shade, shade, shade + rnd.randint(0, 12)))
    d = ImageDraw.Draw(canvas)
    for _ in range(300):                                          # a bit of surface texture
        x, y = rnd.randint(0, W + 399), rnd.randint(0, H + 399)
        v = shade + rnd.randint(-10, 10)
        d.point((x, y), fill=(v, v, v))
    canvas.paste(card, (200 + (W - 630) // 2 + rnd.randint(-25, 25), 200 + (H - 880) // 2 + rnd.randint(-25, 25)))
    if hard:                                                      # glare and a sleeve's haze
        ov = Image.new("L", canvas.size, 0)
        od = ImageDraw.Draw(ov)
        for _ in range(rnd.randint(1, 2)):
            cx, cy, rx, ry = rnd.randint(250, W + 150), rnd.randint(250, H + 150), rnd.randint(60, 200), rnd.randint(40, 140)
            od.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=rnd.randint(120, 220))
        ov = ov.filter(ImageFilter.GaussianBlur(40))
        canvas = Image.composite(Image.new("RGB", canvas.size, (255, 255, 250)), canvas, ov)
        if rnd.random() < 0.5:
            canvas = Image.blend(canvas, Image.new("RGB", canvas.size, (200, 200, 205)), 0.12)
        tint = Image.new("RGB", canvas.size, rnd.choice([(255, 220, 170), (190, 210, 255), (255, 255, 255)]))
        canvas = Image.blend(canvas, tint, 0.12)
    canvas = canvas.rotate(rnd.uniform(-9, 9) if hard else rnd.uniform(-4, 4), resample=Image.BICUBIC, fillcolor=(shade, shade, shade))
    # mild keystone (phone not perfectly flat)
    w, h = canvas.size
    dx = rnd.uniform(-0.08, 0.08) * w if hard else rnd.uniform(-0.035, 0.035) * w
    canvas = canvas.transform((w, h), Image.QUAD, (dx, 0, -dx * .3, h, w + dx * .3, h, w - dx, 0), resample=Image.BICUBIC)
    canvas = canvas.crop((200, 200, 200 + W, 200 + H))
    # light: brightness/contrast, a soft gradient, blur, noise, jpeg
    canvas = ImageEnhance.Brightness(canvas).enhance(rnd.uniform(0.75, 1.15))
    canvas = ImageEnhance.Contrast(canvas).enhance(rnd.uniform(0.8, 1.1))
    grad = Image.linear_gradient("L").resize((W, H)).rotate(rnd.choice([0, 90, 180, 270]))
    canvas = Image.composite(canvas, ImageEnhance.Brightness(canvas).enhance(0.8), grad)
    canvas = canvas.filter(ImageFilter.GaussianBlur(rnd.uniform(0.4, 1.3)))
    noise = Image.effect_noise((W, H), rnd.uniform(6, 14)).convert("RGB")
    canvas = Image.blend(canvas, noise, 0.06)
    canvas = canvas.resize((int(W * 1.4), int(H * 1.4)))           # roughly what the frame crop gives on a phone
    buf = io.BytesIO()
    canvas.save(buf, "JPEG", quality=rnd.randint(68, 85))
    return buf.getvalue()


def serve(d):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=d)
    h.log_message = lambda *a: None
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"


def main(argv):
    pages = argv[0]
    n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 50
    out = argv[argv.index("--out") + 1] if "--out" in argv else "bench-out"
    scripts = [a for a in argv[1:] if a.endswith(".js")]
    os.makedirs(out, exist_ok=True)
    cards, groups = pick(pages, n, seed=int(argv[argv.index("--seed") + 1]) if "--seed" in argv else 7)
    rnd = random.Random(11)
    shots = []
    for r in cards:
        try:
            req = urllib.request.Request(f"https://tcgplayer-cdn.tcgplayer.com/product/{r[0]}_in_1000x1000.jpg", headers={"User-Agent": "Mozilla/5.0"})
            img = Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=30).read()))
        except Exception as e:
            print(f"skip {r[0]}: {e}")
            continue
        jpg = photo(img, rnd, hard="--hard" in argv)
        open(os.path.join(out, f"{r[0]}.jpg"), "wb").write(jpg)
        shots.append((r, base64.b64encode(jpg).decode()))
    print(f"bench: {len(shots)} photos")
    srv, root = serve(pages)
    from playwright.sync_api import sync_playwright
    results = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for js in scripts:
            src = open(js, encoding="utf-8").read()
            if "window.dysScanFile" not in src:
                src = src.replace("window.dysScanMatch = match;", "window.dysScanMatch = match; window.dysScanFile = scanFile;")
            pg = b.new_page()
            pg.goto(root + "index.html", wait_until="domcontentloaded")
            pg.add_script_tag(content=src)
            ok = sure_ok = sure_bad = top3 = 0
            times, misses, dists = [], [], []
            for r, b64 in shots:
                t0 = time.time()
                res = pg.evaluate("""async (b64) => {
                    const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
                    const f = new File([bin], "card.jpg", {type: "image/jpeg"});
                    const out = await window.dysScanFile(f, {status() {}});
                    return {ids: out.list.slice(0, 3).map(x => x.r[0]), sure: out.sure, nums: out.nums, text: out.text.slice(0, 300), d: out.d || null};
                }""", b64)
                dt = time.time() - t0
                times.append(dt)
                dists.append([r[0], bool(res["ids"]) and res["ids"][0] == r[0], res["d"], res["sure"]])
                hit = bool(res["ids"]) and res["ids"][0] == r[0]
                ok += hit
                top3 += r[0] in res["ids"]
                if res["sure"]:
                    sure_ok += hit
                    sure_bad += not hit
                if not hit:
                    misses.append(f"{r[1]} ({r[5]}, {groups.get(str(r[2]), ['?'])[0]}) -> {res['ids'][:1]} nums={res['nums'][:3]}")
            name = os.path.basename(os.path.dirname(js)) + "/" + os.path.basename(js)
            results[name] = dict(n=len(shots), top1=ok, top3=top3, sure_ok=sure_ok, sure_bad=sure_bad,
                                 avg_s=round(sum(times) / max(1, len(times)), 2), first_s=round(times[0], 1) if times else None)
            print(f"::notice title=Scan bench {name}::right first {ok}/{len(shots)}, in top 3 {top3}, sure+right {sure_ok}, sure+WRONG {sure_bad}, avg {results[name]['avg_s']}s/scan (first {results[name]['first_s']}s)")
            results[name]["misses"] = misses
            results[name]["dists"] = dists
            pg.close()
        b.close()
    srv.shutdown()
    json.dump(results, open(os.path.join(out, "results.json"), "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1:])
