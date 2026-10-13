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
  const links = [["index", "Overview"], ["sets", "Sets"], ["trends", "Trends"], ["cards", "Cards"], ["about", "About the data"]];
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
function moverRows(list, meta, limit) {
  if (!list || !list.length) return `<div class="empty-note">Not enough price history for this view yet.</div>`;
  return list.slice(0, limit).map((r, i) => {
    const [id, name, gid, now, old, p] = r;
    return `<a class="row" href="${prodUrl(id, gid)}"><span class="rank">${i + 1}</span>${imgTag(id)}
      <span class="name"><b>${esc(name)}</b><span>${esc(meta.groups[gid]?.[0] || "")}</span></span>
      <span class="figs"><b>${money(now)}</b>${chg(p)}<span class="muted" style="font-size:12px;display:block">from ${money(old)}</span></span></a>`;
  }).join("");
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
    $("[data-up]", container).innerHTML = moverRows(w?.up, meta, limit);
    $("[data-down]", container).innerHTML = moverRows(w?.down, meta, limit);
  };
  tabs($("[data-g]", container), games, game, (v) => { game = v; draw(); });
  tabs($("[data-w]", container), WINDOWS, win, (v) => { win = v; draw(); });
  if (thresholds) tabs($("[data-t]", container), [["5", "$5+"], ["20", "$20+"], ["100", "$100+"]], thr, (v) => { thr = v; draw(); });
  draw();
}
function setsTable(rows, meta, opts = {}) {
  const gl = Object.fromEntries(meta.games.map((g) => [g.slug, g.label]));
  const today = meta.updated;
  return `<div class="table-wrap"><table><thead><tr><th>Set</th><th class="hide-sm">Game</th><th class="hide-sm">Released</th><th class="num hide-sm">Products</th><th class="num">Booster box</th><th class="num">7D</th></tr></thead><tbody>
    ${rows.map((s) => `<tr><td class="title"><a href="set.html?id=${s.id}">${s.bbId ? imgTag(s.bbId, "") : ""}<span>${esc(s.n)}${s.pub > today ? ` <span class="badge up-next">Upcoming</span>` : ""}</span></a></td>
      <td class="hide-sm">${esc(gl[s.k] || s.k)}</td><td class="hide-sm">${fmtDate(s.pub)}</td><td class="num hide-sm">${s.np}</td><td class="num">${money(s.bb)}</td><td class="num">${chg(s.c7)}</td></tr>`).join("")}
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
      <span class="badge">In stock</span><span class="t">${esc(s.n)}</span>
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
      ${items.slice(0, limit).map((i) => `<tr><td class="title"><a href="${prodUrl(i.id, set.id)}">${imgTag(i.id, "")}<span>${esc(i.n)}${i.dys ? ` <span class="badge">In stock</span>` : ""}</span></a></td>
        ${isCard ? `<td class="hide-sm">${esc(i.r || "")}</td>` : ""}<td class="num"><b>${money(i.p)}</b></td><td class="num">${chg(i.ch?.["7"])}</td><td class="num hide-sm">${chg(i.ch?.["30"])}</td><td class="num hide-sm">${chg(i.ch?.["90"])}</td></tr>`).join("")}
      </tbody></table></div>`;
  };
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
        <div class="kpis">${[["7", "7 days"], ["30", "30 days"], ["90", "90 days"]].map(([k, l]) => `<div class="kpi"><div class="l">${l}</div>${chg(v.ch?.[k])}</div>`).join("")}</div>
        <div class="btns">${v.dys ? `<a class="btn primary" href="${esc(v.dys.u)}">In stock at Drive Your Style · ${money(v.dys.p)}</a>` : `<a class="btn primary" href="${STORE}">Shop Drive Your Style</a>`}
          <a class="btn" href="https://www.tcgplayer.com/product/${id}" target="_blank" rel="noopener">View on TCGplayer ↗</a></div>
        <div class="chart-card"><div class="chart-head"><b>Price history</b><div id="range"></div></div><div class="chart" id="chart"></div>
          <p class="muted" style="font-size:12px;margin:6px 0 4px">Nightly TCGplayer market price. Gaps mean no market price was recorded that day.</p></div>
      </div>`;
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
      up.innerHTML = moverRows(rows.filter((r) => r[5] > 0).sort((a, b) => b[5] - a[5]), meta, 25);
      down.innerHTML = moverRows(rows.filter((r) => r[5] < 0).sort((a, b) => a[5] - b[5]), meta, 25);
      $("#note").textContent = win !== w ? "Single-set view goes back 90 days." : "";
      return;
    }
    $("#note").textContent = recent ? "Showing cards from sets released in the last 12 months." : "";
    const data = await getJSON(`movers/cards-${game}.json`);
    const w = data.windows[win]?.["5"] || {};
    const keep = (r) => !recent || (sets.find((s) => s.id === r[2])?.pub || "") >= yearAgo;
    up.innerHTML = moverRows((w.up || []).filter(keep), meta, 25);
    down.innerHTML = moverRows((w.down || []).filter(keep), meta, 25);
  };
  tabs($("#game"), [["all", "All games"], ...meta.games.map((g) => [g.slug, g.label])], game, (v) => { game = v; fillSets(); draw(); });
  tabs($("#win"), WINDOWS, win, (v) => { win = v; draw(); });
  setSel.addEventListener("change", () => { setId = setSel.value; draw(); });
  $("#recent").addEventListener("change", (e) => { recent = e.target.checked; fillSets(); draw(); });
  fillSets(); draw();
}

/* ---------- boot ---------- */
shell();
document.querySelectorAll("[data-search]").forEach(initSearch);
const pages = { index: pageIndex, sets: pageSets, set: pageSet, product: pageProduct, trends: pageTrends, cards: pageCards };
(pages[PAGE] || (async () => {}))().catch((err) => {
  console.error(err);
  const main = $("main");
  if (main) main.insertAdjacentHTML("afterbegin", `<div class="wrap"><p class="panel empty-note" style="margin-top:24px">Couldn't load market data right now. Please refresh in a minute.</p></div>`);
});
})();
