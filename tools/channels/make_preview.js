// A one-file preview of "Where to sell?" for Keo to try on his phone: the real edge-channels.js and edge.css, on SAMPLE
// numbers (made up, not PkmnPrices data). Nothing is sent or saved anywhere. Usage: node tools/channels/make_preview.js <out.html>
const fs = require("fs"), path = require("path");
const root = path.join(__dirname, "../..");
const css = fs.readFileSync(path.join(root, "site/assets/edge.css"), "utf8");
const js = fs.readFileSync(path.join(root, "site/assets/edge-channels.js"), "utf8");
const harness = String.raw`
(() => {
  const C = window.EdgeChannels, shipAuto = (p) => p >= 5000 ? 500 : 100;
  const ebay = { feePct: 13.25, topFrom: 750000, topPct: 2.35, feeFlat: 40, buyerTax: 7.5, ship: null, sup: 50 };
  const common = { roi: 20, minProfit: 500, shipAuto, breaks: [5000], ebay, save: () => {} };
  const tabs = { a: { cost: 7000, ref: 8200, refLabel: "PSA 10 typical sold price (sample)", item: { kind: "graded", name: "Sample card A" } },
                 b: { cost: 4200, ref: 6500, refLabel: "raw sold median (sample)", item: { kind: "raw", name: "Sample card B" } } };
  for (const [k, o] of Object.entries(tabs)) C.mount(document.getElementById("ch-" + k), { ...common, ...o });
  for (const b of document.querySelectorAll("[data-tab]")) b.onclick = () => {
    for (const x of document.querySelectorAll("[data-tab]")) x.classList.toggle("on", x === b);
    for (const k of Object.keys(tabs)) document.getElementById("p-" + k).hidden = k !== b.dataset.tab;
  };
})();`;
const html = `<!doctype html><html lang="en" data-theme="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DYS Edge: where to sell? preview (sample data)</title>
<style>${css}
.pv-note{margin:0 0 12px;padding:10px 12px;border-radius:12px;background:color-mix(in srgb,var(--warn) 14%,transparent);color:var(--warn);font-size:13px;line-height:1.4}
.pv-tabs{display:flex;gap:6px;margin:0 0 12px}.pv-tabs button{flex:1;padding:9px;border-radius:10px;border:1px solid var(--line);background:var(--surface);color:var(--ink-2);font:600 13px var(--font)}
.pv-tabs button.on{background:color-mix(in srgb,var(--accent) 22%,var(--surface));color:var(--ink)}
body{padding-bottom:40px}</style></head><body>
<header class="bar"><div class="bar-in"><div class="brand"><span class="mark" aria-hidden="true">E</span><span>DYS Edge</span></div><span class="asof">Where to sell? preview</span></div></header>
<main class="view"><p class="pv-note"><b>Sample numbers, not real sales.</b> In Edge this section sits under the PSA check (cards you own: your cost is what you paid) and under the Deal check (a card you might buy). Open "Price and costs (edit)" on any option and change a number.</p>
<div class="pv-tabs"><button type="button" data-tab="a" class="on">PSA 10 you own ($70 paid)</button><button type="button" data-tab="b">Deal check (raw, $42 cost)</button></div>
<div id="p-a"><section class="sec panel" id="ch-a"></section></div><div id="p-b" hidden><section class="sec panel" id="ch-b"></section></div></main>
<script>${js}</script><script>${harness}</script></body></html>`;
fs.writeFileSync(process.argv[2], html);
console.log(`wrote ${process.argv[2]} (${html.length} bytes)`);
