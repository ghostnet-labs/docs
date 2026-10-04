"""Integration tests ensure API evidence cannot bypass the protected merge."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from merge_policy import handle, snapshot, GATE

class FakeAPI:
    def __init__(self):
        self.merge_calls = []
        self.pr = {"state": "open", "draft": False, "changed_files": 1, "body": "", "labels": [],
                   "base": {"ref": "main"}, "head": {"sha": "current", "repo": {"full_name": "ghostnet-labs/docs"}},
                   "mergeable_state": "clean"}
        self.runs = [{"id": 1, "head_sha": "current", "event": "pull_request", "path": "tests.yml",
                     "pull_requests": [{"number": 7}], "status": "completed", "conclusion": "success"}]
        self.checks = [{"id": 1, "name": GATE, "status": "completed", "conclusion": "success", "app": {"id": 15368}}]
        self.rules = [{"type": "pull_request", "parameters": {"required_review_thread_resolution": True}},
                      {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": True,
                       "required_status_checks": [{"context": GATE, "integration_id": 15368}]}}]
        self.reviews = []
        self.status = {"statuses": [], "state": "pending"}
    def pages(self, path, key=None):
        if "/files" in path: return [{"filename": "AGENTS.md"}]
        if "/actions/runs" in path: return self.runs
        if "/check-runs" in path: return self.checks
        if "/reviews" in path: return self.reviews
        raise AssertionError(path)
    def call(self, path, data=None, method=None):
        if path.endswith("/merge"):
            self.merge_calls.append((data, method))
            return {"merged": True, "sha": "merged"}
        if "/rules/branches/" in path: return self.rules
        if path.endswith("/status"): return self.status
        if "/pulls/" in path: return self.pr
        raise AssertionError(path)

class APITests(unittest.TestCase):
    profile = {"branch": "main", "workflows": [{"path": "tests.yml", "paths": None}]}
    def test_pass_uses_expected_sha_and_protected_endpoint(self):
        api = FakeAPI()
        handle(api, "ghostnet-labs/docs", 7, self.profile)
        self.assertEqual(api.merge_calls, [({"sha": "current", "merge_method": "merge"}, "PUT")])
    def test_holds_drafts_forks_conflicts_missing_runs_and_protection_block(self):
        for change in ["hold", "draft", "fork", "behind", "missing", "protection", "review", "external"]:
            with self.subTest(change=change):
                api = FakeAPI()
                if change == "hold": api.pr["labels"] = [{"name": "do-not-merge"}]
                if change == "draft": api.pr["draft"] = True
                if change == "fork": api.pr["head"]["repo"]["full_name"] = "fork/docs"
                if change == "behind": api.pr["mergeable_state"] = "behind"
                if change == "missing": api.runs = []
                if change == "protection": api.rules = []
                if change == "review": api.reviews = [{"id": 1, "user": {"login": "reviewer"}, "state": "CHANGES_REQUESTED"}]
                if change == "external": api.status = {"statuses": [{"context": "external", "state": "pending"}], "state": "pending"}
                handle(api, "ghostnet-labs/docs", 7, self.profile)
                self.assertEqual(api.merge_calls, [])
    def test_incomplete_file_inventory_and_gate_source_block(self):
        api = FakeAPI()
        api.pr["changed_files"] = 3001
        self.assertTrue(snapshot(api, "ghostnet-labs/docs", 7, self.profile)[1])
        api = FakeAPI()
        api.checks[0]["app"]["id"] = 99
        handle(api, "ghostnet-labs/docs", 7, self.profile)
        self.assertEqual(api.merge_calls, [])

if __name__ == "__main__":
    unittest.main()
