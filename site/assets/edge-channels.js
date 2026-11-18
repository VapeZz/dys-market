"use strict";
/* DYS Edge: where to sell? Profit compared across selling options (loaded by edge.js; owner only).

   For one card (a deal being checked, or a graded card the owner holds) it estimates, per selling option, what a sale
   leaves after that option's costs, the profit against the cost, ROI, the break-even price and the price for the profit
   target. Everything is an ESTIMATE: realized profit is only what the owner records in Ledger → Sell.
   The starting price is the eBay sold median (PkmnPrices, already loaded by the Deal check or the PSA check; no extra
   calls). Local buyers are not assumed to pay eBay prices: local options start at a share of it, labeled and editable.

   Sales tax is kept apart: tax the owner collects from a local buyer is passed on to the state, so it is neither revenue
   nor profit. It only matters through a payment fee charged on the whole amount the buyer pays (price + tax).

   Fee and policy defaults were read from each company's own pages on Nov 17, 2026 (POLICY below). Every number is
   editable. Money in cents. Market data and estimates, not financial or tax advice. */
(() => {
  const VERSION = 1, CHECKED = "Nov 17, 2026";

  // payment methods for in-person sales (official fee pages, checked Nov 17, 2026)
  const PAY = {
    cash: { label: "Cash", pct: 0, flat: 0, note: "No fee." },
    venmo: { label: "Venmo, goods & services (personal)", pct: 2.99, flat: 0, note: "Venmo: 2.99% when the buyer marks the payment as goods and services (venmo.com fees page)." },
    venmobiz: { label: "Venmo business profile", pct: 1.9, flat: 10, note: "Venmo: 1.9% + $0.10 on business profile payments (venmo.com)." },
    paypal: { label: "PayPal goods & services", pct: 2.99, flat: 0, note: "PayPal: 2.99% to send or receive money for goods and services (paypal.com fees page)." },
    card: { label: "Card reader (Square tap, dip or swipe)", pct: 2.6, flat: 15, note: "Square: 2.6% + 15¢ per in-person card payment (squareup.com)." },
    custom: { label: "Other (type the fee)", pct: 0, flat: 0, note: "Type your payment fee." } };

  const POLICY = {
    fb: "Facebook charges no selling fee on local pickup. Its 10% selling fee (minimum $0.80) applies only to shipped checkout orders (Marketplace Seller Protection Policy).",
    offerup: "OfferUp has been local-only since October 2025 and takes no fee or commission on in-person sales (OfferUp Help Center).",
    show: "No platform fee. A booth fee, if you have one, is split over the number of sales you expect at the show.",
    ebay: "eBay trading cards: 13.25% of the total including the buyer's sales tax up to $7,500, 2.35% above, plus $0.40 an order over $10.",
    vinted: "Vinted charges sellers no selling fee. The buyer pays a Vinted fee (usually 5% + $0.70) and the shipping label on top of your price, so buyers may offer less (Vinted Help Center)." };

  // the five options; local ones start at a share of the eBay sold median (Keo's choice, Nov 17: 90%; Vinted 85%)
  const CHANNELS = [
    { k: "fb", name: "Facebook Marketplace", how: "local pickup", local: true, pricePct: 90, feePct: 0, feeFlat: 0, pay: "cash", ship: 0, sup: 0, travel: 0, booth: 0, boothSales: 10, taxPct: 0 },
    { k: "offerup", name: "OfferUp", how: "local pickup", local: true, pricePct: 90, feePct: 0, feeFlat: 0, pay: "cash", ship: 0, sup: 0, travel: 0, booth: 0, boothSales: 10, taxPct: 0 },
    { k: "show", name: "Card show / cash sale", how: "in person", local: true, show: true, pricePct: 90, feePct: 0, feeFlat: 0, pay: "cash", ship: 0, sup: 0, travel: 0, booth: 0, boothSales: 10, taxPct: 0 },
    { k: "ebay", name: "eBay", how: "shipped", pricePct: 100, tiered: true, feePct: 13.25, topPct: 2.35, topFrom: 750000, feeFlat: 40, buyerTax: 7.5, ship: null, sup: 50, travel: 0, booth: 0, boothSales: 10 },
    { k: "vinted", name: "Vinted", how: "shipped, buyer pays the label", pricePct: 85, feePct: 0, feeFlat: 0, ship: 0, sup: 50, travel: 0, booth: 0, boothSales: 10 } ];
  const EDIT = ["pricePct", "feePct", "feeFlat", "buyerTax", "pay", "payPct", "payFlat", "ship", "sup", "travel", "booth", "boothSales", "taxPct"];

  const money = (c) => c == null || !isFinite(c) ? "—" : `${c < 0 ? "−" : ""}$${(Math.abs(c) / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const signed = (c) => c == null || !isFinite(c) ? "—" : (c >= 0 ? "+" : "") + money(c);
  const pct = (x) => x == null || !isFinite(x) ? "—" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toFixed(0)}%`;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);

  /* ---------- one option's costs at a price ---------- */
  // a channel with its saved and session edits applied; payment fee defaults to the chosen method's
  function setup(base, saved = {}) {
    const ch = { ...base, ...saved };
    const p = PAY[ch.pay] || null;
    if (ch.local) { if (ch.payPct == null) ch.payPct = p ? p.pct : 0; if (ch.payFlat == null) ch.payFlat = p ? p.flat : 0; }
    else { ch.payPct = 0; ch.payFlat = 0; ch.taxPct = 0; }   // eBay and Vinted take payment inside their own fee
    return ch;
  }
  function platformFee(ch, price) {
    if (!price) return 0;
    if (ch.tiered) {   // eBay: percent of the total including the buyer's sales tax, a lower percent above topFrom, plus the per-order fee
      const b = Math.round(price * (1 + (ch.buyerTax || 0) / 100)), top = ch.topFrom ?? Infinity;
      return Math.round((ch.feeFlat || 0) + Math.min(b, top) * (ch.feePct || 0) / 100 + Math.max(0, b - top) * (ch.topPct || 0) / 100);
    }
    return Math.round(price * (ch.feePct || 0) / 100) + (ch.feeFlat || 0);
  }
  function costsAt(ch, price, ctx = {}) {
    const tax = ch.local && price ? Math.round(price * (ch.taxPct || 0) / 100) : 0;   // collected and passed on; not revenue
    const fee = platformFee(ch, price);
    const pay = price && (ch.payPct || ch.payFlat) ? Math.round((price + tax) * (ch.payPct || 0) / 100) + (ch.payFlat || 0) : 0;
    const ship = ch.ship == null ? (ctx.shipAuto ? ctx.shipAuto(price) : 0) : ch.ship;
    const booth = ch.booth ? Math.round(ch.booth / Math.max(1, ch.boothSales || 1)) : 0;
    const out = { price, tax, fee, pay, ship, sup: ch.sup || 0, travel: ch.travel || 0, booth };
    out.costs = fee + pay + ship + out.sup + out.travel + booth;
    out.net = price - out.costs;
    return out;
  }
  const netAt = (ch, p, ctx) => costsAt(ch, p, ctx).net;
  // the lowest price whose net clears `ok`. Net rises with price except where automatic shipping steps up, so the search
  // runs inside each shipping band (ctx.breaks) and takes the lowest answer
  function lowestPrice(ch, ok, ctx = {}) {
    const breaks = ch.ship == null ? (ctx.breaks || []) : [];
    const bands = [0, ...breaks].map((lo, i, a) => [lo, i + 1 < a.length ? a[i + 1] - 1 : null]);
    for (const [lo, hiCap] of bands) {
      let hi = hiCap;
      if (hi == null) { hi = Math.max(lo, 100); while (!ok(netAt(ch, hi, ctx))) { hi *= 2; if (hi > 1e10) return null; } }
      else if (!ok(netAt(ch, hi, ctx))) continue;
      if (ok(netAt(ch, lo, ctx))) return lo;
      let a = lo, b = hi;
      while (b - a > 1) { const m = Math.floor((a + b) / 2); if (ok(netAt(ch, m, ctx))) b = m; else a = m; }
      return b;
    }
    return null;
  }

  /* ---------- may this card be listed there? (Vinted's own rules, checked Nov 17, 2026) ---------- */
  function eligibility(k, item = {}) {
    if (k !== "vinted") return { ok: true, text: "" };
    if (item.kind === "graded") return { ok: false, verify: true, text: "Check first: Vinted's Catalog Rules ban graded cards without authenticity certificates. Confirm your slab's certification counts before listing." };
    if (item.kind === "sealed") return /booster (pack|box)|booster bundle|\bbooster\b/i.test(item.name || "")
      ? { ok: true, text: "Allowed: Vinted lists booster packs and boxes under Trading cards." }
      : { ok: false, verify: true, text: "Check first: Vinted lists booster packs and boxes; confirm this product fits a Trading cards category." };
    return { ok: true, text: "Allowed: Vinted lists single trading cards under Trading cards." };
  }

  /* ---------- the comparison ---------- */
  // o: { cost, ref (eBay sold reference, cents or null), item: { kind, name }, saved: { fb: {...} }, prices: { fb: cents } (this card only),
  //      ebay: { feePct, feeFlat, buyerTax, ship, sup } (from the panel above it, if any), roi, minProfit, shipAuto, breaks }
  function compare(o) {
    const ctx = { shipAuto: o.shipAuto, breaks: o.breaks || [5000] }, roi = o.roi ?? 20, minProfit = o.minProfit ?? 500, cost = o.cost || 0;
    const rows = CHANNELS.map((b) => {
      const ch = setup(b.k === "ebay" && o.ebay ? { ...b, ...o.ebay } : b, (o.saved || {})[b.k]);
      const typed = o.prices && o.prices[b.k] != null, price = typed ? o.prices[b.k] : o.ref != null ? Math.round(o.ref * (ch.pricePct ?? 100) / 100) : null;
      const at = price != null ? costsAt(ch, price, ctx) : null;
      const profit = at ? at.net - cost : null;
      const elig = eligibility(b.k, o.item);
      return { k: b.k, ch, typed, price, at, profit, roi: profit != null && cost > 0 ? profit / cost * 100 : null, elig,
        clears: profit != null && profit >= minProfit && profit * 100 >= cost * roi,
        breakEven: lowestPrice(ch, (n) => n >= cost, ctx),
        target: lowestPrice(ch, (n) => n - cost >= minProfit && (n - cost) * 100 >= cost * roi, ctx) };
    });
    const eb = rows.find((r) => r.k === "ebay");
    for (const r of rows) r.matchEbay = r.k !== "ebay" && eb.at ? lowestPrice(r.ch, (n) => n >= eb.at.net, ctx) : null;
    const ranked = rows.filter((r) => r.profit != null && r.elig.ok).sort((a, b) => b.profit - a.profit);
    return { rows, best: ranked.length ? ranked[0].k : null, cost, ref: o.ref, roi, minProfit };
  }

  /* ---------- the panel ---------- */
  const d$ = (c) => c == null ? "" : (c / 100).toFixed(2);
  function rowHtml(r, res, open) {
    const c = r.ch, at = r.at, best = res.best === r.k;
    const status = r.profit == null ? "" : r.clears ? `<span class="chip good">Clears ${res.roi}%</span>` : r.profit >= 0 ? `<span class="chip">Under ${res.roi}%</span>` : `<span class="chip bad">Loss</span>`;
    const field = (k, label, v, step = "0.01") => `<label class="f">${label}<input class="field ch-in" data-f="${k}" type="number" inputmode="decimal" min="0" step="${step}" value="${v}"></label>`;
    const lines = at ? [
      at.fee ? `<div><span>${c.tiered ? `Platform fee (${c.feePct}% on price + ${c.buyerTax || 0}% buyer tax, + ${money(c.feeFlat)})` : "Platform fee"}</span><span>−${money(at.fee)}</span></div>` : "",
      at.pay ? `<div><span>Payment fee (${esc((PAY[c.pay] || PAY.custom).label)})</span><span>−${money(at.pay)}</span></div>` : "",
      at.ship ? `<div><span>Shipping out</span><span>−${money(at.ship)}</span></div>` : "",
      at.sup ? `<div><span>Supplies</span><span>−${money(at.sup)}</span></div>` : "",
      at.travel ? `<div><span>Travel</span><span>−${money(at.travel)}</span></div>` : "",
      at.booth ? `<div><span>Booth share (${money(c.booth)} ÷ ${c.boothSales} sales)</span><span>−${money(at.booth)}</span></div>` : "",
      `<div><span>You'd keep</span><span>${money(at.net)}</span></div>`,
      `<div><span>Your cost</span><span>−${money(res.cost)}</span></div>`,
      `<div><span><b>Estimated profit</b></span><span><b class="${r.profit > 0 ? "up" : r.profit < 0 ? "down" : ""}">${signed(r.profit)}</b> <small>${pct(r.roi)}</small></span></div>`,
      at.tax ? `<div><span>Sales tax the buyer pays you (passed on, not profit)</span><span>${money(at.tax)}</span></div>` : ""].join("") : "";
    return `<div class="ch-row${best ? " ch-best" : ""}" data-k="${r.k}">
      <div class="ch-top"><b>${esc(c.name)}</b><small>${esc(c.how)}</small>${best ? `<span class="chip good">Best estimate</span>` : ""}${r.elig.verify ? `<span class="chip hot">Check rules</span>` : ""}</div>
      ${r.elig.text ? `<p class="small ${r.elig.verify ? "ch-warn" : "muted"}">${esc(r.elig.text)}</p>` : ""}
      <div class="ch-nums"><span><small>Price${r.typed ? "" : " (est.)"}</small><b>${money(r.price)}</b></span><span><small>You'd keep</small><b>${at ? money(at.net) : "—"}</b></span>
        <span><small>Est. profit</small><b class="${r.profit > 0 ? "up" : r.profit < 0 ? "down" : ""}">${signed(r.profit)}</b></span></div>
      <div class="ch-sub">${status}<span>Break-even ${money(r.breakEven)}</span><span>${res.roi}% profit at ${money(r.target)}</span>${r.matchEbay != null ? `<span>Matches eBay at ${money(r.matchEbay)}</span>` : ""}</div>
      <details class="dl-more ch-edit"${open ? " open" : ""}><summary>Price and costs (edit)</summary>
        ${at ? `<div class="kv">${lines}</div>` : `<p class="dl-note">Type an expected price to see this option.</p>`}
        <form class="form" onsubmit="return false">
          ${field("price", "Expected price $", d$(r.price))}${field("pricePct", "Start at % of eBay sold", c.pricePct, "1")}
          ${c.tiered ? field("feePct", "Fee %", c.feePct) + field("feeFlat", "Per-order fee $", d$(c.feeFlat)) + field("buyerTax", "Buyer sales tax % (fee base)", c.buyerTax, "0.1")
            : field("feePct", "Platform fee %", c.feePct) + field("feeFlat", "Platform fee $", d$(c.feeFlat))}
          ${c.local ? `<label class="f">Paid by<select class="select ch-pay">${Object.entries(PAY).map(([k, p]) => `<option value="${k}"${k === c.pay ? " selected" : ""}>${esc(p.label)}</option>`).join("")}</select></label>
            ${field("payPct", "Payment fee %", c.payPct)}${field("payFlat", "Payment fee $", d$(c.payFlat))}${field("taxPct", "Sales tax you collect %", c.taxPct, "0.1")}` : ""}
          ${c.local ? "" : field("ship", c.k === "ebay" ? "Shipping out $ (blank = Settings)" : "Shipping out $", d$(c.ship))}
          ${field("sup", "Supplies $", d$(c.sup))}${field("travel", "Travel $", d$(c.travel))}
          ${c.show ? field("booth", "Booth fee $", d$(c.booth)) + field("boothSales", "Sales expected at the show", c.boothSales, "1") : ""}</form>
        <p class="small muted">${esc(POLICY[c.k])} ${c.local && PAY[c.pay] ? esc(PAY[c.pay].note) : ""} Checked ${CHECKED}.${c.local ? " Sales tax you collect is passed on to the state: it isn't counted as revenue or profit (not tax advice)." : ""}</p>
      </details></div>`;
  }
  function html(res, state = {}) {
    const ref = res.ref != null ? `${money(res.ref)} (${esc(state.refLabel || "eBay sold median")})` : null;
    return `<div class="dl-head"><span class="lab">Where to sell? · estimates</span></div>
      <p class="dl-note">${ref ? `Starting point: the eBay sold price ${ref}. Local buyers often pay less than eBay buyers, so local options start at a lower, editable price.` : "No sold price is loaded, so there is no starting price. Type an expected price for an option to compare."} Your cost: <b>${money(res.cost)}</b>.</p>
      <div class="ch-list">${res.rows.map((r) => rowHtml(r, res, state.open && state.open[r.k])).join("")}</div>
      ${state.note ? `<p class="dl-note">${esc(state.note)}</p>` : ""}
      <div class="btns"><button type="button" class="btn sm ch-save">Save costs as my defaults</button><button type="button" class="btn sm ghost ch-reset">Use Edge's defaults</button></div>
      <p class="dl-foot"><b>Estimated profit</b> is what a sale at that price would leave after the costs shown, minus your cost. <b>Break-even</b> is the lowest price that gets your cost back. <b>Realized profit</b> is only what you record in Ledger → Sell after a real sale. Prices change and local buyers negotiate. Not financial or tax advice.</p>`;
  }

  /* opts: compare()'s inputs plus { refLabel, save(saved | null), base } → { update(partial), result } */
  function mount(root, opts) {
    let o = { ...opts, saved: JSON.parse(JSON.stringify(opts.saved || {})), prices: {} }, last = null;
    const state = { open: {}, note: "", refLabel: opts.refLabel };
    const draw = () => {
      for (const d of root.querySelectorAll(".ch-row")) { const det = d.querySelector(".ch-edit"); if (det) state.open[d.dataset.k] = det.open; }
      const res = compare(o); last = res;
      root.classList.add("dl", "ch"); root.innerHTML = html(res, state);
      for (const row of root.querySelectorAll(".ch-row")) {
        const k = row.dataset.k, s = (o.saved[k] ||= {});
        for (const inp of row.querySelectorAll(".ch-in")) inp.onchange = () => {
          const f = inp.dataset.f, v = inp.value.trim(), x = v === "" ? null : Math.max(0, parseFloat(v) || 0);
          const cents = ["price", "feeFlat", "payFlat", "ship", "sup", "travel", "booth"].includes(f);
          if (f === "price") { if (x == null) delete o.prices[k]; else o.prices[k] = Math.round(x * 100); }
          else if (f === "boothSales") s.boothSales = Math.max(1, Math.round(x || 1));
          else if (f === "ship" && k === "ebay" && x == null) s.ship = null;
          else s[f] = x == null ? 0 : cents ? Math.round(x * 100) : x;
          if (f === "pricePct") delete o.prices[k];
          state.open[k] = true; state.note = ""; draw();
        };
        const sel = row.querySelector(".ch-pay");
        if (sel) sel.onchange = () => { const p = PAY[sel.value]; s.pay = sel.value; s.payPct = p.pct; s.payFlat = p.flat; state.open[k] = true; draw(); };
      }
      root.querySelector(".ch-save").onclick = () => { const keep = {}; for (const [k, v] of Object.entries(o.saved)) if (Object.keys(v).length) keep[k] = { ...v }; o.save && o.save(keep); state.note = "Saved as your defaults for these options (prices you typed stay with this card only)."; draw(); };
      root.querySelector(".ch-reset").onclick = () => { o.saved = {}; o.prices = {}; o.save && o.save(null); state.note = "Back to Edge's defaults."; draw(); };
      return res;
    };
    draw();
    return { update(p) { o = { ...o, ...p }; if (p.refLabel) state.refLabel = p.refLabel; return draw(); }, get result() { return last; } };
  }

  const api = { v: VERSION, CHANNELS, PAY, POLICY, CHECKED, setup, platformFee, costsAt, netAt, lowestPrice, eligibility, compare, html, mount };
  if (typeof window !== "undefined") window.EdgeChannels = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
