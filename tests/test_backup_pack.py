"""Tests for tools/backup_pack.py: the weekly backup records only what was verified on the computer.

Everything is synthetic: a small git repo built here, fake release files, and a fake "DYS Backup" folder that
behaves like the Windows one the task writes to (names ignore case, nothing can be deleted or renamed, writes can
fail half way). No network, no real data, no real backup folder.

    python -m unittest tests/test_backup_pack.py
"""
import contextlib, errno, gzip, hashlib, io, json, os, shutil, subprocess, sys, tempfile, unittest
import time
from datetime import timedelta
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
        self.clock = int(time.time() * 1000)     # milliseconds; each write moves it forward like a real clock

    def _touch(self, p):
        self.clock += 1000
        os.utime(p, ns=(self.clock * 1_000_000, self.clock * 1_000_000))

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
        self._touch(p)

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
                st = os.stat(os.path.join(r, f))
                out.append({"name": rel, "type": "file", "size": st.st_size, "mtimeMs": st.st_mtime_ns // 1_000_000})
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
            self._touch(p)
            if fault == "enospc":
                raise OSError(errno.ENOSPC, "There is not enough space on the disk")
            if fault == "interrupt":
                raise ConnectionError("bridge dropped")
            return
        with open(p, "wb") as f:
            f.write(data)
        self._touch(p)

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


class Run:
    """One run of the weekly task, step by step as tools/BACKUP-TASK.md says, so tests can interleave two runs.
    faults: {dest: kind} for the first write of that file; dests in `always` fail every time."""

    def __init__(self, pc, mirror, today, work, faults=None, recover="", always=(), sep="/", break_lock=""):
        self.pc, self.mirror, self.today, self.work = pc, mirror, today, work
        self.faults, self.always, self.recover, self.sep, self.break_lock = dict(faults or {}), set(always), recover, sep, break_lock
        self.out = os.path.join(work, "out")
        self.locked = False
        os.makedirs(work, exist_ok=True)

    def write(self, dest, local):
        f = "corrupt" if dest in self.always and self.faults.get(dest) == "corrupt" else self.faults.pop(dest, None)
        if dest in self.always:
            f = f or "missing"
        try:
            self.pc.commit(dest, local, f)
        except (OSError, ConnectionError):
            pass                                  # the tool call failed; verification decides

    def listing(self, name):
        path = os.path.join(self.work, name)
        jdump(path, self.pc.listing(self.sep))
        return path

    def stage_to(self, name, dests):
        path = os.path.join(self.work, name)
        jdump(path, self.pc.stage([rel(d) for d in dests]))
        return path

    def fail(self, line):
        if self.locked:                           # step 9: release the lock only if it is still ours
            g = self.listing("guard.json")
            st = self.stage_to("staged-guard.json", self.plan["guard_paths"])
            code, _ = call("guard", "--out", self.out, "--dest-listing", g, "--staged", st, "--phase", "release")
            if code == 0:
                self.write(bp.LOCK, self.plan["lock"]["release"])
        return line

    def pack(self, cmd="pack", extra=()):
        before = self.listing("before.json")
        if not self.pc.exists("backup-state.json"):
            return "FAILED: backup folder or backup-state.json missing"
        names = [e["name"] for e in self.pc.listing("\\")["entries"]]
        hist = sorted(n for n in names if n.lower().startswith("state-history\\"))[-3:]
        want = ["backup-state.json"] + (["backup.lock"] if "backup.lock" in names else []) + hist
        staged = {s["devicePath"].split(ROOT + "\\")[-1]: s["stagedPath"] for s in self.pc.stage(want)}
        hdir = os.path.join(self.work, "hist")
        shutil.rmtree(hdir, ignore_errors=True)
        os.makedirs(hdir)
        for h in hist:
            shutil.copyfile(staged[h], os.path.join(hdir, os.path.basename(staged[h])))
        state = os.path.join(self.work, "backup-state.json")
        shutil.copyfile(staged["backup-state.json"], state)
        lock = os.path.join(self.work, "backup.lock")
        if "backup.lock" in staged:
            shutil.copyfile(staged["backup.lock"], lock)
        args = [cmd, "--out", self.out, "--state", state, "--state-history", hdir, "--dest-listing", before,
                "--lock", lock, "--today", self.today] + list(extra)
        if cmd == "pack":
            args += ["--mirror", self.mirror]
            if self.recover:
                args += ["--recover-month", self.recover]
        if self.break_lock:
            args += ["--break-lock", self.break_lock]
        code, text = call(*args)
        if code != 0:
            return "FAILED: " + text.strip().splitlines()[-1]
        self.plan = jload(os.path.join(self.out, "plan.json"))
        return None

    def take_lock(self):
        self.write(self.plan["lock"]["dest"], self.plan["lock"]["acquire"])
        return None

    def guard(self, phase):
        g = self.listing("guard.json")
        st = self.stage_to("staged-guard.json", self.plan["guard_paths"])
        code, text = call("guard", "--out", self.out, "--dest-listing", g, "--staged", st, "--phase", phase)
        if code != 0:
            return "FAILED: " + text.strip().splitlines()[-1]
        if phase == "start":
            self.locked = True
        return None

    def transfer(self):
        for t in self.plan["transfer"]:
            self.write(t["dest"], t["local"])

    def verify(self):
        after = self.listing("after.json")
        staged = [{"staged": self.pc.stage([rel(d) for d in b])} for b in self.plan["stage_paths"]]
        jdump(os.path.join(self.work, "staged.json"), staged)
        code, text = call("verify", "--out", self.out, "--dest-listing", after, "--staged", os.path.join(self.work, "staged.json"))
        if code != 0:
            v = jload(os.path.join(self.out, "verify.json"))
            if v["verdict"] != "retry":
                return self.fail("FAILED: " + text.strip().splitlines()[0].split(": ", 1)[-1])
            local = {t["dest"]: t["local"] for t in self.plan["transfer"]}
            for d in v["resend"]:
                self.write(d, local[d])
            after = self.listing("after.json")
            staged.append({"staged": self.pc.stage(v["resend"])})
            jdump(os.path.join(self.work, "staged.json"), staged)
            code, text = call("verify", "--out", self.out, "--dest-listing", after,
                              "--staged", os.path.join(self.work, "staged.json"), "--attempt", "2")
            if code != 0:
                return self.fail("FAILED: " + text.strip().splitlines()[0].split(": ", 1)[-1])
        return None

    def record(self):
        bad = self.guard("commit")
        if bad:
            return self.fail(bad)
        commit = jload(os.path.join(self.out, "commit.json"))
        for c in commit["files"]:
            self.write(c["dest"], c["local"])
        final = self.listing("final.json")
        sc = self.stage_to("staged-commit.json", [ROOT + "\\" + c["dest"] for c in commit["files"]])
        code, text = call("confirm", "--out", self.out, "--dest-listing", final, "--staged", sc)
        return text.strip().splitlines()[-1]

    def all(self, cmd="pack", extra=()):
        for step in (lambda: self.pack(cmd, extra), self.take_lock, lambda: self.guard("start")):
            r = step()
            if r:
                return (self.fail(r) if self.locked else r), self.out
        self.transfer()
        r = self.verify()
        if r:
            return r, self.out
        return self.record(), self.out


def rel(device_path):
    return device_path.split(ROOT + "\\")[-1] if device_path.startswith(ROOT + "\\") else device_path


def run_task(pc, mirror, today, work, **kw):
    return Run(pc, mirror, today, work, **kw).all()


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
        self.assertIn("BLOCKED:", line)

    def test_recovery_of_a_good_month_is_blocked(self):
        self.seed_legacy()
        self.task("2026-12-06")
        line, _ = self.task("2026-12-13", recover="2026-12")
        self.assertIn("BLOCKED:", line)


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
                self.assertIn("BLOCKED:", line)
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

    def test_half_a_bundle_is_caught(self):
        d = tempfile.mkdtemp(dir=self.tmp)
        full = os.path.join(d, "full.bundle")
        data = other_bundle(self.mirror, full)
        self.assertIsNone(bp.check_file(full, "bundle", None))
        half = os.path.join(d, "half.bundle")
        wtext(half, data[: len(data) // 2], "wb")
        self.assertIsNotNone(bp.check_file(half, "bundle", None))      # "git bundle verify" alone says okay
        hdr = os.path.join(d, "hdr.bundle")
        wtext(hdr, b"# v2 git bundle\n", "wb")
        self.assertIsNotNone(bp.check_file(hdr, "bundle", None))

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


def other_bundle(mirror, path):
    """A valid git bundle with different bytes (only main): stands in for a copy another run wrote."""
    subprocess.run(["git", "-C", mirror, "bundle", "create", "-q", path, "refs/heads/main", "refs/heads/gh-pages"],
                   check=True, capture_output=True)
    with open(path, "rb") as f:
        return f.read()


class OneRunAtATime(Base):
    def setUp(self):
        super().setUp()
        self.seed_legacy()

    def lock(self):
        return json.loads(self.pc.get("backup.lock"))

    def test_second_run_is_blocked_while_the_first_holds_the_lock(self):
        a = Run(self.pc, self.mirror, "2026-12-06", os.path.join(self.base, "a"))
        self.assertIsNone(a.pack()); a.take_lock(); self.assertIsNone(a.guard("start"))
        before = self.pc.snapshot()
        line, _ = self.task("2026-12-06")                               # b starts while a is working
        self.assertIn("BLOCKED: another backup run may be writing", line)
        self.assertEqual(self.pc.snapshot(), before)                    # b changed nothing, lock untouched
        a.transfer(); self.assertIsNone(a.verify())
        self.assertTrue(a.record().startswith("DYS backup OK:"))
        self.assertEqual(self.lock()["state"], "released")
        line, _ = self.task("2026-12-13")                               # free again
        self.assertTrue(line.startswith("DYS backup OK:"), line)

    def test_both_take_the_lock_at_once_only_one_goes_on(self):
        a = Run(self.pc, self.mirror, "2026-12-06", os.path.join(self.base, "a"))
        b = Run(self.pc, self.mirror, "2026-12-06", os.path.join(self.base, "b"))
        self.assertIsNone(a.pack()); self.assertIsNone(b.pack())        # both saw no lock
        a.take_lock(); b.take_lock()                                    # b's write lands last
        self.assertIn("belongs to another run", a.guard("start"))
        self.assertFalse(a.locked)
        self.assertIsNone(b.guard("start"))
        b.transfer(); self.assertIsNone(b.verify())
        self.assertTrue(b.record().startswith("DYS backup OK:"))
        s = self.state()
        self.assertEqual((s["seq"], s["txn"]), (1, b.plan["txn"]))
        self.assertEqual(len(self.pc.snapshot(bp.HISTORY)), 2)          # legacy copy + b, nothing from a

    def test_race_lost_after_start_is_caught_before_recording(self):
        a = Run(self.pc, self.mirror, "2026-12-06", os.path.join(self.base, "a"))
        b = Run(self.pc, self.mirror, "2026-12-06", os.path.join(self.base, "b"))
        self.assertIsNone(a.pack()); self.assertIsNone(b.pack())
        a.take_lock(); self.assertIsNone(a.guard("start"))               # a read back its own lock...
        b.take_lock(); self.assertIsNone(b.guard("start"))               # ...then b overwrote it
        a.transfer(); b.transfer()
        line = a.verify()
        self.assertIn("conflict", line)                                 # a never records
        self.assertEqual(self.lock()["txn"], b.plan["txn"])             # and doesn't release b's lock
        self.assertIsNone(b.verify())
        self.assertTrue(b.record().startswith("DYS backup OK:"))
        self.assertEqual(self.state()["txn"], b.plan["txn"])
        self.check_slot_matches_record()

    def test_tonights_overlap_a_late_writer_after_verify(self):
        """Nov 15: run A verified and recorded, run B then rewrote a weekly file. Now A refuses to record."""
        a = Run(self.pc, self.mirror, "2026-12-06", os.path.join(self.base, "a"))
        self.assertIsNone(a.pack()); a.take_lock(); self.assertIsNone(a.guard("start"))
        a.transfer(); self.assertIsNone(a.verify())
        self.pc.put("weekly-2\\repo-code.bundle", other_bundle(self.mirror, os.path.join(self.base, "x.bundle")))
        line = a.record()
        self.assertIn("changed on the computer after it was checked", line)
        self.assertEqual(self.state()["version"], 1)                    # nothing recorded
        self.assertEqual(self.lock()["state"], "released")              # a released its own lock

    def test_writer_after_the_record_is_reported_and_blocks_the_next_run(self):
        a = Run(self.pc, self.mirror, "2026-12-06", os.path.join(self.base, "a"))
        self.assertIsNone(a.pack()); a.take_lock(); self.assertIsNone(a.guard("start"))
        a.transfer(); self.assertIsNone(a.verify())
        self.assertIsNone(a.guard("commit"))
        commit = jload(os.path.join(a.out, "commit.json"))
        for c in commit["files"]:
            a.write(c["dest"], c["local"])
        self.pc.put("weekly-2\\repo-code.bundle", other_bundle(self.mirror, os.path.join(self.base, "x.bundle")))
        final = a.listing("final.json")
        sc = a.stage_to("staged-commit.json", [ROOT + "\\" + c["dest"] for c in commit["files"]])
        code, text = call("confirm", "--out", a.out, "--dest-listing", final, "--staged", sc)
        self.assertEqual(code, 5)
        self.assertIn("changed on the computer after they were checked", text)
        line, _ = self.task("2026-12-13")
        self.assertIn("no longer matches its record", line)

    def test_record_written_by_another_run_stops_this_one(self):
        a = Run(self.pc, self.mirror, "2026-12-06", os.path.join(self.base, "a"))
        self.assertIsNone(a.pack()); a.take_lock(); self.assertIsNone(a.guard("start"))
        a.transfer(); self.assertIsNone(a.verify())
        self.pc.put("state-history\\backup-state-000001-20261206-zzzzzz.json", b"{}")
        self.assertIn("state-history changed", a.record())

    def test_abandoned_lock_lapses_after_two_hours(self):
        a = Run(self.pc, self.mirror, "2026-12-06", os.path.join(self.base, "a"))
        self.assertIsNone(a.pack()); a.take_lock(); self.assertIsNone(a.guard("start"))   # then a crashes
        line, _ = self.task("2026-12-06")
        self.assertIn("holds backup.lock until", line)
        lock = self.lock()
        lock["expires"] = bp.iso(bp.now_utc() - timedelta(minutes=1))
        self.pc.put("backup.lock", json.dumps(lock).encode())
        line, _ = self.task("2026-12-06")
        self.assertTrue(line.startswith("DYS backup OK:"), line)
        self.assertEqual(self.lock()["state"], "released")

    def test_resumed_run_older_than_two_hours_must_start_over(self):
        a = Run(self.pc, self.mirror, "2026-12-06", os.path.join(self.base, "a"))
        self.assertIsNone(a.pack()); a.take_lock(); self.assertIsNone(a.guard("start"))
        a.transfer()
        plan = jload(os.path.join(a.out, "plan.json"))
        plan["created_at"] = bp.iso(bp.now_utc() - timedelta(hours=3))
        jdump(os.path.join(a.out, "plan.json"), plan)
        self.assertIn("more than 2 hours ago", a.verify())
        self.assertEqual(self.state()["version"], 1)

    def test_unreadable_lock_is_held_until_it_is_old(self):
        self.pc.put("backup.lock", b'{"state": "act')                   # a half-written lock, just now
        line, _ = self.task("2026-12-06")
        self.assertIn("unreadable backup.lock", line)
        p = self.pc._real("backup.lock")
        old = (bp.now_utc() - timedelta(hours=3)).timestamp()
        os.utime(p, (old, old))
        line, _ = self.task("2026-12-06")
        self.assertTrue(line.startswith("DYS backup OK:"), line)

    def test_break_lock_takes_over_only_the_named_run(self):
        a = Run(self.pc, self.mirror, "2026-12-06", os.path.join(self.base, "a"))
        self.assertIsNone(a.pack()); a.take_lock()
        self.n += 1
        line, _ = Run(self.pc, self.mirror, "2026-12-06", os.path.join(self.base, "w"), break_lock="20261206-nope").all()
        self.assertIn("holds backup.lock", line)
        line, _ = Run(self.pc, self.mirror, "2026-12-06", os.path.join(self.base, "b"), break_lock=a.plan["txn"]).all()
        self.assertTrue(line.startswith("DYS backup OK:"), line)

    def test_failed_run_releases_its_lock(self):
        line, _ = self.task("2026-12-06", always={"weekly-2\\saved-data.zip"})
        self.assertTrue(line.startswith("FAILED:"), line)
        self.assertEqual(self.lock()["state"], "released")
        line, _ = self.task("2026-12-06")
        self.assertTrue(line.startswith("DYS backup OK:"), line)

    def check_slot_matches_record(self):
        s = self.state()
        for whole, f in s["slots"][s["newest_slot"]]["files"].items():
            data = b"".join(self.pc.get(p) for p in f["parts"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), f["sha256"], whole)


class Reconcile(Base):
    """The Nov 15 state: record says one checksum, the computer holds another complete copy."""

    def setUp(self):
        super().setUp()
        self.seed_legacy()
        line, _ = self.task("2026-11-22")                               # weekly-2 recorded, weekly-1 = legacy copy
        self.assertTrue(line.startswith("DYS backup OK:"), line)
        self.weekly1 = self.pc.snapshot("weekly-1")
        self.pc.put("weekly-2\\repo-code.bundle", other_bundle(self.mirror, os.path.join(self.base, "x.bundle")))

    def reconcile(self, **kw):
        self.n += 1
        return Run(self.pc, self.mirror, "2026-11-22", os.path.join(self.base, f"rec{self.n}"), **kw).all(
            cmd="reconcile", extra=["--slot", "weekly-2"])

    def test_mismatch_blocks_normal_runs(self):
        before = self.pc.snapshot()
        line, _ = self.task("2026-11-29")
        self.assertIn("no longer matches its record", line)
        self.assertEqual(self.pc.snapshot(), before)                    # weekly-1 not overwritten to "fix" it

    def test_reconcile_corrects_the_record_and_keeps_weekly_1(self):
        line, _ = self.reconcile()
        self.assertTrue(line.startswith("DYS backup OK:"), line)
        s = self.state()
        self.assertEqual((s["seq"], s["newest_slot"], s["runs"][-1]["verdict"]), (2, "weekly-2", "reconciled"))
        f = s["slots"]["weekly-2"]["files"]["weekly-2\\repo-code.bundle"]
        self.assertEqual(hashlib.sha256(self.pc.get("weekly-2\\repo-code.bundle")).hexdigest(), f["sha256"])
        self.assertIn("was_sha256", f["reconciled"])
        self.assertEqual(self.pc.snapshot("weekly-1"), self.weekly1)    # untouched
        self.assertIn(b"RECORD CORRECTED", self.pc.get("weekly-2\\FILE-LIST.txt"))
        line, _ = self.task("2026-11-29")                               # rotation goes on as normal
        self.assertTrue(line.startswith("DYS backup OK:"), line)
        self.assertEqual(self.state()["newest_slot"], "weekly-1")

    def test_reconcile_refuses_a_damaged_file(self):
        self.pc.put("weekly-2\\repo-code.bundle", b"# v2 git bundle\nnot really")
        state_before = self.pc.get("backup-state.json")
        line, _ = self.reconcile()
        self.assertTrue(line.startswith("FAILED:"), line)
        self.assertIn("repo-code.bundle: bundle holds no branches", line)
        self.assertEqual(self.pc.get("backup-state.json"), state_before)
        self.assertEqual(json.loads(self.pc.get("backup.lock"))["state"], "released")
        self.assertEqual(self.pc.snapshot("weekly-1"), self.weekly1)


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
