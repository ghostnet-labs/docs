"""Tests for studio_runners.py. Run: python3 -m unittest discover -s tools/studio-runners"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio_runners as sr  # noqa: E402

NOW = datetime(2026, 11, 26, 16, 0, tzinfo=timezone.utc)
REPO = "ghostnet-labs/docs"


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def job(labels, status="completed", conclusion="success", created=None, started=None,
        completed=None, runner="", name="Build", url="https://example/job"):
    return {"labels": labels, "status": status, "conclusion": conclusion, "name": name,
            "created_at": iso(created) if created else None, "started_at": iso(started) if started else None,
            "completed_at": iso(completed) if completed else None, "runner_name": runner, "html_url": url}


MAC = ["self-hosted", "macOS", "ARM64"]
ARC = ["ghostnet-linux-arm64"]
BUILD = ["self-hosted", "openwrt-build"]
HOSTED = ["ubuntu-24.04"]


def runner(name, labels, status="online"):
    return {"name": name, "status": status, "labels": [{"name": label} for label in labels]}


class FakeGitHub:
    """Serves canned GET answers by path prefix and records POSTs."""

    def __init__(self, routes=None, errors=None):
        self.routes = routes or {}
        self.errors = errors or {}
        self.posts = []
        self.calls = 0

    def _match(self, table, path):
        for prefix in sorted(table, key=len, reverse=True):
            if path.startswith(prefix):
                return table[prefix]
        return None

    def get(self, path):
        self.calls += 1
        err = self._match(self.errors, path)
        if err is not None:
            raise err
        value = self._match(self.routes, path)
        if callable(value):
            return value(path)
        return value if value is not None else {}

    def post(self, path, body=None):
        self.posts.append(path)
        return {}


class PoolOfTest(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(sr.pool_of(MAC), "mac")
        self.assertEqual(sr.pool_of(["ghostnet-gate"]), "arc")
        self.assertEqual(sr.pool_of(["ghostnet-linux-arm64-large"]), "arc")
        self.assertEqual(sr.pool_of(BUILD), "build")
        self.assertIsNone(sr.pool_of(HOSTED))
        self.assertIsNone(sr.pool_of(["self-hosted", "Linux", "ARM64"]))
        self.assertIsNone(sr.pool_of(["ghostnet-linux-arm64X"]))
        self.assertIsNone(sr.pool_of(None))


class CountOnlineTest(unittest.TestCase):
    def test_counts_and_skips_retired(self):
        counts = sr.count_online([
            runner("studio-mac-1", MAC), runner("studio-mac-2", MAC, "offline"),
            runner("studio-build-1", BUILD, "offline"), runner("gh-ubuntu-1", BUILD),
            runner("ghostnet-linux-arm64-abc", ARC),
        ])
        self.assertEqual(counts, {"mac": 1, "arc": 1, "build": 0})


class DecideWithRunnerListTest(unittest.TestCase):
    def ev(self, jobs=()):
        return sr.job_evidence(list(jobs), NOW)

    def test_all_online(self):
        v = sr.decide({"mac": 3, "arc": 0, "build": 1}, self.ev())
        self.assertTrue(all(v[p]["online"] for p in sr.POOLS))
        self.assertIn("same host", v["arc"]["why"])

    def test_studio_off(self):
        v = sr.decide({"mac": 0, "arc": 0, "build": 0}, self.ev())
        self.assertFalse(any(v[p]["online"] for p in sr.POOLS))

    def test_macbook_builder_keeps_build_pool(self):
        v = sr.decide({"mac": 0, "arc": 0, "build": 1}, self.ev())
        self.assertTrue(v["build"]["online"])
        self.assertFalse(v["mac"]["online"])

    def test_arc_pod_listed_is_online_even_if_queue_is_long(self):
        stuck = job(ARC, status="queued", conclusion=None, created=NOW - timedelta(hours=2))
        v = sr.decide({"mac": 1, "arc": 1, "build": 1}, self.ev([stuck]))
        self.assertTrue(v["arc"]["online"])

    def test_arc_down_when_no_pod_and_job_waits(self):
        stuck = job(ARC, status="queued", conclusion=None, created=NOW - timedelta(minutes=45))
        v = sr.decide({"mac": 2, "arc": 0, "build": 1}, self.ev([stuck]))
        self.assertFalse(v["arc"]["online"])
        self.assertTrue(v["mac"]["online"])

    def test_short_arc_wait_is_not_an_outage(self):
        queued = job(ARC, status="queued", conclusion=None, created=NOW - timedelta(minutes=10))
        v = sr.decide({"mac": 2, "arc": 0, "build": 1}, self.ev([queued]))
        self.assertTrue(v["arc"]["online"])


class DecideFromJobsTest(unittest.TestCase):
    def test_no_evidence_assumed_online(self):
        v = sr.decide(None, sr.job_evidence([], NOW))
        self.assertTrue(all(v[p]["online"] for p in sr.POOLS))

    def test_expired_wait_marks_pool_and_host_offline(self):
        # docs #197: the gate waited 24 hours on the Macs and was cancelled.
        created = NOW - timedelta(hours=30)
        expired = job(MAC, conclusion="cancelled", created=created, completed=created + timedelta(hours=24))
        v = sr.decide(None, sr.job_evidence([expired], NOW))
        self.assertFalse(v["mac"]["online"])
        self.assertFalse(v["arc"]["online"])  # no evidence of its own: follows the host
        self.assertFalse(v["build"]["online"])

    def test_later_runner_clears_the_wait(self):
        created = NOW - timedelta(hours=30)
        expired = job(MAC, conclusion="cancelled", created=created, completed=created + timedelta(hours=24))
        ok = job(MAC, created=NOW - timedelta(hours=2), started=NOW - timedelta(hours=2), runner="studio-mac-1")
        v = sr.decide(None, sr.job_evidence([expired, ok], NOW))
        self.assertTrue(v["mac"]["online"])

    def test_concurrency_cancel_is_not_an_outage(self):
        created = NOW - timedelta(hours=1)
        cancelled = job(MAC, conclusion="cancelled", created=created, completed=created + timedelta(minutes=5))
        v = sr.decide(None, sr.job_evidence([cancelled], NOW))
        self.assertTrue(v["mac"]["online"])

    def test_live_wait(self):
        stuck = job(ARC, status="queued", conclusion=None, created=NOW - timedelta(minutes=40))
        busy = job(MAC, status="in_progress", conclusion=None, created=NOW - timedelta(minutes=5),
                   started=NOW - timedelta(minutes=4), runner="studio-mac-3")
        v = sr.decide(None, sr.job_evidence([stuck, busy], NOW))
        self.assertFalse(v["arc"]["online"])
        self.assertTrue(v["mac"]["online"])

    def test_hosted_jobs_ignored(self):
        created = NOW - timedelta(hours=30)
        hosted = job(HOSTED, conclusion="cancelled", created=created, completed=created + timedelta(hours=24))
        v = sr.decide(None, sr.job_evidence([hosted], NOW))
        self.assertTrue(all(v[p]["online"] for p in sr.POOLS))


class ReadRunnersTest(unittest.TestCase):
    def test_missing_token(self):
        self.assertEqual(sr.read_runners(""), (None, "RUNNER_READ_TOKEN is not set"))

    def test_rejected_token_links_renewal(self):
        gh = FakeGitHub(errors={"/orgs/": sr.HTTPError(401, "HTTP 401")})
        counts, problem = sr.read_runners("x", gh)
        self.assertIsNone(counts)
        self.assertIn(sr.TOKEN_PAGE, problem)
        self.assertIn(sr.SECRET_PAGE, problem)

    def test_reads_runners(self):
        gh = FakeGitHub({"/orgs/": {"runners": [runner("studio-mac-1", MAC)]}})
        counts, problem = sr.read_runners("x", gh)
        self.assertIsNone(problem)
        self.assertEqual(counts["mac"], 1)


def runs_route(by_status):
    def answer(path):
        for status, runs in by_status.items():
            if f"status={status}&" in path:
                return {"workflow_runs": [dict(r) for r in runs]}
        return {"workflow_runs": []}
    return answer


class PickTest(unittest.TestCase):
    def run_pick(self, gh, runner_fetch=None, env=None):
        with tempfile.TemporaryDirectory() as tmp:
            out, summary = Path(tmp, "out"), Path(tmp, "summary")
            saved = dict(os.environ)
            os.environ.update({"GITHUB_OUTPUT": str(out), "GITHUB_STEP_SUMMARY": str(summary),
                               "RUNNER_READ_TOKEN": "", **(env or {})})
            try:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    sr.pick(REPO, NOW, gh=gh, runner_fetch=runner_fetch)
            finally:
                os.environ.clear()
                os.environ.update(saved)
            return out.read_text(), summary.read_text(), buf.getvalue()

    def test_crash_keeps_studio_routes(self):
        gh = FakeGitHub(errors={"/repos/": sr.HTTPError(500, "boom")})
        out, summary, log = self.run_pick(gh)
        self.assertEqual(out, "mac=true\narc=true\nbuild=true\n")
        self.assertIn("check failed", summary)

    def test_offline_writes_false_and_warns(self):
        gh = FakeGitHub({"/repos/": {"workflow_runs": []}})
        rf = FakeGitHub({"/orgs/": {"runners": [runner("studio-mac-1", MAC, "offline")]}})
        out, summary, log = self.run_pick(gh, rf, {"RUNNER_READ_TOKEN": "x"})
        self.assertEqual(out, "mac=false\narc=false\nbuild=false\n")
        self.assertIn("GitHub-hosted fallback", summary)
        self.assertIn("::warning title=Studio runners offline::", log)

    def test_token_mode_skips_deep_scan(self):
        gh = FakeGitHub({"/repos/": {"workflow_runs": []}})
        rf = FakeGitHub({"/orgs/": {"runners": [runner("studio-mac-1", MAC)]}})
        self.run_pick(gh, rf, {"RUNNER_READ_TOKEN": "x"})
        self.assertEqual(gh.calls, 2)  # queued and in_progress lists only


class RescueTest(unittest.TestCase):
    def setUp(self):
        self.queued_run = {"id": 10, "status": "queued", "run_attempt": 1, "event": "pull_request",
                           "html_url": "https://example/run/10"}
        self.jobs = [job(HOSTED, name="Studio runners", created=NOW - timedelta(hours=1),
                         started=NOW - timedelta(hours=1), runner="GitHub Actions 1"),
                     job(MAC, status="queued", conclusion=None, name="Manet merge gate",
                         created=NOW - timedelta(hours=1))]

    def gh(self, runs, jobs, extra=None):
        routes = {"/repos/{}/actions/runs?".format(REPO): runs_route(runs),
                  "/repos/{}/actions/runs/".format(REPO): lambda p: {"jobs": jobs} if "/jobs" in p
                  else {"status": "completed"}}
        routes.update(extra or {})
        return FakeGitHub(routes)

    def test_cancels_and_reruns_stuck_run(self):
        gh = self.gh({"queued": [self.queued_run]}, self.jobs)
        rf = FakeGitHub({"/orgs/": {"runners": []}})
        with redirect_stdout(io.StringIO()):
            done = sr.rescue(gh, REPO, NOW, "x", runner_fetch=rf, sleep=lambda s: None)
        self.assertEqual(gh.posts, [f"/repos/{REPO}/actions/runs/10/cancel", f"/repos/{REPO}/actions/runs/10/rerun"])
        self.assertEqual(len(done), 1)

    def test_leaves_runs_without_selector(self):
        gh = self.gh({"queued": [self.queued_run]}, self.jobs[1:])
        rf = FakeGitHub({"/orgs/": {"runners": []}})
        with redirect_stdout(io.StringIO()):
            sr.rescue(gh, REPO, NOW, "x", runner_fetch=rf, sleep=lambda s: None)
        self.assertEqual(gh.posts, [])

    def test_attempt_cap(self):
        run = dict(self.queued_run, run_attempt=3)
        gh = self.gh({"queued": [run]}, self.jobs)
        rf = FakeGitHub({"/orgs/": {"runners": []}})
        with redirect_stdout(io.StringIO()):
            sr.rescue(gh, REPO, NOW, "x", runner_fetch=rf, sleep=lambda s: None)
        self.assertEqual(gh.posts, [])

    def test_nothing_when_online(self):
        gh = self.gh({"queued": [self.queued_run]}, self.jobs)
        rf = FakeGitHub({"/orgs/": {"runners": [runner("studio-mac-1", MAC)]}})
        with redirect_stdout(io.StringIO()):
            sr.rescue(gh, REPO, NOW, "x", runner_fetch=rf, sleep=lambda s: None)
        self.assertEqual(gh.posts, [])

    def test_dry_run(self):
        gh = self.gh({"queued": [self.queued_run]}, self.jobs)
        rf = FakeGitHub({"/orgs/": {"runners": []}})
        with redirect_stdout(io.StringIO()):
            done = sr.rescue(gh, REPO, NOW, "x", dry_run=True, runner_fetch=rf)
        self.assertEqual(gh.posts, [])
        self.assertTrue(done[0].startswith("would cancel"))



if __name__ == "__main__":
    unittest.main()
