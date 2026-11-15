// A second, separately written scoring of the rules (plain loops), compared with what stats.py wrote.
const fs = require("fs"), path = require("path"), BT = process.env.BT_DIR || path.join(path.resolve(__dirname, "../.."), "bt-work"), sig = BT + "/sig";
const res = JSON.parse(fs.readFileSync(process.argv[2] || BT + "/edge-backtest.json", "utf8"));
const days = JSON.parse(fs.readFileSync(BT + "/days.json", "utf8"));
const infos = fs.readdirSync(sig).filter((f) => /^info\./.test(f)).sort().map((f) => JSON.parse(fs.readFileSync(sig + "/" + f, "utf8")));
const T = { Int32Array, Int16Array, Uint8Array, Float32Array };
const load = (name) => infos.map((i) => { const b = fs.readFileSync(`${sig}/${name}.${i.shard}.bin`); return new T[i.types[name]](b.buffer, b.byteOffset, b.length / T[i.types[name]].BYTES_PER_ELEMENT); });
const day = load("day"), setup = load("setup"), r30 = load("r30");
const setups = infos[0].setups, nD = days.length, CLAIM = res.claims, R = res.rule;
const monthOf = days.map((d) => +d.slice(0, 4) * 12 + +d.slice(5, 7) - 1);
const clip = (x) => Math.min(3, Math.max(-0.9, x));
// pass 1: each day's all-cards average
const bs = new Float64Array(nD), bn = new Float64Array(nD);
let first = Infinity, last = -Infinity;
for (let s = 0; s < day.length; s++) for (let i = 0; i < day[s].length; i++) {
  const d = day[s][i], r = r30[s][i];
  if (d < 365 || Number.isNaN(r) || r <= -1.5) continue;
  bs[d] += clip(r); bn[d]++; first = Math.min(first, monthOf[d]); last = Math.max(last, monthOf[d]);
}
const mid = Math.floor((first + last + 1) / 2);
// pass 2: each rule
const acc = setups.map(() => ({ n: 0, sum: 0, base: 0, up: 0, flat: 0, down: 0, m: new Map(), h: [0, 0, 0, 0] }));
for (let s = 0; s < day.length; s++) for (let i = 0; i < day[s].length; i++) {
  const d = day[s][i], r = r30[s][i];
  if (d < 365 || Number.isNaN(r) || r <= -1.5) continue;
  const a = acc[setup[s][i]], b = bs[d] / bn[d], ex = clip(r) - b, mo = monthOf[d];
  a.n++; a.sum += clip(r); a.base += b; if (r > 0) a.up++; else if (r < 0) a.down++; else a.flat++;
  const mm = a.m.get(mo) || [0, 0]; mm[0] += ex; mm[1]++; a.m.set(mo, mm);
  const k = mo < mid ? 0 : 1; a.h[k] += ex; a.h[k + 2]++;
}
let diffs = 0, checked = 0;
const near = (x, y, what) => { checked++; if (Math.abs(x - y) > 0.011) { diffs++; console.log("DIFF", what, x, y); } };
setups.forEach((id, c) => {
  const a = acc[c], want = res.rules[id];
  if (!a.n) { if (want) { diffs++; console.log("DIFF", id, "missing here"); } return; }
  const avg = a.sum / a.n * 100, base = a.base / a.n * 100, edge = avg - base, claim = CLAIM[id] || 0;
  near(a.n, want.n, id + " n"); near(avg, want.avg, id + " avg"); near(base, want.baseAvg, id + " base"); near(edge, want.edge, id + " edge");
  near(a.up / a.n * 100, want.up, id + " up"); near(a.flat / a.n * 100, want.flat, id + " flat"); near(a.down / a.n * 100, want.down, id + " down");
  const big = [...a.m.values()].filter((x) => x[1] >= 30), okM = claim && big.length ? big.filter((x) => x[0] / x[1] * claim > 0).length / big.length * 100 : null;
  if (okM != null) near(okM, want.okMonths, id + " months");
  let verdict = "none";
  if (claim) {
    const halves = a.h[2] >= 100 && a.h[3] >= 100 && a.h[0] / a.h[2] * claim > 0 && a.h[1] / a.h[3] * claim > 0;
    if (edge * claim <= 0 || (okM != null && okM < R.badMonths)) verdict = "fail";
    else if (a.n >= R.minN && a.m.size >= R.minMonths && edge * claim >= R.edge && avg * claim > 0 && okM != null && okM >= R.okMonths && halves) verdict = "pass";
    else verdict = "unproven";
  }
  checked++; if (verdict !== want.verdict) { diffs++; console.log("DIFF", id, "verdict", verdict, want.verdict); }
});
console.log(`second scoring: ${checked} numbers and verdicts compared, differences ${diffs}`);
