"""Static, crawlable price pages for the most-searched cards and sealed products.

    python tools/price_pages.py site [registry.json]

The interactive pages (product.html?id=...) are drawn in the browser, which search engines
index poorly. This writes plain HTML pages to site/p/<slug>.html with the price, recent
changes, a small price chart and links, and adds them to the sitemap. Rebuilt nightly.

How the list of pages is kept (so an address never disappears once it is published):
  - A registry remembers every page ever published and its address: data/pages/registry.json,
    which the nightly job saves on the data branch with the rest of data/.
    {"v": 1, "pages": {"<product id>|<item name>": ["<slug>", "<first day>", "<last day seen>"]}}
  - Every page in the registry is written again each night for as long as its item is still in
    the data, whatever its price or rank has become. Its address never changes.
  - New pages: Pokémon candidates are always added; the other games are added by price, most
    valuable first, only while the total is under CAP. Past MAX_PAGES nothing new is added (the
    run says so), so the site's size stays bounded.
  - First run (no registry yet, or one that can't be read, which is set aside and never overwritten):
    the registry is seeded from the pages that are live now (the site's data/pages.json, which this
    script publishes every night), so none of them is dropped. If that list can't be fetched the
    pages are built the old way for that night, nothing is saved, and the next night tries again.

Each page is also the full card page: the HTML written here is what search engines read, and
site/assets/app.js (data-page="price") then draws the interactive page over it. The address of
its page is written on each item in site/data/set/*.json ("pg"), so set pages and card pages
link straight to it.
"""
import glob
import html
import json
import os
import re
import subprocess
import sys
import unicodedata
import urllib.request
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_pages import HEAD  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "data", "pages", "registry.json")
SITE = "https://market.driveyourstyle.net"
STORE = "https://driveyourstyle.net"
GAME = {"pokemon": "Pokémon TCG", "pokemon-jp": "Pokémon Japan", "one-piece": "One Piece Card Game", "lorcana": "Disney Lorcana",
        "riftbound": "Riftbound", "palworld": "Palworld Card Game", "gundam": "Gundam Card Game", "union-arena": "Union Arena", "yugioh": "Yu-Gi-Oh!", "dragon-ball-fusion-world": "Dragon Ball Super Fusion World"}
# how many of each set's most valuable cards get a page (popular games get more)
PER_SET = {"pokemon": 25, "one-piece": 15, "pokemon-jp": 6, "lorcana": 10, "riftbound": 10, "gundam": 10, "union-arena": 6, "palworld": 6, "yugioh": 8, "dragon-ball-fusion-world": 8}
MIN_CARD, MIN_SEALED = 300, 1000
ALWAYS = {"pokemon"}   # games whose candidates always get a page
CAP = 11000            # the other games get new pages only while the total is under this
MAX_PAGES = 15000      # no new page for any game past this (a published page still always stays); keeps the site's size bounded
SKIP = re.compile(r"code card|\bjumbo\b|oversize", re.I)
BODY_TAG = '<body data-page="@@PAGE@@">'


def esc(t):
    return html.escape(str(t), quote=True)


def money(c):
    return "—" if c is None else f"${c / 100:,.2f}"


def money_shown(c):
    """The big price exactly as the page script shows it (money() in site/assets/app.js: whole dollars from $1,000),
    so the number doesn't change when the script draws the full page over this HTML."""
    return f"${int(c / 100 + 0.5):,}" if c >= 100000 else money(c)


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


def key_of(i):
    return f"{i['id']}|{i['n']}"


def set_short(d):
    return re.sub(r"^[A-Z0-9]{1,6}\d*[a-z]?\s*[:\-–]\s*", "", d["n"])


def shown_variant(i, nvar):
    v = i["n"][len(base_name(i["n"])):].strip(" ()")
    return v if v and (nvar.get(i["id"], 1) > 1 or v not in ("Holofoil", "Normal")) else ""


