/* DYS Edge — Real-profit scorecard (Nov 21, 2026).
   What the owner actually made, from the Ledger only: every recorded sale's money in, selling fees, shipping paid,
   supplies, the cost of what was sold (price plus its share of tax, shipping and fees, plus costs tied to it), profit and
   ROI, grouped by where it was bought, by type (raw by condition, graded by grader and grade, sealed), by where it sold and
   by cost per copy. Expenses not tied to an item are shown apart. Nothing is estimated here.

   Edge's estimate at the time of a buy is compared only when it was recorded: a line in the item's note that Edge writes
   when a Deal check, Show check or lot offer opens the buy form ("Edge est: net $35–$40/copy (Show check · NM · B · 2026-11-21)").
   The estimate is a band (the same widths as the Buy list's resale range), never an exact sold price, so it may sit in
   the Sheet. Items with no such line are counted as "no estimate recorded" and left out of the comparison.

   Input: the Ledger's compute() result (edge-ledger.js). No dependencies: node tests/edge_score.test.js */
(() => {
  "use strict";
  const VERSION = 1;
  const DAYMS = 864e5;
  const TAG_RE = /Edge est: net \$([\d,]+(?:\.\d\d)?)[–-]\$([\d,]+(?:\.\d\d)?)\/copy(?: \(([^)]*)\))?/;
  const COST_BANDS = [[0, 2000, "Under $20"], [2000, 5000, "$20–$50"], [5000, 7500, "$50–$75"], [7500, Infinity, "$75 and up"]];
  const PERIODS = { all: null, year: "year", d90: 90, d30: 30 };

  const int = (v) => { const n = Math.round(Number(v)); return isFinite(n) ? n : 0; };
  const toC = (s) => Math.round(parseFloat(String(s).replace(/,/g, "")) * 100);
  const dayNum = (d) => d ? Math.floor(Date.parse(d + "T00:00:00Z") / DAYMS) : null;
  const fmt = (c) => `$${(c / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  /* ---------- the estimate line ---------- */
  // the band an estimate is kept in: $2 under $20, $5 under $50, $10 under $100, $25 above (as the Buy list's resale range)
  function band(c) {
    if (c == null || !isFinite(c) || c <= 0) return null;
    const w = c < 2000 ? 200 : c < 5000 ? 500 : c < 10000 ? 1000 : 2500, lo = Math.floor(c / w) * w;
    return [lo, lo + w];
  }
  // the note line for a buy, from a Deal check result (memory only) — only when the sold evidence cleared every check
  // before profit, so an estimate is never recorded from thin data. src: "Show check" | "Deal check" | "Lot offer" | ...
  const EVIDENCE = ["fresh", "evidence", "liquidity", "spread", "agree", "trend"];
  function tagFromCheck(r, cond, src, day) {
    if (!r || !r.routes || !r.routes.flip || !r.scope) return "";
    const F = r.routes.flip;
    if (EVIDENCE.some((c) => F.gates.some((g) => g.code === c && g.hard && !g.ok))) return "";
    return tagFromNet(F.proceeds, cond, src, r.confidence, day);
  }
  function tagFromNet(net, cond, src, grade, day) {
    const b = band(net); if (!b) return "";
    const bits = [src, cond, grade, day].filter(Boolean).join(" · ");
    return `Edge est: net ${fmt(b[0])}–${fmt(b[1])}/copy${bits ? ` (${bits})` : ""}`;
  }
  function parseTag(note) {
    const m = TAG_RE.exec(note || ""); if (!m) return null;
    const lo = toC(m[1]), hi = toC(m[2]);
    if (!(lo >= 0 && hi > lo)) return null;
    const bits = (m[3] || "").split(" · ").map((s) => s.trim()).filter(Boolean);
    return { lo, hi, mid: Math.round((lo + hi) / 2), src: bits[0] || "", cond: bits.find((b) => /^(NM|LP|MP|HP|DMG)$/.test(b)) || "", grade: bits.find((b) => /^[A-D]$/.test(b)) || "", day: bits.find((b) => /^\d{4}-\d{2}-\d{2}$/.test(b)) || "" };
  }
  // a note with the estimate line put in (replacing any earlier one) — the rest of the note is kept as it was
  function withTag(note, tag) {
    const rest = String(note || "").replace(TAG_RE, "").replace(/\s*·\s*$/, "").replace(/^\s*·\s*/, "").trim();
    return tag ? (rest ? `${rest} · ${tag}` : tag) : rest;
  }

  /* ---------- the scorecard ---------- */
  const zero = () => ({ sales: 0, units: 0, proceeds: 0, fees: 0, shipOut: 0, supplies: 0, other: 0, shipIn: 0, net: 0, cost: 0, profit: 0, wins: 0, held: 0, heldN: 0 });
  function addTo(g, s) {
    g.sales++; g.units += s.qty; g.proceeds += s.proceeds; g.shipIn += int(s.shipIn); g.fees += int(s.fees); g.shipOut += int(s.shipOut); g.supplies += int(s.supplies); g.other += int(s.other);
    g.net += s.net; g.cost += s.cost; g.profit += s.profit; if (s.profit > 0) g.wins++;
    if (s.held != null) { g.held += s.held; g.heldN++; }
  }
  const finish = (g) => ({ ...g, roi: g.cost > 0 ? g.profit / g.cost * 100 : null, winRate: g.sales ? g.wins / g.sales * 100 : null, avgHeld: g.heldN ? g.held / g.heldN : null,
    feeShare: g.proceeds > 0 ? g.fees / g.proceeds * 100 : null });
  function typeOf(x) {
    if (!x) return "Unknown";
    if (x.kind === "Raw") return `Raw · ${x.cond || "NM"}`;
    if (x.kind === "Graded") return `Graded · ${[x.grader || "", x.grade || ""].join(" ").trim() || "graded"}`;
    return x.kind || "Other";
  }
  const costBand = (each) => (COST_BANDS.find(([lo, hi]) => each >= lo && each < hi) || COST_BANDS[0])[2];

  /* R: compute() from edge-ledger.js. opt: { book: "All" | "Business" | "Personal", period: "all" | "year" | "d90" | "d30", today: "YYYY-MM-DD" } */
  function score(R, opt = {}) {
    const book = opt.book || "All", period = opt.period || "all", today = opt.today || new Date().toISOString().slice(0, 10);
    const t = dayNum(today), yr = today.slice(0, 4);
    const inPeriod = (d) => period === "all" ? true : period === "year" ? String(d || "").slice(0, 4) === yr : (() => { const n = dayNum(d); return n != null && n > t - PERIODS[period] && n <= t; })();
    const inBook = (b) => book === "All" || (b || "Business") === book;
    const items = new Map((R.items || []).map((x) => [x.id, x])), buys = new Map((R.buys || []).map((b) => [b.id, b]));
    const sales = (R.sales || []).filter((s) => inBook(s.book) && inPeriod(s.day));
    const tot = zero(), by = { source: new Map(), type: new Map(), plat: new Map(), cost: new Map() };
    const put = (m, k, s) => { if (!m.has(k)) m.set(k, zero()); addTo(m.get(k), s); };
    const rows = [], est = { recorded: 0, total: sales.length, rows: [], inBand: 0, above: 0, below: 0, estProfit: 0, actualProfit: 0, estNet: 0, actualNet: 0 };
    for (const s of sales) {
      const x = items.get(s.item), b = x && x.buy ? buys.get(x.buy) : null;
      addTo(tot, s);
      const src = b ? (b.where || "Other") : x ? "Before the Ledger" : "Unknown";
      put(by.source, src, s); put(by.type, typeOf(x), s); put(by.plat, s.plat || "Other", s);
      const each = s.qty ? Math.round(s.cost / s.qty) : 0; put(by.cost, costBand(each), s);
      const row = { id: s.id, day: s.day, name: s.name || (x && x.name) || "", type: typeOf(x), src, plat: s.plat || "", qty: s.qty, proceeds: s.proceeds, fees: int(s.fees), shipOut: int(s.shipOut),
        supplies: int(s.supplies), other: int(s.other), net: s.net, cost: s.cost, profit: s.profit, roi: s.cost > 0 ? s.profit / s.cost * 100 : null, held: s.held, est: null };
      // the comparison: only where Edge's estimate was recorded on the item, and only for the same condition
      const tag = x ? parseTag(x.note) : null;
      if (tag && (!tag.cond || x.kind !== "Raw" || tag.cond === (x.cond || "NM"))) {
        const perCopy = s.qty ? s.net / s.qty : 0;
        const where = perCopy < tag.lo ? "below" : perCopy > tag.hi ? "above" : "in";
        const estNet = tag.mid * s.qty, estProfit = estNet - s.cost;
        row.est = { ...tag, perCopy: Math.round(perCopy), where, estNet, estProfit, diff: s.net - estNet };
        est.recorded++; est[where === "in" ? "inBand" : where]++; est.estProfit += estProfit; est.actualProfit += s.profit; est.estNet += estNet; est.actualNet += s.net;
        est.rows.push(row);
      }
      rows.push(row);
    }
    est.error = est.estNet ? (est.actualNet - est.estNet) / est.estNet * 100 : null;
    // expenses not tied to an item, in the same period and book (grading paid upfront, supplies, table fees...)
    const expenses = (R.costs || []).filter((c) => !c.void && !c.item && inBook(c.book) && inPeriod(c.day));
    const expTotal = expenses.reduce((s2, c) => s2 + int(c.amount), 0);
    const expBy = new Map(); for (const c of expenses) expBy.set(c.kind || "Other", (expBy.get(c.kind || "Other") || 0) + int(c.amount));
    // still held (context only: not realized)
    const held = (R.items || []).filter((x) => x.left > 0 && inBook(x.book));
    const group = (m) => [...m.entries()].map(([k, g]) => ({ key: k, ...finish(g) })).sort((a, b) => b.profit - a.profit || a.key.localeCompare(b.key));
    const sorted = rows.slice().sort((a, b) => b.profit - a.profit);
    return {
      v: VERSION, book, period, today, total: finish(tot), afterExpenses: tot.profit - expTotal, expenses: { total: expTotal, by: [...expBy.entries()].sort((a, b) => b[1] - a[1]) },
      bySource: group(by.source), byType: group(by.type), byPlat: group(by.plat), byCost: COST_BANDS.map(([, , k]) => k).filter((k) => by.cost.has(k)).map((k) => ({ key: k, ...finish(by.cost.get(k)) })),
      best: sorted.filter((r) => r.profit > 0).slice(0, 5), worst: sorted.filter((r) => r.profit < 0).reverse().slice(0, 5), rows, est,
      held: { items: held.length, units: held.reduce((s2, x) => s2 + x.left, 0), cost: held.reduce((s2, x) => s2 + x.costLeft, 0) },
      warn: (R.warn || []).slice(),
    };
  }

  const api = { v: VERSION, TAG_RE, COST_BANDS, PERIODS, EVIDENCE, band, tagFromCheck, tagFromNet, parseTag, withTag, typeOf, costBand, score };
  if (typeof window !== "undefined") window.EdgeScore = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
