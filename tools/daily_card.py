"""Daily "Card of the Day" for TikTok: 3 full-screen slides (1080x1920) + a short hook caption.

    python tools/daily_card.py site/data data/social-daily [--date YYYY-MM-DD] [--offline]

Picks the biggest mover among recent Pokémon cards (same rules as the weekly Trending
carousel) that hasn't been featured in the last 21 days, and writes
<out>/<date>/slide-1..3.jpg, post.json and <out>/latest.json. The nightly workflow copies
it to https://market.driveyourstyle.net/social-daily/. TikTok adds music to photo posts
automatically, so the slideshow plays like a short video.
"""
import json
import os
import re
import sys
from datetime import date

from playwright.sync_api import sync_playwright

from social import BASE, FONT_CSS, LOGO, esc, img, money, pick

SITE = "https://market.driveyourstyle.net"
TAGS = "#pokemon #pokemoncards #pokemontcg #cardcollecting #tcg"
B = BASE.replace("height:1350px", "height:1920px")


def spark(site_data, card):
    """Price series for the card (cents), oldest first, from its set file."""
    try:
        d = json.load(open(os.path.join(site_data, "set", f"{card['gid']}.json")))
    except (OSError, ValueError):
        return []
    for i in d["items"]:
        if i["id"] == card["id"] and i.get("s"):
            return [v for v in i["s"] if v]
    return []


def spark_svg(vals, w=900, h=260):
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    pts = " ".join(f"{i * w / (len(vals) - 1):.1f},{h - (v - lo) / rng * (h - 20) - 10:.1f}" for i, v in enumerate(vals))
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}"><defs><linearGradient id="g" x1="0" x2="1">'
            f'<stop offset="0" stop-color="#5ee7ff"/><stop offset=".5" stop-color="#a78bfa"/><stop offset="1" stop-color="#3ee08f"/></linearGradient></defs>'
            f'<polyline points="{pts}" fill="none" stroke="url(#g)" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def slides(c, period, vals):
    name = c["name"]
    hook = f"""<div class="slide" style="height:1920px;padding:170px 80px 400px;align-items:center;text-align:center">
<img src="file://{LOGO}" style="height:100px">
<div class="tag" style="margin-top:50px">Card of the day</div>
<div style="margin-top:44px;font-family:'Barlow Condensed';font-weight:800;font-size:120px;line-height:.95;text-transform:uppercase">This card is<br><span style="color:#3ee08f">up {c['pct']:.0f}%</span><br>{esc(period)}</div>
<div class="card" style="margin-top:44px;width:470px;height:658px;transform:rotate(-3deg)"><img src="{img(c['id'])}"></div>
<div style="margin-top:auto;font-size:38px;color:#bdb9b2">Swipe for the price →</div></div>"""
    price = f"""<div class="slide" style="height:1920px;padding:170px 80px 400px;align-items:center;text-align:center">
<div class="card" style="width:520px;height:728px"><img src="{img(c['id'])}"></div>
<div style="margin-top:46px;font-family:'Barlow Condensed';font-weight:800;font-size:{70 if len(name) < 30 else 56}px;line-height:1.02;text-transform:uppercase">{esc(name)}</div>
<div style="margin-top:12px;font-size:36px;color:#bdb9b2">{esc(c['set'])}</div>
<div style="margin-top:40px;display:flex;gap:60px;align-items:flex-end;justify-content:center">
 <div><div style="font-size:32px;color:#bdb9b2">Market price</div><div style="font-family:'Barlow Condensed';font-weight:800;font-size:130px;line-height:1">{money(c['now'])}</div></div>
 <div><div style="font-family:'Barlow Condensed';font-weight:800;font-size:96px;line-height:1;color:#3ee08f">▲ {c['pct']:.0f}%</div><div style="font-size:32px;color:#bdb9b2">was {money(c['old'])}</div></div></div>
<div style="margin-top:30px">{spark_svg(vals, 900, 170)}</div></div>"""
    cta = f"""<div class="slide" style="height:1920px;justify-content:center;align-items:center;text-align:center;padding:170px 80px 400px">
<img src="file://{LOGO}" style="height:200px">
<div style="margin-top:80px;font-family:'Barlow Condensed';font-weight:800;font-size:130px;line-height:.92;text-transform:uppercase">Check <span class="holo">your</span><br>cards free</div>
<div style="margin-top:44px;font-size:44px;color:#d8d5cf;max-width:880px">Live prices on 60,000+ cards. Scan a card with your camera to see what it's worth.</div>
<div style="margin-top:70px;font-family:'Barlow Condensed';font-weight:700;font-size:62px;border:4px solid #f2f0eb;padding:18px 40px 14px">market.driveyourstyle.net</div>
<div style="margin-top:90px;font-family:'Barlow Condensed';font-weight:800;font-size:56px;letter-spacing:.04em;text-transform:uppercase" class="holo">Follow for a card every day</div></div>"""
    return [hook, price, cta]


