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

    def test_runner_and_vm_show_their_current_job_and_pr(self):
        raw = {"runners": [runner(1, "studio-build-1", busy=True), runner(2, "studio-build-2"),
                           runner(3, "gh-ubuntu-1", busy=True)],
               "jobs": [job("in_progress", ["self-hosted"], 12, runner_name="studio-build-1",
                            prs=[56]),
                        job("in_progress", ["self-hosted"], 3, runner_name="gh-ubuntu-1",
                            repo="docs", prs=[])],
               "machine_stats": {"Mac Studio": {"vms": [
                   {"name": "gh-build", "status": "Running"},
                   {"name": "gh-build-2", "status": "Running"},
                   {"name": "gh-ubuntu", "status": "Running"}]}}}
        st = rs.build_state(raw, self.cfg, NOW)
        studio = st["machines"][0]
        by_name = {r["name"]: r for r in studio["runners"]}
        build = by_name["studio-build-1"]["job"]
        self.assertEqual(build["prs"], [{"number": 56, "url":
                                         "https://github.com/ghostnet-labs/firmware/pull/56"}])
        self.assertAlmostEqual(build["age_min"], 12, places=3)
        self.assertIsNone(by_name["studio-build-2"]["job"])
        vms = {v["name"]: v for v in studio["stats"]["vms"]}
        self.assertEqual(vms["gh-build"]["runners"], ["studio-build-1"])
        self.assertEqual(vms["gh-build"]["jobs"][0]["repo"], "firmware")
        self.assertEqual((vms["gh-build-2"]["runners"], vms["gh-build-2"]["jobs"]),
                         (["studio-build-2"], []))
        self.assertEqual(vms["gh-ubuntu"]["jobs"][0]["repo"], "docs")
        # The input stats are not mutated (they can be shared with the push thread).
        self.assertNotIn("runners", raw["machine_stats"]["Mac Studio"]["vms"][0])

    def test_dev_mac_appears_once_its_runner_exists(self):
        raw = {"runners": [runner(1, "macbook-pro-build-1")]}
        st = rs.build_state(raw, self.cfg, NOW)
        pro = next(m for m in st["machines"] if m["name"] == "MacBook Pro")
        self.assertEqual(pro["runners"][0]["name"], "macbook-pro-build-1")
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


class FakeGitHub:
    """Answers the API paths the poller uses; records calls."""

    def __init__(self):
        self.token, self.kind, self.source = "github_pat_fake", "fine-grained", "test"
        self.mu = threading.Lock()  # protects calls
        self.calls = []
        self.rate_remaining = 4999

    def get(self, path, params=None):
        with self.mu:
            self.calls.append(path)
        if path.endswith("/actions/runners"):
            return {"runners": [runner(1, "studio-mac-1", busy=True)]}
        if path.endswith("/repos"):
            return [{"name": "firmware"}, {"name": "docs"}, {"name": "old", "archived": True}]
        if path.endswith("/runner-groups"):
            return {"runner_groups": [{"id": 1, "name": "Default"}]}
        if "/runner-groups/1/runners" in path:
            return {"runners": [{"id": 1}]}
        if path.endswith("/actions/runs"):
            if path.startswith("/repos/o/firmware") and params["status"] == "queued":
                return {"workflow_runs": [{"name": "Build", "head_branch": "main",
                                           "jobs_url": "jobs/firmware/1",
                                           "pull_requests": [{"number": 41}]}]}
            return {"workflow_runs": []}
        if path.startswith("jobs/"):
            return {"jobs": [job("queued", ["ubuntu-latest"], 3), job("completed", [], 9)]}
        if path.endswith("/actions/workflows"):
            return {"workflows": [{"name": "Old", "state": "disabled_manually"}]}
        raise rs.GitHubError("not available")

    def usage(self):
        with self.mu:  # like GitHub.usage(), which holds its non-reentrant lock
            return {"remaining": self.rate_remaining, "limit": 5000, "reset": None,
                    "used_by_page_last_hour": len(self.calls), "free_304s": 0}


