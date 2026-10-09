import base64
import io
import json
import unittest
import urllib.error
from contextlib import redirect_stdout
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from merge_policy import (evaluate, matches, reviews_clear, protection_ready,
                          check_blockers, external_build_blockers, GATE,
                          terminal_blocker, handle, stale_gate_run)

class GateTests(unittest.TestCase):
    def setUp(self):
        self.profile = {"workflows": [{"path": "tests.yml", "paths": ["src/**"]}]}
        self.run = {"id": 1, "head_sha": "current", "event": "pull_request", "path": "tests.yml",
                    "pull_requests": [{"number": 7}], "status": "completed", "conclusion": "success"}

    def evaluate(self, runs, files=None):
        return evaluate(self.profile, files or ["src/main.go"], runs, "current", 7)

    def test_transient_neutral_waits_but_never_passes(self):
        neutral = dict(self.run, conclusion="neutral")
        blockers = self.evaluate([neutral])
        self.assertTrue(blockers)
        self.assertFalse(any(terminal_blocker(b) for b in blockers))
        self.assertEqual(self.evaluate([neutral, dict(self.run, id=2)]), [])

    def test_terminal_failures_exit_promptly(self):
        for outcome in ["failure", "cancelled", "timed_out", "action_required", "skipped"]:
            self.assertTrue(terminal_blocker("Check test: completed/" + outcome))
        self.assertFalse(terminal_blocker("Check test: in_progress/None"))

    def test_success(self):
        self.assertEqual(self.evaluate([self.run]), [])

    def test_missing(self):
        self.assertTrue(self.evaluate([]))

    def test_stale_and_other_pr_do_not_count(self):
        for changes in [{"head_sha": "old"}, {"pull_requests": [{"number": 8}]}, {"event": "push"}]:
            self.assertTrue(self.evaluate([dict(self.run, **changes)]))

    def test_terminal_non_success_does_not_pass(self):
        for conclusion in ["failure", "cancelled", "skipped", "neutral", "timed_out", "action_required"]:
            self.assertTrue(self.evaluate([dict(self.run, conclusion=conclusion)]))

    def test_pending_does_not_pass(self):
        for status in ["queued", "in_progress", "waiting"]:
            self.assertTrue(self.evaluate([dict(self.run, status=status, conclusion=None)]))

    def test_new_attempt_supersedes_old(self):
        failed = dict(self.run, conclusion="failure")
        self.assertEqual(self.evaluate([failed, dict(self.run, id=2)]), [])
        self.assertTrue(self.evaluate([self.run, dict(failed, id=2)]))

    def test_not_applicable_does_not_require_run(self):
        self.assertEqual(self.evaluate([], ["README.md"]), [])

    def test_extra_triggered_workflow_failure_blocks(self):
        extra = dict(self.run, id=2, path="label-build.yml", conclusion="failure")
        self.assertTrue(self.evaluate([self.run, extra]))

    def test_gate_does_not_wait_on_itself(self):
        gate = dict(self.run, path=".github/workflows/manet-merge-gate.yml", status="in_progress")
        self.assertEqual(self.evaluate([self.run, gate]), [])

    def test_path_matching(self):
        for path, pattern in [("a/b/c.go", "**.go"), ("main.go", "**/*.go"),
                              ("a/b/main.go", "**/*.go"), ("src/x/y", "src/**")]:
            self.assertTrue(matches(path, pattern))
        self.assertFalse(matches("src/x/y", "src/*"))

    def test_package_code_without_build_blocks(self):
        profile = {"workflows": [], "externalBuild": True}
        self.assertTrue(evaluate(profile, ["net/test/Makefile"], [], "current", 7))
        self.assertEqual(evaluate(profile, ["README.md"], [], "current", 7), [])

    def test_packages_profile_requires_compile_workflow(self):
        profiles = json.loads((Path(__file__).resolve().parents[1] / "scripts" / "merge_profiles.json").read_text())
        profile = profiles["packages"]
        self.assertFalse(profile.get("externalBuild"))
        self.assertIn("Missing applicable workflow: .github/workflows/build-packages.yml",
                      evaluate(profile, ["net/test/Makefile"], [], "current", 7))
        build = dict(self.run, path=".github/workflows/build-packages.yml")
        self.assertEqual(evaluate(profile, ["net/test/Makefile"], [build], "current", 7), [])

    def test_openmanetd_profile_requires_browser_e2e_for_ui_changes(self):
        profiles = json.loads((Path(__file__).resolve().parents[1] / "scripts" / "merge_profiles.json").read_text())
        profile = profiles["openmanetd"]
        e2e = ".github/workflows/e2e-frontend.yml"
        for changed in ["frontend/src/App.jsx", "internal/frontend/server.go", "internal/config/config.go"]:
            self.assertIn("Missing applicable workflow: " + e2e,
                          evaluate(profile, [changed], [], "current", 7), changed)
        self.assertNotIn("Missing applicable workflow: " + e2e,
                         evaluate(profile, ["internal/mgmt/alfred.go"], [], "current", 7))
        runs = [dict(self.run, id=i, path=w["path"]) for i, w in enumerate(profile["workflows"])]
        self.assertEqual(evaluate(profile, ["frontend/src/App.jsx"], runs, "current", 7), [])

    def test_luci_profile_builds_without_openwrt_formalities(self):
        profiles = json.loads((Path(__file__).resolve().parents[1] / "scripts" / "merge_profiles.json").read_text())
        paths = [w["path"] for w in profiles["luci"]["workflows"]]
        self.assertIn(".github/workflows/build.yml", paths)
        self.assertNotIn(".github/workflows/formal.yml", paths)
        self.assertEqual(evaluate(profiles["luci"], ["applications/luci-app-x/Makefile"], [], "current", 7),
                         ["Missing applicable workflow: .github/workflows/build.yml"])

    def test_requested_changes_and_dismissal(self):
        review = {"id": 1, "user": {"login": "reviewer"}, "state": "CHANGES_REQUESTED"}
        self.assertFalse(reviews_clear([review]))
        self.assertFalse(reviews_clear([review, dict(review, id=2, state="COMMENTED")]))
        self.assertTrue(reviews_clear([review, dict(review, id=2, state="APPROVED")]))
        self.assertTrue(reviews_clear([review, dict(review, id=2, state="DISMISSED")]))

    def test_native_protection_required(self):
        rules = [{"type": "pull_request", "parameters": {"required_review_thread_resolution": True}},
                 {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": True,
                   "required_status_checks": [{"context": GATE, "integration_id": 15368}]}}]
        self.assertTrue(protection_ready(rules))
        self.assertFalse(protection_ready(rules[1:]))
        rules[-1]["parameters"]["strict_required_status_checks_policy"] = False
        self.assertFalse(protection_ready(rules))

    def test_external_checks_and_skipped_tests_block(self):
        check = {"id": 1, "app": {"id": 99}, "name": "External security scan", "status": "completed", "conclusion": "success"}
        self.assertEqual(check_blockers([check]), [])
        for changes in [{"status": "in_progress", "conclusion": None}, {"conclusion": "failure"}, {"conclusion": "neutral"}, {"conclusion": "skipped"}]:
            self.assertTrue(check_blockers([dict(check, **changes)]))
        self.assertEqual(check_blockers([dict(check, name="Upload ccache cache to s3", conclusion="skipped")]), [])
        self.assertTrue(check_blockers([dict(check, name="test", conclusion="skipped")]))


