"use strict";
/* DYS Edge: the technical chart on a card's sheet (loaded by edge.js; owner only).

   Prices are TCGplayer market prices recorded nightly. A card's set file has them daily for 30 days and
   about weekly back a year; data/edge/daily/<set>.json (pipeline/edge_daily.py) adds every day of the
   last 120. The chart draws the price with 7, 30 and 90-day averages and Bollinger bands, an RSI panel
   and a MACD panel, and reads out the 52-week high and low and the distance from the high.

   How the numbers are made (the standard definitions, so they can be checked against any charting tool):
   - 7 / 30 / 90-day average: the plain average of that many days. A recorded price stands for the days
     since the one before it, so the older weekly points still count toward the 30 and 90-day averages
     (the same rule as the market site's chart, movingAvg in app.js).
   - RSI 14 (Wilder), MACD 12 26 9 and Bollinger bands 20 / 2 use daily prices only. A day with no
     recorded price counts as the last price, for up to MAX_FILL days in a row; a longer hole starts the
     indicator over. TCGplayer's market price itself stays put until the next sale, so this matches it.
   - RSI: average gain over average loss of the last 14 daily changes, smoothed Wilder's way. 70 and
     above is the overbought zone, 30 and below the oversold zone.
   - MACD: the 12-day EMA minus the 26-day EMA; signal: the 9-day EMA of that; histogram: MACD minus
     signal. Each EMA starts from the plain average of its first window.
   - Bollinger bands: the 20-day average plus and minus 2 standard deviations (population) of those 20 days.
   - Thin market: fewer than THIN_MOVES price moves in the last 14 days. The numbers are still shown, with a
     note that they rest on very little (about two cards in three, by the Nov 14, 2026 prices).
   - 52-week high and low: the highest and lowest recorded price of the last 365 days (weekly points
     before the last 120 days, so a spike between two weekly points can be missed).
   It describes what the price did. It is not advice. */
