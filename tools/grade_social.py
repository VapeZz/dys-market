"""'Grade it?' carousel: 5 cheap raw cards whose PSA 10 sells for 10x+ raw, one game per post.

    python tools/grade_social.py SPEC.json SITE_DIR OUT_DIR

SPEC.json: {"date": "YYYY-MM-DD", "game": "pokemon", "cards": [{"id", "name", "no", "gid", "raw", "p10", "sold"}, ...]}
  raw  = TCGplayer market price (our own nightly data), dollars
  p10  = median eBay SOLD price of PSA 10 copies over the last 30 days (Buy It Now + auctions), dollars,
         checked by hand on eBay's sold listings right before posting
  sold = PSA 10 sales on eBay in that window (text, e.g. "16" or "22+")
  days = optional, the sold window in days (30 by default; 60 for slower games)
3 to 5 cards: smaller games often don't have 5 that qualify.
No PokemonPriceTracker data is used anywhere in these posts.

Writes OUT_DIR/<date>/slide-1..7.jpg (1080x1350, Instagram/Facebook), tt-1..7.jpg (1080x1920, TikTok/Story),
short.mp4 (YouTube Short with its own music), post.json, OUT_DIR/latest.json and OUT_DIR/history.json
(card ids already featured, so a card doesn't come back within 8 weeks).
"""
import io
import json
import os
import re
import sys
import urllib.request
from datetime import date, timedelta

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from social import FONT_CSS, LOGO  # noqa: E402

SITE = "https://market.driveyourstyle.net"
EPN = "5339229587"   # eBay Partner Network campaign id (same as the market site's eBay links)
PSA_FEE, SHIP = 59.99, 15.0        # PSA's cheapest open tier (Value tiers paused) + shipping both ways
GAMES = {  # slug: (label, hashtags)
    "pokemon": ("Pokémon", "#pokemon #pokemoncards #pokemontcg #psa #psagrading #cardgrading #tcg"),
    "one-piece": ("One Piece", "#onepiecetcg #onepiececardgame #optcg #psa #psagrading #cardgrading #tcg"),
    "lorcana": ("Lorcana", "#lorcana #disneylorcana #lorcanatcg #psa #psagrading #cardgrading #tcg"),
    "riftbound": ("Riftbound", "#riftbound #riftboundtcg #leagueoflegends #psa #psagrading #cardgrading #tcg"),
    "gundam": ("Gundam", "#gundamcardgame #gundamtcg #psa #psagrading #cardgrading #tcg"),
    "union-arena": ("Union Arena", "#unionarena #unionarenatcg #psa #psagrading #cardgrading #tcg"),
    "pokemon-jp": ("Japanese Pokémon", "#pokemon #pokemoncards #japanesepokemon #pokemontcg #psa #psagrading #tcg"),
    "yugioh": ("Yu-Gi-Oh!", "#yugioh #yugiohcards #yugiohtcg #psa #psagrading #cardgrading #tcg"),
    "dragon-ball-fusion-world": ("Dragon Ball", "#dragonball #dragonballsuper #fusionworld #dbsfusionworld #psa #cardgrading #tcg"),
    "palworld": ("Palworld", "#palworld #palworldtcg #psa #cardgrading #tcg"),
}


def profit(raw, p10):
    """What a PSA 10 nets after eBay fees (13.25% + $0.40), the PSA fee, shipping and the raw card itself."""
    return p10 * (1 - .1325) - .40 - raw - PSA_FEE - SHIP


def m(v, cents=True):
    return f"${v:,.2f}" if cents and v < 1000 else f"${v:,.0f}"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (DriveYourStyleMarket)"})
    return urllib.request.urlopen(req, timeout=30).read()


