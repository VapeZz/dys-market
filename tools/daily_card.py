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

from datetime import timedelta

from social import BASE, FONT_CSS, LOGO, SKIP, clean_name, esc, img, money, pick, short_set

SITE = "https://market.driveyourstyle.net"
TAGS = "#pokemon #pokemoncards #pokemontcg #cardcollecting #tcg"
GAMES = {   # slug: (display name, hashtags, image watermarked on TCGplayer?)
    "pokemon": ("Pokémon", TAGS, False),
    "one-piece": ("One Piece", "#onepiecetcg #onepiececardgame #onepiece #optcg #tcg", True),
    "lorcana": ("Lorcana", "#lorcana #disneylorcana #lorcanatcg #disney #tcg", False),
    "riftbound": ("Riftbound", "#riftbound #leagueoflegends #riftboundtcg #lol #tcg", False),
    "gundam": ("Gundam", "#gundamcardgame #gundam #gundamtcg #gunpla #tcg", False),
    "union-arena": ("Union Arena", "#unionarena #unionarenatcg #anime #animetcg #tcg", False),
}
ROTATION = ["one-piece", "lorcana", "gundam", "riftbound", "union-arena"]   # midday slot, one game per day


def pick_game(site_data, today, game, limit=40):
    """Biggest risers ($5+) among a game's sets from the last 3 years."""
    if game == "pokemon":
        return pick(site_data, today, limit=limit)[:2]
    recent = (today - timedelta(days=3 * 365)).isoformat()
    sets = [s for s in json.load(open(os.path.join(site_data, "sets.json")))
            if s["k"] == game and recent <= (s.get("pub") or "") <= today.isoformat()]
    rows, has7 = [], False
    for st in sets:
        try:
            items = json.load(open(os.path.join(site_data, "set", f"{st['id']}.json")))["items"]
        except (OSError, ValueError):
            continue
        for i in items:
            if i["t"] == "c" and (i.get("p") or 0) >= 500 and not SKIP.search(i["n"]):
                has7 = has7 or (i.get("ch") or {}).get("7") is not None
                rows.append((st, i))
    win = "7" if has7 else "a"
    out = []
    for st, i in rows:
        pct = (i.get("ch") or {}).get(win)
        if pct is None or not (3 <= pct <= 150):
            continue
        out.append({"id": i["id"], "name": clean_name(i["n"]), "set": short_set(st["n"]), "gid": st["id"], "game": game,
                    "now": i["p"], "old": round(i["p"] / (1 + pct / 100)), "pct": pct})
    out.sort(key=lambda c: -c["pct"])
    if not out:   # no price moves yet (new game / short history): feature the newest set's chase cards
        newest = sorted(sets, key=lambda st: st.get("pub") or "", reverse=True)
        for st in newest[:3]:
            for st2, i in sorted((r for r in rows if r[0]["id"] == st["id"]), key=lambda r: -r[1]["p"])[:5]:
                out.append({"id": i["id"], "name": clean_name(i["n"]), "set": short_set(st2["n"]), "gid": st2["id"], "game": game,
                            "now": i["p"], "old": None, "pct": None})
    return out[:limit], win
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


