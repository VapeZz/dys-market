"""Set ranking: "Top 20 <set> cards ranked by price" as a fast vertical video (about 1 second per card),
full-screen slides (1080x1920) and a caption. One set per post, counting down to the #1 card.

    python tools/set_rank.py site/data data/social-rank [--date YYYY-MM-DD] [--set ID-or-name] [--game G]
        [--n 20] [--offline] [--force]

Rules (owner's content rules):
- every card shown has its own photo, checked live on TCGplayer's CDN. A ranking can't skip a card, so the
  list is cut just above the first card without a photo (20 -> 15 -> 10 cards); under 10, nothing is built
- prices are TCGplayer market prices and the slides and caption say so

Which set (owner's rule: no repeat posts): without --set it rotates through the POOL newest booster sets and
never ranks the same set twice in a row. First a fresh set (out under FRESH_DAYS days) that was never ranked or
last ranked FRESH_GAP+ days ago (its prices still move a lot), then sets never ranked, then the one ranked longest
ago. <out>/history.json remembers when each set was ranked.

Writes <out>/<date>/slide-N.jpg, short.mp4, post.json and <out>/latest.json; one post per day unless --force.
The nightly workflow runs it for Saturdays and copies the folder to https://market.driveyourstyle.net/social-rank/.
"""
import json
import os
import re
import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

import daily_card as dc
from social import FONT_CSS, LOGO, clean_name, esc, img, money

SIZES = (20, 15, 10)       # cards per ranking, biggest that the set (and its photos) can fill
FLOOR = 100                # cents: cards under $1 aren't worth a slot
POOL = 8                   # the rotation: this many of the newest booster sets
FRESH_DAYS, FRESH_GAP = 60, 28   # a set under 60 days old comes back every 4 weeks
KEEP = 6                   # dated folders kept (one per week)
SITE = "https://market.driveyourstyle.net"


def booster_sets(sets):
    """Booster sets with 40+ priced cards, newest first (no decks, tins, promos or collections)."""
    return [s for s in sorted(sets, key=lambda s: s.get("pub") or "", reverse=True)
            if (s.get("np") or 0) >= 40 and not dc.DECKS.search(s["n"])]


def rotation(sets, history, today):
    """Sets to try, best first; the set ranked last time is left out (no repeat posts)."""
    pool = booster_sets(sets)[:POOL]
    last = max(history.items(), key=lambda kv: kv[1])[0] if history else None

    def key(st):
        seen = history.get(str(st["id"]))
        fresh = st.get("pub") and (today - date.fromisoformat(st["pub"])).days <= FRESH_DAYS
        if fresh and (not seen or today - date.fromisoformat(seen) >= timedelta(days=FRESH_GAP)):
            return (0, "")
        return (1, "") if not seen else (2, seen)
    order = sorted(pool, key=key)   # stable sort: newest set first inside each group
    return [st for st in order if str(st["id"]) != last] or order


def named(sets, want):
    """The set asked for with --set: its id, or part of its name (the biggest set wins)."""
    hit = [s for s in sets if str(s["id"]) == str(want) or want.lower() in s["n"].lower()]
    return sorted(hit, key=lambda s: s.get("np") or 0, reverse=True)[:1]


def ranked(st, rows, n):
    """The set's n most expensive cards, #1 first; cut above the first card with no photo."""
    top = sorted((i for s2, i in rows if s2["id"] == st["id"] and i["p"] >= FLOOR), key=lambda i: -i["p"])
    cards = []
    for i in top[:max(SIZES)]:
        if not dc.has_photo(i["id"]):
            break
        nm = clean_name(i["n"])
        cards.append({"id": i["id"], "name": re.sub(r"\s*-\s*[\w-]+/[\w-]+\s*$", "", nm), "full": nm, "no": i.get("no"),
                      "rarity": i.get("r"), "now": i["p"], "pct": (i.get("ch") or {}).get("7")})
    size = next((k for k in SIZES if k <= min(n, len(cards))), 0)
    return cards[:size]


