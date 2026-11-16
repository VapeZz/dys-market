"use strict";
/* DYS Edge: Verified Deal Check (milestone M1; loaded by edge.js; owner only).

   Answers one question for one item at one asking price: is this a BUY candidate, or a PASS?
   It reads completed sales (sold comps), not chart signals. The verdict is PASS unless every gate below
   clears. "BUY candidate" means the evidence supports a closer look at this price; it is never an order.

   Input (one item; all money in cents, days counted from 1970-01-01 UTC):
     item   { name, t: "c" card | "s" sealed, year, tcg (TCGplayer market, optional second source), tcgDay }
     data   { asOf (day the comps were read), source (provider name),
              comps: [[day, cents, grade, exact]]   grade: "raw" | "sealed" | "PSA 10" | "PSA 9" | ...,
                                                   exact: 1 when the sale belongs to this printing alone
              pop:   { total, g10, g9, asOf }       PSA population (optional) }
     offer  { ask, cond: "NM" | "LP" | "MP" | "HP" | "DMG", shipIn, taxIn (percent paid on the purchase) }
     cfg    { today, fees ({ flat, parts } as in Edge's fee file), buyerTax (percent the marketplace adds and
              charges its fee on), shipOut(price, t), supplies(t), roi (target percent), minProfit, grade {...},
              holdRate (cost of money, percent a month) }

   Gates for BUY candidate on a route (all must clear; any miss is a PASS with its reason):
     scope      item worth SCOPE_MIN or more (M1 covers $20+)
     evidence   MIN_COMPS exact-printing sales of the right grade in 90 days
     liquidity  MIN_SALES_30 of them in the last 30 days
     fresh      comps read within MAX_FETCH_AGE days, newest sale within MAX_SALE_AGE days
     spread     the middle half of 90-day prices within MAX_SPREAD percent of the median
     agree      sold median within MAX_DISAGREE percent of the second source (no second source: no BUY)
     trend      30-day median not FALLING percent or more under the 90-day median, and the chart's
                tested warning rules (Falling knife, Breakdown) not firing
     margin     net profit at the conservative exit clears the ROI target and MIN_PROFIT
   Conservative exit: the lower of the 30-day and 90-day sold medians, times the condition share for a
   raw card that is not Near Mint. Sell side: marketplace fee on price plus buyer tax, shipping out,
   supplies. Buy side: ask, purchase tax, shipping in.
   Grade route (raw cards): PSA 10 / PSA 9 shares from population, each grade's own sold median and
   liquidity, grading fee, shipping to the grader, and the cost of money for the turnaround.
   Hold: information only (no engine until M4): the rise needed to break even over 6 and 12 months
   (fees on the higher price; shipping and supplies at today's level).

   Every threshold is a named constant below. Market data, not financial advice. */
