"""Story slides (1080x1920) of what's in stock at Drive Your Style, 4 products per slide.

    python tools/shop_story.py site/data out_dir [--slides 3]
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from social import FONT_CSS, LOGO, esc, img, money  # noqa: E402

CSS = """*{margin:0;box-sizing:border-box}body{width:1080px;height:1920px;overflow:hidden;color:#f2f0eb;font-family:'Space Grotesk';
background:radial-gradient(900px 700px at 100% 8%,rgba(124,92,255,.32),transparent 60%),radial-gradient(800px 600px at 0% 95%,rgba(0,200,255,.18),transparent 60%),#050404;padding:250px 70px 330px;display:flex;flex-direction:column}
.logo{height:96px;align-self:flex-start}h1{font-family:'Barlow Condensed';font-weight:800;font-size:124px;line-height:.9;text-transform:uppercase;margin-top:40px}
.holo{background:linear-gradient(90deg,#5ee7ff,#a78bfa,#ff7ad9,#ffd36e);-webkit-background-clip:text;background-clip:text;color:transparent}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:26px;margin-top:40px}.it{background:#14131a;border-radius:24px;padding:18px;display:flex;flex-direction:column}
.im{background:#fff;border-radius:16px;height:330px;display:grid;place-items:center;overflow:hidden}.im img{max-width:100%;max-height:100%;object-fit:contain}
.n{font-size:30px;font-weight:700;line-height:1.15;margin-top:14px;height:70px;overflow:hidden}.p{font-family:'Barlow Condensed';font-weight:800;font-size:58px;margin-top:6px}
.m{font-size:24px;color:#bdb9b2}.u{color:#3ee08f}.box{margin-top:auto;border:4px solid #f2f0eb;padding:22px;font-family:'Barlow Condensed';font-weight:700;font-size:54px;text-align:center}"""

def main(a):
    site, out = a[0], a[1]; n = int(a[a.index("--slides") + 1]) if "--slides" in a else 3
    rows = [r for r in json.load(open(os.path.join(site, "stock.json"))) if r.get("p")]
    rows.sort(key=lambda r: (r.get("t") != "s", -(r["p"])))
    os.makedirs(out, exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1080, "height": 1920})
        for k in range(n):
            items = rows[k * 4:(k + 1) * 4]
            if not items: break
            cards = "".join(f'<div class="it"><div class="im"><img src="{img(r["id"], 400)}"></div><div class="n">{esc(re.sub(r" [(](Holofoil|Normal)[)]$", "", r["n"]))}</div>'
                            f'<div class="p">{money(r["p"])}</div><div class="m">{"<span class=u>Under market</span>" if r.get("m") and r["p"] < r["m"] else "Ships from Las Vegas"}</div></div>' for r in items)
            head = "In stock<br><span class='holo'>now</span>" if k == 0 else f"More in<br><span class='holo'>stock</span>"
            html = f"<html><head><meta charset=utf-8><style>{FONT_CSS}{CSS}</style></head><body><img class='logo' src='file://{LOGO}'><h1>{head}</h1><div class='grid'>{cards}</div><div class='box'>Shop: driveyourstyle.net</div></body></html>"
            f = os.path.abspath(f"{out}/_s.html"); open(f, "w").write(html)
            pg.goto("file://" + f, wait_until="networkidle"); pg.evaluate("document.fonts.ready")
            pg.screenshot(path=f"{out}/shop-{k + 1}.jpg", type="jpeg", quality=90)
        os.remove(f); b.close()
    print("shop story: done")

if __name__ == "__main__":
    main(sys.argv[1:])
