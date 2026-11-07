"""Regenerates site/*.html from one shared template. Run: python tools/make_pages.py"""
import os
import re
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GW_BANNER = '''<section class="block" style="padding-top:0;padding-bottom:0"><div class="wrap"><a class="report-banner gw-banner" href="giveaway.html?ref=home"><div><b>🎁 Win an Elite Trainer Box every month</b><span>Free to enter: build your binder on the site. Bonus entries for every friend you bring.</span></div><span>Enter →</span></a></div></section>
'''
GIVEAWAY_ON = False   # paused: hides the homepage banner and the bio link; giveaway.html says it's paused

HEAD = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>@@TITLE@@</title>
<meta name="description" content="@@DESC@@">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Drive Your Style Market Insights">
<meta property="og:title" content="@@TITLE@@">
<meta property="og:description" content="@@DESC@@">
<meta property="og:image" content="https://market.driveyourstyle.net/assets/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="@@TITLE@@">
<meta name="twitter:description" content="@@DESC@@">
<meta name="twitter:image" content="https://market.driveyourstyle.net/assets/og.png">
<link rel="canonical" href="https://market.driveyourstyle.net/@@CANON@@">
<meta name="theme-color" content="#0b0d14">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="assets/app.css">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="assets/icons/apple-touch-icon.png">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="DYS Market">
<link rel="icon" type="image/png" href="assets/favicon.png">
<script data-goatcounter="https://driveyourstyle.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
<script>try{document.documentElement.dataset.theme=localStorage.getItem("dys-theme")||"dark"}catch(e){document.documentElement.dataset.theme="dark"}</script>
</head>
<body data-page="@@PAGE@@">
<header id="top"></header>
<main>
@@BODY@@
</main>
<footer id="foot"></footer>
<script src="assets/app.js"></script>
</body>
</html>
'''
SEARCH = '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>'
SK = '<div class="stat"><div class="skeleton"></div></div>'
MOVERS = '''<div class="movers"><div class="panel"><h3><span class="chg up">▲</span> Biggest gains</h3><div data-up></div></div>
  <div class="panel"><h3><span class="chg down">▼</span> Biggest drops</h3><div data-down></div></div></div>'''

AMZ_TAG = "driveyourstyl-20"   # Amazon Associates tracking id (also in site/assets/app.js AFF.amazon)


def amz(q):
    """Amazon search link with our Associates tag (search links: no prices or Amazon images on our pages)."""
    from urllib.parse import quote_plus
    return f"https://www.amazon.com/s?k={quote_plus(q)}&tag={AMZ_TAG}"


SUPPLIES = [
    ("Before you grade", "What PSA, CGC and BGS want in the box, and what saves you a wasted fee.", [
        ("Penny sleeves", "Every card goes in a soft sleeve first so it never touches hard plastic.", "Ultra Pro penny sleeves"),
        ("Card Saver 1 holders", "The semi-rigid holder PSA asks for. Graders can slide cards out without damage, unlike top loaders.", "Cardboard Gold Card Saver 1"),
        ("Team bags", "Seal each Card Saver so dust and moisture stay out on the way to the grader.", "resealable team bags trading cards"),
        ("Microfiber cloth", "Wipe fingerprints and dust off the surface right before it goes in.", "microfiber cleaning cloth"),
        ("LED loupe", "Check corners, edges and surface for whitening and scratches before you pay to grade.", "jeweler loupe LED 30x 60x"),
    ]),
    ("Store & display", "Keep raw cards and slabs in the condition you bought them.", [
        ("Top loaders (35pt)", "Stiff protection for cards you keep or ship.", "Ultra Pro toploaders 35pt"),
        ("9-pocket binder", "Side-loading pages keep a whole set together without cards sliding out.", "Vault X 9 pocket binder"),
        ("Magnetic one-touch holders", "Show off your best raw cards on a shelf or at a card show.", "magnetic card holder 35pt one touch"),
        ("Graded slab storage box", "Holds PSA, CGC and BGS slabs upright and scratch-free.", "graded card storage box PSA slabs"),
    ]),
    ("Ship cards", "What sellers use so cards arrive in the grade you sold them in.", [
        ("Bubble mailers 4x8", "Fits a top loader with room for cardboard on both sides.", "bubble mailers 4x8"),
        ("Painter's tape", "Seals the top loader shut and peels off without sticky residue.", "painters tape 1 inch"),
    ]),
]


def supplies_body():
    out = []
    for h, sub, items in SUPPLIES:
        cards = "".join(f'<a class="sup" href="{amz(q)}" target="_blank" rel="sponsored noopener"><b>{t}</b><span>{why}</span><em>See on Amazon →</em></a>' for t, why, q in items)
        out.append(f'<section class="block" style="padding-top:8px"><div class="block-head"><div><h2>{h}</h2><p>{sub}</p></div></div><div class="sup-grid">{cards}</div></section>')
    return f"""
<div class="wrap"><section class="block" style="padding-bottom:0">
  <span class="in-kicker">GRADING · STORAGE · SHIPPING</span><h1 class="in-h">Grading supplies</h1>
  <p class="muted" style="max-width:760px;margin:-6px 0 6px">What we use to send cards to PSA, CGC and BGS, and to store and ship them. Not sure a card is worth grading yet? Check it with <a href="grading.html">Grading Insights</a> and the <a href="centering.html">centering check</a> first.</p>
  <p class="muted" style="font-size:13px;margin:0">Links go to Amazon. As an Amazon Associate we earn from qualifying purchases, at no extra cost to you.</p>
</section>
{''.join(out)}
</div>"""


SUPPLIES_BODY = supplies_body()

# tools.html: every tool on one page (the "Tools" tab of the new layout)
_I = lambda d: f'<span class="tool-i"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{d}</svg></span>'


def nav_from_app():
    """The site menu (NAV in site/assets/app.js) as [(group, [(href, label, one-liner, icon path)])], so the Tools page and the
    home shortcuts always use the same names as the header menu."""
    js = open(os.path.join(ROOT, "site", "assets", "app.js"), encoding="utf-8").read()
    block = js[js.index("const NAV = ["):js.index("const NAV_SNEAKERS")]
    item = re.compile(r"""\["([\w/]+)", "([^"]+)", "([^"]*)", '([^']*)'\]""")
    href = lambda pg: pg if pg.endswith("/") else f"{pg}.html"
    groups = []
    for g in re.finditer(r'\n  \["([^"]+)", \[(.*?)\n  \], \[', block, re.S):
        items = [(href(m[1]), m[2], m[3], m[4]) for m in item.finditer(g[2]) if GIVEAWAY_ON or m[1] != "giveaway"]
        groups.append((g[1], items))
    sn = item.search(js[js.index("const NAV_SNEAKERS"):])
    groups.append(("Sneakers", [(href(sn[1]), sn[2], sn[3], sn[4]),
                                ("https://driveyourstyle.net", "Shop the store", "Sealed, singles, sneakers", '<path d="M6 7h12l-1 13H7z"/><path d="M9 7a3 3 0 0 1 6 0"/>')]))
    assert len(groups) == 5 and all(i for _, i in groups), "couldn't read NAV from app.js"
    return groups


HUB = nav_from_app()
HOME_TOOLS = ["search.html", "grading.html", "centering.html", "collection.html", "watchlist.html", "intel.html", "calendar.html", "sell.html"]
NAV_ITEM = {u: (t, d, ic) for _, items in HUB for u, t, d, ic in items}


def tool_tile(u):
    t, d, ic = NAV_ITEM[u]
    return f'<a class="tool" href="{u}">{_I(ic)}<b>{t}</b><span>{d}</span></a>'


TOOLS_BODY = '<div class="wrap"><section class="block" style="padding-bottom:4px"><h1 class="in-h">All tools</h1><p class="muted" style="margin:-6px 0 0">Everything on the site, in the same groups as the menu. Free, no sign-up needed.</p></section>' + "".join(
    f'<section class="block hub-sec"><h2>{h}</h2><div class="hub">' + "".join(f'<a class="tool" href="{u}">{_I(d)}<b>{t}</b><span>{s}</span></a>' for u, t, s, d in items) + "</div></section>"
    for h, items in HUB) + "</div>"


# investing.html: the card investing playbook (long-form guide, with a live sealed-movers board filled in by app.js)
_PB_ICON = lambda d: f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{d}</svg>'
PB_CHAPTERS = [("lanes", "Pick your lane"), ("cycle", "How prices move"), ("grading", "Does grading pay?"),
               ("risk", "Protect the downside"), ("sell", "Know when to sell"), ("routine", "Your weekly routine"), ("faq", "Questions")]
PB_RULES = [
    ("Pay for scarcity, not hype.", "Prices built on excitement fade. Prices built on short supply tend to stick."),
    ("Set your sell price before you buy.", "If you can't name it, you're guessing."),
    ("Count every fee.", "Grading, shipping and selling fees are part of what you paid."),
    ("Grade the card you have.", "Not the one you hope it is."),
    ("Spread it out.", "No single set or product should be able to sink your budget."),
]
# name, icon, what it is, hold time, budget/effort/risk (1-3), works when, watch for, [(link, label)]
PB_LANES = [
    ("Sealed stacker", '<path d="M4 8l8-4 8 4v8l-8 4-8-4z"/><path d="M4 8l8 4 8-4M12 12v8"/>',
     "Buy booster boxes, ETBs and collection boxes near retail. Hold until they're out of print and gone from shelves.",
     "2–5+ years", 2, 1, 2,
     "you can buy close to retail and store boxes flat, dry and out of sunlight.",
     "reprints, crushed or resealed shrink wrap, and money locked up for years.",
     [("trends.html", "Sealed trends")]),
    ("Grader", '<path d="M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.4 6.8 19.1l1-5.8L3.5 9.2l5.9-.9z"/>',
     "Buy raw cards that look clean, send them to PSA, CGC or BGS, then sell or keep the slabs.",
     "2–6 months", 1, 3, 2,
     "the gap between a raw copy and a 10 is wide enough to cover every fee, and still works if it comes back a 9.",
     "grading fees, slow turnaround, and cards that come back an 8.",
     [("grading.html", "Grading Insights"), ("centering.html", "Centering check")]),
    ("Flipper", '<path d="M7 7h11l-3-3M17 17H6l3 3"/>',
     "Buy under market at card shows, local shops and in bulk lots, then resell within weeks.",
     "Days to weeks", 1, 3, 1,
     "you buy far enough under market price to profit after selling fees and shipping.",
     "chasing whatever's trending, and margins that vanish once fees come out.",
     [("cards.html", "Card movers"), ("watchlist.html", "Want list")]),
    ("Long-term collector", '<path d="M4 6h16v12H4z"/><path d="M4 10h16"/>',
     "Own the cards you'd want anyway: iconic Pokémon, vintage, top chase cards, in the best condition you can afford.",
     "5+ years", 3, 1, 2,
     "you'd be happy holding the card even if its price went flat.",
     "buying at a peak, and fakes on big-ticket cards. Buy those graded, or from sellers with a track record.",
     [("collection.html", "My Collection")]),
]
PB_PHASES = [
    ("Release buzz", "Pre-orders and the first weeks. Excitement pushes prices above retail, often on just a few sales."),
    ("Supply catches up", "Big print runs reach stores. Prices slide, and sealed often dips under retail. Patient buyers shop here."),
    ("On the shelf", "Prices go flat while the product is still easy to find. Little upside, little pressure."),
    ("Out of print", "Printing stops and stock dries up. Demand stays, supply doesn't, and prices can climb. A reprint can reset it all."),
]
PB_DRIVERS = [
    ("Print run", "How much was made. Big runs and reprints hold prices down; short runs push them up.", '<path d="M6 9V3h12v6M6 18H4v-7h16v7h-2"/><path d="M6 14h12v7H6z"/>'),
    ("Character pull", "Charizard, Pikachu, Umbreon and other fan favorites carry demand from set to set.", '<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>'),
    ("Artwork", "Full arts and illustration rares with standout art keep drawing collectors long after release.", '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/>'),
    ("Condition & pop", "The grade, and how many 10s exist. A low PSA 10 count can make a 10 worth many times the raw card.", '<path d="M4 19V9M10 19V5M16 19v-7M22 19H2"/>'),
    ("Liquidity", "How often it sells. A price built on three sales is a guess; one built on three hundred is a market.", '<path d="M3 12h4l3-8 4 16 3-8h4"/>'),
]
PB_CHECK = [
    ("Centering is inside the grader's 10 range.", ("centering.html", "Check it from a photo")),
    ("The surface is clean under a bright light: no scratches, print lines or dents.", None),
    ("Corners and edges show no whitening under a loupe.", None),
    ("The raw-to-10 gap covers every fee, and the math still works if it's a 9.", ("grading.html", "Grading Insights runs this for every card")),
    ("You'd be fine keeping it if it doesn't hit.", None),
]
# title, what goes wrong, what to do, optional (link, label)
PB_RISKS = [
    ("Reprints", "A new print run can knock a product's price down overnight.", "Watch announcements and the release calendar before buying in bulk.", ("calendar.html", "Release calendar")),
    ("Fakes & reseals", "Counterfeit cards and resealed packs show up most on expensive items.", "Buy big-ticket cards graded or from sellers with a long record. Check shrink wrap seams and logos.", None),
    ("Hype spikes", "A price that doubles in a week on a handful of sales often gives most of it back.", "Wait for the number of sales to catch up before you chase.", ("cards.html", "Card movers")),
    ("Fee drag", "Selling fees, shipping and grading take a big bite out of cheaper cards.", "Price every buy after fees, not before.", None),
    ("Condition damage", "Heat, humidity and loose storage turn a 10 into an 8 while it sits in a drawer.", "Sleeves, top loaders or Card Savers, and a cool, dry spot.", ("supplies.html", "Grading supplies")),
    ("Cash tied up", "Money in a box you can't sell for three years can't buy the next deal.", "Keep part of your budget free for buys that come up.", None),
]
PB_SELL = ["It hit the price you set when you bought it.", "It jumped fast on only a few sales.", "A reprint or new print run was announced.",
           "The number of PSA 10s is climbing quickly.", "You found a better use for the money."]
PB_HOLD = ["It just went out of print and stock is drying up.", "The price dipped on a quiet week with no news.",
           "Its demand comes from a character or artwork collectors chase year after year.", "Selling now would mean handing the profit to fees."]
PB_WHERE = [
    ("TCGplayer", "Raw singles at market price. Buyers search by card, so common cards sell fast."),
    ("eBay", "Graded cards and high-value singles. Sold listings show exactly what buyers paid."),
    ("Whatnot & live shows", "Volume, bundles and cards that sell better in front of a crowd."),
    ("Local shops & card shows", "Quick cash and trades, with no shipping risk."),
]
PB_STEPS = [
    ("blog/", "Read the market report", "Our Sunday write-up: what climbed, what dropped and why."),
    ("cards.html", "Scan the movers", "Check card movers and sealed trends for anything you own or want."),
    ("collection.html", "Update your collection", "Add new pickups so you always know what your binder is worth."),
    ("watchlist.html", "Set your max prices", "Put the most you'd pay on your Want list, and only buy at your number."),
]
PB_FAQ = [
    ("Sealed or singles: which is the better investment?",
     "They do different jobs. Sealed is simple to hold and tends to rise once a product goes out of print, but it ties up more cash and is exposed to reprints. Singles let you buy exactly the card you want, and top cards can outrun sealed, but condition matters far more. Plenty of collectors hold some of both."),
    ("How long should I hold sealed product?",
     "Usually at least until it's out of print and gone from store shelves, which is often a year or more after release. Many sealed holders plan on three to five years. Sealed trends shows where a product sits on its price cycle."),
    ("Are Japanese cards worth investing in?",
     "They're their own market. Japanese sets often release first, use smaller packs, and some artwork never comes out in English. Their prices don't always move with the English versions, so track them separately. Pokémon Japan has its own set pages on this site."),
    ("Which grading company should I use?",
     "For most Pokémon cards, PSA 10s sell for the most, so most people grading to sell choose PSA. CGC and BGS can make sense when their fees or turnaround fit a card's value better. Check what each slab actually sells for before you pick."),
    ("Will I get the market price when I sell?",
     "Not quite. Market price here reflects recent completed sales on TCGplayer. What you keep is that price minus selling fees and shipping, and a card can sell above or below it on any given day."),
    ("Is this financial advice?",
     "No. This page explains how the card market tends to work. Cards can lose value, and past prices don't promise future ones. Only put in money you're comfortable holding for a long time."),
]
PB_TOOLS = ["search.html", "trends.html", "cards.html", "grading.html", "centering.html", "collection.html", "watchlist.html", "sell.html"]
PB_TITLE = "Pokémon Card Investing Playbook · Drive Your Style Market Insights"
PB_DESC = "A plain-English playbook for investing in Pokémon and TCG cards: pick a strategy, read the price cycle, run the grading math, avoid common losses and know when to sell."


def investing_body():
    import json
    lvl = ("Low", "Medium", "High")

    def lk(link):
        return f' <a href="{link[0]}">{link[1]} →</a>' if link else ""

    def pips(n):
        return "".join(f'<i class="{"on" if k < n else ""}"></i>' for k in range(3)) + f"<em>{lvl[n - 1]}</em>"

    def chapter(n, cid, title, intro, inner):
        return (f'<section class="pb-ch" id="{cid}"><header class="pb-ch-h"><span class="pb-num">{n:02d}</span>'
                f'<div><h2>{title}</h2><p>{intro}</p></div></header>{inner}</section>')

    rules = "".join(f"<li><b>{t}</b> <span>{s}</span></li>" for t, s in PB_RULES)
    toc = "".join(f'<a href="#{c}"><span>{i:02d}</span>{t}</a>' for i, (c, t) in enumerate(PB_CHAPTERS, 1))
    lanes = "".join(
        f'''<article class="pb-lane"><div class="pb-lane-top"><span class="pb-ico">{_PB_ICON(ic)}</span><h3>{name}</h3></div>
  <p class="pb-lane-what">{what}</p>
  <dl class="pb-meters"><div><dt>Hold</dt><dd class="pb-hold">{hold}</dd></div><div><dt>Budget</dt><dd>{pips(b)}</dd></div><div><dt>Effort</dt><dd>{pips(e)}</dd></div><div><dt>Risk</dt><dd>{pips(r)}</dd></div></dl>
  <p class="pb-lane-why"><b>Works when</b> {works}</p><p class="pb-lane-why"><b>Watch for</b> {watch}</p>
  <div class="pb-lane-go">{"".join(f'<a href="{u}">{l} →</a>' for u, l in links)}</div></article>'''
        for name, ic, what, hold, b, e, r, works, watch, links in PB_LANES)
    # typical sealed price arc: buzz above retail, slide under it, flat, climb once out of print (dotted: a reprint resets it)
    cycle_svg = '''<div class="pb-cy-wrap"><svg class="pb-cycle-svg" viewBox="0 0 640 230" preserveAspectRatio="none" role="img" aria-label="Typical sealed price arc: above retail at release, dips below retail as supply lands, flat on the shelf, then climbs once out of print, unless it is reprinted.">
  <defs><linearGradient id="pb-cy-g" x1="0" x2="1" y1="0" y2="0"><stop offset="0" style="stop-color:var(--accent-2)"/><stop offset=".55" style="stop-color:var(--accent)"/><stop offset="1" style="stop-color:#ff7ad9"/></linearGradient></defs>
  <g class="pb-cy-grid"><line x1="160" y1="16" x2="160" y2="230"/><line x1="320" y1="16" x2="320" y2="230"/><line x1="480" y1="16" x2="480" y2="230"/></g>
  <line class="pb-cy-retail" x1="0" y1="132" x2="640" y2="132"/>
  <path class="pb-cy-area" d="M0 132 C 30 60, 70 52, 110 74 S 190 176, 240 168 S 300 160, 340 158 S 420 150, 480 132 S 580 52, 640 40 L640 230 L0 230 Z"/>
  <path class="pb-cy-line" d="M0 132 C 30 60, 70 52, 110 74 S 190 176, 240 168 S 300 160, 340 158 S 420 150, 480 132 S 580 52, 640 40"/>
  <path class="pb-cy-alt" d="M480 132 S 530 100, 560 104 S 610 170, 640 172"/>
