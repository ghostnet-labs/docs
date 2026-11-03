"""Tests for runner_cleanup.py. Run: python3 -m unittest discover -s tools/runner-status -p 'test_runner_cleanup.py'"""

import argparse
import io
import json
import os
import plistlib
import re
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
import runner_cleanup as rc  # noqa: E402

NOW = time.time()
DAY = 86400


def touch(path, days_old=0.0, data=b"x" * 100):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    age(path, days_old)


def age(path, days_old):
    t = NOW - days_old * DAY
    os.utime(path, (t, t), follow_symlinks=False)


def make_runner(base, name="actions-runner"):
    """A fake runner dir with protected files, old and fresh work."""
    r = os.path.join(base, name)
    for f in (".runner", ".credentials", ".credentials_rsaparams", ".env", ".path",
              "svc.sh", "config.sh", "run.sh", "bin/Runner.Listener", "externals/node20/bin/node"):
        touch(os.path.join(r, f), days_old=100)
    touch(os.path.join(r, "_work/_temp/tmp.sh"))  # _temp: any age
    touch(os.path.join(r, "_work/_tool/go/1.22/go"), days_old=100)
    touch(os.path.join(r, "_work/old-repo/old-repo/README"), days_old=10)
    age(os.path.join(r, "_work/old-repo/old-repo"), 10)
    age(os.path.join(r, "_work/old-repo"), 10)
    touch(os.path.join(r, "_work/fresh-repo/fresh-repo/README"), days_old=10)
    age(os.path.join(r, "_work/fresh-repo/fresh-repo"), 1)  # child touched yesterday
    age(os.path.join(r, "_work/fresh-repo"), 10)
    touch(os.path.join(r, "_work/_actions/actions/checkout/v4/action.yml"), days_old=30)
    age(os.path.join(r, "_work/_actions/actions/checkout/v4"), 30)
    age(os.path.join(r, "_work/_actions/actions/checkout"), 30)
    age(os.path.join(r, "_work/_actions/actions"), 30)
    touch(os.path.join(r, "_work/_actions/docker/login/v3/action.yml"), days_old=2)
    touch(os.path.join(r, "_diag/Runner_old.log"), days_old=10)
    touch(os.path.join(r, "_diag/Runner_new.log"), days_old=1)
    touch(os.path.join(r, "_diag/Worker_old.log"), days_old=9)
    touch(os.path.join(r, "_diag/keep.txt"), days_old=30)
    return r


def opts(root, apply=False, **kw):
    o = argparse.Namespace(apply=apply, dry_run=False, runner_root=[root], depth=4, work_days=3,
                           log_days=7, vms=False, caches=False, json=False,
                           logs_dir=os.path.join(root, "Logs"), lock_file=os.path.join(root, "lock"))
    for k, v in kw.items():
        setattr(o, k, v)
    return o


def no_commands(cmd, timeout=15, env=None):
    return None


def snapshot(root):
    out = set()
    for d, dirs, files in os.walk(root):
        for n in dirs + files:
            out.add(os.path.relpath(os.path.join(d, n), root))
    return out


class CleanupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.runner = make_runner(self.root)
        self.log = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_it(self, apply, procs=()):
        return rc.run_cleanup(opts(self.root, apply), list_procs=lambda: list(procs),
                              runner=no_commands, now=NOW, log=self.log.append, system="Linux")

    def test_discovers_runner_without_following_symlinks(self):
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        make_runner(other.name, "elsewhere")
        os.symlink(other.name, os.path.join(self.root, "link"))
        self.assertEqual(rc.discover_runners([self.root]), [self.runner])

    def test_dry_run_deletes_nothing(self):
        before = snapshot(self.root)
        res = self.run_it(apply=False)
        self.assertEqual(snapshot(self.root), before)
        paths = {os.path.relpath(i["path"], self.runner) for i in res["runners"][0]["items"]}
        self.assertEqual(paths, {"_work/_temp/tmp.sh", "_work/old-repo", "_work/_actions/actions",
                                 "_diag/Runner_old.log", "_diag/Worker_old.log"})
        self.assertGreater(res["total_bytes"], 0)
        self.assertTrue(rc.render_text(res).endswith("Would free " + rc.fmt_bytes(res["total_bytes"])))

    def test_apply_removes_only_old_items_and_keeps_protected(self):
        res = self.run_it(apply=True)
        r = self.runner
        gone = ["_work/_temp/tmp.sh", "_work/old-repo", "_work/_actions/actions",
                "_diag/Runner_old.log", "_diag/Worker_old.log"]
        kept = [".runner", ".credentials", ".credentials_rsaparams", ".env", ".path", "svc.sh",
                "config.sh", "run.sh", "bin/Runner.Listener", "externals/node20/bin/node",
                "_work/_temp", "_work/_tool/go/1.22/go", "_work/fresh-repo/fresh-repo/README",
                "_work/_actions/docker/login/v3/action.yml", "_diag/Runner_new.log", "_diag/keep.txt"]
        for p in gone:
            self.assertFalse(os.path.lexists(os.path.join(r, p)), p)
        for p in kept:
            self.assertTrue(os.path.exists(os.path.join(r, p)), p)
        self.assertTrue(rc.render_text(res).splitlines()[-1].startswith("Freed "))
        self.assertTrue(any(m.startswith("removed ") for m in self.log))

    def test_busy_runner_is_skipped(self):
        before = snapshot(self.root)
        procs = [{"pid": 42, "cmd": f"{self.runner}/bin/Runner.Worker spawnclient 1 2", "cwd": None}]
        res = self.run_it(apply=True, procs=procs)
        self.assertEqual(res["runners"][0]["status"], "busy")
        self.assertEqual(snapshot(self.root), before)
        self.assertIn("skipped, busy", rc.render_text(res))

    def test_busy_by_work_path_or_cwd(self):
        self.assertIsNotNone(rc.runner_busy(self.runner, [{"pid": 1, "cmd": f"make -C {self.runner}/_work/fw"}], NOW))
        self.assertIsNotNone(rc.runner_busy(self.runner, [{"pid": 1, "cmd": "make", "cwd": f"{self.runner}/_work/fw"}], NOW))
        self.assertIsNotNone(rc.runner_busy(self.runner, None, NOW))  # ps failed: hands off
        self.assertIsNone(rc.runner_busy(self.runner, [{"pid": 1, "cmd": f"{self.runner}/bin/Runner.Listener run"}], NOW))
        # a sibling runner with a shared prefix is not confused with this one
        self.assertIsNone(rc.runner_busy(self.runner, [{"pid": 1, "cmd": f"{self.runner}-2/bin/Runner.Worker"}], NOW))

    def test_recent_worker_log_counts_as_busy(self):
        touch(os.path.join(self.runner, "_diag/Worker_now.log"))
        self.assertIn("finished", rc.runner_busy(self.runner, [], NOW))

    def test_safe_delete_refuses_outside_and_protected(self):
        roots = rc.runner_roots(self.runner)
        outside = os.path.join(self.root, "outside.txt")
        touch(outside)
        for path in (outside, os.path.join(self.runner, ".runner"), os.path.join(self.runner, "bin"),
                     os.path.join(self.runner, "_work"), os.path.join(self.runner, "_work/_tool"),
                     os.path.join(self.runner, "_work/_tool/go"), os.path.join(self.runner, "_work/_temp"),
                     os.path.join(self.runner, "_work/../.credentials")):
            ok, what = rc.safe_delete(path, roots, apply=True, log=self.log.append)
            self.assertFalse(ok, path)
            self.assertTrue(what.startswith("refused"), what)
            self.assertTrue(os.path.exists(path), path)

    def test_safe_delete_symlink_pointing_outside_unlinks_link_only(self):
        victim = os.path.join(self.root, "victim")
        touch(os.path.join(victim, "precious"))
        link = os.path.join(self.runner, "_work/_temp/evil")
        os.symlink(victim, link)
        ok, what = rc.safe_delete(link, rc.runner_roots(self.runner), apply=True, log=self.log.append)
        self.assertTrue(ok)
        self.assertFalse(os.path.lexists(link))
        self.assertTrue(os.path.exists(os.path.join(victim, "precious")))

    def test_safe_delete_refuses_path_through_symlinked_dir(self):
        victim = os.path.join(self.root, "victim")
        touch(os.path.join(victim, "precious"))
        os.symlink(victim, os.path.join(self.runner, "_work/sneaky"))
        path = os.path.join(self.runner, "_work/sneaky/precious")
        ok, what = rc.safe_delete(path, rc.runner_roots(self.runner), apply=True, log=self.log.append)
        self.assertFalse(ok)
        self.assertTrue(os.path.exists(os.path.join(victim, "precious")))

    def test_symlinked_checkout_not_a_candidate_and_target_survives(self):
        victim = os.path.join(self.root, "victim")
        touch(os.path.join(victim, "precious"), days_old=30)
        os.symlink(victim, os.path.join(self.runner, "_work/linked"))
        self.run_it(apply=True)
        self.assertTrue(os.path.exists(os.path.join(victim, "precious")))

    def test_log_truncation_keeps_tail(self):
        logs = os.path.join(self.root, "Logs")
        big = os.path.join(logs, "runner-status-serve.log")
        os.makedirs(logs)
        with open(big, "wb") as fh:
            fh.write(b"old line\n" * 100 + b"newest line\n")
        item = rc.truncate_log(big, [big], apply=False, limit=500, keep=100, log=self.log.append)
        self.assertEqual(item["action"], "would truncate")
        self.assertEqual(os.path.getsize(big), 912)
        item = rc.truncate_log(big, [big], apply=True, limit=500, keep=100, log=self.log.append)
        self.assertEqual(item["action"], "truncated")
        with open(big, "rb") as fh:
            data = fh.read()
        self.assertLessEqual(len(data), 100)
        self.assertTrue(data.endswith(b"newest line\n"))
        self.assertTrue(data.startswith(b"old line\n") or data.startswith(b"newest"))
        other = os.path.join(logs, "other.log")
        touch(other, data=b"x" * 1000)
        self.assertTrue(rc.truncate_log(other, [big], apply=True, limit=500, keep=100,
                                        log=self.log.append)["action"].startswith("refused"))
        self.assertEqual(os.path.getsize(other), 1000)

    def test_json_main_and_lock(self):
        o = opts(self.root)
        lock = rc.acquire_lock(o.lock_file)
        self.assertIsNotNone(lock)
        self.assertIsNone(rc.acquire_lock(o.lock_file))  # second run is refused
        lock.close()
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = rc.main(["--json", "--no-vms", "--no-caches", "--runner-root", self.root,
                            "--lock-file", o.lock_file, "--logs-dir", o.logs_dir])
        self.assertEqual(code, 0)
        data = json.loads(out.getvalue())
        self.assertFalse(data["apply"])
        self.assertTrue(os.path.exists(os.path.join(self.runner, "_work/old-repo")))


