// Checks for Edge's ledger (site/assets/edge-ledger.js) and the Sheet's web app (tools/ledger/Code.gs, run on an
// emulated Sheet). Synthetic data only. No dependencies: node tests/edge_ledger.test.js
const path = require("path"), assert = require("assert");
const L = require(path.join(__dirname, "../site/assets/edge-ledger.js"));
const F = require(path.join(__dirname, "../tools/ledger/fake_gas.js"));
let n = 0;
const pending = [];
const test = (name, fn) => {
  const done = (e) => { if (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; } else n++; };
  try { const r = fn(); if (r && r.then) pending.push(r.then(() => done(), done)); else done(); } catch (e) { done(e); }
};
const T0 = () => L.blank();
const sum = (a) => a.reduce((s, x) => s + x, 0);
let seq = 0; const rnd = () => ((seq = (seq * 9301 + 49297) % 233280) / 233280);

/* ---------- allocation ---------- */
test("allocate: parts add up exactly, by weight, ties to the earlier line", () => {
  assert.deepStrictEqual(L.allocate(100, [1, 1, 1]), [34, 33, 33]);
  assert.deepStrictEqual(L.allocate(1000, [10000, 5000, 5000]), [500, 250, 250]);
  assert.deepStrictEqual(L.allocate(0, [5, 5]), [0, 0]);
  assert.deepStrictEqual(L.allocate(7, [0, 0]), [4, 3]);
  assert.deepStrictEqual(L.allocate(-5, [1, 1]), [-3, -2]);
  assert.deepStrictEqual(L.allocate(5, []), []);
  for (let k = 0; k < 3000; k++) {
    const w = Array.from({ length: 1 + Math.floor(rnd() * 8) }, () => Math.floor(rnd() * 50000)), a = Math.floor(rnd() * 20000);
    const p = L.allocate(a, w); assert.strictEqual(sum(p), a);
    const tot = sum(w); if (tot) p.forEach((x, i) => assert.ok(Math.abs(x - a * w[i] / tot) < 1 + 1e-9));
  }
});

