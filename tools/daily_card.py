"""Daily "Top cards of the day": 3 to 5 cards around one theme, as full-screen slides (1080x1920),
a short video and a caption. Two slots use it: Pokémon (evening) and other TCGs (midday, --rotate).

    python tools/daily_card.py site/data data/social-daily [--date YYYY-MM-DD] [--rotate] [--game G]
        [--theme T] [--trending PATH] [--history PATH] [--sample] [--offline] [--force]

Themes (THEMES): biggest jumps, under $10 and climbing, new highs, biggest drops ("buy the dip?"),
chase cards of the newest set. One theme per weekday (THEME_DAYS); if fewer than 3 cards qualify,
the next theme is tried. The midday slot also rotates games (ROTATION) and falls back to the next game.

Rules (owner's content rules):
- every card shown has its own photo: checked live on TCGplayer's CDN (no stand-ins, no watermarked games)
- no card featured in the last 21 days, or in this week's Trending carousel
- prices are TCGplayer market prices and the caption says so ("Prices: TCGplayer market")

Writes <out>/<date>/slide-N.jpg, short.mp4, post.json and <out>/latest.json. post.json keeps "card"
(the #1 card) for older readers and adds "cards" and "theme". The nightly workflow copies the folder
to https://market.driveyourstyle.net/<out name>/.
--sample renders every theme (or, with --rotate, every game) into <out>/samples/ and records nothing.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

from social import BASE, FONT_CSS, LOGO, SKIP, clean_name, esc, img, money, short_set

SITE = "https://market.driveyourstyle.net"
TAGS = "#pokemon #pokemoncards #pokemontcg #cardcollecting #tcg"
GAMES = {   # slug: (display name, hashtags, photo watermarked on TCGplayer?)
    "pokemon": ("Pokémon", TAGS, False),
    "one-piece": ("One Piece", "#onepiecetcg #onepiececardgame #onepiece #optcg #tcg", True),
    "lorcana": ("Lorcana", "#lorcana #disneylorcana #lorcanatcg #disney #tcg", False),
    "riftbound": ("Riftbound", "#riftbound #leagueoflegends #riftboundtcg #lol #tcg", False),
    "gundam": ("Gundam", "#gundamcardgame #gundam #gundamtcg #gunpla #tcg", False),
    "union-arena": ("Union Arena", "#unionarena #unionarenatcg #anime #animetcg #tcg", False),
    "yugioh": ("Yu-Gi-Oh!", "#yugioh #yugiohtcg #yugiohcards #ygo #tcg", False),
    "dragon-ball-fusion-world": ("Dragon Ball", "#dragonball #dbsfusionworld #dragonballsuper #dbs #tcg", False),
}
# midday slot, one game per day (7 = one week). Riftbound twice: it does best of the other games (doc 10).
# One Piece stays out while TCGplayer's One Piece photos carry a "SAMPLE" watermark (every post needs real photos).
ROTATION = ["riftbound", "lorcana", "yugioh", "riftbound", "gundam", "union-arena", "dragon-ball-fusion-world"]
THEMES = ["jumps", "under10", "highs", "dip", "newset"]
THEME_DAYS = {0: "newset", 1: "under10", 2: "highs", 3: "dip", 4: "jumps", 5: "under10", 6: "jumps"}   # Mon=0; Monday's Trending covers jumps
MIN_CARDS, MAX_CARDS, PER_SET = 3, 5, 2
SIDEWAYS = re.compile(r"\bBREAK\b|\bLEGEND\b|jumbo|oversize", re.I)   # landscape cards don't fit the portrait slides
NOT_CARDS = re.compile(r"action point card|\btoken\b", re.I)   # game pieces, not collectible cards
UA = {"User-Agent": "DriveYourStyleMarket/1.0 (+https://driveyourstyle.net)"}
B = BASE.replace("height:1350px", "height:1920px")
GREEN, RED = "#3ee08f", "#ff6b6b"
_photo = {}
OFFLINE = False


def has_photo(pid):
    """True if TCGplayer serves a real photo for this product (403/404 when there is none)."""
    if OFFLINE:
        return True
    if pid not in _photo:
        _photo[pid] = False
        for method in ("HEAD", "GET"):
            try:
                req = urllib.request.Request(img(pid, 1000), method=method, headers=UA)
                with urllib.request.urlopen(req, timeout=20) as r:
                    _photo[pid] = r.status == 200 and r.headers.get("Content-Type", "").startswith("image")
                break
            except urllib.error.HTTPError as e:
                if e.code in (403, 404, 410):
                    break
            except Exception:
                pass
    return _photo[pid]


def game_rows(site_data, today, game):
    """(set, item) for priced single cards of a game's sets released in the last 3 years, plus those sets."""
    recent = (today - timedelta(days=3 * 365)).isoformat()
    sets = [s for s in json.load(open(os.path.join(site_data, "sets.json")))
            if s["k"] == game and recent <= (s.get("pub") or "") <= today.isoformat()]
    rows = []
    for st in sets:
        try:
            items = json.load(open(os.path.join(site_data, "set", f"{st['id']}.json")))["items"]
        except (OSError, ValueError):
            continue
        for i in items:
            if i["t"] == "c" and i.get("p") and not SKIP.search(i["n"]) and not SIDEWAYS.search(i["n"]) and not NOT_CARDS.search(i["n"]):
                rows.append((st, i))
    return sets, rows


