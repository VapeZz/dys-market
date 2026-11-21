/* DYS Edge — Binder / lot offers (Nov 21, 2026).
   Several cards offered together (a binder page, a box, a stack): what the cards would net on resale, what the lot is
   safe to pay, a conservative opening offer, and whether the price asked fits the owner's buying rules.

   Value comes only from the Deal check's own math, card by card:
     - live: fresh sold prices read this visit (memory only); each card's net per copy is the engine's conservative
       resale (lower of the 30 and 90-day sold medians, times the condition share) after the marketplace fee on price plus
       buyer tax, shipping out and supplies;
     - estimate: the saved Buy-list-style estimate (rounded, no sold prices), valued at the LOW end of its resale range.
   A card adds value only when its evidence clears every check the Deal check makes before profit (enough exact sales, sold
   in the last 30 days, fresh, consistent prices, TCGplayer agrees, not falling), it is $20+, and its printing is confirmed
   when the card comes in more than one. Anything else is flagged and counted at $0: a free extra, never assumed value.
   Copies beyond what sells in a month are counted at $0 too.

   The rules apply to the whole purchase, so a bundle can't get round them: the all-in lot price must stay within the
   per-purchase limit, keep the cash reserve, and the lot's profit must clear the minimum profit and the ROI target.
   Only a live check (every valued card read this visit) can say BUY candidate; an estimate says "fits" at most.

   What is saved (localStorage "dys-edge-lots"): the cards (id, name, set, printing, condition, quantity), the prices typed
   for the lot, and per card the same rounded estimate the Buy list keeps (edge-buylist.js; no sold prices, medians or
   exact amounts). Live sold prices and every exact result stay in memory.
   No dependencies besides the Deal check and Buy list modules passed in. node tests/edge_lot.test.js */
