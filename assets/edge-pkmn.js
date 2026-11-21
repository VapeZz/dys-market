"use strict";
/* DYS Edge: live sold comps from PkmnPrices for the Deal check (M1; loaded by edge.js; owner only).

   On demand only: when the owner taps "Get sold prices" on one card, this file asks PkmnPrices (through the
   owner's private relay, see tools/deal/relay-worker.js) for that card's recent eBay sold listings (raw, PSA 10,
   PSA 9) and its graded population, and turns them into the Deal check's data. Nothing is saved: results live
   in this page's memory until it is closed or reloaded. Nothing is shared or published.

   Why a relay: PkmnPrices' API does not answer browser pages (no CORS header, checked Nov 16, 2026), and the
   API key must not sit in a public page. The relay holds the key and forwards a short list of read-only calls.

   Within PkmnPrices' published terms (Pro plan: commercial use listed; credits and rate limits per plan):
   a few calls per card, 1 credit per row returned; reads stop at 90 days back or MAX_PAGES pages per grade.

   Output (the Deal check's data): { asOf, source, comps: [[day, cents, grade, exact]], pop, popAsOf, meta }.
   Sales without a date, outside USD, or from the future are left out and counted in meta. */
(() => {
  const VERSION = 1, DAY = 864e5;
  const PAGE = 20;                                   // rows per call (one credit each); the API's page size is 20 (seen Nov 16)
  const MAX_PAGES = { raw: 5, "PSA 10": 3, "PSA 9": 2, sealed: 4 };   // at most about 300 credits a card
  const WINDOW = 90;                                 // days of sales the Deal check reads
  const QUERIES = { raw: { graded: "false" }, "PSA 10": { graded: "true", grader: "PSA", grade: "10" }, "PSA 9": { graded: "true", grader: "PSA", grade: "9" } };
  const SOURCE = "PkmnPrices · eBay sold (runs about 8 days behind)";

  const dayOf = (ts) => { if (!ts) return null; const s = String(ts), t = Date.parse(/^\d{4}-\d{2}-\d{2}$/.test(s) ? s + "T00:00:00Z" : s); return isFinite(t) ? Math.floor(t / DAY) : null; };
  // the printing in an Edge item name, as PkmnPrices names variants
  // PkmnPrices names printings as TCGplayer does (the finder's Near Mint price lookups match "1st Edition" exactly). Before
  // Nov 20, 2026 "(1st Edition)" and "(Unlimited)" were read as "Normal", so their own sales were dropped as another printing.
  const PRINTINGS = ["1st Edition Holofoil", "1st Edition Normal", "1st Edition", "Unlimited Holofoil", "Unlimited", "Reverse Holofoil", "Holofoil", "Normal"];
  const variantOf = (name) => { const m = /\(([^()]*)\)\s*$/.exec(String(name || "")); return m && PRINTINGS.includes(m[1]) ? m[1] : "Normal"; };

  /* Title rules for one sold row (Nov 20, 2026; the finder's v3 rules): PkmnPrices attributes same-number reprints and
     some other printings as "exact", and raw sales carry no condition field, so the title is the only check left.
     Returns a reason to drop the row, or "" to keep it. raw: also drop graded, played and damaged copies. */
  const T_FOREIGN = /\b(chinese|japanese|japan|korean|korea|italian|italiano|french|fran[cç]ais|german|deutsch|spanish|espa[nñ]ol|portuguese|thai|indonesian|simplified|traditional|jpn?|cn|chn|kr|kor|ita|fr|ger|de|esp?)\b|\b(sv|sm|s)\d{1,2}[a-z]{1,2}\b/i;
  const T_GRADED = /\b(psa|bgs|cgc|sgc|beckett|graded|slab(bed)?|bvg)\b|\btag ?\d/i;
  const T_FAKE = /\b(proxy|proxies|custom art|fan ?art|orica|replica|fake|metal card|not real)\b/i;
  const T_LOT = /\b(lot|bundle|playset|set of \d+)\b|\b(choose|pick|select)\s+(your|a|any)\b|\byou\s*(pick|choose)\b|\bcomplete your\b|\bsingles\b/i;
  const T_PLAYED = /\b(lp\+?|mp|vlp|hp|dmg|damaged|played|creased?|bent|scratch(ed|es)?|heavily|heavy|moderately|lightly|poor|good condition)\b/i;
  const T_REPRINT = /\b(celebrations?|30th|classic collection|anniversary|jumbo|oversized?|mcdonald'?s|trick or trade|reprint|world championships?|wcd)\b/i;
  const T_HOLO = /\bholo(foil|graphic)?\b/i, T_NONHOLO = /\b(non|no)[\s-]?holo\b/i;
  function compDrop(title, item, raw) {
    const t = String(title || ""), pr = variantOf(item.n), low = t.toLowerCase();
    const rev = /\breverse\b/i.test(t), first = /\b1st\b|first edition/i.test(t);
    if (pr.includes("Reverse") ? !rev : rev) return "printing";
    if (pr.startsWith("1st Edition") ? !first : first) return "printing";
    const own = `${item.n || ""} ${item.setN || ""}`;
    if (T_REPRINT.test(t) && !T_REPRINT.test(own)) return "reprint";
    if (T_FOREIGN.test(t)) return "foreign";
    if (T_LOT.test(t) || T_FAKE.test(t)) return "lot";
    const nonHolo = ["Normal", "Unlimited", "1st Edition", "1st Edition Normal"].includes(pr) && item.r && !/holo/i.test(item.r);
    if (nonHolo && T_HOLO.test(t) && !T_NONHOLO.test(t)) return "printing";
    if (raw && T_GRADED.test(t)) return "graded";
    // "HP" alone is a card's hit points ("120 HP"); only the condition words count
    if (raw && T_PLAYED.test(t.replace(/\b\d+\s*hp\b|\bhp\s*\d+\b/gi, ""))) return "played";
    return "";
  }

  /* one call through the relay: { status, body, credits } */
  async function call(cfg, path, q = {}) {
    const qs = Object.entries(q).filter(([, v]) => v != null && v !== "").map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&");
    const url = `${cfg.relay.replace(/\/+$/, "")}${path}${qs ? `?${qs}` : ""}`;
    let r;
    try { r = await (cfg.fetch || fetch)(url, { headers: { "X-Edge-Pass": cfg.pass || "", Accept: "application/json" } }); }
    catch (e) { return { status: 0, body: null, credits: 0, error: "network" }; }
    let body = null; try { body = await r.json(); } catch { body = null; }
    const credits = parseInt(r.headers && r.headers.get ? r.headers.get("x-credits-charged") || "0" : "0", 10) || 0;
    return { status: r.status, body, credits };
  }

  /* the sold rows for one grade, newest first, until WINDOW days back or MAX_PAGES (opt: { query, pages, keep(row) }) */
  async function sales(cfg, base, grade, day, meta, variant, opt = {}) {
    const out = [], pages = opt.pages || MAX_PAGES[grade] || 2;
    let cursor = null;
    for (let page = 0; page < pages; page++) {
      const r = await call(cfg, `${base}/listings/ebay`, { limit: PAGE, sort: "date_desc", cursor, ...(opt.query || QUERIES[grade] || {}) });
      meta.calls++; meta.credits += r.credits;
      if (r.status !== 200) { meta.errors.push(`${grade}: ${r.status === 0 ? "no connection" : `HTTP ${r.status}`}`); break; }
      const rows = (r.body && r.body.data) || [];
      let oldest = day;
      for (const x of rows) {
        const d = dayOf(x.sold_at), cur = String(x.currency || "USD").toUpperCase(), px = Number(x.price);
        if (d == null) { meta.undated++; continue; }
        if (d > day) { meta.future++; continue; }
        oldest = Math.min(oldest, d);
        if (cur !== "USD" || !(px > 0)) { meta.otherCurrency++; continue; }
        // a sale of another printing of the same card (Normal vs Reverse Holofoil...) is not this item's sale
        if (variant && x.variant && x.variant !== variant) { meta.otherPrinting++; continue; }
        if (opt.keep && !opt.keep(x, meta)) continue;
        const exact = x.attribution === "exact" && (!variant || x.variant === variant) ? 1 : 0;
        if (d > day - WINDOW) out.push([d, Math.round(px * 100), grade, exact]);
      }
      const pg = (r.body && r.body.pagination) || {};
      cursor = pg.next_cursor || null;
      meta.oldestRead = Math.min(meta.oldestRead ?? day, oldest);
      if (!pg.has_more || !cursor || oldest <= day - WINDOW) break;
      if (page === pages - 1) meta.capped.push(grade);   // more sales inside 90 days than were read
    }
    return out;
  }

  /* population for the item's printing: PSA counts, the date PkmnPrices last updated them */
  function popOf(body, variant) {
    const vs = (body && body.variants) || [];
    const v = vs.find((x) => x.variant === variant) || (vs.length === 1 ? vs[0] : null);
    if (!v) return null;
    const G = v.graders || {}, psa = G.PSA || G.psa || null;
    if (!psa || !(psa.total > 0)) return null;
    const g = psa.grades || {};
    return { total: psa.total, g10: +g["10"] || 0, g9: +g["9"] || 0, asOf: dayOf(v.updated_at) };
  }

  /* everything the Deal check needs for one Edge item: { id (TCGplayer product), n (name), t ("c" | "s") } */
  async function lookup(item, cfg) {
    const day = cfg.today ?? Math.floor(Date.now() / DAY);
    const meta = { calls: 0, credits: 0, errors: [], undated: 0, future: 0, otherCurrency: 0, otherPrinting: 0, titleDrops: {}, capped: [], found: false };
    if (!cfg.relay) return { ok: false, reason: "not-set-up", meta };
    let base = null;
    if (item.t === "s") {
      const r = await call(cfg, "/v1/sealed", { name: String(item.n || "").replace(/\s*\(.*?\)\s*$/, ""), per_page: 10 });
      meta.calls++; meta.credits += r.credits;
      if (r.status !== 200) return { ok: false, reason: r.status === 0 ? "network" : r.status === 401 || r.status === 403 ? "denied" : "error", status: r.status, meta };
      const hit = ((r.body && r.body.data) || []).find((x) => +x.tcg_player_id === +item.id);
      if (hit) base = `/v1/sealed/${encodeURIComponent(hit.id)}`;
    } else {
      const r = await call(cfg, "/v1/cards", { tcg_player_id: item.id });
      meta.calls++; meta.credits += r.credits;
      if (r.status !== 200) return { ok: false, reason: r.status === 0 ? "network" : r.status === 401 || r.status === 403 ? "denied" : "error", status: r.status, meta };
      const found = (r.body && r.body.data) || [];
      if (found.length === 1) base = `/v1/cards/${encodeURIComponent(found[0].id)}`;
      else if (found.length > 1) meta.errors.push(`${found.length} matches for this TCGplayer id; none used`);
    }
    if (!base) return { ok: false, reason: "not-found", meta };
    meta.found = true;
    const comps = [];
    if (item.t === "s") comps.push(...await sales(cfg, base, "sealed", day, meta, null));
    else for (const g of cfg.rawOnly ? ["raw"] : ["raw", "PSA 10", "PSA 9"]) {   // rawOnly: the buy list needs the resale only
      const keep = (x, m) => { const k = compDrop(x.title, item, g === "raw"); if (!k) return true; m.titleDrops[k] = (m.titleDrops[k] || 0) + 1; return false; };
      comps.push(...await sales(cfg, base, g, day, meta, variantOf(item.n), { keep }));
    }
    let pop = null;
    if (item.t === "c" && !cfg.rawOnly) {
      const r = await call(cfg, `${base}/population`);
      meta.calls++; meta.credits += r.credits;
      if (r.status === 200) pop = popOf(r.body, variantOf(item.n)); else meta.errors.push(`population: HTTP ${r.status}`);
    }
    return { ok: true, data: { asOf: day, source: SOURCE, comps: comps.sort((a, b) => a[0] - b[0]), pop, popAsOf: pop ? pop.asOf : null, capped: meta.capped.slice(), meta }, meta };
  }

  /* ---------- one grade of one card (the Ledger's "Check sold prices" for a graded item) ---------- */
  // graders and grades PkmnPrices filters on (graded=true&grader=&grade=); others are answered "unsupported", never guessed
  const GRADERS = ["PSA"];
  const GRADED_PAGES = 8;                            // at most 160 rows (credits) for the one grade asked
  const okGrade = (g) => /^(10|[1-9](\.5)?)$/.test(String(g || "").trim());
  // a title that names another grade or grader, or a lot of several cards, is not a sale of this slab
  const SLAB = /\b(PSA|CGC|BGS|BECKETT|TAG|SGC|ACE)\s*(?:GEM\s*(?:MINT|MT)\s*|MINT\s*|NM-?MT\s*|PRISTINE\s*)?(10|[1-9](?:\.5)?)\b/gi;
  const LOT = /\b(lot|bundle|bulk)\b|\b\d+\s*(?:x\s*)?(?:cards|slabs)\b|\bset of\b/i;
  function titleCheck(title, grader, grade) {
    const t = String(title || "");
    if (!t) return "ok";
    if (LOT.test(t)) return "lot";
    for (const m of t.matchAll(SLAB)) {
      const g = m[1].toUpperCase() === "BECKETT" ? "BGS" : m[1].toUpperCase();
      if (g !== grader || m[2] !== String(grade)) return "other";
    }
    return "ok";
  }
  async function findCard(item, cfg, meta) {
    const r = await call(cfg, "/v1/cards", { tcg_player_id: item.id });
    meta.calls++; meta.credits += r.credits;
    if (r.status !== 200) return { reason: r.status === 0 ? "network" : r.status === 401 || r.status === 403 ? "denied" : "error", status: r.status };
    const found = (r.body && r.body.data) || [];
    if (found.length > 1) meta.errors.push(`${found.length} matches for this TCGplayer id; none used`);
    return found.length === 1 ? { base: `/v1/cards/${encodeURIComponent(found[0].id)}`, pid: found[0].id } : { reason: "not-found" };
  }
  /* sold prices for one grader and grade of one card: { id (TCGplayer product), n (name) }, { grader, grade } */
  async function lookupGrade(item, slab, cfg) {
    const day = cfg.today ?? Math.floor(Date.now() / DAY);
    const grader = String(slab.grader || "").toUpperCase(), grade = String(slab.grade || "").trim(), label = `${grader} ${grade}`;
    const meta = { calls: 0, credits: 0, errors: [], undated: 0, future: 0, otherCurrency: 0, otherPrinting: 0, otherGrade: 0, lot: 0, capped: [], found: false, oldestRead: null };
    if (!cfg.relay) return { ok: false, reason: "not-set-up", meta };
    if (!GRADERS.includes(grader) || !okGrade(grade)) return { ok: false, reason: "unsupported", label, meta };
    const c = await findCard(item, cfg, meta);
    if (!c.base) return { ok: false, reason: c.reason, status: c.status, meta };
    meta.found = true;
    const keep = (x, m) => { const t = titleCheck(x.title, grader, grade); if (t === "ok") return true; if (t === "lot") m.lot++; else m.otherGrade++; return false; };
    const comps = await sales(cfg, c.base, label, day, meta, variantOf(item.n), { query: { graded: "true", grader, grade }, pages: GRADED_PAGES, keep });
    if (meta.errors.length && !comps.length && !meta.oldestRead) return { ok: false, reason: "error", meta };
    return { ok: true, data: { asOf: day, source: SOURCE, label, comps: comps.sort((a, b) => a[0] - b[0]), capped: meta.capped.slice(), oldestRead: meta.capped.length ? meta.oldestRead : null, meta }, meta };
  }

  /* memory-only cache for this page: one lookup per item per page load unless asked again */
  const mem = new Map();
  const memKey = (item) => `${item.t}|${item.id}|${item.n || ""}`;   // every printing of a card shares the TCGplayer product id
  async function get(item, cfg, fresh = false) {
    const k = memKey(item);
    if (!fresh && mem.has(k)) return mem.get(k);
    const p = lookup(item, cfg);
    mem.set(k, p);
    const r = await p;
    if (!r.ok) mem.delete(k);
    return r;
  }

  const memG = new Map();
  async function getGrade(item, slab, cfg, fresh = false) {
    const k = `${item.id}|${variantOf(item.n)}|${String(slab.grader || "").toUpperCase()} ${String(slab.grade || "").trim()}`;
    if (!fresh && memG.has(k)) return memG.get(k);
    const p = lookupGrade(item, slab, cfg);
    memG.set(k, p);
    const r = await p;
    if (!r.ok) memG.delete(k);
    return r;
  }

  const api = { v: VERSION, lookup, get, lookupGrade, getGrade, titleCheck, compDrop, memKey, GRADERS, popOf, variantOf, dayOf, K: { PAGE, MAX_PAGES, WINDOW, GRADED_PAGES }, SOURCE, _mem: mem, _memG: memG };
  if (typeof window !== "undefined") window.EdgePkmn = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
