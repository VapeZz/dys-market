"""Tests for tools/history_pull.py as the nightly tcgcsv full-file archive (no network: a fake tcgcsv and a fake
GitHub run on localhost). Synthetic 7z days are built with py7zr.

    python -m unittest tests/test_tcgcsv_daily.py
"""
import hashlib, http.server, io, json, os, re, shutil, socketserver, subprocess, sys, tempfile, threading, unittest
from datetime import date, timedelta
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
try:
    import py7zr
except ImportError:  # pragma: no cover
    py7zr = None


def make_day(day, rows=3):
    """A small tcgcsv-style archive: <day>/3/<gid>/prices and <day>/85/<gid>/prices."""
    buf = io.BytesIO()
    with py7zr.SevenZipFile(buf, "w") as z:
        for cat in ("3", "85"):
            res = [{"productId": 1000 + i, "subTypeName": "Holofoil", "marketPrice": 1.5 + i, "lowPrice": 1.0,
                    "midPrice": 1.4, "highPrice": 9.0, "directLowPrice": None} for i in range(rows)]
            z.writestr(json.dumps({"success": True, "errors": [], "results": res}), f"{day}/{cat}/{int(cat) * 7}/prices")
    return buf.getvalue()


def s3_etag(data):
    return '"' + hashlib.md5(hashlib.md5(data).digest()).hexdigest() + '-1"'


class World:
    """State of the fake tcgcsv and fake GitHub."""
    def __init__(self):
        self.files, self.faults = {}, {}        # day -> bytes ; day -> fault name
        self.releases, self.assets = {}, {}     # tag -> id ; id -> {name: asset}
        self.upload_fault, self.uploads, self.deletes, self.downloads = None, [], [], []
        self.next_id = 100
        self.artifacts, self.actions_read = [], True     # [{id, name, expired, created_at, zip}]


