"use strict";
/* DYS Edge: the strategy box on a card's sheet (loaded by edge.js; owner only).

   It reads the chart's own numbers (edge-ta.js: averages, RSI, MACD, bands, 52-week range) and turns them
   into one call, the reasons, a price ladder and a risk level. Version 1: fixed rules, NOT backtested yet.
   Every rule and threshold is named below so the backtest can score each one on our own price history.

   Calls: Buy zone, Hold, Trim (sell part into strength), Sell (or stay out), Watch (no call yet).

   Which rules run:
   - No call (Watch): no price in the last 3 days, a price under MIN_PRICE, fewer than MIN_HISTORY days of
     prices, or no 30-day average.
   - Fast rules: the card has FAST_DAYS daily prices in a row and at least THIN_MOVES price moves in the last
     14 days, so RSI, MACD and the bands mean something. First match wins, in the order of FAST below.
   - Slow rules: everything else (about two cards in three are thin markets). They use only the 30 and
     90-day averages and the 52-week range. First match wins, in the order of SLOW below.

   Price ladder: supports under the price (30 and 90-day averages, lower band, 30-day low, 52-week low; the
   nearest two within BUY_REACH percent) are the buy levels, resistances over it (upper band, the averages,
   52-week high; the nearest one and the furthest) the sell levels. Levels within LEVEL_MERGE percent of each
   other are one rung. Each sell level shows what it would clear after fees if bought at today's price. Break-even
   is the lowest sale price that returns today's market price plus shipping in, after the selling fees in
   Mine > Settings. The cut level is CUT_UNDER percent under the lowest buy level shown (or under the price).

   Risk: points for a thin market, a wide 90-day range, a falling longer or short trend, short history, a new
   set, an overbought reading and a lot of money in one item. Under RISK_MED is Low, under RISK_HIGH Medium.

   Rules on TCGplayer market prices. Market data, not financial advice. */
