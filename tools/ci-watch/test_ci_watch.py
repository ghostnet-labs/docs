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


def check(name, status="completed", conclusion="success", run_id=1, started=30):
    return {"name": name, "status": status, "conclusion": conclusion, "id": run_id, "started_at": ts(started)}


def repo_routes(repo="luci", prs=None, checks=None, statuses=None, merge="clean", auto_merge=True,
                wf_state="active", run_age=10, details=None) -> dict:
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

    def test_young_or_hosted_queue_is_not_starved(self):
        self.assertEqual(cw.starved_labels(self.starved_state(age=5)), {})
        state = self.starved_state()
        state["jobs"][0]["hosted"] = True
        self.assertEqual(cw.starved_labels(state), {})

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
                            "--deploy-status", "", "--idle-restart-status", ""])
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


if __name__ == "__main__":
    unittest.main()
