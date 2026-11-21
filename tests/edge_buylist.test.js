// Checks for the card-show buy list (site/assets/edge-buylist.js) with the real Deal check engine on synthetic sales,
// and for the service worker's weak-signal rule for Edge (site/sw.js). No dependencies: node tests/edge_buylist.test.js
const path = require("path"), assert = require("assert"), fs = require("fs"), vm = require("vm");
const B = require(path.join(__dirname, "../site/assets/edge-buylist.js"));
const D = require(path.join(__dirname, "../site/assets/edge-deal.js"));
const Y = require(path.join(__dirname, "../tools/deal/synth.js"));
const T = Y.DAY0, NOW = T * 864e5 + 12 * 36e5, H = 36e5;
let n = 0;
const test = async (name, fn) => { try { await fn(); n++; } catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; } };
const AGES = [3, 5, 9, 12, 15, 20, 25, 40, 50, 60, 70, 80];
const flat = (px, ages = AGES) => ages.map((a) => [T - a, px, "raw", 1]);
const item = (o = {}) => ({ id: 1, n: "Test card (Holofoil)", name: "Test card", t: "c", tcg: 4000, tcgDay: T, ...o });
const data = (comps) => ({ asOf: T, source: "test", comps });
const cfg = (o = {}) => ({ ...Y.cfg(), budget: { limit: 7500, reserve: 10000, cash: null }, ...o });
const memLS = () => { const m = new Map(); return { getItem: (k) => m.has(k) ? m.get(k) : null, setItem: (k, v) => m.set(k, String(v)), _m: m }; };