def new_slug(i, d, used, nvar):
    """The address for a page that has none yet. Never one that is already taken, now or in the past."""
    nm = slugify(base_name(i["n"]))
    s = nm if slugify(set_short(d)) in nm else slugify(f"{base_name(i['n'])} {set_short(d)}")
    if shown_variant(i, nvar):
        s = slugify(f"{s} {shown_variant(i, nvar)}")
    if not s:
        s = "item"
    if s in used:
        s = f"{s}-{i['id']}"
    stem, n = s, 2
    while s in used:
        s, n = f"{stem}-{n}", n + 1
    return s


def variant_counts(sets):
    n = {}
    for d in sets.values():
        for x in d["items"]:
            n[x["id"]] = n.get(x["id"], 0) + 1
    return n


def candidates(sets, today):
    """Items that qualify for a new page: each released set's most valuable cards and its sealed products."""
    out = []
    for gid in sorted(sets):
        d = sets[gid]
        if (d.get("pub") or "") > today:
            continue
        priced = [i for i in d["items"] if i.get("p") and not SKIP.search(i["n"])]
        cards = sorted((i for i in priced if i["t"] == "c" and i["p"] >= MIN_CARD), key=lambda i: -i["p"])[:PER_SET.get(d["k"], 6)]
        sealed = [i for i in priced if i["t"] == "s" and i["p"] >= MIN_SEALED]
        out += [(i, d) for i in cards + sealed]
    return out


def plan(sets, pages, today, cap=CAP, max_pages=MAX_PAGES):
    """Decide tonight's pages. `pages` is the registry's map and is updated in place.

    Returns ([(item, set, slug)], {"kept", "added", "resting", "waiting"}): every registered page whose
    item is still in the data, then new ones (ALWAYS games first, then the rest by price while under cap).
    "waiting" counts ALWAYS-game candidates left without a page because max_pages was reached.
    """
    index, nvar = {}, variant_counts(sets)
    for gid in sorted(sets):   # sorted, so an item listed under two sets always resolves to the same one
        for i in sets[gid]["items"]:
            index.setdefault(key_of(i), (i, sets[gid]))
    picks = []
    for k, rec in pages.items():
        hit = index.get(k)
        if hit:
            rec[2] = today
            picks.append((hit[0], hit[1], rec[0]))
    kept = len(picks)
    used = {rec[0] for rec in pages.values()}
    fresh = sorted(candidates(sets, today), key=lambda x: (x[1]["k"] not in ALWAYS, -x[0]["p"]))
    waiting = 0
    for i, d in fresh:
        k = key_of(i)
        if k in pages:
            continue
        if d["k"] not in ALWAYS and len(picks) >= cap:
            break   # sorted: only capped games remain
        if len(picks) >= max_pages:
            waiting += 1
            continue
        s = new_slug(i, d, used, nvar)
        used.add(s)
        pages[k] = [s, today, today]
        picks.append((i, d, s))
    return picks, {"kept": kept, "added": len(picks) - kept, "resting": len(pages) - len(picks), "waiting": waiting}


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_registry(path):
    """The registry's pages, or None when there is none to use. A file that can't be read is never overwritten:
    it is set aside under another name, and the registry starts again from the live page list."""
    if not os.path.exists(path):
        return None
    try:
        reg = read_json(path)
        pages = reg.get("pages") if isinstance(reg, dict) and reg.get("v") == 1 else None
        if not isinstance(pages, dict) or not all(isinstance(r, list) and len(r) == 3 and isinstance(r[0], str) and re.fullmatch(r"[a-z0-9-]+", r[0]) for r in pages.values()):
            raise ValueError("not a version 1 page registry")
        if len({r[0] for r in pages.values()}) != len(pages):
            raise ValueError("two pages share one address")
        return pages
    except Exception as e:
        aside = f"{path}.unreadable-{date.today().isoformat()}"
        os.replace(path, aside)
        print(f"::warning title=Price pages::The page registry could not be used ({str(e)[:100]}). It was set aside as {os.path.basename(aside)}; the registry starts again from the live page list.")
        return None


