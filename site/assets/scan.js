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
  let metaP = null;
  const getMeta = () => (metaP ||= fetch("data/meta.json").then((r) => r.json()).catch(() => ({ groups: {} })));
  const getRows = () => (rowsP ||= fetch("data/search-all.json", { cache: "no-cache" }).then((r) => r.json()));

  /* image -> canvas crops: whole card for the name, bottom strip (enlarged) for the number */
  async function crops(file) {
    const img = file instanceof HTMLCanvasElement ? file : await createImageBitmap(file);
    const mk = (sx, sy, sw, sh, w) => {
      const c = document.createElement("canvas"), s = w / sw;
      c.width = Math.round(sw * s); c.height = Math.round(sh * s);
      const x = c.getContext("2d");
      x.filter = "grayscale(1) contrast(1.35)";
      x.drawImage(img, sx, sy, sw, sh, 0, 0, c.width, c.height);
      return c;
    };
    const W = img.width, H = img.height;
    return { bottom: mk(0, H * 0.72, W, H * 0.28, 1800), corner: mk(0, H * 0.86, W * 0.55, H * 0.14, 1800), full: mk(0, 0, W, H, Math.min(2000, Math.max(1400, W))), top: mk(0, 0, W, H * 0.22, 1600) };
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
    // Pokémon black-star promos: "SVP EN 085", "MEP 028", "SWSH241", "SM78", "XY60", "BW98", "DP47", "HGSS18"
    for (const m of t.matchAll(/\b(SVP|MEP)\s*(?:EN)?\s*[|l]?\s*(\d{3})\b/gi)) strong.add(`${m[1].toUpperCase()}${parseInt(m[2], 10)}`);
    for (const m of t.matchAll(/\b(SWSH|SM|XY|BW|DP|HGSS)\s?(\d{1,3})\b/g)) { const k = `${m[1]}${parseInt(m[2], 10)}`; if (known.has(k)) strong.add(k); }
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
  const rowNum = (no, gname = "") => {
    if (!no) return null;
    const pc = no.match(/^(SWSH|SM|XY|BW|DP|HGSS|SVP|MEP)(\d{1,3})$/);
    if (pc) return `${pc[1]}${parseInt(pc[2], 10)}`;
    if (/^\d{1,3}$/.test(no)) { if (/^SV: Scarlet & Violet Promo/.test(gname)) return `SVP${parseInt(no, 10)}`; if (/^ME: Mega Evolution Promo/.test(gname)) return `MEP${parseInt(no, 10)}`; return null; }
    const s = no.match(/^(\d{1,3})[a-z]?\/(\d{2,3})/i);
    if (s) return slashKey(s[1], s[2]);
    const c = no.match(/^([A-Z]+\d{2}-\d{3})/i) || no.match(/^(P-\d{3})/);
    return c ? c[1].toUpperCase() : null;
  };
  const STOP = new Set(["holofoil", "foil", "normal", "reverse", "edition", "1st", "unlimited", "promo", "the", "and", "pokemon", "card"]);
  const words = (s) => norm(s).replace(/\([^)]*\)/g, " ").split(/[^a-z0-9']+/).map((w) => w.replace(/'s$/, "")).filter((w) => w.length >= 3 && !/^\d+$/.test(w) && !STOP.has(w));
  let numIndex = null;
  function index(data, meta) {
    if (numIndex) return numIndex;
    const by = new Map();
    for (const r of data.rows) { if (r[3] !== "c") continue; const k = rowNum(r[5], meta.groups[r[2]]?.[0]); if (!k) continue; if (!by.has(k)) by.set(k, []); by.get(k).push(r); }
    return (numIndex = by);
  }

  const letters = (s) => norm(s).replace(/\([^)]*\)/g, "").replace(/ - .*$/, "").replace(/[^a-z]/g, "");
  const tris = (s) => { const o = new Set(); for (let i = 0; i < s.length - 2; i++) o.add(s.slice(i, i + 3)); return o; };
  const leadNum = (no) => { const m = String(no || "").match(/(\d{1,3})/); return m ? parseInt(m[1], 10) : null; };

  function match(data, meta, text, nameText, numText) {
    const by = index(data, meta), nums = numbersIn(text, by), toks = new Set(words(nameText + "\n" + text)), hay = norm(text);
    const nameScore = (r) => { const ws = words(r[1]); if (!ws.length) return 0; return ws.filter((w) => toks.has(w) || (w.length >= 5 && hay.includes(w))).length / ws.length; };
    const scored = new Map(), sureSet = new Set();
    const add = (r, bonus) => { const sc = nameScore(r) + bonus; if (!scored.has(r) || scored.get(r) < sc) scored.set(r, sc); };
    const nt = numText.replace(/(?<!\d)(\d{2})\s(\d)(?!\d)/g, "$1$2");   // "08 5" -> "085"
    const bare = [...new Set(nt.match(/(?<!\d)\d{2,3}(?!\d)/g) || [])].slice(0, 10), ints = new Set(bare.map((x) => parseInt(x, 10)));
    nums.strong.forEach((k) => (by.get(k) || []).forEach((r) => { add(r, 1); if (nameScore(r) >= 0.5) sureSet.add(r); }));
    nums.weak.forEach((k) => (by.get(k) || []).forEach((r) => { const ns = nameScore(r); add(r, ns >= 0.5 ? 1.2 : 0.4); if (ns >= 0.99) sureSet.add(r); }));
    // a clearly read card name always counts; a matching number (even printed bare, like "18" for 18/53) seals it
    const lines = text.split("\n").map(letters).filter((l) => l.length >= 5);
    for (const r of data.rows) {
      if (r[3] !== "c") continue;
      const ws = words(r[1]), nm = letters(r[1]);
      if (!ws.length || nm.length < 5 || !ws.every((w) => toks.has(w) || hay.includes(w))) continue;
      if (!lines.some((l) => l.includes(nm))) continue;          // the full name has to sit together on one line
      const numOk = ints.has(leadNum(r[5])) || (r[5] && bare.includes(r[5]));
      if (ws.length < 2 && !numOk) continue;                      // one-word names (Switch, Pikachu) need the number too
      add(r, -0.5 + 0.05 * ws.length + (numOk ? 1 : 0));   // add() already counts the name once
      if (numOk) sureSet.add(r);
    }
    if (!scored.size || Math.max(...scored.values()) < 1.5) {   // only a bare number like "085" (promos) or a misread one: fuzzy-match the name among cards with that number
      const T = tris(letters(nameText));
      if (ints.size) for (const r of data.rows) {
        if (r[3] !== "c" || !ints.has(leadNum(r[5]))) continue;
        const t = tris(letters(r[1])); let m = 0; t.forEach((x) => { if (T.has(x)) m++; });
        const exact = bare.includes(r[5]), ratio = m / Math.max(1, t.size);   // exact = a bare promo number like "085" printed as-is
        if (exact || (m >= 6 && ratio >= 0.5)) { const sc = (exact ? 1.2 : 0) + ratio; if (!scored.has(r) || scored.get(r) < sc) scored.set(r, sc); }
      }
    }
    const list = [...scored].sort((a, b) => b[1] - a[1] || (b[0][4] || 0) - (a[0][4] || 0)).slice(0, 12).map(([r, s]) => ({ s, r }));
    return { nums: [...nums.strong, ...nums.weak], list, sure: list.length > 0 && sureSet.has(list[0].r) && (list.length === 1 || list[1].s < list[0].s) };
  }

  async function scanFile(file, ui) {
    const [w, data, c, meta] = await Promise.all([getWorker(ui.status), getRows(), crops(file), getMeta()]);
    ui.status("Reading the card…");
    const txt = {};
    for (const [k, cv] of Object.entries(c)) { const r = await w.recognize(cv); txt[k] = r.data.text; ui.status(k === "top" ? "Matching…" : "Reading the card…"); }
    const text = [txt.bottom, txt.corner, txt.full, txt.top].join("\n");
    return { text, ...match(data, meta, text, txt.top, txt.corner + "\n" + txt.bottom) };
  }

  /* ---------- UI: full-screen sheet ---------- */
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (c) => c == null ? "—" : "$" + (c / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  function camera(box, onShot) {
    const view = box.querySelector(".scan-live"), video = view.querySelector("video");
    let stream = null;
    const stop = () => { stream?.getTracks().forEach((t) => t.stop()); stream = null; view.hidden = true; };
    const start = async () => {
      if (!navigator.mediaDevices?.getUserMedia) return false;
      try { stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1440 } }, audio: false }); }
      catch { return false; }
      video.srcObject = stream; view.hidden = false; await video.play().catch(() => {});
      return true;
    };
    view.querySelector(".scan-shoot").addEventListener("click", () => {
      const fr = view.querySelector(".scan-frame").getBoundingClientRect(), vr = video.getBoundingClientRect();
      const vw = video.videoWidth, vh = video.videoHeight; if (!vw) return;
      const k = Math.max(vr.width / vw, vr.height / vh), ox = (vr.width - vw * k) / 2, oy = (vr.height - vh * k) / 2;
      const sx = (fr.left - vr.left - ox) / k, sy = (fr.top - vr.top - oy) / k, sw = fr.width / k, sh = fr.height / k;
      const c = document.createElement("canvas"); c.width = Math.round(sw); c.height = Math.round(sh);
      c.getContext("2d").drawImage(video, sx, sy, sw, sh, 0, 0, c.width, c.height);
      stop(); onShot(c);
    });
    view.querySelector(".scan-cancel").addEventListener("click", stop);
    return { start, stop };
  }

  window.dysScan = function open() {
    const box = document.createElement("div");
    box.className = "scan-sheet";
    box.innerHTML = `<div class="scan-in"><button class="scan-x" type="button" aria-label="Close">✕</button>
      <h2>Scan a card</h2><p class="muted">Take it out of the sleeve if you can, use good light, and line the card up inside the frame.</p>
      <button type="button" class="btn primary scan-open">📷 Open camera</button>
      <label class="scan-alt">or <u>use a photo</u><input type="file" accept="image/*" hidden></label>
      <div class="scan-live" hidden><video playsinline muted autoplay></video><div class="scan-frame"><span>Card inside the frame</span></div>
        <div class="scan-live-bar"><button type="button" class="btn scan-cancel">Cancel</button><button type="button" class="btn primary scan-shoot">Scan</button></div></div>
      <div class="scan-prev"></div><p class="scan-status muted" role="status"></p><div class="scan-res"></div>
      <div class="scan-refine" hidden><input class="field" type="search" placeholder="Not it? Type the number or name, e.g. 085 or grey felt" aria-label="Narrow it down"></div></div>`;
    document.body.appendChild(box); document.body.style.overflow = "hidden";
    const cam = camera(box, (canvas) => run(canvas, canvas.toDataURL("image/jpeg", 0.7)));
    const close = () => { cam.stop(); box.remove(); document.body.style.overflow = ""; };
    box.addEventListener("click", (e) => { if (e.target === box || e.target.closest(".scan-x")) close(); });
    const status = (t) => { box.querySelector(".scan-status").textContent = t; };
    const fileIn = box.querySelector(".scan-alt input");
    box.querySelector(".scan-open").addEventListener("click", async () => { if (!(await cam.start())) { status("Camera not available here, so pick or take a photo instead."); fileIn.click(); } });
    fileIn.addEventListener("change", () => { const f = fileIn.files && fileIn.files[0]; fileIn.value = ""; if (f) run(f, URL.createObjectURL(f)); });

    let meta = { groups: {} }, rows = null;
    const show = (list, sure) => {
      box.querySelector(".scan-res").innerHTML = list.slice(0, 9).map((r, i) => `<div class="scan-hit${i === 0 && sure ? " best" : ""}">
        <a href="product.html?id=${r[0]}&set=${r[2]}"><img src="https://tcgplayer-cdn.tcgplayer.com/product/${r[0]}_200w.jpg" alt="" loading="lazy">
        <span><b>${esc(r[1])}</b><small>${esc(meta.groups[r[2]]?.[0] || "")}${r[5] ? " · " + esc(r[5]) : ""}</small><em>${money(r[4])}</em></span></a>
        <span class="scan-acts"><button type="button" class="btn" data-add="${i}">＋ Collection</button><button type="button" class="btn" data-want="${i}">♡ Want</button></span></div>`).join("");
      box.querySelectorAll("[data-add]").forEach((b) => b.addEventListener("click", () => { (window.dysCollectionAdd || window.dysAddToCollection)?.(list[+b.dataset.add]); b.textContent = "✓ Added"; b.disabled = true; }));
      box.querySelectorAll("[data-want]").forEach((b) => b.addEventListener("click", () => { window.dysWant?.(list[+b.dataset.want]); b.textContent = "♥ Wanted"; b.disabled = true; }));
    };
    const refine = box.querySelector(".scan-refine input");
    refine.addEventListener("input", () => {
      const q = norm(refine.value).trim(); if (!rows || q.length < 2) return;
      const terms = q.split(/\s+/);
      const hits = rows.filter((r) => r[3] === "c" && terms.every((t) => norm(r[1]).includes(t) || (r[5] && norm(r[5]).replace(/^0+/, "").startsWith(t.replace(/^0+/, ""))))).sort((a, b) => (b[4] || 0) - (a[4] || 0));
      status(hits.length ? `${hits.length} match${hits.length > 1 ? "es" : ""}` : "No matches. Try fewer letters.");
      show(hits, false);
    });

    async function run(input, previewUrl) {
      box.querySelector(".scan-prev").innerHTML = `<img src="${previewUrl}" alt="">`;
      box.querySelector(".scan-res").innerHTML = ""; box.querySelector(".scan-refine").hidden = true;
      status("Getting ready…");
      try {
        const res = await scanFile(input, { status });
        meta = await getMeta(); rows = (await getRows()).rows;
        const best = res.list[0]?.s || 0, good = res.list.filter((x) => x.s >= Math.max(0.4, best * 0.5));
        box.querySelector(".scan-refine").hidden = false;
        if (!good.length) { status("Couldn't read that one. Try again with less glare, or type the number or name below."); return; }
        const sure = res.sure;
        status(sure ? "Found it. Tap to open, add, or ♡." : `${good.length} possible match${good.length > 1 ? "es" : ""}. Pick yours, or narrow it below:`);
        show(good.map((x) => x.r), sure);
      } catch (err) {
        status("The card reader couldn't load. Check your connection and try again.");
      }
    }
  };
})();
