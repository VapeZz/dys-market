"""Regenerates site/*.html from one shared template. Run: python tools/make_pages.py"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Cdefs%3E%3ClinearGradient id='g'%3E%3Cstop offset='0' stop-color='%235ee7ff'/%3E%3Cstop offset='.5' stop-color='%23a78bfa'/%3E%3Cstop offset='1' stop-color='%23ff7ad9'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='32' height='32' rx='8' fill='url(%23g)'/%3E%3C/svg%3E">
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

PAGES = {
"index": ("Market Insights · Drive Your Style",
          "Nightly market prices, biggest movers and set values for Pokémon and One Piece sealed product and cards.", f'''
<section class="hero"><div class="wrap">
  <span class="eyebrow"><b>●</b> Live market data · Beta</span>
  <h1>Know the market <span class="holo">before you rip.</span></h1>
  <p class="lead">We record the going market price for Pokémon and One Piece sealed product and cards every night, so you can see what's moving before you buy, sell or hold.</p>
  <div class="search" data-search>{SEARCH}<input type="search" placeholder="Search products &amp; cards" aria-label="Search products and cards" autocomplete="off"><div class="results"></div></div>
  <div class="chips" id="game-chips"></div>
</div></section>
<div class="wrap"><div class="stats" id="stats">{SK * 4}</div></div>
<section class="block"><div class="wrap">
  <div class="block-head"><div><h2>Biggest sealed movers</h2><p>Sealed products over $5, ranked by market price change.</p></div><a class="more" href="trends.html">Full trends →</a></div>
  <div id="sealed-movers"></div>
</div></section>
<section class="block"><div class="wrap">
  <div class="block-head"><div><h2>Biggest card movers</h2><p>Single cards over $5, ranked by market price change.</p></div><a class="more" href="cards.html">All card movers →</a></div>
  <div id="card-movers"></div>
</div></section>
<section class="block" id="stock-block"><div class="wrap">
  <div class="block-head"><div><h2>In stock at Drive Your Style</h2><p>Our price next to today's market price.</p></div><a class="more" href="https://driveyourstyle.net/collections/sealed-product">Shop sealed →</a></div>
  <div class="grid" id="stock"></div>
</div></section>
<section class="block"><div class="wrap">
  <div class="cta"><div><h2>Get restock &amp; drop alerts</h2><p>Be first to know when new sets, singles and sneakers land at Drive Your Style.</p></div>
  <a class="btn" href="https://driveyourstyle.net/#newsletter">Sign up at the store →</a></div>
</div></section>
<section class="block"><div class="wrap">
  <div class="block-head"><div><h2>Recent &amp; upcoming sets</h2><p>Booster box price (or the main sealed product when there is no booster box) and 7-day change in total sealed value.</p></div><a class="more" href="sets.html">All sets →</a></div>
  <div id="recent"></div>
</div></section>'''),
"sets": ("All sets · Drive Your Style Market Insights",
         "Every Pokémon and One Piece set with booster box market price and 7-day change.", '''
<div class="wrap"><section class="block">
  <div class="block-head"><div><h1 style="font-size:36px">Sets</h1><p id="count"></p></div></div>
  <div class="controls"><div id="game"></div><input class="field" id="q" type="search" placeholder="Filter sets" aria-label="Filter sets">
    <select class="select" id="sort" aria-label="Sort"><option value="pub">Newest first</option><option value="bb">Main sealed price</option><option value="up">7D gainers</option><option value="down">7D decliners</option></select></div>
  <div id="table"><div class="skeleton" style="height:300px"></div></div>
</section></div>'''),
"set": ("Set prices · Drive Your Style Market Insights", "Sealed and card market prices for this set.", '''
<div class="wrap"><div class="crumbs" id="crumbs"></div>
<section class="block" style="padding-top:12px"><h1 id="title" style="font-size:clamp(28px,4vw,42px)"></h1><p class="muted" id="sub"></p>
  <h2 style="font-size:22px;margin:24px 0 12px">Sealed product</h2><div id="sealed"><div class="skeleton" style="height:200px"></div></div>
  <h2 style="font-size:22px;margin:32px 0 12px">Cards</h2><div id="cards"></div>
</section></div>'''),
"product": ("Price history · Drive Your Style Market Insights", "Market price history.", '''
<div class="wrap"><div class="crumbs" id="crumbs"></div><div class="prod" id="prod"><div class="skeleton" style="height:320px"></div></div></div>'''),
"trends": ("Trends · Drive Your Style Market Insights",
           "Biggest sealed product price movers across Pokémon and One Piece.", '''
<div class="wrap"><section class="block">
  <div class="block-head"><div><h1 style="font-size:36px">Trends</h1><p>The 50 biggest sealed price moves for each game and time window. Defaults to products over $20.</p></div></div>
  <div id="sealed"></div>
</section></div>'''),
"cards": ("Card movers · Drive Your Style Market Insights", "Biggest single card price movers by game and set.", f'''
<div class="wrap"><section class="block">
  <div class="block-head"><div><h1 style="font-size:36px">Card movers</h1><p>Single cards over $5. Pick a set to rank that set's cards.</p></div></div>
  <div class="controls"><div id="game"></div><div id="win"></div>
    <select class="select" id="set" aria-label="Set"></select>
    <label class="toggle"><input type="checkbox" id="recent"> Released in last 12 months</label></div>
  <p class="muted" id="note" style="margin:-6px 0 12px;font-size:13px"></p>
  {MOVERS}
</section></div>'''),
"compare": ("Compare prices · Drive Your Style Market Insights", "Compare two Pokémon or One Piece products side by side: market price, recent change and price history.", '''
<div class="wrap"><section class="block">
  <div class="block-head"><div><h1 style="font-size:36px">Compare</h1><p>Pick any two sealed products or cards to compare price, recent change and price history.</p></div></div>
  <div id="slots" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px;margin:8px 0 18px"></div>
  <div id="result"></div>
</section></div>'''),
"calendar": ("Release calendar · Drive Your Style Market Insights", "Upcoming and recent Pokémon, Pokémon Japan and One Piece TCG set release dates with current sealed prices.", '''
<div class="wrap"><section class="block">
  <div class="block-head"><div><h1 style="font-size:36px">Release calendar</h1><p>Upcoming sets and everything released in the last 90 days. Dates come from TCGplayer and can shift.</p></div></div>
  <div class="controls"><div id="game"></div></div>
  <h2 style="font-size:24px;margin:18px 0 0">Upcoming</h2><div id="upcoming"><div class="skeleton" style="height:160px"></div></div>
  <div class="cta" style="margin:28px 0"><div><h2>Want it on release day?</h2><p>Pre-orders and new drops land at Drive Your Style first.</p></div><a class="btn" href="https://driveyourstyle.net/collections/pre-orders">Shop pre-orders →</a></div>
  <h2 style="font-size:24px;margin:18px 0 0">Recently released</h2><div id="released"></div>
</section></div>'''),
"about": ("About the data · Drive Your Style Market Insights", "Where Drive Your Style market prices come from.", '''
<div class="wrap"><article class="prose">
  <h1>Where this data comes from</h1>
  <p>Every night we save the TCGplayer <b>market price</b> for each Pokémon, Pokémon Japan and One Piece product, using the public daily data published by <a href="https://tcgcsv.com" style="color:var(--accent)">TCGCSV</a>. Market price reflects recent completed sales on TCGplayer.</p>
  <h2>How movers are calculated</h2>
  <p>A mover's change compares today's market price with the price saved closest to 7, 30, 90 or 365 days ago. Items under $5 today, or under $1 at the start of the window, are left out so tiny prices don't produce huge percentages.</p>
  <h2>Sets</h2>
  <p>A set's 7-day change is the change in the combined market price of its sealed products. "Booster box" shows the main booster box when the set has one.</p>
  <h2>Good to know</h2>
  <ul><li>Prices can lag by about a day and swing on thin sales, especially right after release.</li>
  <li>These are market reference prices, not Drive Your Style's prices. Items marked "In stock" link to our store.</li>
  <li>For research only. Not financial advice.</li>
  <li>Not affiliated with or endorsed by The Pokémon Company, Nintendo, Bandai or TCGplayer.</li></ul>
</article></div>'''),
}

for page, (title, desc, body) in PAGES.items():
    canon = "" if page == "index" else f"{page}.html"
    html = HEAD.replace("@@CANON@@", canon).replace("@@TITLE@@", title).replace("@@DESC@@", desc).replace("@@PAGE@@", page).replace("@@BODY@@", body)
    with open(os.path.join(ROOT, "site", f"{page}.html"), "w", encoding="utf-8") as f:
        f.write(html)
print("pages written:", ", ".join(PAGES))
