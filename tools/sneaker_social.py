"""Weekly "Sneaker drops" Instagram carousel, made from the release calendar.

    python tools/sneaker_social.py site data/social-sneakers [--date YYYY-MM-DD] [--offline]

Reads site/sneakers.json and site/data/sneaker-images.json and covers the 7 days
after --date (it runs on Sundays, so that's Monday to Sunday). Writes
<out>/<date>/slide-N.jpg (1080x1350), caption.txt, post.json and <out>/latest.json.
The nightly workflow copies it to https://market.driveyourstyle.net/social-sneakers/.
"""
import html
import json
import os
import re
import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

from social import BASE, FONT_CSS, LOGO

SITE = "https://market.driveyourstyle.net"
HASHTAGS = "#sneakers #sneakerreleases #snkrs #jordan #nike #kicks #sneakerhead #sneakernews #kobe #airjordan #lasvegas #vegassneakers #driveyourstyle"
VERDICT = {"cop": ("Cop", "#3ee08f"), "wear": ("Cop to wear", "#a78bfa"), "wait": ("Wait", "#ffd36e")}


def esc(t):
    return html.escape(str(t), quote=True)


def usd(r):
    return f"${r}" if r else "TBA"


def pick(site, start, end):
    data = json.load(open(os.path.join(site, "sneakers.json")))
    try:
        imgs = json.load(open(os.path.join(site, "data", "sneaker-images.json")))
    except (OSError, ValueError):
        imgs = {}
    picks = {p["c"]: p for p in data.get("picks", [])}
    big = lambda u: u and u.replace(",w_500/", ",w_1200/")  # sharper photos for 1080px slides
    week = [dict(r, im=big(r.get("im") or imgs.get(r.get("c") or ""))) for r in data["releases"]
            if start.isoformat() <= r["d"] <= end.isoformat()]
    for r in week:
        r["pick"] = picks.get(r.get("c"))
    # featured: picks and hot drops first, photos before no-photo, then by date
    ranked = sorted(week, key=lambda r: (-(r["pick"] is not None), -r["h"], -(r["im"] is not None), r["d"]))
    featured = [r for r in ranked if r["im"]][:5]
    if len(featured) < 3:
        featured = (featured + [r for r in ranked if r not in featured])[:5]
    featured.sort(key=lambda r: (r["d"], -r["h"]))
    return week, featured


def day(d, fmt):
    return date.fromisoformat(d).strftime(fmt).replace(" 0", " ")


def shoe(r, h=None):
    if r.get("im"):
        return f'<img src="{esc(r["im"])}" style="width:100%;height:100%;object-fit:cover">'
    return (f'<div style="width:100%;height:100%;display:grid;place-content:center;justify-items:center;color:#8a8fa3;'
            f"font-family:'Barlow Condensed';font-weight:800;font-size:{60 if h else 40}px;letter-spacing:.08em;text-transform:uppercase\">"
            f'{esc(r["b"])}</div>')


def cover(feat, span):
    spots = [(330, 10, 0, 5, 420), (60, 150, -9, 4, 360), (660, 150, 9, 4, 360)]
    fan = "".join(
        f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{w}px;transform:rotate({rot}deg);z-index:{z};'
        f'background:#f2f2f2;border-radius:28px;overflow:hidden;box-shadow:0 30px 80px rgba(0,0,0,.6)">{shoe(r)}</div>'
        for r, (x, y, rot, z, w) in zip([f for f in feat if f.get("im")][:3], spots))
    return f"""<div class="slide">
<div class="top"><img class="logo" src="file://{LOGO}"><div class="tag">Release week</div></div>
<div style="margin-top:56px;font-family:'Barlow Condensed';font-weight:800;font-size:150px;line-height:.9;text-transform:uppercase">Sneaker<br><span class="holo">drops</span></div>
<div style="margin-top:22px;font-size:40px;color:#d8d5cf">What's releasing {esc(span)}</div>
<div style="position:relative;flex:1;margin-top:50px">{fan}</div>
<div class="bar" style="margin-bottom:26px"></div>
<div class="foot"><span>Swipe for this week's drops →</span><span>market.driveyourstyle.net</span></div></div>"""