def dollars(c):
    return f"${c / 100:,.0f}"


def slides(cards, setname, label, day):
    n = len(cards)
    top = cards[0]
    head = lambda right: (f'<div style="display:flex;width:100%;justify-content:space-between;align-items:center">'
                          f'<img src="file://{LOGO}" style="height:74px">{right}</div>')
    # cover = the thumbnail: the set, the size of the list, the #1 price; the #1 card itself stays hidden
    spots = [(-15, 150, -18, 3), (125, 85, -9, 4), (475, 85, 9, 4), (615, 150, 18, 3)]
    fan = "".join(f'<div class="card" style="position:absolute;width:300px;height:420px;left:{x}px;top:{y}px;transform:rotate({r}deg);z-index:{z}">'
                  f'<img src="{img(c["id"], 400)}"></div>' for c, (x, y, r, z) in zip(cards[1:5], spots))
    mystery = (f'<div class="card" style="position:absolute;width:380px;height:532px;left:260px;top:10px;z-index:6;background:#111;'
               f'box-shadow:0 0 0 6px #a78bfa,0 0 90px rgba(167,139,250,.75),0 30px 80px rgba(0,0,0,.7)">'
               f'<img src="{img(top["id"], 400)}" style="filter:blur(26px) brightness(.6) saturate(1.4);transform:scale(1.15)">'
               f'<div class="holo" style="position:absolute;inset:0;display:grid;place-content:center;font-family:\'Barlow Condensed\';font-weight:800;font-size:330px;line-height:1">?</div>'
               f'<div style="position:absolute;left:14px;top:12px;font-family:\'Barlow Condensed\';font-weight:800;font-size:46px;color:#050404;background:#f2f0eb;border-radius:999px;padding:2px 18px 0">#1</div></div>')
    big = 104 if len(setname) <= 16 else 84 if len(setname) <= 22 else 66
    out = [f"""<div class="slide" style="height:1920px;padding:170px 70px 400px;align-items:center;text-align:center">
{head(f'<div class="tag" style="font-size:26px">{esc(label)} · Set ranking</div>')}
<div style="margin-top:56px;font-family:'Barlow Condensed';font-weight:800;font-size:{big}px;line-height:.95;text-transform:uppercase">{esc(setname)}</div>
<div class="holo" style="font-family:'Barlow Condensed';font-weight:800;font-size:330px;line-height:.88">TOP {n}</div>
<div style="margin-top:14px;font-size:46px;font-weight:700;color:#bdb9b2">ranked by price · #1 is <b style="color:#f2f0eb">{dollars(top['now'])}</b></div>
<div style="position:relative;width:900px;height:600px;margin-top:50px;flex-shrink:0">{fan}{mystery}</div>
<div style="margin-top:auto;font-family:'Barlow Condensed';font-weight:700;font-size:48px;letter-spacing:.04em;text-transform:uppercase">Which card? Counting down #{n} → #1</div></div>"""]
    for rank in range(n, 0, -1):   # countdown: the most expensive card last
        c = cards[rank - 1]
        hot = rank <= 3
        nm = c["name"]
        sub = " · ".join(x for x in (c.get("rarity"), c.get("no")) if x)
        seg = "".join(f'<div style="flex:1;height:10px;border-radius:5px;background:{"#f2f0eb" if k >= rank else "#2a2826"}"></div>'
                      for k in range(n, 0, -1))
        glow = ";box-shadow:0 0 0 6px #a78bfa,0 0 90px rgba(167,139,250,.6),0 30px 80px rgba(0,0,0,.7)" if hot else ""
        out.append(f"""<div class="slide" style="height:1920px;padding:150px 80px 400px;align-items:center;text-align:center">
{head(f'<div style="font-family:Barlow Condensed;font-weight:800;font-size:{190 if hot else 160}px;line-height:.9" class="{"holo" if hot else ""}">#{rank}</div>')}
<div class="card" style="margin-top:22px;width:{520 if hot else 560}px;height:{726 if hot else 782}px;flex-shrink:0{glow}"><img src="{img(c['id'])}"></div>
<div style="margin-top:30px;font-family:'Barlow Condensed';font-weight:800;font-size:{68 if len(nm) < 26 else 52}px;line-height:1.02;text-transform:uppercase">{esc(nm)}</div>
<div style="margin-top:6px;font-size:32px;color:#bdb9b2">{esc(sub)}</div>
<div class="{'holo' if hot else ''}" style="margin-top:8px;font-family:'Barlow Condensed';font-weight:800;font-size:{200 if hot else 180}px;line-height:.92">{money(c['now'])}</div>
<div style="margin-top:auto;width:100%"><div style="display:flex;gap:6px">{seg}</div>
<div style="margin-top:16px;font-size:26px;color:#8f8b85;letter-spacing:.06em">{esc(setname.upper())} · PRICE: TCGPLAYER MARKET, {day.upper()}</div></div></div>""")
    out.append(f"""<div class="slide" style="height:1920px;justify-content:center;align-items:center;text-align:center;padding:170px 80px 400px">
<img src="file://{LOGO}" style="height:180px">
<div style="margin-top:70px;font-family:'Barlow Condensed';font-weight:800;font-size:132px;line-height:.92;text-transform:uppercase">Which one<br>did <span class="holo">you</span> pull?</div>
<div style="margin-top:40px;font-size:46px;color:#d8d5cf">Comment it 👇</div>
<div style="margin-top:80px;font-size:40px;color:#bdb9b2;max-width:880px">Every {esc(setname)} card price, free:</div>
<div style="margin-top:24px;font-family:'Barlow Condensed';font-weight:700;font-size:62px;border:4px solid #f2f0eb;padding:18px 40px 14px">market.driveyourstyle.net</div>
<div style="margin-top:80px;font-family:'Barlow Condensed';font-weight:800;font-size:54px;letter-spacing:.04em;text-transform:uppercase" class="holo">Follow for the next set</div></div>""")
    return out


