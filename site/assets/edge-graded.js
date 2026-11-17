"use strict";
/* DYS Edge: graded-card sold-price check (loaded by edge.js; owner only).

   For one graded card the owner holds (one grader and grade, e.g. PSA 10), from that exact grade's eBay sold prices:
   recent sales, volume, median, the middle half, what happened lately (a description, not a forecast), what a sale
   at the typical price leaves after selling costs, profit or loss against what the owner paid, the break-even price
   and the price for the profit target. One of three calls:
     SELL candidate     a sale at the typical price clears the profit target (ROI and minimum profit)
     HOLD               it doesn't: selling now at the typical price misses the target (not a prediction)
     INSUFFICIENT DATA  too few, too old or too scattered sales of this exact grade to give a typical price
   Only sales of the exact grader and grade are used: raw and other grades never enter (edge-pkmn.js lookupGrade).

   Input: data { asOf, label ("PSA 10"), comps: [[day, cents, label, exact]], capped, oldestRead }
          holding { cost (cents each, all-in), label }
          sell { feePct, topPct, topFrom (cents), perOrder (cents), buyerTax (percent the marketplace adds and charges
                 its fee on), ship (cents, or null for shipAuto(price)), supplies (cents), shipAuto(price) }
          opts { today, roi (percent), minProfit (cents) }
   Money in cents; days counted from 1970-01-01 UTC. Market data, not financial advice. */
