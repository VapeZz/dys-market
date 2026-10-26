"""Image fingerprints for the card scanner (site/assets/scan.js matches a phone photo against these).

    python tools/card_prints.py SITE_DIR STORE_DIR [--max N]

For every Pokémon and One Piece card worth $1+ it downloads the TCGplayer image once, trims the white padding,
and stores a 256-bit difference hash of the card (inside the outer border). Cached in STORE_DIR/prints.json
(product id -> hex), so each night only new cards are fetched. Writes SITE_DIR/data/prints.bin:
records of [uint32 little-endian product id][32 bytes hash], sorted by id.

The hash must be computed exactly the same way in scan.js (fingerprint()):
card -> 250x350, grayscale (0.299/0.587/0.114), crop x 12..238, y 12..338, area-average down to 17x16,
bit = pixel[x+1] > pixel[x] for x in 0..15, row by row, most significant bit first in each byte.
"""
import concurrent.futures as cf
import io
import json
import os
import struct
import sys
import urllib.request

import numpy as np
from PIL import Image, ImageChops

GAMES = ("pokemon", "one-piece")
MIN_PRICE = 100   # cents


def trim(img):
    img = img.convert("RGB")
    bg = Image.new("RGB", img.size, (255, 255, 255))
    box = ImageChops.difference(img, bg).convert("L").point(lambda v: 255 if v > 18 else 0).getbbox()
    return img.crop(box) if box else img


def area_resize(g, w, h):
    """exact area average (what scan.js does), g = 2-D float array"""
    H, W = g.shape
    xs, ys = np.linspace(0, W, w + 1), np.linspace(0, H, h + 1)
    I = np.zeros((H + 1, W + 1))
    I[1:, 1:] = g.cumsum(0).cumsum(1)

    def at(y, x):   # integral image at fractional coordinates (bilinear between grid points)
        y0, x0 = int(np.floor(y)), int(np.floor(x))
        y1, x1 = min(y0 + 1, H), min(x0 + 1, W)
        fy, fx = y - y0, x - x0
        return (I[y0, x0] * (1 - fy) * (1 - fx) + I[y0, x1] * (1 - fy) * fx + I[y1, x0] * fy * (1 - fx) + I[y1, x1] * fy * fx)
    out = np.zeros((h, w))
    for j in range(h):
        for i in range(w):
            s = at(ys[j + 1], xs[i + 1]) - at(ys[j], xs[i + 1]) - at(ys[j + 1], xs[i]) + at(ys[j], xs[i])
            out[j, i] = s / ((ys[j + 1] - ys[j]) * (xs[i + 1] - xs[i]))
    return out


def fingerprint(card):
    a = np.asarray(card.convert("RGB").resize((250, 350), Image.BILINEAR), dtype=np.float64)
    g = a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114
    small = area_resize(g[12:338, 12:238], 17, 16)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return np.packbits(bits).tobytes().hex()


def fetch(pid):
    try:
        req = urllib.request.Request(f"https://tcgplayer-cdn.tcgplayer.com/product/{pid}_200w.jpg", headers={"User-Agent": "Mozilla/5.0 (DriveYourStyleMarket)"})
        img = Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=25).read()))
        return pid, fingerprint(trim(img))
    except Exception:
        return pid, None


def main(argv):
    site, store = argv[0], argv[1]
    mx = int(argv[argv.index("--max") + 1]) if "--max" in argv else 30000
    os.makedirs(store, exist_ok=True)
    cpath = os.path.join(store, "prints.json")
    try:
        cache = json.load(open(cpath))
    except (OSError, ValueError):
        cache = {}
    d = os.path.join(site, "data")
    rows = json.load(open(os.path.join(d, "search-all.json")))["rows"]
    groups = json.load(open(os.path.join(d, "meta.json")))["groups"]
    want = []
    seen = set()
    for r in sorted(rows, key=lambda r: -(r[4] or 0)):
        if r[3] != "c" or not r[4] or r[4] < MIN_PRICE or r[0] in seen or groups.get(str(r[2]), ["", ""])[1] not in GAMES:
            continue
        seen.add(r[0])
        want.append(r[0])
    todo = [p for p in want if str(p) not in cache][:mx]
    got = 0
    with cf.ThreadPoolExecutor(16) as ex:
        for pid, h in ex.map(fetch, todo):
            if h:
                cache[str(pid)] = h
                got += 1
    json.dump(cache, open(cpath, "w"), separators=(",", ":"))
    keep = sorted(int(p) for p in cache if int(p) in seen)
    with open(os.path.join(d, "prints.bin"), "wb") as f:
        for pid in keep:
            f.write(struct.pack("<I", pid) + bytes.fromhex(cache[str(pid)]))
    print(f"prints: {got} new, {len(keep)} cards in the scanner ({len(want) - len(keep)} still to fetch)")


if __name__ == "__main__":
    main(sys.argv[1:])
