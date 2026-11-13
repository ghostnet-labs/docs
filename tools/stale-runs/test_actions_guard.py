"""Tests for actions_guard.py. Run: python3 -m unittest discover -s tools/stale-runs -v"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import actions_guard as ag  # noqa: E402

NOW = datetime(2026, 11, 3, 16, 0, tzinfo=timezone.utc)
GRACE = timedelta(minutes=20)
STALE = timedelta(hours=3)
BASE = "/repos/ghostnet-labs/luci"
SHA = "a" * 40


def ts(minutes_ago: float) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")


class FakeGitHub:
    def __init__(self, routes: dict):
        self.routes = routes

    def get(self, path: str):
        value = self.routes[path]
        if isinstance(value, Exception):
            raise value
        return value


def _runs(queued):
    """(age, jobs) or (age, jobs, event, head_sha); a PR run on the open PR's head by default."""
    return [tuple(q) + ("pull_request", SHA)[len(q) - 2:] for q in queued]


def routes(*, enabled=True, wf_state="active", draft=False, pr_age=120, checks=0, statuses=0,
           run_age=30, perms=None, queued=(), same_commit=()) -> dict:
    pull = {"number": 9, "draft": draft, "created_at": ts(pr_age), "updated_at": ts(pr_age),
            "head": {"sha": SHA}}
    return {
        f"{BASE}/actions/permissions": perms if perms is not None else {"enabled": enabled},
        f"{BASE}/actions/workflows?per_page=100": {"workflows": [{"name": "Manet merge gate", "state": wf_state}]},
        f"{BASE}/pulls?state=open&per_page=100": [pull],
        f"{BASE}/commits/{SHA}/check-runs?per_page=1": {"total_count": checks},
        f"{BASE}/commits/{SHA}/status": {"total_count": statuses},
        f"{BASE}/actions/runs?per_page=1": {"workflow_runs": [{"created_at": ts(run_age)}]},
        f"{BASE}/actions/runs?status=queued&per_page=50": {"workflow_runs": [
            {"id": i, "name": "PR Gate", "created_at": ts(age), "html_url": f"https://github.com/x/runs/{i}",
             "event": event, "head_sha": head}
            for i, (age, _, event, head) in enumerate(_runs(queued))]},
        **{f"{BASE}/actions/runs/{i}/jobs?per_page=1": {"total_count": jobs} for i, (_, jobs, *_rest) in enumerate(queued)},
        # Other runs on the same commit, as (name, age); none by default.
        **{f"{BASE}/actions/runs?head_sha={h}&per_page=20": {"workflow_runs": [
            {"id": 100 + j, "name": name, "created_at": ts(age)} for j, (name, age) in enumerate(same_commit)]}
           for h in (SHA, "b" * 40)},
    }


def kinds(r: dict) -> list[str]:
    return [f["kind"] for f in ag.check_repo(FakeGitHub(r), "luci", NOW, GRACE, STALE)]


def forbidden_checks(r: dict, runs: int) -> dict:
    """check-runs answers 403 (fine-grained token on a private repo); Actions runs stand in."""
    r[f"{BASE}/commits/{SHA}/check-runs?per_page=1"] = RuntimeError(
        "GET check-runs: HTTP 403: Resource not accessible by personal access token")
    r[f"{BASE}/actions/runs?head_sha={SHA}&per_page=1"] = {
        "total_count": runs, "workflow_runs": [{"id": 1, "name": "PR checks", "status": "completed",
                                                "conclusion": "success"}][:runs]}
    return r