(() => {
  "use strict";
  const VERSION = 1, DAY = 864e5, H = 36e5;
  const KEY = "dys-edge-lots";
  const MAX_LOTS = 10, MAX_LINES = 40, MAX_QTY = 99;
  const TOP_SHARE = 0.6;          // one card carrying 60%+ of the value: say so, check that card closely
  const EVIDENCE = ["fresh", "evidence", "liquidity", "spread", "agree", "trend"];   // the Deal check's checks before profit
  const FLAG = {
    printing: "Confirm the printing: this card comes in more than one, and the price depends on it.",
    missing: "No sold prices for this exact card: counted at $0.",
    "not-checked": "Not checked yet: counted at $0 until prices are checked.",
    "too-old": "Saved estimate older than 3 days: counted at $0. Check prices again.",
    scope: "Worth under $20: outside the Deal check, counted at $0 (a free extra).",
    evidence: "Weak sales evidence: counted at $0.",
    "no-value": "Resale doesn't cover fees and shipping: counted at $0.",
  };
  const PACE_LOW = { "0": 0, "1–2": 1, "3–6": 3, "7–14": 7, "15+": 15 };

  const int = (v) => { const n = Math.round(Number(v)); return isFinite(n) ? n : 0; };
  const pos = (v) => Math.max(0, int(v));
  const uid = (rand = Math.random) => `l${Date.now().toString(36)}${Math.floor(rand() * 1e8).toString(36)}`;
  const cardKey = (x) => `${x.id}|${x.n}`;

  /* ---------- one line of the lot ----------
     line { l, k, id, g, n, setN, t, r, cond, qty, ask (cents each, optional), alts (other printings' names), prOk, est }
     live: { data } read this visit for this card, or null. bl: the Buy list module (estimates). cfg: the Deal check settings. */
  function valueLine(deal, bl, line, live, cfg, now = Date.now()) {
    const qty = Math.min(MAX_QTY, Math.max(1, int(line.qty) || 1)), cond = line.cond || "NM", t = line.t || "c";
    const out = { l: line.l, k: line.k, qty, cond, mode: "none", flags: [], why: "", unit: 0, counted: 0, value: 0, tcg: null, pace: null, grade: null, exit: null, inexact: 0 };
    // the TCGplayer price the Deal check compares with: the one read with the live sold prices, else the saved one
    const item = { id: line.id, n: line.n, name: line.n, t, tcg: (live && live.tcg) ?? line.tcg ?? (line.est && line.est.tcg) ?? null, tcgDay: (live && live.tcgDay) ?? line.tcgDay ?? null };
    const flag = (code, why) => { out.flags.push(code); if (!out.why) out.why = why || FLAG[code]; };
    if ((line.alts || []).length && !line.prOk) flag("printing");
    if (live && live.data) {
      out.mode = "live";
      const base = { ...cfg, budget: null };
      const r = deal.check(item, live.data, { ask: 100, cond, shipIn: 0, taxIn: 0 }, base), F = r.routes.flip;
      out.tcg = item.tcg; out.grade = r.confidence || null; out.exit = F.exit; out.inexact = F.ev ? F.ev.inexact : 0;
      out.pace = F.ev ? F.ev.n30 : null;
      if (r.reason === "no-data") flag("missing");
      else if (!r.scope) flag("scope");
      else {
        const miss = EVIDENCE.map((c) => F.gates.find((g) => g.code === c && g.hard && !g.ok)).find(Boolean);
        if (miss) flag("evidence", `${miss.text}: counted at $0.`);
        else if (!(F.proceeds > 0)) flag("no-value");
        else out.unit = F.proceeds;
      }
    } else {
      const est = line.est || null, st = bl.ageState(est, now);
      out.tcg = est ? est.tcg : null; out.grade = est ? est.grade : null;
      if (st === "none") flag("not-checked");
      else if (st === "expired") flag("too-old");
      else {
        out.mode = "estimate"; out.stale = st === "stale";
        out.pace = est.pace != null && est.pace in PACE_LOW ? PACE_LOW[est.pace] : null;
        const evOk = !!(est.walk && est.walk.NM) || est.issue === "margin";
        if (est.issue === "scope") flag("scope");
        else if (est.issue === "no-data" || est.issue === "not-found") flag("missing");
        else if (!evOk) flag("evidence", `${(bl.ISSUE[est.issue] || "Weak sales evidence.").replace(/\.$/, "")}: counted at $0.`);
        else if (!est.resale) flag("missing");
        else {
          const cm = t === "s" ? 1 : deal.COND[cond] ?? 1;
          const low = Math.round(est.resale[0] * cm);           // the low end of the saved resale range: conservative
          out.exit = low;
          const u = deal.netSale(low, t, cfg);
          if (u > 0) out.unit = u; else flag("no-value");
        }
      }
    }
    if (out.flags.length) out.unit = 0;
    // copies beyond about a month of sales aren't counted: a quick resale is the point
    out.counted = out.unit > 0 ? (out.pace == null ? qty : Math.min(qty, Math.max(1, out.pace))) : 0;
    if (out.unit > 0 && out.counted < qty) out.slow = qty - out.counted;
    out.value = out.unit * out.counted;
    return out;
  }

  /* ---------- the whole lot ----------
     lot { askMode: "total" | "each", total, shipIn, taxIn (percent), lines }
     liveOf(k) → { data } | null. cfg.budget { limit, reserve, cash }. */
  function evaluate(deal, bl, lot, liveOf, cfg, now = Date.now()) {
    const lines = lot.lines || [];
    const rows = lines.map((x) => valueLine(deal, bl, x, liveOf ? liveOf(x.k) : null, cfg, now));
    const out = { rows, n: lines.length, copies: rows.reduce((s, r) => s + r.qty, 0), value: 0, ask: null, cost: null, profit: null, roi: null,
      max: 0, maxRules: 0, walk: null, open: null, capBy: null, result: "empty", mode: "none", text: "", top: [], flagged: [], notes: [] };
    if (!lines.length) { out.text = "Add the cards in the lot."; return out; }
    out.value = rows.reduce((s, r) => s + r.value, 0);
    const valued = rows.filter((r) => r.value > 0);
    out.flagged = rows.filter((r) => r.flags.length);
    // live only when every card that could add value was read live; one estimate makes the whole lot an estimate
    const needData = rows.filter((r) => !(r.flags.length === 1 && r.flags[0] === "printing"));
    out.mode = valued.length && needData.every((r) => r.mode === "live") ? "live" : valued.length ? "estimate" : rows.some((r) => r.mode === "live") ? "live" : "none";
    out.top = valued.slice().sort((a, b) => b.value - a.value).map((r) => ({ l: r.l, k: r.k, value: r.value, share: out.value ? r.value / out.value : 0 }));
    if (out.top.length > 1 && out.top[0].share >= TOP_SHARE) out.notes.push("top");
    if (rows.some((r) => r.slow)) out.notes.push("slow");
    if (rows.some((r) => r.stale)) out.notes.push("stale");
    // the price asked
    if (lot.askMode === "each") {
      const missing = lines.filter((x) => !(pos(x.ask) > 0));
      out.ask = missing.length ? null : lines.reduce((s, x) => s + pos(x.ask) * Math.min(MAX_QTY, Math.max(1, int(x.qty) || 1)), 0);
      out.askMissing = missing.length;
    } else out.ask = pos(lot.total) > 0 ? pos(lot.total) : null;
    const offer = { taxIn: Math.max(0, +lot.taxIn || 0), shipIn: pos(lot.shipIn) };
    const B = cfg.budget || {}, lim = B.limit || Infinity, res = B.reserve || 0, cash = B.cash;
    let cap = lim, capBy = isFinite(lim) ? "limit" : null;
    if (res && cash != null && cash - res < cap) { cap = Math.max(0, cash - res); capBy = "reserve"; }
    const minP = cfg.minProfit ?? deal.K.MIN_PROFIT;
    out.maxRules = out.value > 0 ? deal.maxAsk(out.value, offer, cfg.roi, minP) : 0;
    out.max = out.value > 0 ? deal.maxAsk(out.value, offer, cfg.roi, minP, cap) : 0;
    out.capBy = out.max < out.maxRules ? capBy : null;
    out.walk = bl.floorTo(out.max);                      // rounded down like the Buy list's walk-away
    out.open = out.walk ? bl.opening(out.walk) : null;
    if (out.ask != null) {
      out.cost = deal.costIn(out.ask, offer);
      out.profit = out.value - out.cost; out.roi = out.cost > 0 ? out.profit / out.cost * 100 : null;
      out.limitOk = out.cost <= lim;
      out.reserveOk = !res ? true : cash == null ? null : cash - out.cost >= res;
      out.marginOk = out.profit >= minP && out.profit * 100 >= out.cost * cfg.roi;
    }
    // the verdict, clearest reason first
    const est = out.mode !== "live";
    if (!valued.length && rows.some((r) => r.flags.includes("not-checked") || r.flags.includes("too-old"))) { out.result = "need-prices"; out.text = "Check sold prices first (step 2): until a card is checked it counts $0."; return out; }
    if (!valued.length) { out.result = "no-value"; out.text = "No card in this lot has sold-price evidence strong enough to count. Don't pay for value Edge can't confirm."; return out; }
    if (out.ask == null) { out.result = "need-ask"; out.text = lot.askMode === "each" ? `Type the seller's price for every card (${out.askMissing} missing), or switch to one total.` : "Type the seller's total for the lot."; return out; }
    if (!out.marginOk) { out.result = "over"; out.text = out.walk ? `The lot doesn't clear ${fmt(minP)} and ${cfg.roi}% at this price. Counter at ${fmt(out.walk)} or less.` : `No price for this lot clears ${fmt(minP)} and ${cfg.roi}% within your rules.`; return out; }
    if (!out.limitOk) { out.result = "limit"; out.text = "The numbers work, but the whole lot is over your per-purchase limit. A bundle can't go over it: buy fewer cards or walk away."; return out; }
    if (out.reserveOk === null) { out.result = "need-cash"; out.text = "Enter your cash on hand to check your reserve."; return out; }
    if (!out.reserveOk) { out.result = "reserve"; out.text = "Paying this would break your cash reserve."; return out; }
    if (est) { out.result = "fits"; out.text = "Fits your rules on saved estimates. Check the lot live before you pay."; return out; }
    out.result = "buy"; out.text = "BUY candidate: every counted card was checked on today's sold prices and the whole lot clears your rules.";
    return out;
  }
  const fmt = (c) => `$${(c / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  /* ---------- a Ledger buy for a lot he bought ----------
     paid: the total paid (cents). Each card's cost is its share of the price: by the seller's per-card prices when he typed
     one for every card, else by TCGplayer market × condition × qty (the same basis for every card, so a $0 extra still
     carries a cost); the shares add up exactly.
     opt.rows (evaluate()'s rows) and opt.tag(net, cond, src, grade, day) (edge-score.js): each counted card's note gets
     Edge's estimate as a band, so the scorecard can compare it with what the card really sold for. */
  function ledgerDraft(deal, lot, paid, opt = {}) {
    const lines = (lot.lines || []).map((x) => ({ x, qty: Math.min(MAX_QTY, Math.max(1, int(x.qty) || 1)) }));
    const asks = lot.askMode === "each" && lines.length && lines.every(({ x }) => pos(x.ask) > 0);
    const w = lines.map(({ x, qty }) => {
      if (asks) return pos(x.ask) * qty;
      const m = x.tcg ?? (x.est && x.est.tcg) ?? 0, cm = (x.t || "c") === "s" ? 1 : deal.COND[x.cond || "NM"] ?? 1;
      return Math.max(1, Math.round(m * cm)) * qty;
    });
    const rowOf = new Map((opt.rows || []).map((r) => [r.l, r]));
    const shares = split(pos(paid), w);
    const out = [];
    lines.forEach(({ x, qty }, i) => {
      const r = rowOf.get(x.l), tag = r && r.unit > 0 && opt.tag ? opt.tag(r.unit, x.cond || "NM", r.mode === "live" ? "Lot offer" : "Lot offer est.", r.grade, opt.day) : "";
      const base = { kind: (x.t || "c") === "s" ? "Sealed" : "Raw", tcg: x.id, g: x.g, n: x.n, name: x.n, set: x.setN || "", cond: x.cond || "NM", ...(tag ? { note: tag } : {}) };
      const each = Math.floor(shares[i] / qty), rest = shares[i] - each * qty;
      // a share that doesn't divide by the quantity: one copy carries the extra cents, so the buy adds up to the cent
      if (rest && qty > 1) { out.push({ ...base, qty: qty - 1, price: each }); out.push({ ...base, qty: 1, price: each + rest }); }
      else out.push({ ...base, qty, price: each + rest });
    });
    return { where: opt.where || "Card show", pay: opt.pay || "Cash", from: opt.from || "", ship: pos(lot.shipIn), tax: Math.round(pos(paid) * Math.max(0, +lot.taxIn || 0) / 100),
      note: `Lot${lot.name ? `: ${lot.name}` : ""} (${out.reduce((s, l) => s + l.qty, 0)} cards, Edge lot offer)`, lines: out };
  }
  // largest remainder: parts add up to the amount exactly
  function split(amount, weights) {
    const tot = weights.reduce((s, x) => s + x, 0);
    if (!weights.length) return [];
    const raw = weights.map((x) => tot ? amount * x / tot : amount / weights.length), out = raw.map(Math.floor);
    let rest = amount - out.reduce((s, x) => s + x, 0);
    raw.map((x, i) => [x - Math.floor(x), i]).sort((a, b) => b[0] - a[0] || a[1] - b[1]).forEach(([, i]) => { if (rest > 0) { out[i]++; rest--; } });
    return out;
  }

  /* ---------- the saved lots ---------- */
  const LOT_KEYS = ["id", "name", "created", "askMode", "total", "shipIn", "taxIn", "lines"];
  const LINE_KEYS = ["l", "k", "id", "g", "n", "setN", "t", "r", "cond", "qty", "ask", "alts", "prOk", "tcg", "tcgDay", "est"];
  function cleanLine(x, EST_KEYS) {
    const o = {}; for (const k of LINE_KEYS) if (x[k] !== undefined) o[k] = x[k];
    o.qty = Math.min(MAX_QTY, Math.max(1, int(o.qty) || 1));
    if (o.ask != null) o.ask = pos(o.ask) || undefined;
    if (o.alts) o.alts = (Array.isArray(o.alts) ? o.alts : []).filter((s) => typeof s === "string").slice(0, 8);
    if (o.est) { const e = {}; for (const k of EST_KEYS) if (o.est[k] !== undefined) e[k] = o.est[k]; o.est = e; }
    return o;
  }
  function cleanLot(x, EST_KEYS) {
    const o = {}; for (const k of LOT_KEYS) if (x[k] !== undefined) o[k] = x[k];
    o.askMode = o.askMode === "each" ? "each" : "total";
    o.total = pos(o.total) || undefined; o.shipIn = pos(o.shipIn) || undefined;
    o.taxIn = Math.min(20, Math.max(0, +o.taxIn || 0)) || undefined;
    o.lines = (Array.isArray(o.lines) ? o.lines : []).filter((l) => l && l.id && l.n).slice(0, MAX_LINES).map((l) => cleanLine(l, EST_KEYS));
    return o;
  }
  function Store(ls, bl, now = () => Date.now(), rand = Math.random) {
    const EK = bl.EST_KEYS;
    const read = () => {
      let j = null; try { j = JSON.parse(ls.getItem(KEY) || "null"); } catch { j = null; }
      const lots = (j && j.v === VERSION && Array.isArray(j.lots) ? j.lots : []).filter((x) => x && x.id).slice(0, MAX_LOTS).map((x) => cleanLot(x, EK));
      for (const lot of lots) for (const x of lot.lines) if (x.est && !(x.est.at > now() - bl.KEEP_D * DAY && x.est.at <= now() + H)) delete x.est;
      return lots;
    };
    let lots = read();
    const write = () => { try { ls.setItem(KEY, JSON.stringify({ v: VERSION, lots: lots.map((x) => cleanLot(x, EK)) })); return true; } catch { return false; } };
    write();
    const lot = (id) => lots.find((x) => x.id === id) || null;
    const touch = (id, fn) => { const L = lot(id); if (!L) return false; const r = fn(L); write(); return r === undefined ? true : r; };
    return {
      all: () => lots.map((x) => ({ ...x, lines: x.lines.slice() })),
      get: (id) => { const L = lot(id); return L ? { ...L, lines: L.lines.map((x) => ({ ...x })) } : null; },
      create(name) {
        if (lots.length >= MAX_LOTS) return null;
        const L = cleanLot({ id: `lot${now().toString(36)}${Math.floor(rand() * 1e6).toString(36)}`, name: String(name || "").slice(0, 60), created: now(), askMode: "total", lines: [] }, EK);
        lots = [L, ...lots]; write(); return L.id;
      },
      remove(id) { lots = lots.filter((x) => x.id !== id); write(); },
      set: (id, patch) => touch(id, (L) => { for (const k of ["name", "askMode", "total", "shipIn", "taxIn"]) if (k in patch) L[k] = patch[k]; Object.assign(L, cleanLot(L, EK)); }),
      addLine: (id, c) => touch(id, (L) => {
        if (L.lines.length >= MAX_LINES) return false;
        L.lines.push(cleanLine({ l: uid(rand), k: cardKey(c), id: c.id, g: c.g, n: c.n, setN: c.setN || "", t: c.t || "c", r: c.r || "", cond: c.cond || "NM", qty: c.qty || 1,
          alts: c.alts || [], prOk: !(c.alts || []).length, tcg: c.tcg ?? undefined, tcgDay: c.tcgDay ?? undefined,
          est: c.est || (L.lines.find((y) => y.k === cardKey(c)) || {}).est }, EK));
        return true;
      }),
      setLine: (id, l, patch) => touch(id, (L) => {
        const x = L.lines.find((y) => y.l === l); if (!x) return false;
        for (const k of ["cond", "qty", "ask", "prOk"]) if (k in patch) x[k] = patch[k];
        Object.assign(x, cleanLine(x, EK));
      }),
      removeLine: (id, l) => touch(id, (L) => { L.lines = L.lines.filter((y) => y.l !== l); }),
      // an estimate belongs to the card: every line of that card in the lot gets it
      setEst: (id, k, est, tcg) => touch(id, (L) => { for (const x of L.lines) if (x.k === k) { x.est = est; if (tcg != null) x.tcg = tcg; } }),
      reload() { lots = read(); return this.all(); },
    };
  }

  // which cards a price check should read (distinct cards with no usable fresh estimate, oldest first) within a budget
  function plan(bl, lot, budget, now = Date.now(), have = () => false) {
    const seen = new Set(), need = [];
    for (const x of (lot.lines || []).slice().sort((a, b) => (a.est ? a.est.at : 0) - (b.est ? b.est.at : 0))) {
      if (seen.has(x.k)) continue; seen.add(x.k);
      if (have(x.k) || bl.ageState(x.est, now) === "fresh") continue;
      need.push(x);
    }
    const fit = Math.max(0, Math.floor((budget || 0) / bl.CREDITS_PER_CARD));
    return { need, take: need.slice(0, fit), fit, perCard: bl.CREDITS_PER_CARD };
  }
  // distinct cards a live check still has to read
  const liveNeed = (lot, have) => { const s = new Set(); return (lot.lines || []).filter((x) => !have(x.k) && !s.has(x.k) && s.add(x.k)); };

  const api = { v: VERSION, KEY, MAX_LOTS, MAX_LINES, MAX_QTY, TOP_SHARE, EVIDENCE, FLAG, PACE_LOW, LOT_KEYS, LINE_KEYS,
    cardKey, valueLine, evaluate, ledgerDraft, split, Store, plan, liveNeed };
  if (typeof window !== "undefined") window.EdgeLot = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
