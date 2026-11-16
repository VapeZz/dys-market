// Checks for Edge's Deal Check (site/assets/edge-deal.js), on synthetic data only. No dependencies: node tests/edge_deal.test.js
const path = require("path"), assert = require("assert");
const D = require(path.join(__dirname, "../site/assets/edge-deal.js"));
const Y = require(path.join(__dirname, "../tools/deal/synth.js"));
const K = D.K, T = Y.DAY0;
let n = 0;
const test = (name, fn) => { try { fn(); n++; } catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; } };

/* a hand-made liquid card: 10 raw sales at $100 spread over 90 days (5 in the last 30), read today, TCGplayer agrees */
const flat = (grade, px, ages) => ages.map((a) => [T - a, px, grade, 1]);
const AGES = [9, 12, 15, 20, 25, 40, 50, 60, 70, 80];
const card = (o = {}) => ({ item: { name: "Test card", t: "c", tcg: 10000, tcgDay: T, ...o.item },
  data: { asOf: T, source: "test", comps: flat("raw", 10000, AGES), ...o.data }, offer: { ask: 5000, cond: "NM", shipIn: 150, taxIn: 0, ...o.offer } });
const run = (c, cfg = {}, ctx = {}) => D.check(c.item, c.data, c.offer, Y.cfg(cfg), ctx);
const gate = (r, code, route = "flip") => r.routes[route].gates.find((g) => g.code === code);

