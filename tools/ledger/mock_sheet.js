// The ledger's web app (the real Code.gs) on an emulated Sheet, served over HTTP for local browser checks.
// Usage: node tools/ledger/mock_sheet.js <port> <device hash,...>
//   POST /exec   → doPost (what Edge calls)         GET /exec → doGet
//   GET  /dump   → every tab's cells, as JSON       POST /mode {"mode": "ok" | "offline" | "error"}
// Nothing here is published; the data is whatever the test types in.
const http = require("http"), path = require("path");
const F = require(path.join(__dirname, "fake_gas.js"));
const [port, hashes] = process.argv.slice(2);
const g = F.load({ hashes: hashes || "" });
let mode = "ok", posts = 0;
const CORS = { "Access-Control-Allow-Origin": "*" };
http.createServer((req, res) => {
  let body = "";
  req.on("data", (c) => { body += c; });
  req.on("end", () => {
    const send = (code, obj, type = "application/json") => { res.writeHead(code, { ...CORS, "Content-Type": type }); res.end(typeof obj === "string" ? obj : JSON.stringify(obj)); };
    if (req.url === "/dump") return send(200, { posts, tabs: Object.fromEntries(g.ss.tabs.map((t) => [t.name, t.grid.filter((r) => r.some((v) => v !== ""))])) });
    if (req.url === "/mode") { mode = JSON.parse(body).mode; return send(200, { mode }); }
    if (req.url.startsWith("/exec")) {
      if (req.method === "GET") return send(200, g.ctx.doGet().text);
      posts++;
      if (mode === "error") return send(500, "Internal error", "text/html");
      return send(200, g.ctx.doPost({ postData: { contents: body } }).text);
    }
    send(404, { error: "not found" });
  });
}).listen(+port, "127.0.0.1", () => console.log(`mock sheet on ${port}`));
