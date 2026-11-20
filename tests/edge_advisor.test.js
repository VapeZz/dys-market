// Checks for the Holdings Advisor (site/assets/edge-advisor.js), driven by the real Deal check, graded check and selling
// options on synthetic sales only. No dependencies: node tests/edge_advisor.test.js
const path = require("path"), assert = require("assert");
const A = require(path.join(__dirname, "../site/assets/edge-advisor.js"));
const D = require(path.join(__dirname, "../site/assets/edge-deal.js"));
const G = require(path.join(__dirname, "../site/assets/edge-graded.js"));
const C = require(path.join(__dirname, "../site/assets/edge-channels.js"));
const Y = require(path.join(__dirname, "../tools/deal/synth.js"));
const T = Y.DAY0;
let n = 0;
const test = (name, fn) => { try { fn(); n++; } catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; } };

const AGES = [9, 12, 15, 20, 25, 40, 50, 60, 70, 80];
const flat = (grade, px, ages) => ages.map((a) => [T - a, px, grade, 1]);
const cfg = Y.cfg();
const item = (tcg = 10000, t = "c") => ({ name: "SYNTH card", t, tcg, tcgDay: T });
const chOpts = (kind, cost, ref) => ({ item: { kind, name: "SYNTH" }, saved: {}, roi: 20, minProfit: 500, breaks: [5000], shipAuto: (p) => p >= 5000 ? 500 : 100,
  ebay: { feePct: 13.25, topFrom: 750000, topPct: 2.35, feeFlat: 40, buyerTax: 7.5, ship: null, sup: 50 }, cost, ref });
// a raw holding the way edge.js builds it: own() on the sold data, channels at the conservative sold exit
function raw(cost, data, o = {}) {
  const own = D.own(item(o.tcg, o.t), data, { cost, cond: o.cond || "NM" }, cfg);
  const ref = own.r.routes.flip.exit;
  return { key: o.key || "k" + cost, name: o.name || "SYNTH raw", kind: o.t === "s" ? "sealed" : "raw", qty: o.qty || 1, cost, cond: o.cond || "NM",
    own, ch: ref && ["sell", "hold", "grade"].includes(own.label) ? C.compare(chOpts(o.t === "s" ? "sealed" : "card", cost, ref)) : null };
}
const SELL = { feePct: 13.25, topPct: 2.35, topFrom: 750000, perOrder: 40, buyerTax: 7.5, ship: null, supplies: 50, shipAuto: (p) => p >= 5000 ? 500 : 100, breaks: [5000] };
const OPTS = { today: T, roi: 20, minProfit: 500 };
function slab(cost, list, o = {}) {
  const data = { asOf: T, label: "PSA 10", comps: list.map(([age, c]) => [T - age, c, "PSA 10", 1]), capped: [], oldestRead: null };
  const r = G.evaluate(data, { cost, label: "PSA 10" }, SELL, OPTS);
  return { key: o.key || "g" + cost, name: o.name || "SYNTH slab", kind: "graded", qty: 1, cost, grade: "PSA 10", graded: r,
    ch: r.typical != null ? C.compare(chOpts("graded", cost, r.typical)) : null };
}
const liquid = { asOf: T, comps: flat("raw", 10000, AGES) };

