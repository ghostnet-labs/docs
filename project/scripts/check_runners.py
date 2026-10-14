#!/usr/bin/env python3
"""Runner policy for Manet GitHub Actions workflows.

Keeps CI on Justin's self-hosted runners and keeps it from piling up stale
runs. Each rule names a failure that already happened once:

  hosted-runner     A job runs only on GitHub-hosted runners. Hosted minutes
                    are limited; on 2026-10-13 ~220 hosted jobs sat queued for
                    7+ hours. Same-repo work belongs on [self-hosted, ...] with
                    an ubuntu fallback for fork pull requests only.
  pr-concurrency    A pull_request workflow has no concurrency group with
                    cancel-in-progress, so every push leaves the previous
                    run going (firmware PR #42 held 12 board builds at once).
  hosted-cron       A schedule fires more than once an hour on a hosted
                    runner (the 15-minute auto-merge sweep made ~670 hosted
                    jobs a day across 7 repos).
  pinned-reusable   A job calls another repository's reusable workflow by a
                    branch or tag instead of a commit SHA, so its behaviour
                    (and runner choice) can change without a PR here.
  job-timeout       A job has no timeout-minutes, so a hung step holds a
                    runner for GitHub's 6-hour default.
  fork-pr-self-hosted
                    A workflow that runs on pull_request puts a job on a
                    self-hosted runner with no fork guard. A fork PR could then
                    run its own code on Justin's Macs. The runs-on must pick
                    self-hosted only when the PR head repo is this repo, e.g.
                    `${{ github.event.pull_request.head.repo.full_name ==
                    github.repository && fromJSON('["self-hosted", ...]') ||
                    'ubuntu-latest' }}`.

Exceptions live in project/ci/runner-allowlist.json with a reason, so each
one is reviewed in a docs PR. Usage:

  check_runners.py --repo NAME [--workflows DIR] [--allowlist FILE]
  check_runners.py --root DIR   # audit DIR/<repo>/.github/workflows for every repo
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
DEFAULT_ALLOWLIST = HERE.parent / "ci" / "runner-allowlist.json"
RULES = ("hosted-runner", "pr-concurrency", "hosted-cron", "pinned-reusable", "job-timeout",
         "fork-pr-self-hosted")
PR_EVENTS = ("pull_request", "pull_request_target")
SHA_RE = re.compile(r"@[0-9a-f]{40}$")


@dataclass(frozen=True)
class Finding:
    repo: str
    workflow: str
    job: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.repo}/{self.workflow} job {self.job}: {self.rule}: {self.detail}"


def _triggers(doc: dict) -> dict:
    # PyYAML (YAML 1.1) reads the bare key `on` as boolean True.
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {k: None for k in on}
    return on or {}


def _runs_on_text(runs_on) -> str:
    if isinstance(runs_on, dict):  # {group:, labels:}
        return json.dumps(runs_on)
    if isinstance(runs_on, list):
        return " ".join(str(x) for x in runs_on)
    return str(runs_on or "")


def is_self_hosted(runs_on) -> bool:
    """True when the job can run on a self-hosted runner.

    A fork-PR fallback expression such as
    `${{ head.repo.full_name == github.repository && fromJSON('["self-hosted", ...]') || 'ubuntu-latest' }}`
    counts as self-hosted: same-repo work goes to the Macs.
    """
    return "self-hosted" in _runs_on_text(runs_on)


def has_fork_guard(runs_on) -> bool:
    """True when runs-on compares the PR head repo with this repo.

    Matches the guard expression, not the exact spelling, so both
    `head.repo.full_name == github.repository` orders pass.
    """
    text = _runs_on_text(runs_on)
    return "head.repo.full_name" in text and "github.repository" in text


def _cancels(conc) -> bool:
    if isinstance(conc, dict):
        cip = conc.get("cancel-in-progress")
        return cip is True or (isinstance(cip, str) and cip.strip() not in ("", "false"))
    return False


def cron_is_subhourly(expr: str) -> bool:
    minute = expr.split()[0]
    if minute == "*":
        return True
    if minute.startswith("*/"):
        return int(minute[2:]) < 60
    return "," in minute or "-" in minute


def check_workflow(repo: str, name: str, doc: dict) -> list[Finding]:
    out: list[Finding] = []
    triggers = _triggers(doc)
    on_pr = any(e in triggers for e in PR_EVENTS)
    crons = [c.get("cron", "") for c in (triggers.get("schedule") or []) if isinstance(c, dict)]
    wf_cancels = _cancels(doc.get("concurrency"))
    for job_id, job in (doc.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        uses = job.get("uses")
        if uses:
            if not uses.startswith("./") and not SHA_RE.search(uses):
                out.append(Finding(repo, name, job_id, "pinned-reusable", f"calls {uses}"))
            # Runner choice belongs to the called workflow, which is checked itself.
            hosted = not uses.startswith("./")
        else:
            hosted = not is_self_hosted(job.get("runs-on"))
            if hosted:
                out.append(Finding(repo, name, job_id, "hosted-runner",
                                   f"runs-on {_runs_on_text(job.get('runs-on'))!r}"))
            if on_pr and is_self_hosted(job.get("runs-on")) and not has_fork_guard(job.get("runs-on")):
                out.append(Finding(repo, name, job_id, "fork-pr-self-hosted",
                                   "pull request code can run on a self-hosted runner "
                                   f"(runs-on {_runs_on_text(job.get('runs-on'))!r} has no fork guard)"))
            if "timeout-minutes" not in job:
                out.append(Finding(repo, name, job_id, "job-timeout", "no timeout-minutes"))
        if on_pr and not wf_cancels and not _cancels(job.get("concurrency")):
            out.append(Finding(repo, name, job_id, "pr-concurrency",
                               "pull request runs are not cancelled by a newer push"))
        if hosted and any(cron_is_subhourly(c) for c in crons):
            out.append(Finding(repo, name, job_id, "hosted-cron",
                               f"schedule {crons} fires more than hourly on a hosted runner"))
    return out


def load_workflows(path: Path):
    for f in sorted(list(path.glob("*.yml")) + list(path.glob("*.yaml"))):
        doc = yaml.safe_load(f.read_text())
        if isinstance(doc, dict) and "jobs" in doc:
            yield f.name, doc


def check_repo(repo: str, workflows_dir: Path) -> list[Finding]:
    found: list[Finding] = []
    for name, doc in load_workflows(workflows_dir):
        found.extend(check_workflow(repo, name, doc))
    return found


def load_allowlist(path: Path) -> list[dict]:
    entries = json.loads(path.read_text())["entries"]
    for e in entries:
        missing = {"repo", "workflow", "job", "rules", "reason"} - e.keys()
        if missing:
            raise ValueError(f"allowlist entry {e} lacks {sorted(missing)}")
        bad = set(e["rules"]) - set(RULES)
        if bad:
            raise ValueError(f"allowlist entry {e} names unknown rules {sorted(bad)}")
        if not e["reason"].strip():
            raise ValueError(f"allowlist entry {e} has an empty reason")
    return entries


def _matches(entry: dict, f: Finding) -> bool:
    return (entry["repo"] == f.repo
            and fnmatch.fnmatchcase(f.workflow, entry["workflow"])
            and fnmatch.fnmatchcase(f.job, entry["job"])
            and f.rule in entry["rules"])


def apply_allowlist(findings, entries, repos):
    """Split findings into (violations, allowed) and list allowlist entries no
    finding used, for the repos that were checked."""
    used: set[int] = set()
    violations, allowed = [], []
    for f in findings:
        hit = next((i for i, e in enumerate(entries) if _matches(e, f)), None)
        if hit is None:
            violations.append(f)
        else:
            used.add(hit)
            allowed.append(f)
    unused = [e for i, e in enumerate(entries) if i not in used and e["repo"] in repos]
    return violations, allowed, unused


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="repository name, e.g. firmware")
    ap.add_argument("--workflows", default=".github/workflows", help="workflow directory for --repo")
    ap.add_argument("--root", help="directory holding one checkout per repo (audit mode)")
    ap.add_argument("--allowlist", default=str(DEFAULT_ALLOWLIST))
    args = ap.parse_args(argv)
    entries = load_allowlist(Path(args.allowlist))
    findings: list[Finding] = []
    repos: list[str] = []
    if args.root:
        for d in sorted(Path(args.root).iterdir()):
            wf = d / ".github" / "workflows"
            if wf.is_dir():
                repos.append(d.name)
                findings += check_repo(d.name, wf)
    elif args.repo:
        repos.append(args.repo)
        findings = check_repo(args.repo, Path(args.workflows))
    else:
        ap.error("pass --repo or --root")
    violations, allowed, unused = apply_allowlist(findings, entries, repos)
    print(f"Checked {', '.join(repos)}: {len(violations)} violation(s), "
          f"{len(allowed)} allowlisted finding(s).")
    for e in unused:
        # A fixed exception should leave the allowlist; say so without failing.
        msg = f"allowlist entry no longer needed: {e['repo']}/{e['workflow']} job {e['job']} {e['rules']}"
        print(f"::warning::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"warning: {msg}")
    for v in violations:
        print(f"::error::{v}" if os.environ.get("GITHUB_ACTIONS") else f"error: {v}")
    if violations:
        print("Fix the workflow, or add a reviewed exception to project/ci/runner-allowlist.json.")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
