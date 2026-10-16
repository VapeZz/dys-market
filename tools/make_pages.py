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
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="assets/icons/apple-touch-icon.png">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="DYS Market">
<link rel="icon" type="image/png" href="assets/favicon.png">
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
<section class="hero hero-tight"><div class="wrap">
  <span class="eyebrow"><b>●</b> Live market data · Beta</span>
  <h1>Know the market <span class="holo">before you rip.</span></h1>
  <p class="lead">Nightly market prices for Pokémon and One Piece cards and sealed product.</p>
  <div class="search" data-search>{SEARCH}<input type="search" placeholder="Search any card or product" aria-label="Search products and cards" autocomplete="off"><div class="results"></div></div>
</div></section>
<section class="block" style="padding-top:4px"><div class="wrap"><div class="gtiles" id="gtiles"></div></div></section>
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
         "Every Pokémon, Pokémon Japan and One Piece set by era, with sealed and card market prices.", '''
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
"search": ("Card search · Drive Your Style Market Insights", "Search every Pokémon, Pokémon Japan and One Piece card and sealed product by name, set, number or rarity, with today's market price.", '''
<div class="wrap"><section class="block">
  <div class="block-head"><div><h1 style="font-size:36px">Card search</h1><p>Every card and sealed product we track. Search by name, set, card number or rarity.</p></div></div>
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
"calendar": ("Release calendar · Drive Your Style Market Insights", "Upcoming and recent Pokémon, Pokémon Japan and One Piece TCG set release dates with current sealed prices.", '''
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
"collection": ("My Collection · Drive Your Style Market Insights", "Track your Pokémon and One Piece card collection with live market values.", '''
<div class="wrap"><section class="block">
  <div class="block-head"><div><span class="eyebrow"><b>●</b> Members</span><h1 id="title" style="font-size:36px;margin-top:8px">My collection</h1>
    <p id="shared-note" class="muted" hidden>A collection shared from Drive Your Style. <a href="collection.html" style="color:var(--accent)">Start your own →</a></p></div></div>
  <div id="acct" class="panel acct-bar" hidden></div>
  <div id="prof" class="panel prof-panel" hidden></div>
  <div id="mine">
    <div class="search" id="add-box" style="max-width:640px">''' + SEARCH + '''<input id="add-q" type="search" placeholder="Search a card or product to add" aria-label="Search a card or product to add" autocomplete="off"><div class="results" id="add-results"></div></div>
    <p class="muted" id="added" style="min-height:20px;font-size:14px;margin:8px 0 0" role="status"></p>
  </div>
  <div class="stats" id="stats" style="margin:18px 0"></div>
  <div class="chart-card" id="cchart-wrap" hidden style="margin-bottom:18px"><div class="chart-head"><b>Collection value</b><div id="crange"></div></div><div class="chart" id="cchart"></div>
    <p class="muted" style="font-size:12px;margin:6px 0 4px">Your current quantities at each day's market price.</p></div>
  <div id="csets" style="margin-bottom:18px"></div>
  <div class="ctools"><input class="field" id="cq" type="search" placeholder="Search your collection" aria-label="Search your collection">
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
"collectors": ("Collectors · Drive Your Style Market Insights", "Browse Pokémon and One Piece collections from Drive Your Style collectors. Like your favorites and follow collectors.", '''
<div class="wrap"><section class="block">
  <div class="block-head"><div><span class="eyebrow"><b>●</b> Community</span><h1 style="font-size:36px;margin-top:8px">Collectors</h1>
    <p>Binders collectors chose to share. Tap one to see every card, like it, or follow the collector.</p></div>
    <a class="btn primary" href="collection.html" id="join">Share your binder →</a></div>
  <div class="controls"><div id="ctab"></div><input class="field" id="cfind" type="search" placeholder="Find a collector" aria-label="Find a collector"></div>
  <p class="muted" id="cnote" style="font-size:13px;margin:4px 0 12px"></p>
  <div id="clist" class="col-grid"><div class="skeleton" style="height:220px"></div></div>
  <p class="muted" style="font-size:12px;margin-top:18px">Values use nightly market prices for raw cards and each collector's own value for slabs. Likes and follows need a free account and update every 30 minutes.</p>
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
    head = HEAD.replace("<link rel=\"canonical\"", "<meta name=\"robots\" content=\"noindex\">\n<link rel=\"canonical\"") if page in ("importer", "demand") else HEAD
    html = head.replace("@@CANON@@", canon).replace("@@TITLE@@", title).replace("@@DESC@@", desc).replace("@@PAGE@@", page).replace("@@BODY@@", body)
    with open(os.path.join(ROOT, "site", f"{page}.html"), "w", encoding="utf-8") as f:
        f.write(html)
print("pages written:", ", ".join(PAGES))
