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
const NOIMG = "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 250 350"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2a2f45"/><stop offset="1" stop-color="#151827"/></linearGradient></defs><rect x="4" y="4" width="242" height="342" rx="16" fill="url(#g)" stroke="#3a4060" stroke-width="3"/><circle cx="125" cy="150" r="38" fill="none" stroke="#6b7395" stroke-width="6"/><path d="M87 150h76" stroke="#6b7395" stroke-width="6"/><circle cx="125" cy="150" r="11" fill="#151827" stroke="#6b7395" stroke-width="6"/><text x="125" y="240" fill="#8b93b5" font-family="Arial,sans-serif" font-size="20" text-anchor="middle">No image yet</text></svg>');
window.dysImg = (el) => { if (el.dataset.alt && !el.dataset.tried) { el.dataset.tried = "1"; el.src = el.dataset.alt; } else { el.onerror = null; el.src = NOIMG; } };
const imgTag = (id, cls = "thumb", size = 200, alt = "") =>
  `<img class="${cls}" src="${img(id, size)}"${alt ? ` data-alt="${esc(alt)}"` : ""} alt="" loading="lazy" onerror="dysImg(this)">`;
const prodUrl = (id, gid) => `product.html?id=${id}&set=${gid}`;
const fmtDate = (d) => d ? new Date(d + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—";
const below = (ours, mkt) => ours != null && mkt != null && ours < mkt;
const BELOW = `<span class="badge deal">Below market</span>`;
const WKEY = "dys-watch";
const watchGet = () => { try { return JSON.parse(localStorage.getItem(WKEY) || "[]"); } catch { return []; } };
const watchSet = (list) => { try { localStorage.setItem(WKEY, JSON.stringify(list)); } catch {} };
/* ---------- Want list: saved in the binder (synced to the account), tallied anonymously into "Most wanted" ---------- */
const wantKey = (id, n) => `${id}|${printCode(subOf(n || ""))}`;
const wantGet = () => colGet().want || [];
const wantHas = (k) => wantGet().some((w) => w.k === k);
function wantToggle(it) {   // it: {id, g, n, at (market price now)}
  const c = colGet(), list = c.want || [], k = wantKey(it.id, it.n), i = list.findIndex((w) => w.k === k);
  if (i >= 0) list.splice(i, 1); else list.push({ k, id: it.id, g: it.g, n: it.n, at: it.at ?? null, max: null, ts: Date.now() });
  c.want = list.slice(-300); colSet(c);
  toast(i >= 0 ? "Removed from your Want list" : "Added to your Want list ♥ Set the most you'd pay on the Want list page");
  return i < 0;
}
const HEARTS = (on) => on ? "♥" : "♡";
/* adds a ♡ next to every "+" add button in a grid; itemOf(addKey) -> {id, g, n, at} */
function wantButtons(root, itemOf) {
  root.querySelectorAll(".cadd[data-add]").forEach((b) => {
    const k = b.dataset.add, on = wantHas(k);
    const w = document.createElement("button");
    w.type = "button"; w.className = "cwant" + (on ? " on" : ""); w.textContent = HEARTS(on);
    w.setAttribute("aria-label", "Add to Want list"); w.setAttribute("aria-pressed", on);
    w.addEventListener("click", (e) => { e.preventDefault(); const it = itemOf(k); if (!it) return; const now = wantToggle(it);
      w.classList.toggle("on", now); w.textContent = HEARTS(now); w.setAttribute("aria-pressed", now); });
    b.before(w);
  });
}
(() => {   // one-time move of the old device-only Watchlist into the Want list
  try {
    const old = watchGet(); if (!old.length || localStorage.getItem("dys-watch-moved")) return;
    const c = colGet(), list = c.want || [];
    for (const w of old) { const k = `${w.id}|`; if (!list.some((x) => x.id === w.id)) list.push({ k, id: w.id, g: w.g, n: w.n, at: w.at ?? null, max: null, ts: Date.now() }); }
    c.want = list; localStorage.setItem("dys-collection", JSON.stringify(c)); localStorage.setItem("dys-watch-moved", "1");
  } catch {}
})();
const fmtShort = (d) => d ? new Date(d + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "";
const bestCh = (ch) => ch?.["7"] != null ? ch["7"] : ch?.a ?? null;
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
  const links = [["sets", "Sets"], ["trends", "Trends"], ["cards", "Movers"], ["search", "Search"], ["compare", "Compare"], ["calendar", "Calendar"], ["sneakers", "Sneakers"], ["watchlist", "Want list"], ["collection", "My Collection"], ["collectors", "Collectors"], ["about", "About"]];
  $("#top").outerHTML = `<header class="top"><div class="wrap">
    <a class="brand" href="index.html" aria-label="Drive Your Style Market Insights home"><img class="logo-img logo-on-dark" src="assets/logo-light.png" alt="Drive Your Style" width="61" height="40"><img class="logo-img logo-on-light" src="assets/logo-dark.png" alt="" width="61" height="40"><span class="brand-sub">Market<br>Insights</span></a>
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
  const I = (d) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
  const tb = [["index", "Home", I('<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>')],
    ["sets", "Sets", I('<rect x="7" y="3" width="13" height="17" rx="2"/><path d="M4 7v12a2 2 0 0 0 2 2h10"/>')],
    ["collection", "Collection", I('<path d="M4 6h16v12H4z"/><path d="M4 10h16"/>')],
    ["trends", "Trends", I('<path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/>')],
    ["shop", "Shop", I('<path d="M6 7h12l-1 13H7z"/><path d="M9 7a3 3 0 0 1 6 0"/>')]];
  const bar = document.createElement("nav"); bar.className = "tabbar"; bar.setAttribute("aria-label", "Main");
  bar.innerHTML = tb.map(([p, l, i]) => `<a href="${p === "shop" ? STORE : p + ".html"}"${p === PAGE || (p === "sets" && PAGE === "set") ? ' aria-current="page"' : ""}>${i}<span>${l}</span></a>`).join("");
  document.body.appendChild(bar);
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
const wordRe = (t) => new RegExp(`(^|[^a-z0-9])${t.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&")}([^a-z0-9]|$)`);
/* rank matches: exact whole-word name matches first (so "mew" puts Mew before Mewtwo), then by price */
function rankHits(rows, terms, hayOf, nameOf, limit = Infinity) {
  const res = [], res2 = terms.map(wordRe);
  rows.forEach((r, i) => {
    const hay = hayOf(r, i);
    if (!terms.every((t) => hay.includes(t))) return;
    const name = nameOf(r).toLowerCase().replace(/é/g, "e");
    let sc = 0;
    res2.forEach((re) => { if (re.test(name)) sc += 2; });
    if (terms.length && name.startsWith(terms[0])) sc += 1;
    res.push([sc, i, r]);
  });
  res.sort((a, b) => b[0] - a[0] || a[1] - b[1]);
  return res.slice(0, limit).map((x) => x[2]);
}
function initSearch(box) {
  const input = $("input", box), out = $(".results", box);
  let rows = null, sel = -1, meta = null;
  const load = async () => { if (!rows) { [rows, meta] = await Promise.all([getJSON("search.json"), getJSON("meta.json")]); } };
  input.addEventListener("focus", load);
  const render = () => {
    const q = input.value.trim().toLowerCase().replace(/é/g, "e");
    if (!rows || q.length < 2) { out.classList.remove("open"); return; }
    const terms = q.split(/\s+/);
    const hits = rankHits(rows, terms, (r) => alias((r[1] + " " + (meta.groups[r[2]]?.[0] || "")).toLowerCase().replace(/é/g, "e")), (r) => r[1], 12);
    sel = -1;
    out.innerHTML = hits.length ? hits.map((r) => `<a href="${prodUrl(r[0], r[2])}">${imgTag(r[0])}
      <span class="name"><b>${esc(r[1])}</b><span>${esc(meta.groups[r[2]]?.[0] || "")} · ${r[3] === "s" ? "Sealed" : "Card"}</span></span>
      <span class="figs" style="margin-left:auto"><b>${money(r[4])}</b></span></a>`).join("")
      : `<div class="empty">No matches for "${esc(input.value)}"</div>`;
    out.innerHTML += `<a class="all-res" href="search.html?q=${encodeURIComponent(input.value.trim())}"><b>Search every card for "${esc(input.value.trim())}" →</b></a>`;
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
    } else if (e.key === "Enter") { (items[sel] || items[items.length - 1]).click(); }
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
  let game = "all", win = meta.anchors?.["7"] ? "7" : meta.anchors?.all ? "all" : "7", thr = defaultThr;
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
  $("#stats").textContent = `Tracking ${meta.cards.toLocaleString()} cards and ${meta.sealed.toLocaleString()} sealed products across ${meta.sets.toLocaleString()} sets · prices updated ${fmtDate(meta.updated)}`;
  const allSets = await getJSON("sets.json");
  const GT = { "pokemon": "Pokémon TCG", "pokemon-jp": "Pokémon Japan", "one-piece": "One Piece Card Game" };
  $("#gtiles").innerHTML = meta.games.map((g, i) => `<a class="gtile gt${i}" href="sets.html?game=${g.slug}"><b>${esc(GT[g.slug] || g.label)}</b><span>${g.sets} sets<i> · browse cards &amp; prices</i> →</span></a>`).join("");
  const horizon = new Date(Date.now() + 45 * 864e5).toISOString().slice(0, 10);
  $("#newsets").innerHTML = allSets.filter((s) => s.pub && s.pub <= horizon && !SPECIAL.test(s.n) && (s.lg || s.bbId || s.tc?.length))
    .sort((a, b) => b.pub.localeCompare(a.pub)).slice(0, 12).map((s) => setTile(s, meta.updated)).join("");
  moversPanel($("#card-movers"), { kind: "cards", meta, limit: 5 });
  moversPanel($("#sealed-movers"), { kind: "sealed", meta, limit: 5 });
  getJSON("wanted.json").then((w) => {
    const top = (w.top || []).slice(0, 12); if (!top.length) return;
    $("#wanted-block").hidden = false;
    $("#wanted").innerHTML = top.map((i) => `<a class="scard" href="${prodUrl(i.id, i.g)}"><span class="si">${imgTag(i.id, "", 1000)}<span class="badge want">♥ ${i.c} want${i.c > 1 ? "" : "s"} this</span></span>
      <span class="t">${esc(i.n)}</span><span class="pp"><b>${money(i.m)}</b>${i.st ? `<span class="muted">In stock</span>` : ""}</span></a>`).join("");
  }).catch(() => {});
  const stock = await getJSON("stock.json").catch(() => []);
  if (stock.length) {
    const deals = stock.slice().sort((a, b) => (below(b.p, b.m) - below(a.p, a.m)) || (b.m || 0) - (a.m || 0));
    $("#stock").innerHTML = deals.slice(0, 16).map((s) => `<a class="scard" href="${esc(s.u)}"><span class="si">${imgTag(s.id, "", 1000)}${below(s.p, s.m) ? `<span class="badge deal">Below market</span>` : ""}</span>
      <span class="t">${esc(s.n)}</span><span class="pp"><b>${money(s.p)}</b><span class="muted">Mkt ${money(s.m)}</span></span></a>`).join("");
  } else {
    $("#stock-block").hidden = true;
  }
}

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
  if (SPECIAL.test(s.n)) return PROMO_GROUP;
  if (!s.pub) return "Other";
  const e = (ERAS[s.k] || []).find(([d]) => s.pub >= d);
  return e ? e[1] : "Other";
}

function setTile(s, today) {
  return `<a class="stile" href="set.html?id=${s.id}">
      <span class="simg${s.lg ? " logo" : s.tc?.length ? " fan" : ""}">${s.lg ? `<img src="${esc(s.lg)}" alt="${esc(s.n)} logo" loading="lazy">` : s.bbId ? imgTag(s.bbId, "", 1000)
        : s.tc?.length ? s.tc.map(([id, im]) => `<span class="fc">${imgTag(id, "", 400, im || "")}</span>`).join("") : `<span class="sph">${esc((s.a || s.n).slice(0, 8))}</span>`}${s.pub && s.pub > today ? `<span class="badge up-next">Upcoming</span>` : ""}</span>
      <span class="sname">${esc(s.n.replace(/^(ME|SV|SWSH|SM|M)\d*[a-z]?:\s*/i, ""))}</span>
      <span class="smeta">${s.pub ? new Date(s.pub + "T12:00:00").toLocaleDateString("en-US", { month: "short", year: "numeric" }) : "—"}</span></a>`;
}

async function pageSets() {
  const [meta, sets] = await Promise.all([getJSON("meta.json"), getJSON("sets.json")]);
  let game = params.get("game") || "pokemon", q = "", era = "all";
  const today = meta.updated;
  const tile = (s) => setTile(s, today);
  const draw = () => {
    const list = sets.filter((s) => s.k === game && (!q || (s.n + " " + s.a).toLowerCase().includes(q)))
      .sort((a, b) => (b.pub || "").localeCompare(a.pub || ""));
    const groups = new Map();
    for (const s of list) { const e = eraOf(s); if (!groups.has(e)) groups.set(e, []); groups.get(e).push(s); }
    if (game === "one-piece") for (const k of ["Promos & Events", "Other"]) if (groups.has(k)) { const v = groups.get(k); groups.delete(k); groups.set(k, v); }
    if (game !== "one-piece") for (const k of [PROMO_GROUP, "Other"]) if (groups.has(k)) { const v = groups.get(k); groups.delete(k); groups.set(k, v); }
    const eras = [...groups.keys()];
    if (era !== "all" && !groups.has(era)) era = "all";
    $("#eras").innerHTML = [["all", "All"], ...eras.map((e) => [e, e])].map(([v, l]) => `<button type="button" class="chip${v === era ? " on" : ""}" data-e="${esc(v)}">${esc(l)}</button>`).join("");
    $("#count").textContent = `${list.length} sets`;
    $("#table").innerHTML = list.length ? [...groups].filter(([e]) => era === "all" || e === era).map(([e, ss]) =>
      `<section class="era"><h2>${esc(e)} <small>${ss.length} sets</small></h2><div class="sgrid">${ss.map(tile).join("")}</div></section>`).join("")
      : `<div class="panel empty-note">No sets match.</div>`;
  };
  tabs($("#game"), meta.games.map((g) => [g.slug, g.label]), game, (v) => { game = v; era = "all"; draw(); });
  $("#eras").addEventListener("click", (e) => { const b = e.target.closest("[data-e]"); if (!b) return; era = b.dataset.e; draw(); window.scrollTo({ top: $("#table").offsetTop - 140, behavior: "smooth" }); });
  $("#q").addEventListener("input", (e) => { q = e.target.value.trim().toLowerCase(); draw(); });
  draw();
}

async function pageSet() {
  const id = params.get("id");
  const [meta, set, allSets] = await Promise.all([getJSON("meta.json"), getJSON(`set/${id}.json`), getJSON("sets.json")]);
  document.title = `${set.n} prices · Drive Your Style Market Insights`;
  const gl = Object.fromEntries(meta.games.map((g) => [g.slug, g.label]));
  $("#crumbs").innerHTML = `<a href="sets.html">Sets</a> / <a href="sets.html?game=${set.k}">${esc(gl[set.k] || set.k)}</a> / ${esc(set.n)}`;
  $("#title").textContent = set.n;
  const sinfo = allSets.find((s) => String(s.id) === String(set.id));
  if (sinfo?.lg) { $("#set-logo").innerHTML = `<img src="${esc(sinfo.lg)}" alt="${esc(set.n)} logo">`; $("#set-logo").hidden = false; }
  $("#sub").textContent = `${gl[set.k] || ""}${set.pub ? " · Released " + fmtDate(set.pub) : ""}`;
  const cards = set.items.filter((i) => i.t === "c"), sealed = set.items.filter((i) => i.t === "s");
  const rarities = [...cards.reduce((m, c) => m.set(c.r || "Other", (m.get(c.r || "Other") || 0) + 1), new Map())]
    .sort((a, b) => a[1] - b[1]).map(([r]) => r);
  const ownKey = (i) => `${i.id}|${printCode(subOf(i.n))}`;
  const owned = sumOwned;
  let tab = params.get("tab") === "sealed" || !cards.length ? "s" : "c", rar = "all", q = "", sort = "price", view = "grid", lim = 60, ownf = "all";
  try { view = localStorage.getItem("dys-view") || "grid"; } catch {}

  const short = (i) => i.n.replace(/ \((Holofoil|Normal|Reverse Holofoil)\)$/, "").replace(/ - [^-]*\d+\/\d+.*$/, "");
  const printing = (i) => ({ Holofoil: "Holo", "Reverse Holofoil": "Reverse", Normal: "" }[subOf(i.n)] ?? subOf(i.n));
  const numOf = (i) => { const m = (i.no || "").match(/\d+/); return m ? Number(m[0]) : 1e9; };

  const stats = () => {
    const own = owned(), uniq = new Set(cards.map((c) => c.id));
    const ownedIds = new Set(cards.filter((c) => own.has(ownKey(c))).map((c) => c.id));
    const value = cards.reduce((a, c) => a + (c.p || 0), 0);
    $("#set-stats").innerHTML = [
      [`${uniq.size ? Math.round(ownedIds.size / uniq.size * 100) : 0}%`, "Owned"],
      [uniq.size.toLocaleString(), "Cards"],
      [cards.some((c) => c.p != null) ? money(value) : "—", "Set value"],
      [sealed.length.toLocaleString(), "Sealed"],
    ].map(([v, l]) => `<div><b>${v}</b><span>${l}</span></div>`).join("");
  };

  const draw = () => {
    const own = owned();
    let items = (tab === "c" ? cards : sealed).filter((i) => (tab === "s" || rar === "all" || (i.r || "Other") === rar) && (!q || (i.n + " " + (i.no || "")).toLowerCase().includes(q))
      && (ownf === "all" || (ownf === "owned" ? own.has(ownKey(i)) : ownf === "missing" ? !own.has(ownKey(i)) : !!i.dys)));
    items = items.slice().sort((a, b) => sort === "price" ? (b.p ?? -1) - (a.p ?? -1) : sort === "low" ? (a.p ?? 1e12) - (b.p ?? 1e12) : sort === "num" ? numOf(a) - numOf(b) || a.n.localeCompare(b.n) : a.n.localeCompare(b.n));
    $("#rar").hidden = tab !== "c" || rarities.length < 2;
    $("#count-line").textContent = `${items.length} ${tab === "c" ? "cards" : "sealed products"}`;
    if (!items.length) { $("#grid").innerHTML = `<div class="panel empty-note">Nothing matches.</div>`; return; }
    const shown = items.slice(0, lim);
    $("#grid").className = view === "grid" ? "cgrid" : "clist";
    $("#grid").innerHTML = shown.map((i) => {
      const k = ownKey(i), qty = own.get(k) || 0, pr = tab === "c" ? printing(i) : "";
      return view === "grid"
        ? `<div class="ctile${tab === "s" ? " sealed" : ""}${qty ? " owned" : ""}"><a href="${prodUrl(i.id, set.id)}" class="cimg">${imgTag(i.id, "", 1000, i.im)}</a>
            <button class="cadd" type="button" data-add="${esc(k)}" aria-label="Add ${esc(i.n)} to My Collection">${qty ? `✓${qty > 1 ? qty : ""}` : "+"}</button>
            <a href="${prodUrl(i.id, set.id)}" class="cinfo"><span class="cn"><b>${esc(tab === "c" ? short(i) : i.n)}</b>${i.no ? `<small>${esc(i.no)}</small>` : ""}</span>
            <span class="cp">${i.p == null ? `<small class="muted">No price yet</small>` : `<b>${money(i.p)}</b>`}${bestCh(i.ch) != null ? `<small class="cchg">${chg(bestCh(i.ch))}</small>` : ""}${pr ? `<em>${esc(pr)}</em>` : ""}${i.dys ? `<em class="instock">In stock</em>` : ""}</span></a></div>`
        : `<div class="crow${qty ? " owned" : ""}"><a href="${prodUrl(i.id, set.id)}">${imgTag(i.id, "", 200, i.im)}<span><b>${esc(i.n)}</b><small>${esc([i.r, i.no].filter(Boolean).join(" · "))}</small></span></a>
            <span class="num"><b>${money(i.p)}</b>${chg(i.ch?.["7"])}</span><button class="cadd" type="button" data-add="${esc(k)}" aria-label="Add ${esc(i.n)} to My Collection">${qty ? `✓${qty > 1 ? qty : ""}` : "+"}</button></div>`;
    }).join("") + (items.length > lim ? `<div class="cmore"><button class="btn" id="more" type="button">Show all ${items.length}</button></div>` : "");
    $("#more")?.addEventListener("click", () => { lim = 1e9; draw(); });
    $("#grid").querySelectorAll("[data-add]").forEach((b) => b.addEventListener("click", () => {
      const it = items.find((i) => ownKey(i) === b.dataset.add); if (!it) return;
      const col = colGet(), ex = col.items.find((x) => !x.gr && `${x.id}|${printCode(subOf(x.n || ""))}` === b.dataset.add);
      ex ? ex.qty++ : col.items.push({ id: it.id, g: set.id, n: it.n, qty: 1, paid: null });
      colSet(col); toast(`Added ${tab === "c" ? short(it) : it.n} to My Collection`); draw(); stats();
    }));
    wantButtons($("#grid"), (k) => { const it = items.find((i) => ownKey(i) === k); return it && { id: it.id, g: set.id, n: it.n, at: it.p }; });
  };

  tabs($("#tab"), [["c", `Cards`], ["s", `Sealed`]], tab, (v) => { tab = v; lim = 60; draw(); });
  if (!cards.length) $("#tab").hidden = true;
  $("#rar").innerHTML = [["all", "All"], ...rarities.map((r) => [r, r])].map(([v, l]) => `<button type="button" class="chip${v === rar ? " on" : ""}" data-r="${esc(v)}">${esc(l)}</button>`).join("");
  $("#rar").addEventListener("click", (e) => { const b = e.target.closest("[data-r]"); if (!b) return; rar = b.dataset.r; $("#rar").querySelectorAll(".chip").forEach((x) => x.classList.toggle("on", x === b)); lim = 60; draw(); });
  $("#q").addEventListener("input", (e) => { q = e.target.value.trim().toLowerCase(); lim = 60; draw(); });
  $("#ownf").innerHTML = [["all", "Everything"], ["owned", "Owned"], ["missing", "Missing"], ["stock", "In stock at DYS"]].map(([v, l]) => `<button type="button" class="chip${v === ownf ? " on" : ""}" data-o="${v}">${l}</button>`).join("");
  $("#ownf").addEventListener("click", (e) => { const b = e.target.closest("[data-o]"); if (!b) return; ownf = b.dataset.o; $("#ownf").querySelectorAll(".chip").forEach((x) => x.classList.toggle("on", x === b)); lim = 60; draw(); });
  $("#sort").addEventListener("change", (e) => { sort = e.target.value; draw(); });
  $("#view").addEventListener("click", () => { view = view === "grid" ? "list" : "grid"; try { localStorage.setItem("dys-view", view); } catch {} $("#view").innerHTML = view === "grid" ? ICON_LIST : ICON_GRID; draw(); });
  $("#view").innerHTML = view === "grid" ? ICON_LIST : ICON_GRID;
  stats(); draw();
}

const ICON_GRID = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/></svg>`;
const ICON_LIST = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/></svg>`;
function toast(msg) {
  let t = $("#toast"); if (!t) { t = document.createElement("div"); t.id = "toast"; t.setAttribute("role", "status"); document.body.appendChild(t); }
  t.textContent = msg; t.classList.add("show"); clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.remove("show"), 1800);
}

function moreHtml(set, id) {
  const seen = new Set([id]), cards = set.items.filter((i) => i.t === "c" && !seen.has(i.id) && seen.add(i.id));
  if (!cards.length) return "";
  return `<section style="grid-column:1/-1;margin-top:28px;min-width:0"><div class="block-head"><div><h2 style="font-size:24px">More from ${esc(set.n)}</h2><p>The most valuable cards in this set.</p></div><a class="more" href="set.html?id=${set.id}">All cards →</a></div>
    <div class="chase-row">${cards.slice(0, 12).map((c) => `<a class="chase" href="${prodUrl(c.id, set.id)}">${imgTag(c.id, "", 1000)}<span class="t">${esc(c.n)}</span><span class="p"><b>${money(c.p)}</b>${chg(bestCh(c.ch))}</span></a>`).join("")}</div></section>`;
}
function pullsHtml(set) {
  const seen = new Set(), cards = set.items.filter((i) => i.t === "c" && !seen.has(i.id) && seen.add(i.id));
  if (!cards.length) return "";
  return `<section style="grid-column:1/-1;margin-top:28px;min-width:0"><div class="block-head"><div><h2 style="font-size:24px">Top cards you could pull</h2><p>The most valuable singles in ${esc(set.n)} at today's market price.</p></div><a class="more" href="set.html?id=${set.id}">All ${cards.length} cards →</a></div>
    <div class="chase-row">${cards.slice(0, 18).map((c, i) => `<a class="chase" href="${prodUrl(c.id, set.id)}"><span class="rank">${i + 1}</span>${imgTag(c.id, "", 1000)}<span class="t">${esc(c.n)}</span><span class="p"><b>${money(c.p)}</b>${chg(c.ch?.["7"])}</span></a>`).join("")}</div></section>`;
}

function gradedHtml(base, set, v) {
  const setName = set.n.replace(/^[A-Z0-9]+[a-z]?\s*[:\-–]\s*/, "");
  const q = `${set.k === "one-piece" ? "One Piece" : "Pokemon"} ${base.replace(/ - /, " ")} ${base.includes(v.no || "~") ? "" : v.no || ""} ${setName}`.replace(/\s+/g, " ").trim();
  const ebay = (g) => `https://www.ebay.com/sch/i.html?_nkw=${encodeURIComponent(q + " " + g)}&LH_Sold=1&LH_Complete=1&_sop=13`;
  const link = (h, t, s) => `<a class="glink" href="${h}" target="_blank" rel="noopener"><b>${t}</b><span>${s}</span></a>`;
  return `<section class="graded"><h2 style="font-size:24px">Graded prices &amp; gem rate</h2>
    <p class="muted">Live graded data isn't built in yet. These links search recent graded sales for this card, and GemRate for its population and gem rate.</p>
    <div class="glinks">${link(ebay("PSA 10"), "PSA 10 sold ↗", "eBay sold listings")}${link(ebay("PSA 9"), "PSA 9 sold ↗", "eBay sold listings")}${link(ebay("CGC 10"), "CGC 10 sold ↗", "eBay sold listings")}${link(`https://www.pricecharting.com/search-products?q=${encodeURIComponent(q)}&type=prices`, "All grades ↗", "PriceCharting")}${link("https://www.gemrate.com/", "Gem rate &amp; pop ↗", "Search it on GemRate")}</div>
    <div class="gcalc" id="gcalc"></div>
  </section>`;
}

/* ---------- Grade It? calculator ---------- */
const GKEY = "dys-grade";
const ODDS = { fresh: [55, 35, "Pack fresh"], nm: [30, 50, "Near mint"], lp: [5, 35, "Light play"] };
function gradeCalc(el, rawCents, id) {
  if (!el) return;
  let all = {}; try { all = JSON.parse(localStorage.getItem(GKEY)) || {}; } catch {}
  const saved = all[id] || {};
  const dollars = (c) => c == null ? "" : (c / 100).toFixed(2);
  const s = { cond: saved.cond || "nm", o10: saved.o10 ?? ODDS[saved.cond || "nm"][0], o9: saved.o9 ?? ODDS[saved.cond || "nm"][1],
    raw: saved.raw ?? dollars(rawCents), p10: saved.p10 ?? "", p9: saved.p9 ?? "", p8: saved.p8 ?? "", fee: saved.fee ?? "25", ship: saved.ship ?? "20" };
  const f = (k, l, extra = "") => `<label class="gfield"><span>${l}</span><input class="field" type="number" inputmode="decimal" min="0" step="0.01" data-g="${k}" value="${esc(s[k])}"${extra}></label>`;
  el.innerHTML = `<div class="gcalc-head"><div><h2>Grade It?</h2><p class="muted">Should you grade this card raw, or buy it already graded? Paste PSA prices from the sold links above.</p></div></div>
    <div class="gverdict" id="gv"><span class="gl">Verdict</span><b id="gv-t"></b><span id="gv-w" class="muted"></span></div>
    <div class="gbody">
      <div class="gcol">
        <span class="gsub">Your condition estimate</span>
        <div class="tabs gcond" role="group" aria-label="Condition">${Object.entries(ODDS).map(([k, o]) => `<button type="button" data-cond="${k}" aria-pressed="${k === s.cond}">${o[2]}</button>`).join("")}</div>
        <div class="godds" id="godds"></div>
        <div class="ggrid">${f("o10", "PSA 10 odds %", ' max="100" step="1"')}${f("o9", "PSA 9 odds %", ' max="100" step="1"')}</div>
      </div>
      <div class="gcol">
        <div class="ggrid">${f("raw", "Raw price $")}${f("p10", "PSA 10 price $")}${f("p9", "PSA 9 price $")}${f("p8", "PSA 8 or lower $")}${f("fee", "Grading fee $")}${f("ship", "Ship + insure $")}</div>
      </div>
    </div>
    <div class="gbreak" id="gb"></div>
    <p class="muted" style="font-size:12px;margin:8px 0 0">Raw price starts at today's market price. Odds are rough starting guesses; use the card's gem rate if you know it. Estimates only, not financial advice. Your numbers save on this device.</p>`;
  const n = (v) => { const x = parseFloat(v); return isNaN(x) ? 0 : x; };
  const save = () => { all[id] = s; try { localStorage.setItem(GKEY, JSON.stringify(all)); } catch {} };
  const calc = () => {
    const o10 = Math.min(100, Math.max(0, n(s.o10))) / 100, o9 = Math.min(1 - o10, Math.max(0, n(s.o9) / 100)), o8 = Math.max(0, 1 - o10 - o9);
    $("#godds", el).innerHTML = [["PSA 10", o10, "var(--up)"], ["PSA 9", o9, "var(--accent)"], ["PSA 8 or lower", o8, "var(--ink-3)"]]
      .map(([l, p, c]) => `<div class="godd"><span>${l}</span><i><b style="width:${Math.round(p * 100)}%;background:${c}"></b></i><span class="num">${Math.round(p * 100)}%</span></div>`).join("");
    const raw = n(s.raw), p10 = n(s.p10), p9 = n(s.p9), p8 = s.p8 === "" ? raw : n(s.p8), cost = raw + n(s.fee) + n(s.ship);
    const box = $("#gv", el);
    if (!p10) {
      box.dataset.v = "wait"; $("#gv-t", el).textContent = "Add the PSA 10 price";
      $("#gv-w", el).textContent = "Tap “PSA 10 sold” above, then enter a typical recent sale.";
      $("#gb", el).innerHTML = ""; return;
    }
    const ev = o10 * p10 + o9 * (p9 || raw) + o8 * p8, profit = ev - cost, chase = o10 > 0 ? cost / o10 : Infinity;
    let v, w, k;
    if (chase > p10 && profit <= raw * 0.15) { k = "slab"; v = "Buy the slab"; w = "Chasing a 10 costs more than buying one already graded."; }
    else if (profit > raw * 0.15) { k = "grade"; v = "Grade it"; w = "Expected graded value beats your cost plus fees by a clear margin."; }
    else if (profit > 0) { k = "hold"; v = "Marginal: keep it raw"; w = "Small expected gain. Probably not worth the wait and the grade risk."; }
    else { k = "raw"; v = "Keep or sell raw"; w = "Fees and grade risk outweigh the graded premium."; }
    box.dataset.v = k; $("#gv-t", el).textContent = v; $("#gv-w", el).textContent = w;
    const d = (x) => isFinite(x) ? money(Math.round(x * 100)) : "—";
    $("#gb", el).innerHTML = [["Expected value after grading", d(ev)], ["Total cost (card + fee + shipping)", d(cost)],
      [`Expected profit`, `<b class="${profit >= 0 ? "up" : "down"}">${profit >= 0 ? "+" : "−"}${d(Math.abs(profit))}</b>`],
      ["Average cost to land one PSA 10", d(chase)], ["Buy a PSA 10 outright", d(p10)]]
      .map(([l, x]) => `<div><span>${l}</span><span class="num">${x}</span></div>`).join("");
  };
  el.querySelectorAll("[data-g]").forEach((i) => i.addEventListener("input", () => { s[i.dataset.g] = i.value; save(); calc(); }));
  el.querySelectorAll("[data-cond]").forEach((b) => b.addEventListener("click", () => {
    s.cond = b.dataset.cond; s.o10 = ODDS[s.cond][0]; s.o9 = ODDS[s.cond][1];
    el.querySelectorAll("[data-cond]").forEach((x) => x.setAttribute("aria-pressed", x === b));
    $('[data-g="o10"]', el).value = s.o10; $('[data-g="o9"]', el).value = s.o9; save(); calc();
  }));
  calc();
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
    $("#prod").innerHTML = `<div class="prod-img">${imgTag(id, "", 1000, v.im)}</div>
      <div><span class="muted">${esc(gl[set.k] || "")} · ${esc(set.n)}${v.no ? " · #" + esc(v.no) : ""}${v.r ? " · " + esc(v.r) : ""}</span>
        <h1 style="font-size:clamp(26px,3.4vw,38px);margin-top:6px">${esc(base)}</h1>
        ${variants.length > 1 ? `<div id="var" style="margin-top:12px"></div>` : ""}
        <div class="muted" style="margin-top:14px">Market price</div><div class="price-big">${v.p == null ? `<span class="muted" style="font-size:.6em">No market price yet</span>` : money(v.p)}</div>
        ${v.dys && below(v.dys.p, v.p) ? `<p style="margin:6px 0 0">${BELOW} <span class="muted">Our price ${money(v.dys.p)} is ${Math.round((1 - v.dys.p / v.p) * 100)}% under market</span></p>` : ""}
        <div class="kpis">${[["7", "7 days"], ["30", "30 days"], ["90", "90 days"], ["a", `Since ${fmtShort(meta.first)}`]].map(([k, l]) => `<div class="kpi"><div class="l">${l}</div>${chg(v.ch?.[k])}</div>`).join("")}</div>
        <div class="btns">${v.dys ? `<a class="btn primary" href="${esc(v.dys.u)}">Buy at Drive Your Style · ${money(v.dys.p)}</a>`
          : `<a class="btn primary" href="mailto:customerservice@driveyourstyle.net?subject=${encodeURIComponent("Request: " + v.n)}&body=${encodeURIComponent(`Hi Drive Your Style,\n\nI'm interested in: ${v.n} (${set.n}).\nMarket price today: ${money(v.p)}\nQuantity: 1\n\nPlease let me know if you can get it.\n\nThanks!`)}">Request from Drive Your Style</a>`}
          <button class="btn" id="addcol" type="button"></button>
          <a class="btn" href="https://www.tcgplayer.com/product/${id}" target="_blank" rel="noopener">View on TCGplayer ↗</a>
          <a class="btn" href="compare.html?a=${id}:${set.id}">Compare ⇄</a>
          <button class="btn" id="watch" type="button"></button></div>
        <div class="chart-card"><div class="chart-head"><b>Price history</b><div id="range"></div></div><div class="chart" id="chart"></div>
          <p class="muted" style="font-size:12px;margin:6px 0 4px">Nightly TCGplayer market price. Gaps mean no market price was recorded that day.</p></div>
      </div>${v.t === "c" ? gradedHtml(base, set, v) : ""}${v.t === "s" ? pullsHtml(set) : moreHtml(set, id)}`;
    const ck = `${id}|${printCode(subOf(v.n))}`;
    const paintCol = () => { const n = sumOwned().get(ck) || 0; $("#addcol").textContent = n ? `✓ In collection (${n}) · add 1` : "＋ Add to collection"; };
    $("#addcol").addEventListener("click", () => {
      const c = colGet(), x = c.items.find((y) => !y.gr && `${y.id}|${printCode(subOf(y.n || ""))}` === ck);
      x ? x.qty++ : c.items.push({ id, g: set.id, n: v.n, qty: 1, paid: null });
      colSet(c); paintCol(); toast(`Added to My Collection`);
    });
    paintCol();
    if (v.t === "c") gradeCalc($("#gcalc"), v.p, `${id}|${printCode(subOf(v.n))}`);
    const paint = () => { const on = wantHas(wantKey(id, v.n)); const b = $("#watch"); b.textContent = on ? "♥ On your Want list" : "♡ Want"; b.classList.toggle("wanted", on); b.setAttribute("aria-pressed", on); };
    $("#watch").addEventListener("click", () => { wantToggle({ id, g: set.id, n: v.n, at: v.p }); paint(); });
    paint();
    getJSON("wanted.json").then((d) => { const w = (d.all || {})[`${id}`]; if (w) $("#watch").insertAdjacentHTML("afterend", `<span class="want-count">♥ ${w} collector${w > 1 ? "s" : ""} want this</span>`); }).catch(() => {});
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
    const terms = q.split(/\s+/);
    const hits = rankHits(rows, terms, (r) => alias((r[1] + " " + (meta.groups[r[2]]?.[0] || "")).toLowerCase().replace(/é/g, "e")), (r) => r[1], 10);
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

/* ---------- sneakers ---------- */
const snkLinks = (code, name) => {
  const q = encodeURIComponent(code || name);
  return `<span class="snk-resale"><a href="https://stockx.com/search?s=${q}" target="_blank" rel="noopener">StockX</a><a href="https://www.goat.com/search?query=${q}" target="_blank" rel="noopener">GOAT</a><a href="https://www.ebay.com/sch/i.html?_nkw=${q}&LH_Sold=1&LH_Complete=1" target="_blank" rel="noopener">eBay sold</a></span>`;
};
const SNK_NS = "https://abacus.jasoncameron.dev";
const voteKey = (code, dir) => `dys-snk/${code.replace(/[^A-Za-z0-9-]/g, "")}-${dir}`;
const VKEY = "dys-snk-votes";
const myVotes = () => { try { return JSON.parse(localStorage.getItem(VKEY) || "{}"); } catch { return {}; } };
const SHOE = `<svg viewBox="0 0 64 32" fill="currentColor" aria-hidden="true"><path d="M3 22c0-4 1-9 3-12 1-2 3-2 4 0 2 3 5 5 9 5 3 0 5-2 7-4l3 1c3 5 10 8 18 9 6 1 11 3 12 6v2H5c-1 0-2-1-2-2z"/><rect x="3" y="27" width="58" height="3" rx="1.5"/></svg>`;
const snkPh = (r, cls) => `<span class="${cls} ph">${SHOE}<span>${esc(r.b)}</span></span>`;
window.dysShoe = (el) => { el.outerHTML = el.dataset.ph; };
const snkImg = (im, r, cls) => im ? `<img class="${cls}" src="${esc(im)}" alt="${esc(r.n)}" loading="lazy" data-ph="${esc(snkPh(r, cls))}" onerror="dysShoe(this)">` : snkPh(r, cls);
/* Abacus allows ~30 requests per 10s per visitor, so counts load through a slow queue, only when visible. */
const abQ = []; let abRunning = false;
const abFetch = (path) => new Promise((res) => { abQ.push([path, res]); if (!abRunning) abPump(); });
function abPump() {
  const job = abQ.shift(); if (!job) { abRunning = false; return; }
  abRunning = true;
  fetch(`${SNK_NS}/${job[0]}`).then((r) => r.ok ? r.json() : (r.status === 404 ? { value: 0 } : null)).catch(() => null).then((j) => job[1](j));
  setTimeout(abPump, 380);
}
const snkCountQ = (code, dir) => abFetch(`get/${voteKey(code, dir)}`).then((j) => j ? j.value || 0 : null);
const voteSeen = typeof IntersectionObserver === "function" ? new IntersectionObserver((ents) => ents.forEach((e) => {
  if (e.isIntersecting) { voteSeen.unobserve(e.target); e.target._load?.(); }
}), { rootMargin: "200px" }) : null;
function voteBox(el, code, compact = false) {
  const draw = (up, dn) => {
    const mine = myVotes()[code], tot = (up || 0) + (dn || 0), pct = tot ? Math.round((up || 0) / tot * 100) : null;
    const btn = (d, ico, n) => `<button type="button" data-d="${d}" class="vote${mine === d ? " on" : ""}"${mine ? " disabled" : ""} aria-label="${d === "up" ? "Thumbs up" : "Thumbs down"}">${ico} <b>${n ?? "–"}</b></button>`;
    el.innerHTML = `<div class="vote-row">${btn("up", "👍", up)}${btn("dn", "👎", dn)}
      <span class="vote-note">${pct == null ? (mine ? "Thanks for voting" : compact ? "" : "Would you cop?") : `${pct}% would cop${mine && !compact ? " · you voted" : ""}`}</span></div>
      ${pct == null || compact ? "" : `<div class="vote-bar"><i style="width:${pct}%"></i></div>`}`;
    el.querySelectorAll("button[data-d]").forEach((b) => b.addEventListener("click", async () => {
      if (myVotes()[code]) return;
      const d = b.dataset.d, v = myVotes(); v[code] = d;
      try { localStorage.setItem(VKEY, JSON.stringify(v)); } catch {}
      if (d === "up") up = (up || 0) + 1; else dn = (dn || 0) + 1;
      draw(up, dn);
      const res = await fetch(`${SNK_NS}/hit/${voteKey(code, d)}`).then((r) => r.json()).catch(() => null);
      if (res?.value != null) { if (d === "up") up = res.value; else dn = res.value; draw(up, dn); }
    }));
  };
  draw(null, null);
  el._load = () => Promise.all([snkCountQ(code, "up"), snkCountQ(code, "dn")]).then(([up, dn]) => draw(up, dn));
  if (voteSeen) voteSeen.observe(el); else el._load();
}
/* "Remind me": an all-day calendar event with alerts the day before (9am) and on the morning of the drop */
const icsDate = (d, add = 0) => { const x = new Date(d + "T12:00:00"); x.setDate(x.getDate() + add); return x.toLocaleDateString("en-CA").replace(/-/g, ""); };
const icsText = (s) => String(s).replace(/[\;,]/g, (c) => "\\" + c).replace(/\n/g, "\\n");
function icsFor(r) {
  const title = `${r.n} release`, desc = `${r.cw ? r.cw + "\n" : ""}${r.c ? "Style code " + r.c + "\n" : ""}Retail ${r.r ? "$" + r.r : "TBA"}\nResale and more drops: https://market.driveyourstyle.net/sneakers.html`;
  return ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Drive Your Style//Sneaker drops//EN", "BEGIN:VEVENT",
    `UID:${(r.c || r.n).replace(/\W+/g, "")}-${r.d}@driveyourstyle.net`, `DTSTAMP:${new Date().toISOString().replace(/[-:]/g, "").slice(0, 15)}Z`,
    `DTSTART;VALUE=DATE:${icsDate(r.d)}`, `DTEND;VALUE=DATE:${icsDate(r.d, 1)}`, `SUMMARY:${icsText(title)}`, `DESCRIPTION:${icsText(desc)}`,
    "URL:https://market.driveyourstyle.net/sneakers.html",
    "BEGIN:VALARM", "TRIGGER:-PT15H", "ACTION:DISPLAY", `DESCRIPTION:${icsText(r.n + " drops tomorrow")}`, "END:VALARM",
    "BEGIN:VALARM", "TRIGGER:PT6H45M", "ACTION:DISPLAY", `DESCRIPTION:${icsText(r.n + " drops today")}`, "END:VALARM",
    "END:VEVENT", "END:VCALENDAR"].join("\r\n");
}
const gcalFor = (r) => `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(r.n + " release")}&dates=${icsDate(r.d)}/${icsDate(r.d, 1)}&details=${encodeURIComponent(`${r.cw || ""}${r.c ? " · " + r.c : ""} · Retail ${r.r ? "$" + r.r : "TBA"}\nhttps://market.driveyourstyle.net/sneakers.html`)}`;
const SNK_REL = [];
const remindHtml = (r) => { const i = SNK_REL.push(r) - 1; return `<details class="remind"><summary>🔔 Remind me</summary><div class="remind-menu">
  <a href="#" data-ics="${i}">📅 Phone calendar</a><a href="${esc(gcalFor(r))}" target="_blank" rel="noopener">Google Calendar</a></div></details>`; };
document.addEventListener("click", (e) => {
  const a = e.target.closest("[data-ics]");
  if (a) {
    const r = SNK_REL[a.dataset.ics];
    a.href = "data:text/calendar;charset=utf-8," + encodeURIComponent(icsFor(r));
    a.download = `${(r.n).replace(/[^\w]+/g, "-").replace(/^-|-$/g, "")}.ics`;
    setTimeout(() => a.closest("details")?.removeAttribute("open"), 300);
    return;
  }
  document.querySelectorAll("details.remind[open]").forEach((d) => { if (!d.contains(e.target)) d.removeAttribute("open"); });
});
const IG_DM = "https://ig.me/m/drive.yourstyle";
const snkActions = (r, { remind = true, request = false } = {}) =>
  snkLinks(r.c, r.n).replace("</span>", `${remind ? remindHtml(r) : ""}${request ? `<a class="req" href="${IG_DM}" target="_blank" rel="noopener" title="DM us the shoe and your size">🙋 Request this pair</a>` : ""}</span>`);
const VERDICT = { cop: ["Cop", "v-cop"], wear: ["Cop to wear", "v-wear"], wait: ["Wait", "v-wait"] };
const HEAT = ["", "", `<span class="badge heat">Hyped</span>`, `<span class="badge heat hot">🔥 Hot</span>`];
async function pageSneakers() {
  const [data, imgs] = await Promise.all([fetch("sneakers.json", { cache: "no-cache" }).then((r) => r.json()), getJSON("sneaker-images.json").catch(() => ({}))]);
  const imOf = (r) => r.im || (r.c && imgs[r.c]) || null;
  const today = new Date().toLocaleDateString("en-CA");
  const back = new Date(); back.setDate(back.getDate() - 14); const since = back.toLocaleDateString("en-CA");
  const rel = data.releases;
  const by = Object.fromEntries(rel.filter((r) => r.c).map((r) => [r.c, r]));
  const pickOf = Object.fromEntries(data.picks.map((p) => [p.c, p]));
  const usd = (d) => d == null ? "TBA" : "$" + d;
  const day = (d, o) => new Date(d + "T12:00:00").toLocaleDateString("en-US", o);
  $("#picks").innerHTML = data.picks.map((p) => {
    const r = by[p.c]; if (!r || r.d < today) return "";
    const [v, cls] = VERDICT[p.v] || VERDICT.wear;
    return `<div class="snk-pick"><div class="snk-pick-img">${snkImg(imOf(r), r, "pimg")}<span class="verdict ${cls}">${v}</span></div>
      <div class="snk-pick-top muted">${day(r.d, { weekday: "short", month: "short", day: "numeric" })} · ${usd(r.r)} retail</div>
      <b>${esc(r.n)}</b><span class="muted snk-cw">${esc(r.cw || "")}</span><p>${esc(p.why)}</p>
      <div class="snk-vote" data-vote="${esc(p.c)}"></div>${snkActions(r, { request: true })}</div>`;
  }).join("") || `<div class="panel empty-note">New picks are coming soon.</div>`;
  $("#picks").querySelectorAll("[data-vote]").forEach((el) => voteBox(el, el.dataset.vote));
  const past = rel.filter((r) => r.d < today && r.d >= since).sort((a, b) => b.d.localeCompare(a.d) || b.h - a.h);
  if (past.length) {
    $("#dropped-block").hidden = false;
    $("#dropped").innerHTML = past.map((r) => {
      const p = pickOf[r.c], vd = p && (VERDICT[p.v] || VERDICT.wear);
      return `<div class="scard snk-card snk-past"><span class="si">${snkImg(imOf(r), r, "pimg")}${vd ? `<span class="verdict ${vd[1]}">We said: ${vd[0]}</span>` : ""}</span>
        <span class="t">${esc(r.n)}</span><span class="pp"><span class="muted">${day(r.d, { month: "short", day: "numeric" })}</span><b>${usd(r.r)} retail</b></span>
        <span class="snk-past-cta muted">How's it trading?</span>${snkActions(r, { remind: false })}</div>`;
    }).join("");
  }
  $("#snk-src").innerHTML = `Release info last checked ${fmtDate(data.updated)} from ${data.sources.map(([n, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(n)}</a>`).join(" and ")}. Photos from Nike.com. Resale links open live searches. Not affiliated with Nike, Jordan Brand, adidas, StockX, GOAT or eBay.`;
  let brand = "all", hot = false;
  const brands = [...new Set(rel.map((r) => r.b))].sort((a, b) => rel.filter((r) => r.b === b).length - rel.filter((r) => r.b === a).length);
  const weekOf = (d) => { const x = new Date(d + "T12:00:00"); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x.toLocaleDateString("en-CA"); };
  const draw = () => {
    const list = rel.filter((r) => r.d >= today && (brand === "all" || r.b === brand) && (!hot || r.h >= 2))
      .sort((a, b) => a.d.localeCompare(b.d) || b.h - a.h);
    const weeks = new Map();
    for (const r of list) { const w = weekOf(r.d); if (!weeks.has(w)) weeks.set(w, []); weeks.get(w).push(r); }
    const thisWeek = weekOf(today);
    $("#cal").innerHTML = list.length ? [...weeks].map(([w, items]) => `<h3 class="cal-month">${w === thisWeek ? "This week" : "Week of " + day(w, { month: "long", day: "numeric" })} <small>${items.length} drop${items.length > 1 ? "s" : ""}</small></h3>
      <div class="snk-list">${items.map((r) => `<div class="snk-item${r.h === 3 ? " is-hot" : ""}"><div class="cal-date"><b>${day(r.d, { day: "numeric" })}</b><span>${day(r.d, { month: "short" })}</span></div>
        ${snkImg(imOf(r), r, "simg-s")}
        <div class="snk-body"><div class="snk-name">${esc(r.n)} ${HEAT[r.h]}</div>
        <div class="muted snk-meta">${[r.cw, r.c].filter(Boolean).map(esc).join(" · ")}<span class="snk-mprice"> · <b>${usd(r.r)}</b></span></div>
        ${r.h === 3 && r.c ? `<div class="snk-vote compact" data-cvote="${esc(r.c)}"></div>` : ""}${snkActions(r, { request: r.h >= 2 })}</div>
        <div class="snk-price"><b>${usd(r.r)}</b><span class="muted">retail</span></div></div>`).join("")}</div>`).join("")
      : `<div class="panel empty-note">No upcoming releases match.</div>`;
    $("#cal").querySelectorAll("[data-cvote]").forEach((el) => voteBox(el, el.dataset.cvote, true));
  };
  tabs($("#brand"), [["all", "All brands"], ...brands.map((b) => [b, b])], brand, (v) => { brand = v; draw(); });
  $("#hot").addEventListener("change", (e) => { hot = e.target.checked; draw(); });
  draw();
  const stock = (await getJSON("sneakers-stock.json").catch(() => [])).filter((s) => s.a !== false);
  if (stock.length) {
    $("#snk-stock-block").hidden = false;
    $("#snk-stock").innerHTML = stock.map((s) => `<div class="scard snk-card"><a class="si" href="${esc(s.u)}">${s.im ? `<img src="${esc(s.im + (s.im.includes("?") ? "&" : "?") + "width=600")}" alt="${esc(s.n)}" loading="lazy">` : ""}</a>
      <a class="t" href="${esc(s.u)}">${esc(s.n)}</a><span class="pp"><b>${money(s.p)}</b>${s.s ? `<span class="muted">Size ${esc(s.s)}</span>` : ""}</span>${snkLinks(s.c, s.n)}</div>`).join("");
  }
}

async function pageWatchlist() {
  const [meta, rows, stock, wanted] = await Promise.all([getJSON("meta.json"), getJSON("search.json"), getJSON("stock.json").catch(() => []),
    getJSON("wanted.json").catch(() => ({}))]);
  const byKey = new Map(rows.map((r) => [`${r[0]}|${printCode(subOf(r[1]))}`, r])), byId = new Map();
  rows.forEach((r) => { if (!byId.has(r[0])) byId.set(r[0], r); });
  const inStock = new Map(stock.filter((x) => x.a).map((x) => [x.id, x]));
  if (acct.enabled() && acct.signedIn()) {   // pick up wants saved on other devices
    acct.pull().then((remote) => { if (!remote?.want?.length) return; const c = colGet(), m = new Map((c.want || []).map((w) => [w.k, w]));
      remote.want.forEach((w) => { if (!m.has(w.k)) m.set(w.k, w); }); if (m.size !== (c.want || []).length) { c.want = [...m.values()]; colSet(c, false); draw(); } }).catch(() => {});
  }
  $("#acct-note").innerHTML = acct.enabled() && acct.signedIn() ? "Synced to your account." : `Saved on this device. <a href="collection.html" style="color:var(--accent)">Sign in on My Collection</a> to sync it and count toward Most wanted.`;
  const draw = () => {
    const list = wantGet().slice().reverse();
    if (!list.length) { $("#list").innerHTML = `<div class="panel empty-note">Nothing on your Want list yet. Tap <b>♡</b> on any card or product (in search, a set, or its price page) to add it.</div>`; return; }
    $("#list").innerHTML = `<div class="want-list">${list.map((w) => {
      const r = byKey.get(w.k) || byId.get(w.id), mkt = r?.[4] ?? null, st = inStock.get(w.id), since = w.at && mkt ? (mkt - w.at) / w.at * 100 : null;
      const under = w.max != null && mkt != null && mkt <= w.max, others = (wanted.all || {})[`${w.id}`];
      return `<div class="want-row${st ? " has-stock" : ""}"><a href="${prodUrl(w.id, w.g)}" class="want-img">${imgTag(w.id, "", 400)}</a>
        <div class="want-body"><a href="${prodUrl(w.id, w.g)}"><b>${esc(r?.[1] || w.n)}</b></a><span class="muted">${esc(meta.groups[w.g]?.[0] || "")}</span>
          <div class="want-price"><b>${money(mkt)}</b><span class="muted">market</span>${since != null ? chg(since) : ""}${others > 1 ? `<span class="muted">♥ ${others}</span>` : ""}</div>
          <label class="want-max">I'd pay up to $<input class="field" type="number" min="0" step="0.01" inputmode="decimal" value="${w.max != null ? (w.max / 100).toFixed(2) : ""}" placeholder="${mkt != null ? (mkt / 100).toFixed(2) : ""}" data-max="${esc(w.k)}"></label>
          <div class="want-tags">${st ? `<a class="tag stock" href="${esc(st.u)}">In stock at Drive Your Style · ${money(st.p)} →</a>` : ""}${under ? `<span class="tag deal">Market is under your max</span>` : ""}</div></div>
        <button class="btn icon want-x" type="button" data-rm="${esc(w.k)}" aria-label="Remove from Want list">✕</button></div>`; }).join("")}</div>`;
    $("#list").querySelectorAll("[data-max]").forEach((el) => el.addEventListener("change", () => {
      const c = colGet(), w = (c.want || []).find((x) => x.k === el.dataset.max); if (!w) return;
      w.max = el.value === "" ? null : Math.round(Number(el.value) * 100); colSet(c); toast("Saved"); setTimeout(draw);
    }));
    $("#list").querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", () => { const c = colGet(); c.want = (c.want || []).filter((x) => x.k !== b.dataset.rm); colSet(c); draw(); }));
  };
  draw();
}

/* ---------- demand report (owner): what collectors want, anonymous ---------- */
async function pageDemand() {
  const [meta, d] = await Promise.all([getJSON("meta.json"), getJSON("demand.json").catch(() => null)]);
  if (!d || !d.items?.length) { $("#list").innerHTML = `<div class="panel empty-note">No Want list data yet. It fills in as signed-in collectors tap ♡ on cards.</div>`; return; }
  let f = "all";
  $("#sum").textContent = `${d.wanters} collector${d.wanters === 1 ? "" : "s"} with a Want list · ${d.items.length} different items wanted · updated ${new Date(d.updated).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`;
  const draw = () => {
    const list = d.items.filter((i) => f === "all" || (f === "stock" ? i.st : f === "nostock" ? !i.st : i.mx != null));
    $("#list").innerHTML = `<div class="table-wrap"><table><thead><tr><th>#</th><th>Item</th><th class="num">Want it</th><th class="num">Typical max</th><th class="num">Market</th><th class="num">Your stock</th></tr></thead><tbody>
      ${list.map((i, ix) => `<tr><td>${ix + 1}</td><td class="title"><a href="${prodUrl(i.id, i.g)}">${imgTag(i.id, "")}<span>${esc(i.n)}<span class="muted" style="display:block;font-size:12px">${esc(meta.groups[i.g]?.[0] || "")}</span></span></a></td>
        <td class="num"><b>${i.c}</b></td><td class="num">${i.mx != null ? `${money(i.mx)}<span class="muted" style="display:block;font-size:11px">${i.nm} set a max</span>` : "—"}</td>
        <td class="num">${money(i.m)}</td><td class="num">${i.st ? `<a href="${esc(i.st.u)}">${money(i.st.p)}</a>${i.st.p && i.mx != null && i.st.p > i.mx ? `<span class="muted" style="display:block;font-size:11px">above their max</span>` : ""}` : `<span class="tag need">Not stocked</span>`}</td></tr>`).join("")}
      </tbody></table></div>`;
  };
  tabs($("#f"), [["all", "All"], ["nostock", "Not in stock"], ["stock", "In stock"], ["max", "Has a max price"]], f, (v) => { f = v; draw(); });
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
    "Option1 name", "Option1 value", "Price", "Cost per item", "Charge tax", "Inventory tracker", "Inventory quantity", "Continue selling when out of stock",
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
      "Condition", sealed ? "Unopened" : "Near Mint", (Math.max(p.p, p.cost ? Math.round(p.cost * 100) : 0) / 100).toFixed(2), p.cost != null ? p.cost.toFixed(2) : "", "TRUE", "shopify", p.qty, "DENY",
      "TRUE", "manual", img(p.id, 1000), "1", title, `${title} | Drive Your Style`, seoDesc.slice(0, 320)]);
  }
  return rows.map((r) => r.map(csvCell).join(",")).join("\r\n");
}

const GH_REPO = "VapeZz/dys-market";
const ghToken = { get() { try { return localStorage.getItem("dys-gh-token") || ""; } catch { return ""; } },
  set(v) { try { v ? localStorage.setItem("dys-gh-token", v) : localStorage.removeItem("dys-gh-token"); } catch {} } };
const gh = (path, opts = {}) => fetch(`https://api.github.com/repos/${GH_REPO}${path}`, { ...opts,
  headers: { Accept: "application/vnd.github+json", Authorization: `Bearer ${ghToken.get()}`, "Content-Type": "application/json" } });

