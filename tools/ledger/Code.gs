/**
 * DYS Edge ledger: the web app bound to Keo's ledger Google Sheet (milestone M2).
 * @OnlyCurrentDoc   (this script can open only the Sheet it is bound to)
 *
 * Edge (site/assets/edge-ledger.js) sends the changes it has queued and gets every table back:
 *   POST text/plain  {"token": "<this device's pairing token>", "ops": [{opId, table, row}],
 *                     "shown": {items: [[id, costEach, left]], ...}, "summary": [[...]]}
 *   →  {"ok": true, "tables": {buys:[...], items:[...], sales:[...], costs:[...], cash:[...]}, "applied": n, "skipped": n, "sheet": "<url>", "at": "<iso>"}
 *   or {"ok": false, "error": "denied" | "busy" | "bad request"}
 * Who may write: a device whose token's SHA-256 is in the script property EDGE_DEVICE_HASHES (comma-separated),
 * the same pairing codes the sold-price relay uses. Nothing else is accepted; the token is never stored or logged.
 *
 * In the Sheet: one tab per table, a header row, money in dollars, days as text (YYYY-MM-DD). Columns are found by
 * their header, so tabs can be widened or reordered by hand. A row is replaced only by a newer change (upd);
 * deleting in Edge sets Deleted = 1 and keeps the row. Every applied change is listed on the Log tab.
 * The Summary tab is rewritten from Edge's numbers on each sync. Records for the owner's own use.
 */
var SCHEMA = {
  buys: { tab: 'Buys', cols: [['id', 'ID', 's'], ['day', 'Date', 'd'], ['book', 'Book', 's'], ['where', 'Where', 's'], ['from', 'From', 's'], ['pay', 'Paid with', 's'],
    ['tax', 'Sales tax', 'm'], ['ship', 'Shipping', 'm'], ['fees', 'Fees', 'm'], ['total', 'Total', 'm'], ['note', 'Note', 's'], ['upd', 'Updated', 'n'], ['void', 'Deleted', 'n']] },
  items: { tab: 'Items', cols: [['id', 'ID', 's'], ['buy', 'Buy ID', 's'], ['day', 'Acquired', 'd'], ['book', 'Book', 's'], ['kind', 'Type', 's'], ['name', 'Item', 's'], ['set', 'Set', 's'],
    ['cond', 'Condition', 's'], ['grader', 'Grader', 's'], ['grade', 'Grade', 's'], ['cert', 'Cert', 's'], ['qty', 'Qty', 'n'], ['price', 'Price each', 'm'], ['costEach', 'Cost each', 'm'],
    ['left', 'Qty held', 'n'], ['status', 'Status', 's'], ['tcg', 'TCGplayer ID', 's'], ['g', 'Set ID', 's'], ['n', 'Variant', 's'], ['note', 'Note', 's'], ['upd', 'Updated', 'n'], ['void', 'Deleted', 'n']] },
  sales: { tab: 'Sales', cols: [['id', 'ID', 's'], ['day', 'Date', 'd'], ['item', 'Item ID', 's'], ['name', 'Item', 's'], ['book', 'Book', 's'], ['qty', 'Qty', 'n'], ['plat', 'Sold on', 's'],
    ['price', 'Sale price', 'm'], ['shipIn', 'Shipping charged', 'm'], ['fees', 'Fees', 'm'], ['shipOut', 'Shipping paid', 'm'], ['supplies', 'Supplies', 'm'], ['other', 'Other costs', 'm'],
    ['net', 'Net', 'm'], ['cost', 'Cost', 'm'], ['profit', 'Profit', 'm'], ['note', 'Note', 's'], ['upd', 'Updated', 'n'], ['void', 'Deleted', 'n']] },
  costs: { tab: 'Expenses', cols: [['id', 'ID', 's'], ['day', 'Date', 'd'], ['book', 'Book', 's'], ['kind', 'Category', 's'], ['amount', 'Amount', 'm'], ['item', 'Item ID', 's'],
    ['note', 'Note', 's'], ['upd', 'Updated', 'n'], ['void', 'Deleted', 'n']] },
  cash: { tab: 'Cash', cols: [['id', 'ID', 's'], ['day', 'Date', 'd'], ['book', 'Book', 's'], ['kind', 'Type', 's'], ['amount', 'Amount', 'm'], ['to', 'To book', 's'],
    ['note', 'Note', 's'], ['upd', 'Updated', 'n'], ['void', 'Deleted', 'n']] }
};
// columns Edge fills in for reading the Sheet; Edge recomputes them itself and never reads them back
var SHOWN = { buys: ['total'], items: ['costEach', 'left'], sales: ['name', 'net', 'cost', 'profit'], costs: [], cash: [] };
var LOG = { tab: 'Log', head: ['Change ID', 'When', 'Device', 'Table', 'Row ID', 'What'] };
var MAX_OPS = 500;

