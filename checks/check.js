// Browser checks for the search fixes on a local test build. Nothing here depends on the day's prices:
// expected values are read from the build's own data and HTML.
//
//   node checks/check.js            AFTER=http://127.0.0.1:8765 (the test build)  BEFORE=http://127.0.0.1:8766 (the published copy)
//
// Everything outside 127.0.0.1 is blocked (card photos, fonts, analytics), so only the site's own behaviour is measured.
const { chromium } = require("playwright");
const AFTER = process.env.AFTER || "http://127.0.0.1:8765", BEFORE = process.env.BEFORE || "http://127.0.0.1:8766", SITE = "https://market.driveyourstyle.net/";
const results = [];
const ok = (name, pass, detail = "") => { results.push({ name, pass: !!pass, detail }); };
// the page script's own price format (money() in site/assets/app.js)
const money = (c) => { const d = c / 100; return d >= 1000 ? "$" + Math.round(d).toLocaleString("en-US") : "$" + d.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); };

async function open(ctx, url, wait = 1800) {
  const page = await ctx.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push("exception: " + String(e.message).slice(0, 160)));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource|net::ERR/.test(m.text())) errs.push("console: " + m.text().slice(0, 160)); });
  const resp = await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(wait);
  return { page, errs, status: resp.status() };
}
const head = (page) => page.evaluate(() => ({
  title: document.title,
  canon: [...document.querySelectorAll('link[rel="canonical"]')].map((l) => l.getAttribute("href")),
  desc: document.querySelector('meta[name="description"]')?.content || "",
  ogurl: document.querySelector('meta[property="og:url"]')?.content || "",
  ogtitle: document.querySelector('meta[property="og:title"]')?.content || "",
  robots: document.querySelector('meta[name="robots"]')?.content || "",
  h1: document.querySelector("h1")?.innerText || "",
  overflow: document.documentElement.scrollWidth > innerWidth + 1,
}));
const bigPrice = (raw) => (raw.match(/<div class="price-big">([^<]*)</) || [])[1];

