// Random synthetic cases and the app's answers, for tools/deal/ref.py. Usage: node tools/deal/dump.js 20000 > /tmp/deal.json
const path = require("path");
const D = require(path.join(__dirname, "../../site/assets/edge-deal.js"));
const Y = require(path.join(__dirname, "synth.js"));
const n = +(process.argv[2] || 5000), cases = Y.randomCases(n, +(process.argv[3] || 7)), cfg = Y.cfg();
const results = cases.map((c) => {
  const r = D.check(c.item, c.data, c.offer, cfg, c.ctx);
  const F = r.routes.flip, G = r.routes.grade, H = r.routes.hold;
  return { verdict: r.verdict, route: r.route, confidence: r.confidence, scope: r.scope,
    flip: { exit: F.exit, profit: F.profit, max: F.max, pass: F.pass, gates: Object.fromEntries(F.gates.filter((g) => g.hard).map((g) => [g.code, g.ok])) },
    grade: G ? { expected: G.expected, profit: G.profit, pass: G.pass } : null,
    hold: H ? { m6: H.m6, m12: H.m12 } : null,
    own: D.own(c.item, c.data, { cost: c.offer.ask, cond: c.offer.cond }, cfg, c.ctx).label };
});
process.stdout.write(JSON.stringify({ today: Y.DAY0, cases, results }));
