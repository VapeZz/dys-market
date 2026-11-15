// Checks for Edge's strategy box (site/assets/edge-strat.js). No dependencies: node tests/edge_strat.test.js
const path = require("path"), assert = require("assert");
const TA = require(path.join(__dirname, "../site/assets/edge-ta.js"));
const ST = require(path.join(__dirname, "../site/assets/edge-strat.js"));
const K = ST.K;
let n = 0;
const test = (name, fn) => { try { fn(); n++; } catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; } };

/* a card in a quiet, liquid state; each test bends the numbers one rule looks at */
const base = () => ({ v: 5000, a7: 5000, a30: 5000, a90: 5000, gap: 0, trend: "flat", long: 0, vs30: 0, rsi: 50, pctB: 0.5, bu: 5300, bl: 4700, side: "on", cross: null,
  hi: 6000, lo: 4000, off: 16.7, up: 25, low30: 4800, range90: 10, moves: 8, dailyDays: 120, history: 300, today: 20000 });
const thin = (o = {}) => ({ ...base(), moves: 0, ...o });
const id = (f) => ST.pick(f).id;

test("gates come first", () => {
  assert.deepStrictEqual(ST.pick(null), { id: "stale", mode: "none" });
  assert.strictEqual(id({ ...base(), v: K.MIN_PRICE - 1 }), "bulk");
  assert.strictEqual(id({ ...base(), history: K.MIN_HISTORY - 1 }), "young");
  assert.strictEqual(id({ ...base(), a30: null }), "young");
  assert.strictEqual(ST.pick({ ...base(), history: K.MIN_HISTORY }).mode, "fast");
});
test("fast rules need daily prices and price moves; the rest get the slow rules", () => {
  assert.strictEqual(ST.pick(base()).mode, "fast");
  assert.strictEqual(ST.pick({ ...base(), moves: K.THIN_MOVES - 1 }).mode, "slow");
  assert.strictEqual(ST.pick({ ...base(), dailyDays: K.FAST_DAYS - 1 }).mode, "slow");
  assert.strictEqual(ST.pick({ ...base(), rsi: null }).mode, "slow");
});
test("each fast setup", () => {
  assert.strictEqual(id(base()), "none");
  assert.strictEqual(id({ ...base(), rsi: 75, vs30: 12 }), "stretched");
  assert.strictEqual(id({ ...base(), pctB: 1.1, vs30: 10 }), "stretched");
  assert.notStrictEqual(id({ ...base(), rsi: 99, vs30: 9.9 }), "stretched");           // overbought on a small move is not stretched
  const down = { ...base(), trend: "down", gap: -5, side: "below", v: 4400, a90: 5200, long: -3.8, vs30: -12 };
  assert.strictEqual(id({ ...down, rsi: 25 }), "knife");
  assert.strictEqual(id({ ...down, rsi: 25, vs30: -9 }), "breakdown");                // oversold on a small drop: the trend rule decides
  assert.strictEqual(id({ ...down, rsi: 40 }), "breakdown");
  assert.strictEqual(id({ ...down, rsi: 40, side: "above" }), "weak");
  assert.strictEqual(id({ ...base(), off: 45, up: 8, side: "above", cross: 4, rsi: 42, long: -6, v: 4300, a90: 5000 }), "turn");
  assert.strictEqual(id({ ...base(), off: 45, up: 8, side: "above", cross: 11, rsi: 42, long: -6, v: 4300, a90: 5000 }), "weak");
  assert.strictEqual(id({ ...base(), long: 5, a90: 4700, rsi: 40 }), "dip");
  assert.strictEqual(id({ ...base(), long: 5, a90: 4700, pctB: 0.2 }), "dip");
  assert.strictEqual(id({ ...base(), long: 5, a90: 5100, rsi: 40 }), "none");         // under the 90-day average is not a dip in an uptrend
  const push = { ...base(), off: 1, side: "above", rsi: 60, trend: "up", gap: 4, long: 5, a90: 4700 };
  assert.strictEqual(id(push), "breakout");
  assert.strictEqual(id({ ...push, history: K.BREAKOUT_HISTORY - 1 }), "ride");
  assert.strictEqual(id({ ...push, rsi: 72 }), "ride");
  assert.strictEqual(id({ ...push, off: 8 }), "ride");
});
test("each slow setup", () => {
  assert.strictEqual(id(thin()), "s-none");
  assert.strictEqual(id(thin({ vs30: 15 })), "s-spike");
  assert.strictEqual(id(thin({ vs30: -15 })), "s-drop");
  assert.strictEqual(id(thin({ long: -2, v: 4900, a30: 5000, vs30: -2 })), "s-down");
  assert.strictEqual(id(thin({ off: 35, up: 5 })), "s-base");
  assert.strictEqual(id(thin({ long: 4, v: 4900, a30: 5000, a90: 4800, vs30: -2 })), "s-dip");
  assert.strictEqual(id(thin({ long: 4, a90: 4800 })), "s-up");
});
test("every setup has a call, an action and reasons", () => {
  for (const [k, [name, call, tier, act]] of Object.entries(ST.SETUPS)) {
    assert.ok(name && act && ST.CALLS[call], k);
    assert.ok(tier === null || ST.TIERS[tier], k);
  }
  assert.deepStrictEqual([...ST.FAST, ...ST.SLOW, "stale", "bulk", "young"].sort(), Object.keys(ST.SETUPS).sort());
});

