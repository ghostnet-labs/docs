"""Tests for project/scripts/add_runner_policy_gate.py (needs PyYAML, so not in project/tests)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "project" / "scripts"))

import yaml  # noqa: E402

import add_runner_policy_gate as ag  # noqa: E402

SHA = "a" * 40
GATE = (ROOT / ".github" / "workflows" / "manet-merge-gate.yml").read_text()


class AddRunnerPolicyGateTest(unittest.TestCase):
    def test_inserts_the_steps_before_the_regression_suite(self):
        steps = yaml.safe_load(ag.patch(GATE, SHA))["jobs"]["gate"]["steps"]
        names = [s.get("name") for s in steps]
        self.assertEqual(names.index("Check the runner policy") + 1, names.index("Verify merge policy regression suite"))
        self.assertEqual(steps[names.index("Check out the runner policy")]["with"]["ref"], SHA)

    def test_refuses_to_patch_twice_or_with_a_bad_ref(self):
        patched = ag.patch(GATE, SHA)
        with self.assertRaises(ValueError):
            ag.patch(patched, SHA)
        with self.assertRaises(ValueError):
            ag.patch(GATE, "main")

    def test_patched_gate_still_passes_the_runner_policy(self):
        import check_runners as cr
        doc = yaml.safe_load(ag.patch(GATE, SHA))
        found = cr.check_workflow("docs", "manet-merge-gate.yml", doc)
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