(async () => {
  await test("steps and bands round down, so a saved number never exceeds the exact one", () => {
    assert.deepStrictEqual([1999, 2000, 2649, 4999, 5000, 7499].map(B.floorTo), [1900, 2000, 2500, 4750, 5000, 7000]);
    assert.strictEqual(B.floorTo(0), null); assert.strictEqual(B.floorTo(99), 0);   // under $1: nothing to offer
    assert.deepStrictEqual(B.resaleBand(3350), [3000, 4000]); assert.deepStrictEqual(B.resaleBand(1849), [1500, 2000]); assert.deepStrictEqual(B.resaleBand(12345), [10000, 12500]);
    assert.deepStrictEqual([0, 2, 5, 9, 20].map(B.paceBand), ["0", "1–2", "3–6", "7–14", "15+"]);
    assert.strictEqual(B.opening(2700), 2100); assert.strictEqual(B.opening(500), 400); assert.strictEqual(B.opening(100), null); assert.strictEqual(B.opening(null), null);
    for (const w of [300, 1000, 2250, 2700, 7000]) assert.ok(B.opening(w) < w && B.opening(w) % 100 === 0, `open < walk for ${w}`);
  });

  await test("derive: walk-away per condition is the engine's max floored to its step, and clears every rule at the engine", () => {
    const it = item(), d = data(flat(4000)), c = cfg();
    const est = B.derive(D, it, d, c, NOW);
    assert.ok(est.walk.NM && est.walk.LP && est.walk.MP && est.walk.NM > est.walk.LP && est.walk.LP > est.walk.MP, JSON.stringify(est.walk));
    const noRes = { ...c, budget: { limit: 7500 } };
    for (const cond of B.CONDS) {
      const exact = D.check(it, d, { ask: 100, cond, shipIn: 0, taxIn: 0 }, noRes).routes.flip.max;
      const w = est.walk[cond];
      assert.ok(w <= exact && w > exact - B.step(exact), `${cond}: walk ${w} vs exact ${exact}`);
      const at = D.check(it, d, { ask: w, cond, shipIn: 0, taxIn: 0 }, { ...c, budget: { limit: 7500, reserve: 10000, cash: 100000 } });
      assert.strictEqual(at.verdict, "buy", `${cond}: the engine calls the walk-away a BUY with cash`);
      const F = at.routes.flip; assert.ok(F.profit >= 500 && F.profit * 100 >= F.cost * 20 && F.cost <= 7500);
    }
    assert.strictEqual(est.grade, D.check(it, d, { ask: 100, cond: "NM", shipIn: 0, taxIn: 0 }, noRes).confidence); assert.ok(/^[A-D]$/.test(est.grade)); assert.strictEqual(est.pace, "7–14"); assert.deepStrictEqual(est.resale, [4000, 5000]);
    assert.strictEqual(est.issue, null); assert.strictEqual(est.at, NOW); assert.strictEqual(est.tcg, 4000);
  });

  await test("derive: the $75 limit caps the walk-away; thin, scattered, disagreeing or falling cards get no walk-away and a reason", () => {
    const big = B.derive(D, item({ tcg: 30000 }), data(flat(30000)), cfg(), NOW);
    assert.ok(big.walk.NM && big.walk.NM <= 7500, `limit: ${big.walk.NM}`);
    const thin = B.derive(D, item(), data(flat(4000, [5, 40])), cfg(), NOW);
    assert.ok(!thin.walk.NM && ["evidence", "liquidity", "fresh"].includes(thin.issue), JSON.stringify(thin));
    const disagree = B.derive(D, item({ tcg: 9000 }), data(flat(4000)), cfg(), NOW);
    assert.ok(!disagree.walk.NM && disagree.issue === "agree", JSON.stringify(disagree));
    const none = B.derive(D, item(), data([]), cfg(), NOW); assert.strictEqual(none.issue, "no-data"); assert.deepStrictEqual(none.walk, {});
    const cheap = B.derive(D, item({ tcg: 900 }), data(flat(900)), cfg(), NOW);
    assert.ok(!cheap.walk.NM && cheap.issue, JSON.stringify(cheap));
    for (const e of [thin, disagree, none, cheap]) assert.ok(B.ISSUE[e.issue], `fixed text for ${e.issue}`);
  });

  await test("saved form: only our own rounded numbers; no sold price, median, comp or exact max is stored", () => {
    const ls = memLS(), st = B.Store(ls, () => NOW), d = data(flat(4137));
    st.add({ k: "1|Test card (Holofoil)", id: 1, g: 9, n: "Test card (Holofoil)", setN: "Set", t: "c", junk: "x" });
    const est = B.derive(D, item({ tcg: 4137 }), d, cfg(), NOW);
    st.setEst("1|Test card (Holofoil)", { ...est, comps: d.comps, median: 4137, exit: 4137 });
    const raw = ls.getItem(B.KEY), j = JSON.parse(raw), x = j.items[0];
    assert.deepStrictEqual(Object.keys(x).sort(), ["added", "cond", "est", "g", "id", "k", "n", "r", "setN", "t"]);
    assert.ok(Object.keys(x.est).every((k) => B.EST_KEYS.includes(k)), Object.keys(x.est).join());
    assert.ok(!/4137/.test(JSON.stringify(x.est.walk)) && !/4137/.test(JSON.stringify(x.est.resale)) && !/comps|median|exit/.test(raw), raw);
    const exact = D.check(item({ tcg: 4137 }), d, { ask: 100, cond: "NM", shipIn: 0, taxIn: 0 }, { ...cfg(), budget: { limit: 7500 } }).routes.flip.max;
    assert.notStrictEqual(x.est.walk.NM, exact, "the exact max is not stored");
    assert.ok(Object.values(x.est.walk).every((w) => w % B.step(w) === 0));
  });

  await test("store: survives a reload, keeps 60 cards at most, drops estimates after 7 days but keeps the cards", () => {
    const ls = memLS(); let now = NOW; const st = B.Store(ls, () => now);
    for (let i = 0; i < 65; i++) st.add({ k: `k${i}`, id: i + 1, g: 1, n: `Card ${i}` });
    assert.strictEqual(st.all().length, 60); assert.strictEqual(st.add({ k: "k0", id: 1, g: 1, n: "Card 0" }), false);
    st.setEst("k0", { at: now, walk: { NM: 2000 }, grade: "A" }); st.setCond("k1", "LP");
    const again = B.Store(ls, () => now); assert.strictEqual(again.get("k0").est.walk.NM, 2000); assert.strictEqual(again.get("k1").cond, "LP");
    now = NOW + 8 * 24 * H; const later = B.Store(ls, () => now);
    assert.strictEqual(later.get("k0").est, undefined); assert.strictEqual(later.all().length, 60);
    later.remove("k5"); assert.strictEqual(B.Store(ls, () => now).all().length, 59);
    ls.setItem(B.KEY, "{bad json"); assert.deepStrictEqual(B.Store(ls, () => now).all(), []);
  });

  await test("age: fresh under a day, stale to 3 days, then too old to use", () => {
    const e = (h) => ({ at: NOW - h * H });
    assert.deepStrictEqual([0.5, 23.9, 24, 71, 72, 200].map((h) => B.ageState(e(h), NOW)), ["fresh", "fresh", "stale", "stale", "expired", "expired"]);
    assert.strictEqual(B.ageState(null, NOW), "none"); assert.strictEqual(B.ageState({ at: NOW + 2 * H }, NOW), "expired");
    assert.strictEqual(B.ageTxt(e(0.2), NOW), "checked under an hour ago"); assert.strictEqual(B.ageTxt(e(5), NOW), "checked 5 h ago"); assert.strictEqual(B.ageTxt(e(50), NOW), "checked 2 days ago");
  });

  await test("at the table: fits, over, limit, reserve, cash missing, stale and expired; never a BUY", () => {
    const c = cfg(), est = { at: NOW - 2 * H, tcg: 4000, grade: "A", pace: "7–14", resale: [4000, 5000], walk: { NM: 2700, LP: 2200 }, issue: null };
    const r = (ask, cash, e = est, cond = "NM") => B.atTable(D, e, cond, ask, cash, c, "c", NOW);
    assert.strictEqual(r(2500, 30000).result, "fits"); assert.ok(/Verify/.test(r(2500, 30000).text));
    assert.strictEqual(r(2800, 30000).result, "over");
    assert.strictEqual(r(2500, null).result, "need-cash"); assert.strictEqual(r(2500, 12000).result, "reserve");
    assert.strictEqual(r(0, 30000).result, "need-ask");
    assert.strictEqual(r(2100, 30000, est, "LP").result, "fits"); assert.strictEqual(r(2300, 30000, est, "LP").result, "over");
    assert.strictEqual(r(1000, 30000, est, "MP").result, "no-walk"); assert.strictEqual(r(1000, 30000, est, "HP").result, "no-walk");
    const bigEst = { ...est, walk: { NM: 9000 } };   // an estimate saved before a limit change: the limit still applies
    assert.strictEqual(r(8000, 50000, bigEst).result, "limit");
    const stale = { ...est, at: NOW - 30 * H }; assert.strictEqual(r(2500, 30000, stale).result, "fits"); assert.ok(/stale/.test(r(2500, 30000, stale).text));
    const old = { ...est, at: NOW - 80 * H }; assert.strictEqual(r(2500, 30000, old).result, "expired"); assert.strictEqual(r(2500, 30000, old).walk, null);
    assert.strictEqual(r(2500, 30000, null).result, "none");
    const p = r(2500, 30000); assert.ok(p.profit[0] < p.profit[1] && p.roi[0] < p.roi[1]);
    assert.strictEqual(p.profit[0], D.netSale(4000, "c", c) - 2500); assert.strictEqual(p.cost, 2500);
    for (const x of [r(2500, 30000), r(2800, 30000), r(2500, null), r(2500, 30000, stale), r(2500, 30000, old)]) assert.ok(!/\bBUY\b/.test(x.text) && x.result !== "buy", x.text);
  });

  await test("plan: oldest information first, only cards not checked today, as many as the budget covers", () => {
    const items = [{ k: "a", est: { at: NOW - 2 * H } }, { k: "b" }, { k: "c", est: { at: NOW - 30 * H } }, { k: "d", est: { at: NOW - 90 * H } }];
    const p = B.plan(items, 250, NOW);
    assert.deepStrictEqual(p.need.map((x) => x.k), ["b", "d", "c"]); assert.deepStrictEqual(p.take.map((x) => x.k), ["b", "d"]);
    assert.strictEqual(B.plan(items, 100, NOW).take.length, 0); assert.strictEqual(B.plan(items, 5000, NOW).take.length, 3);
  });

  await test("service worker: Edge answers from its saved copy after 3.5 s of no network; the rest of the site stays network-first", async () => {
    const src = fs.readFileSync(path.join(__dirname, "../site/sw.js"), "utf8");
    let handler = null, netDelay = 0, netOk = true, store = new Map();
    const resp = (body) => ({ ok: true, body, clone() { return resp(body); } });
    const ctx = { self: { addEventListener: (t, f) => { if (t === "fetch") handler = f; }, location: { origin: "https://m.test" }, skipWaiting() {}, clients: { claim() {} } },
      caches: { match: async (req) => store.get(req.url) || undefined, open: async () => ({ put: async (req, r) => store.set(req.url, r) }), keys: async () => [], delete: async () => true },
      fetch: (req) => new Promise((res, rej) => setTimeout(() => netOk ? res(resp("net:" + req.url)) : rej(new Error("offline")), netDelay)), URL, Response: { error: () => ({ error: true }) }, setTimeout, Promise };
    vm.runInNewContext(src, ctx);
    const ask = (url, referrer = "") => new Promise((done) => handler({ request: { url, method: "GET", referrer, mode: "cors" }, respondWith: (p) => Promise.resolve(p).then(done) }));
    store.set("https://m.test/data/meta.json", resp("saved"));
    netDelay = 10; assert.strictEqual((await ask("https://m.test/data/meta.json", "https://m.test/edge/")).body, "net:https://m.test/data/meta.json");
    store.set("https://m.test/data/meta.json", resp("saved"));
    netDelay = 8000; let t0 = Date.now(); const slow = await ask("https://m.test/data/meta.json", "https://m.test/edge/");
    assert.strictEqual(slow.body, "saved"); assert.ok(Date.now() - t0 < 5000 && Date.now() - t0 >= 3400, `${Date.now() - t0} ms`);
    netDelay = 10; netOk = false; assert.strictEqual((await ask("https://m.test/edge/nothing-saved.js")).error, true);   // offline, nothing saved: an error, not a hang
    store.set("https://m.test/edge/", resp("shell")); assert.strictEqual((await ask("https://m.test/edge/")).body, "shell");
    netOk = true; netDelay = 300; store.set("https://m.test/index.html", resp("old"));
    t0 = Date.now(); assert.strictEqual((await ask("https://m.test/index.html", "https://m.test/")).body, "net:https://m.test/index.html"); assert.ok(Date.now() - t0 >= 290, "site pages wait for the network");
  });

  console.log(`${n} buy list tests passed${process.exitCode ? " (with failures above)" : ""}`);
})();
