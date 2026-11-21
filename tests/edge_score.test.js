// Checks for the real-profit scorecard (site/assets/edge-score.js) on synthetic Ledgers run through the real Ledger math
// (edge-ledger.js), the estimate line from the real Deal check, and the lot offer's Ledger draft. No dependencies:
//   node tests/edge_score.test.js
const path = require("path"), assert = require("assert");
const SC = require(path.join(__dirname, "../site/assets/edge-score.js"));
const L = require(path.join(__dirname, "../site/assets/edge-ledger.js"));
const D = require(path.join(__dirname, "../site/assets/edge-deal.js"));
const B = require(path.join(__dirname, "../site/assets/edge-buylist.js"));
const LOT = require(path.join(__dirname, "../site/assets/edge-lot.js"));
const Y = require(path.join(__dirname, "../tools/deal/synth.js"));
let n = 0;
const test = (name, fn) => { try { fn(); n++; } catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; } };
const sum = (a, f) => a.reduce((s, x) => s + f(x), 0);
const T = Y.DAY0, AGES = [3, 5, 9, 12, 15, 20, 25, 40, 50, 60, 70, 80];
const flat = (px, ages = AGES) => ages.map((a) => [T - a, px, "raw", 1]);
const data = (comps) => ({ asOf: T, source: "test", comps });
const cfg = () => ({ ...Y.cfg(), budget: null });

// a hand-made ledger: a card-show buy of 2 cards with tax and shipping, an online buy, one moved-in item, sales, a grading
// cost tied to an item and a table fee not tied to one
function sample() {
  const t = L.blank();
  t.buys.push({ id: "b1", day: "2026-10-01", book: "Business", where: "Card show", pay: "Cash", tax: 838, ship: 0, fees: 0 });
  t.items.push({ id: "i1", buy: "b1", day: "2026-10-01", book: "Business", kind: "Raw", name: "Pikachu", cond: "NM", qty: 2, price: 2000,
    note: "bought with a friend · Edge est: net $35.00–$40.00/copy (Show check · NM · B · 2026-10-01)" });
  t.items.push({ id: "i2", buy: "b1", day: "2026-10-01", book: "Business", kind: "Raw", name: "Charmander", cond: "LP", qty: 1, price: 1000, note: "Edge est: net $14.00–$16.00/copy (Lot offer · NM · 2026-10-01)" });
  t.buys.push({ id: "b2", day: "2026-10-05", book: "Personal", where: "Online", pay: "Card", tax: 0, ship: 500, fees: 0 });
  t.items.push({ id: "i3", buy: "b2", day: "2026-10-05", book: "Personal", kind: "Graded", grader: "PSA", grade: "10", name: "Umbreon", qty: 1, price: 30000, note: "Edge est: net $300.00–$325.00/copy (Deal check · B · 2026-10-05)" });
  t.items.push({ id: "i4", buy: "", day: "2026-09-01", book: "Business", kind: "Sealed", name: "ETB", qty: 1, price: 4500 });
  t.costs.push({ id: "c1", day: "2026-10-10", book: "Personal", item: "i3", kind: "Grading", amount: 2500 });
  t.costs.push({ id: "c2", day: "2026-11-01", book: "Business", item: "", kind: "Show table", amount: 4000 });
  t.sales.push({ id: "s1", day: "2026-11-02", item: "i1", book: "Business", qty: 1, plat: "eBay", price: 4500, shipIn: 0, fees: 650, shipOut: 100, supplies: 50, other: 0 });
  t.sales.push({ id: "s2", day: "2026-11-10", item: "i2", book: "Business", qty: 1, plat: "Card show", price: 1200, shipIn: 0, fees: 0, shipOut: 0, supplies: 0, other: 0 });
  t.sales.push({ id: "s3", day: "2026-11-12", item: "i3", book: "Personal", qty: 1, plat: "eBay", price: 30000, shipIn: 500, fees: 4100, shipOut: 500, supplies: 100, other: 0 });
  t.sales.push({ id: "s4", day: "2025-06-01", item: "i4", book: "Business", qty: 1, plat: "Whatnot", price: 6000, shipIn: 0, fees: 600, shipOut: 0, supplies: 0, other: 0 });
  return t;
}