class Handler(http.server.BaseHTTPRequestHandler):
    world = None

    def log_message(self, *a):
        pass

    def send(self, status, body=b"", headers=None):
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        w, u = self.world, urlparse(self.path)
        m = re.fullmatch(r"/archive/tcgplayer/prices-(\d{4}-\d\d-\d\d)\.ppmd\.7z", u.path)
        if m:
            day = m.group(1); w.downloads.append(day)
            fault, data = w.faults.get(day), w.files.get(day)
            if data is None or fault == "missing":
                return self.send(404, b"<Error>NoSuchKey</Error>")
            if fault == "server_error":
                return self.send(503, b"slow down")
            if fault == "truncated":           # claims the full length, sends half, closes
                self.send_response(200); self.send_header("Content-Length", str(len(data))); self.send_header("ETag", s3_etag(data))
                self.end_headers(); self.wfile.write(data[: len(data) // 2]); self.wfile.flush()
                self.close_connection = True
                return
            if fault == "reset":                 # connection dropped before any body
                self.close_connection = True
                self.connection.shutdown(2)
                return
            body, etag = data, s3_etag(data)
            if fault == "corrupt":               # one byte flipped in transit, ETag of the real file
                b = bytearray(data); b[len(b) // 2] ^= 0xFF; body = bytes(b)
            if fault == "corrupt_no_etag":
                b = bytearray(data); b[-20] ^= 0xFF; body, etag = bytes(b), None
            hdr = {"Content-Type": "application/octet-stream"}
            if etag:
                hdr["ETag"] = etag
            return self.send(200, body, hdr)
        if u.path == "/repos/VapeZz/dys-market/actions/artifacts":
            if not w.actions_read:
                return self.send(403, b'{"message":"Resource not accessible by integration"}')
            name = parse_qs(u.query).get("name", [None])[0]
            rows = [{k: v for k, v in a.items() if k != "zip"} for a in w.artifacts if name in (None, a["name"])]
            return self.send(200, json.dumps({"total_count": len(rows), "artifacts": rows}).encode())
        m = re.fullmatch(r"/repos/VapeZz/dys-market/actions/artifacts/(\d+)/zip", u.path)
        if m:
            if not w.actions_read:
                return self.send(403, b"{}")
            host = self.headers.get("Host")
            return self.send(302, b"", {"Location": f"http://{host}/signed/{m.group(1)}"})
        m = re.fullmatch(r"/signed/(\d+)", u.path)
        if m:
            a = next((a for a in w.artifacts if a["id"] == int(m.group(1))), None)
            return self.send(200, a["zip"]) if a else self.send(404)
        m = re.fullmatch(r"/repos/[^/]+/[^/]+/releases/tags/(.+)", u.path)
        if m:
            tag = m.group(1)
            if tag not in w.releases:
                return self.send(404, b'{"message":"Not Found"}')
            return self.send(200, json.dumps({"id": w.releases[tag], "tag_name": tag}).encode())
        m = re.fullmatch(r"/repos/[^/]+/[^/]+/releases/(\d+)/assets", u.path)
        if m:
            rows = list(w.assets.get(int(m.group(1)), {}).values())
            page = int(parse_qs(u.query).get("page", ["1"])[0]); per = int(parse_qs(u.query).get("per_page", ["30"])[0])
            return self.send(200, json.dumps(rows[(page - 1) * per: page * per]).encode())
        self.send(404, b"{}")

    def do_POST(self):
        w, u = self.world, urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0); data = self.rfile.read(n)
        if re.fullmatch(r"/repos/[^/]+/[^/]+/releases", u.path):
            tag = json.loads(data)["tag_name"]; w.next_id += 1; w.releases[tag] = w.next_id
            return self.send(201, json.dumps({"id": w.next_id}).encode())
        m = re.fullmatch(r"/repos/[^/]+/[^/]+/releases/(\d+)/assets", u.path)
        if m:
            rid, name = int(m.group(1)), parse_qs(u.query)["name"][0]
            w.uploads.append(name)
            if w.upload_fault == "error":
                return self.send(500, b'{"message":"Server Error"}')
            if name in w.assets.setdefault(rid, {}):
                return self.send(422, b'{"message":"Validation Failed","errors":[{"code":"already_exists"}]}')
            stored = data if w.upload_fault != "mangle" else data[:-1] + bytes([data[-1] ^ 0xFF])
            asset = {"name": name, "size": len(stored), "state": "uploaded", "digest": "sha256:" + hashlib.sha256(stored).hexdigest()}
            w.assets[rid][name] = asset
            return self.send(201, json.dumps(asset).encode())
        self.send(404, b"{}")

    def do_DELETE(self):
        self.world.deletes.append(self.path)
        self.send(204)


class Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


@unittest.skipIf(py7zr is None, "needs py7zr")
class NightlyArchiveTests(unittest.TestCase):
    END = date(2026, 11, 18)

    def setUp(self):
        self.w = World()
        Handler.world = self.w
        self.srv = Threaded(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.tmp = tempfile.mkdtemp(prefix="dys-test-tcgcsv-")
        for i in range(14):
            d = (self.END - timedelta(days=i)).isoformat()
            self.w.files[d] = make_day(d, rows=2 + i % 3)
        self.w.releases["tcgcsv-2026"] = 1
        self.w.assets[1] = {}

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def keep_as_artifact(self, out, run_no):
        """What actions/upload-artifact does with pull-out/ at the end of a run (a zip of its files)."""
        files = sorted(os.listdir(out)) if os.path.isdir(out) else []
        if not files:
            return None
        buf = io.BytesIO()
        import zipfile
        with zipfile.ZipFile(buf, "w") as z:
            for f in files:
                z.write(os.path.join(out, f), f)
        self.w.next_id += 1
        self.w.artifacts.append({"id": self.w.next_id, "name": "tcgcsv-unsaved", "expired": False,
                                 "created_at": f"2026-11-{18 + run_no:02d}T05:00:00Z", "zip": buf.getvalue()})
        return self.w.next_id

    def fresh_runner(self):
        """A later run starts on a new machine: nothing from the earlier run's folders is left."""
        shutil.rmtree(os.path.join(self.tmp, "repo"), ignore_errors=True)

    def run_pull(self, start=None, end=None, **extra):
        env = dict(os.environ, GH_TOKEN="test", GITHUB_REPOSITORY="VapeZz/dys-market", TCGCSV_BASE=self.base,
                   GITHUB_API_URL=self.base, GITHUB_UPLOADS_URL=self.base, PULL_PAUSE="0", PULL_RETRY_WAIT="0",
                   PULL_STORE_WAIT_SCALE="0", PULL_START=(start or (self.END - timedelta(days=13))).isoformat(),
                   PULL_END=(end or self.END).isoformat(), **extra)
        env.pop("GITHUB_STEP_SUMMARY", None)
        work = os.path.join(self.tmp, "repo")
        if not os.path.isdir(work):
            shutil.copytree(os.path.join(ROOT, "tools"), os.path.join(work, "tools"))
            shutil.copytree(os.path.join(ROOT, "pipeline"), os.path.join(work, "pipeline"))
        r = subprocess.run([sys.executable, os.path.join(work, "tools", "history_pull.py")], env=env, capture_output=True, text=True, timeout=120)
        return r, os.path.join(work, "pull-out")

    def stored(self):
        return self.w.assets[1]

    def assertStoredExactly(self, day):
        a = self.stored()[f"prices-{day}.ppmd.7z"]
        self.assertEqual(a["digest"], "sha256:" + hashlib.sha256(self.w.files[day]).hexdigest())

    def test_fresh_window_stores_every_day_exactly(self):
        r, _ = self.run_pull()
        self.assertIn("RESULT: COMPLETE", r.stdout, r.stdout + r.stderr)
        self.assertEqual(len(self.stored()), 14)
        for d in self.w.files:
            self.assertStoredExactly(d)

    def test_rerun_downloads_and_uploads_nothing(self):
        self.run_pull()
        dl, up = len(self.w.downloads), len(self.w.uploads)
        r, _ = self.run_pull()
        self.assertIn("14 already stored, 0 to fetch", r.stdout)
        self.assertEqual((len(self.w.downloads), len(self.w.uploads)), (dl, up))

    def test_missing_day_at_tcgcsv_is_reported_and_others_stored(self):
        miss = (self.END - timedelta(days=3)).isoformat()
        self.w.faults[miss] = "missing"
        r, _ = self.run_pull()
        self.assertIn(miss, r.stdout)
        self.assertNotIn(f"prices-{miss}.ppmd.7z", self.stored())
        self.assertEqual(len(self.stored()), 13)

    def test_partial_download_not_stored_then_recovers(self):
        bad = (self.END - timedelta(days=1)).isoformat()
        self.w.faults[bad] = "truncated"
        r, _ = self.run_pull()
        self.assertNotIn(f"prices-{bad}.ppmd.7z", self.stored(), r.stdout)
        self.assertEqual(len(self.stored()), 13)
        del self.w.faults[bad]
        r, _ = self.run_pull()
        self.assertStoredExactly(bad)
        self.assertEqual(len(self.stored()), 14)

    def test_corrupted_download_rejected_by_etag(self):
        bad = (self.END - timedelta(days=2)).isoformat()
        self.w.faults[bad] = "corrupt"
        r, _ = self.run_pull()
        self.assertIn("ETag", r.stdout)
        self.assertNotIn(f"prices-{bad}.ppmd.7z", self.stored())

    def test_corrupted_download_without_etag_rejected_by_archive_test(self):
        bad = (self.END - timedelta(days=4)).isoformat()
        self.w.faults[bad] = "corrupt_no_etag"
        r, _ = self.run_pull()
        self.assertIn("integrity test", r.stdout)
        self.assertNotIn(f"prices-{bad}.ppmd.7z", self.stored())

    def test_interrupted_transfer_not_stored_then_recovers(self):
        bad = self.END.isoformat()
        self.w.faults[bad] = "reset"
        self.run_pull()
        self.assertNotIn(f"prices-{bad}.ppmd.7z", self.stored())
        del self.w.faults[bad]
        self.run_pull()
        self.assertStoredExactly(bad)

    def test_three_refusals_in_a_row_stop_the_run(self):
        for i in range(3):
            self.w.faults[(self.END - timedelta(days=i)).isoformat()] = "server_error"
        r, _ = self.run_pull()
        self.assertIn("RESULT: STOPPED", r.stdout)
        self.assertEqual(len(self.stored()), 0)
        self.assertEqual(len(self.w.downloads), 3)

    def test_existing_files_are_never_replaced_or_deleted(self):
        keep = (self.END - timedelta(days=5)).isoformat()
        old = b"7z\xbc\xaf\x27\x1c an older stored copy"
        self.stored()[f"prices-{keep}.ppmd.7z"] = {"name": f"prices-{keep}.ppmd.7z", "size": len(old), "state": "uploaded",
                                                   "digest": "sha256:" + hashlib.sha256(old).hexdigest()}
        self.run_pull()
        self.assertEqual(self.stored()[f"prices-{keep}.ppmd.7z"]["digest"], "sha256:" + hashlib.sha256(old).hexdigest())
        self.assertNotIn(keep, self.w.downloads)      # a stored day isn't fetched again
        self.assertEqual(self.w.deletes, [])

    def test_unfinished_upload_with_same_name_stops_without_replacing(self):
        day = self.END.isoformat()
        self.stored()[f"prices-{day}.ppmd.7z"] = {"name": f"prices-{day}.ppmd.7z", "size": 10, "state": "starter", "digest": None}
        r, out = self.run_pull()
        self.assertIn("RESULT: STOPPED", r.stdout)
        self.assertEqual(self.stored()[f"prices-{day}.ppmd.7z"]["state"], "starter")
        self.assertTrue(os.path.exists(os.path.join(out, f"prices-{day}.ppmd.7z")))   # kept for the artifact
        self.assertEqual(self.w.deletes, [])

    def test_upload_failure_keeps_file_and_next_run_recovers(self):
        self.w.upload_fault = "error"
        r, out = self.run_pull()
        self.assertIn("RESULT: STOPPED", r.stdout)
        kept = os.path.join(out, f"prices-{self.END.isoformat()}.ppmd.7z")
        self.assertTrue(os.path.exists(kept))
        with open(kept, "rb") as f:
            self.assertEqual(f.read(), self.w.files[self.END.isoformat()])
        self.w.upload_fault = None
        r, _ = self.run_pull()
        self.assertIn("RESULT: COMPLETE", r.stdout)
        self.assertEqual(len(self.stored()), 14)

    def test_github_copy_that_differs_is_not_counted_as_stored(self):
        self.w.upload_fault = "mangle"
        r, out = self.run_pull()
        self.assertIn("doesn't match what was sent", r.stdout)
        self.assertIn("RESULT: STOPPED", r.stdout)

    def test_new_year_release_created_when_needed(self):
        self.w.files["2027-01-01"] = make_day("2027-01-01")
        r, _ = self.run_pull(start=date(2027, 1, 1), end=date(2027, 1, 1))
        self.assertIn("tcgcsv-2027", self.w.releases)
        self.assertIn("prices-2027-01-01.ppmd.7z", self.w.assets[self.w.releases["tcgcsv-2027"]])

    # ---- two separate runs: a day GitHub refused in run 1 is stored from run 1's artifact in run 2 ----
    def test_run2_stores_run1_artifact_without_downloading_again(self):
        day = self.END.isoformat()
        self.w.upload_fault = "error"
        r1, out = self.run_pull(SEED_RECENT="tcgcsv-unsaved")
        self.assertIn("RESULT: STOPPED", r1.stdout)
        self.assertIsNotNone(self.keep_as_artifact(out, 1))
        self.assertEqual(self.w.downloads.count(day), 1)
        self.fresh_runner()
        self.w.upload_fault = None
        r2, out2 = self.run_pull(SEED_RECENT="tcgcsv-unsaved")
        self.assertIn("from an earlier run", r2.stdout)
        self.assertIn("RESULT: COMPLETE", r2.stdout)
        self.assertStoredExactly(day)
        self.assertEqual(self.w.downloads.count(day), 1)          # not fetched from tcgcsv a second time
        self.assertEqual(len(self.stored()), 14)
        self.assertFalse(os.path.isdir(out2) and os.listdir(out2))  # nothing left to keep after run 2

    def test_run3_after_artifact_used_does_nothing(self):
        self.w.upload_fault = "error"
        _, out = self.run_pull(SEED_RECENT="tcgcsv-unsaved"); self.keep_as_artifact(out, 1)
        self.fresh_runner(); self.w.upload_fault = None
        self.run_pull(SEED_RECENT="tcgcsv-unsaved")
        self.fresh_runner()
        up = len(self.w.uploads)
        r3, _ = self.run_pull(SEED_RECENT="tcgcsv-unsaved")
        self.assertIn("14 already stored, 0 to fetch", r3.stdout)
        self.assertEqual(len(self.w.uploads), up)                 # the old artifact is seen as already stored

    def test_expired_artifact_ignored_and_day_downloaded(self):
        day = self.END.isoformat()
        self.w.upload_fault = "error"
        _, out = self.run_pull(SEED_RECENT="tcgcsv-unsaved"); self.keep_as_artifact(out, 1)
        self.w.artifacts[-1]["expired"] = True
        self.fresh_runner(); self.w.upload_fault = None
        r2, _ = self.run_pull(SEED_RECENT="tcgcsv-unsaved")
        self.assertStoredExactly(day)
        self.assertEqual(self.w.downloads.count(day), 2)

    def test_corrupted_artifact_not_used(self):
        day = self.END.isoformat()
        self.w.upload_fault = "error"
        _, out = self.run_pull(SEED_RECENT="tcgcsv-unsaved")
        path = os.path.join(out, f"prices-{day}.ppmd.7z")
        with open(path, "rb") as f:
            b = bytearray(f.read())
        b[-20] ^= 0xFF
        with open(path, "wb") as f:
            f.write(bytes(b))
        self.keep_as_artifact(out, 1)
        self.fresh_runner(); self.w.upload_fault = None
        r2, _ = self.run_pull(SEED_RECENT="tcgcsv-unsaved")
        self.assertIn("integrity test; not used", r2.stdout)
        self.assertStoredExactly(day)                             # downloaded fresh instead

    def test_without_actions_read_falls_back_to_download(self):
        day = self.END.isoformat()
        self.w.upload_fault = "error"
        _, out = self.run_pull(SEED_RECENT="tcgcsv-unsaved"); self.keep_as_artifact(out, 1)
        self.w.actions_read = False
        self.fresh_runner(); self.w.upload_fault = None
        r2, _ = self.run_pull(SEED_RECENT="tcgcsv-unsaved")
        self.assertIn("couldn't list earlier runs' files (HTTP 403)", r2.stdout)
        self.assertStoredExactly(day)

    def test_default_settings_unchanged_for_manual_use(self):
        """No PULL_* settings: the original range (Feb 8, 2024 to the day before SEALED_BEFORE), all stored -> nothing to do."""
        d = date(2024, 2, 8)
        self.w.releases.update({"tcgcsv-2024": 2, "tcgcsv-2025": 3})
        while d <= date(2026, 10, 11):
            rid = {"2024": 2, "2025": 3, "2026": 1}[str(d.year)]
            self.w.assets.setdefault(rid, {})[f"prices-{d}.ppmd.7z"] = {"name": f"prices-{d}.ppmd.7z", "size": 1, "state": "uploaded", "digest": None}
            d += timedelta(days=1)
        env = dict(os.environ, GH_TOKEN="test", TCGCSV_BASE=self.base, GITHUB_API_URL=self.base, GITHUB_UPLOADS_URL=self.base)
        for k in ("PULL_START", "PULL_END", "SEED_RECENT", "GITHUB_STEP_SUMMARY"):
            env.pop(k, None)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "history_pull.py")], env=env, capture_output=True, text=True, timeout=120)
        self.assertIn("History pull 2024-02-08 to 2026-10-11: 977 days wanted, 977 already stored, 0 to fetch", r.stdout, r.stderr)
        self.assertEqual(self.w.downloads, [])


