"""Twice-weekly "How to use market.driveyourstyle.net" posts: one free tool per post, shown with real
screenshots of the live site in a phone frame.

    python tools/howto_social.py SITE_DIR data/social-howto [--date YYYY-MM-DD] [--feature KEY] [--force] [--offline]

SITE_DIR is the built site (served locally while the screenshots are taken). Each run picks the next
feature not yet posted in the current cycle (no repeats until every feature has had a turn; later
cycles use the alternate hook and a different example card, so posts never look the same).
Writes <out>/<date>/slide-N.jpg (1080x1350), tt-N.jpg (1080x1920), short.mp4, post.json and
<out>/latest.json. The nightly job runs it on Tuesdays and Fridays and copies it to /social-howto/.
"""
import functools
import http.server
import json
import os
import re
import socketserver
import sys
import threading
import urllib.request
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from social import BASE, FONT_CSS, LOGO, esc, money  # noqa: E402

SITE = "https://market.driveyourstyle.net"
TAGS = "#pokemontcg #pokemoncards #pokemon #tcg #onepiecetcg #tradingcards #cardcollector #pokemoncollector #pokemoninvesting #driveyourstyle"
SKIP = re.compile(r"prerelease|\[staff\]|code card|jumbo|oversize|stamp", re.I)


def base(n):
    n = re.sub(r"\s*\([^)]*\)", "", n)
    return re.sub(r"\s+-\s+[\w/*-]+$", "", n).strip()


def examples(site, week):
    """Example Pokémon cards for the screenshots, rotating weekly: modern cards $40-$400 (with PSA 10 sales when graded prices are on)."""
    d = os.path.join(site, "data")
    rows = json.load(open(os.path.join(d, "grading.json")))["rows"]
    graded = json.load(open(os.path.join(d, "graded.json"))).get("cards", {})
    seen, pool = set(), []
    for r in sorted(rows, key=lambda r: -r[3]):
        g = (graded.get(str(r[0])) or {}).get("g") or {}
        if r[7] != "pokemon" or r[8] != "modern" or not (4000 <= r[3] <= 40000) or SKIP.search(r[2]):
            continue
        if graded and (not g.get("psa10") or not (1.5 * r[3] <= g["psa10"][0] <= 30 * r[3])):    # graded prices may be off
            continue
        b = base(r[2])
        if b in seen:
            continue
        seen.add(b)
        pool.append({"id": r[0], "g": r[1], "n": r[2], "p": r[3], "name": b, "no": r[6]})
    if not pool:
        raise SystemExit("howto: no example cards found")
    k = (week * 7) % len(pool)
    return pool[k:] + pool[:k]


