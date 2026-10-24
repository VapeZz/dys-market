"""Weekly "In stock & under market" carousel: Drive Your Style products priced below today's market price.

    python tools/deals_social.py site/data data/social-deals [--date YYYY-MM-DD] [--force] [--offline]

Posts only when there are real deals: at least 3 in-stock products priced 2%+ under market.
Skips when the deals are the same as a post from the last 14 days (same products at the same prices).
Writes <out>/<date>/slide-N.jpg (1080x1350), tt-N.jpg (1080x1920), short.mp4, post.json and <out>/latest.json
({"post": false, "reason"} on skipped weeks). The nightly job copies it to market.driveyourstyle.net/social-deals/.
"""
import json
import os
import re
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from social import BASE, FONT_CSS, LOGO, esc, img, money  # noqa: E402

SITE = "https://market.driveyourstyle.net"
STORE = "https://driveyourstyle.net"
MIN_OFF, MIN_ITEMS, MAX_ITEMS = 0.02, 3, 5
TAGS = "#pokemontcg #pokemoncards #pokemon #tcg #onepiecetcg #tradingcards #cardcollector #lasvegas #vegaspokemon #driveyourstyle"


def clean(n):
    return re.sub(r"\s*\((Holofoil|Normal|Foil|Reverse Holofoil)\)$", "", n)


def pick(site_data):
    rows = json.load(open(os.path.join(site_data, "stock.json")))
    out = []
    for r in rows:
        if not r.get("m") or not r.get("p") or r["p"] <= 0:
            continue
        off = 1 - r["p"] / r["m"]
        if off >= MIN_OFF:
            out.append({**r, "off": off, "name": clean(r["n"])})
    out.sort(key=lambda r: (-r["off"], -r["m"]))
    return out[:MAX_ITEMS]


def cover(items):
    fan = "".join(
        f'<div class="card" style="position:absolute;width:300px;height:300px;left:{x}px;top:{y}px;transform:rotate({rot}deg);z-index:{z}">'
        f'<img src="{img(c["id"], 400)}" style="padding:14px"></div>'
        for c, (x, y, rot, z) in zip(items, [(372, 60, 0, 5), (140, 110, -10, 4), (604, 110, 10, 4), (-40, 200, -18, 3), (794, 200, 18, 3)]))
    top = max(i["off"] for i in items)
    return f"""<div class="slide">
<div class="top"><img class="logo" src="file://{LOGO}"><div class="tag">In stock now</div></div>
<div style="margin-top:56px;font-family:'Barlow Condensed';font-weight:800;font-size:138px;line-height:.9;text-transform:uppercase">Under<br><span class="holo">market</span></div>
<div style="margin-top:22px;font-size:40px;color:#d8d5cf">{len(items)} deals this week · up to {top * 100:.0f}% under market price</div>
<div style="position:relative;flex:1;margin-top:40px">{fan}</div>
<div class="bar" style="margin-bottom:26px"></div>
<div class="foot"><span>Swipe for prices →</span><span>Ships from Las Vegas</span></div></div>"""


def item_slide(n, c):
    return f"""<div class="slide">
<div class="top"><img class="logo" src="file://{LOGO}" style="height:72px"><div style="font-family:'Barlow Condensed';font-weight:800;font-size:64px;line-height:1;color:#3ee08f">{c['off'] * 100:.0f}% UNDER MARKET</div></div>
<div style="display:flex;justify-content:center;margin-top:30px"><div class="card" style="width:600px;height:600px"><img src="{img(c['id'])}" style="padding:24px"></div></div>
<div style="margin-top:40px;font-family:'Barlow Condensed';font-weight:800;font-size:{62 if len(c['name']) < 34 else 50}px;line-height:1.05;text-transform:uppercase;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">{esc(c['name'])}</div>
<div style="margin-top:auto;display:flex;align-items:flex-end;justify-content:space-between">
 <div><div style="font-size:28px;color:#bdb9b2">Our price</div><div style="font-family:'Barlow Condensed';font-weight:800;font-size:110px;line-height:1">{money(c['p'])}</div></div>
 <div style="text-align:right"><div style="font-size:28px;color:#bdb9b2">Market price today</div><div style="font-family:'Barlow Condensed';font-weight:700;font-size:64px;line-height:1;color:#bdb9b2;text-decoration:line-through">{money(c['m'])}</div>
 <div style="font-size:28px;color:#3ee08f;margin-top:6px">You save {money(c['m'] - c['p'])}</div></div>
</div></div>"""


def cta():
    return f"""<div class="slide" style="justify-content:center;align-items:center;text-align:center">
<img src="file://{LOGO}" style="height:200px">
<div style="margin-top:70px;font-family:'Barlow Condensed';font-weight:800;font-size:104px;line-height:.95;text-transform:uppercase">Grab it before<br><span class="holo">it's gone</span></div>
<div style="margin-top:34px;font-size:40px;color:#d8d5cf;max-width:840px">Limited stock. Prices checked against today's market price.</div>
<div style="margin-top:56px;font-family:'Barlow Condensed';font-weight:700;font-size:62px;letter-spacing:.04em;border:4px solid #f2f0eb;padding:16px 36px 12px">driveyourstyle.net</div>
<div class="bar" style="width:100%;margin-top:80px"></div>
<div class="foot" style="width:100%;margin-top:26px"><span>Link in bio</span><span>DM @drive.yourstyle</span></div></div>"""


