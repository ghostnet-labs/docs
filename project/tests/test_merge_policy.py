import base64
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from merge_policy import (evaluate, matches, reviews_clear, protection_ready,
                          check_blockers, external_build_blockers, GATE,
                          terminal_blocker)

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


if __name__ == "__main__":
    unittest.main()