async function pageImporter() {
  const [meta, sets, stockMap, report] = await Promise.all([getJSON("meta.json"), getJSON("sets.json"),
    getJSON("store-prices.json").catch(() => ({})), getJSON("sync-report.json").catch(() => null)]);
  const handleOf = {}; for (const [h, r] of Object.entries(stockMap)) handleOf[r.id] = h;
  const justAdded = new Set(); // imported this session; re-adding them restocks (matched by SKU)
  const gl = Object.fromEntries(meta.games.map((g) => [g.slug, g.label]));
  let game = "pokemon", kind = "s", minP = 0, q = "", set = null;
  const picks = new Map();
  const keyOf = (i) => `${i.id}|${i.n}`;

  /* connection */
  const paintConn = () => {
    const on = !!ghToken.get();
    $("#conn-state").innerHTML = on ? `<span class="chg up">● Connected</span>` : `<span class="chg down">● Not connected</span>`;
    $("#conn-form").hidden = on; $("#conn-off").hidden = !on;
    $("#add").textContent = on ? "Add to store" : "Connect to add to store";
  };
  $("#conn-save").addEventListener("click", async () => {
    const v = $("#conn-token").value.trim(); if (!v) return;
    ghToken.set(v); const r = await gh("/actions/workflows/import.yml").catch(() => null);
    if (!r || !r.ok) { ghToken.set(""); $("#conn-msg").textContent = "That key didn't work. Check it has Actions: read and write on dys-market."; }
    else { $("#conn-msg").textContent = ""; $("#conn-token").value = ""; }
    paintConn();
  });
  $("#conn-off").addEventListener("click", () => { ghToken.set(""); paintConn(); });

  /* held report */
  if (report && report.held && report.held.length) {
    $("#held").hidden = false;
    $("#held-list").innerHTML = report.held.map((h) => `<li><a href="https://admin.shopify.com/store/s11bjx-1e/products/${esc(h.pid)}" target="_blank" rel="noopener">${esc(h.t)}</a>: yours ${money(h.have)}, market ${money(h.mkt)}. ${esc(h.why)}</li>`).join("");
  }

  const fillSets = () => {
    const list = sets.filter((s) => s.k === game);
    $("#set").innerHTML = list.map((s) => `<option value="${s.id}">${esc(s.n)}${s.pub ? " · " + s.pub.slice(0, 7) : ""}</option>`).join("");
    loadSet(list[0]?.id);
  };
  const loadSet = async (gid) => { if (!gid) return; set = await getJSON(`set/${gid}.json`); draw(); };
  const summary = () => {
    const all = [...picks.values()], n = all.length, re = all.filter((p) => p.handle).length;
    const total = all.reduce((a, p) => a + p.p * p.qty, 0);
    $("#count").textContent = n ? `${n - re} new · ${re} restock · ${money(total)} at market` : "Nothing selected yet";
    $("#add").disabled = !n && !!ghToken.get(); $("#dl").hidden = !n || !!all.find((p) => p.handle); $("#clear").disabled = !n;
  };
  const draw = () => {
    if (!set) return;
    const items = set.items.filter((i) => i.t === kind && i.p != null && i.p >= minP * 100 && (!q || i.n.toLowerCase().includes(q)));
    $("#rows").innerHTML = items.length ? `<div class="table-wrap"><table><thead><tr><th style="width:36px"><input type="checkbox" id="all" aria-label="Select all"></th><th>${kind === "s" ? "Product" : "Card"}</th><th class="num">Market</th><th class="num">Qty</th></tr></thead><tbody>
      ${items.map((i, ix) => { const k = keyOf(i), on = picks.get(k), have = handleOf[i.id] || justAdded.has(i.id);
        return `<tr><td><input type="checkbox" data-ix="${ix}" ${on ? "checked" : ""} aria-label="Select ${esc(i.n)}"></td>
        <td class="title"><span style="display:flex;align-items:center;gap:10px">${imgTag(i.id, "")}<span>${esc(i.n)}${i.r ? `<span class="muted" style="display:block;font-size:12px">${esc(i.r)}</span>` : ""}${have ? ` <span class="badge">In store · restock</span>` : ""}</span></span></td>
        <td class="num"><b>${money(i.p)}</b></td>
        <td class="num"><div style="display:flex;flex-direction:column;gap:4px;align-items:flex-end"><input class="field" type="number" min="0" max="999" value="${on ? on.qty : 1}" data-q="${ix}" aria-label="Quantity" style="width:72px">
        ${have ? "" : `<input class="field" type="number" min="0" step="0.01" placeholder="cost $" value="${on && on.cost != null ? on.cost : ""}" data-c="${ix}" aria-label="Your cost (optional)" style="width:72px">`}</div></td></tr>`; }).join("")}
      </tbody></table></div>` : `<div class="panel empty-note">No ${kind === "s" ? "sealed products" : "cards"} match in this set.</div>`;
    const read = (ix) => ({ qty: Math.max(0, Number($(`[data-q="${ix}"]`).value) || 0), cost: $(`[data-c="${ix}"]`)?.value ? Number($(`[data-c="${ix}"]`).value) : null });
    const pick = (i, ix) => {
      const { qty, cost } = read(ix), sub = (i.n.match(/ \(([^)]+)\)$/) || [, "Normal"])[1];
      return { id: i.id, n: i.n, t: i.t, p: i.p, r: i.r, k: set.k, sub: i.t === "s" ? "Normal" : sub, setName: set.n, gameLabel: gl[set.k] || set.k,
        qty, cost, handle: handleOf[i.id] || null };
    };
    $("#rows").querySelectorAll("[data-ix]").forEach((cb) => cb.addEventListener("change", () => {
      const i = items[+cb.dataset.ix]; cb.checked ? picks.set(keyOf(i), pick(i, +cb.dataset.ix)) : picks.delete(keyOf(i)); summary();
    }));
    $("#rows").querySelectorAll("[data-q],[data-c]").forEach((inp) => inp.addEventListener("input", () => {
      const ix = +(inp.dataset.q ?? inp.dataset.c), i = items[ix];
      if (picks.has(keyOf(i))) { picks.set(keyOf(i), pick(i, ix)); summary(); }
    }));
    $("#all")?.addEventListener("change", (e) => {
      items.forEach((i, ix) => { e.target.checked ? picks.set(keyOf(i), pick(i, ix)) : picks.delete(keyOf(i)); });
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

  const status = (html) => { $("#run").hidden = false; $("#run").innerHTML = html; };
  $("#add").addEventListener("click", async () => {
    if (!ghToken.get()) { $("#conn").open = true; $("#conn-token").focus(); return; }
    const all = [...picks.values()]; if (!all.length) return;
    if (all.some((p) => !p.handle && p.qty === 0) && !confirm("Some new products have quantity 0. They'll be listed as sold out. Continue?")) return;
    const items = all.map((p) => p.handle ? { handle: p.handle, qty: p.qty } : { id: p.id, sub: p.sub, qty: p.qty, ...(p.cost != null ? { cost: p.cost } : {}) });
    $("#add").disabled = true;
    const lastRun = async () => (await gh("/actions/workflows/import.yml/runs?per_page=1").then((x) => x.json()).catch(() => null))?.workflow_runs?.[0];
    const before = (await lastRun())?.id || 0;
    status(`<b>Sending ${items.length} item${items.length === 1 ? "" : "s"} to your store…</b>`);
    const r = await gh("/actions/workflows/import.yml/dispatches", { method: "POST",
      body: JSON.stringify({ ref: "main", inputs: { items: JSON.stringify(items), status: $("#status").value.toUpperCase() } }) }).catch(() => null);
    if (!r || r.status !== 204) { status(`<b class="chg down">Couldn't start the import.</b> ${r ? `GitHub said ${r.status}.` : "Check your connection."} Try again or reconnect.`); $("#add").disabled = false; return; }
    const sentNew = all.filter((p) => !p.handle);
    picks.clear(); draw(); summary();
    for (let t = 0; t < 120; t++) {
      await new Promise((res) => setTimeout(res, 5000));
      const latest = await lastRun();
      const run = latest && latest.id > before ? latest : null;
      if (!run) { status(`<b>Waiting for the import to start…</b>`); continue; }
      if (run.status !== "completed") { status(`<b>Adding products to your store…</b> <span class="muted">This usually takes about a minute.</span>`); continue; }
      if (run.conclusion === "success") { sentNew.forEach((p) => justAdded.add(p.id)); draw(); }
      status(run.conclusion === "success"
        ? `<b class="chg up">Done. Your products are in the store.</b> <a href="${esc(run.html_url)}" target="_blank" rel="noopener" style="color:var(--accent)">See exactly what was added →</a>`
        : `<b class="chg down">The import hit a problem.</b> <a href="${esc(run.html_url)}" target="_blank" rel="noopener" style="color:var(--accent)">See details →</a>`);
      summary();
      return;
    }
    status(`<b>Still running.</b> <a href="https://github.com/${GH_REPO}/actions/workflows/import.yml" target="_blank" rel="noopener" style="color:var(--accent)">Check progress →</a>`);
  });
  paintConn(); fillSets(); summary();
}

/* ---------- My Collection ---------- */
const CKEY = "dys-collection";
const colGet = () => { try { return JSON.parse(localStorage.getItem(CKEY)) || { name: "", items: [] }; } catch { return { name: "", items: [] }; } };
const colSet = (c, stamp = true) => { if (stamp) c.updated = Date.now(); try { localStorage.setItem(CKEY, JSON.stringify(c)); } catch {} if (stamp) acct.push(c); };

const CAM = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/></svg>`;
/* ---------- your own card photos (kept on this device, outside the synced collection) ---------- */
const photos = (() => {
  let dbp = null;
  const open = () => dbp ||= new Promise((res, rej) => {
    if (!("indexedDB" in window)) return rej(new Error("no idb"));
    const r = indexedDB.open("dys-photos", 1);
    r.onupgradeneeded = () => r.result.createObjectStore("p");
    r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
  });
  const tx = (mode, fn) => open().then((db) => new Promise((res, rej) => {
    const t = db.transaction("p", mode), q = fn(t.objectStore("p"));
    t.oncomplete = () => res(q && q.result); t.onerror = () => rej(t.error);
  }));
  return {
    get: (k) => tx("readonly", (s) => s.get(k)).catch(() => null),
    put: (k, blob) => tx("readwrite", (s) => s.put(blob, k)),
    del: (k) => tx("readwrite", (s) => s.delete(k)).catch(() => {}),
  };
})();
const shrinkPhoto = (file) => new Promise((res, rej) => {
  const u = URL.createObjectURL(file), im = new Image();
  im.onload = () => {
    const k = Math.min(1, 1000 / Math.max(im.naturalWidth, im.naturalHeight)), c = document.createElement("canvas");
    c.width = Math.round(im.naturalWidth * k); c.height = Math.round(im.naturalHeight * k);
    c.getContext("2d").drawImage(im, 0, 0, c.width, c.height); URL.revokeObjectURL(u);
    c.toBlob((b) => b ? res(b) : rej(new Error("encode")), "image/jpeg", 0.85);
  };
  im.onerror = () => { URL.revokeObjectURL(u); rej(new Error("decode")); };
  im.src = u;
});

/* ---------- customer accounts (Shopify Customer Account API, public client + PKCE) ---------- */
const ACCT = {
  clientId: "c51d986b-2da8-4405-96a5-a0f4f97e2d75", // Headless channel > Customer Account API > Client ID
  shopId: "73346351331",
  apiVersion: "2026-01",
  redirect: "https://market.driveyourstyle.net/collection.html",
};
const acct = (() => {
  const auth = `https://shopify.com/authentication/${ACCT.shopId}`;
  const api = `https://shopify.com/${ACCT.shopId}/account/customer/api/${ACCT.apiVersion}/graphql`;
  const K = "dys-acct";
  const get = () => { try { return JSON.parse(localStorage.getItem(K)) || null; } catch { return null; } };
  const put = (v) => { try { v ? localStorage.setItem(K, JSON.stringify(v)) : localStorage.removeItem(K); } catch {} };
  const rnd = (n = 32) => { const a = new Uint8Array(n); crypto.getRandomValues(a); return btoa(String.fromCharCode(...a)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); };
  const sha = async (v) => btoa(String.fromCharCode(...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(v))))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const form = (o) => new URLSearchParams(o).toString();
  const tokenReq = async (body) => {
    const r = await fetch(`${auth}/oauth/token`, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: form(body) });
    if (!r.ok) throw new Error(`token ${r.status}`);
    const t = await r.json();
    const cur = get() || {};
    put({ ...cur, access: t.access_token, refresh: t.refresh_token || cur.refresh, idToken: t.id_token || cur.idToken, exp: Date.now() + (t.expires_in || 3600) * 1000 - 60000 });
  };
  const token = async () => {
    const a = get(); if (!a) return null;
    if (a.exp > Date.now()) return a.access;
    if (!a.refresh) { put(null); return null; }
    try { await tokenReq({ grant_type: "refresh_token", client_id: ACCT.clientId, refresh_token: a.refresh }); return get().access; }
    catch { put(null); return null; }
  };
  const gql = async (query, variables = {}) => {
    const t = await token(); if (!t) throw new Error("signed out");
    const r = await fetch(api, { method: "POST", headers: { "Content-Type": "application/json", Authorization: t }, body: JSON.stringify({ query, variables }) });
    const j = await r.json(); if (j.errors) throw new Error(JSON.stringify(j.errors).slice(0, 200)); return j.data;
  };
  let pushTimer = null;
  return {
    enabled: () => !!ACCT.clientId,
    signedIn: () => !!get(),
    info: () => get(),
    async signIn() {
      const verifier = rnd(48), state = rnd(16), nonce = rnd(16);
      try { sessionStorage.setItem("dys-pkce", JSON.stringify({ verifier, state })); } catch {}
      const u = new URL(`${auth}/oauth/authorize`);
      Object.entries({ scope: "openid email customer-account-api:full", client_id: ACCT.clientId, response_type: "code", redirect_uri: ACCT.redirect,
        state, nonce, code_challenge: await sha(verifier), code_challenge_method: "S256" }).forEach(([k, v]) => u.searchParams.set(k, v));
      location.href = u.toString();
    },
    async finish() {   // returns true if this page load completed a sign-in
      const qs = new URLSearchParams(location.search), code = qs.get("code");
      if (!code) return false;
      let saved = {}; try { saved = JSON.parse(sessionStorage.getItem("dys-pkce") || "{}"); sessionStorage.removeItem("dys-pkce"); } catch {}
      history.replaceState(null, "", location.pathname + location.hash);
      if (!saved.verifier || qs.get("state") !== saved.state) throw new Error("Sign-in expired. Please try again.");
      await tokenReq({ grant_type: "authorization_code", client_id: ACCT.clientId, redirect_uri: ACCT.redirect, code, code_verifier: saved.verifier });
      const d = await gql(`query { customer { id firstName emailAddress { emailAddress } } }`);
      put({ ...get(), id: d.customer.id, name: d.customer.firstName || "", email: d.customer.emailAddress?.emailAddress || "" });
      return true;
    },
    signOut() {
      const a = get(); put(null);
      if (a?.idToken) location.href = `${auth}/logout?id_token_hint=${encodeURIComponent(a.idToken)}&post_logout_redirect_uri=${encodeURIComponent(ACCT.redirect)}`;
      else location.reload();
    },
    async pull() {
      const d = await gql(`query { customer { id metafield(namespace: "dys", key: "binder") { value } } }`);
      try { return d.customer.metafield ? JSON.parse(d.customer.metafield.value) : null; } catch { return null; }
    },
    push(c) {
      if (!ACCT.clientId || !get()) return;
      clearTimeout(pushTimer);
      pushTimer = setTimeout(async () => {
        try {
          const a = get();
          const r = await gql(`mutation($m: [MetafieldsSetInput!]!) { metafieldsSet(metafields: $m) { userErrors { message } } }`,
            { m: [{ ownerId: a.id, namespace: "dys", key: "binder", type: "json", value: JSON.stringify({ name: c.name || "", updated: c.updated || Date.now(), items: c.items,
              alias: c.alias || "", pub: !!c.pub, likes: c.likes || [], follows: c.follows || [], want: (c.want || []).map(({ k, id, g, n, at, max, ts }) => ({ k, id, g, n, at, max, ts })) }) }] });
          const e = r.metafieldsSet.userErrors; document.dispatchEvent(new CustomEvent("dys-sync", { detail: e.length ? "error" : "ok" }));
        } catch { document.dispatchEvent(new CustomEvent("dys-sync", { detail: "error" })); }
      }, 800);
    },
  };
})();
const subOf = (n) => (n.match(/ \(([^)]+)\)$/) || [, "Normal"])[1];
const b64e = (o) => btoa(unescape(encodeURIComponent(JSON.stringify(o)))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const b64d = (t) => JSON.parse(decodeURIComponent(escape(atob(t.replace(/-/g, "+").replace(/_/g, "/")))));

/* ---------- collectors: public binders, likes, follows ----------
   Your likes / follows live in your binder (synced to your account); a job tallies everyone's every 30 minutes. */
const ALIAS_OK = /^[A-Za-z0-9_.\- ]{3,20}$/;
const cleanAlias = (v) => String(v || "").replace(/^@/, "").replace(/\s+/g, " ").trim();
const myPid = async () => { const a = acct.info(); if (!a?.id) return null;
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode("dys:" + a.id));
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 12); };
const social = {
  has: (kind, pid) => (colGet()[kind] || []).includes(pid),
  /* counts from the last tally, plus your own change if you made it after that tally */
  count: (kind, pid, base, tallied) => { const c = colGet(), t = (c.socialAt || {})[`${kind}:${pid}`] || 0, on = (c[kind] || []).includes(pid);
    return Math.max(0, base + (t > tallied ? (on ? 1 : -1) : 0)); },
  async toggle(kind, pid) {
    if (!acct.enabled() || !acct.signedIn()) { toast("Sign in on My Collection to like and follow collectors"); setTimeout(() => { location.href = "collection.html"; }, 1400); return null; }
    if (pid === await myPid()) { toast("That's your binder 🙂"); return null; }
    const c = colGet(), list = new Set(c[kind] || []), on = !list.has(pid);
    on ? list.add(pid) : list.delete(pid);
    c[kind] = [...list].slice(-500); c.socialAt = { ...(c.socialAt || {}), [`${kind}:${pid}`]: Date.now() };
    colSet(c); return on;
  },
};
const HEART = (on) => `<svg viewBox="0 0 24 24" width="16" height="16" fill="${on ? "currentColor" : "none"}" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 21s-7.5-4.6-9.6-9.2C.9 8.4 3 4.5 6.8 4.5c2.1 0 3.6 1.1 5.2 3 1.6-1.9 3.1-3 5.2-3 3.8 0 5.9 3.9 4.4 7.3C19.5 16.4 12 21 12 21z"/></svg>`;
function socialButtons(el, prof, tallied) {
  const paint = () => {
    const liked = social.has("likes", prof.p), fol = social.has("follows", prof.p);
    el.innerHTML = `<button type="button" class="soc-btn${liked ? " on" : ""}" data-k="likes" aria-pressed="${liked}">${HEART(liked)} <b>${social.count("likes", prof.p, prof.l || 0, tallied)}</b><span>${liked ? "Liked" : "Like"}</span></button>
      <button type="button" class="soc-btn follow${fol ? " on" : ""}" data-k="follows" aria-pressed="${fol}"><b>${social.count("follows", prof.p, prof.f || 0, tallied)}</b><span>${fol ? "Following" : "Follow"}</span></button>`;
    el.querySelectorAll("[data-k]").forEach((b) => b.addEventListener("click", async (e) => { e.preventDefault(); e.stopPropagation(); if (await social.toggle(b.dataset.k, prof.p) != null) paint(); }));
  };
  paint();
}