def drop_slide(r):
    v = r.get("pick") and VERDICT.get(r["pick"]["v"])
    badge = ""
    if v:
        badge = f'<div style="font-family:\'Barlow Condensed\';font-weight:800;font-size:40px;letter-spacing:.06em;text-transform:uppercase;color:#050404;background:{v[1]};padding:8px 20px 4px;border-radius:999px">Our call: {v[0]}</div>'
    elif r["h"] == 3:
        badge = '<div style="font-family:\'Barlow Condensed\';font-weight:800;font-size:40px;letter-spacing:.06em;text-transform:uppercase;color:#050404;background:#ff7a59;padding:8px 20px 4px;border-radius:999px">🔥 Hot drop</div>'
    name = r["n"]
    return f"""<div class="slide">
<div class="top"><img class="logo" src="file://{LOGO}" style="height:72px">
 <div style="text-align:right;font-family:'Barlow Condensed';font-weight:800;line-height:.95;text-transform:uppercase"><div style="font-size:44px;color:#bdb9b2">{day(r["d"], "%A")}</div><div class="holo" style="font-size:96px">{day(r["d"], "%b %d")}</div></div></div>
<div style="margin-top:30px;height:640px;background:#f2f2f2;border-radius:28px;overflow:hidden;position:relative">{shoe(r, True)}
 <div style="position:absolute;left:24px;top:24px">{badge}</div></div>
<div style="margin-top:34px;font-family:'Barlow Condensed';font-weight:800;font-size:{64 if len(name) < 34 else 52}px;line-height:1.02;text-transform:uppercase;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">{esc(name)}</div>
<div style="margin-top:10px;font-size:30px;color:#bdb9b2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(r.get("cw") or "")}</div>
<div style="margin-top:auto;display:flex;align-items:flex-end;justify-content:space-between">
 <div><div style="font-size:28px;color:#bdb9b2">Retail</div><div style="font-family:'Barlow Condensed';font-weight:800;font-size:96px;line-height:1">{usd(r.get("r"))}</div></div>
 <div style="text-align:right;font-size:28px;color:#bdb9b2">{esc(r.get("c") or "")}<br>Resale check at market.driveyourstyle.net</div>
</div></div>"""


def list_slide(week, span):
    rows = sorted(week, key=lambda r: (r["d"], -r["h"]))[:11]
    more = len(week) - len(rows)
    li = "".join(
        f'<div style="display:flex;gap:26px;align-items:baseline;padding:16px 0;border-bottom:2px solid rgba(255,255,255,.08)">'
        f'<div style="flex:0 0 120px;font-family:\'Barlow Condensed\';font-weight:800;font-size:38px;color:#bdb9b2;text-transform:uppercase">{day(r["d"], "%a %d")}</div>'
        f'<div style="flex:1;font-size:32px;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{"🔥 " if r["h"] == 3 else ""}{esc(r["n"])}</div>'
        f'<div style="font-family:\'Barlow Condensed\';font-weight:800;font-size:40px">{usd(r.get("r"))}</div></div>' for r in rows)
    return f"""<div class="slide">
<div class="top"><img class="logo" src="file://{LOGO}" style="height:72px"><div class="tag">Full list</div></div>
<div style="margin-top:40px;font-family:'Barlow Condensed';font-weight:800;font-size:96px;line-height:.95;text-transform:uppercase">All drops <span class="holo">{esc(span)}</span></div>
<div style="margin-top:24px">{li}</div>
<div style="margin-top:auto;font-size:30px;color:#bdb9b2">{f"+{more} more · " if more > 0 else ""}Full calendar with resale checks at market.driveyourstyle.net</div></div>"""


def cta():
    return f"""<div class="slide" style="justify-content:center;align-items:center;text-align:center">
<img src="file://{LOGO}" style="height:200px">
<div style="margin-top:70px;font-family:'Barlow Condensed';font-weight:800;font-size:110px;line-height:.95;text-transform:uppercase">Never miss<br>a <span class="holo">drop</span></div>
<div style="margin-top:34px;font-size:40px;color:#d8d5cf;max-width:860px">Release dates, our cop-or-wait calls, one-tap reminders and resale checks. Free.</div>
<div style="margin-top:56px;font-family:'Barlow Condensed';font-weight:700;font-size:58px;letter-spacing:.04em;border:4px solid #f2f0eb;padding:16px 36px 12px">market.driveyourstyle.net</div>
<div class="bar" style="width:100%;margin-top:80px"></div>
<div class="foot" style="width:100%;margin-top:26px"><span>Shop sneakers · link in bio</span><span>DM @drive.yourstyle</span></div></div>"""


