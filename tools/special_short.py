"""One-off countdown Short: "The most expensive card in every TCG right now".

    python tools/special_short.py cards.json out_dir

cards.json: [{"id": productId, "name", "set", "game", "p": cents}, ...] ordered #N..#1.
Writes slide-1..N.jpg and short.mp4 (1080x1920).
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from social import BASE, FONT_CSS, LOGO, esc, img  # noqa: E402

B = BASE.replace("height:1350px", "height:1920px")
PAD = "padding:170px 80px 400px;align-items:center;text-align:center"


def money0(c):
    return f"${c / 100:,.0f}"


def bodies(cards):
    n = len(cards)
    fan = "".join(f'<div class="card" style="position:absolute;left:{110 + k * 130}px;top:{40 + abs(k - 2) * 26}px;width:330px;height:462px;'
                  f'transform:rotate({(k - 2) * 7}deg);z-index:{5 - abs(k - 2)}"><img src="{img(c["id"])}"></div>'
                  for k, c in enumerate(cards[:5]))
    out = [f"""<div class="slide" style="height:1920px;{PAD}">
<img src="file://{LOGO}" style="height:100px">
<div class="tag" style="margin-top:50px">TCG price check · {n} games</div>
<div style="margin-top:44px;font-family:'Barlow Condensed';font-weight:800;font-size:122px;line-height:.93;text-transform:uppercase">The most<br><span class="holo">expensive pull</span><br>in every TCG</div>
<div style="position:relative;width:1000px;height:600px;margin-top:40px">{fan}</div>
<div style="margin-top:auto;font-size:40px;color:#bdb9b2">Guess #1 before the end 👀</div></div>"""]
    for k, c in enumerate(cards):
        rank = n - k
        nm = c["name"]
        out.append(f"""<div class="slide" style="height:1920px;{PAD}">
<div style="display:flex;align-items:center;gap:28px"><div style="font-family:'Barlow Condensed';font-weight:800;font-size:150px;line-height:.9" class="{'holo' if rank == 1 else ''}">#{rank}</div>
<div class="tag" style="font-size:34px">{esc(c['game'])}</div></div>
<div class="card" style="margin-top:34px;width:500px;height:700px"><img src="{img(c['id'])}"></div>
<div style="margin-top:40px;font-family:'Barlow Condensed';font-weight:800;font-size:{66 if len(nm) < 30 else 54}px;line-height:1.02;text-transform:uppercase">{esc(nm)}</div>
<div style="margin-top:10px;font-size:34px;color:#bdb9b2">{esc(c['set'])}</div>
<div style="margin-top:26px;font-family:'Barlow Condensed';font-weight:800;font-size:150px;line-height:1;color:#3ee08f">{money0(c['p'])}</div></div>""")
    out.append(f"""<div class="slide" style="height:1920px;justify-content:center;{PAD}">
<img src="file://{LOGO}" style="height:200px">
<div style="margin-top:80px;font-family:'Barlow Condensed';font-weight:800;font-size:124px;line-height:.92;text-transform:uppercase">Which one<br><span class="holo">would you pull?</span></div>
<div style="margin-top:44px;font-size:42px;color:#d8d5cf;max-width:880px">Live prices on 70,000+ cards across 8 games. Check yours free:</div>
<div style="margin-top:60px;font-family:'Barlow Condensed';font-weight:700;font-size:62px;border:4px solid #f2f0eb;padding:18px 40px 14px">market.driveyourstyle.net</div>
<div style="margin-top:70px;font-size:30px;color:#9a968f">TCGplayer market prices, Oct 17 2026 · cards from booster sets</div></div>""")
    return out


def main(argv):
    cards = json.load(open(argv[0]))
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    paths = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1920})
        tmp = os.path.abspath(os.path.join(out, "_s.html"))
        for i, body in enumerate(bodies(cards), 1):
            open(tmp, "w", encoding="utf-8").write(B % (FONT_CSS, body))
            pg.goto("file://" + tmp, wait_until="networkidle")
            pg.evaluate("document.fonts.ready")
            path = os.path.join(out, f"slide-{i}.jpg")
            pg.screenshot(path=path, type="jpeg", quality=90)
            paths.append(path)
        b.close()
        os.remove(tmp)
    from tiktok import make_short
    print("short:", make_short(paths, os.path.join(out, "short.mp4"), per=3.0))


if __name__ == "__main__":
    main(sys.argv[1:])
