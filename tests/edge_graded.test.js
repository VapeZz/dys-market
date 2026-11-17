// Checks for the graded sold-price check (site/assets/edge-graded.js) and its one-grade lookup (edge-pkmn.js lookupGrade).
// Synthetic data only. No dependencies: node tests/edge_graded.test.js
const path = require("path"), assert = require("assert");
const G = require(path.join(__dirname, "../site/assets/edge-graded.js"));
const P = require(path.join(__dirname, "../site/assets/edge-pkmn.js"));
const T = 20000, iso = (d) => new Date(d * 864e5).toISOString().slice(0, 10);
let n = 0;
const test = async (name, fn) => { try { await fn(); n++; } catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; } };

// Edge's defaults: eBay trading cards 13.25% to $7,500 then 2.35%, $0.40 an order, on price + 7.5% buyer tax; $1 / $5 shipping, $0.50 supplies
const SELL = { feePct: 13.25, topPct: 2.35, topFrom: 750000, perOrder: 40, buyerTax: 7.5, ship: null, supplies: 50, shipAuto: (p) => p >= 5000 ? 500 : 100, breaks: [5000] };
const OPTS = { today: T, roi: 20, minProfit: 500 };
const sales = (label, list) => list.map(([age, cents, exact = 1]) => [T - age, cents, label, exact]);
const data = (list, o = {}) => ({ asOf: T, label: "PSA 10", source: "test", comps: sales("PSA 10", list), capped: [], oldestRead: null, ...o });
const HOLD = { cost: 7000, label: "PSA 10" };