# ---------- the features (two hooks each: first cycle uses hook 0, the next hook 1, ...) ----------
def features(ex):
    c, cards = ex[0], ex[:6]
    prod = f"product.html?id={c['id']}&set={c['g']}"
    binder = {"name": "My binder", "items": [{"id": x["id"], "g": x["g"], "n": x["n"], "qty": 1, "paid": round(x["p"] * 0.72 / 100) * 100} for x in cards]}
    want = dict(binder, items=[], want=[{"k": f"{x['id']}|", "id": x["id"], "g": x["g"], "n": x["n"], "at": x["p"],
                                          "max": round(x["p"] * (1.1 if i % 2 == 0 else 0.85) / 100) * 100, "ts": 0} for i, x in enumerate(ex[6:11])])
    return [
        {"key": "price", "cover": 2, "tag": "Free price check",
         "hooks": [("What's your card", "worth today?"), ("Stop guessing", "card prices")],
         "sub": "Look up any card in 5 seconds. Free, no sign-up.",
         "steps": [("Search any card", "Name, set or card number. 120,000+ cards across 10 games.", {"url": f"search.html?q={c['name']}"}),
                   ("See today's price", "Market price updated every night, plus the price chart.", {"url": prod, "scroll": ".price-big"}),
                   ("See the cheapest listing", "Lowest listing vs recent sales, plus condition prices.", {"url": prod, "scroll": ".pb"})],
         "lines": [f"Example: {c['name']} is {money(c['p'])} today.", "1. Search any card by name, set or number", "2. See today's market price and its price chart",
                   "3. Compare the cheapest listing with recent sales"],
         "yt": "What's your Pokémon card worth? 🔎 Check any card FREE in 5 seconds #pokemon"},
        {"key": "grading", "tag": "Grading calculator",
         "hooks": [("Is your card", "worth grading?"), ("Don't waste money", "on grading")],
         "sub": "See which cards actually pay off at PSA, CGC, BGS or TAG.",
         "steps": [("Set your real cost", "Pick the grader, your fee and your odds of a 10.", {"url": "grading.html"}),
                   ("See what's worth it", "Every card with its break-even graded price.", {"url": "grading.html", "scroll": "#gr-list"}),
                   ("Check one card", "Run the numbers for any card: grade it, keep it raw, or buy the slab.", {"url": prod, "scroll": "#gcalc"})],
         "lines": ["1. Set your grading company, fee and your odds of a 10", "2. See the price a slab needs to sell for before grading pays off",
                   f"3. Check any single card (e.g. {c['name']}: raw {money(c['p'])})"],
         "yt": "Is your Pokémon card worth grading? 🤔 Free PSA grading calculator #pokemon"},
        {"key": "centering", "cover": 2, "tag": "Centering check",
         "hooks": [("Check centering", "before you grade"), ("Will it get", "a PSA 10?")],
         "sub": "Measure your card's centering with your phone camera. Free.",
         "steps": [("Snap the front", "Lay it flat on a dark surface, shoot straight down.", {"url": "centering.html"}),
                   ("Line up the borders", "Drag the lines to the card edges and the art border.", {"url": "centering.html", "upload": c["id"]}),
                   ("Get your best grade", "Left/right and top/bottom % with the PSA, CGC and BGS limits.", {"url": "centering.html", "upload": c["id"], "scroll": "#cz-res"})],
         "lines": ["1. Take a photo of the front (raw, sleeved or slabbed all work)", "2. Line up the edges and the art border",
                   "3. See your centering % and the best PSA, CGC and BGS grade it allows", "Your photo stays on your phone. Nothing is uploaded."],
         "yt": "Will your Pokémon card get a PSA 10? 📏 Free centering check #pokemon"},
        {"key": "collection", "cover": 2, "tag": "Collection tracker",
         "hooks": [("What's your binder", "worth?"), ("Track your", "collection value")],
         "sub": "Add your cards and watch the total value update every night.",
         "steps": [("Add your cards", "Search, scan with your camera or tap + on any card.", {"url": f"search.html?q={cards[1]['name']}"}),
                   ("See the total value", "What you paid vs what it's worth today.", {"url": "collection.html", "ls": binder, "scroll": "#stats"}),
                   ("Watch it move", "Every card with today's price and change.", {"url": "collection.html", "ls": binder, "scroll": "#list"})],
         "lines": ["1. Add cards by search, camera scan or the + button", "2. Enter what you paid to see your gain or loss",
                   "3. Values update every night. Sign in to sync it across your phone and computer"],
         "yt": "What's your Pokémon binder worth? 📒 Free collection tracker #pokemon"},
        {"key": "want", "cover": 2, "tag": "Want list",
         "hooks": [("Never overpay", "at a card show"), ("Know your", "max price")],
         "sub": "Save the cards you're hunting with the most you'd pay.",
         "steps": [("Tap ♥ on any card", "Saves it to your Want list.", {"url": f"search.html?q={ex[6]['name']}"}),
                   ("Set your max price", "We flag it when the market drops under your max.", {"url": "watchlist.html", "ls": want}),
                   ("Open it at the show", "Today's price on every card you want, right in your pocket.", {"url": "watchlist.html", "ls": want, "scroll": "#list"})],
         "lines": ["1. Tap ♥ on any card to add it to your Want list", "2. Set the most you'd pay", "3. Pull it up at a show or shop to know a good deal on the spot"],
         "yt": "Never overpay for Pokémon cards again 💸 Free want list with max prices #pokemon"},
        {"key": "intel", "tag": "Market intel",
         "hooks": [("Read the card market", "in 30 seconds"), ("Is the market", "up or down?")],
         "sub": "A free daily brief on what's rising and cooling.",
         "steps": [("Today's brief", "One short read on what moved the market.", {"url": "intel.html"}),
                   ("Market mood", "How many cards are rising vs falling this week.", {"url": "intel.html", "scroll": "#s-pulse"}),
                   ("Steady risers", "Cards with week-long gains, not one-day spikes.", {"url": "intel.html", "scroll": "#s-sig"})],
         "lines": ["1. Read the daily market brief", "2. Check the market mood: rising vs cooling cards", "3. See steady risers by game, not one-day spikes"],
         "yt": "Is the Pokémon card market up or down? 📊 Free daily market brief #pokemon"},
        {"key": "calendar", "tag": "Release calendar",
         "hooks": [("Every TCG release date", "in one place"), ("Don't miss", "the next drop")],
         "sub": "Pokémon, One Piece, Lorcana, Riftbound and more.",
         "steps": [("Upcoming sets", "Release dates for 10 games, sorted by date.", {"url": "calendar.html"}),
                   ("Filter your game", "Just Pokémon, just One Piece, or everything.", {"url": "calendar.html?game=pokemon", "act": "document.querySelector('#game [data-g=pokemon], #game button:nth-child(2)')?.click()"}),
                   ("Check what dropped", "Sealed prices for sets released in the last 90 days.", {"url": "calendar.html", "scroll": "#released"})],
         "lines": ["1. See upcoming release dates for 10 TCGs", "2. Filter to the game you play or collect", "3. Check how recent sets are holding their price"],
         "yt": "Every Pokémon & One Piece release date in one place 📅 Free TCG calendar #pokemon"},
        {"key": "sets", "cover": 2, "tag": "Set values",
         "hooks": [("Which set is", "worth ripping?"), ("The chase cards", "in every set")],
         "sub": "Every card and sealed product in a set, with today's price.",
         "steps": [("Pick a set", "Every set by era, with its booster box price.", {"url": "sets.html"}),
                   ("See the chase cards", "Sorted by price, so you know what you're chasing.", {"url": f"set.html?id={c['g']}", "scroll": "#grid"}),
                   ("Check the sealed", "Booster box, ETB and bundle prices in the same place.", {"url": f"set.html?id={c['g']}&tab=sealed", "scroll": "#grid"})],
         "lines": ["1. Pick any set", "2. See every card sorted by price, chase cards first", "3. Compare the sealed prices before you buy a box"],
         "yt": "Which Pokémon set is worth ripping? 📦 Every chase card + sealed price FREE #pokemon"},
    ]