DECKS = re.compile(r"\bdeck\b|starter|start deck|trial|promo|collection|\btin\b|\bkit\b|bundle|box set", re.I)


def set_name(n):
    """Short set name without the leading code (\"UE10DC: Bleach ...\" -> \"Bleach ...\")."""
    return re.sub(r"^[A-Z]{1,5}\d{1,3}[A-Z]{0,3}\s*[:\-–]\s*", "", short_set(n))


def base_name(n):
    return re.sub(r"\s*\(.*$", "", n).strip().lower()


def card(st, i, pct):
    if pct is not None and abs(pct) < 1:   # a move under 1% isn't news: show the rarity instead
        pct = None
    return {"id": i["id"], "name": clean_name(i["n"]), "set": set_name(st["n"]), "gid": st["id"], "game": st["k"],
            "now": i["p"], "old": round(i["p"] / (1 + pct / 100)) if pct is not None else None, "pct": pct,
            "rarity": i.get("r")}


def new_high(i):
    """Latest price is the highest of the last 30 tracked days, with enough history to mean something."""
    vals = [v for v in (i.get("s") or [])[-30:] if v]
    return len(vals) >= 8 and vals[-1] >= max(vals) and vals[-1] >= min(vals) * 1.05


def pick_theme(site_data, today, game, theme, exclude):
    """Up to MAX_CARDS cards for one theme, best first, each with its own photo; and the price window."""
    sets, rows = game_rows(site_data, today, game)
    has7 = sum(1 for _, i in rows if (i.get("ch") or {}).get("7") is not None) > (50 if game == "pokemon" else 5)
    win = "7" if has7 else "a"
    floor = 1000 if game == "pokemon" else 500
    cands = []
    for st, i in rows:
        if i["id"] in exclude:
            continue
        pct = (i.get("ch") or {}).get(win)
        p = i["p"]
        if theme == "jumps" and p >= floor and pct is not None and 5 <= pct <= 150:
            cands.append((-pct, st, i, pct))
        elif theme == "under10" and 300 <= p < 1000 and pct is not None and 8 <= pct <= 150:
            cands.append((-pct, st, i, pct))
        elif theme == "highs" and p >= 500 and pct is not None and 3 <= pct <= 150 and new_high(i):
            cands.append((-pct, st, i, pct))
        elif theme == "dip" and p >= floor and pct is not None and -60 <= pct <= -8:
            cands.append((pct, st, i, pct))
    if theme == "newset":   # chase cards of the newest set that has enough priced cards
        for st in sorted(sets, key=lambda s: s.get("pub") or "", reverse=True):
            if (st.get("np") or 0) < 40 or DECKS.search(st["n"]):
                continue
            top = sorted(((s2, i) for s2, i in rows if s2["id"] == st["id"] and i["p"] >= 300 and i["id"] not in exclude),
                         key=lambda r: -r[1]["p"])
            if len(top) >= MIN_CARDS:
                cands = [(-i["p"], s2, i, (i.get("ch") or {}).get(win)) for s2, i in top]
                break
    cands.sort(key=lambda r: r[0])
    out, per_set, names = [], {}, set()
    for _, st, i, pct in cands:
        if len(out) == MAX_CARDS:
            break
        if theme != "newset" and per_set.get(st["id"], 0) >= PER_SET:
            continue
        if base_name(i["n"]) in names:   # same card, other printing
            continue
        if not has_photo(i["id"]):
            continue
        names.add(base_name(i["n"]))
        per_set[st["id"]] = per_set.get(st["id"], 0) + 1
        out.append(card(st, i, pct))
    return out, ("this week" if win == "7" else "lately")