def timing(n):
    """Seconds per slide: quick cover, about a second per card, longer on the top 3, then the ending."""
    per = [1.4]
    for rank in range(n, 0, -1):
        per.append(2.8 if rank == 1 else 1.6 if rank <= 3 else 1.1 if rank <= 10 else 0.9)
    return per + [2.4]


def render(bodies, out, offline=False):
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1920})
        if offline:
            pg.route(re.compile(r"tcgplayer-cdn"), lambda r: r.fulfill(path=os.environ["FAKE_CARD"], content_type="image/jpeg"))
        tmp = os.path.abspath(os.path.join(out, "_slide.html"))
        for k, body in enumerate(bodies, 1):
            open(tmp, "w", encoding="utf-8").write(dc.B % (FONT_CSS, body))
            pg.goto("file://" + tmp, wait_until="networkidle")
            pg.evaluate("document.fonts.ready")
            pg.screenshot(path=os.path.join(out, f"slide-{k}.jpg"), type="jpeg", quality=90)
        b.close()
        os.remove(tmp)
    from tiktok import make_short
    paths = [os.path.join(out, f"slide-{k}.jpg") for k in range(1, len(bodies) + 1)]
    return make_short(paths, os.path.join(out, "short.mp4"), per=timing(len(bodies) - 2), fade=0.12)


def texts(cards, setname, label, tags, day):
    n, top = len(cards), cards[0]
    first = f"Top {n} {setname} cards ranked by price 💎 #1 is a {dollars(top['now'])} card. Can you guess it?"
    lines = [f"{k}. {c['name']}{' (' + c['rarity'] + ')' if c.get('rarity') else ''}: {money(c['now'])}"
             for k, c in reversed(list(enumerate(cards, 1)))]
    tag = "#" + re.sub(r"[^a-z0-9]", "", setname.lower())
    cap = (f"{first}\nPrices: TCGplayer market, {day}\n\n" + "\n".join(lines) +
           f"\n\nWhich one did you pull? 👇 Check your {label} cards free at market.driveyourstyle.net (link in bio)\n\n"
           f"{' '.join(tags.split()[:3])} {tag} {' '.join(tags.split()[3:])}")
    yt = f"Top {n} {setname} cards ranked by price 💎 #1 is {dollars(top['now'])} {tags.split()[0]}"
    return cap, yt[:100], f"Top {n} {setname} cards 💎"