def card_png(pid, out, game="pokemon", no=""):
    im = None
    if game == "one-piece" and re.fullmatch(r"[A-Z]{2,3}\d{2}-\d{3}", no or ""):
        try:   # TCGplayer's One Piece photos carry a SAMPLE watermark: use Bandai's official card image
            im = Image.open(io.BytesIO(get(f"https://en.onepiece-cardgame.com/images/cardlist/card/{no}.png"))).convert("RGB")
        except Exception:
            im = None
    if im is None:
        im = Image.open(io.BytesIO(get(f"https://tcgplayer-cdn.tcgplayer.com/product/{pid}_in_1000x1000.jpg"))).convert("RGB")
    box = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255))).convert("L").point(lambda v: 255 if v > 18 else 0).getbbox()
    path = os.path.join(out, f"card-{pid}.png")
    (im.crop(box) if box else im).save(path)
    return os.path.abspath(path)


def logo_png(url, gid, out):
    if not url:
        return None
    try:
        path = os.path.join(out, f"logo-{gid}.png")
        open(path, "wb").write(get(url))
        Image.open(path).verify()
        return os.path.abspath(path)
    except Exception:
        return None


CSS = """*{box-sizing:border-box;margin:0}
body{width:1080px;height:%(h)dpx;overflow:hidden;background:#050404;color:#f2f0eb;font-family:'Space Grotesk',sans-serif}
.s{position:relative;width:1080px;height:%(h)dpx;padding:%(pad)dpx 64px;display:flex;flex-direction:column;align-items:center;
 background:radial-gradient(1000px 700px at 100%% 0%%,rgba(124,92,255,.32),transparent 60%%),radial-gradient(800px 600px at 0%% 100%%,rgba(0,200,255,.18),transparent 60%%),#050404}
.bc{font-family:'Barlow Condensed';font-weight:800;text-transform:uppercase;line-height:.95}
.holo{background:linear-gradient(90deg,#5ee7ff,#a78bfa 45%%,#3ee08f);-webkit-background-clip:text;background-clip:text;color:transparent}
.top{width:100%%;display:flex;justify-content:space-between;align-items:center}
.logo{height:%(logo)dpx}.muted{color:#bdb9b2}
.card{border-radius:%(rad)dpx;box-shadow:0 30px 90px rgba(0,0,0,.7),0 0 0 2px rgba(255,255,255,.08)}
.pill{border-radius:22px;padding:%(pp)dpx 26px;text-align:center}
.raw{background:rgba(242,240,235,.08);border:3px solid rgba(242,240,235,.25)}
.ten{background:rgba(62,224,143,.12);border:3px solid #3ee08f}
.lab{font-family:'Barlow Condensed';font-weight:700;font-size:%(lab)dpx;letter-spacing:.12em;text-transform:uppercase;color:#bdb9b2}
.big{font-family:'Barlow Condensed';font-weight:800;font-size:%(big)dpx;line-height:1}
.chip{font-family:'Barlow Condensed';font-weight:700;font-size:32px;letter-spacing:.14em;text-transform:uppercase;border:3px solid #f2f0eb;padding:8px 18px 6px}"""
SIZES = {   # tall = 1080x1920 (TikTok, Story, Short), feed = 1080x1350 (Instagram / Facebook carousel)
    "tall": dict(h=1920, pad=70, logo=84, rad=26, pp=22, lab=38, big=112, card=900, fan=500, hook=150, hook2=190, gap=40),
    "feed": dict(h=1350, pad=52, logo=70, rad=18, pp=14, lab=30, big=84, card=640, fan=330, hook=104, hook2=132, gap=22),
}
PAGE = "<!doctype html><html><head><meta charset='utf-8'><style>%s%s</style></head><body>%s</body></html>"


