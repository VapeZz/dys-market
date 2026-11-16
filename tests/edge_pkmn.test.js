// Checks for the PkmnPrices adapter (site/assets/edge-pkmn.js) against a mocked relay. Response shapes follow the
// Nov 14 read-only probe (tools/pkmnprices_probe.py on branch pkmn-probe). Every row here is synthetic.
// No dependencies: node tests/edge_pkmn.test.js
const path = require("path"), assert = require("assert");
const P = require(path.join(__dirname, "../site/assets/edge-pkmn.js"));
const D = require(path.join(__dirname, "../site/assets/edge-deal.js"));
const Y = require(path.join(__dirname, "../tools/deal/synth.js"));
const T = Y.DAY0, iso = (d) => new Date(d * 864e5).toISOString().slice(0, 10);
let n = 0;
const test = async (name, fn) => { try { await fn(); n++; } catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; } };

/* a fake relay: routes → [status, body]; records every URL and header */
function relay(routes) {
  const log = [];
  const fetch = async (url, opts) => {
    log.push({ url, pass: opts.headers["X-Edge-Pass"] });
    const u = new URL(url), key = u.pathname + (u.searchParams.get("graded") ? `?${u.searchParams.get("graded")}${u.searchParams.get("grade") || ""}${u.searchParams.get("cursor") ? "@" + u.searchParams.get("cursor") : ""}` : "");
    const hit = routes[key] || routes[u.pathname];
    if (hit === "throw") throw new Error("offline");
    const [status, body] = hit || [404, { error: "not found" }];
    return { status, json: async () => body, headers: { get: (h) => h === "x-credits-charged" ? String((body && body.data && body.data.length) || 1) : null } };
  };
  return { fetch, log };
}
const sale = (age, price, o = {}) => ({ sold_at: iso(T - age), price, currency: "USD", attribution: "exact", sale_type: "auction", ...o });
const cfgFor = (r, o = {}) => ({ relay: "https://relay.example/", pass: "secret", fetch: r.fetch, today: T, ...o });
const CARD = { id: 610516, n: "Umbreon ex - 161/131 (Holofoil)", t: "c" };

const routes = () => ({
  "/v1/cards": [200, { data: [{ id: "pk-1", name: "Umbreon ex", number: "161" }] }],
  "/v1/cards/pk-1/listings/ebay?false": [200, { data: [sale(8, 950), sale(10, 990.5), sale(12, 1010, { attribution: "shared" }), sale(20, 980), sale(25, 1000, { currency: "EUR" }), sale(40, 1020), { price: 999, currency: "USD" }], pagination: { has_more: true, next_cursor: "c2" } }],
  "/v1/cards/pk-1/listings/ebay?false@c2": [200, { data: [sale(60, 1050), sale(95, 1100), sale(-2, 5000)], pagination: { has_more: true, next_cursor: "c3" } }],
  "/v1/cards/pk-1/listings/ebay?true10": [200, { data: [sale(9, 2600), sale(11, 2550), sale(30, 2500)], pagination: { has_more: false } }],
  "/v1/cards/pk-1/listings/ebay?true9": [200, { data: [], pagination: { has_more: false } }],
  "/v1/cards/pk-1/population": [200, { variants: [{ variant: "Normal", graders: { PSA: { total: 10, grades: { 10: 1 } } } }, { variant: "Holofoil", updated_at: iso(T - 20) + "T03:00:00Z", graders: { PSA: { total: 23218, grades: { 10: 6778, 9: 11397 } } } }] }],
});