def slides(c, period, vals, game="pokemon"):
    name = c["name"]
    label, _, wm = GAMES.get(game, GAMES["pokemon"])
    if wm:   # TCGplayer's photo carries a SAMPLE watermark: show a big price chart instead of the card
        art_hook = f"""<div style="margin-top:60px;width:900px;padding:40px 30px;border:3px solid rgba(242,240,235,.25);border-radius:30px">
<div style="font-family:'Barlow Condensed';font-weight:800;font-size:{72 if len(name) < 26 else 56}px;line-height:1;text-transform:uppercase">{esc(name)}</div>
<div style="margin-top:14px;font-size:34px;color:#bdb9b2">{esc(c['set'])}</div><div style="margin-top:30px">{spark_svg(vals, 820, 300)}</div></div>"""
        art_price = f"""<div style="margin-top:120px;font-family:'Barlow Condensed';font-weight:800;font-size:110px;line-height:1;text-transform:uppercase" class="holo">{esc(label)}</div>
<div style="margin-top:10px;font-size:36px;color:#bdb9b2;letter-spacing:.1em;text-transform:uppercase">Price check</div>"""
    else:
        art_hook = f"""<div class="card" style="margin-top:44px;width:470px;height:658px;transform:rotate(-3deg)"><img src="{img(c['id'])}"></div>"""
        art_price = f"""<div class="card" style="width:520px;height:728px"><img src="{img(c['id'])}"></div>"""
    hook = f"""<div class="slide" style="height:1920px;padding:170px 80px 400px;align-items:center;text-align:center">
<img src="file://{LOGO}" style="height:100px">
<div class="tag" style="margin-top:50px">{esc(label)} card of the day</div>
<div style="margin-top:44px;font-family:'Barlow Condensed';font-weight:800;font-size:120px;line-height:.95;text-transform:uppercase">{f"This card is<br><span style='color:#3ee08f'>up {c['pct']:.0f}%</span><br>{esc(period)}" if c.get("pct") is not None else f"Chase card<br><span class='holo'>of the set</span>"}</div>
{art_hook}
<div style="margin-top:auto;font-size:38px;color:#bdb9b2">Swipe for the price →</div></div>"""
    price = f"""<div class="slide" style="height:1920px;padding:170px 80px 400px;align-items:center;text-align:center">
{art_price}
<div style="margin-top:46px;font-family:'Barlow Condensed';font-weight:800;font-size:{70 if len(name) < 30 else 56}px;line-height:1.02;text-transform:uppercase">{esc(name)}</div>
<div style="margin-top:12px;font-size:36px;color:#bdb9b2">{esc(c['set'])}</div>
<div style="margin-top:40px;display:flex;gap:60px;align-items:flex-end;justify-content:center">
 <div><div style="font-size:32px;color:#bdb9b2">Market price</div><div style="font-family:'Barlow Condensed';font-weight:800;font-size:130px;line-height:1">{money(c['now'])}</div></div>
 {f"<div><div style=\"font-family:'Barlow Condensed';font-weight:800;font-size:96px;line-height:1;color:#3ee08f\">▲ {c['pct']:.0f}%</div><div style=\"font-size:32px;color:#bdb9b2\">was {money(c['old'])}</div></div>" if c.get("pct") is not None else ""}</div>
<div style="margin-top:30px">{spark_svg(vals, 900, 170)}</div></div>"""
    cta = f"""<div class="slide" style="height:1920px;justify-content:center;align-items:center;text-align:center;padding:170px 80px 400px">
<img src="file://{LOGO}" style="height:200px">
<div style="margin-top:80px;font-family:'Barlow Condensed';font-weight:800;font-size:130px;line-height:.92;text-transform:uppercase">Check <span class="holo">your</span><br>cards free</div>
<div style="margin-top:44px;font-size:44px;color:#d8d5cf;max-width:880px">Live prices on 70,000+ cards. Scan a card with your camera to see what it's worth.</div>
<div style="margin-top:70px;font-family:'Barlow Condensed';font-weight:700;font-size:62px;border:4px solid #f2f0eb;padding:18px 40px 14px">market.driveyourstyle.net</div>
<div style="margin-top:90px;font-family:'Barlow Condensed';font-weight:800;font-size:56px;letter-spacing:.04em;text-transform:uppercase" class="holo">Follow for a card every day</div></div>"""
    return [hook, price, cta]


def render(site_data, c, period, game, out, offline=False):
    bodies = slides(c, period, spark(site_data, c), game)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1920})
        if offline:
            pg.route(re.compile(r"tcgplayer-cdn"), lambda r: r.fulfill(path=os.environ["FAKE_CARD"], content_type="image/jpeg"))
        tmp = os.path.abspath(os.path.join(out, "_slide.html"))
        for n, body in enumerate(bodies, 1):
            open(tmp, "w", encoding="utf-8").write(B % (FONT_CSS, body))
            pg.goto("file://" + tmp, wait_until="networkidle")
            pg.evaluate("document.fonts.ready")
            pg.screenshot(path=os.path.join(out, f"slide-{n}.jpg"), type="jpeg", quality=90)
        b.close()
        os.remove(tmp)
    from tiktok import make_short
    return make_short([os.path.join(out, f"slide-{n}.jpg") for n in range(1, 4)], os.path.join(out, "short.mp4"))