def main(argv):
    site_data, out_root = argv[0], argv[1]
    arg = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    today = date.fromisoformat(arg("--date")) if "--date" in argv else date.today()
    game = arg("--game", "pokemon")
    dc.OFFLINE = "--offline" in argv
    label, tags, marked = dc.GAMES[game]
    if marked:
        print(f"set ranking: {label} photos are watermarked on TCGplayer; skipping")
        return
    hist_path = os.path.join(out_root, "history.json")
    history = json.load(open(hist_path)) if os.path.exists(hist_path) else {}
    done = os.path.join(out_root, today.isoformat(), "post.json")
    if os.path.exists(done) and "--force" not in argv:   # one post per day, even if the site is rebuilt again
        post = json.load(open(done))
        json.dump(post, open(os.path.join(out_root, "latest.json"), "w"), indent=1, ensure_ascii=False)
        print(f"set ranking: already made for {today} ({post.get('set')})")
        return
    sets, rows = dc.game_rows(site_data, today, game)
    st, cards = None, []
    for cand in (named(sets, arg("--set")) if "--set" in argv else rotation(sets, history, today)):
        cards = ranked(cand, rows, int(arg("--n", max(SIZES))))
        if cards:
            st = cand
            break
        print(f"set ranking: {cand['n']}: fewer than {min(SIZES)} cards in a row with a photo; next set")
    if not st:
        print("set ranking: no set with enough cards and photos; skipping")
        return
    setname = dc.set_name(st["n"])
    day = f"{today:%b} {today.day}"
    out = os.path.join(out_root, today.isoformat())
    os.makedirs(out, exist_ok=True)
    bodies = slides(cards, setname, label, day)
    video = render(bodies, out, dc.OFFLINE)
    cap, yt, tt = texts(cards, setname, label, tags, day)
    web = f"{SITE}/{os.path.basename(os.path.normpath(out_root))}"
    g = tags.split()[0].lstrip("#")   # plain game word for YouTube tags ("pokemon")
    post = {"date": today.isoformat(), "game": game, "set": setname, "set_id": st["id"], "cards": cards, "caption": cap,
            "slides": [f"{web}/{today.isoformat()}/slide-{k}.jpg" for k in range(1, len(bodies) + 1)],
            "caption_link": cap.replace("market.driveyourstyle.net (link in bio)", "https://market.driveyourstyle.net"),
            "short": f"{web}/{today.isoformat()}/short.mp4" if video else None, "short_title": yt, "title": tt,
            "yt_tags": [g, f"{g} cards", f"{g} tcg", setname.lower(), "card prices", "shorts"],
            "seconds": round(sum(timing(len(cards))), 1)}
    json.dump(post, open(os.path.join(out, "post.json"), "w"), indent=1, ensure_ascii=False)
    json.dump(post, open(os.path.join(out_root, "latest.json"), "w"), indent=1, ensure_ascii=False)
    history[str(st["id"])] = today.isoformat()
    json.dump(history, open(hist_path, "w"))
    dirs = sorted(d for d in os.listdir(out_root) if re.match(r"\d{4}-\d{2}-\d{2}$", d))
    for d in dirs[:-KEEP]:
        for f in os.listdir(os.path.join(out_root, d)):
            os.remove(os.path.join(out_root, d, f))
        os.rmdir(os.path.join(out_root, d))
    print(f"set ranking ({setname}, top {len(cards)}, {post['seconds']} s): {cap.splitlines()[0]} -> {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
