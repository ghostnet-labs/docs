"""Tests for runner_watchdog.py. Run: python3 -m unittest discover -s tools/runner-status"""

import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import runner_status as rs  # noqa: E402
import runner_watchdog as wd  # noqa: E402

GIB = 1024 ** 3


class FakeHost(wd.Host):
    """Scripted machine: VMs, launchd services, VM units and journals."""

    def __init__(self, offline, vms=None, launchd="", units="", journal="", vm_net=True,
                 net=True, free=500 * GIB, page_error=None):
        self.offline, self.vms_, self.launchd, self.units = offline, vms or {}, launchd, units
        self.journal, self.vm_net, self.net, self.free = journal, vm_net, net, free
        self.page_error = page_error
        self.ran = []

    def page_state(self, page):
        if self.page_error:
            raise OSError(self.page_error)
        return {"machines": [{"name": "Mac Studio", "runners": [
            {"name": n, "status": "offline"} for n in self.offline] + [
            {"name": "studio-mac-9", "status": "idle"}]}]}

    def run(self, cmd, timeout=30):
        if cmd[:2] == ["limactl", "list"]:
            return 0, "\n".join(json.dumps({"name": k, "status": v})
                                for k, v in self.vms_.items())
        if cmd[:2] == ["launchctl", "list"]:
            return 0, self.launchd
        self.ran.append(cmd)
        return 0, ""

    def vm(self, vm, script, timeout=30):
        if script.startswith("systemctl list-units"):
            return 0, self.units
        if script.startswith("journalctl"):
            return 0, self.journal + "\n/dev/vda1 61255492 20000000 41255492 33% /\n"
        if script.startswith("curl"):
            return (0 if self.vm_net else 7), ""
        return 0, ""

    def free_bytes(self, path="/"):
        return self.free

    def reachable(self, url="https://github.com"):
        return self.net

    def uid(self):
        return 501


class WatchdogTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        for name in ("ATTEMPTS_FILE", "MAINTENANCE_FILE", "REPORT_FILE", "DRIFT_FILE"):
            p = mock.patch.object(wd, name, os.path.join(self.dir.name, name.lower()))
            p.start()
            self.addCleanup(p.stop)
        self.cfg = json.loads(json.dumps(rs.DEFAULT_CONFIG))
        self.cfg["machines"][0]["jit_slots"] = []  # tests opt in
        self.cfg["machines"][0]["vm_roles"] = {}

    def run_dog(self, host, dry_run=False, jit=None):
        return wd.Watchdog(self.cfg, "Mac Studio", host, dry_run=dry_run,
                           jit_command=jit).run_once()

    def test_stopped_vm_is_started_once_for_all_its_runners(self):
        host = FakeHost(["gh-ubuntu-1", "gh-ubuntu-2"], vms={"gh-ubuntu": "Stopped"})
        rep = self.run_dog(host)
        self.assertEqual(rep["runners"]["gh-ubuntu-1"]["cause"], "vm-stopped")
        self.assertEqual(host.ran, [["limactl", "start", "gh-ubuntu"]])
        self.assertEqual(rep["runners"]["gh-ubuntu-1"]["result"], "ok")
        self.assertIn("(starting)", rep["runners"]["gh-ubuntu-2"]["detail"])

    def test_dead_unit_in_vm_is_restarted(self):
        host = FakeHost(["studio-build-1"], vms={"gh-build": "Running"},
                        units="actions.runner.ghostnet-labs.studio-build-1.service loaded failed "
                              "failed GitHub Actions Runner\n")
        rep = self.run_dog(host)
        e = rep["runners"]["studio-build-1"]
        self.assertEqual(e["cause"], "service-dead")
        self.assertEqual(host.ran, [["limactl", "shell", "gh-build", "--", "sudo", "systemctl",
                                     "restart",
                                     "actions.runner.ghostnet-labs.studio-build-1.service"]])

    def test_removed_registration_is_reported_not_restarted(self):
        host = FakeHost(["studio-build-1"], vms={"gh-build": "Running"},
                        units="actions.runner.o.studio-build-1.service loaded failed failed x\n",
                        journal="Runner registration has been deleted from the server")
        e = self.run_dog(host)["runners"]["studio-build-1"]
        self.assertEqual(e["cause"], "registration")
        self.assertIsNone(e["action"])
        self.assertEqual(host.ran, [])

    def test_maintenance_entry_means_draining(self):
        with open(wd.MAINTENANCE_FILE, "w") as fh:
            json.dump({"entries": [{"runner": "^gh-ubuntu", "reason": "JIT conversion",
                                    "until": "2099-01-01T00:00:00Z"},
                                   {"runner": "studio-mac", "reason": "old",
                                    "until": "2000-01-01T00:00:00Z"}]}, fh)
        host = FakeHost(["gh-ubuntu-3"], vms={"gh-ubuntu": "Stopped"})
        e = self.run_dog(host)["runners"]["gh-ubuntu-3"]
        self.assertEqual((e["cause"], e["detail"]), ("maintenance", "draining: JIT conversion"))
        self.assertEqual(host.ran, [])
        self.assertIsNone(wd.maintenance_reason("studio-mac-1", [{"runner": "studio-mac",
                          "until": "2000-01-01T00:00:00Z"}], time.time()))

    def test_launchd_runner_kickstarted_and_backoff_caps_tries(self):
        launchd = "PID\tStatus\tLabel\n-\t1\tactions.runner.ghostnet-labs.studio-mac-1\n"
        host = FakeHost(["studio-mac-1"], launchd=launchd)
        e = self.run_dog(host)["runners"]["studio-mac-1"]
        self.assertEqual(e["cause"], "service-dead")
        self.assertEqual(host.ran[0], ["launchctl", "kickstart", "-k",
                                       "gui/501/actions.runner.ghostnet-labs.studio-mac-1"])
        e = self.run_dog(host)["runners"]["studio-mac-1"]  # right away: backoff
        self.assertTrue(e["result"].startswith("retrying: waiting"))
        self.assertFalse(e["gave_up"])
        self.assertEqual(len(host.ran), 1)
        now = time.time()
        self.assertEqual(wd.may_act([now - 1000, now - 600, now - 300], now)[0], False)
        with open(wd.ATTEMPTS_FILE, "w") as fh:
            json.dump({"studio-mac-1":
                       [now - 1000, now - 600, now - 300]}, fh)
        e = self.run_dog(host)["runners"]["studio-mac-1"]
        self.assertTrue(e["gave_up"])
        self.assertTrue(e["result"].startswith("gave up"))
        self.assertEqual(e["tries"], 3)
        self.assertTrue(wd.may_act([now - 4000], now)[0])

    def test_network_disk_and_no_service(self):
        host = FakeHost(["studio-mac-1"], net=False)
        self.assertEqual(self.run_dog(host)["runners"]["studio-mac-1"]["cause"], "network")
        host = FakeHost(["studio-mac-1"], free=GIB)
        self.assertEqual(self.run_dog(host)["runners"]["studio-mac-1"]["cause"], "disk-full")
        host = FakeHost(["studio-mac-1"])
        e = self.run_dog(host)["runners"]["studio-mac-1"]
        self.assertEqual((e["cause"], e["action"]), ("no-service", None))
        host = FakeHost(["studio-mac-1"])
        e = self.run_dog(host, jit=["/Users/x/jit-runners.sh", "refill"])["runners"]["studio-mac-1"]
        self.assertEqual(host.ran, [["/Users/x/jit-runners.sh", "refill", "studio-mac-1"]])

    def test_vm_without_network_is_restarted(self):
        host = FakeHost(["gh-ubuntu-1"], vms={"gh-ubuntu": "Running"}, vm_net=False,
                        units="actions.runner.o.gh-ubuntu-1.service loaded active running x\n")
        e = self.run_dog(host)["runners"]["gh-ubuntu-1"]
        self.assertEqual(e["cause"], "network")
        self.assertEqual(host.ran, [["limactl", "restart", "gh-ubuntu"]])

    def test_dry_run_changes_nothing(self):
        host = FakeHost(["gh-ubuntu-1"], vms={"gh-ubuntu": "Stopped"})
        e = self.run_dog(host, dry_run=True)["runners"]["gh-ubuntu-1"]
        self.assertEqual(e["result"], "dry run: not run")
        self.assertEqual(host.ran, [])
        self.assertFalse(os.path.exists(wd.ATTEMPTS_FILE))

    def test_page_down_still_starts_stopped_vm(self):
        host = FakeHost([], vms={"gh-build": "Stopped", "unrelated": "Stopped"},
                        page_error="refused")
        rep = self.run_dog(host)
        self.assertIn("status page unreachable", rep["error"])
        self.assertEqual(host.ran, [["limactl", "start", "gh-build"]])

    def test_report_reaches_page_and_explains_offline_runner(self):
        host = FakeHost(["gh-ubuntu-1"], vms={"gh-ubuntu": "Stopped"})
        rep = self.run_dog(host)
        wd.write_json(wd.REPORT_FILE, rep)
        st = {"watchdog": rs.read_watchdog(wd.REPORT_FILE)}
        st = rs.sanitize_stats(st)
        raw = {"runners": [{"id": 1, "name": "gh-ubuntu-1", "status": "offline",
                            "labels": []}], "machine_stats": {"Mac Studio": st}}
        state = rs.build_state(raw, self.cfg, rs.utcnow())
        r = state["machines"][0]["runners"][0]
        self.assertEqual(r["why"]["cause"], "vm-stopped")
        text = state["alerts"][0]["text"]
        self.assertIn("VM gh-ubuntu is Stopped", text)
        self.assertIn("auto-recovery: limactl start gh-ubuntu -> ok", text)

    def test_page_explains_draining_and_silent_host(self):
        st = {"watchdog": {"runners": {"gh-ubuntu-1": {"cause": "maintenance",
                                                       "detail": "draining: JIT"}}}}
        raw = {"runners": [{"id": 1, "name": "gh-ubuntu-1", "status": "offline", "labels": []},
                           {"id": 2, "name": "macbook-pro-build-1", "status": "offline",
                            "labels": []}],
               "machine_stats": {"Mac Studio": st,
                                 "MacBook Pro": {"error": "no stats pushed for 400s"}}}
        alerts = {a["text"]: a["level"] for a in rs.build_state(raw, self.cfg,
                                                                 rs.utcnow())["alerts"]}
        self.assertEqual(alerts["Draining for maintenance: gh-ubuntu-1 (draining: JIT)"], "info")
        self.assertTrue(any("asleep, off, or off the network" in t for t in alerts))

    def test_jit_slots_kickstarted_vm_started_never_registered(self):
        launchd = ("PID\tStatus\tLabel\n501\t0\tcom.ghostnet.jit.studio-ubuntu-1\n"
                   "-\t1\tcom.ghostnet.jit.studio-ubuntu-2\n")
        host = FakeHost([], vms={"gh-ubuntu": "Running", "gh-build": "Stopped"}, launchd=launchd)
        self.cfg["machines"][0]["jit_slots"] = ["studio-ubuntu-1", "studio-ubuntu-2",
                                                "studio-ubuntu-3", "studio-build-1"]
        rep = self.run_dog(host)["runners"]
        self.assertNotIn("studio-ubuntu-1", rep)  # running: nothing to say
        self.assertEqual(rep["studio-ubuntu-2"]["cause"], "service-dead")
        self.assertEqual(rep["studio-ubuntu-3"]["cause"], "no-service")
        self.assertIsNone(rep["studio-ubuntu-3"]["action"])
        self.assertEqual(rep["studio-build-1"]["cause"], "vm-stopped")
        self.assertEqual(host.ran, [
            ["launchctl", "kickstart", "-k", "gui/501/com.ghostnet.jit.studio-ubuntu-2"],
            ["limactl", "start", "gh-build"]])

    def test_jit_slot_in_maintenance_is_draining(self):
        with open(wd.MAINTENANCE_FILE, "w") as fh:
            json.dump({"entries": [{"runner": "^studio-(ubuntu|build)-", "reason": "JIT conversion"}]},
                      fh)
        host = FakeHost([], vms={"gh-ubuntu": "Stopped"})
        self.cfg["machines"][0]["jit_slots"] = ["studio-ubuntu-1"]
        rep = self.run_dog(host)["runners"]
        self.assertEqual(rep["studio-ubuntu-1"]["cause"], "maintenance")
        self.assertEqual(host.ran, [])

    def test_hourly_drift_check_reaches_the_page(self):
        calls = []

        class Host2(FakeHost):
            def vm_stdin(self, vm, role, script):
                calls.append((vm, role, "verify-vm" in script or "usage" in script))
                return 0, ("FAIL: /usr/local/bin/runc exists (breaks the OpenWrt build)\n"
                           if vm == "gh-build" else "")

        self.cfg["machines"][0]["vm_roles"] = {"gh-ubuntu": "ubuntu", "gh-build": "build",
                                               "gh-build-2": "build"}
        host = Host2([], vms={"gh-ubuntu": "Running", "gh-build": "Running",
                              "gh-build-2": "Stopped"})
        rep = self.run_dog(host)
        self.assertEqual(sorted(c[:2] for c in calls),
                         [("gh-build", "build"), ("gh-ubuntu", "ubuntu")])  # stopped VM skipped
        self.assertTrue(all(c[2] for c in calls))  # the real script was sent
        self.assertEqual(rep["drift"]["gh-ubuntu"], [])
        calls.clear()
        self.assertEqual(self.run_dog(host)["drift"]["gh-build"][0][:5], "FAIL:")
        self.assertEqual(calls, [])  # not due again within the hour
        st = rs.sanitize_stats({"watchdog": rep})
        alerts = rs.machine_alerts("Mac Studio", st, rs.DEFAULT_CONFIG, None)
        self.assertEqual(len(alerts), 1)
        self.assertIn("VM gh-build drifted from the committed setup", alerts[0]["text"])
        self.assertIn("/usr/local/bin/runc exists", alerts[0]["text"])

    def test_plist(self):
        import contextlib
        import io
        import plistlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            wd.main(["launchd", "--machine", "MacBook Pro", "--page", "http://s.local:8090"])
        plist = plistlib.loads(buf.getvalue().encode())
        self.assertEqual(plist["StartInterval"], 120)
        self.assertEqual(plist["ProgramArguments"][-4:],
                         ["--machine", "MacBook Pro", "--page", "http://s.local:8090"])


if __name__ == "__main__":
    unittest.main()