(() => {
  const VERSION = 1;
  /* ---------- thresholds ---------- */
  const SCOPE_MIN = 2000;     // cents: M1 covers items worth $20 and up
  const MIN_COMPS = 5;        // exact-printing sales of the right grade in 90 days
  const MIN_SALES_30 = 3;     // of those, in the last 30 days (liquidity floor)
  const MAX_FETCH_AGE = 3;    // days since the comps were read
  const MAX_SALE_AGE = 21;    // days since the newest matching sale (the feed runs about 8 days behind)
  const MAX_SPREAD = 25;      // percent: half the interquartile range over the median
  const MAX_DISAGREE = 25;    // percent between the sold median and the second source
  const FALLING = 10;         // percent the 30-day median sits under the 90-day median: a falling market
  const MIN_PROFIT = 500;     // cents: the smallest net profit worth the work
  const GRADE_MIN_POP = 100;  // graded copies before population odds count
  const GRADE_MIN_SALES_30 = 2; // PSA 10 sales in 30 days before the grade route can pass
  const LOWER_GRADES = 0.9;   // a copy that misses PSA 9 sells at this share of the raw exit
  const WARNINGS = ["knife", "breakdown"];   // chart rules that passed the backtest as warnings
  const COND = { NM: 1, LP: 0.85, MP: 0.7, HP: 0.55, DMG: 0.4 };   // as Edge's condition shares
  const DAY = 864e5;

  /* ---------- small helpers ---------- */
  const today = () => Math.floor(Date.now() / DAY);
  const median = (xs) => { if (!xs.length) return null; const s = [...xs].sort((a, b) => a - b), m = s.length >> 1; return s.length % 2 ? s[m] : Math.round((s[m - 1] + s[m]) / 2); };
  // quartile by the nearest-rank method (no interpolation; easy to recompute by hand)
  const rank = (xs, q) => { if (!xs.length) return null; const s = [...xs].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.max(0, Math.ceil(q * s.length) - 1))]; };
  const money = (c) => c == null || !isFinite(c) ? "—" : `${c < 0 ? "−" : ""}$${(Math.abs(c) / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const signed = (c) => c == null || !isFinite(c) ? "—" : (c >= 0 ? "+" : "") + money(c);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
  const r2 = (x) => Math.round(x * 100) / 100;   // percentages to 0.01 so a boundary is exact
  const pct = (x, d = 0) => { if (x == null || !isFinite(x)) return "—"; const a = Math.abs(x).toFixed(d), z = +a === 0; return `${z ? "" : x > 0 ? "+" : "−"}${z ? (0).toFixed(d) : a}%`; };

  /* ---------- money ---------- */
  // the marketplace fee: tiered percent parts plus a flat fee, charged on the price plus the buyer's sales tax
  function fee(fees, price, buyerTax = 0) {
    if (!fees || !price) return 0;
    const base = Math.round(price * (1 + buyerTax / 100));
    let f = fees.flat || 0;
    for (const [p, lo, hi, cap] of fees.parts || []) { const part = Math.max(0, (hi == null ? base : Math.min(base, hi)) - lo) * p / 100; f += cap == null ? part : Math.min(part, cap); }
    return Math.round(f);
  }
  // what a sale at `price` leaves after fee, shipping out and supplies
  function netSale(price, t, cfg) {
    if (!price) return 0;
    return price - fee(cfg.fees, price, cfg.buyerTax || 0) - (cfg.shipOut ? cfg.shipOut(price, t) : 0) - (cfg.supplies ? cfg.supplies(t) : 0);
  }
  // all-in cost of buying at `ask`
  const costIn = (ask, offer) => ask + Math.round(ask * (offer.taxIn || 0) / 100) + (offer.shipIn || 0);
  // the highest ask whose net profit still clears the ROI target and the minimum profit (a search: fees are stepped)
  function maxAsk(proceeds, offer, roi, minProfit) {
    if (!(proceeds > 0)) return 0;
    const ok = (a) => { const c = costIn(a, offer), pr = proceeds - c; return pr >= minProfit && pr * 100 >= c * roi; };
    let lo = 0, hi = proceeds;
    if (!ok(lo)) return 0;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (ok(mid)) lo = mid; else hi = mid; }
    return lo;
  }

  /* ---------- the evidence for one grade ---------- */
  function comps(data, grade, day) {
    const all = (data.comps || []).filter((c) => c[2] === grade && c[3] && c[0] <= day && c[0] > day - 90);
    const p90 = all.map((c) => c[1]), p30 = all.filter((c) => c[0] > day - 30).map((c) => c[1]);
    const newest = all.length ? Math.max(...all.map((c) => c[0])) : null;
    const m90 = median(p90), m30 = p30.length >= MIN_SALES_30 ? median(p30) : null;
    const q1 = rank(p90, 0.25), q3 = rank(p90, 0.75);
    return { grade, n90: p90.length, n30: p30.length, m90, m30, q1, q3, newest, saleAge: newest == null ? null : day - newest,
      spread: m90 ? r2((q3 - q1) / 2 / m90 * 100) : null, change: m30 && m90 ? r2((m30 / m90 - 1) * 100) : null,
      exit: m30 != null && m90 != null ? Math.min(m30, m90) : m90,
      // when more sales exist than were read (data.capped), the counts are lower bounds and the pace comes from the days read
      capped: !!(data.capped && data.capped.includes(grade)),
      everyDays: !p30.length ? null : data.capped && data.capped.includes(grade) ? (Math.max(...all.map((c) => c[0])) - Math.min(...all.map((c) => c[0])) + 1) / p90.length : 30 / p30.length,
      inexact: (data.comps || []).filter((c) => c[2] === grade && !c[3] && c[0] > day - 90).length };
  }

  /* ---------- gates ---------- */
  const gate = (code, ok, text, hard = true) => ({ code, ok: !!ok, text, hard });
  function gatesFor(ev, item, data, day, ctx) {
    const g = [];
    const ref = ev.m90;
    g.push(gate("evidence", ev.n90 >= MIN_COMPS, ev.n90 >= MIN_COMPS ? `${ev.n90}${ev.capped ? "+" : ""} exact ${ev.grade} sales in 90 days${ev.capped ? " (the newest read; more exist)" : ""}`
      : `Only ${ev.n90} exact ${ev.grade} sale${ev.n90 === 1 ? "" : "s"} in 90 days (needs ${MIN_COMPS})${ev.inexact ? `; ${ev.inexact} more shared with other printings were left out` : ""}`));
    g.push(gate("liquidity", ev.n30 >= MIN_SALES_30, ev.n30 >= MIN_SALES_30 ? `${ev.n30}${ev.capped ? "+" : ""} sold in the last 30 days (about ${ev.everyDays < 1 ? `${(1 / ev.everyDays).toFixed(0)} a day` : `one every ${ev.everyDays.toFixed(1)} days`})`
      : `${ev.n30} sold in the last 30 days (needs ${MIN_SALES_30}): hard to resell quickly`));
    const fetchAge = data.asOf == null ? null : day - data.asOf;
    const fresh = fetchAge != null && fetchAge <= MAX_FETCH_AGE && ev.saleAge != null && ev.saleAge <= MAX_SALE_AGE;
    g.push(gate("fresh", fresh, fetchAge == null ? "No date on the sales data"
      : fetchAge > MAX_FETCH_AGE ? `Sales data is ${fetchAge} days old (needs ${MAX_FETCH_AGE} or less)`
      : ev.saleAge == null ? "No recent sale on record"
      : ev.saleAge > MAX_SALE_AGE ? `Newest sale is ${ev.saleAge} days old (needs ${MAX_SALE_AGE} or less)`
      : `Read ${fetchAge === 0 ? "today" : `${fetchAge} day${fetchAge === 1 ? "" : "s"} ago`}; newest sale ${ev.saleAge} days ago`));
    g.push(gate("spread", ev.spread != null && ev.spread <= MAX_SPREAD, ev.spread == null ? "No price spread to read"
      : ev.spread <= MAX_SPREAD ? `Sold prices are consistent (middle half within ±${ev.spread.toFixed(0)}%)`
      : `Sold prices are scattered (middle half ±${ev.spread.toFixed(0)}%, limit ${MAX_SPREAD}%): condition or listing mix`));
    if (ctx.second) {
      const tcg = item.tcg, tcgAge = item.tcgDay == null ? null : day - item.tcgDay;
      const d = tcg && ref ? r2((tcg / ref - 1) * 100) : null;
      const ok = d != null && Math.abs(d) <= MAX_DISAGREE && tcgAge != null && tcgAge <= MAX_FETCH_AGE;
      g.push(gate("agree", ok, d == null ? "No second price source to check against: no BUY without one"
        : tcgAge == null || tcgAge > MAX_FETCH_AGE ? `Second source is ${tcgAge == null ? "undated" : `${tcgAge} days old`}`
        : ok ? `TCGplayer market ${money(tcg)} agrees (${pct(d)} vs sold median)` : `TCGplayer market ${money(tcg)} is ${pct(d)} from the sold median (limit ±${MAX_DISAGREE}%)`));
    }
    const falling = ev.change != null && ev.change <= -FALLING;
    const warn = ctx.warning && WARNINGS.includes(ctx.warning.id) && ctx.warning.verdict === "pass";
    g.push(gate("trend", !falling && !warn, warn ? `Chart warning "${ctx.warning.name}" is on (a rule that held up in the backtest): wait`
      : falling ? `Falling: 30-day median ${pct(ev.change)} under the 90-day` : ev.change == null ? "Trend: not enough 30-day sales to compare (exit uses the 90-day median)"
      : `Trend: 30-day median ${pct(ev.change)} vs 90-day`));
    return g;
  }

  /* ---------- routes ---------- */
  function flipRoute(item, data, offer, cfg, day, ctx) {
    const grade = item.t === "s" ? "sealed" : "raw";
    const ev = comps(data, grade, day);
    const cm = item.t === "s" ? 1 : COND[offer.cond] ?? 1;
    const exit = ev.exit ? Math.round(ev.exit * cm) : null;
    const proceeds = exit ? netSale(exit, item.t, cfg) : null;
    const cost = costIn(offer.ask, offer);
    const profit = proceeds != null ? proceeds - cost : null;
    const roi = profit != null && cost > 0 ? profit / cost * 100 : null;
    const gates = gatesFor(ev, item, data, day, { second: true, warning: ctx.warning });
    if (cm < 1) gates.push(gate("condition", true, `${offer.cond}: exit taken at ${Math.round(cm * 100)}% of the Near Mint median; check the copy in hand`, false));
    const clears = profit != null && profit >= (cfg.minProfit ?? MIN_PROFIT) && profit * 100 >= cost * cfg.roi;
    gates.push(gate("margin", clears,
      profit == null ? "No sold price to work from"
      : `Net ${signed(profit)} (${pct(roi)}) at a ${money(exit)} exit${clears ? "" : ` (needs ${cfg.roi}% and ${money(cfg.minProfit ?? MIN_PROFIT)})`}`));
    const max = proceeds ? maxAsk(proceeds, offer, cfg.roi, cfg.minProfit ?? MIN_PROFIT) : 0;
    return { route: "flip", grade, ev, exit, proceeds, cost, profit, roi, max, gates, pass: gates.every((x) => x.ok || !x.hard), days: ev.everyDays };
  }

  function gradeRoute(item, data, offer, cfg, day, ctx) {
    if (item.t !== "c" || !cfg.grade) return null;
    const G = cfg.grade, pop = data.pop;
    const raw = comps(data, "raw", day), e10 = comps(data, "PSA 10", day), e9 = comps(data, "PSA 9", day);
    const popOk = pop && pop.total >= GRADE_MIN_POP;
    const p10 = popOk ? pop.g10 / pop.total : null, p9 = popOk ? pop.g9 / pop.total : null;
    const cm = COND[offer.cond] ?? 1;
    const rawExit = raw.exit ? Math.round(raw.exit * cm) : null;
    // a copy that is not Near Mint is not sent to grade: the odds below are for Near Mint submissions
    const gradeable = offer.cond === "NM";
    const n10 = e10.exit ? netSale(e10.exit, "c", cfg) : null, n9 = e9.exit ? netSale(e9.exit, "c", cfg) : null, nLow = rawExit ? netSale(Math.round(rawExit * LOWER_GRADES), "c", cfg) : null;
    const expected = gradeable && p10 != null && n10 != null && n9 != null && nLow != null ? Math.round(p10 * n10 + p9 * n9 + (1 - p10 - p9) * nLow) : null;
    const fees = (G.fee || 0) + (G.ship || 0);
    const months = Number.isFinite(+G.months) ? +G.months : 0, carry = Math.round(offer.ask * (cfg.holdRate || 0) / 100 * months);
    const cost = costIn(offer.ask, offer) + fees + carry;
    const profit = expected != null ? expected - cost : null, roi = profit != null ? profit / cost * 100 : null;
    const gates = [];
    gates.push(gate("gradeable", gradeable, gradeable ? "Near Mint copy" : `${offer.cond} copy: not a grading candidate`));
    gates.push(gate("population", popOk, popOk ? `PSA population ${pop.total.toLocaleString("en-US")}: ${(p10 * 100).toFixed(0)}% PSA 10, ${(p9 * 100).toFixed(0)}% PSA 9` : `PSA population under ${GRADE_MIN_POP} or missing: no odds to work from`));
    gates.push(gate("psa10-sales", e10.n30 >= GRADE_MIN_SALES_30 && e10.n90 >= MIN_COMPS, `${e10.n30} PSA 10 sold in 30 days, ${e10.n90} in 90 (needs ${GRADE_MIN_SALES_30} and ${MIN_COMPS})`));
    gates.push(...gatesFor(e10, item, data, day, { second: false, warning: ctx.warning }).filter((x) => x.code === "fresh" || x.code === "trend" || x.code === "spread").map((x) => ({ ...x, text: `PSA 10: ${x.text}` })));
    gates.push(gate("psa9-sales", e9.n90 >= MIN_COMPS, `${e9.n90} PSA 9 sold in 90 days (needs ${MIN_COMPS})`));
    gates.push(gate("margin", profit != null && profit >= (cfg.minProfit ?? MIN_PROFIT) && profit * 100 >= cost * cfg.roi,
      profit == null ? "Not enough to work out an expected value" : `Expected net ${signed(profit)} (${pct(roi)}) after grading ${money(fees)} and ${months} months of cost of money ${money(carry)}`));
    return { route: "grade", months, p10, p9, n10, n9, nLow, e10, e9, expected, fees, carry, cost, profit, roi, gates, pass: gates.every((x) => x.ok || !x.hard) };
  }

  function holdRoute(flip, offer, cfg) {
    if (!flip.exit) return null;
    const cost = flip.cost, rate = (cfg.holdRate || 0) / 100;
    // shipping and supplies held at today's level so the search runs on a rising curve (shipping steps up with price)
    const fixed = (cfg.shipOut ? cfg.shipOut(flip.exit, flip.t) : 0) + (cfg.supplies ? cfg.supplies(flip.t) : 0);
    const netAt = (p) => p - fee(cfg.fees, p, cfg.buyerTax || 0) - fixed;
    // the sale price needed after n months so the net covers the cost plus the cost of money, as a rise from today's exit
    const need = (n) => {
      const target = Math.round(cost * (1 + rate * n));
      if (netAt(flip.exit) >= target) return 0;
      let lo = flip.exit, hi = flip.exit * 2;
      while (netAt(hi) < target) { lo = hi; hi *= 2; }
      while (hi - lo > 1) { const m = Math.floor((lo + hi) / 2); if (netAt(m) >= target) hi = m; else lo = m; }
      return (hi / flip.exit - 1) * 100;
    };
    return { route: "hold", m6: need(6), m12: need(12) };
  }

  /* ---------- the check ---------- */
  function check(item, data, offer, cfg, ctx = {}) {
    const day = cfg.today ?? today();
    const out = { v: VERSION, verdict: "pass", why: "", route: null, routes: {}, scope: true, confidence: null };
    const flip = flipRoute(item, data || {}, offer, cfg, day, ctx); flip.t = item.t;
    out.routes.flip = flip;
    out.routes.grade = gradeRoute(item, data || {}, offer, cfg, day, ctx);
    out.routes.hold = holdRoute(flip, offer, cfg);
    // out of scope only when every price we have says under $20 (a sold median far under TCGplayer is a data problem the
    // agree check reports, e.g. Master Ball Umbreon 059/131 on Nov 16: sold $1.99, TCGplayer $50.04)
    out.scope = Math.max(flip.ev.m90 || 0, item.tcg || 0) >= SCOPE_MIN;
    out.confidence = confidence(flip);
    out.fetchAge = data && data.asOf != null ? day - data.asOf : null;
    if (!data || !(data.comps || []).length) { out.reason = "no-data"; out.why = data ? "No sold prices on record" : "No sold prices loaded"; return out; }
    // only a resale that clears every check makes a BUY candidate; a grading route that clears is shown, never called
    // (population odds count only copies people chose to send in, so they run high for a raw copy bought at a table)
    out.gradeClears = !!(out.routes.grade && out.routes.grade.pass);
    const pick = flip.pass ? flip : null;
    if (!out.scope) { out.reason = "scope"; out.why = `Out of M1 scope: worth under ${money(SCOPE_MIN)}`; return out; }
    if (pick) { out.verdict = "buy"; out.route = pick.route; out.why = pick.route === "flip" ? `Every check clears for a resale at ${money(flip.exit)}` : "Every check clears for grading"; return out; }
    const ORDER = ["fresh", "evidence", "liquidity", "spread", "agree", "trend", "margin"];   // the clearest reason first: old data before thin data
    const miss = ORDER.map((c) => flip.gates.find((x) => x.code === c && x.hard && !x.ok)).find(Boolean) || flip.gates.find((x) => x.hard && !x.ok);
    const WHY = { evidence: "Not enough evidence", liquidity: "Not enough evidence", fresh: "Not enough evidence", spread: "Not enough evidence",
      agree: "Sold prices not confirmed by a second source", trend: "Market is falling or flagged", margin: "Doesn't clear your margin" };
    out.why = miss ? WHY[miss.code] || "A check misses" : "A check misses";
    out.reason = miss ? miss.code : null;
    return out;
  }

  // how much the sold evidence can be trusted (independent of the asking price): A best, D weakest
  function confidence(flip) {
    const want = ["evidence", "liquidity", "fresh", "spread", "agree"];
    const miss = flip.gates.filter((x) => want.includes(x.code) && !x.ok).length;
    const deep = flip.ev.n90 >= MIN_COMPS * 3 && flip.ev.n30 >= MIN_SALES_30 * 2;
    return miss === 0 ? (deep ? "A" : "B") : miss === 1 ? "C" : "D";
  }

  /* ---------- plain words ---------- */
  const daysTxt = (d) => d == null ? "" : d < 0.75 ? `about ${Math.round(1 / d)} a day` : d < 1.5 ? "about one a day" : `about one every ${Math.round(d)} days`;
  // one sentence on the verdict, for a phone screen
  function summary(r, item, offer, cfg) {
    const F = r.routes.flip, G = r.routes.grade, ev = F.ev, tgt = cfg.roi;
    if (r.reason === "no-data") return "No sold prices loaded yet. Edge won't guess a value, so this stays a PASS until real sales are in.";
    if (!r.scope) return `Under ${money(SCOPE_MIN)}: fees and shipping eat most of any profit, so the Deal check doesn't call it.`;
    if (r.verdict === "buy") return `Sells ${daysTxt(ev.everyDays)} near ${money(F.exit)}. At ${money(offer.ask)} you'd net about ${signed(F.profit)} (${pct(F.roi)}) after fees, tax and shipping. Don't pay more than ${money(F.max)}${offer.shipIn ? ` plus the ${money(offer.shipIn)} shipping` : ""}.`;
    switch (r.reason) {
      case "evidence": return `Only ${ev.n90} sale${ev.n90 === 1 ? "" : "s"} of this exact card in 90 days: too few to trust a price.`;
      case "liquidity": return `Only ${ev.n30} sold in the last 30 days: it could take a while to resell.`;
      case "fresh": {
        if (r.fetchAge != null && r.fetchAge <= MAX_FETCH_AGE && ev.saleAge != null) return `The last sale of this exact card was ${ev.saleAge} days ago: it rarely sells, so a quick resale is unlikely.`;
        const g = F.gates.find((x) => x.code === "fresh"); return `The sales data is too old to trust: ${g ? g.text.charAt(0).toLowerCase() + g.text.slice(1) : "check the dates"}. Refresh it.`; }
      case "spread": return "Sold prices are all over the place (mixed conditions or listings), so there's no reliable value.";
      case "agree": return item.tcg ? `TCGplayer (${money(item.tcg)}) and eBay sold (${money(ev.m90)}) disagree by more than ${MAX_DISAGREE}%. Find out which is right before buying.` : "Only one price source, so the value can't be cross-checked.";
      case "trend": return "Prices are falling or a tested warning is on. Wait.";
      case "margin": return `At ${money(offer.ask)} you'd net ${signed(F.profit)} (${pct(F.roi)}), under your ${tgt}% target. ${F.max ? `Pay ${money(F.max)} or less${offer.shipIn ? ` plus the ${money(offer.shipIn)} shipping` : ""}.` : "No price works at this resale value."}${r.gradeClears ? ` Grading might pay (expected ${signed(G.profit)}), but that bets on the grade.` : ""}`;
      default: return r.why;
    }
  }

  /* a card the owner already holds: sell now, grade, or keep (facts at today's sold prices, not a forecast) */
  function own(item, data, holding, cfg, ctx = {}) {
    const offer = { ask: holding.cost || 0, cond: holding.cond || "NM", shipIn: 0, taxIn: 0 };
    const r = check(item, data, offer, cfg, ctx), F = r.routes.flip, G = r.routes.grade;
    const out = { r, offer, label: "unknown", text: "", proceeds: F.proceeds, profit: F.profit, gradeProfit: G ? G.profit : null };
    if (r.reason === "no-data") { out.text = "No sold prices loaded."; return out; }
    const weak = F.gates.find((x) => ["evidence", "liquidity", "fresh", "spread"].includes(x.code) && !x.ok);
    if (weak) { out.label = "unclear"; out.text = `Not enough reliable sales to value it: ${weak.text.charAt(0).toLowerCase() + weak.text.slice(1)}.`; return out; }
    const falling = F.gates.find((x) => x.code === "trend" && !x.ok);
    if (G && G.pass && (F.profit == null || G.profit > F.profit)) { out.label = "grade"; out.text = `Grading: expected ${signed(G.profit)} vs ${signed(F.profit)} selling raw today (${Math.round(G.p10 * 100)}% PSA 10 odds).`; return out; }
    const clears = F.profit != null && F.profit >= (cfg.minProfit ?? MIN_PROFIT) && F.profit * 100 >= F.cost * cfg.roi;
    if (clears) { out.label = "sell"; out.text = `Selling now nets about ${money(F.proceeds)}: ${signed(F.profit)} over what you paid${falling ? ", and prices are slipping" : ""}.`; return out; }
    out.label = "hold"; out.text = `Selling now nets about ${money(F.proceeds)} (${signed(F.profit)} vs what you paid), under your ${cfg.roi}% target.`;
    return out;
  }

  /* ---------- the panel ---------- */
  const CONF = { A: "deep, fresh, consistent sales that agree with TCGplayer", B: "enough fresh, consistent sales that agree with TCGplayer", C: "one evidence check misses", D: "two or more evidence checks miss" };
  const ROUTE = { flip: "Resell", grade: "Grade, then sell" };
  const gateList = (gs) => `<ul class="dl-gates">${gs.map((x) => `<li class="${x.ok ? "ok" : x.hard ? "no" : "info"}"><i aria-hidden="true">${x.ok ? "✓" : x.hard ? "✕" : "•"}</i><span>${esc(x.text)}</span></li>`).join("")}</ul>`;
  const ageTxt = (n) => n == null ? "" : n <= 0 ? "today" : n === 1 ? "yesterday" : `${n} days ago`;
  // state: { status: "idle" | "loading" | "ready" | "error" | "off", note }
  function html(r, item, data, offer, cfg, state = {}) {
    const F = r.routes.flip, G = r.routes.grade, H = r.routes.hold, ev = F.ev, none = r.reason === "no-data";
    const head = r.verdict === "buy" ? `<div class="dl-call dl-buy"><b>BUY candidate</b><span>${esc(ROUTE[r.route])}</span></div>`
      : `<div class="dl-call dl-pass"><b>PASS</b><span>${esc(r.why)}</span></div>`;
    const st = state.status || (data ? "ready" : "idle");
    const badge = st === "loading" ? "Getting sold prices…" : data && data.asOf != null ? `Sold prices read ${ageTxt(cfg.today - data.asOf)}` : st === "off" ? "Sold prices not set up" : "No sold prices yet";
    const btn = state.canLoad ? `<button type="button" class="btn sm dl-load"${st === "loading" ? " disabled" : ""}>${data ? "Refresh sold prices" : "Get sold prices"}</button>` : "";
    const tile = (lab, val, sub, cls = "") => `<div class="tile"><span class="lab">${lab}</span><b class="${cls}">${val}</b><small>${sub}</small></div>`;
    return `<div class="dl-head"><span class="lab">Deal check</span><span class="dl-beta">${esc(badge)}</span></div>
      <form class="dl-form" onsubmit="return false">
        <label class="f">Price $<input class="field dl-ask" type="number" inputmode="decimal" min="0" step="0.01" value="${(offer.ask / 100).toFixed(2)}"></label>
        <label class="f">Shipping to you $<input class="field dl-ship" type="number" inputmode="decimal" min="0" step="0.01" value="${((offer.shipIn || 0) / 100).toFixed(2)}"></label>
        ${item.t === "c" ? `<label class="f dl-full">Condition<select class="select dl-cond">${Object.keys(COND).map((c) => `<option${c === offer.cond ? " selected" : ""}>${c}</option>`).join("")}</select></label>` : ""}
      </form>
      ${head}
      <p class="dl-sum">${esc(summary(r, item, offer, cfg))}</p>
      <div class="prices dl-tiles">${tile("Resale value", F.exit ? money(F.exit) : "—", F.exit ? `${ev.n30}${ev.capped ? "+" : ""} sold in 30 days` : "no sold data")}
        ${tile("Net profit", F.profit != null ? signed(F.profit) : "—", F.profit != null ? `${pct(F.roi)} after costs` : "needs sold data", F.profit > 0 ? "up" : F.profit < 0 ? "down" : "")}
        ${tile("Max to pay", F.max ? money(F.max) : "—", F.max ? `for ${cfg.roi}% profit` : "—")}</div>
      ${btn || state.note ? `<div class="dl-data">${btn}${state.note ? `<p class="dl-note">${esc(state.note)}</p>` : ""}</div>` : ""}
      ${none ? "" : `<div class="chips"><span class="chip dl-conf dl-conf-${r.confidence}" title="${esc(CONF[r.confidence])}">Evidence: ${r.confidence}</span>
        <span class="chip">${esc(daysTxt(ev.everyDays) || "no sales in 30 days")}</span>${G && G.pass ? `<span class="chip">Grading might pay</span>` : ""}</div>`}
      <details class="dl-more"${state.open ? " open" : ""}><summary>Why, sold comps and costs</summary>
      ${none ? `<p class="dl-note">No sold prices are loaded for this card. Edge never fills in a price it doesn't have.${item.tcg ? ` TCGplayer market is ${money(item.tcg)}, but a market price alone isn't a sale.` : ""}</p>` : `
      ${gateList(F.gates)}
      <span class="lab">Sold comps · ${esc(F.grade)} · this exact printing</span>
      <div class="kv"><div><span>Median, last 30 days${ev.capped ? " (newest sales)" : ""}</span><span>${F.ev.m30 ? money(F.ev.m30) : "—"} <small>(${ev.n30}${ev.capped ? "+" : ""} sold)</small></span></div>
        <div><span>Median, last 90 days${ev.capped ? " (newest sales)" : ""}</span><span>${money(ev.m90)} <small>(${ev.n90}${ev.capped ? "+" : ""} sold)</small></span></div>
        <div><span>Middle half of 90 days</span><span>${ev.q1 != null ? `${money(ev.q1)} – ${money(ev.q3)}` : "—"}</span></div>
        <div><span>Newest sale</span><span>${ev.saleAge != null ? ageTxt(ev.saleAge) : "—"}</span></div>
        ${ev.inexact ? `<div><span>Sales shared with other printings (left out)</span><span>${ev.inexact}</span></div>` : ""}
        ${item.tcg ? `<div><span>TCGplayer market (second source)</span><span>${money(item.tcg)}</span></div>` : ""}</div>
      <span class="lab">${item.t === "s" ? "Resell" : "Resell raw"} · after every cost</span>
      <div class="kv">${F.exit ? `<div><span>Sale at the resale value${item.t === "c" && offer.cond !== "NM" ? ` (${offer.cond})` : ""}</span><span>${money(F.exit)}</span></div>
        <div><span>Marketplace fee (on price + ${cfg.buyerTax || 0}% buyer tax)</span><span>−${money(fee(cfg.fees, F.exit, cfg.buyerTax || 0))}</span></div>
        <div><span>Shipping out + supplies</span><span>−${money((cfg.shipOut ? cfg.shipOut(F.exit, item.t) : 0) + (cfg.supplies ? cfg.supplies(item.t) : 0))}</span></div>
        <div><span>Your cost (price, ${offer.taxIn || 0}% tax, shipping)</span><span>−${money(F.cost)}</span></div>
        <div><span><b>Net profit</b></span><span><b class="${F.profit > 0 ? "up" : "down"}">${signed(F.profit)}</b> <small>${pct(F.roi)}</small></span></div>` : `<div><span>No exact sold price on record</span><span>—</span></div>`}</div>
      ${G && (G.e10.n90 || (data && data.pop)) ? `<span class="lab">Grade, then sell · ${G.pass ? "might pay (information only)" : "does not clear"}</span>
        <div class="kv">${G.expected != null ? `<div><span>Expected sale net (PSA 10 ${(G.p10 * 100).toFixed(0)}% · 9 ${(G.p9 * 100).toFixed(0)}% · lower ${((1 - G.p10 - G.p9) * 100).toFixed(0)}%)</span><span>${money(G.expected)}</span></div>
          <div><span>Cost with grading and ${G.months} months of money</span><span>−${money(G.cost)}</span></div>
          <div><span><b>Expected net</b></span><span><b class="${G.profit > 0 ? "up" : "down"}">${signed(G.profit)}</b> <small>${pct(G.roi)}</small></span></div>` : `<div><span>Not enough data for an expected value</span><span>—</span></div>`}
          ${data && data.pop ? `<div><span>PSA population${data.pop.asOf != null ? `, updated ${ageTxt(cfg.today - data.pop.asOf)}` : ""}</span><span>${data.pop.total.toLocaleString("en-US")}</span></div>` : ""}</div>
        ${gateList(G.gates)}` : ""}
      ${H ? `<span class="lab">Hold · information only</span><p class="dl-note">To break even after fees and ${cfg.holdRate || 0}% a month cost of money, ${H.m12 > 0 ? `the sold price has to rise ${pct(H.m6, 1)} in 6 months or ${pct(H.m12, 1)} in 12` : "today's resale value already covers 12 months"}. Edge makes no hold call yet.</p>` : ""}
      ${data && data.source ? `<p class="dl-note">Source: ${esc(data.source)}.</p>` : ""}`}
      </details>
      <p class="dl-foot">PASS unless every check clears. "BUY candidate" means real sold prices support this price, not that the price will rise. Check the copy and live listings before you buy. Market data, not financial advice.</p>`;
  }
  /* hooks.load(fresh) → Promise<{ ok, data, note }>; without hooks the panel only reads `data` */
  function mount(root, item, data, offer, cfg, ctx = {}, hooks = null) {
    const state = { status: data ? "ready" : hooks && hooks.load ? "idle" : (hooks && hooks.off ? "off" : "idle"), canLoad: !!(hooks && hooks.load), note: hooks && hooks.note || "", open: false };
    let last = null;
    const draw = () => {
      const r = check(item, data, offer, cfg, ctx);
      const det = root.querySelector(".dl-more"); if (det) state.open = det.open;
      root.classList.add("dl"); root.dataset.verdict = r.verdict; root.dataset.reason = r.reason || ""; root.innerHTML = html(r, item, data, offer, cfg, state);
      const a = root.querySelector(".dl-ask"), s = root.querySelector(".dl-ship"), c = root.querySelector(".dl-cond"), b = root.querySelector(".dl-load");
      const num = (el) => Math.max(0, Math.round((parseFloat(el.value) || 0) * 100));
      if (a) a.onchange = () => { offer.ask = num(a); draw(); };
      if (s) s.onchange = () => { offer.shipIn = num(s); draw(); };
      if (c) c.onchange = () => { offer.cond = c.value; draw(); };
      if (b) b.onclick = async () => {
        state.status = "loading"; state.note = ""; draw();
        let res; try { res = await hooks.load(!!data); } catch (e) { res = { ok: false, note: "Couldn't get sold prices." }; }
        if (res && res.ok) { data = res.data; state.status = "ready"; } else state.status = "error";
        state.note = (res && res.note) || ""; draw();
      };
      last = r; return r;
    };
    draw();
    return { get result() { return last; }, redraw: draw };
  }

  const api = { v: VERSION, check, own, summary, mount, html, comps, fee, netSale, costIn, maxAsk, median, rank, COND,
    K: { SCOPE_MIN, MIN_COMPS, MIN_SALES_30, MAX_FETCH_AGE, MAX_SALE_AGE, MAX_SPREAD, MAX_DISAGREE, FALLING, MIN_PROFIT, GRADE_MIN_POP, GRADE_MIN_SALES_30, LOWER_GRADES } };
  if (typeof window !== "undefined") window.EdgeDeal = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
