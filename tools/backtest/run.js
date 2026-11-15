// Backtest of Edge's strategy rules on our own price history.
// For each decision day (every STEP days) and each item priced $1+ that day, rebuild what Edge would have had on that day
// (a price for each of the last 120 days, and one a week before that back a year), run the live code on it
// (edge-ta.js analyse -> edge-strat.js facts, pick, ladder, risk) and record what the price did afterwards.
// usage: node tools/backtest/run.js <shard> <shards> <out dir> [step=7] [only this day index]
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "../.."), SITE = path.join(ROOT, "site"), BT = process.env.BT_DIR || path.join(ROOT, "bt-work");
const TA = require(SITE + "/assets/edge-ta.js"), ST = require(SITE + "/assets/edge-strat.js");
const [,, shardS = "0", shardsS = "1", out = BT + "/sig", stepS = "7", onlyS = ""] = process.argv;
const shard = +shardS, shards = +shardsS, STEP = +stepS;
const days = JSON.parse(fs.readFileSync(BT + "/days.json", "utf8")), keys = JSON.parse(fs.readFileSync(BT + "/keys.json", "utf8")), meta = JSON.parse(fs.readFileSync(BT + "/meta.json", "utf8"));
const nD = days.length, nK = keys.length;
const buf = fs.readFileSync(BT + "/prices.i32");
const P = new Int32Array(buf.buffer, buf.byteOffset, nK * nD);
const sunday = days.map((d) => new Date(d + "T00:00:00Z").getUTCDay() === 0);
const SETUPS = Object.keys(ST.SETUPS), CODE = Object.fromEntries(SETUPS.map((k, i) => [k, i]));
const GAMES = [...new Set(Object.values(meta).map((m) => m[3]))].sort();
const HORIZONS = [7, 14, 30, 60, 90], PATH = 60, FILL = 5;
fs.mkdirSync(out, { recursive: true });

// per key: product type, release day and game (cards unless the site data says sealed)
const kType = new Uint8Array(nK), kGame = new Uint8Array(nK).fill(255), kPub = new Array(nK).fill("");
keys.forEach((k, i) => { const m = meta[k.slice(0, k.indexOf(":"))]; if (m) { kType[i] = m[0] === "s" ? 1 : 0; kPub[i] = m[2]; kGame[i] = GAMES.indexOf(m[3]); } });

// decision days: every STEP days, counted back from the last day (so the newest day is one of them)
const decide = [];
if (onlyS !== "") decide.push(+onlyS);
else for (let d = nD - 1; d >= ST.K.MIN_HISTORY; d -= STEP) decide.unshift(d);

// growable columns
const cols = { key: [Int32Array], day: [Int16Array], setup: [Uint8Array], risk: [Uint8Array], v: [Int32Array], touch: [Uint8Array], sell1: [Float32Array], cut: [Float32Array], moves: [Uint8Array] };
for (const h of HORIZONS) cols["r" + h] = [Float32Array];
let cap = 1 << 20, n = 0;
for (const c of Object.values(cols)) c.push(new c[0](cap));
const grow = () => { cap *= 2; for (const c of Object.values(cols)) { const a = new c[0](cap); a.set(c[1]); c[1] = a; } };

const price = (base, j) => {            // the price on day j, or the last one in the FILL days before it, or 0
  for (let k = j; k >= 0 && k >= j - FILL; k--) { const v = P[base + k]; if (v > 0) return v; }
  return 0;
};
const t0 = Date.now();
let seen = 0;
for (const d of decide) {
  const from = Math.max(0, d - 119);
  const dDates = days.slice(from, d + 1);
  const wk = [];                         // the newest day of each week, 121 to 366 days back (what the set file keeps)
  for (let j = Math.max(0, d - 366); j <= d - 121; j++) if (sunday[j]) wk.push(j);
  const sDates = wk.map((j) => days[j]).concat(days[d]);
  for (let r = shard; r < nK; r += shards) {
    const base = r * nD, v = P[base + d];
    if (v < 100) continue;               // the site tracks items priced $1 and up on the day
    seen++;
    const dVals = new Array(d + 1 - from);
    for (let j = from; j <= d; j++) { const x = P[base + j]; dVals[j - from] = x > 0 ? x : null; }
    const sVals = wk.map((j) => { const x = P[base + j]; return x > 0 ? x : null; });
    sVals.push(v);
    const a = TA.analyse(sDates, sVals, { dates: dDates, values: dVals });
    const f = ST.facts(a), pk = ST.pick(f);
    if (n === cap) grow();
    cols.key[1][n] = r; cols.day[1][n] = d; cols.setup[1][n] = CODE[pk.id]; cols.v[1][n] = v; cols.moves[1][n] = f ? f.moves : 255;
    let touch = 255, s1 = NaN, cutPct = NaN, risk = 255;
    if (pk.mode !== "none") {
      const L = ST.ladder(f, {});
      risk = ST.risk(f, { pub: kPub[r] }).score;
      const sell = L.sells.length ? L.sells[0].price : 0, cut = L.cut;
      s1 = sell ? (sell / v - 1) * 100 : NaN; cutPct = (1 - cut / v) * 100;
      // which came first in the next PATH days: the first sell level or the cut level
      touch = d + PATH < nD ? 0 : 3;     // 0 neither, 1 sell level first, 2 cut first, 3 neither yet and the window is not over
      for (let j = d + 1; j <= d + PATH && j < nD; j++) {
        const x = P[base + j];
        if (!x) continue;
        if (x <= cut) { touch = 2; break; }
        if (sell && x >= sell) { touch = 1; break; }
      }
    }
    cols.touch[1][n] = touch; cols.sell1[1][n] = s1; cols.cut[1][n] = cutPct; cols.risk[1][n] = risk;
    for (const h of HORIZONS) { const j = d + h, x = j < nD ? price(base, j) : 0; cols["r" + h][1][n] = j < nD ? (x ? x / v - 1 : -2) : NaN; }   // -2: no price any more
    n++;
  }
  if (decide.indexOf(d) % 10 === 0) console.error(`shard ${shard}: ${days[d]} (${decide.indexOf(d) + 1}/${decide.length}), ${n} rows, ${((Date.now() - t0) / 1000).toFixed(0)}s`);
}
for (const [name, c] of Object.entries(cols)) fs.writeFileSync(path.join(out, `${name}.${shard}.bin`), Buffer.from(c[1].buffer, 0, n * c[0].BYTES_PER_ELEMENT));
fs.writeFileSync(path.join(out, `info.${shard}.json`), JSON.stringify({ n, shard, shards, step: STEP, setups: SETUPS, games: GAMES, horizons: HORIZONS, path: PATH, decide: decide.map((d) => days[d]), types: Object.fromEntries(Object.entries(cols).map(([k, c]) => [k, c[0].name])), K: ST.K, seconds: (Date.now() - t0) / 1000 }));
console.log(`shard ${shard}/${shards}: ${decide.length} decision days, ${seen} item-days, ${n} rows, ${((Date.now() - t0) / 1000).toFixed(0)}s`);