function doGet() { return out_({ ok: true, app: 'dys-edge-ledger', v: 1 }); }   // a health check: no data, no sign-in needed
function doPost(e) {
  var req; try { req = JSON.parse((e && e.postData && e.postData.contents) || ''); } catch (err) { return out_({ ok: false, error: 'bad request' }); }
  return out_(handle_(req, SpreadsheetApp.getActiveSpreadsheet(), new Date()));
}
function out_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }

function handle_(req, ss, now) {
  if (!req || typeof req !== 'object') return { ok: false, error: 'bad request' };
  var dev = device_(req.token);
  if (!dev) return { ok: false, error: 'denied' };
  var ops = Array.isArray(req.ops) ? req.ops.slice(0, MAX_OPS) : [];
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(20000)) return { ok: false, error: 'busy' };
  try {
    setup_(ss);
    var seen = seenOps_(ss), applied = 0, skipped = 0, log = [], when = Utilities.formatDate(now, ss.getSpreadsheetTimeZone() || 'America/Los_Angeles', 'yyyy-MM-dd HH:mm:ss');
    var byTable = {};
    for (var i = 0; i < ops.length; i++) {
      var op = ops[i];
      if (!op || !op.opId || !SCHEMA[op.table] || !op.row || !op.row.id) { skipped++; continue; }
      if (seen[op.opId]) { skipped++; continue; }
      seen[op.opId] = 1;
      (byTable[op.table] = byTable[op.table] || []).push(op);
    }
    for (var t in byTable) {
      var res = writeRows_(ss, t, byTable[t]);
      applied += res.applied; skipped += res.skipped;
      for (var j = 0; j < byTable[t].length; j++) { var o = byTable[t][j]; log.push([o.opId, when, dev.slice(0, 8), t, String(o.row.id), res.what[j]]); }
    }
    if (log.length) { var L = ss.getSheetByName(LOG.tab), at = L.getLastRow() + 1; L.getRange(at, 1, log.length, LOG.head.length).setNumberFormat('@').setValues(log.map(function (r) { return r.map(asText_); })); }
    if (req.shown && typeof req.shown === 'object') shown_(ss, req.shown);
    if (Array.isArray(req.summary) && req.summary.length) summary_(ss, req.summary);
    return { ok: true, tables: readAll_(ss), applied: applied, skipped: skipped, sheet: ss.getUrl(), at: now.toISOString() };
  } finally { lock.releaseLock(); }
}

/* the device's pairing token → its SHA-256, checked against EDGE_DEVICE_HASHES; returns the hash or '' */
function device_(token) {
  if (typeof token !== 'string' || token.length < 32 || token.length > 256) return '';
  var list = String(PropertiesService.getScriptProperties().getProperty('EDGE_DEVICE_HASHES') || '').toLowerCase().split(/[\s,]+/).filter(String);
  var bytes = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, token, Utilities.Charset.UTF_8), h = '';
  for (var i = 0; i < bytes.length; i++) h += ('0' + ((bytes[i] + 256) % 256).toString(16)).slice(-2);
  return list.indexOf(h) >= 0 ? h : '';
}