class HelpersTest(unittest.TestCase):
    def test_parse_ac_sleep(self):
        text = ("Battery Power:\n sleep                1\n displaysleep         2\n"
                "AC Power:\n displaysleep         10\n disksleep            10\n sleep                0\n")
        self.assertEqual(rc.parse_ac_sleep(text), 0)
        self.assertEqual(rc.parse_ac_sleep("AC Power:\n sleep                5 (sleep prevented by x)\n"), 5)
        self.assertIsNone(rc.parse_ac_sleep(""))

    def test_parse_ps(self):
        text = "  PID  PPID     ELAPSED COMMAND\n  12     1    01:02:03 /a/bin/Runner.Worker spawnclient 1 2\n"
        self.assertEqual(rc.parse_ps(text), [{"pid": 12, "ppid": "1", "etime": "01:02:03",
                                              "cmd": "/a/bin/Runner.Worker spawnclient 1 2", "cwd": None}])

    def test_parse_vm_output(self):
        res = rc.parse_vm_output("RUNNER /home/r\nCAND 2048 temp /home/r/_work/_temp/x\n"
                                 "SKIP /home/s busy\nNOTE journal: ok\nDONE\n")
        self.assertEqual(res["items"], [{"bytes": 2 * 1024 * 1024, "kind": "temp", "path": "/home/r/_work/_temp/x"}])
        self.assertEqual(res["busy_runners"], ["/home/s"])
        self.assertTrue(res["done"])
        self.assertEqual(rc.parse_vm_output("SKIPVM Runner.Worker running\n")["skipped"], "Runner.Worker running")

    def test_lima_vms_runs_script_only_in_running_vms(self):
        calls = []

        def fake(cmd, timeout=15, env=None):
            calls.append(cmd)
            if cmd[:2] == ["limactl", "list"]:
                return ('{"name":"gh-build","status":"Running","disk":64424509440,"dir":"/nonexistent"}\n'
                        '{"name":"gh-old","status":"Stopped","disk":1}\n')
            if cmd[:2] == ["limactl", "shell"]:
                return "RUNNER /home/r\nCAND 10 temp /home/r/_work/_temp/a\nDONE\n"
            return None
        vms = rc.lima_vms(False, True, 3, 7, fake, lambda m: None)
        self.assertEqual([v["name"] for v in vms], ["gh-build", "gh-old"])
        shells = [c for c in calls if c[:2] == ["limactl", "shell"]]
        self.assertEqual(len(shells), 1)
        self.assertIn("gh-build", shells[0])
        self.assertEqual(vms[0]["reclaim"], 10 * 1024)


