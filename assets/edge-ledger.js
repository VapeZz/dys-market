"use strict";
/* DYS Edge: Ledger (milestone M2; loaded by edge.js; owner only).

   Purchases, sales, expenses, cash and inventory (raw, graded, sealed) in two books, Business and Personal,
   with realized and unrealized profit and a tax-year export. The record lives in the owner's Google Sheet
   (tools/ledger/Code.gs, a web app bound to that Sheet); this phone keeps a copy and a queue of changes, so
   it works with no signal at a card show and catches up when it's back online.

   Tables (one tab each in the Sheet; all money in cents here, dollars in the Sheet; days are "YYYY-MM-DD"):
     buys   id, day, book, where, from, pay, tax, ship, fees, note
     items  id, buy, day, book, kind, tcg, g, n, name, set, cond, grader, grade, cert, qty, price (each), status, note
     sales  id, day, item, book, qty, plat, price (total for qty), shipIn (charged to the buyer), fees, shipOut, supplies, other, note
     costs  id, day, book, item (optional), kind, amount, note          money spent that isn't a buy
     cash   id, day, book, kind, amount, to, note                       starting cash, money in/out, moves between books
   Every row also has upd (when it last changed, ms) and void (1 = deleted; kept so the Sheet keeps the history).

   The math (all exact in cents):
     an item's cost = its price × qty + its share of the buy's tax, shipping and fees (by price) + costs tied to it
     a sale's cost  = the matching slice of that cost (first sale to last, rounded so the slices add up exactly)
     a sale's net   = price + shipping charged − fees − shipping paid − supplies − other
     profit         = net − cost
     cash per book  = starting cash + money in − money out ± moves + sales' net − buys − costs
   Market value comes from Edge's own prices (priceOf); an item with no price is left out of value and counted.

   Records for the owner's own use; not tax advice. */
