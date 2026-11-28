#!/usr/bin/env python3
"""Give workflow jobs the GitHub-hosted fallback for when the Mac Studio is offline.

  add_studio_fallback.py WORKFLOW --sha DOCS_SHA JOB=POOL [JOB=POOL ...] [--studio-if EXPR]

POOL is mac, arc or build. The script adds a `studio` job (one step: the docs
action .github/actions/studio-runners pinned at DOCS_SHA, on the pinned hosted
image) and, for each named job:

  * puts `needs.studio.outputs.POOL != 'false' && ` in front of the
    self-hosted pick of its fork-guarded runs-on, so the job goes to the
    guard's hosted fallback while that pool is offline;
  * adds studio to its needs, and wraps its `if:` in `!cancelled() && ...` so a
    failed check still runs the job on its usual route (never skips a gate).
    A job that already had needs keeps requiring them: `needs.X.result ==
    'success'` for each.

Re-running it with a new --sha only moves the action pin. Edits text in place
so comments and layout stay; check the diff. Runner policy (check_runners.py)
accepts the resulting routes.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HOSTED_IMAGE = "ubuntu-24.04"
ACTION = "ghostnet-labs/docs/.github/actions/studio-runners"
ACTION_PIN = re.compile(re.escape(ACTION) + r"@[0-9a-f]{40}")
PICK = re.compile(r"&& (fromJSON\('\[|'ghostnet-)")
TERM = re.compile(r"needs\.studio\.outputs\.(mac|arc|build) != 'false' && ")


def studio_job(sha: str, studio_if: str | None) -> str:
    cond = f"    if: {studio_if}\n" if studio_if else ""
    return (
        "  studio:\n"
        "    # Which Mac Studio runner pools are online. While one is offline the jobs\n"
        "    # below use their GitHub-hosted fallback (docs tools/studio-runners).\n"
        "    name: Studio runners\n"
        f"{cond}"
        f"    runs-on: {HOSTED_IMAGE}\n"
        "    timeout-minutes: 5\n"
        "    permissions:\n"
        "      actions: read\n"
        "    outputs:\n"
        "      mac: ${{ steps.pick.outputs.mac }}\n"
        "      arc: ${{ steps.pick.outputs.arc }}\n"
        "      build: ${{ steps.pick.outputs.build }}\n"
        "    steps:\n"
        "      - id: pick\n"
        f"        uses: {ACTION}@{sha}\n"
        "        with:\n"
        "          runner-token: ${{ secrets.RUNNER_READ_TOKEN }}\n"
    )


def job_span(lines: list[str], job: str) -> tuple[int, int]:
    start = next((i for i, line in enumerate(lines) if line.rstrip() == f"  {job}:"), None)
    if start is None:
        raise SystemExit(f"job {job} not found")
    end = start + 1
    while end < len(lines) and (lines[end].startswith("    ") or not lines[end].strip()):
        end += 1
    return start, end


def unwrap(expr: str) -> str:
    expr = expr.strip()
    m = re.fullmatch(r"\$\{\{\s*(.*?)\s*\}\}", expr)
    if m:
        return m.group(1)
    if len(expr) >= 2 and expr[0] == expr[-1] and expr[0] in "'\"":
        return expr[1:-1]
    return expr


def wire_job(lines: list[str], job: str, pool: str) -> None:
    start, end = job_span(lines, job)
    body = lines[start + 1:end]
    ro = next((i for i, line in enumerate(body) if line.startswith("    runs-on: ")), None)
    if ro is None:
        raise SystemExit(f"job {job} has no one-line runs-on")
    if not TERM.search(body[ro]):
        new, n = PICK.subn(lambda m: f"&& needs.studio.outputs.{pool} != 'false' && {m.group(1)}", body[ro], count=1)
        if n != 1:
            raise SystemExit(f"job {job}: no fork-guarded self-hosted pick in {body[ro].strip()}")
        body[ro] = new
    needs_i = next((i for i, line in enumerate(body) if line.startswith("    needs: ")), None)
    if_i = next((i for i, line in enumerate(body) if line.startswith("    if: ")), None)
    old_needs: list[str] = []
    if needs_i is not None:
        raw = body[needs_i].split(":", 1)[1].strip()
        old_needs = [n.strip() for n in raw.strip("[]").split(",") if n.strip()]
    if "studio" not in old_needs:
        others = list(old_needs)
        conds = ["!cancelled()"] + [f"needs.{n}.result == 'success'" for n in others]
        if if_i is not None:
            orig = unwrap(body[if_i].split(":", 1)[1])
            if orig and orig not in ("!cancelled()", "always()"):
                conds.append(f"({orig})" if "||" in orig else orig)
        line_needs = f"    needs: [{', '.join(others + ['studio'])}]\n" if others else "    needs: studio\n"
        line_if = "    if: ${{ " + " && ".join(conds) + " }}\n"
        if needs_i is not None:
            body[needs_i] = line_needs
        if if_i is not None:
            body[if_i] = line_if
        anchor = next(i for i, line in enumerate(body) if line.startswith("    runs-on: "))
        insert = []
        if needs_i is None:
            insert.append(line_needs)
        if if_i is None:
            insert.append(line_if)
        body[anchor:anchor] = insert
    lines[start + 1:end] = body


def apply(text: str, sha: str, jobs: dict[str, str], studio_if: str | None = None) -> str:
    if ACTION_PIN.search(text):
        text = ACTION_PIN.sub(f"{ACTION}@{sha}", text)
    else:
        m = re.search(r"^jobs:\n", text, re.MULTILINE)
        if m is None:
            raise SystemExit("no jobs: block")
        text = text[:m.end()] + studio_job(sha, studio_if) + text[m.end():]
    lines = text.splitlines(keepends=True)
    for job, pool in jobs.items():
        wire_job(lines, job, pool)
    return "".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workflow", type=Path)
    ap.add_argument("--sha", required=True, help="docs commit that holds the studio-runners action")
    ap.add_argument("--studio-if", help="if: for the studio job, e.g. the gate's \"github.event.action != 'closed'\"")
    ap.add_argument("jobs", nargs="*", help="JOB=POOL (mac, arc or build)")
    args = ap.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.sha):
        ap.error("--sha must be a full commit sha")
    jobs = {}
    for spec in args.jobs:
        job, _, pool = spec.partition("=")
        if pool not in ("mac", "arc", "build"):
            ap.error(f"{spec}: POOL must be mac, arc or build")
        jobs[job] = pool
    args.workflow.write_text(apply(args.workflow.read_text(), args.sha, jobs, args.studio_if))
    return 0


if __name__ == "__main__":
    sys.exit(main())