/* ---------- a card show, worked by hand ---------- */
// Buy at a card show, $10 table-side fee split by price; 8.375% tax on $350 = $29.31:
//   Charizard $100, two Pikachu at $50 (= $100), a booster box $150 → extras $39.31 = 3,931 cents
//   split 100 : 100 : 150 → 1123.14 / 1123.14 / 1684.71 → 1123, 1123, 1685 (largest remainder) → costs 11,123 / 11,123 / 16,685
const show = () => {
  const T = T0();
  T.buys.push({ id: "b1", day: "2026-03-01", book: "Business", where: "Card show", pay: "Cash", tax: 2931, ship: 0, fees: 1000 });
  T.items.push({ id: "i1", buy: "b1", day: "2026-03-01", book: "Business", kind: "Raw", name: "Charizard", qty: 1, price: 10000 },
    { id: "i2", buy: "b1", day: "2026-03-01", book: "Business", kind: "Raw", name: "Pikachu", qty: 2, price: 5000 },
    { id: "i3", buy: "b1", day: "2026-03-01", book: "Business", kind: "Sealed", name: "Booster box", qty: 1, price: 15000 });
  return T;
};
test("buy: tax, shipping and fees split over the lines by price, exactly", () => {
  const R = L.compute(show(), { year: "2026" }), c = Object.fromEntries(R.items.map((x) => [x.id, x.cost]));
  assert.deepStrictEqual(c, { i1: 11123, i2: 11123, i3: 16685 });
  assert.strictEqual(R.buys[0].total, 35000 + 3931);
  assert.strictEqual(R.tot.Business.cash, -38931);
  assert.strictEqual(R.tot.Business.costHeld, 38931);
  assert.strictEqual(R.items.find((x) => x.id === "i2").costEach, 5562);       // 11,123 / 2 = 5,561.5 → 5,562 (display only)
});
test("sales: cost slices add up to the item's cost; net, profit, days held", () => {
  const T = show();
  T.sales.push({ id: "s1", day: "2026-04-01", item: "i2", book: "Business", qty: 1, plat: "eBay", price: 8000, shipIn: 0, fees: 1100, shipOut: 100, supplies: 50, other: 0 },
    { id: "s2", day: "2026-05-01", item: "i2", book: "Business", qty: 1, plat: "Card show", price: 7000 });
  const R = L.compute(T, { year: "2026" }), s1 = R.sales.find((s) => s.id === "s1"), s2 = R.sales.find((s) => s.id === "s2");
  assert.strictEqual(s1.cost + s2.cost, 11123);
  assert.deepStrictEqual([s1.cost, s2.cost], [5562, 5561]);                     // round(11123/2) then the rest
  assert.strictEqual(s1.net, 8000 - 1100 - 100 - 50);
  assert.strictEqual(s1.profit, 6750 - 5562);
  assert.strictEqual(s1.held, 31); assert.strictEqual(s1.term, "Short");
  const i2 = R.items.find((x) => x.id === "i2"); assert.strictEqual(i2.left, 0); assert.strictEqual(i2.costLeft, 0);
  assert.strictEqual(R.tot.Business.realized, (6750 - 5562) + (7000 - 5561));
  assert.strictEqual(R.tot.Business.cash, -38931 + 6750 + 7000);
  assert.strictEqual(R.tot.Business.cogs, 11123);
});
test("a lot of 3 sold 1 then 2: slices 333 + 667 = 1,000", () => {
  const T = T0();
  T.items.push({ id: "x", day: "2026-01-01", book: "Business", kind: "Sealed", name: "ETB", qty: 3, price: 333 });
  T.costs.push({ id: "c", day: "2026-01-02", book: "Business", item: "x", kind: "Shipping", amount: 1 });   // 999 + 1 = 1,000
  T.sales.push({ id: "a", day: "2026-02-01", item: "x", book: "Business", qty: 1, price: 500 }, { id: "b", day: "2026-02-02", item: "x", book: "Business", qty: 2, price: 1000 });
  const R = L.compute(T); assert.deepStrictEqual(R.sales.map((s) => s.cost), [333, 667]);
});
test("long-term after 365 days; sold more than held is flagged", () => {
  const T = T0();
  T.items.push({ id: "x", day: "2024-01-01", book: "Personal", kind: "Graded", name: "Umbreon PSA 10", qty: 1, price: 100000 });
  T.sales.push({ id: "a", day: "2025-01-01", item: "x", book: "Personal", qty: 1, price: 150000 }, { id: "b", day: "2025-01-02", item: "x", book: "Personal", qty: 1, price: 1 });
  const R = L.compute(T, { year: "2025" });
  assert.strictEqual(R.sales[0].held, 366); assert.strictEqual(R.sales[0].term, "Long");
  assert.ok(R.warn.some((w) => /sold 2 of 1/.test(w)));
});
test("grading cost tied to an item adds to its cost; a general expense counts against the year", () => {
  const T = show();
  T.costs.push({ id: "g", day: "2026-03-05", book: "Business", item: "i1", kind: "Grading", amount: 2499 },
    { id: "e", day: "2026-03-06", book: "Business", item: "", kind: "Show table", amount: 15000 },
    { id: "old", day: "2025-12-31", book: "Business", item: "", kind: "Supplies", amount: 700 });
  const R = L.compute(T, { year: "2026" }), b = R.tot.Business;
  assert.strictEqual(R.items.find((x) => x.id === "i1").cost, 11123 + 2499);
  assert.strictEqual(b.expenses, 15000);                                        // linked grading and last year's supplies are not this year's expenses
  assert.strictEqual(b.cash, -38931 - 2499 - 15000 - 700);
  assert.strictEqual(b.net, b.realized - 15000);
});
test("cash: starting cash, money in/out and moves; both books add up", () => {
  const T = T0();
  T.cash.push({ id: "1", day: "2026-01-01", book: "Business", kind: "Starting cash", amount: 100000 },
    { id: "2", day: "2026-01-01", book: "Personal", kind: "Starting cash", amount: 5000 },
    { id: "3", day: "2026-01-02", book: "Business", kind: "Money out", amount: 20000 },
    { id: "4", day: "2026-01-03", book: "Business", kind: "Move", to: "Personal", amount: 30000 },
    { id: "5", day: "2026-01-04", book: "Personal", kind: "Money in", amount: 1000 },
    { id: "6", day: "2026-01-05", book: "Personal", kind: "Move", to: "Personal", amount: 999 });          // a move to the same book does nothing
  const R = L.compute(T);
  assert.strictEqual(R.tot.Business.cash, 100000 - 20000 - 30000);
  assert.strictEqual(R.tot.Personal.cash, 5000 + 30000 + 1000);
  assert.strictEqual(R.tot.All.cash, R.tot.Business.cash + R.tot.Personal.cash);
});
test("market value: items with no price are left out and counted, never guessed", () => {
  const T = show();
  const R = L.compute(T, { priceOf: (x) => x.id === "i1" ? 15000 : x.id === "i2" ? 4000 : null });
  const b = R.tot.Business;
  assert.strictEqual(b.value, 15000 + 8000); assert.strictEqual(b.valued, 2); assert.strictEqual(b.unvalued, 1);
  assert.strictEqual(b.unreal, (15000 - 11123) + (8000 - 11123));
  assert.strictEqual(R.items.find((x) => x.id === "i3").value, null);
});
test("deleted rows are ignored; the year only counts that year's sales", () => {
  const T = show();
  T.items.push({ id: "gone", day: "2026-03-01", book: "Business", kind: "Raw", name: "Oops", qty: 1, price: 999, void: 1 });
  T.sales.push({ id: "s25", day: "2025-06-01", item: "i1", book: "Business", qty: 1, price: 20000 }, { id: "sv", day: "2026-06-01", item: "i3", book: "Business", qty: 1, price: 1, void: 1 });
  const R = L.compute(T, { year: "2026" });
  assert.ok(!R.items.some((x) => x.id === "gone"));
  assert.strictEqual(R.tot.Business.sales, 0);
  assert.strictEqual(L.compute(T, { year: "2025" }).tot.Business.sales, 1);
});
test("the two books stay apart; an item moved to Personal sells in Personal", () => {
  const T = show(); T.items[0].book = "Personal";
  T.sales.push({ id: "s", day: "2026-07-01", item: "i1", book: "Personal", qty: 1, price: 20000 });
  const R = L.compute(T, { year: "2026" });
  assert.strictEqual(R.tot.Personal.realized, 20000 - 11123); assert.strictEqual(R.tot.Business.realized, 0);
  assert.strictEqual(R.tot.Business.cash, -38931); assert.strictEqual(R.tot.Personal.cash, 20000);
  assert.strictEqual(R.tot.All.realized, R.tot.Personal.realized);
});

