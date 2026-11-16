"""Tests for tools/backup_pack.py: the weekly backup records only what was verified on the computer.

Everything is synthetic: a small git repo built here, fake release files, and a fake "DYS Backup" folder that
behaves like the Windows one the task writes to (names ignore case, nothing can be deleted or renamed, writes can
fail half way). No network, no real data, no real backup folder.

    python -m unittest tests/test_backup_pack.py
"""
import contextlib, errno, gzip, hashlib, io, json, os, shutil, subprocess, sys, tempfile, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import backup_pack as bp

ROOT = bp.DEST_ROOT


def git(*a, cwd=None):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout


def make_mirror(base, days=12, extra_files=6):
    """A mirror clone with main, gh-pages and data branches, like the real repo but tiny."""
    w = os.path.join(base, "work")
    os.makedirs(w)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    os.environ.update(env)
    git("init", "-q", "-b", "main", cwd=w)
    wtext(os.path.join(w, "README.md"), "code\n")
    git("add", "-A", cwd=w); git("commit", "-qm", "code", cwd=w)
    git("checkout", "-q", "--orphan", "gh-pages", cwd=w); git("rm", "-rqf", ".", cwd=w)
    wtext(os.path.join(w, "index.html"), "<html>site</html>\n")
    git("add", "-A", cwd=w); git("commit", "-qm", "site", cwd=w)
    git("checkout", "-q", "--orphan", "data", cwd=w); git("rm", "-rqf", ".", cwd=w)
    os.makedirs(os.path.join(w, "data", "snapshots"))
    for i in range(days):
        with gzip.open(os.path.join(w, "data", "snapshots", f"2026-11-{10 + i:02d}.json.gz"), "wt") as f:
            json.dump({"1:Normal": 100 + i, "pad": "x" * 2000}, f)
    wtext(os.path.join(w, "data", "snapshots", "2026-10-01.json.gz.enc"), os.urandom(256), "wb")
    for i in range(extra_files):
        wtext(os.path.join(w, "data", f"other-{i}.json"), json.dumps({"i": i, "pad": "y" * 3000}))
    git("add", "-A", cwd=w); git("commit", "-qm", "data", cwd=w)
    m = os.path.join(base, "mirror.git")
    git("clone", "-q", "--mirror", w, m)
    return m


RELEASES = {
    "archive-2026-10": [("pokemon-2026-10-31.json.gz", b"oct" * 50)],
    "archive-2026-11": [("pokemon-2026-11-01.json.gz", b"nov1" * 50), ("pokemon-2026-11-02.json.gz", b"nov2" * 50)],
    "archive-2026-12": [("pokemon-2026-12-01.json.gz", b"dec1" * 50)],
}


def fake_assets(_repo, tag):
    return [(n, len(b), f"mem://{tag}/{n}") for n, b in RELEASES.get(tag, [])]


def fake_get(url, timeout=60):
    tag, name = url[len("mem://"):].split("/", 1)
    return dict(RELEASES[tag])[name]


