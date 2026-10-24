"""Weekly "Trending cards" Instagram carousel, made from the market data.

    python tools/social.py site/data data/social [--date YYYY-MM-DD] [--offline]

Writes data/social/<date>/slide-1.jpg ... slide-7.jpg (1080x1350), caption.txt
and post.json, plus data/social/latest.json pointing at the newest set. The
nightly workflow copies data/social to the site, so the images are public at
https://market.driveyourstyle.net/social/<date>/slide-N.jpg for scheduling.
"""
import html
import json
import os
import re
import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "tools", "social-fonts")
LOGO = os.path.join(ROOT, "tools", "social-logo.png")
SITE = "https://market.driveyourstyle.net"
SKIP = re.compile(r"prerelease|\[staff\]|code card|jumbo|oversize", re.I)
HASHTAGS = "#pokemontcg #pokemoncards #pokemon #pokemontcgcommunity #pokemoncollection #tcg #tradingcards #cardcollector #pokemoncollector #lasvegas #vegaspokemon #driveyourstyle"


def esc(t):
    return html.escape(str(t), quote=True)


def money(c):
    return f"${c / 100:,.2f}"


def short_set(n):
    return re.sub(r"^(ME|SV|SWSH|SM|XY|BW|M|OP|EB|ST|PRB)\d*[a-z]?\s*[:\-–]\s*", "", n, flags=re.I)


def clean_name(n):
    n = re.sub(r" \((Holofoil|Normal|Foil)\)$", "", n).replace(" (Foil)", "")
    return n.replace(" (Reverse Holofoil)", " (Reverse Holo)")


def pick(site_data, today, limit=5):
    """Top 5 card risers from sets released in the last 3 years (priced $15+), max 2 per set."""
    meta = json.load(open(os.path.join(site_data, "meta.json")))
    recent = (today - timedelta(days=3 * 365)).isoformat()
    sets = [s for s in json.load(open(os.path.join(site_data, "sets.json"))) if (s.get("pub") or "") >= recent and s["pub"] <= today.isoformat()]
    items = []
    for s in sets:
        path = os.path.join(site_data, "set", f"{s['id']}.json")
        if not os.path.exists(path):
            continue
        for i in json.load(open(path))["items"]:
            if i["t"] == "c" and i.get("p") and i["p"] >= 1000 and i.get("ch") and not SKIP.search(i["n"]):
                items.append((s, i))
    win = "7" if sum(1 for _, i in items if i["ch"].get("7") is not None) > 50 else "a"
    rows = []
    for s, i in items:
        pct = i["ch"].get(win)
        if pct is None or not (5 <= pct <= 150):
            continue
        old = round(i["p"] / (1 + pct / 100))
        rows.append((pct, s, i, old))
    rows.sort(key=lambda r: -r[0])
    out, per_set, used = [], {}, set()
    def take(limit_pokemon, limit_other):
        quota = {"pokemon": limit_pokemon, "other": limit_other}
        for pct, s, i, old in rows:
            if len(out) == limit:
                return
            bucket = "pokemon" if s["k"].startswith("pokemon") else "other"
            if i["id"] in used or per_set.get(s["id"], 0) >= 2 or quota[bucket] <= 0:
                continue
            per_set[s["id"]] = per_set.get(s["id"], 0) + 1
            quota[bucket] -= 1
            used.add(i["id"])
            out.append({"id": i["id"], "name": clean_name(i["n"]), "set": short_set(s["n"]), "gid": s["id"], "game": s["k"], "now": i["p"], "old": old, "pct": pct})
    take(limit, 0)   # Pokémon only: TCGplayer's One Piece photos carry a "SAMPLE" watermark
    out.sort(key=lambda c: -c["pct"])
    since = meta.get("anchors", {}).get("7") if win == "7" else meta.get("first")
    return out, ("7" if win == "7" else "all"), since


FONT_CSS = "".join(
    f"@font-face{{font-family:'{fam}';font-weight:{w};src:url('file://{FONTS}/{f}')}}"
    for fam, w, f in [("Barlow Condensed", 600, "barlow-condensed-latin-600-normal.woff2"),
                      ("Barlow Condensed", 700, "barlow-condensed-latin-700-normal.woff2"),
                      ("Barlow Condensed", 800, "barlow-condensed-latin-800-normal.woff2"),
                      ("Space Grotesk", 500, "space-grotesk-latin-500-normal.woff2"),
                      ("Space Grotesk", 700, "space-grotesk-latin-700-normal.woff2")])

