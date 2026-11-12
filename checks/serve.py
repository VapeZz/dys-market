"""Serves a folder the way GitHub Pages does for this site: files as they are, and 404.html (status 404) for anything missing."""
import http.server, os, sys
root, port = sys.argv[1], int(sys.argv[2])
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=root, **k)
    def log_message(self, *a): pass
    def send_error(self, code, message=None, explain=None):
        p = os.path.join(root, "404.html")
        if code == 404 and os.path.exists(p):
            body = open(p, "rb").read()
            self.send_response(404); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers()
            if self.command != "HEAD": self.wfile.write(body)
        else:
            super().send_error(code, message, explain)
http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