(() => {
  const VERSION = 1;
  const TABLES = ["buys", "items", "sales", "costs", "cash"];
  const BOOKS = ["Business", "Personal"];
  const WHERE = ["Card show", "Online", "Store", "Local", "Trade", "Other"];
  const PAY = ["Cash", "Card", "Trade", "Other"];
  const KINDS = ["Raw", "Graded", "Sealed", "Other"];
  const STATUS = ["", "At grading", "Listed"];
  const PLATS = ["eBay", "TCGplayer", "Whatnot", "Shopify", "Card show", "Local", "Facebook Marketplace", "OfferUp", "Vinted", "Trade", "Other"];
  const NO_SHIP = ["Card show", "Local", "Trade", "Facebook Marketplace", "OfferUp", "Vinted"];   // in person, or the buyer pays the label (Vinted)
  const NO_SUP = ["Card show", "Local", "Trade", "Facebook Marketplace", "OfferUp"];
  const PLAT_FEES = { eBay: "ebay", TCGplayer: "tcgplayer", Whatnot: "whatnot" };     // fee estimate from Edge's fee file; others: typed in
  const COST_KINDS = ["Grading", "Supplies", "Shipping", "Show table", "Subscription", "Other"];
  const CASH_KINDS = ["Starting cash", "Money in", "Money out", "Move"];
  const LONG_DAYS = 365;          // held more than a year: long-term (US)
  const MONEY = { buys: ["tax", "ship", "fees"], items: ["price"], sales: ["price", "shipIn", "fees", "shipOut", "supplies", "other"], costs: ["amount"], cash: ["amount"] };

  /* ---------- small helpers ---------- */
  const int = (v) => { const n = Math.round(Number(v)); return isFinite(n) ? n : 0; };
  const dayNum = (d) => d ? Math.floor(Date.parse(d + "T00:00:00Z") / 864e5) : null;
  const yearOf = (d) => String(d || "").slice(0, 4);
  const live = (rows) => (rows || []).filter((r) => r && !r.void);
  const byDay = (a, b) => (a.day || "").localeCompare(b.day || "") || String(a.id).localeCompare(String(b.id));
  // split an amount over weights so the parts add up exactly (largest remainder; ties go to the earlier line)
  function allocate(amount, weights) {
    const tot = weights.reduce((s, w) => s + Math.max(0, w), 0), n = weights.length;
    if (!n) return [];
    if (!tot) { const base = Math.trunc(amount / n), out = weights.map(() => base); let r = amount - base * n; for (let i = 0; r && i < n; i++, r -= Math.sign(r)) out[i] += Math.sign(r); return out; }
    const raw = weights.map((w) => amount * Math.max(0, w) / tot), out = raw.map((x) => Math.trunc(x));
    let rest = amount - out.reduce((s, x) => s + x, 0);
    const order = raw.map((x, i) => [Math.abs(x - Math.trunc(x)), i]).sort((a, b) => b[0] - a[0] || a[1] - b[1]);
    for (let k = 0; rest !== 0 && k < order.length * 2; k++) { const i = order[k % order.length][1]; out[i] += Math.sign(rest); rest -= Math.sign(rest); }
    return out;
  }
  const newId = (prefix, rand = Math.random) => `${prefix}${Date.now().toString(36)}${Math.floor(rand() * 1e8).toString(36).padStart(5, "0")}`;
  const PREFIX = { buys: "b", items: "i", sales: "s", costs: "c", cash: "m" };
  const blank = () => ({ buys: [], items: [], sales: [], costs: [], cash: [] });

  /* ---------- the books ---------- */
  /* T: the five tables. opt: { priceOf(item) → cents per unit or null, asOf: "YYYY-MM-DD" (rows after it ignored), year } */
  function compute(T, opt = {}) {
    const asOf = opt.asOf || null, inScope = (r) => !asOf || !r.day || r.day <= asOf;
    const buys = live(T.buys).filter(inScope), items = live(T.items).filter(inScope), sales = live(T.sales).filter(inScope).sort(byDay);
    const costs = live(T.costs).filter(inScope), cash = live(T.cash).filter(inScope);
    const year = opt.year || yearOf(asOf || opt.today || new Date().toISOString());
    const IT = new Map(items.map((x) => [x.id, { ...x, qty: Math.max(0, int(x.qty)), price: int(x.price), base: int(x.price) * Math.max(0, int(x.qty)), extra: 0, added: 0, sold: 0, soldCost: 0, sales: [] }]));
    const B = new Map(), warn = [];
    for (const b of buys) {
      const lines = [...IT.values()].filter((x) => x.buy === b.id), gross = lines.reduce((s, x) => s + x.base, 0);
      const extras = int(b.tax) + int(b.ship) + int(b.fees), parts = allocate(extras, lines.map((x) => x.base));
      lines.forEach((x, i) => { x.extra = parts[i]; });
      B.set(b.id, { ...b, lines: lines.map((x) => x.id), gross, extras, total: gross + extras });
    }
    for (const c of costs) if (c.item) { const x = IT.get(c.item); if (x) x.added += int(c.amount); else warn.push(`cost ${c.id}: its item is gone`); }
    for (const x of IT.values()) x.cost = x.base + x.extra + x.added;
    const S = [];
    for (const s of sales) {
      const x = IT.get(s.item), q = Math.max(0, int(s.qty)) || 1;
      const net = int(s.price) + int(s.shipIn) - int(s.fees) - int(s.shipOut) - int(s.supplies) - int(s.other);
      let cost = 0, held = null;
      if (x) {
        const before = x.sold, after = before + q, slice = (k) => x.qty ? Math.round(x.cost * Math.min(k, x.qty) / x.qty) : 0;
        cost = slice(after) - slice(before);
        if (after > x.qty) warn.push(`${x.name || x.id}: sold ${after} of ${x.qty}`);
        x.sold = after; x.soldCost += cost; x.sales.push(s.id);
        const a = dayNum(x.day), d = dayNum(s.day); held = a != null && d != null ? d - a : null;
      } else warn.push(`sale ${s.id}: its item is gone`);
      S.push({ ...s, qty: q, net, cost, profit: net - cost, held, term: held == null ? "" : held > LONG_DAYS ? "Long" : "Short",
        proceeds: int(s.price) + int(s.shipIn), selling: int(s.fees) + int(s.shipOut) + int(s.supplies) + int(s.other), name: x ? x.name : "", kind: x ? x.kind : "", bought: x ? x.day : "" });
    }
    const priceOf = opt.priceOf || (() => null);
    const I = [...IT.values()].map((x) => {
      const left = Math.max(0, x.qty - x.sold), costLeft = x.cost - x.soldCost, each = left ? priceOf(x) : null;
      const value = each == null || !isFinite(each) ? null : Math.round(each) * left;
      return { ...x, left, costLeft, costEach: x.qty ? Math.round(x.cost / x.qty) : 0, value, gain: value == null ? null : value - costLeft };
    });
    const tot = {}, mk = () => ({ cash: 0, held: 0, units: 0, costHeld: 0, value: 0, valued: 0, unvalued: 0, unreal: 0, costValued: 0,
      sales: 0, proceeds: 0, selling: 0, cogs: 0, realized: 0, expenses: 0, net: 0, bought: 0, buys: 0 });
    for (const k of [...BOOKS, "All"]) tot[k] = mk();
    const add = (book, f) => { for (const k of [BOOKS.includes(book) ? book : "Business", "All"]) f(tot[k]); };
    for (const c of cash) {
      const a = int(c.amount);
      if (c.kind === "Money out") add(c.book, (t) => { t.cash -= a; });
      else if (c.kind === "Move") { if (c.to && c.to !== c.book) { add(c.book, (t) => { t.cash -= a; }); add(c.to, (t) => { t.cash += a; }); } }   // both sides land in All too, so they cancel there
      else add(c.book, (t) => { t.cash += a; });
    }
    for (const b of B.values()) add(b.book, (t) => { t.cash -= b.total; if (yearOf(b.day) === year) { t.bought += b.total; t.buys++; } });
    for (const c of costs) add(c.book, (t) => { t.cash -= int(c.amount); if (!c.item && yearOf(c.day) === year) t.expenses += int(c.amount); });
    for (const s of S) add(s.book, (t) => { t.cash += s.net; if (yearOf(s.day) === year) { t.sales++; t.proceeds += s.proceeds; t.selling += s.selling; t.cogs += s.cost; t.realized += s.profit; } });
    for (const x of I) if (x.left) add(x.book, (t) => { t.held++; t.units += x.left; t.costHeld += x.costLeft; if (x.value == null) t.unvalued++; else { t.valued++; t.value += x.value; t.costValued += x.costLeft; t.unreal += x.gain; } });
    for (const t of Object.values(tot)) t.net = t.realized - t.expenses;
    return { items: I, sales: S, buys: [...B.values()], costs, cash, tot, year, warn };
  }
  /* ---------- tax-year export (CSV) ---------- */
  const cell = (v) => {
    if (v == null) return "";
    let s = String(v);
    if (typeof v === "string" && /^[=+\-@\t\r]/.test(s) && !/^-?\d+(\.\d+)?$/.test(s)) s = "'" + s;      // a spreadsheet must not read text as a formula (numbers stay numbers)
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = (rows) => rows.map((r) => r.map(cell).join(",")).join("\r\n") + "\r\n";
  const usd = (c) => c == null ? "" : (c / 100).toFixed(2);
  function exportYear(T, year, book = "All") {
    const y = String(year), end = `${y}-12-31`, R = compute(T, { asOf: end, year: y }), pick = (b) => book === "All" || b === book;
    const sales = [["Date sold", "Date acquired", "Book", "Item", "Kind", "Qty", "Sold on", "Sale price", "Shipping charged", "Proceeds", "Marketplace fees", "Shipping paid", "Supplies", "Other selling costs", "Net", "Cost basis", "Profit", "Days held", "Holding period", "Note"]];
    for (const s of R.sales) if (yearOf(s.day) === y && pick(s.book)) sales.push([s.day, s.bought, s.book, s.name, s.kind, s.qty, s.plat, usd(int(s.price)), usd(int(s.shipIn)), usd(s.proceeds), usd(int(s.fees)), usd(int(s.shipOut)), usd(int(s.supplies)), usd(int(s.other)), usd(s.net), usd(s.cost), usd(s.profit), s.held ?? "", s.term, s.note || ""]);
    const names = new Map(R.items.map((x) => [x.id, x.name]));
    const expenses = [["Date", "Book", "Category", "Amount", "Added to an item's cost", "Item", "Note"]];
    for (const c of R.costs.slice().sort(byDay)) if (yearOf(c.day) === y && pick(c.book)) expenses.push([c.day, c.book, c.kind, usd(int(c.amount)), c.item ? "Yes" : "No", c.item ? names.get(c.item) || "" : "", c.note || ""]);
    const purchases = [["Date", "Book", "Where", "From", "Paid with", "Items", "Subtotal", "Tax", "Shipping", "Fees", "Total", "Note"]];
    for (const b of R.buys.slice().sort(byDay)) if (yearOf(b.day) === y && pick(b.book)) purchases.push([b.day, b.book, b.where, b.from || "", b.pay, b.lines.map((id) => names.get(id)).join("; "), usd(b.gross), usd(int(b.tax)), usd(int(b.ship)), usd(int(b.fees)), usd(b.total), b.note || ""]);
    const inventory = [["Book", "Item", "Kind", "Grade", "Acquired", "Qty held", "Cost basis held"]];
    for (const x of R.items.slice().sort(byDay)) if (x.left && pick(x.book)) inventory.push([x.book, x.name, x.kind, x.kind === "Graded" ? `${x.grader || ""} ${x.grade || ""}`.trim() : x.cond || "", x.day, x.left, usd(x.costLeft)]);
    const books = book === "All" ? [...BOOKS, "All"] : [book], t = (k) => R.tot[k];
    const line = (label, f) => [label, ...books.map((k) => usd(f(t(k))))];
    const summary = [[`DYS Edge ledger, tax year ${y}`, ...books.map((k) => k === "All" ? "Both books" : k)],
      line("Sales proceeds (price + shipping charged)", (x) => x.proceeds),
      line("Selling costs (fees, shipping, supplies)", (x) => x.selling),
      line("Cost of items sold", (x) => x.cogs),
      line("Profit on sales", (x) => x.realized),
      line("Other expenses (not added to an item)", (x) => x.expenses),
      line("Net", (x) => x.net),
      line(`Purchases in ${y}`, (x) => x.bought),
      line(`Inventory at cost on ${end}`, (x) => x.costHeld),
      [], ["Records from DYS Edge for the owner's own use. Not tax advice: give these files to your tax preparer."],
      ["Holding period: Long = held more than 365 days. Collectibles held long-term can be taxed differently; ask your preparer."]];
    return { sales: csv(sales), expenses: csv(expenses), purchases: csv(purchases), inventory: csv(inventory), summary: csv(summary), counts: { sales: sales.length - 1, expenses: expenses.length - 1, purchases: purchases.length - 1, inventory: inventory.length - 1 } };
  }
  // the Sheet's Summary tab: this year by book, written on each sync
  function summaryRows(R, at) {
    const k = [...BOOKS, "All"], t = R.tot, row = (label, f) => [label, ...k.map((b) => f(t[b]) / 100)];
    return [["DYS Edge ledger", "Business", "Personal", "Both books"],
      row("Cash (money in − money out)", (x) => x.cash), row("Inventory held, at cost", (x) => x.costHeld), row("Market value of what has a price", (x) => x.value),
      row("Unrealized gain on those", (x) => x.unreal), row(`Profit on sales in ${R.year}`, (x) => x.realized), row(`Other expenses in ${R.year}`, (x) => x.expenses),
      row(`Net in ${R.year}`, (x) => x.net), [], [`Updated from Edge ${at}. Market values are TCGplayer market prices (raw by condition) and graded sold prices where Edge has them; items with no price are left out.`, "", "", ""]];
  }

  // the columns the Sheet shows but Edge works out (Code.gs SHOWN), for every live row
  const shownRows = (R) => ({ buys: R.buys.map((b) => [b.id, b.total]), items: R.items.map((x) => [x.id, x.costEach, x.left]),
    sales: R.sales.map((s) => [s.id, s.name, s.net, s.cost, s.profit]) });

  /* ---------- this phone's copy and the sync queue ---------- */
  /* storage: localStorage-like. The Sheet is the record; the queue holds changes it hasn't confirmed yet. */
  function Store(storage, key = "dys-edge-ledger", clock = () => Date.now(), rand = Math.random) {
    let st;
    const read = () => { try { const d = JSON.parse(storage.getItem(key) || "null"); if (d && d.v === 1) return { ...d, T: { ...blank(), ...d.T } }; } catch {} return { v: 1, T: blank(), q: [], pulled: 0, err: "", migrated: false, sheet: "" }; };
    const write = () => { try { storage.setItem(key, JSON.stringify(st)); return true; } catch { return false; } };
    st = read();
    const apply = (T, op) => {
      const rows = T[op.table]; if (!rows) return;
      const i = rows.findIndex((r) => r.id === op.row.id);
      if (i < 0) rows.push({ ...op.row }); else if ((op.row.upd || 0) >= (rows[i].upd || 0)) rows[i] = { ...rows[i], ...op.row };
    };
    let last = 0;
    const stamp = () => { const t = Math.max(clock(), last + 1); last = t; return t; };
    const api = {
      get T() { return st.T; }, get queue() { return st.q.length; }, get state() { return st; },
      put(table, row) {
        if (!TABLES.includes(table)) throw new Error(`no table ${table}`);
        const r = { ...row, id: row.id || newId(PREFIX[table], rand), upd: stamp() };
        const op = { opId: newId("o", rand), table, row: r }; apply(st.T, op); st.q.push(op); write(); return r;
      },
      remove(table, id) { const cur = st.T[table].find((r) => r.id === id); if (!cur) return null; return api.put(table, { ...cur, void: 1 }); },
      set(k, v) { st[k] = v; write(); },
      // one round trip: send what's queued, take back every table. send(body) → { ok, tables, sheet } (the caller does the network)
      async sync(send, extra = {}) {
        const ops = st.q.slice(0, 200);
        let res; try { res = await send({ ops, ...extra }); } catch (e) { st.err = "offline"; write(); return { ok: false, reason: "offline" }; }
        if (!res || !res.ok) { st.err = (res && res.error) || "error"; write(); return { ok: false, reason: st.err }; }
        if (!res.tables || TABLES.some((k) => !Array.isArray(res.tables[k]))) { st.err = "bad reply"; write(); return { ok: false, reason: st.err }; }   // never wipe this phone's copy on a bad reply
        const sent = new Set(ops.map((o) => o.opId));
        st.q = st.q.filter((o) => !sent.has(o.opId));
        const T = blank(); for (const k of TABLES) T[k] = (res.tables && res.tables[k]) || [];
        for (const op of st.q) apply(T, op);            // changes made while this request was out stay on top
        st.T = T; st.pulled = clock(); st.err = ""; if (res.sheet) st.sheet = res.sheet; write();
        return { ok: true, sent: ops.length, left: st.q.length };
      },
      saveOk: write
    };
    return api;
  }

  /* ---------- building rows from the forms ---------- */
  // a buy: one row for the purchase and one per line (each line is an item)
  function buyRows(f, rand = Math.random) {
    const buy = { id: f.buyId || newId("b", rand), day: f.day, book: f.book, where: f.where, from: f.from || "", pay: f.pay, tax: int(f.tax), ship: int(f.ship), fees: int(f.fees), note: f.note || "" };
    const items = (f.lines || []).map((l) => ({ id: l.id || newId("i", rand), buy: buy.id, day: f.day, book: f.book, kind: l.kind || "Raw", tcg: l.tcg || "", g: l.g || "", n: l.n || "",
      name: l.name || "Item", set: l.set || "", cond: l.kind === "Raw" ? l.cond || "NM" : "", grader: l.kind === "Graded" ? l.grader || "PSA" : "", grade: l.kind === "Graded" ? String(l.grade || "") : "",
      cert: l.cert || "", qty: Math.max(1, int(l.qty) || 1), price: Math.max(0, int(l.price)), status: "", note: l.note || "" }));
    return { buy, items };
  }
  // a buy line for a card or sealed product picked in Edge (c: { id, g, n, t, price, set })
  const lineFromCard = (c) => ({ kind: c.t === "s" ? "Sealed" : "Raw", tcg: c.id, g: c.g, n: c.n, name: c.n, set: c.set || "", qty: 1, cond: "NM", price: Math.max(0, int(c.price)) });
  // a moved inventory row's ledger ID comes from the row itself, so moving it twice gives the same item, not two
  const migId = (o) => { let h = 0x811c9dc5; for (const ch of `${o.k}|${o.at || ""}|${o.cost}`) { h ^= ch.charCodeAt(0); h = Math.imul(h, 0x01000193) >>> 0; } return `iv${h.toString(36)}${String(o.id).slice(-4)}`; };
  // a grade as graders give it: 1 to 10, halves allowed (9.5)
  const okGrade = (g) => /^(10|[1-9](\.5)?)$/.test(String(g || "").trim());
  const netOf = (s) => int(s.price) + int(s.shipIn) - int(s.fees) - int(s.shipOut) - int(s.supplies) - int(s.other);

  /* ---------- screens (Mine → Ledger) ---------- */
  /* ctx from edge.js: { store, h (helpers: money, signed, esc, img, cleanN, localDay, fmtDay, cents, dollars, toast, cls, pct),
       priceOf(item), feeEst(platKey, priceCents, t) → cents, shipEst(priceCents, t), supplies(t), pick(form) (search for cards to add to form.lines), resume (a form to reopen),
       conn() → { url, token } | null, sync() → Promise, oldInv() → [rows], archiveOldInv() → keeps a copy, true if saved, backup() (backup file), openCard(id, g, n), draft (prefill a buy) } */
  function mount(root, ctx) {
    const { money: short, esc, img, cleanN, localDay, fmtDay, cents, dollars, toast, cls } = ctx.h;
    // the ledger shows every amount to the cent (Edge's money() rounds $1,000+ to whole dollars); the tiles stay short
    const money = (c, whole) => whole ? short(c, true) : c == null || !isFinite(c) ? "—" : (c < 0 ? "−" : "") + "$" + (Math.abs(c) / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const signed = (c, whole) => c == null || !isFinite(c) ? "—" : (c >= 0 ? "+" : "") + money(c, whole);
    const st = ctx.store;
    let view = ctx.view || "home", book = ctx.book || "All", year = yearOf(localDay()), form = null, fc = null;   // fc: the open form's click handler
    const $ = (q) => root.querySelector(q), $$ = (q) => [...root.querySelectorAll(q)];
    const opt = (list, v) => list.map((x) => `<option${x === v ? " selected" : ""}>${esc(x)}</option>`).join("");
    const inBook = (b) => book === "All" || b === book;
    const R = () => compute(st.T, { priceOf: ctx.priceOf, today: localDay() });
    const pic = (x) => x.tcg ? img(x.tcg) : `<span class="ph"></span>`;
    const syncLine = () => {
      const s = st.state, c = ctx.conn();
      if (!c) return `<p class="small muted lg-sync">Not connected to your Google Sheet yet: everything is saved on this phone${st.queue ? ` (${st.queue} change${st.queue === 1 ? "" : "s"} to send)` : ""}.</p>`;
      if (st.queue) return `<p class="small warn lg-sync">${st.queue} change${st.queue === 1 ? "" : "s"} waiting to reach your Sheet${s.err === "offline" ? " (no connection; they go when you're back online)" : s.err ? ` (${esc(s.err === "denied" ? "the Sheet refused this phone" : s.err)})` : "…"}. <button type="button" class="btn sm" data-a="sync">Send now</button></p>`;
      return `<p class="small muted lg-sync">Synced with your Sheet${s.pulled ? ` ${ago(s.pulled)}` : ""}.${s.sheet ? ` <a href="${esc(s.sheet)}" target="_blank" rel="noopener">Open Sheet ↗</a>` : ""} <button type="button" class="btn sm ghost" data-a="sync">Refresh</button></p>`;
    };
    const ago = (t) => { const m = Math.round((Date.now() - t) / 6e4); return m < 1 ? "just now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`; };
    const books = () => `<div class="seg lg-books" role="group" aria-label="Book">${["All", ...BOOKS].map((b) => `<button type="button" data-book="${b}" aria-pressed="${b === book}">${b === "All" ? "Both books" : b}</button>`).join("")}</div>`;
    const views = () => `<div class="seg" role="group" aria-label="Ledger">${[["home", "Overview"], ["items", "Items"], ["act", "Activity"], ["tax", "Export"]].map(([k, l]) => `<button type="button" data-view="${k}" aria-pressed="${k === view}">${l}</button>`).join("")}</div>`;

    function draw() {
      if (form) return drawForm();
      fc = null;
      const r = R();
      root.innerHTML = `${views()}${books()}${syncLine()}<div id="lg-body"></div>`;
      const body = $("#lg-body");
      ({ home: home, items: itemsView, act: activity, tax: taxView }[view] || home)(body, r);
    }
    function home(el, r) {
      const t = r.tot[book], old = ctx.oldInv ? ctx.oldInv() : [];
      el.innerHTML = `${old.length && !st.state.migrated ? `<div class="panel lg-move"><b>Move your inventory into the ledger</b>
          <p class="small muted" style="margin:4px 0 8px">Your ${old.length} inventory item${old.length === 1 ? "" : "s"} on this phone become ledger items at what you paid, dated the day you added them. Your old list stays on this phone as it is; nothing is deleted. Save a backup file first, then pick the book they're in.</p>
          <div class="btns"><button type="button" class="btn" data-a="bk">1. Save a backup file</button></div>
          <div class="btns" style="margin-top:8px"><button type="button" class="btn primary" data-a="mig" data-b="Business">2. Move into Business</button><button type="button" class="btn" data-a="mig" data-b="Personal">2. Move into Personal</button></div></div>` : ""}
        <div class="btns lg-acts"><button type="button" class="btn primary" data-a="buy">+ Buy</button><button type="button" class="btn" data-a="sell">Sell</button><button type="button" class="btn" data-a="cost">+ Expense</button><button type="button" class="btn" data-a="cash">Cash</button></div>
        <div class="tiles lg-tiles">
          <div class="tile"><span class="lab">Cash</span><b class="${t.cash < 0 ? "down" : ""}">${money(t.cash, true)}</b><small>money in − money out</small></div>
          <div class="tile"><span class="lab">Holding</span><b>${money(t.costHeld, true)}</b><small>${t.units} item${t.units === 1 ? "" : "s"} at cost</small></div>
          <div class="tile"><span class="lab">Worth now</span><b>${t.valued ? money(t.value, true) : "—"}</b><small>${t.unvalued ? `${t.unvalued} with no price` : "market value"}</small></div>
          <div class="tile"><span class="lab">Unrealized</span><b class="${cls(t.unreal)}">${t.valued ? signed(t.unreal, true) : "—"}</b><small>on what has a price</small></div>
          <div class="tile"><span class="lab">Profit ${r.year}</span><b class="${cls(t.realized)}">${signed(t.realized, true)}</b><small>${t.sales} sale${t.sales === 1 ? "" : "s"}</small></div>
          <div class="tile"><span class="lab">Net ${r.year}</span><b class="${cls(t.net)}">${signed(t.net, true)}</b><small>after ${money(t.expenses)} expenses</small></div></div>
        ${r.warn.length ? `<p class="small warn">Check: ${r.warn.map(esc).join(" · ")}</p>` : ""}
        <h3 class="lg-h">Recent</h3>${feed(r, 6)}`;
    }
    const itemLine = (x, right) => `<button type="button" class="row lg-row" data-item="${esc(x.id)}">${pic(x)}<span style="min-width:0;display:flex;flex-direction:column;gap:2px">
        <span class="nm">${esc(cleanN(x.name))}</span><span class="st">${esc([x.kind === "Graded" ? `${x.grader} ${x.grade}` : x.kind === "Raw" ? x.cond : x.kind, x.set, book === "All" ? x.book : "", x.status].filter(Boolean).join(" · "))}</span></span>
        <span class="rt">${right}</span></button>`;
    let showSold = false;
    function itemsView(el, r) {
      const rows = r.items.filter((x) => inBook(x.book) && (showSold ? x.sold : x.left)).sort((a, b) => (b.value ?? b.costLeft) - (a.value ?? a.costLeft) || byDay(b, a));
      el.innerHTML = `<div class="btns"><button type="button" class="btn sm${showSold ? "" : " primary"}" data-a="held">Holding</button><button type="button" class="btn sm${showSold ? " primary" : ""}" data-a="soldl">Sold</button></div>
        ${rows.length ? `<div class="list">${rows.map((x) => itemLine(x, showSold
          ? `<b class="${cls(r.sales.filter((s) => s.item === x.id).reduce((a, s) => a + s.profit, 0))}">${signed(r.sales.filter((s) => s.item === x.id).reduce((a, s) => a + s.profit, 0))}</b><small class="muted">${x.sold} sold</small>`
          : `<b>${x.value != null ? money(x.value) : money(x.costLeft)}</b><small class="${x.gain == null ? "muted" : cls(x.gain)}">${x.gain == null ? "no price · at cost" : `${signed(x.gain)}${x.left > 1 ? ` · ${x.left}` : ""}`}</small>`)).join("")}</div>`
          : `<div class="empty"><b>${showSold ? "Nothing sold yet" : "Nothing held"}</b>${showSold ? "Sales you record show here with their profit." : "Tap + Buy on Overview, or Bought it on any card."}</div>`}`;
    }
    function feed(r, max) {
      const names = new Map(r.items.map((x) => [x.id, x.name]));
      const ev = [
        ...r.buys.filter((b) => inBook(b.book)).map((b) => ({ day: b.day, upd: b.upd, t: "buys", id: b.id, label: `Bought ${b.lines.length === 1 ? cleanN(names.get(b.lines[0]) || "") : `${b.lines.length} items`}`, sub: [b.where, b.from, book === "All" ? b.book : ""].filter(Boolean).join(" · "), amt: -b.total })),
        ...r.sales.filter((s) => inBook(s.book)).map((s) => ({ day: s.day, upd: s.upd, t: "sales", id: s.id, label: `Sold ${cleanN(s.name)}${s.qty > 1 ? ` ×${s.qty}` : ""}`, sub: `${s.plat} · profit ${signed(s.profit)}`, amt: s.net })),
        ...r.costs.filter((c) => inBook(c.book)).map((c) => ({ day: c.day, upd: c.upd, t: "costs", id: c.id, label: c.kind + (c.item ? `: ${cleanN(names.get(c.item) || "")}` : ""), sub: c.note || (book === "All" ? c.book : ""), amt: -int(c.amount) })),
        ...r.cash.filter((c) => inBook(c.book) || (c.kind === "Move" && inBook(c.to))).map((c) => ({ day: c.day, upd: c.upd, t: "cash", id: c.id, label: c.kind === "Move" ? `Moved ${c.book} → ${c.to}` : c.kind, sub: c.note || "",
          amt: c.kind === "Money out" ? -int(c.amount) : c.kind === "Move" ? (book === "All" ? 0 : c.to === book ? int(c.amount) : -int(c.amount)) : int(c.amount) }))
      ].sort((a, b) => (b.day || "").localeCompare(a.day || "") || (b.upd || 0) - (a.upd || 0));
      const rows = ev.slice(0, max || ev.length);
      return rows.length ? `<div class="list">${rows.map((e) => `<div class="row lg-ev"><span class="lg-day">${esc(fmtDay(e.day))}</span><span style="min-width:0;display:flex;flex-direction:column;gap:2px"><span class="nm">${esc(e.label)}</span><span class="st">${esc(e.sub)}</span></span>
          <span class="rt"><b class="${cls(e.amt)}">${e.amt ? signed(e.amt) : "—"}</b><button type="button" class="btn sm ghost danger" data-del="${e.t}|${esc(e.id)}" aria-label="Delete">Delete</button></span></div>`).join("")}</div>`
        : `<div class="empty"><b>No activity yet</b>Buys, sales, expenses and cash show here.</div>`;
    }
    function activity(el, r) { el.innerHTML = feed(r); }
    function taxView(el, r) {
      const years = [...new Set([yearOf(localDay()), ...live(st.T.sales).map((s) => yearOf(s.day)), ...live(st.T.buys).map((b) => yearOf(b.day)), ...live(st.T.costs).map((c) => yearOf(c.day))])].filter(Boolean).sort().reverse();
      if (!years.includes(year)) year = years[0];
      const x = exportYear(st.T, year, book);
      el.innerHTML = `<div class="panel"><div class="form"><label class="f">Tax year<select class="select" id="lg-y">${opt(years, year)}</select></label>
          <label class="f">Book<select class="select" id="lg-yb">${opt(["All", ...BOOKS], book)}</select></label></div>
        <p class="small muted">Files for your tax preparer (CSV, opens in Sheets or Excel): ${x.counts.sales} sales, ${x.counts.purchases} purchases, ${x.counts.expenses} expenses, ${x.counts.inventory} items held on Dec 31.</p>
        <div class="btns">${["summary", "sales", "purchases", "expenses", "inventory"].map((k) => `<button type="button" class="btn sm" data-csv="${k}">${k[0].toUpperCase() + k.slice(1)}</button>`).join("")}</div>
        <p class="small muted" style="margin:8px 0 0">Records for your own use, not tax advice. Long = held more than 365 days.</p></div>`;
      $("#lg-y").onchange = (e) => { year = e.target.value; draw(); };
      $("#lg-yb").onchange = (e) => { book = e.target.value; draw(); };
    }

    /* ---------- forms ---------- */
    // each form gets its row IDs when it opens, so saving it twice (a double tap, a retry) updates the same rows
    function open(kind, data = {}) { form = { kind, rowId: newId({ sell: "s", cost: "c", cash: "m" }[kind] || "x"), feeId: newId("c"), shipId: newId("c"), upId: newId("c"), ...data }; draw(); window.scrollTo && window.scrollTo(0, 0); }
    function close() { form = null; draw(); }
    const money$ = (id, label, v, full) => `<label class="f${full ? " full" : ""}">${label} $<input class="field" id="${id}" type="number" inputmode="decimal" min="0" step="0.01" value="${v ? dollars(v) : ""}" placeholder="0"></label>`;
    const day$ = (v) => `<label class="f">Date<input class="field" id="lf-day" type="date" value="${esc(v || localDay())}"></label>`;
    const book$ = (v) => `<label class="f">Book<select class="select" id="lf-book">${opt(BOOKS, v || ctx.defBook || "Business")}</select></label>`;
    function drawForm() {
      const f = form;
      ({ buy: buyForm, sell: sellForm, cost: costForm, cash: cashForm, item: itemPanel, grade: gradeForm, back: backForm, editgrade: editGradeForm }[f.kind])(f);
    }
    function lineHTML(l, i) {
      return `<div class="panel lg-line" data-line="${i}"><div class="lg-lh">${l.tcg ? img(l.tcg) : ""}<b>${esc(cleanN(l.name) || "New item")}</b><button type="button" class="btn sm ghost danger" data-rm="${i}">Remove</button></div>
        <div class="form">${l.tcg ? "" : `<label class="f full">Name<input class="field" data-k="name" value="${esc(l.name || "")}" placeholder="What is it?"></label>`}
          <label class="f">Type<select class="select" data-k="kind">${opt(KINDS, l.kind)}</select></label>
          ${l.kind === "Raw" ? `<label class="f">Condition<select class="select" data-k="cond">${opt(["NM", "LP", "MP", "HP", "DMG"], l.cond || "NM")}</select></label>`
            : l.kind === "Graded" ? `<label class="f">Grader<select class="select" data-k="grader">${opt(["PSA", "CGC", "BGS", "TAG", "SGC"], l.grader || "PSA")}</select></label><label class="f">Grade<input class="field" data-k="grade" inputmode="decimal" value="${esc(l.grade || "")}"></label><label class="f">Cert #<input class="field" data-k="cert" inputmode="numeric" value="${esc(l.cert || "")}"></label>` : `<span></span>`}
          <label class="f">Qty<input class="field" data-k="qty" type="number" inputmode="numeric" min="1" step="1" value="${l.qty || 1}"></label>
          <label class="f">Price each $<input class="field" data-k="price" type="number" inputmode="decimal" min="0" step="0.01" value="${l.price ? dollars(l.price) : ""}" placeholder="0"></label></div></div>`;
    }
    function buyForm(f) {
      f.lines ||= [];
      const gross = f.lines.reduce((s, l) => s + int(l.price) * (int(l.qty) || 1), 0), total = gross + int(f.tax) + int(f.ship) + int(f.fees);
      root.innerHTML = `<form class="lg-form" id="lf"><div class="sec-head"><h2>${f.id ? "Edit buy" : "Record a buy"}</h2><button type="button" class="more" data-a="close">Cancel</button></div>
        <div class="form">${day$(f.day)}${book$(f.book)}
          <label class="f">Where<select class="select" id="lf-where">${opt(WHERE, f.where || "Card show")}</select></label>
          <label class="f">Paid with<select class="select" id="lf-pay">${opt(PAY, f.pay || "Cash")}</select></label>
          <label class="f full">From (seller or shop, optional)<input class="field" id="lf-from" value="${esc(f.from || "")}"></label></div>
        <h3 class="lg-h">Items</h3>${f.lines.map(lineHTML).join("")}
        <div class="btns"><button type="button" class="btn" data-a="pick">+ Card or sealed from Edge</button><button type="button" class="btn ghost" data-a="addline">+ Something else</button></div>
        <h3 class="lg-h">On top of the price</h3>
        <div class="form">${money$("lf-tax", "Sales tax", f.tax)}${money$("lf-ship", "Shipping", f.ship)}${money$("lf-fees", "Fees", f.fees)}
          <label class="f full">Note<input class="field" id="lf-note" value="${esc(f.note || "")}"></label></div>
        <p class="lg-total">Total <b>${money(total)}</b>${f.lines.length > 1 && total !== gross ? ` <span class="small muted">· tax, shipping and fees split over the items by price</span>` : ""}</p>
        <div class="btns"><button type="submit" class="btn primary"${f.lines.length ? "" : " disabled"}>Save buy</button></div></form>`;
      const keep = () => {
        Object.assign(f, { day: $("#lf-day").value, book: $("#lf-book").value, where: $("#lf-where").value, pay: $("#lf-pay").value, from: $("#lf-from").value.trim(),
          tax: cents($("#lf-tax").value), ship: cents($("#lf-ship").value), fees: cents($("#lf-fees").value), note: $("#lf-note").value.trim() });
        $$("[data-line]").forEach((el) => { const l = f.lines[+el.dataset.line]; el.querySelectorAll("[data-k]").forEach((i) => { const k = i.dataset.k; l[k] = k === "price" ? cents(i.value) : k === "qty" ? Math.max(1, int(i.value) || 1) : i.value.trim(); }); });
      };
      $("#lf").onchange = (e) => { if (e.target.dataset.k === "kind") { keep(); draw(); } };
      $("#lf").oninput = () => { keep(); const g = f.lines.reduce((s, l) => s + int(l.price) * (int(l.qty) || 1), 0); const b = root.querySelector(".lg-total b"); if (b) b.textContent = money(g + int(f.tax) + int(f.ship) + int(f.fees)); };
      fc = (e) => {
        const a = e.target.closest("[data-a]")?.dataset.a, rm = e.target.closest("[data-rm]");
        if (rm) { keep(); f.lines.splice(+rm.dataset.rm, 1); draw(); return; }
        if (a === "close") close();
        else if (a === "addline") { keep(); f.lines.push({ kind: "Raw", qty: 1, cond: "NM" }); draw(); }
        else if (a === "pick") { keep(); ctx.pick(f); }        // Edge's search adds lines to f, then mounts this form again
      };
      $("#lf").onsubmit = (e) => {
        e.preventDefault(); keep();
        if (!f.lines.length) return;
        if (f.lines.some((l) => !l.name)) { toast("Every item needs a name"); return; }
        if (f.lines.some((l) => l.kind === "Graded" && !okGrade(l.grade))) { toast("Enter the grade for each graded card (like 10 or 9.5)"); return; }
        if (f.saved) return; f.saved = true;
        f.buyId ||= newId("b"); f.lines.forEach((l) => { l.id ||= newId("i"); });
        const { buy, items } = buyRows(f), paid = items.reduce((s, x) => s + x.price * x.qty, 0) + buy.tax + buy.ship + buy.fees;
        st.put("buys", buy); for (const x of items) st.put("items", x);
        toast(`Saved: ${items.length} item${items.length === 1 ? "" : "s"}, ${money(paid)}`);
        form = null; view = "home"; draw(); ctx.sync();
      };
    }
    function sellForm(f) {
      const r = R(), held = r.items.filter((x) => x.left && inBook(x.book) || x.id === f.item).sort((a, b) => a.name.localeCompare(b.name));
      const x = r.items.find((y) => y.id === f.item);
      if (!x) {
        root.innerHTML = `<div class="sec-head"><h2>What did you sell?</h2><button type="button" class="more" data-a="close">Cancel</button></div>
          ${held.length ? `<div class="list">${held.map((y) => itemLine(y, `<b>${money(y.costEach)}</b><small class="muted">cost${y.left > 1 ? ` · ${y.left} left` : ""}</small>`)).join("")}</div>` : `<div class="empty"><b>Nothing held</b>Record a buy first.</div>`}`;
        fc = (e) => { if (e.target.closest("[data-a=close]")) close(); const it = e.target.closest("[data-item]"); if (it) { f.item = it.dataset.item; draw(); } };
        return;
      }
      f.qty ||= 1; f.plat ||= "eBay"; f.day ||= localDay();
      const est = (p) => ({ fees: PLAT_FEES[f.plat] ? ctx.feeEst(PLAT_FEES[f.plat], p, x.kind === "Sealed" ? "s" : "c") : 0, shipOut: NO_SHIP.includes(f.plat) ? 0 : ctx.shipEst(p, x.kind === "Sealed" ? "s" : "c"), supplies: NO_SUP.includes(f.plat) ? 0 : ctx.supplies(x.kind === "Sealed" ? "s" : "c") });
      if (f.price == null) { f.price = x.value != null ? Math.round(x.value / x.left) : 0; Object.assign(f, est(f.price)); }
      const costNow = () => { const q = Math.min(x.left, Math.max(1, f.qty)), slice = (k) => Math.round(x.cost * Math.min(k, x.qty) / x.qty); return slice(x.sold + q) - slice(x.sold); };
      const show = () => { const n = netOf(f), c = costNow(); return `You keep <b>${money(n)}</b> · cost ${money(c)} · profit <b class="${cls(n - c)}">${signed(n - c)}</b>`; };
      root.innerHTML = `<form class="lg-form" id="lf"><div class="sec-head"><h2>Record a sale</h2><button type="button" class="more" data-a="close">Cancel</button></div>
        <div class="list">${itemLine(x, `<b>${money(x.costEach)}</b><small class="muted">cost each</small>`)}</div>
        <div class="form">${day$(f.day)}
          <label class="f">Sold on<select class="select" id="lf-plat">${opt(PLATS, f.plat)}</select></label>
          ${x.left > 1 ? `<label class="f">Qty (of ${x.left})<input class="field" id="lf-qty" type="number" inputmode="numeric" min="1" max="${x.left}" step="1" value="${f.qty}"></label>` : ""}
          ${money$("lf-price", `Sale price${x.left > 1 ? " (total)" : ""}`, f.price)}${money$("lf-shipin", "Shipping the buyer paid", f.shipIn)}
          ${money$("lf-fees", "Fees", f.fees)}${money$("lf-shipout", "Shipping you paid", f.shipOut)}${money$("lf-sup", "Supplies", f.supplies)}${money$("lf-other", "Other costs", f.other)}
          <label class="f full">Note<input class="field" id="lf-note" value="${esc(f.note || "")}"></label></div>
        <p class="small muted" style="margin:0">${PLAT_FEES[f.plat] ? `Fees, shipping and supplies start at Edge's estimate for ${esc(f.plat)}; type the real numbers from your order.` : "Type the fees, if any (a payment app's fee counts). Sales tax you collected isn't part of the sale price."}</p>
        <p class="lg-total" id="lf-out">${show()}</p>
        <div class="btns"><button type="submit" class="btn primary">Save sale</button></div></form>`;
      const keep = () => Object.assign(f, { day: $("#lf-day").value, plat: $("#lf-plat").value, qty: $("#lf-qty") ? Math.min(x.left, Math.max(1, int($("#lf-qty").value) || 1)) : 1,
        price: cents($("#lf-price").value), shipIn: cents($("#lf-shipin").value), fees: cents($("#lf-fees").value), shipOut: cents($("#lf-shipout").value), supplies: cents($("#lf-sup").value), other: cents($("#lf-other").value), note: $("#lf-note").value.trim() });
      $("#lf").oninput = (e) => { keep(); if (e.target.id === "lf-price" && !f.touched) { Object.assign(f, est(f.price)); ["fees", "shipOut", "supplies"].forEach((k) => { const i = $({ fees: "#lf-fees", shipOut: "#lf-shipout", supplies: "#lf-sup" }[k]); if (i) i.value = dollars(f[k]); }); }
        if (["lf-fees", "lf-shipout", "lf-sup"].includes(e.target.id)) f.touched = true; $("#lf-out").innerHTML = show(); };
      $("#lf-plat").onchange = () => { keep(); if (!f.touched) Object.assign(f, est(f.price)); draw(); };
      fc = (e) => { if (e.target.closest("[data-a=close]")) close(); };
      $("#lf").onsubmit = (e) => {
        e.preventDefault(); keep();
        if (f.saved) return; f.saved = true;
        st.put("sales", { id: f.rowId, day: f.day, item: x.id, book: x.book, qty: f.qty, plat: f.plat, price: f.price, shipIn: f.shipIn || 0, fees: f.fees || 0, shipOut: f.shipOut || 0, supplies: f.supplies || 0, other: f.other || 0, note: f.note || "" });
        if (x.status === "Listed" && f.qty >= x.left) st.put("items", { ...rawItem(x.id), status: "" });
        toast(`Sale saved · profit ${signed(netOf(f) - costNow())}`); form = null; view = "home"; draw(); ctx.sync();
      };
    }
    const rawItem = (id) => st.T.items.find((y) => y.id === id);
    function costForm(f) {
      const r = R(), held = r.items.filter((x) => x.left);
      root.innerHTML = `<form class="lg-form" id="lf"><div class="sec-head"><h2>Record an expense</h2><button type="button" class="more" data-a="close">Cancel</button></div>
        <div class="form">${day$(f.day)}${book$(f.book)}
          <label class="f">What for<select class="select" id="lf-kind">${opt(COST_KINDS, f.kindOf || "Supplies")}</select></label>${money$("lf-amt", "Amount", f.amount)}
          <label class="f full">Add it to an item's cost? (grading, for example)<select class="select" id="lf-item"><option value="">No: a general expense</option>${held.map((x) => `<option value="${esc(x.id)}"${x.id === f.item ? " selected" : ""}>${esc(cleanN(x.name))}${x.kind === "Graded" ? ` (${esc(x.grader)} ${esc(x.grade)})` : ""}</option>`).join("")}</select></label>
          <label class="f full">Note<input class="field" id="lf-note" value="${esc(f.note || "")}"></label></div>
        <div class="btns"><button type="submit" class="btn primary">Save expense</button></div></form>`;
      fc = (e) => { if (e.target.closest("[data-a=close]")) close(); };
      $("#lf").onsubmit = (e) => {
        e.preventDefault();
        const amount = cents($("#lf-amt").value); if (!amount) { toast("Enter an amount"); return; }
        const item = $("#lf-item").value, it = item ? rawItem(item) : null;
        if (f.saved) return; f.saved = true;
        st.put("costs", { id: f.rowId, day: $("#lf-day").value, book: it ? it.book : $("#lf-book").value, item, kind: $("#lf-kind").value, amount, note: $("#lf-note").value.trim() });
        toast("Expense saved"); form = null; draw(); ctx.sync();
      };
    }
    function cashForm(f) {
      root.innerHTML = `<form class="lg-form" id="lf"><div class="sec-head"><h2>Cash</h2><button type="button" class="more" data-a="close">Cancel</button></div>
        <p class="small muted" style="margin:0">Starting cash once per book, then money you put in or take out. A move shifts money from one book to the other.</p>
        <div class="form">${day$(f.day)}${book$(f.book)}
          <label class="f">Type<select class="select" id="lf-kind">${opt(CASH_KINDS, f.kindOf || "Starting cash")}</select></label>${money$("lf-amt", "Amount", f.amount)}
          <label class="f full" id="lf-tow"${(f.kindOf || "Starting cash") === "Move" ? "" : " hidden"}>To book<select class="select" id="lf-to">${opt(BOOKS, "Personal")}</select></label>
          <label class="f full">Note<input class="field" id="lf-note"></label></div>
        <div class="btns"><button type="submit" class="btn primary">Save</button></div></form>`;
      $("#lf-kind").onchange = (e) => { $("#lf-tow").hidden = e.target.value !== "Move"; };
      fc = (e) => { if (e.target.closest("[data-a=close]")) close(); };
      $("#lf").onsubmit = (e) => {
        e.preventDefault();
        const amount = cents($("#lf-amt").value), kind = $("#lf-kind").value, b = $("#lf-book").value, to = kind === "Move" ? $("#lf-to").value : "";
        if (!amount) { toast("Enter an amount"); return; }
        if (kind === "Move" && to === b) { toast("Pick the other book"); return; }
        if (f.saved) return; f.saved = true;
        st.put("cash", { id: f.rowId, day: $("#lf-day").value, book: b, kind, amount, to, note: $("#lf-note").value.trim() });
        toast("Saved"); form = null; draw(); ctx.sync();
      };
    }
    function itemPanel(f) {
      const r = R(), x = r.items.find((y) => y.id === f.item); if (!x) { close(); return; }
      const sales = r.sales.filter((s) => s.item === x.id), costs = r.costs.filter((c) => c.item === x.id);
      root.innerHTML = `<div class="sec-head"><h2>${esc(cleanN(x.name))}</h2><button type="button" class="more" data-a="close">Back</button></div>
        <div class="list">${itemLine(x, x.value != null ? `<b>${money(x.value)}</b><small class="${cls(x.gain)}">${signed(x.gain)}</small>` : `<b>${money(x.costLeft)}</b><small class="muted">no price</small>`)}</div>
        <div class="panel lg-kv"><div><span>Book</span><span>${esc(x.book)}</span></div><div><span>Bought</span><span>${esc(fmtDay(x.day))} ${esc(yearOf(x.day))}</span></div>
          ${x.kind === "Graded" ? `<div><span>Grade</span><span>${esc([x.grader, x.grade || "not entered"].join(" "))} · ${costs.some((c) => c.kind === "Grading") ? "you sent it for grading" : "bought graded"}</span></div>` : ""}
          <div><span>Qty</span><span>${x.qty}${x.sold ? ` · ${x.sold} sold · ${x.left} left` : ""}</span></div>
          <div><span>Price paid</span><span>${money(x.base)}</span></div>${x.extra ? `<div><span>Share of tax, shipping, fees</span><span>${money(x.extra)}</span></div>` : ""}
          ${costs.map((c) => `<div><span>${esc(c.kind)} ${esc(fmtDay(c.day))}</span><span>${money(int(c.amount))}</span></div>`).join("")}
          <div><b>Cost</b><b>${money(x.cost)}${x.qty > 1 ? ` · ${money(x.costEach)} each` : ""}</b></div>
          ${sales.map((s) => `<div><span>Sold ${esc(fmtDay(s.day))} on ${esc(s.plat)}${s.qty > 1 ? ` ×${s.qty}` : ""}</span><span class="${cls(s.profit)}">${money(s.net)} · ${signed(s.profit)}</span></div>`).join("")}
          ${x.cert ? `<div><span>Cert</span><span>${esc(x.cert)}</span></div>` : ""}${x.note ? `<div><span>Note</span><span>${esc(x.note)}</span></div>` : ""}</div>
        ${x.kind === "Graded" && x.left && x.tcg && ctx.checkSold ? `<section class="sec panel lg-sold"><span class="lab">What it sells for</span>
          <p class="small muted" style="margin:0">Real eBay sold prices for ${esc([x.grader, x.grade].join(" "))} copies of this exact card only, against the ${money(x.costEach)} you paid.</p>
          <div class="btns"><button type="button" class="btn primary" data-a="sold">Check sold prices</button></div><div id="lg-sold-box"></div></section>` : ""}
        <div class="btns">${x.left ? `<button type="button" class="btn${x.kind === "Graded" && ctx.checkSold ? "" : " primary"}" data-a="sell1">Sell</button>` : ""}
          ${x.left && x.kind === "Raw" && x.status !== "At grading" ? `<button type="button" class="btn" data-a="tograde">Send to grading</button>` : ""}
          ${x.status === "At grading" ? `<button type="button" class="btn" data-a="back">Back from grading</button>` : ""}
          ${x.left && x.status !== "At grading" ? `<button type="button" class="btn" data-a="list">${x.status === "Listed" ? "Not listed" : "Mark listed"}</button>` : ""}
          ${x.left ? `<button type="button" class="btn" data-a="move">Move to ${x.book === "Business" ? "Personal" : "Business"}</button>` : ""}
          ${x.kind === "Graded" ? `<button type="button" class="btn" data-a="editgrade">Edit grade</button>` : ""}
          ${x.tcg ? `<button type="button" class="btn ghost" data-a="card">Open card</button>` : ""}
          ${!sales.length ? `<button type="button" class="btn ghost danger" data-a="delitem">Delete</button>` : ""}</div>
        ${x.book === "Business" || !x.left ? "" : `<p class="small muted">Moving an item into Business keeps its cost; your tax preparer may want its value on the day you move it.</p>`}`;
      fc = (e) => {
        const a = e.target.closest("[data-a]")?.dataset.a; if (!a) return;
        const raw = rawItem(x.id);
        if (a === "close") { form = null; view = "items"; draw(); }
        else if (a === "sell1") open("sell", { item: x.id });
        else if (a === "tograde") open("grade", { item: x.id });
        else if (a === "back") open("back", { item: x.id });
        else if (a === "list") { st.put("items", { ...raw, status: x.status === "Listed" ? "" : "Listed" }); ctx.sync(); draw(); }
        else if (a === "move") { const to = x.book === "Business" ? "Personal" : "Business"; st.put("items", { ...raw, book: to, note: [raw.note, `Moved to ${to} ${localDay()}`].filter(Boolean).join(" · ") }); toast(`Moved to ${to}`); ctx.sync(); draw(); }
        else if (a === "editgrade") open("editgrade", { item: x.id });
        else if (a === "sold") { const b = e.target.closest("[data-a]"); b.closest(".btns").remove(); ctx.checkSold(x, $("#lg-sold-box")); }
        else if (a === "card") ctx.openCard(+x.tcg, +x.g, x.n);
        else if (a === "delitem") { if (!confirmIn(root, `Delete ${cleanN(x.name)} from the ledger?`, () => { st.remove("items", x.id); for (const c of st.T.costs.filter((c) => c.item === x.id && !c.void)) st.remove("costs", c.id); toast("Deleted"); form = null; view = "items"; draw(); ctx.sync(); })) return; }
      };
    }
    function gradeForm(f) {
      const x = rawItem(f.item);
      root.innerHTML = `<form class="lg-form" id="lf"><div class="sec-head"><h2>Send to grading</h2><button type="button" class="more" data-a="close">Cancel</button></div>
        <p class="small muted" style="margin:0">${esc(cleanN(x.name))}. The grading fee and shipping are added to its cost.</p>
        <div class="form">${day$()}<label class="f">Grader<select class="select" id="lf-gr">${opt(["PSA", "CGC", "BGS", "TAG", "SGC"], "PSA")}</select></label>
          ${money$("lf-fee", "Grading fee", f.fee)}${money$("lf-ship", "Shipping + insurance", f.ship)}</div>
        <div class="btns"><button type="submit" class="btn primary">Save</button></div></form>`;
      fc = (e) => { if (e.target.closest("[data-a=close]")) { open("item", { item: x.id }); } };
      $("#lf").onsubmit = (e) => {
        e.preventDefault();
        const day = $("#lf-day").value, gr = $("#lf-gr").value, fee = cents($("#lf-fee").value), ship = cents($("#lf-ship").value);
        st.put("items", { ...x, status: "At grading", grader: gr });
        if (fee) st.put("costs", { id: f.feeId, day, book: x.book, item: x.id, kind: "Grading", amount: fee, note: `${gr} grading fee` });
        if (ship) st.put("costs", { id: f.shipId, day, book: x.book, item: x.id, kind: "Shipping", amount: ship, note: `To ${gr} and back` });
        toast("Marked at grading"); open("item", { item: x.id }); ctx.sync();
      };
    }
    // fix a graded item's grader, grade or cert: the same row is updated; its price, cost and purchase are left alone
    function editGradeForm(f) {
      const x = rawItem(f.item);
      root.innerHTML = `<form class="lg-form" id="lf"><div class="sec-head"><h2>Edit grade</h2><button type="button" class="more" data-a="close">Cancel</button></div>
        <p class="small muted" style="margin:0">${esc(cleanN(x.name))}. Only the grade details change; what you paid stays ${money(int(x.price))}.</p>
        <div class="form"><label class="f">Grader<select class="select" id="lf-gr">${opt(["PSA", "CGC", "BGS", "TAG", "SGC"], x.grader || "PSA")}</select></label>
          <label class="f">Grade<input class="field" id="lf-grade" inputmode="decimal" value="${esc(x.grade || "")}"></label>
          <label class="f full">Cert # (optional)<input class="field" id="lf-cert" inputmode="numeric" value="${esc(x.cert || "")}"></label></div>
        <div class="btns"><button type="submit" class="btn primary">Save grade</button></div></form>`;
      fc = (e) => { if (e.target.closest("[data-a=close]")) open("item", { item: x.id }); };
      $("#lf").onsubmit = (e) => {
        e.preventDefault();
        const grade = $("#lf-grade").value.trim(); if (!okGrade(grade)) { toast("Enter the grade (like 10 or 9.5)"); return; }
        if (f.saved) return; f.saved = true;
        st.put("items", { ...rawItem(x.id), grader: $("#lf-gr").value, grade, cert: $("#lf-cert").value.trim() });
        toast(`Grade saved: ${$("#lf-gr").value} ${grade}`); open("item", { item: x.id }); ctx.sync();
      };
    }
    function backForm(f) {
      const x = rawItem(f.item);
      root.innerHTML = `<form class="lg-form" id="lf"><div class="sec-head"><h2>Back from grading</h2><button type="button" class="more" data-a="close">Cancel</button></div>
        <div class="form"><label class="f">Grader<select class="select" id="lf-gr">${opt(["PSA", "CGC", "BGS", "TAG", "SGC"], x.grader || "PSA")}</select></label>
          <label class="f">Grade<input class="field" id="lf-grade" inputmode="decimal"></label>
          <label class="f full">Cert #<input class="field" id="lf-cert" inputmode="numeric"></label>${money$("lf-up", "Upcharge or extra fees", 0, true)}</div>
        <div class="btns"><button type="submit" class="btn primary">Save</button></div></form>`;
      fc = (e) => { if (e.target.closest("[data-a=close]")) open("item", { item: x.id }); };
      $("#lf").onsubmit = (e) => {
        e.preventDefault();
        const grade = $("#lf-grade").value.trim(); if (!okGrade(grade)) { toast("Enter the grade (like 10 or 9.5)"); return; }
        st.put("items", { ...x, kind: "Graded", grader: $("#lf-gr").value, grade, cert: $("#lf-cert").value.trim(), cond: "", status: "" });
        const up = cents($("#lf-up").value); if (up) st.put("costs", { id: f.upId, day: localDay(), book: x.book, item: x.id, kind: "Grading", amount: up, note: "Upcharge / extra" });
        toast(`Graded ${$("#lf-gr").value} ${grade}`); open("item", { item: x.id }); ctx.sync();
      };
    }
    // an in-page confirm (browser dialogs are avoided in Edge)
    function confirmIn(el, msg, yes) {
      const box = document.createElement("div"); box.className = "inline-form lg-confirm";
      box.innerHTML = `<span>${esc(msg)}</span><div class="btns"><button type="button" class="btn primary danger">Delete</button><button type="button" class="btn ghost">Keep</button></div>`;
      el.prepend(box); box.scrollIntoView && box.scrollIntoView({ block: "nearest" });
      const [y, n] = box.querySelectorAll("button"); y.onclick = (e) => { e.stopPropagation(); box.remove(); yes(); }; n.onclick = (e) => { e.stopPropagation(); box.remove(); };
      return false;
    }

    /* ---------- list taps ---------- */
    function listClicks(e) {
      const b = e.target.closest("[data-book]"); if (b) { book = b.dataset.book; draw(); return; }
      const v = e.target.closest("[data-view]"); if (v) { view = v.dataset.view; draw(); return; }
      const it = e.target.closest("[data-item]"); if (it) { open("item", { item: it.dataset.item }); return; }
      const d = e.target.closest("[data-del]");
      if (d) { const [t, id] = d.dataset.del.split("|"); confirmIn($("#lg-body") || root, "Delete this entry? It's kept in the Sheet's history.", () => {
        st.remove(t, id);
        if (t === "buys") for (const x of st.T.items.filter((x) => x.buy === id && !x.void)) { if (live(st.T.sales).some((s) => s.item === x.id)) continue; st.remove("items", x.id); }
        toast("Deleted"); draw(); ctx.sync(); }); return; }
      const c = e.target.closest("[data-csv]");
      if (c) { const x = exportYear(st.T, year, book), k = c.dataset.csv; ctx.download(`dys-ledger-${year}-${book === "All" ? "both" : book.toLowerCase()}-${k}.csv`, x[k]); return; }
      const a = e.target.closest("[data-a]")?.dataset.a;
      if (a === "buy") open("buy", { book: book === "All" ? ctx.defBook : book });
      else if (a === "sell") open("sell", {});
      else if (a === "cost") open("cost", { book: book === "All" ? ctx.defBook : book });
      else if (a === "cash") open("cash", { book: book === "All" ? ctx.defBook : book });
      else if (a === "held") { showSold = false; draw(); }
      else if (a === "soldl") { showSold = true; draw(); }
      else if (a === "sync") ctx.sync().then(draw);
      else if (a === "bk") { ctx.backup(); toast("Backup file saved"); }
      else if (a === "mig") {
        const bk = e.target.closest("[data-b]").dataset.b, old = ctx.oldInv();
        if (st.state.migrated) return;
        if (!ctx.archiveOldInv()) { toast("Couldn't keep a copy on this phone. Save a backup file first."); return; }
        for (const o of old) st.put("items", { id: migId(o), buy: "", day: o.at || localDay(), book: bk, kind: o.t === "s" ? "Sealed" : "Raw", tcg: o.id, g: o.g, n: o.n, name: o.n, set: o.sn || "", cond: o.t === "s" ? "" : o.cond || "NM", grader: "", grade: "", cert: "", qty: o.qty || 1, price: o.cost || 0, status: "", note: "Moved from Edge inventory" });
        st.set("migrated", true); toast(`${old.length} item${old.length === 1 ? "" : "s"} moved into ${bk}`); draw(); ctx.sync();
      }
    }
    // one click handler: the open form's, or the lists' (so one tap is never handled twice)
    root.addEventListener("click", (e) => { if (form) { if (fc) fc(e); } else listClicks(e); });
    if (ctx.resume) { form = ctx.resume; draw(); }
    else if (ctx.draft) open("buy", { book: ctx.defBook, lines: [ctx.draft] });
    else draw();
    return { redraw: draw, open };
  }

  const api = { v: VERSION, TABLES, BOOKS, WHERE, PAY, KINDS, STATUS, PLATS, PLAT_FEES, COST_KINDS, CASH_KINDS, MONEY, LONG_DAYS,
    allocate, compute, exportYear, summaryRows, shownRows, Store, buyRows, lineFromCard, migId, okGrade, netOf, mount, newId, blank, csv };
  if (typeof window !== "undefined") window.EdgeLedger = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
