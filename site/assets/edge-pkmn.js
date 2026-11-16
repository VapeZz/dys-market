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
  const variantOf = (name) => { for (const v of ["1st Edition Holofoil", "Reverse Holofoil", "Holofoil"]) if (String(name || "").endsWith(`(${v})`)) return v; return "Normal"; };

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

  /* the sold rows for one grade, newest first, until WINDOW days back or MAX_PAGES */
  async function sales(cfg, base, grade, day, meta, variant) {
    const out = [];
    let cursor = null;
    for (let page = 0; page < (MAX_PAGES[grade] || 2); page++) {
      const r = await call(cfg, `${base}/listings/ebay`, { limit: PAGE, sort: "date_desc", cursor, ...(QUERIES[grade] || {}) });
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
        const exact = x.attribution === "exact" && (!variant || x.variant === variant) ? 1 : 0;
        if (d > day - WINDOW) out.push([d, Math.round(px * 100), grade, exact]);
      }
      const pg = (r.body && r.body.pagination) || {};
      cursor = pg.next_cursor || null;
      if (!pg.has_more || !cursor || oldest <= day - WINDOW) break;
      if (page === (MAX_PAGES[grade] || 2) - 1) meta.capped.push(grade);   // more sales inside 90 days than were read
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
    const meta = { calls: 0, credits: 0, errors: [], undated: 0, future: 0, otherCurrency: 0, otherPrinting: 0, capped: [], found: false };
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
    else for (const g of ["raw", "PSA 10", "PSA 9"]) comps.push(...await sales(cfg, base, g, day, meta, variantOf(item.n)));
    let pop = null;
    if (item.t === "c") {
      const r = await call(cfg, `${base}/population`);
      meta.calls++; meta.credits += r.credits;
      if (r.status === 200) pop = popOf(r.body, variantOf(item.n)); else meta.errors.push(`population: HTTP ${r.status}`);
    }
    return { ok: true, data: { asOf: day, source: SOURCE, comps: comps.sort((a, b) => a[0] - b[0]), pop, popAsOf: pop ? pop.asOf : null, capped: meta.capped.slice(), meta }, meta };
  }

  /* memory-only cache for this page: one lookup per item per page load unless asked again */
  const mem = new Map();
  async function get(item, cfg, fresh = false) {
    const k = `${item.t}|${item.id}`;
    if (!fresh && mem.has(k)) return mem.get(k);
    const p = lookup(item, cfg);
    mem.set(k, p);
    const r = await p;
    if (!r.ok) mem.delete(k);
    return r;
  }

  const api = { v: VERSION, lookup, get, popOf, variantOf, dayOf, K: { PAGE, MAX_PAGES, WINDOW }, SOURCE, _mem: mem };
  if (typeof window !== "undefined") window.EdgePkmn = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