/* the money side, with eBay's fee and Edge's default shipping */
const net = (p) => p ? Math.max(0, p - 40 - p * 0.1325) - (p >= 5000 ? 500 : 100) : 0;
const ctx = { net, shipIn: 150, roi: 20, maxBuy: (p) => Math.max(0, Math.floor(net(p) / 1.2 - 150)), lo: null };
test("break-even is the first price whose net covers the cost", () => {
  for (const cost of [300, 1234, 4648, 4900, 9999, 250000]) {
    const p = ST.breakeven(cost, net);
    assert.ok(net(p) >= cost && net(p - 1) < cost, `cost ${cost} gave ${p}`);
  }
  assert.strictEqual(ST.breakeven(4648, net), 5981);     // under $50 never covers it; over $50 pays the dearer shipping
  assert.strictEqual(ST.breakeven(0, net), null);
});
test("ladder: sells above the price, buys below, cut under the lowest buy", () => {
  const f = { ...base(), v: 5000, a30: 4800, a90: 4500, bl: 4600, bu: 5400, low30: 4700, hi: 6000, lo: 3000 };
  const L = ST.ladder(f, ctx), by = Object.fromEntries(L.rungs.map((r) => [r.k, r]));
  // a $50.00 buy costs $51.50 with shipping in; after eBay's fee and $5 shipping out a sale has to reach $65.60, above both sell levels
  assert.deepStrictEqual(L.rungs.map((r) => r.k), ["even", "sell2", "sell1", "now", "buy1", "buy2", "cut", "flip"]);
  assert.strictEqual(by.even.price, 6560);
  assert.ok(by.sell2.profit < 0 && by.sell1.profit < by.sell2.profit);
  assert.strictEqual(by.sell1.price, 5400); assert.strictEqual(by.sell1.what, "upper band");
  assert.strictEqual(by.sell2.price, 6000); assert.strictEqual(by.sell2.what, "52-week high");
  assert.strictEqual(by.buy1.price, 4800); assert.strictEqual(by.buy1.what, "30-day average");
  assert.strictEqual(by.buy2.price, 4700);
  assert.strictEqual(by.cut.price, Math.round(4700 * 0.97));
  assert.strictEqual(L.cost, 5150);
  assert.ok(Math.abs(by.sell2.profit - (net(6000) - 5150)) < 1e-9);
  assert.strictEqual(by.flip.price, ctx.maxBuy(5000));
  for (let i = 1; i < L.rungs.length; i++) assert.ok(L.rungs[i - 1].price >= L.rungs[i].price);
});
test("ladder: close levels merge, far supports are left out, a flat card still gets a cut", () => {
  const near = ST.ladder({ ...base(), a30: 4800, a90: 4790, bl: null, bu: null, low30: 5000, hi: 5000, lo: 3000 }, ctx);
  assert.strictEqual(near.buys.length, 1);
  assert.strictEqual(near.buys[0].what, "30-day average, 90-day average");
  // a band the price has broken through is not a level: the upper band under the price is no buy rung, the lower band over it no sell rung
  const through = ST.ladder({ ...base(), v: 5000, a30: 4500, a90: 4400, bu: 4900, bl: 4300, low30: 4200, hi: 5000, lo: 3000 }, ctx);
  assert.ok(!through.buys.some((l) => /upper band/.test(l.what)));
  assert.strictEqual(through.buys[0].what, "30-day average");
  const below = ST.ladder({ ...base(), v: 4000, a30: 4500, a90: 4600, bu: 4700, bl: 4100, low30: 4000, hi: 6000, lo: 4000 }, ctx);
  assert.ok(!below.sells.some((l) => /lower band/.test(l.what)));
  assert.strictEqual(near.sells.length, 0);
  const flat = ST.ladder({ ...base(), a30: 5000, a90: 5000, bl: null, bu: null, low30: 5000, hi: 5000, lo: 5000 }, ctx);
  assert.deepStrictEqual(flat.rungs.map((r) => r.k), ["even", "now", "cut", "flip"]);
  assert.strictEqual(flat.cut, 4850);
});
test("risk adds up and stays inside 0 to 100", () => {
  const calm = ST.risk({ ...base(), moves: 9, range90: 5 }, {});
  assert.deepStrictEqual([calm.score, calm.level, calm.parts.length], [0, "Low", 0]);
  const bad = ST.risk({ ...base(), v: 60000, moves: 0, range90: 80, long: -5, trend: "down", history: 40, rsi: 20 }, { pub: "2024-09-01" });
  assert.deepStrictEqual(bad.parts.map((p) => p.pts), [30, 25, 15, 10, 10, 10, 5]);   // thin, range, long trend, history, new set, size, short trend
  assert.strictEqual(bad.score, 100);                                                // 105 points, capped
  assert.strictEqual(bad.level, "High");
  const mid = ST.risk({ ...base(), moves: 4, range90: 35 }, {});
  assert.deepStrictEqual([mid.score, mid.level], [25, "Medium"]);
  const fresh = ST.risk({ ...base(), today: 20000 }, { pub: new Date((20000 - 30) * 864e5).toISOString().slice(0, 10) });
  assert.ok(fresh.parts.some((p) => /30 days old/.test(p.text)));
});

