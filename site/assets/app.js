/* Drive Your Style Market Insights — shared site script */
(() => {
const STORE = "https://driveyourstyle.net";
const PAGE = document.body.dataset.page;
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const params = new URLSearchParams(location.search);
const cache = {};
const getJSON = (path) => (cache[path] ||= fetch(`data/${path}`, { cache: "no-cache" }).then((r) => {
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}));

const money = (c) => {
  if (c == null) return "—";
  const d = c / 100;
  return d >= 1000 ? "$" + Math.round(d).toLocaleString("en-US") : "$" + d.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};
const tick = (c, span) => { const d = c / 100; return "$" + (span / 100 < 10 ? d.toFixed(2) : Math.round(d).toLocaleString("en-US")); };
const chg = (p) => {
  if (p == null || isNaN(p)) return `<span class="chg flat">—</span>`;
  const cls = p > 0 ? "up" : p < 0 ? "down" : "flat";
  const arrow = p > 0 ? "▲" : p < 0 ? "▼" : "";
  return `<span class="chg ${cls}">${arrow} ${Math.abs(p).toFixed(1)}%</span>`;
};
const img = (id, size = 200) => `https://tcgplayer-cdn.tcgplayer.com/product/${id}_${size === 1000 ? "in_1000x1000" : size + "w"}.jpg`;
const imgTag = (id, cls = "thumb", size = 200) =>
  `<img class="${cls}" src="${img(id, size)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">`;
const prodUrl = (id, gid) => `product.html?id=${id}&set=${gid}`;
const fmtDate = (d) => d ? new Date(d + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—";
const below = (ours, mkt) => ours != null && mkt != null && ours < mkt;
const BELOW = `<span class="badge deal">Below market</span>`;
const WKEY = "dys-watch";
const watchGet = () => { try { return JSON.parse(localStorage.getItem(WKEY) || "[]"); } catch { return []; } };
const watchSet = (list) => { try { localStorage.setItem(WKEY, JSON.stringify(list)); } catch {} };
const WINDOWS = [["7", "7D"], ["30", "30D"], ["90", "90D"], ["365", "1Y"], ["all", "All"]];

/* ---------- theme ---------- */
function getTheme() { try { return localStorage.getItem("dys-theme") || "dark"; } catch { return "dark"; } }
function setTheme(t) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("dys-theme", t); } catch {}
  document.querySelectorAll(".theme-switch button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.t === t));
}
document.documentElement.dataset.theme = getTheme();

/* ---------- shell ---------- */
const SEARCH_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>`;
function shell() {
  const links = [["index", "Overview"], ["sets", "Sets"], ["trends", "Trends"], ["cards", "Cards"], ["compare", "Compare"], ["calendar", "Calendar"], ["watchlist", "Watchlist"], ["about", "About the data"]];
  $("#top").outerHTML = `<header class="top"><div class="wrap">
    <a class="brand" href="index.html"><span class="brand-mark">DYS</span><span>Drive Your Style<small>Market Insights</small></span></a>
    <nav class="nav" id="nav">${links.map(([p, l]) => `<a href="${p}.html"${p === PAGE ? ' aria-current="page"' : ""}>${l}</a>`).join("")}
      <a href="${STORE}" class="nav-shop">Shop the store →</a></nav>
    <div class="top-actions">
      ${PAGE !== "index" ? `<div class="search" data-search>${SEARCH_ICON}<input type="search" placeholder="Search products & cards" aria-label="Search"><div class="results"></div></div>` : ""}
      <a class="shop-btn" href="${STORE}">Shop</a>
      <button class="menu-btn" aria-label="Menu" aria-expanded="false">☰</button>
    </div></div></header>`;
  $("#foot").outerHTML = `<footer><div class="wrap cols">
    <div style="max-width:560px">
      <p><b style="color:var(--ink)">Drive Your Style Market Insights</b> · Beta</p>
      <p>Market prices are recorded nightly from public TCGplayer market data and may lag by a day. For research only, not financial advice. These are not Drive Your Style's prices. Not affiliated with or endorsed by The Pokémon Company, Bandai, or TCGplayer.</p>
      <p id="updated-line"></p>
    </div>
    <div>
      <p><a href="${STORE}">Shop Drive Your Style</a> · <a href="about.html">Where this data comes from</a></p>
      <div class="theme-switch" role="group" aria-label="Theme"><button data-t="dark">Dark</button><button data-t="light">Light</button></div>
    </div></div></footer>`;
  document.querySelectorAll(".theme-switch button").forEach((b) => b.addEventListener("click", () => setTheme(b.dataset.t)));
  setTheme(getTheme());
  const mb = $(".menu-btn");
  mb.addEventListener("click", () => { const o = $("#nav").classList.toggle("open"); mb.setAttribute("aria-expanded", o); });
  getJSON("meta.json").then((m) => { $("#updated-line").textContent = `Prices last updated ${fmtDate(m.updated)}.`; }).catch(() => {});
}

/* ---------- search ---------- */
const ALIASES = [[/elite trainer box/, " etb"], [/booster box/, " bb"], [/ultra[- ]premium collection/, " upc"],
  [/super[- ]premium collection/, " spc"], [/premium collection/, " pc"], [/booster bundle/, " bundle"], [/pokemon center/, " pc etb"]];
const alias = (h) => { h = h.replace(/é/g, "e"); for (const [re, add] of ALIASES) if (re.test(h)) h += add; return h; };
function initSearch(box) {
  const input = $("input", box), out = $(".results", box);
  let rows = null, sel = -1, meta = null;
  const load = async () => { if (!rows) { [rows, meta] = await Promise.all([getJSON("search.json"), getJSON("meta.json")]); } };
  input.addEventListener("focus", load);
  const render = () => {
    const q = input.value.trim().toLowerCase().replace(/é/g, "e");
    if (!rows || q.length < 2) { out.classList.remove("open"); return; }
    const terms = q.split(/\s+/);
    const hits = [];
    for (const r of rows) {
      const hay = alias((r[1] + " " + (meta.groups[r[2]]?.[0] || "")).toLowerCase());
      if (terms.every((t) => hay.includes(t))) { hits.push(r); if (hits.length >= 12) break; }
    }
    sel = -1;
    out.innerHTML = hits.length ? hits.map((r) => `<a href="${prodUrl(r[0], r[2])}">${imgTag(r[0])}
      <span class="name"><b>${esc(r[1])}</b><span>${esc(meta.groups[r[2]]?.[0] || "")} · ${r[3] === "s" ? "Sealed" : "Card"}</span></span>
      <span class="figs" style="margin-left:auto"><b>${money(r[4])}</b></span></a>`).join("")
      : `<div class="empty">No matches for "${esc(input.value)}"</div>`;
    out.classList.add("open");
  };
  input.addEventListener("input", async () => { await load(); render(); });
  input.addEventListener("keydown", (e) => {
    const items = [...out.querySelectorAll("a")];
    if (!items.length) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      sel = (sel + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
      items.forEach((a, i) => a.classList.toggle("active", i === sel));
    } else if (e.key === "Enter") { (items[sel] || items[0]).click(); }
  });
  document.addEventListener("click", (e) => { if (!box.contains(e.target)) out.classList.remove("open"); });
}

/* ---------- reusable pieces ---------- */
function tabs(el, options, value, onChange) {
  el.classList.add("tabs");
  el.innerHTML = options.map(([v, l]) => `<button type="button" data-v="${esc(v)}" aria-pressed="${v === value}">${esc(l)}</button>`).join("");
  el.addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    el.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x === b));
    onChange(b.dataset.v);
  });
}
function startsOn(meta, win) {
  if (!meta.first || win === "all") return "";
  const d = new Date(new Date(meta.first + "T12:00:00Z").getTime() + Number(win) * 864e5).toISOString().slice(0, 10);
  return d > meta.updated ? ` Price tracking began ${fmtDate(meta.first)}, so this view fills in around ${fmtDate(d)}.` : "";
}
function moverRows(list, meta, limit, win) {
  if (!list || !list.length) return `<div class="empty-note">Not enough price history for this view yet.${win ? startsOn(meta, win) : ""}</div>`;
  return list.slice(0, limit).map((r, i) => {
    const [id, name, gid, now, old, p] = r;
    return `<a class="row" href="${prodUrl(id, gid)}"><span class="rank">${i + 1}</span>${imgTag(id)}
      <span class="name"><b>${esc(name)}</b><span>${esc(meta.groups[gid]?.[0] || "")}</span></span>
      <span class="figs"><b>${money(now)}</b>${chg(p)}<span class="muted" style="font-size:12px;display:block">from ${money(old)}</span></span></a>`;
  }).join("");
}
const BAND_TOP = { "5": 2000, "20": 10000 };
function topRows(list, meta, offset) {
  return list.map((r, i) => `<a class="row" href="${prodUrl(r[0], r[2])}"><span class="rank">${offset + i + 1}</span>${imgTag(r[0])}
    <span class="name"><b>${esc(r[1])}</b><span>${esc(meta.groups[r[2]]?.[0] || "")}</span></span>
    <span class="figs"><b>${money(r[3])}</b></span></a>`).join("");
}
function moversPanel(container, { kind, meta, limit = 10, thresholds = false, defaultThr = "5" }) {
  const games = [["all", "All games"], ...meta.games.map((g) => [g.slug, g.label])];
  let game = "all", win = "7", thr = defaultThr;
  container.innerHTML = `<div class="controls"><div data-g></div><div data-w></div>${thresholds ? "<div data-t></div>" : ""}</div>
    <div class="movers"><div class="panel"><h3><span class="chg up">▲</span> Biggest gains</h3><div data-up></div></div>
    <div class="panel"><h3><span class="chg down">▼</span> Biggest drops</h3><div data-down></div></div></div>`;
  const draw = async () => {
    const data = await getJSON(`movers/${kind}-${game}.json`);
    const w = data.windows[win]?.[thr];
    if (!w?.up?.length && !w?.down?.length) {
      // No history for this window yet: show today's most valuable items so the section isn't empty.
      const rows = (await getJSON("search.json"))
        .filter((r) => r[3] === (kind === "sealed" ? "s" : "c") && (game === "all" || meta.groups[r[2]]?.[1] === game) && r[4] >= Number(thr) * 100 && (!thresholds || r[4] < (BAND_TOP[thr] || Infinity)))
        .slice(0, limit)
        .map((r) => [r[0], r[1], r[2], r[4], null, null]);
      $("[data-up]", container).innerHTML = `<div class="empty-note" style="padding-bottom:6px">${startsOn(meta, win).trim() || "Not enough price history for this view yet."} Meanwhile, here are today's highest market prices.</div>` + topRows(rows.slice(0, Math.ceil(limit / 2)), meta, 0);
      $("[data-down]", container).innerHTML = `<div class="empty-note" style="padding-bottom:6px">Highest market prices, continued.</div>` + topRows(rows.slice(Math.ceil(limit / 2)), meta, Math.ceil(limit / 2));
      const band = thresholds ? (BAND_TOP[thr] ? ` · $${thr}–$${BAND_TOP[thr] / 100}` : ` · $${thr}+`) : "";
      container.querySelectorAll(".panel h3").forEach((h, i) => { h.innerHTML = (i ? "Most valuable (cont.)" : "Most valuable today") + band; });
      return;
    }
    container.querySelectorAll(".panel h3").forEach((h, i) => { h.innerHTML = i ? `<span class="chg down">▼</span> Biggest drops` : `<span class="chg up">▲</span> Biggest gains`; });
    $("[data-up]", container).innerHTML = moverRows(w?.up, meta, limit, win);
    $("[data-down]", container).innerHTML = moverRows(w?.down, meta, limit, win);
  };
  tabs($("[data-g]", container), games, game, (v) => { game = v; draw(); });
  tabs($("[data-w]", container), WINDOWS, win, (v) => { win = v; draw(); });
  if (thresholds) tabs($("[data-t]", container), [["5", "$5+"], ["20", "$20+"], ["100", "$100+"]], thr, (v) => { thr = v; draw(); });
  draw();
}
function setsTable(rows, meta, opts = {}) {
  const gl = Object.fromEntries(meta.games.map((g) => [g.slug, g.label]));
  const today = meta.updated;
  return `<div class="table-wrap"><table><thead><tr><th>Set</th><th class="hide-sm">Game</th><th class="hide-sm">Released</th><th class="num hide-sm">Products</th><th class="num">Main sealed</th><th class="num">7D</th></tr></thead><tbody>
    ${rows.map((s) => `<tr><td class="title"><a href="set.html?id=${s.id}">${s.bbId ? imgTag(s.bbId, "") : ""}<span>${esc(s.n)}${s.pub && s.pub > today ? ` <span class="badge up-next">Upcoming</span>` : ""}</span></a></td>
      <td class="hide-sm">${esc(gl[s.k] || s.k)}</td><td class="hide-sm">${s.pub ? fmtDate(s.pub) : "—"}</td><td class="num hide-sm">${s.np}</td><td class="num" title="${esc(s.bbN || "")}">${money(s.bb)}${s.bbN && !/booster box/i.test(s.bbN) ? `<span class="muted" style="display:block;font-size:11px;max-width:160px;overflow:hidden;text-overflow:ellipsis;margin-left:auto">${esc(s.bbN.replace(s.n, "").trim() || s.bbN)}</span>` : ""}</td><td class="num">${chg(s.c7)}</td></tr>`).join("")}
    </tbody></table></div>`;
}