(() => {
  const DAY = 864e5, MAX_FILL = 5, VERSION = 1;
  const RSI_N = 14, FAST = 12, SLOW = 26, SIG = 9, BB_N = 20, BB_K = 2;
  const ON_LINE = 1e-6;      // cents: a MACD histogram closer to zero than this is rounding, not a side of the signal line
  const THIN_MOVES = 3;      // fewer price moves than this in the last 14 days: the card is flagged as a thin market
  const TREND_BAND = 2;      // percent the 7-day average must sit above or below the 30-day average to call a trend (as on the market site)
  const RANGES = [["30", "1M", "past month"], ["90", "3M", "past 3 months"], ["180", "6M", "past 6 months"], ["365", "1Y", "past year"]];
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const dayNum = (d) => Math.round(Date.parse(d + "T00:00:00Z") / DAY);
  const dayIso = (t) => new Date(t * DAY).toISOString().slice(0, 10);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (c) => {
    if (c == null || !isFinite(c)) return "—";
    const neg = c < 0, d = Math.abs(c) / 100;
    return (neg ? "−" : "") + "$" + (d >= 1000 ? Math.round(d).toLocaleString("en-US") : d.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  };
  // a small signed amount (MACD values): under a cent still shows which side of zero it is on
  const delta = (c) => c == null || !isFinite(c) ? "—" : c === 0 ? "$0.00" : (c < 0 ? "−" : "+") + (Math.abs(c) < 0.5 ? "<$0.01" : money(Math.abs(c)));
  const fmtShort = (d) => { const [, m, dd] = d.split("-"); return `${MONTHS[m - 1]} ${+dd}`; };
  const fmtDate = (d) => `${fmtShort(d)}, ${d.slice(0, 4)}`;
  const f1 = (n) => n.toFixed(1);

  /* ---------- data ---------- */
  // one item's packed prices from the daily file ("<first day> <price> <change | z | zN | n | nN> ...")
  function unpack(text, n) {
    const out = new Array(n).fill(null), tok = String(text || "").split(" ").filter(Boolean);
    if (tok.length < 2) return out;
    let i = +tok[0], prev = +tok[1];
    if (!Number.isInteger(i) || !Number.isFinite(prev) || i < 0) return out;
    if (i < n) out[i] = prev;
    i++;
    for (let k = 2; k < tok.length; k++) {
      const t = tok[k], c = t[0];
      if (c === "z" || c === "n") {
        const run = t.length > 1 ? +t.slice(1) : 1;
        if (!Number.isInteger(run) || run < 1) return new Array(n).fill(null);
        if (c === "z") for (let j = i; j < i + run && j < n; j++) out[j] = prev;
        i += run;
      } else {
        if (!Number.isFinite(+t)) return new Array(n).fill(null);
        prev += +t;
        if (i < n) out[i] = prev;
        i++;
      }
    }
    return out;
  }
  const fileDates = (f) => Array.isArray(f.dates) ? f.dates : Array.from({ length: f.days || 0 }, (_, i) => dayIso(dayNum(f.from) + i));
  // the daily prices of one item, or null when the file has none for it (then the set file's prices are all there is)
  function dailyOf(file, id, name) {
    if (!file || file.v !== VERSION || !file.s) return null;
    const row = file.s[`${id}|${name}`];
    if (!row) return null;
    const dates = fileDates(file);
    return { dates, values: unpack(row, dates.length) };
  }
  // every recorded price once, oldest first: the set file's points plus the daily file's
  function points(setDates, setVals, daily) {
    const by = new Map();
    (setDates || []).forEach((d, i) => { const v = setVals ? setVals[i] : null; if (v != null) by.set(d, v); });
    if (daily) daily.dates.forEach((d, i) => { const v = daily.values[i]; if (v != null) by.set(d, v); });
    return [...by].map(([d, v]) => ({ d, t: dayNum(d), v })).sort((a, b) => a.t - b.t);
  }

  /* ---------- the math ---------- */
  /* Time-weighted average of the last n days (the market site's movingAvg). A value is given only where the
     whole window is on record and no price in it stands for more than maxSpan days. */
  function movingAvg(pts, n, maxSpan) {
    return pts.map((p, i) => {
      let sum = 0, got = 0;
      for (let j = i; j >= 0 && got < n; j--) {
        const hi = pts[j].t, lo = j ? pts[j - 1].t : hi - 1;
        if (hi - lo > maxSpan) return null;
        const w = Math.min(hi - lo, n - got);
        sum += pts[j].v * w; got += w;
      }
      return got >= n ? sum / n : null;
    });
  }
  // stretches of daily prices: a day with no price takes the last one (up to MAX_FILL days); a longer hole ends the stretch
  function dailyRuns(pts) {
    const runs = [];
    let run = null;
    pts.forEach((p, i) => {
      const prev = pts[i - 1];
      if (!run || p.t - prev.t > MAX_FILL + 1) { run = []; runs.push(run); }
      else for (let t = prev.t + 1; t < p.t; t++) run.push({ t, v: prev.v, p: null });
      run.push({ t: p.t, v: p.v, p });
    });
    return runs;
  }
  function ema(src, n, from) {     // src has values from index `from` on; the first EMA value is the plain average of the first n
    const out = new Array(src.length).fill(null), k = 2 / (n + 1);
    if (src.length - from < n) return out;
    let e = 0;
    for (let i = from; i < from + n; i++) e += src[i];
    e /= n;
    out[from + n - 1] = e;
    for (let i = from + n; i < src.length; i++) { e += (src[i] - e) * k; out[i] = e; }   // the same as price * k + e * (1 - k); a flat price stays exactly flat
    return out;
  }
  function indicators(run) {
    const c = run.map((x) => x.v), n = c.length;
    let g = 0, l = 0;
    for (let i = 1; i < n; i++) {
      const ch = c[i] - c[i - 1], up = ch > 0 ? ch : 0, dn = ch < 0 ? -ch : 0;
      if (i <= RSI_N) { g += up; l += dn; if (i === RSI_N) { g /= RSI_N; l /= RSI_N; } }
      else { g = (g * (RSI_N - 1) + up) / RSI_N; l = (l * (RSI_N - 1) + dn) / RSI_N; }
      if (i >= RSI_N) run[i].rsi = l === 0 ? (g === 0 ? null : 100) : 100 - 100 / (1 + g / l);   // no change at all on record: no reading
    }
    const fast = ema(c, FAST, 0), slow = ema(c, SLOW, 0);
    const macd = c.map((_, i) => slow[i] == null ? null : fast[i] - slow[i]);
    const sig = ema(macd.map((v) => v ?? 0), SIG, SLOW - 1);
    for (let i = SLOW - 1; i < n; i++) {
      run[i].macd = macd[i];
      if (sig[i] != null) { run[i].sig = sig[i]; run[i].hist = macd[i] - sig[i]; }
    }
    for (let i = BB_N - 1; i < n; i++) {
      let m = 0, q = 0;
      for (let j = i - BB_N + 1; j <= i; j++) m += c[j];
      m /= BB_N;                                                   // whole cents add up exactly, so 20 equal prices give a width of exactly 0
      for (let j = i - BB_N + 1; j <= i; j++) q += (c[j] - m) ** 2;
      const sd = Math.sqrt(q / BB_N);
      run[i].bm = m; run[i].bu = m + BB_K * sd; run[i].bl = m - BB_K * sd;
    }
    for (const x of run) if (x.p) for (const k of ["rsi", "macd", "sig", "hist", "bm", "bu", "bl"]) x.p[k] = x[k] ?? null;
  }
  /* Everything the chart and the tiles show, from the two price lists. `now` describes the newest price and is
     set only when that price is at most 3 days old. */
  function analyse(setDates, setVals, daily) {
    const pts = points(setDates, setVals, daily);
    const today = setDates && setDates.length ? dayNum(setDates[setDates.length - 1]) : pts.length ? pts[pts.length - 1].t : 0;
    const a7 = movingAvg(pts, 7, 2), a30 = movingAvg(pts, 30, 10), a90 = movingAvg(pts, 90, 10);
    pts.forEach((p, i) => { p.a7 = a7[i]; p.a30 = a30[i]; p.a90 = a90[i]; });
    const runs = dailyRuns(pts);
    runs.forEach(indicators);
    const last = pts[pts.length - 1], fresh = !!last && today - last.t <= 3;
    let now = null;
    if (fresh && pts.length >= 2) {
      const run = runs[runs.length - 1], n = run.length;
      // how many of the last 14 daily steps changed the price: a thin market makes every daily indicator a weak reading
      let moves = 0;
      for (let i = Math.max(1, n - RSI_N); i < n; i++) if (run[i].v !== run[i - 1].v) moves++;
      // MACD against its signal line, and how long ago it last crossed
      let side = null, cross = null;
      if (last.hist != null) {
        const sideOf = (h) => h > ON_LINE ? 1 : h < -ON_LINE ? -1 : 0;
        side = ["below", "on", "above"][sideOf(last.hist) + 1];
        let k = n - 1;
        while (k > 0 && run[k - 1].hist != null && sideOf(run[k - 1].hist) === sideOf(last.hist)) k--;
        if (side !== "on" && k > 0 && run[k - 1].hist != null) cross = { days: last.t - run[k].t, d: dayIso(run[k].t) };
      }
      // the last 365 days' high and low (the most recent day each was reached)
      const yr = pts.filter((p) => p.t >= today - 365);
      let hi = null, lo = null;
      for (const p of yr) { if (!hi || p.v >= hi.v) hi = p; if (!lo || p.v <= lo.v) lo = p; }
      const gap = last.a7 != null && last.a30 ? (last.a7 / last.a30 - 1) * 100 : null;
      const width = last.bu != null ? last.bu - last.bl : null;
      now = {
        last, moves, dailyDays: n,
        trend: gap == null ? null : gap > TREND_BAND ? "up" : gap < -TREND_BAND ? "down" : "flat", gap,
        rsi: last.rsi, zone: last.rsi == null ? null : last.rsi >= 70 ? "over" : last.rsi <= 30 ? "under" : "mid",
        macd: last.macd, sig: last.sig, hist: last.hist, side, cross,
        bu: last.bu, bl: last.bl, bm: last.bm, pctB: width ? (last.v - last.bl) / width : null, bandPct: width != null && last.bm ? width / last.bm * 100 : null,
        hi, lo, since: yr.length && yr[0].t > today - 358 ? yr[0].d : null,
        off: hi ? (1 - last.v / hi.v) * 100 : null, up: lo && lo.v ? (last.v / lo.v - 1) * 100 : null,
      };
    }
    return { pts, today, now, daily: !!daily };
  }

  /* round axis steps (1, 2, 2.5 or 5 times a power of ten, in whole cents): the widest step that still leaves `min` marks */
  function niceTicks(lo, hi, min) {
    const marks = (step) => { const t = []; for (let v = Math.ceil(lo / step - 1e-9) * step; v <= hi + step * 1e-6; v += step) t.push(v); return t; };
    for (let k = Math.ceil(Math.log10(Math.max(hi - lo, 1))); k >= 0; k--)
      for (const m of [5, 2.5, 2, 1]) {
        const step = m * 10 ** k, t = Number.isInteger(step) ? marks(step) : [];
        if (t.length >= min) return { step, ticks: t };
      }
    return { step: 1, ticks: marks(1) };
  }

  /* ---------- the tiles under the chart ---------- */
  function tiles(a) {
    const n = a.now;
    if (!n) return "";
    const tile = (lab, b, s, cls = "") => `<div class="tile"><span class="lab">${lab}</span><b${cls ? ` class="${cls}"` : ""}>${b}</b><small>${s}</small></div>`;
    // fewer than 3 price moves in 14 days: RSI, MACD and the bands rest on almost nothing, so say so above them
    const thin = n.moves < THIN_MOVES && n.dailyDays > RSI_N;
    const thinNote = thin ? `<p class="ta-thin"><b>Thin market.</b> ${n.moves === 0 ? "No price moves" : n.moves === 1 ? "1 price move" : "2 price moves"} in the last 14 days, so RSI, MACD and the bands rest on very little. Read them loosely.</p>` : "";
    const need = (days) => a.daily ? `Needs ${days} daily prices` : "Needs the daily prices";
    const t = [];
    t.push(n.trend == null ? tile("Trend", "—", "Needs 30 days of prices")
      : n.trend === "flat" ? tile("Trend", "━ Flat", `7D avg within ${TREND_BAND}% of the 30D avg`)
      : tile("Trend", n.trend === "up" ? "▲ Uptrend" : "▼ Downtrend", `7D avg ${Math.abs(n.gap).toFixed(1)}% ${n.trend === "up" ? "above" : "below"} the 30D avg`, n.trend === "up" ? "up" : "down"));
    t.push(n.rsi == null ? tile("RSI 14", "—", n.dailyDays > RSI_N ? "No price moves on record" : need(RSI_N + 1))
      : tile("RSI 14", n.rsi.toFixed(1), n.zone === "over" ? "Overbought zone (70 and up)" : n.zone === "under" ? "Oversold zone (30 and under)" : "Neutral (between 30 and 70)", n.zone === "mid" || thin ? "" : "warn"));
    t.push(n.hist == null ? tile("MACD", "—", need(SLOW + SIG - 1))
      : n.side === "on" ? tile("MACD", "On signal", "No momentum either way")
      : tile("MACD", n.side === "above" ? "Above signal" : "Below signal",
        // which side of its signal line, and of zero: building, recovering, fading or falling momentum
        `Momentum ${n.side === "above" ? (n.macd >= 0 ? "building" : "recovering, still under zero") : (n.macd > 0 ? "fading, still above zero" : "falling")}. ${n.cross ? `Crossed ${n.cross.days === 0 ? "today" : n.cross.days === 1 ? "yesterday" : `${n.cross.days} days ago`}.` : "No cross on record."}`, n.side === "above" ? "up" : "down"));
    const b = n.pctB;
    t.push(n.bu == null ? tile("Bollinger bands", "—", need(BB_N))
      : b == null ? tile("Bollinger bands", "No width", `Price flat for ${BB_N} days at ${money(n.bm)}`)
      : tile("Bollinger bands", b > 1 ? "Above upper" : b < 0 ? "Below lower" : b >= 0.8 ? "Near upper" : b <= 0.2 ? "Near lower" : "Mid-band",
        `${money(Math.round(n.bl))} to ${money(Math.round(n.bu))} (${n.bandPct.toFixed(n.bandPct < 10 ? 1 : 0)}% wide)`, b > 1 || b < 0 ? "warn" : ""));
    if (n.hi) {
      const lab = n.since ? "High" : "52-week high", lab2 = n.since ? "Low" : "52-week low", tail = n.since ? ` · since ${fmtShort(n.since)}` : "";
      t.push(tile(lab, money(n.hi.v), fmtDate(n.hi.d) + tail));
      t.push(tile(lab2, money(n.lo.v), fmtDate(n.lo.d) + tail));
      t.push(n.off < 0.05 ? tile("From the high", "At the high", n.up < 0.05 ? "No range on record" : `${n.up.toFixed(1)}% above the low`, "up")
        : tile("From the high", `${n.off.toFixed(1)}% below`, `${money(n.hi.v - n.last.v)} under · ${n.up < 0.05 ? "at the low" : `${n.up.toFixed(1)}% above the low`}`, n.up < 0.05 ? "down" : ""));
    }
    const avgs = [["7D", n.last.a7], ["30D", n.last.a30], ["90D", n.last.a90]].filter((x) => x[1] != null);
    if (avgs.length) {
      const over = avgs.filter((x) => n.last.v > x[1]).length;
      t.push(tile("Vs averages", `Above ${over} of ${avgs.length}`, avgs.map((x) => `${x[0]} ${money(Math.round(x[1]))}`).join(" · "), over === avgs.length ? "up" : over === 0 ? "down" : ""));
    }
    return `${thinNote}<div class="ta-tiles">${t.join("")}</div>`;
  }

  /* ---------- the chart ---------- */
  const KEYS = [["a7", "7D", "7-day average"], ["a30", "30D", "30-day average"], ["a90", "90D", "90-day average"], ["bb", "Bands", "Bollinger bands (20 days, 2 standard deviations)"],
    ["rsi", "RSI", "RSI panel (14 days)"], ["macd", "MACD", "MACD panel (12, 26, 9)"]];
  const DEF = { range: "90", a7: false, a30: true, a90: false, bb: true, rsi: true, macd: true };
  const loadPrefs = () => { try { return { ...DEF, ...JSON.parse(localStorage.getItem("edge-ta") || "{}") }; } catch (e) { return { ...DEF }; } };
  let abort = null;        // one chart at a time: drop the old one's listeners when a card is opened again

  function mount(root, { dates, values, daily }) {
    abort?.abort();
    const ac = abort = new AbortController(), sig = { signal: ac.signal };
    const a = analyse(dates, values, daily), all = a.pts, today = a.today, last = all[all.length - 1];
    if (all.length < 2) {
      root.innerHTML = `<div class="ta-head"><span class="lab">Price chart</span></div><p class="muted small">Not enough price history yet. It builds every night.</p>`;
      return a;
    }
    const st = loadPrefs();
    if (!RANGES.some((r) => r[0] === st.range)) st.range = DEF.range;
    const save = () => { try { localStorage.setItem("edge-ta", JSON.stringify(st)); } catch (e) {} };
    root.innerHTML = `<div class="ta-head"><span class="lab">Price chart</span><div class="ta-range" role="group" aria-label="Time range">${
        RANGES.map((r) => `<button type="button" data-r="${r[0]}" aria-pressed="${r[0] === st.range}">${r[1]}</button>`).join("")}</div></div>
      <div class="ta-read"><b class="ta-px"></b><span class="ta-date"></span><span class="ta-move"></span></div>
      <div class="ta-keys" role="group" aria-label="Lines and panels">${KEYS.map(([k, l, title]) =>
        `<button type="button" class="ta-key" data-k="${k}" aria-pressed="${!!st[k]}" title="Show or hide the ${title}"><i class="k-${k}"></i>${l}<b></b></button>`).join("")}</div>
      <div class="ta-plot" tabindex="0" aria-label="Price chart. Use the left and right arrow keys to read each day."></div>
      ${tiles(a)}
      <p class="muted small ta-note">Price: TCGplayer market, recorded nightly. ${a.daily ? "Daily for the last 120 days, about weekly before that." : "Daily for the last 30 days, about weekly before that: the daily file for this set didn't load, so MACD is off."} RSI, MACD and the bands use the daily prices only; a day with no price counts as the last price. Market data, not financial advice.</p>`;
    const $ = (s, el = root) => el.querySelector(s);
    const el = $(".ta-plot"), pxEl = $(".ta-px"), dateEl = $(".ta-date"), moveEl = $(".ta-move");
    const keyVal = Object.fromEntries(KEYS.map(([k]) => [k, $(`.ta-key[data-k="${k}"] b`)]));
    const avg = (v) => v == null ? "—" : money(Math.round(v));
    let pts = [], cur = -1, pick = () => {}, clear = () => {};
    const read = (p, latest) => {
      pxEl.textContent = p ? money(p.v) : "—";
      dateEl.textContent = p ? fmtDate(p.d) + (latest ? " · latest" : "") : "";
      for (const k of ["a7", "a30", "a90"]) keyVal[k].textContent = st[k] && p ? avg(p[k]) : "";
      keyVal.bb.textContent = st.bb && p ? (p.bu == null ? "—" : `${avg(p.bl)}–${avg(p.bu).slice(1)}`) : "";
    };

    const plot = () => {
      const rg = RANGES.find((r) => r[0] === st.range);
      pts = all.filter((p) => p.t >= today - Number(st.range));
      cur = -1;
      if (pts.length < 2) {
        el.innerHTML = `<p class="muted small">No prices in this range yet. Try a longer one.</p>`;
        read(last, true); moveEl.innerHTML = ""; pick = clear = () => {};
        return;
      }
      const first = pts[0], end = pts[pts.length - 1];
      const pct = first.v ? (end.v - first.v) / first.v * 100 : null;
      const span = first.t > today - Number(st.range) + 10 ? `since ${fmtShort(first.d)}` : rg[2];
      moveEl.className = "ta-move " + (pct > 0 ? "up" : pct < 0 ? "down" : "");
      moveEl.textContent = pct == null ? "" : `${pct > 0 ? "+" : pct < 0 ? "−" : ""}${Math.abs(pct).toFixed(1)}% ${span}`;

      // layout: the price panel, then the RSI and MACD panels when they are on, then the time axis
      const W = el.clientWidth || 340, L = 2, T = 8, HM = W < 360 ? 168 : 190, GAP = 20, HR = 58, HD = 66, B = 22;
      const rsiOn = st.rsi, macdOn = st.macd;
      const yR = T + HM + GAP, yD = yR + (rsiOn ? HR + GAP : 0), H = (macdOn ? yD + HD : rsiOn ? yR + HR : T + HM) + B, base = H - B;
      const lines = ["v", ...["a7", "a30", "a90"].filter((k) => st[k]), ...(st.bb ? ["bu", "bl"] : [])];
      let yLo = Infinity, yHi = -Infinity;
      for (const p of pts) for (const k of lines) if (p[k] != null) { yLo = Math.min(yLo, p[k]); yHi = Math.max(yHi, p[k]); }
      const pad = (yHi - yLo) * 0.1 || yHi * 0.05 || 100;
      yLo = Math.max(0, yLo - pad); yHi += pad;
      const { step, ticks } = niceTicks(yLo, yHi, 3);
      const tl = (c) => "$" + (step % 100 ? (c / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : Math.round(c / 100).toLocaleString("en-US"));
      const R = Math.ceil(Math.max(...ticks.map((v) => tl(v).length), money(Math.round(yHi)).length, 5) * 6.3) + 14;
      const PW = W - L - R, t0 = first.t, t1 = end.t;
      const x = (t) => L + (t - t0) / (t1 - t0 || 1) * PW;
      const y = (v) => T + (1 - (v - yLo) / (yHi - yLo)) * HM;
      const yRsi = (v) => yR + 3 + (1 - v / 100) * (HR - 6);
      let mMax = 0;
      for (const p of pts) for (const k of ["macd", "sig", "hist"]) if (p[k] != null) mMax = Math.max(mMax, Math.abs(p[k]));
      mMax = mMax || 1;
      const yMacd = (v) => yD + HD / 2 - v / mMax * (HD / 2 - 3);

      // time axis: day marks on a month view, month starts on longer views (the year shows on the first mark and each January)
      let xt = [];
      if (t1 - t0 <= 45) for (let t = t1, sd = t1 - t0 > 21 ? 7 : t1 - t0 > 9 ? 3 : t1 - t0 > 4 ? 2 : 1; t >= t0; t -= sd) xt.unshift({ t, l: fmtShort(dayIso(t)) });
      else {
        const d0 = new Date(t0 * DAY);
        for (let m = new Date(Date.UTC(d0.getUTCFullYear(), d0.getUTCMonth() + 1, 1)); m.getTime() / DAY <= t1; m = new Date(Date.UTC(m.getUTCFullYear(), m.getUTCMonth() + 1, 1)))
          xt.push({ t: m.getTime() / DAY, m: m.getUTCMonth(), yr: m.getUTCFullYear() });
      }
      const every = Math.ceil(xt.length / Math.max(2, Math.floor(PW / 58)));
      xt = xt.filter((_, i) => (xt.length - 1 - i) % every === 0);
      xt.forEach((k, i) => { if (k.l == null) k.l = MONTHS[k.m] + (i === 0 || k.m === 0 ? " ’" + String(k.yr).slice(2) : ""); });

      const path = (key, yy) => { let d = "", pen = false; for (const p of pts) { if (p[key] == null) { pen = false; continue; } d += `${pen ? "L" : "M"}${f1(x(p.t))},${f1(yy(p[key]))}`; pen = true; } return d; };
      // the band between the upper and lower Bollinger lines, one closed shape per unbroken stretch
      const band = () => {
        let d = "", seg = [];
        const close = () => { if (seg.length > 1) d += "M" + seg.map((p) => `${f1(x(p.t))},${f1(y(p.bu))}`).join("L") + "L" + seg.slice().reverse().map((p) => `${f1(x(p.t))},${f1(y(p.bl))}`).join("L") + "Z"; seg = []; };
        for (const p of pts) { if (p.bu == null) close(); else seg.push(p); }
        close();
        return d;
      };
      const endY = y(end.v), tagH = 17;
      const grid = ticks.map((v) => `<line x1="${L}" x2="${L + PW}" y1="${f1(y(v))}" y2="${f1(y(v))}" class="ta-grid"/>${Math.abs(y(v) - endY) < tagH - 3 ? "" : `<text x="${L + PW + 6}" y="${f1(y(v) + 3.5)}" class="ta-ay" data-y="${f1(y(v))}">${tl(v)}</text>`}`).join("");
      const xgrid = xt.map((k) => `<line x1="${f1(x(k.t))}" x2="${f1(x(k.t))}" y1="${T}" y2="${base}" class="ta-grid ta-gx"/><text x="${f1(x(k.t))}" y="${H - 6}" text-anchor="${x(k.t) < 22 ? "start" : "middle"}" class="ta-at" data-x="${f1(x(k.t))}">${esc(k.l)}</text>`).join("");
      // the 52-week high and low, drawn on the year view (where they are the top and bottom of what is shown)
      const n = a.now;
      const lvl = st.range === "365" && n && n.hi && n.hi.v !== n.lo.v ? [[n.hi, "High"], [n.lo, "Low"]].map(([p, l]) =>
        `<line x1="${L}" x2="${L + PW}" y1="${f1(y(p.v))}" y2="${f1(y(p.v))}" class="ta-lvl"/><text x="${L + 4}" y="${f1(y(p.v) - 4)}" class="ta-lv">${l} ${money(p.v)}</text>`).join("") : "";
      const tag = (cls, yy, txt) => `<g class="${cls}" transform="translate(${L + PW + 2},${f1(Math.min(T + HM - tagH / 2, Math.max(T + tagH / 2, yy)))})"><rect y="${-tagH / 2}" width="${R - 3}" height="${tagH}" rx="4"/><text x="4" y="3.5">${txt}</text></g>`;
      const price = path("v", y);
      // RSI panel: the 30 to 70 zone is tinted, the line is drawn over it
      const rsiPanel = !rsiOn ? "" : `<g class="ta-panel"><line x1="${L}" x2="${L + PW}" y1="${yR}" y2="${yR}" class="ta-frame"/>
          <rect x="${L}" y="${f1(yRsi(70))}" width="${PW}" height="${f1(yRsi(30) - yRsi(70))}" class="ta-zone"/>
          ${[70, 30].map((v) => `<line x1="${L}" x2="${L + PW}" y1="${f1(yRsi(v))}" y2="${f1(yRsi(v))}" class="ta-guide"/><text x="${L + PW + 6}" y="${f1(yRsi(v) + 3.5)}" class="ta-ay">${v}</text>`).join("")}
          <path d="${path("rsi", yRsi)}" class="ta-rsi"/>
          <text x="${L + 2}" y="${yR - 6}" class="ta-pl">RSI 14 <tspan class="ta-pv" data-p="rsi"></tspan></text></g>`;
      // MACD panel: histogram bars from the zero line, the MACD line and its signal line
      const bw = Math.max(1, Math.min(6, PW / Math.max(1, t1 - t0) - 1));
      const macdPanel = !macdOn ? "" : `<g class="ta-panel"><line x1="${L}" x2="${L + PW}" y1="${yD}" y2="${yD}" class="ta-frame"/>
          <line x1="${L}" x2="${L + PW}" y1="${f1(yMacd(0))}" y2="${f1(yMacd(0))}" class="ta-guide"/><text x="${L + PW + 6}" y="${f1(yMacd(0) + 3.5)}" class="ta-ay">0</text>
          ${pts.filter((p) => p.hist != null).map((p) => { const y0 = yMacd(0), y1 = yMacd(p.hist); return `<rect x="${f1(x(p.t) - bw / 2)}" y="${f1(Math.min(y0, y1))}" width="${f1(bw)}" height="${f1(Math.max(0.5, Math.abs(y1 - y0)))}" class="ta-bar ${p.hist >= 0 ? "pos" : "neg"}"/>`; }).join("")}
          <path d="${path("macd", yMacd)}" class="ta-macd"/><path d="${path("sig", yMacd)}" class="ta-sig"/>
          <text x="${L + 2}" y="${yD - 6}" class="ta-pl">MACD <tspan class="ta-pv" data-p="macd"></tspan></text></g>`;
      el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="${esc(`Price chart: ${money(end.v)} on ${fmtDate(end.d)}${pct == null ? "" : `, ${pct >= 0 ? "up" : "down"} ${Math.abs(pct).toFixed(1)}% ${span.startsWith("since") ? span : `over the ${span}`}`}`)}">
        <defs><linearGradient id="etafill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="var(--ta-price)" stop-opacity=".22"/><stop offset="1" stop-color="var(--ta-price)" stop-opacity="0"/></linearGradient></defs>
        ${xgrid}${grid}
        ${st.bb ? `<path d="${band()}" class="ta-band"/><path d="${path("bu", y)}" class="ta-bb"/><path d="${path("bl", y)}" class="ta-bb"/>` : ""}${lvl}
        <path d="${price}L${f1(x(t1))},${T + HM}L${f1(x(t0))},${T + HM}Z" fill="url(#etafill)"/>
        ${st.a90 ? `<path d="${path("a90", y)}" class="ta-ma ta-a90"/>` : ""}${st.a30 ? `<path d="${path("a30", y)}" class="ta-ma ta-a30"/>` : ""}${st.a7 ? `<path d="${path("a7", y)}" class="ta-ma ta-a7"/>` : ""}
        <path d="${price}" class="ta-price"/>
        <circle cx="${f1(x(t1))}" cy="${f1(endY)}" r="3.5" class="ta-end"/>${tag("ta-tag", endY, money(end.v))}
        ${rsiPanel}${macdPanel}
        <g class="ta-x" visibility="hidden"><line class="ta-xv" y1="${T}" y2="${base}"/><line class="ta-xh" x1="${L}" x2="${L + PW}"/>
          <circle r="4" class="ta-dv"/><circle r="3" class="ta-dr"/><circle r="3" class="ta-dm"/>
          ${tag("ta-tag ta-tagx", 0, "")}<g class="ta-dt"><rect y="${base + 2}" height="${tagH}" rx="4"/><text y="${base + 14}" text-anchor="middle"></text></g></g>
        <rect x="${L}" y="${T}" width="${PW}" height="${base - T}" fill="transparent" class="ta-hit"/></svg>`;
      const svg = $("svg", el), g = $(".ta-x", el), xv = $(".ta-xv", el), xh = $(".ta-xh", el), tagx = $(".ta-tagx", el), dt = $(".ta-dt", el);
      const ay = [...el.querySelectorAll(".ta-ay[data-y]")], atx = [...el.querySelectorAll(".ta-at")];
      const pv = { rsi: $('[data-p="rsi"]', el), macd: $('[data-p="macd"]', el) };
      const panels = (p) => {
        if (pv.rsi) pv.rsi.textContent = p.rsi == null ? "—" : p.rsi.toFixed(1);
        if (pv.macd) pv.macd.textContent = p.macd == null ? "—" : `${delta(p.macd)} · signal ${delta(p.sig)} · hist ${delta(p.hist)}`;
      };
      const dot = (c, v, yy) => { const d = $(c, el); d.setAttribute("visibility", v != null ? "inherit" : "hidden"); if (v != null) { d.setAttribute("cx", f1(x(pts[cur].t))); d.setAttribute("cy", f1(yy(v))); } };
      pick = (i) => {
        cur = Math.max(0, Math.min(pts.length - 1, i));
        const p = pts[cur], cx = x(p.t), cy = y(p.v);
        xv.setAttribute("x1", f1(cx)); xv.setAttribute("x2", f1(cx)); xh.setAttribute("y1", f1(cy)); xh.setAttribute("y2", f1(cy));
        dot(".ta-dv", p.v, y); dot(".ta-dr", rsiOn ? p.rsi : null, yRsi); dot(".ta-dm", macdOn ? p.macd : null, yMacd);
        tagx.setAttribute("transform", `translate(${L + PW + 2},${f1(Math.min(T + HM - tagH / 2, Math.max(T + tagH / 2, cy)))})`);
        $("text", tagx).textContent = money(p.v);
        for (const t of ay) t.setAttribute("visibility", Math.abs(t.dataset.y - cy) < tagH - 3 ? "hidden" : "visible");
        const label = fmtDate(p.d), w = label.length * 6 + 12, mid = Math.min(W - w / 2, Math.max(w / 2, cx));
        $("text", dt).textContent = label; $("text", dt).setAttribute("x", f1(mid));
        $("rect", dt).setAttribute("x", f1(mid - w / 2)); $("rect", dt).setAttribute("width", f1(w));
        for (const t of atx) t.setAttribute("visibility", Math.abs(t.dataset.x - mid) < w / 2 + 24 ? "hidden" : "visible");
        g.setAttribute("visibility", "visible");
        read(p, false); panels(p);
      };
      clear = () => { cur = -1; g.setAttribute("visibility", "hidden"); for (const t of [...ay, ...atx]) t.setAttribute("visibility", "visible"); read(end, end === last); panels(end); };
      const at = (ev) => {
        const r = svg.getBoundingClientRect(), px = (ev.clientX - r.left) * (W / r.width);
        let b = 0;
        for (let i = 1; i < pts.length; i++) if (Math.abs(x(pts[i].t) - px) < Math.abs(x(pts[b].t) - px)) b = i;
        return b;
      };
      const hit = $(".ta-hit", el);
      hit.addEventListener("pointerdown", (ev) => pick(at(ev)));
      hit.addEventListener("pointermove", (ev) => pick(at(ev)));
      hit.addEventListener("pointerleave", (ev) => { if (ev.pointerType === "mouse") clear(); });   // a touch keeps its reading until a tap elsewhere
      clear();
    };

    $(".ta-range").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-r]"); if (!b) return;
      st.range = b.dataset.r; save();
      for (const x of root.querySelectorAll(".ta-range button")) x.setAttribute("aria-pressed", x === b);
      plot();
    });
    $(".ta-keys").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-k]"); if (!b) return;
      const k = b.dataset.k; st[k] = !st[k]; save(); b.setAttribute("aria-pressed", st[k]);
      const keep = cur; plot(); if (keep >= 0) pick(keep);
    });
    el.addEventListener("keydown", (e) => {
      if (pts.length < 2) return;
      const k = e.key, stp = k === "ArrowLeft" ? -1 : k === "ArrowRight" ? 1 : 0;
      if (stp) pick(cur < 0 ? pts.length - 1 : cur + stp);
      else if (k === "Home") pick(0);
      else if (k === "End") pick(pts.length - 1);
      else if (k === "Escape" && cur >= 0) { clear(); e.stopPropagation(); }
      else return;
      e.preventDefault();
    });
    el.addEventListener("blur", () => clear());
    document.addEventListener("pointerdown", (e) => { if (!el.contains(e.target) && !e.target.closest?.(".ta-keys")) clear(); }, sig);
    if (window.ResizeObserver) {   // redraw when the sheet changes width (rotation, window resize)
      let w = el.clientWidth;
      const ro = new ResizeObserver(() => { if (!el.isConnected) { ro.disconnect(); return; } if (el.clientWidth !== w) { w = el.clientWidth; const keep = cur; plot(); if (keep >= 0) pick(keep); } });
      ro.observe(el); ac.signal.addEventListener("abort", () => ro.disconnect());
    }
    plot();
    return a;
  }

  const api = { v: VERSION, mount, analyse, dailyOf, unpack, fileDates, points, movingAvg, dailyRuns, MAX_FILL };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window !== "undefined") window.EdgeTA = api;
})();