class FakeExternalAPI:
    def __init__(self, commit, compare="ahead", pinned=None, gate="success", pr_gate="success"):
        self.commit = commit
        self.compare = compare
        self.pinned = commit if pinned is None else pinned
        self.gate = gate
        self.pr_gate = pr_gate

    def call(self, path, data=None, method=None):
        if "/compare/" in path:
            return {"status": self.compare}
        if path.endswith("/pulls/42"):
            return {"draft": False, "head": {"sha": "integration-head"}}
        if "/contents/feeds.conf.default?ref=integration-head" in path:
            text = f"src-git openmanet https://github.com/ghostnet-labs/packages.git^{self.pinned}\n"
            return {"content": base64.b64encode(text.encode()).decode()}
        if path.endswith("/commits/integration-head/status"):
            return {"statuses": [], "state": "success"}
        raise AssertionError(path)

    def pages(self, path, key=None):
        if path.endswith("/commits/integration-head/check-runs"):
            return [
                {"id": 1, "name": GATE, "app": {"id": 15368}, "status": "completed", "conclusion": self.gate},
                {"id": 2, "name": "PR gate", "app": {"id": 15368}, "status": "completed", "conclusion": self.pr_gate},
            ]
        raise AssertionError(path)


class ExternalBuildTests(unittest.TestCase):
    commit = "a" * 40
    profile = {"workflows": [], "externalBuild": True,
               "externalBuildRepo": "ghostnet-labs/firmware",
               "externalBuildPinPath": "feeds.conf.default"}
    files = ["openmanetd/Makefile"]

    def pr(self, body=None):
        if body is None:
            body = ("External-Integration-PR: https://github.com/ghostnet-labs/firmware/pull/42\n"
                    f"External-Integration-Commit: {self.commit}\n")
        return {"body": body, "head": {"sha": "package-head"}}

    def test_verified_external_integration_passes(self):
        api = FakeExternalAPI(self.commit)
        self.assertEqual(external_build_blockers(api, "ghostnet-labs/packages", self.pr(), self.files, self.profile), [])

    def test_missing_external_integration_fails_closed(self):
        api = FakeExternalAPI(self.commit)
        blockers = external_build_blockers(api, "ghostnet-labs/packages", self.pr(""), self.files, self.profile)
        self.assertTrue(blockers)

    def test_stale_external_integration_commit_fails(self):
        api = FakeExternalAPI(self.commit, compare="diverged")
        blockers = external_build_blockers(api, "ghostnet-labs/packages", self.pr(), self.files, self.profile)
        self.assertIn("does not contain", blockers[0])

    def test_mismatched_external_pin_fails(self):
        api = FakeExternalAPI(self.commit, pinned="b" * 40)
        blockers = external_build_blockers(api, "ghostnet-labs/packages", self.pr(), self.files, self.profile)
        self.assertIn("does not pin", blockers[0])

    def test_failed_external_checks_fail(self):
        api = FakeExternalAPI(self.commit, pr_gate="failure")
        blockers = external_build_blockers(api, "ghostnet-labs/packages", self.pr(), self.files, self.profile)
        self.assertTrue(any("External integration" in b for b in blockers))


