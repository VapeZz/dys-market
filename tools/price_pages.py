"""Static, crawlable price pages for the most-searched cards and sealed products.

    python tools/price_pages.py site

The interactive pages (product.html?id=...) are drawn in the browser, which search engines
index poorly. This writes plain HTML pages to site/p/<slug>.html with the price, recent
changes, a small price chart and links, and adds them to the sitemap. Rebuilt nightly.
"""
import glob
import html
import json
import os
import re
import sys
import unicodedata
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_pages import HEAD  # noqa: E402

SITE = "https://market.driveyourstyle.net"
STORE = "https://driveyourstyle.net"
GAME = {"pokemon": "Pokémon TCG", "pokemon-jp": "Pokémon Japan", "one-piece": "One Piece Card Game", "lorcana": "Disney Lorcana",
        "riftbound": "Riftbound", "palworld": "Palworld Card Game", "gundam": "Gundam Card Game", "union-arena": "Union Arena", "yugioh": "Yu-Gi-Oh!", "dragon-ball-fusion-world": "Dragon Ball Super Fusion World"}
# how many of each set's most valuable cards get a page (popular games get more)
PER_SET = {"pokemon": 25, "one-piece": 15, "pokemon-jp": 6, "lorcana": 10, "riftbound": 10, "gundam": 10, "union-arena": 6, "palworld": 6, "yugioh": 8, "dragon-ball-fusion-world": 8}
MIN_CARD, MIN_SEALED, CAP = 300, 1000, 9000
SKIP = re.compile(r"code card|\bjumbo\b|oversize", re.I)


def esc(t):
    return html.escape(str(t), quote=True)


def money(c):
    return "—" if c is None else f"${c / 100:,.2f}"


def slugify(t):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    t = re.sub(r"&", " and ", t.lower())
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:90]


def img(pid):
    return f"https://tcgplayer-cdn.tcgplayer.com/product/{pid}_in_1000x1000.jpg"


def spark(vals, dates):
    vals = [v for v in vals if v]
    if len(vals) < 2:
        return ""
    w, h, lo, hi = 640, 160, min(vals), max(vals)
    rng = (hi - lo) or 1
    pts = " ".join(f"{i * w / (len(vals) - 1):.1f},{h - 12 - (v - lo) / rng * (h - 24):.1f}" for i, v in enumerate(vals))
    up = vals[-1] >= vals[0]
    return (f'<figure class="pp-chart"><svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" role="img" aria-label="Market price over the last {len(vals)} days">'
            f'<polyline points="{pts}" fill="none" stroke="{"#3ee08f" if up else "#ff6b81"}" stroke-width="3" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>'
            f'<figcaption><span>{esc(dates[0]) if dates else ""}</span><span>Low {money(lo)} · High {money(hi)}</span><span>{esc(dates[-1]) if dates else ""}</span></figcaption></figure>')


def chg(v):
    if v is None:
        return '<span class="muted">—</span>'
    return f'<span class="chg {"up" if v > 0 else "down" if v < 0 else ""}">{"▲" if v > 0 else "▼" if v < 0 else ""} {abs(v):.1f}%</span>'


def base_name(n):
    return re.sub(r" \((Holofoil|Reverse Holofoil|Normal|1st Edition.*?|Unlimited.*?)\)$", "", n)


