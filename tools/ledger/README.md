# DYS Edge Ledger (M2)

Buys, sales, expenses, cash and inventory in two books (Business, Personal). The record is Keo's Google Sheet;
Edge (`site/assets/edge-ledger.js`, Mine → Ledger) keeps a copy on the phone and a queue of changes, so it works with
no signal and catches up when back online.

| File | What it is |
|---|---|
| `Code.gs` + `appsscript.json` | The web app bound to the ledger Sheet. Only scope: this one Sheet (`spreadsheets.currentonly`). Accepts a device whose pairing token's SHA-256 is in the script property `EDGE_DEVICE_HASHES` (same codes as the sold-price relay). |
| `fake_gas.js` | A stand-in for the Apps Script services, so the real `Code.gs` runs under Node in tests (formats and Sheets' typing rules included). |
| `mock_sheet.js` | `Code.gs` on the emulated Sheet over HTTP, for browser checks. |
| `browser_check.py` | The whole flow in the real Edge app on a local site copy: move inventory in, Bought it, buy from Search, sell, expense, cash, grading, move books, offline queue, delete, export, a refused phone. 360/390/430 px. |
| `random_ledgers.js` + `ref.py` | An independent Python version of the math, compared on random ledgers. |
| `make_preview.js` | The sample-data preview page. |

Tests: `node tests/edge_ledger.test.js` · `python3 tools/ledger/ref.py 7 3000` · `python3 tools/ledger/browser_check.py <site copy>`.

## The live Sheet (set up Nov 16, 2026)
- Sheet **DYS Edge Ledger** in keo.llaneza@gmail.com's Drive (id 1_LWdc3GtTJRonoYxvM9hMp43EwRa9rzb0TUqce_juUc), not shared.
- Script attached to it: project 1bgP5M5PSQ_qCtHlJqoPVHZeKiTt8GughalMM0huJdyGj-RyWJH24Cy2J (shows "Container: DYS Edge Ledger"),
  Code.gs sha256 c4f615bc…, permission `spreadsheets.currentonly` only, authorized by Keo.
- Web app (deployment version 3): https://script.google.com/macros/s/AKfycby2YPa5O2iq_IJOBz_BNcJPKayUdLM3u1Oq-_KZ7FUl_SOALNdiHfkiaQFLTfxdt9BOjw/exec
  To change the code: edit, save, then Deploy → Manage deployments → Edit → New version (same address).
- **Use the Claude app's built-in browser on skibidi** for anything in Apps Script. It is signed in to keo.llaneza only.
  Skibidi's Chrome has several Google accounts, and Google's Extensions → Apps Script and its sign-in pop-up fail there
  ("Sorry, unable to open the file", 404).
- A first, unattached script project ("DYS Edge Ledger", 1HSIEXP7…) is left over from the first attempt and is unused.
- Live check (tools/ledger/live_check.js, synthetic rows only): 25 of 25 on version 3. Test tabs removed afterwards.

## Going live (needs Keo's OK)
1. Create a Google Sheet "DYS Edge Ledger" in Keo's Drive.
2. Extensions → Apps Script: paste `Code.gs`, set `appsscript.json` (show it in Project Settings), run `setup` once.
3. Project Settings → Script properties: `EDGE_DEVICE_HASHES` = the same comma-separated hashes as the relay.
4. Deploy → Web app, execute as me, anyone can reach it (the device check is in the script). Google asks Keo to allow
   access to this one Sheet.
5. Put the `/exec` address in `LEDGER_URL` in `edge.js`, bump `?v=`, publish Edge.
A newly paired device must be added to both the relay and the Sheet's `EDGE_DEVICE_HASHES`.