RULES = [
    {"type": "pull_request", "parameters": {"required_review_thread_resolution": True}},
    {"type": "required_status_checks", "parameters": {
        "strict_required_status_checks_policy": True,
        "required_status_checks": [{"context": GATE, "integration_id": 15368}]}},
]


class FakeMergeAPI:
    """Just enough of the GitHub API for handle() on PR 7 with head "head"."""

    def __init__(self, gate="success", gate_status="completed", tests="success", merge_error=None,
                 rerun_error=None, gate_attempt=1):
        self.gate_attempt = gate_attempt
        self.gate = gate
        self.gate_status = gate_status
        self.tests = tests
        self.merge_error = merge_error
        self.rerun_error = rerun_error
        self.writes = []

    def call(self, path, data=None, method=None):
        if method:
            self.writes.append((method, path))
            error = self.merge_error if path.endswith("/merge") else self.rerun_error
            if error:
                raise urllib.error.HTTPError(path, error, "refused", {}, None)
            return {"merged": True, "sha": "merged"} if path.endswith("/merge") else {}
        if path == "repos/o/r/pulls/7":
            return {"state": "open", "draft": False, "base": {"ref": "main"}, "body": "",
                    "head": {"sha": "head", "repo": {"full_name": "o/r"}}, "labels": [],
                    "changed_files": 1, "mergeable_state": "clean"}
        if path.endswith("/commits/head/status"):
            return {"statuses": [], "state": "pending"}
        if path.endswith("/rules/branches/main"):
            return RULES
        if path == "repos/o/r/actions/runs/99":
            return {"run_attempt": self.gate_attempt}
        raise AssertionError(path)

    def pages(self, path, key=None):
        if path.startswith("repos/o/r/pulls/7/files"):
            return [{"filename": "src/main.go"}]
        if path.startswith("repos/o/r/actions/runs"):
            return [{"id": 1, "head_sha": "head", "event": "pull_request", "path": "tests.yml",
                     "pull_requests": [{"number": 7}], "status": "completed", "conclusion": self.tests}]
        if path.endswith("/commits/head/check-runs"):
            return [{"id": 5, "name": GATE, "app": {"id": 15368}, "status": self.gate_status,
                     "conclusion": self.gate if self.gate_status == "completed" else None,
                     "details_url": "https://github.com/o/r/actions/runs/99/job/5"}]
        if path.endswith("/reviews"):
            return []
        raise AssertionError(path)