/* graded slabs: each grade is its own line in the collection, valued at the owner's number (eBay sold is one tap away) */
const GRADES = [["PSA", ["10", "9", "8", "7", "6", "5"]], ["CGC", ["10 Pristine", "10", "9.5", "9", "8.5", "8"]], ["BGS", ["10 Black Label", "10", "9.5", "9", "8.5"]],
  ["SGC", ["10", "9.5", "9", "8"]], ["TAG", ["10", "9", "8"]], ["ACE", ["10", "9", "8"]]];
const gradeOpts = (cur) => `<option value=""${cur ? "" : " selected"}>Raw</option>` + GRADES.map(([co, gs]) => `<optgroup label="${co}">${gs.map((g) => { const v = `${co} ${g}`; return `<option value="${v}"${v === cur ? " selected" : ""}>${v}</option>`; }).join("")}</optgroup>`).join("") + `<option value="Other slab"${cur === "Other slab" ? " selected" : ""}>Other slab</option>`;
const cleanCard = (n) => n.replace(/ \((Holofoil|Normal|Foil|Reverse Holofoil)\)$/, "").replace(/ - (\S+)$/, " $1");
const soldUrl = (name, gr) => `https://www.ebay.com/sch/i.html?_nkw=${encodeURIComponent(`${cleanCard(name)} ${gr === "Other slab" ? "graded" : gr}`)}&LH_Sold=1&LH_Complete=1&_sop=13`;
const sumOwned = () => { const m = new Map(); for (const x of colGet().items) { const k = `${x.id}|${printCode(subOf(x.n || ""))}`; m.set(k, (m.get(k) || 0) + x.qty); } return m; };