SIDEWAYS = re.compile(r"\bBREAK\b|\bLEGEND\b|jumbo|oversize", re.I)   # landscape cards don't fit the portrait slides


def yt_title(short, c, period, tag):
    """YouTube Shorts title: curiosity hook + question (vidIQ scored this pattern 90 vs 82 for the plain one)."""
    when = "in ONE week" if period == "this week" else "lately"
    for name in (short, short[:40].rsplit(" ", 1)[0]):
        if c["pct"] is not None:
            t = f"{name} jumped {c['pct']:.0f}% {when} 📈 Is it worth buying now? {tag}"
        else:
            t = f"{name} is the chase card of {c['set']} 🔥 Is it worth {money(c['now'])}? {tag}"
        if len(t) <= 100:
            return t
    return t[:100]


def main(argv):
    site_data, out_root = argv[0], argv[1]
    today = date.fromisoformat(argv[argv.index("--date") + 1]) if "--date" in argv else date.today()
    web = f"{SITE}/{os.path.basename(os.path.normpath(out_root))}"
    if "--sample" in argv:   # one preview per game, nothing recorded
        for game in GAMES:
            cards, win = pick_game(site_data, today, game)
            cards = [c for c in cards if not SIDEWAYS.search(c["name"])]
            if not cards:
                print(f"sample {game}: no movers")
                continue
            out = os.path.join(out_root, "samples", game)
            os.makedirs(out, exist_ok=True)
            render(site_data, cards[0], "this week" if win == "7" else "lately", game, out, "--offline" in argv)
            print(f"sample {game}: {cards[0]['name']} ({'+%.0f%%' % cards[0]['pct'] if cards[0]['pct'] is not None else 'chase'})")
        return
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
    if "--rotate" in argv:   # midday slot: today's game first, then the others as fallbacks
        k = today.toordinal() % len(ROTATION)
        order = ROTATION[k:] + ROTATION[:k]
    else:
        order = [argv[argv.index("--game") + 1] if "--game" in argv else "pokemon"]
    c = None
    for game in order:
        cards, win = pick_game(site_data, today, game)
        fresh = [x for x in cards if x["id"] not in recent and not SIDEWAYS.search(x["name"])]
        if fresh:
            c = fresh[0]
            break
    if not c:
        print("daily card: nothing new to feature today; skipping")
        return
    label, tags, _ = GAMES[game]
    period = "this week" if win == "7" else "lately"
    out = os.path.join(out_root, today.isoformat())
    os.makedirs(out, exist_ok=True)
    video = render(site_data, c, period, game, out, "--offline" in argv)
    short = re.sub(r"\s*-\s*\S+/\S+$", "", c["name"])
    hook = (f"{short} is up {c['pct']:.0f}% {period} 📈 now {money(c['now'])}" if c["pct"] is not None
            else f"{short} is the chase card of {c['set']} 🔥 worth {money(c['now'])}")
    caption = (f"{hook}\n\n"
               f"Do you have one? 👇 Check your {label} cards free at market.driveyourstyle.net (link in bio)\n\n{tags}")
    first_tag = tags.split()[0]
    post = {"date": today.isoformat(), "game": game, "card": c, "caption": caption,
            "slides": [f"{web}/{today.isoformat()}/slide-{n}.jpg" for n in range(1, 4)],
            "short": f"{web}/{today.isoformat()}/short.mp4" if video else None,
            "short_title": yt_title(short, c, period, first_tag),
            "title": f"{label} card of the day 📈"}
    json.dump(post, open(os.path.join(out, "post.json"), "w"), indent=1, ensure_ascii=False)
    json.dump(post, open(os.path.join(out_root, "latest.json"), "w"), indent=1, ensure_ascii=False)
    history[str(c["id"])] = today.isoformat()
    json.dump(history, open(hist_path, "w"))
    dirs = sorted(d for d in os.listdir(out_root) if re.match(r"\d{4}-\d{2}-\d{2}$", d))
    for d in dirs[:-14]:
        for f in os.listdir(os.path.join(out_root, d)):
            os.remove(os.path.join(out_root, d, f))
        os.rmdir(os.path.join(out_root, d))
    print(f"daily card ({game}): {c['name']} ({hook}) -> {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
