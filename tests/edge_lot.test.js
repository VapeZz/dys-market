// Checks for binder / lot offers (site/assets/edge-lot.js) with the real Deal check engine and Buy list estimates on
// synthetic sales. Nothing real is called. No dependencies: node tests/edge_lot.test.js
const path = require("path"), assert = require("assert");
const L = require(path.join(__dirname, "../site/assets/edge-lot.js"));
const B = require(path.join(__dirname, "../site/assets/edge-buylist.js"));
const D = require(path.join(__dirname, "../site/assets/edge-deal.js"));
const Y = require(path.join(__dirname, "../tools/deal/synth.js"));
const T = Y.DAY0, NOW = T * 864e5 + 12 * 36e5, H = 36e5;
let n = 0;
const test = async (name, fn) => { try { await fn(); n++; } catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; } };
const AGES = [3, 5, 9, 12, 15, 20, 25, 40, 50, 60, 70, 80];
const flat = (px, ages = AGES) => ages.map((a) => [T - a, px, "raw", 1]);
const data = (comps) => ({ asOf: T, source: "test", comps });
const cfg = (o = {}) => ({ ...Y.cfg(), budget: { limit: 7500, reserve: 10000, cash: null }, ...o });
const withCash = (c, cash) => ({ ...c, budget: { ...c.budget, cash } });
const memLS = () => { const m = new Map(); return { getItem: (k) => m.has(k) ? m.get(k) : null, setItem: (k, v) => m.set(k, String(v)), _m: m }; };
let seq = 0;
const line = (o = {}) => { const id = o.id || 1000 + ++seq, nm = o.n || `Card ${id} (Holofoil)`; return { l: `l${id}`, k: `${id}|${nm}`, id, g: 1, n: nm, setN: "Set", t: "c", cond: "NM", qty: 1, tcg: o.px || 4000, tcgDay: T, ...o, px: undefined }; };
// a lot read live: k -> { data }
const liveMap = (pairs) => { const m = new Map(pairs); return (k) => m.get(k) || null; };
const unitOf = (px, cond = "NM", c = cfg()) => D.check({ id: 1, n: "x", t: "c", tcg: px, tcgDay: T }, data(flat(px)), { ask: 100, cond, shipIn: 0, taxIn: 0 }, { ...c, budget: null }).routes.flip.proceeds;

