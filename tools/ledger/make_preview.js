// A one-file preview of the Ledger (Mine → Ledger) for Keo to try on his phone: the real edge-ledger.js and
// edge.css, on SAMPLE data, with a pretend Sheet kept in the page. Nothing is real, nothing is sent anywhere.
// Usage: node tools/ledger/make_preview.js <out.html>
const fs = require("fs"), path = require("path");
const root = path.join(__dirname, "../..");
const css = fs.readFileSync(path.join(root, "site/assets/edge.css"), "utf8");
const js = fs.readFileSync(path.join(root, "site/assets/edge-ledger.js"), "utf8");
const harness = String.raw`
(() => {
  const L = window.EdgeLedger, $ = (q) => document.querySelector(q);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (c, whole) => { if (c == null || !isFinite(c)) return "—"; const neg = c < 0, d = Math.abs(c) / 100;
    const s = d >= 1000 || whole ? "$" + Math.round(d).toLocaleString("en-US") : "$" + d.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); return (neg ? "−" : "") + s; };
  const signed = (c) => c == null || !isFinite(c) ? "—" : (c >= 0 ? "+" : "") + money(c);
  const localDay = () => { const d = new Date(); return new Date(d - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10); };
  const cents = (v) => Math.round((parseFloat(v) || 0) * 100), dollars = (c) => c == null ? "" : (c / 100).toFixed(2).replace(/\.00$/, "");
  const fmtDay = (d) => d ? new Date(d + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "";
  const cls = (x) => x > 0 ? "up" : x < 0 ? "down" : "";
  function toast(m) { const t = $("#toast"); t.textContent = m; t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, 2400); }
  // sample data (made up; not real sales or prices)
  const mem = {}, storage = { getItem: (k) => mem[k] ?? null, setItem: (k, v) => { mem[k] = String(v); } };
  const st = L.Store(storage, "preview");
  const y = new Date().getFullYear(), d = (m, dd) => y + "-" + String(m).padStart(2, "0") + "-" + String(dd).padStart(2, "0");
  st.put("cash", { day: d(1, 2), book: "Business", kind: "Starting cash", amount: 300000 });
  const show = L.buyRows({ day: d(9, 14), book: "Business", where: "Card show", from: "Sample table 12", pay: "Cash", tax: 0, ship: 0, fees: 0,
    lines: [{ kind: "Raw", name: "Sample card A (raw, NM)", qty: 1, price: 42000 }, { kind: "Raw", name: "Sample card B (raw, NM)", qty: 2, price: 6500 }, { kind: "Sealed", name: "Sample booster box", qty: 1, price: 16000 }] });
  st.put("buys", show.buy); show.items.forEach((x) => st.put("items", x));
  const online = L.buyRows({ day: d(10, 3), book: "Personal", where: "Online", from: "eBay", pay: "Card", tax: 1676, ship: 499, fees: 0, lines: [{ kind: "Graded", name: "Sample card C", grader: "PSA", grade: "10", cert: "00000000", qty: 1, price: 20000 }] });
  st.put("buys", online.buy); online.items.forEach((x) => st.put("items", x));
  st.put("sales", { day: d(10, 20), item: show.items[1].id, book: "Business", qty: 1, plat: "eBay", price: 11000, shipIn: 0, fees: 1569, shipOut: 100, supplies: 50, other: 0 });
  st.put("costs", { day: d(10, 22), book: "Business", item: show.items[0].id, kind: "Grading", amount: 2499, note: "PSA grading fee" });
  st.put("items", { ...st.T.items.find((x) => x.id === show.items[0].id), status: "At grading", grader: "PSA" });
  st.put("costs", { day: d(9, 14), book: "Business", item: "", kind: "Show table", amount: 7500 });
  const PRICE = { [show.items[0].id]: 51000, [show.items[1].id]: 9800, [show.items[2].id]: 17500, [online.items[0].id]: 26500 };
  // a pretend Sheet in this page: newer change wins, like the real one
  const sheet = L.blank();
  const send = async (body) => { await new Promise((r) => setTimeout(r, 350)); for (const o of body.ops) { const rows = sheet[o.table], i = rows.findIndex((r) => r.id === o.row.id); if (i < 0) rows.push({ ...o.row }); else if ((o.row.upd || 0) >= (rows[i].upd || 0)) rows[i] = { ...o.row }; } return { ok: true, tables: JSON.parse(JSON.stringify(sheet)), sheet: "#" }; };
  let mounted;
  const sync = () => st.sync(send).then(() => mounted && mounted.redraw());
  const PICKS = [{ id: 0, g: 0, n: "Sample card D (picked from Search)", t: "c" }, { id: 0, g: 0, n: "Sample ETB (picked from Search)", t: "s" }];
  let pi = 0;
  mounted = L.mount($("#m-body"), { store: st, defBook: "Business",
    h: { money, signed, esc, img: () => "", cleanN: (s) => s, localDay, fmtDay, cents, dollars, toast, cls, pct: (x) => x },
    priceOf: (x) => PRICE[x.id] ?? null, conn: () => ({ url: "preview", token: "x" }), sync: () => { setTimeout(sync, 600); return Promise.resolve(); },
    feeEst: (k, p) => { if (!p) return 0; const v = Math.round(p * 1.075); return Math.round(v * (k === "tcgplayer" ? .1075 : k === "whatnot" ? .109 : .1325) + 40); },
    shipEst: (p, t) => t === "s" ? (p >= 10000 ? 1500 : 800) : (p >= 5000 ? 500 : 100), supplies: (t) => t === "s" ? 150 : 50,
    pick: (f) => { const c = PICKS[pi++ % PICKS.length]; f.lines.push({ ...L.lineFromCard({ ...c, price: c.t === "s" ? 5499 : 2500 }), tcg: "" }); toast("In Edge this opens Search; the preview adds a sample item"); mounted.open("buy", f); },
    oldInv: () => [], clearOldInv: () => {}, openCard: () => toast("In Edge this opens the card"),
    download: (name, text) => { $("#csv").hidden = false; $("#csv h3").textContent = name; $("#csv pre").textContent = text; $("#csv").scrollIntoView({ block: "start" }); } });
  $("#csv button").onclick = () => { $("#csv").hidden = true; };
  sync();
})();`;
const html = `<!doctype html><html lang="en" data-theme="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DYS Edge Ledger preview (sample data)</title>
<style>${css}
.pv-note{margin:0 0 12px;padding:10px 12px;border-radius:12px;background:color-mix(in srgb,var(--warn) 14%,transparent);color:var(--warn);font-size:13px;line-height:1.4}
#csv{margin-top:14px}#csv pre{white-space:pre-wrap;word-break:break-all;font-size:11px;max-height:50vh;overflow:auto;background:var(--surface-2);padding:8px;border-radius:8px}
body{padding-bottom:40px}</style></head><body>
<header class="bar"><div class="bar-in"><div class="brand"><span class="mark" aria-hidden="true">E</span><span>DYS Edge</span></div><span class="asof">Ledger preview</span></div></header>
<main class="view"><p class="pv-note"><b>Sample data, not real.</b> This is the new Mine → Ledger on made-up numbers. Try + Buy, Sell, an item's Send to grading, Activity and Export. A pretend Sheet in this page stands in for your Google Sheet; nothing is sent anywhere.</p>
<div id="m-body"></div><section id="csv" class="panel" hidden><div class="sec-head"><h3 style="margin:0;font-size:13px"></h3><button type="button" class="more">Close</button></div><pre></pre></section></main>
<div id="toast" class="toast" role="status" aria-live="polite" hidden></div>
<script>${js}</script><script>${harness}</script></body></html>`;
fs.writeFileSync(process.argv[2], html);
console.log(`wrote ${process.argv[2]} (${html.length} bytes)`);
