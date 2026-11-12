from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from check_decision_ids import DECISIONS, check


def doc(log_ids, next_id, retired_ids=(1,)):
    rows = "\n".join(f"| D-{n:03d} | 2026-11-01 | x | y |" for n in log_ids)
    retired = "\n".join(f"| R-{n:03d} | x | Rejected | y |" for n in retired_ids)
    return (f"## Log\n\n| ID | Date | Decision | Why |\n|---|---|---|---|\n{rows}\n\n"
            f"The next decision takes ID **D-{next_id:03d}**.\n\n"
            f"## Retired and rejected\n\n| ID | Item | Status | Reason |\n|---|---|---|---|\n{retired}\n")


class DecisionIDsTest(unittest.TestCase):
    def test_current_record_is_consistent(self):
        problems, _ = check(DECISIONS.read_text(encoding="utf-8"))
        self.assertEqual(problems, [])

    def test_consistent_log_passes(self):
        self.assertEqual(check(doc([3, 2, 1], 4)), ([], 4))

    def test_stale_next_id_is_reported(self):
        problems, expected = check(doc([3, 2, 1], 2))
        self.assertEqual(expected, 4)
        self.assertIn("should say D-004", problems[0])

    def test_duplicate_gap_and_order(self):
        problems, _ = check(doc([2, 4, 2], 5))
        text = " ".join(problems)
        self.assertIn("D-002 appears more than once", text)
        self.assertIn("D-001, D-003", text)
        self.assertIn("newest first", text)

    def test_duplicate_retired_id(self):
        problems, _ = check(doc([1], 2, retired_ids=(1, 1)))
        self.assertIn("R-001 appears more than once", problems[0])

    def test_missing_next_line(self):
        problems, _ = check(doc([1], 2).replace("The next decision", "Next"))
        self.assertTrue(any("exactly one" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