def save_registry(path, pages):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"v": 1, "pages": pages}, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def live_pages():
    """The pages that are live right now ({"<id>|<name>": "<slug>"}), from the site, else from the gh-pages branch."""
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{SITE}/data/pages.json", headers={"User-Agent": "dys-market price pages"}), timeout=60) as r:
            got = json.load(r)
        if isinstance(got, dict) and got:
            return got, "the live site"
    except Exception as e:
        print(f"price pages: live list not readable from the site ({str(e)[:120]})")
    try:
        subprocess.run(["git", "fetch", "-q", "--depth", "1", "origin", "gh-pages"], cwd=ROOT, check=True, timeout=600)
        got = json.loads(subprocess.run(["git", "show", "FETCH_HEAD:data/pages.json"], cwd=ROOT, check=True, capture_output=True, timeout=120).stdout)
        if isinstance(got, dict) and got:
            return got, "the gh-pages branch"
    except Exception as e:
        print(f"price pages: live list not readable from gh-pages ({str(e)[:120]})")
    return None, ""


def asset_version():
    """Same ?v= the publish step puts on the other pages (the run id), so the browser loads one copy of the script."""
    v = os.environ.get("GITHUB_RUN_ID", "")
    return v if v.isdigit() else date.today().strftime("%Y%m%d")


