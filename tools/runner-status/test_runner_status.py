"""Tests for runner_status.py. Run: python3 -m unittest discover -s tools/runner-status"""

import json
import os
import sys
import threading
import unittest
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
import runner_status as rs  # noqa: E402

NOW = datetime(2026, 10, 13, 5, 0, tzinfo=timezone.utc)


def runner(i, name, status="online", busy=False, labels=("self-hosted",)):
    return {"id": i, "name": name, "status": status, "busy": busy,
            "labels": [{"name": x} for x in labels]}


def job(status, labels, minutes_ago, **kw):
    ts = datetime.fromtimestamp(NOW.timestamp() - minutes_ago * 60, timezone.utc).isoformat()
    j = {"repo": "firmware", "workflow": "wf", "name": "job", "status": status,
         "labels": list(labels), "created_at": ts, "started_at": ts, "html_url": "u"}
    j.update(kw)
    return j


class BuildStateTest(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads(json.dumps(rs.DEFAULT_CONFIG))

    def test_runners_grouped_by_machine_and_status(self):
        raw = {"runners": [runner(1, "studio-mac-1", busy=True), runner(2, "gh-ubuntu-1"),
                           runner(3, "studio-build-2", status="offline"),
                           runner(4, "mystery-box")],
               "groups": {1: "Default"}}
        st = rs.build_state(raw, self.cfg, NOW)
        names = [m["name"] for m in st["machines"]]
        self.assertEqual(names, ["Mac Studio", "Other runners"])
        studio = st["machines"][0]
        self.assertEqual(studio["counts"], {"idle": 1, "busy": 1, "offline": 1})
        self.assertEqual(studio["runners"][2]["group"], "Default")
        self.assertIn("Offline runners: studio-build-2", [a["text"] for a in st["alerts"]])

    def test_dev_mac_appears_once_its_runner_exists(self):
        raw = {"runners": [runner(1, "macbook-dev-1")]}
        st = rs.build_state(raw, self.cfg, NOW)
        self.assertIn("Mac (dev)", [m["name"] for m in st["machines"]])
        self.assertNotIn("R620", [m["name"] for m in st["machines"]])

    def test_hosted_stall_and_queue_alerts(self):
        raw = {"jobs": [job("queued", ["ubuntu-latest"], 40),
                        job("queued", ["self-hosted", "Linux"], 25),
                        job("in_progress", ["self-hosted"], 5)]}
        st = rs.build_state(raw, self.cfg, NOW)
        texts = " ".join(a["text"] for a in st["alerts"])
        self.assertIn("2 job(s) queued", texts)
        self.assertIn("GitHub-hosted runners look stalled: 1", texts)
        self.assertEqual(st["counts"], {"queued": 2, "running": 1})
        self.assertEqual(st["jobs"][0]["status"], "queued")  # oldest queued first
        self.assertAlmostEqual(st["jobs"][0]["age_min"], 40, places=3)

    def test_fresh_hosted_job_is_not_a_stall(self):
        st = rs.build_state({"jobs": [job("queued", ["ubuntu-latest"], 2)]}, self.cfg, NOW)
        self.assertEqual(st["alerts"], [])

    def test_disabled_workflow_billing_disk_and_vm_alerts(self):
        gib = 1024 ** 3
        raw = {"disabled_workflows": [{"repo": "luci", "name": "CI", "state": "disabled_manually",
                                       "url": "x"}],
               "billing": {"included_minutes": 2000, "total_minutes_used": 2000},
               "machine_stats": {"Mac Studio": {
                   "disks": [{"path": "/", "total": 100 * gib, "used": 95 * gib, "free": 5 * gib}],
                   "vms": [{"name": "gh-build-2", "status": "Stopped"}]}}}
        levels = {a["text"]: a["level"] for a in rs.build_state(raw, self.cfg, NOW)["alerts"]}
        self.assertEqual(levels["Workflow disabled: luci / CI (disabled_manually)"], "warn")
        self.assertEqual(levels["Actions minutes 2000 of 2000 (100%) used this month"], "crit")
        self.assertIn("Mac Studio disk / low: 5.0 GB free", levels)
        self.assertIn("Mac Studio VM gh-build-2 is Stopped", levels)

    def test_demo_data_renders(self):
        st = rs.build_state(rs.demo_raw(), self.cfg, NOW)
        self.assertTrue(st["machines"][0]["runners"])


class TokenErrorTest(unittest.TestCase):
    def test_explanations(self):
        cases = [
            (401, "Bad credentials", "/orgs/x/actions/runners", "token rejected"),
            (403, "Resource not accessible by personal access token", "/orgs/x/actions/runners",
             "Self-hosted runners: Read-only"),
            (403, "Resource not accessible by personal access token", "/repos/x/y/actions/runs",
             "Actions: Read-only"),
            (403, "The 'ghostnet-labs' organization forbids access via a fine-grained personal "
                  "access tokens if the token's lifetime is greater than 366 days.",
             "/orgs/x/repos", "does not allow fine-grained"),
            (403, "API rate limit exceeded", "/orgs/x/repos", "rate limit"),
            (500, "boom", "/orgs/x/repos", "HTTP 500: boom"),
        ]
        for code, msg, path, want in cases:
            with self.subTest(code=code, msg=msg):
                self.assertIn(want, rs.explain_http_error(code, msg, path, "file", "kind"))

    def test_token_kind_never_shows_token(self):
        self.assertEqual(rs.token_kind("github_pat_abc"), "fine-grained personal token")
        self.assertEqual(rs.token_kind("ghs_abc"), "GitHub Actions or app token (short-lived)")
        self.assertNotIn("xyz", rs.token_kind("xyz"))

    def test_token_file_beats_stray_github_token(self):
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "token")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("github_pat_file\n")
            env = {"GITHUB_TOKEN": "ghs_runner"}
            with mock.patch.object(rs, "TOKEN_FILE", path), mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(rs.read_token(), ("github_pat_file", path))
            with mock.patch.object(rs, "TOKEN_FILE", os.path.join(d, "none")), \
                    mock.patch.dict(os.environ, {}, clear=True):
                token, source = rs.read_token()
                self.assertIsNone(token)
                self.assertIn("missing", source)

    def test_401_from_api_becomes_plain_error_and_alert(self):
        from http.server import BaseHTTPRequestHandler

        class H(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                body = b'{"message": "Bad credentials"}'
                self.send_response(401)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        srv = rs.ThreadingHTTPServer(("127.0.0.1", 0), H)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        self.addCleanup(t.join)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        gh = rs.GitHub("github_pat_x", "~/.config/runner-status/token")
        from unittest import mock
        with mock.patch.dict(os.environ, {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}):
            with self.assertRaises(rs.GitHubError) as ctx:
                gh.get(f"http://127.0.0.1:{srv.server_port}/orgs/x/actions/runners")
        self.assertIn("token rejected", str(ctx.exception))
        self.assertIn("fine-grained personal token", str(ctx.exception))
        st = rs.build_state({"errors": [f"Runners: {ctx.exception}"] * 2},
                            json.loads(json.dumps(rs.DEFAULT_CONFIG)), NOW)
        self.assertEqual(len(st["errors"]), 1)
        self.assertEqual(st["alerts"][0]["level"], "crit")


class ParserTest(unittest.TestCase):
    def test_vm_stat(self):
        text = ('Mach Virtual Memory Statistics: (page size of 16384 bytes)\n'
                'Pages free:                               1000.\n'
                'Pages active:                             2000.\n'
                'Pages wired down:                         500.\n'
                'Pages occupied by compressor:             100.\n')
        mem = rs.parse_vm_stat(text, 10 ** 9)
        self.assertEqual(mem["used"], 2600 * 16384)
        self.assertEqual(mem["compressed"], 100 * 16384)

    def test_lima_ndjson(self):
        text = ('{"name":"gh-ubuntu","status":"Running","cpus":6,"memory":6442450944,"disk":1}\n'
                '{"name":"gh-build-2","status":"Stopped","cpus":6,"memory":1,"disk":1}\n')
        vms = rs.parse_lima(text)
        self.assertEqual([v["name"] for v in vms], ["gh-ubuntu", "gh-build-2"])
        self.assertEqual(vms[1]["status"], "Stopped")

    def test_meminfo(self):
        mem = rs.parse_meminfo("MemTotal: 1000 kB\nMemAvailable: 400 kB\n")
        self.assertEqual(mem, {"total": 1024000, "used": 614400, "compressed": 0})

    def test_collect_stats_runs_here(self):
        st = rs.collect_stats(["/"])
        self.assertEqual(st["disks"][0]["path"], "/")


class ServerTest(unittest.TestCase):
    def test_page_and_state_endpoints(self):
        cfg = json.loads(json.dumps(rs.DEFAULT_CONFIG))
        cfg["machines"][0]["agent"] = ""
        poller = rs.Poller(cfg, None, demo=True)
        poller.poll_once()

        def body(path):
            if path == "/":
                return rs.PAGE, "text/html"
            if path == "/api/state":
                return json.dumps(poller.snapshot()), "application/json"
            return None, ""

        srv = rs.ThreadingHTTPServer(("127.0.0.1", 0), rs.make_handler(body))
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        self.addCleanup(t.join)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = f"http://127.0.0.1:{srv.server_port}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(base + "/") as r:
            self.assertIn(b"Builders and runners", r.read())
        with opener.open(base + "/api/state") as r:
            state = json.loads(r.read())
        self.assertEqual(state["machines"][0]["name"], "Mac Studio")
        with self.assertRaises(urllib.error.HTTPError):
            opener.open(base + "/nope")


if __name__ == "__main__":
    unittest.main()