class VMScriptTest(unittest.TestCase):
    RM = re.compile(r"(^|[\s;|&{(])rm(\s|$)")

    def test_dry_run_has_no_rm_and_no_destructive_commands(self):
        s = rc.vm_script(False, 3, 7)
        self.assertIsNone(self.RM.search(s))
        for word in ("fstrim", "--vacuum", "prune"):
            self.assertNotIn(word, s)
        self.assertIn("du -sxk", s)

    def test_apply_has_rm_and_fstrim(self):
        s = rc.vm_script(True, 3, 7)
        self.assertIsNotNone(self.RM.search(s))
        self.assertIn("rm -rf --one-file-system --", s)
        self.assertIn("fstrim -av", s)
        self.assertIn("journalctl --vacuum-time=7d", s)
        self.assertIn("docker system prune -f --filter until=72h", s)
        self.assertNotIn("--volumes", s)
        self.assertNotIn("prune -a", s)
        self.assertNotIn("--all", s)

    def test_script_rules(self):
        s = rc.vm_script(True, 5, 9)
        self.assertIn("find / -xdev -maxdepth 4 -name .runner", s)
        self.assertIn("-mindepth 1 -maxdepth 1", s)
        self.assertIn("-mtime +5", s)
        self.assertIn("-mtime +9", s)
        self.assertIn("-mtime +14", s)
        for keep in ("! -name _tool", "! -name _actions", "! -name _temp", "! -name _PipelineMapping"):
            self.assertIn(keep, s)
        # the script must not match itself when it greps ps for the worker process
        self.assertNotIn("Runner.Worker", s)

    def test_script_is_valid_sh(self):
        import shutil
        import subprocess
        if not shutil.which("sh"):
            self.skipTest("no sh")
        for apply in (False, True):
            r = subprocess.run(["sh", "-n", "-c", rc.vm_script(apply, 3, 7)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)


class VMScriptRunTest(unittest.TestCase):
    """Run the generated script for real against a temp tree (find / is
    swapped for the temp dir), so the shell logic itself is exercised."""

    def run_script(self, root, apply):
        import platform
        import subprocess
        if platform.system() != "Linux":
            self.skipTest("needs GNU find/readlink/rm")
        script = rc.vm_script(apply, 3, 7).replace("find / -xdev", f"find '{root}' -xdev")
        out = subprocess.run(["sh", "-c", script], capture_output=True, text=True, timeout=60).stdout
        res = rc.parse_vm_output(out)
        if res["skipped"]:
            self.skipTest(f"test host looks busy: {res['skipped']}")
        self.assertTrue(res["done"], out)
        return res

    def test_dry_run_then_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.realpath(tmp)
            r = make_runner(root)
            victim = os.path.join(root, "victim")
            touch(os.path.join(victim, "precious"), days_old=30)
            os.symlink(victim, os.path.join(r, "_work/_temp/evil"))
            before = snapshot(root)
            res = self.run_script(root, apply=False)
            self.assertEqual(snapshot(root), before)
            got = {os.path.relpath(i["path"], r) for i in res["items"]}
            self.assertEqual(got, {"_work/_temp/tmp.sh", "_work/_temp/evil", "_work/old-repo",
                                   "_work/_actions/actions", "_diag/Runner_old.log", "_diag/Worker_old.log"})
            self.run_script(root, apply=True)
            for p in got:
                self.assertFalse(os.path.lexists(os.path.join(r, p)), p)
            for p in (".runner", ".credentials", "bin/Runner.Listener", "_work/_tool/go/1.22/go",
                      "_work/fresh-repo/fresh-repo/README", "_diag/Runner_new.log"):
                self.assertTrue(os.path.exists(os.path.join(r, p)), p)
            self.assertTrue(os.path.exists(os.path.join(victim, "precious")))

    def test_newline_and_escaping_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.realpath(tmp)
            r = make_runner(root)
            outside = os.path.join(root, "outside")
            touch(os.path.join(outside, "precious"), days_old=30)
            # in-root path that a newline-split fragment of the nasty name would hit
            keep = os.path.join(r, "_work/_temp/keep")
            touch(os.path.join(keep, "file"), days_old=0)
            nasty = os.path.join(r, "_work/_temp/x\n" + keep)
            touch(nasty, days_old=0)
            os.symlink(outside, os.path.join(r, "_work/_temp/link\nout"))
            os.symlink(outside, os.path.join(r, "_work/_temp/plain-link"))
            res = self.run_script(root, apply=True)
            self.assertTrue(os.path.exists(os.path.join(outside, "precious")))
            self.assertFalse(os.path.lexists(nasty))
            self.assertFalse(os.path.lexists(os.path.join(r, "_work/_temp/link\nout")))
            self.assertFalse(os.path.lexists(os.path.join(r, "_work/_temp/plain-link")))
            for i in res["items"]:
                self.assertNotIn("\n", i["path"])


class LaunchdTest(unittest.TestCase):
    def test_plist(self):
        text = rc.launchd_plist("/usr/bin/python3", "/opt/runner_cleanup.py", [], "/Users/me")
        p = plistlib.loads(text.encode())
        self.assertEqual(p["Label"], "com.ghostnet.runner-cleanup")
        self.assertEqual(p["StartCalendarInterval"], {"Hour": 4, "Minute": 30})
        self.assertEqual(p["ProgramArguments"], ["/usr/bin/python3", "/opt/runner_cleanup.py", "--apply"])
        self.assertTrue(p["LowPriorityIO"])
        self.assertEqual(p["Nice"], 10)
        self.assertEqual(p["StandardOutPath"], "/Users/me/Library/Logs/runner-cleanup.log")

    def test_plist_dry_run_and_cli(self):
        p = plistlib.loads(rc.launchd_plist("py", "s", ["--dry-run", "--no-vms"], "/h").encode())
        self.assertEqual(p["ProgramArguments"], ["py", "s", "--dry-run", "--no-vms"])
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            self.assertEqual(rc.main(["launchd"]), 0)
        self.assertIn("--apply", plistlib.loads(out.getvalue().encode())["ProgramArguments"])


if __name__ == "__main__":
    unittest.main()