(() => {
  const VERSION = 1, DAY = 864e5;
  /* ---------- thresholds (every number the calls rest on) ---------- */
  const MIN_PRICE = 100;      // cents: under $1 is bulk, no call
  const MIN_HISTORY = 35;     // days of prices on record before any call
  const FAST_DAYS = 35;       // daily prices in a row the fast rules need (MACD's signal line needs 34)
  const THIN_MOVES = 3;       // fewer price moves than this in 14 days: thin market, slow rules (as on the chart)
  const TREND_BAND = 2;       // percent between two averages before it counts as a trend (as on the chart)
  const RSI_HOT = 70, RSI_COLD = 30;  // overbought and oversold zones (as on the chart)
  const RSI_DIP = 45;         // RSI at or under this inside an uptrend: a pullback
  const RSI_PUSH = 55;        // RSI at or over this and under RSI_HOT: momentum without being overbought
  const BAND_DIP = 0.25;      // lower quarter of the bands: a pullback
  const BAND_TOP = 1;         // at or above the upper band
  const STRETCH = 10;         // percent above the 30-day average before overbought counts as stretched (a move big enough to matter after fees)
  const KNIFE = 10;           // percent under the 30-day average before oversold counts as a falling knife
  const NEAR_HIGH = 3;        // percent under the 52-week high that counts as at the high
  const DEEP_OFF = 30;        // percent under the 52-week high that counts as beaten down
  const NEAR_LOW = 15;        // percent above the 52-week low that counts as near the low (fast rules)
  const BASE_LOW = 10;        // the same for the slow rules
  const CROSS_DAYS = 10;      // a MACD cross this recent counts as a fresh turn
  const SLOW_JUMP = 15;       // percent above or below the 30-day average that counts as a jump on few sales
  const BREAKOUT_HISTORY = 90; // days of prices before a 52-week high means anything
  /* ladder */
  const LEVEL_GAP = 1;        // percent a level must sit from the price to be its own rung
  const LEVEL_MERGE = 1.5;    // levels closer together than this percent are one rung
  const BUY_REACH = 25;       // percent under the price: supports further down than this are not buy levels
  const CUT_UNDER = 3;        // percent under the lowest buy level shown (or the price) where the idea is wrong
  /* risk */
  const RISK_MED = 25, RISK_HIGH = 50;
  const NEW_SET_DAYS = 120;

  const CALLS = { buy: "Buy zone", hold: "Hold", trim: "Trim", sell: "Sell", watch: "Watch" };
  const TIERS = {
    easy: ["Easy", "one clear move on something you own"],
    average: ["Average", "needs a limit price and patience"],
    hard: ["Hard", "early or thin market, so small size and slow exits"],
  };
  /* id: [name, call, execution tier, what to do] */
  const SETUPS = {
    stale: ["No fresh price", "watch", null, "No price in the last 3 days, so no call."],
    bulk: ["Bulk price", "watch", null, "Under $1: fees and shipping eat any flip. No call."],
    young: ["Too new", "watch", null, "Not enough price history yet. Calls start at 35 days."],
    // fast rules, in the order they are tried
    stretched: ["Stretched", "trim", "easy", "Own it: sell part into this strength. Don't own it: don't chase."],
    knife: ["Falling knife", "watch", null, "Oversold but still falling. Wait for MACD to cross up before buying."],
    breakdown: ["Breakdown", "sell", "easy", "The trend is broken. Own it: sell. Don't own it: stay out."],
    turn: ["Bottom turning", "buy", "hard", "Early turn off the lows. Small first buy; add only if it holds."],
    dip: ["Dip in an uptrend", "buy", "average", "Pullback inside an uptrend. Buy here, add lower, cut if it breaks."],
    breakout: ["Breakout", "buy", "average", "Pushing at its high with momentum. Buy small; cut fast if it falls back."],
    ride: ["Uptrend", "hold", "easy", "Rising, and not stretched yet. Hold; buy only on a dip."],
    weak: ["Weak trend", "watch", null, "The longer trend is down and nothing has turned. Wait."],
    none: ["No setup", "hold", "easy", "Nothing lines up. Hold what you own; no new buy."],
    // slow rules (thin market or too few daily prices), in the order they are tried
    "s-spike": ["Jump on few sales", "trim", "average", "Price jumped on few sales. Own it: list it now. Don't own it: don't chase."],
    "s-drop": ["Drop on few sales", "watch", null, "Price dropped on few sales. Check live listings before you believe it."],
    "s-down": ["Slow downtrend", "sell", "average", "Slow, steady decline. Own it: sell. Don't own it: stay out."],
    "s-base": ["Flat near its low", "watch", "hard", "Flat near its low. A stack candidate once it starts to turn; not yet."],
    "s-dip": ["Slow dip in an uptrend", "buy", "hard", "Longer trend up, price back under its 30-day average. Small buy; exits are slow."],
    "s-up": ["Slow uptrend", "hold", "easy", "Rising slowly. Hold; buy only on a dip."],
    "s-none": ["Quiet", "hold", "easy", "Quiet. Hold what you own; no new buy."],
  };
  const FAST = ["stretched", "knife", "breakdown", "turn", "dip", "breakout", "ride", "weak", "none"];
  const SLOW = ["s-spike", "s-drop", "s-down", "s-base", "s-dip", "s-up", "s-none"];

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (c) => {
    if (c == null || !isFinite(c)) return "—";
    const neg = c < 0, d = Math.abs(c) / 100;
    return (neg ? "−" : "") + "$" + (d >= 1000 ? Math.round(d).toLocaleString("en-US") : d.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  };
  const signed = (c) => (c >= 0 ? "+" : "") + money(c);
  const pc = (x) => `${Math.abs(x).toFixed(1)}%`;
  const dayNum = (d) => Math.round(Date.parse(d + "T00:00:00Z") / DAY);
  const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;

  /* ---------- the numbers a call rests on ---------- */
  function facts(a) {
    const n = a && a.now;
    if (!n) return null;
    const last = n.last, v = last.v, pts = a.pts, today = a.today;
    const in30 = pts.filter((p) => p.t >= today - 30), in90 = pts.filter((p) => p.t >= today - 90);
    const min = (list) => list.reduce((m, p) => Math.min(m, p.v), Infinity), max = (list) => list.reduce((m, p) => Math.max(m, p.v), -Infinity);
    const a30 = last.a30 ?? null, a90 = last.a90 ?? null;
    const lo90 = min(in90), hi90 = max(in90);
    return {
      v, a7: last.a7 ?? null, a30, a90, gap: n.gap ?? null, trend: n.trend ?? null,
      long: a30 != null && a90 ? (a30 / a90 - 1) * 100 : null,      // the 30-day average against the 90-day one, percent
      vs30: a30 ? (v / a30 - 1) * 100 : null,                         // the price against its 30-day average, percent
      rsi: n.rsi ?? null, pctB: n.pctB ?? null, bu: n.bu ?? null, bl: n.bl ?? null, side: n.side ?? null, cross: n.cross ? n.cross.days : null,
      hi: n.hi ? n.hi.v : null, lo: n.lo ? n.lo.v : null, off: n.off ?? null, up: n.up ?? null,
      low30: min(in30), range90: lo90 > 0 ? (hi90 / lo90 - 1) * 100 : null,
      moves: n.moves, dailyDays: n.dailyDays, history: pts.length ? today - pts[0].t : 0, today,
    };
  }

  /* ---------- the rules ---------- */
  const TEST = {
    stretched: (f) => (f.rsi >= RSI_HOT || f.pctB >= BAND_TOP) && f.vs30 >= STRETCH,
    knife: (f) => f.rsi <= RSI_COLD && f.trend === "down" && f.side === "below" && f.vs30 <= -KNIFE,
    breakdown: (f) => f.trend === "down" && f.v < (f.a90 ?? f.a30) && f.side === "below",
    turn: (f) => f.off >= DEEP_OFF && f.up <= NEAR_LOW && f.side === "above" && f.cross != null && f.cross <= CROSS_DAYS && f.rsi > RSI_COLD,
    dip: (f) => f.long != null && f.long >= TREND_BAND && f.v >= f.a90 && (f.rsi <= RSI_DIP || f.pctB <= BAND_DIP),
    breakout: (f) => f.off <= NEAR_HIGH && f.side === "above" && f.rsi >= RSI_PUSH && f.rsi < RSI_HOT && f.trend === "up" && f.history >= BREAKOUT_HISTORY,
    ride: (f) => f.trend === "up" && (f.a90 == null || f.v >= f.a90),
    weak: (f) => f.long != null && f.long <= -TREND_BAND && f.v < f.a90,
    none: () => true,
    "s-spike": (f) => f.vs30 >= SLOW_JUMP,
    "s-drop": (f) => f.vs30 <= -SLOW_JUMP,
    "s-down": (f) => f.long != null && f.long <= -TREND_BAND && f.v <= f.a30,
    "s-base": (f) => f.off >= DEEP_OFF && f.up <= BASE_LOW && f.trend === "flat",
    "s-dip": (f) => f.long != null && f.long >= TREND_BAND && f.v < f.a30 && f.v >= f.a90,
    "s-up": (f) => f.long != null && f.long >= TREND_BAND && f.v >= f.a30,
    "s-none": () => true,
  };
  // which rule set a card gets, and the setup that matches
  function pick(f) {
    if (!f) return { id: "stale", mode: "none" };
    if (f.v < MIN_PRICE) return { id: "bulk", mode: "none" };
    if (f.history < MIN_HISTORY || f.a30 == null) return { id: "young", mode: "none" };
    const fast = f.moves >= THIN_MOVES && f.dailyDays >= FAST_DAYS && f.rsi != null && f.pctB != null && f.side != null;
    const list = fast ? FAST : SLOW;
    return { id: list.find((id) => TEST[id](f)), mode: fast ? "fast" : "slow" };
  }

  /* ---------- the reasons, in plain words ---------- */
  const say = {
    trend: (f) => f.gap == null ? null : Math.abs(f.gap) < 0.05 ? "7D avg level with the 30D avg" : `7D avg ${pc(f.gap)} ${f.gap > 0 ? "above" : "below"} the 30D avg`,
    long: (f) => f.long == null ? "No 90-day average yet" : Math.abs(f.long) < 0.05 ? "30D avg level with the 90D avg" : `30D avg ${pc(f.long)} ${f.long > 0 ? "above" : "below"} the 90D avg`,
    vs30: (f) => Math.abs(f.vs30) < 0.05 ? "Price level with its 30D avg" : `Price ${pc(f.vs30)} ${f.vs30 > 0 ? "above" : "below"} its 30D avg`,
    vs90: (f) => f.a90 == null ? null : `Price ${f.v >= f.a90 ? "above" : "below"} its 90D avg of ${money(f.a90)}`,
    rsi: (f) => `RSI ${f.rsi.toFixed(1)}${f.rsi >= RSI_HOT ? ": overbought (70 and up)" : f.rsi <= RSI_COLD ? ": oversold (30 and under)" : f.rsi <= RSI_DIP ? ": pulled back" : f.rsi >= RSI_PUSH ? ": strong, not overbought" : ": neutral"}`,
    band: (f) => f.pctB >= 1 ? "Price at or above the upper band" : f.pctB <= 0 ? "Price at or below the lower band" : `Price ${Math.round(f.pctB * 100)}% of the way up its bands`,
    macd: (f) => `MACD ${f.side} its signal line${f.cross == null ? "" : f.cross === 0 ? ", crossed today" : `, crossed ${plural(f.cross, "day")} ago`}`,
    high: (f) => f.off < 0.05 ? `At its 52-week high of ${money(f.hi)}` : `${pc(f.off)} under the 52-week high of ${money(f.hi)}`,
    low: (f) => f.up < 0.05 ? `At its 52-week low of ${money(f.lo)}` : `${pc(f.up)} above the 52-week low of ${money(f.lo)}`,
    thin: (f) => f.moves < THIN_MOVES ? `Thin market: ${f.moves === 0 ? "no price moves" : plural(f.moves, "price move")} in 14 days, so only the slow rules run` : `Only ${plural(f.dailyDays, "daily price")} in a row, so only the slow rules run`,
  };
  const WHY = {
    stale: () => ["The newest price is more than 3 days old, or there is only one"],
    bulk: (f) => [`Market price ${money(f.v)}`],
    young: (f) => [f.history < MIN_HISTORY ? `${plural(f.history, "day")} of prices on record` : "Gaps in the last 30 days of prices"],
    stretched: (f) => [say.rsi(f), say.band(f), say.vs30(f), say.high(f)],
    knife: (f) => [say.vs30(f), say.rsi(f), say.trend(f), say.macd(f)],
    breakdown: (f) => [say.trend(f), say.vs90(f) || say.vs30(f), say.macd(f)],
    turn: (f) => [say.high(f), say.low(f), say.macd(f), say.rsi(f)],
    dip: (f) => [say.long(f), say.vs90(f), say.rsi(f), say.band(f)],
    breakout: (f) => [say.high(f), say.trend(f), say.macd(f), say.rsi(f)],
    ride: (f) => [say.trend(f), say.vs90(f), `${say.vs30(f)} (stretched starts at ${STRETCH}%)`, say.rsi(f)],
    weak: (f) => [say.long(f), say.vs90(f), say.macd(f)],
    none: (f) => [say.trend(f), say.long(f), say.rsi(f), say.macd(f)],
    "s-spike": (f) => [say.vs30(f), say.high(f), say.thin(f)],
    "s-drop": (f) => [say.vs30(f), say.low(f), say.thin(f)],
    "s-down": (f) => [say.long(f), say.vs30(f), say.thin(f)],
    "s-base": (f) => [say.high(f), say.low(f), say.trend(f), say.thin(f)],
    "s-dip": (f) => [say.long(f), say.vs30(f), say.vs90(f), say.thin(f)],
    "s-up": (f) => [say.long(f), say.vs30(f), say.thin(f)],
    "s-none": (f) => [say.long(f), say.vs30(f), say.thin(f)],
  };

  /* ---------- price ladder ---------- */
  // the lowest sale price whose net (after selling fees and shipping out) covers `cost`
  // (cent by cent, because shipping out steps up at $50 and $100, so the net is not a straight line)
  function breakeven(cost, net) {
    if (!(cost > 0) || typeof net !== "function") return null;
    const top = cost * 4 + 2000;
    for (let p = Math.ceil(cost); p <= top; p++) if (net(p) >= cost) return p;
    return null;
  }
  // levels within LEVEL_MERGE percent of each other become one rung, named for all of them
  function merge(levels) {
    const out = [];
    for (const l of levels) {
      const g = out[out.length - 1];
      if (g && Math.abs(l.price / g.price - 1) * 100 < LEVEL_MERGE) g.what += `, ${l.what}`;
      else out.push({ ...l });
    }
    return out;
  }
  function ladder(f, ctx) {
    const v = f.v, c = [];
    // side: "u" only ever a level under the price, "o" only over it (a band the price has broken through is not a level)
    const add = (price, what, side) => { if (price != null && isFinite(price) && price > 0) c.push({ price: Math.round(price), what, side }); };
    add(f.a30, "30-day average"); add(f.a90, "90-day average"); add(f.low30, "30-day low", "u");
    if (f.bl != null && (f.lo == null || f.bl >= f.lo)) add(f.bl, "lower band", "u");
    if (f.bu != null && (f.hi == null || f.bu <= f.hi)) add(f.bu, "upper band", "o");
    add(f.hi, "52-week high", "o"); add(f.lo, "52-week low", "u");
    const under = merge(c.filter((l) => l.side !== "o" && l.price <= v * (1 - LEVEL_GAP / 100) && l.price >= v * (1 - BUY_REACH / 100)).sort((x, y) => y.price - x.price)).slice(0, 2);
    const over = merge(c.filter((l) => l.side !== "u" && l.price >= v * (1 + LEVEL_GAP / 100)).sort((x, y) => x.price - y.price));
    const sells = over.length > 2 ? [over[0], over[over.length - 1]] : over;
    const cost = v + (ctx.shipIn || 0);
    const even = breakeven(cost, ctx.net);
    const cut = Math.round((under.length ? under[under.length - 1].price : v) * (1 - CUT_UNDER / 100));
    const rungs = [];
    sells.forEach((l, i) => {
      const pr = ctx.net ? ctx.net(l.price) - cost : null;
      rungs.push({ k: `sell${i + 1}`, tag: `Sell ${i + 1}`, what: l.what, price: l.price, profit: pr, roi: pr == null ? null : pr / cost * 100 });
    });
    if (even != null) rungs.push({ k: "even", tag: "Break-even", what: "after fees, buying at market", price: even, up: (even / v - 1) * 100 });
    rungs.push({ k: "now", tag: "Market now", what: "", price: v });
    under.forEach((l, i) => rungs.push({ k: `buy${i + 1}`, tag: `Buy ${i + 1}`, what: l.what, price: l.price, down: (1 - l.price / v) * 100 }));
    rungs.push({ k: "cut", tag: "Cut", what: `${CUT_UNDER}% under ${under.length ? `Buy ${under.length}` : "the price"}`, price: cut, down: (1 - cut / v) * 100 });
    if (ctx.maxBuy) {
      const mb = ctx.maxBuy(v);
      if (mb > 0) rungs.push({ k: "flip", tag: "Max buy", what: `${ctx.roi}% profit selling at today's price`, price: mb, down: (1 - mb / v) * 100 });
    }
    // top to bottom by price; at equal prices sells stay above the market row and buys below it
    const rank = { sell2: 0, sell1: 1, even: 2, now: 3, buy1: 4, buy2: 5, cut: 6, flip: 7 };
    rungs.sort((x, y) => y.price - x.price || rank[x.k] - rank[y.k]);
    return { rungs, cost, even, cut, sells, buys: under, top: rungs.find((r) => r.k === `sell${sells.length}`) || null };
  }

  /* ---------- risk ---------- */
  function risk(f, item) {
    const parts = [];
    const add = (pts, text) => { if (pts > 0) parts.push({ pts, text }); };
    if (f.dailyDays <= 14) add(22, "Too few daily prices to tell how often it sells");
    else add(f.moves === 0 ? 30 : f.moves < THIN_MOVES ? 22 : f.moves < 6 ? 10 : 0,
      f.moves === 0 ? "No price moves in 14 days: slow to sell" : f.moves < THIN_MOVES ? `${plural(f.moves, "price move")} in 14 days: slow to sell` : `${plural(f.moves, "price move")} in 14 days: sells now and then`);
    if (f.range90 != null) add(f.range90 >= 60 ? 25 : f.range90 >= 30 ? 15 : f.range90 >= 12 ? 7 : 0, `90-day range of ${f.range90.toFixed(0)}% from low to high`);
    if (f.long != null && f.long <= -TREND_BAND) add(15, "Longer trend is down (30D avg under the 90D avg)");
    if (f.trend === "down") add(5, "Short trend is down");
    if (f.history < 90) add(10, `Only ${plural(f.history, "day")} of prices on record`);
    const age = item && item.pub ? f.today - dayNum(item.pub) : null;
    if (age != null && age >= 0 && age < NEW_SET_DAYS) add(10, `Set is ${plural(age, "day")} old: prices still settling`);
    if (f.rsi != null && f.rsi >= RSI_HOT && f.moves >= THIN_MOVES) add(8, "Overbought (RSI 70 and up)");
    add(f.v >= 50000 ? 10 : f.v >= 10000 ? 5 : 0, `${money(f.v)} in one item`);
    const score = Math.min(100, parts.reduce((s, p) => s + p.pts, 0));
    parts.sort((x, y) => y.pts - x.pts);
    return { score, level: score >= RISK_HIGH ? "High" : score >= RISK_MED ? "Medium" : "Low", parts };
  }

  /* ---------- the whole plan for one item ----------
     a: EdgeTA.analyse(...) (what the chart's mount returns)
     item: { pub } the set's release day, when known
     ctx: { net(price), shipIn, roi, maxBuy(price), lo } the money side, from Edge's settings */
  function plan(a, item = {}, ctx = {}) {
    const f = facts(a), { id, mode } = pick(f);
    const [name, call, tier, act] = SETUPS[id];
    const out = { v: VERSION, id, name, call, label: CALLS[call], mode, tier, act, why: [], ladder: null, risk: null, deal: null, money: null, facts: f };
    if (!f) { out.why = WHY.stale(); return out; }
    out.why = WHY[id](f).filter(Boolean);
    if (mode === "none") return out;
    const L = out.ladder = ladder(f, ctx);
    out.risk = risk(f, item);
    // the money side of acting at today's market price
    if (L.top && L.top.profit != null) {
      out.money = L.top.profit > 0
        ? `Bought at today's market price, a sale at ${money(L.top.price)} (${L.top.what}) clears ${signed(L.top.profit)} after fees.`
        : `Bought at today's market price, even a sale at ${money(L.top.price)} (${L.top.what}) loses ${money(-L.top.profit)} after fees. Only a buy under market works.`;
    } else if (L.even != null) out.money = `No sell level above the price. Bought at today's market price, a sale has to reach ${money(L.even)} to break even.`;
    // the lowest listing already clears the profit target at today's price
    if (ctx.lo && ctx.net) {
      const cost = ctx.lo + (ctx.shipIn || 0), pr = ctx.net(f.v) - cost;
      if (cost > 0 && pr / cost * 100 >= ctx.roi) out.deal = `The lowest listing, ${money(ctx.lo)}, would clear ${signed(pr)} (${(pr / cost * 100).toFixed(0)}%) at today's price. Check its condition first.`;
    }
    return out;
  }

  /* ---------- the box ---------- */
  function html(p) {
    const tier = p.tier ? TIERS[p.tier] : null;
    const chips = [
      tier ? `<span class="chip" title="${esc(tier[1])}">Execution: ${tier[0]}</span>` : "",
      p.risk ? `<span class="chip sg-risk-${p.risk.level.toLowerCase()}">Risk: ${p.risk.level}</span>` : "",
      p.mode === "fast" ? `<span class="chip">Fast rules</span>` : p.mode === "slow" ? `<span class="chip">Slow rules</span>` : "",
    ].join("");
    const note = (r) => r.k.startsWith("sell") ? (r.profit == null ? "" : `${signed(r.profit)} if bought today`)
      : r.k === "even" ? `+${r.up.toFixed(1)}% from here`
      : r.k === "now" ? "you are here"
      : `−${r.down.toFixed(1)}%`;
    const rung = (r) => `<div class="sg-rung sg-${r.k.replace(/\d$/, "")}" data-k="${r.k}"><span class="sg-tag"><b>${r.tag}</b>${r.what ? `<small>${esc(r.what)}</small>` : ""}</span><span class="sg-px"><b>${money(r.price)}</b><small class="${r.k.startsWith("sell") && r.profit != null ? (r.profit > 0 ? "up" : "down") : ""}">${note(r)}</small></span></div>`;
    return `<div class="sg-head"><span class="lab">Strategy</span><span class="sg-beta">v1 rules · not backtested</span></div>
      <div class="sg-call sg-${p.call}"><b>${esc(p.label)}</b><span>${esc(p.name)}</span></div>
      ${chips ? `<div class="chips">${chips}</div>` : ""}
      <p class="sg-act">${esc(p.act)}${tier ? ` <span class="sg-tier">${tier[0]}: ${esc(tier[1])}.</span>` : ""}</p>
      ${p.deal ? `<p class="sg-deal"><b>Low listing.</b> ${esc(p.deal)}</p>` : ""}
      ${p.why.length ? `<span class="lab">Why</span><ul class="sg-list">${p.why.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
      ${p.ladder ? `<span class="lab">Price ladder</span><div class="sg-ladder">${p.ladder.rungs.map(rung).join("")}</div>${p.money ? `<p class="sg-money">${esc(p.money)}</p>` : ""}` : ""}
      ${p.risk ? `<span class="lab">Risk · ${p.risk.level} · ${p.risk.score} of 100</span>${p.risk.parts.length ? `<ul class="sg-list">${p.risk.parts.map((x) => `<li>${esc(x.text)} <i>+${x.pts}</i></li>`).join("")}</ul>` : `<p class="sg-money">Nothing on the list applies.</p>`}` : ""}
      <p class="sg-foot">Fixed rules on TCGplayer market prices, not backtested yet. Market data, not financial advice. Check live listings and sold prices before you act.</p>`;
  }
  function mount(root, p) {
    root.classList.add("sg");
    root.dataset.call = p.call; root.dataset.setup = p.id;
    root.innerHTML = html(p);
    return p;
  }

  const api = { v: VERSION, plan, mount, html, facts, pick, ladder, risk, breakeven, SETUPS, FAST, SLOW, CALLS, TIERS,
    K: { MIN_PRICE, MIN_HISTORY, FAST_DAYS, THIN_MOVES, TREND_BAND, RSI_HOT, RSI_COLD, RSI_DIP, RSI_PUSH, BAND_DIP, BAND_TOP, STRETCH, KNIFE, NEAR_HIGH, DEEP_OFF, NEAR_LOW, BASE_LOW, CROSS_DAYS, SLOW_JUMP, BREAKOUT_HISTORY, LEVEL_GAP, LEVEL_MERGE, BUY_REACH, CUT_UNDER, RISK_MED, RISK_HIGH, NEW_SET_DAYS } };
  if (typeof window !== "undefined") window.EdgeStrat = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