def cover(cards, game, z):
    top = max(cards, key=lambda c: c["p10"] / c["raw"])
    mult = max(c["p10"] / c["raw"] for c in cards)
    n, step = len(cards), 140 if z["h"] > 1500 else 150
    mid, left0 = (n - 1) / 2, 20 + (5 - n) * step / 2
    fan = "".join(f"<img class='card' src='file://{c['img']}' style='position:absolute;height:{z['fan']}px;left:{left0 + i * step:.0f}px;"
                  f"top:{abs(i - mid) * (40 if z['h'] > 1500 else 26):.0f}px;transform:rotate({(i - mid) * 7:.1f}deg)'>" for i, c in enumerate(cards))
    big = z["h"] > 1500
    return f"""<div class='s'><div class='top'><img class='logo' src='file://{LOGO}'><span class='chip'>Grade it?</span></div>
<div class='bc' style='margin-top:{90 if big else 34}px;font-size:{z['hook']}px;text-align:center'>A ${top['raw']:.0f} card</div>
<div class='bc' style='margin-top:8px;font-size:{76 if big else 54}px;text-align:center'>sells for</div>
<div class='bc holo' style='margin-top:8px;font-size:{z['hook2']}px;text-align:center'>{m(top['p10'], False)}</div>
<div class='bc' style='margin-top:6px;font-size:{76 if big else 54}px;text-align:center'>in a PSA 10</div>
<div style='margin-top:{40 if big else 20}px;font-size:{44 if big else 34}px;text-align:center;max-width:900px' class='muted'>{len(cards)} cheap {GAMES[game][0]} cards that sell for up to <b style='color:#f2f0eb'>{mult:.0f}×</b> raw once they grade a 10</div>
<div style='position:relative;width:952px;height:{z['fan'] + 180}px;margin-top:{60 if big else 30}px'>{fan}</div>
<div class='bc' style='margin-top:auto;font-size:{64 if big else 48}px'>Swipe for all {len(cards)} →</div></div>"""


def slide(i, c, z, n=5):
    big = z["h"] > 1500
    head = (f"<img src='file://{c['logo']}' style='max-height:{170 if big else 110}px;max-width:{560 if big else 460}px'>" if c.get("logo")
            else f"<span class='bc' style='font-size:{52 if big else 40}px'>{c['set']}</span>")
    return f"""<div class='s'><div class='top'>{head}<img class='logo' src='file://{LOGO}'></div>
<img class='card' src='file://{c['img']}' style='margin-top:{z['gap']}px;height:{z['card']}px'>
<div class='bc' style='margin-top:{z['gap']}px;font-size:{76 if big else 58}px;text-align:center'>{c['name']} <span class='muted' style='font-size:{52 if big else 40}px'>{c['no']}</span></div>
<div style='margin-top:{30 if big else 18}px;width:100%;display:flex;gap:26px;align-items:center;justify-content:center'>
 <div class='pill raw' style='flex:1'><div class='lab'>Raw</div><div class='big'>{m(c['raw'])}</div></div>
 <div class='bc' style='font-size:{90 if big else 66}px'>→</div>
 <div class='pill ten' style='flex:1.25'><div class='lab' style='color:#3ee08f'>PSA 10</div><div class='big holo'>{m(c['p10'])}</div></div></div>
<div style='margin-top:{34 if big else 18}px;font-size:{42 if big else 32}px;text-align:center'><b class='holo' style='font-size:{52 if big else 40}px'>{c['p10'] / c['raw']:.0f}× raw</b> · {c['sold']} PSA 10s sold on eBay in {c.get('days', 30)} days</div>
<div style='margin-top:{18 if big else 8}px;font-size:{36 if big else 28}px;text-align:center' class='muted'>Gets a 10? About <b style='color:#3ee08f'>+{m(profit(c['raw'], c['p10']))}</b> profit after the PSA fee, shipping and eBay fees</div>
<div style='position:absolute;bottom:{58 if big else 34}px;left:64px;right:64px;display:flex;justify-content:space-between;align-items:center'><span class='muted' style='font-size:{26 if big else 22}px'>PSA 10: median eBay sold price · Raw: TCGplayer market</span><span class='bc' style='font-size:{40 if big else 32}px'>{i} / {n}</span></div></div>"""


