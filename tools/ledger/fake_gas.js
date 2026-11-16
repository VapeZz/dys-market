// A small stand-in for the Google Apps Script services Code.gs uses (SpreadsheetApp, LockService, PropertiesService,
// Utilities, ContentService), so the real Code.gs runs under Node in tests. Only what Code.gs calls is here.
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm"), crypto = require("crypto");
// Like Sheets: a cell formatted as plain text ("@") keeps a string as typed; any other cell reads a string the way
// a person's typing is read (a leading "=" makes a formula, a date-looking string becomes a date, a number-looking
// one a number). Formats are kept per cell.
function enter(v, f) {
  if (typeof v !== "string" || f === "@") return v;
  if (/^=/.test(v)) return "#FORMULA:" + v;
  if (/^'/.test(v)) return v.slice(1);
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return new Date(v + "T00:00:00Z");
  if (/^-?\d+(\.\d+)?$/.test(v)) return Number(v);
  return v;
}
function Sheet(name, rows = 1000, cols = 26) {
  const g = Array.from({ length: rows }, () => new Array(cols).fill(""));
  const fmt = {};          // "r,c" → format
  const sh = {
    name, grid: g, fmt, frozen: 0,
    getName: () => name, getMaxRows: () => g.length, getMaxColumns: () => g[0].length,
    getLastRow: () => { for (let r = g.length - 1; r >= 0; r--) if (g[r].some((v) => v !== "")) return r + 1; return 0; },
    getLastColumn: () => { let m = 0; for (const row of g) for (let c = row.length - 1; c >= m; c--) if (row[c] !== "") { m = c + 1; break; } return m; },
    setFrozenRows: (n) => { sh.frozen = n; },
    clear: () => { for (const row of g) row.fill(""); for (const k in fmt) delete fmt[k]; },
    // a person typing into a cell (for tests of hand edits)
    type: (r, c, v) => { g[r - 1][c - 1] = enter(v, fmt[`${r},${c}`]); },
    getRange(r, c, nr = 1, nc = 1) {
      if (r < 1 || c < 1 || nr < 1 || nc < 1) throw new Error(`bad range ${r},${c},${nr},${nc}`);
      while (g.length < r + nr - 1) g.push(new Array(g[0].length).fill(""));
      for (const row of g) while (row.length < c + nc - 1) row.push("");
      const rg = {
        getValues: () => g.slice(r - 1, r - 1 + nr).map((row) => row.slice(c - 1, c - 1 + nc).map((v) => v instanceof Date ? new Date(v) : v)),
        setValues: (vals) => {
          if (vals.length !== nr || vals.some((x) => x.length !== nc)) throw new Error(`setValues: ${vals.length}x${vals[0] && vals[0].length} into ${nr}x${nc}`);
          vals.forEach((row, i) => row.forEach((v, j) => { g[r - 1 + i][c - 1 + j] = enter(v, fmt[`${r + i},${c + j}`]); })); return rg;
        },
        setNumberFormat: (f) => { for (let i = 0; i < nr; i++) for (let j = 0; j < nc; j++) fmt[`${r + i},${c + j}`] = f; return rg; },
        setFontWeight: () => rg
      };
      return rg;
    }
  };
  return sh;
}
function Spreadsheet(tz = "America/Los_Angeles") {
  const tabs = [];
  return { tabs, getSheetByName: (n) => tabs.find((t) => t.name === n) || null,
    insertSheet: (n, at) => { const s = Sheet(n); if (at === 0) tabs.unshift(s); else tabs.push(s); return s; },
    getUrl: () => "https://docs.google.com/spreadsheets/d/TEST/edit", getSpreadsheetTimeZone: () => tz };
}
function load(opts = {}) {
  const props = { EDGE_DEVICE_HASHES: opts.hashes || "" }, ss = opts.ss || Spreadsheet();
  let locked = false;
  const ctx = {
    console,
    SpreadsheetApp: { getActiveSpreadsheet: () => ss },
    LockService: { getScriptLock: () => ({ tryLock: () => opts.busy ? false : (locked = true), releaseLock: () => { locked = false; } }) },
    PropertiesService: { getScriptProperties: () => ({ getProperty: (k) => props[k] ?? null }) },
    Utilities: {
      DigestAlgorithm: { SHA_256: "sha256" }, Charset: { UTF_8: "utf8" },
      computeDigest: (alg, s) => [...crypto.createHash("sha256").update(String(s), "utf8").digest()].map((b) => b > 127 ? b - 256 : b),
      formatDate: (d, tz, f) => {
        const p = Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).formatToParts(d).map((x) => [x.type, x.value]));
        return f.replace("yyyy", p.year).replace("MM", p.month).replace("dd", p.day).replace("HH", p.hour === "24" ? "00" : p.hour).replace("mm", p.minute).replace("ss", p.second);
      }
    },
    ContentService: { MimeType: { JSON: "json" }, createTextOutput: (t) => ({ text: t, setMimeType() { return this; } }) }
  };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname, "Code.gs"), "utf8"), ctx, { filename: "Code.gs" });
  return { ctx, ss, props, post: (body, now = new Date()) => JSON.parse(ctx.doPost({ postData: { contents: typeof body === "string" ? body : JSON.stringify(body) } }).text), handle: (req, now = new Date()) => ctx.handle_(req, ss, now), isLocked: () => locked };
}
const sha = (s) => crypto.createHash("sha256").update(s, "utf8").digest("hex");
module.exports = { load, Spreadsheet, Sheet, sha };
