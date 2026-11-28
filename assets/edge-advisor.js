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
    if (h && h.saved) return h;          // a saved call (see snapshot): already classified, amounts are ranges only
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

  /* ---------- saved calls (12 hours on the phone): our own calls only, never PkmnPrices data ----------
     Kept: the call, a reason without amounts, sale counts and age, which selling option was best, and the profit as a
     range (the same kind of bands the Near Mint finder saves). Not kept: sold prices, medians, sales, exact profits or any
     amount an exact sold price could be worked back from. The owner's own cost and quantity come from his Ledger. */
  const BANDS = [[-Infinity, -10000], [-10000, -5000], [-5000, -2000], [-2000, -500], [-500, 0], [0, 500], [500, 1000], [1000, 2000], [2000, 5000], [5000, 10000], [10000, 25000], [25000, Infinity]];
  const bandOf = (c) => c == null || !isFinite(c) ? null : BANDS.findIndex(([lo, hi]) => c >= lo && c < hi);
  const bandMid = (i) => i == null ? 0 : i === 0 ? -15000 : i === BANDS.length - 1 ? 30000 : (BANDS[i][0] + BANDS[i][1]) / 2;
  const whole = (c) => `$${Math.abs(c / 100).toLocaleString("en-US")}`;
  function bandTxt(i) {
    if (i == null) return "—";
    const [lo, hi] = BANDS[i];
    if (lo === -Infinity) return `loss over ${whole(hi)}`;
    if (hi === Infinity) return `+${whole(lo)} or more`;
    if (hi <= 0) return `−${whole(lo)} to ${hi === 0 ? "$0" : "−" + whole(hi)}`;
    return `${lo === 0 ? "$0" : "+" + whole(lo)} to +${whole(hi)}`;
  }
  const short = (c) => `${c < 0 ? "−" : "+"}${whole(c)}`;
  const rangeTxt = (lo, hi) => lo === hi ? signed(lo) : !isFinite(hi) ? `${short(lo)} or more` : !isFinite(lo) ? `up to ${short(hi)}` : `${short(lo)} to ${short(hi)}`;
  // a reason without amounts, for a saved call
  function savedWhy(x) {
    if (x.action === "sell") return "Cleared your target on eBay at the sold prices checked.";
    if (x.action === "grade") return "Grading's expected result beat selling raw. A bet on the grade, never a sure profit.";
    if (x.action === "monitor") return `${x.profitNow != null && x.profitNow < 0 ? "Worth less than you paid at the sold prices checked" : "Below your target"}${x.evidence && x.evidence.change != null && x.evidence.change <= SLIPPING || x.evidence && x.evidence.trend === "lower" ? "; sold prices were slipping" : ""}.`;
    if (x.action === "hold") return "Below your target at the sold prices checked; prices steady.";
    return /\$/.test(x.why || "") ? "Not enough reliable sales to value it." : (x.why || "Not enough reliable sales to value it.");
  }
  // classified items -> what may be kept on the phone
  function snapshot(items) {
    return items.map((x) => ({ key: x.key, name: x.name, kind: x.kind, qty: x.qty, cost: x.cost, cond: x.cond, grade: x.grade, book: x.book, action: x.action,
      why: savedWhy(x), band: x.action === "data" ? null : bandOf(x.action === "grade" ? x.gradeProfit : x.profitNow),
      ev: x.evidence ? { n30: x.evidence.n30, n90: x.evidence.n90, capped: !!x.evidence.capped, age: x.evidence.age } : null,
      bestName: x.action !== "data" && x.best ? x.best.name : null, bestAssumed: !!(x.best && x.best.assumed) }));
  }
  // kept rows -> items the board and the panel show (marked saved: amounts as ranges)
  function restore(rows) {
    return (rows || []).filter((r) => r && r.key && ACTIONS.includes(r.action)).map((r) => ({ key: r.key, name: r.name, kind: r.kind, qty: r.qty || 1, cost: r.cost || 0,
      cond: r.cond || "", grade: r.grade || "", book: r.book || "", action: r.action, why: r.why, saved: true, band: r.action === "data" ? null : (r.band ?? null),
      evidence: r.ev, best: r.bestName ? { name: r.bestName, assumed: r.bestAssumed } : null, ref: null, refBasis: "", profitNow: null, gradeProfit: null }));
  }

  // every holding, grouped by action, with totals for the top of Today
  function board(list) {
    const items = list.map(classify), by = {};
    for (const a of ACTIONS) by[a] = [];
    for (const x of items) by[x.action].push(x);
    const pv = (x) => x.saved ? bandMid(x.band) : x.action === "grade" ? x.gradeProfit : x.profitNow;
    const order = { sell: (x) => -(pv(x) || 0), grade: (x) => -(pv(x) || 0), monitor: (x) => pv(x) ?? 0, hold: (x) => -(pv(x) ?? 0), data: () => 0 };
    for (const a of ACTIONS) by[a].sort((p, q) => order[a](p) - order[a](q) || String(p.name).localeCompare(String(q.name)));
    const sum = (xs, f) => xs.reduce((s, x) => s + (f(x) || 0) * x.qty, 0);
    const saved = items.some((x) => x.saved), sellSaved = by.sell.some((x) => x.saved);
    return { items, by, counts: Object.fromEntries(ACTIONS.map((a) => [a, by[a].length])), saved,
      sellProfit: sellSaved ? null : sum(by.sell, (x) => x.profitNow), sellBest: sellSaved ? null : sum(by.sell, (x) => x.best ? x.best.profit : x.profitNow),
      // with saved calls in it, the total is a range: each saved row's band, each fresh row's exact profit
      sellRange: sellSaved ? [sum(by.sell, (x) => x.saved ? BANDS[x.band][0] : x.profitNow), sum(by.sell, (x) => x.saved ? BANDS[x.band][1] : x.profitNow)] : null,
      valued: items.filter((x) => x.ref != null || (x.saved && x.action !== "data")).length, total: items.length };
  }

  /* ---------- the panel (Today and Inventory) ---------- */
  function row(x, h) {
    const b = x.best, ev = x.evidence;
    const right = x.action === "data" ? `<b class="muted">—</b><small class="muted">no value</small>`
      : x.saved ? `<b class="${x.band >= 5 ? "up" : x.band != null && x.band <= 4 ? "down" : ""}">${bandTxt(x.band)}</b><small class="muted">${x.action === "grade" ? "if graded (est.), range" : "eBay, range"}</small>`
      : x.action === "grade" ? `<b class="up">${signed(x.gradeProfit)}</b><small class="muted">if graded (est.)</small>`
      : `<b class="${x.profitNow > 0 ? "up" : x.profitNow < 0 ? "down" : ""}">${signed(x.profitNow)}</b><small class="muted">eBay, at sold prices</small>`;
    const evTxt = ev ? `${ev.n30}${ev.capped ? "+" : ""} sold in 30 days · ${ageTxt(ev.age)}` : "";
    const line2 = [x.qty > 1 ? `${x.qty}×` : "", x.grade || (x.kind === "raw" ? x.cond : x.kind === "sealed" ? "Sealed" : ""), x.book === "Personal" ? "Personal" : "", `paid ${money(x.cost)}`].filter(Boolean).join(" · ");
    return `<div class="adv-row" data-act="${x.action}" data-key="${esc(x.key)}"${h.attrs ? h.attrs(x) : ""}>
      ${h.img ? h.img(x) : `<span class="ph"></span>`}<div class="adv-main"><b class="adv-n">${esc(x.name)}</b><span class="adv-s">${esc(line2)}</span>
        <span class="adv-why">${esc(x.why)}</span>${evTxt ? `<span class="adv-ev">Evidence: ${esc(evTxt)}${x.ref != null ? ` · valued at ${money(x.ref)} (${esc(x.refBasis)})` : ""}</span>` : ""}
        ${b && x.saved && x.action !== "data" ? `<span class="adv-ev adv-best">Best place to sell: ${esc(b.name)}${b.assumed ? " (local price assumed)" : ""}</span>` : ""}
        ${b && !x.saved && x.action !== "data" ? `<span class="adv-ev adv-best">Best estimate: ${esc(b.name)} at ${money(b.price)}${b.assumed ? " (assumed: a share of the eBay sold price)" : ""} → keep ${money(b.keep)}, ${signed(b.profit)}${x.action !== "sell" && b.target ? ` · ${h.roi}% profit at ${money(b.target)}` : ""}</span>` : ""}</div>
      <div class="adv-rt">${right}</div></div>`;
  }
  function html(B, h) {
    if (!B.total) return `<div class="empty"><b>Nothing held yet</b>Record a buy in Mine → Ledger (or tap Bought it on a card) and Edge will tell you what to do with it.</div>`;
    const tile = (a) => `<button type="button" class="adv-tile" data-jump="${a}"><b>${B.counts[a]}</b><small>${NAME[a]}</small></button>`;
    const sec = (a, title, note) => B.by[a].length ? `<section class="adv-sec" id="adv-${a}"><div class="sec-head"><h2>${title}</h2><span class="chip ${CHIP[a]}">${B.by[a].length}</span></div>
      ${note ? `<p class="muted small adv-note">${note}</p>` : ""}<div class="adv-list">${B.by[a].map((x) => row(x, h)).join("")}</div></section>` : "";
    const sellAmt = B.sellRange ? `<b class="${B.sellRange[0] >= 0 ? "up" : ""}">${rangeTxt(B.sellRange[0], B.sellRange[1])}</b>` : `<b class="${B.sellProfit >= 0 ? "up" : "down"}">${signed(B.sellProfit)}</b>`;
    if (h.compact) return `<div class="adv-tiles">${ACTIONS.map(tile).join("")}</div>
      ${B.counts.sell ? `<p class="small adv-sum">${B.counts.sell} worth selling: about ${sellAmt} over cost on eBay at the sold prices checked.</p>` : ""}
      <p class="small muted adv-note">Each item's call is on its row below. The full list with reasons and where to sell is on Today.</p>`;
    return `<div class="adv-tiles">${ACTIONS.map(tile).join("")}</div>
      ${B.counts.sell ? `<p class="small adv-sum">Selling the ${B.counts.sell} item${B.counts.sell === 1 ? "" : "s"} worth selling on eBay at the sold prices checked: about ${sellAmt} over cost after fees${!B.sellRange && B.sellBest > B.sellProfit ? `; at each one's best estimate (local prices assumed) about ${signed(B.sellBest)}` : ""}${B.sellRange ? " (saved calls keep ranges, not exact amounts)" : ""}. Check live listings before you price.</p>` : ""}
      ${sec("sell", "Worth selling", "Clears your target on eBay at real sold prices, after fees, shipping and supplies. Best estimate = the selling option with the highest estimated profit; local prices are assumptions you can change on the card's Where to sell?.")}
      ${sec("grade", "May be worth grading", "Expected value from PSA population odds and PSA sold prices. A bet on the grade, never a sure profit.")}
      ${sec("monitor", "Monitor", "Below target and worth less than you paid, or sold prices slipping.")}
      ${sec("hold", "Hold", "Below target at today's sold prices; prices steady. Not a prediction they'll rise.")}
      ${sec("data", "Not enough data", "Edge won't value these from list prices or other grades. Check them by hand before acting.")}`;
  }

  const api = { v: VERSION, classify, board, html, where, snapshot, restore, bandOf, bandTxt, BANDS, ACTIONS, NAME, K: { SLIPPING } };
  if (typeof window !== "undefined") window.EdgeAdvisor = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