test("fee is charged on the price plus the buyer's tax, then the flat fee", () => {
  const fees = { flat: 40, parts: [[13.25, 0, null, null]] };
  assert.strictEqual(D.fee(fees, 10000, 7.5), 1464);            // 10,750 × 13.25% = 1,424.4 + 40
  assert.strictEqual(D.fee(fees, 10000, 0), 1365);
  assert.strictEqual(D.fee({ flat: 0, parts: [[10, 0, 5000, null], [5, 5000, null, 100]] }, 10000, 0), 600);   // tiered with a cap
  assert.strictEqual(D.fee(fees, 0, 7.5), 0);
});
test("net sale and all-in cost", () => {
  const cfg = Y.cfg();
  assert.strictEqual(D.netSale(10000, "c", cfg), 10000 - 1464 - 500 - 50);
  assert.strictEqual(D.netSale(4000, "c", cfg), 4000 - Math.round(4300 * 0.1325 + 40) - 100 - 50);
  assert.strictEqual(D.netSale(12000, "s", cfg), 12000 - Math.round(12900 * 0.1325 + 40) - 1500 - 150);
  assert.strictEqual(D.costIn(5000, { taxIn: 8.375, shipIn: 150 }), 5000 + 419 + 150);
});
test("max ask is the highest ask that still clears both the ROI target and the minimum profit", () => {
  for (const proceeds of [800, 2000, 7986, 50000]) for (const offer of [{ shipIn: 150 }, { shipIn: 600, taxIn: 8.375 }]) {
    const m = D.maxAsk(proceeds, offer, 20, 500), ok = (a) => { const c = D.costIn(a, offer), pr = proceeds - c; return pr >= 500 && pr >= c * 0.2; };
    if (m > 0) assert.ok(ok(m) && !ok(m + 1), `${proceeds} ${m}`); else assert.ok(!ok(0));
  }
});
test("comps: only exact sales of the grade, inside 90 days, none from the future; medians and nearest-rank quartiles", () => {
  const data = { comps: [...flat("raw", 1000, [5]), [T - 10, 2000, "raw", 1], [T - 40, 3000, "raw", 1], [T - 89, 4000, "raw", 1],
    [T - 90, 9999, "raw", 1], [T + 1, 9999, "raw", 1], [T - 3, 9999, "raw", 0], [T - 3, 9999, "PSA 10", 1]] };
  const e = D.comps(data, "raw", T);
  assert.deepStrictEqual([e.n90, e.n30, e.m90, e.m30, e.q1, e.q3, e.newest, e.saleAge, e.inexact], [4, 2, 2500, null, 1000, 3000, T - 5, 5, 1]);
  assert.strictEqual(e.exit, 2500);                                       // fewer than 3 sales in 30 days: the 90-day median
  assert.strictEqual(D.median([1, 2, 3]), 2); assert.strictEqual(D.median([]), null); assert.strictEqual(D.rank([1, 2, 3, 4], 0.25), 1);
});
test("a clean card at half its sold price is a BUY candidate on the resale route", () => {
  const r = run(card());
  assert.deepStrictEqual([r.verdict, r.route, r.confidence], ["buy", "flip", "B"]);
  const F = r.routes.flip;
  assert.strictEqual(F.exit, 10000); assert.strictEqual(F.profit, 7986 - 5150); assert.ok(F.gates.every((g) => g.ok));
});
test("PASS is the default: each evidence gate on its own blocks a BUY", () => {
  const few = run(card({ data: { comps: flat("raw", 10000, AGES.slice(0, K.MIN_COMPS - 1)) } }));
  assert.deepStrictEqual([few.verdict, few.reason, gate(few, "evidence").ok], ["pass", "evidence", false]);
  assert.strictEqual(run(card({ data: { comps: flat("raw", 10000, [9, 12, 15, 40, 50]) } })).verdict, "buy");       // exactly MIN_COMPS, 3 in 30 days
  const slow = run(card({ data: { comps: flat("raw", 10000, [9, 12, 40, 50, 60, 70]) } }));                         // 2 in 30 days
  assert.deepStrictEqual([slow.verdict, gate(slow, "liquidity").ok], ["pass", false]);
  assert.strictEqual(run(card({ data: { asOf: T - K.MAX_FETCH_AGE } }), {}).verdict, "buy");
  assert.strictEqual(gate(run(card({ data: { asOf: T - K.MAX_FETCH_AGE - 1 } })), "fresh").ok, false);
  const old = (a) => flat("raw", 10000, [a, a + 1, a + 2, 40, 50, 60]);
  assert.strictEqual(gate(run(card({ data: { comps: old(K.MAX_SALE_AGE) } })), "fresh").ok, true);
  assert.strictEqual(gate(run(card({ data: { comps: old(K.MAX_SALE_AGE + 1) } })), "fresh").ok, false);
});
test("spread, second source, trend and warnings", () => {
  const wide = run(card({ data: { comps: [...flat("raw", 5000, [9, 12, 40]), ...flat("raw", 10000, [15, 50]), ...flat("raw", 15000, [20, 60, 70])] } }));
  assert.deepStrictEqual([wide.verdict, gate(wide, "spread").ok], ["pass", false]);
  assert.strictEqual(gate(run(card({ item: { tcg: 12500 } })), "agree").ok, true);           // exactly +25%
  assert.strictEqual(gate(run(card({ item: { tcg: 12510 } })), "agree").ok, false);
  assert.strictEqual(gate(run(card({ item: { tcg: 7500 } })), "agree").ok, true);
  const none = run(card({ item: { tcg: null } }));
  assert.deepStrictEqual([none.verdict, none.reason, none.why], ["pass", "agree", "Sold prices not confirmed by a second source"]);
  assert.strictEqual(gate(run(card({ item: { tcgDay: T - 4 } })), "agree").ok, false);
  const fall = (p30) => card({ data: { comps: [...flat("raw", p30, [9, 12, 15]), ...flat("raw", 10000, [40, 50, 60, 70, 80])] } });
  assert.strictEqual(gate(run(fall(9000)), "trend").ok, false);                                // 30-day median exactly −10%
  assert.strictEqual(gate(run(fall(9010)), "trend").ok, true);
  assert.strictEqual(run(fall(9010)).routes.flip.exit, 9010);                                   // the lower median is the exit
  const knife = run(card(), {}, { warning: { id: "knife", verdict: "pass", name: "Falling knife" } });
  assert.deepStrictEqual([knife.verdict, knife.reason], ["pass", "trend"]);
  assert.strictEqual(run(card(), {}, { warning: { id: "knife", verdict: "unproven", name: "Falling knife" } }).verdict, "buy");
  assert.strictEqual(run(card(), {}, { warning: { id: "dip", verdict: "pass", name: "Dip" } }).verdict, "buy");
});
test("margin, condition and scope", () => {
  const tight = run(card({ offer: { ask: 6700 } }));
  assert.deepStrictEqual([tight.verdict, tight.reason, tight.why], ["pass", "margin", "Doesn't clear your margin"]);
  const F = run(card()).routes.flip;
  assert.strictEqual(run(card({ offer: { ask: F.max } })).verdict, "buy");
  assert.strictEqual(run(card({ offer: { ask: F.max + 1 } })).verdict, "pass");
  const lp = run(card({ offer: { cond: "LP" } })).routes.flip;
  assert.strictEqual(lp.exit, 8500); assert.ok(lp.gates.some((g) => g.code === "condition" && !g.hard));
  const cheap = run(card({ item: { tcg: 1500 }, data: { comps: flat("raw", 1500, AGES) }, offer: { ask: 100 } }));
  assert.deepStrictEqual([cheap.verdict, cheap.scope], ["pass", false]);
  assert.strictEqual(run(card({ item: { tcg: 2000 }, data: { comps: flat("raw", 2000, AGES) }, offer: { ask: 100 } })).scope, true);
});
test("sealed uses sealed sales and has no grade route", () => {
  const r = run({ item: { name: "Box", t: "s", tcg: 20000, tcgDay: T }, data: { asOf: T, comps: flat("sealed", 20000, AGES) }, offer: { ask: 9000, shipIn: 600 } });
  assert.deepStrictEqual([r.verdict, r.route, r.routes.grade], ["buy", "flip", null]);
  assert.strictEqual(r.routes.flip.profit, D.netSale(20000, "s", Y.cfg()) - 9600);
});
test("grade route: expected value from population odds and each grade's sold median", () => {
  const c = card({ data: { comps: [...flat("raw", 4000, AGES), ...flat("PSA 10", 20000, AGES), ...flat("PSA 9", 7000, AGES)], pop: { total: 1000, g10: 400, g9: 400 } },
    item: { tcg: 4000 }, offer: { ask: 3500 } });
  const cfg = Y.cfg(), r = run(c), G = r.routes.grade;
  const exp = Math.round(0.4 * D.netSale(20000, "c", cfg) + 0.4 * D.netSale(7000, "c", cfg) + 0.2 * D.netSale(3600, "c", cfg));
  assert.strictEqual(G.expected, exp);
  assert.strictEqual(G.cost, 3500 + 150 + 2500 + 1500 + Math.round(3500 * 0.01 * 3));
  assert.deepStrictEqual([G.pass, r.verdict, r.route], [true, "buy", "grade"]);
  assert.strictEqual(r.routes.flip.pass, false);                                              // reselling raw at $40 doesn't clear
  assert.strictEqual(run({ ...c, offer: { ...c.offer, cond: "LP" } }).routes.grade.pass, false);
  assert.strictEqual(run({ ...c, data: { ...c.data, pop: { total: 99, g10: 50, g9: 30 } } }).routes.grade.pass, false);
  assert.strictEqual(run({ ...c, data: { ...c.data, comps: [...flat("raw", 4000, AGES), ...flat("PSA 10", 20000, [40, 50, 60, 70, 80]), ...flat("PSA 9", 7000, AGES)] } }).routes.grade.pass, false);
});
test("hold is information only: the rise needed to break even", () => {
  const r = run(card({ offer: { ask: 9500 } }));
  assert.strictEqual(r.verdict, "pass");
  const H = r.routes.hold, cfg = Y.cfg(), cost = 9500 + 150, need = (m) => Math.round(cost * (1 + 0.01 * m));
  const p12 = Math.round(10000 * (1 + H.m12 / 100));
  assert.ok(D.netSale(p12, "c", cfg) >= need(12) && D.netSale(p12 - 1, "c", cfg) < need(12));
  assert.ok(H.m12 > H.m6 && H.m6 > 0);
  assert.strictEqual(run(card()).routes.hold.m12, 0);
});
test("confidence grades the evidence, not the price", () => {
  assert.strictEqual(run(card()).confidence, "B");
  assert.strictEqual(run(card({ data: { comps: flat("raw", 10000, [...AGES, 9, 10, 11, 12, 13, 14, 16, 17]) } })).confidence, "A");
  assert.strictEqual(run(card({ item: { tcg: null } })).confidence, "C");
  assert.strictEqual(run(card({ item: { tcg: null }, data: { asOf: T - 9 } })).confidence, "D");
  assert.strictEqual(run(card({ offer: { ask: 9900 } })).confidence, run(card()).confidence);
});
test("every synthetic scenario lands where it is meant to", () => {
  const want = { "good-flip": "buy", "fair-price": "pass", thin: "pass", stale: "pass", scattered: "pass", disagree: "pass", falling: "pass", "no-second": "pass", played: "pass", grade: "buy", sealed: "pass", cheap: "pass" };
  for (const s of Y.scenarios()) assert.strictEqual(run(s).verdict, want[s.key], s.key);
});
test("the panel: PASS or BUY candidate, every cost line, names escaped, no chart call", () => {
  const c = card({ item: { name: "<b>x</b>" } }), cfg = Y.cfg();
  const r = D.check(c.item, c.data, c.offer, cfg), h = D.html(r, c.item, c.data, c.offer, cfg);
  assert.ok(/<b>BUY candidate<\/b>/.test(h) && /Marketplace fee \(on price \+ 7.5% buyer tax\)/.test(h) && /Shipping out \+ supplies/.test(h) && /Net profit/.test(h) && /Offer up to \$/.test(h));
  assert.ok(!/Buy zone/.test(h) && !/<b>x<\/b>/.test(h));
  const p = run(card({ offer: { ask: 9900 } })), hp = D.html(p, c.item, c.data, { ...c.offer, ask: 9900 }, cfg);
  assert.ok(/<b>PASS<\/b>/.test(hp) && /PASS unless every check clears/.test(hp));
});
test("no panel ever prints a missing number (scenarios and 3,000 random cases), even with a bad grading setting", () => {
  const bad = /undefined|NaN|\bnull\b|Infinity/;
  for (const s of Y.scenarios()) { const cfg = Y.cfg(), r = D.check(s.item, s.data, s.offer, cfg); assert.ok(!bad.test(D.html(r, s.item, s.data, s.offer, cfg)), s.key); }
  for (const c of Y.randomCases(3000, 11)) { const cfg = Y.cfg(), r = D.check(c.item, c.data, c.offer, cfg, c.ctx), h = D.html(r, c.item, c.data, c.offer, cfg); assert.ok(!bad.test(h), h.match(/.{40}(undefined|NaN|null|Infinity).{40}/)?.[0]); }
  const cfg = Y.cfg({ grade: { fee: 2500, ship: 1500, months: "90–100" } }), c = card(), r = D.check(c.item, c.data, c.offer, cfg);
  assert.ok(Number.isFinite(r.routes.grade.cost) && !bad.test(D.html(r, c.item, c.data, c.offer, cfg)));
});
console.log(`${n} deal check tests passed${process.exitCode ? " (with failures above)" : ""}`);