test("totals are the Ledger's own sale math, worked out again by hand", () => {
  const R = L.compute(sample(), { today: "2026-11-21" }), C = SC.score(R, { today: "2026-11-21" });
  // costs: b1 tax 838 split by price 4000:1000 → 670:168; Pikachu each (4000+670)/2, sold 1 → 2335; Charmander 1168;
  // Umbreon 30000 + 500 ship + 2500 grading = 33000; ETB 4500
  const costs = { s1: 2335, s2: 1168, s3: 33000, s4: 4500 };
  const nets = { s1: 4500 - 650 - 100 - 50, s2: 1200, s3: 30500 - 4100 - 500 - 100, s4: 6000 - 600 };
  for (const r of C.rows) { assert.strictEqual(r.cost, costs[r.id], r.id); assert.strictEqual(r.net, nets[r.id], r.id); assert.strictEqual(r.profit, nets[r.id] - costs[r.id], r.id); }
  const t = C.total;
  assert.strictEqual(t.sales, 4); assert.strictEqual(t.proceeds, 4500 + 1200 + 30500 + 6000); assert.strictEqual(t.fees, 650 + 4100 + 600);
  assert.strictEqual(t.shipOut, 600); assert.strictEqual(t.supplies, 150); assert.strictEqual(t.shipIn, 500);
  assert.strictEqual(t.cost, sum(Object.values(costs), (x) => x)); assert.strictEqual(t.profit, sum(Object.keys(nets), (k) => nets[k] - costs[k]));
  assert.ok(Math.abs(t.roi - t.profit / t.cost * 100) < 1e-9); assert.strictEqual(t.wins, 3);
  assert.strictEqual(C.expenses.total, 4000); assert.strictEqual(C.afterExpenses, t.profit - 4000);
  assert.strictEqual(C.held.units, 1); assert.strictEqual(C.held.cost, 2335);   // the second Pikachu
  assert.deepStrictEqual(C.best.map((r) => r.id), ["s1", "s4", "s2"]); assert.deepStrictEqual(C.worst.map((r) => r.id), ["s3"]);
});

test("groups: where bought, type, where sold and cost per item; every grouping adds up to the total", () => {
  const C = SC.score(L.compute(sample(), { today: "2026-11-21" }), { today: "2026-11-21" });
  const keys = (g) => g.map((x) => x.key).sort();
  assert.deepStrictEqual(keys(C.bySource), ["Before the Ledger", "Card show", "Online"]);
  assert.deepStrictEqual(keys(C.byType), ["Graded · PSA 10", "Raw · LP", "Raw · NM", "Sealed"]);
  assert.deepStrictEqual(keys(C.byPlat), ["Card show", "Whatnot", "eBay"]);
  assert.deepStrictEqual(C.byCost.map((x) => x.key), ["Under $20", "$20–$50", "$75 and up"]);
  for (const g of [C.bySource, C.byType, C.byPlat, C.byCost]) for (const f of ["sales", "proceeds", "fees", "shipOut", "cost", "profit", "net"]) assert.strictEqual(sum(g, (x) => x[f]), C.total[f], f);
  const show = C.bySource.find((x) => x.key === "Card show"); assert.strictEqual(show.sales, 2); assert.strictEqual(show.profit, (3700 - 2335) + (1200 - 1168));
});

