"""Product photos with the background removed (for the store's frameless look).

    LIST='[{"p": product id, "h": handle, "m": media id, "u": image url}, ...]' python tools/cutouts.py OUT_DIR

For each photo: download it, remove the background with rembg (isnet-general-use), trim to the product,
add a small margin and save OUT_DIR/<handle>.png. Photos that already have a transparent background are
only trimmed. Writes OUT_DIR/report.json and contact sheets (original on white next to the cut-out on
the store's dark background) so every result can be checked before it goes on a product.
"""
import io
import json
import os
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFont
import pillow_avif  # noqa: F401  (registers AVIF)
from rembg import new_session, remove

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
items = json.loads(os.environ["LIST"])
sess = new_session("isnet-general-use")
report, pairs = [], []
# Packaged products (official shots on pure white): the AI model keeps the artwork's characters and drops
# the box, so for these only the white around the product is removed (white connected to the photo's edge).
WHITE_KINDS = {"Sealed", "OnePiece"}


def white_out(rgba):
    import numpy as np
    from scipy import ndimage
    a = np.asarray(rgba.convert("RGB")).astype(np.int16)
    lo, hi = a.min(axis=2), a.max(axis=2)
    whiteish = (lo >= 243) & (hi - lo <= 12)
    lab, _ = ndimage.label(whiteish)
    edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    bg = np.isin(lab, edge[edge > 0])
    fg = ~bg
    fg = ndimage.binary_opening(fg, iterations=1)            # drop specks
    fg = ndimage.binary_fill_holes(fg) | (fg & ~bg)          # keep white areas inside the product
    # soft edge without a white halo: shrink one pixel, then feather
    core = ndimage.binary_erosion(fg, iterations=1)
    alpha = ndimage.gaussian_filter(core.astype(np.float32), 0.7)
    out = np.dstack([a.astype(np.uint8), (np.clip(alpha, 0, 1) * 255).astype(np.uint8)])
    return Image.fromarray(out, "RGBA")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (dys-market cutouts)", "Accept": "image/png,image/jpeg,image/webp,image/avif,*/*"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


for it in items:
    try:
        src = Image.open(io.BytesIO(get(it["u"] + ("&" if "?" in it["u"] else "?") + "width=1400")))
        src.load()
        rgba = src.convert("RGBA")
        alpha = rgba.getchannel("A")
        clear = sum(1 for v in alpha.getdata() if v < 250) / (rgba.width * rgba.height)
        if clear > 0.05:
            cut, how = rgba, "already transparent"
        elif it.get("k") in WHITE_KINDS:
            cut, how = white_out(rgba), "white background removed"
        else:
            cut, how = remove(rgba, session=sess, post_process_mask=True), "removed"
        mask = cut.getchannel("A").point(lambda v: 255 if v > 16 else 0)
        box = mask.getbbox()
        if not box:
            report.append({**it, "ok": False, "why": "nothing left after removal"})
            continue
        cut = cut.crop(box)
        kept = sum(1 for v in mask.crop(box).getdata() if v) / (cut.width * cut.height)
        pad = int(max(cut.size) * 0.04)
        canvas = Image.new("RGBA", (cut.width + 2 * pad, cut.height + 2 * pad), (0, 0, 0, 0))
        canvas.paste(cut, (pad, pad))
        canvas.thumbnail((1200, 1200))
        path = os.path.join(out, it["h"] + ".png")
        canvas.save(path, optimize=True)
        # how much of the original frame the product fills: tiny = probably cut too much
        share = (box[2] - box[0]) * (box[3] - box[1]) / (rgba.width * rgba.height)
        report.append({**it, "ok": True, "how": how, "fill": round(kept, 2), "area": round(share, 2), "file": it["h"] + ".png"})
        pairs.append((it["h"], rgba, canvas))
        print(f"{it['h']}: {how}, fill {kept:.2f}, area {share:.2f}")
    except Exception as e:  # keep going; the report says what failed
        report.append({**it, "ok": False, "why": str(e)[:200]})
        print(f"{it['h']}: FAILED {e}")

json.dump(report, open(os.path.join(out, "report.json"), "w"), indent=1)

# contact sheets: 4 pairs per row, 5 rows per sheet
T = 300
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
except OSError:
    font = ImageFont.load_default()
per = 20
for s in range(0, len(pairs), per):
    chunk = pairs[s:s + per]
    rows = (len(chunk) + 3) // 4
    sheet = Image.new("RGB", (4 * (2 * T + 30), rows * (T + 40)), (40, 42, 50))
    d = ImageDraw.Draw(sheet)
    for i, (h, a, b) in enumerate(chunk):
        x, y = (i % 4) * (2 * T + 30), (i // 4) * (T + 40)
        left = Image.new("RGB", (T, T), (255, 255, 255)); ac = a.copy(); ac.thumbnail((T, T)); left.paste(ac, ((T - ac.width) // 2, (T - ac.height) // 2), ac)
        right = Image.new("RGB", (T, T), (11, 13, 20)); bc = b.copy(); bc.thumbnail((T, T)); right.paste(bc, ((T - bc.width) // 2, (T - bc.height) // 2), bc)
        sheet.paste(left, (x + 5, y + 5)); sheet.paste(right, (x + T + 10, y + 5))
        d.text((x + 6, y + T + 10), f"{s + i + 1}. {h[:56]}", fill=(230, 230, 230), font=font)
    sheet.save(os.path.join(out, f"sheet-{s // per + 1}.jpg"), quality=82)
print(f"cutouts: {sum(1 for r in report if r.get('ok'))} of {len(report)} done")
