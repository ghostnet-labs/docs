"""Tests for ci_watch.py. Run: python3 -m unittest discover -s tools/ci-watch -v"""

from __future__ import annotations

import argparse
import base64
import json
import os
import plistlib
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_watch as cw  # noqa: E402

NOW = datetime(2026, 11, 3, 17, 0, tzinfo=timezone.utc)
SHA = "b" * 40


def ts(minutes_ago: float) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")


class FakeGitHub:
    """Answers GET paths from a dict; a missing path is an HTTP 404 like the real client."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls = 0
        self.not_modified = 0

    def get(self, path: str):
        if path not in self.routes:
            raise RuntimeError(f"GET {path}: HTTP 404: not in fake")
        value = self.routes[path]
        if isinstance(value, Exception):
            raise value
        return value

    def save(self):
        pass


def check(name, status="completed", conclusion="success", run_id=1, started=30, completed=None):
    run = {"name": name, "status": status, "conclusion": conclusion, "id": run_id, "started_at": ts(started)}
    if completed is not None:
        run["completed_at"] = ts(completed)
    return run


def repo_routes(repo="luci", prs=None, checks=None, statuses=None, merge="clean", auto_merge=True,
                wf_state="active", run_age=10, details=None, queued=None) -> dict:
    base = f"/repos/ghostnet-labs/{repo}"
    prs = prs if prs is not None else [{
        "number": 9, "title": "Bump feeds", "draft": False, "created_at": ts(120), "updated_at": ts(60),
        "head": {"sha": SHA, "ref": "claude/x"}, "labels": [], "user": {"login": "stupidmonk37"},
        "html_url": f"https://github.com/ghostnet-labs/{repo}/pull/9", "body": "",
        "auto_merge": {"merge_method": "merge"} if auto_merge else None}]
    checks = checks if checks is not None else [check("Manet merge gate"), check("Test x86_64", run_id=2)]
    r = {
        f"{base}/actions/permissions": {"enabled": True},
        f"{base}/actions/workflows?per_page=100": {"workflows": [{"name": "Manet merge gate", "state": wf_state}]},
        f"{base}/pulls?state=open&per_page=100": prs,
        f"{base}/actions/runs?per_page=1": {"workflow_runs": [{"created_at": ts(run_age)}]},
        f"{base}/actions/runs?status=queued&per_page=50": {"workflow_runs": queued or []},
    }
    for pr in prs:
        sha = pr["head"]["sha"]
        r[f"{base}/pulls/{pr['number']}"] = {"mergeable_state": merge, "auto_merge": pr.get("auto_merge")}
        r[f"{base}/commits/{sha}/check-runs?per_page=1"] = {"total_count": len(checks)}
        r[f"{base}/commits/{sha}/check-runs?per_page=100"] = {"check_runs": checks}
        r[f"{base}/commits/{sha}/status"] = {"total_count": len(statuses or []), "statuses": statuses or []}
    r.update(details or {})
    return r


def args(**kw) -> argparse.Namespace:
    a = cw.parse_args([])
    a.repos = "luci"
    a.branch_hours = 0
    a.upstream_hours = 0
    a.self_update = False
    a.clone = []
    a.deploy_status = ""
    a.idle_restart_status = ""
    a.swap_warn_gb = 0
    a.swap_crit_gb = 0
    a.queue_check = False
    for k, v in kw.items():
        setattr(a, k, v)
    return a


class SummarizeChecksTest(unittest.TestCase):
    def test_newest_rerun_replaces_failure(self):
        s = cw.summarize_checks([check("gate", conclusion="failure", run_id=1), check("gate", run_id=2)], [], NOW)
        self.assertEqual(s["state"], "green")

    def test_failure_and_timeout_are_red(self):
        s = cw.summarize_checks([check("a", conclusion="failure"), check("b", conclusion="timed_out", run_id=2)],
                                [], NOW)
        self.assertEqual(s["state"], "red")
        self.assertEqual(s["red"], ["a", "b (timed_out)"])

    def test_cancelled_alone_is_its_own_state(self):
        s = cw.summarize_checks([check("gate"), check("Handle passing PRs", conclusion="cancelled", run_id=2)],
                                [], NOW)
        self.assertEqual((s["state"], s["cancelled"]), ("cancelled", ["Handle passing PRs"]))

    def test_skipped_and_neutral_are_green(self):
        s = cw.summarize_checks([check("a", conclusion="skipped"), check("b", conclusion="neutral", run_id=2)],
                                [], NOW)
        self.assertEqual(s["state"], "green")

    def test_running_reports_oldest_start(self):
        s = cw.summarize_checks([check("a", status="in_progress", conclusion=None, started=50),
                                 check("b", status="queued", conclusion=None, run_id=2, started=10)], [], NOW)
        self.assertEqual(s["state"], "running")
        self.assertEqual(s["running_minutes"], 50)

    def test_commit_status_failure_is_red(self):
        s = cw.summarize_checks([], [{"context": "buf", "state": "error"}], NOW)
        self.assertEqual((s["state"], s["red"]), ("red", ["buf"]))

    def test_nothing_is_none(self):
        self.assertEqual(cw.summarize_checks([], [], NOW)["state"], "none")


class PRStatusTest(unittest.TestCase):
    def row(self, **kw):
        base = {"draft": False, "labels": [], "mergeable_state": "clean", "auto_merge": True, "depends_on": [],
                "checks": {"state": "green", "red": [], "running": [], "running_minutes": 0}}
        base.update(kw)
        return cw.pr_status(base)[0]

    def test_categories(self):
        cases = [
            ({"draft": True}, "draft"),
            ({"labels": ["hold"]}, "held"),
            ({"checks": {"state": "red", "red": ["gate"], "running": [], "running_minutes": 0}}, "red"),
            ({"mergeable_state": "dirty"}, "conflict"),
            ({"mergeable_state": "behind"}, "behind"),
            ({"depends_on": ["https://github.com/ghostnet-labs/docs/pull/1"]}, "waiting"),
            ({"mergeable_state": "blocked"}, "blocked"),
            ({}, "green"),
            ({"checks": {"state": "none", "red": [], "running": [], "running_minutes": 0}}, "none"),
        ]
        for kw, want in cases:
            with self.subTest(kw=kw):
                self.assertEqual(self.row(**kw), want)

    def test_red_wins_over_conflict(self):
        red = {"state": "red", "red": ["gate"], "running": [], "running_minutes": 0}
        self.assertEqual(self.row(checks=red, mergeable_state="dirty"), "red")


class RunOnceTest(unittest.TestCase):
    def test_first_run_reports_problems_but_no_events(self):
        gh = FakeGitHub(repo_routes(checks=[check("Manet merge gate", conclusion="failure")]))
        _, report, batch = cw.run_once(gh, args(), NOW, {})
        self.assertEqual([n["level"] for n in batch["new"]], ["crit"])
        self.assertIn("ghostnet-labs/luci #9 is red: Manet merge gate", batch["new"][0]["text"])
        self.assertEqual(batch["events"], [])
        self.assertIn("| [ghostnet-labs/luci #9](https://github.com/ghostnet-labs/luci/pull/9)", report)

    def test_same_problem_alerts_once(self):
        gh = FakeGitHub(repo_routes(checks=[check("Manet merge gate", conclusion="failure")]))
        state, _, _ = cw.run_once(gh, args(), NOW, {})
        _, _, batch = cw.run_once(gh, args(), NOW + timedelta(minutes=10), state)
        self.assertEqual(batch["new"], [])
        self.assertEqual(batch["cleared"], [])

    def test_recovery_clears_and_announces(self):
        red = FakeGitHub(repo_routes(checks=[check("Manet merge gate", conclusion="failure")]))
        state, _, _ = cw.run_once(red, args(), NOW, {})
        green = FakeGitHub(repo_routes())
        _, _, batch = cw.run_once(green, args(), NOW + timedelta(minutes=10), state)
        self.assertEqual(len(batch["cleared"]), 1)
        self.assertEqual(len(batch["events"]), 1)
        self.assertIn("no longer red", batch["events"][0]["text"])

    def test_merged_pr_is_an_event(self):
        state, _, _ = cw.run_once(FakeGitHub(repo_routes()), args(), NOW, {})
        merged = {"merged_at": ts(1), "state": "closed"}
        gone = repo_routes(prs=[], details={"/repos/ghostnet-labs/luci/pulls/9": merged})
        _, _, batch = cw.run_once(FakeGitHub(gone), args(), NOW + timedelta(minutes=10), state)
        self.assertEqual([e["text"] for e in batch["events"]], ["ghostnet-labs/luci #9 merged: Bump feeds"])

    def test_new_pr_is_an_event_after_first_run(self):
        state, _, _ = cw.run_once(FakeGitHub(repo_routes(prs=[])), args(), NOW, {})
        _, _, batch = cw.run_once(FakeGitHub(repo_routes()), args(), NOW, state)
        self.assertEqual([e["text"] for e in batch["events"]], ["ghostnet-labs/luci #9 opened: Bump feeds"])

    def test_behind_with_auto_merge_warns(self):
        _, _, batch = cw.run_once(FakeGitHub(repo_routes(merge="behind")), args(), NOW, {})
        self.assertTrue(any("behind its base" in n["text"] for n in batch["new"]))

    def test_cancelled_sweep_warns_with_rerun_hint(self):
        cancelled = [check("Manet merge gate"), check("Handle passing PRs", conclusion="cancelled", run_id=2)]
        _, _, batch = cw.run_once(FakeGitHub(repo_routes(checks=cancelled)), args(), NOW, {})
        self.assertEqual([n["level"] for n in batch["new"]], ["warn"])
        self.assertIn("re-run the latest 'Handle passing PRs' run", batch["new"][0]["text"])

    def test_behind_without_auto_merge_is_report_only(self):
        _, report, batch = cw.run_once(FakeGitHub(repo_routes(merge="behind", auto_merge=False)), args(), NOW, {})
        self.assertEqual(batch["new"], [])
        self.assertIn("green, behind base", report)

    def test_red_head_reminds_after_six_hours_then_daily(self):
        def red(failed_min):
            return FakeGitHub(repo_routes(checks=[check("Build", conclusion="failure", started=failed_min + 20,
                                                        completed=failed_min)]))
        state, _, batch = cw.run_once(red(60), args(), NOW, {})
        self.assertEqual([n["key"].split(":")[0] for n in batch["new"]], ["red"])
        # 6 h after the failure with no new push: one reminder, naming the branch and auto-merge.
        state, _, batch = cw.run_once(red(6 * 60), args(), NOW, state)
        self.assertEqual(len(batch["new"]), 1)
        self.assertIn("ghostnet-labs/luci #9 still red after 6.0h with no new push", batch["new"][0]["text"])
        self.assertIn("auto-merge on", batch["new"][0]["text"])
        self.assertIn("branch claude/x", batch["new"][0]["text"])
        self.assertEqual(batch["new"][0]["level"], "crit")
        # Same day: nothing new.
        state, _, batch = cw.run_once(red(12 * 60), args(), NOW, state)
        self.assertEqual((batch["new"], batch["cleared"]), ([], []))
        # A day later: another reminder, and the old one does not read as "cleared".
        state, _, batch = cw.run_once(red(30 * 60), args(), NOW, state)
        self.assertEqual(len(batch["new"]), 1)
        self.assertIn("still red after 30.0h", batch["new"][0]["text"])
        self.assertEqual(batch["cleared"], [])
        # Fixed: the red alert clears once; the reminder clears quietly.
        _, _, batch = cw.run_once(FakeGitHub(repo_routes()), args(), NOW, state)
        self.assertEqual([c["key"].split(":")[0] for c in batch["cleared"]], ["red"])

    def test_red_reminder_off_with_zero(self):
        gh = FakeGitHub(repo_routes(checks=[check("Build", conclusion="failure", completed=48 * 60)]))
        _, _, batch = cw.run_once(gh, args(red_remind_hours=0), NOW, {})
        self.assertFalse(any(n["key"].startswith("red-stale:") for n in batch["new"]))

    def test_red_minutes_from_commit_status(self):
        s = cw.summarize_checks([], [{"context": "buf", "state": "failure", "updated_at": ts(90)}], NOW)
        self.assertEqual(s["red_minutes"], 90)

    def test_stuck_checks_warn(self):
        slow = [check("Build", status="in_progress", conclusion=None, started=200)]
        _, _, batch = cw.run_once(FakeGitHub(repo_routes(checks=slow)), args(), NOW, {})
        self.assertTrue(any("checks running" in n["text"] for n in batch["new"]))

    def test_disabled_workflow_is_crit(self):
        _, _, batch = cw.run_once(FakeGitHub(repo_routes(wf_state="disabled_fork")), args(), NOW, {})
        self.assertTrue(any(n["level"] == "crit" and "workflow-off" in n["text"] for n in batch["new"]))

    def test_runs_stale_key_is_stable_as_hours_grow(self):
        a = cw.guard_findings(FakeGitHub(repo_routes(run_age=200)), "luci", NOW)
        b = cw.guard_findings(FakeGitHub(repo_routes(run_age=260)), "luci", NOW)
        self.assertEqual(set(a), set(b))

    def test_unreadable_repo_keeps_findings_and_alerts_after_three_runs(self):
        state, _, _ = cw.run_once(FakeGitHub(repo_routes(wf_state="disabled_fork")), args(), NOW, {})
        broken = FakeGitHub({})
        for i in range(1, 4):
            state, report, batch = cw.run_once(broken, args(), NOW + timedelta(minutes=10 * i), state)
            self.assertEqual(batch["cleared"], [], "a read failure must not look like a fix")
        self.assertEqual(state["error_runs"], 3)
        self.assertTrue(any(n["key"] == "watch:api-error" for n in batch["new"]))
        self.assertIn("Could not read: luci", report)
        self.assertIn("luci#9", state["prs"])  # PR kept for the next run's merge check

    def test_runner_page_alerts_are_forwarded(self):
        page = {"alerts": [{"level": "crit", "text": "studio-build-1 offline 25 min"},
                           {"level": "info", "text": "slot draining"}]}
        a = args(runner_page="http://studio.local:8090")
        _, _, batch = cw.run_once(FakeGitHub(repo_routes()), a, NOW, {}, runner_fetch=lambda u: page)
        self.assertEqual([n["text"] for n in batch["new"]], ["runner: studio-build-1 offline 25 min"])

    def test_runner_alert_key_ignores_changing_minutes(self):
        one = cw.runner_findings("p", lambda u: {"alerts": [{"level": "warn", "text": "job queued 21 min"}]})
        two = cw.runner_findings("p", lambda u: {"alerts": [{"level": "warn", "text": "job queued 31 min"}]})
        self.assertEqual(set(one), set(two))

    def test_runner_page_down_warns(self):
        def boom(url):
            raise OSError("connection refused")
        found = cw.runner_findings("http://studio.local:8090", boom)
        self.assertEqual(list(found), ["runner-page:down"])


class BranchesTest(unittest.TestCase):
    def test_lists_only_merged_branches_without_open_pr(self):
        base = "/repos/ghostnet-labs/docs"
        gh = FakeGitHub({
            base: {"default_branch": "main"},
            f"{base}/branches?per_page=100": [{"name": "main"}, {"name": "old"}, {"name": "live"},
                                              {"name": "pr-branch"}],
            f"{base}/compare/main...old": {"ahead_by": 0},
            f"{base}/compare/main...live": {"ahead_by": 3},
        })
        out = cw.merged_branches(gh, "docs", {"pr-branch"})
        self.assertEqual([b["branch"] for b in out], ["old"])

    def test_scan_runs_on_interval(self):
        r = repo_routes()
        r["/repos/ghostnet-labs/luci"] = {"default_branch": "mm-23.05"}
        r["/repos/ghostnet-labs/luci/branches?per_page=100"] = [{"name": "mm-23.05"}, {"name": "done"}]
        r["/repos/ghostnet-labs/luci/compare/mm-23.05...done"] = {"ahead_by": 0}
        state, report, _ = cw.run_once(FakeGitHub(r), args(branch_hours=1), NOW, {})
        self.assertEqual([b["branch"] for b in state["branches"]], ["done"])
        self.assertIn("ghostnet-labs/luci done", report)
        r["/repos/ghostnet-labs/luci/compare/mm-23.05...done"] = RuntimeError("must not be called")
        state, _, _ = cw.run_once(FakeGitHub(r), args(branch_hours=1), NOW + timedelta(minutes=10), state)
        self.assertEqual([b["branch"] for b in state["branches"]], ["done"])


class DeliverTest(unittest.TestCase):
    def batch(self):
        return {"new": [{"level": "crit", "text": "ghostnet-labs/luci #9 is red: gate",
                         "url": "https://github.com/ghostnet-labs/luci/pull/9", "key": "red"}],
                "cleared": [], "events": [{"level": "info", "text": "ghostnet-labs/docs #1 merged: x",
                                           "url": "https://github.com/ghostnet-labs/docs/pull/1"}]}

    def test_ntfy_request(self):
        sent = []

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def opener(req, timeout):
            sent.append(req)
            return Resp()

        cw.notify_ntfy("https://ntfy.sh", "manet-ci", "CI watch", "line one\nline two", "crit",
                       "https://x", opener=opener)
        req = sent[0]
        self.assertEqual(req.full_url, "https://ntfy.sh/manet-ci")
        self.assertEqual(req.get_header("Priority"), "high")
        self.assertEqual(req.get_header("Click"), "https://x")
        self.assertEqual(req.data, b"line one\nline two")

    def test_min_level_filters_banners_and_push(self):
        a = args(notify=False, ntfy="t", min_level="warn")
        with mock.patch.object(cw, "notify_ntfy") as push:
            cw.deliver(a, self.batch(), "r", False, None)
        text = push.call_args.args[3]
        self.assertIn("is red", text)
        self.assertNotIn("merged", text)

    def test_issue_gets_body_and_linked_comment(self):
        issue = mock.Mock()
        cw.deliver(args(), self.batch(), "report", True, issue)
        issue.update_body.assert_called_once_with("report")
        issue.comment.assert_called_once()

    def test_channel_failure_is_reported_not_raised(self):
        with mock.patch.object(cw, "notify_ntfy", side_effect=OSError("dns")):
            failures = cw.deliver(args(ntfy="t"), self.batch(), "r", False, None)
        self.assertEqual(failures, ["ntfy: dns"])

    def test_nothing_new_sends_nothing(self):
        issue = mock.Mock()
        with mock.patch.object(cw, "notify_ntfy") as push:
            cw.deliver(args(ntfy="t"), {"new": [], "cleared": [], "events": []}, "r", False, issue)
        push.assert_not_called()
        issue.comment.assert_not_called()

    def test_issue_comment_links_each_line(self):
        sent = []
        sink = cw.IssueSink("tok", 140, opener=lambda req, timeout: sent.append(req) or mock.MagicMock())
        b = self.batch()
        sink.comment(cw.alert_text(b["new"], [], b["events"]), b["new"] + b["events"])
        body = json.loads(sent[0].data)["body"]
        self.assertIn("- [ghostnet-labs/luci #9 is red: gate](https://github.com/ghostnet-labs/luci/pull/9)", body)
        self.assertTrue(sent[0].full_url.endswith("/repos/ghostnet-labs/setup/issues/140/comments"))

    def test_macos_banner_only_on_darwin(self):
        run = mock.Mock()
        with mock.patch.object(cw.platform, "system", return_value="Linux"):
            cw.notify_macos("t", "x", run=run)
        run.assert_not_called()
        with mock.patch.object(cw.platform, "system", return_value="Darwin"):
            cw.notify_macos("t", "a\nb\nc", run=run)
        self.assertIn("(+2 more)", run.call_args.args[0][2])


class FixOnceTest(unittest.TestCase):
    """Checks added so a problem met once is caught by the script next time."""

    def test_disabled_fork_links_the_actions_tab(self):
        url, how = cw.enable_link("luci", "disabled_fork", ".github/workflows/gate.yml")
        self.assertEqual(url, "https://github.com/ghostnet-labs/luci/actions")
        self.assertIn("go ahead and enable them", how)

    def test_inactive_workflow_links_its_own_page(self):
        url, how = cw.enable_link("luci", "disabled_inactivity", ".github/workflows/gate.yml")
        self.assertEqual(url, "https://github.com/ghostnet-labs/luci/actions/workflows/gate.yml")
        self.assertIn("Enable workflow", how)

    def test_disabled_workflow_alert_carries_the_link(self):
        r = repo_routes(wf_state="disabled_inactivity")
        r["/repos/ghostnet-labs/luci/actions/workflows?per_page=100"] = {"workflows": [
            {"name": "Manet merge gate", "state": "disabled_inactivity", "path": ".github/workflows/gate.yml"}]}
        found = cw.guard_findings(FakeGitHub(r), "luci", NOW)
        item = next(v for k, v in found.items() if "workflow-off" in k)
        self.assertEqual(item["url"], "https://github.com/ghostnet-labs/luci/actions/workflows/gate.yml")

    def test_held_runs_alert_is_crit_with_actions_link_and_stable_key(self):
        def held(age):
            r = repo_routes(queued=[{"id": 77, "name": "PR Gate", "created_at": ts(age),
                                     "html_url": "https://github.com/ghostnet-labs/luci/actions/runs/77"}])
            r["/repos/ghostnet-labs/luci/actions/runs/77/jobs?per_page=1"] = {"total_count": 0}
            return cw.guard_findings(FakeGitHub(r), "luci", NOW)
        a, b = held(40), held(130)
        (key, item), = [(k, v) for k, v in a.items() if "runs-held" in k]
        self.assertEqual(item["level"], "crit")
        self.assertEqual(item["url"], "https://github.com/ghostnet-labs/luci/actions")
        self.assertIn("enable button", item["text"])
        self.assertIn("/actions/runs/77", item["text"])
        self.assertIn(key, b, "the key must not change as the run ages, or it re-alerts every cycle")

    def page(self, *runners):
        return {"alerts": [{"level": "crit", "text": "Offline runners: " + ", ".join(r["name"] for r in runners)}],
                "jobs": [], "machines": [{"name": "Mac Studio", "runners": list(runners)}]}

    def test_retired_runners_are_one_info_line(self):
        runners = [{"name": f"studio-ubuntu-{i}", "id": 2990 + i, "status": "offline", "offline_min": 900}
                   for i in range(1, 6)]
        found = cw.runner_findings("p", lambda u: self.page(*runners))
        self.assertEqual(set(found), {"runner:retired"})
        self.assertEqual(found["runner:retired"]["level"], "info")
        self.assertIn("5 retired runner registration(s)", found["runner:retired"]["text"])

    def test_live_offline_runner_stays_crit_beside_retired_ones(self):
        found = cw.runner_findings("p", lambda u: self.page(
            {"name": "studio-ubuntu-1", "status": "offline", "offline_min": 900},
            {"name": "studio-build-1", "status": "offline", "offline_min": 45}))
        self.assertEqual(found["runner:offline"]["level"], "crit")
        self.assertIn("studio-build-1", found["runner:offline"]["text"])
        self.assertNotIn("studio-ubuntu-1", found["runner:offline"]["text"])
        self.assertNotIn("stale-runner:studio-ubuntu-1", found)

    def test_extra_retired_pattern_from_flag(self):
        found = cw.runner_findings("p", lambda u: self.page(
            {"name": "old-mac-1", "status": "offline", "offline_min": 900}), retired=[r"^old-mac-"])
        self.assertEqual(set(found), {"runner:retired"})

    def test_queued_label_only_on_retired_runners_says_so(self):
        found = cw.starved_labels(self.starved_state(
            {"name": "studio-ubuntu-2", "status": "offline", "labels": ["openwrt-build"]}),
            retired=[cw.re.compile(r"^studio-ubuntu-")])
        self.assertIn("only retired runners", found["starved:openwrt-build"]["text"])

    def starved_state(self, *runners, age=30):
        job = {"status": "queued", "hosted": False, "age_min": age, "labels": ["self-hosted", "openwrt-build"],
               "url": "https://github.com/ghostnet-labs/firmware/actions/runs/1/job/2"}
        return {"alerts": [], "jobs": [job], "machines": [{"name": "Mac Studio", "runners": list(runners)}]}

    def test_queued_label_with_only_offline_runners_alerts(self):
        found = cw.starved_labels(self.starved_state(
            {"name": "studio-build-1", "status": "offline", "labels": ["self-hosted", "openwrt-build"]}))
        item = found["starved:openwrt-build"]
        self.assertEqual(item["level"], "crit")
        self.assertIn("studio-build-1", item["text"])
        self.assertIn("/actions/runs/1/job/2", item["text"])
        self.assertIn("settings/actions/runners", item["text"])

    def test_queued_label_with_no_runner_registered_alerts(self):
        found = cw.starved_labels(self.starved_state())
        self.assertIn("no runner with these labels is registered", found["starved:openwrt-build"]["text"])

    def test_busy_online_runner_is_not_starved(self):
        found = cw.starved_labels(self.starved_state(
            {"name": "studio-build-1", "status": "busy", "labels": ["self-hosted", "OpenWrt-Build"]}))
        self.assertEqual(found, {})

    def idle_runner_state(self, status="idle", age=20, n=1):
        jobs = [{"status": "queued", "hosted": False, "age_min": age, "labels": ["self-hosted", "openwrt-build"],
                 "url": f"https://github.com/ghostnet-labs/firmware/actions/runs/86/job/{i}"} for i in range(n)]
        runner = {"name": "studio-build-1", "status": status, "labels": ["self-hosted", "macOS", "openwrt-build"]}
        return {"jobs": jobs, "machines": [{"name": "GitHub", "runners": [runner]}]}

    def test_idle_runner_with_queued_job_alerts_on_second_run(self):
        state = self.idle_runner_state(n=5)
        found, track = cw.idle_runners(state, {}, NOW)
        self.assertEqual(found, {}, "first sighting may be the moment between two jobs")
        found, track = cw.idle_runners(state, track, NOW + timedelta(minutes=10))
        item = found["idle-runner:studio-build-1"]
        self.assertEqual(item["level"], "crit")
        self.assertIn("online but idle for 10m+", item["text"])
        self.assertIn("5 job(s) for label openwrt-build", item["text"])
        self.assertIn("/runs/86/job/2", item["text"])
        self.assertNotIn("/runs/86/job/3", item["text"])
        self.assertIn("(+2 more)", item["text"])

    def test_busy_runner_or_young_queue_is_not_idle_alert(self):
        found, _ = cw.idle_runners(self.idle_runner_state(status="busy"), {"idle_since": {}}, NOW)
        self.assertEqual(found, {})
        track = {"idle_since": {"studio-build-1": (NOW - timedelta(minutes=30)).isoformat()}}
        found, _ = cw.idle_runners(self.idle_runner_state(age=5), track, NOW)
        self.assertNotIn("idle-runner:studio-build-1", found)

    def test_idle_gap_closes_into_24h_summary(self):
        track = {"idle_since": {"studio-build-1": (NOW - timedelta(minutes=185)).isoformat()}}
        found, track = cw.idle_runners(self.idle_runner_state(status="busy"), track, NOW)
        self.assertEqual(track["idle_since"], {})
        self.assertEqual(track["gaps"][0]["min"], 185)
        self.assertEqual(found["idle-runner:gaps"]["level"], "info")
        self.assertIn("longest 185 min on studio-build-1", found["idle-runner:gaps"]["text"])
        found, track = cw.idle_runners(self.idle_runner_state(status="busy"), track, NOW + timedelta(hours=25))
        self.assertEqual(found, {})
        self.assertEqual(track["gaps"], [])

    def queue_routes(self, runners):
        base = "/repos/ghostnet-labs/firmware/actions/runs"
        job = {"status": "queued", "labels": ["self-hosted", "openwrt-build"], "name": "build (bpi-r4)",
               "created_at": ts(40), "html_url": "https://github.com/ghostnet-labs/firmware/actions/runs/86/job/1"}
        routes = {f"{base}?status=queued&per_page=50": {"workflow_runs": []},
                  f"{base}?status=in_progress&per_page=50": {"workflow_runs": [{"id": 86}]},
                  f"{base}/86/jobs?per_page=100": {"jobs": [job, dict(job, status="completed")]}}
        routes["/orgs/ghostnet-labs/actions/runners?per_page=100"] = runners
        return routes

    def test_queue_state_reads_runners_and_jobs_from_github(self):
        runners = {"runners": [{"name": "studio-build-1", "id": 7, "status": "online", "busy": False,
                                "labels": [{"name": "self-hosted"}, {"name": "openwrt-build"}]}]}
        state = cw.queue_state(FakeGitHub(self.queue_routes(runners)), ["firmware"], NOW)
        (runner,) = state["machines"][0]["runners"]
        self.assertEqual((runner["name"], runner["status"]), ("studio-build-1", "idle"))
        (job,) = state["jobs"]
        self.assertEqual(job["status"], "queued")
        self.assertFalse(job["hosted"])
        self.assertAlmostEqual(job["age_min"], 40, delta=1)

    def test_unreadable_runner_list_falls_back_to_stall_check(self):
        routes = self.queue_routes(RuntimeError("GET runners: HTTP 403"))
        state = cw.queue_state(FakeGitHub(routes), ["firmware"], NOW)
        self.assertIn("403", state["runners_error"])
        found = cw.stalled_labels(state)
        self.assertIn("nothing with that label is running", found["stalled:openwrt-build"]["text"])
        state["jobs"].append({"status": "in_progress", "labels": ["self-hosted", "openwrt-build"]})
        self.assertEqual(cw.stalled_labels(state), {})

    def test_run_once_tracks_idle_runner_between_runs(self):
        runners = {"runners": [{"name": "studio-build-1", "id": 7, "status": "online", "busy": False,
                                "labels": [{"name": "self-hosted"}, {"name": "openwrt-build"}]}]}
        routes = dict(repo_routes(), **self.queue_routes(runners))
        for path in list(routes):
            routes[path.replace("/firmware/", "/luci/")] = routes[path]
        state, _, _ = cw.run_once(FakeGitHub(routes), args(queue_check=True), NOW, {})
        self.assertIn("studio-build-1", state["idle_runners"]["idle_since"])
        state, _, batch = cw.run_once(FakeGitHub(routes), args(queue_check=True), NOW + timedelta(minutes=10), state)
        self.assertIn("idle-runner:studio-build-1", [i["key"] for i in batch["new"]])

    def test_young_or_hosted_queue_is_not_starved(self):
        self.assertEqual(cw.starved_labels(self.starved_state(age=5)), {})
        state = self.starved_state()
        state["jobs"][0]["hosted"] = True
        self.assertEqual(cw.starved_labels(state), {})

    TOP = ("Processes: 600 total\n\nCOMMAND          MEM\ncom.apple.Virtua 11G+\n"
           "com.apple.Virtua 8900M\nDocker Desktop   2100M\nSafari           900M\n")

    def mem(self, swap="total = 2048.00M  used = 512.00M  free = 1536.00M  (encrypted)", level="1", idle="",
            previous=None, warn=4.0, crit=8.0):
        out = {"vm.swapusage": swap, "kern.memorystatus_vm_pressure_level": level}

        def run(*cmd):
            if cmd[0] == "sysctl":
                return out[cmd[-1]]
            return self.TOP
        return cw.host_memory(previous, warn, crit, idle, run=run)

    def test_low_swap_normal_pressure_is_quiet(self):
        self.assertEqual(self.mem(), {})

    def test_swap_over_4_gib_warns_naming_biggest_processes_and_causes(self):
        found = self.mem(swap="total = 6144.00M  used = 4608.00M  free = 1536.00M")
        item = found["host:memory:warn"]
        self.assertIn("4.5 GiB of 6.0 GiB swap in use", item["text"])
        self.assertIn("Biggest: VM 11G+, VM 8900M, Docker Desktop 2100M, Safari 900M", item["text"])
        self.assertIn("ci-k3s idle restart", item["text"])
        self.assertIn("Docker Desktop and idle apps", item["text"])
        self.assertTrue(item["url"].endswith("#host-memory"))

    def test_swap_over_8_gib_or_critical_pressure_is_crit(self):
        self.assertIn("host:memory:crit", self.mem(swap="total = 10240.00M  used = 9216.00M  free = 1024.00M"))
        self.assertIn("host:memory:crit", self.mem(level="4"))

    def test_pressure_warn_level_warns(self):
        self.assertIn("pressure warn", self.mem(level="2")["host:memory:warn"]["text"])

    def test_nearly_full_swap_file_is_crit_only_when_large(self):
        self.assertIn("host:memory:crit", self.mem(swap="total = 3072.00M  used = 2900.00M  free = 172.00M"))
        self.assertEqual(self.mem(swap="total = 1024.00M  used = 1000.00M  free = 24.00M"), {})

    def test_active_warn_holds_until_swap_is_under_3_gib(self):
        swap35 = "total = 5120.00M  used = 3584.00M  free = 1536.00M"
        self.assertEqual(self.mem(swap=swap35), {})
        active = {"host:memory:warn": {}}
        self.assertIn("host:memory:warn", self.mem(swap=swap35, previous=active))
        self.assertEqual(self.mem(swap="total = 5120.00M  used = 3000.00M  free = 2120.00M", previous=active), {})

    def test_active_crit_holds_until_swap_is_under_6_gib_then_warns(self):
        active = {"host:memory:crit": {}}
        self.assertIn("host:memory:crit", self.mem(swap="total = 8192.00M  used = 6400.00M", previous=active))
        self.assertIn("host:memory:warn", self.mem(swap="total = 8192.00M  used = 3584.00M", previous=active))

    def test_swap_thresholds_zero_turn_off_check_or_crit(self):
        big = "total = 10240.00M  used = 9216.00M  free = 1024.00M"
        self.assertEqual(self.mem(swap=big, level="4", warn=0), {})
        self.assertIn("host:memory:warn", self.mem(swap=big, crit=0))

    def test_memory_alert_quotes_idle_restart_status(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "status.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"ok": True, "action": "wait", "reason": "jobs running"}, f)
            found = self.mem(level="2", idle=path)
        self.assertIn("Idle restart last said wait (jobs running)", found["host:memory:warn"]["text"])

    def test_swap_flags_parse(self):
        a = cw.parse_args(["--swap-warn-gb", "0", "--swap-crit-gb", "6"])
        self.assertEqual((a.swap_warn_gb, a.swap_crit_gb), (0.0, 6.0))
        self.assertEqual(cw.parse_args([]).swap_warn_gb, 4.0)

    def idle(self, status, loaded=True):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "status.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(status, f)
            return cw.idle_restart_status(path, NOW, loaded=loaded)

    def test_idle_restart_not_loaded_is_one_info_line(self):
        found = self.idle({"ok": True, "action": "skip", "at": NOW.isoformat()}, loaded=False)
        self.assertEqual(found["idle-restart:agent"]["level"], "info")
        self.assertIn("not loaded", found["idle-restart:agent"]["text"])

    def test_idle_restart_healthy_skip_is_quiet(self):
        self.assertEqual(self.idle({"ok": True, "action": "skip", "reason": "busy", "at": NOW.isoformat()}), {})

    def test_idle_restart_error_is_crit(self):
        found = self.idle({"ok": False, "action": "error", "reason": "kubectl failed", "at": NOW.isoformat()})
        self.assertEqual(found["idle-restart"]["level"], "crit")
        self.assertIn("kubectl failed", found["idle-restart"]["text"])

    def test_idle_restart_stale_file_is_crit(self):
        found = self.idle({"ok": True, "action": "wait", "at": (NOW - timedelta(hours=3)).isoformat()})
        self.assertIn("last ran", found["idle-restart"]["text"])

    def test_idle_restart_restart_is_info_once_per_run(self):
        found = self.idle({"ok": True, "action": "restarted", "reason": "idle 6 h", "at": NOW.isoformat()})
        (key, item), = found.items()
        self.assertEqual(item["level"], "info")
        self.assertIn("idle 6 h", item["text"])
        self.assertIn(NOW.isoformat(), key)

    def test_idle_restart_missing_file_when_loaded_is_crit(self):
        found = cw.idle_restart_status("/nonexistent/status.json", NOW, loaded=True)
        self.assertEqual(found["idle-restart"]["level"], "crit")

    def deploy_status(self, status, head="abc1234def"):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "deploy-status.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(status, f)
            return cw.deploy_status(path, "/clone", NOW, git=lambda *a: (0, head))

    def test_healthy_autodeploy_is_quiet(self):
        found = self.deploy_status({"ok": True, "commit": "abc1234def", "at": NOW.isoformat()})
        self.assertEqual(found, {})

    def test_autodeploy_failure_alerts_with_reason(self):
        found = self.deploy_status({"ok": False, "commit": "abc1234def", "reason": "local edits",
                                    "at": NOW.isoformat()})
        self.assertIn("local edits", found["deploy-status"]["text"])
        self.assertIn("tools/runner-status", found["deploy-status"]["url"])

    def test_autodeploy_saying_ok_on_an_old_commit_alerts(self):
        found = self.deploy_status({"ok": True, "commit": "0000000aaa", "at": NOW.isoformat()})
        self.assertIn("clone is at abc1234", found["deploy-status"]["text"])

    def test_autodeploy_that_stopped_writing_alerts(self):
        found = self.deploy_status({"ok": True, "commit": "abc1234def",
                                    "at": (NOW - timedelta(hours=2)).isoformat()})
        self.assertIn("last ran", found["deploy-status"]["text"])

    def test_missing_deploy_status_file_is_quiet(self):
        self.assertEqual(cw.deploy_status("/nonexistent/deploy-status.json", "/clone", NOW), {})

    def test_unreadable_deploy_status_alerts(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "deploy-status.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{not json")
            found = cw.deploy_status(path, "/clone", NOW, git=lambda *a: (0, "x"))
        self.assertIn("cannot read", found["deploy-status"]["text"])

    def state(self, *runners):
        return {"alerts": [], "machines": [{"name": "Mac Studio", "runners": list(runners)}]}

    def test_long_offline_runner_is_a_stale_registration(self):
        found = cw.stale_registrations(self.state(
            {"name": "studio-ubuntu-3", "id": 42, "status": "offline", "offline_min": 13 * 60}), 12)
        item = found["stale-runner:studio-ubuntu-3"]
        self.assertEqual(item["url"], "https://github.com/organizations/ghostnet-labs/settings/actions/runners/42")

    def test_runner_with_no_service_is_stale_after_an_hour(self):
        found = cw.stale_registrations(self.state(
            {"name": "gone", "status": "offline", "offline_min": 61, "why": {"cause": "no-service"}}), 12)
        self.assertIn("stale-runner:gone", found)

    def test_short_outage_and_maintenance_are_not_stale(self):
        found = cw.stale_registrations(self.state(
            {"name": "a", "status": "offline", "offline_min": 30},
            {"name": "b", "status": "offline", "offline_min": 2000, "why": {"cause": "maintenance"}},
            {"name": "c", "status": "idle"}), 12)
        self.assertEqual(found, {})

    def drift_gh(self, files):
        return FakeGitHub({
            "/repos/ghostnet-labs/docs/commits/main": {"sha": "new"},
            "/repos/ghostnet-labs/docs/compare/old...new": {
                "ahead_by": 3, "html_url": "https://github.com/ghostnet-labs/docs/compare/old...new",
                "files": [{"filename": f} for f in files]}})

    def test_deploy_drift_alerts_after_the_grace_hour(self):
        git = lambda path, *a: (0, "old")  # noqa: E731
        gh = self.drift_gh(["tools/runner-status/runner_status.py"])
        found, seen = cw.deploy_drift(gh, ["/x/runner-status-src"], NOW, {}, git=git)
        self.assertEqual(found, {})  # first sighting starts the clock
        later = NOW + timedelta(minutes=61)
        found, _ = cw.deploy_drift(gh, ["/x/runner-status-src"], later, seen, git=git)
        item = found["deploy:/x/runner-status-src"]
        self.assertIn("tools/runner-status", item["text"])
        self.assertEqual(item["url"], "https://github.com/ghostnet-labs/docs/compare/old...new")

    def test_deploy_drift_ignores_non_tool_changes_and_current_clones(self):
        gh = self.drift_gh(["project/decisions.md"])
        found, seen = cw.deploy_drift(gh, ["/x"], NOW, {}, git=lambda p, *a: (0, "old"))
        self.assertEqual((found, seen), ({}, {}))
        found, _ = cw.deploy_drift(gh, ["/x"], NOW, {}, git=lambda p, *a: (0, "new"))
        self.assertEqual(found, {})

    def test_unreadable_clone_warns(self):
        gh = self.drift_gh([])
        found, _ = cw.deploy_drift(gh, ["/x"], NOW, {}, git=lambda p, *a: (128, "not a git repository"))
        self.assertIn("deploy:/x:git", found)

    def test_self_update_pulls_a_clean_clone_hourly(self):
        calls = []

        def git(path, *a):
            calls.append(a)
            return 0, ""
        found, st = cw.update_self(NOW, {}, git=git, root="/r")
        self.assertEqual(found, {})
        self.assertEqual(calls, [("status", "--porcelain", "--untracked-files=no"), ("pull", "--ff-only", "--quiet")])
        calls.clear()
        cw.update_self(NOW + timedelta(minutes=10), st, git=git, root="/r")
        self.assertEqual(calls, [])  # not again within the hour

    def test_self_update_never_touches_local_edits(self):
        calls = []

        def git(path, *a):
            calls.append(a)
            return 0, " M tools/ci-watch/ci_watch.py"
        found, _ = cw.update_self(NOW, {}, git=git, root="/r")
        self.assertIn("local edits", found["self-update"]["text"])
        self.assertEqual(len(calls), 1)

    def test_self_update_failure_alerts(self):
        def git(path, *a):
            return (0, "") if a[0] == "status" else (1, "fatal: Not possible to fast-forward")
        found, _ = cw.update_self(NOW, {}, git=git, root="/r")
        self.assertIn("git pull failed", found["self-update"]["text"])


class MainTest(unittest.TestCase):
    def test_launchd_plist_is_valid(self):
        out = []
        with mock.patch("builtins.print", side_effect=lambda s, end="\n": out.append(s)):
            cw.main(["launchd", "--notify", "--ntfy", "topic"])
        plist = plistlib.loads(out[0].encode())
        self.assertEqual(plist["Label"], "com.ghostnet.ci-watch")
        self.assertEqual(plist["StartInterval"], 600)
        self.assertEqual(plist["ProgramArguments"][-3:], ["--notify", "--ntfy", "topic"])

    def test_report_without_state(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(cw.main(["report", "--state-dir", d]), 2)

    def test_full_run_writes_state_and_report(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(cw, "read_token", return_value="tok"), \
                mock.patch.object(cw.sr, "GitHub", return_value=FakeGitHub(repo_routes())), \
                mock.patch.object(cw.sr, "utcnow", return_value=NOW), \
                mock.patch("builtins.print"):
            code = cw.main(["--repos", "luci", "--branch-hours", "0", "--state-dir", d, "--no-self-update",
                            "--deploy-status", "", "--idle-restart-status", "",
                            "--swap-warn-gb", "0", "--no-queue-check"])
            self.assertEqual(code, 0)
            self.assertIn("green, auto-merge on", Path(d, "report.md").read_text())
            self.assertTrue(json.loads(Path(d, "state.json").read_text())["initialized"])


FEEDS = """src-git openmanet https://github.com/ghostnet-labs/packages.git^6b4cf56f1e2e92495ff6288e8af6e306d4edb7c9
src-git morse https://github.com/MorseMicro/morse-feed.git^fc332b01aa2df952e057efe73763de3ff71cb3b0
src-git packages https://github.com/openwrt/packages.git^953b6d47b4e9f0ad3c39547c6d3f9a828f10e206
src-git luci https://github.com/OpenMANET/luci.git^53e65158f7075109d140f8943b4a1f0eb6d84339
"""
OWRT = "34fa4b1af5a30d3a789f07078b91e23e78dad622"


def b64(text: str) -> dict:
    return {"content": base64.b64encode(text.encode()).decode()}


def fork_cmp(repo: str, branch: str, behind: int) -> dict:
    return {f"/repos/ghostnet-labs/{repo}/compare/{branch}...OpenMANET:{repo}:{branch}?per_page=1": {"ahead_by": behind}}


def firmware_routes(fork_behind=1, marker=True, base_behind=0, packages_behind=500, luci_behind=0,
                    own_behind=3) -> dict:
    fw = "/repos/ghostnet-labs/firmware"
    r = fork_cmp("firmware", "24.10", fork_behind)
    r[f"{fw}/contents/feeds.conf.default?ref=24.10"] = b64(FEEDS)
    if marker:
        r[f"{fw}/contents/.openwrt-upstream?ref=24.10"] = b64(f"{OWRT} openwrt-24.10 r29306-34fa4b1af5\n")
        r[f"/repos/openwrt/openwrt/compare/{OWRT}...openwrt-24.10?per_page=1"] = {"ahead_by": base_behind}
    r["/repos/openwrt/openwrt/tags?per_page=100"] = [
        {"name": "v24.10.8"}, {"name": "v24.10.10"}, {"name": "v23.05.6"}, {"name": "v24.10.9-rc1"}]
    r["/repos/openwrt/packages/compare/953b6d47b4e9f0ad3c39547c6d3f9a828f10e206...openwrt-24.10?per_page=1"] = {
        "ahead_by": packages_behind}
    r["/repos/OpenMANET/luci/compare/53e65158f7075109d140f8943b4a1f0eb6d84339...mm-23.05?per_page=1"] = {
        "ahead_by": luci_behind}
    r["/repos/ghostnet-labs/packages/compare/6b4cf56f1e2e92495ff6288e8af6e306d4edb7c9...24.10?per_page=1"] = {
        "ahead_by": own_behind}
    return r


class UpstreamTest(unittest.TestCase):
    def test_fork_behind_warns_with_count_and_compare_link(self):
        rows, found = cw.upstream_drift(FakeGitHub(fork_cmp("openmanetd", "main", 4)), ["openmanetd"])
        self.assertEqual(rows[0]["behind"], 4)
        item = found["upstream:openmanetd"]
        self.assertEqual(item["level"], "warn")
        self.assertIn("4 commits behind OpenMANET/openmanetd main", item["text"])
        self.assertEqual(item["url"], "https://github.com/ghostnet-labs/openmanetd/compare/main...OpenMANET:openmanetd:main")

    def test_fork_in_sync_is_a_row_not_a_finding(self):
        rows, found = cw.upstream_drift(FakeGitHub(fork_cmp("luci", "mm-23.05", 0)), ["luci"])
        self.assertEqual(rows[0]["behind"], 0)
        self.assertEqual(found, {})

    def test_docs_and_setup_are_not_compared(self):
        rows, found = cw.upstream_drift(FakeGitHub({}), ["docs", "setup"])
        self.assertEqual((rows, found), ([], {}))

    def test_firmware_base_and_feed_pins(self):
        rows, found = cw.upstream_drift(FakeGitHub(firmware_routes(base_behind=12)), ["firmware"])
        self.assertIn("upstream:firmware", found)
        base = found["upstream:openwrt-base"]
        self.assertIn("12 commits behind openwrt/openwrt openwrt-24.10", base["text"])
        self.assertIn("latest release v24.10.10", base["text"])
        self.assertIn("500 commits behind openwrt/packages openwrt-24.10", found["upstream:feed:packages"]["text"])
        self.assertIn("3 commits behind ghostnet-labs/packages 24.10", found["upstream:feed:openmanet"]["text"])
        self.assertNotIn("upstream:feed:luci", found)  # in sync
        self.assertNotIn("upstream:feed:morse", found)  # vendor feed, no branch to follow
        self.assertEqual(len(rows), 5)  # fork, base, three tracked feeds

    def test_missing_marker_warns_base_unknown(self):
        _, found = cw.upstream_drift(FakeGitHub(firmware_routes(marker=False)), ["firmware"])
        self.assertIn("base is unknown", found["upstream:openwrt-base"]["text"])

    def test_scan_on_interval_and_findings_carry_over(self):
        routes = repo_routes()
        routes.update(fork_cmp("luci", "mm-23.05", 2))
        gh = FakeGitHub(routes)
        state, report, _ = cw.run_once(gh, args(upstream_hours=6), NOW, {})
        self.assertIn("upstream:luci", state["active"])
        self.assertIn("## Upstream drift", report)
        self.assertIn("[2](https://github.com/ghostnet-labs/luci/compare/", report)
        # An hour later the compare is not repeated, and the finding neither clears nor re-alerts.
        del routes["/repos/ghostnet-labs/luci/compare/mm-23.05...OpenMANET:luci:mm-23.05?per_page=1"]
        state2, _, batch2 = cw.run_once(gh, args(upstream_hours=6), NOW + timedelta(hours=1), state)
        self.assertIn("upstream:luci", state2["active"])
        self.assertEqual([i["key"] for i in batch2["new"] + batch2["cleared"]], [])

    def test_sync_clears_the_finding(self):
        routes = repo_routes()
        routes.update(fork_cmp("luci", "mm-23.05", 2))
        gh = FakeGitHub(routes)
        state, _, _ = cw.run_once(gh, args(upstream_hours=6), NOW, {})
        routes.update(fork_cmp("luci", "mm-23.05", 0))
        _, _, batch = cw.run_once(gh, args(upstream_hours=6), NOW + timedelta(hours=7), state)
        self.assertEqual([i["key"] for i in batch["cleared"]], ["upstream:luci"])

    def test_failed_scan_keeps_findings_and_is_not_a_github_outage(self):
        routes = repo_routes()
        routes.update(fork_cmp("luci", "mm-23.05", 2))
        gh = FakeGitHub(routes)
        state, _, _ = cw.run_once(gh, args(upstream_hours=6), NOW, {})
        del routes["/repos/ghostnet-labs/luci/compare/mm-23.05...OpenMANET:luci:mm-23.05?per_page=1"]
        state2, report, batch = cw.run_once(gh, args(upstream_hours=6), NOW + timedelta(hours=7), state)
        self.assertIn("upstream:luci", state2["active"])
        self.assertEqual(batch["cleared"], [])
        self.assertEqual(state2["error_runs"], 0)
        self.assertIn("Last scan failed", report)

    def test_off_means_no_section_and_no_calls(self):
        state, report, _ = cw.run_once(FakeGitHub(repo_routes()), args(upstream_hours=0), NOW, {})
        self.assertNotIn("Upstream drift", report)
        self.assertEqual(state["upstream"], {})


BOARD_WORKFLOW = """name: Build Firmware (PR) on bcm2710