test("SELL: clears the target at real sold prices; best channel is the highest estimated profit", () => {
  const x = A.classify(raw(3000, liquid));
  assert.strictEqual(x.action, "sell");
  assert.strictEqual(x.ref, 10000);                                        // conservative exit = lower of 30/90-day medians
  assert.ok(x.best && x.best.profit >= 4986, x.best);                      // eBay alone nets +$49.86 (Deal check's own test)
  const ebay = x.best.ebay; assert.strictEqual(ebay.profit, 4986);
  assert.ok(x.evidence.n30 === 5 && x.evidence.age === 9);
});
test("HOLD: below target, prices steady; target price shown", () => {
  const x = A.classify(raw(7500, liquid));
  assert.strictEqual(x.action, "hold"); assert.strictEqual(x.profitNow, 486);
  assert.ok(x.best && x.best.target > 0);
});
test("MONITOR: worth less than paid", () => {
  const x = A.classify(raw(9500, liquid));
  assert.strictEqual(x.action, "monitor"); assert.ok(x.profitNow < 0);
});
test("MONITOR: prices slipping (30-day median 10%+ under 90-day) even when in profit", () => {
  const comps = [...flat("raw", 8500, [9, 12, 15, 20, 25]), ...flat("raw", 11000, [40, 50, 60, 70, 80])];
  const h = raw(6000, { asOf: T, comps });
  assert.ok(h.own.r.routes.flip.ev.change <= -10, h.own.r.routes.flip.ev.change);
  const x = A.classify(h);
  assert.ok(["monitor", "sell"].includes(x.action));
  if (h.own.label === "hold") assert.strictEqual(x.action, "monitor");
  const h2 = raw(7000, { asOf: T, comps });                                 // at this cost it's below target -> monitor, not hold
  assert.strictEqual(h2.own.label, "hold"); assert.strictEqual(A.classify(h2).action, "monitor");
  assert.ok(/slipping/.test(A.classify(h2).why));
});
test("GRADE: raw NM card where grading's expected result beats selling raw; labelled as a bet", () => {
  const data = { asOf: T, comps: [...flat("raw", 4000, AGES), ...flat("PSA 10", 20000, AGES), ...flat("PSA 9", 7000, AGES)], pop: { total: 1000, g10: 400, g9: 400 } };
  const x = A.classify(raw(1000, data, { tcg: 4000 }));
  assert.strictEqual(x.action, "grade"); assert.ok(x.gradeProfit > 0); assert.ok(/bets on the grade/.test(x.why));
});
test("NOT ENOUGH DATA: thin sales, no sales, not checked, provider error", () => {
  assert.strictEqual(A.classify(raw(1000, { asOf: T, comps: flat("raw", 10000, [9, 40]) })).action, "data");
  assert.strictEqual(A.classify(raw(1000, null)).action, "data");
  const nc = A.classify({ key: "n", name: "x", kind: "raw", cost: 100, note: "Not reviewed yet: tap Review." });
  assert.strictEqual(nc.action, "data"); assert.strictEqual(nc.why, "Not reviewed yet: tap Review."); assert.strictEqual(nc.ref, null);
  const er = A.classify({ key: "e", name: "x", kind: "graded", cost: 100, graded: null, note: "No connection to the sold-price relay. Try again." });
  assert.strictEqual(er.action, "data");
  // no number is ever invented for a NOT ENOUGH DATA row
  const B = A.board([raw(1000, null)]); assert.strictEqual(B.by.data[0].best, null); assert.strictEqual(B.by.data[0].profitNow, null);
});
test("graded: SELL / HOLD / MONITOR / NOT ENOUGH DATA from that grade's own sales", () => {
  const steady = [[6, 8200], [7, 8000], [8, 8400], [9, 7900], [12, 8300], [20, 8200], [25, 8100]];
  assert.strictEqual(A.classify(slab(5000, steady)).action, "sell");
  const x = A.classify(slab(7000, steady));                               // the Pikachu case: −$5.58 at $82 typical
  assert.strictEqual(x.action, "monitor"); assert.strictEqual(x.profitNow, -558); assert.ok(/Break-even \$88\.51/.test(x.why), x.why);
  assert.strictEqual(A.classify(slab(6000, steady)).action, "hold");      // +$4.42: positive, under target, steady
  const thin = A.classify(slab(6000, [[6, 8200], [40, 8000]]));
  assert.strictEqual(thin.action, "data"); assert.strictEqual(thin.best, null); assert.strictEqual(thin.ref, null);   // no channel shown on a data row
  const lower = [[1, 7000], [3, 7000], [5, 7100], [8, 7000], [16, 8600], [18, 8500], [20, 8600], [25, 8500]];
  const y = slab(5400, lower); assert.strictEqual(y.graded.s.trend.word, "lower");
  if (y.graded.verdict === "hold") assert.strictEqual(A.classify(y).action, "monitor");
});
test("board: groups, counts, ordering and the sell total", () => {
  const list = [raw(3000, liquid, { key: "a", name: "A" }), raw(2000, liquid, { key: "b", name: "B" }), raw(7500, liquid, { key: "c" }), raw(9500, liquid, { key: "d" }),
    raw(1000, null, { key: "e" }), slab(5000, [[6, 8200], [7, 8000], [8, 8400], [9, 7900], [12, 8300], [20, 8200], [25, 8100]], { key: "f" })];
  const B = A.board(list);
  assert.deepStrictEqual(B.counts, { sell: 3, grade: 0, monitor: 1, hold: 1, data: 1 });
  assert.strictEqual(B.by.sell[0].key, "b");                               // highest profit first
  assert.strictEqual(B.total, 6); assert.strictEqual(B.valued, 5);
  const want = B.by.sell.reduce((s, x) => s + x.profitNow, 0); assert.strictEqual(B.sellProfit, want);
  assert.strictEqual(B.sellBest, B.by.sell.reduce((s, x) => s + x.best.profit, 0)); assert.ok(B.sellBest >= B.sellProfit);
});
test("html: every holding appears once; NOT ENOUGH DATA rows show no price or profit; compact mode", () => {
  const list = [raw(3000, liquid, { key: "a", name: "Alpha" }), raw(1000, null, { key: "z", name: "Zeta" })];
  const h = A.html(A.board(list), { roi: 20 });
  assert.strictEqual((h.match(/data-key="a"/g) || []).length, 1); assert.strictEqual((h.match(/data-key="z"/g) || []).length, 1);
  const zrow = h.slice(h.indexOf('data-key="z"')); assert.ok(/no value/.test(zrow.slice(0, 900)) && !/Best estimate/.test(zrow.slice(0, 900)));
  assert.ok(/Worth selling/.test(h) && /Not enough data/.test(h));
  const c = A.html(A.board(list), { roi: 20, compact: true }); assert.ok(!/data-key=/.test(c) && /adv-tile/.test(c));
  assert.ok(/Nothing held yet/.test(A.html(A.board([]), { roi: 20 })));
  assert.ok(!/<script/i.test(A.html(A.board([raw(3000, liquid, { name: "<script>x</script>" })]), { roi: 20 })));    // names are escaped
});
console.log(`${n} advisor tests passed${process.exitCode ? " (with failures above)" : ""}`);