def choose(site_data, today, games, first_theme, exclude):
    """First (game, theme) with at least MIN_CARDS cards: today's theme first, then the others, game by game."""
    order = [first_theme] + [t for t in THEMES if t != first_theme]
    for game in games:
        if GAMES[game][2]:   # watermarked photos: never post
            continue
        for theme in order:
            cards, period = pick_theme(site_data, today, game, theme, exclude)
            if len(cards) >= MIN_CARDS:
                return game, theme, cards, period
    return None, None, [], None


# ---- slides -------------------------------------------------------------------------------------

def spark(site_data, c):
    """Price series for the card (cents), oldest first, from its set file."""
    try:
        d = json.load(open(os.path.join(site_data, "set", f"{c['gid']}.json")))
    except (OSError, ValueError):
        return []
    for i in d["items"]:
        if i["id"] == c["id"] and i.get("s"):
            return [v for v in i["s"] if v]
    return []


def spark_svg(vals, w=900, h=260):
    if len(vals) < 2:
        return ""
    end = "#3ee08f" if vals[-1] >= vals[0] else RED   # line ends green when the price rose, red when it fell
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    pts = " ".join(f"{i * w / (len(vals) - 1):.1f},{h - (v - lo) / rng * (h - 20) - 10:.1f}" for i, v in enumerate(vals))
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}"><defs><linearGradient id="g" x1="0" x2="1">'
            f'<stop offset="0" stop-color="#5ee7ff"/><stop offset=".5" stop-color="#a78bfa"/><stop offset="1" stop-color="{end}"/></linearGradient></defs>'
            f'<polyline points="{pts}" fill="none" stroke="url(#g)" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def short_name(c):
    return re.sub(r"\s*-\s*\S+/\S+$", "", c["name"])


def headline(theme, n, period, cards):
    if theme == "jumps":
        return f"{n} cards<br><span style='color:{GREEN}'>jumped</span><br>{esc(period)}"
    if theme == "under10":
        return f"{n} cards under<br><span class='holo'>$10</span><br>climbing"
    if theme == "highs":
        return f"{n} cards hit<br>a <span style='color:{GREEN}'>new high</span><br>this month"
    if theme == "dip":
        return f"{n} cards<br><span style='color:{RED}'>dropped</span><br>{esc(period)}"
    st = cards[0]["set"]
    size = "" if len(st) <= 16 else " style='font-size:.62em;display:inline-block;line-height:1.05'" if len(st) <= 26 else " style='font-size:.46em;display:inline-block;line-height:1.1'"
    return f"The {n} chase<br>cards of<br><span class='holo'{size}>{esc(st)}</span>"


