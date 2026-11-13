#!/usr/bin/env python3
"""Alert when GitHub Actions has quietly stopped in a ghostnet-labs repo.

Read-only. Python 3 standard library only; reuses the API client in stale_runs.py.
Exit status 0 means every repo looks healthy, 1 means at least one finding,
2 means no token, 3 means an API error stopped the scan.

Why it exists: luci sat for four days (2026-10-30 to 2026-11-03) with its
workflows switched off. Its open PR showed no checks at all, nobody noticed,
and nothing in the org looked at it. Forks lose their workflows this way:
GitHub lists the workflow as "disabled_fork" or "disabled_inactivity" until
someone clicks the enable button.

Checks, per repo:

  actions-off      the repository-level Actions permission is off
                   (needs a token with repository administration; skipped
                   with a note when the token cannot read it)
  workflow-off     a workflow whose state is not "active"
                   (disabled_fork, disabled_inactivity, disabled_manually)
  pr-no-checks     a ready (non-draft) open PR whose head commit has no check
                   runs and no commit statuses, older than --grace-minutes
  runs-stale       open PRs exist but the newest workflow run in the repo is
                   older than --stale-hours (default 3)
  runs-held        a workflow run queued --held-minutes (15) or longer that
                   GitHub has not given a single job. A runner shortage still
                   creates the jobs (they wait as queued); no jobs at all means
                   GitHub is holding the run, as with the fork's "enable
                   workflows" banner on 2026-11-06 (firmware #92 sat 2 h). The
                   workflow list still says "active" and the PR still has
                   check suites, so none of the checks above see it, and it
                   needs no admin token.
                   PR runs on a commit that is no longer an open PR's head
                   are ignored: nothing waits on them.

Examples:

  python3 actions_guard.py                 # table, exit 1 on any finding
  python3 actions_guard.py --json          # machine-readable
  python3 actions_guard.py --repos luci    # one repo

Run it from the same LaunchAgent as stale_runs.py (every 15 minutes is fine:
ETags make a quiet org nearly free) and page on a non-zero exit. The cloud
live-PR report can run the same four checks through the GitHub connector:
workflow state, check runs on each ready PR head, newest run time.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stale_runs as sr  # noqa: E402

ORG = sr.ORG


HELD = timedelta(minutes=15)


def _superseded(gh, full: str, run: dict, created: datetime) -> bool:
    """A newer run of the same workflow on the same commit replaced this one. packages #42's
    frozen 02:30Z re-run (GitHub refuses to cancel a re-run that never queued) kept this alert
    crit after a fresh dispatch of the same workflow was already building that commit."""
    sha = run.get("head_sha")
    if not sha:
        return False
    same = (lambda r: r.get("workflow_id") == run["workflow_id"]) if run.get("workflow_id") else (
        lambda r: r.get("name") == run.get("name"))
    try:
        others = gh.get(f"{full}/actions/runs?head_sha={sha}&per_page=20").get("workflow_runs", [])
    except RuntimeError:
        return False  # can't tell, so keep alerting
    for other in others:
        when = sr.parse_ts(other.get("created_at"))
        if other.get("id") != run.get("id") and same(other) and when is not None and when > created:
            return True
    return False


def run_as_check(run: dict) -> dict:
    """A workflow run in the shape of a check run (name, status, conclusion, times)."""
    done = run.get("status") == "completed"
    return {"id": run.get("id"), "name": run.get("name") or run.get("path") or "?",
            "status": "completed" if done else "in_progress", "conclusion": run.get("conclusion") if done else None,
            "started_at": run.get("run_started_at") or run.get("created_at"),
            "completed_at": run.get("updated_at") if done else None, "html_url": run.get("html_url")}


def head_checks(gh, full: str, sha: str, per_page: int = 100) -> tuple[list[dict], int, bool]:
    """(check runs, total count, fell back) for one commit.

    Fine-grained tokens have no Checks permission, so on a private repo (setup)
    the check-runs API answers 403 "Resource not accessible by personal access
    token". Then the commit's workflow runs (Actions: Read-only) stand in, shaped
    like check runs. They miss checks posted by non-Actions apps; commit statuses
    are read separately and still count.
    """
    try:
        page = gh.get(f"{full}/commits/{sha}/check-runs?per_page={per_page}")
        return page.get("check_runs", []), page.get("total_count", 0), False
    except RuntimeError as err:
        if "HTTP 403" not in str(err):
            raise
    page = gh.get(f"{full}/actions/runs?head_sha={sha}&per_page={per_page}")
    runs = [run_as_check(r) for r in page.get("workflow_runs", [])]
    return runs, page.get("total_count", len(runs)), True


def check_repo(gh, repo: str, now: datetime, grace: timedelta, stale: timedelta,
               held: timedelta = HELD) -> list[dict]:
    """Return findings for one repo. `gh` needs only a .get(path) method."""
    full = f"/repos/{ORG}/{repo}"
    findings: list[dict] = []

    def add(kind: str, detail: str, **extra) -> None:
        findings.append({"repo": repo, "kind": kind, "detail": detail, **extra})

    try:
        perms = gh.get(f"{full}/actions/permissions")
        if perms.get("enabled") is False:
            add("actions-off", "Actions is disabled for this repository")
    except RuntimeError as err:
        if "HTTP 403" not in str(err) and "HTTP 404" not in str(err):
            raise
        # Token lacks repository administration; the workflow list still shows it.

    workflows = gh.get(f"{full}/actions/workflows?per_page=100").get("workflows", [])
    for wf in workflows:
        if wf.get("state") != "active":
            add("workflow-off", f"workflow '{wf.get('name')}' is {wf.get('state')}",
                workflow=wf.get("name"), state=wf.get("state"), path=wf.get("path", ""))

    prs = gh.get(f"{full}/pulls?state=open&per_page=100")
    for pull in prs:
        if pull.get("draft"):
            continue
        updated = sr.parse_ts(pull.get("updated_at")) or now
        created = sr.parse_ts(pull.get("created_at")) or now
        sha = pull["head"]["sha"]
        # The head commit's age is not in the PR payload; use the later of the PR's
        # creation and last update so a fresh push is not flagged before checks start.
        age = now - max(created, updated)
        if age < grace:
            continue
        _, checks, _ = head_checks(gh, full, sha, per_page=1)
        if checks:
            continue
        statuses = gh.get(f"{full}/commits/{sha}/status").get("total_count", 0)
        if statuses:
            continue
        add("pr-no-checks", f"PR #{pull['number']} has no checks or statuses on {sha[:7]}",
            pr=pull["number"], sha=sha)

    queued = gh.get(f"{full}/actions/runs?status=queued&per_page=50").get("workflow_runs", [])
    # A PR run on a commit that is no longer any open PR's head is left over from an
    # old head or a closed PR; nothing waits on it. Firmware #92's 00:32Z re-runs of an
    # old head stayed held (GitHub refuses to cancel a re-run that never queued) after
    # the PR moved on and built fine, and kept this alert red for hours.
    heads = {pull["head"]["sha"] for pull in prs}
    stuck = []
    for run in queued:
        created = sr.parse_ts(run.get("created_at"))
        if created is None or now - created < held:
            continue
        if run.get("event") in sr.PR_EVENTS and run.get("head_sha") not in heads:
            continue
        if gh.get(f"{full}/actions/runs/{run['id']}/jobs?per_page=1").get("total_count", 0) == 0:
            if not _superseded(gh, full, run, created):
                stuck.append((created, run))
    if stuck:
        stuck.sort(key=lambda x: x[0])
        oldest = int((now - stuck[0][0]).total_seconds() // 60)
        add("runs-held", f"{len(stuck)} queued run(s) have no jobs, oldest {oldest} min "
                         f"({stuck[0][1].get('name', '?')})",
            runs=[r.get("html_url", "") for _, r in stuck[:3]])

    if prs:
        runs = gh.get(f"{full}/actions/runs?per_page=1").get("workflow_runs", [])
        newest = sr.parse_ts(runs[0]["created_at"]) if runs else None
        if newest is None or now - newest > stale:
            hours = "never" if newest is None else f"{(now - newest).total_seconds() / 3600:.1f}h ago"
            add("runs-stale", f"{len(prs)} open PR(s) but the newest workflow run was {hours}",
                open_prs=len(prs))
    return findings


def render(findings: list[dict], repos: list[str]) -> str:
    if not findings:
        return f"OK: Actions looks healthy in {', '.join(repos)}"
    width = max(len(f["repo"]) for f in findings)
    lines = [f"{f['repo']:<{width}}  {f['kind']:<13}  {f['detail']}" for f in findings]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--repos", default=",".join(sr.REPOS), help="comma-separated repo names")
    p.add_argument("--grace-minutes", type=float, default=20.0,
                   help="a ready PR younger than this is not expected to have checks yet")
    p.add_argument("--stale-hours", type=float, default=3.0,
                   help="newest-run age that counts as stale while PRs are open")
    p.add_argument("--held-minutes", type=float, default=15.0,
                   help="a queued run with no jobs this long is held by GitHub")
    p.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = p.parse_args(argv)

    token = sr.read_token()
    if not token:
        print(f"No token: set STALE_RUNS_TOKEN or write one to {sr.TOKEN_FILE}", file=sys.stderr)
        return 2
    gh = sr.GitHub(token)
    repos = [r.strip() for r in args.repos.split(",") if r.strip()]
    now = sr.utcnow()
    findings: list[dict] = []
    try:
        for repo in repos:
            findings += check_repo(gh, repo, now, timedelta(minutes=args.grace_minutes),
                                   timedelta(hours=args.stale_hours), timedelta(minutes=args.held_minutes))
    except RuntimeError as err:
        print(f"error: {err}", file=sys.stderr)
        gh.save()
        return 3
    gh.save()
    if args.json:
        print(json.dumps({"at": now.isoformat(), "findings": findings}, indent=1))
    else:
        print(f"{now:%Y-%m-%d %H:%MZ}  api calls {gh.calls} (+{gh.not_modified} free 304s)")
        print(render(findings, repos))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