/* full-screen card viewer for binders: swipe/arrow through cards */
function cardView(list, start, opts = {}) {
  let i = start;
  const box = document.createElement("div");
  box.className = "cview"; box.setAttribute("role", "dialog"); box.setAttribute("aria-modal", "true");
  const paint = () => {
    const c = list[i], set = opts.setName ? opts.setName(c.g) : "";
    box.innerHTML = `<div class="cview-in"><button type="button" class="cview-x" aria-label="Close">✕</button>
      <div class="cview-img${c.t === "s" ? " sealed" : ""}">${imgTag(c.id, "", 1000)}${c.gr ? `<span class="slab-badge">${esc(c.gr)}</span>` : ""}</div>
      <div class="cview-meta"><b>${esc(c.name)}</b><span class="muted">${esc(set)}${c.qty > 1 ? ` · ×${c.qty}` : ""}</span>
        <span class="cview-val">${money(c.mkt)}<small class="muted">${c.gr ? (c.est ? " raw price" : " owner's value") : " market"}</small></span>
        <span class="cview-links"><a href="${prodUrl(c.id, c.g)}">Price history →</a>${c.gr ? `<a href="${esc(soldUrl(c.name, c.gr))}" target="_blank" rel="noopener">eBay sold ${esc(c.gr)} →</a>` : ""}</span></div>
      ${list.length > 1 ? `<button type="button" class="cview-nav prev" aria-label="Previous">‹</button><button type="button" class="cview-nav next" aria-label="Next">›</button><span class="cview-count">${i + 1} / ${list.length}</span>` : ""}</div>`;
    const ph = opts.photo && opts.photo(c); if (ph) ph.then((u) => { if (u) $(".cview-img img", box).src = u; });
  };
  const go = (d) => { i = (i + d + list.length) % list.length; paint(); };
  const close = () => { box.remove(); document.removeEventListener("keydown", key); document.body.style.overflow = ""; };
  const key = (e) => { if (e.key === "Escape") close(); else if (e.key === "ArrowRight") go(1); else if (e.key === "ArrowLeft") go(-1); };
  box.addEventListener("click", (e) => {
    if (e.target === box || e.target.closest(".cview-x")) close();
    else if (e.target.closest(".prev")) go(-1); else if (e.target.closest(".next")) go(1);
  });
  let x0 = null;
  box.addEventListener("touchstart", (e) => { x0 = e.touches[0].clientX; }, { passive: true });
  box.addEventListener("touchend", (e) => { if (x0 == null) return; const dx = e.changedTouches[0].clientX - x0; if (Math.abs(dx) > 50) go(dx < 0 ? 1 : -1); x0 = null; });
  document.addEventListener("keydown", key);
  document.body.style.overflow = "hidden";
  paint(); document.body.appendChild(box);
}

