/* Drive Your Style: centering check.
   The photo never leaves the phone: it is drawn to a canvas, the card edges and print borders are
   found with a simple edge profile, and the user fine-tunes 8 guide lines by dragging. */
(() => {
  // Published centering limits: worst side of left/right or top/bottom, as the bigger share (55 = 55/45).
  const PSA = [[10, 55, 75], [9, 60, 90], [8, 65, 90], [7, 70, 90], [6, 80, 90], [5, 85, 90], [4, 85, 90], [3, 90, 90], [2, 90, 90]];
  const CGC = [[10, 55, 75], [9, 60, 90], [8, 65, null], [7.5, 65, null], [7, 70, null], [6, 75, null], [4.5, 85, null], [3.5, 90, null]];
  const KEYS = ["oL", "iL", "iR", "oR", "oT", "iT", "iB", "oB"];
  const VERT = { oL: 1, iL: 1, iR: 1, oR: 1 };
  const MAXW = 1600;

  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const sides = { front: null, back: null };   // {src: canvas, rot, g, work: canvas}
  let side = "front", drag = null, sel = null, view = { s: 1 }, root;

  /* ---------- measuring ---------- */
  function measure(g) {
    if (!g) return null;
    const L = g.iL - g.oL, R = g.oR - g.iR, T = g.iT - g.oT, B = g.oB - g.iB;
    if (L <= 0 || R <= 0 || T <= 0 || B <= 0) return null;
    const lr = (L / (L + R)) * 100, tb = (T / (T + B)) * 100;
    const r1 = (v) => Math.round(v * 10) / 10;   // judge on the number we show
    return { lr: r1(lr), tb: r1(tb), worst: r1(Math.max(lr, 100 - lr, tb, 100 - tb)) };
  }
  const pair = (p) => `${p.toFixed(1)}/${(100 - p).toFixed(1)}`;
  const worstPair = (p) => { const w = Math.max(p, 100 - p); return `${Math.round(w)}/${Math.round(100 - w)}`; };
  function best(table, f, b) {
    for (const [grade, fr, bk] of table) {
      if (f > fr + 0.0001) continue;
      if (b != null && bk != null && b > bk + 0.0001) continue;
      return grade;
    }
    return null;
  }

  /* ---------- image handling ---------- */
  function load(file) {
    return new Promise((ok, bad) => {
      const url = URL.createObjectURL(file), im = new Image();
      im.onload = () => {
        const s = Math.min(1, MAXW / Math.max(im.naturalWidth, im.naturalHeight));
        const c = document.createElement("canvas");
        c.width = Math.round(im.naturalWidth * s); c.height = Math.round(im.naturalHeight * s);
        c.getContext("2d").drawImage(im, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url); ok(c);
      };
      im.onerror = () => { URL.revokeObjectURL(url); bad(new Error("That file isn't a photo we can open. Try a JPG or PNG.")); };
      im.src = url;
    });
  }
  function rotated(src, deg) {
    const c = document.createElement("canvas"); c.width = src.width; c.height = src.height;
    const x = c.getContext("2d");
    x.fillStyle = "#000"; x.fillRect(0, 0, c.width, c.height);
    x.translate(c.width / 2, c.height / 2); x.rotate((deg * Math.PI) / 180); x.drawImage(src, -src.width / 2, -src.height / 2);
    return c;
  }

  /* Edge profiles on a small grayscale copy: strongest steps near the outside are the card edges,
     the next strong steps inward are the print borders. A starting point the user then adjusts. */
  function detect(work) {
    const s = Math.min(1, 700 / Math.max(work.width, work.height));
    const w = Math.max(40, Math.round(work.width * s)), h = Math.max(40, Math.round(work.height * s));
    const c = document.createElement("canvas"); c.width = w; c.height = h;
    const x = c.getContext("2d", { willReadFrequently: true }); x.drawImage(work, 0, 0, w, h);
    const d = x.getImageData(0, 0, w, h).data, gray = new Float32Array(w * h);
    for (let i = 0; i < w * h; i++) gray[i] = 0.299 * d[i * 4] + 0.587 * d[i * 4 + 1] + 0.114 * d[i * 4 + 2];
    const prof = (n, along, from, to) => {
      const p = new Float32Array(n);
      for (let a = 1; a < n - 1; a++) {
        let sum = 0;
        for (let b = from; b < to; b++) sum += along ? Math.abs(gray[b * w + a + 1] - gray[b * w + a - 1]) : Math.abs(gray[(a + 1) * w + b] - gray[(a - 1) * w + b]);
        p[a] = sum;
      }
      const q = new Float32Array(n);
      for (let a = 1; a < n - 1; a++) q[a] = (p[a - 1] + 2 * p[a] + p[a + 1]) / 4;
      return q;
    };
    const peak = (p, a, b) => { a = Math.max(1, Math.round(a)); b = Math.min(p.length - 2, Math.round(b)); let m = a; for (let i = a; i <= b; i++) if (p[i] > p[m]) m = i; return m; };
    const col = prof(w, true, Math.round(h * 0.3), Math.round(h * 0.7));
    const oL = peak(col, 1, w * 0.35), oR = peak(col, w * 0.65, w - 2), cw = Math.max(10, oR - oL);
    const row = prof(h, false, Math.round(oL + cw * 0.3), Math.round(oR - cw * 0.3));
    const oT = peak(row, 1, h * 0.35), oB = peak(row, h * 0.65, h - 2), ch = Math.max(10, oB - oT);
    const g = {
      oL, oR, oT, oB,
      iL: peak(col, oL + cw * 0.012, oL + cw * 0.16), iR: peak(col, oR - cw * 0.16, oR - cw * 0.012),
      iT: peak(row, oT + ch * 0.012, oT + ch * 0.16), iB: peak(row, oB - ch * 0.16, oB - ch * 0.012),
    };
    for (const k of KEYS) g[k] = (g[k] + 0.5) / s;
    return fix(refine(work, g, Math.ceil(1.5 / s) + 1));
  }
  /* Snap each line to the strongest full-resolution step near it, to a fraction of a pixel. */
  function refine(work, g, r) {
    const W = work.width, H = work.height, d = work.getContext("2d", { willReadFrequently: true }).getImageData(0, 0, W, H).data;
    const Y = (x, y) => { const i = (y * W + x) * 4; return 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]; };
    const span = (a, b) => { const lo = Math.max(1, Math.round(a)), hi = Math.min(Math.round(b), 1e9); return [lo, hi]; };
    const out = { ...g };
    for (const k of KEYS) {
      const vert = !!VERT[k], n = vert ? W : H;
      const [b0, b1] = vert ? span(g.oT + (g.oB - g.oT) * 0.3, g.oT + (g.oB - g.oT) * 0.7) : span(g.oL + (g.oR - g.oL) * 0.3, g.oL + (g.oR - g.oL) * 0.7);
      const step = Math.max(1, Math.floor((b1 - b0) / 200));
      const c = Math.round(g[k]), lo = Math.max(1, c - r), hi = Math.min(n - 2, c + r), p = {};
      for (let a = lo - 1; a <= hi + 1; a++) {
        if (a < 1 || a > n - 2) { p[a] = 0; continue; }
        let sum = 0;
        for (let b = b0; b < Math.min(b1, vert ? H - 1 : W - 1); b += step) sum += vert ? Math.abs(Y(a + 1, b) - Y(a - 1, b)) : Math.abs(Y(b, a + 1) - Y(b, a - 1));
        p[a] = sum;
      }
      let m = lo; for (let a = lo; a <= hi; a++) if (p[a] > p[m]) m = a;
      const l = p[m - 1] || 0, rr = p[m + 1] || 0, den = l - 2 * p[m] + rr;   // parabola through the peak
      out[k] = m + (den < 0 ? Math.max(-0.5, Math.min(0.5, 0.5 * (l - rr) / den)) : 0);
    }
    return out;
  }
  function fix(g) {   // keep outer < inner < inner < outer with at least 1px between
    const o = (a, b, c, d) => { g[b] = Math.max(g[b], g[a] + 1); g[c] = Math.max(g[c], g[b] + 1); g[d] = Math.max(g[d], g[c] + 1); };
    o("oL", "iL", "iR", "oR"); o("oT", "iT", "iB", "oB");
    return g;
  }

  /* ---------- drawing ---------- */
  const cv = () => root.querySelector("#cz-cv");
  function draw() {
    const st = sides[side], c = cv();
    if (!st || !c) return;
    const box = root.querySelector("#cz-stage"), maxW = box.clientWidth, maxH = Math.min(window.innerHeight * 0.72, 760);
    const s = Math.min(maxW / st.work.width, maxH / st.work.height), dpr = window.devicePixelRatio || 1;
    view.s = s;
    const W = Math.round(st.work.width * s), H = Math.round(st.work.height * s);
    c.style.width = W + "px"; c.style.height = H + "px"; c.width = Math.round(W * dpr); c.height = Math.round(H * dpr);
    const x = c.getContext("2d"); x.setTransform(dpr, 0, 0, dpr, 0, 0);
    x.drawImage(st.work, 0, 0, W, H);
    const g = st.g;
    // shade the borders being measured
    x.fillStyle = "rgba(94,231,255,.16)";
    x.fillRect(g.oL * s, g.oT * s, (g.iL - g.oL) * s, (g.oB - g.oT) * s); x.fillRect(g.iR * s, g.oT * s, (g.oR - g.iR) * s, (g.oB - g.oT) * s);
    x.fillRect(g.iL * s, g.oT * s, (g.iR - g.iL) * s, (g.iT - g.oT) * s); x.fillRect(g.iL * s, g.iB * s, (g.iR - g.iL) * s, (g.oB - g.iB) * s);
    for (const k of KEYS) line(x, k, g[k] * s, W, H, 1);
    if (drag) loupe(x, W, H);
  }
  function line(x, k, v, W, H, z) {
    const outer = k[0] === "o", on = k === sel || (drag && drag.k === k);
    x.save();
    x.strokeStyle = outer ? "#5ee7ff" : "#ff7ad9"; x.lineWidth = (on ? 2.5 : 1.5) / z;
    if (!outer) x.setLineDash([6 / z, 4 / z]);
    x.beginPath();
    if (VERT[k]) { x.moveTo(v, 0); x.lineTo(v, H); } else { x.moveTo(0, v); x.lineTo(W, v); }
    x.stroke(); x.restore();
  }
  function loupe(x, W, H) {
    const st = sides[side], s = view.s, z = 4, r = Math.min(70, W * 0.2);
    const k = drag.k, gx = VERT[k] ? st.g[k] : drag.px / s, gy = VERT[k] ? drag.py / s : st.g[k];
    const cx = gx * s < W / 2 ? W - r - 10 : r + 10, cy = r + 10;
    x.save();
    x.beginPath(); x.arc(cx, cy, r, 0, Math.PI * 2); x.clip();
    x.fillStyle = "#000"; x.fillRect(cx - r, cy - r, r * 2, r * 2);
    x.translate(cx, cy); x.scale(s * z, s * z); x.translate(-gx, -gy);
    x.drawImage(st.work, 0, 0);
    for (const kk of KEYS) line(x, kk, st.g[kk], st.work.width, st.work.height, s * z);
    x.restore();
    x.save(); x.strokeStyle = "#fff"; x.lineWidth = 2; x.beginPath(); x.arc(cx, cy, r, 0, Math.PI * 2); x.stroke(); x.restore();
  }

  /* ---------- interaction ---------- */
  function hit(px, py) {
    const g = sides[side].g, s = view.s; let best = null, bd = 22;
    for (const k of KEYS) {
      const d = Math.abs((VERT[k] ? px : py) - g[k] * s);
      // inside the card prefer the inner line when two are close
      if (d < bd || (d === bd && k[0] === "i")) { bd = d; best = k; }
    }
    return best;
  }
  let raf = 0;
  function paintNudge() {
    const n = root.querySelector("#cz-nudge"); if (!n) return;
    n.hidden = !sel || !sides[side];
    if (!sel) return;
    const v = VERT[sel], names = { oL: "Left edge", iL: "Left border", iR: "Right border", oR: "Right edge", oT: "Top edge", iT: "Top border", iB: "Bottom border", oB: "Bottom edge" };
    n.querySelector(".cz-nl").textContent = names[sel] || "Line";
    n.querySelector('[data-d="-1"]').textContent = v ? "◀" : "▲";
    n.querySelector('[data-d="1"]').textContent = v ? "▶" : "▼";
  }
  function nudge(dir) {
    if (!sel || !sides[side]) return;
    const st = sides[side], lim = VERT[sel] ? st.work.width : st.work.height;
    st.g[sel] = Math.max(0, Math.min(lim, st.g[sel] + dir * Math.max(0.5, 1 / Math.max(view.s, 0.2) * 0.5)));
    clamp(sel); draw(); readout();
  }
  function pos(e) { const r = cv().getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; }
  function bind() {
    const c = cv();
    c.addEventListener("pointerdown", (e) => {
      if (!sides[side]) return;
      const [px, py] = pos(e), k = hit(px, py);
      if (!k) return;
      e.preventDefault(); c.setPointerCapture(e.pointerId);
      // precision drag: the line moves slower than the finger (finer control), and we keep a short history
      // so the tiny slip when a finger lifts off doesn't move the line
      const gain = e.pointerType === "mouse" ? 0.6 : 0.35;
      sel = k; drag = { k, px, py, start: sides[side].g[k], from: VERT[k] ? px : py, gain, touch: e.pointerType !== "mouse", hist: [[performance.now(), sides[side].g[k]]] };
      paintNudge(); draw();
    });
    c.addEventListener("pointermove", (e) => {
      if (!drag) { if (sides[side]) { const [px, py] = pos(e); const k = hit(px, py); c.style.cursor = k ? (VERT[k] ? "ew-resize" : "ns-resize") : "default"; } return; }
      const [px, py] = pos(e), st = sides[side];
      drag.px = px; drag.py = py;
      const lim = VERT[drag.k] ? st.work.width : st.work.height;
      st.g[drag.k] = Math.max(0, Math.min(lim, drag.start + ((VERT[drag.k] ? px : py) - drag.from) * drag.gain / view.s));
      clamp(drag.k);
      const now = performance.now();
      drag.hist.push([now, st.g[drag.k]]);
      while (drag.hist.length > 2 && now - drag.hist[0][0] > 400) drag.hist.shift();
      if (!raf) raf = requestAnimationFrame(() => { raf = 0; draw(); readout(); });
    });
    const end = () => {
      if (!drag) return;
      const st = sides[side], back = drag.touch ? 120 : 50, t = performance.now() - back;
      // use where the line was just before release, not the slip as the finger/mouse lets go
      let v = null;
      for (const [ht, hv] of drag.hist) if (ht <= t) v = hv;
      if (v != null && st) { st.g[drag.k] = v; clamp(drag.k); }
      drag = null; draw(); readout();
    };
    c.addEventListener("pointerup", end); c.addEventListener("pointercancel", end);
    c.addEventListener("keydown", (e) => {
      if (!sel || !sides[side]) return;
      const step = (e.shiftKey ? 5 : 0.5) / Math.max(view.s, 0.2);
      const dir = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 }[e.key];
      if (!dir) return;
      e.preventDefault(); sides[side].g[sel] += dir * step; clamp(sel); draw(); readout();
    });
  }
  function clamp(k) {   // a dragged line can't pass its neighbours
    const g = sides[side].g, order = VERT[k] ? ["oL", "iL", "iR", "oR"] : ["oT", "iT", "iB", "oB"], i = order.indexOf(k);
    if (i > 0) g[k] = Math.max(g[k], g[order[i - 1]] + 1);
    if (i < 3) g[k] = Math.min(g[k], g[order[i + 1]] - 1);
  }

  /* ---------- results ---------- */
  function sideCard(name) {
    const m = measure(sides[name]?.g);
    if (!m) return `<div class="cz-res-side"><b>${name === "front" ? "Front" : "Back"}</b><span class="muted">${name === "back" ? "Optional. Add a back photo for the full check." : "Add a photo"}</span></div>`;
    const lim = name === "front" ? 55 : 75, ok = m.worst <= lim;
    return `<div class="cz-res-side"><b>${name === "front" ? "Front" : "Back"}</b>
      <div class="cz-nums"><div><span class="l">Left / Right</span><span class="v">${pair(m.lr)}</span></div><div><span class="l">Top / Bottom</span><span class="v">${pair(m.tb)}</span></div></div>
      <span class="cz-worst ${ok ? "ok" : "off"}">Worst ${worstPair(m.worst)} · ${ok ? `inside the PSA 10 limit (${lim}/${100 - lim})` : `over the PSA 10 limit (${lim}/${100 - lim})`}</span></div>`;
  }
  function readout() {
    const f = measure(sides.front?.g), b = measure(sides.back?.g);
    const psa = f ? best(PSA, f.worst, b?.worst) : null, cgc = f ? best(CGC, f.worst, b?.worst) : null;
    const pristine = f && b ? f.worst <= 51 && b.worst <= 55 : null;
    const verdict = !f ? `<p class="muted">Add a front photo to see which grades its centering allows.</p>`
      : `<div class="cz-caps">
          <div class="cz-cap"><span class="l">PSA</span><span class="g">${psa == null ? "Below 2" : psa === 10 ? "10" : psa}</span><span class="s">${psa === 10 ? "Centering is fine for a 10" : "Best grade centering allows"}</span></div>
          <div class="cz-cap"><span class="l">CGC</span><span class="g">${cgc == null ? "Below 3.5" : cgc === 10 ? "10" : cgc}</span><span class="s">${cgc === 10 ? "Gem Mint 10 centering" : "Best grade centering allows"}</span></div>
          <div class="cz-cap"><span class="l">BGS Pristine</span><span class="g">${pristine == null ? "–" : pristine ? "Yes" : "No"}</span><span class="s">${pristine == null ? "Needs front and back" : "Needs ~50/50 front, 55/45 back"}</span></div>
        </div>${b ? "" : `<p class="muted cz-note">Front only. Add the back to include the back limit (PSA 10 needs 75/25 or better on the back).</p>`}`;
    root.querySelector("#cz-res").innerHTML = `${verdict}<div class="cz-res-sides">${sideCard("front")}${sideCard("back")}</div>
      ${f ? `<button class="btn" type="button" id="cz-copy">Copy result</button>` : ""}`;
    root.querySelector("#cz-copy")?.addEventListener("click", copy);
  }
  function copy() {
    const f = measure(sides.front?.g), b = measure(sides.back?.g);
    const t = `Centering check (market.driveyourstyle.net/centering.html)\nFront L/R ${pair(f.lr)} · T/B ${pair(f.tb)}` + (b ? `\nBack L/R ${pair(b.lr)} · T/B ${pair(b.tb)}` : "");
    const done = () => { const btn = root.querySelector("#cz-copy"); if (btn) btn.textContent = "Copied"; };
    (navigator.clipboard?.writeText(t) || Promise.reject()).then(done).catch(() => window.prompt && window.prompt("Copy:", t));
  }

  /* ---------- page ---------- */
  function paintSide() {
    root.querySelectorAll("#cz-side button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.s === side)));
    const st = sides[side];
    paintNudge();
    root.querySelector("#cz-empty").hidden = !!st;
    root.querySelector("#cz-edit").hidden = !st;
    root.querySelector("#cz-empty-h").textContent = side === "front" ? "Photo of the front" : "Photo of the back";
    if (st) { root.querySelector("#cz-rot").value = st.rot; root.querySelector("#cz-rotv").textContent = `${st.rot > 0 ? "+" : ""}${st.rot.toFixed(1)}°`; }
    sel = null; draw(); readout();
  }
  async function take(file) {
    if (!file) return;
    const msg = root.querySelector("#cz-msg"); msg.textContent = "Reading the photo…";
    try {
      const src = await load(file), work = rotated(src, 0);
      sides[side] = { src, rot: 0, work, g: detect(work) };
      msg.textContent = "";
      paintSide();
      root.querySelector("#cz-stage").scrollIntoView({ block: "nearest", behavior: "smooth" });
    } catch (err) { msg.textContent = err.message || "Couldn't read that photo."; }
  }

  window.dysCentering = (el) => {
    root = el;
    root.innerHTML = `
      <div class="tabs" id="cz-side" role="group" aria-label="Card side"><button type="button" data-s="front" aria-pressed="true">Front</button><button type="button" data-s="back" aria-pressed="false">Back</button></div>
      <div class="cz-grid">
        <div class="cz-stage panel" id="cz-stage">
          <div class="cz-empty" id="cz-empty">
            <svg class="cz-demo" viewBox="0 0 250 340" aria-hidden="true"><rect x="20" y="15" width="210" height="300" rx="10" fill="none" stroke="#5ee7ff" stroke-width="2"/><rect x="38" y="33" width="168" height="264" rx="4" fill="none" stroke="#ff7ad9" stroke-width="2" stroke-dasharray="6 4"/>
              <path d="M20 165h18M206 165h24M125 15v18M125 297v18" stroke="currentColor" stroke-width="2"/></svg>
            <div><h2 id="cz-empty-h">Photo of the front</h2>
              <p class="muted">Lay the card flat on a dark surface and shoot straight down, with the whole card in frame. Raw, sleeved or slabbed all work.</p>
              <div class="cz-btns"><label class="btn primary"><input type="file" accept="image/*" capture="environment" id="cz-cam" hidden>Take photo</label>
                <label class="btn"><input type="file" accept="image/*" id="cz-file" hidden>Upload photo</label></div>
              <p class="muted cz-note" id="cz-msg" role="status"></p></div>
          </div>
          <div id="cz-edit" hidden>
            <canvas id="cz-cv" tabindex="0" aria-label="Card photo with centering guides. Drag a line to adjust it; arrow keys move the selected line."></canvas>
            <div class="cz-tools">
              <label class="cz-rot">Straighten <input type="range" id="cz-rot" min="-5" max="5" step="0.1" value="0"><span id="cz-rotv">0.0°</span></label>
              <button class="btn" type="button" id="cz-auto">Re-detect</button>
              <label class="btn"><input type="file" accept="image/*" id="cz-new" hidden>New photo</label>
            </div>
            <div class="cz-nudge" id="cz-nudge" hidden><span class="cz-nl">Line</span><button class="btn" type="button" data-d="-1" aria-label="Move line back">◀</button><button class="btn" type="button" data-d="1" aria-label="Move line forward">▶</button><span class="muted">tap or hold to fine-tune</span></div>
            <p class="muted cz-note"><span class="cz-k o"></span> card edge <span class="cz-k i"></span> print border · Drag a line close, then use the arrows to fine-tune. A zoom appears while you drag.</p>
          </div>
        </div>
        <aside class="cz-out panel" aria-live="polite"><h2>Result</h2><div id="cz-res"></div></aside>
      </div>`;
    root.querySelectorAll("#cz-side button").forEach((b) => b.addEventListener("click", () => { side = b.dataset.s; paintSide(); }));
    ["#cz-cam", "#cz-file", "#cz-new"].forEach((id) => root.querySelector(id).addEventListener("change", (e) => { take(e.target.files[0]); e.target.value = ""; }));
    root.querySelector("#cz-rot").addEventListener("input", (e) => {
      const st = sides[side]; if (!st) return;
      st.rot = Number(e.target.value); st.work = rotated(st.src, st.rot);
      root.querySelector("#cz-rotv").textContent = `${st.rot > 0 ? "+" : ""}${st.rot.toFixed(1)}°`; draw(); readout();
    });
    root.querySelector("#cz-auto").addEventListener("click", () => { const st = sides[side]; if (st) { st.g = detect(st.work); draw(); readout(); } });
    root.querySelectorAll("#cz-nudge button").forEach((b) => {
      let tm, iv;
      const stop = () => { clearTimeout(tm); clearInterval(iv); };
      b.addEventListener("pointerdown", (e) => { e.preventDefault(); const d = Number(b.dataset.d); nudge(d); tm = setTimeout(() => { iv = setInterval(() => nudge(d), 60); }, 350); });
      ["pointerup", "pointerleave", "pointercancel"].forEach((ev) => b.addEventListener(ev, stop));
      b.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); nudge(Number(b.dataset.d)); } });
    });
    bind();
    let t; window.addEventListener("resize", () => { clearTimeout(t); t = setTimeout(draw, 120); });
    paintSide();
  };
  window.dysCenteringMath = { measure, best, PSA, CGC };
})();
