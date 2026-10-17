"""Weekly "Market Report" blog posts, generated from the site's own price data.

    python tools/blog.py site data/blog [--date YYYY-MM-DD] [--force]

Runs every night but only writes a new post on Sundays (or with --force). Posts are kept in
<out>/<slug>.html (+ posts.json) and the index page is rebuilt from them each run. The nightly
workflow copies <out> to site/blog/ and adds the pages to the sitemap.
"""
import html
import json
import os
import re
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_pages import HEAD  # noqa: E402
from social import SKIP, clean_name, img, money, pick, short_set  # noqa: E402

SITE = "https://market.driveyourstyle.net"
STORE = "https://driveyourstyle.net"
GAME = {"pokemon": "Pokémon", "pokemon-jp": "Pokémon Japan", "one-piece": "One Piece",
        "lorcana": "Lorcana", "riftbound": "Riftbound", "palworld": "Palworld"}
SIDEWAYS = re.compile(r"\bBREAK\b|\bLEGEND\b|jumbo|oversize", re.I)   # landscape cards look half-size in the grid
VERDICT = {"cop": "Cop", "wear": "Wear", "wait": "Wait"}


def esc(t):
    return html.escape(str(t), quote=True)


def prod(i, g):
    return f"/product.html?id={i}&set={g}"


def load(path, default=None):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def fallers(site_data, today, limit=6):
    """Biggest drops among cards from sets released in the last 3 years, priced $15+ (mirror of pick)."""
    recent = (today - timedelta(days=3 * 365)).isoformat()
    sets = [s for s in load(os.path.join(site_data, "sets.json"), []) if recent <= (s.get("pub") or "") <= today.isoformat()
            and s["k"].startswith("pokemon")]
    rows = []
    for s in sets:
        d = load(os.path.join(site_data, "set", f"{s['id']}.json"))
        if not d:
            continue
        for i in d["items"]:
            if i["t"] != "c" or not i.get("p") or i["p"] < 1500 or not i.get("ch") or SKIP.search(i["n"]):
                continue
            pct = i["ch"].get("7", i["ch"].get("a"))
            if pct is None or not (-80 <= pct <= -5):
                continue
            rows.append({"id": i["id"], "name": clean_name(i["n"]), "set": short_set(s["n"]), "gid": s["id"],
                         "now": i["p"], "old": round(i["p"] / (1 + pct / 100)), "pct": pct})
    rows.sort(key=lambda r: r["pct"])
    out, per = [], {}
    for r in rows:
        if per.get(r["gid"], 0) < 2:
            per[r["gid"]] = per.get(r["gid"], 0) + 1
            out.append(r)
        if len(out) == limit:
            break
    return out


def movers(site_data, name, tier, n=6, sets=None, modern_after=None):
    """Rows from data/movers/<name>.json: [id, name, gid, now, old, pct]."""
    d = load(os.path.join(site_data, "movers", f"{name}.json"))
    if not d:
        return [], []
    win = "7" if "7" in d["windows"] else sorted(d["windows"])[0]
    w = d["windows"][win].get(tier, {})

    def ok(r):
        if SKIP.search(r[1]) or not (-80 <= r[5] <= 150):
            return False
        if modern_after and sets:
            pub = (sets.get(r[2]) or {}).get("pub") or ""
            return pub >= modern_after
        return True
    return [r for r in w.get("up", []) if ok(r)][:n], [r for r in w.get("down", []) if ok(r)][:n]