async function pageCollection() {
  const [meta, rows] = await Promise.all([getJSON("meta.json"), getJSON("search.json")]);
  const byKey = new Map(rows.map((r) => [`${r[0]}|${printCode(subOf(r[1]))}`, r]));
  const setName = (g) => meta.groups[g]?.[0] || "";
  const viewPid = (params.get("p") || "").replace(/[^a-f0-9]/g, "").slice(0, 12);
  const shared = location.hash.startsWith("#c=") || !!viewPid;
  let col = colGet(), prof = null, tallied = 0;
  if (viewPid) {
    [prof, tallied] = await Promise.all([getJSON(`showcase/${viewPid}.json`).catch(() => null), getJSON("showcase.json").then((d) => d.updated).catch(() => 0)]);
    col = prof ? { name: prof.bn || "", items: prof.items } : { name: "", items: [] };
    $("#mine").hidden = true; $("#tools").hidden = true;
    document.title = prof ? `${prof.a} · Collectors · Drive Your Style` : "Collector not found · Drive Your Style";
    $("#shared-note").hidden = false;
    $("#shared-note").innerHTML = prof ? `<span class="prof-line">${col.name ? `${esc(col.name)} · ` : ""}<a href="collectors.html" style="color:var(--accent)">All collectors →</a></span><span class="soc-row" id="prof-soc"></span>`
      : viewPid === await myPid() ? `Your public page is being set up. It goes live within 30 minutes of turning on <b>Show my binder</b>. <a href="collection.html" style="color:var(--accent)">Back to my collection →</a>`
      : `This binder isn't public. <a href="collectors.html" style="color:var(--accent)">Browse collectors →</a>`;
    if (prof) socialButtons($("#prof-soc"), prof, tallied);
  } else if (shared) {
    try { const d = b64d(location.hash.slice(3)); col = { name: d.n || "", items: (d.i || []).map(([id, g, qty, code, gr, gv]) => ({ id, g, qty, code, ...(gr ? { gr, gv: gv ?? null } : {}) })) }; }
    catch { col = { name: "", items: [] }; }
    $("#mine").hidden = true; $("#shared-note").hidden = false;
  }
  const keyOf = (it) => `${it.id}|${it.code ?? printCode(subOf(it.n || ""))}${it.gr ? "|" + it.gr : ""}`;
  const rawKey = (it) => `${it.id}|${it.code ?? printCode(subOf(it.n || ""))}`;
  const changes = {}, series = {}, setCards = {};
  let dates = null, cq = "", csort = "value", grouped = false, range = "90";
  let view = shared ? "binder" : (() => { try { return localStorage.getItem("dys-cview") || "list"; } catch { return "list"; } })();
  let shownNow = [];
  const loadChanges = async () => {
    const gids = [...new Set(col.items.map((i) => i.g))].filter((g) => !setCards[g]).slice(0, 60);
    await Promise.all(gids.map((g) => getJSON(`set/${g}.json`).then((d) => {
      dates = dates || d.dates;
      setCards[g] = new Set(d.items.filter((x) => x.t === "c").map((x) => x.id)).size;
      d.items.forEach((x) => { const k = `${x.id}|${printCode(subOf(x.n))}`; changes[k] = x.ch; if (x.s) series[k] = { s: x.s, dates: d.dates }; });
    }).catch(() => {})));
  };
  const plot = () => {
    if (!dates || !col.items.length) { $("#cchart-wrap").hidden = true; return; }
    const vals = dates.map((d) => {
      let sum = 0, any = false;
      for (const it of col.items) {
        if (it.gr && it.gv != null) { sum += it.gv * it.qty; any = true; continue; }
        const sr = series[rawKey(it)]; if (!sr) continue;
        let j = sr.dates.indexOf(d), v = null; while (j >= 0 && v == null) v = sr.s[j--];
        if (v != null) { sum += v * it.qty; any = true; }
      }
      return any ? sum : null;
    });
    $("#cchart-wrap").hidden = false;
    lineChart($("#cchart"), dates, vals, range);
  };
  const save = () => { if (!shared) colSet(col); };

  const draw = () => {
    const all = col.items.map((it, ix) => { const r = byKey.get(rawKey(it)); const raw = r?.[4] ?? null;
      return { ...it, ix, name: it.n || r?.[1] || `#${it.id}`, raw, mkt: it.gr && it.gv != null ? it.gv : raw, est: !!it.gr && it.gv == null, ch: it.gr ? null : changes[rawKey(it)], t: r?.[3] }; });
    const items = all.slice().sort((a, b) => csort === "name" ? a.name.localeCompare(b.name) : csort === "set" ? setName(a.g).localeCompare(setName(b.g)) || (b.mkt || 0) - (a.mkt || 0)
      : csort === "recent" ? b.ix - a.ix : (b.mkt || 0) * b.qty - (a.mkt || 0) * a.qty);
    const value = items.reduce((a, i) => a + (i.mkt || 0) * i.qty, 0);
    const shown = items.filter((i) => !cq || (i.name + " " + setName(i.g)).toLowerCase().includes(cq));
    // per-set completion (unique cards owned / cards in set)
    const bySet = new Map();
    for (const i of all) { const b = bySet.get(i.g) || { cards: new Set(), value: 0 }; if (i.t === "c") b.cards.add(i.id); b.value += (i.mkt || 0) * i.qty; bySet.set(i.g, b); }
    const sets = [...bySet].map(([g, b]) => ({ g, have: b.cards.size, total: setCards[g] || 0, value: b.value })).filter((x) => x.have).sort((a, b) => b.have / (b.total || 1) - a.have / (a.total || 1));
    $("#csets").innerHTML = sets.length ? `<h2 style="font-size:20px;margin:0 0 10px">Set progress</h2><div class="cset-list">${sets.map((x) => { const p = x.total ? Math.round(x.have / x.total * 100) : 0;
      return `<a class="cset" href="set.html?id=${x.g}"><span class="cset-top"><b>${esc(setName(x.g))}</b><span>${x.have}/${x.total || "?"} · ${p}%</span></span><span class="bar"><i style="width:${Math.max(2, p)}%"></i></span><span class="muted" style="font-size:12px">${money(x.value)} in this set</span></a>`; }).join("")}</div>` : "";
    const paidItems = items.filter((i) => i.paid != null);
    const paid = paidItems.reduce((a, i) => a + i.paid * i.qty, 0);
    const paidValue = paidItems.reduce((a, i) => a + (i.mkt || 0) * i.qty, 0);
    const count = items.reduce((a, i) => a + i.qty, 0);
    $("#title").textContent = prof ? prof.a : col.name || (shared ? "Shared collection" : "My collection");
    $("#stats").innerHTML = (prof ? [
      [money(value), "Collection value"], [count.toLocaleString(), "Items"], [String(new Set(items.map((i) => i.g)).size), "Sets"],
      [String(items.filter((i) => i.gr).reduce((a, i) => a + i.qty, 0)), "Graded slabs"],
    ] : [
      [money(value), items.some((i) => i.gr) ? "Collection value" : "Market value"],
      [count.toLocaleString(), "Items"],
      [paidItems.length ? money(paid) : "—", "You paid"],
      [paidItems.length ? `${paidValue - paid >= 0 ? "+" : "−"}${money(Math.abs(paidValue - paid))}` : "—", paidItems.length && paid ? `Gain ${((paidValue - paid) / paid * 100).toFixed(1)}%` : "Gain / loss"],
    ]).map(([v, l]) => `<div class="stat"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
    let lastG = null;
    const grpRow = (i) => { if (!grouped || i.g === lastG) return ""; lastG = i.g; const st = sets.find((x) => x.g === i.g);
      return `<tr class="grp"><td colspan="6"><b>${esc(setName(i.g))}</b>${st ? ` <span class="muted">· ${st.have}/${st.total || "?"} cards</span>` : ""}</td></tr>`; };
    const list = grouped ? shown.slice().sort((a, b) => setName(a.g).localeCompare(setName(b.g)) || (b.mkt || 0) - (a.mkt || 0)) : shown;
    $("#list").innerHTML = list.length ? `<div class="table-wrap"><table><thead><tr><th>Item</th><th class="num">Qty${shared ? "" : " · paid"}</th><th class="num">Market</th><th class="num">Value</th><th class="num hide-sm">Change</th>${shared ? "" : "<th></th>"}</tr></thead><tbody>
      ${list.map((i) => `${grpRow(i)}<tr><td class="title">${shared ? "" : `<div class="tline"><label class="ph-wrap" data-ph="${esc(keyOf(i))}" title="Add your own photo">${imgTag(i.id, "")}<span class="cam-dot" aria-hidden="true">${CAM}</span><input type="file" accept="image/*" data-cam="${esc(keyOf(i))}" aria-label="Take or choose a photo of ${esc(i.name)}"></label>`}<a href="${prodUrl(i.id, i.g)}">${shared ? imgTag(i.id, "") : ""}<span>${i.gr ? `<span class="slab-badge">${esc(i.gr)}</span> ` : ""}${esc(i.name)}<span class="muted" style="display:block;font-size:12px;font-weight:400">${esc(setName(i.g))}</span></span></a>${shared ? "" : "</div>"}
          ${shared || i.t === "s" ? "" : `<div class="grade-row"><select class="select grade-sel" data-grade="${esc(keyOf(i))}" aria-label="Raw or graded">${gradeOpts(i.gr || "")}</select>
            ${i.gr ? `<label class="gv">Value each $<input class="field" type="number" min="0" step="0.01" inputmode="decimal" placeholder="${i.raw != null ? (i.raw / 100).toFixed(2) : "0.00"}" value="${i.gv != null ? (i.gv / 100).toFixed(2) : ""}" data-gv="${esc(keyOf(i))}" aria-label="Value of your ${esc(i.gr)}"></label>
            <a class="sold-link" href="${esc(soldUrl(i.name, i.gr))}" target="_blank" rel="noopener">eBay sold ${esc(i.gr === "Other slab" ? "graded" : i.gr)} →</a>` : ""}</div>`}</td>
        <td class="num">${shared ? i.qty : `<div style="display:flex;flex-direction:column;gap:4px;align-items:flex-end"><input class="field" type="number" min="1" max="9999" value="${i.qty}" data-qty="${esc(keyOf(i))}" aria-label="Quantity" style="width:72px"><input class="field" type="number" min="0" step="0.01" placeholder="paid $" value="${i.paid != null ? (i.paid / 100).toFixed(2) : ""}" data-paid="${esc(keyOf(i))}" aria-label="Paid each" style="width:72px"></div>`}</td>
        <td class="num">${money(i.mkt)}${i.gr ? `<span class="muted mkt-note">${i.est ? "raw price · set value" : "your value"}</span>` : ""}</td>
        <td class="num"><b>${money(i.mkt == null ? null : i.mkt * i.qty)}</b></td>
        <td class="num hide-sm">${chg(bestCh(i.ch))}</td>
        ${shared ? "" : `<td class="num"><div class="row-acts"><button class="btn icon" type="button" data-unph="${esc(keyOf(i))}" aria-label="Use the official image for ${esc(i.name)}" title="Use official image" hidden><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/></svg></button><button class="btn" type="button" data-rm="${esc(keyOf(i))}" aria-label="Remove ${esc(i.name)}">✕</button></div></td>`}</tr>`).join("")}
      </tbody></table></div>` : `<div class="panel empty-note">${shared ? "This shared collection is empty." : "Your collection is empty. Search above to add your first card or sealed product."}</div>`;
    shownNow = list;
    if (view === "binder" && list.length) {
      let lastSet = null;
      $("#list").innerHTML = `<div class="binder">${list.map((i, ix) => {
        const head = grouped && i.g !== lastSet ? (lastSet = i.g, `<h3 class="binder-set">${esc(setName(i.g))}</h3>`) : "";
        return `${head}<button type="button" class="bslot${i.t === "s" ? " sealed" : ""}${i.gr ? " slab" : ""}" data-bi="${ix}" aria-label="${esc(i.name)}">
          <span class="bimg"${shared ? "" : ` data-ph="${esc(keyOf(i))}"`}>${imgTag(i.id, "", 1000)}</span>
          ${i.gr ? `<span class="slab-badge">${esc(i.gr)}</span>` : ""}${i.qty > 1 ? `<span class="bqty">×${i.qty}</span>` : ""}
          <span class="bval">${money(i.mkt == null ? null : i.mkt * i.qty)}</span></button>`; }).join("")}</div>`;
      $("#list").querySelectorAll("[data-bi]").forEach((b) => b.addEventListener("click", () => cardView(shownNow, +b.dataset.bi, { setName, photo: shared ? null : (c) => photos.get(keyOf(c)).then((bl) => bl ? URL.createObjectURL(bl) : null) })));
    }
    plot();
    if (shared) return;
    const find = (k) => col.items.find((x) => keyOf(x) === k);
    $("#list").querySelectorAll("[data-qty]").forEach((el) => el.addEventListener("change", () => { const it = find(el.dataset.qty); it.qty = Math.max(1, Number(el.value) || 1); save(); setTimeout(draw); }));
    $("#list").querySelectorAll("[data-paid]").forEach((el) => el.addEventListener("change", () => { const it = find(el.dataset.paid); it.paid = el.value === "" ? null : Math.round(Number(el.value) * 100); save(); setTimeout(draw); }));
    $("#list").querySelectorAll("[data-grade]").forEach((el) => el.addEventListener("change", () => {
      const it = find(el.dataset.grade), gr = el.value;
      const target = { ...it, qty: 1 };
      if (gr) { target.gr = gr; target.gv = null; } else { delete target.gr; delete target.gv; }
      const ex = col.items.find((x) => x !== it && keyOf(x) === keyOf(target));
      if (it.qty > 1) it.qty--; else col.items = col.items.filter((x) => x !== it);   // one copy moves; the rest stay as they were
      if (ex) ex.qty++; else col.items.push(target);
      save(); toast(gr ? `Marked 1 copy as ${gr}. Add its value or check eBay sold.` : "Marked 1 copy as raw"); setTimeout(draw);
    }));
    $("#list").querySelectorAll("[data-gv]").forEach((el) => el.addEventListener("change", () => { const it = find(el.dataset.gv); it.gv = el.value === "" ? null : Math.round(Number(el.value) * 100); save(); setTimeout(draw); }));
    $("#list").querySelectorAll("[data-rm]").forEach((el) => el.addEventListener("click", () => { photos.del(el.dataset.rm); col.items = col.items.filter((x) => keyOf(x) !== el.dataset.rm); save(); draw(); }));
    $("#list").querySelectorAll("[data-cam]").forEach((el) => el.addEventListener("change", async () => {
      const file = el.files && el.files[0]; el.value = ""; if (!file) return;
      try { await photos.put(el.dataset.cam, await shrinkPhoto(file)); toast("Photo saved"); paintPhotos(); }
      catch { toast("Couldn't save that photo. Try another."); }
    }));
    $("#list").querySelectorAll("[data-unph]").forEach((el) => el.addEventListener("click", async () => { await photos.del(el.dataset.unph); toast("Showing the official image"); paintPhotos(); }));
    paintPhotos();
  };
  const photoUrls = [];
  const paintPhotos = async () => {
    photoUrls.splice(0).forEach((u) => URL.revokeObjectURL(u));
    for (const w of $("#list").querySelectorAll("[data-ph]")) {
      const k = w.dataset.ph, blob = await photos.get(k);
      const off = $(`[data-unph="${CSS.escape(k)}"]`);
      if (off) off.hidden = !blob;
      const imgEl = $("img", w);
      if (blob) { const u = URL.createObjectURL(blob); photoUrls.push(u); imgEl.onerror = null; imgEl.src = u; w.classList.add("mine"); }
      else if (w.classList.contains("mine")) { w.classList.remove("mine"); imgEl.src = img(Number(k.split("|")[0]), 200); }
    }
  };

  $("#cq").addEventListener("input", (e) => { cq = e.target.value.trim().toLowerCase(); draw(); });
  $("#csort").addEventListener("change", (e) => { csort = e.target.value; draw(); });
  $("#cgroup").addEventListener("change", (e) => { grouped = e.target.checked; draw(); });
  tabs($("#cview"), [["binder", "Binder"], ["list", "List"]], view, (v) => { view = v; if (!shared) { try { localStorage.setItem("dys-cview", v); } catch {} } draw(); });
  tabs($("#crange"), [["30", "1M"], ["90", "3M"], ["365", "1Y"]], range, (r) => { range = r; plot(); });
  if (!shared) {
    const input = $("#add-q"), out = $("#add-results");
    $("#name").value = col.name || "";
    $("#name").addEventListener("input", (e) => { col.name = e.target.value.slice(0, 60); save(); $("#title").textContent = col.name || "My collection"; });
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase().replace(/é/g, "e");
      if (q.length < 2) { out.classList.remove("open"); return; }
      const terms = q.split(/\s+/), hits = [];
      for (const r of rows) { const hay = alias((r[1] + " " + setName(r[2])).toLowerCase()); if (terms.every((t) => hay.includes(t))) { hits.push(r); if (hits.length >= 12) break; } }
      out.innerHTML = hits.length ? hits.map((r, i) => `<a href="#" data-hit="${i}">${imgTag(r[0])}<span class="name"><b>${esc(r[1])}</b><span>${esc(setName(r[2]))} · ${r[3] === "s" ? "Sealed" : "Card"}</span></span><span class="figs" style="margin-left:auto"><b>+ ${money(r[4])}</b></span></a>`).join("") : `<div class="empty">No matches</div>`;
      out.classList.add("open");
      out.querySelectorAll("[data-hit]").forEach((a) => a.addEventListener("click", async (e) => {
        e.preventDefault(); const r = hits[+a.dataset.hit];
        const it = { id: r[0], g: r[2], n: r[1], qty: 1, paid: null };
        const ex = col.items.find((x) => !x.gr && keyOf(x) === keyOf(it));
        ex ? ex.qty++ : col.items.push(it);
        save(); input.value = ""; out.classList.remove("open"); await loadChanges(); draw();
        $("#added").textContent = `Added ${r[1]}`; setTimeout(() => { $("#added").textContent = ""; }, 2500);
      }));
    });
    document.addEventListener("click", (e) => { if (!$("#add-box").contains(e.target)) out.classList.remove("open"); });
    $("#share").addEventListener("click", async () => {
      const url = `${location.origin}${location.pathname}#c=${b64e({ n: col.name, i: col.items.map((i) => [i.id, i.g, i.qty, printCode(subOf(i.n || "")), ...(i.gr ? [i.gr, i.gv ?? null] : [])]) })}`;
      try { if (navigator.share) { await navigator.share({ title: col.name || "My collection", url }); return; } } catch { return; }
      try { await navigator.clipboard.writeText(url); $("#added").textContent = "Share link copied"; } catch { prompt("Copy your share link:", url); }
    });
    $("#backup").addEventListener("click", () => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([JSON.stringify(col, null, 1)], { type: "application/json" }));
      a.download = `dys-collection-${meta.updated}.json`; a.click();
    });
    $("#restore").addEventListener("change", async (e) => {
      const f = e.target.files[0]; if (!f) return;
      try { const d = JSON.parse(await f.text()); if (!Array.isArray(d.items)) throw 0; col = { name: d.name || "", items: d.items.filter((i) => i && i.id && i.g).map((i) => ({ id: i.id, g: i.g, n: i.n, qty: Math.max(1, i.qty | 0), paid: i.paid ?? null, ...(i.gr ? { gr: String(i.gr).slice(0, 30), gv: i.gv ?? null } : {}) })) }; save(); $("#name").value = col.name; await loadChanges(); draw(); $("#added").textContent = "Collection restored"; }
      catch { $("#added").textContent = "That file isn't a collection backup."; }
    });
  }
  const profilePanel = async () => {
    const box = $("#prof"), pid = await myPid(); if (!box || !pid) return;
    box.hidden = false;
    box.innerHTML = `<div class="prof-head"><b>Your collector profile</b><a href="collectors.html" class="more">Browse collectors →</a></div>
      <div class="prof-grid"><label class="muted">Collector name (public)<input class="field" id="alias" maxlength="20" autocomplete="nickname" placeholder="e.g. JKL TCG" value="${esc(col.alias || "")}"></label>
      <label class="toggle"><input type="checkbox" id="pub"${col.pub ? " checked" : ""}> Show my binder on the Collectors page</label></div>
      <p class="muted prof-note" id="alias-msg">3–20 letters, numbers or spaces. Your email and what you paid are never shown. Changes show up within 30 minutes.</p>
      <p class="prof-links" id="prof-links"></p>`;
    const links = () => { $("#prof-links").innerHTML = col.pub && ALIAS_OK.test(col.alias || "") ? `<a href="collection.html?p=${pid}">View my public page →</a>` : ""; };
    const taken = async (al) => { const d = await getJSON("showcase.json").catch(() => null); return !!d?.profiles?.some((p) => p.p !== pid && p.a.toLowerCase() === al.toLowerCase()); };
    const saveAlias = async () => {
      const al = cleanAlias($("#alias").value);
      if (al === (col.alias || "")) return true;
      if (al && !ALIAS_OK.test(al)) { $("#alias-msg").textContent = "Use 3–20 letters, numbers, spaces, _ . or -"; return false; }
      if (al && await taken(al)) { $("#alias-msg").textContent = `"${al}" is taken. Try another.`; return false; }
      col.alias = al; save(); links(); $("#alias-msg").textContent = al ? `Saved. Your collector name is ${al}.` : "Collector name removed.";
      document.dispatchEvent(new CustomEvent("dys-sync", { detail: "ok" }));
      return true;
    };
    let at = 0;
    $("#alias").addEventListener("input", () => { clearTimeout(at); at = setTimeout(saveAlias, 700); });
    $("#alias").addEventListener("change", saveAlias);
    $("#pub").addEventListener("change", async (e) => {
      const want = e.target.checked;
      if (want && !(await saveAlias() && ALIAS_OK.test(col.alias || ""))) { e.target.checked = false; if (!col.alias) $("#alias-msg").textContent = "Type a collector name first."; $("#alias").focus(); return; }
      col.pub = want; save(); links();
      $("#alias-msg").textContent = col.pub ? "You're on the Collectors page within 30 minutes." : "Your binder is private. It leaves the Collectors page within 30 minutes.";
    });
    links();
  };
  if (!shared && acct.enabled()) {
    const bar = $("#acct");
    const paint = (msg) => {
      bar.hidden = false;
      const a = acct.info();
      const al = colGet().alias;
      bar.innerHTML = a ? `<span><b>${al ? `Signed in as ${esc(al)}` : "Saved to your account"}</b>${msg ? ` · <span class="muted">${esc(msg)}</span>` : ""}${al ? "" : `<span class="muted" style="display:block;font-size:13px">Pick a collector name below so people see that instead of your email.</span>`}</span><button class="btn" id="acct-out" type="button">Sign out</button>`
        : `<span><b>Save your binder to your Drive Your Style account</b><span class="muted" style="display:block;font-size:13px">Sign in with the email you shop with. Your binder syncs to every phone and computer.</span></span><button class="btn primary" id="acct-in" type="button">Sign in</button>`;
      $("#acct-in")?.addEventListener("click", () => acct.signIn());
      $("#acct-out")?.addEventListener("click", () => acct.signOut());
    };
    document.addEventListener("dys-sync", (e) => paint(e.detail === "ok" ? "Synced" : "Couldn't sync, will retry"));
    try {
      const justSignedIn = await acct.finish();
      if (acct.signedIn()) {
        paint("Syncing…");
        const remote = await acct.pull();
        const local = colGet();
        if (remote && (!local.items.length || (!justSignedIn && (remote.updated || 0) > (local.updated || 0)))) {
          col = { name: remote.name || local.name || "", items: remote.items || [], updated: remote.updated,
            alias: remote.alias || local.alias || "", pub: remote.pub ?? local.pub ?? false, likes: remote.likes || [], follows: remote.follows || [], want: remote.want || local.want || [], socialAt: local.socialAt };
          colSet(col, false);
        } else if (remote && justSignedIn) {          // first sign-in on this device: combine both
          const key = (x) => `${x.id}|${printCode(subOf(x.n || ""))}${x.gr ? "|" + x.gr : ""}`, m = new Map(remote.items.map((x) => [key(x), x]));
          for (const x of local.items) { const r = m.get(key(x)); m.set(key(x), r ? { ...r, qty: Math.max(r.qty, x.qty), paid: r.paid ?? x.paid } : x); }
          const uni = (k) => [...new Set([...(remote[k] || []), ...(local[k] || [])])];
          col = { name: local.name || remote.name || "", items: [...m.values()], alias: local.alias || remote.alias || "", pub: local.pub ?? remote.pub ?? false,
            likes: uni("likes"), follows: uni("follows"), socialAt: local.socialAt,
            want: [...new Map([...(remote.want || []), ...(local.want || [])].map((w) => [w.k, w])).values()] };
          colSet(col);
        } else { col = local; acct.push(local); }
        $("#name").value = col.name || ""; await loadChanges();
        paint(remote ? "Synced" : "Saved");
        profilePanel();
      } else paint();
    } catch (err) { paint(); if (acct.signedIn()) profilePanel(); $("#added").textContent = String(err.message || err).startsWith("Sign-in") ? err.message : "Couldn't reach your account. Your binder is still saved on this device."; }
  }
  draw(); await loadChanges(); draw();
}