def main(argv):
    site, out_root = argv[0], argv[1]
    today = date.fromisoformat(argv[argv.index("--date") + 1]) if "--date" in argv else date.today()
    start, end = today + timedelta(days=1), today + timedelta(days=7)
    week, feat = pick(site, start, end)
    if len(feat) < 3:
        print(f"sneaker social: only {len(feat)} drops next week; skipping")
        return
    span = f"{start:%b %-d}–{end:%-d}" if start.month == end.month else f"{start:%b %-d}–{end:%b %-d}"
    slides = [cover(feat, span)] + [drop_slide(r) for r in feat] + [list_slide(week, span), cta()]
    out = os.path.join(out_root, today.isoformat())
    os.makedirs(out, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1350})
        if "--offline" in argv:  # local testing without network: stand-in shoe photo
            pg.route(re.compile(r"static\.nike\.com"), lambda r: r.fulfill(path=os.environ["FAKE_SHOE"], content_type="image/jpeg"))
        tmp = os.path.abspath(os.path.join(out, "_slide.html"))
        for i, body in enumerate(slides, 1):
            open(tmp, "w", encoding="utf-8").write(BASE % (FONT_CSS, body))
            pg.goto("file://" + tmp, wait_until="networkidle")
            pg.evaluate("document.fonts.ready")
            pg.screenshot(path=os.path.join(out, f"slide-{i}.jpg"), type="jpeg", quality=92)
        os.remove(tmp)
        from tiktok import full_screen
        tt = full_screen(pg, [os.path.join(out, f"slide-{i}.jpg") for i in range(1, len(slides) + 1)], out,
                         foot="Release dates & resale · market.driveyourstyle.net")
        b.close()
    lines = [f"👟 Sneaker drops {span}", ""]
    for r in sorted(week, key=lambda r: (r["d"], -r["h"])):
        if r["h"] >= 2 or r in feat:
            call = f" · our call: {VERDICT[r['pick']['v']][0]}" if r.get("pick") and r["pick"]["v"] in VERDICT else ""
            lines.append(f"{'🔥' if r['h'] == 3 else '•'} {day(r['d'], '%a %-m/%-d')}: {r['n']} ({usd(r.get('r'))}){call}")
    lines += ["", "Which pair are you copping? 👇", "",
              "Full release calendar with reminders and StockX/GOAT/eBay resale checks at market.driveyourstyle.net (link in bio). Dates can change.",
              "", HASHTAGS]
    caption = "\n".join(lines)
    open(os.path.join(out, "caption.txt"), "w").write(caption)
    hot = next((r for r in feat if r["h"] == 3), feat[0])
    caption_tt = (f"Sneaker drops this week 👟 {hot['n']} {day(hot['d'], '%a %-m/%-d')} at {usd(hot.get('r'))}\n\n"
                  "Which pair are you copping? 👇 Full calendar at market.driveyourstyle.net\n\n"
                  "#sneakers #sneakerreleases #jordan #nike #kicks")
    post = {"date": today.isoformat(), "span": span, "caption": caption, "caption_tiktok": caption_tt,
            "slides_tiktok": [f"{SITE}/social-sneakers/{today.isoformat()}/tt-{i}.jpg" for i in range(1, len(tt) + 1)],
            "drops": [{k: r.get(k) for k in ("d", "n", "c", "r", "h")} for r in feat],
            "slides": [f"{SITE}/social-sneakers/{today.isoformat()}/slide-{i}.jpg" for i in range(1, len(slides) + 1)]}
    json.dump(post, open(os.path.join(out, "post.json"), "w"), indent=1, ensure_ascii=False)
    json.dump(post, open(os.path.join(out_root, "latest.json"), "w"), indent=1, ensure_ascii=False)
    dirs = sorted(d for d in os.listdir(out_root) if re.match(r"\d{4}-\d{2}-\d{2}$", d))
    for d in dirs[:-8]:
        for f in os.listdir(os.path.join(out_root, d)):
            os.remove(os.path.join(out_root, d, f))
        os.rmdir(os.path.join(out_root, d))
    print(f"sneaker social: {len(slides)} slides, {len(week)} drops for {span} -> {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