(async () => {
  await test("fee: 13.25% of price + buyer tax, 2.35% above $7,500, plus the per-order fee", () => {
    assert.strictEqual(G.fee(SELL, 8200), Math.round(40 + 8815 * 0.1325));                 // $82 → base $88.15 → $11.68 + $0.40
    assert.strictEqual(G.fee(SELL, 8200), 1208);
    assert.strictEqual(G.fee(SELL, 1000000), Math.round(40 + 750000 * 0.1325 + 325000 * 0.0235));
    assert.strictEqual(G.fee(SELL, 0), 0);
    assert.strictEqual(G.fee({ ...SELL, buyerTax: 0 }, 10000), 1365);                        // matches edge-deal's fee test
  });
  await test("net, break-even and target for the Pikachu-shaped case ($70 paid, $82 typical)", () => {
    assert.strictEqual(G.netAt(SELL, 8200), 6442);                                          // the figure in the Nov 17 hand check
    const r = G.evaluate(data([[6, 8200], [7, 8000], [8, 8400], [9, 7900], [12, 8300], [20, 8200], [25, 8100]]), HOLD, SELL, OPTS);
    assert.strictEqual(r.typical, 8200);
    assert.strictEqual(r.at.net, 6442); assert.strictEqual(r.profit, -558);
    assert.strictEqual(r.breakEven, 8851); assert.strictEqual(r.target, 10483);             // $88.51 and $104.83, as by hand
    assert.strictEqual(r.verdict, "hold");
    assert.ok(G.netAt(SELL, r.breakEven) >= 7000 && G.netAt(SELL, r.breakEven - 1) < 7000);
    assert.ok(/not a prediction/.test(G.explain(r)) && /\$88\.51/.test(G.explain(r)));
  });
  await test("SELL candidate only when the typical price clears both the ROI target and the minimum profit", () => {
    const at = (px) => G.evaluate(data([[6, px], [7, px], [8, px], [10, px], [15, px], [40, px]]), HOLD, SELL, OPTS);
    const t = G.evaluate(data([[6, 1]]), HOLD, SELL, OPTS).target;
    assert.strictEqual(at(t).verdict, "sell");
    assert.strictEqual(at(t - 1).verdict, "hold");
    // a cheap card: 20% of $15 is $3, so the $5 minimum profit decides
    const cheap = { cost: 1500, label: "PSA 10" }, r = G.evaluate(data([[6, 2500], [7, 2500], [8, 2500], [9, 2500], [10, 2500]]), cheap, SELL, OPTS);
    assert.ok(r.profit >= 300 && r.profit < 500, String(r.profit)); assert.strictEqual(r.verdict, "hold");
  });
  await test("INSUFFICIENT DATA: too few, too few lately, too old, too scattered, or none", () => {
    const why = (list, o) => { const r = G.evaluate(data(list, o), HOLD, SELL, OPTS); return [r.verdict, r.reasons.map((x) => x.code).join(",")]; };
    assert.deepStrictEqual(why([[6, 9000], [7, 9000], [8, 9000], [9, 9000]]), ["insufficient", "evidence"]);
    assert.deepStrictEqual(why([[6, 9000], [7, 9000], [40, 9000], [50, 9000], [60, 9000]]), ["insufficient", "liquidity"]);
    assert.deepStrictEqual(why([[22, 9000], [23, 9000], [24, 9000], [25, 9000], [26, 9000]]), ["insufficient", "fresh"]);
    assert.deepStrictEqual(why([[6, 3000], [7, 4000], [8, 9000], [9, 15000], [10, 16000], [11, 20000]]), ["insufficient", "spread"]);
    const none = G.evaluate({ asOf: T, label: "PSA 10", comps: [] }, HOLD, SELL, OPTS);
    assert.strictEqual(none.verdict, "insufficient"); assert.strictEqual(none.breakEven, 8851);   // what to sell for still shows
    assert.ok(/won't guess/.test(G.explain(none)));
  });
  await test("only exact sales of the asked grade inside 90 days count: other grades, shared printings and the future are out", () => {
    const d = data([[6, 8200], [7, 8000], [8, 8400], [9, 7900], [12, 8300], [10, 99999, 0], [95, 1], [-1, 99999]]);
    d.comps.push([T - 6, 2667, "raw", 1], [T - 6, 4000, "PSA 9", 1]);
    const s = G.stats(d, "PSA 10", T);
    assert.deepStrictEqual([s.n14, s.n30, s.n90, s.inexact], [5, 5, 5, 1]);
    assert.strictEqual(s.m30, 8200); assert.strictEqual(s.lo, 7900); assert.strictEqual(s.hi, 8400);
  });
  await test("medians, nearest-rank quartiles, 14/30/90 windows and weekly blocks", () => {
    const s = G.stats(data([[1, 100], [3, 300], [8, 200], [13, 400], [15, 500], [29, 600], [31, 700], [80, 800]]), "PSA 10", T);
    assert.deepStrictEqual([s.n14, s.n30, s.n90], [4, 6, 8]);
    assert.deepStrictEqual([s.m14, s.m30, s.m90], [250, 350, 450]);
    assert.deepStrictEqual([s.q1, s.q3], [200, 500]);
    assert.deepStrictEqual(s.weeks.map((w) => [w.n, w.m]), [[2, 200], [2, 300], [1, 500], [0, null]]);
    assert.strictEqual(s.saleAge, 1);
  });
  await test("lately: last 14 days vs the 16 before, described not forecast; needs 3 in each half", () => {
    const s = G.stats(data([[6, 7500], [8, 7400], [10, 7600], [16, 8500], [20, 8400], [25, 8600]]), "PSA 10", T);
    assert.strictEqual(s.trend.word, "lower"); assert.strictEqual(s.trend.now, 7500); assert.strictEqual(s.trend.before, 8500);
    assert.ok(/already happened/.test(G.trendText(s)));
    assert.strictEqual(G.stats(data([[6, 7500], [8, 7400], [16, 8500], [20, 8400], [25, 8600]]), "PSA 10", T).trend, null);
    assert.strictEqual(G.stats(data([[6, 8000], [8, 8100], [10, 8000], [16, 8300], [20, 8400], [25, 8300]]), "PSA 10", T).trend.word, "steady");
  });
  await test("capped reads: counts marked as lower bounds, typical price from the newest sales read, no trend across the gap", () => {
    const d = data([[6, 8000], [7, 8100], [8, 8200], [9, 8300], [10, 8400]], { capped: ["PSA 10"], oldestRead: T - 10 });
    const r = G.evaluate(d, HOLD, SELL, OPTS);
    assert.ok(!r.s.full30 && r.s.capped); assert.strictEqual(r.typical, 8200); assert.strictEqual(r.s.trend, null);
    assert.ok(/newest 5 sales \(11 days/.test(r.basis));
    const h = G.html(r, SELL, {}); assert.ok(/5\+ sold in 30 days/.test(h));
  });
  await test("editable costs change the numbers: a fixed shipping amount, no buyer tax, a different fee", () => {
    const d = data([[6, 8200], [7, 8000], [8, 8400], [9, 7900], [12, 8300]]);
    const r = G.evaluate(d, HOLD, { ...SELL, ship: 450, buyerTax: 0, feePct: 12.35, supplies: 0 }, OPTS);
    assert.strictEqual(r.at.fee, Math.round(40 + 8200 * 0.1235)); assert.strictEqual(r.at.ship, 450);
    assert.strictEqual(r.at.net, 8200 - r.at.fee - 450);
    assert.ok(G.netAt({ ...SELL, ship: 450, buyerTax: 0, feePct: 12.35, supplies: 0 }, r.breakEven) >= 7000);
  });
  await test("break-even search handles the shipping step at $50 (a lower band answer wins)", () => {
    const low = { cost: 3000, label: "PSA 10" };
    const be = G.lowestPrice(SELL, (n) => n >= low.cost);
    assert.ok(be < 5000 && G.netAt(SELL, be) >= 3000 && G.netAt(SELL, be - 1) < 3000);
    // a cost that needs more than $49.99 even with $1 shipping lands above $50 with $5 shipping
    const be2 = G.lowestPrice(SELL, (n) => n >= 4100);
    assert.ok(be2 >= 5000 && G.netAt(SELL, be2) >= 4100 && G.netAt(SELL, be2 - 1) < 4100);
  });
  await test("the panel shows the call, the numbers and the plain explanation", () => {
    const r = G.evaluate(data([[6, 8200], [7, 8000], [8, 8400], [9, 7900], [12, 8300], [20, 8200], [25, 8100]]), HOLD, SELL, OPTS);
    const h = G.html(r, SELL, { canLoad: true });
    for (const s of ["HOLD", "$82.00", "$64.42", "−$5.58", "$88.51", "$104.83", "Only PSA 10 sales", "Selling costs", "Save as my defaults", "not financial advice"]) assert.ok(h.includes(s), s);
    assert.ok(!/PASS|BUY/.test(h));
  });

  /* ---------- the one-grade lookup against a fake relay ---------- */
  const sale = (age, price, o = {}) => ({ sold_at: iso(T - age), price, currency: "USD", attribution: "exact", variant: "Normal", title: "Pikachu 020/M-P PSA 10 McDonald's", ...o });
  function relay(routes) {
    const log = [];
    const fetch = async (url, opts) => {
      log.push({ url, pass: opts.headers["X-Edge-Pass"] });
      const u = new URL(url), cur = u.searchParams.get("cursor");
      const key = u.pathname + (u.searchParams.get("graded") ? `?${u.searchParams.get("grader")}${u.searchParams.get("grade")}${cur ? "@" + cur : ""}` : "");
      const [status, body] = routes[key] || routes[u.pathname] || [404, {}];
      return { status, json: async () => body, headers: { get: (h) => h === "x-credits-charged" ? String((body.data && body.data.length) || 1) : null } };
    };
    return { fetch, log };
  }
  const ITEM = { id: 649586, n: "Pikachu - 020/M-P" };
  const cfg = (r) => ({ relay: "https://relay.example", pass: "secret", fetch: r.fetch, today: T });
  await test("lookupGrade asks only for the one grade, keeps the right printing, drops other grades, lots and shared rows", async () => {
    const r = relay({ "/v1/cards": [200, { data: [{ id: "pk-9" }] }],
      "/v1/cards/pk-9/listings/ebay?PSA10": [200, { data: [sale(6, 82), sale(7, 80), sale(8, 75, { title: "Pikachu 020/M-P PSA 9 MINT" }), sale(9, 70, { title: "PSA 10 Pikachu lot of 3" }),
        sale(10, 300, { variant: "Holofoil" }), sale(11, 79, { attribution: "shared" }), sale(12, 84, { title: "CGC 10 Pikachu McDonalds" }), sale(13, 85, { title: "Pikachu PSA GEM MINT 10 M-P" }), sale(14, 90, { title: "" })],
        pagination: { has_more: false } }] });
    const res = await P.lookupGrade(ITEM, { grader: "psa", grade: "10" }, cfg(r));
    assert.ok(res.ok); assert.strictEqual(res.data.label, "PSA 10");
    assert.deepStrictEqual(res.data.comps.map((c) => [T - c[0], c[1], c[2], c[3]]).sort((a, b) => a[0] - b[0]),
      [[6, 8200, "PSA 10", 1], [7, 8000, "PSA 10", 1], [11, 7900, "PSA 10", 0], [13, 8500, "PSA 10", 1], [14, 9000, "PSA 10", 1]]);
    assert.deepStrictEqual([res.meta.otherGrade, res.meta.lot, res.meta.otherPrinting], [2, 1, 1]);
    const urls = r.log.map((x) => x.url).filter((u) => /listings/.test(u));
    assert.ok(urls.every((u) => /graded=true/.test(u) && /grader=PSA/.test(u) && /grade=10/.test(u)), "never asks for raw or another grade");
    assert.ok(r.log.every((x) => x.pass === "secret"));
  });
  await test("lookupGrade reads at most 8 pages and marks the read as capped; stops at 90 days", async () => {
    const page = (k) => [200, { data: Array.from({ length: 20 }, (_, i) => sale(6 + k, 80 + i)), pagination: { has_more: true, next_cursor: `p${k + 1}` } }];
    const routes = { "/v1/cards": [200, { data: [{ id: "pk-9" }] }], "/v1/cards/pk-9/listings/ebay?PSA10": page(0) };
    for (let k = 1; k < 12; k++) routes[`/v1/cards/pk-9/listings/ebay?PSA10@p${k}`] = page(k);
    const r = relay(routes), res = await P.lookupGrade(ITEM, { grader: "PSA", grade: "10" }, cfg(r));
    assert.strictEqual(r.log.filter((x) => /listings/.test(x.url)).length, 8);
    assert.deepStrictEqual(res.data.capped, ["PSA 10"]); assert.strictEqual(res.data.oldestRead, T - 13);
    assert.strictEqual(res.meta.credits, 1 + 160);
    const old = relay({ "/v1/cards": [200, { data: [{ id: "pk-9" }] }], "/v1/cards/pk-9/listings/ebay?PSA10": [200, { data: [sale(10, 80), sale(95, 70)], pagination: { has_more: true, next_cursor: "x" } }] });
    const r2 = await P.lookupGrade(ITEM, { grader: "PSA", grade: "10" }, cfg(old));
    assert.strictEqual(old.log.length, 2); assert.strictEqual(r2.data.comps.length, 1); assert.deepStrictEqual(r2.data.capped, []);
  });
  await test("unsupported grader or grade, not set up, not found and errors are answered, never guessed", async () => {
    const r = relay({});
    assert.strictEqual((await P.lookupGrade(ITEM, { grader: "CGC", grade: "10" }, cfg(r))).reason, "unsupported");
    assert.strictEqual((await P.lookupGrade(ITEM, { grader: "PSA", grade: "" }, cfg(r))).reason, "unsupported");
    assert.strictEqual(r.log.length, 0, "no call for an unsupported grade");
    assert.strictEqual((await P.lookupGrade(ITEM, { grader: "PSA", grade: "10" }, { today: T })).reason, "not-set-up");
    assert.strictEqual((await P.lookupGrade(ITEM, { grader: "PSA", grade: "10" }, cfg(relay({ "/v1/cards": [200, { data: [] }] })))).reason, "not-found");
    assert.strictEqual((await P.lookupGrade(ITEM, { grader: "PSA", grade: "10" }, cfg(relay({ "/v1/cards": [403, {}] })))).reason, "denied");
    assert.strictEqual((await P.lookupGrade(ITEM, { grader: "PSA", grade: "10" }, cfg(relay({ "/v1/cards": [200, { data: [{ id: "pk-9" }] }], "/v1/cards/pk-9/listings/ebay?PSA10": [500, {}] })))).reason, "error");
  });
  await test("getGrade caches per card, printing and grade in memory only; a fresh read asks again", async () => {
    const r = relay({ "/v1/cards": [200, { data: [{ id: "pk-9" }] }], "/v1/cards/pk-9/listings/ebay?PSA10": [200, { data: [sale(6, 82)], pagination: { has_more: false } }], "/v1/cards/pk-9/listings/ebay?PSA9": [200, { data: [sale(6, 40, { title: "Pikachu PSA 9" })], pagination: { has_more: false } }] });
    const c = cfg(r);
    await P.getGrade(ITEM, { grader: "PSA", grade: "10" }, c); await P.getGrade(ITEM, { grader: "PSA", grade: "10" }, c);
    assert.strictEqual(r.log.length, 2);
    const nine = await P.getGrade(ITEM, { grader: "PSA", grade: "9" }, c);
    assert.strictEqual(nine.data.comps[0][2], "PSA 9"); assert.strictEqual(r.log.length, 4);
    await P.getGrade(ITEM, { grader: "PSA", grade: "10" }, c, true); assert.strictEqual(r.log.length, 6);
  });
  await test("titleCheck", () => {
    const t = (s) => P.titleCheck(s, "PSA", "10");
    assert.deepStrictEqual(["Pikachu PSA 10", "PSA GEM MT 10 Pikachu", "Pikachu 020/M-P McDonald's 2021", "", "Pokemon Cards PSA 10 Pikachu"].map(t), ["ok", "ok", "ok", "ok", "ok"]);
    assert.deepStrictEqual(["Pikachu PSA 9", "Pikachu BGS 10", "Beckett 9.5 Pikachu", "PSA 10 lot", "2 cards PSA 10", "PSA 10 + PSA 9 pair"].map(t), ["other", "other", "other", "lot", "lot", "other"]);
  });

  console.log(`${n} graded check tests passed`);
})();