/* ---------- pages ---------- */
async function pageIndex() {
  const meta = await getJSON("meta.json");
  $("#game-chips").innerHTML = meta.games.map((g) => `<a class="chip" href="sets.html?game=${g.slug}">${esc(g.label)} <span class="n">${g.sets} sets</span></a>`).join("")
    + `<a class="chip" href="sets.html">All sets →</a><a class="chip" href="cards.html">Card prices →</a><a class="chip" href="trends.html">Trends →</a>`;
  $("#stats").innerHTML = [
    [meta.sealed.toLocaleString(), "Sealed products tracked"],
    [meta.cards.toLocaleString(), "Cards tracked"],
    [meta.sets.toLocaleString(), "Sets"],
    [fmtDate(meta.updated), "Latest market price"],
  ].map(([v, l]) => `<div class="stat"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
  moversPanel($("#sealed-movers"), { kind: "sealed", meta });
  moversPanel($("#card-movers"), { kind: "cards", meta });

  const stock = await getJSON("stock.json").catch(() => []);
  if (stock.length) {
    $("#stock").innerHTML = stock.slice(0, 10).map((s) => `<a class="card" href="${esc(s.u)}">${imgTag(s.id, "", 1000)}
      <span class="badge">In stock</span>${below(s.p, s.m) ? BELOW : ""}<span class="t">${esc(s.n)}</span>
      <span class="p"><span>Our price <b style="color:var(--ink)">${money(s.p)}</b></span><span>Mkt ${money(s.m)}</span></span></a>`).join("");
  } else {
    $("#stock-block").hidden = true;
  }
  const sets = await getJSON("sets.json");
  const byId = Object.fromEntries(sets.map((s) => [s.id, s]));
  $("#recent").innerHTML = setsTable(meta.recent.map((id) => byId[id]).filter(Boolean), meta);
}

async function pageSets() {
  const [meta, sets] = await Promise.all([getJSON("meta.json"), getJSON("sets.json")]);
  let game = params.get("game") || "all", q = "", sort = "pub";
  const draw = () => {
    let rows = sets.filter((s) => (game === "all" || s.k === game) && (!q || (s.n + " " + s.a).toLowerCase().includes(q)));
    rows = rows.slice().sort((a, b) => sort === "pub" ? (b.pub || "").localeCompare(a.pub || "")
      : sort === "bb" ? (b.bb || 0) - (a.bb || 0)
      : sort === "up" ? (b.c7 ?? -1e9) - (a.c7 ?? -1e9) : (a.c7 ?? 1e9) - (b.c7 ?? 1e9));
    $("#count").textContent = `${rows.length} sets`;
    $("#table").innerHTML = rows.length ? setsTable(rows, meta) : `<div class="panel empty-note">No sets match.</div>`;
  };
  tabs($("#game"), [["all", "All games"], ...meta.games.map((g) => [g.slug, g.label])], game, (v) => { game = v; draw(); });
  $("#q").addEventListener("input", (e) => { q = e.target.value.trim().toLowerCase(); draw(); });
  $("#sort").addEventListener("change", (e) => { sort = e.target.value; draw(); });
  draw();
}

async function pageSet() {
  const id = params.get("id");
  const [meta, set] = await Promise.all([getJSON("meta.json"), getJSON(`set/${id}.json`)]);
  document.title = `${set.n} prices · Drive Your Style Market Insights`;
  const gl = Object.fromEntries(meta.games.map((g) => [g.slug, g.label]));
  $("#crumbs").innerHTML = `<a href="sets.html">Sets</a> / <a href="sets.html?game=${set.k}">${esc(gl[set.k] || set.k)}</a> / ${esc(set.n)}`;
  $("#title").textContent = set.n;
  const sealed = set.items.filter((i) => i.t === "s"), cards = set.items.filter((i) => i.t === "c");
  $("#sub").textContent = `${gl[set.k] || ""} · Released ${fmtDate(set.pub)} · ${sealed.length} sealed · ${cards.length} card prices`;
  const table = (items, isCard, limit) => {
    if (!items.length) return `<div class="panel empty-note">No ${isCard ? "card" : "sealed"} prices for this set yet.</div>`;
    return `<div class="table-wrap"><table><thead><tr><th>${isCard ? "Card" : "Product"}</th>${isCard ? "<th class=\"hide-sm\">Rarity</th>" : ""}<th class="num">Market</th><th class="num">7D</th><th class="num hide-sm">30D</th><th class="num hide-sm">90D</th></tr></thead><tbody>
      ${items.slice(0, limit).map((i) => `<tr><td class="title"><a href="${prodUrl(i.id, set.id)}">${imgTag(i.id, "")}<span>${esc(i.n)}${i.dys ? ` <span class="badge">In stock</span>` : ""}${i.dys && below(i.dys.p, i.p) ? " " + BELOW : ""}</span></a></td>
        ${isCard ? `<td class="hide-sm">${esc(i.r || "")}</td>` : ""}<td class="num"><b>${money(i.p)}</b></td><td class="num">${chg(i.ch?.["7"])}</td><td class="num hide-sm">${chg(i.ch?.["30"])}</td><td class="num hide-sm">${chg(i.ch?.["90"])}</td></tr>`).join("")}
      </tbody></table></div>`;
  };
  const chase = cards.filter((c) => c.p >= 500).slice(0, 10);
  $("#chase-wrap").hidden = !chase.length;
  $("#chase").innerHTML = chase.map((c, i) => `<a class="chase" href="${prodUrl(c.id, set.id)}"><span class="rank">${i + 1}</span>${imgTag(c.id, "", 1000)}
    <span class="t">${esc(c.n)}</span><span class="p"><b>${money(c.p)}</b>${chg(c.ch?.["7"])}</span></a>`).join("");
  $("#sealed").innerHTML = table(sealed, false, 999);
  let lim = 50;
  const drawCards = () => {
    $("#cards").innerHTML = table(cards, true, lim) + (cards.length > lim ? `<p><button class="btn" id="more">Show all ${cards.length} cards</button></p>` : "");
    $("#more")?.addEventListener("click", () => { lim = 1e9; drawCards(); });
  };
  drawCards();
}

async function pageProduct() {
  const id = Number(params.get("id")), gid = params.get("set");
  const [meta, set] = await Promise.all([getJSON("meta.json"), getJSON(`set/${gid}.json`)]);
  const variants = set.items.filter((i) => i.id === id);
  if (!variants.length) { $("#prod").innerHTML = `<p class="empty-note">We don't have a price for this product yet.</p>`; return; }
  let v = variants[0];
  const base = v.n.replace(/ \((Holofoil|Reverse Holofoil|Normal|1st Edition.*?)\)$/, "");
  document.title = `${base} price · Drive Your Style Market Insights`;
  const gl = Object.fromEntries(meta.games.map((g) => [g.slug, g.label]));
  $("#crumbs").innerHTML = `<a href="sets.html">Sets</a> / <a href="set.html?id=${set.id}">${esc(set.n)}</a> / ${esc(base)}`;
  const draw = () => {
    $("#prod").innerHTML = `<div class="prod-img">${imgTag(id, "", 1000)}</div>
      <div><span class="muted">${esc(gl[set.k] || "")} · ${esc(set.n)}${v.no ? " · #" + esc(v.no) : ""}${v.r ? " · " + esc(v.r) : ""}</span>
        <h1 style="font-size:clamp(26px,3.4vw,38px);margin-top:6px">${esc(base)}</h1>
        ${variants.length > 1 ? `<div id="var" style="margin-top:12px"></div>` : ""}
        <div class="muted" style="margin-top:14px">Market price</div><div class="price-big">${money(v.p)}</div>
        ${v.dys && below(v.dys.p, v.p) ? `<p style="margin:6px 0 0">${BELOW} <span class="muted">Our price ${money(v.dys.p)} is ${Math.round((1 - v.dys.p / v.p) * 100)}% under market</span></p>` : ""}
        <div class="kpis">${[["7", "7 days"], ["30", "30 days"], ["90", "90 days"]].map(([k, l]) => `<div class="kpi"><div class="l">${l}</div>${chg(v.ch?.[k])}</div>`).join("")}</div>
        <div class="btns">${v.dys ? `<a class="btn primary" href="${esc(v.dys.u)}">In stock at Drive Your Style · ${money(v.dys.p)}</a>` : `<a class="btn primary" href="${STORE}">Shop Drive Your Style</a>`}
          <a class="btn" href="https://www.tcgplayer.com/product/${id}" target="_blank" rel="noopener">View on TCGplayer ↗</a>
          <a class="btn" href="compare.html?a=${id}:${set.id}">Compare ⇄</a>
          <button class="btn" id="watch" type="button"></button></div>
        <div class="chart-card"><div class="chart-head"><b>Price history</b><div id="range"></div></div><div class="chart" id="chart"></div>
          <p class="muted" style="font-size:12px;margin:6px 0 4px">Nightly TCGplayer market price. Gaps mean no market price was recorded that day.</p></div>
      </div>`;
    const key = `${id}:${set.id}`;
    const paint = () => { const on = watchGet().some((w) => w.k === key); const b = $("#watch"); b.textContent = on ? "★ Watching" : "☆ Watch"; b.setAttribute("aria-pressed", on); };
    $("#watch").addEventListener("click", () => {
      let list = watchGet();
      list = list.some((w) => w.k === key) ? list.filter((w) => w.k !== key) : [...list, { k: key, id, g: set.id, n: base, at: v.p, d: meta.updated }];
      watchSet(list); paint();
    });
    paint();
    if (variants.length > 1) tabs($("#var"), variants.map((x, i) => [String(i), (x.n.match(/\(([^)]+)\)$/) || [, "Normal"])[1]]), String(variants.indexOf(v)), (i) => { v = variants[+i]; draw(); });
    let range = "365";
    const plot = () => lineChart($("#chart"), set.dates, v.s || [], range);
    tabs($("#range"), [["30", "1M"], ["90", "3M"], ["180", "6M"], ["365", "1Y"]], range, (r) => { range = r; plot(); });
    plot();
  };
  draw();
}