# ---------- screenshots ----------
def serve(site):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=site)
    h.log_message = lambda *a: None
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"


def card_photo(pid, out, offline):
    path = os.path.join(out, "_card.jpg")
    if offline:
        return os.environ["FAKE_CARD"]
    req = urllib.request.Request(f"https://tcgplayer-cdn.tcgplayer.com/product/{pid}_in_1000x1000.jpg", headers={"User-Agent": "Mozilla/5.0"})
    open(path, "wb").write(urllib.request.urlopen(req, timeout=30).read())
    # a photo-like shot: the card on a dark surface
    from PIL import Image
    im = Image.open(path).convert("RGB")
    bg = Image.new("RGB", (im.width + 260, im.height + 320), (22, 22, 26))
    bg.paste(im, (130, 160))
    bg.save(path, quality=92)
    return path


def shoot(browser, url, spec, path, out, offline):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    if spec.get("ls"):
        ctx.add_init_script("try{localStorage.setItem('dys-collection'," + json.dumps(json.dumps(spec["ls"])) + ")}catch(e){}")
    if offline:
        ctx.route(re.compile(r"^https?://(?!127\.0\.0\.1)"), lambda r: r.fulfill(path=os.environ["FAKE_CARD"], content_type="image/jpeg")
                  if r.request.resource_type == "image" else r.abort())
    pg = ctx.new_page()
    pg.goto(url, wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(1200)
    if spec.get("upload"):
        try:
            pg.set_input_files("#cz-file", card_photo(spec["upload"], out, offline))
            pg.wait_for_timeout(2500)
        except Exception as e:
            print(f"howto: upload failed on {url}: {e}")
    if spec.get("act"):
        try:
            pg.evaluate(spec["act"])
            pg.wait_for_timeout(800)
        except Exception:
            pass
    if spec.get("scroll"):
        pg.evaluate("""(sel) => { const el = sel.split(',').map(s => document.querySelector(s.trim())).find(Boolean);
            if (el) window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 96); }""", spec["scroll"])
        pg.wait_for_timeout(900)
    pg.screenshot(path=path)
    ctx.close()


# ---------- slides ----------
PHONE = ("<div style=\"width:{w}px;height:{h}px;border-radius:{r}px;background:#16161c;padding:{p}px;"
         "box-shadow:0 40px 100px rgba(0,0,0,.7),0 0 0 3px #2a2a33,0 0 60px rgba(124,92,255,.25)\">"
         "<img src=\"file://{img}\" style=\"display:block;width:100%;height:100%;object-fit:cover;object-position:top;border-radius:{ri}px\"></div>")


def phone(img, w, ratio=844 / 390):
    h = round(w * ratio)
    p = round(w * .03)
    return PHONE.format(w=w + 2 * p, h=h + 2 * p, r=round(w * .14), p=p, img=os.path.abspath(img), ri=round(w * .11))


def cover(f, hook, img):
    return f"""<div class="slide">
<div class="top"><img class="logo" src="file://{LOGO}"><div class="tag">{esc(f['tag'])}</div></div>
<div style="display:flex;gap:44px;margin-top:60px;flex:1">
 <div style="flex:1;display:flex;flex-direction:column">
  <div style="font-family:'Barlow Condensed';font-weight:800;font-size:{120 if max(len(hook[0]), len(hook[1])) <= 12 else 100}px;line-height:.92;text-transform:uppercase">{esc(hook[0])}<br><span class="holo">{esc(hook[1])}</span></div>
  <div style="margin-top:30px;font-size:38px;line-height:1.3;color:#d8d5cf">{esc(f['sub'])}</div>
  <div style="margin-top:auto;font-family:'Barlow Condensed';font-weight:700;font-size:40px;letter-spacing:.04em;color:#3ee08f">FREE · NO SIGN-UP NEEDED</div>
 </div>
 <div style="align-self:flex-end">{phone(img, 400)}</div>
</div>
<div class="bar" style="margin:34px 0 26px"></div>
<div class="foot"><span>Swipe: how to use it →</span><span>market.driveyourstyle.net</span></div></div>"""


def step(n, total, title, text, img):
    return f"""<div class="slide" style="align-items:center;text-align:center">
<div class="top" style="width:100%"><img class="logo" src="file://{LOGO}" style="height:72px"><div style="font-family:'Barlow Condensed';font-weight:800;font-size:44px;letter-spacing:.1em;color:#bdb9b2">STEP {n}/{total}</div></div>
<div style="margin-top:26px;font-family:'Barlow Condensed';font-weight:800;font-size:76px;line-height:1;text-transform:uppercase"><span class="holo">{n}.</span> {esc(title)}</div>
<div style="margin-top:14px;font-size:34px;line-height:1.3;color:#d8d5cf;max-width:900px">{esc(text)}</div>
<div style="margin-top:30px">{phone(img, 490, 720 / 390)}</div></div>"""


def cta(f):
    return f"""<div class="slide" style="justify-content:center;align-items:center;text-align:center">
<img src="file://{LOGO}" style="height:190px">
<div style="margin-top:64px;font-family:'Barlow Condensed';font-weight:800;font-size:100px;line-height:.95;text-transform:uppercase">Try it free<br><span class="holo">right now</span></div>
<div style="margin-top:34px;font-size:40px;color:#d8d5cf;max-width:860px">{esc(f['tag'])} and more free tools for Pokémon, One Piece, Lorcana and 7 more games.</div>
<div style="margin-top:56px;font-family:'Barlow Condensed';font-weight:700;font-size:56px;letter-spacing:.04em;border:4px solid #f2f0eb;padding:16px 34px 12px">market.driveyourstyle.net</div>
<div class="bar" style="width:100%;margin-top:80px"></div>
<div class="foot" style="width:100%;margin-top:26px"><span>Link in bio</span><span>Save this for later 🔖</span></div></div>"""


def main(argv):
    site, out_root = argv[0], argv[1]
    today = date.fromisoformat(argv[argv.index("--date") + 1]) if "--date" in argv else date.today()
    offline = "--offline" in argv
    os.makedirs(out_root, exist_ok=True)
    hpath = os.path.join(out_root, "history.json")
    try:
        history = json.load(open(hpath))
    except (OSError, ValueError):
        history = []
    history = [h for h in history if h["date"] != today.isoformat()]
    ex = examples(site, today.isocalendar()[1])
    feats = features(ex)
    keys = [f["key"] for f in feats]
    if "--feature" in argv:
        key = argv[argv.index("--feature") + 1]
    else:
        n_done = len(history)
        cycle_used = [h["key"] for h in history[n_done - n_done % len(keys):]] if n_done % len(keys) else []
        key = next(k for k in keys if k not in cycle_used)
    f = next(x for x in feats if x["key"] == key)
    cycle = sum(1 for h in history if h["key"] == key)
    hook = f["hooks"][cycle % len(f["hooks"])]
    out = os.path.join(out_root, today.isoformat())
    os.makedirs(out, exist_ok=True)

    from playwright.sync_api import sync_playwright
    srv, root = serve(site)
    shots = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for i, (_, _, spec) in enumerate(f["steps"], 1):
            path = os.path.join(out, f"_shot-{i}.png")
            shoot(b, root + spec["url"], spec, path, out, offline)
            shots.append(path)
        srv.shutdown()
        slides = [cover(f, hook, shots[f.get('cover', 1) - 1])] + [step(i, len(shots), t, d, shots[i - 1]) for i, (t, d, _) in enumerate(f["steps"], 1)] + [cta(f)]
        pg = b.new_page(viewport={"width": 1080, "height": 1350})
        if offline:
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
                         foot="Free tools · market.driveyourstyle.net")
        b.close()
    for s in shots + [os.path.join(out, "_card.jpg")]:
        if os.path.exists(s):
            os.remove(s)
    from tiktok import make_short
    video = make_short(tt, os.path.join(out, "short.mp4"), per=3.6)

    first = f"🛠️ {hook[0]} {hook[1]}? Here's a free tool for it" if not hook[1].endswith("?") else f"🛠️ {hook[0]} {hook[1]} Here's a free tool for it"
    caption = "\n".join([first, "", f"{f['tag']} on market.driveyourstyle.net (link in bio):", *f["lines"], "",
                         "Free, no sign-up. Pokémon, One Piece, Lorcana, Riftbound and 6 more games, prices updated every night.",
                         "Save this for your next card show 🔖", "", TAGS])
    caption_tt = (f"{hook[0]} {hook[1]}{'' if hook[1].endswith('?') else ''} 👀 Free {f['tag'].lower()} at market.driveyourstyle.net (link in bio)\n\n"
                  "Save this for later 🔖\n\n#pokemon #pokemoncards #pokemontcg #tcg #cardcollecting")
    web = f"{SITE}/social-howto/{today.isoformat()}"
    post = {"date": today.isoformat(), "post": True, "feature": key, "tag": f["tag"], "hook": " ".join(hook),
            "caption": caption, "caption_tiktok": caption_tt, "title": f"{f['tag']} 🛠️",
            "slides": [f"{web}/slide-{n}.jpg" for n in range(1, len(slides) + 1)],
            "slides_tiktok": [f"{web}/tt-{n}.jpg" for n in range(1, len(tt) + 1)],
            "short": f"{web}/short.mp4" if video else None,
            "short_title": f["yt"][:100], "link": f"{SITE}/?ref=howto-{key}"}
    json.dump(post, open(os.path.join(out, "post.json"), "w"), indent=1, ensure_ascii=False)
    json.dump(post, open(os.path.join(out_root, "latest.json"), "w"), ensure_ascii=False)
    history.append({"date": today.isoformat(), "key": key})
    json.dump(history[-60:], open(hpath, "w"))
    print(f"howto: made {len(slides)} slides for '{key}' ({' '.join(hook)})")


if __name__ == "__main__":
    main(sys.argv[1:])
