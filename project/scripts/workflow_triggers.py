"""Read on.pull_request.paths from workflow files and compare them with merge_profiles.json.

Shared by the merge gate (merge_policy.py, which blocks a PR that adds or changes a
workflow the profile does not cover) and ci-watch (which audits every repo every 6 hours).
Standard library only, so the gate runner and the Mac need no PyYAML.
"""
from __future__ import annotations

import re

GATE_WORKFLOW = ".github/workflows/manet-merge-gate.yml"
# Workflows the gate itself ignores (merge_policy.py: the gate, LABEL_WORKFLOWS).
GATE_IGNORED = {GATE_WORKFLOW, ".github/workflows/label-kernel.yml", ".github/workflows/label-target.yml"}
YAML_KEY = re.compile(r"^(\s*)(['\"]?)([\w-]+)\2:\s*(.*)$")


def _strip_comment(line: str) -> str:
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _flow_list(value: str) -> list[str]:
    return [_scalar(v) for v in value.strip()[1:-1].split(",") if v.strip()]


def _block(lines: list[str], start: int, indent: int) -> list[str]:
    """Lines after start that are indented deeper than indent (blank lines dropped)."""
    out = []
    for line in lines[start + 1:]:
        if not line.strip():
            continue
        if len(line) - len(line.lstrip()) <= indent:
            break
        out.append(line)
    return out


def _sequence(lines: list[str], start: int, indent: int) -> list[str]:
    """A block sequence under the key at lines[start]; YAML allows its "- " items at the key's own indent."""
    items = []
    for line in lines[start + 1:]:
        if not line.strip():
            continue
        depth = len(line) - len(line.lstrip())
        if depth < indent or (depth == indent and not line.lstrip().startswith("- ")):
            break
        if line.lstrip().startswith("- "):
            items.append(_scalar(line.strip()[2:]))
    return items


def pr_trigger(text: str) -> tuple[bool, list[str] | None]:
    """(runs on pull_request, its paths filter or None for every change) for a workflow file.

    A small reader for the block-style YAML these workflows use, so the Mac needs no PyYAML.
    Only on.pull_request.paths is read; pull_request_target does not count.
    """
    lines = [_strip_comment(line) for line in text.splitlines()]
    for i, line in enumerate(lines):
        m = YAML_KEY.match(line)
        if not m or m.group(1) or m.group(3) != "on":
            continue
        inline = m.group(4).strip()
        if inline:
            names = _flow_list(inline) if inline.startswith("[") else [_scalar(inline)]
            return "pull_request" in names, None
        body = _block(lines, i, 0)
        if not body:
            return False, None
        child = len(body[0]) - len(body[0].lstrip())
        if body[0].lstrip().startswith("- "):
            return "pull_request" in [_scalar(b.strip()[2:]) for b in body if b.strip().startswith("- ")], None
        for j, b in enumerate(body):
            k = YAML_KEY.match(b)
            if not k or len(k.group(1)) != child or k.group(3) != "pull_request":
                continue
            rest = k.group(4).strip()
            if rest and rest not in ("{}", "null", "~"):
                return True, None
            sub = _block(body, j, child)
            if not sub:
                return True, None
            grand = len(sub[0]) - len(sub[0].lstrip())
            for n, s in enumerate(sub):
                km = YAML_KEY.match(s)
                if not km or len(km.group(1)) != grand or km.group(3) != "paths":
                    continue
                val = km.group(4).strip()
                if val.startswith("["):
                    return True, _flow_list(val)
                return True, _sequence(sub, n, grand)
            return True, None
        return False, None
    return False, None


def profile_gaps(profile: dict, workflows: dict[str, str]) -> dict[str, tuple[str, str]]:
    """{workflow path: (level, problem)} where profile and workflow files disagree."""
    gaps: dict[str, tuple[str, str]] = {}
    listed = {w["path"]: w["paths"] for w in profile.get("workflows", [])}
    for path, expected in listed.items():
        if path not in workflows:
            gaps[path] = ("crit", "is in the profile but the workflow file is gone, so the gate waits for it forever")
            continue
        runs, actual = pr_trigger(workflows[path])
        if not runs:
            gaps[path] = ("crit", "is in the profile but no longer runs on pull_request, so the gate waits for it")
            continue
        if expected is None and actual is None:
            continue
        if expected is None or actual is None:
            what = "every change" if actual is None else "only some paths"
            gaps[path] = ("crit" if actual is not None else "warn",
                          f"runs on {what} but the profile says {'every change' if expected is None else 'some paths'}")
            continue
        extra = sorted(set(expected) - set(actual))
        missing = sorted(set(actual) - set(expected))
        if extra:
            gaps[path] = ("crit", "profile lists paths the workflow ignores, so the gate waits for a run that "
                                  "never starts: " + ", ".join(extra))
        elif missing:
            gaps[path] = ("warn", "workflow runs on paths the profile lacks, so the gate does not wait for it: "
                                  + ", ".join(missing))
    for path, text in workflows.items():
        if path in listed or path in GATE_IGNORED:
            continue
        runs, _ = pr_trigger(text)
        if runs:
            gaps[path] = ("warn", "runs on pull requests but is not in the profile, so the gate does not wait for it")
    return gaps
