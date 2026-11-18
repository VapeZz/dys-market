// Random selling-option cases for the independent Python check (ref.py). node tools/channels/cases.js > /tmp/ch_cases.json
const path = require("path"), C = require(path.join(__dirname, "../../site/assets/edge-channels.js"));
let seed = 11; const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
const pick = (a) => a[Math.floor(rnd() * a.length)], out = [];
for (let i = 0; i < 500; i++) {
  const ref = rnd() < 0.1 ? null : Math.round(300 + rnd() * (rnd() < 0.1 ? 900000 : 30000)), cost = Math.round((ref || 5000) * (0.3 + rnd() * 1.2));
  const saved = {};
  for (const k of ["fb", "offerup", "show", "ebay", "vinted"]) if (rnd() < 0.6) {
    const s = {}; if (rnd() < 0.5) s.pricePct = Math.round(60 + rnd() * 50);
    if (["fb", "offerup", "show"].includes(k)) { if (rnd() < 0.6) { s.pay = pick(Object.keys(C.PAY)); s.payPct = C.PAY[s.pay].pct; s.payFlat = C.PAY[s.pay].flat; } if (rnd() < 0.4) s.taxPct = pick([0, 8.375, 7.5]); if (rnd() < 0.4) s.travel = Math.round(rnd() * 1500); }
    if (k === "show" && rnd() < 0.6) { s.booth = Math.round(rnd() * 20000); s.boothSales = Math.ceil(rnd() * 25); }
    if (k === "ebay" && rnd() < 0.5) { s.ship = rnd() < 0.5 ? null : Math.round(rnd() * 800); s.feePct = pick([13.25, 12.35, 10]); s.buyerTax = pick([7.5, 0, 8.375]); }
    if (rnd() < 0.3) s.sup = Math.round(rnd() * 200);
    saved[k] = s;
  }
  const prices = rnd() < 0.3 ? { [pick(["fb", "offerup", "show", "ebay", "vinted"])]: Math.round(rnd() * 40000) } : {};
  const o = { cost, ref, item: { kind: pick(["raw", "graded", "sealed"]), name: pick(["Booster Box", "Elite Trainer Box", "Card"]) }, saved, prices, roi: pick([20, 10, 30]), minProfit: pick([500, 0]), shipAuto: (p) => p >= 5000 ? 500 : 100, breaks: [5000] };
  const r = C.compare(o);
  out.push({ o: { ...o, shipAuto: undefined }, js: { best: r.best, rows: r.rows.map((x) => ({ k: x.k, price: x.price, net: x.at && x.at.net, tax: x.at && x.at.tax, pay: x.at && x.at.pay, fee: x.at && x.at.fee, profit: x.profit, clears: x.clears, state: x.state, breakEven: x.breakEven, target: x.target, matchEbay: x.matchEbay, ok: x.elig.ok })) } });
}
process.stdout.write(JSON.stringify(out));
