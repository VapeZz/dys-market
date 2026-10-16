"""TikTok helpers shared by the social generators.

full_screen(page, slide_paths, out_dir): wraps 1080x1350 slides in a 1080x1920 frame
(brand bar on top, site on the bottom) so they fill a phone screen in TikTok photo mode.
"""
import os

from social import BASE, FONT_CSS

FRAME = """<div class="slide" style="height:1920px;padding:0">
<img src="file://{img}" style="position:absolute;top:170px;left:0;width:1080px;height:1350px;display:block">
<div style="position:absolute;top:1560px;left:0;right:0;text-align:center;font-family:'Barlow Condensed';font-weight:700;font-size:42px;letter-spacing:.06em;text-transform:uppercase;color:#d8d5cf">{foot}</div>
</div>"""
# TikTok covers roughly the top 150px (tabs) and the bottom ~380px (caption, buttons), so the slide sits above that.


def full_screen(page, slide_paths, out_dir, foot="Free card prices · market.driveyourstyle.net"):
    page.set_viewport_size({"width": 1080, "height": 1920})
    base = BASE.replace("height:1350px", "height:1920px")
    tmp = os.path.abspath(os.path.join(out_dir, "_tt.html"))
    outs = []
    for i, src in enumerate(slide_paths, 1):
        open(tmp, "w", encoding="utf-8").write(base % (FONT_CSS, FRAME.format(img=os.path.abspath(src), foot=foot)))
        page.goto("file://" + tmp, wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        out = os.path.join(out_dir, f"tt-{i}.jpg")
        page.screenshot(path=out, type="jpeg", quality=90)
        outs.append(out)
    os.remove(tmp)
    page.set_viewport_size({"width": 1080, "height": 1350})
    return outs