</svg><span class="pb-cy-ret" aria-hidden="true">RETAIL</span>''' + "".join(f'<span class="pb-cy-m" style="left:{x}%" aria-hidden="true">{i}</span>' for i, x in enumerate((12.5, 37.5, 62.5, 87.5), 1)) + "</div>"
    phases = "".join(f'<li><span class="pb-ph-n">{i}</span><b>{t}</b><span>{s}</span></li>' for i, (t, s) in enumerate(PB_PHASES, 1))
    drivers = "".join(f'<div class="pb-driver"><span class="pb-ico">{_PB_ICON(ic)}</span><b>{t}</b><span>{s}</span></div>' for t, s, ic in PB_DRIVERS)
    board = '''<div class="pb-board" id="pb-board" hidden>
    <div class="pb-board-h"><div><h3>On the board this week</h3><p>Every pattern above shows up in real prices. The biggest moves in Pokémon sealed ($20+) <span id="pb-board-when">this week</span>.</p></div><a class="more" href="trends.html">All sealed movers →</a></div>
    <div class="pb-board-cols"><div class="panel"><h3><span class="chg up">▲</span> Climbing</h3><div data-up></div></div>
    <div class="panel"><h3><span class="chg down">▼</span> Cooling off</h3><div data-down></div></div></div></div>'''
    receipt = '''<div class="pb-receipt" aria-label="Worked example">
    <span class="pb-rc-t">Worked example</span>
    <div class="pb-rc-sec"><span class="pb-rc-k">The card</span>
      <p><span>Raw market price</span><b>$40</b></p><p><span>PSA 10 sells for</span><b>$180</b></p><p><span>PSA 9 sells for</span><b>$65</b></p><p><span>Lower grades, about 0.7× raw</span><b>$28</b></p></div>
    <div class="pb-rc-sec"><span class="pb-rc-k">Your odds</span>
      <div class="pb-odds" role="img" aria-label="35% chance of a 10, 45% a 9, 20% lower"><span style="flex:35" class="o10">10 · 35%</span><span style="flex:45" class="o9">9 · 45%</span><span style="flex:20" class="olo">20%</span></div></div>
    <div class="pb-rc-sec"><span class="pb-rc-k">The math</span>
      <p><span>Expected sale<small>35% × $180 + 45% × $65 + 20% × $28</small></span><b>$97.85</b></p>
      <p><span>After ~13% selling fees</span><b>$85.13</b></p>
      <p><span>Cost in<small>$40 card + $30 grading and shipping</small></span><b>−$70.00</b></p></div>
    <p class="pb-rc-total"><span>Expected profit</span><b>+$15.13</b></p>
    <p class="pb-rc-be"><span>Break-even PSA 10 price</span><b>$130 <small>(3.3× raw)</small></b></p>
    <p class="pb-rc-note">Drop the odds of a 10 to 20% and the same card loses about $5. Your odds matter more than any other number here.</p>
  </div>'''
    checklist = "".join(f'<li><span class="pb-tick" aria-hidden="true">✓</span><span>{t}{lk(l)}</span></li>' for t, l in PB_CHECK)
    risks = "".join(f'<div class="pb-risk"><b>{t}</b><p>{w}</p><p class="pb-fix"><span>Do this</span>{d}{lk(l)}</p></div>' for t, w, d, l in PB_RISKS)
    sell = "".join(f"<li>{s}</li>" for s in PB_SELL)
    hold = "".join(f"<li>{s}</li>" for s in PB_HOLD)
    where = "".join(f'<div class="pb-where-row"><b>{t}</b><span>{s}</span></div>' for t, s in PB_WHERE) + \
        '<a class="pb-where-row pb-where-us" href="sell.html"><b>Drive Your Style</b><span>One offer for the whole stack, cash or store credit. <em>Get an offer →</em></span></a>'
    steps = "".join(f'<a class="pb-step" href="{u}"><span class="pb-step-n">{i}</span><b>{t}</b><span>{s}</span></a>' for i, (u, t, s) in enumerate(PB_STEPS, 1))
    faq = "".join(f'<details class="pb-faq"><summary>{q}</summary><p>{a}</p></details>' for q, a in PB_FAQ)
    tools = "".join(tool_tile(u) for u in PB_TOOLS)
    ld = json.dumps([
        {"@context": "https://schema.org", "@type": "Article", "headline": "The card investing playbook", "description": PB_DESC,
         "author": {"@type": "Organization", "name": "Drive Your Style"}, "publisher": {"@type": "Organization", "name": "Drive Your Style", "url": "https://driveyourstyle.net"},
         "mainEntityOfPage": "https://market.driveyourstyle.net/investing.html", "datePublished": "2026-11-07", "image": "https://market.driveyourstyle.net/assets/og.png"},
        {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in PB_FAQ]},
    ], ensure_ascii=False).replace("</", "<\\/")

    body = [
        chapter(1, "lanes", "Pick your lane", "Four ways people make money with cards. Each takes a different budget, patience and amount of work. Most people do best focusing on one or two.",
                f'<div class="pb-lanes">{lanes}</div>'),
        chapter(2, "cycle", "How prices move", "Most sealed products follow the same arc after release. Knowing where a product sits on it tells you whether you're early, late or right on time.",
                f'''<div class="pb-cycle panel">{cycle_svg}<div class="pb-cy-key"><span><i class="k-line"></i>Market price</span><span><i class="k-retail"></i>Retail</span><span><i class="k-alt"></i>If it's reprinted</span></div>
  <ol class="pb-phases">{phases}</ol><p class="pb-cap">A common pattern, not a promise. Plenty of products never climb, and a hot set can skip the dip.</p></div>
  <h3 class="pb-sub">What actually moves a price</h3><div class="pb-drivers">{drivers}</div>{board}'''),
        chapter(3, "grading", "Does grading pay?", "Grading is a bet on the grade. The math takes a minute once you write it down; skip it and fees quietly eat the profit.",
                f'''<div class="pb-math">{receipt}<div class="pb-check"><h3>Before you submit</h3><ul>{checklist}</ul>
  <a class="report-banner" href="supplies.html"><div><b>📦 Ship it right</b><span>Penny sleeves, Card Saver 1s and team bags.</span></div><span>Supplies →</span></a></div></div>'''),
        chapter(4, "risk", "Protect the downside", "Most losses in cards don't come from picking the wrong set. They come from the same handful of mistakes.",
                f'<div class="pb-risks">{risks}</div>'),
        chapter(5, "sell", "Know when to sell", "The best time to decide when you'll sell is before you buy. These signals help when the moment comes.",
                f'''<div class="pb-signals"><div class="pb-sig pb-sig-sell"><h3>Sell signals</h3><ul>{sell}</ul></div><div class="pb-sig pb-sig-hold"><h3>Hold signals</h3><ul>{hold}</ul></div></div>
  <h3 class="pb-sub">Where to sell</h3><div class="pb-where">{where}</div>'''),
        chapter(6, "routine", "Your weekly routine", "Fifteen minutes a week keeps you on top of everything you own and everything you want.",
                f'<div class="pb-steps">{steps}</div>'),
        chapter(7, "faq", "Questions", "Short answers to what collectors ask us most.", f'<div class="pb-faqs">{faq}</div>'),
    ]
    return f'''
