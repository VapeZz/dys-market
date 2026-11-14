/* Drive Your Style: TCGplayer market price on Shopify product pages.
   Usage (theme Custom Liquid block):
   <div class="dys-market" data-handle="{{ product.handle }}" data-price="{{ product.selected_or_first_available_variant.price }}"></div>
   <script src="https://market.driveyourstyle.net/assets/widget.js" defer></script> */
(() => {
  const BASE = "https://market.driveyourstyle.net/";
  const els = document.querySelectorAll(".dys-market[data-handle]");
  if (!els.length) return;
  const money = (c) => "$" + (c / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (!document.getElementById("dys-market-css")) {
    const st = document.createElement("style");
    st.id = "dys-market-css";
    st.textContent = `.dys-market{margin:12px 0;font-size:14px;line-height:1.4}
.dys-market .dm-box{display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;padding:10px 14px;border:1px solid rgba(127,127,127,.3);border-radius:10px}
.dys-market .dm-l{opacity:.75}.dys-market .dm-v{font-weight:700}
.dys-market .dm-up{color:#1f9d63}.dys-market .dm-down{color:#d6455d}
.dys-market .dm-deal{font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;padding:3px 8px;border-radius:999px;background:rgba(245,185,66,.18);color:#9a6412}
.dys-market a{color:inherit;text-decoration:underline;opacity:.8;margin-left:auto}
.dys-market .dm-cards{margin-top:18px}
.dys-market .dm-cards h3{font-size:16px;margin:0 0 4px}
.dys-market .dm-cards p{font-size:13px;opacity:.75;margin:0 0 10px}
.dys-market .dm-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(96px,1fr));gap:10px}
.dys-market .dm-card{display:flex;flex-direction:column;gap:4px;text-decoration:none!important;opacity:1!important;margin:0!important;color:inherit}
.dys-market .dm-card img{font-size:0;color:transparent;width:100%;aspect-ratio:5/7;object-fit:contain;border-radius:6px;background:rgba(127,127,127,.08)}
.dys-market .dm-card span{font-size:11.5px;line-height:1.25;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.dys-market .dm-card b{font-size:12px}
.dys-market .dm-all{display:inline-block;margin:10px 0 0!important;font-size:13px}
.dys-market .dm-snk{padding:12px 14px;border:1px solid rgba(127,127,127,.3);border-radius:10px}
.dys-market .dm-snk b{display:block;font-size:14px;margin-bottom:2px}
.dys-market .dm-snk p{margin:0 0 10px;font-size:13px;opacity:.75}
.dys-market .dm-pills{display:flex;flex-wrap:wrap;gap:8px}
.dys-market .dm-pills a{margin:0!important;opacity:1!important;text-decoration:none!important;font-size:13px;font-weight:600;padding:7px 14px;border:1px solid rgba(127,127,127,.45);border-radius:999px}
.dys-market .dm-pills a:hover{border-color:currentColor}
.dys-market .dm-cal{display:inline-block;margin-top:10px!important;font-size:13px}`;
    document.head.appendChild(st);
  }
  const showCards = (el, row) => {
    fetch(`${BASE}data/set/${row.g}.json`).then((r) => r.ok ? r.json() : null).then((set) => {
      if (!set) return;
      const seen = new Set(), cards = [];
      for (const i of set.items) { if (i.t === "c" && !seen.has(i.id)) { seen.add(i.id); cards.push(i); } }
      if (!cards.length) return;
      const top = cards.slice(0, 12);
      const e = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
      const box = document.createElement("div");
      box.className = "dm-cards";
      box.innerHTML = `<h3>Top cards you could pull</h3><p>The most valuable singles in ${e(set.n)}, at today's market price.</p>
        <div class="dm-grid">${top.map((c) => `<a class="dm-card" href="${BASE}product.html?id=${c.id}&set=${set.id}" target="_blank" rel="noopener">
          <img src="https://tcgplayer-cdn.tcgplayer.com/product/${c.id}_200w.jpg" alt="${e(c.n)}" loading="lazy"><span>${e(c.n.replace(/ \((Holofoil|Normal|Reverse Holofoil)\)$/, ""))}</span><b>${money(c.p)}</b></a>`).join("")}</div>
        <a class="dm-all" href="${BASE}set.html?id=${set.id}" target="_blank" rel="noopener">See all ${cards.length} cards in ${e(set.n)} \u2192</a>`;
      el.appendChild(box);
    }).catch(() => {});
  };
  // Sneakers: resale check (StockX / GOAT / eBay sold) by style code, plus the release calendar
  const showSneaker = (el, s) => {
    const q = encodeURIComponent(s.c || s.n);
    el.innerHTML = `<div class="dm-snk"><b>Check resale before you buy</b><p>Compare this pair${s.c ? ` (${s.c})` : ""} with live listings and recent sales.</p>
      <div class="dm-pills"><a href="https://stockx.com/search?s=${q}" target="_blank" rel="noopener">StockX</a><a href="https://www.goat.com/search?query=${q}" target="_blank" rel="noopener">GOAT</a><a href="https://www.ebay.com/sch/i.html?_nkw=${q}&LH_Sold=1&LH_Complete=1" target="_blank" rel="noopener">eBay sold</a></div>
      <a class="dm-cal" href="${BASE}sneakers.html" target="_blank" rel="noopener">Upcoming sneaker drops &amp; release calendar \u2192</a></div>`;
  };
  const sneakers = () => fetch(BASE + "data/sneakers-stock.json", { cache: "no-cache" }).then((r) => r.ok ? r.json() : []).catch(() => []);
  fetch(BASE + "data/store-prices.json", { cache: "no-cache" }).then((r) => r.ok ? r.json() : {}).then((data) => {
    const rest = [...els].filter((el) => !data[el.dataset.handle]?.m);
    if (rest.length) sneakers().then((list) => rest.forEach((el) => {
      const s = list.find((x) => x.u.endsWith("/products/" + el.dataset.handle));
      if (s) showSneaker(el, s);
    }));
    els.forEach((el) => {
      const row = data[el.dataset.handle];
      if (!row || !row.m) return;
      const ours = Math.round(parseFloat(el.dataset.price || "0")); // Shopify price is already in cents
      const c7 = row.c7;
      const chg = c7 == null ? "" : `<span class="${c7 > 0 ? "dm-up" : c7 < 0 ? "dm-down" : ""}">${c7 > 0 ? "\u25B2" : c7 < 0 ? "\u25BC" : ""} ${Math.abs(c7).toFixed(1)}% 7D</span>`;
      const deal = ours > 0 && ours < row.m ? `<span class="dm-deal">Below market</span>` : "";
      el.innerHTML = `<div class="dm-box"><span class="dm-l">TCGplayer market</span><span class="dm-v">${money(row.m)}</span>${chg}${deal}
        <a href="${BASE}product.html?id=${row.id}&set=${row.g}" target="_blank" rel="noopener">Price history</a></div>`;
      if (row.t === "s" && el.dataset.cards !== "off") showCards(el, row);
    });
  }).catch(() => {});
})();