test("period and book filters", () => {
  const R = L.compute(sample(), { today: "2026-11-21" });
  assert.strictEqual(SC.score(R, { today: "2026-11-21", period: "year" }).total.sales, 3);
  assert.strictEqual(SC.score(R, { today: "2026-11-21", period: "d30" }).total.sales, 3);
  assert.strictEqual(SC.score(R, { today: "2026-11-21", period: "d30" }).expenses.total, 4000);
  assert.strictEqual(SC.score(R, { today: "2026-12-20", period: "d30" }).total.sales, 0);
  const P = SC.score(R, { today: "2026-11-21", book: "Personal" });
  assert.strictEqual(P.total.sales, 1); assert.strictEqual(P.expenses.total, 0); assert.strictEqual(P.held.items, 0);
  assert.strictEqual(SC.score(R, { today: "2026-11-21", book: "Business" }).total.sales, 3);
  const E = SC.score(L.compute(L.blank(), {}), { today: "2026-11-21" });
  assert.strictEqual(E.total.sales, 0); assert.strictEqual(E.total.roi, null); assert.strictEqual(E.est.recorded, 0);
});

test("estimates compared only where recorded, for the same condition; in range, above, below", () => {
  const C = SC.score(L.compute(sample(), { today: "2026-11-21" }), { today: "2026-11-21" });
  const E = C.est;
  assert.strictEqual(E.total, 4); assert.strictEqual(E.recorded, 2, "Charmander's estimate was for NM but it's LP: not compared; the ETB has none");
  const p = E.rows.find((r) => r.id === "s1"), u = E.rows.find((r) => r.id === "s3");
  assert.strictEqual(p.est.where, "in"); assert.strictEqual(p.est.perCopy, 3700); assert.strictEqual(p.est.estNet, 3750);   // $37.00 net, inside $35–$40
  assert.strictEqual(u.est.where, "below"); assert.strictEqual(u.est.perCopy, 25800); assert.strictEqual(u.est.estProfit, 31250 - 33000);
  assert.strictEqual(E.inBand, 1); assert.strictEqual(E.below, 1); assert.strictEqual(E.estNet, 3750 + 31250); assert.strictEqual(E.actualNet, 3700 + 25800);
});

test("parse, write and replace the estimate line; the rest of the note is kept", () => {
  const tag = SC.tagFromNet(3712, "LP", "Show check", "B", "2026-11-21");
  assert.strictEqual(tag, "Edge est: net $35.00–$40.00/copy (Show check · LP · B · 2026-11-21)");
  assert.deepStrictEqual(SC.parseTag(`bought at the Henderson show · ${tag}`), { lo: 3500, hi: 4000, mid: 3750, src: "Show check", cond: "LP", grade: "B", day: "2026-11-21" });
  assert.strictEqual(SC.withTag("bought at the Henderson show", tag), `bought at the Henderson show · ${tag}`);
  const again = SC.tagFromNet(1234, "NM", "Deal check", "A", "2026-11-22");
  assert.strictEqual(SC.withTag(`bought at the Henderson show · ${tag}`, again), `bought at the Henderson show · ${again}`);
  assert.strictEqual(SC.withTag(tag, ""), "");
  assert.strictEqual(SC.parseTag("no estimate here"), null); assert.strictEqual(SC.parseTag("Edge est: net $5.00–$2.00/copy"), null);
  assert.deepStrictEqual(SC.parseTag("Edge est: net $1,000.00–$1,025.00/copy"), { lo: 100000, hi: 102500, mid: 101250, src: "", cond: "", grade: "", day: "" });
  // bands only, never an exact amount: every value is on its band's step
  for (let c = 1; c < 300000; c += 777) { const b = SC.band(c); const w = c < 2000 ? 200 : c < 5000 ? 500 : c < 10000 ? 1000 : 2500; assert.ok(b[0] % w === 0 && b[1] - b[0] === w && b[0] <= c && c < b[1]); }
  assert.deepStrictEqual(SC.band(3712), B.resaleBand(3712), "same widths as the Buy list's resale range");
});