BASE = """<!doctype html><html><head><meta charset="utf-8"><style>%s
*{box-sizing:border-box;margin:0}
body{width:1080px;height:1350px;overflow:hidden;background:#050404;color:#f2f0eb;font-family:'Space Grotesk',sans-serif}
.slide{position:relative;width:1080px;height:1350px;padding:70px 72px;display:flex;flex-direction:column;
 background:radial-gradient(900px 600px at 100%% 0%%,rgba(124,92,255,.28),transparent 60%%),radial-gradient(700px 500px at 0%% 100%%,rgba(0,200,255,.16),transparent 60%%),#050404}
.top{display:flex;justify-content:space-between;align-items:center}
.logo{height:92px}
.tag{font-family:'Barlow Condensed';font-weight:700;font-size:30px;letter-spacing:.18em;text-transform:uppercase;border:3px solid #f2f0eb;padding:8px 18px 6px}
.holo{background:linear-gradient(90deg,#5ee7ff,#a78bfa,#ff7ad9,#ffd36e);-webkit-background-clip:text;background-clip:text;color:transparent}
.bar{height:6px;background:linear-gradient(90deg,#5ee7ff,#a78bfa,#ff7ad9,#ffd36e);border-radius:3px}
.foot{display:flex;justify-content:space-between;align-items:center;font-family:'Barlow Condensed';font-weight:700;font-size:32px;letter-spacing:.08em;text-transform:uppercase;color:#bdb9b2}
.card{background:#fff;border-radius:22px;overflow:hidden;box-shadow:0 30px 80px rgba(0,0,0,.6)}
.card img{display:block;width:100%%;height:100%%;object-fit:contain}
</style></head><body>%s</body></html>"""


def img(pid, size=1000):
    return f"https://tcgplayer-cdn.tcgplayer.com/product/{pid}_in_{size}x{size}.jpg"


def cover(cards, period):
    fan = "".join(
        f'<div class="card" style="position:absolute;width:300px;height:420px;left:{x}px;top:{y}px;transform:rotate({r}deg);z-index:{z}">'
        f'<img src="{img(c["id"], 400)}"></div>'
        for c, (x, y, r, z) in zip(cards, [(372, 40, 0, 5), (150, 90, -12, 4), (594, 90, 12, 4), (-40, 170, -22, 3), (784, 170, 22, 3)]))
    return f"""<div class="slide">
<div class="top"><img class="logo" src="file://{LOGO}"><div class="tag">Market report</div></div>
<div style="margin-top:56px;font-family:'Barlow Condensed';font-weight:800;font-size:150px;line-height:.9;text-transform:uppercase">Trending<br><span class="holo">cards</span></div>
<div style="margin-top:22px;font-size:40px;color:#d8d5cf">Biggest price jumps {esc(period)}</div>
<div style="position:relative;flex:1;margin-top:40px">{fan}</div>
<div class="bar" style="margin-bottom:26px"></div>
<div class="foot"><span>Swipe for the top 5 →</span><span>market.driveyourstyle.net</span></div></div>"""


def card_slide(i, c, period):
    return f"""<div class="slide">
<div class="top"><img class="logo" src="file://{LOGO}" style="height:72px"><div style="font-family:'Barlow Condensed';font-weight:800;font-size:110px;line-height:1" class="holo">#{i}</div></div>
<div style="display:flex;justify-content:center;margin-top:24px"><div class="card" style="width:500px;height:700px"><img src="{img(c['id'])}"></div></div>
<div style="margin-top:36px;font-family:'Barlow Condensed';font-weight:800;font-size:{60 if len(c['name']) < 30 else 50}px;line-height:1.05;text-transform:uppercase;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">{esc(c['name'])}</div>
<div style="margin-top:10px;font-size:30px;color:#bdb9b2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(c['set'])}</div>
<div style="margin-top:auto;display:flex;align-items:flex-end;justify-content:space-between">
 <div><div style="font-size:28px;color:#bdb9b2">Market price</div><div style="font-family:'Barlow Condensed';font-weight:800;font-size:96px;line-height:1">{money(c['now'])}</div></div>
 <div style="text-align:right"><div style="font-family:'Barlow Condensed';font-weight:800;font-size:80px;line-height:1;color:#3ee08f">▲ {c['pct']:.0f}%</div><div style="font-size:28px;color:#bdb9b2">was {money(c['old'])} · {esc(period)}</div></div>
</div></div>"""