async function pageCollectors() {
  const [data, me] = await Promise.all([getJSON("showcase.json").catch(() => ({ profiles: [], updated: 0 })), myPid()]);
  const all = data.profiles || [];
  let tab = params.get("tab") || "value", q = "";
  if (me && all.some((p) => p.p === me)) { $("#join").textContent = "My public page →"; $("#join").href = `collection.html?p=${me}`; }
  const draw = () => {
    const follows = new Set(colGet().follows || []);
    let list = all.filter((p) => !q || p.a.toLowerCase().includes(q) || (p.bn || "").toLowerCase().includes(q));
    if (tab === "following") list = list.filter((p) => follows.has(p.p));
    const by = { value: (a, b) => b.v - a.v, liked: (a, b) => b.l - a.l || b.v - a.v, followed: (a, b) => b.f - a.f || b.v - a.v, new: (a, b) => b.u - a.u, following: (a, b) => b.u - a.u };
    list.sort(by[tab] || by.value);
    $("#cnote").textContent = all.length ? `${all.length} public binder${all.length > 1 ? "s" : ""}${data.updated ? ` · updated ${new Date(data.updated).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}` : ""}` : "";
    $("#clist").innerHTML = list.length ? list.map((p) => `<a class="col-card" href="collection.html?p=${p.p}">
        <span class="col-thumbs">${p.top.map(([id, gr]) => `<span>${imgTag(id, "", 400)}${gr ? `<i class="slab-badge">${esc(gr)}</i>` : ""}</span>`).join("")}</span>
        <span class="col-meta"><b>${esc(p.a)}${p.p === me ? ` <small class="muted">(you)</small>` : ""}</b>${p.bn ? `<span class="muted col-bn">${esc(p.bn)}</span>` : ""}
          <span class="col-figs"><b>${money(p.v)}</b><span class="muted">${p.n.toLocaleString()} item${p.n > 1 ? "s" : ""}</span></span></span>
        <span class="soc-row" data-soc="${p.p}"></span></a>`).join("")
      : `<div class="panel empty-note" style="grid-column:1/-1">${tab === "following" ? "You're not following anyone yet. Open a binder and tap <b>Follow</b>." : all.length ? "No collectors match." : "No public binders yet. Be the first: sign in on My Collection, pick a collector name and turn on <b>Show my binder on the Collectors page</b>."}</div>`;
    $("#clist").querySelectorAll("[data-soc]").forEach((el) => socialButtons(el, all.find((p) => p.p === el.dataset.soc), data.updated || 0));
  };
  tabs($("#ctab"), [["value", "Top value"], ["liked", "Most liked"], ["followed", "Most followed"], ["new", "Recently updated"], ["following", "Following"]], tab, (v) => { tab = v; draw(); });
  $("#cfind").addEventListener("input", (e) => { q = e.target.value.trim().toLowerCase().replace(/^@/, ""); draw(); });
  draw();
}

