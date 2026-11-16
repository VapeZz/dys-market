// Random ledgers and Edge's numbers for them, for the independent check in ref.py. Usage: node random_ledgers.js <seed> <count>
const path = require("path"), L = require(path.join(__dirname, "../../site/assets/edge-ledger.js"));
let s = +process.argv[2] || 1; const rnd = () => ((s = (s * 1103515245 + 12345) % 2147483648) / 2147483648);
const pick = (a) => a[Math.floor(rnd() * a.length)], int = (n) => Math.floor(rnd() * n);
const day = () => `${pick(["2024", "2025", "2026"])}-${String(1 + int(12)).padStart(2, "0")}-${String(1 + int(28)).padStart(2, "0")}`;
const out = [];
for (let k = 0; k < (+process.argv[3] || 500); k++) {
  const T = L.blank(), nb = 1 + int(6);
  for (let b = 0; b < nb; b++) {
    const id = `b${b}`, d = day(), book = pick(L.BOOKS);
    T.buys.push({ id, day: d, book, where: "Card show", pay: "Cash", tax: int(5000), ship: rnd() < .5 ? 0 : int(2000), fees: rnd() < .7 ? 0 : int(1500), void: rnd() < .05 ? 1 : 0 });
    for (let i = 0, ni = 1 + int(5); i < ni; i++) T.items.push({ id: `i${b}_${i}`, buy: id, day: d, book: rnd() < .15 ? pick(L.BOOKS) : book, kind: pick(L.KINDS), name: `n${b}${i}`, qty: 1 + (rnd() < .3 ? int(6) : 0), price: rnd() < .05 ? 0 : int(200000), void: rnd() < .04 ? 1 : 0 });
  }
  for (let i = 0; i < int(3); i++) T.items.push({ id: `m${i}`, buy: "", day: day(), book: pick(L.BOOKS), kind: "Raw", name: `m${i}`, qty: 1 + int(3), price: int(90000) });
  const its = T.items;
  for (let j = 0, ns = int(8); j < ns; j++) { const x = pick(its); T.sales.push({ id: `s${j}`, day: day(), item: rnd() < .03 ? "gone" : x.id, book: x.book, qty: 1 + (rnd() < .2 ? int(3) : 0), plat: "eBay", price: int(300000), shipIn: int(1500), fees: int(30000), shipOut: int(1500), supplies: int(200), other: rnd() < .8 ? 0 : int(5000), void: rnd() < .05 ? 1 : 0 }); }
  for (let j = 0, nc = int(5); j < nc; j++) T.costs.push({ id: `c${j}`, day: day(), book: pick(L.BOOKS), item: rnd() < .5 ? pick(its).id : "", kind: "Grading", amount: int(9000), void: rnd() < .05 ? 1 : 0 });
  for (let j = 0, nm = int(4); j < nm; j++) T.cash.push({ id: `k${j}`, day: day(), book: pick(L.BOOKS), kind: pick(L.CASH_KINDS), amount: int(500000), to: pick(L.BOOKS) });
  const prices = Object.fromEntries(its.map((x) => [x.id, rnd() < .3 ? null : int(250000)]));
  const year = pick(["2025", "2026"]), asOf = rnd() < .3 ? `${year}-12-31` : null;
  const R = L.compute(T, { year, asOf, priceOf: (x) => prices[x.id] });
  out.push({ T, prices, year, asOf, edge: { items: R.items.map((x) => [x.id, x.cost, x.left, x.costLeft, x.value]), sales: R.sales.map((x) => [x.id, x.cost, x.net, x.profit, x.held]), tot: R.tot } });
}
process.stdout.write(JSON.stringify(out));