<div class="wrap pb">
<section class="pb-hero">
  <div class="pb-hero-copy">
    <span class="in-kicker">PLAYBOOK · POKÉMON &amp; TCG</span>
    <h1>The card investing <span>playbook</span></h1>
    <p class="pb-lede">How to buy, hold, grade and sell Pokémon and other TCG cards without guessing. Plain rules, worked math, and the same nightly prices that run this site.</p>
    <div class="btns"><a class="btn primary" href="#lanes">Pick your lane ↓</a><a class="btn" href="trends.html">This week's movers</a></div>
  </div>
  <aside class="pb-rules" aria-labelledby="pb-rules-t"><span class="pb-rules-t" id="pb-rules-t">5 house rules</span><ol>{rules}</ol></aside>
</section>
<div class="pb-layout">
  <nav class="pb-toc" aria-label="Chapters"><span class="pb-toc-t">Chapters</span>{toc}</nav>
  <div class="pb-main">
{"".join(body)}
  <section class="pb-ch pb-end"><h2>Put the playbook to work</h2><p class="muted">Every tool here is free, no sign-up needed.</p><div class="hub">{tools}</div>
  <p class="pb-fine">For research and education only, not financial advice. Examples use round numbers; real prices and fees change daily. Not affiliated with or endorsed by The Pokémon Company, Nintendo or TCGplayer.</p></section>
  </div>
</div>
</div>
<script type="application/ld+json">{ld}</script>'''


INVESTING_BODY = investing_body()

PAGES = {
"index": ("Market Insights · Drive Your Style",
          "Nightly market prices, biggest movers and set values for Pokémon, One Piece, Lorcana, Riftbound, Gundam, Union Arena, Yu-Gi-Oh!, Dragon Ball and Palworld sealed product and cards.", f'''
<section class="hero hero-deal"><div class="wrap hd-grid">
  <div class="hd-copy">
    <h1>What are your cards worth today?</h1>
    <p class="lead" id="hd-lead">Market prices for Pokémon, One Piece, Lorcana, Riftbound, Gundam, Union Arena, Yu-Gi-Oh!, Dragon Ball and Palworld cards and sealed product, updated every night.</p>
    <div class="search" data-search>{SEARCH}<input type="search" placeholder="Search a card, set or booster box" aria-label="Search products and cards" autocomplete="off"><div class="results"></div></div>
    <p class="hd-note" id="hd-note"></p>
  </div>
  <a class="hd-fan" id="hd-fan" href="cards.html" aria-label="See today's biggest movers"></a>
</div></section>
<section class="block tools-block"><div class="wrap"><div class="tools-head"><h2>Free tools</h2><span class="muted">No sign-up needed</span></div><div class="tools" aria-label="Free tools">{"".join(tool_tile(u) for u in HOME_TOOLS)}</div></div></section>
<section class="block" style="padding-top:4px"><div class="wrap"><div class="gtiles" id="gtiles"></div></div></section>
@@GWBANNER@@<section class="block" id="intel-block" hidden style="padding-top:0;padding-bottom:12px"><div class="wrap"><div class="hi-grid">
  <a class="in-card hi-brief" href="intel.html"><span class="in-tag"><span class="in-dot"></span>DAILY MARKET BRIEF · <span id="hi-date"></span></span><b id="intel-head"></b><span class="hi-more">Read the brief →</span></a>
  <div id="hi-idx" class="hi-idx"></div></div></div></section>
<section class="block" id="report-block" hidden style="padding-top:0"><div class="wrap"><a class="report-banner" id="report-link" href="blog/"><div><b>📈 This week's market report</b><span id="report-title"></span></div><span>Read →</span></a></div></section>
<section class="block" id="stock-block"><div class="wrap">
  <div class="block-head"><div><h2>In stock at Drive Your Style</h2><p>Our price next to today's market price.</p></div><a class="more" href="https://driveyourstyle.net/collections/sealed-product">Shop all →</a></div>
  <div class="stockrow" id="stock"></div>
</div></section>
<section class="block" id="wanted-block" hidden><div class="wrap">
  <div class="block-head"><div><h2>Most wanted</h2><p>What collectors are hunting right now, from their Want lists.</p></div><a class="more" href="watchlist.html">My Want list →</a></div>
  <div class="stockrow" id="wanted"></div>
</div></section>
<section class="block"><div class="wrap">
  <div class="block-head"><div><h2>Newest sets</h2><p>Latest and upcoming releases.</p></div><a class="more" href="calendar.html">Release calendar →</a></div>
  <div class="srow" id="newsets"></div>
