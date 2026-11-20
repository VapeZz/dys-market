// A one-file preview of Today's action list (Holdings Advisor) for Keo to look at on his phone: the real edge-advisor.js,
// edge-deal.js, edge-graded.js and edge-channels.js run on SAMPLE sales (made up, not PkmnPrices data), with edge.css.
// Nothing is sent or saved. Usage: node tools/advisor/make_preview.js <out.html>
const fs = require("fs"), path = require("path");
const root = path.join(__dirname, "../..");
const A = require(path.join(root, "site/assets/edge-advisor.js"));
const D = require(path.join(root, "site/assets/edge-deal.js"));
const G = require(path.join(root, "site/assets/edge-graded.js"));
const C = require(path.join(root, "site/assets/edge-channels.js"));
const Y = require(path.join(root, "tools/deal/synth.js"));
const css = fs.readFileSync(path.join(root, "site/assets/edge.css"), "utf8");
const T = Y.DAY0, cfg = Y.cfg();
const AGES = [9, 12, 15, 20, 25, 40, 50, 60, 70, 80];
const flat = (grade, px, ages) => ages.map((a) => [T - a, px, grade, 1]);
const chOpts = (kind, cost, ref, t = "c") => ({ item: { kind, name: "Sample" }, saved: {}, roi: 20, minProfit: 500, breaks: t === "s" ? [10000] : [5000], shipAuto: (p) => t === "s" ? (p >= 10000 ? 1500 : 800) : p >= 5000 ? 500 : 100,
  ebay: { feePct: 13.25, topFrom: 750000, topPct: 2.35, feeFlat: 40, buyerTax: 7.5, ship: null, sup: t === "s" ? 150 : 50 }, cost, ref });
function raw(name, cost, data, o = {}) {
  const t = o.t || "c", own = D.own({ name, t, tcg: o.tcg || 10000, tcgDay: T }, data, { cost, cond: o.cond || "NM" }, cfg), ref = own.r.routes.flip.exit;
  return { key: name, name, kind: t === "s" ? "sealed" : "raw", qty: o.qty || 1, cost, cond: o.cond || "NM", book: o.book || "Business", own,
    ch: ref && ["sell", "hold", "grade"].includes(own.label) ? C.compare(chOpts(t === "s" ? "sealed" : "card", cost, ref, t)) : null };
}
const SELL = { feePct: 13.25, topPct: 2.35, topFrom: 750000, perOrder: 40, buyerTax: 7.5, ship: null, supplies: 50, shipAuto: (p) => p >= 5000 ? 500 : 100, breaks: [5000] };
function slab(name, cost, list, book = "Personal") {
  const data = { asOf: T, label: "PSA 10", comps: list.map(([age, c]) => [T - age, c, "PSA 10", 1]), capped: [], oldestRead: null };
  const r = G.evaluate(data, { cost, label: "PSA 10" }, SELL, { today: T, roi: 20, minProfit: 500 });
  return { key: name, name, kind: "graded", qty: 1, cost, grade: "PSA 10", book, graded: r, ch: r.typical != null ? C.compare(chOpts("graded", cost, r.typical)) : null };
}
const list = [
  raw("Sample modern chase card", 3000, { asOf: T, comps: flat("raw", 10000, AGES) }),
  raw("Sample vintage holo (LP)", 2500, { asOf: T, comps: flat("raw", 6000, AGES) }, { cond: "LP" }),
  raw("Sample alt-art card", 1000, { asOf: T, comps: [...flat("raw", 4000, AGES), ...flat("PSA 10", 20000, AGES), ...flat("PSA 9", 7000, AGES)], pop: { total: 1000, g10: 400, g9: 400 } }, { tcg: 4000 }),
  raw("Sample card bought high", 9500, { asOf: T, comps: flat("raw", 10000, AGES) }),
  raw("Sample card, prices slipping", 7000, { asOf: T, comps: [...flat("raw", 8500, [9, 12, 15, 20, 25]), ...flat("raw", 11000, [40, 50, 60, 70, 80])] }),
  raw("Sample steady card", 7500, { asOf: T, comps: flat("raw", 10000, AGES) }),
  raw("Sample Elite Trainer Box", 5500, { asOf: T, comps: flat("sealed", 7500, AGES) }, { t: "s" }),
  raw("Sample rarely-sold promo", 2000, { asOf: T, comps: flat("raw", 6000, [9, 40]) }),
  slab("Sample PSA 10 (like your McDonald's Pikachu)", 7000, [[6, 8200], [7, 8000], [8, 8400], [9, 7900], [12, 8300], [20, 8200], [25, 8100]]),
  slab("Sample PSA 10 with few sales", 10000, [[6, 12000], [40, 11000]], "Business"),
];
const B = A.board(list);
const body = A.html(B, { roi: 20 });
const html = `<!doctype html><html lang="en" data-theme="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DYS Edge: Today's action list preview (sample data)</title>
<style>${css}
.pv-note{margin:0 0 12px;padding:10px 12px;border-radius:12px;background:color-mix(in srgb,var(--warn) 14%,transparent);color:var(--warn);font-size:13px;line-height:1.4}
body{padding-bottom:40px}</style></head><body>
<header class="bar"><div class="bar-in"><div class="brand"><span class="mark" aria-hidden="true">E</span><span>DYS Edge</span></div><span class="asof">Today · preview</span></div></header>
<main class="view"><p class="pv-note"><b>Sample holdings and made-up sales, not real data.</b> In Edge this is the top of Today: tap <b>Review my holdings</b> and every item in your Ledger is checked against real eBay sold prices (PkmnPrices, through your relay). Results last for that visit only. The same calls show as chips on Mine → Inventory.</p>
<section class="sec" id="t-adv"><div class="sec-head"><h2>Your holdings: what to do</h2></div>
<p class="muted small adv-note">Checks each holding against real eBay sold prices (PkmnPrices, up to about 1,800 credits for 10 items of your 20,000 a day). Facts at today's prices, not a forecast. Nothing is saved; results last for this visit.</p>
<div class="btns"><button type="button" class="btn sm">Review again</button></div><p class="small muted" style="margin:0">Reviewed 10 of 10 just now · sample.</p>
${body}</section>
<section class="sec"><div class="sec-head"><h2>What to consider buying</h2><span class="chip hot">1</span></div>
<div class="list"><div class="row"><span class="ph"></span><span style="min-width:0;display:flex;flex-direction:column;gap:2px"><span class="nm">Sample watched card</span><span class="st">Sample set</span></span><span class="rt"><b>$41.00</b><small class="muted">target $45.00</small></span>
<span class="why">Lowest listing (any condition) at or under your target. Not checked against sold prices yet: open it and run the Deal check.</span></div></div>
<p class="muted small adv-note">Edge only calls something a <b>BUY candidate</b> in a card's Deal check, after real sold prices clear every check (sales, freshness, spread, trend and your 20% target). Near Mint deals from the daily finder will show here once it's connected.</p></section>
<p class="muted small">Below this on Today: market brief, your inventory value, market indices, biggest moves, and "Grading ideas · estimates" (labelled as not checked against sold prices). The old "Best flips right now" list (lowest listing, any condition) is gone from Today.</p></main>
<script>for (const b of document.querySelectorAll(".adv-tile[data-jump]")) b.onclick = () => { const t = document.getElementById("adv-" + b.dataset.jump); if (t) t.scrollIntoView({ behavior: "smooth", block: "start" }); };</script></body></html>`;
fs.writeFileSync(process.argv[2], html);
console.log(`wrote ${process.argv[2]} (${html.length} bytes)`, JSON.stringify(B.counts));
