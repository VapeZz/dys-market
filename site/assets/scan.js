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
  let yearsP = null;   // set id -> release year, to tell a 1999 card from a 2023 one with the same name
  const getYears = () => (yearsP ||= fetch("data/sets.json").then((r) => r.json())
    .then((s) => Object.fromEntries(s.filter((x) => x.pub).map((x) => [x.id, parseInt(x.pub.slice(0, 4), 10)]))).catch(() => ({})));

  /* ---------- image prep ---------- */
  const OPTS = Object.assign({ bin: true, find: true }, window.DYS_SCAN_OPTS || {});
  const canvasOf = (w, h) => { const c = document.createElement("canvas"); c.width = w; c.height = h; return c; };
  /* Where the card sits in the photo: the card differs from the surface around it (sampled along the photo's edges).
     Returns the whole photo when the card already fills it. */
  function cardBox(img) {
    const W = img.width, H = img.height, s = 200 / Math.max(W, H), w = Math.max(20, Math.round(W * s)), h = Math.max(20, Math.round(H * s));
    const c = canvasOf(w, h), x = c.getContext("2d", { willReadFrequently: true });
    x.drawImage(img, 0, 0, w, h);
    const d = x.getImageData(0, 0, w, h).data, px = (i, j) => (j * w + i) * 4;
    const edge = []; const m = Math.max(2, Math.round(Math.min(w, h) * 0.03));
    for (let i = 0; i < w; i++) for (let j = 0; j < h; j++) if (i < m || j < m || i >= w - m || j >= h - m) edge.push(px(i, j));
    const med = [0, 1, 2].map((k) => edge.map((p) => d[p + k]).sort((a, b) => a - b)[edge.length >> 1]);
    const on = (i, j) => { const p = px(i, j); return Math.abs(d[p] - med[0]) + Math.abs(d[p + 1] - med[1]) + Math.abs(d[p + 2] - med[2]) > 60; };
    const rows = [], cols = new Array(w).fill(0);
    for (let j = 0; j < h; j++) { let n = 0; for (let i = 0; i < w; i++) if (on(i, j)) { n++; cols[i]++; } rows.push(n); }
    const r0 = rows.findIndex((n) => n > w * 0.3), r1 = h - 1 - [...rows].reverse().findIndex((n) => n > w * 0.3);
    const c0 = cols.findIndex((n) => n > h * 0.3), c1 = w - 1 - [...cols].reverse().findIndex((n) => n > h * 0.3);
    if (r0 < 0 || c0 < 0 || r1 <= r0 || c1 <= c0) return { x: 0, y: 0, w: W, h: H };
    const bw = (c1 - c0 + 1) / s, bh = (r1 - r0 + 1) / s, ratio = bw / bh;
    if (bw * bh < W * H * 0.3 || ratio < 0.55 || ratio > 0.9) return { x: 0, y: 0, w: W, h: H };   // not a card-shaped area: use the whole photo
    return { x: c0 / s, y: r0 / s, w: bw, h: bh };
  }
  /* crop -> scaled grayscale, stretched contrast, then (optionally) a local threshold so light/dark gradients
     and glare don't wash out small print. Light-on-dark print is flipped to dark-on-light for the reader. */
  function prep(img, sx, sy, sw, sh, outW, bin) {
    const sc = outW / sw, c = canvasOf(Math.round(sw * sc), Math.round(sh * sc)), x = c.getContext("2d", { willReadFrequently: true });
    x.imageSmoothingQuality = "high";
    x.drawImage(img, sx, sy, sw, sh, 0, 0, c.width, c.height);
    const id = x.getImageData(0, 0, c.width, c.height), d = id.data, n = c.width * c.height, g = new Float32Array(n);
    const hist = new Uint32Array(256);
    for (let i = 0; i < n; i++) { const v = (d[i * 4] * 0.3 + d[i * 4 + 1] * 0.59 + d[i * 4 + 2] * 0.11) | 0; g[i] = v; hist[v]++; }
    let lo = 0, hi = 255, acc = 0; for (; lo < 255 && (acc += hist[lo]) < n * 0.02; lo++); acc = 0; for (; hi > 0 && (acc += hist[hi]) < n * 0.02; hi--);
    const span = Math.max(1, hi - lo); let mean = 0;
    for (let i = 0; i < n; i++) { g[i] = Math.min(255, Math.max(0, (g[i] - lo) * 255 / span)); mean += g[i]; }
    mean /= n;
    if (mean < 110) for (let i = 0; i < n; i++) g[i] = 255 - g[i];          // mostly dark strip: light text -> flip
    if (bin) {
      const W = c.width, H = c.height, r = Math.max(8, Math.round(H / 6)), I = new Float64Array((W + 1) * (H + 1));
      for (let y = 0; y < H; y++) { let row = 0; for (let x0 = 0; x0 < W; x0++) { row += g[y * W + x0]; I[(y + 1) * (W + 1) + x0 + 1] = I[y * (W + 1) + x0 + 1] + row; } }
      for (let y = 0; y < H; y++) for (let x0 = 0; x0 < W; x0++) {
        const ax = Math.max(0, x0 - r), ay = Math.max(0, y - r), bx = Math.min(W, x0 + r + 1), by = Math.min(H, y + r + 1);
        const local = (I[by * (W + 1) + bx] - I[ay * (W + 1) + bx] - I[by * (W + 1) + ax] + I[ay * (W + 1) + ax]) / ((bx - ax) * (by - ay));
        g[y * W + x0] = g[y * W + x0] < local - 12 ? 0 : 255;
      }
    }
    for (let i = 0; i < n; i++) { d[i * 4] = d[i * 4 + 1] = d[i * 4 + 2] = g[i]; d[i * 4 + 3] = 255; }
    x.putImageData(id, 0, 0);
    return c;
  }
  /* the strips we read: the name along the top, the set number along the bottom (left on Pokémon, right on
     One Piece and older Pokémon), and the whole card only when those two don't settle it */
  async function crops(file) {
    const img = file instanceof HTMLCanvasElement ? file : await createImageBitmap(file);
    const b = OPTS.find ? cardBox(img) : { x: 0, y: 0, w: img.width, h: img.height };
    const R = (fx, fy, fw, fh, outW, bin = OPTS.bin) => () => prep(img, b.x + b.w * fx, b.y + b.h * fy, b.w * fw, b.h * fh, outW, bin);
    return { name: R(0, 0.015, 0.8, 0.12, 1300, false), bottom: R(0, 0.865, 1, 0.135, 1900), full: R(0, 0, 1, 1, 1500, false) };
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

  function match(data, meta, text, nameText, numText, years = {}) {
    const by = index(data, meta), nums = numbersIn(text, by), toks = new Set(words(nameText + "\n" + text)), hay = norm(text);
    // Old black-star promos print a bare "1" and a PROMO star; the copyright line dates the card.
    const promoSeen = /\bpr[o0]m[o0]\b/i.test(text);
    const yrs = [...text.matchAll(/(?<!\d)(199\d|20[0-3]\d)(?!\d)/g)].map((m) => +m[1]), printYear = yrs.length ? Math.max(...yrs) : null;
    const isPromo = (r) => /promo/i.test(meta.groups[r[2]]?.[0] || "");
    const eraOk = (r) => printYear != null && years[r[2]] != null && Math.abs(years[r[2]] - printYear) <= 1;
    const nameScore = (r) => { const ws = words(r[1]); if (!ws.length) return 0; return ws.filter((w) => toks.has(w) || (w.length >= 5 && hay.includes(w))).length / ws.length; };
    const scored = new Map(), sureSet = new Set();
    const add = (r, bonus) => { const sc = nameScore(r) + bonus; if (!scored.has(r) || scored.get(r) < sc) scored.set(r, sc); };
    const nt = numText.split("\n")   // attack damage (20, 120+) at the end of a line of rules text isn't the card number
      .map((l) => ((l.match(/[a-z]{3,}/gi) || []).length >= 3 ? l.replace(/(?<![\d\/])\d{1,2}0\s?[+×x]?\s*$/, " ") : l)).join("\n")
      .replace(/©\s?\d{4}(?:\s*,\s*\d{2,4})*|#\s?\d+|\bLV\.?\s?\d+|\b(?:19|20)\d\d\b/gi, " ")   // Pokédex no., level and years aren't either
      .replace(/(?<!\d)(\d{2})\s(\d)(?!\d)/g, "$1$2");   // "08 5" -> "085"
    const bare = [...new Set(nt.match(promoSeen || (printYear && printYear <= 2003) ? /(?<!\d)\d{1,3}(?!\d)/g : /(?<!\d)\d{2,3}(?!\d)/g) || [])].slice(0, 14), ints = new Set(bare.map((x) => parseInt(x, 10)));
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
      const promoOk = promoSeen && isPromo(r), era = eraOk(r);
      // One-word names (Switch, Pikachu) need the number too. Without one, the copyright year still narrows it:
      // a card from the right year with no readable set number is most likely a black-star promo.
      const noNum = !nums.strong.length && !nums.weak.length && !numOk, promoGuess = promoOk || (noNum && era && isPromo(r));
      if (ws.length < 2 && !numOk && !era) continue;
      const eraOff = printYear != null && years[r[2]] != null && !era;   // the © year on the card says it's from another set
      add(r, -0.5 + 0.05 * ws.length + (numOk ? 1 : 0) + (era ? 0.3 : 0) + (promoGuess ? 0.3 : 0) - (eraOff ? 0.4 : 0) - (/misprint|error/i.test(r[1]) ? 0.05 : 0));   // add() already counts the name once
      if (numOk && !eraOff && (ws.length > 1 || era || printYear == null)) sureSet.add(r);
    }
    if (!scored.size || Math.max(...scored.values()) < 1.5) {   // only a bare number like "085" (promos) or a misread one: fuzzy-match the name among cards with that number
      const T = tris(letters(nameText));
      if (ints.size) for (const r of data.rows) {
        if (r[3] !== "c" || !ints.has(leadNum(r[5]))) continue;
        const t = tris(letters(r[1])); let m = 0; t.forEach((x) => { if (T.has(x)) m++; });
        // a bare number alone is too common, so some of the name must show too
        const exact = bare.includes(r[5]), ratio = m / Math.max(1, t.size);   // exact = a bare promo number like "085" printed as-is
        if ((exact && (m >= 3 || ratio >= 0.25 || /^0\d\d$/.test(r[5]))) || (m >= 6 && ratio >= 0.5)) { const sc = (exact ? 1.2 : 0) + ratio; if (!scored.has(r) || scored.get(r) < sc) scored.set(r, sc); }
      }
    }
    const list = [...scored].sort((a, b) => b[1] - a[1] || (b[0][4] || 0) - (a[0][4] || 0)).slice(0, 12).map(([r, s]) => ({ s, r }));
    return { nums: [...nums.strong, ...nums.weak], list, sure: list.length > 0 && sureSet.has(list[0].r) && (list.length === 1 || list[1].s < list[0].s) };
  }

  async function scanFile(file, ui, quick = false) {
    const [w, data, c, meta, years] = await Promise.all([getWorker(ui.status), getRows(), crops(file), getMeta(), getYears()]);
    ui.status("Reading the card…");
    const read = async (cv, psm) => { await w.setParameters({ tessedit_pageseg_mode: psm }); return (await w.recognize(cv())).data.text; };
    const t = { bottom: await read(c.bottom, "11") };
    t.name = await read(c.name, "6");
    ui.status("Matching…");
    let text = [t.bottom, t.name].join("\n"), res = match(data, meta, text, t.name, t.bottom, years);
    if (!res.sure && !quick) {                      // not settled: read the whole card too (slower)
      ui.status("Looking closer…");
      t.full = await read(c.full, "3");
      text = [t.bottom, t.name, t.full].join("\n");
      res = match(data, meta, text, t.name + "\n" + t.full.split("\n").slice(0, 3).join("\n"), t.bottom, years);
    }
    return { text, ...res };
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
    // the part of the video inside the on-screen frame (a little margin so the card's edges are in)
    const grab = () => {
      const fr = view.querySelector(".scan-frame").getBoundingClientRect(), vr = video.getBoundingClientRect();
      const vw = video.videoWidth, vh = video.videoHeight; if (!vw) return null;
      const k = Math.max(vr.width / vw, vr.height / vh), ox = (vr.width - vw * k) / 2, oy = (vr.height - vh * k) / 2;
      const mx = fr.width * 0.06, my = fr.height * 0.06;
      const sx = Math.max(0, (fr.left - mx - vr.left - ox) / k), sy = Math.max(0, (fr.top - my - vr.top - oy) / k);
      const sw = Math.min(vw - sx, (fr.width + 2 * mx) / k), sh = Math.min(vh - sy, (fr.height + 2 * my) / k);
      const c = document.createElement("canvas"); c.width = Math.round(sw); c.height = Math.round(sh);
      c.getContext("2d").drawImage(video, sx, sy, sw, sh, 0, 0, c.width, c.height);
      return c;
    };
    view.querySelector(".scan-shoot").addEventListener("click", () => { const c = grab(); if (!c) return; stop(); onShot(c); });
    view.querySelector(".scan-cancel").addEventListener("click", stop);
    return { start, stop, grab, live: () => !!stream };
  }

  window.dysScanMatch = match; window.dysScanFile = scanFile;   // for tests
  window.dysScan = function open() {
    const box = document.createElement("div");
    box.className = "scan-sheet";
    box.innerHTML = `<div class="scan-in"><button class="scan-x" type="button" aria-label="Close">✕</button>
      <h2>Scan a card</h2><p class="muted">Good light, card flat, inside the frame. It reads the name and number and finds the card by itself.</p>
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
    // live mode: keep reading what's in the frame and stop by itself once the card is recognised
    const hint = (t) => { const el = box.querySelector(".scan-frame span"); if (el) el.textContent = t; };
    async function auto() {
      await new Promise((r) => setTimeout(r, 900));
      let tries = 0;
      while (cam.live()) {
        const c = cam.grab();
        if (c) {
          try {
            const res = await scanFile(c, { status: () => {} }, true);
            if (!cam.live()) return;
            if (res.sure) { const url = c.toDataURL("image/jpeg", 0.7); cam.stop(); return show0(res, url); }
            tries++;
            hint(tries < 3 ? "Hold steady… reading" : tries < 6 ? "Move closer: card fills the frame" : "Less glare? Or tap Scan");
          } catch { return; }
        }
        await new Promise((r) => setTimeout(r, 250));
      }
    }
    box.querySelector(".scan-open").addEventListener("click", async () => {
      if (!(await cam.start())) { status("Camera not available here, so pick or take a photo instead."); fileIn.click(); return; }
      status("Point at the card. It scans by itself, or tap Scan."); hint("Hold steady… reading"); auto();
    });
    fileIn.addEventListener("change", () => { const f = fileIn.files && fileIn.files[0]; fileIn.value = ""; if (f) run(f, URL.createObjectURL(f)); });

    let meta = { groups: {} }, rows = null;
    const show = (list, sure) => {
      box.querySelector(".scan-res").innerHTML = list.slice(0, 9).map((r, i) => `<div class="scan-hit${i === 0 && sure ? " best" : ""}">
        <a href="product.html?id=${r[0]}&set=${r[2]}"><img src="https://tcgplayer-cdn.tcgplayer.com/product/${r[0]}_200w.jpg" alt="" loading="lazy">
        <span><b>${esc(r[1])}</b><small>${esc(meta.groups[r[2]]?.[0] || "")}${r[5] ? " · " + esc(r[5]) : ""}</small><em>${money(r[4])}</em></span></a>
        <span class="scan-acts"><button type="button" class="btn" data-add="${i}">＋ Collection</button><button type="button" class="btn" data-want="${i}">♡ Want</button><button type="button" class="btn" data-sell="${i}">💵 Sell</button></span></div>`).join("");
      box.querySelectorAll("[data-add]").forEach((b) => b.addEventListener("click", () => { (window.dysCollectionAdd || window.dysAddToCollection)?.(list[+b.dataset.add]); b.textContent = "✓ Added"; b.disabled = true; }));
      box.querySelectorAll("[data-sell]").forEach((b) => b.addEventListener("click", () => { window.dysSell?.(list[+b.dataset.sell]); b.textContent = "✓ On sell list"; b.disabled = true; }));
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
        await present(await scanFile(input, { status }));
      } catch (err) {
        status("The card reader couldn't load. Check your connection and try again.");
      }
    }
    async function show0(res, url) {
      box.querySelector(".scan-prev").innerHTML = `<img src="${url}" alt="">`;
      await present(res);
    }
    async function present(res) {
      {
        meta = await getMeta(); rows = (await getRows()).rows;
        const best = res.list[0]?.s || 0, good = res.list.filter((x) => x.s >= Math.max(0.6, best * 0.5));
        box.querySelector(".scan-refine").hidden = false;
        if (!good.length) { status("Couldn't read that one. Try again with less glare, or type the number or name below."); return; }
        const sure = res.sure;
        status(sure ? "Found it. Tap to open, add, or ♡." : `${good.length} possible match${good.length > 1 ? "es" : ""}. Pick yours, or narrow it below:`);
        show(good.map((x) => x.r), sure);
      }
    }
  };
})();