def card_grid(cards):
    if len(cards) > 4:
        cards = cards[:len(cards) // 4 * 4]   # full rows only (4 across on desktop, 2 on phones)
    return '<div class="rp-grid">' + "".join(
        f'<a class="rp-card" href="{prod(c["id"], c["gid"])}"><img src="{img(c["id"], 1000)}" alt="{esc(c["name"])}" loading="lazy" width="200" height="280" onerror="window.dysImg&&dysImg(this)">'
        f'<span class="rp-n">{esc(c["name"])}</span><span class="rp-s">{esc(c["set"])}</span>'
        f'<span class="rp-p">{money(c["now"])} <b class="chg {"up" if c["pct"] > 0 else "down"}">{"▲" if c["pct"] > 0 else "▼"} {abs(c["pct"]):.0f}%</b></span>'
        f'<span class="rp-o">was {money(c["old"])}</span></a>' for c in cards) + "</div>"


def mover_table(rows, sets, label):
    if not rows:
        return ""
    body = "".join(
        f'<tr><td><a href="{prod(r[0], r[2])}">{esc(clean_name(r[1]))}</a><span class="rp-s">{esc(short_set((sets.get(r[2]) or {}).get("n", "")))}</span></td>'
        f'<td class="num">{money(r[3])}</td><td class="num"><span class="chg {"up" if r[5] > 0 else "down"}">{"▲" if r[5] > 0 else "▼"} {abs(r[5]):.0f}%</span></td></tr>'
        for r in rows)
    return f'<table class="rp-table"><thead><tr><th>{esc(label)}</th><th class="num">Market</th><th class="num">Change</th></tr></thead><tbody>{body}</tbody></table>'


def build_post(site, today):
    sd = os.path.join(site, "data")
    meta = load(os.path.join(sd, "meta.json"), {})
    sets_list = load(os.path.join(sd, "sets.json"), [])
    sets = {s["id"]: s for s in sets_list}
    start = today - timedelta(days=6)
    span = f"{start.strftime('%b %-d')}–{today.strftime('%b %-d, %Y')}"
    up, win, _ = pick(sd, today, limit=12)
    up = [c for c in up if not SIDEWAYS.search(c["name"])][:8]
    down = [c for c in fallers(sd, today, limit=12) if not SIDEWAYS.search(c["name"])][:8]
    modern = (today - timedelta(days=3 * 365)).isoformat()
    s_up, s_down = movers(sd, "sealed-pokemon", "20", 6, sets, modern)
    v_up, v_down = movers(sd, "cards-pokemon", "100", 5)
    period = "this week" if win == "7" else "since we started tracking"

    secs, toc = [], []

    def sec(anchor, title, inner):
        if inner:
            toc.append((anchor, title))
            secs.append(f'<section id="{anchor}"><h2>{esc(title)}</h2>{inner}</section>')

    if up:
        top = up[0]
        sec("risers", "Biggest Pokémon card gains",
            f"<p>Modern cards (sets from the last three years, $10 and up) that gained the most {period}. "
            f"<a href=\"{prod(top['id'], top['gid'])}\">{esc(top['name'])}</a> led the way, up {top['pct']:.0f}% to {money(top['now'])}.</p>"
            + card_grid(up))
    if down:
        sec("fallers", "Biggest drops",
            f"<p>Cards that cooled off {period}. If one of these is on your want list, this may be a better time to buy.</p>" + card_grid(down))
    if s_up or s_down:
        sec("sealed", "Sealed product",
            "<p>Booster boxes, ETBs and other sealed Pokémon product ($20+) with the biggest moves.</p>"
            + mover_table(s_up, sets, "Rising") + mover_table(s_down, sets, "Falling"))
    if v_up:
        sec("high-end", "High-end and vintage",
            "<p>Cards worth $100+ with the biggest swings. Big percentage moves here often come from a single sale, so check recent sold listings before you act.</p>"
            + mover_table(v_up, sets, "Rising") + mover_table(v_down, sets, "Falling"))

    rec = [sets[i] for i in meta.get("recent", []) if i in sets]
    out_now = sorted([s for s in rec if (s.get("pub") or "") <= today.isoformat()], key=lambda s: s["pub"], reverse=True)[:6]
    soon = sorted([s for s in sets_list if today.isoformat() < (s.get("pub") or "") <= (today + timedelta(days=60)).isoformat()],
                  key=lambda s: s["pub"])[:8]
    if out_now or soon:
        li = lambda s: (f'<li><a href="/set.html?id={s["id"]}">{esc(s["n"])}</a> <span class="rp-s">{esc(GAME.get(s["k"], s["k"]))} · '
                        f'{date.fromisoformat(s["pub"]).strftime("%b %-d, %Y")}</span></li>')
        sec("releases", "New and upcoming sets",
            (f"<h3>Recently released</h3><ul class=\"rp-list\">{''.join(li(s) for s in out_now)}</ul>" if out_now else "")
            + (f"<h3>Coming in the next 60 days</h3><ul class=\"rp-list\">{''.join(li(s) for s in soon)}</ul>" if soon else "")
            + '<p><a href="/calendar.html">Full release calendar →</a></p>')

    snk = load(os.path.join(site, "sneakers.json"), {}) or {}
    picks = {p["c"]: p for p in snk.get("picks", [])}
    week = [r for r in snk.get("releases", []) if today.isoformat() < r["d"] <= (today + timedelta(days=7)).isoformat()]
    week.sort(key=lambda r: (r["d"], -r.get("h", 1)))
    if week:
        rows = "".join(
            f'<tr><td>{date.fromisoformat(r["d"]).strftime("%a %b %-d")}</td><td>{"🔥 " if r.get("h") == 3 else ""}{esc(r["n"])}'
            + (f'<span class="rp-s">Our call: {VERDICT[picks[r["c"]]["v"]]} — {esc(picks[r["c"]]["why"])}</span>' if r.get("c") in picks else "")
            + f'</td><td class="num">{"$" + str(r["r"]) if r.get("r") else "—"}</td></tr>' for r in week[:12])
        sec("sneakers", "Sneaker drops this week",
            f'<table class="rp-table"><thead><tr><th class="d">Date</th><th>Release</th><th class="num">Retail</th></tr></thead><tbody>{rows}</tbody></table>'
            '<p><a href="/sneakers.html">Release calendar with reminders and resale prices →</a></p>')

    wanted = (load(os.path.join(sd, "wanted.json"), {}) or {}).get("top", [])[:6]
    if wanted:
        items = "".join(f'<li><a href="{prod(w["id"], w["g"])}">{esc(clean_name(w["n"]))}</a> <span class="rp-s">♥ {w["c"]} collector{"s" if w["c"] > 1 else ""}</span></li>'
                        for w in wanted)
        sec("wanted", "Most wanted by collectors", f'<p>The cards most often saved to Want lists on this site.</p><ul class="rp-list">{items}</ul>')

    if not secs:
        return None
    title = f"Pokémon Card Market Report: {span}"
    lead = up[0] if up else None
    summary = (f"{lead['name']} up {lead['pct']:.0f}%, the biggest drops, sealed product moves, new sets and this week's sneaker drops."
               if lead else "This week's biggest card moves, sealed product, new sets and sneaker drops.")
    slug = f"market-report-{today.isoformat()}"
    toc_html = '<nav class="rp-toc"><b>In this report</b>' + "".join(f'<a href="#{a}">{esc(t)}</a>' for a, t in toc) + "</nav>"
    body = f'''<article class="wrap rp">
<p class="rp-crumb"><a href="/blog/">Market reports</a></p>
<h1>{esc(title)}</h1>
<p class="rp-meta">Published {today.strftime("%B %-d, %Y")} · Data from nightly TCGplayer market prices</p>
<p class="lead">{esc(summary)}</p>
{toc_html}
{"".join(secs)}
<section class="rp-cta"><h2>Check your own cards</h2><p>Look up any card or sealed product, scan a card with your camera, and track your collection's value for free.</p>
<p><a class="btn primary" href="/">Search prices</a> <a class="btn" href="/collection.html">Track my collection</a> <a class="btn" href="{STORE}">Shop Drive Your Style</a></p></section>
<p class="rp-fine">Market prices come from public TCGplayer data recorded nightly and can lag by a day. Percent changes compare to the price {"7 days ago" if win == "7" else "when tracking began"}. For research only, not financial advice.</p>
</article>'''
    return {"slug": slug, "date": today.isoformat(), "title": title, "summary": summary,
            "image": img(lead["id"], 400) if lead else None, "body": body}


def page(title, desc, canon, body, ld=None):
    h = HEAD.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n<base href="/">')
    h = h.replace('<meta property="og:type" content="website">', '<meta property="og:type" content="article">' if ld else '<meta property="og:type" content="website">')
    if ld:
        h = h.replace("</head>", f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>\n</head>')
    return (h.replace("@@TITLE@@", esc(title)).replace("@@DESC@@", esc(desc)).replace("@@CANON@@", canon)
             .replace("@@PAGE@@", "blog").replace("@@BODY@@", body))


def main(argv):
    site, out = argv[0], argv[1]
    today = date.fromisoformat(argv[argv.index("--date") + 1]) if "--date" in argv else date.today()
    os.makedirs(out, exist_ok=True)
    idx_path = os.path.join(out, "posts.json")
    posts = load(idx_path, []) or []
    if "--force" in argv or today.isoweekday() == 7:
        p = build_post(site, today)
        if p:
            ld = {"@context": "https://schema.org", "@type": "Article", "headline": p["title"], "description": p["summary"],
                  "datePublished": p["date"], "dateModified": p["date"], "mainEntityOfPage": f"{SITE}/blog/{p['slug']}.html",
                  "author": {"@type": "Organization", "name": "Drive Your Style"},
                  "publisher": {"@type": "Organization", "name": "Drive Your Style", "url": STORE}}
            if p["image"]:
                ld["image"] = p["image"]
            open(os.path.join(out, p["slug"] + ".html"), "w", encoding="utf-8").write(
                page(p["title"] + " · Drive Your Style", p["summary"], f"blog/{p['slug']}.html", p["body"], ld))
            posts = [x for x in posts if x["slug"] != p["slug"]] + [{k: p[k] for k in ("slug", "date", "title", "summary", "image")}]
            print(f"blog: wrote {p['slug']}")
        else:
            print("blog: not enough data for a report")
    posts.sort(key=lambda x: x["date"], reverse=True)
    json.dump(posts, open(idx_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    if posts:
        json.dump(posts[0], open(os.path.join(out, "latest.json"), "w", encoding="utf-8"), ensure_ascii=False)
    cards = "".join(
        f'<a class="rp-item" href="/blog/{x["slug"]}.html">' + (f'<img src="{x["image"]}" alt="" loading="lazy" width="120" height="168">' if x.get("image") else "")
        + f'<span><b>{esc(x["title"])}</b><span class="rp-s">{date.fromisoformat(x["date"]).strftime("%B %-d, %Y")}</span>'
          f'<span class="rp-sum">{esc(x["summary"])}</span></span></a>' for x in posts) or "<p>The first report is published this Sunday.</p>"
    body = f'''<section class="hero hero-tight"><div class="wrap"><span class="eyebrow"><b>●</b> Every Sunday</span>
<h1>Market <span class="holo">reports</span></h1>
<p class="lead">A weekly look at the biggest Pokémon card and sealed price moves, new sets and sneaker drops, built from our nightly price data.</p></div></section>
<section class="block"><div class="wrap rp-index">{cards}</div></section>'''
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(
        page("Weekly Pokémon Card Market Reports · Drive Your Style",
             "Weekly Pokémon card market reports: biggest price gains and drops, sealed product, new sets and sneaker drops.", "blog/", body))
    # sitemap: append the blog pages
    sm = os.path.join(site, "sitemap.xml")
    if os.path.exists(sm):
        x = open(sm, encoding="utf-8").read()
        x = re.sub(r"<url><loc>[^<]*/blog/[^<]*</loc>.*?</url>", "", x)
        add = f"<url><loc>{SITE}/blog/</loc></url>" + "".join(f"<url><loc>{SITE}/blog/{p['slug']}.html</loc><lastmod>{p['date']}</lastmod></url>" for p in posts)
        open(sm, "w", encoding="utf-8").write(x.replace("</urlset>", add + "</urlset>"))
    print(f"blog: {len(posts)} post(s)")


if __name__ == "__main__":
    main(sys.argv[1:])
