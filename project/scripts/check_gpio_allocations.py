#!/usr/bin/env python3
"""Validate the canonical CM5 GPIO ledger and explicit cross-document mappings."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "hardware" / "v1-pinout-and-sequencing.md"
HEADER = "| GPIO | CM5 connector pin | Signal | Function / verification status |"
ROW = re.compile(r"^\|\s*(\d+|\d+[–-]\d+)\s*\|\s*(?:\d+|—)\s*\|\s*([A-Z][A-Z0-9_]+)\s*\|")
PAIR = re.compile(
    r"\b([A-Z][A-Z0-9_]+)\b[^;,.|]{0,80}?"
    r"\b(?:on|to|uses?|mapped to|assigned to)\s+"
    r"(?:[A-Za-z0-9_/-]+\s+){0,2}GPIO\s*(\d+)\b"
)


def fail(message: str) -> None:
    print(f"GPIO allocation check: ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if not LEDGER.exists():
        fail(f"canonical ledger missing: {LEDGER.relative_to(ROOT)}")

    lines = LEDGER.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index(HEADER) + 2
    except ValueError:
        fail(f"expected allocation table header not found in {LEDGER.relative_to(ROOT)}")

    allocations: dict[int, str] = {}
    signal_to_gpio: dict[str, int] = {}
    for line in lines[start:]:
        if not line.startswith("|"):
            break
        match = ROW.match(line)
        if not match:
            continue
        gpio_cell, signal = match.groups()
        if "–" in gpio_cell:
            first, last = map(int, gpio_cell.split("–"))
        elif "-" in gpio_cell:
            first, last = map(int, gpio_cell.split("-"))
        else:
            first = last = int(gpio_cell)
        for gpio in range(first, last + 1):
            if gpio in allocations:
                fail(f"GPIO{gpio} assigned twice: {allocations[gpio]} and {signal}")
            allocations[gpio] = signal
            if signal != "Reserved":
                if signal in signal_to_gpio:
                    fail(f"{signal} assigned to both GPIO{signal_to_gpio[signal]} and GPIO{gpio}")
                signal_to_gpio[signal] = gpio

    expected = set(range(28))
    actual = set(allocations)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        fail(f"ledger must allocate/reserve GPIO0–27 exactly once (missing={missing}, extra={extra})")

    errors = []
    project_root = ROOT
    for path in project_root.rglob("*.md"):
        if path == LEDGER:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for signal, gpio_text in PAIR.findall(line):
                if signal in signal_to_gpio and signal_to_gpio[signal] != int(gpio_text):
                    errors.append(
                        f"{path.relative_to(ROOT)}:{lineno}: {signal} explicitly mapped to "
                        f"GPIO{gpio_text}; canonical ledger assigns GPIO{signal_to_gpio[signal]}"
                    )
    if errors:
        for error in errors:
            print(f"GPIO allocation check: ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)

    print(
        "GPIO allocation check: OK — GPIO0–27 are allocated/reserved exactly once; "
        "explicit project-document mappings agree with the canonical ledger."
    )


if __name__ == "__main__":
    main()
