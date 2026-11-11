"""Check that decisions.md IDs are unique and the next-ID line is current.

Run with --fix to rewrite the next-ID line from the table.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
DECISIONS = ROOT / "project" / "decisions.md"

ROW = re.compile(r"(?m)^\| (D|R)-(\d{3}) \|")
NEXT = re.compile(r"The next decision takes ID \*\*D-(\d{3})\*\*")


def check(text):
    """Return (problems, expected next ID number)."""
    problems = []
    log, _, retired = text.partition("\n## Retired and rejected")
    decisions = [int(n) for p, n in ROW.findall(log) if p == "D"]
    retired_ids = [int(n) for p, n in ROW.findall(retired) if p == "R"]
    if not decisions:
        return ["no D-nnn rows found in the log"], None
    for prefix, ids in (("D", decisions), ("R", retired_ids)):
        seen = set()
        for n in ids:
            if n in seen:
                problems.append(f"{prefix}-{n:03d} appears more than once")
            seen.add(n)
        missing = sorted(set(range(1, max(ids, default=0) + 1)) - seen)
        if missing:
            problems.append(f"{prefix} IDs missing: " + ", ".join(f"{prefix}-{n:03d}" for n in missing))
    if decisions != sorted(decisions, reverse=True):
        problems.append("log rows are not newest first (D IDs must descend)")
    expected = max(decisions) + 1
    found = NEXT.findall(text)
    if len(found) != 1:
        problems.append("expected exactly one 'The next decision takes ID **D-nnn**' line")
    elif int(found[0]) != expected:
        problems.append(f"next-ID line says D-{int(found[0]):03d}, but the highest row is D-{expected - 1:03d}; it should say D-{expected:03d}")
    return problems, expected


def main(argv):
    text = DECISIONS.read_text(encoding="utf-8")
    problems, expected = check(text)
    if "--fix" in argv and expected is not None:
        text = NEXT.sub(f"The next decision takes ID **D-{expected:03d}**", text, count=1)
        DECISIONS.write_text(text, encoding="utf-8")
        problems, expected = check(text)
    if problems:
        for p in problems:
            print("decisions.md: " + p, file=sys.stderr)
        print("Fix by hand, or run: python3 project/scripts/check_decision_ids.py --fix", file=sys.stderr)
        return 1
    print(f"decisions.md IDs are consistent; next decision is D-{expected:03d}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