/* ---------- tax-year export ---------- */
const parse = (text) => text.trim().split("\r\n").map((l) => { const out = []; let cur = "", q = false; for (let i = 0; i < l.length; i++) { const ch = l[i]; if (q) { if (ch === '"' && l[i + 1] === '"') { cur += '"'; i++; } else if (ch === '"') q = false; else cur += ch; } else if (ch === '"') q = true; else if (ch === ",") { out.push(cur); cur = ""; } else cur += ch; } out.push(cur); return out; });
test("export: sales, purchases, expenses, Dec 31 inventory and a summary that agrees", () => {
  const T = show();
  T.items[0].name = '=HYPERLINK("x") Charizard, "Base"';
  T.sales.push({ id: "s1", day: "2026-04-01", item: "i2", book: "Business", qty: 1, plat: "eBay", price: 8000, fees: 1100, shipOut: 100, supplies: 50 },
    { id: "s27", day: "2027-01-05", item: "i1", book: "Business", qty: 1, plat: "eBay", price: 30000 });
  T.costs.push({ id: "e", day: "2026-03-06", book: "Business", item: "", kind: "Show table", amount: 15000 });
  const x = L.exportYear(T, 2026), S = parse(x.sales), I = parse(x.inventory), P = parse(x.purchases), E = parse(x.expenses), Y = parse(x.summary);
  assert.strictEqual(S.length, 2); assert.strictEqual(S[1][0], "2026-04-01"); assert.strictEqual(S[1][16], "11.88");    // 67.50 − 55.62
  assert.strictEqual(I.length, 4);                                               // Charizard (sold in 2027) is still held on Dec 31, plus Pikachu ×1 and the box
  assert.ok(I.some((r) => r[1].startsWith("'=HYPERLINK") && r[1].includes('"Base"')), "text that looks like a formula is made safe");
  assert.strictEqual(P[1][10], "389.31");
  assert.deepStrictEqual(E[1].slice(0, 5), ["2026-03-06", "Business", "Show table", "150.00", "No"]);
  const row = (label) => Y.find((r) => r[0].startsWith(label));
  assert.strictEqual(row("Profit on sales")[1], "11.88"); assert.strictEqual(row("Net")[1], (11.88 - 150).toFixed(2));
  assert.strictEqual(row("Inventory at cost")[1], (389.31 - 55.62).toFixed(2));
  assert.strictEqual(x.counts.sales, 1);
  assert.ok(/Not tax advice/.test(x.summary));
});