/* make any missing tab, with its header row (run by hand once, or on the first sync) */
function setup() { setup_(SpreadsheetApp.getActiveSpreadsheet()); }
function setup_(ss) {
  for (var t in SCHEMA) {
    var s = SCHEMA[t], sh = ss.getSheetByName(s.tab);
    if (!sh) {
      sh = ss.insertSheet(s.tab);
      sh.getRange(1, 1, 1, s.cols.length).setValues([s.cols.map(function (c) { return c[1]; })]).setFontWeight('bold');
      sh.setFrozenRows(1);
      for (var i = 0; i < s.cols.length; i++) {
        var f = s.cols[i][2] === 'm' ? '$#,##0.00' : s.cols[i][2] === 'n' ? '0' : '@';
        sh.getRange(2, i + 1, sh.getMaxRows() - 1, 1).setNumberFormat(f);
      }
    } else {
      var head = sh.getRange(1, 1, 1, Math.max(1, sh.getLastColumn())).getValues()[0].map(String), add = [];
      for (var k = 0; k < s.cols.length; k++) if (head.indexOf(s.cols[k][1]) < 0) add.push(s.cols[k][1]);
      if (add.length) sh.getRange(1, head.filter(String).length + 1, 1, add.length).setValues([add]).setFontWeight('bold');
    }
  }
  if (!ss.getSheetByName(LOG.tab)) { var L = ss.insertSheet(LOG.tab); L.getRange(1, 1, 1, LOG.head.length).setValues([LOG.head]).setFontWeight('bold'); L.setFrozenRows(1); L.getRange(2, 1, L.getMaxRows() - 1, LOG.head.length).setNumberFormat('@'); }
  if (!ss.getSheetByName('Summary')) ss.insertSheet('Summary', 0);
}
function seenOps_(ss) {
  var L = ss.getSheetByName(LOG.tab), n = L.getLastRow() - 1, seen = {};
  if (n > 0) { var v = L.getRange(2, 1, n, 1).getValues(); for (var i = 0; i < v.length; i++) seen[String(v[i][0])] = 1; }
  return seen;
}
function cols_(sh, s) {
  var head = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(String), at = {};
  for (var i = 0; i < s.cols.length; i++) at[s.cols[i][0]] = head.indexOf(s.cols[i][1]);
  return { head: head, at: at };
}
/* upsert by ID; a row is replaced only by a change at least as new as the one in the Sheet */
function writeRows_(ss, t, ops) {
  var s = SCHEMA[t], sh = ss.getSheetByName(s.tab), c = cols_(sh, s), width = c.head.length, n = sh.getLastRow() - 1;
  var rng = n > 0 ? sh.getRange(2, 1, n, width) : null;
  // values as Sheets shows them, and any formula behind a cell (kept: a formula the owner added stays a formula)
  var data = rng ? rng.getValues() : [], forms = rng ? rng.getFormulas() : [], idAt = c.at.id, updAt = c.at.upd, index = {};
  for (var r = 0; r < data.length; r++) index[String(data[r][idAt])] = r;
  var what = [], applied = 0, skipped = 0, changed = {}, firstNew = data.length;
  for (var i = 0; i < ops.length; i++) {
    var row = ops[i].row, id = String(row.id), r0 = index[id], cur = r0 == null ? null : data[r0];
    if (cur && Number(cur[updAt] || 0) > Number(row.upd || 0)) { what.push('older than the Sheet: not applied'); skipped++; continue; }
    var line = cur ? cur.slice() : new Array(width).fill(''), fl = cur ? forms[r0].slice() : new Array(width).fill('');
    for (var k = 0; k < s.cols.length; k++) {
      var key = s.cols[k][0], typ = s.cols[k][2], col = c.at[key];
      if (col < 0 || !(key in row)) continue;
      line[col] = toCell_(row[key], typ); fl[col] = '';
    }
    if (cur) { data[r0] = line; forms[r0] = fl; changed[r0] = 1; } else { index[id] = data.length; data.push(line); forms.push(fl); }
    what.push(row['void'] ? 'deleted' : cur ? 'updated' : 'added'); applied++;
  }
  var out = function (r) { return data[r].map(function (v, k) { return forms[r][k] ? forms[r][k] : asText_(v); }); };
  for (var r1 in changed) { var ri = Number(r1); if (ri >= firstNew) continue; formats_(sh, s, c, ri + 2, 1); sh.getRange(ri + 2, 1, 1, width).setValues([out(ri)]); }
  if (data.length > firstNew) {
    var block = []; for (var r2 = firstNew; r2 < data.length; r2++) block.push(out(r2));
    formats_(sh, s, c, firstNew + 2, block.length); sh.getRange(firstNew + 2, 1, block.length, width).setValues(block);
  }
  return { applied: applied, skipped: skipped, what: what };
}
/* plain text for text and day columns before writing, so Sheets keeps "2026-11-16", "0012" and "=..." exactly as typed */
function formats_(sh, s, c, row, n) {
  for (var k = 0; k < s.cols.length; k++) {
    var col = c.at[s.cols[k][0]], typ = s.cols[k][2];
    if (col >= 0) sh.getRange(row, col + 1, n, 1).setNumberFormat(typ === 'm' ? '$#,##0.00' : typ === 'n' ? '0' : '@');
  }
}
function toCell_(v, typ) {
  if (v == null || v === '') return '';
  if (typ === 'm') return Math.round(Number(v) || 0) / 100;
  if (typ === 'n') return Number(v) || 0;
  return String(v);
}
// Sheets reads text starting with = + - @ as a formula even in a plain-text cell (seen live Nov 16: "#ERROR!"). A leading
// apostrophe makes it text; Sheets hides that apostrophe when the cell is read, so every write adds it again.
function asText_(v) { return typeof v === 'string' && /^[=+\-@']/.test(v) ? "'" + v : v; }
function readAll_(ss) {
  var tz = ss.getSpreadsheetTimeZone() || 'America/Los_Angeles', all = {};
  for (var t in SCHEMA) {
    var s = SCHEMA[t], sh = ss.getSheetByName(s.tab), c = cols_(sh, s), n = sh.getLastRow() - 1, rows = [];
    var data = n > 0 ? sh.getRange(2, 1, n, c.head.length).getValues() : [];
    for (var r = 0; r < data.length; r++) {
      var o = {}, line = data[r];
      for (var k = 0; k < s.cols.length; k++) {
        var key = s.cols[k][0], typ = s.cols[k][2], col = c.at[key];
        if (col < 0 || SHOWN[t].indexOf(key) >= 0) continue;
        var v = line[col];
        if (typ === 'm') o[key] = v === '' || v == null ? 0 : Math.round(Number(v) * 100) || 0;
        else if (typ === 'n') o[key] = v === '' || v == null ? 0 : Number(v) || 0;
        else if (typ === 'd') o[key] = v instanceof Date ? Utilities.formatDate(v, tz, 'yyyy-MM-dd') : String(v == null ? '' : v).slice(0, 10);
        else o[key] = v instanceof Date ? Utilities.formatDate(v, tz, 'yyyy-MM-dd') : String(v == null ? '' : v);
      }
      if (o.id) rows.push(o);
    }
    all[t] = rows;
  }
  return all;
}
/* the columns Edge works out (cost each, qty held, net, profit, totals): rewritten for every row on each sync,
   one column at a time, so the Sheet reads right after a sale without Edge resending the item */
function shown_(ss, shown) {
  for (var t in SHOWN) {
    var keys = SHOWN[t], list = shown[t];
    if (!keys.length || !Array.isArray(list)) continue;
    var s = SCHEMA[t], sh = ss.getSheetByName(s.tab), c = cols_(sh, s), n = sh.getLastRow() - 1;
    if (n < 1) continue;
    var ids = sh.getRange(2, c.at.id + 1, n, 1).getValues(), by = {};
    for (var i = 0; i < list.length; i++) if (Array.isArray(list[i])) by[String(list[i][0])] = list[i];
    for (var k = 0; k < keys.length; k++) {
      var col = c.at[keys[k]]; if (col < 0) continue;
      var typ = null; for (var q = 0; q < s.cols.length; q++) if (s.cols[q][0] === keys[k]) typ = s.cols[q][2];
      var vals = ids.map(function (r) { var v = by[String(r[0])]; return [v ? asText_(toCell_(v[k + 1], typ)) : ''] ; });
      sh.getRange(2, col + 1, n, 1).setValues(vals);
    }
  }
}
function summary_(ss, rows) {
  var sh = ss.getSheetByName('Summary'), w = 0;
  rows = rows.slice(0, 40).map(function (r) { return Array.isArray(r) ? r.slice(0, 6) : []; });
  for (var i = 0; i < rows.length; i++) w = Math.max(w, rows[i].length);
  rows = rows.map(function (r) { while (r.length < w) r.push(''); return r.map(function (v) { return typeof v === 'number' ? v : typeof v === 'string' ? asText_(v) : ''; }); });
  sh.clear();
  if (!w) return;
  sh.getRange(1, 1, rows.length, w).setValues(rows);
  sh.getRange(1, 1, 1, w).setFontWeight('bold');
  if (w > 1 && rows.length > 1) sh.getRange(2, 2, rows.length - 1, w - 1).setNumberFormat('$#,##0.00');
}
