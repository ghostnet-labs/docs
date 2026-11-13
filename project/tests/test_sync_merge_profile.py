import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from sync_merge_profile import sync

PR = "on:\n  pull_request:\n    paths:\n      - a/**\n"
WF = ".github/workflows/"


class SyncTests(unittest.TestCase):
    def profile(self, *entries):
        return {"branch": "main", "workflows": [{"path": WF + p, "paths": paths} for p, paths in entries]}

    def test_adds_missing_workflow_with_its_paths(self):
        new, changes = sync(self.profile(), {WF + "new.yml": PR})
        self.assertEqual(new["workflows"], [{"path": WF + "new.yml", "paths": ["a/**"]}])
        self.assertEqual(changes, ["add " + WF + "new.yml"])

    def test_adds_every_change_workflow_with_null_paths(self):
        new, _ = sync(self.profile(), {WF + "all.yml": "on: pull_request\n"})
        self.assertEqual(new["workflows"], [{"path": WF + "all.yml", "paths": None}])

    def test_updates_paths_and_keeps_other_keys_and_order(self):
        old = self.profile(("b.yml", None), ("a.yml", ["x/**"]))
        old["requireUpToDate"] = False
        new, changes = sync(old, {WF + "a.yml": PR, WF + "b.yml": "on: pull_request\n"})
        self.assertEqual([w["path"] for w in new["workflows"]], [WF + "b.yml", WF + "a.yml"])
        self.assertEqual(new["workflows"][1]["paths"], ["a/**"])
        self.assertFalse(new["requireUpToDate"])
        self.assertEqual(changes, ["update paths of " + WF + "a.yml"])

    def test_removes_workflows_that_stopped_or_vanished_and_skips_gate(self):
        old = self.profile(("push.yml", None), ("gone.yml", None))
        new, changes = sync(old, {WF + "push.yml": "on: push\n", WF + "manet-merge-gate.yml": PR})
        self.assertEqual(new["workflows"], [])
        self.assertEqual(len(changes), 2)

    def test_already_matching_changes_nothing(self):
        old = self.profile(("a.yml", ["a/**"]))
        self.assertEqual(sync(old, {WF + "a.yml": PR}), (old, []))