test("the estimate line from a Deal check: only when the evidence cleared every check before profit", () => {
  const it = { id: 1, n: "Test card (Holofoil)", name: "Test", t: "c", tcg: 4000, tcgDay: T };
  const good = D.check(it, data(flat(4000)), { ask: 2000, cond: "LP", shipIn: 0, taxIn: 0 }, cfg());
  const tag = SC.tagFromCheck(good, "LP", "Show check", "2026-11-21"), P = SC.parseTag(tag);
  assert.ok(P && P.lo <= good.routes.flip.proceeds && good.routes.flip.proceeds < P.hi, tag);
  assert.ok(!tag.includes((good.routes.flip.exit / 100).toFixed(2)), "the sold median itself is never written");
  const thin = D.check(it, data(flat(4000, [3, 40, 60])), { ask: 2000, cond: "NM", shipIn: 0, taxIn: 0 }, cfg());
  assert.strictEqual(SC.tagFromCheck(thin, "NM", "Show check"), "");
  const dis = D.check({ ...it, tcg: 9000 }, data(flat(4000)), { ask: 2000, cond: "NM", shipIn: 0, taxIn: 0 }, cfg());
  assert.strictEqual(SC.tagFromCheck(dis, "NM", "Show check"), "");
  // a margin miss still records (the evidence was fine; the price was the problem)
  const dear = D.check(it, data(flat(4000)), { ask: 9000, cond: "NM", shipIn: 0, taxIn: 0 }, cfg());
  assert.strictEqual(dear.verdict, "pass"); assert.ok(SC.tagFromCheck(dear, "NM", "Show check"));
  assert.strictEqual(SC.tagFromCheck(null, "NM", "x"), "");
});

test("a lot's Ledger draft: estimate line on each counted card, by the per-card prices when every card has one", () => {
  let k = 0; const line = (px, o = {}) => ({ l: `l${++k}`, k: `${k}|C${k}`, id: k, g: 1, n: `C${k} (Holofoil)`, setN: "S", t: "c", cond: "NM", qty: 1, tcg: px, tcgDay: T, ...o });
  const a = line(4000, { qty: 2, ask: 1500 }), b = line(3000, { ask: 1000, cond: "LP" }), c = line(800, { ask: 300 });
  const live = new Map([[a.k, { data: data(flat(4000)) }], [b.k, { data: data(flat(3000)) }], [c.k, { data: data(flat(800)) }]]);
  const lot = { askMode: "each", lines: [a, b, c] }, R = LOT.evaluate(D, B, lot, (x) => live.get(x) || null, { ...Y.cfg(), budget: { limit: 7500, reserve: 10000, cash: 50000 } }, T * 864e5);
  const d = LOT.ledgerDraft(D, lot, 4000, { rows: R.rows, tag: SC.tagFromNet, day: "2026-11-21" });
  assert.strictEqual(sum(d.lines, (l) => l.price * l.qty), 4000);
  const tot = (id) => sum(d.lines.filter((l) => l.tcg === id), (l) => l.price * l.qty);
  assert.deepStrictEqual([tot(a.id), tot(b.id), tot(c.id)], [2791, 930, 279], "split by the per-card prices (3000:1000:300 of $40)");
  const tagA = SC.parseTag(d.lines.find((l) => l.tcg === a.id).note), tagB = SC.parseTag(d.lines.find((l) => l.tcg === b.id).note);
  const rowA = R.rows.find((r) => r.l === a.l), rowB = R.rows.find((r) => r.l === b.l);
  assert.ok(tagA.lo <= rowA.unit && rowA.unit < tagA.hi && tagA.src === "Lot offer" && tagA.cond === "NM");
  assert.ok(tagB.lo <= rowB.unit && rowB.unit < tagB.hi && tagB.cond === "LP");
  assert.ok(!d.lines.find((l) => l.tcg === c.id).note, "a card counted $0 (under $20) gets no estimate");
  // without per-card prices it splits by TCGplayer market × condition, as before
  const d2 = LOT.ledgerDraft(D, { ...lot, askMode: "total" }, 4000, {});
  assert.strictEqual(sum(d2.lines, (l) => l.price * l.qty), 4000); assert.ok(d2.lines.every((l) => !l.note));
  // through the Ledger: the note is saved on the item and the scorecard reads it back
  const t = L.blank(), { buy, items } = L.buyRows({ day: "2026-11-21", book: "Business", where: "Card show", pay: "Cash", lines: d.lines });
  t.buys.push(buy); items.forEach((x) => t.items.push(x));
  const ia = items.find((x) => x.tcg === a.id);
  t.sales.push({ id: "s1", day: "2026-11-25", item: ia.id, book: "Business", qty: 1, plat: "eBay", price: 4200, fees: 600, shipOut: 100, supplies: 50 });
  const C = SC.score(L.compute(t, { today: "2026-11-26" }), { today: "2026-11-26" });
  assert.strictEqual(C.est.recorded, 1); assert.strictEqual(C.est.rows[0].est.src, "Lot offer");
});

