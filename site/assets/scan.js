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

  const canvasOf = (w, h) => { const c = document.createElement("canvas"); c.width = w; c.height = h; return c; };
  /* where the card sits in the photo (axis-aligned), or the whole photo when it already fills it */
  function cardBox(img) {
    const W = img.width, H = img.height, { w, h, d, s } = pixels(img, 200), m = Math.max(2, Math.round(Math.min(w, h) * 0.03)), edge = [[], [], []];
    for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) if (i < m || j < m || i >= w - m || j >= h - m) { const p = (j * w + i) * 4; edge[0].push(d[p]); edge[1].push(d[p + 1]); edge[2].push(d[p + 2]); }
    const med = edge.map((a) => a.sort((x, y) => x - y)[a.length >> 1]), rows = new Uint32Array(h), cols = new Uint32Array(w);
    for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) { const p = (j * w + i) * 4; if (Math.abs(d[p] - med[0]) + Math.abs(d[p + 1] - med[1]) + Math.abs(d[p + 2] - med[2]) > 60) { rows[j]++; cols[i]++; } }
    const r0 = rows.findIndex((n) => n > w * 0.3), r1 = h - 1 - [...rows].reverse().findIndex((n) => n > w * 0.3);
    const c0 = cols.findIndex((n) => n > h * 0.3), c1 = w - 1 - [...cols].reverse().findIndex((n) => n > h * 0.3);
    if (r0 < 0 || c0 < 0 || r1 <= r0 || c1 <= c0) return { x: 0, y: 0, w: W, h: H };
    const bw = (c1 - c0 + 1) / s, bh = (r1 - r0 + 1) / s;
    if (bw * bh < W * H * 0.3 || bw / bh < 0.55 || bw / bh > 0.9) return { x: 0, y: 0, w: W, h: H };
    return { x: c0 / s, y: r0 / s, w: bw, h: bh };
  }
  /* ---------- picture match: compare the photo with a fingerprint of every card (data/prints.bin) ----------
     Fast and works without reading any text. The text reader (above) only runs when the picture isn't clear-cut. */
  let printsP = null, rowById = null;
  const getPrints = () => (printsP ||= fetch("data/prints.bin").then((r) => (r.ok ? r.arrayBuffer() : null)).then((buf) => {
    if (!buf || buf.byteLength % 36) return null;
    const n = buf.byteLength / 36, dv = new DataView(buf), ids = new Uint32Array(n), h32 = new Uint32Array(n * 8);
    for (let i = 0; i < n; i++) { ids[i] = dv.getUint32(i * 36, true); for (let k = 0; k < 8; k++) h32[i * 8 + k] = dv.getUint32(i * 36 + 4 + k * 4, false); }
    return { n, ids, h32 };
  }).catch(() => null));
  const POP = new Uint8Array(256).map((_, i) => { let c = 0; for (let x = i; x; x >>= 1) c += x & 1; return c; });
  const pixels = (img, maxSide) => {
    const s = Math.min(1, maxSide / Math.max(img.width, img.height)), w = Math.max(8, Math.round(img.width * s)), h = Math.max(8, Math.round(img.height * s));
    const c = canvasOf(w, h), x = c.getContext("2d", { willReadFrequently: true });
    x.imageSmoothingQuality = "high"; x.drawImage(img, 0, 0, w, h);
    return { w, h, d: x.getImageData(0, 0, w, h).data, s };
  };
  /* the card's four corners (TL, TR, BR, BL) in the photo, found against the surface around it */
  function quad(img) {
    const { w, h, d, s } = pixels(img, 300), m = Math.max(2, Math.round(Math.min(w, h) * 0.03)), edge = [[], [], []];
    for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) if (i < m || j < m || i >= w - m || j >= h - m) { const p = (j * w + i) * 4; edge[0].push(d[p]); edge[1].push(d[p + 1]); edge[2].push(d[p + 2]); }
    const med = edge.map((a) => a.sort((x, y) => x - y)[a.length >> 1]);
    const on = new Uint8Array(w * h), rc = new Uint32Array(h), cc = new Uint32Array(w);
    for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) { const p = (j * w + i) * 4; if (Math.abs(d[p] - med[0]) + Math.abs(d[p + 1] - med[1]) + Math.abs(d[p + 2] - med[2]) > 60) { on[j * w + i] = 1; rc[j]++; cc[i]++; } }
    let n = 0, tl = [0, 0, 1e9], br = [0, 0, -1e9], tr = [0, 0, -1e9], bl = [0, 0, 1e9];
    for (let j = 0; j < h; j++) { if (rc[j] <= w * 0.15) continue; for (let i = 0; i < w; i++) {
      if (!on[j * w + i] || cc[i] <= h * 0.15) continue; n++;
      const a = i + j, b = i - j;
      if (a < tl[2]) tl = [i, j, a]; if (a > br[2]) br = [i, j, a]; if (b > tr[2]) tr = [i, j, b]; if (b < bl[2]) bl = [i, j, b];
    } }
    if (n < w * h * 0.25) return null;
    const q = [tl, tr, br, bl].map(([x, y]) => [x / s, y / s]);
    const wt = Math.hypot(q[1][0] - q[0][0], q[1][1] - q[0][1]), ht = Math.hypot(q[3][0] - q[0][0], q[3][1] - q[0][1]);
    return ht && wt / ht > 0.5 && wt / ht < 0.95 ? q : null;
  }
  /* straighten the card to 250x350 (perspective), or just scale the card's box / the whole photo */
  /* the card's straight edges: strong vertical edges (left/right) and horizontal edges (top/bottom) that frame a
     card-shaped (5:7) box. Works on busy backgrounds (a hand, a table, a sleeve) where the colour test can't. */
  function rects(img) {
    const { w, h, d, s } = pixels(img, 360), ex = new Uint8Array(w * h), ey = new Uint8Array(w * h), T = 18;
    const ch = (i, j) => Math.max(Math.abs(d[i] - d[j]), Math.abs(d[i + 1] - d[j + 1]), Math.abs(d[i + 2] - d[j + 2]));
    for (let y = 1; y < h - 1; y++) for (let x = 1; x < w - 1; x++) {
      const i = y * w + x, gx = ch((i + 1) * 4, (i - 1) * 4), gy = ch((i + w) * 4, (i - w) * 4);
      if (gx > T && gx >= gy) ex[i] = 1; if (gy > T && gy >= gx) ey[i] = 1;
    }
    // longest nearly-unbroken line in each row / column (a card edge is one long line, text is many short ones)
    const run = (get, n) => { let best = 0, cur = 0, gap = 0; for (let k = 0; k < n; k++) { if (get(k)) { cur += 1 + gap; gap = 0; if (cur > best) best = cur; } else if (++gap > 3) { cur = 0; gap = 0; } } return best; };
    const rr = Array.from({ length: h }, (_, y) => run((x) => ey[y * w + x] || (y > 0 && ey[(y - 1) * w + x]) || (y < h - 1 && ey[(y + 1) * w + x]), w));
    const cc = Array.from({ length: w }, (_, x) => run((y) => ex[y * w + x] || (x > 0 && ex[y * w + x - 1]) || (x < w - 1 && ex[y * w + x + 1]), h));
    const peaks = (a, n, min) => { const out = []; for (const i of [...a.keys()].sort((p, q) => a[q] - a[p])) { if (a[i] < min) break; if (out.every((j) => Math.abs(j - i) > 3)) out.push(i); if (out.length >= n) break; } return out; };
    const cols = peaks(cc, 8, h * 0.2), rows = peaks(rr, 8, w * 0.2);
    rects.lines = { cols, rows, cc, rr, s, w, h };
    const band = (m, x0, y0, x1, y1, vert) => {   // share of the line with an edge within ±2px
      let hit = 0, n = 0;
      if (vert) for (let y = Math.max(0, y0); y <= Math.min(h - 1, y1); y += 2) { n++; for (let k = -2; k <= 2; k++) { const x = x0 + k; if (x >= 0 && x < w && m[y * w + x]) { hit++; break; } } }
      else for (let x = Math.max(0, x0); x <= Math.min(w - 1, x1); x += 2) { n++; for (let k = -2; k <= 2; k++) { const y = y0 + k; if (y >= 0 && y < h && m[y * w + x]) { hit++; break; } } }
      return n ? hit / n : 0; };
    const found = [], R = 63 / 88;
    for (const xa of cols) for (const xb of cols) {
      if (xb - xa < w * 0.3) continue;
      const x0 = xa, x1 = xb, H = (x1 - x0) / R, side = (band(ex, x0, 0, x0, h, 1) + band(ex, x1, 0, x1, h, 1)) / 2;
      const add = (y0, y1, edges) => {
        if (y1 - y0 < h * 0.2 || y0 < -0.06 * h || y1 > 1.06 * h) return;
        const r = (x1 - x0) / (y1 - y0); if (r < 0.64 || r > 0.8) return;
        const lr = (band(ex, x0, y0, x0, y1, 1) + band(ex, x1, y0, x1, y1, 1)) / 2;
        const tb = edges.map((y) => band(ey, x0, y, x1, y, 0));
        const sc = (lr * 2 + tb.reduce((p, q) => p + q, 0)) / (2 + tb.length) - (tb.length < 2 ? 0.08 : 0) + 0.15 * (x1 - x0) / w;
        found.push({ x: x0 / s, y: y0 / s, w: (x1 - x0) / s, h: (y1 - y0) / s, sc });
      };
      for (const ya of rows) {
        add(ya, ya + H, [ya]);          // top edge seen, bottom from the card's shape
        add(ya - H, ya, [ya]);          // bottom edge seen
        for (const yb of rows) if (yb > ya) add(ya, yb, [ya, yb]);
      }
      if (side > 0) {}
    }
    found.sort((p, q) => q.sc - p.sc);
    const out = [];
    for (const r of found) { if (r.sc < 0.42) break; if (out.every((o) => Math.abs(o.x - r.x) + Math.abs(o.y - r.y) > 0.04 * (o.w + o.h))) out.push(r); if (out.length >= 3) break; }
    return out;
  }
  /* 250x350 views of the card to compare: straight-edge boxes (with small shifts, since the edge of a sleeve or a
     shadow can be a few pixels off), the perspective-corrected card, and the plain colour box. */
  /* grayscale integral image of the photo, so the fingerprint of any rectangle costs a few hundred lookups */
  function grayOf(img) {
    const { w, h, d, s } = pixels(img, 1000), I = new Float64Array((w + 1) * (h + 1));
    for (let y = 0; y < h; y++) { let row = 0; for (let x = 0; x < w; x++) { const p = (y * w + x) * 4; row += d[p] * 0.299 + d[p + 1] * 0.587 + d[p + 2] * 0.114; I[(y + 1) * (w + 1) + x + 1] = I[y * (w + 1) + x + 1] + row; } }
    return { I, w, h, s };
  }
  /* same 256-bit hash as fingerprint(viewOf(img, r)): the card's inner area (x 12..238, y 12..338 of 250x350) averaged into 17x16 cells */
  function fpRect(G, r) {
    const { I, w: W, h: H, s } = G, R = W + 1;
    const at = (y, x) => { y = Math.min(H, Math.max(0, y)); x = Math.min(W, Math.max(0, x)); const y0 = Math.floor(y), x0 = Math.floor(x), y1 = Math.min(y0 + 1, H), x1 = Math.min(x0 + 1, W), fy = y - y0, fx = x - x0;
      return I[y0 * R + x0] * (1 - fy) * (1 - fx) + I[y0 * R + x1] * (1 - fy) * fx + I[y1 * R + x0] * fy * (1 - fx) + I[y1 * R + x1] * fy * fx; };
    const x0 = (r.x + r.w * 12 / 250) * s, y0 = (r.y + r.h * 12 / 350) * s, cw = (r.w * 226 / 250) * s / 17, chh = (r.h * 326 / 350) * s / 16, A = cw * chh;
    const g = new Float64Array(17 * 16);
    for (let j = 0; j < 16; j++) for (let i = 0; i < 17; i++) { const xa = x0 + i * cw, ya = y0 + j * chh; g[j * 17 + i] = (at(ya + chh, xa + cw) - at(ya, xa + cw) - at(ya + chh, xa) + at(ya, xa)) / A; }
    const out = new Uint8Array(32);
    for (let j = 0, k = 0; j < 16; j++) for (let i = 0; i < 16; i++, k++) if (g[j * 17 + i + 1] > g[j * 17 + i]) out[k >> 3] |= 128 >> (k & 7);
    return out;
  }
  /* a 250x350 view of the photo inside rectangle r */
  let vc = null;
  function viewOf(img, r) {
    vc ||= canvasOf(250, 350).getContext("2d", { willReadFrequently: true });
    vc.imageSmoothingQuality = "high"; vc.fillStyle = "#000"; vc.fillRect(0, 0, 250, 350);
    vc.drawImage(img, r.x, r.y, r.w, r.h, 0, 0, 250, 350);
    return vc.getImageData(0, 0, 250, 350).data;
  }
  /* rough guesses where the card is: straight-edge boxes, the colour box, and (for a camera frame, which has a
     margin around the card) the middle of the picture */
  function roughRects(img, quick) {
    const W = img.width, H = img.height, out = [...rects(img)], b = cardBox(img), L = rects.lines;
    out.push(b);
    // the card's long sides are the most reliable lines: for the strongest pairs of columns, slide a card-shaped
    // box up and down (its top or bottom edge is often lost against a light background or a sleeve)
    const pairs = [];
    for (const a of L.cols) for (const c of L.cols) if (c - a >= L.w * 0.3) pairs.push([a, c, L.cc[a] + L.cc[c]]);
    pairs.sort((p, q) => q[2] - p[2]);
    for (const [a, c] of quick || !SLIDE ? [] : pairs.slice(0, 2)) {
      const bw = (c - a) / L.s, bh = bw * 88 / 63;
      for (let y = -0.04 * bh; y + bh <= H + 0.04 * bh; y += bh * 0.025) for (const dx of [-0.015, 0, 0.015]) out.push({ x: a / L.s + dx * bw, y, w: bw, h: bh, slide: true });
    }
    if (out[0]) out[0].fixed = true;
    for (const k of [0.86, 0.92]) { const w = Math.min(W * k, H * k * 63 / 88), h = w * 88 / 63; out.push({ x: (W - w) / 2, y: (H - h) / 2, w, h, fixed: W / H > 0.6 && W / H < 0.85 }); }
    if (W / H > 0.6 && W / H < 0.85) out.push({ x: 0, y: 0, w: W, h: H, fixed: true });
    b.fixed = true;
    return out.filter((r, i) => r.slide || out.findIndex((o) => Math.abs(o.x - r.x) + Math.abs(o.y - r.y) + Math.abs(o.w - r.w) < 0.01 * (r.w + r.h)) === i);
  }
  const pc = (x) => { x -= (x >>> 1) & 0x55555555; x = (x & 0x33333333) + ((x >>> 2) & 0x33333333); return (((x + (x >>> 4)) & 0x0f0f0f0f) * 0x01010101) >>> 24; };
  const toWords = (fp) => { const dv = new DataView(fp.buffer); return Uint32Array.from({ length: 8 }, (_, k) => dv.getUint32(k * 4, false)); };
  /* best distance per card over a set of fingerprints; returns the closest [index, distance] pairs */
  function nearest(P, fps, keep = 8) {
    const W = fps.map(toWords), H = P.h32, top = [];
    let cut = 257;
    for (let i = 0; i < P.n; i++) {
      const o = i * 8; let dist = 256;
      for (const f of W) { const t = pc(H[o] ^ f[0]) + pc(H[o + 1] ^ f[1]) + pc(H[o + 2] ^ f[2]) + pc(H[o + 3] ^ f[3]) + pc(H[o + 4] ^ f[4]) + pc(H[o + 5] ^ f[5]) + pc(H[o + 6] ^ f[6]) + pc(H[o + 7] ^ f[7]); if (t < dist) dist = t; }
      if (dist < cut) { top.push([i, dist]); top.sort((a, b) => a[1] - b[1]); if (top.length > keep) top.pop(); if (top.length === keep) cut = top[keep - 1][1]; }
    }
    return top;
  }
  function warpQuad(img, q) {
    const out = canvasOf(250, 350), ox = out.getContext("2d", { willReadFrequently: true });
    const src = pixels(img, 1000), k = src.s;
    // homography from the 250x350 output to the photo (solve the 8 unknowns)
    const dst = [[0, 0], [250, 0], [250, 350], [0, 350]], A = [], B = [];
    dst.forEach(([x, y], i) => { const [u, v] = [q[i][0] * k, q[i][1] * k]; A.push([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.push(u); A.push([0, 0, 0, x, y, 1, -v * x, -v * y]); B.push(v); });
    for (let c = 0; c < 8; c++) {
      let piv = c; for (let r = c + 1; r < 8; r++) if (Math.abs(A[r][c]) > Math.abs(A[piv][c])) piv = r;
      [A[c], A[piv]] = [A[piv], A[c]]; [B[c], B[piv]] = [B[piv], B[c]];
      for (let r = 0; r < 8; r++) { if (r === c) continue; const f = A[r][c] / A[c][c]; for (let cc = c; cc < 8; cc++) A[r][cc] -= f * A[c][cc]; B[r] -= f * B[c]; }
    }
    const H = B.map((b, i) => b / A[i][i]), od = ox.createImageData(250, 350), o = od.data, sd = src.d, SW = src.w, SH = src.h;
    for (let y = 0; y < 350; y++) for (let x = 0; x < 250; x++) {
      const z = H[6] * x + H[7] * y + 1, u = (H[0] * x + H[1] * y + H[2]) / z, v = (H[3] * x + H[4] * y + H[5]) / z;
      const x0 = Math.max(0, Math.min(SW - 2, Math.floor(u))), y0 = Math.max(0, Math.min(SH - 2, Math.floor(v))), fx = Math.min(1, Math.max(0, u - x0)), fy = Math.min(1, Math.max(0, v - y0));
      const p = (y * 250 + x) * 4, a = (y0 * SW + x0) * 4, b = a + 4, c2 = a + SW * 4, e = c2 + 4;
      for (let ch = 0; ch < 3; ch++) o[p + ch] = (sd[a + ch] * (1 - fx) + sd[b + ch] * fx) * (1 - fy) + (sd[c2 + ch] * (1 - fx) + sd[e + ch] * fx) * fy;
      o[p + 3] = 255;
    }
    return o;
  }
  /* 256-bit difference hash, identical to tools/card_prints.py */
  function fingerprint(d) {
    const W = 226, H = 326, I = new Float64Array((W + 1) * (H + 1));
    for (let y = 0; y < H; y++) { let row = 0; for (let x = 0; x < W; x++) { const p = ((y + 12) * 250 + x + 12) * 4; row += d[p] * 0.299 + d[p + 1] * 0.587 + d[p + 2] * 0.114; I[(y + 1) * (W + 1) + x + 1] = I[y * (W + 1) + x + 1] + row; } }
    const at = (y, x) => { const y0 = Math.floor(y), x0 = Math.floor(x), y1 = Math.min(y0 + 1, H), x1 = Math.min(x0 + 1, W), fy = y - y0, fx = x - x0, R = W + 1;
      return I[y0 * R + x0] * (1 - fy) * (1 - fx) + I[y0 * R + x1] * (1 - fy) * fx + I[y1 * R + x0] * fy * (1 - fx) + I[y1 * R + x1] * fy * fx; };
    const g = new Float64Array(17 * 16), xs = Array.from({ length: 18 }, (_, i) => (i * W) / 17), ys = Array.from({ length: 17 }, (_, i) => (i * H) / 16);
    for (let j = 0; j < 16; j++) for (let i = 0; i < 17; i++) g[j * 17 + i] = (at(ys[j + 1], xs[i + 1]) - at(ys[j], xs[i + 1]) - at(ys[j + 1], xs[i]) + at(ys[j], xs[i])) / ((ys[j + 1] - ys[j]) * (xs[i + 1] - xs[i]));
    const out = new Uint8Array(32);
    for (let j = 0, k = 0; j < 16; j++) for (let i = 0; i < 16; i++, k++) if (g[j * 17 + i + 1] > g[j * 17 + i]) out[k >> 3] |= 128 >> (k & 7);
    return out;
  }
  async function visual(file, quick = false) {
    const [P, data] = await Promise.all([getPrints(), getRows()]);
    if (!P) return null;
    if (!rowById) { rowById = new Map(); for (const r of data.rows) if (r[3] === "c" && !rowById.has(r[0])) rowById.set(r[0], r); }
    const img = file instanceof HTMLCanvasElement ? file : await createImageBitmap(file);
    // The match is sensitive to a 1-2% offset, so: 1) look around every rough guess and keep the cards that come
    // close (a shortlist), 2) search finely around the most promising guesses against that shortlist only.
    const G = grayOf(img), fpOf = (r) => fpRect(G, r);
    const around = (r, st, n = 1, ks = [1]) => { const o = []; for (const k of ks) for (let a = -n; a <= n; a++) for (let b = -n; b <= n; b++) {
      const w = r.w * k, h = r.h * k; o.push({ x: r.x + (r.w - w) / 2 + a * st * r.w, y: r.y + (r.h - h) / 2 + b * st * r.h, w, h }); } return o; };
    const lead = (t) => t[0][1] - 0.5 * ((t[1] || t[0])[1] - t[0][1]);
    const short = new Set(), stage = roughRects(img, quick).map((r) => {
      const t = nearest(P, (r.slide ? [r] : around(r, 0.02)).map(fpOf), r.slide ? 12 : 40); t.forEach(([i]) => short.add(i)); return { r, d: lead(t) };
    }).sort((a, b) => a.d - b.d);
    const S = { n: short.size, ids: new Uint32Array(short.size), h32: new Uint32Array(short.size * 8), from: [...short] };
    S.from.forEach((i, j) => { S.ids[j] = P.ids[i]; S.h32.set(P.h32.subarray(i * 8, i * 8 + 8), j * 8); });
    const best = (r) => lead(nearest(S, [fpOf(r)], 2));
    let cand = [...stage.slice(0, quick ? 3 : 6), ...stage.filter((x) => x.r.fixed)].filter((x, i, a) => a.indexOf(x) === i);
    cand = cand.flatMap((c) => around(c.r, 0.01, 3, [0.97, 0.985, 1, 1.015, 1.03])).map((r) => ({ r, d: best(r) })).sort((a, b) => a.d - b.d).slice(0, 5);
    cand = cand.flatMap((c) => around(c.r, 0.004, 1, [0.994, 1, 1.006])).map((r) => ({ r, d: best(r) })).sort((a, b) => a.d - b.d).slice(0, 6);
    const fps = cand.map((c) => fpOf(c.r));
    const q = quad(img); if (q) fps.push(fingerprint(warpQuad(img, q)));
    const top = nearest(S, fps).map(([j, d]) => [S.from[j], d]);
    // keep the best match and only real look-alikes of it (stamped promos, reprints with the same art)
    const list = top.map(([i, dist]) => ({ r: rowById.get(P.ids[i]), s: 2 - dist / 128, d: dist })).filter((x, i, a) => x.r && x.d <= a[0].d + 18);
    const d1 = top[0]?.[1] ?? 256, d2 = top[1]?.[1] ?? 256;
    return { list, d1, d2, sure: d1 <= SURE_D && d2 - d1 >= SURE_GAP };
  }
  const SURE_D = 72, SURE_GAP = 12, SLIDE = true;

  async function scanFile(file, ui, quick = false) {
    const v = await visual(file, quick).catch(() => null);
    if (v && (v.sure || quick)) return { text: "", nums: [], list: v.list.slice(0, 6), sure: v.sure, d: [v.d1, v.d2] };
    const [w, data, c, meta, years] = await Promise.all([getWorker(ui.status), getRows(), crops(file), getMeta(), getYears()]);
    ui.status("Reading the card…");
    const txt = {};
    for (const [k, cv] of Object.entries(c)) { const r = await w.recognize(cv); txt[k] = r.data.text; ui.status(k === "top" ? "Matching…" : "Reading the card…"); }
    const text = [txt.bottom, txt.corner, txt.full, txt.top].join("\n");
    const res = match(data, meta, text, txt.top, txt.corner + "\n" + txt.bottom, years);
    if (!v || res.sure) return { text, ...res };
    // picture and text together: a card that both point to wins; otherwise the closest pictures first
    const ocrIds = new Set(res.list.map((x) => x.r[0])), both = v.list.filter((x) => ocrIds.has(x.r[0]));
    const list = [...both, ...(v.d1 <= 100 ? v.list : []), ...res.list].filter((x, i, a) => a.findIndex((y) => y.r[0] === x.r[0]) === i).slice(0, 9);
    return { text, nums: res.nums, list, sure: both.length > 0 && both[0] === v.list[0] && v.d1 <= 95, d: [v.d1, v.d2] };
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
    // the part of the video inside the on-screen frame, with a margin so the card's edges and corners are in
    const grab = () => {
      const fr = view.querySelector(".scan-frame").getBoundingClientRect(), vr = video.getBoundingClientRect();
      const vw = video.videoWidth, vh = video.videoHeight; if (!vw) return null;
      const k = Math.max(vr.width / vw, vr.height / vh), ox = (vr.width - vw * k) / 2, oy = (vr.height - vh * k) / 2;
      const mx = fr.width * 0.08, my = fr.height * 0.06;
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
      <h2>Scan a card</h2><p class="muted">Lay the card flat in good light and fit it inside the frame. It recognises the card by its picture, so it works on sleeved cards too.</p>
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
    // live: keep matching what's in the frame and stop by itself once the same card shows up twice in a row
    const hint = (t) => { const el = box.querySelector(".scan-frame span"); if (el) el.textContent = t; };
    async function auto() {
      let last = null, tries = 0, same = 0;
      while (cam.live()) {
        await new Promise((r) => setTimeout(r, 300));
        const c = cam.live() && cam.grab();
        if (!c) continue;
        const res = await scanFile(c, { status: () => {} }, true).catch(() => null);
        if (!cam.live() || !res) continue;
        // same card twice in a row = done; a close look-alike pair (stamped promos, reprints) settles after a few frames
        const top = res.list[0], id = top && top.d <= SURE_D ? top.r[0] : null;
        same = id && id === last ? same + 1 : 1;
        if (id && ((res.sure && same >= 2) || same >= 4)) { const url = c.toDataURL("image/jpeg", 0.7); cam.stop(); return show0(res, url); }
        last = id; tries++;
        hint(id ? "Got it… hold still" : tries < 8 ? "Hold the card flat inside the frame" : tries < 20 ? "Move a little closer, avoid glare" : "Tap Scan to read the text instead");
      }
    }
    box.querySelector(".scan-open").addEventListener("click", async () => {
      if (!(await cam.start())) { status("Camera not available here, so pick or take a photo instead."); fileIn.click(); return; }
      status("Point at the card. It finds it by itself, or tap Scan."); hint("Hold the card flat inside the frame"); auto();
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
      status("Matching…");
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
