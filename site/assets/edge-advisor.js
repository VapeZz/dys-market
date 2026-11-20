"use strict";
/* DYS Edge: Holdings Advisor and Today's action list (P3/P4; loaded by edge.js; owner only).

   Turns the checks Edge already runs on what the owner holds into one action per holding, from real eBay sold prices:
     SELL      selling now clears the owner's ROI target and minimum profit at the conservative sold price
     GRADE     a raw Near Mint card where grading's expected result beats selling raw (a bet on the grade)
     MONITOR   below target AND either worth less than paid or prices slipping (30-day sold median 10%+ under 90-day,
               or a PSA card whose last 14 days sold 10%+ lower than the 16 before)
     HOLD      below target, prices steady: keep; the price that would clear the target is shown
     NO DATA   not enough reliable sales to value it (Edge doesn't guess from list prices or other grades)

   Inputs per holding (money in cents):
     { key, name, kind: "raw" | "sealed" | "graded", qty, cost (each), cond, grade (e.g. "PSA 10"), book,
       own:    edge-deal.js own() result (raw and sealed)      | null
       graded: edge-graded.js evaluate() result (graded)       | null
       ch:     edge-channels.js compare() at the sold reference | null
       note:   why there is no result (relay, not found, error) }
   Nothing here calls a provider or stores anything: results live in the page's memory, like every sold-price check.
   The SELL / GRADE / HOLD calls are facts at today's sold prices, not forecasts. Market data, not financial advice. */
