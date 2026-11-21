/* DYS Edge — Card-show buy list (Nov 20, 2026; Keo's step 1 of local and card-show buying).
   Before a show: pick cards, read their recent sold prices once within a credit budget, and keep on the phone what is
   needed at the table: a walk-away price per condition, a suggested opening offer, a resale range, the evidence grade and
   when it was checked. At the table: type the seller's price and cash on hand; the saved estimate says whether it fits
   the owner's rules. Only a live Deal check (Show check, fresh sold prices) can call anything a BUY candidate.

   What is saved (localStorage "dys-edge-buylist"): our own derived numbers, rounded so that no exact sold price can be
   worked back from them — the walk-away is the engine's max to pay floored to a step ($1 under $20, $2.50 under $50, $5
   above), the resale value is a band ($5 / $10 / $25 wide), sales pace is a count band, the evidence grade a letter.
   Not saved: sold prices, medians, comps, exact profits or the exact max (PkmnPrices data stays in memory). Estimates are
   dropped after 7 days; after 3 days they are shown but never used for a rules result.
   No dependencies: node tests/edge_buylist.test.js */
(() => {
  "use strict";
  const VERSION = 1, H = 36e5, DAY = 864e5;
  const KEY = "dys-edge-buylist";
  const FRESH_H = 24;          // checked within a day: an estimate you can plan with
  const USE_H = 72;            // up to 3 days: shown with a stale warning; older: shown greyed, no rules result
  const KEEP_D = 7;            // derived numbers dropped after a week (the card stays on the list)
  const MAX_ITEMS = 60;
  const CREDITS_PER_CARD = 101;   // worst case: the card lookup + 5 pages of 20 raw sales (edge-pkmn PAGE, MAX_PAGES.raw)
  const CONDS = ["NM", "LP", "MP"];
  const OPEN_SHARE = 0.8;      // opening offer: 80% of the walk-away, whole dollars (a negotiation habit, not a valuation)

  const step = (c) => c < 2000 ? 100 : c < 5000 ? 250 : 500;
  const floorTo = (c) => c == null || !isFinite(c) || c <= 0 ? null : Math.floor(c / step(c)) * step(c);
  function resaleBand(exit) {
    if (exit == null || !isFinite(exit) || exit <= 0) return null;
    const w = exit < 2000 ? 500 : exit < 10000 ? 1000 : 2500, lo = Math.floor(exit / w) * w;
    return [lo, lo + w];
  }
  const paceBand = (n) => n == null ? null : n <= 0 ? "0" : n <= 2 ? "1–2" : n <= 6 ? "3–6" : n <= 14 ? "7–14" : "15+";
  const opening = (walk) => {
    if (!walk) return null;
    const o = Math.max(100, Math.floor(walk * OPEN_SHARE / 100) * 100);
    return o >= walk ? Math.max(0, walk - 100) || null : o;
  };
  // why a card has no walk-away: fixed texts, never amounts
  const ISSUE = {
    "no-data": "No sold prices found for this exact card.",
    evidence: "Not enough reliable recent sales to value it.", liquidity: "Sells too rarely for a quick resale.",
    fresh: "No recent sales.", spread: "Sold prices are too scattered to trust.",
    agree: "Sold prices and TCGplayer disagree by more than 25%.", trend: "Sold prices are falling.",
    margin: "No price clears $5 and 20% after fees.", scope: "Worth under $20: outside the Deal check.",
    "not-found": "PkmnPrices doesn't have this exact item.", error: "The sold-price check failed. Try again.",
  };

  /* the saved estimate for one card from a fresh sold-price read (memory only) and the engine.
     cfg: the Deal check settings; its budget's cash and reserve are left out on purpose (they are decided at the table). */
  function derive(deal, item, data, cfg, now = Date.now()) {
    const base = { ...cfg, budget: cfg.budget && cfg.budget.limit ? { limit: cfg.budget.limit } : null };
    const est = { at: now, tcg: item.tcg || null, grade: null, pace: null, resale: null, walk: {}, issue: null };
    if (!data || !(data.comps || []).length) { est.issue = "no-data"; return est; }
    let first = null;
    for (const cond of CONDS) {
      const probe = deal.check(item, data, { ask: 100, cond, shipIn: 0, taxIn: 0 }, base);
      const F = probe.routes && probe.routes.flip;
      if (cond === "NM") {
        first = probe;
        est.grade = probe.confidence || null;
        est.pace = F && F.ev ? paceBand(F.ev.n30) : null;
        est.resale = F ? resaleBand(F.exit) : null;
      }
      const max = F && F.max > 0 ? F.max : 0;
      if (!max) { if (cond === "NM") est.issue = probe.reason || "margin"; continue; }
      // the walk-away must itself clear every check (sales, freshness, spread, agreement, trend, $5 and 20%, the limit)
      const at = deal.check(item, data, { ask: max, cond, shipIn: 0, taxIn: 0 }, base);
      if (at.verdict === "buy") { const w = floorTo(max); if (w) est.walk[cond] = w; }
      else if (cond === "NM") est.issue = at.reason || "margin";
    }
    if (!est.walk.NM && !est.issue) est.issue = (first && first.reason) || "margin";
    if (est.walk.NM) est.issue = null;
    return est;
  }

  const ageH = (est, now = Date.now()) => est && est.at ? (now - est.at) / H : null;
  function ageState(est, now = Date.now()) {
    const h = ageH(est, now);
    if (h == null) return "none";
    if (h < 0) return "expired";                   // a clock in the future: don't trust it
    return h < FRESH_H ? "fresh" : h < USE_H ? "stale" : "expired";
  }
  const ageTxt = (est, now = Date.now()) => {
    const h = ageH(est, now); if (h == null) return "not checked";
    if (h < 1) return "checked under an hour ago";
    if (h < 24) return `checked ${Math.floor(h)} h ago`;
    const d = Math.floor(h / 24); return `checked ${d} day${d === 1 ? "" : "s"} ago`;
  };

  /* at the table, from the saved estimate only (works offline). Never a BUY: the strongest result is "fits" (an
     estimate within the walk-away that also meets the limit and the reserve); a BUY needs the live Deal check. */
  function atTable(deal, est, cond, ask, cash, cfg, t = "c", now = Date.now()) {
    const out = { state: ageState(est, now), walk: null, open: null, cost: null, limitOk: null, reserveOk: null, profit: null, roi: null, result: "none", text: "" };
    const lim = cfg.budget && cfg.budget.limit, res = cfg.budget && cfg.budget.reserve;
    if (out.state === "none") { out.text = "No saved estimate yet: check prices before the show, or verify now with live sold prices."; return out; }
    if (out.state === "expired") { out.result = "expired"; out.text = "The saved estimate is too old to use. Verify now with live sold prices."; return out; }
    out.walk = (est.walk || {})[cond] || null; out.open = opening(out.walk);
    if (ask > 0) {
      out.cost = deal.costIn(ask, { taxIn: 0, shipIn: 0 });
      out.limitOk = lim ? out.cost <= lim : true;
      out.reserveOk = res ? (cash == null ? null : cash - out.cost >= res) : true;
      if (est.resale) {
        const cm = deal.COND[cond] ?? 1;
        const p = est.resale.map((e) => deal.netSale(Math.round(e * cm), t, cfg) - out.cost);
        out.profit = p; out.roi = out.cost > 0 ? p.map((x) => x / out.cost * 100) : null;
      }
    }
    if (!out.walk) {
      out.result = "no-walk";
      out.text = est.issue ? ISSUE[est.issue] || "No price clears your rules." : CONDS.includes(cond) ? "No walk-away for this condition." : "Saved estimates cover NM, LP and MP only.";
      return out;
    }
    if (!(ask > 0)) { out.result = "need-ask"; out.text = "Type the seller's price."; return out; }
    if (ask > out.walk) { out.result = "over"; out.text = "Over your walk-away: counter at or under it, or walk away."; return out; }
    if (!out.limitOk) { out.result = "limit"; out.text = "Within the walk-away, but over your per-purchase limit."; return out; }
    if (out.reserveOk === null) { out.result = "need-cash"; out.text = "Within your walk-away. Enter your cash on hand to check your reserve."; return out; }
    if (!out.reserveOk) { out.result = "reserve"; out.text = "Within the walk-away, but it would break your cash reserve."; return out; }
    out.result = "fits";
    out.text = out.state === "fresh" ? "Fits your rules on the saved estimate. Verify with live sold prices before you pay."
      : "Fits your rules on a stale estimate. Prices may have moved: verify before you pay.";
    return out;
  }

  /* the saved list */
  const ITEM_KEYS = ["k", "id", "g", "n", "setN", "t", "r", "cond", "added", "est"];
  const EST_KEYS = ["at", "tcg", "grade", "pace", "resale", "walk", "issue"];
  const clean = (x) => {
    const o = {}; for (const k of ITEM_KEYS) if (x[k] !== undefined) o[k] = x[k];
    if (o.est) { const e = {}; for (const k of EST_KEYS) if (o.est[k] !== undefined) e[k] = o.est[k]; o.est = e; }
    return o;
  };
  function Store(ls, now = () => Date.now()) {
    const read = () => {
      let j = null; try { j = JSON.parse(ls.getItem(KEY) || "null"); } catch { j = null; }
      const items = (j && j.v === VERSION && Array.isArray(j.items) ? j.items : []).filter((x) => x && x.id && x.n).map(clean);
      for (const x of items) if (x.est && !(x.est.at > now() - KEEP_D * DAY && x.est.at <= now() + H)) delete x.est;   // a week old: numbers go
      return items;
    };
    let items = read();
    const write = () => { try { ls.setItem(KEY, JSON.stringify({ v: VERSION, items: items.map(clean) })); return true; } catch { return false; } };
    write();
    return {
      all: () => items.slice(),
      get: (k) => items.find((x) => x.k === k) || null,
      has: (k) => items.some((x) => x.k === k),
      add(x) {
        if (items.some((y) => y.k === x.k)) return false;
        if (items.length >= MAX_ITEMS) return false;
        items = [...items, clean({ k: x.k, id: x.id, g: x.g, n: x.n, setN: x.setN || "", t: x.t || "c", r: x.r || "", cond: x.cond || "NM", added: now() })];
        write(); return true;
      },
      remove(k) { items = items.filter((x) => x.k !== k); write(); },
      setCond(k, cond) { const x = items.find((y) => y.k === k); if (x) { x.cond = cond; write(); } },
      setEst(k, est) { const x = items.find((y) => y.k === k); if (x) { x.est = est; write(); } },
      clearEst() { items.forEach((x) => { delete x.est; }); write(); },
      reload() { items = read(); return items.slice(); },
    };
  }

  // which cards a run should check, oldest information first, and how many fit the budget
  function plan(items, budget, now = Date.now()) {
    const need = items.filter((x) => ageState(x.est, now) !== "fresh")
      .sort((a, b) => (a.est ? a.est.at : 0) - (b.est ? b.est.at : 0));
    const fit = Math.max(0, Math.floor((budget || 0) / CREDITS_PER_CARD));
    return { need, take: need.slice(0, fit), fit, perCard: CREDITS_PER_CARD };
  }

  const api = { v: VERSION, KEY, FRESH_H, USE_H, KEEP_D, MAX_ITEMS, CREDITS_PER_CARD, CONDS, OPEN_SHARE, ISSUE, ITEM_KEYS, EST_KEYS,
    step, floorTo, resaleBand, paceBand, opening, derive, ageH, ageState, ageTxt, atTable, Store, plan };
  if (typeof window !== "undefined") window.EdgeBuyList = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
