// Expected scorecard numbers for tools/score/browser_check.py: the Ledger math and the scorecard run in Node on the same
// ledger the page has. Usage: node expect.js '<ledger tables json>' '<opts json>'
const path = require("path");
const L = require(path.join(__dirname, "../../site/assets/edge-ledger.js")), SC = require(path.join(__dirname, "../../site/assets/edge-score.js"));
const [Tj, oj] = process.argv.slice(2), T = JSON.parse(Tj), o = JSON.parse(oj || "{}");
const C = SC.score(L.compute(T, { today: o.today }), o);
process.stdout.write(JSON.stringify({ total: C.total, afterExpenses: C.afterExpenses, expenses: C.expenses.total, bySource: C.bySource.map((g) => [g.key, g.sales, g.profit]),
  byType: C.byType.map((g) => [g.key, g.sales, g.profit]), byPlat: C.byPlat.map((g) => [g.key, g.sales, g.profit]), byCost: C.byCost.map((g) => [g.key, g.sales, g.profit]), est: { recorded: C.est.recorded, inBand: C.est.inBand, above: C.est.above, below: C.est.below } }));