def cta():
    return f"""<div class="slide" style="justify-content:center;align-items:center;text-align:center">
<img src="file://{LOGO}" style="height:200px">
<div style="margin-top:70px;font-family:'Barlow Condensed';font-weight:800;font-size:110px;line-height:.95;text-transform:uppercase">What's <span class="holo">your</span><br>card worth?</div>
<div style="margin-top:34px;font-size:40px;color:#d8d5cf;max-width:820px">Free live prices on 59,000+ Pokémon &amp; One Piece cards and sealed, updated every night.</div>
<div style="margin-top:56px;font-family:'Barlow Condensed';font-weight:700;font-size:58px;letter-spacing:.04em;border:4px solid #f2f0eb;padding:16px 36px 12px">market.driveyourstyle.net</div>
<div class="bar" style="width:100%;margin-top:80px"></div>
<div class="foot" style="width:100%;margin-top:26px"><span>Shop + all links in bio</span><span>DM @drive.yourstyle</span></div></div>"""


def main(argv):
    site_data, out_root = argv[0], argv[1]
    today = date.fromisoformat(argv[argv.index("--date") + 1]) if "--date" in argv else date.today()
    cards, win, since = pick(site_data, today)
    if len(cards) < 3:
        print(f"social: only {len(cards)} cards qualified; skipping")
        return
    if win == "7":
        start = today - timedelta(days=7)
        period = "this week"
        span = f"{start:%b %-d}–{today:%b %-d}"
    else:
        period = f"since {date.fromisoformat(since):%b %-d}"
        span = f"{date.fromisoformat(since):%b %-d}–{today:%b %-d}"
    out = os.path.join(out_root, today.isoformat())
    os.makedirs(out, exist_ok=True)
    slides = [cover(cards, f"{span}")] + [card_slide(i + 1, c, period) for i, c in enumerate(cards)] + [cta()]
    offline = "--offline" in argv
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1350})
        if offline:  # local testing without network: stand-in card images
            pg.route(re.compile(r"tcgplayer-cdn"), lambda r: r.fulfill(path=os.environ["FAKE_CARD"], content_type="image/jpeg"))
        tmp = os.path.abspath(os.path.join(out, "_slide.html"))
        for i, body in enumerate(slides, 1):
            open(tmp, "w", encoding="utf-8").write(BASE % (FONT_CSS, body))
            pg.goto("file://" + tmp, wait_until="networkidle")
            pg.evaluate("document.fonts.ready")
            pg.screenshot(path=os.path.join(out, f"slide-{i}.jpg"), type="jpeg", quality=92)
        os.remove(tmp)
        from tiktok import full_screen
        tt = full_screen(pg, [os.path.join(out, f"slide-{i}.jpg") for i in range(1, len(slides) + 1)], out)
        b.close()
    from tiktok import make_short
    video = make_short(tt, os.path.join(out, "short.mp4"), per=3.6)
    lines = [f"📈 Trending cards {span}", ""]
    lines += [f"{i}. {c['name']} ({c['set']}): {money(c['now'])}, up {c['pct']:.0f}%" for i, c in enumerate(cards, 1)]
    lines += ["", "Which one are you chasing? 👇", "",
              "Prices are TCGplayer market prices we track every night. Look up any card free at market.driveyourstyle.net (link in bio).",
              "", HASHTAGS]
    caption = "\n".join(lines)
    open(os.path.join(out, "caption.txt"), "w").write(caption)
    top = cards[0]
    caption_tt = (f"These Pokémon cards jumped {period} 📈 #1 is up {top['pct']:.0f}%\n\n"
                  "Which one do you have? 👇 Free prices at market.driveyourstyle.net (link in bio)\n\n"
                  "#pokemon #pokemoncards #pokemontcg #cardcollecting #tcg")
    post = {"date": today.isoformat(), "span": span, "caption": caption, "caption_tiktok": caption_tt, "cards": cards,
            "slides": [f"{SITE}/social/{today.isoformat()}/slide-{i}.jpg" for i in range(1, len(slides) + 1)],
            "slides_tiktok": [f"{SITE}/social/{today.isoformat()}/tt-{i}.jpg" for i in range(1, len(tt) + 1)],
            "short": f"{SITE}/social/{today.isoformat()}/short.mp4" if video else None,
            "short_title": f"These Pokémon cards jumped up to {top['pct']:.0f}% in ONE week 📈 Is #1 worth buying now? #pokemon"}
    json.dump(post, open(os.path.join(out, "post.json"), "w"), indent=1, ensure_ascii=False)
    json.dump(post, open(os.path.join(out_root, "latest.json"), "w"), indent=1, ensure_ascii=False)
    # keep the last 8 weeks
    dirs = sorted(d for d in os.listdir(out_root) if re.match(r"\d{4}-\d{2}-\d{2}$", d))
    for d in dirs[:-8]:
        for f in os.listdir(os.path.join(out_root, d)):
            os.remove(os.path.join(out_root, d, f))
        os.rmdir(os.path.join(out_root, d))
    print(f"social: {len(slides)} slides for {span} -> {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
