"""Weekly "Trending cards" post, made from the market data: this week's winners and losers.
Cover hook "$100 → $X": what $100 in the #1 winner a week ago is worth now. Then 3 winners (▲) and 2 losers (▼);
if fewer than 2 cards fell enough, 5 winners. The "cards" list in post.json holds all of them (Cards of the Day
skips them for the week).

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
import urllib.error
import urllib.request
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


def pick(site_data, today, limit=5, losers=2):
    """Biggest card risers (and fallers) from sets released in the last 3 years (priced $10+), max 2 per set.
    Returns (winners, losers, window, since): 3 winners + 2 losers, or 5 winners if fewer than 2 losers qualify."""
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
    up, down = [], []
    for s, i in items:
        pct = i["ch"].get(win)
        if pct is None:
            continue
        old = round(i["p"] / (1 + pct / 100))
        if 5 <= pct <= 150:
            up.append((pct, s, i, old))
        elif -60 <= pct <= -5:
            down.append((pct, s, i, old))
    up.sort(key=lambda r: -r[0])
    down.sort(key=lambda r: r[0])
    per_set, used = {}, set()

    def take(rows, n):
        out = []
        for pct, s, i, old in rows:
            if len(out) == n:
                break
            # Pokémon only: TCGplayer's One Piece photos carry a "SAMPLE" watermark
            if not s["k"].startswith("pokemon") or i["id"] in used or per_set.get(s["id"], 0) >= 2:
                continue
            if not url_ok(img(i["id"], 400)):   # every card shown needs its own photo
                continue
            per_set[s["id"]] = per_set.get(s["id"], 0) + 1
            used.add(i["id"])
            out.append({"id": i["id"], "name": clean_name(i["n"]), "set": short_set(s["n"]), "gid": s["id"], "game": s["k"], "now": i["p"], "old": old, "pct": pct})
        return out
    winners = take(up, limit - losers)
    lost = take(down, losers)
    if len(lost) < losers:   # not enough fallers this week: all winners, as before
        for c in lost:
            used.discard(c["id"])
            per_set[c["gid"]] -= 1
        lost = []
        winners += take(up, limit - len(winners))
    since = meta.get("anchors", {}).get("7") if win == "7" else meta.get("first")
    return winners, lost, ("7" if win == "7" else "all"), since


def worth(c):
    """What $100 in this card at the start of the window is worth now."""
    return 100 * c["now"] / c["old"]


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


OFFLINE = False   # --offline (local tests): photos are assumed to exist
_ok = {}


def url_ok(u):
    """True if the URL serves a real image (TCGplayer answers 403/404 when a product has no photo)."""
    if not u:
        return False
    if OFFLINE:
        return True
    if u not in _ok:
        _ok[u] = False
        for method in ("HEAD", "GET"):
            try:
                req = urllib.request.Request(u, method=method, headers={"User-Agent": "DriveYourStyleMarket/1.0 (+https://driveyourstyle.net)"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    _ok[u] = r.status == 200 and r.headers.get("Content-Type", "").startswith("image")
                break
            except urllib.error.HTTPError as e:
                if e.code in (403, 404, 410):
                    break
            except Exception:
                pass
    return _ok[u]


GREEN, RED = "#3ee08f", "#ff7a59"


def chip(c):
    up = c["pct"] >= 0
    return (f'<div style="position:absolute;left:12px;top:12px;font-family:\'Barlow Condensed\';font-weight:800;font-size:34px;'
            f'color:#050404;background:{GREEN if up else RED};border-radius:999px;padding:4px 14px 1px">{"▲" if up else "▼"} {abs(c["pct"]):.0f}%</div>')


def cover(winners, losers, span, ago):
    top = winners[0]
    order = [winners[0]] + ([winners[1], losers[0]] + winners[2:3] + losers[1:2] if losers else winners[1:5])
    fan = "".join(
        f'<div class="card" style="position:absolute;width:280px;height:392px;left:{x}px;top:{y}px;transform:rotate({r}deg);z-index:{z}">'
        f'<img src="{img(c["id"], 400)}">{chip(c)}</div>'
        for c, (x, y, r, z) in zip(order, [(328, 30, 0, 5), (128, 80, -12, 4), (528, 80, 12, 4), (-30, 160, -20, 3), (686, 160, 20, 3)]))
    lose = (f'<div style="margin-top:14px;font-size:34px;color:#d8d5cf;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">…but $100 in {esc(losers[0]["name"])} is now <b style="color:{RED}">${worth(losers[0]):.0f}</b></div>'
            if losers else "")
    return f"""<div class="slide">