(() => {
  const VERSION = 1;
  const SLIPPING = -10;              // percent: 30-day sold median vs 90-day (raw/sealed) at or under which prices are slipping
  const ACTIONS = ["sell", "grade", "monitor", "hold", "data"];
  const NAME = { sell: "Sell", grade: "Grade?", monitor: "Monitor", hold: "Hold", data: "Not enough data" };
  const CHIP = { sell: "good", grade: "good", monitor: "hot", hold: "", data: "warn" };
  const money = (c) => c == null || !isFinite(c) ? "—" : `${c < 0 ? "−" : ""}$${(Math.abs(c) / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const signed = (c) => c == null || !isFinite(c) ? "—" : (c >= 0 ? "+" : "") + money(c);
  const pct = (x) => x == null || !isFinite(x) ? "—" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toFixed(0)}%`;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
  const ageTxt = (n) => n == null ? "no dated sale" : n <= 0 ? "newest sale today" : n === 1 ? "newest sale yesterday" : `newest sale ${n} days ago`;

  // the best selling option at the sold reference (eligible options only), and eBay's row for the target price
  function where(ch) {
    if (!ch || !ch.rows) return null;
    const best = ch.best ? ch.rows.find((r) => r.k === ch.best) : null, eb = ch.rows.find((r) => r.k === "ebay");
    if (!best) return null;
    return { k: best.k, name: best.ch.name, price: best.price, keep: best.at ? best.at.net : null, profit: best.profit, roi: best.roi, state: best.state,
      assumed: best.k !== "ebay" && !best.typed, target: best.target, breakEven: best.breakEven,
      ebay: eb && eb.at ? { keep: eb.at.net, profit: eb.profit, target: eb.target } : null };
  }

  function classify(h) {
    const out = judge(h);
    // a NOT ENOUGH DATA row carries no value, profit or selling option: nothing is shown that the evidence doesn't support
    if (out.action === "data") { out.best = null; out.ref = null; out.refBasis = ""; out.profitNow = null; out.gradeProfit = null; }
    return out;
  }
  function judge(h) {
    const out = { key: h.key, name: h.name, kind: h.kind, qty: h.qty || 1, cost: h.cost || 0, grade: h.grade || "", cond: h.cond || "", book: h.book || "",
      action: "data", why: "", ref: null, refBasis: "", evidence: null, best: where(h.ch), gradeProfit: null, profitNow: null };
    // ---- graded: that grader and grade's own sales only
    if (h.kind === "graded") {
      const r = h.graded;
      if (!r) { out.why = h.note || "Not checked yet."; return out; }
      out.evidence = r.s ? { n30: r.s.n30, n90: r.s.n90, capped: !!r.s.capped, age: r.s.saleAge, trend: r.s.trend ? r.s.trend.word : null } : null;
      if (r.verdict === "insufficient") { out.why = r.reasons && r.reasons[0] ? r.reasons[0].text : "Not enough sales of this grade."; return out; }
      out.ref = r.typical; out.refBasis = `${r.label} typical sold price (${r.basis})`; out.profitNow = r.profit;
      const slipping = r.s && r.s.trend && r.s.trend.word === "lower";
      if (r.verdict === "sell") { out.action = "sell"; out.why = `Sells near ${money(r.typical)}: about ${signed(r.profit)} over what you paid on eBay after fees.`; return out; }
      out.action = r.profit < 0 || slipping ? "monitor" : "hold";
      out.why = out.action === "monitor"
        ? `${r.profit < 0 ? `Worth ${money(-r.profit)} less than you paid at today's sold prices` : "Below your target"}${slipping ? "; the last 14 days sold lower" : ""}. Break-even ${money(r.breakEven)}, target ${money(r.target)}.`
        : `Below your target at ${money(r.typical)} (${signed(r.profit)}). Target ${money(r.target)}; not a prediction it gets there.`;
      return out;
    }
    // ---- raw cards and sealed: the Deal check's own() on real sold prices
    const o = h.own;
    if (!o) { out.why = h.note || "Not checked yet."; return out; }
    const F = o.r && o.r.routes && o.r.routes.flip, ev = F && F.ev;
    out.evidence = ev ? { n30: ev.n30, n90: ev.n90, capped: !!ev.capped, age: ev.saleAge, change: ev.change } : null;
    out.gradeProfit = o.gradeProfit;
    if (o.label === "unclear" || o.label === "unknown") { out.why = o.text || "No reliable sold prices."; return out; }
    out.ref = F ? F.exit : null; out.refBasis = ev ? `the lower of the 30- and 90-day ${ev.grade} sold medians${h.kind === "raw" && h.cond && h.cond !== "NM" ? `, at the ${h.cond} share` : ""}` : "";
    out.profitNow = o.profit;
    if (o.label === "sell") { out.action = "sell"; out.why = o.text; return out; }
    if (o.label === "grade") { out.action = "grade"; out.why = `${o.text} That bets on the grade: population odds count only copies people chose to submit.`; return out; }
    const slipping = ev && ev.change != null && ev.change <= SLIPPING;
    out.action = (o.profit != null && o.profit < 0) || slipping ? "monitor" : "hold";
    out.why = `${o.text}${slipping ? ` Sold prices are slipping (30-day median ${pct(ev.change)} vs 90-day).` : ""}`;
    return out;
  }

  // every holding, grouped by action, with totals for the top of Today
  function board(list) {
    const items = list.map(classify), by = {};
    for (const a of ACTIONS) by[a] = [];
    for (const x of items) by[x.action].push(x);
    const order = { sell: (x) => -(x.profitNow || 0), grade: (x) => -(x.gradeProfit || 0), monitor: (x) => x.profitNow ?? 0, hold: (x) => -(x.profitNow ?? 0), data: () => 0 };
    for (const a of ACTIONS) by[a].sort((p, q) => order[a](p) - order[a](q) || String(p.name).localeCompare(String(q.name)));
    const sum = (xs, f) => xs.reduce((s, x) => s + (f(x) || 0) * x.qty, 0);
    return { items, by, counts: Object.fromEntries(ACTIONS.map((a) => [a, by[a].length])),
      sellProfit: sum(by.sell, (x) => x.profitNow), sellBest: sum(by.sell, (x) => x.best ? x.best.profit : x.profitNow),
      valued: items.filter((x) => x.ref != null).length, total: items.length };
  }

  /* ---------- the panel (Today and Inventory) ---------- */
  function row(x, h) {
    const b = x.best, ev = x.evidence;
    const right = x.action === "data" ? `<b class="muted">—</b><small class="muted">no value</small>`
      : x.action === "grade" ? `<b class="up">${signed(x.gradeProfit)}</b><small class="muted">if graded (est.)</small>`
      : `<b class="${x.profitNow > 0 ? "up" : x.profitNow < 0 ? "down" : ""}">${signed(x.profitNow)}</b><small class="muted">eBay, at sold prices</small>`;
    const evTxt = ev ? `${ev.n30}${ev.capped ? "+" : ""} sold in 30 days · ${ageTxt(ev.age)}` : "";
    const line2 = [x.qty > 1 ? `${x.qty}×` : "", x.grade || (x.kind === "raw" ? x.cond : x.kind === "sealed" ? "Sealed" : ""), x.book === "Personal" ? "Personal" : "", `paid ${money(x.cost)}`].filter(Boolean).join(" · ");
    return `<div class="adv-row" data-act="${x.action}" data-key="${esc(x.key)}"${h.attrs ? h.attrs(x) : ""}>
      ${h.img ? h.img(x) : `<span class="ph"></span>`}<div class="adv-main"><b class="adv-n">${esc(x.name)}</b><span class="adv-s">${esc(line2)}</span>
        <span class="adv-why">${esc(x.why)}</span>${evTxt ? `<span class="adv-ev">Evidence: ${esc(evTxt)}${x.ref != null ? ` · valued at ${money(x.ref)} (${esc(x.refBasis)})` : ""}</span>` : ""}
        ${b && x.action !== "data" ? `<span class="adv-ev adv-best">Best estimate: ${esc(b.name)} at ${money(b.price)}${b.assumed ? " (assumed: a share of the eBay sold price)" : ""} → keep ${money(b.keep)}, ${signed(b.profit)}${x.action !== "sell" && b.target ? ` · ${h.roi}% profit at ${money(b.target)}` : ""}</span>` : ""}</div>
      <div class="adv-rt">${right}</div></div>`;
  }
  function html(B, h) {
    if (!B.total) return `<div class="empty"><b>Nothing held yet</b>Record a buy in Mine → Ledger (or tap Bought it on a card) and Edge will tell you what to do with it.</div>`;
    const tile = (a) => `<button type="button" class="adv-tile" data-jump="${a}"><b>${B.counts[a]}</b><small>${NAME[a]}</small></button>`;
    const sec = (a, title, note) => B.by[a].length ? `<section class="adv-sec" id="adv-${a}"><div class="sec-head"><h2>${title}</h2><span class="chip ${CHIP[a]}">${B.by[a].length}</span></div>
      ${note ? `<p class="muted small adv-note">${note}</p>` : ""}<div class="adv-list">${B.by[a].map((x) => row(x, h)).join("")}</div></section>` : "";
    if (h.compact) return `<div class="adv-tiles">${ACTIONS.map(tile).join("")}</div>
      ${B.counts.sell ? `<p class="small adv-sum">${B.counts.sell} worth selling: about <b class="${B.sellProfit >= 0 ? "up" : "down"}">${signed(B.sellProfit)}</b> over cost on eBay at today's sold prices.</p>` : ""}
      <p class="small muted adv-note">Each item's call is on its row below. The full list with reasons and where to sell is on Today.</p>`;
    return `<div class="adv-tiles">${ACTIONS.map(tile).join("")}</div>
      ${B.counts.sell ? `<p class="small adv-sum">Selling the ${B.counts.sell} item${B.counts.sell === 1 ? "" : "s"} worth selling on eBay at today's sold prices: about <b class="${B.sellProfit >= 0 ? "up" : "down"}">${signed(B.sellProfit)}</b> over cost after fees${B.sellBest > B.sellProfit ? `; at each one's best estimate (local prices assumed) about ${signed(B.sellBest)}` : ""}. Check live listings before you price.</p>` : ""}
      ${sec("sell", "Worth selling", "Clears your target on eBay at real sold prices, after fees, shipping and supplies. Best estimate = the selling option with the highest estimated profit; local prices are assumptions you can change on the card's Where to sell?.")}
      ${sec("grade", "May be worth grading", "Expected value from PSA population odds and PSA sold prices. A bet on the grade, never a sure profit.")}
      ${sec("monitor", "Monitor", "Below target and worth less than you paid, or sold prices slipping.")}
      ${sec("hold", "Hold", "Below target at today's sold prices; prices steady. Not a prediction they'll rise.")}
      ${sec("data", "Not enough data", "Edge won't value these from list prices or other grades. Check them by hand before acting.")}`;
  }

  const api = { v: VERSION, classify, board, html, where, ACTIONS, NAME, K: { SLIPPING } };
  if (typeof window !== "undefined") window.EdgeAdvisor = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
