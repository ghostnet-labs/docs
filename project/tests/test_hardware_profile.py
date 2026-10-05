import json
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from merge_policy import evaluate


class HardwareProfileTests(unittest.TestCase):
    def test_changed_qualification_tools_require_their_workflow(self):
        profile = json.loads((SCRIPTS / "merge_profiles.json").read_text())["firmware"]
        blockers = evaluate(profile, ["scripts/hardware-qualification/resources.py"], [], "head", 1)
        self.assertIn("Missing applicable workflow: .github/workflows/hardware-qualification.yml", blockers)
        blockers = evaluate(profile, ["docs/README.md"], [], "head", 1)
        self.assertNotIn("Missing applicable workflow: .github/workflows/hardware-qualification.yml", blockers)