/* whole cards, through the chart's own analysis */
const day = (i) => new Date(Date.UTC(2026, 6, 18) + i * 864e5).toISOString().slice(0, 10);
const card = (values) => { const dates = values.map((_, i) => day(i)); return TA.analyse(dates, values, { dates, values }); };
test("a flat, thin card: Hold on the slow rules, with a ladder and a risk level", () => {
  const p = ST.plan(card(new Array(120).fill(2500)), {}, ctx);
  assert.deepStrictEqual([p.id, p.call, p.mode], ["s-none", "hold", "slow"]);
  assert.ok(p.ladder && p.risk && p.why.length);
  assert.strictEqual(p.risk.parts[0].pts, 30);
});
test("a steady climb with a pullback: a dip in an uptrend", () => {
  const up = Array.from({ length: 120 }, (_, i) => Math.round(2000 * 1.006 ** i + (i % 2 ? 12 : -12)));
  for (let i = 112; i < 120; i++) up[i] = Math.round(up[111] * (1 - 0.01 * (i - 111)));   // 8% off in 8 days
  const p = ST.plan(card(up), {}, ctx);
  assert.deepStrictEqual([p.id, p.call, p.mode, p.tier], ["dip", "buy", "fast", "average"]);
});
test("a new card and a stale one get no call", () => {
  assert.strictEqual(ST.plan(card([1000, 1010, 1020, 1015, 1030, 1040, 1035, 1050]), {}, ctx).id, "young");
  const stale = ST.plan(TA.analyse([day(0), day(1), day(9)], [1000, 1000, null], null), {}, ctx);
  assert.deepStrictEqual([stale.id, stale.call, stale.ladder], ["stale", "watch", null]);
});
test("the low listing line shows only when it clears the profit target", () => {
  const a = card(new Array(120).fill(5000));
  assert.ok(ST.plan(a, {}, { ...ctx, lo: 2500 }).deal);
  assert.strictEqual(ST.plan(a, {}, { ...ctx, lo: 4900 }).deal, null);
});
test("the box never prints a missing number", () => {
  const cards = [new Array(120).fill(2500), Array.from({ length: 120 }, (_, i) => 3000 + ((i * 37) % 11) * 40 - i * 6), Array.from({ length: 60 }, (_, i) => 900 + i * 25), [1000, 1010]];
  for (const c of cards) {
    const h = ST.html(ST.plan(card(c), { pub: day(0) }, ctx));
    assert.ok(!/undefined|NaN|null|Infinity/.test(h), h.match(/.{30}(undefined|NaN|null|Infinity).{30}/)?.[0]);
    assert.ok(/not backtested/.test(h) && /not financial advice/.test(h));
  }
});
/* the backtest result in the box */
const rule = (verdict, claim) => ({ n: 12345, days: 88, avg: 1.2, med: 0, up: 41.2, flat: 20.1, down: 38.7, baseAvg: 2.8, baseUp: 46, baseDown: 35, gone: 0.1, edge: -1.6, months: 21, monthsCounted: 21, claim,
  okMonths: claim ? 62 : null, net: { n: 900, avg: -20, win: 4.4, up20: 5, down20: 3 }, path: { n: 1000, sell: 31, cut: 44, none: 25, sellAt: 5, cutAt: 4 }, verdict });