def cta(game, day, z, cards=()):
    big = z["h"] > 1500
    return f"""<div class='s' style='justify-content:center'><img src='file://{LOGO}' style='height:{150 if big else 110}px'>
<div class='bc' style='margin-top:{80 if big else 50}px;font-size:{130 if big else 100}px;text-align:center'>Check <span class='holo'>your</span><br>cards free</div>
<div style='margin-top:{44 if big else 30}px;font-size:{44 if big else 34}px;text-align:center;max-width:880px' class='muted'>Live raw prices on 150,000+ cards across Pokémon, One Piece, Lorcana, Riftbound and more, plus a free centering check before you grade.</div>
<div class='bc' style='margin-top:{70 if big else 44}px;font-weight:700;font-size:{62 if big else 50}px;border:4px solid #f2f0eb;padding:18px 40px 14px'>market.driveyourstyle.net</div>
<div class='bc holo' style='margin-top:{90 if big else 54}px;font-size:{56 if big else 44}px;letter-spacing:.04em'>Follow for more grading picks</div>
<div style='position:absolute;bottom:{60 if big else 36}px;left:64px;right:64px;font-size:{28 if big else 22}px;text-align:center' class='muted'>PSA 10 = median eBay sold price, last {max(c.get('days', 30) for c in cards)} days. Raw = TCGplayer market price, {date.fromisoformat(day).strftime('%b %-d')}. Not every card grades a 10: check centering and surface first. Not financial advice.</div></div>"""


def render(cards, game, day, out):
    total = len(cards)
    bodies = [lambda z: cover(cards, game, z)] + [lambda z, i=i, c=c: slide(i, c, z, total) for i, c in enumerate(cards, 1)] + [lambda z: cta(game, day, z, cards)]
    with sync_playwright() as p:
        b = p.chromium.launch()
        for size, prefix in (("feed", "slide"), ("tall", "tt")):
            z = SIZES[size]
            pg = b.new_page(viewport={"width": 1080, "height": z["h"]})
            tmp = os.path.abspath(os.path.join(out, "_s.html"))
            for n, body in enumerate(bodies, 1):
                open(tmp, "w", encoding="utf-8").write(PAGE % (FONT_CSS, CSS % z, body(z)))
                pg.goto("file://" + tmp, wait_until="networkidle")
                pg.evaluate("document.fonts.ready")
                pg.screenshot(path=os.path.join(out, f"{prefix}-{n}.jpg"), type="jpeg", quality=90)
            pg.close()
            os.remove(tmp)
        b.close()


def captions(cards, game, day):
    label, tags = GAMES[game]
    top = max(cards, key=lambda c: c["p10"] / c["raw"])
    lo, hi = min(c["p10"] / c["raw"] for c in cards), max(c["p10"] / c["raw"] for c in cards)
    first = f"A ${top['raw']:.0f} {label} card sells for {m(top['p10'], False)} in a PSA 10 👀"
    lines = [f"{i}. {c['name']} {c['no']} ({c['set']}): {m(c['raw'])} raw → {m(c['p10'], False)} PSA 10" for i, c in enumerate(cards, 1)]
    n, days = len(cards), max(c.get("days", 30) for c in cards)
    note = f"PSA 10 = median eBay sold price over the last {days} days. Raw = TCGplayer market price. Not every card grades a 10, so check centering first (free centering tool at market.driveyourstyle.net)."
    cap = (f"{first}\n\n{n} cheap {label} cards selling for {lo:.0f}–{hi:.0f}× raw once they grade a 10:\n\n" + "\n".join(lines) + f"\n\n{note}\n\nWhich one would you grade? 👇\n\n"
           f"🛒 eBay links for all {n} (affiliate links): market.driveyourstyle.net/social-grade (link in bio)\n\n{tags}")
    cap_tt = f"{first} {n} cheap {label} cards worth grading. Which one would you send in? 👇 eBay links for all {n} in bio {tags}"
    short = f"These ${min(c['raw'] for c in cards):.0f}–${max(c['raw'] for c in cards):.0f} {label} cards sell for {lo:.0f}–{hi:.0f}× in a PSA 10 👀 Would you grade #1?"
    return first, cap, cap_tt, (short + (" #" + game.replace("-", "") if len(short) < 85 else ""))[:100]


def ebay(q, day, sold=False):
    """eBay search link tagged with our eBay Partner Network campaign."""
    from urllib.parse import urlencode
    p = {"_nkw": q, "mkcid": "1", "mkrid": "711-53200-19255-0", "siteid": "0", "campid": EPN, "customid": f"grade-{day}", "toolid": "10001", "mkevt": "1"}
    p.update({"LH_Sold": "1", "LH_Complete": "1", "_sop": "13"} if sold else {"LH_BIN": "1", "_sop": "15"})
    return "https://www.ebay.com/sch/i.html?" + urlencode(p)


