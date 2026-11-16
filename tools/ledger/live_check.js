// Live check of the ledger's real Google Sheet web app with SYNTHETIC transactions (every ID starts "zt-",
// every name starts "TEST"). Run in a paired browser on the Edge page (it needs this device's pairing token):
//   const r = await (new Function("return (\n" + await (await fetch(RAW_URL)).text() + "\n)"))()(WEB_APP_URL, LEDGER_JS_URL); r
// It uses its own copy of the ledger in memory: this device's real ledger copy is never read or changed.
// Returns { pass, fail, checks: [[ok, what]] }. At the end every test row is marked Deleted in the Sheet.
async (url, ledgerJs) => {
  const checks = [], ok = (c, what) => { checks.push([!!c, what]); return !!c; };
  const L = await (async () => { const src = await (await fetch(ledgerJs, { cache: "no-store" })).text(); const m = { exports: {} }; new Function("module", "window", src)(m, undefined); return m.exports; })();
  const relay = JSON.parse(localStorage.getItem("dys-edge-relay") || "{}"), token = relay.pass;
  if (!ok(token && token.length >= 32, "this browser is paired (has a pairing token)")) return { checks };
  const post = async (body) => { const t0 = performance.now(); const r = await fetch(url, { method: "POST", headers: { "Content-Type": "text/plain;charset=utf-8" }, body: JSON.stringify(body) }); const j = await r.json(); j._ms = Math.round(performance.now() - t0); j._http = r.status; return j; };
  const mem = () => { const m = {}; return { getItem: (k) => m[k] ?? null, setItem: (k, v) => { m[k] = String(v); } }; };
  let n = 0; const id = (p) => `zt-${p}-${Date.now().toString(36)}-${++n}`;
  const send = async (body) => post({ token, ...JSON.parse(JSON.stringify(body)) });
  const mine = (T) => { const o = {}; for (const k of L.TABLES) o[k] = T[k].filter((r) => String(r.id).startsWith("zt-")); return o; };   // only this check's rows

  // 1. reachable, and strangers are refused
  const h = await (await fetch(url)).json();
  ok(h.ok && h.app === "dys-edge-ledger", "health check answers (no data in it)");
  const bad = await post({ token: "0".repeat(64), ops: [] });
  ok(bad.ok === false && bad.error === "denied", "an unknown device is refused");
  const none = await post({ ops: [] });
  ok(none.ok === false && none.error === "denied", "no token is refused");
  const first = await post({ token, ops: [] });
  ok(first.ok && first.tables && L.TABLES.every((k) => Array.isArray(first.tables[k])), `this device is accepted; every tab answers (${first._ms} ms)`);
  ok(/^https:\/\/docs\.google\.com\/spreadsheets\/d\//.test(first.sheet || ""), "the reply names the Sheet");
  const before = Object.fromEntries(L.TABLES.map((k) => [k, first.tables[k].filter((r) => !String(r.id).startsWith("zt-")).length]));

  // 2. a realistic set of transactions in both books (amounts worked by hand)
  let t = Date.now(); const st = L.Store(mem(), "zt", () => ++t);
  const C = (o) => st.put("cash", { id: id("m"), day: "2026-11-16", note: "TEST", ...o });
  C({ book: "Business", kind: "Starting cash", amount: 100000 });                                  // $1,000.00
  C({ book: "Personal", kind: "Starting cash", amount: 50000 });                                   // $500.00
  const buy = L.buyRows({ buyId: id("b"), day: "2026-11-16", book: "Business", where: "Card show", from: "TEST table", pay: "Cash", tax: 2931, ship: 0, fees: 1000,
    lines: [{ id: id("i"), kind: "Raw", name: "TEST card A", qty: 1, price: 10000 }, { id: id("i"), kind: "Raw", name: "TEST card B", qty: 2, price: 5000 }, { id: id("i"), kind: "Sealed", name: "=TEST box \"x\", y", qty: 1, price: 15000 }] });
  st.put("buys", buy.buy); buy.items.forEach((x) => st.put("items", x));                           // total $389.31; costs 111.23 / 111.23 / 166.85
  const pb = L.buyRows({ buyId: id("b"), day: "2026-10-01", book: "Personal", where: "Online", pay: "Card", tax: 1676, ship: 499, lines: [{ id: id("i"), kind: "Graded", name: "TEST graded", grader: "PSA", grade: "10", cert: "0012345678", price: 20000 }] });
  st.put("buys", pb.buy); pb.items.forEach((x) => st.put("items", x));                               // $221.75
  const [A, B2] = buy.items;
  st.put("sales", { id: id("s"), day: "2026-11-16", item: B2.id, book: "Business", qty: 1, plat: "eBay", price: 11000, shipIn: 0, fees: 1569, shipOut: 100, supplies: 50, other: 0, note: "TEST" });   // net 92.81, cost 55.62
  st.put("costs", { id: id("c"), day: "2026-11-16", book: "Business", item: A.id, kind: "Grading", amount: 2499, note: "TEST" });   // A's cost → 136.22
  st.put("costs", { id: id("c"), day: "2026-11-16", book: "Business", item: "", kind: "Show table", amount: 7500, note: "TEST" });
  C({ book: "Business", kind: "Move", to: "Personal", amount: 2000 });
  const r1 = await st.sync(send);
  ok(r1.ok && r1.sent === 12 && st.queue === 0, `12 synthetic changes sent and confirmed (${r1.sent})`);
  const R = L.compute(mine(st.T), { year: "2026" }), b = R.tot.Business, p = R.tot.Personal;
  ok(b.cash === 100000 - 38931 + 9281 - 2499 - 7500 - 2000, `Business cash $${b.cash / 100} (expect 584.51)`);
  ok(p.cash === 50000 - 22175 + 2000, `Personal cash $${p.cash / 100} (expect 298.25)`);
  ok(R.tot.All.cash === b.cash + p.cash, "both books add up");
  ok(b.realized === 9281 - 5562 && p.realized === 0, `profit stays in its book (Business +$${b.realized / 100}, Personal $0)`);
  ok(b.expenses === 7500 && b.net === 3719 - 7500, "a general expense counts; grading added to the card's cost doesn't");
  const cost = Object.fromEntries(R.items.map((x) => [x.name, x.cost]));
  ok(cost["TEST card A"] === 11123 + 2499 && cost["TEST card B"] === 11123 && cost['=TEST box "x", y'] === 16685 && cost["TEST graded"] === 22175, "item costs: tax and fees split by price, grading added");

  // 3. the Sheet holds exactly that (read back as a fresh phone would: recovery)
  const fresh = L.Store(mem(), "zt2", () => ++t); const r2 = await fresh.sync(send);
  const R2 = L.compute(mine(fresh.T), { year: "2026" });
  ok(r2.ok && JSON.stringify(R2.tot) === JSON.stringify(R.tot), "recovery: a phone with no copy gets the same books back from the Sheet");
  const g = mine(fresh.T).items.find((x) => x.name === "TEST graded"), box = mine(fresh.T).items.find((x) => x.kind === "Sealed");
  ok(g && g.cert === "0012345678" && g.day === "2026-10-01" && g.grade === "10", "text stays text in the Sheet (cert with leading zeros, the date, the grade)");
  ok(box && box.name === '=TEST box "x", y', "a name starting with = is kept as text, not run as a formula");

  // 4. no duplicates: an answer lost and the same changes sent again, a form saved twice, two devices at once
  const extra = id("s"), op = { opId: L.newId("o"), table: "sales", row: { id: extra, day: "2026-11-16", item: buy.items[2].id, book: "Business", qty: 1, plat: "Card show", price: 1, upd: ++t, note: "TEST" } };
  const s1 = await post({ token, ops: [op] }), s2 = await post({ token, ops: [op] });
  ok(s1.applied === 1 && s2.applied === 0 && s2.skipped === 1, "the same change sent twice is applied once");
  const again = await post({ token, ops: [{ ...op, opId: L.newId("o"), row: { ...op.row, upd: ++t } }] });
  ok(again.tables.sales.filter((r) => r.id === extra).length === 1, "the same row saved twice is one row");
  const [c1, c2] = await Promise.all([post({ token, ops: [{ opId: L.newId("o"), table: "costs", row: { id: id("c"), day: "2026-11-16", book: "Personal", kind: "Supplies", amount: 111, upd: ++t, note: "TEST" } }] }),
    post({ token, ops: [{ opId: L.newId("o"), table: "costs", row: { id: id("c"), day: "2026-11-16", book: "Personal", kind: "Supplies", amount: 222, upd: ++t, note: "TEST" } }] })]);
  ok(c1.ok && c2.ok, "two devices syncing at the same moment both succeed");
  const old = await post({ token, ops: [{ opId: L.newId("o"), table: "sales", row: { id: extra, price: 999999, upd: 1 } }] });
  ok(old.skipped === 1 && old.tables.sales.find((r) => r.id === extra).price === 1, "an older edit never overwrites a newer one");

  // 5. money to the cent, both ways
  const amts = Array.from({ length: 40 }, (_, i) => [1, 5, 9, 10, 29, 99, 101, 333, 1005, 12345, 99999, 100001, 2147483][i % 13] + i * 7);
  const mid = id("m"), mo = amts.map((a, i) => ({ opId: L.newId("o"), table: "cash", row: { id: `${mid}-${i}`, day: "2026-11-16", book: "Personal", kind: "Money in", amount: a, upd: ++t, note: "TEST" } }));
  const mr = await post({ token, ops: mo });
  ok(amts.every((a, i) => mr.tables.cash.find((r) => r.id === `${mid}-${i}`)?.amount === a), "40 amounts round-trip to the exact cent");

  // 6. clean up: every test row marked Deleted (kept in the Sheet's history; removed from the tabs afterwards by hand)
  const all = await post({ token, ops: [] }), dels = [];
  for (const k of L.TABLES) for (const r of all.tables[k]) if (String(r.id).startsWith("zt-") && !r.void) dels.push({ opId: L.newId("o"), table: k, row: { id: r.id, void: 1, upd: ++t } });
  const dr = await post({ token, ops: dels });
  ok(dr.ok && L.TABLES.every((k) => dr.tables[k].filter((r) => String(r.id).startsWith("zt-") && !r.void).length === 0), `every test row marked Deleted (${dels.length})`);
  ok(L.TABLES.every((k) => dr.tables[k].filter((r) => !String(r.id).startsWith("zt-")).length === before[k]), "no other row was touched");
  const fails = checks.filter((c) => !c[0]).length;
  return { pass: checks.length - fails, fail: fails, checks, timing_ms: first._ms };
}
