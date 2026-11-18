// Checks for the selling-option comparison (site/assets/edge-channels.js). Synthetic numbers only.
// node tests/edge_channels.test.js
const path = require("path"), assert = require("assert");
const C = require(path.join(__dirname, "../site/assets/edge-channels.js"));
let n = 0;
const test = (name, fn) => { try { fn(); n++; } catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; } };
const shipAuto = (p) => p >= 5000 ? 500 : 100;
const base = { cost: 7000, ref: 8200, item: { kind: "graded", name: "SYNTH Pikachu" }, roi: 20, minProfit: 500, shipAuto, breaks: [5000] };
const row = (res, k) => res.rows.find((r) => r.k === k);

test("eBay row matches the PSA check's hand-checked numbers ($82 sale, $70 paid)", () => {
  const e = row(C.compare(base), "ebay");
  assert.strictEqual(e.price, 8200); assert.strictEqual(e.at.fee, 1208); assert.strictEqual(e.at.ship, 500); assert.strictEqual(e.at.sup, 50);
  assert.strictEqual(e.at.net, 6442); assert.strictEqual(e.profit, -558);
  assert.strictEqual(e.breakEven, 8851); assert.strictEqual(e.target, 10483);
});
test("local options start at 90% of the eBay median, Vinted at 85%, with no platform fee", () => {
  const r = C.compare(base);
  for (const k of ["fb", "offerup", "show"]) { const x = row(r, k); assert.strictEqual(x.price, 7380); assert.strictEqual(x.at.fee, 0); assert.strictEqual(x.at.net, 7380); assert.strictEqual(x.profit, 380); assert.ok(!x.typed); }
  const v = row(r, "vinted"); assert.strictEqual(v.price, 6970); assert.strictEqual(v.at.fee, 0); assert.strictEqual(v.at.ship, 0); assert.strictEqual(v.at.net, 6920);
});
test("break-even and the 20% price per option; 'matches eBay' price", () => {
  const r = C.compare(base), fb = row(r, "fb");
  assert.strictEqual(fb.breakEven, 7000); assert.strictEqual(fb.target, 8400);   // 20% of $70 = $14 ≥ $5 minimum
  assert.strictEqual(fb.matchEbay, 6442);                                       // a $64.42 local cash sale leaves what eBay at $82 leaves
  assert.strictEqual(row(r, "vinted").breakEven, 7050);                        // + $0.50 supplies
  assert.strictEqual(row(r, "ebay").matchEbay, null);
});
test("payment fees: Venmo goods & services 2.99%, Venmo business 1.9% + $0.10, PayPal 2.99%, Square 2.6% + 15¢, cash none", () => {
  const at = (pay) => row(C.compare({ ...base, saved: { fb: { pay, payPct: C.PAY[pay].pct, payFlat: C.PAY[pay].flat } } }), "fb").at;
  assert.strictEqual(at("cash").pay, 0);
  assert.strictEqual(at("venmo").pay, Math.round(7380 * 0.0299));
  assert.strictEqual(at("venmobiz").pay, Math.round(7380 * 0.019) + 10);
  assert.strictEqual(at("paypal").pay, Math.round(7380 * 0.0299));
  assert.strictEqual(at("card").pay, Math.round(7380 * 0.026) + 15);
  const c = C.setup(C.CHANNELS[0], { pay: "card" }); assert.strictEqual(c.payPct, 2.6); assert.strictEqual(c.payFlat, 15);
});
test("sales tax: collected and passed on, never revenue or profit; only the payment fee on the total sees it", () => {
  const cash = row(C.compare({ ...base, saved: { fb: { taxPct: 8.375 } } }), "fb");
  assert.strictEqual(cash.at.tax, Math.round(7380 * 0.08375)); assert.strictEqual(cash.at.net, 7380); assert.strictEqual(cash.profit, 380);
  const card = row(C.compare({ ...base, saved: { fb: { taxPct: 8.375, pay: "card", payPct: 2.6, payFlat: 15 } } }), "fb");
  assert.strictEqual(card.at.pay, Math.round((7380 + cash.at.tax) * 0.026) + 15);
  assert.strictEqual(card.at.net, 7380 - card.at.pay);
  // shipped options never take a tax setting (eBay collects it; it only sets eBay's fee base)
  assert.strictEqual(row(C.compare({ ...base, saved: { ebay: { taxPct: 9 }, vinted: { taxPct: 9 } } }), "vinted").at.tax, 0);
});
test("booth fee is split over the expected sales, and the count is editable; travel is a straight cost", () => {
  const s = row(C.compare({ ...base, saved: { show: { booth: 5000, boothSales: 10, travel: 800 } } }), "show");
  assert.strictEqual(s.at.booth, 500); assert.strictEqual(s.at.travel, 800); assert.strictEqual(s.at.net, 7380 - 1300);
  assert.strictEqual(row(C.compare({ ...base, saved: { show: { booth: 5000, boothSales: 4 } } }), "show").at.booth, 1250);
  assert.strictEqual(row(C.compare({ ...base, saved: { show: { booth: 5000, boothSales: 0 } } }), "show").at.booth, 5000);
  assert.strictEqual(row(C.compare(base), "show").at.booth, 0);
});
test("a typed price is for this card only and wins over the starting share; no sold price means no starting price", () => {
  const r = C.compare({ ...base, prices: { offerup: 9000 } });
  assert.strictEqual(row(r, "offerup").price, 9000); assert.ok(row(r, "offerup").typed); assert.strictEqual(row(r, "fb").price, 7380);
  const none = C.compare({ ...base, ref: null });
  assert.ok(none.rows.every((x) => x.price == null && x.profit == null)); assert.strictEqual(none.best, null);
  assert.strictEqual(row(none, "fb").breakEven, 7000);   // what to sell for still shows
});
test("best estimate: highest estimated profit among options the card may be listed on", () => {
  const r = C.compare(base);
  assert.strictEqual(r.best, "fb");                                  // fb, offerup and show tie at +$3.80; the first wins
  const g = C.compare({ ...base, prices: { vinted: 20000 } });       // Vinted is 'check rules' for a graded card, so never 'best'
  assert.strictEqual(g.best, "fb");
  const raw = C.compare({ ...base, item: { kind: "raw" }, prices: { vinted: 20000 } });
  assert.strictEqual(raw.best, "vinted");
});
test("Vinted eligibility by card type, from Vinted's own rules", () => {
  assert.ok(C.eligibility("vinted", { kind: "raw" }).ok);
  const g = C.eligibility("vinted", { kind: "graded" }); assert.ok(!g.ok && g.verify && /authenticity certificates/.test(g.text));
  assert.ok(C.eligibility("vinted", { kind: "sealed", name: "Prismatic Evolutions Booster Box" }).ok);
  assert.ok(C.eligibility("vinted", { kind: "sealed", name: "Prismatic Evolutions Elite Trainer Box" }).verify);
  assert.ok(C.eligibility("fb", { kind: "graded" }).ok);
});
test("eBay costs: the shipping step at $50 is respected; the fee above $7,500 drops to 2.35%; settings from the panel above flow in", () => {
  const e = (o) => row(C.compare({ ...base, ...o }), "ebay");
  const lo = e({ cost: 3000 });
  assert.ok(lo.breakEven < 5000 && C.netAt(lo.ch, lo.breakEven, { shipAuto }) >= 3000 && C.netAt(lo.ch, lo.breakEven - 1, { shipAuto }) < 3000);
  assert.strictEqual(C.platformFee(C.setup(C.CHANNELS[3]), 1000000), Math.round(40 + 750000 * 0.1325 + 325000 * 0.0235));
  const own = e({ ebay: { ship: 400, buyerTax: 0, feePct: 12.35 } });
  assert.strictEqual(own.at.fee, Math.round(40 + 8200 * 0.1235)); assert.strictEqual(own.at.ship, 400);
});
test("panel words: estimates, break-even and realized profit kept apart; no buy or sell calls", () => {
  const h = C.html(C.compare(base), { refLabel: "PSA 10, last 30 days" });
  for (const s of ["Where to sell? · estimates", "Estimated profit", "Break-even", "Realized profit", "Ledger → Sell", "Best estimate", "Check rules", "Facebook Marketplace", "OfferUp", "Card show", "Vinted", "Matches eBay at $64.42", "$73.80"]) assert.ok(h.includes(s), s);
  assert.ok(!/\bBUY\b|\bSELL candidate\b|\bHOLD\b/.test(h));
  assert.ok(/Checked Nov 17, 2026/.test(h));
});
console.log(`${n} channel comparison tests passed`);