on:
  pull_request:
    # Changes that touch every board build only the smoke set.
    paths:
    - 'boards/ekh-bcm2710/**'
    - "package/kernel/**"   # kernel bumps
  workflow_dispatch:
"""

INDENTED_WORKFLOW = """on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
    paths:
      - internal/**
      - go.mod
"""


class PrTriggerTest(unittest.TestCase):
    def test_paths_at_the_key_indent_and_comments(self):
        self.assertEqual(cw.pr_trigger(BOARD_WORKFLOW), (True, ["boards/ekh-bcm2710/**", "package/kernel/**"]))

    def test_paths_indented_under_the_key(self):
        self.assertEqual(cw.pr_trigger(INDENTED_WORKFLOW), (True, ["internal/**", "go.mod"]))

    def test_every_change_forms(self):
        for text in ("on: pull_request\n", "on: [push, pull_request]\n", "on:\n  - push\n  - pull_request\n",
                     "on:\n  pull_request:\n  push:\n", "on:\n  pull_request:\n    branches: [main]\n",
                     "on:\n  pull_request: {}\n", "'on':\n  pull_request:\n    paths-ignore: ['docs/**']\n"):
            self.assertEqual(cw.pr_trigger(text), (True, None), text)

    def test_flow_paths(self):
        self.assertEqual(cw.pr_trigger("on:\n  pull_request:\n    paths: ['a/**', b]\n"), (True, ["a/**", "b"]))

    def test_not_a_pull_request_workflow(self):
        for text in ("on: push\n", "on:\n  pull_request_target:\n    paths: [a]\n  push:\n",
                     "on:\n  workflow_dispatch:\n", "name: x\n"):
            self.assertEqual(cw.pr_trigger(text)[0], False, text)


def profile(*entries) -> dict:
    return {"branch": "24.10", "workflows": [{"path": p, "paths": paths} for p, paths in entries]}


WF = ".github/workflows/"


class ProfileGapsTest(unittest.TestCase):
    def test_matching_profile_has_no_gaps(self):
        prof = profile((WF + "build-pr-bcm2710.yml", ["boards/ekh-bcm2710/**", "package/kernel/**"]))
        self.assertEqual(cw.profile_gaps(prof, {WF + "build-pr-bcm2710.yml": BOARD_WORKFLOW}), {})

    def test_profile_path_the_workflow_ignores_is_crit(self):
        # The firmware #82 case: the profile kept feeds.conf.default after the workflow dropped it.
        prof = profile((WF + "build-pr-bcm2710.yml", ["boards/ekh-bcm2710/**", "package/kernel/**",
                                                      "feeds.conf.default"]))
        level, text = cw.profile_gaps(prof, {WF + "build-pr-bcm2710.yml": BOARD_WORKFLOW})[WF + "build-pr-bcm2710.yml"]
        self.assertEqual(level, "crit")
        self.assertIn("never starts: feeds.conf.default", text)

    def test_workflow_path_the_profile_lacks_is_warn(self):
        prof = profile((WF + "build-pr-bcm2710.yml", ["boards/ekh-bcm2710/**"]))
        level, text = cw.profile_gaps(prof, {WF + "build-pr-bcm2710.yml": BOARD_WORKFLOW})[WF + "build-pr-bcm2710.yml"]
        self.assertEqual(level, "warn")
        self.assertIn("does not wait for it: package/kernel/**", text)

    def test_missing_file_and_unlisted_workflow(self):
        prof = profile((WF + "gone.yml", None))
        gaps = cw.profile_gaps(prof, {WF + "new.yml": "on: pull_request\n", WF + "push.yml": "on: push\n",
                                      WF + "manet-merge-gate.yml": "on: pull_request\n",
                                      WF + "label-kernel.yml": "on: pull_request\n"})
        self.assertEqual(gaps[WF + "gone.yml"][0], "crit")
        self.assertEqual(gaps[WF + "new.yml"][0], "warn")
        self.assertEqual(set(gaps), {WF + "gone.yml", WF + "new.yml"})

    def test_narrowed_to_paths_is_crit_widened_is_warn(self):
        narrowed = cw.profile_gaps(profile((WF + "a.yml", None)), {WF + "a.yml": BOARD_WORKFLOW})
        widened = cw.profile_gaps(profile((WF + "a.yml", ["x/**"])), {WF + "a.yml": "on: pull_request\n"})
        self.assertEqual(narrowed[WF + "a.yml"][0], "crit")
        self.assertEqual(widened[WF + "a.yml"][0], "warn")

    def test_shipped_profile_parses_and_lists_known_repos(self):
        shipped = json.loads(cw.PROFILE_FILE.read_text(encoding="utf-8"))
        self.assertIn("firmware", shipped)
        self.assertTrue(all("branch" in p and "workflows" in p for p in shipped.values()))


GATE_PINNED = """jobs:
  gate:
    steps:
      - uses: actions/checkout@v6
        with:
          repository: ghostnet-labs/docs
          ref: ea86ea3986ca93b882b720b05ea5c21b7fbaa152
"""


def listing(*paths) -> list[dict]:
    return [{"type": "file", "name": p.rsplit("/", 1)[-1], "path": p} for p in paths]


class ProfileDriftTest(unittest.TestCase):
    def routes(self, pinned_paths) -> dict:
        fw = "/repos/ghostnet-labs/firmware"
        return {
            f"{fw}/contents/.github/workflows?ref=24.10": listing(WF + "build-pr-bcm2710.yml", WF + "manet-merge-gate.yml"),
            f"{fw}/contents/.github/workflows/build-pr-bcm2710.yml?ref=24.10": b64(BOARD_WORKFLOW),
            f"{fw}/contents/.github/workflows/manet-merge-gate.yml?ref=24.10": b64(GATE_PINNED),
            "/repos/ghostnet-labs/docs/contents/project/scripts/merge_profiles.json?ref="
            "ea86ea3986ca93b882b720b05ea5c21b7fbaa152": b64(json.dumps(
                {"firmware": profile((WF + "build-pr-bcm2710.yml", pinned_paths))})),
        }

    def test_checks_the_pinned_profile_and_docs_main(self):
        good = ["boards/ekh-bcm2710/**", "package/kernel/**"]
        local = {"firmware": profile((WF + "build-pr-bcm2710.yml", good + ["feeds.conf.default"]))}
        found = cw.profile_drift(FakeGitHub(self.routes(good)), ["firmware", "luci"], local)
        item = found["profile:firmware:build-pr-bcm2710.yml"]
        self.assertEqual(item["level"], "crit")
        self.assertIn("docs main", item["text"])
        self.assertNotIn("ea86ea3", item["text"])
        self.assertEqual(item["url"], "https://github.com/ghostnet-labs/firmware/blob/24.10/" + WF + "build-pr-bcm2710.yml")

    def test_pinned_profile_drift_is_named(self):
        good = ["boards/ekh-bcm2710/**", "package/kernel/**"]
        local = {"firmware": profile((WF + "build-pr-bcm2710.yml", good))}
        found = cw.profile_drift(FakeGitHub(self.routes(["boards/ekh-bcm2710/**"])), ["firmware"], local)
        self.assertIn("pinned docs ea86ea3", found["profile:firmware:build-pr-bcm2710.yml"]["text"])

    def test_run_once_scans_on_its_interval(self):
        routes = repo_routes()
        gh = FakeGitHub(routes)
        state, _, _ = cw.run_once(gh, args(profile_hours=6, repos="luci"), NOW, {})
        self.assertIn("scan_iso", state["profiles"])
        self.assertEqual(state["profiles"]["found"], {})  # luci's workflows 404 in this fake: skipped, no finding
        # An hour later the scan is not repeated.
        state2, _, _ = cw.run_once(gh, args(profile_hours=6, repos="luci"), NOW + timedelta(hours=1), state)
        self.assertEqual(state2["profiles"]["scan_iso"], state["profiles"]["scan_iso"])


if __name__ == "__main__":
    unittest.main()


class ScheduleFindingsTest(unittest.TestCase):
    def runs(self, *items):
        return {"/repos/ghostnet-labs/firmware/actions/runs?event=schedule&status=completed&per_page=50":
                {"workflow_runs": list(items)}}

    def run_(self, wf, path, conclusion, name="Full firmware build", run_id=1):
        return {"workflow_id": wf, "path": path, "conclusion": conclusion, "name": name,
                "html_url": f"https://github.com/ghostnet-labs/firmware/actions/runs/{run_id}",
                "created_at": "2026-11-05T07:00:09Z"}

    def test_latest_failure_of_full_build_is_crit(self):
        gh = FakeGitHub(self.runs(self.run_(1, ".github/workflows/build-full.yml", "failure", run_id=7)))
        found = cw.schedule_findings(gh, "firmware")
        item = found["schedule:firmware:.github/workflows/build-full.yml"]
        self.assertEqual(item["level"], "crit")
        self.assertIn("/runs/7", item["url"])
        self.assertIn("Full firmware build failed (failure, 2026-11-05 07:00Z)", item["text"])

    def test_only_latest_run_per_workflow_counts(self):
        gh = FakeGitHub(self.runs(
            self.run_(1, ".github/workflows/build-full.yml", "success", run_id=8),
            self.run_(1, ".github/workflows/build-full.yml", "failure", run_id=7),
            self.run_(2, ".github/workflows/sweep.yml", "timed_out", name="Sweep", run_id=6)))
        found = cw.schedule_findings(gh, "firmware")
        self.assertEqual(list(found), ["schedule:firmware:.github/workflows/sweep.yml"])
        self.assertEqual(found["schedule:firmware:.github/workflows/sweep.yml"]["level"], "warn")

    def test_cancelled_and_missing_are_quiet(self):
        gh = FakeGitHub(self.runs(self.run_(1, ".github/workflows/build-full.yml", "cancelled")))
        self.assertEqual(cw.schedule_findings(gh, "firmware"), {})
        self.assertEqual(cw.schedule_findings(FakeGitHub({}), "luci"), {})

    def test_other_errors_propagate(self):
        gh = FakeGitHub({"/repos/ghostnet-labs/luci/actions/runs?event=schedule&status=completed&per_page=50":
                         RuntimeError("HTTP 500")})
        with self.assertRaises(RuntimeError):
            cw.schedule_findings(gh, "luci")