class AutoMergeTests(unittest.TestCase):
    profile = {"branch": "main", "workflows": [{"path": "tests.yml", "paths": None}]}

    def handle(self, api):
        out = io.StringIO()
        with redirect_stdout(out):
            handle(api, "o/r", 7, self.profile)
        return out.getvalue()

    def test_passing_pr_merges(self):
        api = FakeMergeAPI()
        self.assertIn("merged", self.handle(api))
        self.assertEqual(api.writes, [("PUT", "repos/o/r/pulls/7/merge")])

    def test_refused_merge_is_logged_not_raised(self):
        for code in (405, 409):
            api = FakeMergeAPI(merge_error=code)
            self.assertIn(f"HTTP {code}", self.handle(api))

    def test_other_merge_errors_still_fail(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.handle(FakeMergeAPI(merge_error=500))

    def test_timed_out_gate_reruns_once_workflows_pass(self):
        for conclusion in ("failure", "timed_out", "cancelled"):
            api = FakeMergeAPI(gate=conclusion)
            self.assertIn("re-running gate run 99", self.handle(api))
            self.assertEqual(api.writes, [("POST", "repos/o/r/actions/runs/99/rerun")])

    def test_gate_not_rerun_while_workflows_block(self):
        for tests in ("failure", "in_progress"):
            api = FakeMergeAPI(gate="failure", tests=tests)
            self.handle(api)
            self.assertEqual(api.writes, [])

    def test_running_gate_not_rerun(self):
        api = FakeMergeAPI(gate_status="in_progress")
        self.handle(api)
        self.assertEqual(api.writes, [])

    def test_gate_reruns_are_capped(self):
        api = FakeMergeAPI(gate="failure", gate_attempt=3)
        self.handle(api)
        self.assertEqual(api.writes, [])

    def test_rerun_refusal_is_logged(self):
        api = FakeMergeAPI(gate="failure", rerun_error=403)
        self.assertIn("could not re-run gate run 99: HTTP 403", self.handle(api))

    def test_stale_gate_run_ignores_other_blockers_and_bad_urls(self):
        gate = {"id": 1, "status": "completed", "conclusion": "failure", "details_url": "https://example.com/x"}
        self.assertIsNone(stale_gate_run([gate], []))
        self.assertIsNone(stale_gate_run([dict(gate, details_url="https://github.com/o/r/actions/runs/3/job/4")], ["blocked"]))
        self.assertIsNone(stale_gate_run([], []))
        newer = dict(gate, id=2, conclusion="success")
        self.assertIsNone(stale_gate_run([dict(gate, details_url="https://github.com/o/r/actions/runs/3/job/4"), newer], []))


if __name__ == "__main__":
    unittest.main()