</div></section>
<section class="block"><div class="wrap">
  <div class="block-head"><div><h2>Trending cards</h2><p>Biggest card price moves over $5.</p></div><a class="more" href="cards.html">See all →</a></div>
  <div id="card-movers"></div>
</div></section>
<section class="block"><div class="wrap">
  <div class="block-head"><div><h2>Trending sealed</h2><p>Biggest sealed price moves over $5.</p></div><a class="more" href="trends.html">See all →</a></div>
  <div id="sealed-movers"></div>
</div></section>
<section class="block"><div class="wrap">
  <div class="cta"><div><h2>Track your collection</h2><p>Add your cards and sealed, see what your binder is worth tonight, and how close you are to finishing each set.</p></div>
  <a class="btn" href="collection.html">Start My Collection →</a></div>
</div></section>
<section class="block"><div class="wrap">
  <div class="cta"><div><h2>Sneaker drops &amp; resale</h2><p>Upcoming Jordan, Nike and adidas release dates, our worth-copping picks, and one-tap StockX, GOAT and eBay checks.</p></div>
  <a class="btn" href="sneakers.html">See sneaker drops →</a></div>
</div></section>
<section class="block"><div class="wrap">
  <div class="cta"><div><h2>Get restock &amp; drop alerts</h2><p>Be first to know when new sets, singles and sneakers land at Drive Your Style.</p></div>
  <a class="btn" href="https://driveyourstyle.net/#newsletter">Sign up at the store →</a></div>
</div></section>
<div class="wrap"><p class="stats-line" id="stats"></p></div>'''),
"sets": ("All sets · Drive Your Style Market Insights",
         "Every Pokémon, Pokémon Japan, One Piece, Lorcana, Riftbound, Gundam, Union Arena, Yu-Gi-Oh!, Dragon Ball and Palworld set by era, with sealed and card market prices.", '''
<div class="wrap"><section class="block">
  <div class="block-head"><div><h1 style="font-size:36px">Sets</h1><p id="count"></p></div></div>
  <div class="controls"><div id="game"></div><input class="field" id="q" type="search" placeholder="Search sets" aria-label="Search sets"></div>
  <div class="set-tabs" style="margin:4px 0 8px"><div id="eras" class="chips-row"></div></div>
  <div id="table"><div class="skeleton" style="height:300px"></div></div>
</section></div>'''),
"set": ("Set prices · Drive Your Style Market Insights", "Every card and sealed product in this set with today's market price.", '''
<div class="wrap"><div class="crumbs" id="crumbs"></div>
<section class="block" style="padding-top:12px">
  <div id="set-logo" class="set-logo" hidden></div>
  <h1 id="title" style="font-size:clamp(26px,4vw,40px)"></h1><p class="muted" id="sub" style="margin-top:4px"></p>
  <div id="set-grade" hidden></div>
  <div class="set-bar">
    <div class="search set-q">''' + SEARCH + '''<input id="q" type="search" placeholder="Search…" aria-label="Search this set" autocomplete="off"></div>
    <select class="select" id="sort" aria-label="Sort"><option value="price">Price ↓</option><option value="low">Price ↑</option><option value="num">Card number</option><option value="name">Name</option></select>
    <button class="btn icon" id="view" type="button" aria-label="Switch grid or list view"></button>
  </div>
  <div class="set-tabs"><div id="tab"></div><div id="rar" class="chips-row"></div></div>
  <div class="set-stats" id="set-stats"></div>
  <div class="set-tabs" style="margin-top:10px"><div id="ownf" class="chips-row"></div></div>
  <p class="muted" id="count-line" style="font-size:13px;margin:6px 0 10px"></p>
  <div id="grid"><div class="skeleton" style="height:400px"></div></div>
</section></div>'''),
"product": ("Price history · Drive Your Style Market Insights", "Market price history.", '''
<div class="wrap"><div class="crumbs" id="crumbs"></div><div class="prod" id="prod"><div class="skeleton" style="height:320px"></div></div></div>'''),
"trends": ("Sealed trends · Drive Your Style Market Insights",
           "Biggest sealed product price movers across Pokémon, One Piece, Lorcana, Riftbound, Gundam, Union Arena, Yu-Gi-Oh!, Dragon Ball and Palworld.", '''
<div class="wrap"><section class="block">
  <div class="block-head"><div><h1 style="font-size:36px">Sealed trends</h1><p>The 50 biggest sealed price moves for each game and time window. Defaults to products over $20.</p></div></div>
  <div id="sealed"></div>
</section></div>'''),
"cards": ("Card movers · Drive Your Style Market Insights", "Biggest single card price movers by game and set.", f'''
<div class="wrap"><section class="block">
  <div class="block-head"><div><h1 style="font-size:36px">Card movers</h1><p>Single cards over $5. Pick a set to rank that set's cards.</p></div></div>
  <div class="controls"><div id="game"></div><div id="win"></div>
    <select class="select" id="set" aria-label="Set"></select>
    <label class="toggle"><input type="checkbox" id="recent"> Released in last 12 months</label></div>
  <p class="muted" id="note" style="margin:-6px 0 12px;font-size:13px"></p>
  <div id="gmov" class="block" hidden style="padding:0 0 18px"><h2 style="font-size:20px;margin:0 0 4px">PSA 10 movers</h2><p class="muted" style="margin:0 0 10px;font-size:13px">Graded Pokémon cards: PSA 10 sold price this week vs the 90-day average.</p><div class="in-row" id="gmov-row"></div></div>
  {MOVERS}
</section></div>'''),
"search": ("Price check: search or scan any card · Drive Your Style Market Insights", "Search every Pokémon, Pokémon Japan, One Piece, Lorcana, Riftbound, Gundam, Union Arena, Yu-Gi-Oh!, Dragon Ball and Palworld card and sealed product by name, set, number or rarity, with today's market price.", '''
<div class="wrap"><section class="block">
  <div class="block-head"><div><h1 style="font-size:36px">Price check</h1><p>Every card and sealed product we track. Search by name, set, card number or rarity.</p></div></div>
  <div class="search big-q">''' + SEARCH + '''<input id="sq" type="search" placeholder="e.g. Charizard ex 199, Umbreon VMAX, 25/102" aria-label="Search cards" autocomplete="off" enterkeyhint="search"></div>
  <div class="controls" style="margin-top:12px"><div id="sgame"></div><div id="stype"></div>
    <select class="select" id="srar" aria-label="Rarity"><option value="">Any rarity</option></select>
    <select class="select" id="ssort" aria-label="Sort"><option value="price">Best match</option><option value="high">Price: high to low</option><option value="low">Price: low to high</option><option value="name">Name A–Z</option><option value="num">Card number</option></select>
    <label class="toggle"><input type="checkbox" id="spriced"> Only with a price</label></div>
  <p class="muted" id="scount" style="margin:4px 0 12px;font-size:13px">Loading every card…</p>
  <div id="sres" class="cgrid"></div>
</section></div>'''),
"compare": ("Compare prices · Drive Your Style Market Insights", "Compare two Pokémon or One Piece products side by side: market price, recent change and price history.", '''
<div class="wrap"><section class="block">
  <div class="block-head"><div><h1 style="font-size:36px">Compare</h1><p>Pick any two sealed products or cards to compare price, recent change and price history.</p></div></div>
  <div id="slots" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px;margin:8px 0 18px"></div>
  <div id="result"></div>
</section></div>'''),
"calendar": ("Release calendar · Drive Your Style Market Insights", "Upcoming and recent Pokémon, Pokémon Japan, One Piece, Lorcana, Riftbound, Gundam, Union Arena, Yu-Gi-Oh!, Dragon Ball and Palworld TCG set release dates with current sealed prices.", '''
<div class="wrap"><section class="block">
  <div class="block-head"><div><h1 style="font-size:36px">Release calendar</h1><p>Upcoming sets and everything released in the last 90 days. Dates come from TCGplayer and can shift.</p></div></div>
  <div class="controls"><div id="game"></div></div>
  <h2 style="font-size:24px;margin:18px 0 0">Upcoming</h2><div id="upcoming"><div class="skeleton" style="height:160px"></div></div>
  <div class="cta" style="margin:28px 0"><div><h2>Want it on release day?</h2><p>Pre-orders and new drops land at Drive Your Style first.</p></div><a class="btn" href="https://driveyourstyle.net/collections/pre-orders">Shop pre-orders →</a></div>
  <h2 style="font-size:24px;margin:18px 0 0">Recently released</h2><div id="released"></div>
</section></div>'''),
"sneakers": ("Sneaker release dates & resale · Drive Your Style", "Upcoming Jordan, Nike, adidas and more sneaker release dates with retail prices, our worth-copping picks, and quick resale checks on StockX, GOAT and eBay.", '''
<section class="hero hero-tight snk-hero"><div class="wrap">
  <span class="eyebrow"><b>●</b> Sneaker insights</span>
  <h1>Know the drop <span class="holo">before you cop.</span></h1>
  <p class="lead">Upcoming release dates, retail prices, our honest picks, and one-tap resale checks.</p>
</div></section>
<div class="wrap">
<section class="block" style="padding-top:4px">
  <div class="block-head"><div><h2>Worth copping?</h2><p>Our take on the biggest upcoming drops. Opinions, not guarantees.</p></div></div>
  <div class="snk-picks" id="picks"><div class="skeleton" style="height:180px"></div></div>
</section>
<section class="block" id="snk-stock-block" hidden>
  <div class="block-head"><div><h2>In stock at Drive Your Style</h2><p>Brand new pairs, ready to ship or pick up. Check resale before you buy.</p></div><a class="more" href="https://driveyourstyle.net/collections/new-shoes">Shop sneakers →</a></div>
  <div class="snk-stock" id="snk-stock"></div>
</section>
<section class="block" id="dropped-block" hidden>
  <div class="block-head"><div><h2>Just dropped</h2><p>Released in the last 2 weeks. Tap a resale link to see how each pair is trading.</p></div></div>
  <div class="snk-stock" id="dropped"></div>
</section>
<section class="block">
  <div class="block-head"><div><h2>Release calendar</h2><p id="snk-note">Dates and prices can change. Retail is US men's sizing.</p></div></div>
  <div class="controls"><div id="brand"></div><label class="toggle"><input type="checkbox" id="hot"> Hyped drops only</label></div>
  <div id="cal"><div class="skeleton" style="height:300px"></div></div>
