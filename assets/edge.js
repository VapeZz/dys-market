"use strict";
/* DYS Edge: a private buy / sell / trade desk on top of the market site's nightly data
   (TCGplayer market prices, our own price history, eBay Buy It Now listings with their age).
   Holdings, watchlist, trades, lots and settings are kept on this device (with a backup file). */
(() => {
  // the app lives in /edge/ (its own install scope); site files are one folder up
  const BASE = /\/edge\/(index\.html)?$/.test(location.pathname) ? "../" : "";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  // the card sheet's technical chart is its own file (edge-ta.js); it takes this file's ?v= so both refresh together.
  // If it can't load, the sheet draws the simple chart below instead.
  const VER = ((document.currentScript?.src || "").match(/\?v=[\w.-]+/) || [""])[0];
  const part = (file, name) => new Promise((done) => {
    const s = document.createElement("script");
    s.src = `${BASE}assets/${file}${VER}`;
    s.onload = () => done(window[name]?.v >= 1 ? window[name] : null); s.onerror = () => done(null);
    document.head.append(s);
  });
  const TA = part("edge-ta.js", "EdgeTA");
  // the strategy box under the price tiles (edge-strat.js) reads the chart's numbers; without the chart or the file there is no box
  const STRAT = part("edge-strat.js", "EdgeStrat");
  // the Deal check (edge-deal.js, M1) and its live sold prices (edge-pkmn.js): PkmnPrices read on demand through the
  // owner's relay, kept in this page's memory only. Without a relay the panel says so and stays a PASS.
  const DEAL = part("edge-deal.js", "EdgeDeal");
  const PKMN = part("edge-pkmn.js", "EdgePkmn");
  // sold prices for a graded card the owner holds (edge-graded.js): that exact grader and grade only, never raw or other grades
  const GRADED = part("edge-graded.js", "EdgeGraded");
  // where to sell? estimated profit per selling option (edge-channels.js), under the Deal check and the PSA check
  const CHAN = part("edge-channels.js", "EdgeChannels");
  // the Holdings Advisor (edge-advisor.js, P3/P4): one action per holding (sell, grade, monitor, hold, not enough data)
  // from the sold-price checks above; results live in this page's memory only, like every sold-price check
  const ADV = part("edge-advisor.js", "EdgeAdvisor");
  // the ledger (edge-ledger.js, M2): buys, sales, expenses, cash and inventory in two books, kept in the owner's Google
  // Sheet through its web app (tools/ledger/Code.gs), with a copy and a queue of changes on this phone
  const LEDGER = part("edge-ledger.js", "EdgeLedger");
  // the card-show buy list (edge-buylist.js): walk-away prices prepared before a show, kept on this phone as rounded
  // estimates only (never sold prices); at the table only a live Deal check can say BUY
  const BUYL = part("edge-buylist.js", "EdgeBuyList");
  let BLS = null;
  BUYL.then((b) => { if (b) BLS = b.Store(window.localStorage); });
  let LG = null, LS = null, LEDGER_DRAFT = null, LEDGER_RESUME = null;
  LEDGER.then((l) => { if (!l) return; LG = l; LS = l.Store(window.localStorage); ledgerSync(); });
  // how each strategy rule did in the backtest (a fixed file, rebuilt when the rules change); without it the box says "not backtested"
  const BACKTEST = fetch(`${BASE}assets/edge-backtest.json${VER}`).then((r) => r.ok ? r.json() : null).then((j) => j && j.v === 1 && j.rules ? j : null).catch(() => null);
  /* layout (shared with the market site): big pictures, grid view, 5 tabs; ?v2=0 or Mine > Settings brings back the old one */
  const V2 = (() => {
    try {
      const q = new URLSearchParams(location.search);
      if (q.get("v2") === "1") localStorage.setItem("dys-v2", "1");
      if (q.get("v2") === "0") localStorage.setItem("dys-v2", "0");
      if (q.get("grid") === "1") localStorage.setItem("edge-grid", "1");
      if (q.get("grid") === "0") localStorage.setItem("edge-grid", "0");
      return localStorage.getItem("dys-v2") !== "0";
    } catch { return true; }
  })();
  if (V2) {
    document.documentElement.classList.add("v2");
    try { if (localStorage.getItem("edge-grid") !== "0") document.documentElement.classList.add("grid"); } catch { document.documentElement.classList.add("grid"); }
    // 5 tabs at the bottom; Sets and Tools move to the top bar next to a list / grid switch
    const SV = (d) => `<svg viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
    document.querySelectorAll('.tabs a[data-tab="sets"], .tabs a[data-tab="tools"]').forEach((a) => a.remove());
    const asof = document.getElementById("asof");
    asof?.insertAdjacentHTML("afterend", `<div class="hd-acts">
      <a href="#sets" data-tab="sets" aria-label="Sets" title="Sets">${SV('<rect x="3.5" y="7" width="12" height="14" rx="2"/><path d="M7.5 7V5a1.5 1.5 0 0 1 1.5-1.5h10A1.5 1.5 0 0 1 20.5 5v11a1.5 1.5 0 0 1-1.5 1.5h-3.5"/>')}</a>
      <a href="#tools" data-tab="tools" aria-label="Tools" title="Tools">${SV('<rect x="4" y="3" width="16" height="18" rx="2.5"/><path d="M8 7h8M8 12h2M14 12h2M8 16h2M14 16h2"/>')}</a>
      <button type="button" class="hd-grid" aria-label="Show cards as a grid" title="List or grid" aria-pressed="${document.documentElement.classList.contains("grid")}">${SV('<rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/>')}</button></div>`);
    document.querySelector(".hd-grid")?.addEventListener("click", (e) => {
      const on = document.documentElement.classList.toggle("grid");
      e.currentTarget.setAttribute("aria-pressed", on);
      try { localStorage.setItem("edge-grid", on ? "1" : "0"); } catch {}
    });
  }
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (c, whole) => {
    if (c == null || !isFinite(c)) return "—";
    const neg = c < 0, d = Math.abs(c) / 100;
    const s = d >= 1000 || whole ? "$" + Math.round(d).toLocaleString("en-US") : "$" + d.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return (neg ? "−" : "") + s;
  };
  const signed = (c) => c == null || !isFinite(c) ? "—" : (c >= 0 ? "+" : "") + money(c);
  const pct = (x, d = 1) => x == null || !isFinite(x) ? "—" : `${x > 0 ? "+" : ""}${x.toFixed(d)}%`;
  const cls = (x) => x > 0 ? "up" : x < 0 ? "down" : "";
  const localDay = () => { const d = new Date(); return new Date(d - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10); };
  const cents = (dollars) => Math.round((parseFloat(dollars) || 0) * 100);
  const dollars = (c) => c == null ? "" : (c / 100).toFixed(2).replace(/\.00$/, "");
  const cleanN = (n) => String(n || "").replace(/ \((Holofoil|Normal|Foil)\)$/, "").replace(/ \(Foil\)/, "");
  const fmtDay = (d) => d ? new Date(d + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "";
  const daysAgo = (d) => d ? Math.max(0, Math.round((Date.now() - Date.parse(d + "T12:00:00")) / 864e5)) : null;
  const IMG = (id, size = 200) => `https://tcgplayer-cdn.tcgplayer.com/product/${encodeURIComponent(id)}_${size === 1000 ? "in_1000x1000" : size + "w"}.jpg`;
  const img = (id, size = V2 ? 400 : 200) => `<img src="${IMG(id, size)}" alt="" loading="lazy" decoding="async" data-img>`;
  // no photo yet (a brand-new variant, e.g. a Signature card): show the same card's other version, like the market site
  document.addEventListener("error", (e) => {
    const el = e.target; if (!el?.matches?.("img[data-img]")) return;
    const none = () => { const d = document.createElement("div"); d.className = "ph"; el.replaceWith(d); };
    const m = el.src.match(/\/product\/(\d+)_(in_1000x1000|\d+w)\.jpg/), hops = +(el.dataset.hops || 0);
    if (!m || hops >= 2) return none();
    el.dataset.hops = hops + 1;
    getJSON("img-alt.json").then((a) => { const n = a[m[1]]; if (n) el.src = IMG(n, m[2] === "in_1000x1000" ? 1000 : parseInt(m[2])); else none(); }, none);
  }, true);
  const tcgUrl = (id) => `https://www.tcgplayer.com/product/${id}?Language=all`;
  // eBay Buy It Now search for buying one product, cheapest first. Cheapest-first eBay results fill up with junk, so:
  // singles only (CCG Individual Cards), no slabs / cases / proxies / lots / pick-your-card listings, no other-language
  // copies (unless the card is Japanese), reverse holos searched as reverse holos, and a price floor (40% of market for
  // cards, 60% for sealed) so cheap look-alikes can't push the real listings down.
  const buyUrl = (n, no = "", { p = 0, g = null, grade = "", kind = "c" } = {}) => {
    const game = g != null ? gameOfSet(g) : "";
    const jp = /-jp$/.test(game || ""), card = kind !== "s", nm = String(n || "");
    let q = nm.replace(/ \((Holofoil|Normal|Foil|Reverse Holofoil)\)$/, "").replace(/ \(Foil\)/, "").replace(/ - (\S+)$/, " $1").replace(/[()[\]]/g, " ");
    if (/\(Reverse Holofoil\)$/.test(nm)) q += " reverse holo";
    if (card && no && !q.includes(String(no).split("/")[0])) q += " " + no;
    if (jp) q += " japanese";
    if (grade) q += " " + grade;
    else q += card ? " -psa -cgc -bgs -sgc -tag -graded -slab -case -display -proxy -custom -orica -lot -choose -pick -singles" + (/\(Normal\)$/.test(nm) ? " -reverse" : "")
      : ' -empty -opened -promo -lot -"no cards" -psa -cgc -bgs -graded' + ["various", "kids", "mystery", "repack", "custom", "deck", "digital", "code"].filter((w) => !new RegExp(`\\b${w}\\b`, "i").test(nm)).map((w) => " -" + w).join("");
    if (!jp) q += " -japanese -korean -chinese -spanish -french -german -italian -portuguese";
    const u = new URLSearchParams({ _nkw: q.replace(/\s+/g, " ").trim(), LH_BIN: "1", _sop: "15", _sacat: card ? "183454" : "2536" });
    if (!grade && p >= 500) u.set("_udlo", String(Math.floor(p * (card ? 0.4 : 0.6) / 100)));
    return "https://www.ebay.com/sch/i.html?" + u;
  };
  const soldUrl = (n, extra = "") => `https://www.ebay.com/sch/i.html?_nkw=${encodeURIComponent((cleanN(n).replace(/ \(Reverse Holofoil\)$/, "") + " " + extra).trim())}&LH_Sold=1&LH_Complete=1&_sop=13`;
  const COND = [["NM", 1], ["LP", 0.85], ["MP", 0.7], ["HP", 0.55], ["DMG", 0.4]];
  const condX = (c, t) => t === "s" ? 1 : (COND.find((x) => x[0] === c) || COND[0])[1];
  // game filter: [label, game slugs (null = every game)]; every TCG the market site tracks
  const GAMES = { pokemon: ["Pokémon EN + JP", ["pokemon", "pokemon-jp"]], en: ["Pokémon", ["pokemon"]], jp: ["Pokémon Japan", ["pokemon-jp"]],
    "one-piece": ["One Piece", ["one-piece"]], yugioh: ["Yu-Gi-Oh!", ["yugioh"]], lorcana: ["Lorcana", ["lorcana"]], riftbound: ["Riftbound", ["riftbound"]],
    gundam: ["Gundam", ["gundam"]], "union-arena": ["Union Arena", ["union-arena"]], "dragon-ball-fusion-world": ["Dragon Ball", ["dragon-ball-fusion-world"]],
    palworld: ["Palworld", ["palworld"]], all: ["All games", null] };

  /* ---------- this device's state ---------- */
  const KEY = "dys-edge-v1";
  const DEF = { inv: [], watch: [], trade: { give: [], get: [] }, lot: [], lotExtra: 0, recent: [], board: [], sub: [], glog: [], pop: {},
    set: { platform: "ebay", roi: 20, shipCard: 100, shipCard50: 500, shipSealed: 800, shipSealed100: 1500, buyCard: 150, buySealed: 600, cash: 70, trade: 85, game: "pokemon",
      gradeShip: 1500, gco: "PSA", gtier: {}, o10: 40, o9: 45, oddsV: 2, useMyRates: false, useMix: true, boxShip: 4000,
      buyerTax: 7.5, supCard: 50, supSealed: 150, taxIn: 0, minProfit: 500, holdRate: 1, ledgerBook: "Business", buyLimit: 7500, cashReserve: 10000 } };
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const load = () => {
    try {
      const d = JSON.parse(localStorage.getItem(KEY) || "null");
      if (!d) return clone(DEF);
      const set = { ...DEF.set, ...(d.set || {}) }; set.gtier = { ...(d.set?.gtier || {}) };
      return { ...clone(DEF), ...d, set, trade: { give: d.trade?.give || [], get: d.trade?.get || [] } };
    } catch { return clone(DEF); }
  };
  let S = load();
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch {} };
  /* one-time reset of the fallback grading odds to 40% 10s / 45% 9s (Oct 2026): GemRate puts TCG submissions
     at about a 50% gem rate and PSA overall at 43%, on cards owners already picked as likely 10s, so a little under
     that suits raw near-mint buys. Per-card odds from each card's own sales come first. */
  if ((S.set.oddsV || 0) < 2) { Object.assign(S.set, { o10: 40, o9: 45, oddsV: 2, useMix: true }); save(); }
  const hasPkm = () => { const g = (GAMES[S.set.game] || GAMES.pokemon)[1]; return !g || g.some((x) => x.startsWith("pokemon")); };   // graded sold prices are Pokémon only
  const gameOk = (k) => { const g = (GAMES[S.set.game] || GAMES.pokemon)[1]; return !g || g.includes(k); };
  // the game picker: a dropdown (too many games for a row of buttons)
  function gamePick(el, onChange) {
    el.innerHTML = `<label class="gpick"><span class="lab">Game</span><select class="select">${Object.entries(GAMES).map(([k, g]) => `<option value="${k}"${k === S.set.game ? " selected" : ""}>${esc(g[0])}</option>`).join("")}</select></label>`;
    $("select", el).onchange = (e) => { S.set.game = e.target.value; save(); onChange(); };
  }

  /* ---------- data (the market site's own files) ---------- */
  const cache = {};
  const getJSON = (p) => (cache[p] ||= fetch(`${BASE}data/${p}`, { cache: "no-cache" }).then((r) => { if (!r.ok) throw new Error(p); return r.json(); }));
  const feesP = fetch(`${BASE}assets/grade-fees.json`, { cache: "no-cache" }).then((r) => r.json()).catch(() => ({ graders: { PSA: { upcharge: false, tiers: [["Standard", 5999, null, "90–100"]] } },
    sell: { ebay: { label: "eBay", flat: 40, parts: [[13.25, 0, null, null]] }, none: { label: "In person (no fees)", flat: 0, parts: [] } } }));
  let META = null, FEES = null, ROWS = null, HAY = null;
  const IDX = new Map();
  const keyOf = (id, n) => `${id}|${n}`;
  const loadIndex = () => (cache._idx ||= getJSON("search.json").then((rows) => {
    ROWS = rows; HAY = new Array(rows.length);
    rows.forEach((r, i) => { IDX.set(keyOf(r[0], r[1]), r); if (!IDX.has(String(r[0]))) IDX.set(String(r[0]), r); HAY[i] = (r[1] + " " + setName(r[2])).toLowerCase(); });
    return IDX;
  }));
  const setName = (g) => META?.groups?.[g]?.[0] || "";
  const gameOfSet = (g) => META?.groups?.[g]?.[1] || "";
  const marketOf = (x) => { const r = IDX.get(keyOf(x.id, x.n)) || IDX.get(String(x.id)); return r ? r[4] : x.p ?? null; };
  // a price for every day of the last 120 days, per set (pipeline/edge_daily.py); null when it can't be read (not kept, so the next card tries again)
  const dailyFile = (g) => getJSON(`edge/daily/${g}.json`).catch(() => { delete cache[`edge/daily/${g}.json`]; return null; });
  async function detail(id, g, n) {
    const s = await getJSON(`set/${g}.json`);
    const its = s.items.filter((x) => x.id === id);
    return { it: its.find((x) => x.n === n) || its[0] || null, set: s };
  }

  /* ---------- money math ---------- */
  const plat = (k = S.set.platform) => FEES.sell[k] || FEES.sell.ebay;
  function netSale(pl, v) {
    if (!pl || !v) return v || 0;
    let fee = pl.flat || 0;
    for (const [p, lo, hi, cap] of pl.parts) { const part = Math.max(0, (hi == null ? v : Math.min(v, hi)) - lo) * p / 100; fee += cap == null ? part : Math.min(part, cap); }
    return Math.max(0, v - fee);
  }
  const shipOut = (p, t, k = S.set.platform) => k === "none" ? 0 : t === "s" ? (p >= 10000 ? S.set.shipSealed100 : S.set.shipSealed) : (p >= 5000 ? S.set.shipCard50 : S.set.shipCard);
  const shipIn = (t) => t === "s" ? S.set.buySealed : S.set.buyCard;
  const net = (p, t, k = S.set.platform) => p ? netSale(plat(k), p) - shipOut(p, t, k) : 0;
  const maxBuy = (p, t) => p ? Math.max(0, Math.floor(net(p, t) / (1 + S.set.roi / 100) - shipIn(t))) : 0;
  /* the Deal check's settings, from Mine → Settings */
  const dayNum = (d) => d ? Math.floor(Date.parse(d + "T00:00:00Z") / 864e5) : null;
  let CASH_NOW = null;   // cash on hand for buying, typed in any Deal check; kept for this visit only (not saved). No BUY until it's known.
  function dealCfg(value) {
    const { gr, ti, tier } = grader();
    return { today: Math.floor(Date.now() / 864e5), fees: plat(), buyerTax: S.set.platform === "none" ? 0 : S.set.buyerTax,
      shipOut: (x, t) => shipOut(x, t), supplies: (t) => t === "s" ? S.set.supSealed : S.set.supCard, roi: S.set.roi, minProfit: S.set.minProfit, holdRate: S.set.holdRate,
      // buying rules: all-in limit per purchase, and the cash to keep back (cash on hand: what he typed in Show check, this visit only)
      budget: { limit: S.set.buyLimit ?? 7500, reserve: S.set.cashReserve ?? 10000, cash: CASH_NOW },
      grade: { fee: feeAt(gr, ti, value || 0), ship: S.set.gradeShip, months: Math.max(1, Math.round((parseInt(tier[3], 10) || 60) / 30)) + 1 } };
  }
  /* the PkmnPrices relay (address and passphrase), kept on this phone only and out of backup files */
  const RKEY = "dys-edge-relay", RELAY = "https://dys-edge-relay.keo-llaneza.workers.dev";
  const pkmnConn = () => { try { const j = JSON.parse(localStorage.getItem(RKEY) || "null"); return j && j.relay && j.pass ? { relay: j.relay, pass: j.pass } : null; } catch { return null; } };
  const SOLD_WHY = { "not-set-up": "Sold prices aren't set up yet (Mine → Settings).", network: "No connection to the sold-price relay. Try again.",
    denied: "The relay refused the passphrase. Check it in Mine → Settings.", "not-found": "PkmnPrices doesn't have this exact item, so there are no sold prices to show.", error: "PkmnPrices answered with an error. Try again later." };
  function soldNote(res) {
    if (!res.ok) return { ok: false, note: SOLD_WHY[res.reason] || "Couldn't get sold prices." };
    const m = res.meta, bits = [`${m.calls} call${m.calls === 1 ? "" : "s"}, ${m.credits} credit${m.credits === 1 ? "" : "s"}`];
    if (m.capped.length) bits.push(`more ${m.capped.join(" and ")} sales exist than were read`);
    if (m.errors.length) bits.push(`not read: ${m.errors.join("; ")}`);
    if (m.undated + m.future + m.otherCurrency) bits.push(`${m.undated + m.future + m.otherCurrency} sales left out (no date, future date or not in US dollars)`);
    return { ok: true, data: res.data, note: `Read just now: ${bits.join(" · ")}. Kept on this page only.` };
  }
  /* ---------- graded sold-price check: selling costs (Edge's eBay fee file and Settings, or the owner's saved overrides) ---------- */
  function gradedBase() {
    const pl = FEES.sell.ebay, p0 = pl.parts[0] || [13.25, 0, null], p1 = pl.parts[1] || [0];
    return { feePct: p0[0], topFrom: p0[2] ?? null, topPct: p1[0] || 0, perOrder: pl.flat || 0, buyerTax: S.set.buyerTax, ship: null, supplies: S.set.supCard,
      shipAuto: (x) => shipOut(x, "c", "ebay"), breaks: [5000] };
  }
  const gradedSell = () => ({ ...gradedBase(), ...(S.set.gradedSell || {}) });
  function chanOpts(kind, name) {
    const pl = FEES.sell.ebay, p0 = pl.parts[0] || [13.25, 0, null], p1 = pl.parts[1] || [0], t = kind === "sealed" ? "s" : "c";
    return { item: { kind, name }, saved: S.set.channels || {}, roi: S.set.roi, minProfit: S.set.minProfit, breaks: t === "s" ? [10000] : [5000],
      shipAuto: (x) => shipOut(x, t, "ebay"),
      ebay: { feePct: p0[0], topFrom: p0[2] ?? 750000, topPct: p1[0] || 0, feeFlat: pl.flat || 0, buyerTax: S.set.buyerTax, ship: null, sup: t === "s" ? S.set.supSealed : S.set.supCard },
      save: (o) => { S.set.channels = o ? JSON.parse(JSON.stringify(o)) : null; save(); } };
  }
  const gradedSave = (o) => { S.set.gradedSell = o ? { ...o } : null; save(); };
  const gradedOpts = () => ({ today: Math.floor(Date.now() / 864e5), roi: S.set.roi, minProfit: S.set.minProfit });
  // a ledger or inventory row → what lookupGrade needs, and the holding
  const slabOf = (x) => ({ grader: String(x.grader || "").toUpperCase(), grade: String(x.grade || "").trim() });
  const GSOLD_WHY = { unsupported: "Edge can read sold prices for PSA grades only right now, so there's no reliable value for this grade yet." };
  function gradedNote(res) {
    if (!res.ok) return { ok: false, note: GSOLD_WHY[res.reason] || SOLD_WHY[res.reason] || "Couldn't get sold prices." };
    const m = res.meta, bits = [`${m.calls} call${m.calls === 1 ? "" : "s"}, ${m.credits} credit${m.credits === 1 ? "" : "s"}`];
    if (m.capped.length) bits.push("more sales exist than were read (the newest 160)");
    const out = m.otherGrade + m.lot + m.otherPrinting;
    if (out) bits.push(`${out} left out (${[m.otherGrade && `${m.otherGrade} titled as another grade`, m.lot && `${m.lot} lots`, m.otherPrinting && `${m.otherPrinting} another printing`].filter(Boolean).join(", ")})`);
    if (m.errors.length) bits.push(`not read: ${m.errors.join("; ")}`);
    return { ok: true, data: res.data, note: `${bits.join(" · ")}. Kept on this page only.` };
  }
  async function checkSold(x, box) {
    const [g, pkmn] = await Promise.all([GRADED, PKMN]), conn = pkmnConn();
    if (!box) return;
    if (!g || !pkmn) { box.innerHTML = `<p class="small muted">The sold-price check didn't load. Reload and try again.</p>`; return; }
    const item = { id: +x.tcg, n: x.n || x.name }, slab = slabOf(x), label = `${slab.grader} ${slab.grade}`;
    const holding = { cost: x.costEach || 0, label };
    let s0 = false;   // set once sold prices are on the panel (the first draw, before any are loaded, doesn't count)
    const load = (fresh) => pkmn.getGrade(item, slab, conn, fresh).then(gradedNote).then((res) => { s0 = !!res.ok; return res; });
    let cbox = null, cm = null;
    const chan = await CHAN;
    if (chan && box.parentNode) { cbox = document.createElement("div"); cbox.className = "lg-ch"; box.after(cbox); }
    const after = (r, sell) => {
      if (s0 && r.s) noteSold(+x.tcg, x.n, label, r);
      if (!cbox) return;
      const p = { cost: holding.cost, ref: r.typical ?? null, refLabel: r.typical != null ? `${label} typical sold price, ${r.s && r.s.full30 ? "last 30 days" : "newest sales"}` : null,
        ebay: { feePct: sell.feePct, topFrom: sell.topFrom ?? 750000, topPct: sell.topPct || 0, feeFlat: sell.perOrder || 0, buyerTax: sell.buyerTax, ship: sell.ship, sup: sell.supplies || 0 } };
      try { cm ? cm.update(p) : (cm = chan.mount(cbox, { ...chanOpts("graded", x.n || x.name), ...p })); } catch (err) { console.error(err); cbox.remove(); cbox = null; }
    };
    const opts = { holding, sell: gradedSell(), base: gradedBase(), ...gradedOpts(), save: gradedSave, after };
    if (!conn) { g.mount(box, { ...opts, note: "Sold prices aren't set up on this device yet (Mine → Settings → Pair this phone)." }); return; }
    const first = await load(false);
    g.mount(box, { ...opts, load, data: first.ok ? first.data : null, note: first.note, readAt: first.ok ? "just now" : null });
  }
  /* ---------- ledger: the Sheet's web app address (set when the Sheet is made; an override can be typed in Settings) ---------- */
  const LEDGER_URL = "https://script.google.com/macros/s/AKfycby2YPa5O2iq_IJOBz_BNcJPKayUdLM3u1Oq-_KZ7FUl_SOALNdiHfkiaQFLTfxdt9BOjw/exec", LKEY = "dys-edge-ledger-url";   // the ledger Sheet's web app (bound to "DYS Edge Ledger"; only paired devices are accepted)
  const ledgerConn = () => {
    let url = LEDGER_URL; try { url = localStorage.getItem(LKEY) || url; } catch {}
    const c = pkmnConn(); return url && c ? { url, token: c.pass } : null;
  };
  const ledgerOn = () => !!LS && (LS.state.migrated || !S.inv.length);
  // what an item is worth now, per unit: TCGplayer market (raw by condition, sealed as is), graded from the graded sold prices
  const GTOP = { PSA: ["10", "9", "8"], CGC: ["10", "9"], BGS: ["9.5", "9"], TAG: ["10", "9"] };
  const priceOf = (x) => {
    if (!x.tcg) return null;
    if (x.kind === "Graded") {
      const i = (GTOP[x.grader] || []).indexOf(String(x.grade || "").trim()); if (i < 0) return null;
      const gp = gradedOf(+x.tcg, x.grader); return gp ? [gp.p10, gp.p9, gp.p8][i] || null : null;
    }
    if (x.kind !== "Raw" && x.kind !== "Sealed") return null;
    const r = IDX.get(keyOf(+x.tcg, x.n)) || IDX.get(String(x.tcg));
    return r && r[4] ? (x.kind === "Sealed" ? r[4] : Math.round(r[4] * condX(x.cond || "NM", "c"))) : null;
  };
  // one sync at a time: send the queue (200 changes a trip), take back every table; quiet when offline or not set up
  let LSYNC = null;
  function ledgerSync() {
    if (!LS || !LG) return Promise.resolve(null);
    const c = ledgerConn(); if (!c) return Promise.resolve(null);
    if (LSYNC) return LSYNC;
    const send = async (body) => {
      const R = LG.compute(LS.T, { priceOf, today: localDay() });
      const r = await fetch(c.url, { method: "POST", headers: { "Content-Type": "text/plain;charset=utf-8" }, body: JSON.stringify({ token: c.token, ...body, shown: LG.shownRows(R), summary: LG.summaryRows(R, new Date().toLocaleString("en-US")) }) });
      if (!r.ok) return { ok: false, error: `HTTP ${r.status}` };
      return r.json();
    };
    return (LSYNC = (async () => {
      let res = null;
      for (let i = 0; i < 6; i++) { res = await LS.sync(send); if (!res.ok || !res.left) break; }
      return res;
    })().finally(() => { LSYNC = null; }));
  }
  let LTIMER = 0;
  const ledgerSoon = () => { clearTimeout(LTIMER); LTIMER = setTimeout(() => ledgerSync(), 1200); return Promise.resolve(); };
  window.addEventListener("online", () => ledgerSync());
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") ledgerSync(); });
  /* PSA sold-price values for this page visit only: the exact card and grade's eBay sold median from a PSA check that
     already ran (Ledger → Check sold prices, or Sell, grade or keep?). Kept in this variable alone: never written to the
     phone's storage, the backup file or the Sheet (the Sheet's values come from priceOf, which never reads it), and never
     fetched for this: no extra PkmnPrices calls. Gone on reload, by design (PkmnPrices data isn't stored). */
  const SOLDV = new Map();
  const soldKey = (tcg, n, label) => `${tcg}|${n}|${String(label).toUpperCase().trim()}`;
  function noteSold(tcg, n, label, r) {
    const k = soldKey(tcg, n, label);
    // only a check with enough fresh, consistent sales of that exact grade (the PSA check's own evidence rules) values a card
    if (!r || r.typical == null || r.verdict === "insufficient") { SOLDV.delete(k); return; }
    SOLDV.set(k, { each: r.typical, label, n30: r.s.n30, capped: r.s.capped, newest: r.s.newest, at: Date.now() });
  }
  const clock = (ms) => new Date(ms).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  const dayOf = (d) => new Date(d * 864e5).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
  // value per unit (cents, or null when Edge has no price: never 0 for "unknown") and where it came from
  function valueOf(x) {
    if (x.kind === "Graded") {
      const label = `${x.grader} ${x.grade}`, sv = SOLDV.get(soldKey(+x.tcg, x.n, label));
      if (sv) return { each: sv.each, src: `${label} eBay sold median, ${sv.n30}${sv.capped ? "+" : ""} sales in 30 days (newest ${dayOf(sv.newest)}) · checked ${clock(sv.at)}, this visit only`, kind: "sold" };
      const p = priceOf(x), gp = p != null ? gradedOf(+x.tcg, x.grader) : null;
      return p != null ? { each: p, src: `${label} graded price list (PokemonPriceTracker)${gp && gp.at ? `, ${fmtDay(String(gp.at).slice(0, 10))}` : ""}`, kind: "list" } : { each: null, src: "", kind: "none" };
    }
    const p = priceOf(x);
    return p != null ? { each: p, src: `TCGplayer market${x.kind === "Raw" && (x.cond || "NM") !== "NM" ? ` (${x.cond})` : ""}${META && META.updated ? `, ${fmtDay(META.updated)}` : ""}`, kind: "market" } : { each: null, src: "", kind: "none" };
  }
  // what's held, for Inventory and Today: the ledger's items once it's in use, else the old list on this phone
  function invRows() {
    if (!ledgerOn()) return S.inv.map((x) => { const m = marketOf(x); return { ...x, each: m == null ? null : m * condX(x.cond, x.t), src: m == null ? "" : `TCGplayer market${META && META.updated ? `, ${fmtDay(META.updated)}` : ""}` }; });
    return LG.compute(LS.T, { priceOf }).items.filter((x) => x.left && x.tcg).map((x) => { const v = valueOf(x); return { k: keyOf(+x.tcg, x.n), id: +x.tcg, g: +x.g, n: x.n, t: x.kind === "Sealed" ? "s" : "c",
      qty: x.left, cost: x.costEach, cond: x.cond || "NM", graded: x.kind === "Graded" ? `${x.grader} ${x.grade}` : "", each: v.each, src: v.src, srcKind: v.kind, lid: x.id, book: x.book }; });
  }
  const flip = (p, lo, t) => { if (!p || !lo) return null; const cost = lo + shipIn(t), pr = net(p, t) - cost; return { pr, roi: pr / cost * 100, cost }; };
  function tierFor(gr, v) { const t = gr.tiers; for (let i = 0; i < t.length; i++) if (t[i][2] == null || v <= t[i][2]) return i; return t.length - 1; }
  const feeAt = (gr, ti, v) => gr.upcharge ? Math.max(gr.tiers[ti][1], gr.tiers[tierFor(gr, v)][1]) : gr.tiers[ti][1];

  /* ---------- small UI pieces ---------- */
  function toast(msg) { const t = $("#toast"); t.textContent = msg; t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, 2200); }
  function seg(el, options, value, onChange) {
    el.classList.add("seg"); el.setAttribute("role", "group");
    el.innerHTML = options.map(([v, l]) => `<button type="button" data-v="${esc(v)}" aria-pressed="${v === value}">${esc(l)}</button>`).join("");
    el.onclick = (e) => { const b = e.target.closest("button[data-v]"); if (!b) return; $$("button", el).forEach((x) => x.setAttribute("aria-pressed", x === b)); onChange(b.dataset.v); };
  }
  function spark(s, w = 200, h = 36) {
    const v = (s || []).filter((x) => x != null);
    if (v.length < 2) return "";
    const mn = Math.min(...v), mx = Math.max(...v), r = mx - mn || 1;
    const pts = v.map((x, i) => `${(i / (v.length - 1) * w).toFixed(1)} ${(h - 3 - (x - mn) / r * (h - 6)).toFixed(1)}`);
    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><path d="M${pts.join("L")}" fill="none" stroke="var(${v[v.length - 1] >= v[0] ? "--up" : "--down"})" stroke-width="1.7" vector-effect="non-scaling-stroke"/></svg>`;
  }
  function chart(s, dates) {
    const pts = (s || []).map((v, i) => [i, v]).filter((p) => p[1] != null);
    if (pts.length < 2) return `<p class="muted small">Not enough price history yet. It builds every night.</p>`;
    const W = 340, H = 150, L = 4, R = 52, T = 10, B = 22, n = s.length - 1;
    const vs = pts.map((p) => p[1]), mn = Math.min(...vs), mx = Math.max(...vs), rg = mx - mn || mx * 0.05 || 1;
    const X = (i) => L + i / n * (W - L - R), Y = (v) => T + (mx - v) / rg * (H - T - B);
    const line = pts.map(([i, v], k) => `${k ? "L" : "M"}${X(i).toFixed(1)} ${Y(v).toFixed(1)}`).join("");
    const last = pts[pts.length - 1], up = last[1] >= pts[0][1], col = up ? "var(--up)" : "var(--down)";
    const ds = (dates || []).slice(-s.length);
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Price history">
      <line x1="${L}" x2="${W - R}" y1="${Y(mx)}" y2="${Y(mx)}" stroke="var(--line)"/><line x1="${L}" x2="${W - R}" y1="${Y(mn)}" y2="${Y(mn)}" stroke="var(--line)"/>
      <path d="${line}L${X(last[0]).toFixed(1)} ${H - B}L${X(pts[0][0]).toFixed(1)} ${H - B}Z" fill="${col}" opacity=".12"/>
      <path d="${line}" fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round"/>
      <circle cx="${X(last[0])}" cy="${Y(last[1])}" r="3.5" fill="${col}"/>
      <text x="${W - R + 6}" y="${Y(mx) + 4}">${money(mx, mx >= 10000)}</text><text x="${W - R + 6}" y="${Y(mn) + 4}">${money(mn, mn >= 10000)}</text>
      <text x="${L}" y="${H - 6}">${esc(fmtDay(ds[pts[0][0]]))}</text><text x="${W - R}" y="${H - 6}" text-anchor="end">${esc(fmtDay(ds[last[0]]))}</text></svg>`;
  }
  /* ---------- card search: the whole card list, ranked (Nov 21, 2026). Shared by Search (and the Ledger's "add a
     card"), Show check and the Buy list. Before, each stopped after the first 200-400 matches in price order, so cheaper
     cards never showed ("Mew": 425 matches, 12 shown). Every word must start a word of the name or set ("mew" no longer
     matches "Bartholomew"); card numbers match with or without leading zeros ("6/165" finds 006/165, "179" alone finds
     179/131); printing words filter the exact printing (reverse, holo, 1st, unlimited, normal). */
  const SPR = ["1st Edition Holofoil", "1st Edition Normal", "1st Edition", "Unlimited Holofoil", "Unlimited", "Reverse Holofoil", "Holofoil", "Normal"];
  const fold = (x) => String(x || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const printingOfRow = (n, t) => { if (t === "s") return ""; const m = /\(([^()]*)\)\s*$/.exec(n || ""); return m && SPR.includes(m[1]) ? m[1] : "Normal"; };
  const numNorm = (x) => x.split("/").map((p) => p.replace(/^([a-z]*)0+(?=\d)/, "$1")).join("/");
  let SX = null;
  function searchIndex() {
    if (SX && SX.rows === ROWS) return SX;
    const n = ROWS.length, text = new Array(n), base = new Array(n), num = new Array(n), pr = new Array(n);
    for (let i = 0; i < n; i++) {
      const r = ROWS[i], nm = r[1] || "";
      text[i] = " " + fold(nm + " " + setName(r[2])).replace(/[^a-z0-9/]+/g, " ") + " ";
      base[i] = fold(nm.split(" - ")[0].replace(/\s*\(.*$/, "")).replace(/[^a-z0-9]+/g, " ").trim();
      const m = / - ([a-z]*\d+[a-z]*(?:\/[a-z]*\d+[a-z]*)?)/i.exec(nm); num[i] = m ? numNorm(m[1].toLowerCase()) : "";
      pr[i] = printingOfRow(nm, r[3]);
    }
    return (SX = { rows: ROWS, text, base, num, pr });
  }
  const PR_WORDS = [["rev", /\b(reverse holofoil|reverse holo|reverse|rev holo|rh)\b/g], ["1st", /\b(1st edition|1st ed|1st|first edition|first ed)\b/g],
    ["unl", /\b(unlimited|unl)\b/g], ["normal", /\b(non[\s-]?holo|normal)\b/g], ["holo", /\b(holofoil|holo)\b/g]];
  function parseQuery(q) {
    let x = " " + fold(q).replace(/#/g, " ") + " "; const want = new Set();
    for (const [k, re] of PR_WORDS) { re.lastIndex = 0; if (re.test(x)) { want.add(k); x = x.replace(re, " "); } }
    return { toks: x.replace(/[^a-z0-9/]+/g, " ").trim().split(/\s+/).filter(Boolean), want };
  }
  function printingOk(p, want) {
    if (!want.size) return true;
    if (!p) return false;                                   // sealed has no printing
    if (want.has("rev") && p !== "Reverse Holofoil") return false;
    if (want.has("holo") && !want.has("rev") && !(p.endsWith("Holofoil") && p !== "Reverse Holofoil")) return false;
    if (want.has("1st") && !p.startsWith("1st Edition")) return false;
    if (want.has("unl") && !p.startsWith("Unlimited")) return false;
    if (want.has("normal") && !["Normal", "Unlimited", "1st Edition", "1st Edition Normal"].includes(p)) return false;
    return true;
  }
  // every match, best first; keep(r) filters by game or type. Returns rows of the card list.
  function findCards(q, keep) {
    const { toks, want } = parseQuery(q);
    if (!toks.length && !want.size) return [];
    const X = searchIndex(), hits = [], isNum = (t) => /\d/.test(t);
    const words = toks.filter((t) => !isNum(t)).join(" ");
    for (let i = 0; i < ROWS.length; i++) {
      const r = ROWS[i];
      if (keep && !keep(r)) continue;
      if (!printingOk(X.pr[i], want)) continue;
      const tx = X.text[i]; let sc = 0, ok = true;
      for (const t of toks) {
        if (isNum(t) && X.num[i]) { const a = numNorm(t), b = X.num[i]; if (b === a || b.split("/")[0] === a) { sc += 50; continue; } }
        if (tx.includes(" " + t)) continue;
        ok = false; break;
      }
      if (!ok) continue;
      const b = X.base[i];
      if (words) sc += b === words ? 100 : b.startsWith(words + " ") ? 60 : (" " + b + " ").includes(" " + words + " ") ? 40 : b.startsWith(words) ? 25 : 0;
      hits.push([sc, i]);
    }
    hits.sort((a, b) => b[0] - a[0] || (ROWS[b[1]][4] || 0) - (ROWS[a[1]][4] || 0));
    return hits.map((h) => ROWS[h[1]]);
  }
  // a results list that grows: the first `step` rows, then "Show more" adds `step` at a time
  function pagedList(box, list, step, html, wire, wrap = "sc-list") {
    let shown = 0;
    box.innerHTML = `<p class="small muted sr-count" data-n="${list.length}">${list.length.toLocaleString("en-US")} match${list.length === 1 ? "" : "es"}</p><div class="${wrap}"></div><div class="btns sr-more-wrap"></div>`;
    const ul = box.querySelector(`.${wrap.split(" ")[0]}`), more = box.querySelector(".sr-more-wrap");
    const add = () => {
      const part = list.slice(shown, shown + step); shown += part.length;
      const tmp = document.createElement("div"); tmp.innerHTML = part.map(html).join("");
      const nodes = [...tmp.children]; nodes.forEach((n) => ul.appendChild(n)); wire(nodes);
      const left = list.length - shown;
      more.innerHTML = left > 0 ? `<button type="button" class="btn sm sr-more">Show ${Math.min(step, left)} more · ${left.toLocaleString("en-US")} left</button>` : "";
      const b = more.querySelector(".sr-more"); if (b) b.onclick = add;
    };
    add();
  }
  const rowHTML = (x, right, extra = "") => `<button type="button" class="row" data-open="${x.id}" data-g="${x.g}" data-n="${esc(x.n)}">
      ${img(x.id)}<span style="min-width:0;display:flex;flex-direction:column;gap:2px"><span class="nm">${esc(cleanN(x.n))}</span><span class="st">${esc(x.sn || setName(x.g))}</span></span>
      <span class="rt">${right}</span>${extra}</button>`;
  const listOrEmpty = (rows, empty) => rows.length ? `<div class="list">${rows.join("")}</div>` : `<div class="empty">${empty}</div>`;
  document.addEventListener("click", (e) => {
    const r = e.target.closest("[data-open]");
    if (!r || e.target.closest("input,select,.x")) return;
    if (PICK && r.closest("#view")) { pickAdd(+r.dataset.open, +r.dataset.g, r.dataset.n); return; }
    openCard(+r.dataset.open, +r.dataset.g, r.dataset.n);
  });

  // a section body is reused across sub-tabs: drop the previous tool's handlers before drawing the next one
  const fresh = (el) => { el.oninput = el.onchange = el.onclick = null; el.innerHTML = ""; return el; };

  /* ---------- router ---------- */
  let PICK = null;     // adding cards to a trade side or a lot from Search
  const TABS = { today: viewToday, search: viewSearch, sets: viewSets, deals: viewDeals, grade: viewGrade, tools: viewTools, mine: viewMine };
  let TAB = "today", SUB = { deals: "check", tools: "flip", mine: "inv", grade: "board" };
  let ROUTE_N = 0;
  function route() {
    const h = (location.hash || "").slice(1).split("/")[0];
    TAB = TABS[h] ? h : "today";
    if (TAB !== "search") PICK = null;
    $$(".tabs a, .hd-acts a").forEach((a) => a.setAttribute("aria-current", a.dataset.tab === TAB ? "page" : "false"));
    const v = $("#view"); v.innerHTML = ""; window.scrollTo(0, 0);
    // a view still loading when he moves on (a slow connection) must not overwrite the next one with its error
    const n = ++ROUTE_N;
    TABS[TAB](v).catch((err) => { if (n !== ROUTE_N) return; console.error(err); v.innerHTML = `<div class="empty"><b>Couldn't load the market data</b>Check your connection and reopen the app.</div>`; });
  }
  window.addEventListener("hashchange", route);

  /* ---------- Today ---------- */
  async function viewToday(v) {
    v.innerHTML = `<section class="sec" id="t-adv"></section>
      <section class="sec" id="t-buy"></section>
      <section class="brief" id="t-brief"><span class="lab">Market brief</span><h1>Loading…</h1></section>
      <section class="sec" id="t-port"></section>
      <section class="sec"><div class="sec-head"><h2>Market indices</h2></div><div class="hscroll" id="t-idx"></div></section>
      <section class="sec"><div class="sec-head"><h2>Biggest moves today</h2></div><div id="t-mv-seg"></div><div id="t-movers"></div></section>
      <section class="sec" id="t-grade" hidden></section>
      <section class="sec" id="t-store" hidden></section>
      <p class="muted small">Market prices are TCGplayer's, updated nightly. Profits use your selling platform, fees and shipping from Mine → Settings.</p>`;
    const n = ROUTE_N;
    const [intel, buyer] = await Promise.all([getJSON("intel.json").catch(() => null), getJSON("buyer.json").catch(() => null)]);
    await loadIndex();
    if (n !== ROUTE_N) return;      // he moved to another tab while this loaded (slow connection)
    drawAdvisor($("#t-adv"));
    drawBuy($("#t-buy"));
    if (intel) {
      $("#t-brief").innerHTML = `<span class="lab">Market brief · ${esc(fmtDay(intel.date))}</span><h1>${esc(intel.brief.head)}</h1><p>${esc(intel.brief.body)}</p>`;
      $("#t-idx").innerHTML = intel.indices.map((x) => { const ch = x.w1 ?? x.d1; return `<div class="idx"><span class="lab">${esc(x.name)}</span><b>${money(x.v, true)}</b>
        <span class="small ${cls(ch)}">${pct(ch)} ${x.w1 != null ? "this week" : "today"}</span>${spark(x.s)}</div>`; }).join("");
      const drawMv = (k) => {
        const rows = (intel.movers?.[k] || []).filter((m) => gameOk(m.k)).slice(0, 6)
          .map((m) => rowHTML(m, `<b>${money(m.p)}</b><small class="${cls(m.d1)}">${pct(m.d1, 0)}</small>`));
        $("#t-movers").innerHTML = listOrEmpty(rows, `No ${k === "up" ? "risers" : "fallers"} in your games today.`);
      };
      seg($("#t-mv-seg"), [["up", "Rising"], ["down", "Falling"]], "up", drawMv); drawMv("up");
    } else $("#t-brief").innerHTML = `<span class="lab">Market brief</span><h1>Today's brief isn't ready yet</h1>`;
    if (buyer && (buyer.fix?.length || buyer.rising?.length)) {
      const fix = buyer.fix || [];
      $("#t-store").hidden = false;
      $("#t-store").innerHTML = `<div class="sec-head"><h2>Your store</h2><a class="more" href="#deals" data-sub="store">See all</a></div>
        ${listOrEmpty(fix.slice(0, 3).map((x) => rowHTML(x, `<b>${money(x.dys)}</b><small class="${x.gap < 0 ? "down" : "up"}">${pct(x.gap, 0)} vs ${money(x.p)}</small>`)), "")}
        <p class="muted small">${fix.length} store price${fix.length === 1 ? "" : "s"} far from market. Tap one to see the numbers.</p>`;
      $('#t-store [data-sub]').onclick = () => { SUB.deals = "store"; };
    }
    drawPortfolio($("#t-port"));
    await loadGraded();
    const gb = S.board.map((x) => { const bp = boardPrices(x); return { x, e: gradeEval(marketOf(x) || 0, bp.p10, bp.p9, bp.p8, undefined, cardOdds(x.id)) }; }).filter((r) => r.e.profit > 0).sort((a, b) => b.e.profit - a.e.profit).slice(0, 3);
    const mine = new Set(S.board.map((x) => String(x.id)));
    if (gb.length < 3 && GR) for (const o of (await opportunities()) || []) { if (gb.length >= 3 || o.e.profit <= 0) break; if (!mine.has(String(o.r[0]))) gb.push({ x: { id: o.r[0], g: o.r[1], n: o.r[2] }, e: o.e }); }
    if (gb.length) { $("#t-grade").hidden = false; $("#t-grade").innerHTML = `<div class="sec-head"><h2>Grading ideas · estimates</h2><a class="more" href="#grade" id="t-grade-more">${GR ? "All opportunities" : "Grading board"}</a></div>
      <p class="muted small adv-note">Cards to look at, from TCGplayer raw prices and the graded price list. Not checked against sold prices, so no profit is shown here: open a card and run its Deal check (grade route) before sending anything in.</p>
      <div class="list">${gb.map(({ x }) => rowHTML(x, `<b>Check it</b><small class="muted">not sold-checked</small>`)).join("")}</div>`;
      $("#t-grade-more").onclick = () => { SUB.grade = GR ? "find" : "board"; }; }
  }
  function portfolio() {
    const p = { value: 0, cost: 0, costPriced: 0, costUnpriced: 0, items: 0, priced: 0, unpriced: 0, n: 0 };
    for (const x of invRows()) {
      const c = (x.cost || 0) * x.qty; p.items++; p.n += x.qty; p.cost += c;
      if (x.each == null) { p.unpriced++; p.costUnpriced += c; } else { p.priced++; p.value += Math.round(x.each * x.qty); p.costPriced += c; }
    }
    p.pl = p.priced ? p.value - p.costPriced : null;
    return p;
  }
  // the three tiles and the line under them, shared by Today and Inventory
  function valueTiles(p) {
    const some = p.priced > 0;
    return `<div class="tiles"><div class="tile"><span class="lab">Market value</span><b>${some ? money(p.value, true) : "—"}</b><small>${p.priced} of ${p.items} item${p.items === 1 ? "" : "s"} priced</small></div>
      <div class="tile"><span class="lab">Total cost</span><b>${money(p.cost, true)}</b><small>all ${p.items} item${p.items === 1 ? "" : "s"}</small></div>
      <div class="tile"><span class="lab">Unrealized (est.)</span><b class="${some ? cls(p.pl) : ""}">${some ? `${p.pl >= 0 ? "+" : ""}${money(p.pl, true)}` : "—"}</b><small>${some ? `${p.costPriced ? pct(p.pl / p.costPriced * 100, 0) + " " : ""}on ${money(p.costPriced, true)} priced` : "no priced items"}</small></div></div>
      ${p.unpriced ? `<p class="small muted inv-unpriced">${p.unpriced} item${p.unpriced === 1 ? "" : "s"} (${money(p.costUnpriced, true)} cost) ${p.unpriced === 1 ? "has" : "have"} no price yet, so ${p.unpriced === 1 ? "it isn't" : "they aren't"} counted in value or unrealized. That's unknown, not a loss.</p>` : ""}`;
  }
  function drawPortfolio(el) {
    if (!invRows().length) { el.innerHTML = `<div class="empty"><b>Track what you own</b>Search a card, tap <b style="display:inline;font-size:inherit">${LS ? "Bought it" : "Add to inventory"}</b>, and its value updates here every night.</div>`; return; }
    const p = portfolio();
    el.innerHTML = `<div class="sec-head"><h2>Your inventory</h2><a class="more" href="#mine">Open</a></div>${valueTiles(p)}`;
  }
  /* What to consider buying: only leads, never a BUY by themselves. A watched card at its target price is a lead from
     TCGplayer's market or lowest listing (any condition), so it says so and points at the Deal check, which is the only
     place Edge says "BUY candidate" (real sold prices, every gate). The Near Mint finder's list joins here once connected. */
  async function drawBuy(el) {
    if (!el) return;
    const hits = [];
    for (const w of S.watch) {
      const d = await detail(w.id, w.g, w.n).catch(() => null);
      const it = d?.it; if (!it) continue;
      const now = Math.min(it.lo || Infinity, it.p || Infinity);
      if (isFinite(now) && now <= w.target) hits.push(rowHTML({ ...w, n: it.n }, `<b>${money(now)}</b><small class="muted">target ${money(w.target)}</small>`,
        `<span class="why">${it.lo && it.lo <= w.target ? "Lowest listing (any condition)" : "Market price"} at or under your target. Not checked against sold prices yet. ${dcChip(w, now)}</span>`));
    }
    if (!el.isConnected) return;
    el.innerHTML = `<div class="sec-head"><h2>What to consider buying</h2>${hits.length ? `<span class="chip hot">${hits.length}</span>` : ""}</div>
      ${hits.length ? `<div class="list">${hits.join("")}</div>` : `<div class="empty adv-empty">${S.watch.length ? `None of your ${S.watch.length} watched card${S.watch.length === 1 ? " is" : "s are"} at your target price today.` : "Watch a card's price (open it → Watch price) and it shows here when it reaches your number."}</div>`}
      <p class="muted small adv-note">Edge only calls something a <b>BUY candidate</b> in a card's Deal check, after real sold prices clear every check (sales, freshness, spread, trend and your ${S.set.roi}% target). Near Mint deals from the daily finder will show here once it's connected.</p>`;
    wireDc(el);
  }

  /* ---------- Search ---------- */
  let LAST_Q = "", S_TYPE = "all";
  async function viewSearch(v) {
    v.innerHTML = `${PICK ? `<div class="pickbar"><span>Tap cards to add to <b>${esc(PICK.label)}</b></span><button type="button" class="btn sm" id="pick-done">Done</button></div>` : ""}
      <div class="searchbox"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></svg>
        <input id="q" class="field" type="search" placeholder="Card name, number or set" autocomplete="off" enterkeyhint="search" aria-label="Search cards and sealed" value="${esc(LAST_Q)}"></div>
      <div id="s-game"></div><div id="s-type"></div><div id="s-res"><p class="muted small">Loading every card and sealed product…</p></div>`;
    if (PICK) $("#pick-done").onclick = () => { const back = PICK.back; if (PICK.list === "ledger") { LEDGER_RESUME = PICK.form; SUB.mine = "ledger"; } PICK = null; location.hash = back; };
    gamePick($("#s-game"), () => run());
    seg($("#s-type"), [["all", "Everything"], ["c", "Cards"], ["s", "Sealed"]], S_TYPE, (k) => { S_TYPE = k; run(); });
    await loadIndex();
    const q = $("#q");
    const run = () => {
      if (!$("#s-res")) return;                         // left Search before a delayed search ran
      LAST_Q = q.value; const s = q.value.trim().toLowerCase();
      if (!s) { drawRecent(); return; }
      const out = findCards(s, (r) => (S_TYPE === "all" || r[3] === S_TYPE) && gameOk(gameOfSet(r[2])));
      if (!out.length) { $("#s-res").innerHTML = `<div class="empty"><b>Nothing found</b>Try fewer words, a card number like 199/165, or switch games.</div>`; return; }
      pagedList($("#s-res"), out, 30, (r) => rowHTML({ id: r[0], n: r[1], g: r[2], sn: setName(r[2]) + (r[3] === "s" ? "" : ` · ${printingOfRow(r[1], r[3])}`) },
        `<b>${money(r[4])}</b><small class="muted">${r[3] === "s" ? "sealed" : "card"}</small>`), () => {}, "list");
    };
    const drawRecent = () => {
      const rows = S.recent.filter((x) => S_TYPE === "all" || x.t === S_TYPE).map((x) => rowHTML(x, `<b>${money(marketOf(x))}</b>`));
      $("#s-res").innerHTML = rows.length ? `<div class="sec"><div class="sec-head"><h2>Recently viewed</h2></div><div class="list">${rows.join("")}</div></div>`
        : `<div class="empty"><b>Look up anything</b>Every card and sealed product in ${esc((GAMES[S.set.game] || GAMES.pokemon)[0])}, with today's market price, lowest listing and price history.</div>`;
    };
    let t; q.addEventListener("input", () => { clearTimeout(t); t = setTimeout(run, 140); });
    run();
    if (!PICK) q.focus({ preventScroll: true });
  }
  /* ---------- Sets: every set with its box price and weekly move; tap one for all its cards ----------
     Grouped by series like the market site's Sets page; promos, events, decks and other specials sit apart */
  const ERAS = {
    "pokemon": [["2025-09-20", "Mega Evolution"], ["2023-03-25", "Scarlet & Violet"], ["2020-02-01", "Sword & Shield"], ["2017-01-28", "Sun & Moon"], ["2014-02-01", "XY"],
      ["2011-04-20", "Black & White"], ["2010-02-01", "HeartGold & SoulSilver"], ["2007-05-01", "Diamond & Pearl / Platinum"], ["2003-06-01", "EX"], ["2001-12-01", "e-Card & Legendary"], ["2000-12-01", "Neo"], ["1990-01-01", "Classic"]],
    "pokemon-jp": [["2025-08-01", "Mega (M)"], ["2023-01-15", "Scarlet & Violet (SV)"], ["2019-12-01", "Sword & Shield (S)"], ["2016-12-01", "Sun & Moon (SM)"], ["2013-12-01", "XY"],
      ["2010-09-15", "Black & White (BW)"], ["2009-12-01", "LEGEND"], ["2006-09-01", "Diamond & Pearl / Platinum"], ["2001-01-01", "ADV, PCG & e-Series"], ["1990-01-01", "Classic"]],
  };
  const PROMO_GROUP = "Promos & Special Sets";
  const SPECIAL = /promo|mcdonald|trainer kit|battle academy|trick or trade|prize pack|league|championship|jumbo|deck kit|exclusive|first partner|my first battle|trading card game classic|tcg classic|starter (set|deck)|start deck|deck set|battle deck|theme deck|deck build box|gift box|special box|world championship|play! pokemon|kids|placement/i;
  function eraOf(s) {
    if (s.k === "one-piece") {
      const a = (s.a || "").toUpperCase(), n = s.n.toLowerCase();
      if (/release event|promo|tournament|pre-release|judge/.test(n)) return "Promos & Events";
      if (a.startsWith("OP")) return "Booster Sets";
      if (a.startsWith("EB")) return "Extra Boosters";
      if (a.startsWith("PRB")) return "Premium Boosters";
      if (a.startsWith("ST") || a.startsWith("SD")) return "Starter Decks";
      return "Other";
    }
    if (s.k === "union-arena") {   // grouped by series (Chainsaw Man, Jujutsu Kaisen, ...)
      const n = s.n.toLowerCase();
      if (/promo|judge|event|tournament|championship/.test(n)) return "Promos & Events";
      if (/starter|deck|bundle|sleeve|collection|set$/.test(n)) return "Products & Extras";
      return "Booster Sets";
    }
    if (s.k === "yugioh") {   // by era, with decks/tins/promos apart
      const n = s.n.toLowerCase();
      if (/promo|tournament|prize|championship|judge|sneak peek|participation/.test(n)) return "Promos & Events";
      if (/structure deck|starter deck|speed duel|tin|box|collection|pack|bundle|mega|duelist pack|deck/.test(n) && !/booster/.test(n)) return "Decks, Tins & Collections";
      const y = (s.pub || "").slice(0, 4);
      return !y ? "Other" : y >= "2023" ? "Booster Sets · 2023–now" : y >= "2017" ? "Booster Sets · 2017–2022" : y >= "2010" ? "Booster Sets · 2010–2016" : "Booster Sets · 2002–2009";
    }
    if (["lorcana", "riftbound", "palworld", "gundam", "dragon-ball-fusion-world"].includes(s.k)) {   // newer games: main sets vs. everything else, newest first
      const n = s.n.toLowerCase();
      if (/promo|judge|organized play|prototype|championship|event|league/.test(n)) return "Promos & Events";
      if (/illumineer|quest|starter|deck|bundle|gift|sleeve|collection|tin|box set/.test(n) && !/^bp\d/i.test(s.n)) return "Products & Extras";
      return "Main Sets";
    }
    if (SPECIAL.test(s.n)) return PROMO_GROUP;
    if (!s.pub) return "Other";
    const e = (ERAS[s.k] || []).find(([d]) => s.pub >= d);
    return e ? e[1] : "Other";
  }
  // the specials tab, split by what they are
  const specialKind = (x) => { const n = x.n.toLowerCase();
    return /championship|league|prize pack|tournament|event|play! pokemon|pre-?release|judge|staff|world/.test(n) ? "Events & tournaments"
      : /promo|mcdonald|trick or trade|jumbo/.test(n) ? "Promos"
      : /deck|starter|start set|battle academy|trainer kit|kit\b|first partner|my first battle/.test(n) ? "Decks & starter sets" : "Other specials"; };
  const SPECIAL_ERAS = new Set([PROMO_GROUP, "Promos & Events", "Products & Extras", "Decks, Tins & Collections", "Starter Decks", "Other"]);
  const SETV = { q: "", sort: "new", kind: "main" }, SETD = { type: "c", sort: "price", q: "", n: 120 };
  const fmtMon = (d) => d ? new Date(d + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "";
  const SETS_GAMES = () => { const g = (GAMES[S.set.game] || GAMES.pokemon)[1]; return g ? g.length : 99; };
  const gameLabel = (k) => (META?.games || []).find((g) => g.slug === k)?.label || k;
  async function viewSets(v) {
    const gid = +((location.hash || "").split("/")[1] || 0);
    if (gid) return viewSet(v, gid);
    v.innerHTML = `<div class="searchbox"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></svg>
        <input id="sq" class="field" type="search" placeholder="Set name or code" autocomplete="off" aria-label="Find a set" value="${esc(SETV.q)}"></div>
      <div id="ss-game"></div><div id="ss-kind"></div><div id="ss-sort"></div><div id="ss-list"><p class="muted small">Loading sets…</p></div>`;
    const sets = await getJSON("sets.json"), today = localDay();
    const draw = () => {
      const q = SETV.q.trim().toLowerCase();
      // searching looks through both lists; otherwise series sets and specials are kept apart
      let rows = sets.filter((x) => gameOk(x.k) && (q ? (x.n + " " + (x.a || "")).toLowerCase().includes(q) : SPECIAL_ERAS.has(eraOf(x)) === (SETV.kind === "special")));
      const by = { new: (a, b) => (b.pub || "").localeCompare(a.pub || ""), box: (a, b) => (b.bb || 0) - (a.bb || 0),
        up: (a, b) => (b.c7 ?? -1e9) - (a.c7 ?? -1e9), down: (a, b) => (a.c7 ?? 1e9) - (b.c7 ?? 1e9), az: (a, b) => a.n.localeCompare(b.n) }[SETV.sort];
      if (SETV.sort === "box" || SETV.sort === "up" || SETV.sort === "down") rows = rows.filter((x) => SETV.sort === "box" ? x.bb : x.c7 != null);
      rows.sort(by);
      const rowOf = (x) => {
        const pic = x.lg ? `<img class="logo" src="${esc(x.lg)}" alt="" loading="lazy" onerror="this.outerHTML='<span class=&quot;ph abbr&quot;>${(x.a || x.n).replace(/[^\w ]/g, "").slice(0, 5)}</span>'">` : x.bbId ? img(x.bbId) : `<span class="ph abbr">${esc((x.a || x.n).slice(0, 5))}</span>`;
        return `<a class="row" href="#sets/${x.id}">${pic}<span style="min-width:0;display:flex;flex-direction:column;gap:2px"><span class="nm">${esc(x.n)}</span>
          <span class="st">${esc(gameLabel(x.k))}${x.pub ? ` · ${esc(fmtMon(x.pub))}` : ""}${x.np ? ` · ${x.np} products` : ""}</span></span>
          <span class="rt">${x.pub && x.pub > today ? `<span class="chip hot">Upcoming</span>` : ""}${x.bb ? `<b>${money(x.bb)}</b><small class="muted">${/booster box/i.test(x.bbN || "") ? "box" : "sealed"}</small>` : ""}${x.c7 != null ? `<small class="${cls(x.c7)}">${pct(x.c7)} 7d</small>` : ""}</span></a>`;
      };
      const grouped = SETV.sort === "new", cap = grouped ? 1000 : 150, shown = rows.slice(0, cap);
      if (grouped && shown.length) {   // newest first, one block per series (Mega Evolution, Scarlet & Violet, ...)
        const groups = new Map();
        for (const x of shown) { const era = eraOf(x), g = (SETS_GAMES() > 1 ? gameLabel(x.k) + " · " : "") + (SPECIAL_ERAS.has(era) ? specialKind(x) : era); if (!groups.has(g)) groups.set(g, []); groups.get(g).push(x); }
        $("#ss-list").innerHTML = [...groups].map(([g, list]) => `<section class="sec"><div class="sec-head"><h2>${esc(g)}</h2><span class="muted small">${list.length} set${list.length === 1 ? "" : "s"}</span></div><div class="list">${list.map(rowOf).join("")}</div></section>`).join("");
      } else {
        $("#ss-list").innerHTML = listOrEmpty(shown.map(rowOf), "No sets match. Try another name or switch games.");
      }
      if (!shown.length) $("#ss-list").innerHTML = `<div class="empty">No sets match. Try another name or switch games.</div>`;
      if (rows.length > cap) $("#ss-list").insertAdjacentHTML("beforeend", `<p class="muted small">Showing ${cap} of ${rows.length}. Search to find the rest.</p>`);
    };
    gamePick($("#ss-game"), () => draw());
    seg($("#ss-kind"), [["main", "Series sets"], ["special", "Promos, events & specials"]], SETV.kind, (k) => { SETV.kind = k; draw(); });
    seg($("#ss-sort"), [["new", "Newest"], ["box", "Box price"], ["up", "Up this week"], ["down", "Down this week"], ["az", "A–Z"]], SETV.sort, (k) => { SETV.sort = k; draw(); });
    let t; $("#sq").oninput = (e) => { clearTimeout(t); t = setTimeout(() => { SETV.q = e.target.value; draw(); }, 140); };
    draw();
  }
  // % change over the last 7 days of a daily price series (null when there isn't a week of prices)
  function chg7(sr) {
    if (!sr || sr.length < 2) return null;
    let i = sr.length - 1; while (i >= 0 && sr[i] == null) i--;
    if (i < 0) return null;
    let j = Math.min(i - 1, sr.length - 8); while (j >= 0 && sr[j] == null) j--;
    return j >= 0 && sr[j] ? (sr[i] - sr[j]) / sr[j] * 100 : null;
  }
  async function viewSet(v, gid) {
    v.innerHTML = `<p class="muted">Loading set…</p>`;
    const [d, allSets] = await Promise.all([getJSON(`set/${gid}.json`), getJSON("sets.json").catch(() => []), loadGraded()]);
    const sx = allSets.find((x) => x.id === gid) || {};
    const cards = d.items.filter((i) => i.t === "c"), sealed = d.items.filter((i) => i.t === "s");
    const uniq = new Map(); for (const i of cards) if (i.p && !uniq.has(i.id)) uniq.set(i.id, i.p);
    const value = [...uniq.values()].reduce((a, b) => a + b, 0), top = cards.reduce((a, b) => (b.p || 0) > (a?.p || 0) ? b : a, null);
    const { co, l10 } = GR ? grader() : {};
    const mover = cards.filter((i) => (i.p || 0) >= 500).map((i) => ({ i, c: chg7(i.s) })).filter((x) => x.c != null).sort((a, b) => b.c - a.c)[0];
    if (!cards.length) SETD.type = "s";
    // grading picks for this set: cards with steady PokemonPriceTracker graded sales, ranked by expected profit
    // after fees and shipping, with each card's own odds (Grade tab → Your assumptions)
    const GE = new Map();
    if (GR) for (const i of cards) {
      if (!i.p || GE.has(i.id)) continue;
      const gp = gradedOf(i.id); if (!solid(gp)) continue;
      GE.set(i.id, { i, gp, e: gradeEval(i.p, gp.p10, gp.p9, gp.p8, undefined, cardOdds(i.id)) });
    }
    const best = [...GE.values()].filter((x) => x.e.profit > 0).sort((a, b) => b.e.profit - a.e.profit);
    const onBoard = () => new Set(S.board.map((x) => x.id));
    const addChip = (i, ob) => ob.has(i.id) ? `<span class="chip good">On your board</span>` : `<span class="chip" data-addb="${i.id}|${gid}|${esc(i.n)}">+ Add to board</span>`;
    const gradeWhy = ({ i, gp, e }, ob, short) => `<span class="why">${vchip(e.v)} ${short ? "" : `<b class="${cls(e.profit)}">${signed(Math.round(e.profit))}</b> to grade · `}${esc(co)} ${esc(l10)} ${money(gp.p10, gp.p10 >= 100000)} (<b>${(gp.p10 / i.p).toFixed(1)}×</b>, ${gp.n10} sold) · ${Math.round(e.od.o10 * 100)}% ${esc(l10)}s${odTag(e.od)} ${addChip(i, ob)}</span>`;
    const gradeSec = !GR ? (pptKey() || !gameOk("pokemon") ? "" : `<p class="muted small" style="margin:0">Add your PokemonPriceTracker key in Mine → Settings to see which cards in this set are worth grading.</p>`)
      : !GE.size ? "" : `<section class="sec" id="sd-grade"><div class="sec-head"><h2>Worth grading</h2>${best.length > 5 ? `<button type="button" class="more" id="sd-gall">All ${best.length}</button>` : ""}</div>
        <p class="muted small" style="margin:0">${best.length ? `${best.length} of the ${GE.size} card${GE.size === 1 ? "" : "s"} with steady ${esc(co)} sales pay off` : `None of the ${GE.size} cards with steady ${esc(co)} sales pay off right now`} with ${esc(co)} ${esc(grader().tier[0])}, after grading fees, shipping and selling fees. Odds come from each card's own graded sales.</p>
        ${best.length ? `<div class="list" id="sd-glist">${best.slice(0, 5).map((x) => rowHTML({ id: x.i.id, g: gid, n: x.i.n, sn: [x.i.no, x.i.r].filter(Boolean).join(" · ") }, `<b class="up">${signed(Math.round(x.e.profit))}</b><small class="muted">raw ${money(x.i.p)}</small>`, gradeWhy(x, onBoard(), true))).join("")}</div>` : ""}</section>`;
    v.innerHTML = `<a class="more" href="#sets">← All sets</a>
      ${sx.lg || sx.bbId ? `<div class="set-hero${sx.lg ? " logo" : ""}">${sx.lg ? `<img src="${esc(sx.lg)}" alt="${esc(d.n)} logo" onerror="this.parentNode.remove()">` : img(sx.bbId, 1000)}</div>` : ""}
      <section class="sec"><h2 style="margin:0">${esc(d.n)}</h2><p class="muted small" style="margin:2px 0 0">${esc(gameLabel(d.k))}${d.pub ? ` · ${d.pub > localDay() ? "releases" : "released"} ${esc(fmtMon(d.pub))}` : ""} · ${cards.length} cards · ${sealed.length} sealed</p></section>
      <div class="tiles"><div class="tile"><span class="lab">Every card, one each</span><b>${money(value, true)}</b><small>${uniq.size} priced</small></div>
        <div class="tile"><span class="lab">Top card</span><b>${top?.p ? money(top.p, true) : "—"}</b><small>${esc(top ? cleanN(top.n) : "")}</small></div>
        <div class="tile"><span class="lab">Up most, 7 days</span><b class="${mover ? cls(mover.c) : ""}">${mover ? pct(mover.c) : "—"}</b><small>${esc(mover ? cleanN(mover.i.n) : "Needs a week of prices")}</small></div></div>
      ${gradeSec}
      <div id="sd-type"></div><div class="searchbox"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></svg>
        <input id="sdq" class="field" type="search" placeholder="Card name, number or rarity" autocomplete="off" aria-label="Search this set" value=""></div>
      <div id="sd-sort"></div><div id="sd-list"></div>`;
    SETD.q = ""; SETD.n = 120;
    const num = (no) => { const m = String(no || "").match(/\d+/); return m ? +m[0] : 1e9; };
    const draw = () => {
      const q = SETD.q.trim().toLowerCase();
      let rows = (SETD.type === "s" ? sealed : cards).filter((i) => !q || (i.n + " " + (i.no || "") + " " + (i.r || "")).toLowerCase().includes(q)).map((i) => ({ i, c: chg7(i.s) }));
      if (SETD.sort === "up" || SETD.sort === "down") rows = rows.filter((x) => x.c != null);
      if (SETD.sort === "grade") rows = rows.filter((x) => GE.has(x.i.id));
      const ob = onBoard();
      rows.sort({ price: (a, b) => (b.i.p || 0) - (a.i.p || 0), up: (a, b) => b.c - a.c, down: (a, b) => a.c - b.c,
        grade: (a, b) => GE.get(b.i.id).e.profit - GE.get(a.i.id).e.profit,
        num: (a, b) => num(a.i.no) - num(b.i.no) || String(a.i.no).localeCompare(String(b.i.no)) }[SETD.sort]);
      const out = rows.slice(0, SETD.n).map(({ i, c }) => {
        const gp = GR && i.t === "c" ? gradedOf(i.id) : null, ge = i.t === "c" ? GE.get(i.id) : null;
        const extra = ge ? gradeWhy(ge, ob) : gp?.p10 ? `<span class="why">${esc(co)} ${esc(l10)} ${money(gp.p10, gp.p10 >= 100000)}${i.p ? ` · <b>${(gp.p10 / i.p).toFixed(1)}×</b>` : ""} · ${gp.n10} sold in 90 days</span>` : "";
        return rowHTML({ id: i.id, g: gid, n: i.n, sn: [i.no, i.r].filter(Boolean).join(" · ") },
          `<b>${i.p ? money(i.p) : "—"}</b>${c != null ? `<small class="${cls(c)}">${pct(c)} 7d</small>` : i.lo ? `<small class="muted">low ${money(i.lo)}</small>` : ""}`, extra);
      });
      $("#sd-list").innerHTML = listOrEmpty(out, SETD.type === "s" ? "No sealed products in this set." : "No cards match.")
        + (rows.length > SETD.n ? `<button type="button" class="btn full" id="sd-more">Show more (${rows.length - SETD.n} left)</button>` : "");
      const more = $("#sd-more"); if (more) more.onclick = () => { SETD.n += 200; draw(); };
    };
    seg($("#sd-type"), [["c", `Cards (${cards.length})`], ["s", `Sealed (${sealed.length})`]], SETD.type, (k) => { SETD.type = k; SETD.n = 120; draw(); });
    if (SETD.sort === "grade" && !GE.size) SETD.sort = "price";
    const sortSeg = () => seg($("#sd-sort"), [["price", "Price"], ...(GE.size ? [["grade", "Grade it"]] : []), ["up", "Up 7d"], ["down", "Down 7d"], ["num", "Number"]], SETD.sort, (k) => { SETD.sort = k; draw(); });
    sortSeg();
    const gall = $("#sd-gall"); if (gall) gall.onclick = () => { SETD.type = "c"; SETD.sort = "grade"; SETD.n = 120;
      seg($("#sd-type"), [["c", `Cards (${cards.length})`], ["s", `Sealed (${sealed.length})`]], SETD.type, (k) => { SETD.type = k; SETD.n = 120; draw(); }); sortSeg(); draw(); $("#sd-type").scrollIntoView({ behavior: "smooth" }); };
    // + Add to board chips (in the picks and the card list) don't open the card
    const addb = (e) => {
      const b = e.target.closest("[data-addb]"); if (!b) return;
      e.stopPropagation();
      const [id, g, ...n] = b.dataset.addb.split("|"); boardAdd({ id: +id, g: +g, n: n.join("|") }); toast("Added to your grading board");
      v.querySelectorAll(`[data-addb^="${id}|"]`).forEach((c) => { c.outerHTML = `<span class="chip good">On your board</span>`; });
    };
    ["#sd-list", "#sd-glist"].forEach((sel) => $(sel)?.addEventListener("click", addb, true));
    let t; $("#sdq").oninput = (e) => { clearTimeout(t); t = setTimeout(() => { SETD.q = e.target.value; SETD.n = 120; draw(); }, 140); };
    draw();
  }
  function pickAdd(id, g, n) {
    const r = IDX.get(keyOf(id, n)) || IDX.get(String(id));
    if (PICK.list === "ledger") {
      PICK.form.lines.push(LG.lineFromCard({ id, g, n, t: r ? r[3] : "c", price: 0, set: setName(g) }));
      toast(`Added to this buy (${PICK.form.lines.length})`); return;
    }
    const x = { k: keyOf(id, n), id, g, n, t: r ? r[3] : "c", qty: 1, cond: "NM", p: r ? r[4] : null };
    const list = PICK.list === "lot" ? S.lot : S.trade[PICK.list];
    const have = list.find((y) => y.k === x.k);
    if (have) have.qty++; else list.push(x);
    save(); toast(`Added to ${PICK.label}`);
  }

  /* ---------- card sheet ---------- */
  const sheet = $("#sheet");
  sheet.addEventListener("click", (e) => { if (e.target === sheet || e.target.closest(".close")) closeCard(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !sheet.hidden) closeCard(); });
  function closeCard() { sheet.hidden = true; document.body.style.overflow = ""; if (TAB === "today" || TAB === "mine" || TAB === "tools") route(); }
  async function openCard(id, g, n) {
    sheet.hidden = false; document.body.style.overflow = "hidden";
    const card = $("#sheet-card");
    card.innerHTML = `<div class="grab"><span class="lab">Card details</span><button type="button" class="btn sm close">Close</button></div><p class="muted">Loading…</p>`;
    const [{ it, set }, eb, , ta, daily, strat, backtest, deal, pkmn, , chan] = await Promise.all([detail(id, g, n), getJSON("ebay.json").catch(() => ({ cards: {} })), loadGraded(), TA, dailyFile(g), STRAT, BACKTEST, DEAL, PKMN, LEDGER, CHAN]);
    if (!it) { card.innerHTML = `<div class="grab"><span class="lab">Card details</span><button type="button" class="btn sm close">Close</button></div><div class="empty"><b>No price for this one yet</b>It may be too new or not sold recently.</div>`; return; }
    const x = { id: it.id, g, n: it.n, t: it.t, sn: set.n };
    S.recent = [x, ...S.recent.filter((y) => !(y.id === x.id && y.n === x.n))].slice(0, 12); save();
    const p = it.p, lo = it.lo, f = flip(p, lo, it.t), ch = it.ch || {};
    const e = eb.cards?.[it.id], ebAge = e ? daysAgo(e.at) : null;
    const inInv = S.inv.find((y) => y.k === keyOf(it.id, it.n)), watching = S.watch.find((y) => y.k === keyOf(it.id, it.n));
    const mine = LS ? LG.compute(LS.T).items.filter((y) => String(y.tcg) === String(it.id) && y.n === it.n && y.left) : [];
    const held = mine.reduce((a, y) => a + y.left, 0), slabs = mine.filter((y) => y.kind === "Graded" && y.grade).map((y) => `${y.grader} ${y.grade}`);
    const no = (it.n.match(/ - ([\w/-]+)/) || [])[1];
    const simple = `<section class="sec chart panel"><span class="lab">Price history</span>${chart(it.s, set.dates)}</section>`;
    const platRows = Object.entries(FEES.sell).map(([k, pl]) => `<div><span>${k === "none" ? "Sell in person" : `Sell on ${esc(pl.label)}`}</span><span>${p ? money(net(p, it.t, k)) : "—"}</span></div>`).join("");
    card.innerHTML = `<div class="grab"><span class="lab">${esc(gameOfSet(g) === "pokemon" ? (it.t === "s" ? "Sealed" : "Card") : `${gameLabel(gameOfSet(g))}${it.t === "s" ? " · sealed" : ""}`)}</span><button type="button" class="btn sm close">Close</button></div>
      <div class="hero">${img(it.id, 1000)}<div style="display:flex;flex-direction:column;gap:6px;min-width:0">
        <h2>${esc(cleanN(it.n))}</h2><span class="muted small">${esc(set.n)}${it.r ? ` · ${esc(it.r)}` : ""}</span>
        <span class="lab" style="margin-top:6px">Market</span><span class="big">${money(p)}</span>
        <div class="chips">${[["1", "1D"], ["7", "7D"], ["30", "30D"], ["90", "90D"], ["a", "All"]].filter(([k]) => ch[k] != null).map(([k, l]) => `<span class="chip ${ch[k] > 0 ? "good" : ch[k] < 0 ? "bad" : ""}">${l} ${pct(ch[k])}</span>`).join("")}</div>
      </div></div>
      <div class="prices"><div class="tile"><span class="lab">Lowest listing</span><b>${money(lo)}</b><small class="${lo && p ? cls(p - lo) : ""}">${lo && p ? `${pct((lo - p) / p * 100, 0)} vs market` : "on TCGplayer"}</small></div>
        <div class="tile"><span class="lab">Max buy</span><b>${money(maxBuy(p, it.t))}</b><small>for ${S.set.roi}% profit</small></div>
        <div class="tile"><span class="lab">Flip now</span><b class="${f ? cls(f.pr) : ""}">${f ? signed(f.pr) : "—"}</b><small>${f ? `${f.roi.toFixed(0)}% buying the lowest` : "no listing"}</small></div></div>
      ${slabs.length ? `<p class="small muted panel" style="margin:0">You hold this card as ${esc([...new Set(slabs)].join(", "))}. The Deal check below is for buying a raw copy; for your graded copy, open it in Mine → Ledger and tap Check sold prices.</p>` : ""}
      ${deal ? `<section class="sec panel" id="c-deal"></section>` : ""}
      ${deal && chan ? `<section class="sec panel" id="c-ch"></section>` : ""}
      ${ta && strat ? `<section class="sec" id="c-strat" hidden></section>` : ""}
      ${ta ? `<section class="sec ta" id="c-ta"></section>` : simple}
      ${it.t === "c" ? `<section class="sec"><span class="lab">By condition</span><div class="cond">${COND.map(([c, m]) => `<div><b>${c}</b>${money(Math.round(p * m), p * m >= 10000)}</div>`).join("")}</div></section>` : ""}
      <section class="sec panel"><span class="lab">What it's worth to you</span><div class="kv">${platRows}
        <div><span>Cash offer at ${S.set.cash}%</span><span>${money(Math.round(p * S.set.cash / 100))}</span></div>
        <div><span>Trade credit at ${S.set.trade}%</span><span>${money(Math.round(p * S.set.trade / 100))}</span></div></div>
        <p class="muted small" style="margin:6px 0 0">Selling nets are after fees and shipping out. Change them in Mine → Settings.</p></section>
      ${it.t === "c" && GR ? gradedBlock(it, p) : ""}
      ${e && (e.r || e.p10) ? `<section class="sec panel"><span class="lab">eBay Buy It Now · checked ${ebAge < 1 ? "today" : ebAge === 1 ? "yesterday" : `${ebAge} days ago`}</span>
        <div class="kv">${e.r ? `<div><span>Cheapest raw (${e.r[1]} listing${e.r[1] === 1 ? "" : "s"})</span><span><a href="${esc(e.r[2])}" target="_blank" rel="noopener">${money(e.r[0])} ↗</a></span></div>` : ""}
        ${e.p10 ? `<div><span>Cheapest PSA 10 (${e.p10[1]} listing${e.p10[1] === 1 ? "" : "s"})</span><span><a href="${esc(e.p10[2])}" target="_blank" rel="noopener">${money(e.p10[0])} ↗</a></span></div>` : ""}</div>
        <p class="muted small" style="margin:6px 0 0">Shipping included. Listings change fast: tap through for the live price.</p></section>` : ""}
      <section class="sec"><div class="btns">
        ${LS ? `<button type="button" class="btn primary" id="c-buy">${held ? `Bought it · you hold ${held}` : "Bought it"}</button>` : `<button type="button" class="btn primary" id="c-inv">${inInv ? `In inventory (${inInv.qty})` : "Add to inventory"}</button>`}
        <button type="button" class="btn" id="c-watch">${watching ? `Watching at ${money(watching.target)}` : "Watch price"}</button>
        <button type="button" class="btn" data-add="give">Trade: I give</button><button type="button" class="btn" data-add="get">Trade: I get</button>
        <button type="button" class="btn" data-add="lot">Add to lot offer</button>${it.t === "c" ? `<button type="button" class="btn" id="c-grade">${S.board.some((y) => y.k === keyOf(it.id, it.n)) ? "On grading board" : "Grade it?"}</button>` : ""}</div>
        <div id="c-form"></div></section>
      <section class="sec"><span class="lab">Buy</span><div class="links">
        <a class="btn sm" href="${buyUrl(it.n, it.no || no || "", { p: it.p, g, kind: it.t })}" target="_blank" rel="noopener">Buy on eBay ↗</a>
        ${it.t === "c" ? `<a class="btn sm" href="${buyUrl(it.n, it.no || no || "", { g, grade: "PSA 10" })}" target="_blank" rel="noopener">Buy PSA 10 ↗</a>` : ""}
        <a class="btn sm" href="${tcgUrl(it.id)}" target="_blank" rel="noopener">TCGplayer ↗</a></div></section>
      <section class="sec"><span class="lab">Check elsewhere</span><div class="links">
        <a class="btn sm" href="${soldUrl(it.n, no || "")}" target="_blank" rel="noopener">eBay sold ↗</a>
        ${it.t === "c" ? `<a class="btn sm" href="${soldUrl(it.n, (no || "") + " PSA 10")}" target="_blank" rel="noopener">PSA 10 sold ↗</a><a class="btn sm" href="https://www.pricecharting.com/search-products?q=${encodeURIComponent(cleanN(it.n))}&type=prices" target="_blank" rel="noopener">All grades ↗</a>` : ""}
        <a class="btn sm" href="${BASE}product.html?id=${it.id}&set=${g}" target="_blank" rel="noopener">Full page ↗</a></div></section>`;
    let read = null;
    if (ta) try { read = ta.mount($("#c-ta"), { dates: set.dates, values: it.s || [], daily: ta.dailyOf(daily, it.id, it.n) }); }
      catch (err) { console.error(err); $("#c-ta").outerHTML = simple; }
    const box = $("#c-strat");
    let reading = null;
    if (box) try {
      if (!read) throw new Error("no chart reading");
      reading = strat.mount(box, strat.plan(read, { pub: set.pub, k: set.k, game: gameLabel(set.k) }, { net: (x) => net(x, it.t), shipIn: shipIn(it.t), roi: S.set.roi, maxBuy: (x) => maxBuy(x, it.t), lo }, backtest));
      box.hidden = false;
    } catch (err) { console.error(err); box.remove(); }
    const dbox = $("#c-deal");
    if (dbox) try {
      const item = { id: it.id, n: it.n, name: it.n, t: it.t, r: it.r, setN: set.n, tcg: p, tcgDay: dayNum(set.dates?.[set.dates.length - 1]) };
      const warning = reading && !reading.demoted ? { id: reading.id, verdict: reading.verdict, name: reading.name } : null;
      const conn = pkmnConn(), had = pkmn && conn ? pkmn._mem.get(pkmn.memKey(it)) : null;
      const first = had ? await had : null;
      // the comparison follows the Deal check: cost = what this copy would cost you, starting price = the eBay sold value used above
      const cbox = $("#c-ch"); let cm = null;
      const chOf = (r) => { const F = r.routes.flip; return { cost: F.cost, ref: F.exit ?? null, refLabel: F.exit ? `${F.grade === "sealed" ? "sealed" : "raw"} sold median${F.grade === "raw" ? ", condition applied" : ""}` : null }; };
      const after = (r) => { if (!cbox || !chan) return; try { cm ? cm.update(chOf(r)) : (cm = chan.mount(cbox, { ...chanOpts(it.t === "s" ? "sealed" : "raw", it.n), ...chOf(r) })); } catch (err) { console.error(err); cbox.remove(); } };
      deal.mount(dbox, item, first && first.ok ? first.data : null, { ask: lo || p || 0, cond: "NM", shipIn: shipIn(it.t), taxIn: S.set.taxIn }, dealCfg(p), { warning },
        pkmn && conn ? { load: (fresh) => pkmn.get(item, conn, fresh).then(soldNote), after, cash: (c) => { CASH_NOW = c; } } : { off: true, note: pkmn ? "Sold prices aren't set up yet: add your PkmnPrices relay in Mine → Settings. Until then this stays a PASS." : "The sold-price reader didn't load.", after, cash: (c) => { CASH_NOW = c; } });
    } catch (err) { console.error(err); dbox.remove(); }
    const form = $("#c-form");
    const cb = $("#c-buy"); if (cb) cb.onclick = () => {
      // a buy for this card at the lowest listing (change it to what you paid); the Ledger opens with it filled in
      LEDGER_DRAFT = LG.lineFromCard({ id: it.id, g, n: it.n, t: it.t, price: lo || p || 0, set: set.n });
      SUB.mine = "ledger"; sheet.hidden = true; document.body.style.overflow = "";
      if (location.hash === "#mine") route(); else location.hash = "mine";
    };
    if ($("#c-inv")) $("#c-inv").onclick = () => {
      const k = keyOf(it.id, it.n), have = S.inv.find((y) => y.k === k);
      form.innerHTML = `<form class="inline-form" id="f-inv"><div class="form">
          <label class="f">Quantity<input class="field" id="fi-q" type="number" inputmode="numeric" min="1" step="1" value="${have ? have.qty : 1}"></label>
          <label class="f">Paid each $<input class="field" id="fi-c" type="number" inputmode="decimal" min="0" step="0.01" value="${have ? dollars(have.cost) : dollars(lo || p)}"></label>
          ${it.t === "c" ? `<label class="f full">Condition<select class="select" id="fi-cond">${COND.map(([c]) => `<option${(have?.cond || "NM") === c ? " selected" : ""}>${c}</option>`).join("")}</select></label>` : ""}</div>
        <div class="btns"><button class="btn primary" type="submit">Save</button>${have ? `<button class="btn ghost danger" type="button" id="fi-del">Remove</button>` : ""}</div></form>`;
      $("#f-inv").onsubmit = (ev) => {
        ev.preventDefault();
        const row = { k, id: it.id, g, n: it.n, t: it.t, qty: Math.max(1, parseInt($("#fi-q").value, 10) || 1), cost: cents($("#fi-c").value), cond: $("#fi-cond")?.value || "NM", at: localDay() };
        if (have) Object.assign(have, row); else S.inv.push(row);
        save(); toast("Saved to inventory"); openCard(id, g, n);
      };
      if (have) $("#fi-del").onclick = () => { S.inv = S.inv.filter((y) => y.k !== k); save(); toast("Removed"); openCard(id, g, n); };
    };
    $("#c-watch").onclick = () => {
      const k = keyOf(it.id, it.n), have = S.watch.find((y) => y.k === k);
      form.innerHTML = `<form class="inline-form" id="f-w"><label class="f">Alert me when it's at or under $<input class="field" id="fw-t" type="number" inputmode="decimal" min="0" step="0.01" value="${dollars(have ? have.target : maxBuy(p, it.t))}"></label>
        <p class="muted small" style="margin:0">Starts at your max buy for ${S.set.roi}% profit. Alerts show on Today when the lowest listing or market price reaches it.</p>
        <div class="btns"><button class="btn primary" type="submit">Save</button>${have ? `<button class="btn ghost danger" type="button" id="fw-del">Stop watching</button>` : ""}</div></form>`;
      $("#f-w").onsubmit = (ev) => {
        ev.preventDefault();
        const row = { k, id: it.id, g, n: it.n, t: it.t, target: cents($("#fw-t").value) };
        if (have) Object.assign(have, row); else S.watch.push(row);
        save(); toast("Watching"); openCard(id, g, n);
      };
      if (have) $("#fw-del").onclick = () => { S.watch = S.watch.filter((y) => y.k !== k); save(); toast("Stopped watching"); openCard(id, g, n); };
    };
    $$("[data-add]", card).forEach((b) => b.onclick = () => {
      const label = { give: "I give", get: "I get", lot: "the lot" }[b.dataset.add];
      PICK = { list: b.dataset.add, label, back: "tools" }; pickAdd(it.id, g, it.n); PICK = null;
      SUB.tools = b.dataset.add === "lot" ? "lot" : "trade";
    });
    const gb = $("#c-grade"); if (gb) gb.onclick = () => { boardAdd({ id: it.id, g, n: it.n }); GRADE.raw = dollars(p); GRADE.name = cleanN(it.n); GRADE.no = no || ""; SUB.grade = "board"; sheet.hidden = true; document.body.style.overflow = ""; toast("Added to your grading board"); if (location.hash === "#grade") route(); else location.hash = "grade"; };
  }

  /* ---------- Show check: a card in front of you, a seller's price -> BUY candidate or PASS on real sold prices ----------
     The Deal check (edge-deal.js) with the owner's buying rules: sold prices read once per card per visit through the
     relay (memory only), in person (no shipping or tax unless typed), cash on hand optional and never saved. */
  const SC = { q: "", pick: null, ask: "", cond: "NM", log: [], credits: 0 };
  // from a watched card (Watchlist, Today): Show check with the card picked and today's lowest price as the asking price
  const dcChip = (w, price) => `<span class="chip x w-dc" role="button" tabindex="0" data-id="${w.id}" data-g="${w.g}" data-n="${esc(w.n)}" data-ask="${price || 0}">Deal check${price ? ` at ${money(price)}` : ""}</span>`;
  function wireDc(el) {
    $$(".w-dc", el).forEach((b) => { b.onclick = (e) => { e.stopPropagation(); e.preventDefault();
      SC.pick = { id: +b.dataset.id, g: +b.dataset.g, n: b.dataset.n, q: cleanN(b.dataset.n).toLowerCase() }; SC.q = cleanN(b.dataset.n); SC.ask = +b.dataset.ask ? (+b.dataset.ask / 100).toFixed(2) : ""; SC.cond = "NM"; SC.auto = true;
      SUB.deals = "check"; if (location.hash === "#deals") route(); else location.hash = "deals"; }; });
  }
  async function drawShowCheck(el) {
    const [deal, pkmn] = await Promise.all([DEAL, PKMN]), conn = pkmnConn();
    const fmt = (c) => money(c), lim = S.set.buyLimit ?? 7500, res = S.set.cashReserve ?? 10000;
    el.innerHTML = `<p class="muted small" style="margin:0 0 8px">At a show or a local buy: find the card, type the seller's price and condition. Real eBay sold prices decide it. Your rules: ${fmt(lim)} most per purchase, ${fmt(res)} cash kept back, ${fmt(S.set.minProfit)} and ${S.set.roi}% profit. Enter your cash on hand once per visit.</p>
      ${conn ? "" : `<div class="panel sc-off"><b>Sold prices aren't set up on this phone</b><p class="small muted" style="margin:4px 0 8px">Pair it once in Mine → Settings. Without sold prices every check stays a PASS.</p><div class="btns"><button type="button" class="btn sm primary sc-pair">Go to Settings</button></div></div>`}
      <div class="searchbox"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></svg>
        <input id="sc-q" class="field" type="search" placeholder="Card name and number, e.g. Umbreon 161" autocomplete="off" enterkeyhint="search" aria-label="Find the card" value="${esc(SC.q)}"></div>
      <div id="sc-res"></div><div id="sc-card"></div>
      <div id="sc-log"></div>`;
    const pair = $(".sc-pair", el); if (pair) pair.onclick = () => { SUB.mine = "set"; location.hash = "mine"; };
    await loadIndex();
    const q = $("#sc-q", el);
    if (!q) return;                                   // he switched to another tab while the card list loaded
    const results = (typed) => {
      SC.q = q.value; const t = q.value.trim().toLowerCase(), box = $("#sc-res", el);
      if (!t || (!typed && SC.pick && t === SC.pick.q)) { box.innerHTML = ""; return; }   // the picked card's name: no list until he types
      const out = findCards(t, (r) => gameOk(gameOfSet(r[2])));
      if (!out.length) { box.innerHTML = `<p class="muted small">Nothing found. Try the card number (e.g. 161/131) or fewer words.</p>`; return; }
      pagedList(box, out, 20, (r) => `<button type="button" class="sc-hit" data-sc="${r[0]}" data-g="${r[2]}" data-n="${esc(r[1])}" data-t="${r[3]}">
          ${img(r[0])}<span class="sc-hn"><b>${esc(cleanN(r[1]))}</b><small class="muted">${esc(setName(r[2]))} · ${r[3] === "s" ? "sealed" : esc(printingOfRow(r[1], r[3]))}</small></span><span class="sc-hp"><b>${money(r[4])}</b><small class="muted">TCGplayer</small></span></button>`,
        (nodes) => nodes.forEach((b) => { b.onclick = () => pick({ id: +b.dataset.sc, g: +b.dataset.g, n: b.dataset.n, t: b.dataset.t }); }));
    };
    let tm; q.addEventListener("input", () => { clearTimeout(tm); tm = setTimeout(() => results(true), 140); });
    const pick = async (x) => {
      SC.pick = { ...x, q: cleanN(x.n).toLowerCase() }; SC.ask = ""; q.value = cleanN(x.n); SC.q = q.value; $("#sc-res", el).innerHTML = "";
      await drawPick(true);
    };
    // the picked card: header, the Deal check (sold prices read once per card per visit), quick actions
    const drawPick = async (load) => {
      const box = $("#sc-card", el), x = SC.pick; if (!box || !x) return;
      const { it, set } = await detail(x.id, x.g, x.n);
      if (!it) { box.innerHTML = `<div class="empty">No TCGplayer listing for this one: Edge can't match it to sold prices.</div>`; return; }
      box.innerHTML = `<div class="sc-head">${img(it.id)}<div><b>${esc(cleanN(it.n))}</b><small class="muted">${esc(set.n)}${it.p ? ` · TCGplayer market ${money(it.p)}` : ""}</small></div></div>
        <div class="sc-deal" id="sc-deal"></div>
        <div class="btns sc-acts"><button type="button" class="btn sm sc-open">Open full card</button><button type="button" class="btn sm sc-watch">Watch at max to pay</button><button type="button" class="btn sm sc-blist">${BLS && BLS.has(keyOf(it.id, it.n)) ? "On your buy list" : "Add to buy list"}</button>${LS ? `<button type="button" class="btn sm sc-buy">Bought it</button>` : ""}</div>`;
      const item = { id: it.id, n: it.n, name: it.n, t: it.t, r: it.r, setN: set.n, tcg: it.p, tcgDay: dayNum(set.dates?.[set.dates.length - 1]) };
      const had = pkmn && conn ? pkmn._mem.get(pkmn.memKey(it)) : null, first = had ? await had : null;
      const offer = { ask: SC.ask === "" ? 0 : Math.round(parseFloat(SC.ask) * 100) || 0, cond: it.t === "s" ? "NM" : SC.cond, shipIn: 0, taxIn: 0 };
      let lastR = null;
      const after = (r, data) => {
        lastR = r; SC.ask = offer.ask ? (offer.ask / 100).toFixed(2) : ""; SC.cond = offer.cond;
        // a live read of a card on the buy list refreshes its saved estimate (rounded; no sold prices kept)
        if (data && BLS && BLS.has(keyOf(it.id, it.n))) BUYL.then((bl) => { if (bl && deal) BLS.setEst(keyOf(it.id, it.n), bl.derive(deal, item, data, dealCfg(it.p))); });
        if (data && offer.ask) {
          const F = r.routes.flip, key = `${it.id}|${offer.ask}|${offer.cond}`;
          if (!SC.log.length || SC.log[0].key !== key) SC.log = [{ key, id: it.id, g: x.g, n: it.n, ask: offer.ask, cond: offer.cond, verdict: r.verdict, why: r.why, profit: F.profit, max: F.max }, ...SC.log.filter((y) => y.key !== key)].slice(0, 20);
          drawLog();
        }
      };
      const mounted = deal.mount($("#sc-deal", box), item, first && first.ok ? first.data : null, offer, dealCfg(it.p), {},
        pkmn && conn ? { load: (fresh) => pkmn.get(item, conn, fresh).then((res) => { if (res && res.meta) SC.credits += res.meta.credits || 0; return soldNote(res); }), after, cash: (c) => { CASH_NOW = c; } } : { off: true, note: "Sold prices aren't set up yet: pair this phone in Mine → Settings.", after, cash: (c) => { CASH_NOW = c; } });
      const lb = $("#sc-deal .dl-load", box);
      const askBox = () => $("#sc-deal .dl-ask", box);
      if (askBox()) askBox().focus({ preventScroll: true });
      if (load && lb && !(first && first.ok)) { lb.click(); const a = askBox(); if (a) a.focus({ preventScroll: true }); }      // picking a card reads its sold prices once (memory only for this visit)
      $(".sc-open", box).onclick = () => openCard(it.id, x.g, it.n);
      $(".sc-blist", box).onclick = (e) => { if (blAdd({ id: it.id, g: x.g, n: it.n, t: it.t, r: it.r, setN: set.n })) e.target.textContent = "On your buy list"; };
      $(".sc-watch", box).onclick = () => {
        const F = lastR && lastR.routes.flip, tgt = F && F.max ? F.max : null;
        if (!tgt) { toast("No max to pay yet: needs sold prices that clear your rules"); return; }
        const k = keyOf(it.id, it.n);
        S.watch = [{ k, id: it.id, g: x.g, n: it.n, t: it.t, target: tgt, from: "deal" }, ...S.watch.filter((w) => w.k !== k)]; save();
        toast(`Watching at ${money(tgt)}`);
      };
      const bb = $(".sc-buy", box); if (bb) bb.onclick = () => {
        LEDGER_DRAFT = LG.lineFromCard({ id: it.id, g: x.g, n: it.n, t: it.t, price: offer.ask || it.p || 0, set: set.n });
        SUB.mine = "ledger"; location.hash = "mine";
      };
      return mounted;
    };
    const drawLog = () => {
      const box = $("#sc-log", el); if (!box) return;
      box.innerHTML = SC.log.length ? `<div class="sec"><div class="sec-head"><h2>Checked this visit</h2><span class="chip">${SC.credits.toLocaleString("en-US")} credits</span></div>
        <div class="sc-list">${SC.log.map((r) => `<button type="button" class="sc-hit sc-past" data-sc="${r.id}" data-g="${r.g}" data-n="${esc(r.n)}" data-ask="${r.ask}" data-cond="${r.cond}">
          <span class="sc-hn"><b>${esc(cleanN(r.n))}</b><small class="muted">${money(r.ask)} · ${r.cond}</small></span>
          <span class="sc-hp"><b class="${r.verdict === "buy" ? "up" : ""}">${r.verdict === "buy" ? "BUY candidate" : "PASS"}</b><small class="muted">${r.verdict === "buy" ? signed(r.profit) : esc(r.why)}</small></span></button>`).join("")}</div>
        <p class="muted small">Kept only while Edge is open. Sold prices for these cards are in memory, so re-checking them costs nothing.</p></div>` : "";
      $$(".sc-past", box).forEach((b) => { b.onclick = async () => { SC.ask = (+b.dataset.ask / 100).toFixed(2); SC.cond = b.dataset.cond; SC.pick = { id: +b.dataset.sc, g: +b.dataset.g, n: b.dataset.n, q: cleanN(b.dataset.n).toLowerCase() };
        q.value = cleanN(b.dataset.n); await drawPick(false); window.scrollTo({ top: 0, behavior: "smooth" }); }; });
    };
    results();
    if (SC.pick) { const auto = !!SC.auto; SC.auto = false; await drawPick(auto); } else q.focus({ preventScroll: true });
    drawLog();
  }

  /* ---------- Daily deals: the Near Mint finder's newest results, through the relay (paired phones only) ----------
     The finder's own calls (CANDIDATE / UNCERTAIN / REJECT, reasons, its max price) are leads, never a BUY here: a row's
     Deal check runs today's sold prices and the owner's rules (limit, reserve, $5 and 20%) before anything says BUY. */
  const DD = { data: null, at: 0, err: "" };
  const DD_WHY = { "not-connected": "Daily deals isn't connected yet: the finder's results reach your phone once its read-only key is added to your relay.",
    none: "No finder results have been published yet.", denied: "The relay didn't recognise this phone. Pair it again in Mine → Settings.",
    network: "No connection to the relay. Try again.", bad: "Couldn't read the latest finder results. Try again later." };
  async function loadDaily(force) {
    const conn = pkmnConn();
    if (!conn) return { err: "unpaired" };
    if (DD.data && !force && Date.now() - DD.at < 10 * 6e4) return { data: DD.data };
    let r; try { r = await fetch(`${conn.relay.replace(/\/$/, "")}/edge/finder`, { headers: { "X-Edge-Pass": conn.pass, Accept: "application/json" }, cache: "no-store" }); } catch { return { err: "network" }; }
    if (r.status === 401) return { err: "denied" };
    let j = null; try { j = await r.json(); } catch {}
    if (!r.ok) return { err: (j && j.error) === "not-connected" ? "not-connected" : (j && j.error) === "none" ? "none" : "bad" };
    if (!j || j.kind !== "nm-finder-phone" || !Array.isArray(j.cards)) return { err: "bad" };
    DD.data = j; DD.at = Date.now(); return { data: j };
  }
  /* The finder's card is one printing; TCGplayer gives every printing of a card the same product id, so the id alone can
     pick the wrong printing (Unlimited vs 1st Edition, Normal vs Reverse Holofoil). Match id + exact name, else id + the
     finder's printing; no match -> no Deal check rather than a guess. */
  const DD_PR = ["1st Edition Holofoil", "1st Edition Normal", "1st Edition", "Unlimited Holofoil", "Unlimited", "Reverse Holofoil", "Holofoil", "Normal"];
  const prOf = (n) => { const m = /\(([^()]*)\)\s*$/.exec(n || ""); return m && DD_PR.includes(m[1]) ? m[1] : "Normal"; };
  function ddRow(x) {
    const exact = IDX.get(keyOf(x.tcgplayer_id, x.name));
    if (exact) return exact;
    const same = (ROWS || []).filter((r) => r[0] === +x.tcgplayer_id && prOf(r[1]) === (x.printing || "Normal"));
    return same.length === 1 ? same[0] : null;
  }
  const usd = (x) => x == null ? "—" : money(Math.round(x * 100));
  async function drawDaily(el, force) {
    el.innerHTML = `<p class="muted small">Getting the finder's latest results…</p>`;
    const { data: d, err } = await loadDaily(force);
    if (err === "unpaired") { el.innerHTML = `<div class="panel sc-off"><b>Sold prices aren't set up on this phone</b><p class="small muted" style="margin:4px 0 8px">Daily deals and Deal check use your private relay. Pair this phone once in Mine → Settings.</p><div class="btns"><button type="button" class="btn sm primary sc-pair">Go to Settings</button></div></div>`;
      $(".sc-pair", el).onclick = () => { SUB.mine = "set"; location.hash = "mine"; }; return; }
    if (err) { el.innerHTML = `<div class="empty dd-err" data-err="${esc(err)}"><b>${err === "not-connected" ? "Not connected yet" : "No results to show"}</b>${esc(DD_WHY[err] || DD_WHY.bad)}</div><div class="btns"><button type="button" class="btn sm dd-ref">Try again</button></div>`;
      $(".dd-ref", el).onclick = () => drawDaily(el, true); return; }
    await loadIndex();
    const today = localDay(), age = d.data_day ? Math.round((Date.parse(today) - Date.parse(d.data_day)) / 864e5) : null, c = d.counts || {};
    const grp = (lab) => d.cards.filter((x) => x.label === lab);
    const row = (x) => {
      const r = ddRow(x), name = cleanN(x.name || (r && r[1]) || "Card");
      return `<div class="sc-hit dd-row" data-label="${esc(x.label)}" data-id="${x.tcgplayer_id}">
        ${r ? img(r[0]) : `<span class="ph"></span>`}<span class="sc-hn"><b>${esc(name)}</b><small class="muted">${esc([x.set, x.number].filter(Boolean).join(" · "))}</small>
          <small class="dd-why">${esc((x.reasons || [])[0] || (x.label === "CANDIDATE" ? "Every finder check cleared" : ""))}</small>
          <span class="dd-acts">${x.tcgplayer_url ? `<a class="chip x" href="${esc(x.tcgplayer_url)}" target="_blank" rel="noopener">TCGplayer NM ↗</a>` : ""}${r ? `<span class="chip x dd-dc" role="button" tabindex="0" data-id="${r[0]}" data-g="${r[2]}" data-n="${esc(r[1])}" data-ask="${Math.round((x.max_listing_price || 0) * 100)}">Deal check</span>` : `<span class="chip muted">not in Edge's card list</span>`}</span></span>
        <span class="sc-hp"><b>${usd(x.max_listing_price)}</b><small class="muted">max listing</small><small class="muted">profit unverified</small></span></div>`;   // the finder's own profit figure rests on TCGplayer's NM price, which runs stale: only the Deal check (sold prices) shows profit
    };
    const cand = grp("CANDIDATE"), unc = grp("UNCERTAIN"), rej = grp("REJECT");
    el.innerHTML = `<div class="panel dd-head"><b>Finder results · prices from ${esc(d.data_day || "?")}</b>
        <p class="small muted" style="margin:4px 0 0">${(c.seen || 0).toLocaleString("en-US")} cards seen · ${(c.shortlist || 0).toLocaleString("en-US")} shortlisted · ${(c.screened || 0).toLocaleString("en-US")} checked · ${c.nm_under_max || 0} with a Near Mint copy under your max.</p>
        ${age != null && age >= 2 ? `<p class="small dd-stale">These are ${age} days old: most cheap listings will be gone. The finder runs only when you start it.</p>` : ""}
        <div class="btns"><button type="button" class="btn sm dd-ref">Refresh</button></div></div>
      <p class="muted small">The finder's picks are leads. Tap <b>Deal check</b>: today's sold prices and your rules ($${((S.set.buyLimit ?? 7500) / 100).toFixed(0)} limit, $${((S.set.cashReserve ?? 10000) / 100).toFixed(0)} reserve, ${money(S.set.minProfit)} and ${S.set.roi}%) decide whether it's a BUY candidate. Type the real listing price there.</p>
      <div class="sec"><div class="sec-head"><h2>Candidates</h2><span class="chip ${cand.length ? "hot" : ""}">${cand.length}</span></div>
        ${cand.length ? `<div class="sc-list">${cand.map(row).join("")}</div>` : `<div class="empty">No candidates in this run: no Near Mint copy cleared every check. The closest ones are below.</div>`}</div>
      <div class="sec"><div class="sec-head"><h2>Worth a look</h2><span class="chip">${unc.length}</span></div>
        <p class="muted small" style="margin:0 0 6px">A Near Mint copy under your max, but the evidence was weak. Not enough to call it; check it yourself.</p>
        ${unc.length ? `<div class="sc-list">${unc.map(row).join("")}</div>` : `<div class="empty">None.</div>`}</div>
      <details class="sec dd-rej"><summary><b>Rejected (${c.rejects ?? rej.length})</b> <span class="muted small">why the cheap copies didn't count</span></summary>
        ${(d.reasons_top || []).length ? `<div class="kv">${d.reasons_top.map(([k, v]) => `<div><span>${esc(k)}</span><span>${v}</span></div>`).join("")}</div>` : ""}
        <div class="sc-list">${rej.map(row).join("")}</div></details>`;
    $(".dd-ref", el).onclick = () => drawDaily(el, true);
    $$(".dd-dc", el).forEach((b) => { b.onclick = (e) => { e.stopPropagation();
      SC.pick = { id: +b.dataset.id, g: +b.dataset.g, n: b.dataset.n, q: cleanN(b.dataset.n).toLowerCase() }; SC.q = cleanN(b.dataset.n);
      SC.ask = +b.dataset.ask ? (+b.dataset.ask / 100).toFixed(2) : ""; SC.cond = "NM"; SC.auto = true; SUB.deals = "check"; route(); }; });
  }

  /* ---------- Buy list: prepare before a show, check at the table (estimates), verify live (Show check) ----------
     Prices are read once per card within a credit budget he picks; what stays on the phone is rounded (walk-away floored
     to a step, resale as a range, pace as a count band) so no sold price can be worked back from it. At the table the
     saved estimate can only say "fits your rules"; "Verify now" opens Show check, where fresh sold prices decide BUY. */
  const blPlural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
  const BLV = { open: null, ask: {}, adding: false, prep: false, budget: 500, run: null, q: "" };
  const BL_PR = ["1st Edition Holofoil", "1st Edition Normal", "1st Edition", "Unlimited Holofoil", "Unlimited", "Reverse Holofoil", "Holofoil", "Normal"];
  const printingOf = (n) => { const m = /\(([^()]*)\)\s*$/.exec(n || ""); return m && BL_PR.includes(m[1]) ? m[1] : "Normal"; };
  const blName = (n) => String(n || "").replace(/\s*\((1st Edition Holofoil|1st Edition Normal|1st Edition|Unlimited Holofoil|Unlimited|Reverse Holofoil|Holofoil|Normal)\)\s*$/, "");
  function blAdd(x) {
    if (!BLS) { toast("The buy list didn't load"); return false; }
    const k = keyOf(x.id, x.n);
    if (BLS.has(k)) { toast("Already on your buy list"); return false; }
    const ok = BLS.add({ k, id: x.id, g: x.g, n: x.n, setN: x.setN || setName(x.g), t: x.t || "c", r: x.r || "", cond: "NM" });
    toast(ok ? "Added to your buy list" : "Your buy list is full (60 cards)");
    return ok;
  }
  async function drawBuyList(el) {
    const bl = await BUYL;
    if (!bl) { el.innerHTML = `<div class="empty">The buy list didn't load. Reopen Edge.</div>`; return; }
    if (!BLS) BLS = bl.Store(window.localStorage);
    const conn = pkmnConn(), now = Date.now(), items = BLS.all();
    const lim = S.set.buyLimit ?? 7500, res = S.set.cashReserve ?? 10000;
    const withEst = items.filter((x) => x.est), oldest = withEst.length ? Math.min(...withEst.map((x) => x.est.at)) : null;
    const st = (x) => bl.ageState(x.est, now);
    const nStale = items.filter((x) => st(x) === "stale").length, nOld = items.filter((x) => st(x) === "expired").length, nNone = items.filter((x) => st(x) === "none").length;
    const ready = items.filter((x) => st(x) !== "expired" && x.est && x.est.walk && x.est.walk[x.cond]).length;
    const ageWarn = nOld ? `<p class="small bl-warn bl-old">${blPlural(nOld, "card")}: estimate older than 3 days, not used. Check prices again or verify each card live.</p>`
      : nStale ? `<p class="small bl-warn">${blPlural(nStale, "estimate")} older than a day: prices may have moved. Verify before you pay.</p>` : "";
    el.innerHTML = `<p class="muted small" style="margin:0 0 8px">Prepare before a show: add cards, check their sold prices once within a credit budget, and Edge keeps a walk-away price per condition on this phone (works with poor signal). At the table, type the seller's price. Saved numbers are <b>estimates</b>; only <b>Verify now</b> (live sold prices) can say BUY. Your rules: ${money(lim)} most per purchase, ${money(res)} kept back, ${money(S.set.minProfit)} and ${S.set.roi}% profit.</p>
      <div class="panel bl-sum" data-n="${items.length}" data-ready="${ready}">
        <div class="bl-sum-row"><b>${blPlural(items.length, "card")}</b><span class="chip ${ready ? "hot" : ""}">${ready} with a walk-away</span><span class="chip bl-age${nOld ? " bl-old" : nStale ? " bl-stale" : ""}">${oldest ? `oldest ${bl.ageTxt({ at: oldest }, now)}` : "not checked yet"}</span></div>
        ${ageWarn}${nNone && items.length ? `<p class="small muted" style="margin:4px 0 0">${blPlural(nNone, "card")} not checked yet.</p>` : ""}
        <div class="btns"><button type="button" class="btn sm bl-add-open">${BLV.adding ? "Done adding" : "Add cards"}</button><button type="button" class="btn sm primary bl-prep-open"${items.length ? "" : " disabled"}>Check prices</button></div>
      </div>
      <div id="bl-add"></div><div id="bl-prep"></div>
      <div class="sc-list bl-list">${items.length ? items.map((x) => blRow(bl, x, now)).join("") : `<div class="empty">Your buy list is empty. Add cards from your watchlist or search, or tap <b>Add to buy list</b> in Show check.</div>`}</div>`;
    $(".bl-add-open", el).onclick = () => { BLV.adding = !BLV.adding; BLV.prep = false; drawBuyList(el); };
    $(".bl-prep-open", el).onclick = () => { BLV.prep = !BLV.prep; BLV.adding = false; drawBuyList(el); };
    if (BLV.adding) drawBlAdd($("#bl-add", el), el);
    if (BLV.prep) drawBlPrep($("#bl-prep", el), el, bl);
    $$(".bl-head", el).forEach((b) => { b.onclick = () => { const k = b.closest(".bl-row").dataset.k; BLV.open = BLV.open === k ? null : k; drawBuyList(el); }; });
    const openRow = BLV.open && $(`.bl-row[data-k="${CSS.escape(BLV.open)}"]`, el);
    if (openRow) wireBlTable(bl, openRow, el);
  }
  function blRow(bl, x, now) {
    const s = bl.ageState(x.est, now), w = x.est && x.est.walk ? x.est.walk[x.cond] : null, usable = s === "fresh" || s === "stale";
    const right = !x.est ? `<b class="muted">—</b><small class="muted">not checked</small>`
      : !usable ? `<b class="muted">${w ? money(w) : "—"}</b><small class="bl-old">too old: verify</small>`
      : w ? `<b>${money(w)}</b><small class="muted">walk-away (est.)</small><small class="muted">open ${money(bl.opening(w))}</small>`
      : `<b class="muted">no buy</b><small class="muted">${esc((bl.ISSUE[x.est.issue] || "No price clears your rules.").replace(/\.$/, ""))}</small>`;
    const ev = x.est ? [x.est.grade ? `Evidence ${x.est.grade}` : null, x.est.pace != null ? `${x.est.pace} sold in 30 days` : null, bl.ageTxt(x.est, now)].filter(Boolean).join(" · ") : "Not checked yet";
    const open = BLV.open === x.k;
    return `<div class="bl-row${open ? " open" : ""}" data-k="${esc(x.k)}" data-state="${s}">
      <button type="button" class="sc-hit bl-head" aria-expanded="${open}">${img(x.id)}<span class="sc-hn"><b>${esc(blName(x.n))}</b>
        <small class="muted">${esc(x.setN || setName(x.g))}</small><small><span class="chip bl-pr">${esc(printingOf(x.n))}</span> <span class="chip bl-cond">${esc(x.cond)}</span></small>
        <small class="bl-ev ${s === "stale" ? "bl-stale" : s === "expired" ? "bl-old" : "muted"}">${esc(ev)}</small></span>
        <span class="sc-hp">${right}</span></button>
      ${open ? `<div class="bl-table">${blTableHTML(bl, x, now)}</div>` : ""}</div>`;
  }
  function blTableHTML(bl, x, now) {
    const ask = BLV.ask[x.k] ?? "", s = bl.ageState(x.est, now), e = x.est;
    const w = e && e.walk ? e.walk[x.cond] : null, usable = s === "fresh" || s === "stale";
    return `<div class="bl-neg${usable && w ? "" : " muted"}"><span class="lab">Negotiation suggestions, not valuations</span>
        ${usable && w ? `<div class="bl-neg-row"><span>Opening offer</span><b>${money(bl.opening(w))}</b></div><div class="bl-neg-row"><span>Walk away above</span><b>${money(w)}</b></div>` : `<p class="small" style="margin:2px 0">No walk-away for ${esc(x.cond)} on the saved estimate.</p>`}
        ${e && e.tcg ? `<div class="bl-neg-row muted"><span>TCGplayer market (what sellers often quote)</span><span>${money(e.tcg)}</span></div>` : ""}
        ${usable && e && e.resale ? `<div class="bl-neg-row muted"><span>Resells for about (NM, range)</span><span>${money(e.resale[0])}–${money(e.resale[1])}</span></div>` : ""}</div>
      <div class="bl-form">
        <label class="f">Seller's price $<input class="field bl-ask" inputmode="decimal" enterkeyhint="done" placeholder="0.00" value="${esc(ask)}"></label>
        <label class="f">Condition<select class="select bl-cnd">${["NM", "LP", "MP", "HP", "DMG"].map((c) => `<option${c === x.cond ? " selected" : ""}>${c}</option>`).join("")}</select></label>
        <label class="f">Cash on hand $<input class="field bl-cash" inputmode="decimal" placeholder="0.00" value="${CASH_NOW != null ? (CASH_NOW / 100).toFixed(2) : ""}"><small class="muted">this visit only, not saved</small></label>
      </div>
      <div class="bl-out"></div>
      <div class="btns"><button type="button" class="btn sm primary bl-verify">Verify now</button><button type="button" class="btn sm bl-remove">Remove</button></div>
      <p class="small muted bl-vnote"></p>`;
  }
  function wireBlTable(bl, row, el) {
    const k = row.dataset.k, x = BLS.get(k); if (!x) return;
    const cfg = dealCfg(x.est && x.est.tcg), askI = $(".bl-ask", row), cashI = $(".bl-cash", row), condS = $(".bl-cnd", row), out = $(".bl-out", row);
    const cents = (v) => { const n = parseFloat(String(v || "").replace(/[$,\s]/g, "")); return isFinite(n) && n > 0 ? Math.round(n * 100) : 0; };
    const draw = async () => {
      const deal = await DEAL; if (!deal) { out.innerHTML = `<p class="small muted">The deal engine didn't load.</p>`; return; }
      const ask = cents(askI.value), r = bl.atTable(deal, x.est, x.cond, ask, CASH_NOW, cfg, x.t || "c");
      const line = (ok, txt) => `<li class="${ok === true ? "ok" : ok === false ? "no" : "info"}"><i aria-hidden="true">${ok === true ? "✓" : ok === false ? "✕" : "•"}</i><span>${txt}</span></li>`;
      const head = { fits: "Fits your rules (estimate)", over: "Over your walk-away", limit: "Over your limit", reserve: "Breaks your reserve", "need-cash": "Within your walk-away", "need-ask": "Saved estimate", "no-walk": "No buy on the saved estimate", expired: "Estimate too old", none: "Not checked yet" }[r.result] || "Saved estimate";
      const lines = [];
      if (r.walk) lines.push(line(ask > 0 ? ask <= r.walk : null, `Walk-away ${money(r.walk)} for ${esc(x.cond)}: the most that still clears ${money(S.set.minProfit)} and ${S.set.roi}% at the sold prices checked (rounded down)`));
      if (r.cost != null) {
        lines.push(line(r.limitOk, `All-in ${money(r.cost)} ${r.limitOk ? "within" : "over"} your ${money(cfg.budget.limit)} limit`));
        lines.push(line(r.reserveOk, r.reserveOk == null ? `Cash on hand not entered: enter it to check your ${money(cfg.budget.reserve)} reserve` : `${r.reserveOk ? "Leaves" : "Would leave"} ${money(CASH_NOW - r.cost)} cash (reserve ${money(cfg.budget.reserve)})`));
        if (r.profit) lines.push(line(null, `Estimated net profit ${signed(r.profit[0])} to ${signed(r.profit[1])} (${pct(r.roi[0], 0)} to ${pct(r.roi[1], 0)}) from the resale range, after fees and shipping`));
      }
      out.dataset.result = r.result; out.dataset.state = r.state;
      out.innerHTML = `<div class="bl-call ${r.result === "fits" ? "fits" : ["over", "limit", "reserve", "no-walk", "expired"].includes(r.result) ? "no" : ""}"><span class="bl-badge">ESTIMATE · ${esc(bl.ageTxt(x.est))}${r.state === "stale" ? " · STALE" : ""} · not a verified BUY</span><b>${esc(head)}</b><p class="small" style="margin:2px 0 0">${esc(r.text)}</p></div>${lines.length ? `<ul class="dl-gates">${lines.join("")}</ul>` : ""}`;
      BLV.ask[k] = askI.value;
    };
    askI.oninput = draw; askI.onchange = draw;
    cashI.oninput = () => { const c = cents(cashI.value); CASH_NOW = cashI.value.trim() === "" ? null : c; draw(); };
    condS.onchange = () => { BLS.setCond(k, condS.value); BLV.ask[k] = askI.value; drawBuyList(el); };
    $(".bl-remove", row).onclick = () => { BLS.remove(k); BLV.open = null; toast("Removed from your buy list"); drawBuyList(el); };
    const vb = $(".bl-verify", row), vn = $(".bl-vnote", row), conn = pkmnConn();
    const online = navigator.onLine !== false;
    if (!conn || !online) { vb.disabled = true; vn.textContent = !conn ? "Verify needs sold prices: pair this phone in Mine → Settings." : "No connection: verify when you have signal. Until then this is an estimate only."; }
    else vn.textContent = `Reads live sold prices for this exact card (about ${bl.CREDITS_PER_CARD + 40} credits at most) and opens Show check with your price.`;
    vb.onclick = () => {
      const ask = cents(askI.value);
      SC.pick = { id: x.id, g: x.g, n: x.n, q: cleanN(x.n).toLowerCase() }; SC.q = cleanN(x.n);
      SC.ask = ask ? (ask / 100).toFixed(2) : ""; SC.cond = condS.value; SC.auto = true; SUB.deals = "check";
      if (location.hash === "#deals") route(); else location.hash = "deals";
    };
    draw();
    if (!askI.value) askI.focus({ preventScroll: true });
  }
  async function drawBlAdd(box, el) {
    const watch = S.watch.filter((w) => (w.t || "c") === "c" || w.t === "s");
    box.innerHTML = `<div class="panel bl-addp"><b>Add cards</b>
      <div class="searchbox" style="margin-top:6px"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></svg>
        <input id="bl-q" class="field" type="search" placeholder="Card name and number" autocomplete="off" aria-label="Find a card to add" value="${esc(BLV.q)}"></div>
      <div id="bl-res"></div>
      ${watch.length ? `<p class="small" style="margin:8px 0 4px"><b>From your watchlist</b></p><div class="sc-list">${watch.slice(0, 40).map((w) => {
        const on = BLS && BLS.has(w.k || keyOf(w.id, w.n));
        return `<button type="button" class="sc-hit bl-w" data-id="${w.id}" data-g="${w.g}" data-n="${esc(w.n)}" data-t="${w.t || "c"}"${on ? " disabled" : ""}><span class="sc-hn"><b>${esc(blName(w.n))}</b><small class="muted">${esc(setName(w.g))} · ${esc(printingOf(w.n))}</small></span><span class="sc-hp"><b>${on ? "✓ on list" : "+ Add"}</b></span></button>`; }).join("")}</div>` : `<p class="small muted" style="margin:8px 0 0">Your watchlist is empty: search above instead.</p>`}</div>`;
    $$(".bl-w", box).forEach((b) => { b.onclick = () => { if (blAdd({ id: +b.dataset.id, g: +b.dataset.g, n: b.dataset.n, t: b.dataset.t })) drawBuyList(el); }; });
    const q = $("#bl-q", box), resBox = $("#bl-res", box);
    const results = () => {
      BLV.q = q.value; const t = q.value.trim().toLowerCase();
      if (!t || !ROWS) { resBox.innerHTML = t && !ROWS ? `<p class="small muted">The card list needs a connection the first time.</p>` : ""; return; }
      const hits = findCards(t, (r) => gameOk(gameOfSet(r[2])));
      if (!hits.length) { resBox.innerHTML = `<p class="small muted">Nothing found. Try the card number or fewer words.</p>`; return; }
      pagedList(resBox, hits, 10, (r) => { const on = BLS && BLS.has(keyOf(r[0], r[1]));
        return `<button type="button" class="sc-hit bl-s" data-id="${r[0]}" data-g="${r[2]}" data-n="${esc(r[1])}" data-t="${r[3]}"${on ? " disabled" : ""}>${img(r[0])}<span class="sc-hn"><b>${esc(blName(r[1]))}</b><small class="muted">${esc(setName(r[2]))} · ${esc(printingOf(r[1]))}</small></span><span class="sc-hp"><b>${on ? "✓ on list" : "+ Add"}</b><small class="muted">${money(r[4])}</small></span></button>`; },
        (nodes) => nodes.forEach((b) => { b.onclick = () => { if (blAdd({ id: +b.dataset.id, g: +b.dataset.g, n: b.dataset.n, t: b.dataset.t })) { BLV.q = q.value; drawBuyList(el); } }; }));
    };
    let tm; q.addEventListener("input", () => { clearTimeout(tm); tm = setTimeout(results, 140); });
    loadIndex().then(results).catch(() => results());
    if (!BLV.q) q.focus({ preventScroll: true });
  }
  function drawBlPrep(box, el, bl) {
    const conn = pkmnConn(), P = bl.plan(BLS.all(), BLV.budget), run = BLV.run;
    if (!conn) { box.innerHTML = `<div class="panel sc-off"><b>Sold prices aren't set up on this phone</b><p class="small muted" style="margin:4px 0 8px">Pair it once in Mine → Settings to check prices.</p><div class="btns"><button type="button" class="btn sm primary bl-pair">Go to Settings</button></div></div>`;
      $(".bl-pair", box).onclick = () => { SUB.mine = "set"; location.hash = "mine"; }; return; }
    const busy = run && !run.over;
    box.innerHTML = `<div class="panel bl-prepp"><b>Check sold prices</b>
      <p class="small" style="margin:4px 0 6px">Reads recent eBay sold prices (raw copies only) for cards not checked in the last day, oldest first. About ${bl.CREDITS_PER_CARD} credits a card at most, usually less. Your plan has 20,000 credits a day.</p>
      <label class="f">Credit budget<select class="select bl-budget"${busy ? " disabled" : ""}>${[250, 500, 1000, 2000, 5000].map((c) => `<option value="${c}"${c === BLV.budget ? " selected" : ""}>${c.toLocaleString("en-US")} credits</option>`).join("")}</select></label>
      <p class="small bl-plan" data-need="${P.need.length}" data-take="${P.take.length}">${P.need.length ? `${blPlural(P.need.length, "card")} need a check; this budget covers up to ${P.take.length}${P.take.length < P.need.length ? ` (the rest stay unchecked)` : ""}.` : "Every card was checked in the last day: nothing to spend."}</p>
      ${run ? `<p class="small bl-run" data-done="${run.done}" data-credits="${run.credits}">${run.over ? "Done" : "Checking"}: ${run.done} of ${run.total} cards · ${run.credits.toLocaleString("en-US")} credits${run.msg ? ` · ${esc(run.msg)}` : ""}</p>` : ""}
      <div class="btns">${busy ? `<button type="button" class="btn sm bl-stop">Stop</button>` : `<button type="button" class="btn sm primary bl-go"${P.take.length ? "" : " disabled"}>Check ${blPlural(P.take.length, "card")} · up to ${(P.take.length * bl.CREDITS_PER_CARD).toLocaleString("en-US")} credits</button>`}</div></div>`;
    const bsel = $(".bl-budget", box); if (bsel) bsel.onchange = () => { BLV.budget = +bsel.value; BLV.run = null; drawBuyList(el); };
    const go = $(".bl-go", box); if (go) go.onclick = () => blRun(el, bl);
    const stop = $(".bl-stop", box); if (stop) stop.onclick = () => { if (BLV.run) BLV.run.stop = true; };
  }
  async function blRun(el, bl) {
    const [deal, pkmn] = await Promise.all([DEAL, PKMN]), conn = pkmnConn();
    if (!deal || !pkmn || !conn) { toast("Sold prices aren't available"); return; }
    const budget = BLV.budget, P = bl.plan(BLS.all(), budget);
    const run = BLV.run = { done: 0, total: P.take.length, credits: 0, stop: false, over: false, msg: "" };
    const redraw = () => { if (SUB.deals === "list" && TAB === "deals" && document.body.contains(el)) drawBuyList(el); };
    redraw();
    for (const x of P.take) {
      if (run.stop) { run.msg = "stopped"; break; }
      if (run.credits + bl.CREDITS_PER_CARD > budget) { run.msg = "budget reached"; break; }
      let d = null; try { d = await detail(x.id, x.g, x.n); } catch { d = null; }
      if (!d || !d.it) { run.msg = "card list unavailable: check your connection"; break; }
      const { it, set } = d;
      const item = { id: it.id, n: it.n, name: it.n, t: it.t, r: it.r, setN: set.n, tcg: it.p, tcgDay: dayNum(set.dates?.[set.dates.length - 1]) };
      const res = await pkmn.lookup(item, { ...conn, rawOnly: true });
      run.credits += res.meta ? res.meta.credits || 0 : 0;
      if (!res.ok && (res.reason === "network" || res.reason === "denied" || res.reason === "error")) { run.msg = SOLD_WHY[res.reason] || "sold prices unavailable"; break; }
      BLS.setEst(x.k, res.ok ? bl.derive(deal, item, res.data, dealCfg(it.p)) : { at: Date.now(), tcg: it.p || null, grade: null, pace: null, resale: null, walk: {}, issue: "not-found" });
      run.done++; redraw();
    }
    run.over = true; redraw();
    toast(`Checked ${blPlural(run.done, "card")} · ${run.credits.toLocaleString("en-US")} credits`);
  }

  /* ---------- Deals ---------- */
  let D_BUDGET = 0, D_MV = { win: "7", min: null, dir: "up" };
  async function viewDeals(v) {
    v.innerHTML = `<div id="d-seg"></div><div id="d-game"></div><div class="filters"><label class="f" style="flex:1">Budget<select class="select" id="d-budget">
        ${[[0, "Any price"], [2500, "Under $25"], [5000, "Under $50"], [10000, "Under $100"], [25000, "Under $250"], [50000, "Under $500"], [100000, "Under $1,000"]].map(([c, l]) => `<option value="${c}"${c === D_BUDGET ? " selected" : ""}>${l}</option>`).join("")}</select></label></div>
      <p class="muted small" id="d-note"></p><div id="d-list"><p class="muted">Loading…</p></div>`;
    // the nightly lists load only for the list views: Show check, Buy list and Daily deals never wait on them (poor signal)
    const listsP = Promise.all([getJSON("scout.json").catch(() => null), getJSON("buyer.json").catch(() => null)]);
    const draw = async () => {
      const sub = SUB.deals, ok = (r) => gameOk(r.k) && (!D_BUDGET || (r.lo || r.p) <= D_BUDGET);
      const note = $("#d-note"), out = $("#d-list");
      const listy = !["check", "list", "daily"].includes(sub); $("#d-game").hidden = !listy; $(".filters", v).hidden = !listy;
      if (sub === "check") { note.textContent = ""; await drawShowCheck(out); return; }
      if (sub === "list") { note.textContent = ""; await drawBuyList(out); return; }
      if (sub === "daily") { note.textContent = ""; await drawDaily(out); return; }
      out.innerHTML = `<p class="muted">Loading…</p>`;
      const [scout, buyer] = await listsP;
      if (["flip", "ride", "dip"].includes(sub)) {
        if (!scout) { out.innerHTML = `<div class="empty">The deal list builds with the nightly update.</div>`; return; }
        note.textContent = { flip: "Listed far enough under market to resell for your target profit after fees and shipping.", ride: "Steady climbs: rising most days this week.", dip: "Off their usual price and no longer falling." }[sub]
          + (scout.history_days < 30 ? ` Based on ${scout.history_days} days of price history so far.` : "");
        let rows = scout.picks.filter((r) => r.plan === sub && ok(r));
        if (sub === "flip") rows = rows.map((r) => ({ r, f: flip(r.p, r.lo, r.t) })).filter((x) => x.f).sort((a, b) => b.f.pr - a.f.pr).map((x) => x.r);
        out.innerHTML = listOrEmpty(rows.slice(0, 80).map((r) => {
          const f = flip(r.p, r.lo, r.t);
          const right = sub === "flip" ? `<b class="${cls(f?.pr)}">${f ? signed(f.pr) : "—"}</b><small class="muted">buy ${money(r.lo)} · sell ${money(r.p)}</small>`
            : `<b>${money(r.p)}</b><small class="${cls(r.w7)}">${pct(r.w7, 0)} 7D</small>`;
          const extra = `<span class="why">${esc((r.why || [])[0] || "")}${r.risk?.length ? `<span class="risk">${esc(r.risk[0])}</span>` : ""}${sub !== "flip" && r.max ? ` <span class="chip">max buy ${money(r.max)}</span>` : ""}</span>`;
          return rowHTML(r, right, extra);
        }), "Nothing matches. Try a bigger budget or another game.");
      } else if (sub === "under") {
        note.textContent = "Cheapest listing far below the market price. Check condition and the seller before buying.";
        out.innerHTML = listOrEmpty((buyer?.under || []).filter(ok).slice(0, 80).map((r) => rowHTML(r, `<b class="up">${money(r.lo)}</b><small class="muted">${r.off.toFixed(0)}% under ${money(r.p)}</small>`)), "Nothing listed far under market right now.");
      } else if (sub === "fall") {
        note.textContent = "Falling fast. Hold off buying these, and think about selling if you own them.";
        out.innerHTML = listOrEmpty((scout?.avoid || []).filter(ok).slice(0, 80).map((r) => rowHTML(r, `<b>${money(r.p)}</b><small class="down">${pct(r.w7, 0)} 7D</small>`, `<span class="why">${esc(r.why || "")}</span>`)), "Nothing in a steep fall right now.");
      } else if (sub === "movers") {
        note.textContent = "Biggest price changes over the window you pick, from our own nightly history.";
        await drawMovers(out);
      } else if (sub === "store") {
        note.textContent = "Your Drive Your Style prices compared with today's market.";
        const fix = (buyer?.fix || []).filter(ok), rising = (buyer?.rising || []).filter(ok);
        out.innerHTML = `<div class="sec"><h3>Far from market</h3>${listOrEmpty(fix.map((x) => rowHTML(x, `<b>${money(x.dys)}</b><small class="${x.gap < 0 ? "down" : "up"}">${pct(x.gap, 0)} vs ${money(x.p)}</small>`)), "Every store price is close to market.")}</div>
          <div class="sec"><h3>Rising this week</h3>${listOrEmpty(rising.map((x) => rowHTML(x, `<b>${money(x.p)}</b><small class="up">${pct(x.ch, 0)} · yours ${money(x.dys)}</small>`)), "None of your stock is rising fast.")}</div>`;
      }
    };
    seg($("#d-seg"), [["check", "Show check"], ["list", "Buy list"], ["daily", "Daily deals"], ["flip", "Flips"], ["ride", "Momentum"], ["dip", "Dips"], ["under", "Under market"], ["movers", "Movers"], ["fall", "Falling"], ["store", "My store"]], SUB.deals, (k) => { SUB.deals = k; draw(); });
    gamePick($("#d-game"), () => draw());
    $("#d-budget").onchange = (e) => { D_BUDGET = +e.target.value; draw(); };
    draw();
  }
  async function drawMovers(out) {
    const games = (GAMES[S.set.game] || GAMES.pokemon)[1] || ["all"];
    const files = await Promise.all(games.flatMap((g) => ["cards", "sealed"].map((t) => getJSON(`movers/${t}-${g}.json`).then((d) => ({ t, d })).catch(() => null)))).then((a) => a.filter(Boolean));
    const has = (w) => files.some((f) => Object.values(f.d.windows?.[w] || {}).some((m) => (m.up || []).length || (m.down || []).length));
    const wins = [...new Set(files.flatMap((f) => Object.keys(f.d.windows || {})))].filter(has).sort((a, b) => (a === "all") - (b === "all") || +a - +b);
    if (!wins.includes(D_MV.win)) D_MV.win = wins[0] || "7";
    const mins = [...new Set(files.flatMap((f) => Object.keys(f.d.windows?.[D_MV.win] || {})))].sort((a, b) => +a - +b);
    if (!mins.includes(D_MV.min)) D_MV.min = mins.includes("20") ? "20" : mins[0];
    out.innerHTML = `<div id="mv-win"></div><div id="mv-min"></div><div id="mv-dir"></div><div id="mv-list"></div>`;
    const list = () => {
      const rows = files.flatMap((f) => (f.d.windows?.[D_MV.win]?.[D_MV.min]?.[D_MV.dir] || []).map((r) => ({ id: r[0], n: r[1], g: r[2], p: r[3], was: r[4], ch: r[5], t: f.t === "sealed" ? "s" : "c" })))
        .filter((r) => !D_BUDGET || r.p <= D_BUDGET).sort((a, b) => D_MV.dir === "up" ? b.ch - a.ch : a.ch - b.ch).slice(0, 80);
      $("#mv-list").innerHTML = listOrEmpty(rows.map((r) => rowHTML(r, `<b>${money(r.p)}</b><small class="${cls(r.ch)}">${pct(r.ch, 0)} from ${money(r.was)}</small>`)), "No movers for this window yet. Longer windows fill in as our history grows.");
    };
    seg($("#mv-win"), wins.map((w) => [w, w === "all" ? "All time" : `${w} days`]), D_MV.win, (w) => { D_MV.win = w; drawMovers(out); });
    seg($("#mv-min"), mins.map((m) => [m, `$${m}+`]), D_MV.min, (m) => { D_MV.min = m; list(); });
    seg($("#mv-dir"), [["up", "Rising"], ["down", "Falling"]], D_MV.dir, (d) => { D_MV.dir = d; list(); });
    list();
  }

  /* ---------- Tools ---------- */
  const FLIP = { buy: "", sell: "", t: "c", plat: null };
  const GRADE = { raw: "", p10: "", p9: "", p8: "", cond: "nm", tier: "0", name: "", no: "", plat: null };
  const ODDS = { fresh: [55, 35, "Pack fresh"], nm: [40, 45, "Near mint"], lp: [5, 35, "Light play"] };
  async function viewTools(v) {
    v.innerHTML = `<div id="t-seg"></div><div id="t-body"></div>`;
    const draw = () => { const el = fresh($("#t-body")); ({ flip: toolFlip, lot: toolLot, trade: toolTrade, grade: toolGrade, fees: toolFees, cert: toolCert }[SUB.tools] || toolFlip)(el); };
    seg($("#t-seg"), [["flip", "Flip"], ["trade", "Trade"], ["lot", "Buy a lot"], ["fees", "Fees"], ["cert", "PSA cert"]], SUB.tools, (k) => { SUB.tools = k; draw(); });
    draw();
  }
  const platSelect = (id, val) => `<select class="select" id="${id}">${Object.entries(FEES.sell).map(([k, p]) => `<option value="${k}"${k === val ? " selected" : ""}>${esc(p.label)}</option>`).join("")}</select>`;
  function toolFlip(el) {
    FLIP.plat ||= S.set.platform;
    el.innerHTML = `<section class="sec panel"><h2>Flip calculator</h2>
      <div class="form"><label class="f">You pay $<input class="field" id="fl-b" type="number" inputmode="decimal" min="0" step="0.01" value="${esc(FLIP.buy)}" placeholder="0.00"></label>
        <label class="f">You sell for $<input class="field" id="fl-s" type="number" inputmode="decimal" min="0" step="0.01" value="${esc(FLIP.sell)}" placeholder="0.00"></label>
        <label class="f">It's a<select class="select" id="fl-t"><option value="c"${FLIP.t === "c" ? " selected" : ""}>Card</option><option value="s"${FLIP.t === "s" ? " selected" : ""}>Sealed product</option></select></label>
        <label class="f">Selling on${platSelect("fl-p", FLIP.plat)}</label></div>
      <div id="fl-out"></div></section>`;
    const calc = () => {
      FLIP.buy = $("#fl-b").value; FLIP.sell = $("#fl-s").value; FLIP.t = $("#fl-t").value; FLIP.plat = $("#fl-p").value;
      const b = cents(FLIP.buy), s = cents(FLIP.sell), t = FLIP.t, k = FLIP.plat;
      if (!s) { $("#fl-out").innerHTML = `<p class="muted small">Enter what you'd sell it for to see fees, shipping and profit.</p>`; return; }
      const fee = s - netSale(plat(k), s), so = shipOut(s, t, k), si = b ? shipIn(t) : 0, pr = s - fee - so - b - si, roi = b ? pr / (b + si) * 100 : null;
      const mb = Math.max(0, Math.floor((s - fee - so) / (1 + S.set.roi / 100) - shipIn(t)));
      $("#fl-out").innerHTML = `<div class="verdict ${pr > 0 && (roi ?? 99) >= S.set.roi ? "good" : pr > 0 ? "meh" : "bad"}"><span class="lab">Profit</span><b>${signed(pr)}</b><span class="small muted">${roi != null ? `${roi.toFixed(0)}% return on ${money(b + si)}` : "enter what you pay"}</span></div>
        <div class="kv"><div><span>Sale price</span><span>${money(s)}</span></div><div><span>${esc(plat(k).label)} fees</span><span>−${money(fee)}</span></div>
        <div><span>Shipping to the buyer</span><span>−${money(so)}</span></div>${b ? `<div><span>What you pay + shipping in</span><span>−${money(b + si)}</span></div>` : ""}
        <div><span>Max buy for ${S.set.roi}% profit</span><span>${money(mb)}</span></div></div>`;
    };
    $$("input,select", el).forEach((i) => i.addEventListener("input", calc)); calc();
  }
  const lineItems = (list, which) => list.length ? list.map((x, i) => {
    const m = marketOf(x), val = (m || 0) * condX(x.cond, x.t) * x.qty;
    return `<div class="line-item">${img(x.id)}<div style="min-width:0"><div class="nm">${esc(cleanN(x.n))}</div>
      <div class="ctl"><input type="number" inputmode="numeric" min="1" step="1" value="${x.qty}" aria-label="Quantity" data-q="${which}:${i}">${x.t === "c" ? `<select aria-label="Condition" data-c="${which}:${i}">${COND.map(([c]) => `<option${x.cond === c ? " selected" : ""}>${c}</option>`).join("")}</select>` : ""}</div></div>
      <div style="text-align:right"><b class="tn">${money(Math.round(val))}</b><br><button type="button" class="x" aria-label="Remove" data-x="${which}:${i}">✕</button></div></div>`;
  }).join("") : `<p class="muted small">No cards yet.</p>`;
  const listTotal = (list) => list.reduce((a, x) => a + (marketOf(x) || 0) * condX(x.cond, x.t) * x.qty, 0);
  const listNet = (list) => list.reduce((a, x) => { const each = Math.round((marketOf(x) || 0) * condX(x.cond, x.t)); return a + net(each, x.t) * x.qty; }, 0);
  function bindLines(el, get, redraw) {
    el.onchange = (e) => {
      const q = e.target.dataset.q, c = e.target.dataset.c;
      if (q) { const [w, i] = q.split(":"); get(w)[i].qty = Math.max(1, parseInt(e.target.value, 10) || 1); save(); redraw(); }
      if (c) { const [w, i] = c.split(":"); get(w)[i].cond = e.target.value; save(); redraw(); }
    };
    el.onclick = (e) => { const x = e.target.closest("[data-x]"); if (!x) return; const [w, i] = x.dataset.x.split(":"); get(w).splice(+i, 1); save(); redraw(); };
  }
  async function toolTrade(el) {
    await loadIndex();
    const draw = () => {
      const give = listTotal(S.trade.give), get = listTotal(S.trade.get), diff = get - give;
      const credit = get * S.set.trade / 100;
      const body = `<div class="sides"><div class="side panel"><div class="sec-head"><h3>I give</h3><button type="button" class="more" data-pick="give">+ Add cards</button></div>${lineItems(S.trade.give, "give")}<div class="total"><span>Market</span><span>${money(Math.round(give))}</span></div></div>
        <div class="side panel"><div class="sec-head"><h3>I get</h3><button type="button" class="more" data-pick="get">+ Add cards</button></div>${lineItems(S.trade.get, "get")}<div class="total"><span>Market</span><span>${money(Math.round(get))}</span></div></div></div>
        ${S.trade.give.length || S.trade.get.length ? `<div class="verdict ${Math.abs(diff) <= Math.max(give, get) * 0.05 ? "good" : diff > 0 ? "good" : "bad"}"><span class="lab">At market value</span>
          <b>${Math.abs(diff) <= Math.max(give, get) * 0.05 ? "Fair trade" : diff > 0 ? `You come out ${money(Math.round(diff))} ahead` : `You're down ${money(Math.round(-diff))}`}</b>
          <span class="small muted">${diff < 0 ? `Ask for ${money(Math.round(-diff))} cash to even it out.` : diff > 0 ? `They'd need ${money(Math.round(diff))} cash from you to make it even.` : "Both sides match."}</span></div>
          <div class="kv"><div><span>Their cards as store credit (${S.set.trade}%)</span><span>${money(Math.round(credit))}</span></div>
          <div><span>Your side if sold instead</span><span>${money(Math.round(listNet(S.trade.give)))}</span></div><div><span>Their side if you resold it</span><span>${money(Math.round(listNet(S.trade.get)))}</span></div></div>
          <button type="button" class="btn ghost danger" id="tr-clear">Clear trade</button>` : `<div class="empty"><b>Build a trade</b>Add the cards on each side and see who comes out ahead, what to ask in cash, and what each side nets if sold.</div>`}`;
      el.innerHTML = body;
      $$("[data-pick]", el).forEach((b) => b.onclick = () => { PICK = { list: b.dataset.pick, label: b.dataset.pick === "give" ? "I give" : "I get", back: "tools" }; location.hash = "search"; });
      const c = $("#tr-clear", el); if (c) c.onclick = () => { S.trade = { give: [], get: [] }; save(); draw(); };
    };
    bindLines(el, (w) => S.trade[w], draw); draw();
  }
  async function toolLot(el) {
    await loadIndex();
    const draw = () => {
      const mk = listTotal(S.lot) + (S.lotExtra || 0), offer = Math.round(mk * S.set.cash / 100);
      const resale = listNet(S.lot) + netSale(plat(), S.lotExtra || 0), pr = resale - offer;
      el.innerHTML = `<section class="sec panel"><div class="sec-head"><h2>Buy a collection</h2><button type="button" class="more" data-pick="lot">+ Add cards</button></div>
        ${lineItems(S.lot, "lot")}
        <label class="f">Other items, total market value $<input class="field" id="lot-x" type="number" inputmode="decimal" min="0" step="1" value="${dollars(S.lotExtra) || ""}" placeholder="bulk, extras"></label>
        <label class="f">Cash offer: <b id="lot-pv">${S.set.cash}%</b> of market<input type="range" id="lot-p" min="30" max="95" step="5" value="${S.set.cash}"></label>
        <div class="verdict ${pr > 0 ? "good" : "bad"}"><span class="lab">Offer</span><b>${money(offer, true)}</b><span class="small muted">for ${money(Math.round(mk), true)} of market value</span></div>
        <div class="kv"><div><span>If you resell it all on ${esc(plat().label)}</span><span>${money(Math.round(resale), true)}</span></div>
          <div><span>Profit at this offer</span><span class="${cls(pr)}">${signed(Math.round(pr))}</span></div>
          <div><span>Return</span><span>${offer ? pct(pr / offer * 100, 0) : "—"}</span></div>
          <div><span>Store credit offer (${S.set.trade}%)</span><span>${money(Math.round(mk * S.set.trade / 100), true)}</span></div></div>
        ${S.lot.length || S.lotExtra ? `<button type="button" class="btn ghost danger" id="lot-clear">Clear lot</button>` : ""}</section>`;
      $("[data-pick]", el).onclick = () => { PICK = { list: "lot", label: "the lot", back: "tools" }; location.hash = "search"; };
      $("#lot-x").onchange = (e) => { S.lotExtra = cents(e.target.value); save(); draw(); };
      $("#lot-p").oninput = (e) => { S.set.cash = +e.target.value; save(); draw(); };
      const c = $("#lot-clear"); if (c) c.onclick = () => { S.lot = []; S.lotExtra = 0; save(); draw(); };
    };
    bindLines(el, () => S.lot, draw); draw();
  }
  function toolGrade(el) {
    GRADE.plat ||= S.set.platform;
    const psa = FEES.graders.PSA;
    const f = (k, l) => `<label class="f">${l}<input class="field" data-g="${k}" type="number" inputmode="decimal" min="0" step="0.01" value="${esc(GRADE[k])}"></label>`;
    el.innerHTML = `<section class="sec panel"><h2>Grade it?</h2>${GRADE.name ? `<p class="muted small" style="margin:0">${esc(GRADE.name)}</p>` : ""}
      <div class="form">${f("raw", "Raw value $")}${f("p10", "PSA 10 sells for $")}${f("p9", "PSA 9 sells for $")}${f("p8", "PSA 8 or lower $")}
        <label class="f full">Condition<select class="select" data-g="cond">${Object.entries(ODDS).map(([k, o]) => `<option value="${k}"${k === GRADE.cond ? " selected" : ""}>${o[2]} (${o[0]}% 10s, ${o[1]}% 9s)</option>`).join("")}</select></label>
        <label class="f full">PSA service<select class="select" data-g="tier">${psa.tiers.map((t, i) => `<option value="${i}"${String(GRADE.tier) === String(i) ? " selected" : ""}>${esc(t[0])} · ${money(t[1])}${t[2] ? ` · up to ${money(t[2], true)}` : ""}</option>`).join("")}</select></label>
        <label class="f full">Sell the slab on${platSelect("gr-p", GRADE.plat)}</label></div>
      <div class="links">${GRADE.name ? `<a class="btn sm" href="${buyUrl(GRADE.name, GRADE.no, { p: cents(GRADE.raw) })}" target="_blank" rel="noopener">Buy raw on eBay ↗</a><a class="btn sm" href="${soldUrl(GRADE.name, GRADE.no + " PSA 10")}" target="_blank" rel="noopener">PSA 10 sold ↗</a><a class="btn sm" href="${soldUrl(GRADE.name, GRADE.no + " PSA 9")}" target="_blank" rel="noopener">PSA 9 sold ↗</a>` : ""}<a class="btn sm" href="${BASE}centering.html" target="_blank" rel="noopener">Check centering ↗</a></div>
      <div id="gr-out"></div></section>`;
    const calc = () => {
      $$("[data-g]", el).forEach((i) => { GRADE[i.dataset.g] = i.value; }); GRADE.plat = $("#gr-p").value;
      const raw = cents(GRADE.raw), p10 = cents(GRADE.p10), p9 = cents(GRADE.p9) || raw, p8 = GRADE.p8 === "" ? Math.round(raw * 0.7) : cents(GRADE.p8);
      if (!raw || !p10) { $("#gr-out").innerHTML = `<p class="muted small">Enter the raw value and what a PSA 10 sells for (use the sold links) to get a verdict.</p>`; return; }
      const [a, b] = ODDS[GRADE.cond], o10 = a / 100, o9 = b / 100, o8 = Math.max(0, 1 - o10 - o9), ti = +GRADE.tier || 0, pl = plat(GRADE.plat);
      const fee = (v) => feeAt(psa, ti, v), grading = o10 * fee(p10) + o9 * fee(p9) + o8 * fee(p8), cost = raw + grading + S.set.gradeShip;
      const value = o10 * netSale(pl, p10) + o9 * netSale(pl, p9) + o8 * netSale(pl, p8), pr = value - cost, rawNet = netSale(pl, raw);
      const nine = netSale(pl, p9) - raw - fee(p9) - S.set.gradeShip;
      let k, t, w;
      if (pr > raw * 0.15 && nine >= 0) { k = "good"; t = "Safe grade"; w = "Worth it even if it comes back a 9."; }
      else if (pr > raw * 0.15) { k = "good"; t = "Good odds"; w = "Pays off on average, but a 9 loses money."; }
      else if (pr > 0) { k = "meh"; t = "Risky"; w = "Small expected gain. Only a 10 really pays."; }
      else { k = "bad"; t = "Skip it"; w = "Fees and grade risk eat the premium. Sell or keep it raw."; }
      const up = psa.upcharge && tierFor(psa, p10) > ti ? psa.tiers[tierFor(psa, p10)] : null;
      $("#gr-out").innerHTML = `<div class="verdict ${k}"><span class="lab">Verdict</span><b>${t}</b><span class="small muted">${w}</span></div>
        <div class="kv"><div><span>Expected profit</span><span class="${cls(pr)}">${signed(Math.round(pr))}</span></div>
          <div><span>If it's a 10</span><span class="up">${signed(Math.round(netSale(pl, p10) - raw - fee(p10) - S.set.gradeShip))}</span></div>
          <div><span>If it's a 9</span><span class="${cls(nine)}">${signed(Math.round(nine))}</span></div>
          <div><span>Grading, average with upcharges</span><span>${money(Math.round(grading))}</span></div>
          <div><span>Shipping both ways</span><span>${money(S.set.gradeShip)}</span></div>
          <div><span>Sell it raw instead</span><span>${money(Math.round(rawNet))}</span></div></div>
        ${up ? `<p class="muted small" style="margin:6px 0 0">A 10 at this price is worth more than ${esc(psa.tiers[ti][0])} covers, so PSA upcharges it to ${esc(up[0])} (${money(up[1])}). That's counted.</p>` : ""}`;
    };
    el.oninput = calc; calc();
  }
  function toolFees(el) {
    el.innerHTML = `<section class="sec panel"><h2>Where to sell</h2><div class="form"><label class="f">Sale price $<input class="field" id="fe-s" type="number" inputmode="decimal" min="0" step="0.01" placeholder="100"></label>
      <label class="f">It's a<select class="select" id="fe-t"><option value="c">Card</option><option value="s">Sealed product</option></select></label></div><div id="fe-out"></div></section>`;
    const calc = () => {
      const s = cents($("#fe-s").value) || 10000, t = $("#fe-t").value;
      const rows = Object.entries(FEES.sell).map(([k, pl]) => { const fee = s - netSale(pl, s), so = shipOut(s, t, k); return { k, pl, fee, so, n: s - fee - so }; }).sort((a, b) => b.n - a.n);
      $("#fe-out").innerHTML = `<div class="kv">${rows.map((r) => `<div><span>${esc(r.pl.label)}<br><small class="muted">fees ${money(r.fee)}${r.so ? ` · shipping ${money(r.so)}` : ""}</small></span><span>${money(r.n)}</span></div>`).join("")}</div>
        <p class="muted small" style="margin:6px 0 0">You keep this much from a ${money(s)} sale. Fees checked ${esc(fmtDay(FEES.checked))}.</p>`;
    };
    el.oninput = calc; calc();
  }
  function toolCert(el) {
    el.innerHTML = `<section class="sec panel"><h2>Check a PSA slab</h2><p class="muted small" style="margin:0">Look up any PSA cert number on PSA's site before you buy: grade, card and population.</p>
      <form id="ce-f" class="btns"><input class="field" id="ce-n" inputmode="numeric" pattern="[0-9]*" placeholder="Cert number" aria-label="PSA cert number" style="flex:1;min-width:0"><button class="btn primary" type="submit">Look up</button></form>
      <p id="ce-out" class="small"></p></section>`;
    $("#ce-f").onsubmit = (e) => {
      e.preventDefault();
      const n = $("#ce-n").value.replace(/\D/g, "");
      $("#ce-out").innerHTML = n.length >= 6 ? `<a class="btn" href="https://www.psacard.com/cert/${n}/psa" target="_blank" rel="noopener">Open cert ${esc(n)} on PSA ↗</a>` : `<span class="down">Cert numbers are at least 6 digits.</span>`;
    };
  }

  /* ---------- Grade: your grading board, candidate finder, submission planner, results log ----------
     Graded prices here are the ones you enter (from the sold links), so every number is yours to check. */
  const GL = { PSA: ["10", "9"], CGC: ["10", "9"], BGS: ["9.5", "9"], TAG: ["10", "9"] };
  const FIND = { min: 30, max: 500, era: "modern", q: "", sort: null, mult: 0, liquid: false };
  function myRates() {
    const L = S.glog; if (L.length < 5) return null;
    const ten = L.filter((x) => parseFloat(x.grade) >= 10).length, nine = L.filter((x) => { const g = parseFloat(x.grade); return g >= 9 && g < 10; }).length;
    return { o10: ten / L.length, o9: nine / L.length, n: L.length };
  }
  function odds() { const m = S.set.useMyRates ? myRates() : null; return m ? { o10: m.o10, o9: m.o9, mine: true, src: "mine" } : { o10: S.set.o10 / 100, o9: Math.min(1 - S.set.o10 / 100, S.set.o9 / 100), mine: false, src: "guess" }; }
  /* Per-card odds from PokemonPriceTracker: the share of a card's graded sales (last 90 days) that were 10s and 9s.
     Small samples lean toward your own setting so a handful of sales can't swing it to 0% or 100%.
     It runs high (people sell their 10s more often than their 9s), so it ranks cards well but isn't a true gem rate. */
  const MIX_MIN = 5;
  function mixOf(id) {
    const c = GR?.c?.[id]; if (!c) return null;
    const [k10, k9, k8] = GK[grader().co] || GK.PSA, g = c[1] || {}, sk = ladderSkip(g), cnt = (k) => k && sk[k] !== "above" ? g[k]?.[1] || 0 : 0;
    const n10 = cnt(k10), n9 = cnt(k9), n8 = cnt(k8), n = n10 + n9 + n8;
    if (n < MIX_MIN) return null;
    const b = odds(), w = n / (n + 10), o10 = w * n10 / n + (1 - w) * b.o10;
    return { o10, o9: Math.min(1 - o10, w * n9 / n + (1 - w) * b.o9), mine: false, src: "mix", n, s10: n10 / n, s9: n9 / n };
  }
  /* PSA population: the real share of every copy PSA has graded that came back 10 / 9 (PSA grader only).
     Beats the sales mix when there are enough graded copies; small populations lean toward your setting. */
  const POP_MIN = 20;
  /* Numbers the owner typed in from PSA's pop report (S.pop[id] = [day, total graded, 10s, 9s or null]) come before
     the ones from PSA's API, so the real gem rate works for a card before PSA approves API access. */
  const popTyped = (id) => { const m = (S.pop || {})[id]; return m && m[1] >= POP_MIN && m[2] != null && m[2] <= m[1] && (m[3] == null || m[2] + m[3] <= m[1]) ? m : null; };
  const popIn = (id, k) => { const m = (S.pop || {})[id]; return m && m[k] != null ? m[k] : ""; };
  function popNote(id) {
    const m = (S.pop || {})[id];
    if (!m) return `Type this card's numbers from PSA's pop report or GemRate and the odds use its real gem rate. Blank = the estimate.`;
    if (m[1] != null && m[2] != null && (m[2] > m[1] || (m[3] != null && m[2] + m[3] > m[1]))) return `<span class="warn">10s and 9s can't add up to more than the total graded.</span>`;
    if (m[1] == null || m[2] == null) return `Enter both the total graded and the number of PSA 10s.`;
    if (m[1] < POP_MIN) return `Needs ${POP_MIN} or more graded copies to count; using the estimate until then.`;
    return `Using your numbers: ${Math.round(m[2] / m[1] * 100)}% of ${m[1].toLocaleString()} graded copies are PSA 10s (entered ${fmtDay(m[0])}).`;
  }
  function popOf(id) {
    if (grader().co !== "PSA") return null;
    const typed = popTyped(id), c = typed || POP?.c?.[id]; if (!c || c[1] < POP_MIN) return null;
    const [, n, n10, n9] = c, b = odds(), w = n / (n + 20), o10 = w * n10 / n + (1 - w) * b.o10;
    return { o10, o9: Math.min(1 - o10, n9 == null ? b.o9 : w * n9 / n + (1 - w) * b.o9), mine: false, src: "pop", n, s10: n10 / n, s9: n9 == null ? null : n9 / n, at: c[0], typed: !!typed };
  }
  const cardOdds = (id) => (S.set.useMix !== false && id != null && (popOf(id) || mixOf(id))) || odds();
  const odTag = (od) => od.src === "pop" ? " (PSA pop)" : od.src === "mix" ? "" : " (your setting)";
  const oddsText = (od) => `${Math.round(od.o10 * 100)}% ${grader().l10}s, ${Math.round(od.o9 * 100)}% ${grader().l9}s · ${od.src === "pop" ? `PSA population${od.typed ? " you entered" : ""}: ${Math.round(od.s10 * 100)}% of ${od.n.toLocaleString()} graded copies are 10s (as of ${fmtDay(od.at)})` : od.src === "mix" ? `from this card's ${od.n} graded sales` : od.src === "mine" ? "your graded results" : S.set.useMix === false ? "your setting (per-card odds are off under Your assumptions)" : "your setting (not enough sales for this card)"}`;
  function grader() {
    const co = FEES.graders[S.set.gco] ? S.set.gco : "PSA", gr = FEES.graders[co];
    const ti = Math.min(gr.tiers.length - 1, Math.max(0, +(S.set.gtier[co] ?? 0) || 0));
    return { co, gr, ti, tier: gr.tiers[ti], l10: GL[co]?.[0] || "10", l9: GL[co]?.[1] || "9" };
  }
  // expected result of grading one card worth `raw` (market value you give up), from the graded prices you entered
  function gradeEval(raw, p10, p9, p8, shipEach = S.set.gradeShip, od = odds()) {
    const { gr, ti } = grader(), { o10, o9 } = od, o8 = Math.max(0, 1 - o10 - o9), pl = plat();
    p9 = p9 || raw; p8 = p8 || Math.round(raw * 0.7);
    const fee = (v) => feeAt(gr, ti, v), out = (v) => netSale(pl, v) - fee(v) - shipEach - raw;
    const k = raw + shipEach + o9 * (fee(p9) - netSale(pl, p9)) + o8 * (fee(p8) - netSale(pl, p8));
    let be10 = 0;
    if (k > 0) {
      const ok = (v) => o10 * (netSale(pl, v) - fee(v)) >= k;
      if (!(o10 > 0) || !ok(1e9)) be10 = Infinity;
      else { let lo = 0, hi = 1e9; for (let i = 0; i < 60; i++) { const m = (lo + hi) / 2; if (ok(m)) hi = m; else lo = m; } be10 = hi; }
    }
    if (!p10) return { be10, od };
    const profit = o10 * out(p10) + o9 * out(p9) + o8 * out(p8), nine = out(p9), ten = out(p10);
    const v = profit > raw * 0.15 && nine >= 0 ? ["good", "Safe grade"] : profit > raw * 0.15 ? ["good", "Good odds"] : profit > 0 ? ["meh", "Risky"] : ["bad", "Skip it"];
    const up = gr.upcharge && tierFor(gr, p10) > ti ? gr.tiers[tierFor(gr, p10)] : null;
    return { be10, profit, nine, ten, v, up, od, grading: o10 * fee(p10) + o9 * fee(p9) + o8 * fee(p8) };
  }
  const tierLabel = (t) => `${t[0]} · ${money(t[1])}${t[2] ? ` · cards up to ${money(t[2], true)}` : ""}${t[3] ? ` · ~${t[3]} days` : ""}`;
  /* Graded sold prices from PokemonPriceTracker, for this phone only (personal use, on the owner's API plan).
     The update job publishes them encrypted; the key comes from the API key entered in Mine → Settings,
     which stays on this phone and out of backup files. */
  const PKEY = "dys-edge-ppt";
  const pptKey = () => { try { return (localStorage.getItem(PKEY) || "").replace(/\s+/g, ""); } catch { return ""; } };   // keys never contain spaces; pasted ones sometimes do
  let GR = null, GRP = null, GR_ERR = "", POP = null;   // POP: PSA population for the owner's top grading candidates (tools/psapop.py)
  const GK = { PSA: ["psa10", "psa9", "psa8"], CGC: ["cgc10", "cgc9", null], BGS: ["bgs9_5", "bgs9", null], TAG: ["tag10", "tag9", null] };
  const GNAME = [["psa10", "PSA 10"], ["psa9", "PSA 9"], ["psa8", "PSA 8"], ["cgc10", "CGC 10"], ["cgc9_5", "CGC 9.5"], ["cgc9", "CGC 9"], ["bgs10", "BGS 10"], ["bgs9_5", "BGS 9.5"], ["bgs9", "BGS 9"], ["tag10", "TAG 10"], ["tag9", "TAG 9"]];
  function loadGraded() {
    const k = pptKey();
    if (!k) { GR = null; GR_ERR = ""; return Promise.resolve(null); }
    if (!window.crypto?.subtle || typeof DecompressionStream === "undefined") { GR_ERR = "browser"; return Promise.resolve(null); }
    return (GRP ||= (async () => {
      const r = await fetch(`${BASE}data/edge/graded.enc`, { cache: "no-cache" });
      const M = new TextEncoder().encode("DYSENC1"), b = r.ok ? new Uint8Array(await r.arrayBuffer()) : new Uint8Array(0);
      if (b.length < 40 || M.some((c, i) => b[i] !== c)) { GR_ERR = "none"; return null; }
      const ck = await crypto.subtle.importKey("raw", await crypto.subtle.digest("SHA-256", new TextEncoder().encode("dys-sealed-edge:" + k)), "AES-GCM", false, ["decrypt"]);
      let plain;
      try { plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: b.slice(7, 19), additionalData: M }, ck, b.slice(19)); }
      catch { GR_ERR = "key"; return null; }
      GR = JSON.parse(await new Response(new Blob([plain]).stream().pipeThrough(new DecompressionStream("gzip"))).text());
      GR_ERR = "";
      try {   // same key; missing until the PSA job has run
        const r2 = await fetch(`${BASE}data/edge/psapop.enc`, { cache: "no-cache" }), b2 = r2.ok ? new Uint8Array(await r2.arrayBuffer()) : new Uint8Array(0);
        if (b2.length > 40 && !M.some((c, i) => b2[i] !== c)) {
          const p2 = await crypto.subtle.decrypt({ name: "AES-GCM", iv: b2.slice(7, 19), additionalData: M }, ck, b2.slice(19));
          POP = JSON.parse(await new Response(new Blob([p2]).stream().pipeThrough(new DecompressionStream("gzip"))).text());
        }
      } catch { POP = null; }
      return GR;
    })().catch(() => { GR_ERR ||= "load"; return null; }));
  }
  /* Grade prices that can't be right are left out of every calculation (they still show, marked):
     a lower grade selling above a higher one is almost always a mismatched sale (a different card or a lot),
     and a grade whose last sale is over 4 months old is no longer a price. */
  const LADDERS = [["psa10", "psa9", "psa8"], ["cgc10", "cgc9_5", "cgc9"], ["bgs10", "bgs9_5", "bgs9"], ["tag10", "tag9"]];
  const OLD_DAYS = 120;
  function ladderSkip(g) {
    const out = {};
    for (const L of LADDERS) for (let i = 1; i < L.length; i++) {
      const v = g[L[i]]; if (!v) continue;
      const higher = L.slice(0, i).filter((k) => g[k] && !out[k]).map((k) => g[k][0]);
      if (higher.length && v[0] > Math.min(...higher)) out[L[i]] = "above";
      else if (v[3] && daysAgo(v[3]) > OLD_DAYS) out[L[i]] = "old";
    }
    return out;
  }
  const SKIP_WHY = { above: "not used: sells above a higher grade, likely a mismatched sale", old: "not used: last sale over 4 months ago" };
  // one company's graded prices for a card (cents), or null
  function gradedOf(id, co = grader().co) {
    const c = GR?.c?.[id]; if (!c) return null;
    const [k10, k9, k8] = GK[co] || GK.PSA, g = c[1] || {}, sk = ladderSkip(g), a = g[k10], b = sk[k9] ? null : g[k9], d = k8 && !sk[k8] ? g[k8] : null;
    if (!a && !b) return null;
    return { p10: a?.[0] || null, n10: a?.[1] || 0, l10: a?.[3] || null, p9: b?.[0] || null, n9: b?.[1] || 0, p8: d?.[0] || null, n8: d?.[1] || 0, at: c[0],
      skip9: sk[k9] || null, skip8: k8 ? sk[k8] || null : null };
  }
  // what the board uses: your own prices first, then PokemonPriceTracker's
  function boardPrices(x) {
    const gp = gradedOf(x.id);
    return { p10: x.p10 || gp?.p10 || null, p9: x.p9 || gp?.p9 || null, p8: gp?.p8 || null, gp };
  }
  const solid = (gp) => gp?.p10 && gp.n10 >= 3 && (!gp.l10 || daysAgo(gp.l10) <= 60);
  // every steady single with enough graded sales, ranked by expected profit at your assumptions
  async function opportunities() {
    if (!GR) return null;
    const gd = await getJSON("grading.json").catch(() => null); if (!gd) return null;
    const seen = {}; for (const r of gd.rows) seen[r[0]] = (seen[r[0]] || 0) + 1;
    const out = [];
    for (const r of gd.rows) {
      if (seen[r[0]] > 1 || !gameOk(r[7])) continue;
      const gp = gradedOf(r[0]); if (!solid(gp)) continue;
      out.push({ r, gp, e: gradeEval(r[3], gp.p10, gp.p9, gp.p8, undefined, cardOdds(r[0])) });
    }
    return out.sort((a, b) => b.e.profit - a.e.profit);
  }
  function gradedBlock(it, p) {
    const c = GR?.c?.[it.id], g = c?.[1] || {}, have = GNAME.filter(([k]) => g[k]), sk = ladderSkip(g);
    if (!have.length) return `<section class="sec panel"><span class="lab">Graded sold prices</span><p class="muted small" style="margin:0">No graded sales on PokemonPriceTracker for this card yet${GR.c && Object.keys(GR.c).length ? "" : " (they fill in over the next updates)"}.</p></section>`;
    const bp = gradedOf(it.id), { co, l10 } = grader(), e = bp?.p10 ? gradeEval(p, bp.p10, bp.p9, bp.p8, undefined, cardOdds(it.id)) : null;
    return `<section class="sec panel"><span class="lab">Graded sold prices</span>
      <div class="kv">${have.map(([k, l]) => { const v = g[k]; return `<div${sk[k] ? ' style="opacity:.6"' : ""}><span>${l}<br><small class="muted">${v[1]} sold${v[3] ? ` · last ${esc(fmtDay(v[3]))}` : ""}</small>${sk[k] ? `<br><small class="warn">${SKIP_WHY[sk[k]]}</small>` : ""}</span><span>${sk[k] === "above" ? `<s>${money(v[0])}</s>` : money(v[0])}${p ? `<br><small class="muted">${(v[0] / p).toFixed(1)}× raw</small>` : ""}</span></div>`; }).join("")}</div>
      ${e ? `<div class="verdict ${e.v[0]}"><span class="lab">Grade it with ${esc(co)}?</span><b>${e.v[1]} · ${signed(Math.round(e.profit))} expected</b><span class="small muted">If ${esc(l10)}: ${signed(Math.round(e.ten))} · if ${esc(grader().l9)}: ${signed(Math.round(e.nine))}. Odds: ${esc(oddsText(e.od))}.</span></div>` : ""}
      <p class="muted small" style="margin:0">From PokemonPriceTracker (personal use)${c[0] ? `, checked ${esc(fmtDay(c[0]))}` : ""}.</p></section>`;
  }
  const vchip = (v) => `<span class="chip ${v[0] === "good" ? "good" : v[0] === "bad" ? "bad" : "hot"}">${v[1]}</span>`;
  const beText = (be, raw) => !isFinite(be) ? "—" : be < 1 ? "any grade pays" : `${money(Math.round(be))} (${(be / raw).toFixed(1)}× raw)`;
  function boardAdd(x) {
    const k = keyOf(x.id, x.n);
    if (!S.board.find((y) => y.k === k)) S.board.unshift({ k, id: x.id, g: x.g, n: x.n, t: "c", p10: null, p9: null, at: localDay() });
    save();
  }
  async function viewGrade(v) {
    v.innerHTML = `<div id="g-seg"></div><div id="g-body"></div>`;
    await Promise.all([loadIndex(), loadGraded()]);
    const draw = () => { const el = fresh($("#g-body")); ({ board: gradeBoard, find: gradeFind, submit: gradeSubmit, log: gradeLog, check: toolGrade }[SUB.grade] || gradeBoard)(el); };
    seg($("#g-seg"), [["board", "Board"], ["find", "Find"], ["submit", "Submit"], ["log", "Results"], ["check", "Check"]], SUB.grade, (k) => { SUB.grade = k; draw(); });
    draw();
  }
  function assumptions(onChange) {
    const { co, gr, ti } = grader(), m = myRates(), o = odds();
    const html = `<details class="panel" id="g-asm"><summary><b>Your assumptions</b> <span class="muted small">${esc(co)} ${esc(gr.tiers[ti][0])} · ${S.set.useMix !== false && GR ? "odds per card from its sales" : `${Math.round(o.o10 * 100)}% 10s, ${Math.round(o.o9 * 100)}% 9s${o.mine ? " (your results)" : ""}`} · sell on ${esc(plat().label)}</span></summary>
      <div class="form" style="margin-top:12px"><label class="f">Grading company<select class="select" id="ga-co">${Object.keys(FEES.graders).map((c) => `<option${c === co ? " selected" : ""}>${c}</option>`).join("")}</select></label>
        <label class="f full">Service level<select class="select" id="ga-tier">${gr.tiers.map((t, i) => `<option value="${i}"${i === ti ? " selected" : ""}>${esc(tierLabel(t))}</option>`).join("")}</select></label>
        <label class="toggle full"><input type="checkbox" id="ga-mix"${S.set.useMix !== false ? " checked" : ""}${GR ? "" : " disabled"}> Odds per card from its graded sales: the share of its last-90-day ${esc(co)} sales that were ${esc(GL[co][0])}s and ${esc(GL[co][1])}s (cards with ${MIX_MIN}+ sales). Runs a bit high, since people sell their 10s more often. When PSA's population is in (top grading candidates, about 45 new cards a day), PSA odds use its real gem rate instead.${GR ? "" : " Needs your PokemonPriceTracker key."}</label>
        <p class="muted small full" style="margin:0">${S.set.useMix !== false && GR ? "For cards with too few sales:" : "Your odds:"}</p>
        <label class="f">Chance of a ${esc(GL[co][0])}: <b id="ga-o10v">${S.set.o10}%</b><input type="range" id="ga-o10" min="5" max="90" step="5" value="${S.set.o10}"${o.mine ? " disabled" : ""}></label>
        <label class="f">Chance of a ${esc(GL[co][1])}: <b id="ga-o9v">${S.set.o9}%</b><input type="range" id="ga-o9" min="0" max="90" step="5" value="${S.set.o9}"${o.mine ? " disabled" : ""}></label>
        <label class="f">Shipping + insurance per card, both ways $<input class="field" id="ga-ship" type="number" inputmode="decimal" min="0" step="1" value="${dollars(S.set.gradeShip)}"></label>
        <label class="f">Sell the slab on${platSelect("ga-plat", S.set.platform)}</label>
        <label class="toggle full"><input type="checkbox" id="ga-mine"${S.set.useMyRates ? " checked" : ""}${m ? "" : " disabled"}> Use my real results${m ? ` (${m.n} graded: ${Math.round(m.o10 * 100)}% 10s, ${Math.round(m.o9 * 100)}% 9s)` : " (log 5+ graded cards in My results first)"}</label></div>
      ${gr.note ? `<p class="muted small" style="margin:8px 0 0">${esc(gr.note)}</p>` : ""}</details>`;
    const bind = (root) => {
      const det = $("#g-asm", root); det.open = !!assumptions.open; det.ontoggle = () => { assumptions.open = det.open; };
      $("#ga-co", root).onchange = (e) => { S.set.gco = e.target.value; save(); onChange(); };
      $("#ga-tier", root).onchange = (e) => { S.set.gtier[grader().co] = +e.target.value; save(); onChange(); };
      $("#ga-o10", root).oninput = (e) => { S.set.o10 = +e.target.value; $("#ga-o10v", root).textContent = `${S.set.o10}%`; };
      $("#ga-o9", root).oninput = (e) => { S.set.o9 = +e.target.value; $("#ga-o9v", root).textContent = `${S.set.o9}%`; };
      $("#ga-o10", root).onchange = $("#ga-o9", root).onchange = () => { save(); onChange(); };
      $("#ga-ship", root).onchange = (e) => { S.set.gradeShip = cents(e.target.value); save(); onChange(); };
      $("#ga-plat", root).onchange = (e) => { S.set.platform = e.target.value; save(); onChange(); };
      $("#ga-mine", root).onchange = (e) => { S.set.useMyRates = e.target.checked; save(); onChange(); };
      $("#ga-mix", root).onchange = (e) => { S.set.useMix = e.target.checked; save(); onChange(); };
    };
    return { html, bind };
  }
  function gradeBoard(el) {
    const draw = () => {
      const a = assumptions(draw), { co, l10, l9 } = grader();
      const rows = S.board.map((x, i) => {
        const raw = marketOf(x) || 0, bp = boardPrices(x), e = gradeEval(raw, bp.p10, bp.p9, bp.p8, undefined, cardOdds(x.id));
        return { x, i, raw, e, gp: bp.gp, p10: bp.p10, no: (x.n.match(/ - ([\w/-]+)/) || [])[1] || "" };
      });
      // sort: priced cards first in every order except name / newest
      const VORD = { "Safe grade": 0, "Good odds": 1, "Risky": 2, "Skip it": 3 }, pr = (r) => r.e.profit ?? -1e12;
      const SORTS = { profit: (a, b) => pr(b) - pr(a),
        safe: (a, b) => (VORD[a.e.v?.[1]] ?? 9) - (VORD[b.e.v?.[1]] ?? 9) || pr(b) - pr(a),
        if9: (a, b) => (b.e.nine ?? -1e12) - (a.e.nine ?? -1e12),
        mult: (a, b) => (b.p10 && b.raw ? b.p10 / b.raw : -1) - (a.p10 && a.raw ? a.p10 / a.raw : -1),
        raw: (a, b) => b.raw - a.raw, added: (a, b) => a.i - b.i, az: (a, b) => cleanN(a.x.n).localeCompare(cleanN(b.x.n)) };
      if (!SORTS[S.set.gbSort]) S.set.gbSort = "profit";
      rows.sort(SORTS[S.set.gbSort]);
      const priced = rows.filter((r) => r.e.profit != null), best = priced.filter((r) => r.e.profit > 0);
      el.innerHTML = `${a.html}
        ${S.board.length ? `<div class="tiles"><div class="tile"><span class="lab">On your board</span><b>${S.board.length}</b><small>${priced.length} with ${esc(co)} prices</small></div>
          <div class="tile"><span class="lab">Worth grading</span><b class="up">${best.length}</b><small>expected profit</small></div>
          <div class="tile"><span class="lab">Safe grades</span><b>${priced.filter((r) => r.e.v[1] === "Safe grade").length}</b><small>a ${esc(l9)} still pays</small></div></div>` : ""}
        <div class="sec-head"><h2>Grading board</h2><button type="button" class="more" id="gb-add">+ Add cards</button></div>
        ${S.board.length > 1 ? `<div id="gb-sort"></div>` : ""}
        ${!GR && !pptKey() ? `<p class="muted small" style="margin:0">Add your PokemonPriceTracker key in Mine → Settings and graded prices fill in by themselves.</p>` : ""}
        ${rows.length ? rows.map(({ x, i, raw, e, gp, no }) => `<div class="gcard panel">
          <button type="button" class="gc-top" data-open="${x.id}" data-g="${x.g}" data-n="${esc(x.n)}">${img(x.id)}<span class="gc-name"><span class="nm">${esc(cleanN(x.n))}</span><span class="st">${esc(setName(x.g))} · raw ${money(raw)}</span></span>
            ${e.v ? `<span class="chip ${e.v[0] === "good" ? "good" : e.v[0] === "bad" ? "bad" : "hot"}">${e.v[1]}</span>` : `<span class="chip">Needs prices</span>`}</button>
          <div class="gc-in"><label class="f">${esc(co)} ${esc(l10)} sells for $<input class="field" type="number" inputmode="decimal" min="0" step="0.01" data-b10="${i}" value="${dollars(x.p10)}" placeholder="${gp?.p10 ? dollars(gp.p10) + " (PPT)" : "from sold"}"></label>
            <label class="f">${esc(co)} ${esc(l9)} sells for $<input class="field" type="number" inputmode="decimal" min="0" step="0.01" data-b9="${i}" value="${dollars(x.p9)}" placeholder="${gp?.p9 ? dollars(gp.p9) + " (PPT)" : "blank = raw price"}"></label></div>
          ${gp ? `<p class="muted small" style="margin:0">PokemonPriceTracker sold prices: ${esc(l10)} ${gp.p10 ? `${money(gp.p10)} (${gp.n10} sold${gp.l10 ? `, last ${fmtDay(gp.l10)}` : ""})` : "no sales"} · ${esc(l9)} ${gp.p9 ? `${money(gp.p9)} (${gp.n9} sold)` : gp.skip9 ? `<span class="warn">${SKIP_WHY[gp.skip9]}</span>` : "no sales"}.${gp.n10 && gp.n10 < 3 ? ` <span class="warn">Only ${gp.n10} sale${gp.n10 === 1 ? "" : "s"}: check the sold links.</span>` : ""} Type a price to use your own.</p>` : GR ? `<p class="muted small" style="margin:0">No ${esc(co)} sales on PokemonPriceTracker for this one yet. Use the sold links.</p>` : ""}
          <div class="links"><a class="btn sm" href="${buyUrl(x.n, no, { p: raw, g: x.g })}" target="_blank" rel="noopener">Buy raw on eBay ↗</a><a class="btn sm" href="${soldUrl(x.n, no + " " + co + " " + l10)}" target="_blank" rel="noopener">${esc(co)} ${esc(l10)} sold ↗</a><a class="btn sm" href="${soldUrl(x.n, no + " " + co + " " + l9)}" target="_blank" rel="noopener">${esc(co)} ${esc(l9)} sold ↗</a>
            <a class="btn sm" href="https://www.pricecharting.com/search-products?q=${encodeURIComponent(cleanN(x.n))}&type=prices" target="_blank" rel="noopener">All grades ↗</a><a class="btn sm" href="https://www.gemrate.com/" target="_blank" rel="noopener">Gem rate ↗</a></div>
          <div class="kv">${e.profit != null ? `<div><span>Expected profit</span><span class="${cls(e.profit)}">${signed(Math.round(e.profit))}</span></div>
            <div><span>If ${esc(l10)} / if ${esc(l9)}</span><span><span class="up">${signed(Math.round(e.ten))}</span> / <span class="${cls(e.nine)}">${signed(Math.round(e.nine))}</span></span></div>` : ""}
            <div><span>${esc(l10)} needs to sell for</span><span>${beText(e.be10, raw)}</span></div>
            <div><span>Odds used</span><span class="small">${esc(oddsText(e.od))}</span></div></div>
          ${grader().co === "PSA" ? `<div class="gc-in gc-pop"><label class="f">PSA total graded<input class="field" type="number" inputmode="numeric" min="0" step="1" data-pop="${i}" data-pk="1" value="${popIn(x.id, 1)}"></label>
            <label class="f">PSA 10s<input class="field" type="number" inputmode="numeric" min="0" step="1" data-pop="${i}" data-pk="2" value="${popIn(x.id, 2)}"></label>
            <label class="f">PSA 9s (optional)<input class="field" type="number" inputmode="numeric" min="0" step="1" data-pop="${i}" data-pk="3" value="${popIn(x.id, 3)}"></label></div>
          <p class="muted small" style="margin:0">${popNote(x.id)}</p>` : ""}
          ${e.up ? `<p class="muted small" style="margin:0">A ${esc(l10)} here is upcharged to ${esc(e.up[0])} (${money(e.up[1])}); counted.</p>` : ""}
          <div class="btns"><button type="button" class="btn sm" data-log="${i}">Log result</button><button type="button" class="btn sm ghost danger" data-rm="${i}">Remove</button></div></div>`).join("")
          : `<div class="empty"><b>Build your grading board</b>Add cards from <b style="display:inline;font-size:inherit">Find</b> or tap Grade it? on any card. Enter what a 10 and a 9 sell for (tap the sold links), and the board ranks them by expected profit after every fee.</div>`}`;
      a.bind(el);
      if ($("#gb-sort", el)) seg($("#gb-sort", el), [["profit", "Most profit"], ["safe", "Safest"], ["if9", "Best if a 9"], ["mult", "10 vs raw"], ["raw", "Raw price"], ["added", "Newest"], ["az", "A–Z"]],
        S.set.gbSort, (k) => { S.set.gbSort = k; save(); draw(); });
      $("#gb-add", el).onclick = () => { SUB.grade = "find"; viewGrade($("#view")); };
      el.onchange = (e) => {
        const t = e.target, i10 = t.dataset.b10, i9 = t.dataset.b9;
        if (i10 != null) { S.board[+i10].p10 = cents(t.value) || null; save(); draw(); }
        if (i9 != null) { S.board[+i9].p9 = cents(t.value) || null; save(); draw(); }
        if (t.dataset.pop != null) {      // PSA population typed in for this card
          const id = S.board[+t.dataset.pop].id, m = (S.pop ||= {})[id] || [null, null, null, null], v = t.value.trim() === "" ? null : Math.round(+t.value);
          m[+t.dataset.pk] = Number.isFinite(v) && v >= 0 ? v : null; m[0] = localDay();
          if (m[1] == null && m[2] == null && m[3] == null) delete S.pop[id]; else S.pop[id] = m;
          save(); draw();
        }
      };
      el.onclick = (e) => {
        const rm = e.target.closest("[data-rm]"), lg = e.target.closest("[data-log]");
        if (rm) { S.board.splice(+rm.dataset.rm, 1); save(); draw(); }
        if (lg) { const x = S.board[+lg.dataset.log]; LOGDRAFT = { k: x.k, id: x.id, g: x.g, n: x.n, raw: marketOf(x) }; SUB.grade = "log"; viewGrade($("#view")); }
      };
    };
    draw();
  }
  async function gradeFind(el) {
    el.innerHTML = `<p class="muted">Loading cards…</p>`;
    const [main, cheap] = await Promise.all([getJSON("grading.json").catch(() => null), getJSON("grading-cheap.json").catch(() => null)]);
    if (!main) { el.innerHTML = `<div class="empty">The candidate list builds with the nightly update.</div>`; return; }
    const gd = { rows: main.rows.concat(cheap?.rows || []) };
    const multi = new Set(), seen = {};
    for (const r of gd.rows) { seen[r[0]] = (seen[r[0]] || 0) + 1; if (seen[r[0]] > 1) multi.add(r[0]); }
    // liquid = the graded copy actually trades: 5+ sold in 90 days and one in the last 30
    const liquid = (gp) => gp && gp.n10 >= 5 && gp.l10 && daysAgo(gp.l10) <= 30;
    el.innerHTML = `${GR ? `<div id="fd-asm"></div><p class="muted small" style="margin:0">Steady singles ranked by expected profit from grading, using ${esc(grader().co)} sold prices from PokemonPriceTracker (cards with 3+ sales in 90 days) and your assumptions above. Add the best ones to your board.</p>`
        : `<p class="muted small" style="margin:0">Singles with steady prices and live listings near market, so the raw price is real. Each shows what a graded ${esc(grader().l10)} has to sell for to pay off at your assumptions.${pptKey() ? "" : " Add your PokemonPriceTracker key in Mine → Settings to rank them by real profit."}</p>`}
      ${GR ? `<button type="button" class="btn full" id="fd-10x">Cheap 10× finder: $1–$25 raw, ${esc(grader().co + " " + grader().l10)} sells 10×+, liquid</button>` : ""}
      <div class="form"><label class="f">Raw price from $<input class="field" id="fd-min" type="number" inputmode="decimal" min="0" value="${FIND.min}"></label>
        <label class="f">to $<input class="field" id="fd-max" type="number" inputmode="decimal" min="0" value="${FIND.max}"></label>
        <label class="f full">Search<input class="field" id="fd-q" type="search" placeholder="Card or set" value="${esc(FIND.q)}"></label></div>
      ${GR && !hasPkm() ? `<p class="muted small" style="margin:0">Graded sold prices cover Pokémon only, so ${esc((GAMES[S.set.game] || [""])[0])} cards show what a 10 has to sell for to pay off. Switch the game in Search or Sets to Pokémon for real grade prices.</p>` : ""}
      <div id="fd-era"></div>${GR ? `<div id="fd-mult"></div><label class="toggle"><input type="checkbox" id="fd-liq"${FIND.liquid ? " checked" : ""}> Liquid only: ${esc(grader().co + " " + grader().l10)} sold 5+ times in 90 days, last sale within 30 days</label>` : ""}<div id="fd-sort"></div><div id="fd-list"></div>`;
    const draw = () => {
      const q = FIND.q.trim().toLowerCase(), onBoard = new Set(S.board.map((x) => x.k));
      let rows = gd.rows.filter((r) => !multi.has(r[0]) && gameOk(r[7]) && (FIND.era === "all" || r[8] === FIND.era) && r[3] >= FIND.min * 100 && (!FIND.max || r[3] <= FIND.max * 100)
        && (!q || (r[2] + " " + setName(r[1])).toLowerCase().includes(q)));
      const sort = (FIND.sort === "profit" || FIND.sort === "mult") && !hasPkm() ? "price" : FIND.sort || (GR && hasPkm() ? "profit" : "price"), { l10 } = grader();
      rows = rows.map((r) => { const gp = GR ? gradedOf(r[0]) : null, ok = solid(gp); return { r, gp: ok ? gp : null, e: gradeEval(r[3], ok ? gp.p10 : null, ok ? gp.p9 : null, ok ? gp.p8 : null, undefined, cardOdds(r[0])) }; });
      if (GR && FIND.mult) rows = rows.filter((x) => x.gp && x.gp.p10 >= FIND.mult * x.r[3]);
      if (GR && FIND.liquid) rows = rows.filter((x) => liquid(x.gp));
      if (sort === "profit" || sort === "mult") rows = rows.filter((x) => x.gp);
      rows.sort(sort === "mult" ? (a, b) => b.gp.p10 / b.r[3] - a.gp.p10 / a.r[3] : sort === "profit" ? (a, b) => b.e.profit - a.e.profit : sort === "easy" ? (a, b) => (a.e.be10 / a.r[3]) - (b.e.be10 / b.r[3]) : (a, b) => b.r[3] - a.r[3]);
      const out = rows.slice(0, 80).map(({ r, gp, e }) => { const k = keyOf(r[0], r[2]), be = e.be10;
        const add = onBoard.has(k) ? `<span class="chip good">On your board</span>` : `<span class="chip" data-addb="${r[0]}|${r[1]}|${esc(r[2])}">+ Add to board</span>`;
        return gp ? rowHTML({ id: r[0], g: r[1], n: r[2] }, `<b class="${cls(e.profit)}">${signed(Math.round(e.profit))}</b><small class="muted">raw ${money(r[3])} · ${esc(l10)} ${money(gp.p10, gp.p10 >= 100000)}</small>`,
            `<span class="why">${vchip(e.v)} <b>${(gp.p10 / r[3]).toFixed(1)}×</b> · ${Math.round(e.od.o10 * 100)}% ${esc(l10)}s${odTag(e.od)} · ${gp.n10} sold in 90 days${gp.l10 ? `, last ${fmtDay(gp.l10)}` : ""}${gp.p9 ? ` · ${esc(grader().l9)} ${money(gp.p9)}` : ""} ${add}${gp.p10 > 40 * r[3] ? `<span class="risk">a ${esc(l10)} at ${Math.round(gp.p10 / r[3])}× raw is unusual. Check the sold listings: they may include a 1st Edition, shadowless or other printing.</span>` : ""}</span>`)
          : rowHTML({ id: r[0], g: r[1], n: r[2] }, `<b>${money(r[3])}</b><small class="muted">${esc(grader().co + " " + l10)} needs ${!isFinite(be) ? "—" : `${money(Math.round(be), be >= 100000)} (${(be / r[3]).toFixed(0)}×)`}</small>`, `<span class="why">${add}</span>`); });
      $("#fd-list").innerHTML = (FIND.mult && rows.length ? `<p class="muted small" style="margin:0">${rows.length} card${rows.length === 1 ? "" : "s"} where a ${esc(grader().co + " " + l10)} sells for ${FIND.mult}×+ raw${FIND.liquid ? " and trades often" : ""}. A big multiple on a cheap card can still lose money once fees are in: the green number is profit after grading fees, shipping, selling fees and your grade odds.</p>` : "")
        + listOrEmpty(out, FIND.mult ? `No cards at ${FIND.mult}×+ yet${FIND.liquid ? " that trade often" : ""}. Graded prices for $1–$20 cards fill in over the next few days; try again soon, lower the multiple, or turn off Liquid only.` : sort === "profit" ? "No cards with enough graded sales match. Widen the price range, switch era or games, or sort by Most valuable." : "No cards match. Widen the price range or switch games.") + (rows.length > 80 ? `<p class="muted small">Showing 80 of ${rows.length}. Narrow it with search or price.</p>` : "");
    };
    seg($("#fd-era"), [["modern", "Modern"], ["vintage", "Older sets"], ["all", "All"]], FIND.era, (k) => { FIND.era = k; draw(); });
    if (GR) {
      seg($("#fd-mult"), [[0, "Any multiple"], [5, "5×+"], [10, "10×+"], [20, "20×+"]], FIND.mult, (k) => { FIND.mult = +k; draw(); });
      $("#fd-liq").onchange = (e) => { FIND.liquid = e.target.checked; draw(); };
      $("#fd-10x").onclick = () => { Object.assign(FIND, { min: 1, max: 25, era: "all", mult: 10, liquid: true, sort: "profit", q: "" }); gradeFind(fresh($("#g-body"))); };
    }
    seg($("#fd-sort"), [...(GR ? [["profit", "Best profit"], ["mult", "Multiple"]] : []), ["price", "Most valuable"], ["easy", "Easiest to pay off"]], FIND.sort || (GR ? "profit" : "price"), (k) => { FIND.sort = k; draw(); });
    if (GR) { const asm = () => { const a = assumptions(() => { asm(); draw(); }); $("#fd-asm").innerHTML = a.html; a.bind($("#fd-asm")); }; asm(); }
    $("#fd-min").onchange = (e) => { FIND.min = +e.target.value || 0; draw(); };
    $("#fd-max").onchange = (e) => { FIND.max = +e.target.value || 0; draw(); };
    let t; $("#fd-q").oninput = (e) => { clearTimeout(t); t = setTimeout(() => { FIND.q = e.target.value; draw(); }, 200); };
    $("#fd-list").addEventListener("click", (e) => {
      const b = e.target.closest("[data-addb]"); if (!b) return;
      e.stopPropagation();
      const [id, g, ...n] = b.dataset.addb.split("|"); boardAdd({ id: +id, g: +g, n: n.join("|") }); toast("Added to your board"); draw();
    }, true);
    draw();
  }
  function gradeSubmit(el) {
    const draw = () => {
      const a = assumptions(draw), { co, gr, tier, l10, l9 } = grader();
      const box = S.set.boxShip, picked = S.board.filter((x) => S.sub.includes(x.k));
      const per = picked.map((x) => { const raw = marketOf(x) || 0, bp = boardPrices(x); return { x, raw, e: gradeEval(raw, bp.p10, bp.p9, bp.p8, 0, cardOdds(x.id)) }; });
      const base = picked.length * tier[1], exp = per.reduce((s, r) => s + (r.e.grading ?? tier[1]), 0);
      const profit = per.reduce((s, r) => s + (r.e.profit ?? 0), 0) - box, worst = per.reduce((s, r) => s + (r.e.nine ?? 0), 0) - box;
      const missing = per.filter((r) => r.e.profit == null).length;
      el.innerHTML = `${a.html}<section class="sec panel"><h2>Plan a submission</h2>
        <p class="muted small" style="margin:0">Tick the cards from your board to send together. Shipping and insurance are for the whole box.</p>
        <div class="list">${S.board.length ? S.board.map((x) => { const raw = marketOf(x) || 0, bp = boardPrices(x), e = gradeEval(raw, bp.p10, bp.p9, bp.p8, 0, cardOdds(x.id));
          return `<label class="row" style="grid-template-columns:24px 44px minmax(0,1fr) auto;cursor:pointer"><input type="checkbox" data-sub="${esc(x.k)}"${S.sub.includes(x.k) ? " checked" : ""}>${img(x.id)}
            <span style="min-width:0"><span class="nm">${esc(cleanN(x.n))}</span><span class="st">raw ${money(raw)}</span></span><span class="rt">${e.v ? `<span class="chip ${e.v[0] === "good" ? "good" : e.v[0] === "bad" ? "bad" : "hot"}">${e.v[1]}</span>` : `<small class="muted">no ${esc(l10)} price</small>`}</span></label>`; }).join("")
          : `<p class="muted small" style="padding:12px">Your board is empty. Add cards in Find first.</p>`}</div>
        <label class="f">Shipping + insurance for the whole box, both ways $<input class="field" id="sb-box" type="number" inputmode="decimal" min="0" step="1" value="${dollars(box)}"></label>
        ${picked.length ? `<div class="verdict ${profit > 0 && worst >= 0 ? "good" : profit > 0 ? "meh" : "bad"}"><span class="lab">${picked.length} card${picked.length === 1 ? "" : "s"} · ${esc(co)} ${esc(tier[0])}</span>
          <b>${signed(Math.round(profit))} expected</b><span class="small muted">If every card comes back a ${esc(l9)}: ${signed(Math.round(worst))}${missing ? `. ${missing} card${missing === 1 ? " has" : "s have"} no ${esc(l10)} price yet and count${missing === 1 ? "s" : ""} as zero.` : "."}</span></div>
          <div class="kv"><div><span>Grading fees at ${money(tier[1])} each</span><span>${money(base)}</span></div>
            <div><span>Expected fees with upcharges</span><span>${money(Math.round(exp))}</span></div>
            <div><span>Shipping + insurance</span><span>${money(box)}</span></div>
            <div><span>Raw value you're sending</span><span>${money(per.reduce((s, r) => s + r.raw, 0), true)}</span></div>
            <div><span>Turnaround</span><span>about ${esc(tier[3])} business days</span></div></div>
          ${tier[2] && per.some((r) => r.raw > tier[2]) ? `<p class="warn small" style="margin:0">Some cards are already worth more than ${esc(tier[0])} covers (${money(tier[2], true)}). Declare them at a higher tier.</p>` : ""}
          ${co === "CGC" && tier[0] === "Bulk" && picked.length < 25 ? `<p class="warn small" style="margin:0">CGC Bulk needs 25 or more cards. Add more or pick Economy.</p>` : ""}` : ""}</section>`;
      a.bind(el);
      $("#sb-box", el).onchange = (e) => { S.set.boxShip = cents(e.target.value); save(); draw(); };
      el.onchange = (e) => { const k = e.target.dataset.sub; if (k == null) return; S.sub = e.target.checked ? [...new Set([...S.sub, k])] : S.sub.filter((y) => y !== k); save(); draw(); };
    };
    draw();
  }
  let LOGDRAFT = null;
  function gradeLog(el) {
    const draw = () => {
      const m = myRates(), L = S.glog;
      const sold = L.filter((x) => x.sold), pr = sold.reduce((s, x) => s + (netSale(plat(), x.sold) - x.raw - x.fee), 0);
      const d = LOGDRAFT || {};
      el.innerHTML = `<div class="tiles"><div class="tile"><span class="lab">Graded</span><b>${L.length}</b><small>cards logged</small></div>
        <div class="tile"><span class="lab">Gem rate</span><b>${L.length ? Math.round(L.filter((x) => parseFloat(x.grade) >= 10).length / L.length * 100) + "%" : "—"}</b><small>10s (BGS 9.5+)</small></div>
        <div class="tile"><span class="lab">Profit</span><b class="${cls(pr)}">${sold.length ? (pr >= 0 ? "+" : "") + money(Math.round(pr), true) : "—"}</b><small>${sold.length} sold, after fees</small></div></div>
        ${m ? `<p class="muted small" style="margin:0">Your board can use your real rates (${Math.round(m.o10 * 100)}% 10s, ${Math.round(m.o9 * 100)}% 9s) instead of a guess: turn it on under Your assumptions.</p>` : `<p class="muted small" style="margin:0">Log at least 5 graded cards and the board can use your own gem rate instead of a guess.</p>`}
        <form class="inline-form" id="lg-f"><h3>Log a graded card</h3><div class="form">
          <label class="f full">Card<input class="field" id="lg-n" value="${esc(d.n ? cleanN(d.n) : "")}" placeholder="Name and number" required></label>
          <label class="f">Company<select class="select" id="lg-co">${Object.keys(GL).map((c) => `<option${c === (d.co || grader().co) ? " selected" : ""}>${c}</option>`).join("")}</select></label>
          <label class="f">Grade<select class="select" id="lg-gr">${["10", "9.5", "9", "8.5", "8", "7"].map((g) => `<option value="${g}">${g === "7" ? "7 or lower" : g}</option>`).join("")}</select></label>
          <label class="f">Raw value when sent $<input class="field" id="lg-raw" type="number" inputmode="decimal" min="0" step="0.01" value="${dollars(d.raw)}"></label>
          <label class="f">Grading + shipping paid $<input class="field" id="lg-fee" type="number" inputmode="decimal" min="0" step="0.01" value="${dollars(grader().tier[1] + S.set.gradeShip)}"></label>
          <label class="f full">Sold for $ (leave blank if you kept it)<input class="field" id="lg-sold" type="number" inputmode="decimal" min="0" step="0.01"></label></div>
          <div class="btns"><button class="btn primary" type="submit">Save result</button></div></form>
        ${L.length ? `<div class="list">${L.map((x, i) => `<div class="row" style="cursor:default">${x.id ? img(x.id) : `<div class="ph"></div>`}<span style="min-width:0"><span class="nm">${esc(cleanN(x.n))}</span><span class="st">${esc(x.co)} ${esc(x.grade)} · ${esc(fmtDay(x.at))}</span></span>
          <span class="rt"><b>${x.sold ? money(x.sold) : "kept"}</b><small class="${x.sold ? cls(netSale(plat(), x.sold) - x.raw - x.fee) : "muted"}">${x.sold ? signed(Math.round(netSale(plat(), x.sold) - x.raw - x.fee)) : `raw ${money(x.raw)}`}</small><button type="button" class="x" aria-label="Delete" data-del="${i}">✕</button></span></div>`).join("")}</div>` : ""}`;
      $("#lg-f", el).onsubmit = (e) => {
        e.preventDefault();
        S.glog.unshift({ id: d.id || null, g: d.g || null, n: $("#lg-n", el).value.trim(), co: $("#lg-co", el).value, grade: $("#lg-gr", el).value,
          raw: cents($("#lg-raw", el).value), fee: cents($("#lg-fee", el).value), sold: cents($("#lg-sold", el).value) || null, at: localDay() });
        LOGDRAFT = null; save(); toast("Result saved"); draw();
      };
      el.onclick = (e) => { const b = e.target.closest("[data-del]"); if (!b) return; S.glog.splice(+b.dataset.del, 1); save(); draw(); };
    };
    draw();
  }

  /* ---------- Mine ---------- */
  async function viewMine(v) {
    v.innerHTML = `<div id="m-seg"></div><div id="m-body"></div>`;
    await loadIndex();
    await Promise.all([LEDGER, loadGraded()]);
    if (SUB.mine === "ledger" && !LS) SUB.mine = "inv";
    const draw = () => { const el = fresh($("#m-body")); ({ inv: mineInv, ledger: mineLedger, watch: mineWatch, set: mineSettings }[SUB.mine] || mineInv)(el); };
    seg($("#m-seg"), [["inv", "Inventory"], ...(LS ? [["ledger", "Ledger"]] : []), ["watch", "Watchlist"], ["set", "Settings"]], SUB.mine, (k) => { SUB.mine = k; draw(); });
    ledgerSync().then((r) => { if (r && r.ok && SUB.mine === "ledger" && LMOUNT) LMOUNT.redraw(); });
    draw();
  }
  /* ---------- Holdings Advisor: review every holding against real sold prices (this page only) ---------- */
  const ADVIN = new Map(); let ADVAT = null, ADVCRED = 0, ADVBUSY = false;
  const advKey = (x) => x.lid || x.k;
  // rough upper bound for the button: raw up to ~210 credits (raw, PSA 10, PSA 9 sales + population), PSA ~161, sealed ~90
  const advEstimate = (inv) => inv.reduce((s, x) => s + (x.graded ? 161 : x.t === "s" ? 90 : 210), 0);
  const advBase = (x) => ({ key: advKey(x), name: cleanN(x.n), kind: x.graded ? "graded" : x.t === "s" ? "sealed" : "raw", qty: x.qty, cost: x.cost || 0,
    cond: x.cond || "NM", grade: x.graded || "", book: x.book || "" });
  // guards against paid repeats (Claude's defaults; the review log keeps only when, how many and credits: no prices)
  const ADV_RECENT_H = 12;            // hours: a full review this recent asks "review again anyway?"
  const ADV_DAY_CAP = 10000;          // credits a day for holdings reviews on this phone (half the plan's 20,000; Deal checks keep the rest)
  let ADVSTOP = false;
  const advLog = () => (Array.isArray(S.advLog) ? S.advLog : []).filter((r) => r && r.at > Date.now() - 2 * 864e5);
  const advToday = () => advLog().filter((r) => r.day === localDay()).reduce((s, r) => s + (r.cr || 0), 0);
  const advLast = () => advLog().filter((r) => r.full).sort((a, b) => b.at - a.at)[0] || null;
  function advRecord(n, cr, full) { S.advLog = [...advLog(), { at: Date.now(), day: localDay(), n, cr, full: !!full }].slice(-20); save(); }
  /* Saved calls: the advisor's own calls kept on this phone for 12 hours (edge-advisor.js snapshot: call, reason without
     amounts, sale counts, best option's name, profit as a range). No sold prices or other PkmnPrices data, and not in
     backup files. A row is dropped when it expires, when that holding's cost, quantity, condition or grade changes, or
     when the selling settings it was worked out with change. */
  const AKEY = "dys-edge-advice", ADV_KEEP_H = 12;
  const advSig = () => JSON.stringify(["roi", "minProfit", "platform", "buyerTax", "supCard", "supSealed", "shipCard", "shipCard50", "shipSealed", "shipSealed100", "gradeShip", "holdRate"].map((k) => S.set[k] ?? null));
  const advFp = (x) => [x.cost || 0, x.qty, x.cond || "", x.graded || "", x.t || ""].join("|");
  function advSaved() {
    try {
      const j = JSON.parse(localStorage.getItem(AKEY) || "null"), now = Date.now();
      if (!j || j.v !== 1 || j.sig !== advSig() || !Array.isArray(j.rows)) { if (j) localStorage.removeItem(AKEY); return new Map(); }
      const rows = j.rows.filter((r) => r && r.at > now - ADV_KEEP_H * 36e5 && r.at <= now);
      if (rows.length !== j.rows.length) { if (rows.length) localStorage.setItem(AKEY, JSON.stringify({ ...j, rows })); else localStorage.removeItem(AKEY); }
      return new Map(rows.map((r) => [r.key, r]));
    } catch { return new Map(); }
  }
  // the saved call for a holding, if it still matches that holding
  const advSavedFor = (x, M) => { const r = M.get(advKey(x)); return r && r.fp === advFp(x) ? r : null; };
  async function advKeep(inv) {
    const adv = await ADV; if (!adv) return;
    const M = advSaved(), rows = [];
    for (const x of inv) {
      const k = advKey(x), fresh = ADVIN.get(k);
      if (fresh && fresh.at) rows.push({ ...adv.snapshot([adv.classify(fresh)])[0], fp: advFp(x), at: fresh.at });
      else { const r = advSavedFor(x, M); if (r) rows.push(r); }
    }
    try { if (rows.length) localStorage.setItem(AKEY, JSON.stringify({ v: 1, sig: advSig(), rows })); else localStorage.removeItem(AKEY); } catch {}
  }
  const ADVOWN = { sell: "sell", grade: "grade", monitor: "monitor", hold: "hold", data: "unclear" };
  // Inventory's per-row chips from saved calls, for holdings not checked on this visit
  function advChips() {
    const M = advSaved();
    for (const x of invRows()) { const k = advKey(x); if (ADVIN.has(k) || OWN.has(k)) continue; const r = advSavedFor(x, M); if (r) OWN.set(k, { label: ADVOWN[r.action], text: `${r.why} (saved ${clock(r.at)})` }); }
  }
  async function reviewHoldings(inv, st) {
    const conn = pkmnConn(), [deal, pkmn, gr, chan] = await Promise.all([DEAL, PKMN, GRADED, CHAN]);
    if (!conn || !deal || !pkmn || !gr) return { ok: false, why: "Sold prices aren't set up yet (Mine → Settings → Pair this phone)." };
    if (ADVBUSY) return { ok: false, why: "A review is already running." };
    ADVBUSY = true; ADVSTOP = false; let credits = 0, i = 0, cut = null, stopped = 0;
    const put = (x, val, own) => { ADVIN.set(advKey(x), { ...advBase(x), ...val, at: Date.now() }); if (own) OWN.set(advKey(x), own); };
    try {
      for (const x of inv) {
        // the relay can't be reached or refuses this phone: the rest would fail the same way, so they aren't tried
        if (cut) { put(x, x.graded ? { graded: null, note: cut } : { own: null, note: cut }, { label: "unknown", text: cut }); continue; }
        if (ADVSTOP) { stopped++; continue; }
        st && st(`Checking ${++i} of ${inv.length}… · ${credits.toLocaleString("en-US")} credits so far`);
        if (x.graded) {
          // a slab: that grader and grade's sold prices only (the raw Deal check doesn't apply to a slab)
          try {
            const [grader, grade] = x.graded.split(" "), res = await pkmn.getGrade({ id: x.id, n: x.n }, { grader, grade }, conn, true);
            credits += res.meta ? res.meta.credits : 0;
            if (!res.ok) { const note = gradedNote(res).note; if (res.reason === "network" || res.reason === "denied") cut = note;
              put(x, { graded: null, note }, { label: res.reason === "unsupported" ? "unclear" : "unknown", text: note }); continue; }
            const sell = gradedSell(), r = gr.evaluate(res.data, { cost: x.cost || 0, label: x.graded }, sell, gradedOpts());
            noteSold(x.id, x.n, x.graded, r);
            const ch = chan && r.typical != null ? chan.compare({ ...chanOpts("graded", x.n), cost: x.cost || 0, ref: r.typical,
              ebay: { feePct: sell.feePct, topFrom: sell.topFrom ?? 750000, topPct: sell.topPct || 0, feeFlat: sell.perOrder || 0, buyerTax: sell.buyerTax, ship: sell.ship, sup: sell.supplies || 0 } }) : null;
            put(x, { graded: r, ch }, { label: { sell: "sell", hold: "hold", insufficient: "unclear" }[r.verdict], text: gr.line(r) });
          } catch (err) { console.error(err); put(x, { graded: null, note: "Couldn't check this one." }, { label: "unknown", text: "Couldn't check this one." }); }
          continue;
        }
        try {
          const d = await detail(x.id, x.g, x.n), it = d.it;
          if (!it) { const note = "No market price for this item right now."; put(x, { own: null, note }, { label: "unknown", text: note }); continue; }
          const item = { id: it.id, n: it.n, name: it.n, t: it.t, r: it.r, setN: d.set.n, tcg: it.p, tcgDay: dayNum(d.set.dates?.[d.set.dates.length - 1]) };
          const res = await pkmn.get(item, conn, true); credits += res.meta ? res.meta.credits : 0;
          if (!res.ok) { const note = soldNote(res).note; if (res.reason === "network" || res.reason === "denied") cut = note;
            put(x, { own: null, note }, { label: "unknown", text: note }); continue; }
          const o = deal.own(item, res.data, { cost: x.cost || 0, cond: x.cond || "NM" }, dealCfg(it.p));
          const ref = o.r && o.r.routes && o.r.routes.flip ? o.r.routes.flip.exit : null;
          const ch = chan && ref && ["sell", "hold", "grade"].includes(o.label) ? chan.compare({ ...chanOpts(x.t === "s" ? "sealed" : "card", x.n), cost: x.cost || 0, ref }) : null;
          put(x, { own: o, ch }, o);
        } catch (err) { console.error(err); put(x, { own: null, note: "Couldn't check this one." }, { label: "unknown", text: "Couldn't check this one." }); }
      }
    } finally { ADVBUSY = false; ADVSTOP = false; }
    ADVAT = Date.now(); ADVCRED = credits;
    return { ok: true, credits, stopped, checked: i, cut: !!cut };
  }
  // the action list: every holding, reviewed or not (not reviewed = "Not enough data: not checked yet")
  async function drawAdvisor(el, opt = {}) {
    if (!el) return;
    const adv = await ADV, inv = invRows();
    if (!adv) { el.innerHTML = ""; return; }
    const M = advSaved(), kept = new Map(adv.restore(inv.map((x) => !ADVIN.has(advKey(x)) && advSavedFor(x, M)).filter(Boolean)).map((r) => [r.key, r]));
    const keptAt = [...kept.keys()].map((k) => M.get(k).at);
    const list = inv.map((x) => ADVIN.get(advKey(x)) || kept.get(advKey(x)) || { ...advBase(x), note: "Not reviewed yet: tap Review." });
    const has = (x) => ADVIN.has(advKey(x)) || kept.has(advKey(x));
    const done = inv.filter(has).length, fresh = inv.filter((x) => !has(x)), conn = pkmnConn();
    const fmt = (n) => n.toLocaleString("en-US"), plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
    // what the main button does: all holdings the first time; only the ones added since, once some are reviewed
    const target = done && fresh.length ? fresh : inv, full = target === inv, est = advEstimate(target), last = advLast(), spent = advToday();
    const goTxt = !done ? `Review my ${plural(inv.length, "holding")}` : fresh.length ? `Check ${plural(fresh.length, "unchecked holding")}` : "Review all again";
    const lastTxt = last ? `Last full review ${last.day === localDay() ? "today" : "yesterday"} at ${clock(last.at)}: ${plural(last.n, "item")}, ${fmt(last.cr)} credits.` : "";
    el.innerHTML = `<div class="sec-head"><h2>${opt.title || "Your holdings: what to do"}</h2>${opt.title ? "" : `<a class="more" href="#mine">Inventory</a>`}</div>
      ${inv.length ? `<p class="muted small adv-note">Checks each holding against real eBay sold prices (PkmnPrices). Facts at today's prices, not a forecast. Sold prices aren't saved: the calls stay on this phone for 12 hours, with amounts as ranges.</p>
      ${!conn ? `<div class="panel adv-off"><b>Sold prices aren't set up on this phone</b><p class="small muted" style="margin:4px 0 8px">Pair it once in Mine → Settings. Until then nothing is checked and no credits are used; everything else in Edge works as usual.</p>
        <div class="btns"><button type="button" class="btn sm primary adv-pair">Go to Settings</button><button type="button" class="btn sm adv-go" disabled>Set up sold prices first</button></div></div>`
      : `<div class="btns"><button type="button" class="btn ${done && !fresh.length ? "sm" : "primary"} adv-go">${goTxt}</button>${done && fresh.length ? `<button type="button" class="btn sm adv-all">Review all again</button>` : ""}</div>
      <p class="small muted adv-est" style="margin:0">Up to about ${fmt(est)} credits for ${plural(target.length, "item")} (usually less) of your 20,000 a day.${lastTxt && !done ? ` ${lastTxt}` : ""}</p>
      <div class="adv-ask" hidden></div>
      <p class="small muted adv-st" style="margin:0">${done ? `Reviewed ${done} of ${inv.length}${ADVAT ? ` at ${clock(ADVAT)} · ${fmt(ADVCRED)} credits` : ""}.${fresh.length ? ` ${plural(fresh.length, "item")} not checked yet.` : ""}` : ""}</p>`}
      ${kept.size ? `<p class="small muted adv-kept" style="margin:4px 0 0">${kept.size === done ? "Saved calls" : `${plural(kept.size, "saved call")}`} from ${clock(Math.min(...keptAt))}, kept on this phone until ${clock(Math.min(...keptAt) + ADV_KEEP_H * 36e5)} at no cost. Amounts are ranges: exact sold prices aren't stored. <button type="button" class="linkish adv-forget">Clear saved calls</button></p>` : ""}` : ""}
      ${!inv.length || done ? adv.html(adv.board(list), { roi: S.set.roi, compact: !!opt.compact, img: (x) => { const r = inv.find((y) => advKey(y) === x.key); return r ? img(r.id) : `<span class="ph"></span>`; },
        attrs: (x) => { const r = inv.find((y) => advKey(y) === x.key); return r ? ` data-open="${r.id}" data-g="${r.g}" data-n="${esc(r.n)}"` : ""; } }) : ""}`;
    $$(".adv-tile[data-jump]", el).forEach((b) => { b.onclick = () => { const t = $(`#adv-${b.dataset.jump}`, el); if (t) t.scrollIntoView({ behavior: "smooth", block: "start" }); else if (opt.compact) location.hash = "today"; }; });
    const forget = $(".adv-forget", el);
    if (forget) forget.onclick = () => { try { localStorage.removeItem(AKEY); } catch {} for (const k of [...OWN.keys()]) if (!ADVIN.has(k)) OWN.delete(k); drawAdvisor(el, opt); opt.after && opt.after(); };
    const pair = $(".adv-pair", el);
    if (pair) pair.onclick = () => { SUB.mine = "set"; if (location.hash === "#mine") route(); else location.hash = "mine"; };
    const ask = $(".adv-ask", el), st = $(".adv-st", el), go = $(".adv-go", el), all = $(".adv-all", el);
    // step 1: say what it costs (and warn on a recent repeat or the daily limit); step 2: run only on "Review now"
    const confirm = (items, isFull) => {
      if (!ask || ADVBUSY) return;
      const e = advEstimate(items), recent = isFull && last && Date.now() - last.at < ADV_RECENT_H * 36e5, over = spent + e > ADV_DAY_CAP;
      ask.hidden = false;
      ask.innerHTML = `<div class="panel adv-confirm${recent || over ? " adv-warn" : ""}">
        ${over ? `<b>Today's review limit is reached</b><p class="small" style="margin:4px 0 8px">Holdings reviews on this phone have used ${fmt(spent)} credits today; this one could use up to ${fmt(e)}, past the ${fmt(ADV_DAY_CAP)} a day kept for reviews so Deal checks always have credits. Single cards can still be checked from their Deal check. The limit resets tomorrow.</p>
          <div class="btns"><button type="button" class="btn sm adv-no">OK</button></div>`
        : `<b>${isFull ? `Review ${plural(items.length, "holding")}?` : `Check ${plural(items.length, "unchecked holding")}?`}</b>
          <p class="small" style="margin:4px 0 8px">Uses up to about <b>${fmt(e)} credits</b> (usually less) of your 20,000 a day.${spent ? ` Reviews on this phone today: ${fmt(spent)} credits.` : ""}${recent ? `<br><b>You already reviewed your holdings at ${clock(last.at)}</b> (${fmt(last.cr)} credits). Sold prices change slowly, so another review now will most likely show the same calls.` : ""}</p>
          <div class="btns"><button type="button" class="btn sm primary adv-yes">${recent ? "Review again anyway" : "Review now"} · up to ${fmt(e)} credits</button><button type="button" class="btn sm adv-no">Cancel</button></div>`}</div>`;
      $(".adv-no", ask).onclick = () => { ask.hidden = true; ask.innerHTML = ""; };
      const yes = $(".adv-yes", ask);
      if (yes) yes.onclick = async () => {
        if (ADVBUSY) return;
        yes.disabled = true; if (go) go.disabled = true; if (all) all.disabled = true;
        ask.innerHTML = `<div class="btns"><button type="button" class="btn sm adv-stop">Stop after this item</button></div>`;
        $(".adv-stop", ask).onclick = (ev) => { ADVSTOP = true; ev.target.disabled = true; ev.target.textContent = "Stopping…"; };
        const res = await reviewHoldings(items, (t) => { if (st) st.textContent = t; });
        if (!res.ok) { ask.hidden = true; ask.innerHTML = ""; if (st) st.textContent = res.why; if (go) go.disabled = false; if (all) all.disabled = false; return; }
        if (res.credits) advRecord(res.checked, res.credits, isFull && !res.stopped && !res.cut);
        await advKeep(invRows());
        await drawAdvisor(el, opt); opt.after && opt.after();
        if (res.stopped) { const s2 = $(".adv-st", el); if (s2) s2.textContent += ` Stopped: ${plural(res.stopped, "item")} not checked.`; }
      };
    };
    if (go && conn) go.onclick = () => confirm(target, full);
    if (all) all.onclick = () => confirm(inv, true);
  }
  /* "Sell, grade or keep?" for what the owner holds: today's real sold prices, this page only */
  const OWN = new Map();
  const OWNL = { sell: ["good", "Sell clears your target"], grade: ["good", "Grading looks better"], hold: ["", "Keep for now"], monitor: ["hot", "Monitor"], unclear: ["warn", "Not enough sales"], unknown: ["", "No sold data"] };
  function mineInv(el) {
    const draw = () => {
      advChips();
      const inv = invRows(), on = ledgerOn();
      const moveNote = LS && !on ? `<div class="panel lg-move"><b>Your ledger is ready</b><p class="small muted" style="margin:4px 0 8px">Move these ${S.inv.length} items into it to track what you paid, what you sell and your profit, in your Google Sheet.</p><div class="btns"><button type="button" class="btn primary" id="inv-move">Open Ledger</button></div></div>` : "";
      if (!inv.length) { el.innerHTML = `<div class="empty"><b>Nothing here yet</b>Open any card from Search or Deals and tap ${LS ? "Bought it" : "Add to inventory"}. You'll see what it's worth and your profit every day.</div>`; return; }
      const p = portfolio();
      const rows = inv.map((x, i) => ({ x, i, val: x.each == null ? null : Math.round(x.each * x.qty), cost: (x.cost || 0) * x.qty })).sort((a, b) => (b.val ?? -1) - (a.val ?? -1));
      el.innerHTML = `${valueTiles(p)}
        <section class="sec panel own-box" id="inv-adv"></section>
        <div class="list">${rows.map(({ x, val, cost }) => { const o = OWN.get(x.lid || x.k), L = o ? OWNL[o.label] || OWNL.unknown : null;
          return rowHTML(x, val == null ? `<b class="inv-np">No price yet</b><small class="muted">cost ${money(cost)}</small>` : `<b>${money(val)}</b><small class="${cls(val - cost)}">${cost ? `${signed(val - cost)} est.` : `${x.qty}×`}</small>`,
          `<span class="why">${x.qty}× · ${x.graded ? esc(x.graded) + " · " : x.t === "c" ? esc(x.cond) + " · " : ""}${on && x.book === "Personal" ? "Personal · " : ""}paid ${money(x.cost)} each${val && x.qty ? ` · sells for ${money(Math.round(net(Math.round(val / x.qty), x.t)))} each on ${esc(plat().label)}` : ""}</span>
          <span class="why inv-src">${val == null ? `No price yet: Edge has no value for this ${x.graded ? "grade" : "item"}${x.graded ? ". Tap Sell, grade or keep? or open it in Ledger → Check sold prices to value it for this visit" : ""}.` : `Value: ${esc(x.src)}`}</span>${o ? `<span class="why own-res"><span class="chip ${L[0]}">${L[1]}</span> ${esc(o.text)}</span>` : ""}`); }).join("")}</div>
        <p class="muted small">${on ? "Tap an item for its card. Buys, sales and costs are in Ledger." : "Tap an item to change it."} Market value is before selling costs; unrealized gains and losses are estimates. Realized profit is only from recorded sales (Ledger).${SOLDV.size ? " Sold-price values last for this visit only and aren't saved." : ""}</p>`;
      el.insertAdjacentHTML("afterbegin", moveNote);
      const mv = $("#inv-move", el); if (mv) mv.onclick = () => { SUB.mine = "ledger"; route(); };
      drawAdvisor($("#inv-adv", el), { title: "Sell, grade or keep?", compact: true, after: draw });
    };
    draw();
  }
  // a backup file of everything on this phone: settings, inventory, watchlist, the ledger copy (never the pairing token)
  function saveBackup() {
    const blob = new Blob([JSON.stringify({ app: "dys-edge", v: 1, saved: new Date().toISOString(), data: S, ...(LS ? { ledger: LS.state } : {}) }, null, 1)], { type: "application/json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `dys-edge-backup-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }
  let LMOUNT = null;
  function mineLedger(el) {
    const resume = LEDGER_RESUME, draft = LEDGER_DRAFT; LEDGER_RESUME = LEDGER_DRAFT = null;
    LMOUNT = LG.mount(el, { store: LS, defBook: S.set.ledgerBook || "Business", resume, draft,
      h: { money, signed, esc, img: (id) => img(id, 200), cleanN, localDay, fmtDay, cents, dollars, toast, cls, pct },
      priceOf, conn: ledgerConn, sync: () => { ledgerSoon(); return Promise.resolve(); },
      feeEst: (k, p, t) => { const pl = FEES.sell[k]; if (!pl || !p) return 0; const v = Math.round(p * (1 + S.set.buyerTax / 100)); return Math.round(v - netSale(pl, v)); },
      shipEst: (p, t) => shipOut(p, t, "ebay"), supplies: (t) => t === "s" ? S.set.supSealed : S.set.supCard,
      pick: (f) => { PICK = { list: "ledger", label: "this buy", back: "mine", form: f }; location.hash = "search"; },
      // moving inventory into the ledger never touches the old list: a copy is kept beside it, and S.inv stays as it was
      oldInv: () => S.inv.map((x) => ({ ...x, sn: x.sn || setName(x.g) })),
      archiveOldInv: () => { try { if (!localStorage.getItem("dys-edge-inv-before-ledger")) localStorage.setItem("dys-edge-inv-before-ledger", JSON.stringify({ saved: new Date().toISOString(), inv: S.inv })); return true; } catch { return false; } },
      backup: saveBackup,
      openCard: (id, g, n) => openCard(id, g, n),
      checkSold,
      download: (name, text) => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type: "text/csv" })); a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000); } });
  }
  async function mineWatch(el) {
    if (!S.watch.length) { el.innerHTML = `<div class="empty"><b>No watched cards</b>Open a card and tap Watch price. When the lowest listing or market price hits your number, it shows up on Today.</div>`; return; }
    el.innerHTML = `<p class="muted">Checking prices…</p>`;
    const rows = await Promise.all(S.watch.map(async (w) => {
      const it = (await detail(w.id, w.g, w.n).catch(() => null))?.it;
      const now = it ? Math.min(it.lo || Infinity, it.p || Infinity) : null, hit = now != null && isFinite(now) && now <= w.target;
      const away = now && isFinite(now) ? (now - w.target) / w.target * 100 : null;
      return { hit, away, html: rowHTML(w, `<b class="${hit ? "up" : ""}">${now && isFinite(now) ? money(now) : "—"}</b><small>${hit ? `<span class="chip good">At target</span>` : away != null ? `${away.toFixed(0)}% above ${money(w.target)}` : "no price"}</small>`,
        `<span class="why">${w.from === "deal" ? "Target = max to pay on sold prices. " : ""}${dcChip(w, now && isFinite(now) ? now : 0)}</span>`) };
    }));
    rows.sort((a, b) => b.hit - a.hit || (a.away ?? 1e9) - (b.away ?? 1e9));
    el.innerHTML = `<div class="list">${rows.map((r) => r.html).join("")}</div><p class="muted small">Price shown is the lower of the cheapest listing (any condition) and the market price, not a sale. Deal check runs it against real sold prices and your rules. Tap a card to change its target.</p>`;
    wireDc(el);
  }
  function mineSettings(el) {
    const s = S.set, d = (k) => dollars(s[k]);
    setTimeout(() => { const t = $("#v2-on"); if (t) t.onchange = () => { try { localStorage.setItem("dys-v2", t.checked ? "1" : "0"); } catch {} location.reload(); }; });
    el.innerHTML = `<section class="sec panel"><h2>Layout</h2>
        <label class="toggle"><input type="checkbox" id="v2-on"${V2 ? " checked" : ""}> Big card pictures, grid view and 5 tabs (off = the old layout)</label></section>
      <section class="sec panel"><h2>Graded prices</h2>
        <p class="muted small" style="margin:0">Enter your PokemonPriceTracker API key (the same one saved on GitHub as PPT_API_KEY) to unlock graded sold prices for PSA, CGC, BGS and TAG. The grading board fills in by itself, Find ranks real grading opportunities, and each card shows its graded prices. The key stays on this phone and isn't saved in backup files. For personal use, which your API plan covers.</p>
        <form class="btns" id="pp-f"><input class="field" id="pp-k" type="password" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="PokemonPriceTracker API key" placeholder="${pptKey() ? "Saved ✓" : "PokemonPriceTracker API key"}" style="flex:1;min-width:0"><button class="btn primary" type="submit">Save</button>${pptKey() ? `<button type="button" class="btn ghost danger" id="pp-rm">Remove</button>` : ""}</form>
        <p class="small" id="pp-st" style="margin:0"></p></section>
      <section class="sec panel"><h2>Sold prices (PkmnPrices)</h2>
        <p class="muted small" style="margin:0">The Deal check reads real eBay sold prices from your PkmnPrices plan on demand, through your private relay. Pair this phone once: it makes its own private key, kept on this phone and out of backup files, and shows a pairing code to send to Claude. Results are kept only while the page is open.</p>
        <div class="btns"><button type="button" class="btn primary" id="rl-pair">${pkmnConn()?.device ? "Paired ✓ · pair again" : "Pair this phone"}</button></div>
        <p class="small" id="rl-code" style="margin:0;word-break:break-all"></p>
        <details><summary class="small muted">Or use a relay address and passphrase</summary>
        <form class="form" id="rl-f"><label class="f full">Relay address<input class="field" id="rl-u" type="url" inputmode="url" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="https://…workers.dev" value="${esc(pkmnConn()?.relay || "")}"></label>
          <label class="f full">Passphrase<input class="field" id="rl-p" type="password" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="${pkmnConn() ? "Saved ✓" : "Relay passphrase"}"></label>
          <div class="btns full"><button class="btn primary" type="submit">Save</button></div></form></details>
        ${pkmnConn() ? `<div class="btns"><button class="btn" type="button" id="rl-t">Test</button><button class="btn ghost danger" type="button" id="rl-x">Remove from this phone</button></div>` : ""}
        <p class="small" id="rl-st" style="margin:0"></p></section>
      ${LS ? `<section class="sec panel"><h2>Ledger (Google Sheet)</h2>
        <p class="muted small" style="margin:0">Your buys, sales, expenses and cash are saved on this phone and sent to your Google Sheet, which is the record. It uses the same pairing as sold prices.</p>
        <p class="small" id="lg-st" style="margin:0"></p>
        <div class="form"><label class="f full">New buys go in<select class="select" id="lg-def">${["Business", "Personal"].map((b) => `<option${(s.ledgerBook || "Business") === b ? " selected" : ""}>${b}</option>`).join("")}</select></label></div>
        <div class="btns">${ledgerConn() ? `<button type="button" class="btn" id="lg-now">Sync now</button>` : ""}${LS.state.sheet ? `<a class="btn ghost" href="${esc(LS.state.sheet)}" target="_blank" rel="noopener">Open Sheet ↗</a>` : ""}</div>
        <details><summary class="small muted">Sheet web app address</summary><form class="btns" id="lg-uf"><input class="field" id="lg-u" type="url" inputmode="url" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="https://script.google.com/macros/s/…/exec" value="${esc((() => { try { return localStorage.getItem(LKEY) || ""; } catch { return ""; } })())}" style="flex:1 1 220px"><button class="btn" type="submit">Save</button></form></details></section>` : ""}
      <form class="sec panel" id="st-f"><h2>Your numbers</h2>
      <div class="form"><label class="f full">I usually sell on${platSelect("st-plat", s.platform)}</label>
        <label class="f">Target profit %<input class="field" id="st-roi" type="number" inputmode="numeric" min="0" max="500" value="${s.roi}"></label>
        <label class="f">Default games<select class="select" id="st-game">${Object.entries(GAMES).map(([k, g]) => `<option value="${k}"${k === s.game ? " selected" : ""}>${g[0]}</option>`).join("")}</select></label>
        <label class="f">Cash offers, % of market<input class="field" id="st-cash" type="number" inputmode="numeric" min="0" max="100" value="${s.cash}"></label>
        <label class="f">Trade credit, % of market<input class="field" id="st-trade" type="number" inputmode="numeric" min="0" max="100" value="${s.trade}"></label></div>
      <h3>Shipping you pay</h3>
      <div class="form"><label class="f">Card under $50 $<input class="field" id="st-sc" type="number" inputmode="decimal" step="0.01" value="${d("shipCard")}"></label>
        <label class="f">Card $50+ $<input class="field" id="st-sc50" type="number" inputmode="decimal" step="0.01" value="${d("shipCard50")}"></label>
        <label class="f">Sealed under $100 $<input class="field" id="st-ss" type="number" inputmode="decimal" step="0.01" value="${d("shipSealed")}"></label>
        <label class="f">Sealed $100+ $<input class="field" id="st-ss100" type="number" inputmode="decimal" step="0.01" value="${d("shipSealed100")}"></label>
        <label class="f">Card shipped to you $<input class="field" id="st-bc" type="number" inputmode="decimal" step="0.01" value="${d("buyCard")}"></label>
        <label class="f">Sealed shipped to you $<input class="field" id="st-bs" type="number" inputmode="decimal" step="0.01" value="${d("buySealed")}"></label>
        <label class="f full">Grading: shipping + insurance per card, both ways $<input class="field" id="st-gs" type="number" inputmode="decimal" step="0.01" value="${d("gradeShip")}"></label></div>
      <h3>Deal check costs</h3>
      <div class="form"><label class="f">Buyer's sales tax the marketplace charges fees on %<input class="field" id="st-btax" type="number" inputmode="decimal" step="0.01" min="0" max="20" value="${s.buyerTax}"></label>
        <label class="f">Sales tax you pay when buying %<input class="field" id="st-tin" type="number" inputmode="decimal" step="0.001" min="0" max="20" value="${s.taxIn}"></label>
        <label class="f">Supplies per card $<input class="field" id="st-supc" type="number" inputmode="decimal" step="0.01" value="${d("supCard")}"></label>
        <label class="f">Supplies per sealed item $<input class="field" id="st-sups" type="number" inputmode="decimal" step="0.01" value="${d("supSealed")}"></label>
        <label class="f">Smallest profit worth it $<input class="field" id="st-minp" type="number" inputmode="decimal" step="0.01" value="${d("minProfit")}"></label>
        <label class="f">Most to spend on one purchase, all-in $<input class="field" id="st-lim" type="number" inputmode="decimal" step="1" min="0" value="${d("buyLimit")}"></label>
        <label class="f">Cash to always keep back $<input class="field" id="st-res" type="number" inputmode="decimal" step="1" min="0" value="${d("cashReserve")}"></label>
        <label class="f">Cost of money, % a month<input class="field" id="st-hold" type="number" inputmode="decimal" step="0.1" min="0" max="10" value="${s.holdRate}"></label></div>
      <div class="btns"><button class="btn primary" type="submit">Save</button></div></form>
      <section class="sec panel"><h2>Backup</h2><p class="muted small" style="margin:0">Your inventory, watchlist, trades and settings live on this phone. Save a backup file now and then, or to move them to another device.</p>
        <div class="btns"><button type="button" class="btn" id="bk-save">Save backup file</button><label class="btn" for="bk-load">Restore from file</label><input type="file" id="bk-load" accept="application/json,.json" hidden></div><div id="bk-out"></div></section>
      <section class="sec panel"><h2>Look</h2><div class="btns"><button type="button" class="btn" id="th">${document.documentElement.dataset.theme === "light" ? "Switch to dark" : "Switch to light"}</button></div></section>`;
    const ppStatus = async () => {
      const st = $("#pp-st"); if (!st) return;
      if (!pptKey()) { st.className = "small muted"; st.textContent = "Not set up."; return; }
      st.className = "small muted"; st.textContent = "Checking…";
      const d = await loadGraded();
      if (d) { st.className = "small up"; st.textContent = `Unlocked: graded prices for ${Object.keys(d.c || {}).length.toLocaleString()} cards, updated ${fmtDay(d.u)}.${POP ? ` PSA population for ${Object.keys(POP.c || {}).length.toLocaleString()} cards, updated ${fmtDay(POP.u)}.` : ""}`; return; }
      st.className = "small down";
      st.textContent = { key: "That key doesn't open your graded prices yet. It has to match the key saved on GitHub (PPT_API_KEY_NEW, or PPT_API_KEY if you haven't added a new one). After you add or change it there, they unlock with the next update, within 4 hours.",
        none: "Key saved. Your graded prices aren't published yet; they arrive with the next update (every 4 hours).",
        browser: "This browser can't unlock them. Use Chrome or Safari, up to date." }[GR_ERR] || "Couldn't load your graded prices. Check your connection.";
    };
    $("#pp-f").onsubmit = (e) => {
      e.preventDefault(); const v = $("#pp-k").value.replace(/\s+/g, ""); if (!v) return;
      try { localStorage.setItem(PKEY, v); } catch { toast("This browser won't save it"); return; }
      GR = null; GRP = null; GR_ERR = ""; POP = null; mineSettings(el);
    };
    const rm = $("#pp-rm"); if (rm) rm.onclick = () => { try { localStorage.removeItem(PKEY); } catch {} GR = null; GRP = null; GR_ERR = ""; POP = null; toast("Key removed from this phone"); mineSettings(el); };
    ppStatus();
    $("#rl-f").onsubmit = (e) => {
      e.preventDefault();
      const u = $("#rl-u").value.trim(), pw = $("#rl-p").value.trim() || pkmnConn()?.pass || "";
      if (!/^https:\/\/[^\s/]+/.test(u) || !pw) { $("#rl-st").className = "small down"; $("#rl-st").textContent = "Needs an https address and a passphrase."; return; }
      try { localStorage.setItem(RKEY, JSON.stringify({ relay: u.replace(/\/+$/, ""), pass: pw })); } catch { toast("This browser won't save it"); return; }
      toast("Saved on this phone"); mineSettings(el);
    };
    // pairing: this phone makes a random token and keeps it; only its SHA-256 goes to the relay's EDGE_DEVICE_HASHES
    $("#rl-pair").onclick = async () => {
      const b = crypto.getRandomValues(new Uint8Array(32)), token = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
      const h = [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token)))].map((x) => x.toString(16).padStart(2, "0")).join("");
      try { localStorage.setItem(RKEY, JSON.stringify({ relay: RELAY, pass: token, device: "phone", paired: new Date().toISOString(), hash: h })); } catch { toast("This browser won't save it"); return; }
      mineSettings(el);
      const c = $("#rl-code"); c.className = "small";
      c.innerHTML = `Pairing code for Claude (safe to share: it can't be used to sign in): <b>${h}</b> <button type="button" class="btn sm" id="rl-copy">Copy</button>`;
      $("#rl-copy").onclick = () => navigator.clipboard?.writeText(h).then(() => toast("Copied"), () => {});
    };
    const rt = $("#rl-t"); if (rt) rt.onclick = async () => {
      const c = pkmnConn(), st = $("#rl-st"); st.className = "small muted"; st.textContent = "Testing…";
      try {
        const r = await fetch(`${c.relay.replace(/\/+$/, "")}/v1/cards?tcg_player_id=610516`, { headers: { "X-Edge-Pass": c.pass, Accept: "application/json" } });
        st.className = `small ${r.ok ? "up" : "down"}`; st.textContent = r.ok ? "Connected: PkmnPrices answered (1 credit)." : r.status === 401 ? "The relay refused the passphrase." : `The relay answered HTTP ${r.status}.`;
      } catch { st.className = "small down"; st.textContent = "Couldn't reach the relay."; }
    };
    if (LS) {
      const ls = $("#lg-st"), st0 = LS.state, c = ledgerConn();
      const show = () => { ls.className = `small ${!c ? "muted" : LS.queue || st0.err ? "warn" : "up"}`;
        ls.textContent = !c ? (pkmnConn() ? "Not connected to a Sheet yet. Everything stays on this phone until it is." : "Pair this phone above first; then it can reach your Sheet.")
          : LS.queue ? `${LS.queue} change${LS.queue === 1 ? "" : "s"} waiting${LS.state.err ? ` (${LS.state.err === "offline" ? "no connection" : LS.state.err === "denied" ? "the Sheet doesn't know this phone yet" : LS.state.err})` : ""}.`
          : LS.state.err ? `Last sync failed: ${LS.state.err === "denied" ? "the Sheet doesn't know this phone yet" : LS.state.err}.` : `Connected${LS.state.pulled ? `, synced ${new Date(LS.state.pulled).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}` : ""}.`; };
      show();
      $("#lg-def").onchange = (e) => { S.set.ledgerBook = e.target.value; save(); toast("Saved"); };
      const now = $("#lg-now"); if (now) now.onclick = async () => { ls.className = "small muted"; ls.textContent = "Syncing…"; await ledgerSync(); show(); };
      $("#lg-uf").onsubmit = (e) => {
        e.preventDefault(); const u = $("#lg-u").value.trim();
        if (u && !/^https:\/\/script\.google\.com\/macros\/s\/[\w-]+\/exec$/.test(u)) { ls.className = "small down"; ls.textContent = "That isn't a Google Apps Script web app address (https://script.google.com/macros/s/…/exec)."; return; }
        try { if (u) localStorage.setItem(LKEY, u); else localStorage.removeItem(LKEY); } catch {}
        toast(u ? "Saved on this phone" : "Cleared"); mineSettings(el); ledgerSync().then(() => { if ($("#lg-st")) mineSettings(el); });
      };
    }
    const rx = $("#rl-x"); if (rx) rx.onclick = () => { try { localStorage.removeItem(RKEY); } catch {} toast("Removed from this phone"); mineSettings(el); };
    $("#st-f").onsubmit = (e) => {
      e.preventDefault();
      const n = (id) => Math.max(0, parseFloat($(id).value) || 0);
      Object.assign(S.set, { platform: $("#st-plat").value, roi: n("#st-roi"), game: $("#st-game").value, cash: Math.min(100, n("#st-cash")), trade: Math.min(100, n("#st-trade")),
        shipCard: cents($("#st-sc").value), shipCard50: cents($("#st-sc50").value), shipSealed: cents($("#st-ss").value), shipSealed100: cents($("#st-ss100").value),
        buyCard: cents($("#st-bc").value), buySealed: cents($("#st-bs").value), gradeShip: cents($("#st-gs").value),
        buyerTax: Math.min(20, n("#st-btax")), taxIn: Math.min(20, n("#st-tin")), supCard: cents($("#st-supc").value), supSealed: cents($("#st-sups").value),
        minProfit: cents($("#st-minp").value), holdRate: Math.min(10, n("#st-hold")), buyLimit: cents($("#st-lim").value), cashReserve: cents($("#st-res").value) });
      save(); toast("Settings saved");
    };
    $("#bk-save").onclick = saveBackup;
    $("#bk-load").onchange = async (e) => {
      const file = e.target.files?.[0]; if (!file) return;
      let d; try { d = JSON.parse(await file.text()); } catch { d = null; }
      if (!d || d.app !== "dys-edge" || !d.data) { $("#bk-out").innerHTML = `<p class="down small">That file isn't a DYS Edge backup.</p>`; return; }
      $("#bk-out").innerHTML = `<div class="inline-form"><span>Replace what's on this phone with the backup from ${esc(fmtDay((d.saved || "").slice(0, 10)))} (${(d.data.inv || []).length} inventory items, ${(d.data.watch || []).length} watched)?</span>
        <div class="btns"><button type="button" class="btn primary" id="bk-yes">Replace</button><button type="button" class="btn ghost" id="bk-no">Cancel</button></div></div>`;
      $("#bk-yes").onclick = () => {
        try { localStorage.setItem(KEY, JSON.stringify(d.data)); if (d.ledger && d.ledger.v === 1 && LG) localStorage.setItem("dys-edge-ledger", JSON.stringify(d.ledger)); } catch { $("#bk-out").innerHTML = `<p class="down small">This browser won't save data. Open the app outside private browsing and try again.</p>`; return; }
        S = load(); if (d.ledger && LG) LS = LG.Store(window.localStorage); toast("Backup restored"); route(); ledgerSync();
      };
      $("#bk-no").onclick = () => { $("#bk-out").innerHTML = ""; e.target.value = ""; };
    };
    $("#th").onclick = () => {
      const t = document.documentElement.dataset.theme === "light" ? "dark" : "light";
      document.documentElement.dataset.theme = t; try { localStorage.setItem("dys-theme", t); } catch {}
      mineSettings(el);
    };
  }

  /* ---------- start ---------- */
  (async () => {
    try { [META, FEES] = await Promise.all([getJSON("meta.json"), feesP]); }
    catch { $("#view").innerHTML = `<div class="empty"><b>Couldn't load the market data</b>Check your connection and reopen the app.</div>`; return; }
    $("#asof").textContent = META.updated ? `Prices ${fmtDay(META.updated)}` : "";
    route();
    (window.requestIdleCallback || setTimeout)(() => loadIndex().then(() => (window.requestIdleCallback || setTimeout)(() => searchIndex())).catch(() => {}));   // the search index too, so the first search is quick
    if ("serviceWorker" in navigator && window.isSecureContext) navigator.serviceWorker.register(`${BASE}sw.js`).catch(() => {});
  })();
})();
