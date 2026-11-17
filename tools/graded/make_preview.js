// A one-file preview of the graded sold-price check for Keo to try on his phone: the real edge-graded.js and edge.css,
// on SAMPLE sales (made up, not PkmnPrices data). The "Sell, grade or keep?" lines use the same code. Nothing is sent anywhere.
// Usage: node tools/graded/make_preview.js <out.html>
const fs = require("fs"), path = require("path");
const root = path.join(__dirname, "../..");
const css = fs.readFileSync(path.join(root, "site/assets/edge.css"), "utf8");
const js = fs.readFileSync(path.join(root, "site/assets/edge-graded.js"), "utf8");
const harness = String.raw`
(() => {
  const G = window.EdgeGraded, $ = (q) => document.querySelector(q), T = Math.floor(Date.now() / 864e5);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // Edge's defaults: eBay trading cards, $1 / $5 shipping (under / from $50), $0.50 supplies, 20% target, $5 minimum profit
  const base = { feePct: 13.25, topPct: 2.35, topFrom: 750000, perOrder: 40, buyerTax: 7.5, ship: null, supplies: 50, shipAuto: (p) => p >= 5000 ? 500 : 100, breaks: [5000] };
  let saved = null;
  const sell = () => ({ ...base, ...(saved || {}) });
  const comps = (label, list) => list.map(([age, d]) => [T - age, Math.round(d * 100), label, 1]);
  // sample sales, made up to show each call
  const CARDS = [
    { key: "a", name: "Sample card A", label: "PSA 10", cost: 7000, note: "Paid $70, bought graded",
      sales: comps("PSA 10", [[6, 82], [7, 80], [8, 84], [9, 79], [10, 75], [12, 83], [15, 86], [17, 84], [19, 82], [21, 85], [24, 81], [26, 88], [29, 83], [45, 90], [60, 92]]) },
    { key: "b", name: "Sample card B", label: "PSA 10", cost: 15000, note: "Paid $150, bought graded",
      sales: comps("PSA 10", [[6, 260], [7, 255], [9, 265], [12, 250], [14, 262], [18, 258], [22, 259], [27, 249], [40, 240], [70, 230]]) },
    { key: "c", name: "Sample card C", label: "PSA 9", cost: 9000, note: "Paid $75 + $15 grading",
      sales: comps("PSA 9", [[30, 120], [70, 115]]) } ];
  const box = $("#cards");
  box.innerHTML = CARDS.map((c) => '<section class="sec panel"><div class="sec-head"><h2 style="margin:0">' + esc(c.name) + " · " + esc(c.label) + '</h2></div><p class="small muted" style="margin:0 0 6px">' + esc(c.note) + '</p><div id="gs-' + c.key + '"></div></section>').join("");
  const own = () => { $("#own").innerHTML = CARDS.map((c) => { const r = G.evaluate({ asOf: T, label: c.label, comps: c.sales }, { cost: c.cost, label: c.label }, sell(), { today: T, roi: 20, minProfit: 500 });
      const L = { sell: ["good", "Sell clears your target"], hold: ["", "Keep for now"], insufficient: ["warn", "Not enough sales"] }[r.verdict];
      return '<div class="row"><div class="meta"><b>' + esc(c.name) + '</b><span class="why own-res"><span class="chip ' + L[0] + '">' + L[1] + "</span> " + esc(G.line(r)) + "</span></div></div>"; }).join(""); };
  for (const c of CARDS) {
    const data = { asOf: T, label: c.label, comps: c.sales, source: "SAMPLE sales (made up for this preview)" };
    G.mount($("#gs-" + c.key), { holding: { cost: c.cost, label: c.label }, sell: sell(), base, today: T, roi: 20, minProfit: 500, data, readAt: "sample",
      load: () => new Promise((ok) => setTimeout(() => ok({ ok: true, data, note: "In Edge this reads real eBay sold prices (about 10 to 160 credits). The preview reloads the samples.", readAt: "sample" }), 500)),
      save: (o) => { saved = o; own(); } });
  }
  own();
})();`;
const html = `<!doctype html><html lang="en" data-theme="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DYS Edge graded sold-price check preview (sample data)</title>
<style>${css}
.pv-note{margin:0 0 12px;padding:10px 12px;border-radius:12px;background:color-mix(in srgb,var(--warn) 14%,transparent);color:var(--warn);font-size:13px;line-height:1.4}
body{padding-bottom:40px}</style></head><body>
<header class="bar"><div class="bar-in"><div class="brand"><span class="mark" aria-hidden="true">E</span><span>DYS Edge</span></div><span class="asof">Graded check preview</span></div></header>
<main class="view"><p class="pv-note"><b>Sample sales, not real.</b> This is what a graded item shows in Mine → Ledger after you tap <b>Check sold prices</b>: one HOLD, one SELL candidate and one INSUFFICIENT DATA. Open "Selling costs" and change a number to see everything recalculate.</p>
<div id="cards"></div>
<section class="sec panel"><span class="lab">Sell, grade or keep? (Mine → Inventory) · graded items now included</span><div class="list" id="own"></div></section></main>
<script>${js}</script><script>${harness}</script></body></html>`;
fs.writeFileSync(process.argv[2], html);
console.log(`wrote ${process.argv[2]} (${html.length} bytes)`);