</section>
<section class="block"><div class="cta"><div><h2>Selling a pair?</h2><p>We buy and consign sneakers. Get an offer in a day.</p></div><a class="btn" href="https://driveyourstyle.net/pages/sell-with-us">Sell with us →</a></div></section>
<p class="muted" id="snk-src" style="font-size:12px;margin:0 0 24px"></p>
</div>'''),
"watchlist": ("Want list · Drive Your Style Market Insights", "Cards and sealed products you want, with today's market price, your max price and in-stock alerts.", '''
<div class="wrap"><section class="block">
  <div class="block-head"><div><h1 style="font-size:36px">Want list</h1><p>Cards and sealed you're hunting. Set the most you'd pay and we'll flag it when the market drops under your max or Drive Your Style has it in stock.</p>
    <p class="muted" id="acct-note" style="font-size:13px"></p></div></div>
  <div id="list"><div class="skeleton" style="height:200px"></div></div>
</section></div>'''),
"demand": ("Demand report · Drive Your Style", "What collectors want.", '''
<div class="wrap"><section class="block">
  <div class="block-head"><div><h1 style="font-size:36px">Demand report</h1><p>What collectors have on their Want lists, most wanted first. Anonymous counts; updates every 30 minutes.</p>
    <p class="muted" id="sum" style="font-size:13px"></p></div></div>
  <div class="controls"><div id="f"></div></div>
  <div id="list"><div class="skeleton" style="height:240px"></div></div>