/* ---------- this phone's copy and its queue ---------- */
const mem = () => { const m = {}; return { getItem: (k) => m[k] ?? null, setItem: (k, v) => { m[k] = String(v); }, _m: m }; };
test("store: changes queue until the Sheet confirms them; a failed or bad reply keeps everything", async () => {
  let t = 1000; const st = L.Store(mem(), "k", () => t++, rnd);
  const b = st.put("buys", { day: "2026-11-16", book: "Business", where: "Card show", pay: "Cash" });
  st.put("items", { buy: b.id, day: "2026-11-16", book: "Business", kind: "Raw", name: "A", qty: 1, price: 100 });
  assert.strictEqual(st.queue, 2);
  assert.deepStrictEqual(await st.sync(async () => { throw new Error("offline"); }), { ok: false, reason: "offline" });
  assert.strictEqual(st.queue, 2); assert.strictEqual(st.T.items.length, 1);
  assert.strictEqual((await st.sync(async () => ({ ok: true }))).reason, "bad reply");
  assert.strictEqual(st.T.items.length, 1, "a reply without tables never wipes this phone");
  assert.strictEqual((await st.sync(async () => ({ ok: false, error: "denied" }))).reason, "denied");
  let sent;
  const r = await st.sync(async (body) => { sent = body; return { ok: true, tables: { buys: [body.ops[0].row], items: [body.ops[1].row], sales: [], costs: [], cash: [] } }; });
  assert.deepStrictEqual(r, { ok: true, sent: 2, left: 0 }); assert.strictEqual(sent.ops.length, 2); assert.strictEqual(st.queue, 0);
});
test("store: a change made while a sync is out stays on top of the Sheet's answer", async () => {
  let t = 1; const st = L.Store(mem(), "k", () => t++, rnd);
  const x = st.put("items", { day: "2026-11-16", book: "Business", kind: "Raw", name: "Old name", qty: 1, price: 100 });
  const r = st.sync(async (body) => { st.put("items", { ...x, name: "New name" }); return { ok: true, tables: { ...L.blank(), items: [body.ops[0].row] } }; });
  await r; assert.strictEqual(st.T.items[0].name, "New name"); assert.strictEqual(st.queue, 1);
});
test("store: delete keeps the row as deleted; it survives a reload", () => {
  const m = mem(); let t = 1; const st = L.Store(m, "k", () => t++, rnd);
  const x = st.put("items", { name: "A", qty: 1, price: 1 }); st.remove("items", x.id);
  const again = L.Store(m, "k", () => t++, rnd);
  assert.strictEqual(again.T.items[0].void, 1); assert.strictEqual(again.queue, 2);
});