class EtagTests(unittest.TestCase):
    def test_forms(self):
        import history_pull as hp
        data = b"abc" * 1000
        md5 = hashlib.md5(data)
        self.assertTrue(hp.etag_matches(data, '"' + md5.hexdigest() + '"'))
        self.assertTrue(hp.etag_matches(data, '"' + hashlib.md5(md5.digest()).hexdigest() + '-1"'))
        self.assertFalse(hp.etag_matches(data + b"x", '"' + md5.hexdigest() + '"'))
        self.assertIsNone(hp.etag_matches(data, '"' + md5.hexdigest() + '-3"'))   # multi-part: can't check
        self.assertIsNone(hp.etag_matches(data, None))
        self.assertTrue(hp.etag_matches(data, 'W/"' + md5.hexdigest() + '"'))


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(py7zr is None, "needs py7zr")
class WorkflowStepTests(unittest.TestCase):
    """The new archive.yml steps: structure, and their shell run against the fakes (incl. failures)."""
    @classmethod
    def setUpClass(cls):
        try:
            import yaml
        except ImportError:  # pragma: no cover
            raise unittest.SkipTest("needs PyYAML")
        with open(os.path.join(ROOT, ".github", "workflows", "archive.yml"), encoding="utf-8") as f:
            cls.wf = yaml.safe_load(f)
        cls.steps = cls.wf["jobs"]["archive"]["steps"]

    def test_structure(self):
        wf, names = self.wf, [s.get("name") for s in self.steps]
        on = wf.get("on", wf.get(True))
        self.assertEqual(on["schedule"], [{"cron": "15 23 * * *"}])
        self.assertEqual(wf["permissions"], {"contents": "write", "actions": "read"})
        self.assertEqual(wf["concurrency"], {"group": "archive", "cancel-in-progress": False})
        i = names.index("Upload to the monthly releases")
        new = self.steps[i + 1:]
        self.assertEqual([s["name"] for s in new], ["Keep tcgcsv's full daily price file",
                                                   "Keep any tcgcsv file GitHub didn't store (the next run stores it from here)"])
        for s in new:
            self.assertIs(s.get("continue-on-error"), True)       # can't fail the job
        self.assertEqual(new[1]["with"]["name"], "tcgcsv-unsaved")
        self.assertEqual(new[1]["with"]["retention-days"], 14)
        for s in self.steps[: i + 1]:
            self.assertNotIn("continue-on-error", s)              # the original steps are as they were

    def run_step(self, base, day_txt="2026-11-18", tcgcsv_from="", break_github=False):
        script = self.steps[-2]["run"].replace("which 7z || sudo apt-get install -y p7zip-full", "true")
        tmp = tempfile.mkdtemp(prefix="dys-step-")
        shutil.copytree(os.path.join(ROOT, "tools"), os.path.join(tmp, "tools"))
        shutil.copytree(os.path.join(ROOT, "pipeline"), os.path.join(tmp, "pipeline"))
        if day_txt is not None:
            os.makedirs(os.path.join(tmp, "archive-out"))
            with open(os.path.join(tmp, "archive-out", "day.txt"), "w") as f:
                f.write(day_txt)
        api = "http://127.0.0.1:9" if break_github else base
        env = dict(os.environ, GH_TOKEN="t", TCGCSV_FROM=tcgcsv_from, TCGCSV_BASE=base, GITHUB_API_URL=api,
                   GITHUB_UPLOADS_URL=api, GITHUB_REPOSITORY="VapeZz/dys-market", PULL_RETRY_WAIT="0", PULL_STORE_WAIT_SCALE="0")
        env.pop("GITHUB_STEP_SUMMARY", None)
        r = subprocess.run(["bash", "-e", "-c", script.replace("python ", sys.executable + " ")], cwd=tmp, env=env,
                           capture_output=True, text=True, timeout=300)
        shutil.rmtree(tmp, ignore_errors=True)
        return r

    def test_step_shell_normal_and_failures(self):
        w = World(); Handler.world = w
        for i in range(14):
            d = (date(2026, 11, 18) - timedelta(days=i)).isoformat(); w.files[d] = make_day(d)
        w.releases["tcgcsv-2026"] = 1; w.assets[1] = {}
        srv = Threaded(("127.0.0.1", 0), Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            r = self.run_step(base)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("History pull 2026-11-05 to 2026-11-18", r.stdout)       # 14-day window from day.txt
            self.assertEqual(len(w.assets[1]), 14)
            r = self.run_step(base, tcgcsv_from="2026-11-10")
            self.assertIn("History pull 2026-11-10 to 2026-11-18", r.stdout)
            # failures end the step with an error code; continue-on-error keeps the job green
            self.assertNotEqual(self.run_step(base, day_txt=None).returncode, 0)
            self.assertNotEqual(self.run_step(base, tcgcsv_from="not-a-date").returncode, 0)
            self.assertNotEqual(self.run_step(base, break_github=True).returncode, 0)
            w.faults = {d: "server_error" for d in w.files}; w.assets[1] = {}
            r = self.run_step(base)                                                  # tcgcsv down: stops, no crash
            self.assertIn("RESULT: STOPPED", r.stdout)
        finally:
            srv.shutdown(); srv.server_close()