def first_line(theme, n, label, period, cards):
    top = cards[0]
    if theme == "jumps":
        return f"{n} {label} cards that jumped {period} 📈 #1 is up {top['pct']:.0f}%"
    if theme == "under10":
        return f"{n} {label} cards under $10 that are climbing 📈 #1 is up {top['pct']:.0f}%"
    if theme == "highs":
        return f"{n} {label} cards just hit a new high 🚀 #1 is up {top['pct']:.0f}% {period}"
    if theme == "dip":
        return f"{n} {label} cards that dropped {period} 📉 #1 is down {abs(top['pct']):.0f}%. Buy the dip?"
    return f"The {n} chase cards of {top['set']} 💎 #1 is worth {money(top['now'])}"


def move_html(c, big=96):
    if c.get("pct") is None:
        return f"<div><div style=\"font-size:32px;color:#bdb9b2\">Rarity</div><div style=\"font-family:'Barlow Condensed';font-weight:800;font-size:56px;line-height:1.1\">{esc(c.get('rarity') or 'Chase')}</div></div>"
    up = c["pct"] >= 0
    return (f"<div><div style=\"font-family:'Barlow Condensed';font-weight:800;font-size:{big}px;line-height:1;color:{GREEN if up else RED}\">"
            f"{'▲' if up else '▼'} {abs(c['pct']):.0f}%</div><div style=\"font-size:32px;color:#bdb9b2\">was {money(c['old'])}</div></div>")


def slides(cards, theme, period, game, sparks):
    label = GAMES[game][0]
    n = len(cards)
    spots = {3: [(300, 40, 0, 5), (70, 110, -12, 4), (530, 110, 12, 4)],
             4: [(190, 40, -5, 5), (410, 40, 5, 5), (-20, 130, -16, 4), (620, 130, 16, 4)],
             5: [(305, 30, 0, 5), (135, 90, -11, 4), (475, 90, 11, 4), (-15, 170, -19, 3), (625, 170, 19, 3)]}[n]
    fan = "".join(f'<div class="card" style="position:absolute;width:300px;height:420px;left:{x}px;top:{y}px;transform:rotate({r}deg);z-index:{z}">'
                  f'<img src="{img(c["id"], 400)}"></div>' for c, (x, y, r, z) in zip(cards, spots))
    hook = f"""<div class="slide" style="height:1920px;padding:170px 80px 400px;align-items:center;text-align:center">
<img src="file://{LOGO}" style="height:100px">
<div class="tag" style="margin-top:46px">{esc(label)} · Cards of the day</div>
<div style="margin-top:40px;font-family:'Barlow Condensed';font-weight:800;font-size:118px;line-height:.95;text-transform:uppercase">{headline(theme, n, period, cards)}</div>
<div style="position:relative;width:900px;height:600px;margin-top:44px;flex-shrink:0">{fan}</div>
<div style="margin-top:auto;font-size:40px;color:#bdb9b2">Counting down #{n} → #1 →</div></div>"""
    out = [hook]
    for rank in range(n, 0, -1):   # countdown: best card last
        c = cards[rank - 1]
        nm = c["name"]
        out.append(f"""<div class="slide" style="height:1920px;padding:150px 80px 400px;align-items:center;text-align:center">
<div style="display:flex;width:100%;justify-content:space-between;align-items:center"><img src="file://{LOGO}" style="height:70px">
 <div style="font-family:'Barlow Condensed';font-weight:800;font-size:110px;line-height:1" class="holo">#{rank}<span style="font-size:44px;color:#bdb9b2;-webkit-text-fill-color:#bdb9b2"> / {n}</span></div></div>
<div class="card" style="margin-top:34px;width:500px;height:700px"><img src="{img(c['id'])}"></div>
<div style="margin-top:38px;font-family:'Barlow Condensed';font-weight:800;font-size:{64 if len(nm) < 30 else 50}px;line-height:1.02;text-transform:uppercase">{esc(nm)}</div>
<div style="margin-top:10px;font-size:34px;color:#bdb9b2">{esc(c['set'])}</div>
<div style="margin-top:34px;display:flex;gap:60px;align-items:flex-end;justify-content:center">
 <div><div style="font-size:32px;color:#bdb9b2">Market price</div><div style="font-family:'Barlow Condensed';font-weight:800;font-size:124px;line-height:1">{money(c['now'])}</div></div>
 {move_html(c)}</div>
<div style="margin-top:26px">{spark_svg(sparks.get(c['id'], []), 900, 140)}</div>
<div style="margin-top:auto;font-size:28px;color:#8f8b85;letter-spacing:.06em">PRICE: TCGPLAYER MARKET · MARKET.DRIVEYOURSTYLE.NET</div></div>""")
    out.append(f"""<div class="slide" style="height:1920px;justify-content:center;align-items:center;text-align:center;padding:170px 80px 400px">
<img src="file://{LOGO}" style="height:180px">
<div style="margin-top:70px;font-family:'Barlow Condensed';font-weight:800;font-size:132px;line-height:.92;text-transform:uppercase">Which one<br>would <span class="holo">you</span> buy?</div>
<div style="margin-top:40px;font-size:46px;color:#d8d5cf">Comment your pick 👇</div>
<div style="margin-top:80px;font-size:40px;color:#bdb9b2;max-width:880px">Check what your cards are worth, free:</div>
<div style="margin-top:24px;font-family:'Barlow Condensed';font-weight:700;font-size:62px;border:4px solid #f2f0eb;padding:18px 40px 14px">market.driveyourstyle.net</div>
<div style="margin-top:80px;font-family:'Barlow Condensed';font-weight:800;font-size:54px;letter-spacing:.04em;text-transform:uppercase" class="holo">Follow for daily price moves</div></div>""")
    return out


