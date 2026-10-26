"""Experiment: can a small image fingerprint pick the right card from a phone photo?

    python tools/scan_hash_exp.py PAGES_DIR PHOTOS_DIR [--pool 1500]

PHOTOS_DIR holds <productId>.jpg phone-like photos (from the scan benchmark). The pool is those cards plus
random Pokémon / One Piece cards worth $1+. Prints top-1 / top-5 retrieval for a few fingerprint variants.
"""
import concurrent.futures as cf
import glob
import io
import json
import os
import random
import sys
import urllib.request

import numpy as np
from PIL import Image, ImageChops, ImageFilter


def trim(img):
    img = img.convert("RGB")
    bg = Image.new("RGB", img.size, (255, 255, 255))
    box = ImageChops.difference(img, bg).convert("L").point(lambda v: 255 if v > 18 else 0).getbbox()
    return img.crop(box) if box else img


def card_box(img):
    """same idea as scan.js cardBox: the card differs from the surface along the photo's edges"""
    W, H = img.size
    s = 200 / max(W, H)
    a = np.asarray(img.convert("RGB").resize((max(20, round(W * s)), max(20, round(H * s)))), dtype=np.int32)
    h, w, _ = a.shape
    m = max(2, round(min(w, h) * 0.03))
    edge = np.concatenate([a[:m].reshape(-1, 3), a[-m:].reshape(-1, 3), a[:, :m].reshape(-1, 3), a[:, -m:].reshape(-1, 3)])
    med = np.median(edge, axis=0)
    on = np.abs(a - med).sum(axis=2) > 60
    rows, cols = on.sum(axis=1), on.sum(axis=0)
    r = np.where(rows > w * 0.3)[0]
    c = np.where(cols > h * 0.3)[0]
    if not len(r) or not len(c):
        return img
    r0, r1, c0, c1 = r[0], r[-1], c[0], c[-1]
    bw, bh = (c1 - c0 + 1) / s, (r1 - r0 + 1) / s
    if bw * bh < W * H * 0.3 or not (0.55 < bw / bh < 0.9):
        return img
    return img.crop((int(c0 / s), int(r0 / s), int(c0 / s + bw), int(r0 / s + bh)))


def norm_card(img):
    return img.convert("RGB").resize((250, 350), Image.BILINEAR)


def dhash(g, w, h):
    a = np.asarray(g.resize((w + 1, h), Image.BILINEAR), dtype=np.float32)
    return (a[:, 1:] > a[:, :-1]).flatten()


def feats(card):
    c = norm_card(card)
    g = c.convert("L").filter(ImageFilter.GaussianBlur(1.2))
    inner = g.crop((12, 12, 238, 338))                      # skip the outer border (glare, crop error)
    art = g.crop((20, 40, 230, 175))
    col = np.asarray(c.crop((12, 12, 238, 338)).resize((4, 6), Image.BOX).convert("RGB"), dtype=np.float32).flatten() / 255
    return {"whole16": dhash(inner, 16, 16), "art16": dhash(art, 16, 12), "whole8": dhash(inner, 8, 8),
            "both": np.concatenate([dhash(inner, 16, 16), dhash(art, 16, 12)]), "col": col}


def fetch(pid):
    try:
        req = urllib.request.Request(f"https://tcgplayer-cdn.tcgplayer.com/product/{pid}_200w.jpg", headers={"User-Agent": "Mozilla/5.0"})
        return pid, Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=20).read()))
    except Exception:
        return pid, None


def main(argv):
    pages, photos = argv[0], argv[1]
    n = int(argv[argv.index("--pool") + 1]) if "--pool" in argv else 1500
    rows = json.load(open(os.path.join(pages, "data", "search-all.json")))["rows"]
    groups = json.load(open(os.path.join(pages, "data", "meta.json")))["groups"]
    shots = {int(os.path.basename(f)[:-4]): f for f in glob.glob(os.path.join(photos, "*.jpg"))}
    pool = [r[0] for r in rows if r[3] == "c" and r[4] and r[4] >= 100 and groups.get(str(r[2]), ["", ""])[1] in ("pokemon", "one-piece")]
    random.Random(3).shuffle(pool)
    ids = list(dict.fromkeys(list(shots) + pool[:n]))
    ref = {}
    with cf.ThreadPoolExecutor(16) as ex:
        for pid, img in ex.map(fetch, ids):
            if img is not None:
                ref[pid] = feats(trim(img))
    print(f"pool: {len(ref)} cards")
    keys = list(ref)
    for var in ["whole8", "whole16", "art16", "both", "both+col"]:
        top1 = top5 = 0
        for pid, f in shots.items():
            if pid not in ref:
                continue
            q = feats(card_box(Image.open(f)))
            if var == "both+col":
                M = np.stack([ref[k]["both"] for k in keys])
                d = (M != q["both"]).mean(axis=1)
                C = np.stack([ref[k]["col"] for k in keys])
                d = d + 0.5 * np.abs(C - q["col"]).mean(axis=1)
            else:
                M = np.stack([ref[k][var] for k in keys])
                d = (M != q[var]).mean(axis=1)
            order = np.argsort(d)
            rank = [keys[i] for i in order[:5]]
            top1 += rank[0] == pid
            top5 += pid in rank
        print(f"::notice title=fingerprint {var}::top1 {top1}/{len(shots)}  top5 {top5}/{len(shots)}  (pool {len(ref)})")


if __name__ == "__main__":
    main(sys.argv[1:])