class Computer:
    """The backup folder on Skibidi as the task's tools see it: list, write (commit) and read back (stage)."""

    def __init__(self, base):
        self.dir = os.path.join(base, "skibidi")
        self.stage_dir = os.path.join(base, "uploads")
        os.makedirs(self.dir)
        self.writes = []

    def _real(self, dest):
        """Windows: an existing file is found whatever the case of the name."""
        parts, cur = dest.replace("/", "\\").split("\\"), self.dir
        for p in parts:
            hit = [n for n in (os.listdir(cur) if os.path.isdir(cur) else []) if n.lower() == p.lower()]
            cur = os.path.join(cur, hit[0] if hit else p)
        return cur

    def put(self, dest, data):
        p = self._real(dest)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)

    def get(self, dest):
        with open(self._real(dest), "rb") as f:
            return f.read()

    def exists(self, dest):
        return os.path.exists(self._real(dest))

    def listing(self, sep="/"):
        out = []
        for r, _d, fs in os.walk(self.dir):
            for f in fs:
                rel = os.path.relpath(os.path.join(r, f), self.dir).replace(os.sep, sep)
                out.append({"name": rel, "type": "file", "size": os.path.getsize(os.path.join(r, f))})
        return {"entries": out}

    def commit(self, dest, src, fault=None):
        with open(src, "rb") as f:
            data = f.read()
        self.writes.append(dest)
        if fault == "missing":
            return
        p = self._real(dest)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if fault == "corrupt":
            data = data[:-1] + bytes([data[-1] ^ 0xFF])
        if fault in ("truncate", "enospc", "interrupt"):
            with open(p, "wb") as f:
                f.write(data[: len(data) // 2])
            if fault == "enospc":
                raise OSError(errno.ENOSPC, "There is not enough space on the disk")
            if fault == "interrupt":
                raise ConnectionError("bridge dropped")
            return
        with open(p, "wb") as f:
            f.write(data)

    def stage(self, dests):
        out = []
        for d in dests:
            src = self._real(d)
            if not os.path.exists(src):
                out.append({"devicePath": ROOT + "\\" + d, "ok": False, "error": "not found"})
                continue
            dst = os.path.join(self.stage_dir, "DYS Backup", d.replace("\\", "/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            out.append({"devicePath": ROOT + "\\" + d, "stagedPath": dst, "ok": True})
        return out

    def snapshot(self, prefix=""):
        """{relative path: sha256} of everything under prefix: to prove files were left alone."""
        out = {}
        for r, _d, fs in os.walk(self.dir):
            for f in fs:
                rel = os.path.relpath(os.path.join(r, f), self.dir).replace(os.sep, "\\")
                if rel.lower().startswith(prefix.lower()):
                    with open(os.path.join(r, f), "rb") as fh:
                        out[rel] = hashlib.sha256(fh.read()).hexdigest()
        return out


def call(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = bp.main(list(argv))
    return code, buf.getvalue()


def jload(path):
    with open(path) as f:
        return json.load(f)


def wtext(path, text, mode="w"):
    with open(path, mode) as f:
        f.write(text)


def jdump(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f)


def run_task(pc, mirror, today, work, faults=None, recover="", always=(), sep="/"):
    """What the weekly task does, step by step (tools/BACKUP-TASK.md). faults: {dest: kind} applied on the
    first write of that file; dests in `always` fail every time. Returns (result line, out dir)."""
    faults = dict(faults or {})
    os.makedirs(work, exist_ok=True)
    out = os.path.join(work, "out")
    # 2-3: list the folder; read back the state and the newest history copies
    jdump(os.path.join(work, "before.json"), pc.listing(sep))
    if not pc.exists("backup-state.json"):
        return "FAILED: backup folder or backup-state.json missing", out
    hist = sorted(e["name"] for e in pc.listing("\\")["entries"] if e["name"].lower().startswith("state-history\\"))[-3:]
    staged = pc.stage(["backup-state.json"] + hist)
    hdir = os.path.join(work, "hist")
    shutil.rmtree(hdir, ignore_errors=True)
    os.makedirs(hdir)
    for s in staged[1:]:
        shutil.copyfile(s["stagedPath"], os.path.join(hdir, os.path.basename(s["stagedPath"])))
    state = os.path.join(work, "backup-state.json")
    shutil.copyfile(staged[0]["stagedPath"], state)
    # 4: pack
    args = ["pack", "--out", out, "--state", state, "--state-history", hdir, "--dest-listing",
            os.path.join(work, "before.json"), "--mirror", mirror, "--today", today]
    if recover:
        args += ["--recover-month", recover]
    code, text = call(*args)
    if code != 0:
        return text.strip().splitlines()[-1], out
    plan = jload(os.path.join(out, "plan.json"))

    def write(dest, local):
        f = "corrupt" if dest in always and faults.get(dest) == "corrupt" else faults.pop(dest, None)
        if dest in always:
            f = f or "missing"
        try:
            pc.commit(dest, local, f)
        except (OSError, ConnectionError):
            pass                                  # the tool call failed; verification decides
    # 6: copy the data files
    for t in plan["transfer"]:
        write(t["dest"], t["local"])
    # 7: list again, read everything back, verify
    jdump(os.path.join(work, "after.json"), pc.listing(sep))
    staged = []
    for b in plan["stage_batches"]:
        staged += pc.stage(b)
    jdump(os.path.join(work, "staged.json"), staged)
    code, text = call("verify", "--out", out, "--dest-listing", os.path.join(work, "after.json"), "--staged", os.path.join(work, "staged.json"))
    if code != 0:
        v = jload(os.path.join(out, "verify.json"))
        if v["verdict"] != "retry":
            return text.strip().splitlines()[0], out
        local = {t["dest"]: t["local"] for t in plan["transfer"]}
        for d in v["resend"]:
            write(d, local[d])
        jdump(os.path.join(work, "after.json"), pc.listing(sep))
        staged = [s for s in staged if s.get("devicePath", "").split(ROOT + "\\")[-1] not in v["resend"]] + pc.stage(v["resend"])
        jdump(os.path.join(work, "staged.json"), staged)
        code, text = call("verify", "--out", out, "--dest-listing", os.path.join(work, "after.json"),
                          "--staged", os.path.join(work, "staged.json"), "--attempt", "2")
        if code != 0:
            return text.strip().splitlines()[0], out
    # 9: write the state files in order, read them back, confirm
    commit = jload(os.path.join(out, "commit.json"))
    for c in commit["files"]:
        write(c["dest"], c["local"])
    jdump(os.path.join(work, "final.json"), pc.listing(sep))
    jdump(os.path.join(work, "staged-commit.json"), pc.stage([c["dest"] for c in commit["files"]]))
    code, text = call("confirm", "--out", out, "--dest-listing", os.path.join(work, "final.json"),
                      "--staged", os.path.join(work, "staged-commit.json"))
    return text.strip().splitlines()[-1], out


def legacy_state():
    """Shaped like the real version-1 state after the Nov 15 run: November recorded, its zip never copied."""
    return {"version": 1, "newest_slot": "weekly-1", "months": ["2026-11"],
            "archives": {"archive-2026-10": {"files": 1, "final": True}, "archive-2026-11": {"files": 2, "final": False}},
            "last_good": {"date": "2026-11-15", "files": 13, "bytes": 1, "price_days": 12, "price_bytes": 1},
            "runs": [{"date": "2026-11-15", "verdict": "ok", "slot": "weekly-1"}], "tcgcsv_days": 0}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="dys-test-backup-")
        cls.mirror = make_mirror(os.path.join(cls.tmp, "repo"))
        cls.small = make_mirror(os.path.join(cls.tmp, "small"), days=2, extra_files=0)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.base = tempfile.mkdtemp(dir=self.tmp)
        self.pc = Computer(self.base)
        self.n = 0
        self.patches = [mock.patch.object(bp, "release_assets", fake_assets), mock.patch.object(bp, "_get", fake_get),
                        mock.patch.object(bp, "release_counts", lambda repo: {"tcgcsv-2024": 0})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def seed_legacy(self, state=None):
        """The folder as it is today: two weekly slots, November's price archive, no monthly folder."""
        for slot in bp.SLOTS:
            for f in ("saved-data.zip", "repo-code.bundle", "repo-live-site.bundle", "FILE-LIST.txt"):
                self.pc.put(f"{slot}\\{f}", f"old {slot} {f}".encode())
        self.pc.put("price-archives-monthly\\archive-2026-11.tar", b"old tar")
        self.pc.put("README.txt", b"readme")
        self.pc.put("backup-state.json", json.dumps(state or legacy_state()).encode())

    def task(self, today, **kw):
        self.n += 1
        return run_task(self.pc, kw.pop("mirror", self.mirror), today, os.path.join(self.base, f"run{self.n}"), **kw)

    def state(self):
        return json.loads(self.pc.get("backup-state.json"))


class NormalRuns(Base):
    def test_november_record_without_its_file_is_flagged_not_rebuilt(self):
        self.seed_legacy()
        newest_before = self.pc.snapshot("weekly-1")
        line, _ = self.task("2026-11-22")
        self.assertTrue(line.startswith("DYS backup OK:"), line)
        self.assertIn("2026-11 is listed in the backup record", line)                 # Keo is told
        s = self.state()
        self.assertEqual(s["version"], 2)
        self.assertTrue(bp.intact(s))
        self.assertEqual(s["monthly"]["2026-11"]["status"], "needs-recovery")
        self.assertFalse(any(k.lower().startswith("monthly") for k in self.pc.snapshot()))   # no stand-in made
        self.assertEqual(s["newest_slot"], "weekly-2")                                     # wrote the older slot
        self.assertEqual(self.pc.snapshot("weekly-1"), newest_before)                     # last good copy untouched
        self.assertEqual(self.pc.get("price-archives-monthly\\archive-2026-11.tar"), b"old tar")   # never overwritten
        self.assertTrue(self.pc.exists("price-archives-monthly\\archive-2026-11.asof-2026-11-22.tar"))

    def test_new_month_is_recorded_with_what_is_on_the_computer(self):
        self.seed_legacy()
        line, _ = self.task("2026-12-06")
        self.assertTrue(line.startswith("DYS backup OK:"), line)
        rec = self.state()["monthly"]["2026-12"]
        self.assertEqual(rec["status"], "verified")
        (dest, f), = rec["files"].items()
        self.assertEqual(dest, "monthly\\saved-data-2026-12.zip")
        self.assertEqual(hashlib.sha256(self.pc.get(dest)).hexdigest(), f["sha256"])

    def test_repeated_weekly_runs_rotate_and_keep_the_monthly(self):
        self.seed_legacy()
        slots, seqs = [], []
        for day in ("2026-12-06", "2026-12-13", "2026-12-20", "2026-12-27"):
            line, _ = self.task(day)
            self.assertTrue(line.startswith("DYS backup OK:"), line)
            s = self.state()
            slots.append(s["newest_slot"])
            seqs.append(s["seq"])
            if day == "2026-12-06":
                first = self.pc.snapshot("monthly")
        self.assertEqual(slots, ["weekly-2", "weekly-1", "weekly-2", "weekly-1"])
        self.assertEqual(seqs, [1, 2, 3, 4])
        self.assertEqual(self.pc.snapshot("monthly"), first)               # one monthly copy, never rewritten
        tars = [k for k in self.pc.snapshot("price-archives-monthly") if "archive-2026-12." in k]
        self.assertEqual(len(tars), 4)                                     # a new name each week, none replaced
        hist = sorted(self.pc.snapshot(bp.HISTORY))
        self.assertEqual(len(hist), 5)                                     # 4 runs + the old record kept as it was
        self.assertTrue(hist[0].endswith("000000-legacy-v1.json"))
        self.assertEqual(json.loads(self.pc.get(hist[0])), legacy_state())
        self.assertNotIn("monthly\\saved-data-2026-12.zip", [d for d in self.pc.writes[30:]])

    def test_hold_copies_nothing_and_keeps_both_slots(self):
        self.seed_legacy()
        self.task("2026-12-06")
        before = self.pc.snapshot("weekly")
        line, _ = self.task("2026-12-13", mirror=self.small)               # data shrank: 2 price days instead of 12
        self.assertTrue(line.startswith("DYS backup HELD:"), line)
        self.assertEqual(self.pc.snapshot("weekly"), before)
        s = self.state()
        self.assertEqual(s["runs"][-1]["verdict"], "hold")
        self.assertEqual(s["newest_slot"], "weekly-2")

    def test_legacy_state_month_found_and_good_is_adopted(self):
        st = legacy_state()
        st["months"] = ["2026-12"]
        self.seed_legacy(st)
        buf = io.BytesIO()
        import zipfile
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("data/a.json", "{}")
        self.pc.put("monthly\\saved-data-2026-12.zip", buf.getvalue())
        line, _ = self.task("2026-12-06")
        self.assertTrue(line.startswith("DYS backup OK:"), line)
        rec = self.state()["monthly"]["2026-12"]
        self.assertEqual((rec["status"], rec.get("adopted")), ("verified", True))
        self.assertEqual(self.pc.get("monthly\\saved-data-2026-12.zip"), buf.getvalue())   # read, not rewritten

    def test_legacy_state_month_found_but_damaged_needs_recovery(self):
        st = legacy_state()
        st["months"] = ["2026-12"]
        self.seed_legacy(st)
        self.pc.put("monthly\\saved-data-2026-12.zip", b"PK\x03\x04 not really a zip")
        line, _ = self.task("2026-12-06")
        self.assertTrue(line.startswith("DYS backup OK:"), line)
        self.assertEqual(self.state()["monthly"]["2026-12"]["status"], "needs-recovery")
        self.assertEqual(self.pc.get("monthly\\saved-data-2026-12.zip"), b"PK\x03\x04 not really a zip")


class LaterChanges(Base):
    def test_verified_monthly_that_disappears_is_reported_not_remade(self):
        self.seed_legacy()
        self.task("2026-12-06")
        os.remove(self.pc._real("monthly\\saved-data-2026-12.zip"))
        line, _ = self.task("2026-12-13")
        self.assertTrue(line.startswith("DYS backup OK:"), line)
        self.assertIn("was verified before but is now missing", line)
        self.assertFalse(self.pc.exists("monthly\\saved-data-2026-12-2.zip"))
        self.assertEqual(self.state()["monthly"]["2026-12"]["status"], "verified")

    def test_incomplete_listing_blocks(self):
        self.seed_legacy()
        d = tempfile.mkdtemp(dir=self.tmp)
        listing = dict(self.pc.listing(), truncated=True)
        jdump(os.path.join(d, "before.json"), listing)
        wtext(os.path.join(d, "state.json"), self.pc.get("backup-state.json"), "wb")
        code, text = call("pack", "--out", os.path.join(d, "out"), "--state", os.path.join(d, "state.json"),
                          "--dest-listing", os.path.join(d, "before.json"), "--mirror", self.mirror, "--today", "2026-12-06")
        self.assertEqual(code, 3)
        self.assertIn("incomplete", text)

    def test_staged_results_from_several_calls(self):
        d = tempfile.mkdtemp(dir=self.tmp)
        p = os.path.join(d, "s.json")
        jdump(p, [{"staged": [{"devicePath": ROOT + "\\weekly-1\\a.zip", "stagedPath": "/x/a", "ok": True}]},
                  {"staged": [{"devicePath": ROOT.upper() + "\\WEEKLY-1\\b.zip", "stagedPath": "/x/b", "ok": True},
                              {"devicePath": ROOT + "\\c.zip", "ok": False}]}])
        self.assertEqual(bp.load_staged(p), {"weekly-1\\a.zip": "/x/a", "weekly-1\\b.zip": "/x/b"})


class Failures(Base):
    def setUp(self):
        super().setUp()
        self.seed_legacy()
        self.state_before = self.pc.get("backup-state.json")
        self.newest_before = self.pc.snapshot("weekly-1")

    def assert_nothing_recorded(self):
        self.assertEqual(self.pc.get("backup-state.json"), self.state_before)
        self.assertEqual(self.pc.snapshot(bp.HISTORY), {})
        self.assertEqual(self.pc.snapshot("weekly-1"), self.newest_before)

    def test_missing_file_once_is_resent(self):
        line, _ = self.task("2026-12-06", faults={"monthly\\saved-data-2026-12.zip": "missing"})
        self.assertTrue(line.startswith("DYS backup OK:"), line)
        self.assertEqual(self.state()["monthly"]["2026-12"]["status"], "verified")

    def test_missing_monthly_twice_records_nothing(self):
        line, _ = self.task("2026-12-06", always={"monthly\\saved-data-2026-12.zip"})
        self.assertTrue(line.startswith("FAILED:"), line)
        self.assertIn("not on the computer", line)
        self.assert_nothing_recorded()

    def test_same_size_corruption_is_caught_by_sha256(self):
        line, _ = self.task("2026-12-06", faults={"weekly-2\\saved-data.zip": "corrupt"},
                            always={"weekly-2\\saved-data.zip"})
        self.assertTrue(line.startswith("FAILED:"), line)
        self.assertIn("SHA-256", line)
        self.assert_nothing_recorded()

    def test_disk_full_then_next_run_recovers_without_overwriting(self):
        line, _ = self.task("2026-12-06", faults={"monthly\\saved-data-2026-12.zip": "enospc"},
                            always={"monthly\\saved-data-2026-12.zip"})
        self.assertTrue(line.startswith("FAILED:"), line)
        self.assert_nothing_recorded()
        partial = self.pc.get("monthly\\saved-data-2026-12.zip")
        line, _ = self.task("2026-12-06")                                   # space freed, task runs again
        self.assertTrue(line.startswith("DYS backup OK:"), line)
        self.assertEqual(self.pc.get("monthly\\saved-data-2026-12.zip"), partial)      # the half file is kept as is
        rec = self.state()["monthly"]["2026-12"]
        self.assertEqual(list(rec["files"]), ["monthly\\saved-data-2026-12-2.zip"])
        self.assertEqual(self.state()["newest_slot"], "weekly-2")
        self.assertEqual(self.pc.snapshot("weekly-1"), self.newest_before)

    def test_interrupted_transfer_of_a_weekly_file(self):
        line, _ = self.task("2026-12-06", faults={"weekly-2\\repo-live-site.bundle": "interrupt"},
                            always={"weekly-2\\repo-live-site.bundle"})
        self.assertTrue(line.startswith("FAILED:"), line)
        self.assert_nothing_recorded()
        line, _ = self.task("2026-12-13")
        self.assertTrue(line.startswith("DYS backup OK:"), line)
        self.assertEqual(self.state()["newest_slot"], "weekly-2")          # same slot redone, weekly-1 untouched
        self.assertEqual(self.pc.snapshot("weekly-1"), self.newest_before)

    def test_torn_state_pointer_falls_back_to_history(self):
        line, _ = self.task("2026-12-06", faults={"backup-state.json": "truncate"})
        self.assertTrue(line.startswith("DYS backup OK:"), line)
        self.assertIn("backup-state.json: size on the computer", line)          # Keo is warned
        self.assertIn("the other state copy is intact", line)
        line, _ = self.task("2026-12-13")
        self.assertTrue(line.startswith("DYS backup OK:"), line)
        s = self.state()
        self.assertEqual((s["seq"], s["newest_slot"]), (2, "weekly-1"))      # it knew run 1 committed into weekly-2
        self.assertEqual(s["monthly"]["2026-12"]["files"], {"monthly\\saved-data-2026-12.zip": mock.ANY})

    def test_history_copy_missing_but_pointer_intact_still_counts(self):
        orig = Computer.commit

        def commit(pc, dest, src, fault=None):
            return orig(pc, dest, src, "missing" if dest.startswith(bp.HISTORY) else fault)
        with mock.patch.object(Computer, "commit", commit):
            line, _ = self.task("2026-12-06")
        self.assertTrue(line.startswith("DYS backup OK:") and "WARNINGS" in line, line)
        line, _ = self.task("2026-12-13")
        self.assertTrue(line.startswith("DYS backup OK:"), line)
        self.assertEqual((self.state()["seq"], self.state()["newest_slot"]), (2, "weekly-1"))

    def test_both_state_copies_failed_means_not_committed(self):
        orig = Computer.commit

        def commit(pc, dest, src, fault=None):
            bad = (dest.startswith(bp.HISTORY) and "000000" not in dest) or dest == "backup-state.json"
            return orig(pc, dest, src, "interrupt" if bad else fault)
        with mock.patch.object(Computer, "commit", commit):
            line, _ = self.task("2026-12-06")
        self.assertTrue(line.startswith("DYS backup FAILED:"), line)
        self.assertNotEqual(self.pc.get("backup-state.json"), self.state_before)    # half-written pointer...
        line, _ = self.task("2026-12-13")                                           # ...is recognised and skipped
        self.assertTrue(line.startswith("DYS backup OK:"), line)
        s = self.state()
        self.assertEqual((s["seq"], s["newest_slot"]), (1, "weekly-2"))
        rec = s["monthly"]["2026-12"]
        self.assertIn("monthly\\saved-data-2026-12-2.zip", rec["files"])  # the uncommitted copy was kept, not reused

    def test_broken_packed_file_is_not_retried_forever(self):
        real = bp.check_file

        def check(path, kind, expect):
            return "zip member x is damaged" if path.startswith(self.pc.stage_dir) and kind == "zip" else real(path, kind, expect)
        with mock.patch.object(bp, "check_file", check):
            line, _ = self.task("2026-12-06")
        self.assertTrue(line.startswith("FAILED:"), line)
        self.assert_nothing_recorded()


class SplitFiles(Base):
    def setUp(self):
        super().setUp()
        self.seed_legacy()
        self.small_parts = [mock.patch.object(bp, "MAX_FILE", 3000), mock.patch.object(bp, "PART", 2000),
                            mock.patch.object(bp, "STAGE_BATCH", 12000)]
        for p in self.small_parts:
            p.start()

    def tearDown(self):
        for p in self.small_parts:
            p.stop()
        super().tearDown()

    def test_split_files_are_joined_and_checked(self):
        line, out = self.task("2026-12-06")
        self.assertTrue(line.startswith("DYS backup OK:"), line)
        plan = jload(os.path.join(out, "plan.json"))
        parts = [t["dest"] for t in plan["transfer"] if ".part" in t["dest"]]
        self.assertTrue(parts)
        for b in plan["stage_batches"]:
            self.assertTrue(len(b) == 1 or sum(t["bytes"] for t in plan["transfer"] if t["dest"] in b) <= 12000, b)
        self.assertEqual(sorted(d for b in plan["stage_batches"] for d in b), sorted(t["dest"] for t in plan["transfer"]))
        self.assertTrue(any(p.startswith("monthly\\saved-data-2026-12.zip.part") for p in parts))
        rec = self.state()["monthly"]["2026-12"]["files"]["monthly\\saved-data-2026-12.zip"]
        joined = b"".join(self.pc.get(p) for p in rec["parts"])
        self.assertEqual(hashlib.sha256(joined).hexdigest(), rec["sha256"])

    def test_one_bad_part_fails_the_run(self):
        line, out = self.task("2026-12-06", faults={"weekly-2\\saved-data.zip.part02": "corrupt"},
                              always={"weekly-2\\saved-data.zip.part02"})
        self.assertTrue(line.startswith("FAILED:"), line)
        self.assertEqual(self.pc.snapshot(bp.HISTORY), {})


class Recovery(Base):
    def test_recover_november_with_ok(self):
        self.seed_legacy()
        self.task("2026-11-22")
        line, _ = self.task("2026-11-29", recover="2026-11")
        self.assertTrue(line.startswith("DYS backup OK:"), line)
        rec = self.state()["monthly"]["2026-11"]
        self.assertEqual((rec["status"], rec.get("recovered")), ("verified", True))
        self.assertEqual(list(rec["files"]), ["monthly\\saved-data-2026-11-recovered-2026-11-29.zip"])

    def test_recovery_after_the_month_is_blocked(self):
        self.seed_legacy()
        self.task("2026-11-22")
        line, _ = self.task("2026-12-06", recover="2026-11")
        self.assertTrue(line.startswith("BLOCKED:"), line)

    def test_recovery_of_a_good_month_is_blocked(self):
        self.seed_legacy()
        self.task("2026-12-06")
        line, _ = self.task("2026-12-13", recover="2026-12")
        self.assertTrue(line.startswith("BLOCKED:"), line)


class StateFile(Base):
    def test_unsupported_and_damaged_states_are_blocked(self):
        for content in (json.dumps({"version": 7}), "{not json", json.dumps({"version": 1, "months": "2026-11"}),
                        json.dumps(bp.seal({"version": 2, "seq": 1}))[:-5] + "0000}"):
            with self.subTest(content=content[:30]):
                self.setUp()
                self.seed_legacy()
                self.pc.put("backup-state.json", content.encode())
                before = self.pc.snapshot()
                line, _ = self.task("2026-12-06")
                self.assertTrue(line.startswith("BLOCKED:"), line)
                self.assertEqual(self.pc.snapshot(), before)

    def test_missing_state_is_never_made_up(self):
        line, _ = self.task("2026-12-06")
        self.assertTrue(line.startswith("FAILED:"), line)
        self.assertEqual(self.pc.snapshot(), {})

    def test_edited_state_fails_its_checksum(self):
        s = bp.seal({"version": 2, "seq": 3, "monthly": {}})
        self.assertTrue(bp.intact(s))
        s["monthly"]["2026-11"] = {"status": "verified"}
        self.assertFalse(bp.intact(s))

    def test_old_command_line_does_nothing(self):
        d = tempfile.mkdtemp(dir=self.tmp)
        code, text = call("--out", d, "--state", os.path.join(d, "x.json"))
        self.assertEqual(code, 2)
        self.assertIn("nothing was done", text)
        self.assertEqual(os.listdir(d), [])

    def test_local_disk_full_while_packing_leaves_no_plan(self):
        self.seed_legacy()
        d = tempfile.mkdtemp(dir=self.tmp)
        jdump(os.path.join(d, "before.json"), self.pc.listing())
        wtext(os.path.join(d, "state.json"), self.pc.get("backup-state.json"), "wb")
        out = os.path.join(d, "out")
        with mock.patch.object(bp.shutil, "copyfile", side_effect=OSError(errno.ENOSPC, "No space left on device")):
            code, text = call("pack", "--out", out, "--state", os.path.join(d, "state.json"), "--dest-listing",
                              os.path.join(d, "before.json"), "--mirror", self.mirror, "--today", "2026-12-06")
        self.assertEqual(code, 1)
        self.assertIn("FAILED", text)
        self.assertFalse(os.path.exists(os.path.join(out, "plan.json")))

    def test_atomic_write_keeps_the_old_file_when_interrupted(self):
        d = tempfile.mkdtemp(dir=self.tmp)
        p = os.path.join(d, "s.json")
        bp.atomic_write(p, b"old")
        with mock.patch.object(bp.os, "replace", side_effect=OSError(errno.EIO, "boom")):
            with self.assertRaises(OSError):
                bp.atomic_write(p, b"new")
        with open(p, "rb") as f:
            self.assertEqual(f.read(), b"old")
        self.assertEqual(os.listdir(d), ["s.json"])


class WindowsNames(Base):
    def test_existing_file_in_other_case_is_not_overwritten(self):
        self.seed_legacy()
        self.pc.put("Monthly\\SAVED-DATA-2026-12.ZIP", b"something else")
        line, _ = self.task("2026-12-06", sep="\\")
        self.assertTrue(line.startswith("DYS backup OK:"), line)
        self.assertEqual(self.pc.get("monthly\\saved-data-2026-12.zip"), b"something else")
        self.assertIn("monthly\\saved-data-2026-12-2.zip", self.state()["monthly"]["2026-12"]["files"])

    def test_name_rules(self):
        self.assertTrue(bp.win_name_ok("weekly-1\\saved-data.zip"))
        for bad in ("weekly-1\\CON.zip", "weekly-1\\a.", "weekly-1\\a ", "a:b", "x\\" + "y" * 240, "a\\\\b"):
            self.assertFalse(bp.win_name_ok(bad), bad)
        self.assertEqual(bp.key("Monthly/Saved-Data.ZIP"), bp.key("monthly\\saved-data.zip"))


if __name__ == "__main__":
    unittest.main()