(async () => {
  const browser = await chromium.launch();
  const probe = await browser.newContext();
  const J = async (path) => (await probe.request.get(`${AFTER}/${path}`)).json();
  const set151 = await J("data/set/23237.json"), setRR = await J("data/set/1367.json"), set30 = await J("data/set/24722.json");
  const etb = set151.items.find((i) => i.id === 503313), zard = set151.items.find((i) => i.id === 517045);
  const noPage = set151.items.find((i) => i.t === "c" && i.p && !i.pg);                       // a priced card with no price page
  const dkR = setRR.items.find((i) => i.n === "Darkrai G (Reverse Holofoil)"), dkH = setRR.items.find((i) => i.n === "Darkrai G (Holofoil)");
  const stocked = set30.items.find((i) => i.dys && i.pg);                                      // something in stock at the store
  ok("test data: the items these checks use are in the build", etb?.pg && zard?.pg && noPage && dkR?.pg && dkH, JSON.stringify({ etb: etb?.pg, zard: zard?.pg, noPage: noPage?.id, dkR: dkR?.pg }));
  const hasBefore = await probe.request.get(`${BEFORE}/index.html`).then((r) => r.ok()).catch(() => false);

  for (const [label, vp] of [["phone", { width: 375, height: 812 }], ["desktop", { width: 1280, height: 800 }]]) {
    const ctx = await browser.newContext({ viewport: vp });
    await ctx.route((u) => !u.href.startsWith("http://127.0.0.1"), (r) => r.abort());
    const T = (n) => `[${label}] ${n}`;

    // A. set page
    {
      const { page, errs } = await open(ctx, `${AFTER}/set.html?id=23237`);
      const h = await head(page);
      ok(T("set page: exactly one address tag, its own"), h.canon.length === 1 && h.canon[0] === SITE + "set.html?id=23237", JSON.stringify(h.canon));
      ok(T("set page: own title"), h.title === `${set151.n} prices · Drive Your Style Market Insights`, h.title);
      ok(T("set page: own description"), h.desc.startsWith(`Every card and sealed product in ${set151.n} (Pokémon)`), h.desc);
      ok(T("set page: og:url and og:title match"), h.ogurl === SITE + "set.html?id=23237" && h.ogtitle === h.title, h.ogurl);
      const links = await page.evaluate(() => { const a = [...document.querySelectorAll("#grid a.cimg")].map((x) => x.getAttribute("href")); return { n: a.length, p: a.filter((x) => x.startsWith("p/")).length, prod: a.filter((x) => x.startsWith("product.html")).length }; });
      ok(T("set page: card tiles link to static price pages where they exist"), links.p >= 20 && links.p + links.prod === links.n, JSON.stringify(links));
      ok(T("set page: no script errors"), errs.length === 0, errs.join(" | "));
      ok(T("set page: no sideways scroll"), !h.overflow);
      await page.click('#grid a.cimg[href^="p/"]');
      await page.waitForTimeout(1800);
      const at = page.url();
      const back = await page.evaluate(() => document.querySelector(".crumb-back")?.innerText || "");
      ok(T("tile opens a /p/ price page"), /\/p\/[a-z0-9-]+\.html$/.test(at), at);
      ok(T("price page Back button names where you came from"), back.includes(`Back to ${set151.n}`), back);
      await page.click(".crumb-back");
      await page.waitForTimeout(1200);
      ok(T("Back returns to the set page"), page.url() === `${AFTER}/set.html?id=23237`, page.url());
      await page.close();
    }
    if (hasBefore) {
      const { page } = await open(ctx, `${BEFORE}/set.html?id=23237`);
      const h = await head(page);
      ok(T("BEFORE: the published set page still names the shared address (this check can tell the difference)"), h.canon[0] === SITE + "set.html", JSON.stringify(h.canon));
      await page.close();
    }
    // B. interactive card page with a static twin
    {
      const { page, errs } = await open(ctx, `${AFTER}/product.html?id=503313&set=23237`);
      const h = await head(page);
      ok(T("card page (has price page): one address tag, the price page"), h.canon.length === 1 && h.canon[0] === `${SITE}p/${etb.pg}.html`, JSON.stringify(h.canon));
      ok(T("card page: own description with today's price"), h.desc === `151 Elite Trainer Box (${set151.n}, Pokémon) market price today: ${money(etb.p)}. Price history, recent changes and grading math.`, h.desc);
      ok(T("card page: no script errors"), errs.length === 0, errs.join(" | "));
      await page.close();
    }
    // C. interactive card page without a static twin
    {
      const { page, errs } = await open(ctx, `${AFTER}/product.html?id=${noPage.id}&set=23237`);
      const h = await head(page);
      ok(T("card page (no price page): one address tag, itself"), h.canon.length === 1 && h.canon[0] === `${SITE}product.html?id=${noPage.id}&set=23237`, JSON.stringify(h.canon));
      ok(T("card page (no price page): no script errors"), errs.length === 0, errs.join(" | "));
      await page.close();
    }
    // D. static price page becomes the full card page (sealed)
    {
      const url = `${AFTER}/p/${etb.pg}.html`;
      const raw = await (await ctx.request.get(url)).text();
      const { page, errs } = await open(ctx, url);
      const h = await head(page);
      const st = await page.evaluate(() => ({
        chart: !!document.querySelector("#chart svg"), add: document.querySelector("#addcol")?.innerText || "", want: document.querySelector("#watch")?.innerText || "",
        staticLeft: !!document.querySelector("#pp-static"), price: document.querySelector(".price-big")?.innerText || "",
        bad: [...document.querySelectorAll("main a[href]")].map((a) => a.href).filter((u) => u.includes("/p/p/") || u.includes("/p/set.html") || u.includes("/p/product.html") || u.includes("/p/sets.html")).slice(0, 3),
        pLinks: [...document.querySelectorAll("main a[href]")].map((a) => a.getAttribute("href")).filter((u) => u.startsWith("p/")).length,
        crumbs: document.querySelector(".crumb-path")?.innerText.replace(/\s+/g, " ") || "",
      }));
      ok(T("price page: address tag unchanged by the script (one, its own)"), h.canon.length === 1 && h.canon[0] === `${SITE}p/${etb.pg}.html`, JSON.stringify(h.canon));
      ok(T("price page: title from the HTML is kept"), h.title === (raw.match(/<title>([^<]*)<\/title>/) || [])[1].replace(/&amp;/g, "&") && /151 Elite Trainer Box Price/.test(h.title), h.title);
      ok(T("price page: HTML alone already has price, heading and one address tag"), bigPrice(raw) === money(etb.p) && (raw.match(/rel="canonical"/g) || []).length === 1 && raw.includes("<h1"), bigPrice(raw));
      ok(T("price page: full tools are drawn (chart, collection, want list)"), st.chart && /Add to collection|In collection/.test(st.add) && /Want/.test(st.want), JSON.stringify({ chart: st.chart, add: st.add, want: st.want }));
      ok(T("price page: same price as its HTML"), st.price.trim() === bigPrice(raw), `${st.price} vs ${bigPrice(raw)}`);
      ok(T("price page: plain list removed once the full one is drawn"), !st.staticLeft);
      ok(T("price page: every link resolves from the site root"), st.bad.length === 0, st.bad.join(" "));
      ok(T("price page: links on to other price pages"), st.pLinks >= 5, String(st.pLinks));
      ok(T("price page: breadcrumb path"), st.crumbs.includes(`Sets Pokémon ${set151.n} 151 Elite Trainer Box`), st.crumbs);
      ok(T("price page: no script errors"), errs.length === 0, errs.join(" | "));
      ok(T("price page: no sideways scroll"), !h.overflow);
      await page.click("#addcol");
      await page.waitForTimeout(300);
      const col = await page.evaluate(() => Object.keys(localStorage).map((k) => localStorage.getItem(k)).join(" "));
      ok(T("price page: Add to collection saves the item"), col.includes("503313"), col.slice(0, 120));
      const swScope = await page.evaluate(async () => { try { const r = await navigator.serviceWorker.getRegistration(); return r ? r.scope : "none"; } catch (e) { return "err " + e; } });
      ok(T("price page: app worker registered for the whole site"), swScope === `${AFTER}/`, swScope);
      await page.close();
    }
    // E. price page of a second printing opens on that printing
    {
      const { page, errs } = await open(ctx, `${AFTER}/p/${dkR.pg}.html`);
      const price = await page.evaluate(() => document.querySelector(".price-big")?.innerText.trim());
      ok(T("second-printing price page shows that printing's price"), price === money(dkR.p), `${price} vs ${money(dkR.p)}`);
      ok(T("second-printing price page: no script errors"), errs.length === 0, errs.join(" | "));
      const switched = await page.evaluate(() => { const b = [...document.querySelectorAll("#var button, #var [role=tab]")].find((x) => /^Holofoil$/.test(x.innerText.trim())); if (!b) return "no tab"; b.click(); return document.querySelector(".price-big")?.innerText.trim(); });
      ok(T("switching printing redraws with the other price"), switched === money(dkH.p), `${switched} vs ${money(dkH.p)}`);
      const canon = await page.evaluate(() => [...document.querySelectorAll('link[rel="canonical"]')].map((l) => l.getAttribute("href")));
      ok(T("still exactly one address tag after switching"), canon.length === 1 && canon[0] === `${SITE}p/${dkR.pg}.html`, JSON.stringify(canon));
      await page.close();
    }
    // F. price page of an item in stock at the store (skipped when nothing from this set is in stock)
    if (stocked) {
      const { page, errs } = await open(ctx, `${AFTER}/p/${stocked.pg}.html`);
      const buy = await page.evaluate(() => document.querySelector(".dys-buy")?.innerText.replace(/\s+/g, " ") || "");
      ok(T("in-stock price page shows the store buy box"), /IN STOCK AT DRIVE YOUR STYLE/.test(buy), buy.slice(0, 80));
      ok(T("in-stock price page: no script errors"), errs.length === 0, errs.join(" | "));
      await page.close();
    }
    // G. heading doesn't change when the script takes over; script navigation and Sell to us work from /p/
    {
      const url = `${AFTER}/p/${zard.pg}.html`;
      const raw = await (await ctx.request.get(url)).text();
      const rawH1 = (raw.match(/<h1[^>]*>([^<]*)/) || [])[1];
      const { page, errs } = await open(ctx, url);
      const h = await head(page);
      ok(T("price page: heading is the same before and after the script draws"), rawH1 === "Charizard ex 199/165 price" && h.h1 === rawH1, `${rawH1} | ${h.h1}`);
      await page.click("#sellit");
      await page.waitForTimeout(400);
      const sell = await page.evaluate(() => Object.keys(localStorage).filter((k) => k.includes("sell")).map((k) => localStorage.getItem(k)).join(" "));
      ok(T("price page: Sell to us adds the card to the sell list"), sell.includes("517045"), sell.slice(0, 100));
      const want = await page.evaluate(() => { document.querySelector("#watch").click(); return document.querySelector("#watch").innerText; });
      ok(T("price page: Want button toggles"), /On your Want list/.test(want), want);
      ok(T("price page (card): no script errors"), errs.length === 0, errs.join(" | "));
      await page.evaluate(() => { location.href = "sell.html"; });
      await page.waitForTimeout(1200);
      ok(T("price page: script navigation goes to the site root, not /p/"), page.url() === `${AFTER}/sell.html`, page.url());
      const list = await page.evaluate(() => document.querySelector("#sell-list")?.innerText || "");
      ok(T("sell page lists the card added from the price page"), /Charizard ex/.test(list), list.slice(0, 80));
      await page.close();
    }
    // H. not-found page
    {
      const { page, errs, status } = await open(ctx, `${AFTER}/p/charizard-ex-old-page-123456.html`);
      const h = await head(page);
      const st = await page.evaluate(() => ({ tryHref: document.querySelector("#nf-try a")?.getAttribute("href") || "", hidden: document.querySelector("#nf-try")?.hidden, header: !!document.querySelector("header.top .brand"), css: getComputedStyle(document.body).backgroundColor }));
      ok(T("missing page: answers 404"), status === 404, String(status));
      ok(T("missing page: our own page, styled, with the menu"), h.h1 === "We couldn't find that page" && st.header && st.css !== "rgba(0, 0, 0, 0)", JSON.stringify({ h1: h.h1, css: st.css }));
      ok(T("missing page: offers the search the address asked for"), st.tryHref === "search.html?q=charizard%20ex%20old%20page" && !st.hidden, st.tryHref);
      ok(T("missing page: kept out of search results, no address tag"), h.robots === "noindex" && h.canon.length === 0, h.robots);
      ok(T("missing page: no script errors"), errs.length === 0, errs.join(" | "));
      await page.click("#nf-try a");
      await page.waitForTimeout(2500);
      ok(T("missing page: the suggested search opens Price check with the words filled in"), page.url() === `${AFTER}/search.html?q=charizard%20ex%20old%20page` && (await page.inputValue("#sq")) === "charizard ex old page", page.url());
      await page.close();
      const deep = await open(ctx, `${AFTER}/some/deep/old/link.html`);
      const dh = await head(deep.page);
      ok(T("missing page at any depth still loads its styles and menu"), deep.status === 404 && dh.h1 === "We couldn't find that page" && deep.errs.length === 0 && (await deep.page.evaluate(() => !!document.querySelector("header.top .brand"))), deep.errs.join(" | "));
      await deep.page.close();
    }
    // I. home title
    {
      const { page, errs } = await open(ctx, `${AFTER}/index.html`);
      const h = await head(page);
      ok(T("home: new title"), h.title === "Pokémon Card Prices & Price History · Drive Your Style", h.title);
      ok(T("home: address tag unchanged"), h.canon.length === 1 && h.canon[0] === SITE, JSON.stringify(h.canon));
      ok(T("home: no script errors"), errs.length === 0, errs.join(" | "));
      await page.close();
    }
    // J. addresses that don't exist
    {
      const a = await open(ctx, `${AFTER}/set.html?id=999999999`);
      ok(T("set that doesn't exist: marked noindex"), (await head(a.page)).robots === "noindex");
      await a.page.close();
      const b = await open(ctx, `${AFTER}/product.html?id=1&set=23237`);
      const bh = await head(b.page);
      ok(T("card that doesn't exist: marked noindex, no address tag"), bh.robots === "noindex" && bh.canon.length === 0, bh.robots + JSON.stringify(bh.canon));
      await b.page.close();
    }
    // N. every other page still loads clean
    for (const p of ["search.html", "sets.html", "sets.html?game=pokemon", "cards.html", "trends.html", "grading.html", "centering.html", "collection.html", "watchlist.html", "intel.html", "investing.html", "calendar.html", "compare.html", "sneakers.html", "sell.html", "collectors.html", "about.html", "tools.html", "blog/", "supplies.html", "legal.html", "links.html", "scout.html", "buyer.html"]) {
      const { page, errs } = await open(ctx, `${AFTER}/${p}`, p === "search.html" || p === "grading.html" ? 3000 : 1300);
      const h = await head(page);
      ok(T(`${p}: no script errors, no sideways scroll, address tag unchanged`), errs.length === 0 && !h.overflow && h.canon.length <= 1, errs.join(" | ") + (h.overflow ? " overflow" : ""));
      await page.close();
    }
    await ctx.close();
  }
  await browser.close();
  const bad = results.filter((r) => !r.pass);
  for (const r of results) if (!r.pass || process.env.VERBOSE) console.log(`${r.pass ? "PASS" : "FAIL"}  ${r.name}${r.pass ? "" : "   -> " + r.detail}`);
  console.log(`${results.length - bad.length} of ${results.length} checks passed`);
  process.exit(bad.length ? 1 : 0);
})().catch((e) => { console.error("check script crashed:", e); process.exit(2); });