class PollerTest(unittest.TestCase):
    def test_first_sweep_paints_runners_before_jobs(self):
        from unittest import mock
        cfg = json.loads(json.dumps(rs.DEFAULT_CONFIG))
        cfg["org"] = "o"
        cfg["machines"][0]["agent"] = ""
        gh = FakeGitHub()
        poller = rs.Poller(cfg, gh)
        self.assertTrue(poller.snapshot()["loading"])  # before any poll
        published = []
        with mock.patch.object(rs, "read_token", return_value=(gh.token, "test")):
            raw = poller.fetch(lambda r: published.append(rs.build_state(r, cfg, NOW)))
        first = published[0]
        self.assertTrue(first["loading"])
        self.assertEqual(first["machines"][0]["counts"]["busy"], 1)
        self.assertEqual(first["jobs"], [])
        final = rs.build_state(raw, cfg, NOW)
        self.assertFalse(final["loading"])
        self.assertEqual(final["counts"], {"queued": 1, "running": 0})
        self.assertEqual(final["jobs"][0]["prs"][0]["number"], 41)
        self.assertEqual(final["machines"][0]["runners"][0]["group"], "Default")
        self.assertIn("Workflow disabled: firmware / Old (disabled_manually)",
                      [a["text"] for a in final["alerts"]])
        self.assertNotIn("/repos/o/old/actions/runs", gh.calls)

        # Second sweep: no loading placeholder, cached repos, no workflow re-scan.
        published.clear()
        before = len(gh.calls)
        with mock.patch.object(rs, "read_token", return_value=(gh.token, "test")):
            poller.fetch(lambda r: published.append(r))
        self.assertEqual(published, [])
        self.assertFalse(any(c.endswith("/workflows") for c in gh.calls[before:]))


    def test_sweep_finishes_while_usage_takes_the_client_lock(self):
        from unittest import mock
        cfg = json.loads(json.dumps(rs.DEFAULT_CONFIG))
        cfg["org"] = "o"
        cfg["machines"][0]["agent"] = ""
        gh = FakeGitHub()
        poller = rs.Poller(cfg, gh)
        out = []
        with mock.patch.object(rs, "read_token", return_value=(gh.token, "test")):
            t = threading.Thread(target=lambda: out.append(poller.fetch()), daemon=True)
            t.start()
            t.join(10)
        self.assertFalse(t.is_alive(), "fetch() deadlocked on the GitHub client lock")
        self.assertEqual(out[0]["rate"]["remaining"], 4999)