class CheckRepoTest(unittest.TestCase):
    def test_healthy_repo_has_no_findings(self):
        self.assertEqual(kinds(routes(checks=2)), [])

    def test_check_runs_403_falls_back_to_actions_runs(self):
        self.assertEqual(kinds(forbidden_checks(routes(), runs=1)), [])

    def test_check_runs_403_with_no_runs_or_statuses_is_no_checks(self):
        self.assertEqual(kinds(forbidden_checks(routes(), runs=0)), ["pr-no-checks"])

    def test_check_runs_other_errors_propagate(self):
        r = routes()
        r[f"{BASE}/commits/{SHA}/check-runs?per_page=1"] = RuntimeError("GET x: HTTP 500: boom")
        with self.assertRaises(RuntimeError):
            kinds(r)

    def test_run_as_check_maps_states(self):
        done = ag.run_as_check({"id": 5, "name": "CI", "status": "completed", "conclusion": "failure",
                                "run_started_at": "s", "updated_at": "u"})
        self.assertEqual((done["status"], done["conclusion"], done["completed_at"]), ("completed", "failure", "u"))
        queued = ag.run_as_check({"id": 6, "name": "CI", "status": "queued", "created_at": "c"})
        self.assertEqual((queued["status"], queued["conclusion"], queued["started_at"]), ("in_progress", None, "c"))

    def test_actions_off(self):
        self.assertIn("actions-off", kinds(routes(enabled=False, checks=2)))

    def test_permissions_unreadable_is_skipped(self):
        r = routes(checks=2, perms=RuntimeError("GET x: HTTP 403: nope"))
        self.assertEqual(kinds(r), [])

    def test_other_api_errors_propagate(self):
        r = routes(checks=2, perms=RuntimeError("GET x: HTTP 500: boom"))
        with self.assertRaises(RuntimeError):
            kinds(r)

    def test_disabled_fork_workflow(self):
        self.assertEqual(kinds(routes(wf_state="disabled_fork", checks=2)), ["workflow-off"])

    def test_disabled_inactivity_workflow(self):
        self.assertEqual(kinds(routes(wf_state="disabled_inactivity", checks=2)), ["workflow-off"])

    def test_ready_pr_without_checks(self):
        self.assertEqual(kinds(routes(checks=0)), ["pr-no-checks"])

    def test_queued_run_without_jobs_is_held(self):
        r = routes(checks=2, queued=[(120, 0), (30, 0), (5, 0)])
        (f,) = ag.check_repo(FakeGitHub(r), "luci", NOW, GRACE, STALE)
        self.assertEqual(f["kind"], "runs-held")
        self.assertIn("2 queued run(s) have no jobs, oldest 120 min (PR Gate)", f["detail"])
        self.assertEqual(f["runs"], ["https://github.com/x/runs/0", "https://github.com/x/runs/1"])

    def test_held_run_on_an_old_pr_head_is_ignored(self):
        # Firmware #92: re-runs of an old head stayed held after the PR moved on.
        self.assertEqual(kinds(routes(checks=2, queued=[(240, 0, "pull_request", "b" * 40)])), [])
        # Held push or schedule runs, and current-head PR runs, still count.
        self.assertEqual(kinds(routes(checks=2, queued=[(240, 0, "push", "b" * 40)])), ["runs-held"])
        self.assertEqual(kinds(routes(checks=2, queued=[(240, 0, "pull_request", SHA)])), ["runs-held"])

    def test_held_run_replaced_by_a_newer_run_of_its_workflow_is_ignored(self):
        # packages #42: a frozen re-run stayed queued after a fresh dispatch built the same commit.
        self.assertEqual(kinds(routes(checks=2, queued=[(240, 0)], same_commit=[("PR Gate", 30)])), [])
        # An older run, or a different workflow, on the same commit doesn't replace it.
        self.assertEqual(kinds(routes(checks=2, queued=[(240, 0)], same_commit=[("PR Gate", 300)])), ["runs-held"])
        self.assertEqual(kinds(routes(checks=2, queued=[(240, 0)], same_commit=[("Docs", 30)])), ["runs-held"])

    def test_queued_run_waiting_for_a_runner_is_not_held(self):
        self.assertEqual(kinds(routes(checks=2, queued=[(120, 3)])), [])

    def test_young_queued_run_without_jobs_is_not_held(self):
        self.assertEqual(kinds(routes(checks=2, queued=[(10, 0)])), [])

    def test_pr_with_only_statuses_is_fine(self):
        self.assertEqual(kinds(routes(checks=0, statuses=1)), [])

    def test_young_pr_gets_grace(self):
        self.assertEqual(kinds(routes(pr_age=5, checks=0)), [])

    def test_draft_pr_is_ignored(self):
        self.assertEqual(kinds(routes(draft=True, checks=0)), [])

    def test_stale_runs_with_open_pr(self):
        self.assertEqual(kinds(routes(checks=2, run_age=4 * 60)), ["runs-stale"])

    def test_no_open_prs_means_no_stale_alert(self):
        r = routes(checks=2, run_age=24 * 60)
        r[f"{BASE}/pulls?state=open&per_page=100"] = []
        self.assertEqual(kinds(r), [])

    def test_repo_that_never_ran_with_open_pr(self):
        r = routes(checks=2)
        r[f"{BASE}/actions/runs?per_page=1"] = {"workflow_runs": []}
        self.assertEqual(kinds(r), ["runs-stale"])

    def test_the_luci_stall_is_caught_three_ways(self):
        r = routes(wf_state="disabled_fork", checks=0, run_age=4 * 24 * 60)
        self.assertEqual(sorted(kinds(r)), ["pr-no-checks", "runs-stale", "workflow-off"])


class RenderTest(unittest.TestCase):
    def test_ok_message(self):
        self.assertTrue(ag.render([], ["luci"]).startswith("OK"))

    def test_findings_listed(self):
        out = ag.render([{"repo": "luci", "kind": "workflow-off", "detail": "x"}], ["luci"])
        self.assertIn("luci", out)
        self.assertIn("workflow-off", out)


if __name__ == "__main__":
    unittest.main()