</section></div>'''),
"importer": ("Shopify importer · Drive Your Style Market Insights", "Add TCG products straight to the Drive Your Style Shopify store.", '''
<div class="wrap"><section class="block">
  <div class="block-head"><div><h1 style="font-size:36px">Shopify importer</h1><p>Pick sealed products or singles, set quantities and tap <b>Add to store</b>. New products go live at today's TCGplayer market price; items already in your store get restocked. Prices then follow the market every night, with a safety net.</p></div><div id="conn-state"></div></div>
  <details class="panel" id="conn" style="padding:14px 16px;margin-bottom:16px"><summary style="cursor:pointer;font-weight:600">Store connection &amp; price safety net</summary>
    <div id="conn-form" style="margin-top:12px"><p class="muted" style="font-size:14px;margin:0 0 8px">Paste your GitHub key (fine-grained, <b>Actions: Read and write</b> on dys-market). It stays on this device only.</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><input class="field" id="conn-token" type="password" placeholder="github_pat_…" aria-label="GitHub key" style="flex:1;min-width:220px"><button class="btn primary" id="conn-save" type="button">Connect</button></div>
      <p class="muted" id="conn-msg" style="font-size:13px;color:var(--down)"></p></div>
    <button class="btn" id="conn-off" type="button" style="margin-top:12px" hidden>Disconnect this device</button>
    <ul class="muted" style="font-size:14px;margin:14px 0 0;padding-left:18px">
      <li>Prices update nightly to the market price.</li>
      <li>If the market drops more than <b>15%</b> in one night, the price is held and listed below for you to review.</li>
      <li>Prices never go below <b>Your cost</b> (Shopify's "Cost per item").</li>
      <li>Jumps over 50% in one night are held too (usually bad data).</li></ul>
  </details>
  <div class="panel" id="held" hidden style="padding:14px 16px;margin-bottom:16px;border-color:var(--down)"><b>Held by the safety net</b><ul id="held-list" style="margin:8px 0 0;padding-left:18px;font-size:14px"></ul><p class="muted" style="font-size:13px;margin:8px 0 0">Change these by hand in Shopify if the drop is real.</p></div>
  <div class="controls"><div id="game"></div><select class="select" id="set" aria-label="Set"></select><div id="kind"></div></div>
  <div class="controls"><label class="muted" style="font-size:14px">Min market $ <input class="field" id="min" type="number" min="0" value="0" style="width:80px"></label>
    <input class="field" id="q" type="search" placeholder="Filter by name" aria-label="Filter by name"></div>
  <div id="rows"><div class="skeleton" style="height:240px"></div></div>
  <div class="panel" id="run" hidden style="margin-top:16px;padding:14px 16px"></div>
  <div class="panel" style="position:sticky;bottom:12px;margin-top:16px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between;padding:14px 16px">
    <b id="count"></b>
    <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center"><label class="muted" style="font-size:14px">New items <select class="select" id="status"><option value="Active">Go live</option><option value="Draft">Save as draft</option></select></label>
      <button class="btn" id="clear" type="button">Clear</button><button class="btn" id="dl" type="button">CSV</button><button class="btn primary" id="add" type="button">Add to store</button></div>
  </div>
</section></div>'''),
"collection": ("My Collection · Drive Your Style Market Insights", "Track your Pokémon, One Piece, Lorcana, Riftbound, Gundam, Union Arena, Yu-Gi-Oh!, Dragon Ball and Palworld card collection with live market values.", '''
<div class="wrap"><section class="block">
  <div class="block-head"><div><span class="eyebrow"><b>●</b> Members</span><h1 id="title" style="font-size:36px;margin-top:8px">My Collection</h1>
    <p id="shared-note" class="muted" hidden>A collection shared from Drive Your Style. <a href="collection.html" style="color:var(--accent)">Start your own →</a></p></div></div>
  <div id="acct" class="panel acct-bar" hidden></div>
  <div id="prof" class="panel prof-panel" hidden></div>
  <div id="offers" class="panel prof-panel" hidden></div>
  <div id="giveaway" class="panel prof-panel gw-panel" hidden></div>
  <div id="mine">
    <div class="search" id="add-box" style="max-width:640px">''' + SEARCH + '''<input id="add-q" type="search" placeholder="Search a card or product to add" aria-label="Search a card or product to add" autocomplete="off"><div class="results" id="add-results"></div></div>
    <p class="muted" id="added" style="min-height:20px;font-size:14px;margin:8px 0 0" role="status"></p>
  </div>
  <div class="stats" id="stats" style="margin:18px 0"></div>
  <div class="panel sell-cta" id="sell-cta" hidden><div><b>Thinking of selling?</b><span>Get a cash or store-credit offer from Drive Your Style for your whole collection.</span></div><button class="btn primary" id="sell-col" type="button">💵 Get an offer</button></div>
  <div class="chart-card" id="cchart-wrap" hidden style="margin-bottom:18px"><div class="chart-head"><b>Collection value</b><div id="crange"></div></div><div class="chart" id="cchart"></div>
    <p class="muted" style="font-size:12px;margin:6px 0 4px">Your current quantities at each day's market price.</p></div>
  <div id="csets" style="margin-bottom:18px"></div>
  <div class="ctools"><input class="field" id="cq" type="search" placeholder="Search your collection" aria-label="Search your collection">
    <select class="select" id="cbinder" aria-label="Binder" hidden></select>
    <select class="select" id="csort" aria-label="Sort"><option value="value">Value</option><option value="recent">Recently added</option><option value="name">Name</option><option value="set">Set</option></select>
    <label class="toggle"><input type="checkbox" id="cgroup"> Group by set</label><div id="cview"></div></div>
  <div id="list"><div class="skeleton" style="height:200px"></div></div>
  <div id="tools" class="panel" style="margin-top:18px;padding:14px 16px;display:flex;flex-wrap:wrap;gap:10px;align-items:center">
    <label class="muted" style="font-size:14px;flex:1;min-width:200px">Collection name <input class="field" id="name" maxlength="60" placeholder="e.g. Keo's binder" style="width:100%;margin-top:4px"></label>
    <button class="btn primary" id="share" type="button">Share</button>
    <button class="btn" id="backup" type="button">Back up</button>
    <label class="btn" style="cursor:pointer">Restore<input id="restore" type="file" accept="application/json,.json" hidden></label>
  </div>
  <p class="muted" style="font-size:13px;margin-top:10px">Your collection saves on this device. Use <b>Back up</b> to keep a copy or move it to another phone. Tap the camera on any item to use your own photo; photos stay on this phone. Raw cards use the nightly TCGplayer market price (Near Mint). For a slab, pick its grade under the card and enter what it's worth; the eBay sold link shows recent sales for that grade. Values aren't an offer to buy.</p>
</section></div>'''),
"collectors": ("Collectors · Drive Your Style Market Insights", "Browse Pokémon, One Piece, Lorcana, Riftbound, Gundam, Union Arena, Yu-Gi-Oh!, Dragon Ball and Palworld collections from Drive Your Style collectors. Like your favorites and follow collectors.", '''
<div class="wrap"><section class="block">
  <div class="block-head"><div><span class="eyebrow"><b>●</b> Community</span><h1 style="font-size:36px;margin-top:8px">Collectors</h1>
    <p>Binders collectors chose to share. Tap one to see every card, like it, or follow the collector.</p></div>
    <a class="btn primary" href="collection.html" id="join">Share your binder →</a></div>
  <div class="cboard" id="cboard" hidden></div>
  <div class="controls"><div id="ctab"></div><input class="field" id="cfind" type="search" placeholder="Find a collector" aria-label="Find a collector"></div>
  <p class="muted" id="cnote" style="font-size:13px;margin:4px 0 12px"></p>
  <div id="clist" class="col-grid"><div class="skeleton" style="height:220px"></div></div>
  <p class="muted" style="font-size:12px;margin-top:18px">Values use nightly market prices for raw cards and each collector's own value for slabs. Likes and follows need a free account and update every 30 minutes.</p>
</section></div>'''),
"sell": ("Sell your cards · Drive Your Style", "Get a cash or store-credit offer for your Pokémon, One Piece, Lorcana and other TCG cards, slabs and sealed product from Drive Your Style in Las Vegas.", '''
<section class="hero hero-tight"><div class="wrap">
  <span class="eyebrow"><b>●</b> We buy cards · Las Vegas</span>
  <h1>Sell your cards <span class="holo">for cash or credit.</span></h1>
  <p class="lead">Build your list from any card page or your collection, check the estimate, and send it. We reply within 24–48 hours with a firm offer.</p>
</div></section>
<div class="wrap"><section class="block" style="padding-top:8px">
  <div class="stats" id="sell-est" style="margin:0 0 14px"></div>
  <p class="muted" id="sell-bulk" style="font-size:13px;margin:0 0 10px"></p>
  <div id="sell-list"><div class="skeleton" style="height:160px"></div></div>
  <form id="sell-form" class="panel sell-form" method="post" hidden accept-charset="UTF-8">
    <input type="hidden" name="form_type" value="contact"><input type="hidden" name="utf8" value="✓">
    <input type="hidden" name="contact[tags]" value="sell-request">
    <textarea id="sell-body" name="contact[body]" hidden></textarea>
    <h2 style="font-size:22px;margin:0 0 4px">Send your list</h2>
    <p class="muted" style="margin:0 0 14px;font-size:14px">No obligation. You'll get our offer by email.</p>
    <div class="sell-grid">
      <label>Name<input class="field" name="contact[name]" required autocomplete="name"></label>
      <label>Email<input class="field" type="email" name="contact[email]" required autocomplete="email"></label>
      <label>Phone (optional)<input class="field" type="tel" name="contact[phone]" autocomplete="tel"></label>
      <label>I'd like<select class="select" name="payout"><option>Cash (PayPal / Zelle / cash)</option><option>Store credit (higher offer)</option><option>Either, show me both</option></select></label>
    </div>
    <label style="display:block;margin-top:10px">Notes<textarea class="field" name="notes" rows="3" placeholder="Anything we should know: local pickup, photos available, condition details" style="width:100%"></textarea></label>
    <div class="btns" style="margin-top:14px"><button class="btn primary" type="submit">Send for an offer</button><button class="btn" type="button" id="sell-clear">Clear list</button></div>
    <p class="muted" style="font-size:12.5px;margin:12px 0 0"><span id="sell-rates"></span> Final offers depend on condition once we see the cards. Have photos? Email them to <a id="sell-mail" href="#"></a>. Local sellers can meet in Las Vegas.</p>
  </form>
  <p class="muted" style="font-size:13px;margin-top:18px">Prefer to consign high-end items instead? <a href="https://driveyourstyle.net/pages/sell-with-us">Consign with us</a> and keep up to 85% of the sale.</p>
</section></div>'''),
"giveaway": ("Monthly giveaway: win an Elite Trainer Box · Drive Your Style", "Win a Pokémon Elite Trainer Box every month. Free to enter: sign in, build your binder on Drive Your Style Market Insights, and get bonus entries for every friend you bring.", '''
<section class="hero hero-tight"><div class="wrap">
  <span class="eyebrow"><b>●</b> Free monthly giveaway</span>
  <h1>Win an <span class="holo">Elite Trainer Box</span> every month.</h1>
  <p class="lead">Track your cards on our free price site and you're in. One winner every month, drawn at random.</p>
  <div class="stats gw-stats" id="gw-stats"><div class="stat"><div class="skeleton"></div></div><div class="stat"><div class="skeleton"></div></div><div class="stat"><div class="skeleton"></div></div></div>
  <div class="btns" style="margin-top:18px"><a class="btn primary" href="collection.html#giveaway" id="gw-cta">Enter free →</a><a class="btn" href="#rules">Rules</a></div>
</div></section>
<div class="wrap"><section class="block" style="padding-top:8px">
  <h2 style="font-size:24px">How to enter</h2>
  <ol class="gw-steps">
    <li><b>Sign in on My Collection.</b><span>Free account with your email. No password, no purchase.</span></li>
    <li><b>Add at least 5 cards or products to your binder.</b><span>Search or scan them with your camera. You'll see what your collection is worth.</span></li>
    <li><b>Tick "Enter me in the monthly giveaway".</b><span>That's 1 entry. You stay entered every month.</span></li>
  </ol>
  <h2 style="font-size:24px;margin-top:26px">Bonus entries</h2>
  <ul class="gw-bonus">
    <li><b>+1</b> Make your binder public on the Collectors page.</li>
    <li><b>+1 per friend</b> who signs up with your invite link and adds 5 items (up to 10).</li>
  </ul>
  <div id="gw-mine" class="panel gw-mine" hidden></div>
  <div id="gw-winners"></div>
  <h2 style="font-size:24px;margin-top:30px" id="rules">Official rules</h2>
  <div class="prose gw-rules">
    <p><b>No purchase necessary to enter or win. A purchase does not improve your chances.</b></p>
    <p><b>Sponsor:</b> Drive Style Wizards LLC (Drive Your Style), Las Vegas, Nevada.</p>
    <p><b>Eligibility:</b> Open to legal residents of the 50 United States and D.C. who are 18 or older. Employees of the Sponsor and their households are not eligible. Void where prohibited.</p>
    <p><b>Entry period:</b> Each calendar month (Pacific time) is a separate drawing. Entrants who meet the requirements on the last day of the month are entered in that month's drawing and stay entered in later months until they opt out.</p>
    <p><b>How to enter:</b> Sign in at market.driveyourstyle.net, keep at least 5 items in your binder and tick "Enter me in the monthly giveaway". Bonus entries: 1 for a public binder, and 1 for each person who creates an account through your invite link and keeps at least 5 items in their binder, up to 10. One account per person. Accounts created to collect entries are disqualified.</p>
    <p><b>Prize:</b> One winner per month receives 1 Pokémon TCG Elite Trainer Box chosen by the Sponsor (approximate retail value $60). No cash alternative. Prize ships free within the U.S. or can be picked up in Las Vegas.</p>
    <p><b>Drawing:</b> The winner is selected at random on the 1st of the following month, with chances in proportion to entries. Odds depend on the number of entries received.</p>
    <p><b>Notification:</b> The winner is contacted at the email on their account and must reply within 7 days, or an alternate winner is drawn. The winner's collector name may be posted on this page and on Drive Your Style social media.</p>
    <p><b>General:</b> The Sponsor may verify eligibility and disqualify entries that break these rules or use fake accounts. This giveaway is not sponsored, endorsed or administered by The Pokémon Company, Nintendo, Instagram, TikTok, Facebook or YouTube. By entering you agree to these rules.</p>
  </div>
</section></div>'''),
"intel": ("Market brief: daily movers, indices and signals · Drive Your Style", "Daily trading card market brief: market mood, Chase 100 and Modern Sealed 100 indices, cards with steady rising or cooling prices, today's biggest movers and the best cards to grade for Pokémon, One Piece and more.", '''
<div class="wrap in-wrap"><section class="block">
  <span class="in-kicker" id="in-kick">TODAY</span><h1 class="in-h">Market brief</h1>
  <div class="in-hero">
    <div class="in-card in-brief" id="in-brief"><div class="skeleton" style="height:120px"></div></div>
    <div class="in-card in-mood" id="in-mood"><div class="skeleton" style="height:120px"></div></div>
  </div>
  <div class="in-stats" id="in-stats"></div>
  <nav class="in-nav" id="in-nav" aria-label="Sections">
    <a href="#s-idx">Indices</a><a href="#s-pulse">By game</a><a href="#s-sig">Signals</a><a href="#s-mov">Movers</a><a href="#s-grade" id="in-nav-grade" hidden>Grading picks</a><a href="#s-psa" id="in-nav-psa" hidden>PSA 10</a>
  </nav>
  <h2 class="in-h2" id="s-idx">Market indices</h2>
  <div class="in-grid in-grid4" id="in-idx"><div class="skeleton" style="height:160px"></div><div class="skeleton" style="height:160px"></div></div>
  <div id="s-pulse-wrap" hidden><h2 class="in-h2" id="s-pulse">This week by game</h2><p class="muted in-note">Share of cards worth $5+ that rose or fell more than 1% over the last 7 days.</p><div class="in-pulse" id="in-pulse"></div></div>
  <span class="in-kicker" style="margin-top:28px">DRIVE YOUR STYLE</span><h2 class="in-h2" style="margin-top:2px" id="s-sig">Signals</h2>
  <p class="muted in-note" id="in-sig-note"></p>
  <div class="in-filter" id="in-sig-games"></div>
  <div class="in-cols"><div><h3 class="in-h3 up">Rising</h3><div class="in-list" id="in-up"></div></div><div><h3 class="in-h3 down">Cooling</h3><div class="in-list" id="in-down"></div></div></div>
  <div class="in-more"><button class="btn" type="button" id="in-sig-more" hidden>Show more signals</button></div>
  <div class="in-head2"><h2 class="in-h2" id="s-mov">Top movers · 24h</h2><div id="in-mov-tabs"></div></div>
  <div class="in-row" id="in-movers"></div>
  <div id="in-graded" hidden>
    <span class="in-kicker" style="margin-top:28px">GRADED · REAL SOLD PRICES</span><h2 class="in-h2" style="margin-top:2px" id="s-grade">Grading picks</h2>
    <p class="muted in-note"><span id="in-grade-basis">Modern Pokémon cards where a PSA 10 pays off best and sells at least weekly, after grading fees, shipping and eBay selling fees, at 30% odds of a 10 and 50% of a 9.</span> <a href="grading.html" style="color:var(--accent)">Set your own numbers →</a></p>
    <div class="in-row" id="in-picks"></div>
    <div id="in-gmoves-wrap" hidden><div class="in-head2"><h2 class="in-h2" id="s-psa">PSA 10 movers</h2><div id="in-gm-tabs"></div></div><p class="muted in-note">PSA 10 sold price this week vs its 90-day average, for cards that sell at least a couple of times a week.</p><div class="in-row" id="in-gmoves"></div></div>
  </div>
  <div id="in-deals-wrap" hidden><h2 class="in-h2">Listed under market</h2><div class="in-row" id="in-deals"></div></div>
  <div class="in-card in-cta"><div><b>Track your own cards</b><span class="muted">Add your collection and see its value move every day. Free.</span></div><a class="btn primary" href="collection.html">Start my collection →</a></div>
  <p class="muted in-foot">How this works: every index is a fixed basket of today's most valuable items, valued each day at its TCGplayer market price. A signal means a card's price moved the same way on most days this week and is at its weekly high (rising) or low (cooling); strength grows with the size and consistency of the move. Market mood is the share of cards worth $5+ that rose versus fell this week. Built from <span id="in-days">—</span> days of recorded prices and updated nightly. For research only, not financial advice.</p>
</section></div>'''),
"grading": ("Grading Insights: is your card worth grading? · Drive Your Style", "Free grading calculator for Pokémon, One Piece, Lorcana, Yu-Gi-Oh! and more. See the break-even PSA, CGC, BGS or TAG 10 price for every card after grading and selling fees, and check it against real sold prices.", '''
<div class="wrap"><section class="block">
  <span class="in-kicker">FREE · NO SIGN-IN</span><h1 class="in-h">Grading Insights</h1>
  <p class="muted" style="max-width:760px;margin:-6px 0 16px">Find the cards worth sending to PSA, CGC, BGS or TAG. Pick a grading tier, where you'll sell the slab and your odds of a 10, and every card shows the graded 10 price it needs to sell for before grading pays off, after grading and selling fees.</p>
  <div class="in-card gr-controls" id="gr-controls"></div>
  <div class="gr-bar"><div id="gr-sort"></div></div>
  <p class="muted gr-status" id="gr-status"></p>
  <div class="gr-list" id="gr-list"><div class="skeleton" style="height:240px"></div></div>
  <a class="report-banner" href="supplies.html" style="margin-top:14px"><div><b>📦 Ready to submit?</b><span>Penny sleeves, Card Saver 1s and team bags: what graders want in the box.</span></div><span>Supplies →</span></a>
  <details class="in-card gr-how"><summary><b>How the estimate works</b></summary>
    <p>Only cards with a steady price and live listings near the market price are shown, so thin or spiking prices don't mislead the math. Promos, event and prize cards are left out. All-in cost = the lowest raw listing today + the grading fee + shipping and insurance both ways.</p>
    <p>Grading fees come from each company's current price list, open tiers only. PSA and CGC charge by the card's graded value: when a grade is worth more than your tier covers, it's upcharged to the tier that covers it, and the cost includes that risk at your odds. Sale prices are after the selling fees of the marketplace you pick.</p>
    <p>Expected profit = (chance of 10 × 10 price) + (chance of 9 × 9 price) + (rest × about 0.7× raw), each after selling fees, − all-in cost. Break-even 10 is the 10 price where that profit is zero at your odds; the lower it is compared to raw (shown as ×), the easier grading pays off.</p>
    <p><b>PSA 10 on eBay</b> is the cheapest PSA 10 of that exact card listed for sale on eBay right now (Buy It Now, US sellers, shipping included), checked in the last week. Listings that don't match the card's number or price range are left out. It's an asking price, not a sale, so <b>Profit at that price</b> is what you'd make if your 10 sold for about that much, at your odds, after every fee. Tap <b>PSA 10 sold</b> to see what 10s actually sold for before you buy. Odds are your estimate, not a prediction; check centering and surfaces first. Fees change often, so confirm with the grader before you submit. Taxes aren't included. Estimates only, not financial advice.</p>
    <p class="muted">eBay links on this page are affiliate links: if you buy through them we may earn a small commission at no extra cost to you.</p></details>
</section></div>'''),
"buyer": ("Buyer dashboard · Drive Your Style", "Owner's buyer dashboard.", '''
<div class="wrap"><section class="block">
  <div class="block-head"><div><span class="eyebrow"><b>●</b> Owner only · unlisted</span><h1 style="font-size:34px;margin-top:8px">Buyer dashboard</h1>
    <p class="muted" id="bupd"></p></div></div>
  <div class="b-tabs" id="btabs"></div>
  <p class="muted" id="bnote" style="font-size:13.5px;margin:10px 0 14px"></p>
  <div id="bpanel"><div class="skeleton" style="height:240px"></div></div>
</section></div>'''),
"centering": ("Card centering check for PSA, CGC and BGS · Drive Your Style",
              "Free card centering checker. Take a photo of your Pokémon, One Piece or sports card to measure left/right and top/bottom centering and see the best PSA, CGC and BGS grade it allows before you submit.", '''
<div class="wrap"><section class="block">
  <div class="block-head"><div><h1 style="font-size:36px">Centering check</h1>
    <p>Measure a card's centering before you pay to grade it. Your photo stays on your device. Nothing is uploaded.</p></div></div>
  <div id="cz-root"><p class="panel empty-note">Loading the centering tool…</p></div>
  <div class="cz-info">
    <article class="prose"><h2>How to get an accurate read</h2>
      <ul><li>Lay the card flat on a dark, plain surface. Light cards on a white table are hard to find.</li>
      <li>Hold your phone straight above the card, not at an angle. Angled shots squeeze one side.</li>
      <li>Use Straighten if the card is tilted in the photo, then drag each line onto its edge. The zoom shows you exactly where it sits.</li>
      <li>Do the back too. PSA allows more on the back, but it still counts.</li>
      <li>A phone photo is usually within 1 to 2 points of a flatbed scan. If you're right on a limit, scan it to be sure.</li></ul></article>
    <div class="panel cz-table"><h2>Centering limits</h2>
      <table><thead><tr><th>Grade</th><th class="num">Front</th><th class="num">Back</th></tr></thead><tbody>
        <tr><td>PSA 10</td><td class="num">55/45</td><td class="num">75/25</td></tr>
        <tr><td>PSA 9</td><td class="num">60/40</td><td class="num">90/10</td></tr>
        <tr><td>PSA 8</td><td class="num">65/35</td><td class="num">90/10</td></tr>
        <tr><td>PSA 7</td><td class="num">70/30</td><td class="num">90/10</td></tr>
        <tr><td>PSA 6</td><td class="num">80/20</td><td class="num">90/10</td></tr>
        <tr><td>CGC Gem Mint 10</td><td class="num">55/45</td><td class="num">75/25</td></tr>
        <tr><td>CGC 9</td><td class="num">60/40</td><td class="num">90/10</td></tr>
        <tr><td>BGS Pristine 10</td><td class="num">50/50</td><td class="num">55/45</td></tr>
      </tbody></table>
      <p class="muted cz-note">From each company's published grading standards. Graders can allow a little leeway for eye appeal, and centering is only one part of the grade: corners, edges and surface count too.</p></div>
  </div>
</section></div>'''),
"legal": ("Privacy & Terms · Drive Your Style Market Insights", "How Drive Your Style Market Insights handles your information, and the terms for using the site.", '''
<div class="wrap"><article class="prose">
  <h1>Privacy &amp; Terms</h1>
  <p class="muted">Effective October 28, 2026. Drive Your Style Market Insights (market.driveyourstyle.net) is run by Drive Style Wizards LLC, doing business as Drive Your Style, in Las Vegas, Nevada. Questions: <b>customerservice@driveyourstyle.net</b>.</p>

  <h2 id="privacy">Privacy</h2>
  <h3>What we collect</h3>
  <ul>
    <li><b>Visits.</b> We count page views with GoatCounter, which doesn't use cookies or follow you to other sites. We see totals like which pages are popular and where visitors come from, not who you are.</li>
    <li><b>Things saved on your device.</b> Your collection, want list, calculator numbers, settings and theme are saved in your own browser. We don't receive them unless you sign in and save them, or share a link.</li>
    <li><b>Store account (optional).</b> If you sign in with your Drive Your Style store account (run by Shopify), we receive your first name, email address and account ID, and we save your binder (cards, quantities, grades and what you paid) to your account.</li>
    <li><b>Public binders.</b> If you make your binder public, anyone can see your display name, your cards and their quantities. Your email and what you paid are never shown. Likes and follows are public too. You can make your binder private at any time.</li>
    <li><b>Shared links.</b> A collection share link carries your list inside the link itself. Anyone you send it to can see that list.</li>
    <li><b>Offers.</b> Drive Your Style may send offers on cards in public binders. Offers and replies are kept in your private inbox.</li>
    <li><b>Card scanner.</b> The scanner uses your camera inside your browser. Images stay on your device and are never uploaded.</li>
    <li><b>Messages.</b> When you email us or use our store's contact form (for example to sell us cards), we use what you send to reply and make an offer.</li>
  </ul>
  <h3>How we use it</h3>
  <p>To run the site's features, answer you, make offers you asked for, and improve the site. We don't sell information collected on this site or use it for advertising profiles. Your store account and any purchases are also covered by our store's privacy policy, linked below.</p>
  <h3>Who we share it with</h3>
  <p>Only the services that run the site: GitHub (hosting), Shopify (store accounts and our store) and GoatCounter (visit counts), each under their own privacy terms, or when the law requires it. Our store's own privacy policy is at <a href="https://driveyourstyle.net/policies/privacy-policy">driveyourstyle.net/policies/privacy-policy</a>.</p>
  <h3>Links and affiliate links</h3>
  <p>The site links to other sites such as TCGplayer, eBay, StockX and GOAT. Some eBay and Amazon links are affiliate links (eBay Partner Network, Amazon Associates): if you buy through them we may earn a small commission at no extra cost to you, and those sites may set their own cookies. As an Amazon Associate we earn from qualifying purchases. Their privacy policies apply once you leave our site.</p>
  <h3>Your choices</h3>
  <ul>
    <li>Clear what's saved on your device by clearing this site's data in your browser.</li>
    <li>Make your binder private, or email us to delete your binder, likes, follows and offers.</li>
    <li>Manage or delete your store account through our store or by emailing us.</li>
  </ul>
  <h3>Children</h3>
  <p>The site isn't directed to children under 13, and we don't knowingly collect their personal information. If you think a child has given us information, email us and we'll delete it.</p>
  <h3>Security and keeping data</h3>
  <p>We keep account data only as long as your account or binder exists, and we protect what we store with access controls and encryption. No site is perfectly secure, so please don't put sensitive information in your binder name or alias.</p>

  <h2 id="terms">Terms of use</h2>
  <h3>What the site is</h3>
  <p>A free market research tool. Prices are market reference prices recorded nightly from public TCGplayer data, plus eBay listings shown with the date we checked them. They can be wrong, late or missing, and they aren't Drive Your Style's prices unless an item is marked in stock. Calculators and picks are estimates. Nothing here is financial, investment or legal advice; please do your own research before you buy, sell or grade.</p>
  <h3>Trademarks and images</h3>
  <p>Not affiliated with or endorsed by The Pokémon Company, Nintendo, Creatures, GAME FREAK, Bandai, Disney, Ravensburger, Riot Games, Sunrise, Konami, Pocketpair, TCGplayer, eBay, PSA, CGC, Beckett or TAG. All trademarks, product names and card images belong to their owners and appear only to identify products. eBay and the eBay logo are trademarks of eBay Inc.</p>
  <h3>Using the site</h3>
  <ul>
    <li>Use the site for your own research and collecting.</li>
    <li>Don't scrape, bulk download, resell or republish the site's data.</li>
    <li>Don't misuse accounts, offers or public binders: no spam, fraud, impersonation, or offensive or illegal content.</li>
    <li>We may remove content or limit access that breaks these terms.</li>
  </ul>
  <h3>Your content</h3>
  <p>You own your binder and display name. By making them public, you let us show them on the site until you make them private or delete them.</p>
  <h3>Offers and purchases</h3>
  <p>Offers from Drive Your Style are invitations to talk, not binding until we both agree. Purchases and sales go through our store or a written agreement, under our store's terms. Giveaways, when running, follow the official rules posted with each one.</p>
  <h3>No warranty, limits</h3>
  <p>The site is provided as is, without warranties. To the extent the law allows, Drive Style Wizards LLC isn't liable for losses from using the site or relying on its prices, estimates or picks.</p>
  <h3>Changes and law</h3>
  <p>We may update this page; the effective date above shows the latest version. These terms are governed by the laws of Nevada, USA. Questions: <b>customerservice@driveyourstyle.net</b>.</p>
</article></div>'''),
"tools": ("Tools · Drive Your Style Market Insights",
          "Free card tools: price check and scan, movers, sealed trends, Grading Insights, centering check, collection tracker, want list, release calendar and sneaker drops.", TOOLS_BODY),
"supplies": ("Card grading & storage supplies · Drive Your Style",
             "What you need to send cards to PSA, CGC or BGS and to store, display and ship them: penny sleeves, Card Saver 1, team bags, top loaders, binders and more.", SUPPLIES_BODY),
"investing": (PB_TITLE, PB_DESC, INVESTING_BODY),
"about": ("Where our data comes from · Drive Your Style Market Insights", "Where Drive Your Style market prices come from.", '''
<div class="wrap"><article class="prose">
  <h1>Where our data comes from</h1>
  <p>Every night we save the TCGplayer <b>market price</b> for each Pokémon, Pokémon Japan, One Piece, Lorcana, Riftbound, Gundam, Union Arena, Yu-Gi-Oh!, Dragon Ball and Palworld product, using the public daily data published by <a href="https://tcgcsv.com" style="color:var(--accent)">TCGCSV</a>. Market price reflects recent completed sales on TCGplayer.</p>
  <h2>How movers are calculated</h2>
  <p>A mover's change compares today's market price with the price saved closest to 7, 30, 90 or 365 days ago. Items under $5 today, or under $1 at the start of the window, are left out so tiny prices don't produce huge percentages.</p>
  <h2>Sets</h2>
  <p>A set's 7-day change is the change in the combined market price of its sealed products. "Booster box" shows the main booster box when the set has one.</p>
  <h2>Good to know</h2>
  <ul><li>Prices can lag by about a day and swing on thin sales, especially right after release.</li>
  <li>These are market reference prices, not Drive Your Style's prices. Items marked "In stock" link to our store.</li>
  <li>For research only. Not financial advice.</li>
  <li>Not affiliated with or endorsed by The Pokémon Company, Nintendo, Bandai, Disney, Ravensburger, Riot Games, Sunrise, Konami, Pocketpair or TCGplayer.</li>
  <li>How we handle your information and the terms for using the site: <a href="legal.html">Privacy &amp; Terms</a>.</li></ul>
</article></div>'''),
}

LINKS_ICONS = {'TikTok': '<path fill="currentColor" d="M16.6 5.8A4.3 4.3 0 0 1 15.5 3h-3.1v12.4a2.6 2.6 0 1 1-1.8-2.5V9.7a5.8 5.8 0 1 0 4.9 5.7V9.1a7.4 7.4 0 0 0 4.3 1.4V7.4a4.3 4.3 0 0 1-3.2-1.6z"/>', 'YouTube': '<path fill="currentColor" d="M21.6 7.2a2.5 2.5 0 0 0-1.8-1.8C18.2 5 12 5 12 5s-6.2 0-7.8.4A2.5 2.5 0 0 0 2.4 7.2 26 26 0 0 0 2 12a26 26 0 0 0 .4 4.8 2.5 2.5 0 0 0 1.8 1.8c1.6.4 7.8.4 7.8.4s6.2 0 7.8-.4a2.5 2.5 0 0 0 1.8-1.8A26 26 0 0 0 22 12a26 26 0 0 0-.4-4.8zM10 15V9l5.2 3z"/>', 'Instagram': '<rect x="3" y="3" width="18" height="18" rx="5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="17.5" cy="6.5" r="1.2" fill="currentColor"/>', 'Facebook': '<path fill="currentColor" d="M13.5 21v-7.5h2.5l.4-3h-2.9V8.6c0-.9.3-1.5 1.5-1.5h1.5V4.4a20 20 0 0 0-2.2-.1c-2.2 0-3.8 1.4-3.8 3.9v2.3H8v3h2.5V21z"/>'}


def links_page():
    """Link-in-bio page (no site chrome): market.driveyourstyle.net/links.html"""
    rows = [
        # (title, line, link, main button, picture key in assets/links/: made nightly by tools/links_thumbs.py)
        ("Shop Drive Your Style", "Sealed Pokémon & One Piece, singles, sneakers, Pop Mart", "https://driveyourstyle.net/?utm_source=bio&utm_medium=social", True, "shop"),
        ("Check what your cards are worth", "Free prices on 150,000+ cards, scan with your camera", "index.html?ref=bio", False, "worth"),
        *([("🎁 Win an Elite Trainer Box", "Free monthly giveaway: build your binder to enter", "giveaway.html?ref=bio", False, None)] if GIVEAWAY_ON else []),
        ("Cheap cards worth grading", "This week's 5 picks with eBay links", "social-grade/?ref=bio", False, "grade"),
        ("Grading & card supplies", "Sleeves, Card Saver 1s, top loaders, mailers", "supplies.html?ref=bio", False, "supplies"),
        ("Sell us your cards", "Cash or store-credit offer", "sell.html?ref=bio", False, "sell"),
        ("Centering check", "Free PSA, CGC and BGS check from a photo", "centering.html?ref=bio", False, "centering"),
        ("Sneaker release calendar", "This week's drops and our calls", "sneakers.html?ref=bio", False, "sneakers"),
        ("Trending cards & market report", "Biggest gains and drops this week", "blog/?ref=bio", False, "report"),
        ("Track your collection", "See what your binder is worth", "collection.html?ref=bio", False, "collection"),
    ]
    socials = [("TikTok", "https://www.tiktok.com/@drive.your.style"), ("Instagram", "https://www.instagram.com/drive.yourstyle/"),
               ("YouTube", "https://www.youtube.com/@DriveYourStyle"), ("Facebook", "https://www.facebook.com/682608764928900")]
    ver = date.today().isoformat()
    pic = lambda k: f'<img src="assets/links/{k}.jpg?v={ver}" alt="" loading="lazy" onerror="this.remove()">' if k else ""
    main_btns = "".join(f'<a class="lk lk-main" href="{u}">{pic(k)}<span class="tx"><b>{t}</b><span>{d}</span></span></a>' for t, d, u, main, k in rows if main)
    tiles = "".join(f'<a class="tile" href="{u}">{pic(k)}<span class="tx"><b>{t}</b><span>{d}</span></span></a>' for t, d, u, main, k in rows if not main)
    btns = main_btns + f'<div class="grid">{tiles}</div>'
    soc = "".join(f'<a href="{u}" aria-label="{n}" title="{n}" target="_blank" rel="noopener"><svg viewBox="0 0 24 24" aria-hidden="true">{LINKS_ICONS[n]}</svg></a>' for n, u in socials)
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Drive Your Style · Cards &amp; Kicks</title><meta name="description" content="Shop, check card prices, sell your cards and follow Drive Your Style.">
<link rel="canonical" href="https://market.driveyourstyle.net/links.html"><meta name="theme-color" content="#0b0d14">
<meta property="og:title" content="Drive Your Style · Cards &amp; Kicks"><meta property="og:image" content="https://market.driveyourstyle.net/assets/og.png">
<link rel="icon" type="image/png" href="assets/favicon.png">
<script data-goatcounter="https://driveyourstyle.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
<style>
:root{{--bg:#0b0d14;--ink:#f2f0eb;--ink2:#bdb9b2;--line:rgba(242,240,235,.14)}}
*{{box-sizing:border-box;margin:0}}
body{{min-height:100vh;background:radial-gradient(700px 420px at 85% -10%,rgba(124,92,255,.35),transparent 60%),radial-gradient(600px 400px at 0% 110%,rgba(0,200,255,.18),transparent 60%),var(--bg);color:var(--ink);font:16px/1.4 Inter,system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:520px;margin:0 auto;padding:42px 18px 36px;text-align:center}}
.logo{{width:96px;height:96px;border-radius:50%;background:#000;display:grid;place-items:center;margin:0 auto 14px;border:1px solid var(--line);overflow:hidden}}
.logo img{{width:100%;height:100%;object-fit:cover}}
h1{{font-size:22px;margin-bottom:4px}}
.sub{{color:var(--ink2);font-size:14.5px;margin-bottom:22px}}
.lk,.tile{{display:block;text-align:left;border-radius:16px;border:1px solid var(--line);background:rgba(255,255,255,.04);color:var(--ink);text-decoration:none;overflow:hidden}}
.lk img,.tile img{{display:block;width:100%;aspect-ratio:3/2;object-fit:cover;background:#151827}}
.lk img{{aspect-ratio:2/1}}
.tx{{display:block;padding:11px 13px 12px}}
.lk .tx{{padding:13px 18px 14px}}
.tx b{{display:block;font-size:15px;line-height:1.25}}
.lk .tx b{{font-size:17px}}
.tx span{{display:block;color:var(--ink2);font-size:12.5px;margin-top:3px;line-height:1.3}}
.lk:hover,.lk:focus-visible,.tile:hover,.tile:focus-visible{{border-color:rgba(242,240,235,.4);background:rgba(255,255,255,.07)}}
.lk-main{{background:var(--ink);color:var(--bg);border-color:var(--ink);margin-bottom:12px}}
.lk-main .tx span{{color:#3b3f4a}}
.lk-main:hover,.lk-main:focus-visible{{background:#fff}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.grid .tile:last-child:nth-child(odd){{grid-column:1/-1}}
.grid .tile:last-child:nth-child(odd) img{{aspect-ratio:2/1}}
.soc{{display:flex;justify-content:center;gap:12px;margin:22px 0 14px}}
.soc a{{width:46px;height:46px;border-radius:50%;display:grid;place-items:center;border:1px solid var(--line);color:var(--ink)}}
.soc svg{{width:20px;height:20px}}
.fine{{color:var(--ink2);font-size:12.5px}}
a:focus-visible{{outline:2px solid var(--ink);outline-offset:3px}}
</style></head><body><main>
<div class="logo"><img src="assets/icons/apple-touch-icon.png" alt="Drive Your Style"></div>
<h1>Drive Your Style</h1><p class="sub">Cards &amp; Kicks · Las Vegas</p>
{btns}
<div class="soc">{soc}</div>
<p class="fine">New here? Use <b>WELCOME5</b> for $5 off your first $25+ order.</p>
</main></body></html>'''
    with open(os.path.join(ROOT, "site", "links.html"), "w", encoding="utf-8") as f:
        f.write(html)


def main():
    for page, (title, desc, body) in PAGES.items():
        canon = "" if page == "index" else f"{page}.html"
        hidden = ("importer", "demand", "buyer") + (() if GIVEAWAY_ON else ("giveaway",))
        head = HEAD.replace("<link rel=\"canonical\"", "<meta name=\"robots\" content=\"noindex\">\n<link rel=\"canonical\"") if page in hidden else HEAD
        if page == "index":   # impact.com site ownership check
            head = head.replace('<meta name="theme-color" content="#0b0d14">', '<meta name="theme-color" content="#0b0d14">\n<meta name="impact-site-verification" value="9961457d-75f1-4449-9d0a-10bb739058b9">')
        body = body.replace("@@GWBANNER@@", GW_BANNER if GIVEAWAY_ON else "")
        html = head.replace("@@CANON@@", canon).replace("@@TITLE@@", title).replace("@@DESC@@", desc).replace("@@PAGE@@", page).replace("@@BODY@@", body)
        with open(os.path.join(ROOT, "site", f"{page}.html"), "w", encoding="utf-8") as f:
            f.write(html)
    links_page()
    print("pages written:", ", ".join(PAGES), "+ links")


if __name__ == "__main__":
    main()