(async () => {
  await test("a card's value is the Deal check's net per copy at its conservative exit, times the copies counted", () => {
    const a = line({ px: 4000, qty: 2 }), b = line({ px: 3000, cond: "LP" });
    const R = L.evaluate(D, B, { askMode: "total", total: 4000, lines: [a, b] }, liveMap([[a.k, { data: data(flat(4000)) }], [b.k, { data: data(flat(3000)) }]]), withCash(cfg(), 50000), NOW);
    assert.strictEqual(R.mode, "live");
    assert.strictEqual(R.rows[0].unit, unitOf(4000)); assert.strictEqual(R.rows[0].counted, 2);
    assert.strictEqual(R.rows[1].unit, unitOf(3000, "LP"));
    assert.strictEqual(R.value, unitOf(4000) * 2 + unitOf(3000, "LP"));
    assert.strictEqual(R.cost, 4000); assert.strictEqual(R.profit, R.value - 4000);
    assert.strictEqual(R.result, "buy", R.text);
    assert.deepStrictEqual(R.top.map((t) => t.l), [a.l, b.l]); assert.ok(Math.abs(R.top[0].share + R.top[1].share - 1) < 1e-9);
  });

  await test("max safe offer = the engine's max for the lot's value inside limit and reserve; walk-away floored; opening under it", () => {
    const a = line({ px: 4000, qty: 2 }), b = line({ px: 3000 });
    const lot = { askMode: "total", total: 2000, lines: [a, b] }, live = liveMap([[a.k, { data: data(flat(4000)) }], [b.k, { data: data(flat(3000)) }]]);
    const R = L.evaluate(D, B, lot, live, withCash(cfg(), 100000), NOW);
    const exact = D.maxAsk(R.value, { taxIn: 0, shipIn: 0 }, 20, 500, 7500);
    assert.strictEqual(R.max, exact); assert.strictEqual(R.walk, B.floorTo(exact)); assert.ok(R.walk <= R.max && R.open < R.walk);
    // at the walk-away the lot itself is a BUY; one cent over the exact max it isn't (margin or limit)
    const at = L.evaluate(D, B, { ...lot, total: R.walk }, live, withCash(cfg(), 100000), NOW); assert.strictEqual(at.result, "buy");
    const over = L.evaluate(D, B, { ...lot, total: R.max + 1 }, live, withCash(cfg(), 100000), NOW); assert.notStrictEqual(over.result, "buy");
    // little cash: the reserve caps the offer
    const tight = L.evaluate(D, B, lot, live, withCash(cfg(), 12500), NOW);
    assert.strictEqual(tight.max, Math.min(exact, 2500)); assert.strictEqual(tight.capBy, "reserve");
  });

  await test("a bundle can't bypass the rules: limit on the whole lot, reserve on the whole lot, cash needed, $5 and 20% on the lot", () => {
    const a = line({ px: 5000 }), b = line({ px: 5000 }), c = line({ px: 5000 });
    const live = liveMap([[a.k, { data: data(flat(5000)) }], [b.k, { data: data(flat(5000)) }], [c.k, { data: data(flat(5000)) }]]);
    const lot = { askMode: "each", lines: [{ ...a, ask: 2900 }, { ...b, ask: 2900 }, { ...c, ask: 2900 }] };   // each card alone is cheap; together $87
    const R = L.evaluate(D, B, lot, live, withCash(cfg(), 100000), NOW);
    assert.ok(R.marginOk); assert.strictEqual(R.cost, 8700); assert.strictEqual(R.result, "limit");
    assert.ok(R.max <= 7500 && R.capBy === "limit");
    assert.strictEqual(L.evaluate(D, B, { ...lot, lines: lot.lines.slice(0, 2) }, live, cfg(), NOW).result, "need-cash");
    assert.strictEqual(L.evaluate(D, B, { ...lot, lines: lot.lines.slice(0, 2) }, live, withCash(cfg(), 15000), NOW).result, "reserve");
    assert.strictEqual(L.evaluate(D, B, { ...lot, lines: lot.lines.slice(0, 2) }, live, withCash(cfg(), 100000), NOW).result, "buy");
    // thin margin on the lot: no BUY even if one card looks great alone
    const thin = L.evaluate(D, B, { askMode: "total", total: unitOf(5000) * 3 - 300, lines: [a, b, c] }, live, withCash(cfg(), 100000), NOW);
    assert.strictEqual(thin.result, "over");
  });

  await test("weak evidence, missing prices, under $20, unconfirmed printings: flagged and counted at $0, never assumed", () => {
    const good = line({ px: 4000 }), thinL = line({ px: 4000 }), none = line({ px: 4000 }), cheap = line({ px: 900 }), pr = line({ px: 4000, alts: ["Reverse Holofoil"] }), unk = line({ px: 4000 });
    const live = liveMap([[good.k, { data: data(flat(4000)) }], [thinL.k, { data: data(flat(4000, [3, 40, 60])) }], [none.k, { data: data([]) }],
      [cheap.k, { data: data(flat(900)) }], [pr.k, { data: data(flat(4000)) }]]);
    const R = L.evaluate(D, B, { askMode: "total", total: 1500, lines: [good, thinL, none, cheap, { ...pr, prOk: false }, unk] }, live, withCash(cfg(), 100000), NOW);
    const by = (x) => R.rows.find((r) => r.l === x.l);
    assert.deepStrictEqual(by(thinL).flags, ["evidence"]); assert.ok(/needs 5/.test(by(thinL).why));
    assert.deepStrictEqual(by(none).flags, ["missing"]); assert.deepStrictEqual(by(cheap).flags, ["scope"]);
    assert.deepStrictEqual(by(pr).flags, ["printing"]); assert.deepStrictEqual(by(unk).flags, ["not-checked"]);
    for (const x of [thinL, none, cheap, pr, unk]) assert.strictEqual(by(x).value, 0);
    assert.strictEqual(R.value, unitOf(4000));
    assert.strictEqual(R.mode, "estimate", "an unchecked card keeps the lot from being live");
    assert.strictEqual(R.result, "fits");
    // confirming the printing counts it; checking the last card makes the lot live
    const R2 = L.evaluate(D, B, { askMode: "total", total: 1500, lines: [good, { ...pr, prOk: true }] }, live, withCash(cfg(), 100000), NOW);
    assert.strictEqual(R2.value, unitOf(4000) * 2); assert.strictEqual(R2.result, "buy");
    // falling, scattered, disagreeing (TCGplayer far off) also don't count
    const fall = line({ px: 4000 }), dis = line({ px: 9000 });
    const fallComps = [...[31, 35, 40, 45, 50, 55, 60, 65, 70, 80].map((a) => [T - a, 5000, "raw", 1]), ...[3, 8, 14, 20].map((a) => [T - a, 4000, "raw", 1])];   // 30-day median 20% under the 90-day
    const R3 = L.evaluate(D, B, { askMode: "total", total: 1000, lines: [fall, dis] }, liveMap([[fall.k, { data: data(fallComps) }], [dis.k, { data: data(flat(4000)) }]]), withCash(cfg(), 100000), NOW);
    assert.deepStrictEqual(R3.rows.map((r) => r.flags[0]), ["evidence", "evidence"]); assert.strictEqual(R3.result, "no-value");
  });

  await test("nothing valued: no offer at all; no price typed: asks for it; per-card mode needs every price", () => {
    const a = line({ px: 4000 });
    const R = L.evaluate(D, B, { askMode: "total", lines: [a] }, () => null, cfg(), NOW);
    assert.strictEqual(R.result, "need-prices", "not checked yet: asks for prices first"); assert.strictEqual(R.max, 0); assert.strictEqual(R.walk, null); assert.strictEqual(R.open, null);
    const none = L.evaluate(D, B, { askMode: "total", total: 1000, lines: [a] }, liveMap([[a.k, { data: data([]) }]]), cfg(), NOW);
    assert.strictEqual(none.result, "no-value"); assert.strictEqual(none.max, 0);
    const live = liveMap([[a.k, { data: data(flat(4000)) }]]);
    assert.strictEqual(L.evaluate(D, B, { askMode: "total", lines: [a] }, live, cfg(), NOW).result, "need-ask");
    const b = line({ px: 4000 });
    const e = L.evaluate(D, B, { askMode: "each", lines: [{ ...a, ask: 1000 }, b] }, liveMap([[a.k, { data: data(flat(4000)) }], [b.k, { data: data(flat(4000)) }]]), cfg(), NOW);
    assert.strictEqual(e.result, "need-ask"); assert.strictEqual(e.askMissing, 1);
    assert.strictEqual(L.evaluate(D, B, { askMode: "total", lines: [] }, null, cfg(), NOW).result, "empty");
  });

  await test("copies beyond a month of sales count at $0", () => {
    const a = line({ px: 4000, qty: 9 });
    const R = L.evaluate(D, B, { askMode: "total", total: 3000, lines: [a] }, liveMap([[a.k, { data: data(flat(4000)) }]]), withCash(cfg(), 100000), NOW);
    const n30 = AGES.filter((x) => x < 30).length;
    assert.strictEqual(R.rows[0].counted, n30); assert.strictEqual(R.rows[0].slow, 9 - n30); assert.strictEqual(R.value, unitOf(4000) * n30); assert.ok(R.notes.includes("slow"));
  });

  await test("estimates: valued at the low end of the saved range; never BUY; stale noted; older than 3 days not used", () => {
    const it = { id: 1, n: "x", t: "c", tcg: 4000, tcgDay: T };
    const est = B.derive(D, it, data(flat(4000)), cfg(), NOW);
    const a = line({ px: 4000, est }), b = line({ px: 4000, est, cond: "LP" });
    const R = L.evaluate(D, B, { askMode: "total", total: 2000, lines: [a, b] }, null, withCash(cfg(), 100000), NOW);
    assert.strictEqual(R.mode, "estimate"); assert.strictEqual(R.result, "fits");
    assert.strictEqual(R.rows[0].unit, D.netSale(est.resale[0], "c", cfg()));
    assert.strictEqual(R.rows[1].unit, D.netSale(Math.round(est.resale[0] * 0.85), "c", cfg()));
    // the estimate never values a card above the live engine
    assert.ok(R.rows[0].unit <= unitOf(4000));
    const st = L.evaluate(D, B, { askMode: "total", total: 2000, lines: [a] }, null, withCash(cfg(), 100000), NOW + 30 * H);
    assert.ok(st.notes.includes("stale") && st.result === "fits");
    const old = L.evaluate(D, B, { askMode: "total", total: 2000, lines: [a] }, null, withCash(cfg(), 100000), NOW + 80 * H);
    assert.deepStrictEqual(old.rows[0].flags, ["too-old"]); assert.strictEqual(old.result, "need-prices");
    // an estimate with weak evidence counts $0; one that only missed the single-card margin still counts
    const thin = B.derive(D, it, data(flat(4000, [3, 40, 60])), cfg(), NOW);
    assert.deepStrictEqual(L.valueLine(D, B, line({ est: thin }), null, cfg(), NOW).flags, ["evidence"]);
    const low = B.derive(D, { ...it, tcg: 2400 }, data(flat(2400)), cfg(), NOW);
    const v = L.valueLine(D, B, line({ est: low, px: 2400 }), null, cfg(), NOW);
    assert.ok(low.issue === "margin" || low.walk.NM, JSON.stringify(low)); assert.deepStrictEqual(v.flags, []); assert.ok(v.unit > 0);
  });

  await test("random lots: never a BUY that breaks a rule, never value from a flagged card, estimates never BUY", () => {
    let r = 7; const rnd = () => (r = (r * 1103515245 + 12345) % 2147483648) / 2147483648;
    let buys = 0;
    for (let i = 0; i < 3000; i++) {
      const lines = [], pairs = [];
      const nLines = 1 + Math.floor(rnd() * 6);
      for (let j = 0; j < nLines; j++) {
        const px = 500 + Math.floor(rnd() * 12000), kind = rnd();
        const x = line({ px, qty: 1 + Math.floor(rnd() * 4), cond: ["NM", "LP", "MP", "HP"][Math.floor(rnd() * 4)], alts: rnd() < 0.2 ? ["Reverse Holofoil"] : [], prOk: rnd() < 0.5, ask: 100 + Math.floor(rnd() * 4000) });
        const comps = kind < 0.6 ? flat(Math.round(px * (0.8 + rnd() * 0.4))) : kind < 0.75 ? flat(px, [3, 50]) : kind < 0.85 ? [] : flat(px, [40, 50, 60, 70, 80]);
        if (rnd() < 0.15) x.est = B.derive(D, { id: x.id, n: x.n, t: "c", tcg: px, tcgDay: T }, data(comps), cfg(), NOW); else pairs.push([x.k, { data: data(comps) }]);
        lines.push(x);
      }
      const cash = rnd() < 0.2 ? null : Math.floor(rnd() * 40000);
      const lot = { askMode: rnd() < 0.5 ? "each" : "total", total: 500 + Math.floor(rnd() * 12000), shipIn: rnd() < 0.3 ? 500 : 0, taxIn: rnd() < 0.3 ? 8.375 : 0, lines };
      const c = withCash(cfg(), cash), R = L.evaluate(D, B, lot, liveMap(pairs), c, NOW);
      for (const row of R.rows) if (row.flags.length) assert.strictEqual(row.value, 0);
      if (R.result === "buy") {
        buys++;
        assert.strictEqual(R.mode, "live");
        assert.ok(R.cost <= 7500, "limit"); assert.ok(cash != null && cash - R.cost >= 10000, "reserve");
        assert.ok(R.profit >= 500 && R.profit * 100 >= R.cost * 20, "margin");
        assert.ok(R.rows.every((x) => x.mode === "live" || (x.flags.length === 1 && x.flags[0] === "printing")));
      }
      if (R.result === "fits") assert.notStrictEqual(R.mode, "live");
      if (R.max) { assert.ok(R.walk <= R.max && (!R.open || R.open < R.walk)); assert.ok(R.max <= 7500 && (cash == null || R.max <= Math.max(0, cash - 10000) || R.capBy !== "reserve")); }
    }
    assert.ok(buys > 50, `enough BUYs to test (${buys})`);
  });

  await test("ledger draft: every card, its condition and quantity; costs add up to the cent; split by TCGplayer market", () => {
    const lot = { name: "Binder page", shipIn: 500, taxIn: 0, lines: [line({ px: 4000, qty: 3 }), line({ px: 1000, cond: "LP" }), line({ px: 300, qty: 7 })] };
    const d = L.ledgerDraft(D, lot, 5001);
    const total = d.lines.reduce((s, l) => s + l.price * l.qty, 0);
    assert.strictEqual(total, 5001); assert.strictEqual(d.ship, 500); assert.strictEqual(d.lines.reduce((s, l) => s + l.qty, 0), 11);
    assert.ok(d.lines.every((l) => l.kind === "Raw" && l.tcg && l.name && l.set === "Set"));
    assert.strictEqual(d.lines.find((l) => l.cond === "LP").qty, 1);
    const per = (px) => d.lines.filter((l) => l.tcg === lot.lines.find((x) => x.tcg === px).id).reduce((s, l) => s + l.price * l.qty, 0);
    assert.ok(per(4000) > per(1000) && per(1000) > 0 && per(300) > 0);
    assert.ok(/Binder page/.test(d.note) && /11 cards/.test(d.note));
    for (let i = 0; i < 500; i++) {   // random amounts and quantities still add up exactly
      const L2 = { lines: [line({ px: 1 + i * 37 % 9000, qty: 1 + i % 5 }), line({ px: 50 + i * 13 % 4000, qty: 1 + i % 3 })] };
      const p = 1 + i * 997 % 20000, dd = L.ledgerDraft(D, L2, p);
      assert.strictEqual(dd.lines.reduce((s, l) => s + l.price * l.qty, 0), p);
      assert.ok(dd.lines.every((l) => l.price >= 0 && l.qty >= 1));
    }
    assert.deepStrictEqual(L.split(100, [1, 1, 1]), [34, 33, 33]);
  });

  await test("store: saves cards, typed prices and rounded estimates only; nothing restricted; limits; week-old estimates dropped", () => {
    const ls = memLS(); let now = NOW;
    const S = L.Store(ls, B, () => now);
    const id = S.create("Binder"); assert.ok(id);
    const est = B.derive(D, { id: 1, n: "x", t: "c", tcg: 4000, tcgDay: T }, data(flat(4000)), cfg(), NOW);
    assert.ok(S.addLine(id, { id: 5, g: 2, n: "Pikachu (Holofoil)", setN: "Base", t: "c", alts: ["Reverse Holofoil"], tcg: 4000, tcgDay: T, comps: [[1, 2, 3]], median: 4100 }));
    S.addLine(id, { id: 5, g: 2, n: "Pikachu (Holofoil)", setN: "Base", cond: "LP" });
    const lot = S.get(id), k = lot.lines[0].k;
    assert.strictEqual(lot.lines.length, 2); assert.strictEqual(lot.lines[0].prOk, false);
    S.setEst(id, k, { ...est, comps: [[1, 2]], median: 3999, exact: 1234 }, 4100);
    S.setLine(id, lot.lines[1].l, { qty: 3, ask: 1250, cond: "MP", evil: 1 });
    S.set(id, { askMode: "each", total: 4000, shipIn: 300, taxIn: 99, junk: "x" });
    const raw = ls.getItem(L.KEY), j = JSON.parse(raw);
    assert.ok(!/comps|median|exact|evil|junk|sales/.test(raw), raw);
    const sl = j.lots[0];
    assert.strictEqual(sl.taxIn, 20); assert.strictEqual(sl.askMode, "each");
    assert.ok(sl.lines.every((x) => x.est && Object.keys(x.est).every((k2) => B.EST_KEYS.includes(k2))));
    assert.strictEqual(sl.lines[1].qty, 3); assert.strictEqual(sl.lines[1].ask, 1250); assert.strictEqual(sl.lines[1].cond, "MP"); assert.strictEqual(sl.lines[0].tcg, 4100);
    // rounded values only: walk-aways on their steps, resale on band edges
    for (const x of sl.lines) { for (const w of Object.values(x.est.walk)) assert.strictEqual(w % B.step(w), 0); assert.strictEqual(x.est.resale[0] % 200, 0); }
    now = NOW + 8 * 864e5;
    const S2 = L.Store(ls, B, () => now);
    assert.ok(S2.get(id).lines.every((x) => !x.est), "estimates gone after a week; the cards stay");
    assert.strictEqual(S2.get(id).lines.length, 2);
    for (let i = 0; i < 12; i++) S2.create(`x${i}`);
    assert.strictEqual(S2.all().length, L.MAX_LOTS);
    S2.remove(id); assert.ok(!S2.get(id));
    // a broken or foreign value doesn't break the store
    ls.setItem(L.KEY, "{not json"); assert.deepStrictEqual(L.Store(ls, B, () => now).all(), []);
  });

  await test("plan: distinct cards without a fresh estimate or live read, oldest first, within the budget", () => {
    const est = B.derive(D, { id: 1, n: "x", t: "c", tcg: 4000, tcgDay: T }, data(flat(4000)), cfg(), NOW);
    const a = line({}), b = line({ est }), c = line({}), a2 = { ...a, l: "dup", cond: "LP" };
    const lot = { lines: [a, b, c, a2] };
    const P = L.plan(B, lot, 250, NOW);
    assert.deepStrictEqual(P.need.map((x) => x.k), [a.k, c.k]); assert.strictEqual(P.take.length, 2);
    assert.strictEqual(L.plan(B, lot, 150, NOW).take.length, 1);
    assert.strictEqual(L.plan(B, lot, 1000, NOW + 30 * H).need.length, 3, "a day-old estimate is read again");
    assert.deepStrictEqual(L.liveNeed(lot, (k) => k === a.k).map((x) => x.k), [b.k, c.k]);
  });

  console.log(`edge_lot: ${n} tests passed`);
})();