def render(site_data, cards, theme, period, game, out, offline=False):
    sparks = {c["id"]: spark(site_data, c) for c in cards}
    bodies = slides(cards, theme, period, game, sparks)
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
    return len(bodies), make_short([os.path.join(out, f"slide-{n}.jpg") for n in range(1, len(bodies) + 1)],
                                   os.path.join(out, "short.mp4"), per=3.0)


def caption_for(theme, cards, period, game):
    label, tags, _ = GAMES[game]
    lines = [first_line(theme, len(cards), label, period, cards), "Prices: TCGplayer market", ""]
    for k, c in enumerate(cards, 1):
        mv = "" if c.get("pct") is None else f", {'up' if c['pct'] >= 0 else 'down'} {abs(c['pct']):.0f}%"
        lines.append(f"{k}. {short_name(c)} ({c['set']}): {money(c['now'])}{mv}")
    lines += ["", f"Which one would you buy? 👇 Check your {label} cards free at market.driveyourstyle.net (link in bio)", "", tags]
    return "\n".join(lines)


def yt_title(theme, cards, period, game):
    label, tags, _ = GAMES[game]
    base = first_line(theme, len(cards), label, period, cards).replace(". Buy the dip?", "")
    for t in (f"{base} — which would you buy? {tags.split()[0]}", f"{base} {tags.split()[0]}", base):
        if len(t) <= 100:
            return t
    return base[:100]


