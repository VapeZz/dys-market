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
.dys-market a{color:inherit;text-decoration:underline;opacity:.8;margin-left:auto}`;
    document.head.appendChild(st);
  }
  fetch(BASE + "data/store-prices.json", { cache: "no-cache" }).then((r) => r.ok ? r.json() : {}).then((data) => {
    els.forEach((el) => {
      const row = data[el.dataset.handle];
      if (!row || !row.m) return;
      const ours = Math.round(parseFloat(el.dataset.price || "0")); // Shopify price is already in cents
      const c7 = row.c7;
      const chg = c7 == null ? "" : `<span class="${c7 > 0 ? "dm-up" : c7 < 0 ? "dm-down" : ""}">${c7 > 0 ? "▲" : c7 < 0 ? "▼" : ""} ${Math.abs(c7).toFixed(1)}% 7D</span>`;
      const deal = ours > 0 && ours < row.m ? `<span class="dm-deal">Below market</span>` : "";
      el.innerHTML = `<div class="dm-box"><span class="dm-l">TCGplayer market</span><span class="dm-v">${money(row.m)}</span>${chg}${deal}
        <a href="${BASE}product.html?id=${row.id}&set=${row.g}" target="_blank" rel="noopener">Price history</a></div>`;
    });
  }).catch(() => {});
})();