<div class="top"><img class="logo" src="file://{LOGO}"><div class="tag">{"Winners &amp; losers" if losers else "Trending cards"}</div></div>
<div style="margin-top:44px;font-family:'Barlow Condensed';font-weight:800;font-size:170px;line-height:.9;text-transform:uppercase">$100 <span style="color:#bdb9b2">→</span> <span class="holo">${worth(top):.0f}</span></div>
<div style="margin-top:20px;font-size:40px;color:#f2f0eb;font-weight:700;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">If you bought {esc(top['name'])} {esc(ago)}</div>
{lose}
<div style="position:relative;flex:1;margin-top:34px">{fan}</div>
<div class="bar" style="margin-bottom:26px"></div>
<div class="foot"><span>{esc(span)} · swipe →</span><span>market.driveyourstyle.net</span></div></div>"""


def card_slide(label, c, period, ago="a week ago"):
    up = c["pct"] >= 0
    return f"""<div class="slide">
<div class="top"><img class="logo" src="file://{LOGO}" style="height:72px"><div style="font-family:'Barlow Condensed';font-weight:800;font-size:84px;line-height:1;text-transform:uppercase;color:{GREEN if up else RED}">{esc(label)}</div></div>
<div style="display:flex;justify-content:center;margin-top:24px"><div class="card" style="width:500px;height:700px"><img src="{img(c['id'])}"></div></div>
<div style="margin-top:36px;font-family:'Barlow Condensed';font-weight:800;font-size:{60 if len(c['name']) < 30 else 50}px;line-height:1.05;text-transform:uppercase;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">{esc(c['name'])}</div>
<div style="margin-top:10px;font-size:30px;color:#bdb9b2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(c['set'])}</div>
<div style="margin-top:auto;display:flex;align-items:flex-end;justify-content:space-between">
 <div><div style="font-size:28px;color:#bdb9b2">Market price</div><div style="font-family:'Barlow Condensed';font-weight:800;font-size:96px;line-height:1">{money(c['now'])}</div></div>
 <div style="text-align:right"><div style="font-family:'Barlow Condensed';font-weight:800;font-size:80px;line-height:1;color:{GREEN if up else RED}">{"▲" if up else "▼"} {abs(c['pct']):.0f}%</div><div style="font-size:28px;color:#bdb9b2">was {money(c['old'])} · {esc(period)}</div></div>
</div>
<div style="margin-top:14px;display:flex;justify-content:space-between;font-size:28px;color:#8f8a84"><span>$100 {esc(ago)} → <b style="color:{GREEN if up else RED}">${worth(c):.0f}</b> now</span><span>Price: TCGplayer market</span></div></div>"""


def cta(losers=True):
    head = 'Buy the dip or<br>chase the <span class="holo">pump?</span>' if losers else 'What\'s <span class="holo">your</span><br>card worth?'
    return f"""<div class="slide" style="justify-content:center;align-items:center;text-align:center">