def main(argv):
    site = argv[0]
    sd = os.path.join(site, "data")
    meta = json.load(open(os.path.join(sd, "meta.json")))
    today = meta.get("updated") or date.today().isoformat()
    picks, sets = [], {}
    for path in glob.glob(os.path.join(sd, "set", "*.json")):
        d = json.load(open(path))
        if (d.get("pub") or "") > today:
            continue
        sets[d["id"]] = d
        priced = [i for i in d["items"] if i.get("p") and not SKIP.search(i["n"])]
        cards = sorted((i for i in priced if i["t"] == "c" and i["p"] >= MIN_CARD), key=lambda i: -i["p"])[:PER_SET.get(d["k"], 6)]
        sealed = [i for i in priced if i["t"] == "s" and i["p"] >= MIN_SEALED]
        picks += [(i, d) for i in cards + sealed]
    picks.sort(key=lambda x: -x[0]["p"])
    picks = picks[:CAP]

    nvar = {}
    for d in sets.values():
        for x in d["items"]:
            nvar[x["id"]] = nvar.get(x["id"], 0) + 1

    def shown_variant(i):
        v = i["n"][len(base_name(i["n"])):].strip(" ()")
        return v if v and (nvar.get(i["id"], 1) > 1 or v not in ("Holofoil", "Normal")) else ""

    out = os.path.join(site, "p")
    os.makedirs(out, exist_ok=True)
    for f in glob.glob(os.path.join(out, "*.html")):
        os.remove(f)
    slugs, used = {}, set()
    for i, d in picks:
        short = re.sub(r"^[A-Z0-9]{1,6}\d*[a-z]?\s*[:\-–]\s*", "", d["n"])
        nm = slugify(base_name(i["n"]))
        s = nm if slugify(short) in nm else slugify(f"{base_name(i['n'])} {short}")
        if shown_variant(i):
            s = slugify(f"{s} {shown_variant(i)}")
        if s in used:
            s = f"{s}-{i['id']}"
        used.add(s)
        slugs[(i["id"], i["n"])] = s

    head = HEAD.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n<base href="/">')
    for (i, d) in picks:
        s = slugs[(i["id"], i["n"])]
        name, game = base_name(i["n"]), GAME.get(d["k"], d["k"])
        variant = shown_variant(i)
        short = re.sub(r"^[A-Z0-9]{1,6}\d*[a-z]?\s*[:\-–]\s*", "", d["n"])
        nice = name.replace(" - ", " ")
        kind = "sealed product" if i["t"] == "s" else "card"
        ch = i.get("ch") or {}
        wk = ch.get("7", ch.get("a"))
        trend = "" if wk is None else f" It is {'up' if wk > 0 else 'down'} {abs(wk):.1f}% {'over the past week' if '7' in ch else 'since we started tracking'}." if abs(wk) >= 0.5 else " Its price has been steady recently."
        num_txt = f", number {esc(i['no'])}" if i.get("no") else ""
        rar_txt = f", {esc(i['r'])}" if i.get("r") else ""
        intro = (f"{esc(name)}{f' ({esc(variant)})' if variant else ''} is a {esc(game)} {kind} from {esc(d['n'])}"
                 f"{num_txt}{rar_txt}. "
                 f"Its TCGplayer market price is <b>{money(i['p'])}</b> as of {date.fromisoformat(today).strftime('%B %-d, %Y')}.{trend}")
        more = [x for x in sorted(d["items"], key=lambda x: -(x.get("p") or 0)) if x.get("p") and x["id"] != i["id"] and x["t"] == i["t"]][:8]
        def href(x):
            k = (x["id"], x["n"])
            return f"p/{slugs[k]}.html" if k in slugs else f"product.html?id={x['id']}&amp;set={d['id']}"
        more_html = "".join(
            f'<a class="pp-more" href="{href(x)}">'
            f'<img src="https://tcgplayer-cdn.tcgplayer.com/product/{x["id"]}_200w.jpg" alt="" loading="lazy" width="60" height="84"><span>{esc(base_name(x["n"]))}<b>{money(x["p"])}</b></span></a>' for x in more)
        dates = d.get("dates") or []
        ser = i.get("s") or []
        buy = (f'<a class="btn primary" href="{esc(i["dys"]["u"])}">Buy at Drive Your Style · {money(i["dys"]["p"])}</a>' if i.get("dys") else
               f'<a class="btn primary" href="{STORE}">Shop Drive Your Style</a>')
        body = f'''<div class="wrap pp"><p class="crumbs"><a href="sets.html">Sets</a> / <a href="set.html?id={d["id"]}">{esc(d["n"])}</a> / {esc(name)}</p>
<div class="prod">
<div class="prod-img"><img src="{img(i["id"])}" alt="{esc(name)}" width="500" height="700"></div>
<div><span class="muted">{esc(game)} · {esc(d["n"])}{f" · #{esc(i['no'])}" if i.get("no") else ""}{f" · {esc(i['r'])}" if i.get("r") else ""}</span>
<h1 style="font-size:clamp(26px,3.4vw,38px);margin-top:6px">{esc(nice)} price{f" <span class='muted' style='font-size:.6em'>{esc(variant)}</span>" if variant else ""}</h1>
<div class="muted" style="margin-top:14px">Market price</div><div class="price-big">{money(i["p"])}</div>
<div class="kpis">{"".join(f'<div class="kpi"><div class="l">{l}</div>{chg(ch.get(k))}</div>' for k, l in [("7", "7 days"), ("30", "30 days"), ("90", "90 days"), ("a", "Since tracking")])}</div>
<p style="line-height:1.65;margin-top:16px">{intro}</p>
{spark(ser, dates[-len(ser):] if ser else [])}
<div class="btns">{buy}<a class="btn" href="product.html?id={i["id"]}&set={d["id"]}">Full price history &amp; tools →</a>
<a class="btn" href="product.html?id={i["id"]}&set={d["id"]}#sell">💵 Sell yours to us</a></div>
<p class="muted" style="font-size:12.5px;margin-top:14px">Prices are TCGplayer market prices recorded nightly{" for Near Mint condition" if i["t"] == "c" else ""}. Updated {esc(today)}.</p>
</div></div>
{f'<section style="margin-top:34px"><h2 style="font-size:22px">More from {esc(d["n"])}</h2><div class="pp-grid">{more_html}</div></section>' if more_html else ""}
</div>'''
        ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Sets", "item": f"{SITE}/sets.html"},
            {"@type": "ListItem", "position": 2, "name": d["n"], "item": f"{SITE}/set.html?id={d['id']}"},
            {"@type": "ListItem", "position": 3, "name": name, "item": f"{SITE}/p/{s}.html"}]}
        title = f"{nice}{f' ({variant})' if variant else ''} Price – {short} | Drive Your Style"
        desc = f"{name} ({d['n']}, {game}) market price today: {money(i['p'])}. Price history, recent changes and similar {kind}s."
        page = (head.replace("</head>", f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>\n</head>')
                .replace("@@TITLE@@", esc(title)).replace("@@DESC@@", esc(desc)).replace("@@CANON@@", f"p/{s}.html")
                .replace('content="https://market.driveyourstyle.net/assets/og.png"', f'content="{img(i["id"])}"')
                .replace("@@PAGE@@", "static").replace("@@BODY@@", body))
        with open(os.path.join(out, s + ".html"), "w", encoding="utf-8") as f:
            f.write(page)

    # sitemap: add the pages, drop product.html URLs they replace
    sm = os.path.join(site, "sitemap.xml")
    if os.path.exists(sm):
        x = open(sm, encoding="utf-8").read()
        covered = {str(i["id"]) for i, _ in picks}
        x = re.sub(r"<url><loc>[^<]*product\.html\?id=(\d+)&amp;set=\d+</loc>.*?</url>", lambda m: "" if m.group(1) in covered else m.group(0), x)
        x = re.sub(r"<url><loc>[^<]*/p/[^<]*</loc>.*?</url>", "", x)
        add = "".join(f"<url><loc>{SITE}/p/{slugs[(i['id'], i['n'])]}.html</loc><lastmod>{today}</lastmod></url>" for i, _ in picks)
        open(sm, "w", encoding="utf-8").write(x.replace("</urlset>", add + "</urlset>"))
    # id -> page, so the interactive page can point search engines at the static one
    with open(os.path.join(sd, "pages.json"), "w", encoding="utf-8") as f:
        json.dump({f"{i['id']}|{i['n']}": slugs[(i["id"], i["n"])] for i, _ in picks}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"price pages: {len(picks)} written")


if __name__ == "__main__":
    main(sys.argv[1:])