(async () => {
  await test("a card: sold rows become comps; 90-day stop, currency, undated, future and shared rows handled", async () => {
    const r = relay(routes()), res = await P.lookup(CARD, cfgFor(r));
    assert.ok(res.ok);
    const raw = res.data.comps.filter((c) => c[2] === "raw");
    assert.deepStrictEqual(raw.map((c) => [T - c[0], c[1], c[3]]).sort((a, b) => a[0] - b[0]), [[8, 95000, 1], [10, 99050, 1], [12, 101000, 0], [20, 98000, 1], [40, 102000, 1], [60, 105000, 1]]);
    assert.strictEqual(res.data.comps.filter((c) => c[2] === "PSA 10").length, 3);
    assert.deepStrictEqual([res.meta.undated, res.meta.future, res.meta.otherCurrency], [1, 1, 1]);
    assert.ok(!r.log.some((x) => /cursor=c3/.test(x.url)), "stops once a page reaches 90 days back");
    assert.ok(r.log.every((x) => x.pass === "secret" && x.url.startsWith("https://relay.example/v1/")));
    assert.deepStrictEqual(res.data.pop, { total: 23218, g10: 6778, g9: 11397, asOf: T - 20 });     // the Holofoil printing, not Normal
    assert.strictEqual(res.data.asOf, T);
    assert.ok(/PkmnPrices/.test(res.data.source) && /8 days behind/.test(res.data.source));
    assert.strictEqual(res.meta.credits, 1 + 7 + 3 + 3 + 1 + 1);   // the mock charges rows returned, 1 for an answer without rows
  });
  await test("the comps feed the Deal check unchanged", async () => {
    const res = await P.lookup(CARD, cfgFor(relay(routes())));
    const ev = D.comps(res.data, "raw", T);
    assert.deepStrictEqual([ev.n90, ev.n30, ev.inexact], [5, 3, 1]);
    assert.strictEqual(ev.m90, 99050);
  });
  await test("page cap: more sales inside 90 days than read is flagged", async () => {
    const R = routes();
    R["/v1/cards/pk-1/listings/ebay?true10"] = [200, { data: [sale(9, 2600), sale(10, 2600)], pagination: { has_more: true, next_cursor: "x" } }];
    R["/v1/cards/pk-1/listings/ebay?true10@x"] = [200, { data: [sale(11, 2600)], pagination: { has_more: true, next_cursor: "y" } }];
    R["/v1/cards/pk-1/listings/ebay?true10@y"] = [200, { data: [sale(12, 2600)], pagination: { has_more: true, next_cursor: "z" } }];
    const res = await P.lookup(CARD, cfgFor(relay(R)));
    assert.deepStrictEqual(res.meta.capped, ["PSA 10"]);
    assert.strictEqual(res.data.comps.filter((c) => c[2] === "PSA 10").length, 4);
  });
  await test("not set up, offline, denied, not found, two matches", async () => {
    assert.strictEqual((await P.lookup(CARD, { relay: "" })).reason, "not-set-up");
    const R = routes(); R["/v1/cards"] = "throw";
    assert.strictEqual((await P.lookup(CARD, cfgFor(relay(R)))).reason, "network");
    const R2 = routes(); R2["/v1/cards"] = [401, "denied"];
    assert.strictEqual((await P.lookup(CARD, cfgFor(relay(R2)))).reason, "denied");
    const R3 = routes(); R3["/v1/cards"] = [200, { data: [] }];
    assert.strictEqual((await P.lookup(CARD, cfgFor(relay(R3)))).reason, "not-found");
    const R4 = routes(); R4["/v1/cards"] = [200, { data: [{ id: "a" }, { id: "b" }] }];
    const two = await P.lookup(CARD, cfgFor(relay(R4)));
    assert.ok(two.reason === "not-found" && /2 matches/.test(two.meta.errors[0]));
  });
  await test("a failed grade read leaves the others and says so", async () => {
    const R = routes(); R["/v1/cards/pk-1/listings/ebay?true9"] = [429, { error: "rate" }];
    const res = await P.lookup(CARD, cfgFor(relay(R)));
    assert.ok(res.ok && res.meta.errors.includes("PSA 9: HTTP 429") && res.data.comps.some((c) => c[2] === "raw"));
  });
  await test("sealed: found by name, matched on the TCGplayer id", async () => {
    const R = { "/v1/sealed": [200, { data: [{ id: "s-9", tcg_player_id: 1 }, { id: "s-1", tcg_player_id: 503313 }] }],
      "/v1/sealed/s-1/listings/ebay": [200, { data: [sale(9, 120), sale(15, 118)], pagination: {} }] };
    const r = relay(R), res = await P.lookup({ id: 503313, n: "Scarlet & Violet 151 Elite Trainer Box", t: "s" }, cfgFor(r));
    assert.ok(res.ok && res.data.comps.every((c) => c[2] === "sealed") && res.data.comps.length === 2 && res.data.pop === null);
    assert.ok(/name=Scarlet%20%26%20Violet%20151%20Elite%20Trainer%20Box/.test(r.log[0].url));
    const miss = await P.lookup({ id: 999, n: "Box", t: "s" }, cfgFor(relay(R)));
    assert.strictEqual(miss.reason, "not-found");
  });
  await test("memory cache: one read per item per page load; a failure is not kept; refresh reads again", async () => {
    P._mem.clear();
    const r = relay(routes()), cfg = cfgFor(r);
    await P.get(CARD, cfg); const calls = r.log.length;
    await P.get(CARD, cfg); assert.strictEqual(r.log.length, calls);
    await P.get(CARD, cfg, true); assert.strictEqual(r.log.length, calls * 2);
    const R = routes(); R["/v1/cards"] = [500, {}]; const r2 = relay(R);
    await P.get({ ...CARD, id: 1 }, cfgFor(r2)); await P.get({ ...CARD, id: 1 }, cfgFor(r2));
    assert.strictEqual(r2.log.length, 2);
  });
  await test("printing names and dates", () => {
    assert.deepStrictEqual(["A (1st Edition Holofoil)", "B (Reverse Holofoil)", "C (Holofoil)", "D"].map(P.variantOf), ["1st Edition Holofoil", "Reverse Holofoil", "Holofoil", "Normal"]);
    assert.strictEqual(P.dayOf("2026-11-16"), T); assert.strictEqual(P.dayOf("2026-11-16T23:59:00Z"), T); assert.strictEqual(P.dayOf("x"), null);
    assert.strictEqual(P.popOf({ variants: [{ variant: "Normal", graders: { PSA: { total: 5, grades: { 10: 1 } } } }] }, "Holofoil").total, 5);   // one printing only: use it
    assert.strictEqual(P.popOf({ variants: [{ variant: "A", graders: {} }, { variant: "B", graders: {} }] }, "Holofoil"), null);
  });
  console.log(`${n} PkmnPrices adapter tests passed${process.exitCode ? " (with failures above)" : ""}`);
})();