function lineChart(el, dates, values, rangeDays) {
  const end = dates[dates.length - 1];
  const cutoff = new Date(new Date(end + "T00:00:00Z") - rangeDays * 864e5).toISOString().slice(0, 10);
  const pts = dates.map((d, i) => ({ d, v: values[i] })).filter((p) => p.d >= cutoff && p.v != null);
  if (pts.length < 2) { el.innerHTML = `<div class="empty-note">Not enough history yet. Check back in a few days.</div>`; return; }
  const W = el.clientWidth || 600, H = el.clientHeight || 280, L = 56, R = 12, T = 12, B = 28;
  const t0 = Date.parse(pts[0].d), t1 = Date.parse(pts[pts.length - 1].d);
  let lo = Math.min(...pts.map((p) => p.v)), hi = Math.max(...pts.map((p) => p.v));
  const pad = (hi - lo) * 0.12 || hi * 0.05 || 100; lo = Math.max(0, lo - pad); hi += pad;
  const x = (d) => L + (Date.parse(d) - t0) / (t1 - t0 || 1) * (W - L - R);
  const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const ticks = 4, grid = [];
  for (let i = 0; i <= ticks; i++) {
    const v = lo + (hi - lo) * i / ticks;
    grid.push(`<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)" stroke-width="1"/>
      <text x="${L - 8}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="var(--ink-3)">${tick(v, hi - lo)}</text>`);
  }
  const xl = [pts[0], pts[Math.floor(pts.length / 2)], pts[pts.length - 1]].map((p, i) =>
    `<text x="${x(p.d)}" y="${H - 8}" text-anchor="${["start", "middle", "end"][i]}" font-size="11" fill="var(--ink-3)">${new Date(p.d + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })}</text>`);
  const path = pts.map((p, i) => `${i ? "L" : "M"}${x(p.d).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
  const area = `${path}L${x(pts[pts.length - 1].d).toFixed(1)},${H - B}L${x(pts[0].d).toFixed(1)},${H - B}Z`;
  const rising = pts[pts.length - 1].v >= pts[0].v;
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Price history line chart">
    <defs><linearGradient id="fillg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="var(--accent)" stop-opacity=".22"/><stop offset="1" stop-color="var(--accent)" stop-opacity="0"/></linearGradient></defs>
    ${grid.join("")}${xl.join("")}
    <path d="${area}" fill="url(#fillg)"/><path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
    <line class="xh" y1="${T}" y2="${H - B}" stroke="var(--line-strong)" stroke-width="1" visibility="hidden"/>
    <circle class="dot" r="5" fill="var(--accent)" stroke="var(--surface)" stroke-width="2" visibility="hidden"/>
    <rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" fill="transparent" class="hit"/></svg><div class="tip"></div>`;
  el.setAttribute("title", rising ? "Price is up over this range" : "Price is down over this range");
  const svg = $("svg", el), tip = $(".tip", el), xh = $(".xh", el), dot = $(".dot", el);
  const move = (ev) => {
    const r = svg.getBoundingClientRect();
    const px = ((ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left) * (W / r.width);
    let best = pts[0];
    for (const p of pts) if (Math.abs(x(p.d) - px) < Math.abs(x(best.d) - px)) best = p;
    const cx = x(best.d), cy = y(best.v);
    xh.setAttribute("x1", cx); xh.setAttribute("x2", cx); xh.setAttribute("visibility", "visible");
    dot.setAttribute("cx", cx); dot.setAttribute("cy", cy); dot.setAttribute("visibility", "visible");
    tip.style.display = "block"; tip.style.left = (cx / W * r.width) + "px"; tip.style.top = (cy / H * r.height) + "px";
    tip.innerHTML = `<b>${money(best.v)}</b> <span class="muted">${fmtDate(best.d)}</span>`;
  };
  const leave = () => { tip.style.display = "none"; xh.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); };
  const hit = $(".hit", el);
  hit.addEventListener("mousemove", move); hit.addEventListener("touchmove", move, { passive: true });
  hit.addEventListener("mouseleave", leave); hit.addEventListener("touchend", leave);
}

async function pageTrends() {
  const meta = await getJSON("meta.json");
  moversPanel($("#sealed"), { kind: "sealed", meta, limit: 50, thresholds: true, defaultThr: "20" });
}

async function pageCards() {
  const [meta, sets] = await Promise.all([getJSON("meta.json"), getJSON("sets.json")]);
  const gl = Object.fromEntries(meta.games.map((g) => [g.slug, g.label]));
  let game = "all", setId = "", win = "7", recent = false;
  const yearAgo = new Date(new Date(meta.updated) - 365 * 864e5).toISOString().slice(0, 10);
  const pubOf = Object.fromEntries(sets.map((x) => [x.id, x.pub]));
  const setSel = $("#set");
  const fillSets = () => {
    const list = sets.filter((s) => (game === "all" || s.k === game) && (!recent || s.pub >= yearAgo) && s.pub <= meta.updated);
    setSel.innerHTML = `<option value="">All sets</option>` + list.map((s) => `<option value="${s.id}">${esc(s.n)} (${esc(gl[s.k] || "")})</option>`).join("");
    if (setId && !list.some((s) => String(s.id) === setId)) setId = "";
    setSel.value = setId;
  };
  const draw = async () => {
    const up = $("[data-up]"), down = $("[data-down]");
    if (setId) {
      const set = await getJSON(`set/${setId}.json`);
      const w = win === "365" || win === "all" ? "90" : win;
      const rows = set.items.filter((i) => i.t === "c" && i.p >= 500 && i.ch?.[w] != null)
        .map((i) => [i.id, i.n, set.id, i.p, Math.round(i.p / (1 + i.ch[w] / 100)), i.ch[w]]);
      if (!rows.length) {  // no history yet: show the set's most valuable cards
        const top = set.items.filter((i) => i.t === "c" && i.p >= 500).sort((a, b) => b.p - a.p).slice(0, 50).map((i) => [i.id, i.n, set.id, i.p]);
        showTop(top, `${startsOn(meta, win).trim() || "Not enough price history for this view yet."} Meanwhile, here are this set's most valuable cards.`);
        return;
      }
      setHeads(false);
      up.innerHTML = moverRows(rows.filter((r) => r[5] > 0).sort((a, b) => b[5] - a[5]), meta, 25);
      down.innerHTML = moverRows(rows.filter((r) => r[5] < 0).sort((a, b) => a[5] - b[5]), meta, 25);
      $("#note").textContent = win !== w ? "Single-set view goes back 90 days." : "";
      return;
    }
    $("#note").textContent = recent ? "Showing cards from sets released in the last 12 months." : "";
    const data = await getJSON(`movers/cards-${game}.json`);
    const w = data.windows[win]?.["5"] || {};
    const keep = (r) => !recent || (pubOf[r[2]] || "") >= yearAgo;
    if (!w.up?.length && !w.down?.length) {  // no history yet: most valuable cards today
      const top = (await getJSON("search.json"))
        .filter((r) => r[3] === "c" && r[4] >= 500 && (game === "all" || meta.groups[r[2]]?.[1] === game) && keep(r))
        .slice(0, 50).map((r) => [r[0], r[1], r[2], r[4]]);
      showTop(top, `${startsOn(meta, win).trim() || "Not enough price history for this view yet."} Meanwhile, here are today's most valuable cards${recent ? " from the last 12 months" : ""}.`);
      return;
    }
    setHeads(false);
    up.innerHTML = moverRows((w.up || []).filter(keep), meta, 25, win);
    down.innerHTML = moverRows((w.down || []).filter(keep), meta, 25, win);
  };
  const setHeads = (fallback) => document.querySelectorAll(".movers .panel h3").forEach((h, i) => {
    h.innerHTML = fallback ? (i ? "Most valuable (cont.)" : "Most valuable today") : (i ? `<span class="chg down">▼</span> Biggest drops` : `<span class="chg up">▲</span> Biggest gains`);
  });
  const showTop = (rows, note) => {
    setHeads(true);
    const half = Math.ceil(rows.length / 2);
    $("[data-up]").innerHTML = rows.length ? `<div class="empty-note" style="padding-bottom:6px">${note}</div>` + topRows(rows.slice(0, half), meta, 0) : `<div class="empty-note">No cards over $5 match these filters yet.</div>`;
    $("[data-down]").innerHTML = rows.length > half ? topRows(rows.slice(half), meta, half) : `<div class="empty-note">—</div>`;
    $("#note").textContent = "";
  };
  tabs($("#game"), [["all", "All games"], ...meta.games.map((g) => [g.slug, g.label])], game, (v) => { game = v; fillSets(); draw(); });
  tabs($("#win"), WINDOWS, win, (v) => { win = v; draw(); });
  setSel.addEventListener("change", () => { setId = setSel.value; draw(); });
  $("#recent").addEventListener("change", (e) => { recent = e.target.checked; fillSets(); draw(); });
  fillSets(); draw();
}


/* ---------- compare ---------- */
function picker(box, onPick) {
  const input = $("input", box), out = $(".results", box);
  let rows = null, meta = null;
  const load = async () => { if (!rows) [rows, meta] = await Promise.all([getJSON("search.json"), getJSON("meta.json")]); };
  input.addEventListener("focus", load);
  input.addEventListener("input", async () => {
    await load();
    const q = input.value.trim().toLowerCase().replace(/é/g, "e");
    if (q.length < 2) { out.classList.remove("open"); return; }
    const terms = q.split(/\s+/), hits = [];
    for (const r of rows) {
      const hay = alias((r[1] + " " + (meta.groups[r[2]]?.[0] || "")).toLowerCase());
      if (terms.every((t) => hay.includes(t))) { hits.push(r); if (hits.length >= 10) break; }
    }
    out.innerHTML = hits.length ? hits.map((r) => `<a href="#" data-id="${r[0]}" data-g="${r[2]}">${imgTag(r[0])}
      <span class="name"><b>${esc(r[1])}</b><span>${esc(meta.groups[r[2]]?.[0] || "")}</span></span><span class="figs" style="margin-left:auto"><b>${money(r[4])}</b></span></a>`).join("")
      : `<div class="empty">No matches</div>`;
    out.classList.add("open");
  });
  out.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-id]"); if (!a) return;
    e.preventDefault(); out.classList.remove("open"); input.value = "";
    onPick(Number(a.dataset.id), a.dataset.g);
  });
  document.addEventListener("click", (e) => { if (!box.contains(e.target)) out.classList.remove("open"); });
}