def trending_ids(path):
    try:
        return {int(c["id"]) for c in json.load(open(path)).get("cards", [])}
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def main(argv):
    global OFFLINE
    site_data, out_root = argv[0], argv[1]
    arg = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    today = date.fromisoformat(arg("--date")) if "--date" in argv else date.today()
    OFFLINE = "--offline" in argv
    web = f"{SITE}/{os.path.basename(os.path.normpath(out_root))}"
    hist_path = arg("--history", os.path.join(out_root, "history.json"))
    try:
        history = json.load(open(hist_path))
    except (OSError, ValueError):
        history = {}
    recent = {int(k) for k, d in history.items() if (today - date.fromisoformat(d)).days < 21}
    exclude = recent | trending_ids(arg("--trending", os.path.join(os.path.dirname(os.path.normpath(out_root)), "social", "latest.json")))
    theme_today = arg("--theme", THEME_DAYS[today.weekday()])
    if "--rotate" in argv:
        k = today.toordinal() % len(ROTATION)
        games = list(dict.fromkeys(ROTATION[k:] + ROTATION[:k]))
    else:
        games = [arg("--game", "pokemon")]

    if "--sample" in argv:   # previews, nothing recorded
        summary = []
        if "--rotate" in argv:   # one preview per midday game, using today's theme order
            jobs = [(g, None) for g in dict.fromkeys(ROTATION)]
        else:                    # one preview per theme
            jobs = [(games[0], t) for t in THEMES]
        for game, theme in jobs:
            if theme is None:
                g, t, cards, period = choose(site_data, today, [game], theme_today, exclude)
            else:
                g, t = game, theme
                cards, period = pick_theme(site_data, today, game, theme, exclude)
            name = f"{game}-{t or 'none'}"
            if not g or len(cards) < MIN_CARDS:
                summary.append({"sample": name, "cards": len(cards), "skipped": True})
                print(f"sample {name}: only {len(cards)} cards; skipped")
                continue
            out = os.path.join(out_root, "samples", name)
            os.makedirs(out, exist_ok=True)
            n, video = render(site_data, cards, t, period, g, out, OFFLINE)
            cap = caption_for(t, cards, period, g)
            open(os.path.join(out, "caption.txt"), "w").write(cap)
            summary.append({"sample": name, "slides": n, "video": bool(video), "first": cap.split("\n")[0],
                            "yt": yt_title(t, cards, period, g), "cards": cards})
            print(f"sample {name}: {cap.splitlines()[0]}")
        os.makedirs(os.path.join(out_root, "samples"), exist_ok=True)
        json.dump(summary, open(os.path.join(out_root, "samples", "summary.json"), "w"), indent=1, ensure_ascii=False)
        return

    done = os.path.join(out_root, today.isoformat(), "post.json")
    if os.path.exists(done) and "--force" not in argv:   # one post per day, even if the site is rebuilt again
        post = json.load(open(done))
        json.dump(post, open(os.path.join(out_root, "latest.json"), "w"), indent=1, ensure_ascii=False)
        print(f"daily cards: already made for {today} ({post.get('theme', 'card')})")
        return
    game, theme, cards, period = choose(site_data, today, games, theme_today, exclude)
    if not cards:
        print("daily cards: fewer than 3 new cards with photos for any theme today; skipping")
        return
    label = GAMES[game][0]
    out = os.path.join(out_root, today.isoformat())
    os.makedirs(out, exist_ok=True)
    n, video = render(site_data, cards, theme, period, game, out, OFFLINE)
    caption = caption_for(theme, cards, period, game)
    post = {"date": today.isoformat(), "game": game, "theme": theme, "cards": cards, "card": cards[0], "caption": caption,
            "slides": [f"{web}/{today.isoformat()}/slide-{k}.jpg" for k in range(1, n + 1)],
            "short": f"{web}/{today.isoformat()}/short.mp4" if video else None,
            "short_title": yt_title(theme, cards, period, game),
            "title": f"{label} cards of the day 📈"}
    json.dump(post, open(os.path.join(out, "post.json"), "w"), indent=1, ensure_ascii=False)
    json.dump(post, open(os.path.join(out_root, "latest.json"), "w"), indent=1, ensure_ascii=False)
    for c in cards:
        history[str(c["id"])] = today.isoformat()
    json.dump(history, open(hist_path, "w"))
    dirs = sorted(d for d in os.listdir(out_root) if re.match(r"\d{4}-\d{2}-\d{2}$", d))
    for d in dirs[:-14]:
        for f in os.listdir(os.path.join(out_root, d)):
            os.remove(os.path.join(out_root, d, f))
        os.rmdir(os.path.join(out_root, d))
    print(f"daily cards ({game}, {theme}): {caption.splitlines()[0]} -> {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