def main(argv):
    site_data, out_root = argv[0], argv[1]
    today = date.fromisoformat(argv[argv.index("--date") + 1]) if "--date" in argv else date.today()
    force = "--force" in argv
    os.makedirs(out_root, exist_ok=True)
    hpath = os.path.join(out_root, "history.json")
    try:
        history = json.load(open(hpath))
    except (OSError, ValueError):
        history = []
    items = pick(site_data)
    sig = "|".join(f"{i['id']}:{i['p']}" for i in sorted(items, key=lambda i: i["id"]))
    reason = ""
    if len(items) < MIN_ITEMS:
        reason = f"only {len(items)} in-stock products are 2%+ under market; need {MIN_ITEMS}"
    elif not force and any(h["sig"] == sig and h["date"] >= (today - timedelta(days=14)).isoformat() for h in history if h["date"] != today.isoformat()):
        reason = "same deals as a post in the last 14 days"
    if reason:
        post = {"date": today.isoformat(), "post": False, "reason": reason}
        json.dump(post, open(os.path.join(out_root, "latest.json"), "w"), ensure_ascii=False)
        print(f"deals: skipped ({reason})")
        return
    out = os.path.join(out_root, today.isoformat())
    os.makedirs(out, exist_ok=True)
    slides = [cover(items)] + [item_slide(n + 1, c) for n, c in enumerate(items)] + [cta()]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1350})
        if "--offline" in argv:
            pg.route(re.compile(r"tcgplayer-cdn"), lambda r: r.fulfill(path=os.environ["FAKE_CARD"], content_type="image/jpeg"))
        tmp = os.path.abspath(os.path.join(out, "_slide.html"))
        for n, body in enumerate(slides, 1):
            open(tmp, "w", encoding="utf-8").write(BASE % (FONT_CSS, body))
            pg.goto("file://" + tmp, wait_until="networkidle")
            pg.evaluate("document.fonts.ready")
            pg.screenshot(path=os.path.join(out, f"slide-{n}.jpg"), type="jpeg", quality=92)
        os.remove(tmp)
        from tiktok import full_screen
        tt = full_screen(pg, [os.path.join(out, f"slide-{n}.jpg") for n in range(1, len(slides) + 1)], out,
                         foot="In stock now · driveyourstyle.net")
        b.close()
    from tiktok import make_short
    video = make_short(tt, os.path.join(out, "short.mp4"), per=3.4)
    lines = [f"🔥 In stock & under market this week ({today:%b %-d})", ""]
    lines += [f"• {c['name']}: {money(c['p'])} (market {money(c['m'])}, {c['off'] * 100:.0f}% under)" for c in items]
    lines += ["", "Limited stock, ships from Las Vegas. Shop at driveyourstyle.net (link in bio) or DM us to hold one.", "",
              "Market prices are today's TCGplayer market prices, tracked every night at market.driveyourstyle.net.", "", TAGS]
    caption = "\n".join(lines)
    top = items[0]
    caption_tt = (f"In stock and under market price this week 🔥 {top['name']} is {top['off'] * 100:.0f}% under market\n\n"
                  "Shop at driveyourstyle.net (link in bio)\n\n#pokemon #pokemoncards #pokemontcg #tcg #cardcollecting")
    base = f"{SITE}/social-deals/{today.isoformat()}"
    post = {"date": today.isoformat(), "post": True, "caption": caption, "caption_tiktok": caption_tt,
            "items": [{"id": c["id"], "name": c["name"], "p": c["p"], "m": c["m"], "u": c["u"]} for c in items],
            "slides": [f"{base}/slide-{n}.jpg" for n in range(1, len(slides) + 1)],
            "slides_tiktok": [f"{base}/tt-{n}.jpg" for n in range(1, len(tt) + 1)],
            "short": f"{base}/short.mp4" if video else None,
            "short_title": f"{top['name'][:45]} for {top['off'] * 100:.0f}% UNDER market price 🔥 Is it a steal? #pokemon"}
    json.dump(post, open(os.path.join(out, "post.json"), "w"), indent=1, ensure_ascii=False)
    json.dump(post, open(os.path.join(out_root, "latest.json"), "w"), ensure_ascii=False)
    history = [h for h in history if h["date"] != today.isoformat()] + [{"date": today.isoformat(), "sig": sig}]
    json.dump(history[-30:], open(hpath, "w"))
    print(f"deals: made {len(slides)} slides with {len(items)} deals (top {top['name']} {top['off'] * 100:.0f}% under)")


if __name__ == "__main__":
    main(sys.argv[1:])