def render(i, d, s, slugs, nvar, today, head):
    name, game = base_name(i["n"]), GAME.get(d["k"], d["k"])
    variant = shown_variant(i, nvar)
    short = set_short(d)
    nice = name.replace(" - ", " ")
    kind = "sealed product" if i["t"] == "s" else "card"
    ch = i.get("ch") or {}
    wk = ch.get("7", ch.get("a"))
    trend = "" if wk is None else f" It is {'up' if wk > 0 else 'down'} {abs(wk):.1f}% {'over the past week' if '7' in ch else 'since we started tracking'}." if abs(wk) >= 0.5 else " Its price has been steady recently."
    num_txt = f", number {esc(i['no'])}" if i.get("no") else ""
    rar_txt = f", {esc(i['r'])}" if i.get("r") else ""
    when = date.fromisoformat(today).strftime("%B %-d, %Y")
    price_txt = (f"Its TCGplayer market price is <b>{money(i['p'])}</b> as of {when}.{trend}" if i.get("p")
                 else f"It has no TCGplayer market price as of {when}.")
    intro = (f"{esc(name)}{f' ({esc(variant)})' if variant else ''} is a {esc(game)} {kind} from {esc(d['n'])}"
             f"{num_txt}{rar_txt}. {price_txt}")
    more = [x for x in sorted(d["items"], key=lambda x: -(x.get("p") or 0)) if x.get("p") and x["id"] != i["id"] and x["t"] == i["t"]][:8]

    def href(x):
        k = key_of(x)
        return f"p/{slugs[k]}.html" if k in slugs else f"product.html?id={x['id']}&amp;set={d['id']}"
    more_html = "".join(
        f'<a class="pp-more" href="{href(x)}">'
        f'<img src="https://tcgplayer-cdn.tcgplayer.com/product/{x["id"]}_200w.jpg" alt="" loading="lazy" width="60" height="84" onerror="window.dysImg&amp;&amp;dysImg(this)"><span>{esc(base_name(x["n"]))}<b>{money(x["p"])}</b></span></a>' for x in more)
    dates = d.get("dates") or []
    ser = i.get("s") or []
    buy = (f'<a class="btn primary" href="{esc(i["dys"]["u"])}">Buy at Drive Your Style · {money(i["dys"]["p"])}</a>' if i.get("dys") else
           f'<a class="btn primary" href="{STORE}">Shop Drive Your Style</a>')
    set_href = f"set.html?id={d['id']}" + ("&amp;tab=sealed" if i["t"] == "s" else "")
    # Same frame as product.html (#crumbs, #prod): app.js draws the full card page into it once it loads.
    body = f'''<div class="wrap pp"><div class="crumbs" id="crumbs"><a class="crumb-back" href="{set_href}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg><span>Back to {esc(d["n"])}</span></a>
<nav class="crumb-path" aria-label="Breadcrumb"><ol><li><a href="sets.html">Sets</a></li><li><a href="sets.html?game={d["k"]}">{esc(game)}</a></li><li><a href="{set_href}">{esc(d["n"])}</a></li><li><span aria-current="page">{esc(name)}</span></li></ol></nav></div>
<div class="prod" id="prod">
<div class="prod-img"><img src="{img(i["id"])}" alt="{esc(name)}" width="500" height="700" onerror="window.dysImg&amp;&amp;dysImg(this)"></div>
<div><span class="muted">{esc(game)} · {esc(d["n"])}{f" · #{esc(i['no'])}" if i.get("no") else ""}{f" · {esc(i['r'])}" if i.get("r") else ""}</span>
<h1 style="font-size:clamp(26px,3.4vw,38px);margin-top:6px">{esc(nice)} price{f" <span class='muted' style='font-size:.6em'>{esc(variant)}</span>" if variant else ""}</h1>
<div class="muted" style="margin-top:14px">Market price</div><div class="price-big">{money_shown(i["p"]) if i.get("p") else "<span class='muted' style='font-size:.6em'>No market price yet</span>"}</div>
<div class="kpis">{"".join(f'<div class="kpi"><div class="l">{l}</div>{chg(ch.get(k))}</div>' for k, l in [("7", "7 days"), ("30", "30 days"), ("90", "90 days"), ("a", "Since tracking")])}</div>
<p style="line-height:1.65;margin-top:16px">{intro}</p>
{spark(ser, dates[-len(ser):] if ser else [])}
<div class="btns">{buy}<a class="btn" href="{set_href}">All {esc(short)} prices →</a></div>
<p class="muted" style="font-size:12.5px;margin-top:14px">Prices are TCGplayer market prices recorded nightly{" for Near Mint condition" if i["t"] == "c" else ""}. Updated {esc(today)}.</p>
</div></div>
{f'<section id="pp-static" style="margin-top:34px"><h2 style="font-size:22px">More from {esc(d["n"])}</h2><div class="pp-grid">{more_html}</div></section>' if more_html else ""}
</div>'''
    ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Sets", "item": f"{SITE}/sets.html"},
        {"@type": "ListItem", "position": 2, "name": game, "item": f"{SITE}/sets.html?game={d['k']}"},
        {"@type": "ListItem", "position": 3, "name": d["n"], "item": f"{SITE}/set.html?id={d['id']}"},
        {"@type": "ListItem", "position": 4, "name": name, "item": f"{SITE}/p/{s}.html"}]}
    title = f"{nice}{f' ({variant})' if variant else ''} Price – {short} | Drive Your Style"
    desc = (f"{name} ({d['n']}, {game}) market price today: {money(i['p'])}. Price history, recent changes and similar {kind}s." if i.get("p")
            else f"{name} ({d['n']}, {game}): price history, recent changes and similar {kind}s.")
    body_tag = f'<body data-page="price" data-id="{int(i["id"])}" data-set="{int(d["id"])}" data-var="{esc(i["n"])}">'
    return (head.replace("</head>", f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>\n</head>')
            .replace(BODY_TAG, body_tag)
            .replace("@@TITLE@@", esc(title)).replace("@@DESC@@", esc(desc)).replace("@@CANON@@", f"p/{s}.html")
            .replace('content="https://market.driveyourstyle.net/assets/og.png"', f'content="{img(i["id"])}"')
            .replace("@@BODY@@", body))


def main(argv):
    site = argv[0]
    reg_path = argv[1] if len(argv) > 1 else REGISTRY
    sd = os.path.join(site, "data")
    meta = read_json(os.path.join(sd, "meta.json"))
    today = meta.get("updated") or date.today().isoformat()
    sets, files = {}, {}
    for path in glob.glob(os.path.join(sd, "set", "*.json")):
        d = read_json(path)
        sets[d["id"]], files[d["id"]] = d, path

    pages, seeded, keep = load_registry(reg_path), "", True
    if pages is None:
        live, where = live_pages()
        if live is None:
            print("::warning title=Price pages::No page registry yet and the live page list could not be read. Pages are built the old way tonight (addresses near the price line may change); nothing is saved, and the next run tries again.")
            pages, keep = {}, False
        else:
            pages, taken = {}, set()
            for k, s in live.items():
                if isinstance(k, str) and isinstance(s, str) and re.fullmatch(r"[a-z0-9-]+", s) and s not in taken:
                    pages[k] = [s, "", ""]
                    taken.add(s)
            seeded = f", registry started from {where} ({len(pages)} pages)"

    picks, st = plan(sets, pages, today)
    if not keep and len(picks) > 9000:   # no registry to protect: stay at the old size
        picks = sorted(picks, key=lambda x: -(x[0].get("p") or 0))[:9000]

    nvar = variant_counts(sets)
    slugs = {key_of(i): s for i, _, s in picks}

    ver = asset_version()
    head = (HEAD.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n<base href="/">')
            .replace('assets/app.css"', f'assets/app.css?v={ver}"'))
    tail = f'assets/app.js?v={ver}"'
    out = os.path.join(site, "p")
    os.makedirs(out, exist_ok=True)
    for f in glob.glob(os.path.join(out, "*.html")):
        os.remove(f)
    for i, d, s in picks:
        page = render(i, d, s, slugs, nvar, today, head).replace('assets/app.js"', tail)
        with open(os.path.join(out, s + ".html"), "w", encoding="utf-8") as f:
            f.write(page)

    # sitemap: add the pages, drop product.html URLs they replace
    sm = os.path.join(site, "sitemap.xml")
    if os.path.exists(sm):
        with open(sm, encoding="utf-8") as f:
            x = f.read()
        covered = {str(i["id"]) for i, _, _ in picks}
        x = re.sub(r"<url><loc>[^<]*product\.html\?id=(\d+)&amp;set=\d+</loc>.*?</url>", lambda m: "" if m.group(1) in covered else m.group(0), x)
        x = re.sub(r"<url><loc>[^<]*/p/[^<]*</loc>.*?</url>", "", x)
        add = "".join(f"<url><loc>{SITE}/p/{s}.html</loc><lastmod>{today}</lastmod></url>" for _, _, s in picks)
        with open(sm, "w", encoding="utf-8") as f:
            f.write(x.replace("</urlset>", add + "</urlset>"))
    # the live list, published with the site: the registry can be started again from it if it is ever lost
    with open(os.path.join(sd, "pages.json"), "w", encoding="utf-8") as f:
        json.dump({key_of(i): s for i, _, s in picks}, f, ensure_ascii=False, separators=(",", ":"))
    # each item's page address, for the site's own links (written only now that every page exists)
    touched = {}
    for i, d, s in picks:
        i["pg"] = s
        touched[d["id"]] = d
    for gid, d in touched.items():
        tmp = files[gid] + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, files[gid])
    if keep:
        save_registry(reg_path, pages)
    if st["waiting"]:
        print(f"::warning title=Price pages::{st['waiting']} new Pokémon items have no price page because the limit of {MAX_PAGES} pages is reached (MAX_PAGES in tools/price_pages.py). Every existing page is still there.")
    print(f"price pages: {len(picks)} written ({st['kept']} kept, {st['added']} new, {st['resting']} resting){seeded}")


if __name__ == "__main__":
    main(sys.argv[1:])