/* ---------- boot ---------- */
shell();
document.querySelectorAll("[data-search]").forEach(initSearch);
const normNum = (t) => t.replace(/\b0+(\d)/g, "$1");
const ptcgFromLogo = (lg) => (lg || "").match(/^https:\/\/images\.pokemontcg\.io\/([^/]+)\/logo\.png/)?.[1];
const ptcgImg = (setId, no) => { if (!setId || !no) return ""; let n = no.split("/")[0].trim(); if (/^\d+$/.test(n)) n = String(Number(n)); return `https://images.pokemontcg.io/${setId}/${n}.png`; };

async function pageSearch() {
  const [meta, sets] = await Promise.all([getJSON("meta.json"), getJSON("sets.json")]);
  const setById = new Map(sets.map((x) => [x.id, x]));
  let q = (params.get("q") || "").trim(), game = params.get("game") || "all", type = "c", rar = "", sort = "price", priced = false, lim = 60;
  $("#sq").value = q;
  tabs($("#sgame"), [["all", "All games"], ...meta.games.map((g) => [g.slug, g.label])], game, (v) => { game = v; lim = 60; draw(); });
  tabs($("#stype"), [["c", "Cards"], ["s", "Sealed"], ["all", "Both"]], type, (v) => { type = v; lim = 60; draw(); });
  const data = await getJSON("search-all.json");
  const R = data.r;
  $("#srar").innerHTML += R.map((r, i) => [r, i]).sort((a, b) => a[0].localeCompare(b[0])).map(([r, i]) => `<option value="${i}">${esc(r)}</option>`).join("");
  const hay = data.rows.map((r) => alias(normNum(`${r[1]} ${setById.get(r[2])?.n || ""} ${r[5]} ${r[6] >= 0 ? R[r[6]] : ""}`.toLowerCase().replace(/é/g, "e"))));
  const idx = new Map(data.rows.map((r, i) => [r, i]));
  const numOf = (r) => { const m = (r[5] || "").match(/\d+/); return m ? Number(m[0]) : 1e9; };
  const draw = () => {
    const terms = normNum(q.toLowerCase().replace(/é/g, "e")).split(/\s+/).filter(Boolean);
    const pool = data.rows.filter((r) => (type === "all" || r[3] === type) && (game === "all" || setById.get(r[2])?.k === game)
      && (rar === "" || String(r[6]) === rar) && (!priced || r[4] != null));
    const out = terms.length ? rankHits(pool, terms, (r) => hay[idx.get(r)], (r) => normNum(r[1])) : pool;
    if (sort === "price" && !terms.length) out.sort((a, b) => (b[4] ?? -1) - (a[4] ?? -1));
    else if (sort === "high") out.sort((a, b) => (b[4] ?? -1) - (a[4] ?? -1));
    else if (sort === "low") out.sort((a, b) => (a[4] ?? 1e12) - (b[4] ?? 1e12));
    else if (sort === "name") out.sort((a, b) => a[1].localeCompare(b[1]));
    else if (sort === "num") out.sort((a, b) => numOf(a) - numOf(b) || a[1].localeCompare(b[1]));
    $("#scount").textContent = !terms.length && game === "all" && rar === "" ? `${out.length.toLocaleString()} items. Type a name, set or card number to narrow it down.` : `${out.length.toLocaleString()} results`;
    const own = sumOwned();
    $("#sres").innerHTML = out.slice(0, lim).map((r) => {
      const st = setById.get(r[2]), k = `${r[0]}|${printCode(subOf(r[1]))}`, qty = own.get(k) || 0;
      const alt = r[3] === "c" && st?.k === "pokemon" ? ptcgImg(ptcgFromLogo(st.lg), r[5]) : "";
      return `<div class="ctile${r[3] === "s" ? " sealed" : ""}${qty ? " owned" : ""}"><a href="${prodUrl(r[0], r[2])}" class="cimg">${imgTag(r[0], "", 1000, alt)}</a>
        <button class="cadd" type="button" data-add="${esc(k)}" data-i="${r[0]}" aria-label="Add ${esc(r[1])} to My Collection">${qty ? `✓${qty > 1 ? qty : ""}` : "+"}</button>
        <a href="${prodUrl(r[0], r[2])}" class="cinfo"><span class="cn"><b>${esc(r[1])}</b>${r[5] ? `<small>${esc(r[5])}</small>` : ""}</span>
        <span class="cp">${r[4] == null ? `<small class="muted">No price yet</small>` : `<b>${money(r[4])}</b>`}<em>${esc((st?.n || "").replace(/^(ME|SV|SWSH|SM|M)\d*[a-z]?:\s*/i, ""))}</em></span></a></div>`;
    }).join("") + (out.length > lim ? `<div class="cmore"><button class="btn" id="smore" type="button">Show more (${(out.length - lim).toLocaleString()} left)</button></div>` : "")
      + (!out.length ? `<div class="panel empty-note" style="grid-column:1/-1">No matches. Try fewer words, or just the card number like 199/165.</div>` : "");
    $("#smore")?.addEventListener("click", () => { lim += 120; draw(); });
    $("#sres").querySelectorAll("[data-add]").forEach((b) => b.addEventListener("click", () => {
      const r = out.find((x) => `${x[0]}|${printCode(subOf(x[1]))}` === b.dataset.add); if (!r) return;
      const col = colGet(), ex = col.items.find((x) => !x.gr && `${x.id}|${printCode(subOf(x.n || ""))}` === b.dataset.add);
      ex ? ex.qty++ : col.items.push({ id: r[0], g: r[2], n: r[1], qty: 1, paid: null });
      colSet(col); toast(`Added ${r[1]} to My Collection`); draw();
    }));
    wantButtons($("#sres"), (k) => { const r = out.find((x) => `${x[0]}|${printCode(subOf(x[1]))}` === k); return r && { id: r[0], g: r[2], n: r[1], at: r[4] }; });
  };
  let t = 0;
  $("#sq").addEventListener("input", (e) => { q = e.target.value.trim(); lim = 60; clearTimeout(t); t = setTimeout(() => { draw(); history.replaceState(null, "", q ? `?q=${encodeURIComponent(q)}` : "search.html"); }, 180); });
  $("#srar").addEventListener("change", (e) => { rar = e.target.value; lim = 60; draw(); });
  $("#ssort").addEventListener("change", (e) => { sort = e.target.value; draw(); });
  $("#spriced").addEventListener("change", (e) => { priced = e.target.checked; lim = 60; draw(); });
  draw();
  if (!q) $("#sq").focus();
}

