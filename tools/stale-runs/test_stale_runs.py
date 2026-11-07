"""Tests for stale_runs.py. Run: python3 -m unittest discover -s tools/stale-runs -v"""

from __future__ import annotations

import io
import json
import re
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stale_runs as sr  # noqa: E402

NOW = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)


def ts(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z")


def pr(number: int, branch: str, sha: str) -> dict:
    return {"number": number, "head": {"ref": branch, "sha": sha}}


def run(rid: int, *, wf: int = 1, name: str = "CI", event: str = "pull_request",
        branch: str = "feat", sha: str = "a" * 40, prs: list[int] | None = None,
        status: str = "in_progress", hours: float = 0.5) -> dict:
    return {"id": rid, "workflow_id": wf, "name": name, "event": event,
            "head_branch": branch, "head_sha": sha, "status": status,
            "created_at": ts(hours), "html_url": f"https://github.com/x/y/actions/runs/{rid}",
            "pull_requests": [{"number": n} for n in (prs or [])]}


class FakeGitHub:
    """Serves canned GET answers and records cancels."""

    def __init__(self, routes: dict[str, object]):
        self.routes = routes
        self.gets: list[str] = []
        self.cancelled: list[tuple[str, int]] = []
        self.calls = 0
        self.not_modified = 0

    def get(self, path: str):
        self.gets.append(path)
        for prefix, data in self.routes.items():
            if path.startswith(prefix):
                return data
        raise RuntimeError(f"unexpected GET {path}")

    def cancel(self, repo: str, run_id: int) -> str:
        self.cancelled.append((repo, run_id))
        return "cancelled"

    def save(self) -> None:
        pass


class TestClassify(unittest.TestCase):
    def classes(self, runs, prs, head_runs=None):
        items = sr.classify("firmware", runs, {p["number"]: p for p in prs}, NOW, 3.0, head_runs)
        return {i["id"]: (i["class"], i["cancel"]) for i in items}

    def test_current_head_of_open_pr_is_live(self):
        got = self.classes([run(1, sha="h1", prs=[5])], [pr(5, "feat", "h1")])
        self.assertEqual(got[1], ("live", False))

    def test_closed_pr_run_is_dead(self):
        got = self.classes([run(1, prs=[5])], [])
        self.assertEqual(got[1], ("closed", True))

    def test_deleted_branch_without_pr_list_is_dead(self):
        got = self.classes([run(1, prs=[], branch="gone")], [pr(7, "other", "z")])
        self.assertEqual(got[1], ("closed", True))

    def test_fork_pr_matched_by_branch_stays_live(self):
        got = self.classes([run(1, prs=[], branch="feat", sha="h1")], [pr(5, "feat", "h1")])
        self.assertEqual(got[1], ("live", False))

    def test_old_head_superseded_only_when_new_head_has_same_workflow(self):
        runs = [run(1, sha="old", prs=[5]), run(2, sha="new", prs=[5])]
        got = self.classes(runs, [pr(5, "feat", "new")])
        self.assertEqual(got[1], ("superseded", True))
        self.assertEqual(got[2], ("live", False))

    def test_old_head_kept_when_new_head_has_no_run_of_that_workflow(self):
        runs = [run(1, wf=1, sha="old", prs=[5]), run(2, wf=2, sha="new", prs=[5])]
        got = self.classes(runs, [pr(5, "feat", "new")])
        self.assertEqual(got[1], ("live", False))

    def test_old_head_superseded_by_completed_head_run(self):
        got = self.classes([run(1, sha="old", prs=[5])], [pr(5, "feat", "new")],
                           head_runs={(1, "new")})
        self.assertEqual(got[1], ("superseded", True))

    def test_pull_request_target_without_pr_number_is_not_guessed(self):
        got = self.classes([run(1, event="pull_request_target", prs=[], branch="24.10")], [])
        self.assertEqual(got[1], ("live", False))

    def test_push_runs_are_never_cancelled(self):
        runs = [run(1, event="push", branch="24.10", sha="a", hours=2),
                run(2, event="push", branch="24.10", sha="b", hours=1)]
        got = self.classes(runs, [])
        self.assertEqual(got[1], ("stuck-push", False))
        self.assertEqual(got[2], ("live", False))

    def test_dispatch_and_schedule_are_never_cancelled(self):
        runs = [run(1, event="workflow_dispatch", hours=10), run(2, event="schedule", hours=0.1)]
        got = self.classes(runs, [])
        self.assertEqual(got[1], ("zombie", False))
        self.assertEqual(got[2], ("live", False))

    def test_old_live_run_is_reported_as_zombie_not_cancelled(self):
        got = self.classes([run(1, sha="h1", prs=[5], hours=5)], [pr(5, "feat", "h1")])
        self.assertEqual(got[1], ("zombie", False))


class TestOrphanAndMinAge(unittest.TestCase):
    def classify(self, runs, prs=(), tips=None, **kw):
        items = sr.classify("packages", runs, {p["number"]: p for p in prs}, NOW, 3.0,
                            None, tips, **kw)
        return {i["id"]: (i["class"], i["cancel"]) for i in items}

    def test_unstarted_push_run_on_deleted_branch_is_orphan(self):
        got = self.classify([run(1, event="push", branch="gone", sha="a", status="queued", hours=30)],
                            tips={"gone": None})
        self.assertEqual(got[1], ("orphan", True))

    def test_unstarted_push_run_on_moved_branch_is_orphan(self):
        got = self.classify([run(1, event="push", branch="dev", sha="a", status="waiting", hours=25)],
                            tips={"dev": "b" * 40})
        self.assertEqual(got[1], ("orphan", True))

    def test_push_run_on_current_tip_is_not_orphan(self):
        got = self.classify([run(1, event="push", branch="dev", sha="a", status="queued", hours=30)],
                            tips={"dev": "a"})
        self.assertEqual(got[1], ("zombie", False))

    def test_push_run_younger_than_orphan_hours_is_left_to_a_person(self):
        got = self.classify([run(1, event="push", branch="dev", sha="a", status="queued", hours=10)],
                            tips={"dev": "b"})
        self.assertEqual(got[1], ("zombie", False))

    def test_started_push_run_is_never_orphan(self):
        got = self.classify([run(1, event="push", branch="dev", sha="a", status="in_progress", hours=30)],
                            tips={"dev": "b"})
        self.assertEqual(got[1], ("zombie", False))

    def test_unknown_branch_tip_is_never_orphan(self):
        got = self.classify([run(1, event="push", branch="dev", sha="a", status="queued", hours=30)],
                            tips={})
        self.assertEqual(got[1], ("zombie", False))

    def test_orphan_hours_is_configurable(self):
        got = self.classify([run(1, event="push", branch="dev", sha="a", status="queued", hours=10)],
                            tips={"dev": "b"}, orphan_hours=6)
        self.assertEqual(got[1], ("orphan", True))

    def test_min_age_holds_back_closed_and_superseded(self):
        runs = [run(1, prs=[5], hours=2), run(2, sha="old", prs=[6], hours=2),
                run(3, sha="new", prs=[6], hours=1), run(4, prs=[7], hours=30)]
        got = self.classify(runs, prs=[pr(6, "feat", "new")], min_age_hours=24)
        self.assertEqual(got[1], ("closed", False))
        self.assertEqual(got[2], ("superseded", False))
        self.assertEqual(got[4], ("closed", True))

    def test_min_age_reason_says_why(self):
        items = sr.classify("packages", [run(1, prs=[5], hours=2)], {}, NOW, 3.0, min_age_hours=24)
        self.assertIn("younger than 24 h", items[0]["reason"])

    def test_orphan_kernel_run_still_needs_an_expanded_matrix(self):
        items = sr.classify("firmware", [run(1, name="Build Kernel", event="push", branch="dev",
                                             sha="a", status="queued", hours=30)],
                            {}, NOW, 3.0, None, {"dev": "b"})
        gh = FakeGitHub({"/repos/ghostnet-labs/firmware/actions/runs/1/jobs": {"total_count": 1, "jobs": []}})
        sr.apply_guards(items, gh, re.compile(sr.DEFAULT_PROTECT), set(), set())
        self.assertEqual(items[0]["class"], "orphan")
        self.assertFalse(items[0]["cancel"])


class TestBranchTip(unittest.TestCase):
    def test_tip_of_a_live_branch(self):
        gh = FakeGitHub({"/repos/ghostnet-labs/packages/git/ref/heads/claude/x": {"object": {"sha": "abc"}}})
        self.assertEqual(sr.branch_tip(gh, "packages", "claude/x"), (True, "abc"))

    def test_deleted_branch_is_known_with_no_tip(self):
        gh = FakeGitHub({})
        gh.get = lambda path: (_ for _ in ()).throw(RuntimeError(f"GET {path}: HTTP 404: Not Found"))
        self.assertEqual(sr.branch_tip(gh, "packages", "gone"), (True, None))

    def test_other_errors_leave_the_branch_unknown(self):
        gh = FakeGitHub({})
        gh.get = lambda path: (_ for _ in ()).throw(RuntimeError(f"GET {path}: HTTP 502: Bad Gateway"))
        self.assertEqual(sr.branch_tip(gh, "packages", "dev"), (False, None))


class TestScanOrphans(unittest.TestCase):
    def test_scan_looks_up_only_branches_with_old_unstarted_push_runs(self):
        base = "/repos/ghostnet-labs/packages"
        gh = FakeGitHub({
            f"{base}/pulls": [],
            f"{base}/actions/runs?status=queued": {"workflow_runs": [
                run(1, event="push", branch="gone", sha="a", status="queued", hours=30),
                run(2, event="push", branch="fresh", sha="b", status="queued", hours=1),
                run(3, event="push", branch="live", sha="c", status="queued", hours=40)]},
            f"{base}/actions/runs?status=in_progress": {"workflow_runs": []},
            f"{base}/actions/runs?status=waiting": {"workflow_runs": []},
            f"{base}/git/ref/heads/live": {"object": {"sha": "c"}},
        })
        real_get = gh.get

        def get(path):
            if path.endswith("/heads/gone"):
                raise RuntimeError(f"GET {path}: HTTP 404: Not Found")
            return real_get(path)
        gh.get = get
        items = sr.scan(gh, ["packages"], NOW, 3.0)
        got = {i["id"]: (i["class"], i["cancel"]) for i in items}
        self.assertEqual(got[1], ("orphan", True))
        self.assertEqual(got[3], ("zombie", False))
        self.assertEqual(got[2], ("live", False))
        self.assertFalse(any("heads/fresh" in p for p in gh.gets))


class TestGuards(unittest.TestCase):
    PROTECT = re.compile(sr.DEFAULT_PROTECT)

    def items(self, runs, prs):
        return sr.classify("firmware", runs, {p["number"]: p for p in prs}, NOW, 3.0)

    def test_kernel_run_before_matrix_expands_is_left_alone(self):
        items = self.items([run(1, name="Build Kernel", prs=[5])], [])
        gh = FakeGitHub({"/repos/ghostnet-labs/firmware/actions/runs/1/jobs":
                         {"total_count": 1, "jobs": [{"status": "queued", "labels": ["ubuntu-latest"]}]}})
        sr.apply_guards(items, gh, self.PROTECT, set(), set())
        self.assertFalse(items[0]["cancel"])
        self.assertIn("not expanded", items[0]["reason"])

    def test_kernel_run_after_matrix_expands_can_go(self):
        items = self.items([run(1, name="Build Kernel", prs=[5])], [])
        gh = FakeGitHub({"/repos/ghostnet-labs/firmware/actions/runs/1/jobs":
                         {"total_count": 7, "jobs": []}})
        sr.apply_guards(items, gh, self.PROTECT, set(), set())
        self.assertTrue(items[0]["cancel"])

    def test_kernel_run_with_unreadable_jobs_is_left_alone(self):
        items = self.items([run(1, name="Build Kernel", prs=[5])], [])
        sr.apply_guards(items, FakeGitHub({}), self.PROTECT, set(), set())
        self.assertFalse(items[0]["cancel"])

    def test_skip_pr_and_skip_run_win(self):
        items = self.items([run(1, prs=[52]), run(2, prs=[60])], [])
        sr.apply_guards(items, FakeGitHub({}), self.PROTECT, {"firmware#52"}, {2})
        self.assertEqual([i["cancel"] for i in items], [False, False])
        self.assertEqual([i["class"] for i in items], ["off-limits", "off-limits"])

    def test_zombie_gets_job_count_and_waiting_labels(self):
        items = self.items([run(1, event="workflow_dispatch", status="queued", hours=9)], [])
        gh = FakeGitHub({"/repos/ghostnet-labs/firmware/actions/runs/1/jobs": {
            "total_count": 1, "jobs": [{"status": "queued", "labels": ["self-hosted", "openwrt-build"]}]}})
        sr.apply_guards(items, gh, self.PROTECT, set(), set())
        self.assertEqual(items[0]["jobs"], 1)
        self.assertEqual(items[0]["waiting_labels"], ["self-hosted,openwrt-build"])

    def test_plain_dead_run_needs_no_job_call(self):
        items = self.items([run(1, prs=[5])], [])
        gh = FakeGitHub({})
        sr.apply_guards(items, gh, self.PROTECT, set(), set())
        self.assertTrue(items[0]["cancel"])
        self.assertEqual(gh.gets, [])


class TestScanAndMain(unittest.TestCase):
    def routes(self):
        base = "/repos/ghostnet-labs/firmware"
        return {
            f"{base}/pulls": [pr(5, "feat", "new")],
            f"{base}/actions/runs?status=queued": {"workflow_runs": []},
            f"{base}/actions/runs?status=in_progress": {"workflow_runs": [
                run(1, sha="old", prs=[5]), run(3, prs=[9], branch="merged")]},
            f"{base}/actions/runs?status=waiting": {"workflow_runs": []},
            f"{base}/actions/runs?head_sha=new": {"workflow_runs": [
                {"workflow_id": 1, "head_sha": "new"}]},
        }

    def test_scan_looks_up_head_runs_once_and_classifies(self):
        gh = FakeGitHub(self.routes())
        items = sr.scan(gh, ["firmware"], NOW, 3.0)
        got = {i["id"]: i["class"] for i in items}
        self.assertEqual(got, {1: "superseded", 3: "closed"})
        self.assertEqual(sum("head_sha=" in p for p in gh.gets), 1)
        self.assertEqual(len(gh.gets), 5)

    def run_main(self, gh, args):
        orig_gh, orig_tok, orig_now = sr.GitHub, sr.read_token, sr.utcnow
        sr.GitHub = lambda token: gh
        sr.read_token = lambda: "t"
        sr.utcnow = lambda: NOW
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = sr.main(args)
            return code, buf.getvalue()
        finally:
            sr.GitHub, sr.read_token, sr.utcnow = orig_gh, orig_tok, orig_now

    def test_dry_run_cancels_nothing(self):
        gh = FakeGitHub(self.routes())
        code, out = self.run_main(gh, ["--repos", "firmware"])
        self.assertEqual(code, 0)
        self.assertEqual(gh.cancelled, [])
        self.assertIn("superseded", out)

    def test_cancel_respects_max_cancel(self):
        gh = FakeGitHub(self.routes())
        code, out = self.run_main(gh, ["--repos", "firmware", "--cancel", "--max-cancel", "1", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(len(gh.cancelled), 1)
        actions = sorted(i.get("action", "") for i in json.loads(out)["runs"])
        self.assertEqual(actions, ["cancelled", "skipped (max-cancel reached)"])

    def test_launchd_plist_carries_args(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            sr.main(["launchd", "--cancel"])
        self.assertIn("<string>--cancel</string>", buf.getvalue())
        self.assertIn("<integer>900</integer>", buf.getvalue())


class TestEtagCache(unittest.TestCase):
    def test_304_returns_cached_data_and_is_not_counted(self):
        gh = sr.GitHub("t", etag_file=None)
        answers = [(200, {"ETag": '"e1"'}, b'{"n": 1}'), (304, {}, b"")]
        sent = []
        gh._request = lambda method, path, headers: (sent.append(headers), answers.pop(0))[1]
        self.assertEqual(gh.get("/x"), {"n": 1})
        self.assertEqual(gh.get("/x"), {"n": 1})
        self.assertEqual(sent[1].get("If-None-Match"), '"e1"')
        self.assertEqual((gh.calls, gh.not_modified), (1, 1))


if __name__ == "__main__":
    unittest.main()