def page(post, cards, game, day):
    """market.driveyourstyle.net/social-grade/<date>/: the cards with affiliate links (what 'link in bio' opens)."""
    from html import escape as e
    label = GAMES[game][0]
    jp = " japanese" if game == "pokemon-jp" else ""
    d = date.fromisoformat(day)
    rows = "".join(f"""<article class="c"><img src="https://tcgplayer-cdn.tcgplayer.com/product/{c['id']}_in_1000x1000.jpg" alt="{e(c['name'])}" loading="lazy">
<div><h2>{i}. {e(c['name'])} <small>{e(c['no'])} · {e(c['set'])}</small></h2>
<p class="p"><span>Raw <b>{m(c['raw'])}</b></span><span>PSA 10 <b class="g">{m(c['p10'])}</b></span><span><b>{c['p10'] / c['raw']:.0f}×</b> raw</span></p>
<p class="m">{e(c['sold'])} PSA 10s sold on eBay in the last {c.get('days', 30)} days. Gets a 10? About +{m(profit(c['raw'], c['p10']))} after the PSA fee, shipping and eBay fees.</p>
<p class="b"><a class="btn" href="{e(ebay(f"{c['name']} {c['no']}{jp}", day))}" target="_blank" rel="sponsored noopener">Buy raw on eBay</a><a class="btn o" href="{e(ebay(f"{c['name']} {c['no']}{jp} PSA 10", day))}" target="_blank" rel="sponsored noopener">Buy a PSA 10</a><a class="btn o" href="{e(ebay(f"{c['name']} {c['no']}{jp} PSA 10", day, True))}" target="_blank" rel="sponsored noopener">See PSA 10 sales</a><a class="btn o" href="../../product.html?id={c['id']}&amp;set={c['gid']}">Price history</a></p></div></article>""" for i, c in enumerate(cards, 1))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(post['first'])} · Drive Your Style</title><meta name="description" content="{len(cards)} cheap {e(label)} cards whose PSA 10 sells for 10x+ raw, with recent eBay sold prices.">
<meta property="og:image" content="{SITE}/social-grade/{day}/slide-1.jpg"><link rel="icon" type="image/png" href="../../assets/favicon.png">
<style>body{{margin:0;background:#050404;color:#f2f0eb;font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}}main{{max-width:760px;margin:0 auto;padding:22px 16px 40px}}
a{{color:#5ee7ff}}h1{{font-size:28px;line-height:1.15;margin:14px 0 6px}}.sub{{color:#bdb9b2;margin:0 0 18px}}.c{{display:grid;grid-template-columns:110px 1fr;gap:16px;padding:16px 0;border-top:1px solid #222}}
.c img{{width:110px;border-radius:8px;background:#151515}}h2{{font-size:19px;margin:0 0 6px}}h2 small{{display:block;font-size:13px;color:#bdb9b2;font-weight:400}}
.p{{display:flex;flex-wrap:wrap;gap:6px 16px;margin:0 0 6px}}.g{{color:#3ee08f}}.m{{color:#bdb9b2;font-size:14px;margin:0 0 10px}}
.b{{display:flex;flex-wrap:wrap;gap:8px;margin:0}}.btn{{display:inline-block;padding:9px 14px;border-radius:10px;background:#3ee08f;color:#050404;font-weight:700;text-decoration:none;font-size:14px}}
.btn.o{{background:none;color:#f2f0eb;border:1px solid #444}}.f{{color:#8f8a84;font-size:13px;margin-top:24px}}.top{{display:flex;justify-content:space-between;align-items:center;font-weight:700}}
@media(max-width:420px){{.c{{grid-template-columns:84px 1fr;gap:12px}}.c img{{width:84px}}}}</style></head>
<body><main><div class="top"><a href="../../index.html?ref=grade" style="color:#f2f0eb;text-decoration:none">DRIVE YOUR STYLE · Market</a><a href="../../links.html">More links</a></div>
<h1>{e(post['first'])}</h1><p class="sub">{len(cards)} cheap {e(label)} cards worth grading · {d.strftime('%B %-d, %Y')}</p>{rows}
<p class="f">PSA 10 = median eBay sold price over the last {max(c.get('days', 30) for c in cards)} days (Buy It Now and auctions). Raw = TCGplayer market price on {d.strftime('%b %-d')}. Prices change; not every card grades a 10, so check centering first with our <a href="../../centering.html">free centering tool</a>. Not financial advice.<br><br>
Affiliate disclosure: eBay links on this page are affiliate links (eBay Partner Network). If you buy through them we may earn a small commission at no extra cost to you.</p></main></body></html>"""


def main(argv):
    spec, site, out_root = json.load(open(argv[0])), argv[1], argv[2]
    day, game = spec["date"], spec["game"]
    out = os.path.join(out_root, day)
    os.makedirs(out, exist_ok=True)
    sets = {s["id"]: s for s in json.load(open(os.path.join(site, "data", "sets.json")))}
    names = json.load(open(os.path.join(site, "data", "meta.json")))["groups"]
    cards = []
    for c in spec["cards"][:5]:
        c.setdefault("days", 30)
        s = sets.get(int(c["gid"]), {})
        set_name = re.sub(r"^[A-Z0-9]{2,6}[a-z]?:\s*", "", names.get(str(c["gid"]), [s.get("n", "")])[0]).replace("SWSH: ", "")
        cards.append(dict(c, raw=float(c["raw"]), p10=float(c["p10"]), sold=str(c["sold"]), set=set_name,
                          img=card_png(c["id"], out, game, c.get("no", "")), logo=logo_png(s.get("lg"), c["gid"], out)))
    if len(cards) < 3:
        raise SystemExit("need at least 3 cards")
    nslides = len(cards) + 2
    render(cards, game, day, out)
    from tiktok import make_short
    for f in os.listdir(out):   # a re-run with fewer cards must not leave old extra slides behind
        if f.startswith(("slide-", "tt-")) and int(f.split("-")[1].split(".")[0]) > nslides:
            os.remove(os.path.join(out, f))
    short = make_short([os.path.join(out, f"tt-{n}.jpg") for n in range(1, nslides + 1)], os.path.join(out, "short.mp4"))
    for f in os.listdir(out):
        if f.startswith(("card-", "logo-")):
            os.remove(os.path.join(out, f))
    first, cap, cap_tt, short_title = captions(cards, game, day)
    url = f"{SITE}/social-grade/{day}"
    post = {"date": day, "game": game, "post": True, "first": first, "caption": cap, "caption_tiktok": cap_tt, "short_title": short_title,
            "slides": [f"{url}/slide-{n}.jpg" for n in range(1, nslides + 1)], "slides_tiktok": [f"{url}/tt-{n}.jpg" for n in range(1, nslides + 1)],
            "story": f"{url}/tt-1.jpg", "short": f"{url}/short.mp4" if short else None,
            "cards": [{k: c[k] for k in ("id", "name", "no", "raw", "p10", "sold", "days")} for c in cards]}
    post["page"] = f"{url}/"
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(page(post, cards, game, day))
    open(os.path.join(out_root, "index.html"), "w", encoding="utf-8").write(   # /social-grade/ always opens the newest picks
        f'<!doctype html><meta charset="utf-8"><title>Cheap cards worth grading</title><meta http-equiv="refresh" content="0; url={day}/"><link rel="canonical" href="{url}/"><a href="{day}/">This week\'s picks</a>')
    for path in (os.path.join(out, "post.json"), os.path.join(out_root, "latest.json")):
        json.dump(post, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    hp = os.path.join(out_root, "history.json")
    hist = json.load(open(hp)) if os.path.exists(hp) else {}
    hist.update({str(c["id"]): day for c in cards})
    keep = (date.fromisoformat(day) - timedelta(days=120)).isoformat()
    json.dump({k: v for k, v in hist.items() if v >= keep}, open(hp, "w"), indent=0)
    print(f"grade social: {game} {day}: " + ", ".join(f"{c['name']} {c['p10'] / c['raw']:.0f}x" for c in cards))


if __name__ == "__main__":
    main(sys.argv[1:])