(() => {
  const VERSION = 1, DAY = 864e5;
  const MIN_90 = 5;        // sales of this exact grade in 90 days
  const MIN_30 = 3;        // of those, in the last 30 days
  const MAX_SALE_AGE = 21; // days since the newest sale (the feed runs about 6–8 days behind)
  const MAX_SPREAD = 35;   // percent: half the middle-half range over the median, above it prices are too scattered
  const TREND_MIN = 3;     // sales in each half before a "lately" comparison is made
  const TREND_STEP = 10;   // percent change that counts as higher or lower lately

  const median = (xs) => { if (!xs.length) return null; const s = [...xs].sort((a, b) => a - b), m = s.length >> 1; return s.length % 2 ? s[m] : Math.round((s[m - 1] + s[m]) / 2); };
  const rank = (xs, q) => { if (!xs.length) return null; const s = [...xs].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.max(0, Math.ceil(q * s.length) - 1))]; };
  const money = (c) => c == null || !isFinite(c) ? "—" : `${c < 0 ? "−" : ""}$${(Math.abs(c) / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const signed = (c) => c == null || !isFinite(c) ? "—" : (c >= 0 ? "+" : "") + money(c);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
  const pct = (x, d = 0) => x == null || !isFinite(x) ? "—" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toFixed(d)}%`;
  const fmtDay = (d) => new Date(d * DAY).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

  /* ---------- selling costs ---------- */
  // the marketplace fee: percent up to topFrom, topPct above it, plus the per-order fee; charged on price plus buyer tax
  function fee(sell, price) {
    if (!price) return 0;
    const base = Math.round(price * (1 + (sell.buyerTax || 0) / 100)), top = sell.topFrom ?? Infinity;
    const f = (sell.perOrder || 0) + Math.min(base, top) * (sell.feePct || 0) / 100 + Math.max(0, base - top) * (sell.topPct || 0) / 100;
    return Math.round(f);
  }
  const shipFor = (sell, price) => sell.ship != null ? sell.ship : sell.shipAuto ? sell.shipAuto(price) : 0;
  const costsAt = (sell, price) => { const f = fee(sell, price), s = shipFor(sell, price), u = sell.supplies || 0; return { fee: f, ship: s, supplies: u, net: price - f - s - u }; };
  const netAt = (sell, price) => costsAt(sell, price).net;
  // the lowest price whose net clears `ok`. Net rises with price except where automatic shipping steps up, so the search
  // runs inside each shipping band (sell.breaks: the prices where it steps) and takes the lowest answer
  function lowestPrice(sell, ok) {
    const breaks = sell.ship != null ? [] : (sell.breaks || []);
    const bands = [0, ...breaks].map((lo, i, a) => [lo, i + 1 < a.length ? a[i + 1] - 1 : null]);
    for (const [lo, hiCap] of bands) {
      let hi = hiCap;
      if (hi == null) { hi = Math.max(lo, 100); while (!ok(netAt(sell, hi), hi)) { hi *= 2; if (hi > 1e10) return null; } }
      else if (!ok(netAt(sell, hi), hi)) continue;
      if (ok(netAt(sell, lo), lo)) return lo;
      let a = lo, b = hi;   // ok(b), !ok(a)
      while (b - a > 1) { const m = Math.floor((a + b) / 2); if (ok(netAt(sell, m), m)) b = m; else a = m; }
      return b;
    }
    return null;
  }

  /* ---------- the evidence ---------- */
  function stats(data, label, day) {
    const all = (data.comps || []).filter((c) => c[2] === label && c[3] && c[0] <= day && c[0] > day - 90).sort((a, b) => b[0] - a[0]);
    const inDays = (n) => all.filter((c) => c[0] > day - n).map((c) => c[1]);
    const p14 = inDays(14), p30 = inDays(30), p90 = all.map((c) => c[1]);
    const capped = !!(data.capped && data.capped.includes(label));
    // when more sales exist than were read, only windows that start on or after the oldest day read are complete
    const from = capped && data.oldestRead != null ? data.oldestRead : null;
    const complete = (n) => from == null || day - n + 1 >= from;
    const newest = all.length ? all[0][0] : null;
    const s = { label, n14: p14.length, n30: p30.length, n90: p90.length, m14: median(p14), m30: median(p30), m90: median(p90),
      q1: rank(p30, 0.25), q3: rank(p30, 0.75), lo: p30.length ? Math.min(...p30) : null, hi: p30.length ? Math.max(...p30) : null,
      newest, saleAge: newest == null ? null : day - newest, capped, from, full30: complete(30), full90: complete(90),
      inexact: (data.comps || []).filter((c) => c[2] === label && !c[3] && c[0] > day - 90).length,
      recent: all.slice(0, 12).map((c) => [c[0], c[1]]) };
    s.spread = s.m30 ? Math.round((s.q3 - s.q1) / 2 / s.m30 * 10000) / 100 : null;
    // lately: sales in the last 14 days against the 16 days before them (both inside the 30-day window)
    const a = p14, b = all.filter((c) => c[0] <= day - 14 && c[0] > day - 30).map((c) => c[1]);
    const ma = median(a), mb = median(b);
    s.trend = a.length >= TREND_MIN && b.length >= TREND_MIN && complete(30) ? { now: ma, before: mb, nNow: a.length, nBefore: b.length, change: Math.round((ma / mb - 1) * 10000) / 100 } : null;
    if (s.trend) s.trend.word = s.trend.change <= -TREND_STEP ? "lower" : s.trend.change >= TREND_STEP ? "higher" : "steady";
    // weekly medians, newest week first (7-day blocks back from today)
    s.weeks = [0, 1, 2, 3].map((w) => { const xs = all.filter((c) => c[0] > day - 7 * (w + 1) && c[0] <= day - 7 * w).map((c) => c[1]); return { w, n: xs.length, m: median(xs), full: complete(7 * (w + 1)) }; });
    return s;
  }

  /* ---------- the call ---------- */
  function evaluate(data, holding, sell, opts) {
    const day = opts.today ?? Math.floor(Date.now() / DAY), roi = opts.roi ?? 20, minProfit = opts.minProfit ?? 500;
    const label = (data && data.label) || holding.label;
    const out = { v: VERSION, verdict: "insufficient", label, reasons: [], s: null, typical: null, basis: "", at: null, profit: null, roi: null, breakEven: null, target: null, cost: holding.cost || 0, roiTarget: roi, minProfit };
    // what the owner needs to sell for: these depend only on cost and selling costs, so they show even without sales
    const cost = out.cost;
    out.breakEven = lowestPrice(sell, (n) => n >= cost);
    out.target = lowestPrice(sell, (n) => n - cost >= minProfit && (n - cost) * 100 >= cost * roi);
    if (!data || !(data.comps || []).length) { out.reasons.push({ code: "none", text: `No ${label} sales of this exact card were found in the last 90 days.` }); return out; }
    const s = out.s = stats(data, label, day);
    if (s.n90 < MIN_90) out.reasons.push({ code: "evidence", text: `Only ${s.n90} ${label} sale${s.n90 === 1 ? "" : "s"} of this exact card in 90 days (Edge needs ${MIN_90} to trust a typical price).` });
    if (s.n30 < MIN_30) out.reasons.push({ code: "liquidity", text: `Only ${s.n30} sold in the last 30 days (Edge needs ${MIN_30}): there's no reliable recent price.` });
    if (s.saleAge == null || s.saleAge > MAX_SALE_AGE) out.reasons.push({ code: "fresh", text: s.saleAge == null ? "No dated sale to work from." : `The newest sale on record is ${s.saleAge} days old (Edge needs one within ${MAX_SALE_AGE} days).` });
    if (s.spread != null && s.spread > MAX_SPREAD) out.reasons.push({ code: "spread", text: `Recent prices are too scattered to name one typical price (the middle half runs ${money(s.q1)} to ${money(s.q3)}).` });
    // the typical price: the median of the last 30 days (or of the newest sales read, when more exist than were read)
    if (s.m30 != null) { out.typical = s.m30; out.basis = s.full30 ? `the median of ${s.n30} sales in the last 30 days` : `the median of the newest ${s.n30} sales (${day - s.from + 1} days; more exist than were read)`; }
    if (out.typical != null) {
      const c = costsAt(sell, out.typical);
      out.at = c; out.profit = c.net - cost; out.roi = cost > 0 ? out.profit / cost * 100 : null;
    }
    if (out.reasons.length) return out;
    const clears = out.profit >= minProfit && out.profit * 100 >= cost * roi;
    out.verdict = clears ? "sell" : "hold";
    return out;
  }

  /* ---------- plain words ---------- */
  const NAME = { sell: "SELL candidate", hold: "HOLD", insufficient: "INSUFFICIENT DATA" };
  function explain(r) {
    const L = r.label;
    if (r.verdict === "insufficient") {
      const why = r.reasons.map((x) => x.text).join(" ");
      return `${why} Edge won't guess a value from raw prices or other grades. ${r.breakEven ? `For reference: with your costs, a sale has to reach ${money(r.breakEven)} to break even.` : ""}`.trim();
    }
    const at = `At the typical ${L} sold price of ${money(r.typical)} you'd keep ${money(r.at.net)} after fees, shipping and supplies`;
    if (r.verdict === "sell") return `${at}: ${signed(r.profit)} (${pct(r.roi)}) over the ${money(r.cost)} you paid, which clears your ${r.roiTarget}% target. Recent sales support listing near ${money(r.typical)}. Check live listings before you price it.`;
    return `${at}: ${r.profit < 0 ? `${money(-r.profit)} less than` : `${signed(r.profit)} over`} the ${money(r.cost)} you paid${r.profit >= 0 ? `, under your ${r.roiTarget}% target` : ""}. To break even a sale has to reach ${money(r.breakEven)}; for ${r.roiTarget}% profit, ${money(r.target)}. HOLD means selling now doesn't reach your target. It is not a prediction that the price will rise.`;
  }
  function trendText(s) {
    if (!s.trend) return s.n30 ? "Not enough sales in each half of the last 30 days to compare." : "";
    const t = s.trend;
    return `Last 14 days: median ${money(t.now)} (${t.nNow} sales) vs ${money(t.before)} (${t.nBefore} sales) in the 16 days before, ${t.word === "steady" ? `about the same (${pct(t.change)})` : `${pct(t.change)}, ${t.word} lately`}. This describes sales that already happened, not what comes next.`;
  }
  // the short line for "Sell, grade or keep?"
  function line(r) {
    if (r.verdict === "insufficient") return `${r.label}: not enough sales to value it. ${r.reasons[0] ? r.reasons[0].text : ""}`;
    return `${r.label} typical ${money(r.typical)}: you'd keep ${money(r.at.net)}, ${signed(r.profit)} vs what you paid${r.verdict === "hold" ? `. Break-even ${money(r.breakEven)}` : ""}.`;
  }

  /* ---------- the panel ---------- */
  const ageTxt = (n) => n == null ? "—" : n <= 0 ? "today" : n === 1 ? "yesterday" : `${n} days ago`;
  const plus = (s, full) => s.capped && !full ? "+" : "";
  function html(r, sell, state = {}) {
    const s = r.s, cls = { sell: "dl-buy", hold: "dl-hold", insufficient: "dl-warn" }[r.verdict];
    const tile = (lab, val, sub, c = "") => `<div class="tile"><span class="lab">${lab}</span><b class="${c}">${val}</b><small>${sub}</small></div>`;
    const st = state.status || "ready";
    const field = (k, label, v, step, unit) => `<label class="f">${label}${unit === "$" ? " $" : ""}<input class="field gs-${k}" type="number" inputmode="decimal" min="0" step="${step}" value="${v}"></label>`;
    const noData = !s;
    return `<div class="dl-head"><span class="lab">Sold prices · ${esc(r.label)} · this exact card</span><span class="dl-beta">${st === "loading" ? "Getting sold prices…" : state.readAt != null ? `Read ${esc(state.readAt)}` : ""}</span></div>
      <div class="dl-call ${cls}"><b>${NAME[r.verdict]}</b><span>${r.verdict === "sell" ? "Selling at the typical price clears your target" : r.verdict === "hold" ? "Selling now misses your target" : "Not enough reliable sales"}</span></div>
      <p class="dl-sum">${esc(explain(r))}</p>
      <div class="prices dl-tiles">${tile("Typical sold price", r.typical != null ? money(r.typical) : "—", s ? `${s.n30}${plus(s, s.full30)} sold in 30 days` : "no sales")}
        ${tile("You'd keep", r.at ? money(r.at.net) : "—", r.at ? "after selling costs" : "needs sales")}
        ${tile("Profit vs paid", r.profit != null ? signed(r.profit) : "—", r.profit != null ? `${pct(r.roi)} on ${money(r.cost)}` : `paid ${money(r.cost)}`, r.profit > 0 ? "up" : r.profit < 0 ? "down" : "")}</div>
      <div class="kv"><div><span>Break-even sale price</span><span><b>${money(r.breakEven)}</b></span></div>
        <div><span>Sale price for ${r.roiTarget}% profit</span><span><b>${money(r.target)}</b></span></div></div>
      ${state.note ? `<p class="dl-note">${esc(state.note)}</p>` : ""}
      ${state.canLoad ? `<div class="btns"><button type="button" class="btn sm gs-load"${st === "loading" ? " disabled" : ""}>${s ? "Refresh sold prices" : "Get sold prices"}</button></div>` : ""}
      ${noData ? "" : `<span class="lab">Sales of ${esc(r.label)} only</span>
      <div class="kv"><div><span>Sold, last 14 / 30 / 90 days</span><span>${s.n14} / ${s.n30}${plus(s, s.full30)} / ${s.n90}${plus(s, s.full90)}</span></div>
        <div><span>Median, last 14 days</span><span>${money(s.m14)}</span></div>
        <div><span>Median, last 30 days (typical price)</span><span>${money(s.m30)}</span></div>
        ${s.full90 ? `<div><span>Median, last 90 days</span><span>${money(s.m90)}</span></div>` : ""}
        <div><span>Middle half of the last 30 days</span><span>${s.q1 != null ? `${money(s.q1)} – ${money(s.q3)}` : "—"}</span></div>
        <div><span>Lowest – highest, last 30 days</span><span>${s.lo != null ? `${money(s.lo)} – ${money(s.hi)}` : "—"}</span></div>
        <div><span>Newest sale</span><span>${ageTxt(s.saleAge)}</span></div>
        ${s.inexact ? `<div><span>Sales shared with other printings (left out)</span><span>${s.inexact}</span></div>` : ""}</div>
      <span class="lab">Lately</span><p class="dl-note">${esc(trendText(s))}</p>
      <div class="kv">${s.weeks.map((w) => `<div><span>${w.w === 0 ? "Last 7 days" : `${7 * w.w + 1}–${7 * (w.w + 1)} days ago`}</span><span>${w.n ? `${money(w.m)} <small>(${w.n}${w.full ? "" : "+"} sold)</small>` : "no sales"}</span></div>`).join("")}</div>
      <details class="dl-more"${state.openSales ? " open" : ""} data-k="openSales"><summary>Newest ${s.recent.length} ${esc(r.label)} sales</summary>
        <div class="kv">${s.recent.map(([d, c]) => `<div><span>${fmtDay(d)}</span><span>${money(c)}</span></div>`).join("")}</div></details>`}
      ${r.at ? `<span class="lab">A sale at ${money(r.typical)}</span><div class="kv">
        <div><span>Marketplace fee (${sell.feePct}% on price + ${sell.buyerTax}% buyer tax, + ${money(sell.perOrder)})</span><span>−${money(r.at.fee)}</span></div>
        <div><span>Shipping out</span><span>−${money(r.at.ship)}</span></div><div><span>Supplies</span><span>−${money(r.at.supplies)}</span></div>
        <div><span>You'd keep</span><span>${money(r.at.net)}</span></div><div><span>What you paid (all-in)</span><span>−${money(r.cost)}</span></div>
        <div><span><b>Profit or loss</b></span><span><b class="${r.profit > 0 ? "up" : "down"}">${signed(r.profit)}</b></span></div></div>` : ""}
      <details class="dl-more gs-costs"${state.openCosts ? " open" : ""} data-k="openCosts"><summary>Selling costs (change them if yours differ)</summary>
        <form class="form" onsubmit="return false">${field("fee", "Fee %", sell.feePct, "0.01", "%")}${field("order", "Per-order fee", (sell.perOrder / 100).toFixed(2), "0.01", "$")}
          ${field("tax", "Buyer sales tax %", sell.buyerTax, "0.1", "%")}${field("ship", "Shipping out", sell.ship != null ? (sell.ship / 100).toFixed(2) : "", "0.01", "$")}
          ${field("sup", "Supplies", ((sell.supplies || 0) / 100).toFixed(2), "0.01", "$")}</form>
        <p class="small muted" style="margin:4px 0">Defaults: eBay trading cards (checked Nov 17, 2026): ${sell.feePct === 13.25 ? "13.25%" : "fee"} of the total including the buyer's sales tax, 2.35% on any part over $7,500, plus $0.40 an order (over $10). Shipping left blank uses your Settings (${sell.shipAuto ? `${money(sell.shipAuto(4999))} under $50, ${money(sell.shipAuto(5000))} at $50 and up` : "none"}). Promoted listings, if you use them, cost extra.</p>
        <div class="btns"><button type="button" class="btn sm gs-save">Save as my defaults</button><button type="button" class="btn sm ghost gs-reset">Use Edge's defaults</button></div></details>
      <p class="dl-foot">Only ${esc(r.label)} sales of this exact card count: raw and other grades are left out. Median = the middle sale price; half sold above it, half below. Source: ${esc(state.source || "PkmnPrices · eBay sold")}. Market data, not financial advice.</p>`;
  }

  /* opts: { holding, sell, base (Edge's default selling costs), today, roi, minProfit, load(fresh) → Promise<{ ok, data, note, readAt }>,
             save(sellOverrides) → void, data (already loaded) } */
  function mount(root, o) {
    const state = { status: o.data ? "ready" : "idle", canLoad: !!o.load, note: o.note || "", openCosts: false, openSales: false, readAt: o.readAt ?? null, source: o.data && o.data.source };
    let data = o.data || null, sell = { ...o.sell }, last = null;
    const draw = () => {
      for (const d of root.querySelectorAll("details[data-k]")) state[d.dataset.k] = d.open;
      const r = evaluate(data, o.holding, sell, o);
      root.classList.add("dl", "gs"); root.dataset.verdict = r.verdict; root.innerHTML = html(r, sell, state);
      const q = (k) => root.querySelector(`.gs-${k}`), num = (k) => { const v = q(k).value.trim(); return v === "" ? null : Math.max(0, parseFloat(v) || 0); };
      for (const k of ["fee", "order", "tax", "ship", "sup"]) q(k).onchange = () => {
        sell = { ...sell, feePct: num("fee") ?? 0, perOrder: Math.round((num("order") ?? 0) * 100), buyerTax: num("tax") ?? 0,
          ship: num("ship") == null ? null : Math.round(num("ship") * 100), supplies: Math.round((num("sup") ?? 0) * 100) };
        state.openCosts = true; draw();
      };
      q("save").onclick = () => { o.save && o.save({ feePct: sell.feePct, perOrder: sell.perOrder, buyerTax: sell.buyerTax, ship: sell.ship, supplies: sell.supplies }); state.note = "Saved as your selling-cost defaults for graded checks."; draw(); };
      q("reset").onclick = () => { sell = { ...o.base }; o.save && o.save(null); state.note = "Back to Edge's defaults."; state.openCosts = true; draw(); };
      const b = q("load"); if (b) b.onclick = async () => {
        state.status = "loading"; state.note = ""; draw();
        let res; try { res = await o.load(!!data); } catch (e) { res = { ok: false, note: "Couldn't get sold prices." }; }
        if (res && res.ok) { data = res.data; state.status = "ready"; state.readAt = res.readAt ?? "just now"; state.source = data.source; } else state.status = "error";
        state.note = (res && res.note) || ""; draw();
      };
      last = r; return r;
    };
    draw();
    return { get result() { return last; }, redraw: draw, get sell() { return sell; } };
  }

  const api = { v: VERSION, evaluate, stats, fee, costsAt, netAt, lowestPrice, explain, trendText, line, html, mount, median, rank, NAME,
    K: { MIN_90, MIN_30, MAX_SALE_AGE, MAX_SPREAD, TREND_MIN, TREND_STEP } };
  if (typeof window !== "undefined") window.EdgeGraded = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