def main(argv):
    site_data, out_root = argv[0], argv[1]
    today = date.fromisoformat(argv[argv.index("--date") + 1]) if "--date" in argv else date.today()
    hist_path = os.path.join(out_root, "history.json")
    try:
        history = json.load(open(hist_path))
    except (OSError, ValueError):
        history = {}
    done = os.path.join(out_root, today.isoformat(), "post.json")
    if os.path.exists(done) and "--force" not in argv:   # one card per day, even if the site is rebuilt again
        post = json.load(open(done))
        json.dump(post, open(os.path.join(out_root, "latest.json"), "w"), indent=1, ensure_ascii=False)
        print(f"daily card: already made for {today} ({post['card']['name']})")
        return
    recent = {int(k) for k, d in history.items() if (today - date.fromisoformat(d)).days < 21}
    cards, win, _ = pick(site_data, today, limit=40)
    sideways = re.compile(r"\bBREAK\b|\bLEGEND\b|jumbo|oversize", re.I)   # landscape cards don't fit the portrait slides
    fresh = [c for c in cards if c["id"] not in recent and not sideways.search(c["name"])]
    if not fresh:
        print("daily card: nothing new to feature today; skipping")
        return
    c = fresh[0]
    period = "this week" if win == "7" else "lately"
    out = os.path.join(out_root, today.isoformat())
    os.makedirs(out, exist_ok=True)
    bodies = slides(c, period, spark(site_data, c))
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1920})
        if "--offline" in argv:
            pg.route(re.compile(r"tcgplayer-cdn"), lambda r: r.fulfill(path=os.environ["FAKE_CARD"], content_type="image/jpeg"))
        tmp = os.path.abspath(os.path.join(out, "_slide.html"))
        for i, body in enumerate(bodies, 1):
            open(tmp, "w", encoding="utf-8").write(B % (FONT_CSS, body))
            pg.goto("file://" + tmp, wait_until="networkidle")
            pg.evaluate("document.fonts.ready")
            pg.screenshot(path=os.path.join(out, f"slide-{i}.jpg"), type="jpeg", quality=90)
        b.close()
        os.remove(tmp)
    from tiktok import make_short
    video = make_short([os.path.join(out, f"slide-{i}.jpg") for i in range(1, 4)], os.path.join(out, "short.mp4"))
    short = re.sub(r"\s*-\s*\d+/\d+$", "", c["name"])
    caption = (f"{short} is up {c['pct']:.0f}% {period} 📈 now {money(c['now'])}\n\n"
               f"Do you have one? 👇 Check your cards free at market.driveyourstyle.net (link in bio)\n\n{TAGS}")
    post = {"date": today.isoformat(), "card": c, "caption": caption,
            "slides": [f"{SITE}/social-daily/{today.isoformat()}/slide-{i}.jpg" for i in range(1, 4)],
            "short": f"{SITE}/social-daily/{today.isoformat()}/short.mp4" if video else None,
            "short_title": f"{short} is up {c['pct']:.0f}% {period} 📈 #pokemon #shorts"[:100]}
    json.dump(post, open(os.path.join(out, "post.json"), "w"), indent=1, ensure_ascii=False)
    json.dump(post, open(os.path.join(out_root, "latest.json"), "w"), indent=1, ensure_ascii=False)
    history[str(c["id"])] = today.isoformat()
    json.dump(history, open(hist_path, "w"))
    dirs = sorted(d for d in os.listdir(out_root) if re.match(r"\d{4}-\d{2}-\d{2}$", d))
    for d in dirs[:-14]:
        for f in os.listdir(os.path.join(out_root, d)):
            os.remove(os.path.join(out_root, d, f))
        os.rmdir(os.path.join(out_root, d))
    print(f"daily card: {c['name']} (+{c['pct']:.0f}%) -> {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
