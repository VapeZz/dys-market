// Random graded-check cases for the independent Python check (ref.py). node tools/graded/cases.js > /tmp/graded_cases.json
const path = require("path"), G = require(path.join(__dirname, "../../site/assets/edge-graded.js"));
let seed = 7; const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
const T = 20000, out = [];
for (let i = 0; i < 400; i++) {
  const base = Math.round(500 + rnd() * (rnd() < 0.1 ? 900000 : 30000)), n = Math.floor(rnd() * 40);
  const comps = Array.from({ length: n }, () => [T - Math.floor(rnd() * 100) + (rnd() < 0.03 ? 5 : 0), Math.max(1, Math.round(base * (0.6 + rnd() * 0.8))), "PSA 10", rnd() < 0.9 ? 1 : 0]);
  if (rnd() < 0.3) comps.push([T - 5, base, "PSA 9", 1], [T - 5, base, "raw", 1]);
  const capped = rnd() < 0.15, data = { asOf: T, label: "PSA 10", comps, capped: capped ? ["PSA 10"] : [], oldestRead: capped ? T - Math.floor(5 + rnd() * 40) : null };
  const sell = { feePct: [13.25, 12.35, 10][Math.floor(rnd() * 3)], topPct: 2.35, topFrom: 750000, perOrder: [40, 30, 0][Math.floor(rnd() * 3)], buyerTax: [7.5, 0, 8.375][Math.floor(rnd() * 3)],
    ship: rnd() < 0.5 ? null : Math.round(rnd() * 800), supplies: Math.round(rnd() * 200), breaks: [5000] };
  const cost = Math.round(base * (0.3 + rnd() * 1.2)), opts = { today: T, roi: [20, 10, 30][Math.floor(rnd() * 3)], minProfit: [500, 0, 1000][Math.floor(rnd() * 3)] };
  const r = G.evaluate(data, { cost, label: "PSA 10" }, { ...sell, shipAuto: (p) => p >= 5000 ? 500 : 100 }, opts);
  out.push({ data, sell, cost, opts, js: { verdict: r.verdict, reasons: r.reasons.map((x) => x.code), typical: r.typical, net: r.at ? r.at.net : null, profit: r.profit, breakEven: r.breakEven, target: r.target,
    s: r.s && { n14: r.s.n14, n30: r.s.n30, n90: r.s.n90, m14: r.s.m14, m30: r.s.m30, m90: r.s.m90, q1: r.s.q1, q3: r.s.q3, lo: r.s.lo, hi: r.s.hi, saleAge: r.s.saleAge, trend: r.s.trend && r.s.trend.word } } });
}
process.stdout.write(JSON.stringify(out));