test("random ledgers: groupings always add up, ROI matches, nothing breaks on odd rows", () => {
  let s = 11; const rnd = () => ((s = (s * 1103515245 + 12345) % 2147483648) / 2147483648), pick = (a) => a[Math.floor(rnd() * a.length)], int = (k) => Math.floor(rnd() * k);
  const day = () => `${pick(["2025", "2026"])}-${String(1 + int(12)).padStart(2, "0")}-${String(1 + int(28)).padStart(2, "0")}`;
  for (let k = 0; k < 600; k++) {
    const t = L.blank();
    for (let b = 0; b < 1 + int(5); b++) {
      const id = `b${b}`, d = day(), book = pick(L.BOOKS);
      t.buys.push({ id, day: d, book, where: pick(L.WHERE), pay: "Cash", tax: int(800), ship: int(600), fees: 0, void: rnd() < .05 ? 1 : 0 });
      for (let i = 0; i < 1 + int(4); i++) t.items.push({ id: `i${b}_${i}`, buy: id, day: d, book, kind: pick(L.KINDS), cond: pick(["NM", "LP", ""]), grader: "PSA", grade: pick(["10", "9", ""]), name: `n${b}${i}`, qty: 1 + int(3), price: int(20000),
        note: rnd() < .4 ? SC.tagFromNet(1 + int(30000), "NM", pick(["Show check", "Lot offer"]), "B", d) : "" });
    }
    for (let j = 0; j < int(9); j++) { const x = pick(t.items); t.sales.push({ id: `s${j}`, day: day(), item: rnd() < .03 ? "gone" : x.id, book: x.book, qty: 1 + int(2), plat: pick(L.PLATS), price: int(40000), shipIn: int(500), fees: int(5000), shipOut: int(800), supplies: int(100), other: rnd() < .8 ? 0 : int(500), void: rnd() < .05 ? 1 : 0 }); }
    for (let j = 0; j < int(3); j++) t.costs.push({ id: `c${j}`, day: day(), book: pick(L.BOOKS), item: rnd() < .5 ? pick(t.items).id : "", kind: pick(L.COST_KINDS), amount: int(4000) });
    const R = L.compute(t, { today: "2026-11-21" });
    for (const book of ["All", ...L.BOOKS]) for (const period of ["all", "year", "d90"]) {
      const C = SC.score(R, { book, period, today: "2026-11-21" });
      for (const g of [C.bySource, C.byType, C.byPlat, C.byCost]) for (const f of ["sales", "units", "proceeds", "fees", "shipOut", "supplies", "cost", "net", "profit"]) assert.strictEqual(sum(g, (x) => x[f]), C.total[f], `${f} ${book} ${period}`);
      assert.strictEqual(C.total.profit, sum(C.rows, (r) => r.profit)); assert.strictEqual(C.rows.length, C.total.sales);
      if (C.total.cost > 0) assert.ok(Math.abs(C.total.roi - C.total.profit / C.total.cost * 100) < 1e-9);
      assert.ok(C.est.recorded <= C.est.total && C.est.inBand + C.est.above + C.est.below === C.est.recorded);
      if (period === "year" && book === "All") assert.strictEqual(C.total.profit, R.tot.All.realized, "same as the Ledger's own realized total for the year");
    }
  }
});

console.log(`edge_score: ${n} tests passed`);