async function pageCompare() {
  const meta = await getJSON("meta.json");
  const gl = Object.fromEntries(meta.games.map((g) => [g.slug, g.label]));
  const parse = (v) => { const [id, g] = (v || "").split(":"); return id && g ? { id: Number(id), g } : null; };
  const picks = [parse(params.get("a")), parse(params.get("b"))];
  const COLORS = ["var(--accent)", "var(--accent-2)"];
  let range = "90";
  const sync = () => {
    const u = new URL(location.href);
    ["a", "b"].forEach((k, i) => picks[i] ? u.searchParams.set(k, `${picks[i].id}:${picks[i].g}`) : u.searchParams.delete(k));
    history.replaceState(null, "", u);
  };
  const load = async (p) => {
    if (!p) return null;
    const set = await getJSON(`set/${p.g}.json`).catch(() => null);
    const item = set?.items.find((i) => i.id === p.id);
    return item ? { set, item } : null;
  };
  const draw = async () => {
    const data = await Promise.all(picks.map(load));
    $("#slots").innerHTML = data.map((d, i) => d ? `<div class="panel" style="padding:16px;display:flex;gap:14px;align-items:center">
        <span style="width:12px;height:12px;border-radius:3px;background:${COLORS[i]};flex:0 0 12px"></span>
        ${imgTag(d.item.id, "thumb")}
        <div class="name" style="flex:1"><b><a href="${prodUrl(d.item.id, d.set.id)}">${esc(d.item.n)}</a></b><span>${esc(gl[d.set.k] || "")} · ${esc(d.set.n)}</span></div>
        <div class="figs"><b>${money(d.item.p)}</b>${chg(d.item.ch?.["7"])}</div>
        <button class="btn" data-clear="${i}" aria-label="Remove" style="padding:6px 10px">✕</button></div>`
      : `<div class="panel" style="padding:16px"><div class="muted" style="font-size:13px;margin-bottom:8px">Product ${i + 1}</div>
        <div class="search" data-pick="${i}">${SEARCH_ICON}<input type="search" placeholder="Search a product or card" autocomplete="off"><div class="results"></div></div></div>`).join("");
    document.querySelectorAll("[data-pick]").forEach((box) => picker(box, (id, g) => { picks[Number(box.dataset.pick)] = { id, g }; sync(); draw(); }));
    document.querySelectorAll("[data-clear]").forEach((b) => b.addEventListener("click", () => { picks[Number(b.dataset.clear)] = null; sync(); draw(); }));
    const ready = data.filter(Boolean);
    if (ready.length < 2) {
      $("#result").innerHTML = `<div class="panel empty-note">Pick two products to compare their prices and history.</div>`;
      return;
    }
    const rows = [["Market price", (d) => `<b>${money(d.item.p)}</b>`], ["7 days", (d) => chg(d.item.ch?.["7"])], ["30 days", (d) => chg(d.item.ch?.["30"])], ["90 days", (d) => chg(d.item.ch?.["90"])],
      ["Set", (d) => esc(d.set.n)], ["Released", (d) => fmtDate(d.set.pub)], ["Type", (d) => d.item.t === "s" ? "Sealed" : "Card"],
      ["At Drive Your Style", (d) => d.item.dys ? `<a class="more" href="${esc(d.item.dys.u)}">In stock · ${money(d.item.dys.p)}</a>` : `<span class="muted">—</span>`]];
    $("#result").innerHTML = `<div class="table-wrap"><table class="cmp"><thead><tr><th></th>${ready.map((d, i) => `<th class="num"><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:${COLORS[i]};margin-right:6px"></span>${esc(d.item.n.length > 28 ? d.item.n.slice(0, 27) + "…" : d.item.n)}</th>`).join("")}</tr></thead>
      <tbody>${rows.map(([l, f]) => `<tr><td class="muted">${l}</td>${ready.map((d) => `<td class="num">${f(d)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
      <div class="chart-card" style="margin-top:16px"><div class="chart-head"><b>Price change (%) over time</b><div id="range"></div></div>
      <div class="legend" style="display:flex;gap:16px;flex-wrap:wrap;font-size:13px;margin:0 0 6px">${ready.map((d, i) => `<span style="display:inline-flex;align-items:center;gap:6px"><span style="width:14px;height:3px;border-radius:2px;background:${COLORS[i]}"></span>${esc(d.item.n)}</span>`).join("")}</div>
      <div class="chart" id="chart"></div><p class="muted" style="font-size:12px;margin:6px 0 4px">Both lines start at 0% on the first day both have a price, so products at different prices can be compared.</p></div>`;
    const plot = () => compareChart($("#chart"), ready.map((d, i) => ({ dates: d.set.dates, values: d.item.s || [], color: COLORS[i], name: d.item.n })), Number(range));
    tabs($("#range"), [["30", "1M"], ["90", "3M"], ["180", "6M"], ["365", "1Y"]], range, (r) => { range = r; plot(); });
    plot();
  };
  draw();
}

function compareChart(el, series, rangeDays) {
  const allDates = [...new Set(series.flatMap((s) => s.dates))].sort();
  const end = allDates[allDates.length - 1];
  const cutoff = new Date(new Date(end + "T00:00:00Z") - rangeDays * 864e5).toISOString().slice(0, 10);
  const maps = series.map((s) => new Map(s.dates.map((d, i) => [d, s.values[i]]).filter(([d, v]) => v != null && d >= cutoff)));
  const common = allDates.filter((d) => d >= cutoff && maps.every((m) => m.has(d)));
  if (common.length < 2) { el.innerHTML = `<div class="empty-note">Not enough shared price history yet. Check back in a few days.</div>`; return; }
  const base = maps.map((m) => m.get(common[0]));
  const lines = maps.map((m, i) => common.map((d) => ({ d, v: (m.get(d) / base[i] - 1) * 100, p: m.get(d) })));
  const W = el.clientWidth || 600, H = el.clientHeight || 280, L = 52, R = 12, T = 12, B = 28;
  const t0 = Date.parse(common[0]), t1 = Date.parse(common[common.length - 1]);
  let lo = Math.min(0, ...lines.flat().map((p) => p.v)), hi = Math.max(0, ...lines.flat().map((p) => p.v));
  const pad = (hi - lo) * 0.12 || 2; lo -= pad; hi += pad;
  const x = (d) => L + (Date.parse(d) - t0) / (t1 - t0 || 1) * (W - L - R);
  const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  let grid = "";
  for (let i = 0; i <= 4; i++) { const v = lo + (hi - lo) * i / 4; grid += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="var(--ink-3)">${v > 0 ? "+" : ""}${v.toFixed(0)}%</text>`; }
  grid += `<line x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}" stroke="var(--line-strong)"/>`;
  const xl = [common[0], common[Math.floor(common.length / 2)], common[common.length - 1]].map((d, i) => `<text x="${x(d)}" y="${H - 8}" text-anchor="${["start", "middle", "end"][i]}" font-size="11" fill="var(--ink-3)">${new Date(d + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })}</text>`).join("");
  const paths = lines.map((ln, i) => `<path d="${ln.map((p, j) => `${j ? "L" : "M"}${x(p.d).toFixed(1)},${y(p.v).toFixed(1)}`).join("")}" fill="none" stroke="${series[i].color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`).join("");
  const dots = series.map((s, i) => `<circle class="dot${i}" r="5" fill="${s.color}" stroke="var(--surface)" stroke-width="2" visibility="hidden"/>`).join("");
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Price change comparison chart">${grid}${xl}${paths}
    <line class="xh" y1="${T}" y2="${H - B}" stroke="var(--line-strong)" visibility="hidden"/>${dots}
    <rect class="hit" x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" fill="transparent"/></svg><div class="tip"></div>`;
  const svg = $("svg", el), tip = $(".tip", el), xh = $(".xh", el), hit = $(".hit", el);
  const move = (ev) => {
    const r = svg.getBoundingClientRect();
    const px = ((ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left) * (W / r.width);
    let j = 0; common.forEach((d, k) => { if (Math.abs(x(d) - px) < Math.abs(x(common[j]) - px)) j = k; });
    const cx = x(common[j]);
    xh.setAttribute("x1", cx); xh.setAttribute("x2", cx); xh.setAttribute("visibility", "visible");
    lines.forEach((ln, i) => { const c = $(".dot" + i, el); c.setAttribute("cx", cx); c.setAttribute("cy", y(ln[j].v)); c.setAttribute("visibility", "visible"); });
    tip.style.display = "block"; tip.style.left = (cx / W * r.width) + "px"; tip.style.top = (Math.min(...lines.map((ln) => y(ln[j].v))) / H * r.height) + "px";
    tip.innerHTML = `<div class="muted" style="font-size:12px">${fmtDate(common[j])}</div>` + lines.map((ln, i) => `<div><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${series[i].color};margin-right:6px"></span>${money(ln[j].p)} <span class="muted">(${ln[j].v >= 0 ? "+" : ""}${ln[j].v.toFixed(1)}%)</span></div>`).join("");
  };
  const leave = () => { tip.style.display = "none"; xh.setAttribute("visibility", "hidden"); lines.forEach((_, i) => $(".dot" + i, el).setAttribute("visibility", "hidden")); };
  hit.addEventListener("mousemove", move); hit.addEventListener("touchmove", move, { passive: true });
  hit.addEventListener("mouseleave", leave); hit.addEventListener("touchend", leave);
}

async function pageCalendar() {
  const [meta, sets] = await Promise.all([getJSON("meta.json"), getJSON("sets.json")]);
  const gl = Object.fromEntries(meta.games.map((g) => [g.slug, g.label]));
  const today = meta.updated;
  const back = new Date(today + "T12:00:00"); back.setDate(back.getDate() - 90);
  const from = back.toISOString().slice(0, 10);
  let game = params.get("game") || "all";
  const draw = () => {
    const rows = sets.filter((s) => s.pub && s.pub >= from && (game === "all" || s.k === game))
      .sort((a, b) => a.pub.localeCompare(b.pub) || a.n.localeCompare(b.n));
    const up = rows.filter((s) => s.pub > today), past = rows.filter((s) => s.pub <= today).reverse();
    const month = (d) => new Date(d + "T12:00:00").toLocaleDateString("en-US", { month: "long", year: "numeric" });
    const group = (list) => {
      const out = []; let cur = null;
      for (const s of list) { const m = month(s.pub); if (m !== cur) { cur = m; out.push([m, []]); } out[out.length - 1][1].push(s); }
      return out.map(([m, items]) => `<h3 class="cal-month">${esc(m)}</h3><div class="cal-list">${items.map((s) => {
        const d = new Date(s.pub + "T12:00:00");
        return `<a class="cal-item" href="set.html?id=${s.id}"><div class="cal-date"><b>${d.getDate()}</b><span>${d.toLocaleDateString("en-US", { month: "short" })}</span></div>
          ${s.bbId ? imgTag(s.bbId, "cal-img") : `<span class="cal-img"></span>`}
          <div class="cal-body"><div class="cal-name">${esc(s.n)}${s.pub > today ? ` <span class="badge up-next">Upcoming</span>` : ""}</div>
          <div class="muted cal-meta">${esc(gl[s.k] || s.k)}${s.np ? ` · ${s.np} products` : ""}${s.bb ? ` · ${esc(/booster box/i.test(s.bbN || "") ? "Booster box" : "Main sealed")} ${money(s.bb)}` : ""}</div></div></a>`;
      }).join("")}</div>`).join("");
    };
    $("#upcoming").innerHTML = up.length ? group(up) : `<div class="panel empty-note">No upcoming release dates announced yet for this game.</div>`;
    $("#released").innerHTML = past.length ? group(past) : `<div class="panel empty-note">No releases in the last 90 days.</div>`;
  };
  tabs($("#game"), [["all", "All games"], ...meta.games.map((g) => [g.slug, g.label])], game, (v) => { game = v; draw(); });
  draw();
}

async function pageWatchlist() {
  const draw = async () => {
    const list = watchGet();
    if (!list.length) {
      $("#list").innerHTML = `<div class="panel empty-note">Nothing saved yet. Open any product or card and tap <b>☆ Watch</b> to track it here.</div>`;
      return;
    }
    const sets = {};
    await Promise.all([...new Set(list.map((w) => w.g))].map((g) => getJSON(`set/${g}.json`).then((d) => { sets[g] = d; }).catch(() => {})));
    $("#list").innerHTML = `<div class="table-wrap"><table><thead><tr><th>Product</th><th class="num">Market</th><th class="num hide-sm">Since saved</th><th class="num">7D</th><th class="num hide-sm">30D</th><th></th></tr></thead><tbody>
      ${list.map((w) => {
        const set = sets[w.g];
        const it = set && (set.items.find((i) => i.id === w.id && i.n.startsWith(w.n)) || set.items.find((i) => i.id === w.id));
        const since = it && w.at ? (it.p - w.at) / w.at * 100 : null;
        return `<tr><td class="title"><a href="${prodUrl(w.id, w.g)}">${imgTag(w.id, "")}<span>${esc(w.n)}${set ? `<span class="muted" style="display:block;font-size:12px">${esc(set.n)}</span>` : ""}</span></a></td>
          <td class="num"><b>${money(it?.p)}</b></td><td class="num hide-sm">${chg(since)}</td><td class="num">${chg(it?.ch?.["7"])}</td><td class="num hide-sm">${chg(it?.ch?.["30"])}</td>
          <td class="num"><button class="btn" data-rm="${esc(w.k)}" type="button" aria-label="Remove">✕</button></td></tr>`;
      }).join("")}</tbody></table></div>`;
    $("#list").querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", () => { watchSet(watchGet().filter((w) => w.k !== b.dataset.rm)); draw(); }));
  };
  draw();
}

/* ---------- Shopify importer ---------- */
const PRINT_CODES = { Normal: "", Holofoil: "H", "Reverse Holofoil": "RH" };
const printCode = (sub) => sub in PRINT_CODES ? PRINT_CODES[sub] : sub.replace(/[^A-Za-z0-9]/g, "").toUpperCase().slice(0, 12);
const GAME_META = {
  "pokemon": { vendor: "The Pokémon Company", tag: "Pokemon", sealed: "Pokémon Sealed", single: "Pokémon Single" },
  "pokemon-jp": { vendor: "The Pokémon Company", tag: "Pokemon", extra: "Pokemon Japan", sealed: "Pokémon Japan Sealed", single: "Pokémon Japan Single" },
  "one-piece": { vendor: "Bandai", tag: "One Piece", sealed: "One Piece Sealed", single: "One Piece Single" },
};
const slugify = (t) => t.toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/&/g, " and ").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 200);
const csvCell = (v) => { const t = String(v ?? ""); return /[",\n\r]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t; };
const htmlEsc = (t) => String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function shopifyRows(picks, status) {
  const head = ["Title", "URL handle", "Description", "Vendor", "Type", "Tags", "Published on online store", "Status", "SKU",
    "Option1 name", "Option1 value", "Price", "Charge tax", "Inventory tracker", "Inventory quantity", "Continue selling when out of stock",
    "Requires shipping", "Fulfillment service", "Product image URL", "Image position", "Image alt text", "SEO title", "SEO description"];
  const rows = [head];
  const used = new Set();
  for (const p of picks) {
    const gm = GAME_META[p.k] || GAME_META.pokemon;
    const sealed = p.t === "s";
    const sub = (p.n.match(/ \(([^)]+)\)$/) || [, "Normal"])[1];
    const title = p.n;
    let handle = slugify(title); if (used.has(handle)) handle += "-" + p.id; used.add(handle);
    const code = sealed ? "" : printCode(sub);
    const sku = "TCGP-" + p.id + (code ? "-" + code : "");
    const desc = sealed
      ? `<p>Factory-sealed ${htmlEsc(title)} from the ${htmlEsc(p.setName)} set (${htmlEsc(p.gameLabel)}).</p><p>All sealed product is sold factory sealed and ships from Las Vegas.</p>`
      : `<p>${htmlEsc(title)} from ${htmlEsc(p.setName)} (${htmlEsc(p.gameLabel)}).${p.r ? ` Rarity: ${htmlEsc(p.r)}.` : ""}</p><p>Condition: Near Mint. Ships sleeved and protected from Las Vegas.</p>`;
    const tags = [gm.tag, gm.extra, sealed ? "Sealed" : "Singles", "TCG", p.setName].filter(Boolean).join(", ");
    const seoDesc = sealed ? `Shop factory-sealed ${title} at Drive Your Style. Ships fast from Las Vegas.` : `Shop ${title} (${p.setName}), Near Mint, at Drive Your Style. Ships fast from Las Vegas.`;
    rows.push([title, handle, desc, gm.vendor, sealed ? gm.sealed : gm.single, tags, "TRUE", status, sku,
      "Condition", sealed ? "Unopened" : "Near Mint", (p.p / 100).toFixed(2), "TRUE", "shopify", p.qty, "DENY",
      "TRUE", "manual", img(p.id, 1000), "1", title, `${title} | Drive Your Style`, seoDesc.slice(0, 320)]);
  }
  return rows.map((r) => r.map(csvCell).join(",")).join("\r\n");
}

async function pageImporter() {
  const [meta, sets, stockMap] = await Promise.all([getJSON("meta.json"), getJSON("sets.json"), getJSON("store-prices.json").catch(() => ({}))]);
  const inStore = new Set(Object.values(stockMap).map((r) => r.id));
  const gl = Object.fromEntries(meta.games.map((g) => [g.slug, g.label]));
  let game = "pokemon", kind = "s", minP = 0, q = "", set = null;
  const picks = new Map(); // key -> pick
  const keyOf = (i) => `${i.id}|${i.n}`;
  const fillSets = () => {
    const list = sets.filter((s) => s.k === game);
    $("#set").innerHTML = list.map((s) => `<option value="${s.id}">${esc(s.n)}${s.pub ? " · " + s.pub.slice(0, 7) : ""}</option>`).join("");
    loadSet(list[0]?.id);
  };
  const loadSet = async (gid) => { if (!gid) return; set = await getJSON(`set/${gid}.json`); draw(); };
  const summary = () => {
    const n = picks.size, total = [...picks.values()].reduce((a, p) => a + p.p * p.qty, 0);
    $("#count").textContent = n ? `${n} product${n === 1 ? "" : "s"} selected · ${money(total)} at market` : "Nothing selected yet";
    $("#dl").disabled = !n; $("#clear").disabled = !n;
  };
  const draw = () => {
    if (!set) return;
    const items = set.items.filter((i) => i.t === kind && i.p >= minP * 100 && (!q || i.n.toLowerCase().includes(q)));
    $("#rows").innerHTML = items.length ? `<div class="table-wrap"><table><thead><tr><th style="width:36px"><input type="checkbox" id="all" aria-label="Select all"></th><th>${kind === "s" ? "Product" : "Card"}</th>${kind === "c" ? `<th class="hide-sm">Rarity</th>` : ""}<th class="num">Market</th><th class="num">Qty</th></tr></thead><tbody>
      ${items.map((i, ix) => { const k = keyOf(i), on = picks.has(k), have = inStore.has(i.id);
        return `<tr><td><input type="checkbox" data-ix="${ix}" ${on ? "checked" : ""} ${have ? "disabled" : ""} aria-label="Select ${esc(i.n)}"></td>
        <td class="title"><span style="display:flex;align-items:center;gap:10px">${imgTag(i.id, "")}<span>${esc(i.n)}${i.no ? `<span class="muted" style="display:block;font-size:12px">#${esc(i.no)}</span>` : ""}${have ? ` <span class="badge">In your store</span>` : ""}</span></span></td>
        ${kind === "c" ? `<td class="hide-sm">${esc(i.r || "")}</td>` : ""}<td class="num"><b>${money(i.p)}</b></td>
        <td class="num"><input class="field qty" type="number" min="0" max="999" value="${on ? picks.get(k).qty : 1}" data-q="${ix}" aria-label="Quantity" style="width:64px"></td></tr>`; }).join("")}
      </tbody></table></div>` : `<div class="panel empty-note">No ${kind === "s" ? "sealed products" : "cards"} match in this set.</div>`;
    const pick = (i, qty) => ({ id: i.id, n: i.n, t: i.t, p: i.p, no: i.no, r: i.r, k: set.k, setName: set.n, gameLabel: gl[set.k] || set.k, qty });
    $("#rows").querySelectorAll("[data-ix]").forEach((cb) => cb.addEventListener("change", () => {
      const i = items[+cb.dataset.ix], qty = Number($(`[data-q="${cb.dataset.ix}"]`).value) || 0;
      cb.checked ? picks.set(keyOf(i), pick(i, qty)) : picks.delete(keyOf(i)); summary();
    }));
    $("#rows").querySelectorAll("[data-q]").forEach((inp) => inp.addEventListener("input", () => {
      const i = items[+inp.dataset.q], k = keyOf(i); if (picks.has(k)) { picks.get(k).qty = Math.max(0, Number(inp.value) || 0); summary(); }
    }));
    $("#all")?.addEventListener("change", (e) => {
      items.forEach((i, ix) => { if (inStore.has(i.id)) return; const k = keyOf(i);
        if (e.target.checked) picks.set(k, pick(i, Number($(`[data-q="${ix}"]`).value) || 0)); else picks.delete(k); });
      draw(); summary();
    });
  };
  tabs($("#game"), meta.games.map((g) => [g.slug, g.label]), game, (v) => { game = v; fillSets(); });
  tabs($("#kind"), [["s", "Sealed"], ["c", "Singles"]], kind, (v) => { kind = v; draw(); });
  $("#set").addEventListener("change", (e) => loadSet(e.target.value));
  $("#min").addEventListener("input", (e) => { minP = Number(e.target.value) || 0; draw(); });
  $("#q").addEventListener("input", (e) => { q = e.target.value.trim().toLowerCase(); draw(); });
  $("#clear").addEventListener("click", () => { picks.clear(); draw(); summary(); });
  $("#dl").addEventListener("click", () => {
    const csv = shopifyRows([...picks.values()], $("#status").value);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
    a.download = `dys-shopify-import-${meta.updated}.csv`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  });
  fillSets(); summary();
}

/* ---------- boot ---------- */
shell();
document.querySelectorAll("[data-search]").forEach(initSearch);
const pages = { index: pageIndex, sets: pageSets, set: pageSet, product: pageProduct, trends: pageTrends, cards: pageCards, compare: pageCompare, calendar: pageCalendar, watchlist: pageWatchlist, importer: pageImporter };
(pages[PAGE] || (async () => {}))().catch((err) => {
  console.error(err);
  const main = $("main");
  if (main) main.insertAdjacentHTML("afterbegin", `<div class="wrap"><p class="panel empty-note" style="margin-top:24px">Couldn't load market data right now. Please refresh in a minute.</p></div>`);
});
})();