/* ---------- the Sheet's web app (the real Code.gs on an emulated Sheet) ---------- */
const TOK = "f3".repeat(20), TOK2 = "9a".repeat(20);
const app = (o = {}) => F.load({ hashes: [F.sha(TOK), F.sha(TOK2)].join(","), ...o });
const op = (table, row, id) => ({ opId: id || L.newId("o", rnd), table, row });
test("web app: only paired devices; a bad body or a busy lock is refused", () => {
  const g = app();
  assert.deepStrictEqual(g.post({ token: "short", ops: [] }), { ok: false, error: "denied" });
  assert.deepStrictEqual(g.post({ token: "x".repeat(40), ops: [] }), { ok: false, error: "denied" });
  assert.deepStrictEqual(g.post("not json"), { ok: false, error: "bad request" });
  assert.strictEqual(g.post({ token: TOK, ops: [] }).ok, true);
  assert.strictEqual(g.post({ token: TOK2, ops: [] }).ok, true);
  assert.deepStrictEqual(app({ busy: true }).post({ token: TOK, ops: [] }), { ok: false, error: "busy" });
  assert.deepStrictEqual(JSON.parse(g.ctx.doGet().text), { ok: true, app: "dys-edge-ledger", v: 1 });
});
test("web app: money round-trips to the cent; text stays text (dates, leading zeros, '=')", () => {
  const g = app(), rows = [];
  for (let k = 0; k < 400; k++) rows.push({ id: `i${k}`, day: "2026-11-16", book: "Business", kind: "Raw", name: k % 7 ? `Card ${k}` : `=SUM(A1) ${k}`, cert: "00" + k, qty: 1, price: Math.floor(rnd() * 10000000), upd: 1 });
  const r = g.post({ token: TOK, ops: rows.map((x) => op("items", x)) });
  assert.strictEqual(r.applied, 400);
  const back = new Map(r.tables.items.map((x) => [x.id, x]));
  for (const x of rows) { const b = back.get(x.id); assert.strictEqual(b.price, x.price); assert.strictEqual(b.name, x.name); assert.strictEqual(b.cert, x.cert); assert.strictEqual(b.day, "2026-11-16"); }
});
test("web app: a newer change wins, an older one is skipped, a replay is applied once", () => {
  const g = app();
  const o1 = op("items", { id: "i1", name: "A", qty: 1, price: 100, upd: 10 }, "o1");
  g.post({ token: TOK, ops: [o1] });
  let r = g.post({ token: TOK, ops: [op("items", { id: "i1", name: "Old", upd: 5 }, "o2")] });
  assert.strictEqual(r.skipped, 1); assert.strictEqual(r.tables.items[0].name, "A");
  r = g.post({ token: TOK, ops: [op("items", { id: "i1", name: "B", upd: 11 }, "o3"), o1] });
  assert.strictEqual(r.applied, 1); assert.strictEqual(r.skipped, 1); assert.strictEqual(r.tables.items[0].name, "B");
  assert.strictEqual(r.tables.items[0].price, 100, "a change without a column leaves that column alone");
  const log = g.ss.getSheetByName("Log"); assert.strictEqual(log.getLastRow(), 1 + 3);
});
test("web app: text starting with = survives later changes to its row; a formula the owner adds is kept", () => {
  const g = app();
  g.post({ token: TOK, ops: [op("items", { id: "x", name: "=Pikachu \"promo\", 1/1", note: "+1 for the sleeve", qty: 1, price: 100, upd: 1 })] });
  const sh = g.ss.getSheetByName("Items"), w = sh.grid[0].filter((v) => v !== "").length;
  sh.grid[0][w] = "My total"; sh.type(2, w + 1, "=SUM(1,2)");            // the owner's own column with a formula
  let r = g.post({ token: TOK, ops: [op("items", { id: "x", status: "Listed", upd: 2 })] });
  r = g.post({ token: TOK, ops: [op("items", { id: "x", void: 1, upd: 3 })] });
  const x = r.tables.items[0];
  assert.strictEqual(x.name, '=Pikachu "promo", 1/1'); assert.strictEqual(x.note, "+1 for the sleeve"); assert.strictEqual(x.status, "Listed");
  assert.strictEqual(sh.getRange(2, w + 1).getFormulas()[0][0], "=SUM(1,2)", "the owner's formula is still a formula");
});
test("web app: columns are found by header after hand edits; a typed date reads back as a day", () => {
  const g = app();
  g.post({ token: TOK, ops: [op("sales", { id: "s1", day: "2026-11-01", item: "i1", book: "Business", qty: 1, plat: "eBay", price: 5000, upd: 1 })] });
  const sh = g.ss.getSheetByName("Sales");
  // the owner inserts a "Buyer" column after Date by hand: shift everything from column 3 right by one
  sh.grid.forEach((row) => row.splice(2, 0, "")); sh.grid[0][2] = "Buyer"; sh.grid[1][2] = "pat123";
  sh.type(2, 2, "2026-11-02");                                                      // a hand-typed date in a cell without plain-text format
  const r = g.post({ token: TOK, ops: [op("sales", { id: "s1", fees: 700, upd: 2 })] });
  const s = r.tables.sales[0];
  assert.strictEqual(s.day, "2026-11-02"); assert.strictEqual(s.price, 5000); assert.strictEqual(s.fees, 700);
  assert.strictEqual(sh.grid[1][2], "pat123", "the owner's own column is kept");
});
test("web app: the shown columns and the Summary tab are written; the token is never stored", () => {
  const g = app(), T = show();
  const ops = [...T.buys.map((r) => op("buys", { ...r, upd: 1 })), ...T.items.map((r) => op("items", { ...r, upd: 1 }))];
  const R = L.compute(T, { year: "2026" });
  const r = g.post({ token: TOK, ops, shown: L.shownRows(R), summary: L.summaryRows(R, "2026-11-16 03:40") });
  assert.ok(r.ok);
  const it = g.ss.getSheetByName("Items"), head = it.grid[0], col = (h) => head.indexOf(h);
  const i2 = it.grid.find((row) => row[0] === "i2");
  assert.strictEqual(i2[col("Cost each")], 55.62); assert.strictEqual(i2[col("Qty held")], 2);
  assert.strictEqual(g.ss.getSheetByName("Buys").grid[1][head.length ? g.ss.getSheetByName("Buys").grid[0].indexOf("Total") : 0], 389.31);
  const sm = g.ss.getSheetByName("Summary").grid; assert.strictEqual(sm[0][0], "DYS Edge ledger"); assert.strictEqual(sm[2][1], 389.31);
  assert.ok(!r.tables.items[0].costEach && r.tables.items[0].left === undefined, "Edge's own numbers are not read back as facts");
  const all = JSON.stringify(g.ss.tabs.map((t) => t.grid)); assert.ok(!all.includes(TOK), "the token is not in the Sheet");
});
test("end to end: a phone offline at a show and the desktop both land in the Sheet", async () => {
  const g = app(); let t = 1;
  const phone = L.Store(mem(), "k", () => t++, rnd), desk = L.Store(mem(), "k", () => t++, rnd);
  const send = (tok) => async (body) => g.post(JSON.parse(JSON.stringify({ token: tok, ...body })));
  const { buy, items } = L.buyRows({ day: "2026-11-21", book: "Business", where: "Card show", pay: "Cash", tax: 0, ship: 0, fees: 0, lines: [{ kind: "Raw", name: "Umbreon ex", qty: 1, price: 60000 }, { kind: "Sealed", name: "ETB", qty: 2, price: 5000 }] }, rnd);
  phone.put("buys", buy); items.forEach((x) => phone.put("items", x));
  assert.strictEqual((await phone.sync(async () => { throw new Error("no signal"); })).ok, false);
  desk.put("costs", { day: "2026-11-21", book: "Business", item: "", kind: "Show table", amount: 7500 });
  assert.ok((await desk.sync(send(TOK2))).ok);
  assert.ok((await phone.sync(send(TOK))).ok);
  assert.ok((await desk.sync(send(TOK2))).ok);
  for (const s of [phone, desk]) { const R = L.compute(s.T, { year: "2026" }); assert.strictEqual(R.tot.Business.cash, -(60000 + 10000 + 7500)); assert.strictEqual(R.items.length, 2); }
  const strange = L.Store(mem(), "k", () => t++, rnd); strange.put("cash", { day: "2026-11-21", book: "Business", kind: "Money out", amount: 1 });
  assert.strictEqual((await strange.sync(send("e".repeat(40)))).reason, "denied");
  assert.strictEqual(L.compute(desk.T).cash.length, 0);
});
test("buyRows: one buy row and one item per line, with sane defaults", () => {
  const { buy, items } = L.buyRows({ day: "2026-11-16", book: "Personal", where: "Online", pay: "Card", tax: "12", lines: [{ kind: "Graded", name: "X", grade: 10, qty: 0, price: -5 }, { kind: "Raw", name: "Y" }] }, rnd);
  assert.strictEqual(buy.tax, 12); assert.strictEqual(items.length, 2);
  assert.deepStrictEqual([items[0].grader, items[0].grade, items[0].qty, items[0].price, items[0].cond], ["PSA", "10", 1, 0, ""]);
  assert.strictEqual(items[1].cond, "NM"); assert.ok(items.every((x) => x.buy === buy.id && x.book === "Personal"));
});

