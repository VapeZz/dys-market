/* Drive Your Style: scan a card with the phone camera.
   Reads the card number (199/165, OP05-119, 164/204, EBP01-050 ...) and name with on-device OCR
   (tesseract.js, nothing is uploaded), then matches against every card we track. */
(() => {
  const TJS = "https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js";
  const PATHS = {
    workerPath: "https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/worker.min.js",
    corePath: "https://cdn.jsdelivr.net/npm/tesseract.js-core@5.1.1",
    langPath: "https://cdn.jsdelivr.net/npm/@tesseract.js-data/eng@1.0.0/4.0.0_best_int",
  };
  let worker = null, rowsP = null;
  const loadScript = (src) => new Promise((ok, bad) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = bad; document.head.appendChild(s); });
  async function getWorker(progress) {
    if (worker) return worker;
    if (!window.Tesseract) await loadScript(TJS);
    progress("Loading the card reader (first time only)…");
    worker = await window.Tesseract.createWorker("eng", 1, PATHS);
    return worker;
  }
  const getRows = () => (rowsP ||= fetch("data/search-all.json", { cache: "no-cache" }).then((r) => r.json()));

  /* image -> canvas crops: whole card for the name, bottom strip (enlarged) for the number */
  async function crops(file) {
    const img = await createImageBitmap(file);
    const mk = (sx, sy, sw, sh, w) => {
      const c = document.createElement("canvas"), s = w / sw;
      c.width = Math.round(sw * s); c.height = Math.round(sh * s);
      const x = c.getContext("2d");
      x.filter = "grayscale(1) contrast(1.35)";
      x.drawImage(img, sx, sy, sw, sh, 0, 0, c.width, c.height);
      return c;
    };
    const W = img.width, H = img.height;
    return { bottom: mk(0, H * 0.72, W, H * 0.28, 1800), corner: mk(0, H * 0.86, W * 0.55, H * 0.14, 1800), full: mk(0, 0, W, H, Math.min(1400, W * 1.5)), top: mk(0, 0, W, H * 0.22, 1600) };
  }

  const norm = (s) => String(s || "").toLowerCase().replace(/é/g, "e");
  const slashKey = (a, b) => `${parseInt(a, 10)}/${parseInt(b, 10)}`;
  /* numbers on the card. OCR often reads the "/" in 149/128 as 7, 1, l or |, so every digit run is also
     split at those characters, and only numbers that exist on a real card are kept (known = Set of them). */
  function numbersIn(text, known) {
    const strong = new Set(), weak = new Set();
    const t = text.replace(/[Oo](?=\d)|(?<=\d)[Oo]/g, "0");
    for (const m of t.matchAll(/(\d{1,3})[a-z]?\s*[\/|]\s*(\d{2,3})/g)) { const k = slashKey(m[1], m[2]); if (known.has(k)) strong.add(k); }
    for (const m of t.matchAll(/\b(OP|ST|EB|PRB|EBP|BP|TD)\s?(\d{2})\s?[-–~]\s?(\d{3})/gi)) strong.add(`${m[1]}${m[2]}-${m[3]}`.toUpperCase());
    for (const m of t.matchAll(/\bP\s?[-–]\s?(\d{3})\b/g)) strong.add(`P-${m[1]}`);
    for (const run of t.match(/[0-9\/|lI]{4,12}/g) || []) {
      for (let i = 1; i < run.length - 2; i++) {
        if (!"/|lI71".includes(run[i])) continue;
        const left = run.slice(0, i).replace(/\D/g, ""), right = run.slice(i + 1).replace(/\D/g, "");
        for (let la = 1; la <= 3 && la <= left.length; la++) for (let lb = 2; lb <= 3 && lb <= right.length; lb++) {
          const k = slashKey(left.slice(-la), right.slice(0, lb));
          if (known.has(k) && !strong.has(k)) weak.add(k);
        }
      }
    }
    return { strong: [...strong], weak: [...weak] };
  }
  const rowNum = (no) => {
    if (!no) return null;
    const s = no.match(/^(\d{1,3})[a-z]?\/(\d{2,3})/i);
    if (s) return slashKey(s[1], s[2]);
    const c = no.match(/^([A-Z]+\d{2}-\d{3})/i) || no.match(/^(P-\d{3})/);
    return c ? c[1].toUpperCase() : null;
  };
  const STOP = new Set(["holofoil", "foil", "normal", "reverse", "edition", "1st", "unlimited", "promo", "the", "and", "pokemon", "card"]);
  const words = (s) => norm(s).replace(/\([^)]*\)/g, " ").split(/[^a-z0-9']+/).map((w) => w.replace(/'s$/, "")).filter((w) => w.length >= 3 && !/^\d+$/.test(w) && !STOP.has(w));
  let numIndex = null;
  function index(data) {
    if (numIndex) return numIndex;
    const by = new Map();
    for (const r of data.rows) { if (r[3] !== "c") continue; const k = rowNum(r[5]); if (!k) continue; if (!by.has(k)) by.set(k, []); by.get(k).push(r); }
    return (numIndex = by);
  }

  function match(data, text, nameText) {
    const by = index(data), nums = numbersIn(text, by), toks = new Set(words(nameText + "\n" + text)), hay = norm(text);
    const nameScore = (r) => { const ws = words(r[1]); if (!ws.length) return 0; return ws.filter((w) => toks.has(w) || (w.length >= 5 && hay.includes(w))).length / ws.length; };
    const scored = new Map();
    const add = (r, bonus) => { const sc = nameScore(r) + bonus; if (!scored.has(r) || scored.get(r) < sc) scored.set(r, sc); };
    nums.strong.forEach((k) => (by.get(k) || []).forEach((r) => add(r, 1)));
    nums.weak.forEach((k) => (by.get(k) || []).forEach((r) => add(r, 0.4)));
    if (!scored.size) {   // no number found at all: lean on the card name
      const names = [...toks].filter((w) => w.length >= 4);
      if (names.length) for (const r of data.rows) { if (r[3] !== "c") continue; const sc = nameScore(r); if (sc >= 0.99 && words(r[1]).some((w) => w.length >= 5 && toks.has(w))) add(r, 0); }
    }
    const list = [...scored].sort((a, b) => b[1] - a[1] || (b[0][4] || 0) - (a[0][4] || 0)).slice(0, 12).map(([r, s]) => ({ s, r }));
    return { nums: [...nums.strong, ...nums.weak], list };
  }

  async function scanFile(file, ui) {
    const [w, data, c] = await Promise.all([getWorker(ui.status), getRows(), crops(file)]);
    ui.status("Reading the card…");
    const txt = {};
    for (const [k, cv] of Object.entries(c)) { const r = await w.recognize(cv); txt[k] = r.data.text; ui.status(k === "top" ? "Matching…" : "Reading the card…"); }
    const text = [txt.bottom, txt.corner, txt.full, txt.top].join("\n");
    return { text, ...match(data, text, txt.top) };
  }

  /* ---------- UI: full-screen sheet ---------- */
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (c) => c == null ? "—" : "$" + (c / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  window.dysScan = function open(opts = {}) {
    const box = document.createElement("div");
    box.className = "scan-sheet";
    box.innerHTML = `<div class="scan-in"><button class="scan-x" type="button" aria-label="Close">✕</button>
      <h2>Scan a card</h2><p class="muted">Lay the card flat in good light and fill the photo with it. The card number at the bottom is what we read best.</p>
      <label class="btn primary scan-cam">📷 Take a photo<input type="file" accept="image/*" capture="environment" hidden></label>
      <label class="scan-alt">or <u>choose a photo</u><input type="file" accept="image/*" hidden></label>
      <div class="scan-prev"></div><p class="scan-status muted" role="status"></p><div class="scan-res"></div></div>`;
    document.body.appendChild(box); document.body.style.overflow = "hidden";
    const close = () => { box.remove(); document.body.style.overflow = ""; };
    box.addEventListener("click", (e) => { if (e.target === box || e.target.closest(".scan-x")) close(); });
    const status = (t) => { box.querySelector(".scan-status").textContent = t; };
    box.querySelectorAll("input[type=file]").forEach((inp) => inp.addEventListener("change", async () => {
      const f = inp.files && inp.files[0]; inp.value = ""; if (!f) return;
      box.querySelector(".scan-prev").innerHTML = `<img src="${URL.createObjectURL(f)}" alt="">`;
      box.querySelector(".scan-res").innerHTML = "";
      status("Getting ready…");
      try {
        const res = await scanFile(f, { status });
        const meta = await fetch("data/meta.json").then((r) => r.json()).catch(() => ({ groups: {} }));
        const best = res.list[0]?.s || 0, good = res.list.filter((x) => x.s >= Math.max(0.4, best * 0.5));
        if (!good.length) {
          status("Couldn't read that one. Try again closer, with less glare, or search by name.");
          box.querySelector(".scan-res").innerHTML = `<a class="btn" href="search.html">Search by name →</a>`;
          return;
        }
        const top = good[0];
        const sure = top.s >= 1.5 && (good.length === 1 || good[1].s < top.s);
        status(sure ? "Found it. Tap to open, add, or ♡." : `${good.length} possible match${good.length > 1 ? "es" : ""}. Pick yours:`);
        box.querySelector(".scan-res").innerHTML = good.slice(0, 9).map(({ r }, i) => `<div class="scan-hit${i === 0 && sure ? " best" : ""}">
          <a href="product.html?id=${r[0]}&set=${r[2]}"><img src="https://tcgplayer-cdn.tcgplayer.com/product/${r[0]}_200w.jpg" alt="" loading="lazy">
          <span><b>${esc(r[1])}</b><small>${esc(meta.groups[r[2]]?.[0] || "")}${r[5] ? " · " + esc(r[5]) : ""}</small><em>${money(r[4])}</em></span></a>
          <span class="scan-acts"><button type="button" class="btn" data-add="${i}">＋ Collection</button><button type="button" class="btn" data-want="${i}">♡ Want</button></span></div>`).join("");
        box.querySelectorAll("[data-add]").forEach((b) => b.addEventListener("click", () => { const r = good[+b.dataset.add].r; (window.dysCollectionAdd || window.dysAddToCollection)?.(r); b.textContent = "✓ Added"; b.disabled = true; }));
        box.querySelectorAll("[data-want]").forEach((b) => b.addEventListener("click", () => { const r = good[+b.dataset.want].r; window.dysWant?.(r); b.textContent = "♥ Wanted"; b.disabled = true; }));
      } catch (err) {
        status("The card reader couldn't load. Check your connection and try again.");
      }
    }));
  };
})();
