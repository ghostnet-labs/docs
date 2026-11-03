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


def routes(*, enabled=True, wf_state="active", draft=False, pr_age=120, checks=0, statuses=0,
           run_age=30, perms=None) -> dict:
    pull = {"number": 9, "draft": draft, "created_at": ts(pr_age), "updated_at": ts(pr_age),
            "head": {"sha": SHA}}
    return {
        f"{BASE}/actions/permissions": perms if perms is not None else {"enabled": enabled},
        f"{BASE}/actions/workflows?per_page=100": {"workflows": [{"name": "Manet merge gate", "state": wf_state}]},
        f"{BASE}/pulls?state=open&per_page=100": [pull],
        f"{BASE}/commits/{SHA}/check-runs?per_page=1": {"total_count": checks},
        f"{BASE}/commits/{SHA}/status": {"total_count": statuses},
        f"{BASE}/actions/runs?per_page=1": {"workflow_runs": [{"created_at": ts(run_age)}]},
    }


def kinds(r: dict) -> list[str]:
    return [f["kind"] for f in ag.check_repo(FakeGitHub(r), "luci", NOW, GRACE, STALE)]


class CheckRepoTest(unittest.TestCase):
    def test_healthy_repo_has_no_findings(self):
        self.assertEqual(kinds(routes(checks=2)), [])

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