class PushTest(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads(json.dumps(rs.DEFAULT_CONFIG))
        self.cfg["machines"][0]["agent"] = ""
        self.poller = rs.Poller(self.cfg, None, demo=True)
        self.poller.poll_once()
        self.handle = rs.push_receiver(self.poller)

    def post(self, data, key=None):
        headers = {"X-Push-Key": key} if key else {}
        return self.handle("/api/push", headers, json.dumps(data).encode())

    def test_push_shows_stats_and_sanitizes(self):
        from unittest import mock
        stats = {"cores": 12, "load": [1.0, 2.0, 3.0, 4.0], "evil": "<script>",
                 "memory": {"total": 100, "used": 50, "x": 1},
                 "disks": [{"path": "/", "total": 10, "used": 5, "free": 5, "junk": 1}],
                 "vms": [{"name": "gh-build", "status": "Running", "cpus": "6"}]}
        with mock.patch.object(rs, "read_push_key", return_value="k"):
            self.assertEqual(self.post({"name": "MacBook Pro", "stats": stats}, "k"), (200, "ok"))
        pro = next(m for m in self.poller.snapshot()["machines"] if m["name"] == "MacBook Pro")
        self.assertEqual(pro["stats"]["memory"], {"total": 100, "used": 50, "compressed": None})
        self.assertEqual(pro["stats"]["load"], [1.0, 2.0, 3.0])
        self.assertNotIn("evil", pro["stats"])
        self.assertEqual(pro["stats"]["disks"][0], {"path": "/", "total": 10, "used": 5, "free": 5})
        self.assertIsNone(pro["stats"]["vms"][0]["cpus"])
        self.assertEqual(self.poller.fetch_agents([])["MacBook Pro"]["cores"], 12)

    def test_push_rejections(self):
        from unittest import mock
        with mock.patch.object(rs, "read_push_key", return_value=None):
            code, text = self.post({"name": "MacBook Pro", "stats": {}}, "anything")
            self.assertEqual(code, 403)
            self.assertIn("push disabled", text)
        with mock.patch.object(rs, "read_push_key", return_value="sekrit"):
            self.assertEqual(self.post({"name": "MacBook Pro", "stats": {}})[0], 403)
            self.assertEqual(self.post({"name": "MacBook Pro", "stats": {}}, "nope")[0], 403)
            self.assertEqual(self.post({"name": "MacBook Pro", "stats": {}}, "sekrit")[0], 200)
            self.assertEqual(self.post({"name": "Mac Studio", "stats": {}}, "sekrit")[0], 403)
            self.assertEqual(self.handle("/api/push", {"X-Push-Key": "sekrit"}, b"{")[0], 400)
            self.assertEqual(self.post({"name": "MacBook Pro"}, "sekrit")[0], 400)
            self.assertEqual(self.handle("/other", {}, b"{}")[0], 404)

    def test_missing_and_stale_push(self):
        from unittest import mock
        self.assertIn("no stats pushed yet", self.poller.fetch_agents([])["MacBook Pro"]["error"])
        self.poller.pushed["MacBook Pro"] = ({"cores": 1}, 0.0)
        self.assertIn("no stats pushed for", self.poller.fetch_agents([])["MacBook Pro"]["error"])
        st = rs.build_state({"machine_stats": self.poller.fetch_agents([])}, self.cfg, NOW)
        self.assertTrue(any("MacBook Pro stats missing" in a["text"] for a in st["alerts"]))

    def test_push_endpoint_over_http_and_size_limit(self):
        srv = rs.ThreadingHTTPServer(("127.0.0.1", 0),
                                     rs.make_handler(lambda p: (None, ""), self.handle))
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        self.addCleanup(t.join)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        url = f"http://127.0.0.1:{srv.server_port}/api/push"
        from unittest import mock
        with mock.patch.object(rs, "read_push_key", return_value="k"):
            body = json.dumps({"name": "MacBook Pro", "stats": {"cores": 2}}).encode()
            req = urllib.request.Request(url, data=body, method="POST", headers={"X-Push-Key": "k"})
            with opener.open(req) as r:
                self.assertEqual(r.read(), b"ok")
            big = b"x" * (rs.PUSH_MAX_BYTES + 1)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                opener.open(urllib.request.Request(url, data=big, method="POST"))
            self.assertEqual(ctx.exception.code, 413)


class RateLimitTest(unittest.TestCase):
    def test_etag_304_returns_cache_and_is_not_billed(self):
        from http.server import BaseHTTPRequestHandler
        hits = []

        class H(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                hits.append(self.headers.get("If-None-Match"))
                if self.headers.get("If-None-Match") == '"v1"':
                    self.send_response(304)
                    self.send_header("X-RateLimit-Remaining", "4000")
                    self.end_headers()
                    return
                body = b'{"runners": [1]}'
                self.send_response(200)
                self.send_header("ETag", '"v1"')
                self.send_header("X-RateLimit-Remaining", "4000")
                self.send_header("X-RateLimit-Limit", "5000")
                self.send_header("X-RateLimit-Reset", "1760000000")
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
        from unittest import mock
        gh = rs.GitHub("github_pat_x", "test")
        url = f"http://127.0.0.1:{srv.server_port}/orgs/o/actions/runners"
        with mock.patch.dict(os.environ, {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}):
            first = gh.get(url)
            second = gh.get(url)
        self.assertEqual(first, second)
        self.assertEqual(hits, [None, '"v1"'])
        usage = gh.usage()
        self.assertEqual(usage["used_by_page_last_hour"], 1)
        self.assertEqual(usage["free_304s"], 1)
        self.assertEqual((usage["remaining"], usage["limit"], usage["reset"]),
                         (4000, 5000, 1760000000))

    def test_next_wait(self):
        self.assertEqual(rs.next_wait({"blocked": True}, 60), rs.ERROR_RETRY_SECONDS)
        # A per-repo error is not a reason to poll faster.
        self.assertEqual(rs.next_wait({"errors": ["firmware runs: boom"]}, 60), 60)
        low = {"rate": {"remaining": 900, "limit": 5000}}
        self.assertEqual(rs.next_wait(low, 60), rs.LOW_QUOTA_POLL_SECONDS)
        self.assertEqual(rs.next_wait({"rate": {"remaining": 4000, "limit": 5000}}, 60), 60)

    def test_low_quota_alert(self):
        cfg = json.loads(json.dumps(rs.DEFAULT_CONFIG))
        st = rs.build_state({"rate": {"remaining": 100, "limit": 5000}}, cfg, NOW)
        self.assertTrue(any("API quota low" in a["text"] for a in st["alerts"]))


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