test("a buy saved twice from the same form writes the same rows; a moved inventory row keeps its ID", () => {
  const f = { day: "2026-11-16", book: "Business", where: "Card show", pay: "Cash", buyId: "b-fixed", lines: [{ id: "i-a", kind: "Raw", name: "A", price: 100 }, { id: "i-b", kind: "Sealed", name: "B", price: 200 }] };
  const one = L.buyRows(f, rnd), two = L.buyRows(f, rnd);
  assert.deepStrictEqual(one, two);
  const st = L.Store(mem(), "k", (() => { let t = 0; return () => ++t; })(), rnd);
  for (const r of [one, two]) { st.put("buys", r.buy); r.items.forEach((x) => st.put("items", x)); }
  assert.strictEqual(st.T.buys.length, 1); assert.strictEqual(st.T.items.length, 2);
  const o = { k: "610516|Umbreon ex - 161/131 (Holofoil)", id: 610516, at: "2026-10-01", cost: 80000 };
  assert.strictEqual(L.migId(o), L.migId({ ...o })); assert.notStrictEqual(L.migId(o), L.migId({ ...o, at: "2026-10-02" }));
});
test("web app: a sync whose answer was lost, sent again, lands once", async () => {
  const g = app(); let t = 1;
  const st = L.Store(mem(), "k", () => t++, rnd);
  st.put("sales", { id: "s-1", day: "2026-11-16", item: "i1", book: "Business", qty: 1, plat: "eBay", price: 5000 });
  st.put("cash", { id: "m-1", day: "2026-11-16", book: "Business", kind: "Starting cash", amount: 100000 });
  // the Sheet takes the changes, then the phone loses the answer
  assert.strictEqual((await st.sync(async (body) => { g.post({ token: TOK, ...JSON.parse(JSON.stringify(body)) }); throw new Error("lost"); })).ok, false);
  assert.strictEqual(st.queue, 2);
  const r = await st.sync(async (body) => g.post({ token: TOK, ...JSON.parse(JSON.stringify(body)) }));
  assert.ok(r.ok); assert.strictEqual(st.queue, 0);
  assert.strictEqual(st.T.sales.length, 1); assert.strictEqual(st.T.cash.length, 1);
  assert.strictEqual(g.ss.getSheetByName("Sales").getLastRow(), 2); assert.strictEqual(g.ss.getSheetByName("Log").getLastRow(), 3);
});
test("recovery: a phone that lost its copy gets everything back from the Sheet", async () => {
  const g = app(); let t = 1; const send = async (body) => g.post({ token: TOK, ...JSON.parse(JSON.stringify(body)) });
  const a = L.Store(mem(), "k", () => t++, rnd), T = show();
  T.buys.forEach((r) => a.put("buys", r)); T.items.forEach((r) => a.put("items", r));
  a.put("sales", { id: "s", day: "2026-04-01", item: "i2", book: "Business", qty: 1, plat: "eBay", price: 8000, fees: 1100 });
  await a.sync(send);
  const fresh = L.Store(mem(), "k", () => t++, rnd);
  await fresh.sync(send);
  const x = L.compute(a.T, { year: "2026" }), y = L.compute(fresh.T, { year: "2026" });
  assert.deepStrictEqual(y.tot, x.tot); assert.deepStrictEqual(y.items.map((i) => i.cost), x.items.map((i) => i.cost));
});

