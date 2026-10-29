"use strict";
/* DYS Edge: a private buy / sell / trade desk on top of the market site's nightly data
   (TCGplayer market prices, our own price history, eBay Buy It Now listings with their age).
   Holdings, watchlist, trades, lots and settings are kept on this device (with a backup file). */
(() => {
  // the app lives in /edge/ (its own install scope); site files are one folder up
  const BASE = /\/edge\/(index\.html)?$/.test(location.pathname) ? "../" : "";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
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
  const img = (id, size = 200) => `<img src="${IMG(id, size)}" alt="" loading="lazy" decoding="async" data-img>`;
  document.addEventListener("error", (e) => { if (e.target?.matches?.("img[data-img]")) { const d = document.createElement("div"); d.className = "ph"; e.target.replaceWith(d); } }, true);
  const tcgUrl = (id) => `https://www.tcgplayer.com/product/${id}?Language=all`;
  const soldUrl = (n, extra = "") => `https://www.ebay.com/sch/i.html?_nkw=${encodeURIComponent((cleanN(n).replace(/ \(Reverse Holofoil\)$/, "") + " " + extra).trim())}&LH_Sold=1&LH_Complete=1&_sop=13`;
  const COND = [["NM", 1], ["LP", 0.85], ["MP", 0.7], ["HP", 0.55], ["DMG", 0.4]];
  const condX = (c, t) => t === "s" ? 1 : (COND.find((x) => x[0] === c) || COND[0])[1];
  const GAMES = { pokemon: ["Pokémon EN + JP", (k) => k === "pokemon" || k === "pokemon-jp"], en: ["Pokémon", (k) => k === "pokemon"], jp: ["Pokémon Japan", (k) => k === "pokemon-jp"], all: ["All games", () => true] };

  /* ---------- this device's state ---------- */
  const KEY = "dys-edge-v1";
  const DEF = { inv: [], watch: [], trade: { give: [], get: [] }, lot: [], lotExtra: 0, recent: [], board: [], sub: [], glog: [],
    set: { platform: "ebay", roi: 20, shipCard: 100, shipCard50: 500, shipSealed: 800, shipSealed100: 1500, buyCard: 150, buySealed: 600, cash: 70, trade: 85, game: "pokemon",
      gradeShip: 1500, gco: "PSA", gtier: {}, o10: 30, o9: 50, useMyRates: false, boxShip: 4000 } };
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
  const gameOk = (k) => (GAMES[S.set.game] || GAMES.pokemon)[1](k);

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
  const TABS = { today: viewToday, search: viewSearch, deals: viewDeals, grade: viewGrade, tools: viewTools, mine: viewMine };
  let TAB = "today", SUB = { deals: "flip", tools: "flip", mine: "inv", grade: "board" };
  function route() {
    const h = (location.hash || "").slice(1);
    TAB = TABS[h] ? h : "today";
    if (TAB !== "search") PICK = null;
    $$(".tabs a").forEach((a) => a.setAttribute("aria-current", a.dataset.tab === TAB ? "page" : "false"));
    const v = $("#view"); v.innerHTML = ""; window.scrollTo(0, 0);
    TABS[TAB](v).catch((err) => { console.error(err); v.innerHTML = `<div class="empty"><b>Couldn't load the market data</b>Check your connection and reopen the app.</div>`; });
  }
  window.addEventListener("hashchange", route);

  /* ---------- Today ---------- */
  async function viewToday(v) {
    v.innerHTML = `<section class="brief" id="t-brief"><span class="lab">Market brief</span><h1>Loading…</h1></section>
      <section class="sec" id="t-port"></section>
      <section class="sec" id="t-alerts" hidden></section>
      <section class="sec"><div class="sec-head"><h2>Market indices</h2></div><div class="hscroll" id="t-idx"></div></section>
      <section class="sec"><div class="sec-head"><h2>Best flips right now</h2><a class="more" href="#deals">All deals</a></div><div id="t-flips"></div></section>
      <section class="sec"><div class="sec-head"><h2>Biggest moves today</h2></div><div id="t-mv-seg"></div><div id="t-movers"></div></section>
      <section class="sec" id="t-grade" hidden></section>
      <section class="sec" id="t-store" hidden></section>
      <p class="muted small">Market prices are TCGplayer's, updated nightly. Profits use your selling platform, fees and shipping from Mine → Settings.</p>`;
    const [intel, scout, buyer] = await Promise.all([getJSON("intel.json").catch(() => null), getJSON("scout.json").catch(() => null), getJSON("buyer.json").catch(() => null)]);
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
    if (scout) {
      const rows = scout.picks.filter((r) => r.plan === "flip" && gameOk(r.k)).map((r) => ({ r, f: flip(r.p, r.lo, r.t) })).filter((x) => x.f && x.f.pr > 0)
        .sort((a, b) => b.f.pr - a.f.pr).slice(0, 5)
        .map(({ r, f }) => rowHTML(r, `<b class="up">${signed(f.pr)}</b><small class="muted">buy ${money(r.lo)} · ${f.roi.toFixed(0)}%</small>`));
      $("#t-flips").innerHTML = listOrEmpty(rows, `No flips clear your ${S.set.roi}% target today.`);
    } else $("#t-flips").innerHTML = `<div class="empty">Today's deal list builds with the nightly update.</div>`;
    if (buyer && (buyer.fix?.length || buyer.rising?.length)) {
      const fix = buyer.fix || [];
      $("#t-store").hidden = false;
      $("#t-store").innerHTML = `<div class="sec-head"><h2>Your store</h2><a class="more" href="#deals" data-sub="store">See all</a></div>
        ${listOrEmpty(fix.slice(0, 3).map((x) => rowHTML(x, `<b>${money(x.dys)}</b><small class="${x.gap < 0 ? "down" : "up"}">${pct(x.gap, 0)} vs ${money(x.p)}</small>`)), "")}
        <p class="muted small">${fix.length} store price${fix.length === 1 ? "" : "s"} far from market. Tap one to see the numbers.</p>`;
      $('#t-store [data-sub]').onclick = () => { SUB.deals = "store"; };
    }
    await loadIndex();
    drawPortfolio($("#t-port"));
    await loadGraded();
    const gb = S.board.map((x) => { const bp = boardPrices(x); return { x, e: gradeEval(marketOf(x) || 0, bp.p10, bp.p9, bp.p8) }; }).filter((r) => r.e.profit > 0).sort((a, b) => b.e.profit - a.e.profit).slice(0, 3);
    const mine = new Set(S.board.map((x) => String(x.id)));
    if (gb.length < 3 && GR) for (const o of (await opportunities()) || []) { if (gb.length >= 3 || o.e.profit <= 0) break; if (!mine.has(String(o.r[0]))) gb.push({ x: { id: o.r[0], g: o.r[1], n: o.r[2] }, e: o.e }); }
    if (gb.length) { $("#t-grade").hidden = false; $("#t-grade").innerHTML = `<div class="sec-head"><h2>Best to grade</h2><a class="more" href="#grade" id="t-grade-more">${GR ? "All opportunities" : "Grading board"}</a></div>
      <div class="list">${gb.map(({ x, e }) => rowHTML(x, `<b class="up">${signed(Math.round(e.profit))}</b><small class="muted">${e.v[1]}</small>`)).join("")}</div>`;
      $("#t-grade-more").onclick = () => { SUB.grade = GR ? "find" : "board"; }; }
    drawAlerts($("#t-alerts"));
  }
  function portfolio() {
    let value = 0, cost = 0, n = 0;
    for (const x of S.inv) { const m = marketOf(x); value += (m || 0) * condX(x.cond, x.t) * x.qty; cost += (x.cost || 0) * x.qty; n += x.qty; }
    return { value, cost, pl: value - cost, n };
  }
  function drawPortfolio(el) {
    if (!S.inv.length) { el.innerHTML = `<div class="empty"><b>Track what you own</b>Search a card, tap <b style="display:inline;font-size:inherit">Add to inventory</b>, and its value updates here every night.</div>`; return; }
    const p = portfolio();
    el.innerHTML = `<div class="sec-head"><h2>Your inventory</h2><a class="more" href="#mine">Open</a></div>
      <div class="tiles"><div class="tile"><span class="lab">Value</span><b>${money(p.value, true)}</b><small>${p.n} item${p.n === 1 ? "" : "s"}</small></div>
      <div class="tile"><span class="lab">Cost</span><b>${money(p.cost, true)}</b><small>what you paid</small></div>
      <div class="tile"><span class="lab">Profit</span><b class="${cls(p.pl)}">${p.pl >= 0 ? "+" : ""}${money(p.pl, true)}</b><small>${p.cost ? pct(p.pl / p.cost * 100, 0) : "—"}</small></div></div>`;
  }
  async function drawAlerts(el) {
    if (!S.watch.length) return;
    const hits = [];
    for (const w of S.watch) {
      const d = await detail(w.id, w.g, w.n).catch(() => null);
      const it = d?.it; if (!it) continue;
      const now = Math.min(it.lo || Infinity, it.p || Infinity);
      if (isFinite(now) && now <= w.target) hits.push(rowHTML({ ...w, n: it.n }, `<b class="up">${money(now)}</b><small class="muted">target ${money(w.target)}</small>`));
    }
    if (!hits.length) return;
    el.hidden = false;
    el.innerHTML = `<div class="sec-head"><h2>At your price</h2><span class="chip hot">${hits.length}</span></div><div class="list">${hits.join("")}</div>`;
  }

  /* ---------- Search ---------- */
  let LAST_Q = "", S_TYPE = "all";
  async function viewSearch(v) {
    v.innerHTML = `${PICK ? `<div class="pickbar"><span>Tap cards to add to <b>${esc(PICK.label)}</b></span><button type="button" class="btn sm" id="pick-done">Done</button></div>` : ""}
      <div class="searchbox"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></svg>
        <input id="q" class="field" type="search" placeholder="Card name, number or set" autocomplete="off" enterkeyhint="search" aria-label="Search cards and sealed" value="${esc(LAST_Q)}"></div>
      <div id="s-game"></div><div id="s-type"></div><div id="s-res"><p class="muted small">Loading every card and sealed product…</p></div>`;
    if (PICK) $("#pick-done").onclick = () => { const back = PICK.back; PICK = null; location.hash = back; };
    seg($("#s-game"), Object.entries(GAMES).map(([k, g]) => [k, g[0]]), S.set.game, (k) => { S.set.game = k; save(); run(); });
    seg($("#s-type"), [["all", "Everything"], ["c", "Cards"], ["s", "Sealed"]], S_TYPE, (k) => { S_TYPE = k; run(); });
    await loadIndex();
    const q = $("#q");
    const run = () => {
      LAST_Q = q.value; const s = q.value.trim().toLowerCase();
      if (!s) { drawRecent(); return; }
      const toks = s.split(/\s+/), out = [];
      for (let i = 0; i < ROWS.length && out.length < 400; i++) {
        const r = ROWS[i];
        if (S_TYPE !== "all" && r[3] !== S_TYPE) continue;
        if (!gameOk(gameOfSet(r[2]))) continue;
        if (toks.every((t) => HAY[i].includes(t))) out.push(r);
      }
      const first = toks[0];
      out.sort((a, b) => (b[1].toLowerCase().startsWith(first) - a[1].toLowerCase().startsWith(first)) || (b[4] || 0) - (a[4] || 0));
      const rows = out.slice(0, 60).map((r) => rowHTML({ id: r[0], n: r[1], g: r[2] }, `<b>${money(r[4])}</b><small class="muted">${r[3] === "s" ? "sealed" : "card"}</small>`));
      $("#s-res").innerHTML = rows.length ? `<div class="list">${rows.join("")}</div>${out.length > 60 ? `<p class="muted small">Showing the top 60 of ${out.length >= 400 ? "400+" : out.length}. Add a set name or number to narrow it.</p>` : ""}`
        : `<div class="empty"><b>Nothing found</b>Try fewer words, a card number like 199/165, or switch games.</div>`;
    };
    const drawRecent = () => {
      const rows = S.recent.filter((x) => S_TYPE === "all" || x.t === S_TYPE).map((x) => rowHTML(x, `<b>${money(marketOf(x))}</b>`));
      $("#s-res").innerHTML = rows.length ? `<div class="sec"><div class="sec-head"><h2>Recently viewed</h2></div><div class="list">${rows.join("")}</div></div>`
        : `<div class="empty"><b>Look up anything</b>Every Pokémon card and sealed product, with today's market price, lowest listing and price history.</div>`;
    };
    let t; q.addEventListener("input", () => { clearTimeout(t); t = setTimeout(run, 140); });
    run();
    if (!PICK) q.focus({ preventScroll: true });
  }
  function pickAdd(id, g, n) {
    const r = IDX.get(keyOf(id, n)) || IDX.get(String(id));
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
    const [{ it, set }, eb] = await Promise.all([detail(id, g, n), getJSON("ebay.json").catch(() => ({ cards: {} })), loadGraded()]);
    if (!it) { card.innerHTML = `<div class="grab"><span class="lab">Card details</span><button type="button" class="btn sm close">Close</button></div><div class="empty"><b>No price for this one yet</b>It may be too new or not sold recently.</div>`; return; }
    const x = { id: it.id, g, n: it.n, t: it.t, sn: set.n };
    S.recent = [x, ...S.recent.filter((y) => !(y.id === x.id && y.n === x.n))].slice(0, 12); save();
    const p = it.p, lo = it.lo, f = flip(p, lo, it.t), ch = it.ch || {};
    const e = eb.cards?.[it.id], ebAge = e ? daysAgo(e.at) : null;
    const inInv = S.inv.find((y) => y.k === keyOf(it.id, it.n)), watching = S.watch.find((y) => y.k === keyOf(it.id, it.n));
    const no = (it.n.match(/ - ([\w/-]+)/) || [])[1];
    const platRows = Object.entries(FEES.sell).map(([k, pl]) => `<div><span>${k === "none" ? "Sell in person" : `Sell on ${esc(pl.label)}`}</span><span>${p ? money(net(p, it.t, k)) : "—"}</span></div>`).join("");
    card.innerHTML = `<div class="grab"><span class="lab">${esc(gameOfSet(g) === "pokemon-jp" ? "Pokémon Japan" : it.t === "s" ? "Sealed" : "Card")}</span><button type="button" class="btn sm close">Close</button></div>
      <div class="hero">${img(it.id, 1000)}<div style="display:flex;flex-direction:column;gap:6px;min-width:0">
        <h2>${esc(cleanN(it.n))}</h2><span class="muted small">${esc(set.n)}${it.r ? ` · ${esc(it.r)}` : ""}</span>
        <span class="lab" style="margin-top:6px">Market</span><span class="big">${money(p)}</span>
        <div class="chips">${[["1", "1D"], ["7", "7D"], ["30", "30D"], ["90", "90D"], ["a", "All"]].filter(([k]) => ch[k] != null).map(([k, l]) => `<span class="chip ${ch[k] > 0 ? "good" : ch[k] < 0 ? "bad" : ""}">${l} ${pct(ch[k])}</span>`).join("")}</div>
      </div></div>
      <div class="prices"><div class="tile"><span class="lab">Lowest listing</span><b>${money(lo)}</b><small class="${lo && p ? cls(p - lo) : ""}">${lo && p ? `${pct((lo - p) / p * 100, 0)} vs market` : "on TCGplayer"}</small></div>
        <div class="tile"><span class="lab">Max buy</span><b>${money(maxBuy(p, it.t))}</b><small>for ${S.set.roi}% profit</small></div>
        <div class="tile"><span class="lab">Flip now</span><b class="${f ? cls(f.pr) : ""}">${f ? signed(f.pr) : "—"}</b><small>${f ? `${f.roi.toFixed(0)}% buying the lowest` : "no listing"}</small></div></div>
      <section class="sec chart panel"><span class="lab">Price history</span>${chart(it.s, set.dates)}</section>
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
        <button type="button" class="btn primary" id="c-inv">${inInv ? `In inventory (${inInv.qty})` : "Add to inventory"}</button>
        <button type="button" class="btn" id="c-watch">${watching ? `Watching at ${money(watching.target)}` : "Watch price"}</button>
        <button type="button" class="btn" data-add="give">Trade: I give</button><button type="button" class="btn" data-add="get">Trade: I get</button>
        <button type="button" class="btn" data-add="lot">Add to lot offer</button>${it.t === "c" ? `<button type="button" class="btn" id="c-grade">${S.board.some((y) => y.k === keyOf(it.id, it.n)) ? "On grading board" : "Grade it?"}</button>` : ""}</div>
        <div id="c-form"></div></section>
      <section class="sec"><span class="lab">Check elsewhere</span><div class="links">
        <a class="btn sm" href="${tcgUrl(it.id)}" target="_blank" rel="noopener">TCGplayer ↗</a>
        <a class="btn sm" href="${soldUrl(it.n, no || "")}" target="_blank" rel="noopener">eBay sold ↗</a>
        ${it.t === "c" ? `<a class="btn sm" href="${soldUrl(it.n, (no || "") + " PSA 10")}" target="_blank" rel="noopener">PSA 10 sold ↗</a><a class="btn sm" href="https://www.pricecharting.com/search-products?q=${encodeURIComponent(cleanN(it.n))}&type=prices" target="_blank" rel="noopener">All grades ↗</a>` : ""}
        <a class="btn sm" href="${BASE}product.html?id=${it.id}&set=${g}" target="_blank" rel="noopener">Full page ↗</a></div></section>`;
    const form = $("#c-form");
    $("#c-inv").onclick = () => {
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

  /* ---------- Deals ---------- */
  let D_BUDGET = 0, D_MV = { win: "7", min: null, dir: "up" };
  async function viewDeals(v) {
    v.innerHTML = `<div id="d-seg"></div><div id="d-game"></div><div class="filters"><label class="f" style="flex:1">Budget<select class="select" id="d-budget">
        ${[[0, "Any price"], [2500, "Under $25"], [5000, "Under $50"], [10000, "Under $100"], [25000, "Under $250"], [50000, "Under $500"], [100000, "Under $1,000"]].map(([c, l]) => `<option value="${c}"${c === D_BUDGET ? " selected" : ""}>${l}</option>`).join("")}</select></label></div>
      <p class="muted small" id="d-note"></p><div id="d-list"><p class="muted">Loading…</p></div>`;
    const [scout, buyer] = await Promise.all([getJSON("scout.json").catch(() => null), getJSON("buyer.json").catch(() => null)]);
    const draw = async () => {
      const sub = SUB.deals, ok = (r) => gameOk(r.k) && (!D_BUDGET || (r.lo || r.p) <= D_BUDGET);
      const note = $("#d-note"), out = $("#d-list");
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
    seg($("#d-seg"), [["flip", "Flips"], ["ride", "Momentum"], ["dip", "Dips"], ["under", "Under market"], ["movers", "Movers"], ["fall", "Falling"], ["store", "My store"]], SUB.deals, (k) => { SUB.deals = k; draw(); });
    seg($("#d-game"), Object.entries(GAMES).map(([k, g]) => [k, g[0]]), S.set.game, (k) => { S.set.game = k; save(); draw(); });
    $("#d-budget").onchange = (e) => { D_BUDGET = +e.target.value; draw(); };
    draw();
  }
  async function drawMovers(out) {
    const games = { pokemon: ["pokemon", "pokemon-jp"], en: ["pokemon"], jp: ["pokemon-jp"], all: ["all"] }[S.set.game] || ["pokemon"];
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
  const ODDS = { fresh: [55, 35, "Pack fresh"], nm: [30, 50, "Near mint"], lp: [5, 35, "Light play"] };
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
      <div class="links">${GRADE.name ? `<a class="btn sm" href="${soldUrl(GRADE.name, GRADE.no + " PSA 10")}" target="_blank" rel="noopener">PSA 10 sold ↗</a><a class="btn sm" href="${soldUrl(GRADE.name, GRADE.no + " PSA 9")}" target="_blank" rel="noopener">PSA 9 sold ↗</a>` : ""}<a class="btn sm" href="${BASE}centering.html" target="_blank" rel="noopener">Check centering ↗</a></div>
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
  function odds() { const m = S.set.useMyRates ? myRates() : null; return m ? { o10: m.o10, o9: m.o9, mine: true } : { o10: S.set.o10 / 100, o9: Math.min(1 - S.set.o10 / 100, S.set.o9 / 100), mine: false }; }
  function grader() {
    const co = FEES.graders[S.set.gco] ? S.set.gco : "PSA", gr = FEES.graders[co];
    const ti = Math.min(gr.tiers.length - 1, Math.max(0, +(S.set.gtier[co] ?? 0) || 0));
    return { co, gr, ti, tier: gr.tiers[ti], l10: GL[co]?.[0] || "10", l9: GL[co]?.[1] || "9" };
  }
  // expected result of grading one card worth `raw` (market value you give up), from the graded prices you entered
  function gradeEval(raw, p10, p9, p8, shipEach = S.set.gradeShip) {
    const { gr, ti } = grader(), { o10, o9 } = odds(), o8 = Math.max(0, 1 - o10 - o9), pl = plat();
    p9 = p9 || raw; p8 = p8 || Math.round(raw * 0.7);
    const fee = (v) => feeAt(gr, ti, v), out = (v) => netSale(pl, v) - fee(v) - shipEach - raw;
    const k = raw + shipEach + o9 * (fee(p9) - netSale(pl, p9)) + o8 * (fee(p8) - netSale(pl, p8));
    let be10 = 0;
    if (k > 0) {
      const ok = (v) => o10 * (netSale(pl, v) - fee(v)) >= k;
      if (!(o10 > 0) || !ok(1e9)) be10 = Infinity;
      else { let lo = 0, hi = 1e9; for (let i = 0; i < 60; i++) { const m = (lo + hi) / 2; if (ok(m)) hi = m; else lo = m; } be10 = hi; }
    }
    if (!p10) return { be10 };
    const profit = o10 * out(p10) + o9 * out(p9) + o8 * out(p8), nine = out(p9), ten = out(p10);
    const v = profit > raw * 0.15 && nine >= 0 ? ["good", "Safe grade"] : profit > raw * 0.15 ? ["good", "Good odds"] : profit > 0 ? ["meh", "Risky"] : ["bad", "Skip it"];
    const up = gr.upcharge && tierFor(gr, p10) > ti ? gr.tiers[tierFor(gr, p10)] : null;
    return { be10, profit, nine, ten, v, up, grading: o10 * fee(p10) + o9 * fee(p9) + o8 * fee(p8) };
  }
  const tierLabel = (t) => `${t[0]} · ${money(t[1])}${t[2] ? ` · cards up to ${money(t[2], true)}` : ""}${t[3] ? ` · ~${t[3]} days` : ""}`;
  /* Graded sold prices from PokemonPriceTracker, for this phone only (personal use, on the owner's API plan).
     The update job publishes them encrypted; the key comes from the API key entered in Mine → Settings,
     which stays on this phone and out of backup files. */
  const PKEY = "dys-edge-ppt";
  const pptKey = () => { try { return (localStorage.getItem(PKEY) || "").trim(); } catch { return ""; } };
  let GR = null, GRP = null, GR_ERR = "";
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
      GR_ERR = ""; return GR;
    })().catch(() => { GR_ERR ||= "load"; return null; }));
  }
  // one company's graded prices for a card (cents), or null
  function gradedOf(id, co = grader().co) {
    const c = GR?.c?.[id]; if (!c) return null;
    const [k10, k9, k8] = GK[co] || GK.PSA, g = c[1] || {}, a = g[k10], b = g[k9], d = k8 ? g[k8] : null;
    if (!a && !b) return null;
    return { p10: a?.[0] || null, n10: a?.[1] || 0, l10: a?.[3] || null, p9: b?.[0] || null, n9: b?.[1] || 0, p8: d?.[0] || null, at: c[0] };
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
      out.push({ r, gp, e: gradeEval(r[3], gp.p10, gp.p9, gp.p8) });
    }
    return out.sort((a, b) => b.e.profit - a.e.profit);
  }
  function gradedBlock(it, p) {
    const c = GR?.c?.[it.id], g = c?.[1] || {}, have = GNAME.filter(([k]) => g[k]);
    if (!have.length) return `<section class="sec panel"><span class="lab">Graded sold prices</span><p class="muted small" style="margin:0">No graded sales on PokemonPriceTracker for this card yet${GR.c && Object.keys(GR.c).length ? "" : " (they fill in over the next updates)"}.</p></section>`;
    const bp = gradedOf(it.id), { co, l10 } = grader(), e = bp?.p10 ? gradeEval(p, bp.p10, bp.p9, bp.p8) : null;
    return `<section class="sec panel"><span class="lab">Graded sold prices · last 90 days</span>
      <div class="kv">${have.map(([k, l]) => { const v = g[k]; return `<div><span>${l}<br><small class="muted">${v[1]} sold${v[3] ? ` · last ${esc(fmtDay(v[3]))}` : ""}</small></span><span>${money(v[0])}${p ? `<br><small class="muted">${(v[0] / p).toFixed(1)}× raw</small>` : ""}</span></div>`; }).join("")}</div>
      ${e ? `<div class="verdict ${e.v[0]}"><span class="lab">Grade it with ${esc(co)}?</span><b>${e.v[1]} · ${signed(Math.round(e.profit))} expected</b><span class="small muted">If ${esc(l10)}: ${signed(Math.round(e.ten))} · if ${esc(grader().l9)}: ${signed(Math.round(e.nine))}. At your assumptions in the Grade tab.</span></div>` : ""}
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
    const html = `<details class="panel" id="g-asm"><summary><b>Your assumptions</b> <span class="muted small">${esc(co)} ${esc(gr.tiers[ti][0])} · ${Math.round(o.o10 * 100)}% 10s, ${Math.round(o.o9 * 100)}% 9s${o.mine ? " (your results)" : ""} · sell on ${esc(plat().label)}</span></summary>
      <div class="form" style="margin-top:12px"><label class="f">Grading company<select class="select" id="ga-co">${Object.keys(FEES.graders).map((c) => `<option${c === co ? " selected" : ""}>${c}</option>`).join("")}</select></label>
        <label class="f full">Service level<select class="select" id="ga-tier">${gr.tiers.map((t, i) => `<option value="${i}"${i === ti ? " selected" : ""}>${esc(tierLabel(t))}</option>`).join("")}</select></label>
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
    };
    return { html, bind };
  }
  function gradeBoard(el) {
    const draw = () => {
      const a = assumptions(draw), { co, l10, l9 } = grader();
      const rows = S.board.map((x, i) => {
        const raw = marketOf(x) || 0, bp = boardPrices(x), e = gradeEval(raw, bp.p10, bp.p9, bp.p8);
        return { x, i, raw, e, gp: bp.gp, no: (x.n.match(/ - ([\w/-]+)/) || [])[1] || "" };
      }).sort((a, b) => (b.e.profit ?? -1e12) - (a.e.profit ?? -1e12));
      const priced = rows.filter((r) => r.e.profit != null), best = priced.filter((r) => r.e.profit > 0);
      el.innerHTML = `${a.html}
        ${S.board.length ? `<div class="tiles"><div class="tile"><span class="lab">On your board</span><b>${S.board.length}</b><small>${priced.length} with ${esc(co)} prices</small></div>
          <div class="tile"><span class="lab">Worth grading</span><b class="up">${best.length}</b><small>expected profit</small></div>
          <div class="tile"><span class="lab">Safe grades</span><b>${priced.filter((r) => r.e.v[1] === "Safe grade").length}</b><small>a ${esc(l9)} still pays</small></div></div>` : ""}
        <div class="sec-head"><h2>Grading board</h2><button type="button" class="more" id="gb-add">+ Add cards</button></div>
        ${!GR && !pptKey() ? `<p class="muted small" style="margin:0">Add your PokemonPriceTracker key in Mine → Settings and graded prices fill in by themselves.</p>` : ""}
        ${rows.length ? rows.map(({ x, i, raw, e, gp, no }) => `<div class="gcard panel">
          <button type="button" class="gc-top" data-open="${x.id}" data-g="${x.g}" data-n="${esc(x.n)}">${img(x.id)}<span class="gc-name"><span class="nm">${esc(cleanN(x.n))}</span><span class="st">${esc(setName(x.g))} · raw ${money(raw)}</span></span>
            ${e.v ? `<span class="chip ${e.v[0] === "good" ? "good" : e.v[0] === "bad" ? "bad" : "hot"}">${e.v[1]}</span>` : `<span class="chip">Needs prices</span>`}</button>
          <div class="gc-in"><label class="f">${esc(co)} ${esc(l10)} sells for $<input class="field" type="number" inputmode="decimal" min="0" step="0.01" data-b10="${i}" value="${dollars(x.p10)}" placeholder="${gp?.p10 ? dollars(gp.p10) + " (PPT)" : "from sold"}"></label>
            <label class="f">${esc(co)} ${esc(l9)} sells for $<input class="field" type="number" inputmode="decimal" min="0" step="0.01" data-b9="${i}" value="${dollars(x.p9)}" placeholder="${gp?.p9 ? dollars(gp.p9) + " (PPT)" : "blank = raw price"}"></label></div>
          ${gp ? `<p class="muted small" style="margin:0">PokemonPriceTracker, last 90 days: ${esc(l10)} ${gp.p10 ? `${money(gp.p10)} (${gp.n10} sold${gp.l10 ? `, last ${fmtDay(gp.l10)}` : ""})` : "no sales"} · ${esc(l9)} ${gp.p9 ? `${money(gp.p9)} (${gp.n9} sold)` : "no sales"}.${gp.n10 && gp.n10 < 3 ? ` <span class="warn">Only ${gp.n10} sale${gp.n10 === 1 ? "" : "s"}: check the sold links.</span>` : ""} Type a price to use your own.</p>` : GR ? `<p class="muted small" style="margin:0">No ${esc(co)} sales on PokemonPriceTracker for this one yet. Use the sold links.</p>` : ""}
          <div class="links"><a class="btn sm" href="${soldUrl(x.n, no + " " + co + " " + l10)}" target="_blank" rel="noopener">${esc(co)} ${esc(l10)} sold ↗</a><a class="btn sm" href="${soldUrl(x.n, no + " " + co + " " + l9)}" target="_blank" rel="noopener">${esc(co)} ${esc(l9)} sold ↗</a>
            <a class="btn sm" href="https://www.pricecharting.com/search-products?q=${encodeURIComponent(cleanN(x.n))}&type=prices" target="_blank" rel="noopener">All grades ↗</a><a class="btn sm" href="https://www.gemrate.com/" target="_blank" rel="noopener">Gem rate ↗</a></div>
          <div class="kv">${e.profit != null ? `<div><span>Expected profit</span><span class="${cls(e.profit)}">${signed(Math.round(e.profit))}</span></div>
            <div><span>If ${esc(l10)} / if ${esc(l9)}</span><span><span class="up">${signed(Math.round(e.ten))}</span> / <span class="${cls(e.nine)}">${signed(Math.round(e.nine))}</span></span></div>` : ""}
            <div><span>${esc(l10)} needs to sell for</span><span>${beText(e.be10, raw)}</span></div></div>
          ${e.up ? `<p class="muted small" style="margin:0">A ${esc(l10)} here is upcharged to ${esc(e.up[0])} (${money(e.up[1])}); counted.</p>` : ""}
          <div class="btns"><button type="button" class="btn sm" data-log="${i}">Log result</button><button type="button" class="btn sm ghost danger" data-rm="${i}">Remove</button></div></div>`).join("")
          : `<div class="empty"><b>Build your grading board</b>Add cards from <b style="display:inline;font-size:inherit">Find</b> or tap Grade it? on any card. Enter what a 10 and a 9 sell for (tap the sold links), and the board ranks them by expected profit after every fee.</div>`}`;
      a.bind(el);
      $("#gb-add", el).onclick = () => { SUB.grade = "find"; viewGrade($("#view")); };
      el.onchange = (e) => {
        const t = e.target, i10 = t.dataset.b10, i9 = t.dataset.b9;
        if (i10 != null) { S.board[+i10].p10 = cents(t.value) || null; save(); draw(); }
        if (i9 != null) { S.board[+i9].p9 = cents(t.value) || null; save(); draw(); }
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
      <div id="fd-era"></div>${GR ? `<div id="fd-mult"></div><label class="toggle"><input type="checkbox" id="fd-liq"${FIND.liquid ? " checked" : ""}> Liquid only: ${esc(grader().co + " " + grader().l10)} sold 5+ times in 90 days, last sale within 30 days</label>` : ""}<div id="fd-sort"></div><div id="fd-list"></div>`;
    const draw = () => {
      const q = FIND.q.trim().toLowerCase(), onBoard = new Set(S.board.map((x) => x.k));
      let rows = gd.rows.filter((r) => !multi.has(r[0]) && gameOk(r[7]) && (FIND.era === "all" || r[8] === FIND.era) && r[3] >= FIND.min * 100 && (!FIND.max || r[3] <= FIND.max * 100)
        && (!q || (r[2] + " " + setName(r[1])).toLowerCase().includes(q)));
      const sort = FIND.sort || (GR ? "profit" : "price"), { l10 } = grader();
      rows = rows.map((r) => { const gp = GR ? gradedOf(r[0]) : null, ok = solid(gp); return { r, gp: ok ? gp : null, e: gradeEval(r[3], ok ? gp.p10 : null, ok ? gp.p9 : null, ok ? gp.p8 : null) }; });
      if (GR && FIND.mult) rows = rows.filter((x) => x.gp && x.gp.p10 >= FIND.mult * x.r[3]);
      if (GR && FIND.liquid) rows = rows.filter((x) => liquid(x.gp));
      if (sort === "profit" || sort === "mult") rows = rows.filter((x) => x.gp);
      rows.sort(sort === "mult" ? (a, b) => b.gp.p10 / b.r[3] - a.gp.p10 / a.r[3] : sort === "profit" ? (a, b) => b.e.profit - a.e.profit : sort === "easy" ? (a, b) => (a.e.be10 / a.r[3]) - (b.e.be10 / b.r[3]) : (a, b) => b.r[3] - a.r[3]);
      const out = rows.slice(0, 80).map(({ r, gp, e }) => { const k = keyOf(r[0], r[2]), be = e.be10;
        const add = onBoard.has(k) ? `<span class="chip good">On your board</span>` : `<span class="chip" data-addb="${r[0]}|${r[1]}|${esc(r[2])}">+ Add to board</span>`;
        return gp ? rowHTML({ id: r[0], g: r[1], n: r[2] }, `<b class="${cls(e.profit)}">${signed(Math.round(e.profit))}</b><small class="muted">raw ${money(r[3])} · ${esc(l10)} ${money(gp.p10, gp.p10 >= 100000)}</small>`,
            `<span class="why">${vchip(e.v)} <b>${(gp.p10 / r[3]).toFixed(1)}×</b> · ${gp.n10} sold in 90 days${gp.l10 ? `, last ${fmtDay(gp.l10)}` : ""}${gp.p9 ? ` · ${esc(grader().l9)} ${money(gp.p9)}` : ""} ${add}</span>`)
          : rowHTML({ id: r[0], g: r[1], n: r[2] }, `<b>${money(r[3])}</b><small class="muted">${esc(l10)} needs ${!isFinite(be) ? "—" : money(Math.round(be), be >= 100000)}</small>`, `<span class="why">${add}</span>`); });
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
      const per = picked.map((x) => { const raw = marketOf(x) || 0, bp = boardPrices(x); return { x, raw, e: gradeEval(raw, bp.p10, bp.p9, bp.p8, 0) }; });
      const base = picked.length * tier[1], exp = per.reduce((s, r) => s + (r.e.grading ?? tier[1]), 0);
      const profit = per.reduce((s, r) => s + (r.e.profit ?? 0), 0) - box, worst = per.reduce((s, r) => s + (r.e.nine ?? 0), 0) - box;
      const missing = per.filter((r) => r.e.profit == null).length;
      el.innerHTML = `${a.html}<section class="sec panel"><h2>Plan a submission</h2>
        <p class="muted small" style="margin:0">Tick the cards from your board to send together. Shipping and insurance are for the whole box.</p>
        <div class="list">${S.board.length ? S.board.map((x) => { const raw = marketOf(x) || 0, bp = boardPrices(x), e = gradeEval(raw, bp.p10, bp.p9, bp.p8, 0);
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
    const draw = () => { const el = fresh($("#m-body")); ({ inv: mineInv, watch: mineWatch, set: mineSettings }[SUB.mine] || mineInv)(el); };
    seg($("#m-seg"), [["inv", "Inventory"], ["watch", "Watchlist"], ["set", "Settings"]], SUB.mine, (k) => { SUB.mine = k; draw(); });
    draw();
  }
  function mineInv(el) {
    const draw = () => {
      if (!S.inv.length) { el.innerHTML = `<div class="empty"><b>Nothing here yet</b>Open any card from Search or Deals and tap Add to inventory. You'll see what it's worth and your profit every day.</div>`; return; }
      const p = portfolio();
      const rows = S.inv.map((x, i) => ({ x, i, m: marketOf(x) })).map((o) => ({ ...o, val: (o.m || 0) * condX(o.x.cond, o.x.t) * o.x.qty, cost: (o.x.cost || 0) * o.x.qty })).sort((a, b) => b.val - a.val);
      el.innerHTML = `<div class="tiles"><div class="tile"><span class="lab">Value</span><b>${money(p.value, true)}</b><small>${p.n} items</small></div>
        <div class="tile"><span class="lab">Cost</span><b>${money(p.cost, true)}</b><small>paid</small></div>
        <div class="tile"><span class="lab">Profit</span><b class="${cls(p.pl)}">${p.pl >= 0 ? "+" : ""}${money(p.pl, true)}</b><small>${p.cost ? pct(p.pl / p.cost * 100, 0) : "—"}</small></div></div>
        <div class="list">${rows.map(({ x, val, cost }) => rowHTML(x, `<b>${money(Math.round(val))}</b><small class="${cls(val - cost)}">${cost ? signed(Math.round(val - cost)) : `${x.qty}×`}</small>`,
          `<span class="why">${x.qty}× · ${x.t === "c" ? esc(x.cond) + " · " : ""}paid ${money(x.cost)} each${val && x.qty ? ` · sells for ${money(Math.round(net(Math.round(val / x.qty), x.t)))} each on ${esc(plat().label)}` : ""}</span>`)).join("")}</div>
        <p class="muted small">Tap an item to change it. Values use today's market price for its condition.</p>`;
    };
    draw();
  }
  async function mineWatch(el) {
    if (!S.watch.length) { el.innerHTML = `<div class="empty"><b>No watched cards</b>Open a card and tap Watch price. When the lowest listing or market price hits your number, it shows up on Today.</div>`; return; }
    el.innerHTML = `<p class="muted">Checking prices…</p>`;
    const rows = await Promise.all(S.watch.map(async (w) => {
      const it = (await detail(w.id, w.g, w.n).catch(() => null))?.it;
      const now = it ? Math.min(it.lo || Infinity, it.p || Infinity) : null, hit = now != null && isFinite(now) && now <= w.target;
      const away = now && isFinite(now) ? (now - w.target) / w.target * 100 : null;
      return { hit, away, html: rowHTML(w, `<b class="${hit ? "up" : ""}">${now && isFinite(now) ? money(now) : "—"}</b><small>${hit ? `<span class="chip good">At target</span>` : away != null ? `${away.toFixed(0)}% above ${money(w.target)}` : "no price"}</small>`) };
    }));
    rows.sort((a, b) => b.hit - a.hit || (a.away ?? 1e9) - (b.away ?? 1e9));
    el.innerHTML = `<div class="list">${rows.map((r) => r.html).join("")}</div><p class="muted small">Price shown is the lower of the cheapest listing and the market price. Tap a card to change its target.</p>`;
  }
  function mineSettings(el) {
    const s = S.set, d = (k) => dollars(s[k]);
    el.innerHTML = `<section class="sec panel"><h2>Graded prices</h2>
        <p class="muted small" style="margin:0">Enter your PokemonPriceTracker API key (the same one saved on GitHub as PPT_API_KEY) to unlock graded sold prices for PSA, CGC, BGS and TAG. The grading board fills in by itself, Find ranks real grading opportunities, and each card shows its graded prices. The key stays on this phone and isn't saved in backup files. For personal use, which your API plan covers.</p>
        <form class="btns" id="pp-f"><input class="field" id="pp-k" type="password" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="PokemonPriceTracker API key" placeholder="${pptKey() ? "Saved ✓" : "PokemonPriceTracker API key"}" style="flex:1;min-width:0"><button class="btn primary" type="submit">Save</button>${pptKey() ? `<button type="button" class="btn ghost danger" id="pp-rm">Remove</button>` : ""}</form>
        <p class="small" id="pp-st" style="margin:0"></p></section>
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
      <div class="btns"><button class="btn primary" type="submit">Save</button></div></form>
      <section class="sec panel"><h2>Backup</h2><p class="muted small" style="margin:0">Your inventory, watchlist, trades and settings live on this phone. Save a backup file now and then, or to move them to another device.</p>
        <div class="btns"><button type="button" class="btn" id="bk-save">Save backup file</button><label class="btn" for="bk-load">Restore from file</label><input type="file" id="bk-load" accept="application/json,.json" hidden></div><div id="bk-out"></div></section>
      <section class="sec panel"><h2>Look</h2><div class="btns"><button type="button" class="btn" id="th">${document.documentElement.dataset.theme === "light" ? "Switch to dark" : "Switch to light"}</button></div></section>`;
    const ppStatus = async () => {
      const st = $("#pp-st"); if (!st) return;
      if (!pptKey()) { st.className = "small muted"; st.textContent = "Not set up."; return; }
      st.className = "small muted"; st.textContent = "Checking…";
      const d = await loadGraded();
      if (d) { st.className = "small up"; st.textContent = `Unlocked: graded prices for ${Object.keys(d.c || {}).length.toLocaleString()} cards, updated ${fmtDay(d.u)}.`; return; }
      st.className = "small down";
      st.textContent = { key: "That key doesn't open your graded prices. Use the same key that's saved on GitHub as PPT_API_KEY.",
        none: "Key saved. Your graded prices aren't published yet; they arrive with the next update (every 4 hours).",
        browser: "This browser can't unlock them. Use Chrome or Safari, up to date." }[GR_ERR] || "Couldn't load your graded prices. Check your connection.";
    };
    $("#pp-f").onsubmit = (e) => {
      e.preventDefault(); const v = $("#pp-k").value.trim(); if (!v) return;
      try { localStorage.setItem(PKEY, v); } catch { toast("This browser won't save it"); return; }
      GR = null; GRP = null; GR_ERR = ""; mineSettings(el);
    };
    const rm = $("#pp-rm"); if (rm) rm.onclick = () => { try { localStorage.removeItem(PKEY); } catch {} GR = null; GRP = null; GR_ERR = ""; toast("Key removed from this phone"); mineSettings(el); };
    ppStatus();
    $("#st-f").onsubmit = (e) => {
      e.preventDefault();
      const n = (id) => Math.max(0, parseFloat($(id).value) || 0);
      Object.assign(S.set, { platform: $("#st-plat").value, roi: n("#st-roi"), game: $("#st-game").value, cash: Math.min(100, n("#st-cash")), trade: Math.min(100, n("#st-trade")),
        shipCard: cents($("#st-sc").value), shipCard50: cents($("#st-sc50").value), shipSealed: cents($("#st-ss").value), shipSealed100: cents($("#st-ss100").value),
        buyCard: cents($("#st-bc").value), buySealed: cents($("#st-bs").value), gradeShip: cents($("#st-gs").value) });
      save(); toast("Settings saved");
    };
    $("#bk-save").onclick = () => {
      const blob = new Blob([JSON.stringify({ app: "dys-edge", v: 1, saved: new Date().toISOString(), data: S }, null, 1)], { type: "application/json" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `dys-edge-backup-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    };
    $("#bk-load").onchange = async (e) => {
      const file = e.target.files?.[0]; if (!file) return;
      let d; try { d = JSON.parse(await file.text()); } catch { d = null; }
      if (!d || d.app !== "dys-edge" || !d.data) { $("#bk-out").innerHTML = `<p class="down small">That file isn't a DYS Edge backup.</p>`; return; }
      $("#bk-out").innerHTML = `<div class="inline-form"><span>Replace what's on this phone with the backup from ${esc(fmtDay((d.saved || "").slice(0, 10)))} (${(d.data.inv || []).length} inventory items, ${(d.data.watch || []).length} watched)?</span>
        <div class="btns"><button type="button" class="btn primary" id="bk-yes">Replace</button><button type="button" class="btn ghost" id="bk-no">Cancel</button></div></div>`;
      $("#bk-yes").onclick = () => {
        try { localStorage.setItem(KEY, JSON.stringify(d.data)); } catch { $("#bk-out").innerHTML = `<p class="down small">This browser won't save data. Open the app outside private browsing and try again.</p>`; return; }
        S = load(); toast("Backup restored"); route();
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
    (window.requestIdleCallback || setTimeout)(() => loadIndex().catch(() => {}));
    if ("serviceWorker" in navigator && window.isSecureContext) navigator.serviceWorker.register(`${BASE}sw.js`).catch(() => {});
  })();
})();
