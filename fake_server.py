"""Serve the fixture tree like tcgcsv.com, plus a fake store /products.json."""
import http.server, json, os, sys, urllib.parse
ROOT = sys.argv[1]; PORT = int(sys.argv[2])
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=ROOT, **k)
    def log_message(self, *a): pass
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/products.json":
            page = int(urllib.parse.parse_qs(u.query).get("page", ["1"])[0])
            data = json.load(open(os.path.join(ROOT, "store", "products.json")))
            body = json.dumps(data if page == 1 else {"products": []}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body); return
        return super().do_GET()
http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