<img src="file://{LOGO}" style="height:200px">
<div style="margin-top:70px;font-family:'Barlow Condensed';font-weight:800;font-size:110px;line-height:.95;text-transform:uppercase">{head}</div>
<div style="margin-top:34px;font-size:40px;color:#d8d5cf;max-width:820px">{"Tell us in the comments. " if losers else ""}Free live prices on 59,000+ Pokémon &amp; One Piece cards and sealed, updated every night.</div>
<div style="margin-top:56px;font-family:'Barlow Condensed';font-weight:700;font-size:58px;letter-spacing:.04em;border:4px solid #f2f0eb;padding:16px 36px 12px">market.driveyourstyle.net</div>
<div class="bar" style="width:100%;margin-top:80px"></div>
<div class="foot" style="width:100%;margin-top:26px"><span>Shop + all links in bio</span><span>DM @drive.yourstyle</span></div></div>"""


def main(argv):
    global OFFLINE
    OFFLINE = "--offline" in argv
    site_data, out_root = argv[0], argv[1]
    today = date.fromisoformat(argv[argv.index("--date") + 1]) if "--date" in argv else date.today()
    winners, losers, win, since = pick(site_data, today)
    if len(winners) < 3:
        print(f"social: only {len(winners)} rising cards qualified; skipping")
        return
    cards = winners + losers
    if win == "7":
        start = today - timedelta(days=7)
        period, ago = "this week", "a week ago"
        span = f"{start:%b %-d}–{today:%b %-d}"
    else:
        period = f"since {date.fromisoformat(since):%b %-d}"
        ago = f"on {date.fromisoformat(since):%b %-d}"
        span = f"{date.fromisoformat(since):%b %-d}–{today:%b %-d}"
    out = os.path.join(out_root, today.isoformat())
    os.makedirs(out, exist_ok=True)
    slides = ([cover(winners, losers, span, ago)] +
              [card_slide(f"Winner #{i}" if losers else f"#{i}", c, period, ago) for i, c in enumerate(winners, 1)] +
              [card_slide(f"Loser #{i}", c, period, ago) for i, c in enumerate(losers, 1)] + [cta(bool(losers))])
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
    top = winners[0]
    hook = f"$100 in {top['name']} {ago} is worth ${worth(top):.0f} today"
    lines = [f"{'📈📉' if losers else '📈'} {hook}", "Prices: TCGplayer market", ""]
    lines += [f"{'Winners' if losers else 'Trending'} {span}:"]
    lines += [f"{i}. {c['name']} ({c['set']}): {money(c['now'])}, up {c['pct']:.0f}%" for i, c in enumerate(winners, 1)]
    if losers:
        lines += ["", "Losers:"]
        lines += [f"{i}. {c['name']} ({c['set']}): {money(c['now'])}, down {abs(c['pct']):.0f}%" for i, c in enumerate(losers, 1)]
    lines += ["", "Buy the dip or chase the pump? 👇" if losers else "Which one are you chasing? 👇", "",
              "Prices are TCGplayer market prices we track every night. Look up any card free at market.driveyourstyle.net (link in bio).",
              "", HASHTAGS]
    caption = "\n".join(lines)
    open(os.path.join(out, "caption.txt"), "w").write(caption)
    caption_tt = (f"$100 in this Pokémon card {ago} = ${worth(top):.0f} today 📈"
                  + (f" …and one lost {abs(losers[0]['pct']):.0f}% 📉" if losers else "") + "\nPrices: TCGplayer market\n\n"
                  + ("Winner or loser, which would you buy? 👇" if losers else "Which one do you have? 👇")
                  + " Free prices at market.driveyourstyle.net (link in bio)\n\n#pokemon #pokemoncards #pokemontcg #cardcollecting #tcg")
    post = {"date": today.isoformat(), "span": span, "caption": caption, "caption_tiktok": caption_tt, "cards": cards,
            "winners": [c["id"] for c in winners], "losers": [c["id"] for c in losers],
            "slides": [f"{SITE}/social/{today.isoformat()}/slide-{i}.jpg" for i in range(1, len(slides) + 1)],
            "slides_tiktok": [f"{SITE}/social/{today.isoformat()}/tt-{i}.jpg" for i in range(1, len(tt) + 1)],
            "short": f"{SITE}/social/{today.isoformat()}/short.mp4" if video else None,
            "short_title": (f"$100 in this Pokémon card {ago} is now ${worth(top):.0f} 📈 "
                            + ("Winners & losers #pokemon" if losers else "Is it worth buying now? #pokemon"))[:100]}
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