const pages = { search: pageSearch, index: pageIndex, sets: pageSets, set: pageSet, product: pageProduct, trends: pageTrends, cards: pageCards, compare: pageCompare, calendar: pageCalendar, sneakers: pageSneakers, watchlist: pageWatchlist, demand: pageDemand, importer: pageImporter, collection: pageCollection, collectors: pageCollectors };
(pages[PAGE] || (async () => {}))().catch((err) => {
  console.error(err);
  const main = $("main");
  if (main) main.insertAdjacentHTML("afterbegin", `<div class="wrap"><p class="panel empty-note" style="margin-top:24px">Couldn't load market data right now. Please refresh in a minute.</p></div>`);
});

/* ---------- install as an app ---------- */
if ("serviceWorker" in navigator && window.isSecureContext) {
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
}
let installEvt = null;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault(); installEvt = e;
  if ($("#install-app")) return;
  const b = document.createElement("button");
  b.id = "install-app"; b.type = "button"; b.className = "install-btn"; b.textContent = "Install app";
  b.addEventListener("click", async () => {
    if (!installEvt) return;
    installEvt.prompt();
    const { outcome } = await installEvt.userChoice.catch(() => ({}));
    installEvt = null; b.remove();
    if (outcome === "accepted") toast("Installed. Open it from your home screen.");
  });
  $(".top-actions")?.prepend(b);
});
window.addEventListener("appinstalled", () => { installEvt = null; $("#install-app")?.remove(); });

/* iPhone/iPad can't install from a button, so the button opens the steps instead */
const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const standalone = window.navigator.standalone === true || matchMedia("(display-mode: standalone)").matches;
if (isIOS && !standalone && $(".top-actions") && !$("#install-app")) {
  const safari = !/CriOS|FxiOS|EdgiOS|OPiOS/.test(navigator.userAgent);
  const SHARE = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12"/><path d="M8 7l4-4 4 4"/><path d="M6 11v9h12v-9"/></svg>`;
  const ADD = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="4"/><path d="M12 8v8M8 12h8"/></svg>`;
  const b = document.createElement("button");
  b.id = "install-app"; b.type = "button"; b.className = "install-btn"; b.textContent = "Install app";
  $(".top-actions").prepend(b);
  b.addEventListener("click", () => {
    if ($("#ios-install")) return;
    const s = document.createElement("div");
    s.id = "ios-install"; s.className = "ios-sheet"; s.setAttribute("role", "dialog"); s.setAttribute("aria-modal", "true"); s.setAttribute("aria-labelledby", "ios-t");
    s.innerHTML = `<div class="ios-card">
        <div class="ios-head"><img src="assets/icons/icon-192.png" alt="" width="48" height="48"><div><b id="ios-t">Install DYS Market</b><span>Add it to your Home Screen in 3 taps.</span></div>
          <button type="button" class="ios-x" aria-label="Close">✕</button></div>
        <ol class="ios-steps">
          <li><span class="ios-n">1</span><span>Tap the <b>Share</b> button <i class="ios-ic">${SHARE}</i> ${safari ? "in Safari's toolbar" : "next to the address bar"}${safari ? "" : ". Don't see it? Open this page in <b>Safari</b>"}.</span></li>
          <li><span class="ios-n">2</span><span>Scroll down and tap <b>Add to Home Screen</b> <i class="ios-ic">${ADD}</i>.</span></li>
          <li><span class="ios-n">3</span><span>Tap <b>Add</b>. DYS Market appears on your Home Screen.</span></li>
        </ol>
        <button type="button" class="btn primary ios-ok">Got it</button>
      </div>${safari ? `<div class="ios-arrow" aria-hidden="true">${SHARE}<span>Share is down here</span></div>` : ""}`;
    const close = () => { s.remove(); b.focus(); };
    s.addEventListener("click", (e) => { if (e.target === s || e.target.closest(".ios-x, .ios-ok")) close(); });
    document.addEventListener("keydown", function k(e) { if (e.key === "Escape") { close(); document.removeEventListener("keydown", k); } });
    document.body.appendChild(s);
    $(".ios-ok", s).focus();
  });
}
})();