test("grades: 1 to 10 with halves; editing a grade keeps the item's cost and adds nothing", () => {
  assert.deepStrictEqual(["10", "9.5", "1", "9", " 8 "].map(L.okGrade), [true, true, true, true, true]);
  assert.deepStrictEqual(["", "0", "10.5", "11", "PSA 10", "9.3"].map(L.okGrade), [false, false, false, false, false, false]);
  let t = 1; const st = L.Store(mem(), "k", () => t++, rnd);
  st.put("buys", { id: "b", day: "2026-11-16", book: "Personal", where: "Card show", pay: "Cash" });
  st.put("items", { id: "i", buy: "b", day: "2026-11-16", book: "Personal", kind: "Graded", name: "Pikachu", grader: "PSA", grade: "", qty: 1, price: 7000 });
  const before = L.compute(st.T, { year: "2026" });
  st.put("items", { ...st.T.items[0], grade: "10", cert: "123" });
  const after = L.compute(st.T, { year: "2026" });
  assert.strictEqual(st.T.items.length, 1); assert.strictEqual(st.T.costs.length, 0); assert.strictEqual(st.T.buys.length, 1);
  assert.strictEqual(after.items[0].cost, 7000); assert.deepStrictEqual(after.tot, before.tot);
});

Promise.all(pending).then(() => { console.log(`${n} ledger checks passed${process.exitCode ? " (with failures above)" : ""}`); });