const fakeBt = (verdicts) => ({ v: 1, step: 7, from: "2025-02-08", to: "2026-10-10", horizon: 30, path: 60, netMin: 2000, base: { net: { win: 5.1 } },
  rules: Object.fromEntries(Object.entries(verdicts).map(([id, [verdict, claim]]) => [id, rule(verdict, claim)])) });
const dipCard = () => { const up = Array.from({ length: 120 }, (_, i) => Math.round(2000 * 1.006 ** i + (i % 2 ? 12 : -12))); for (let i = 112; i < 120; i++) up[i] = Math.round(up[111] * (1 - 0.01 * (i - 111))); return card(up); };
test("without a backtest file the box says not backtested", () => {
  const p = ST.plan(dipCard(), {}, ctx), h = ST.html(p);
  assert.deepStrictEqual([p.verdict, p.demoted, p.bt], [null, false, null]);
  assert.ok(/v1 rules · not backtested/.test(h) && !/Backtest ·/.test(h) && /Buy zone/.test(h));
});
test("a buy rule that failed its backtest makes no call; the levels stay", () => {
  const p = ST.plan(dipCard(), {}, ctx, fakeBt({ dip: ["fail", 1], "s-none": ["none", 0] })), h = ST.html(p);
  assert.deepStrictEqual([p.id, p.call, p.verdict, p.demoted], ["dip", "buy", "fail", true]);
  assert.ok(/<b>No call<\/b>/.test(h) && /Dip in an uptrend failed its backtest/.test(h) && !/class="sg-call sg-buy"/.test(h));
  assert.ok(/v1 rules · failed backtest/.test(h) && /Backtest · Failed/.test(h) && /did worse than the average card, the opposite/.test(h));
  assert.ok(/Price ladder/.test(h) && /Risk ·/.test(h) && !/Execution:/.test(h));
  assert.ok(/up in 41% of 12,345 cases, flat in 20%, down in 39%/.test(h) && /the rule&#39;s way in 13 of 21 months/.test(h));
  assert.ok(/Items of \$20 and up.*profit after fees in 4% of cases \(all items: 5%\)/.test(h) && /first sell level came before the cut level in 31%/.test(h));
});
test("passed and unproven rules keep their call; a failed hold or watch rule is not demoted", () => {
  const pass = ST.plan(dipCard(), {}, ctx, fakeBt({ dip: ["pass", 1] }));
  assert.deepStrictEqual([pass.verdict, pass.demoted], ["pass", false]);
  assert.ok(/v1 rules · backtest passed/.test(ST.html(pass)) && /did better than the average card, as the rule expects/.test(ST.html(pass)) && /class="sg-call sg-buy"/.test(ST.html(pass)));
  const unp = ST.plan(dipCard(), {}, ctx, fakeBt({ dip: ["unproven", 1] }));
  assert.ok(!unp.demoted && /v1 rules · not proven/.test(ST.html(unp)) && /Execution: Average/.test(ST.html(unp)));
  const flat = ST.plan(card(new Array(120).fill(2500)), {}, ctx, fakeBt({ "s-none": ["fail", 0] }));
  assert.deepStrictEqual([flat.call, flat.demoted], ["hold", false]);
  const none = ST.plan(card(new Array(120).fill(2500)), {}, ctx, fakeBt({ "s-none": ["none", 0] })), hn = ST.html(none);
  assert.ok(/v1 rules · backtested/.test(hn) && /Backtest · No claim/.test(hn) && !/the rule&#39;s way/.test(hn));
});
test("a card's verdict is the worse of all games and its own game; the game can only take a claim away", () => {
  const withGame = (all, inGame) => { const bt = fakeBt({ dip: [all, 1] }); bt.games = { pokemon: { cases: 9999, rules: { dip: { ...rule(inGame, 1), n: 4321, avg: -0.4, baseAvg: 4.9 } } } }; return bt; };
  const item = { k: "pokemon", game: "Pokémon" };
  const down = ST.plan(dipCard(), item, ctx, withGame("pass", "fail")), hd = ST.html(down);
  assert.deepStrictEqual([down.verdict, down.demoted, down.bt.byGame], ["fail", true, true]);
  assert.ok(/Backtest · Failed in Pokémon/.test(hd) && /Across all games this rule passed, but in Pokémon prices did worse than the average Pokémon card/.test(hd));
  assert.ok(/failed its backtest in Pokémon, so Edge makes no call/.test(hd) && /Pokémon only \(4,321 cases\): average move −0.4% against \+4.9% for the average Pokémon card/.test(hd));
  const soft = ST.plan(dipCard(), item, ctx, withGame("pass", "unproven")), hs = ST.html(soft);
  assert.deepStrictEqual([soft.verdict, soft.demoted, soft.bt.byGame], ["unproven", false, true]);
  assert.ok(/Not proven in Pokémon/.test(hs) && /did not clear the same bar/.test(hs) && /class="sg-call sg-buy"/.test(hs));
  const noUp = ST.plan(dipCard(), item, ctx, withGame("unproven", "pass"));
  assert.deepStrictEqual([noUp.verdict, noUp.bt.byGame], ["unproven", false]);                 // a good result in one game adds nothing
  const same = ST.plan(dipCard(), item, ctx, withGame("pass", "pass"));
  assert.deepStrictEqual([same.verdict, same.bt.byGame], ["pass", false]);
  const few = ST.plan(dipCard(), item, ctx, withGame("pass", null));                            // too few cases in the game: the all-games verdict stands
  assert.deepStrictEqual([few.verdict, few.bt.byGame], ["pass", false]);
  const other = ST.plan(dipCard(), { k: "lorcana", game: "Lorcana" }, ctx, withGame("pass", "fail"));
  assert.deepStrictEqual([other.verdict, other.bt.game], ["pass", null]);
  assert.deepStrictEqual(ST.verdictFor(withGame("fail", "pass"), "dip", "pokemon").verdict, "fail");
});
test("a rule missing from the backtest file, and a file from another version", () => {
  const p = ST.plan(dipCard(), {}, ctx, fakeBt({ "s-none": ["none", 0] })), h = ST.html(p);
  assert.deepStrictEqual([p.verdict, p.demoted], [null, false]);
  assert.ok(/had no cases in the backtest/.test(h) && /v1 rules · not backtested/.test(h));
  const old = ST.plan(dipCard(), {}, ctx, { v: 2, rules: {} });
  assert.strictEqual(old.bt, null);
});
test("the shipped backtest file fits the rules in this file", () => {
  const bt = require(path.join(__dirname, "../site/assets/edge-backtest.json"));
  assert.strictEqual(bt.v, 1);
  for (const [id, r] of Object.entries(bt.rules)) {
    assert.ok(ST.SETUPS[id], id);
    assert.ok(ST.VERDICT[r.verdict], id);
    assert.ok(r.n > 0 && Math.abs(r.up + r.flat + r.down - 100) < 0.1, id);
    const call = ST.SETUPS[id][1];
    assert.strictEqual(bt.claims[id] || 0, call === "buy" ? 1 : call === "sell" || call === "trim" ? -1 : (id === "knife" || id === "weak") ? -1 : 0, id);   // every buy, sell and trim rule is scored
    if (!(bt.claims[id])) assert.strictEqual(r.verdict, "none", id);
  }
  for (const id of [...ST.FAST, ...ST.SLOW]) assert.ok(bt.rules[id], `${id} has a result`);
  assert.ok(bt.games && bt.games.pokemon && bt.games["pokemon-jp"] && bt.games.yugioh);
  for (const [k, G] of Object.entries(bt.games)) for (const [id, r] of Object.entries(G.rules)) {
    assert.ok(ST.SETUPS[id] && (r.verdict === null || ST.VERDICT[r.verdict]), `${k} ${id}`);
    assert.ok(r.verdict === null || (r.n >= bt.rule.minN && r.months >= bt.rule.minMonths), `${k} ${id}: a game verdict needs enough cases`);
    const f = ST.verdictFor(bt, id, k).verdict, order = { fail: 0, unproven: 1, pass: 2 };
    if (order[f] != null) assert.ok(order[f] <= order[bt.rules[id].verdict], `${k} ${id}: never better than all games`);
  }
  for (const k of Object.keys(bt.games)) { const hk = ST.html(ST.plan(dipCard(), { pub: day(0), k, game: k }, ctx, bt)); assert.ok(!/undefined|NaN|null|Infinity/.test(hk), `${k}: ${hk.match(/.{30}(undefined|NaN|null|Infinity).{30}/)?.[0]}`); }
  const h = ST.html(ST.plan(dipCard(), { pub: day(0) }, ctx, bt));
  assert.ok(!/undefined|NaN|null|Infinity/.test(h), h.match(/.{30}(undefined|NaN|null|Infinity).{30}/)?.[0]);
  assert.ok(/How every rule did/.test(h));
});
if (!process.exitCode) console.log(`${n} tests passed`);
