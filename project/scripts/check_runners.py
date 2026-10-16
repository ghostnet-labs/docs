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
                    run its own code on Justin's Macs or the ARC runners. The
                    runs-on must pick self-hosted only when the PR head repo is
                    this repo and fall back to a GitHub-hosted label. Three forms
                    pass (HEAD is `github.event.pull_request.head.repo.full_name
                    == github.repository`, either way round):
                      `${{ HEAD && fromJSON('["self-hosted", ...]') ||
                      'ubuntu-latest' }}`
                      `${{ github.event_name == 'pull_request' && HEAD &&
                      fromJSON('["self-hosted", ...]') || 'ubuntu-latest' }}`
                      `${{ (github.event_name != 'pull_request' || HEAD) &&
                      fromJSON('["self-hosted", ...]') || 'ubuntu-latest' }}`
                    Reusable (workflow_call) workflows run with their caller's
                    event, so their self-hosted jobs need a guard as well.
                    The exact ARC routes ARC_PR_ONLY_FALLBACK and
                    ARC_FORK_FALLBACK below pass the same way. The event forms
                    let push runs use self-hosted runners, so they pass only when
                    every trigger is pull_request, push, schedule,
                    workflow_dispatch or merge_group.

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
# ARC scale sets route by their exact name rather than the self-hosted label.
ARC_RUNNER_LABELS = frozenset({"ghostnet-linux-arm64"})
# Only this reviewed expression sends trusted events to ARC and forks to hosted.
ARC_FORK_FALLBACK = (
    "${{ (github.event_name != 'pull_request' || "
    "github.event.pull_request.head.repo.full_name == github.repository) "
    "&& 'ghostnet-linux-arm64' || 'ubuntu-latest' }}"
)

# Publishing/deletion jobs can keep their secrets on hosted runners.
ARC_PR_ONLY_FALLBACK = (
    "${{ github.event_name == 'pull_request' && "
    "github.event.pull_request.head.repo.full_name == github.repository "
    "&& 'ghostnet-linux-arm64' || 'ubuntu-latest' }}"
)


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


def _expression_tokens(value: str) -> str:
    # Normalize layout without changing quoted runner names or event values.
    return re.sub(r"'(?:[^']|'')*'|\s+",
                  lambda match: match[0] if match[0].startswith("'") else "", value)


def is_self_hosted(runs_on) -> bool:
    """True when the job can run on a self-hosted runner.

    A fork-PR fallback expression such as
    `${{ head.repo.full_name == github.repository && fromJSON('["self-hosted", ...]') || 'ubuntu-latest' }}`
    counts as self-hosted: same-repo work goes to the Macs. ARC scale-set
    names are recognized as exact static labels or the canonical trusted-event
    ARC/fork-hosted fallback. Other dynamic ARC routes need policy review.
    """
    if "self-hosted" in _runs_on_text(runs_on):
        return True
    if isinstance(runs_on, str) and _expression_tokens(runs_on) in {
        _expression_tokens(ARC_FORK_FALLBACK), _expression_tokens(ARC_PR_ONLY_FALLBACK)
    }:
        return True
    labels = runs_on.get("labels") if isinstance(runs_on, dict) else runs_on
    if isinstance(labels, str):
        labels = [labels]
    return isinstance(labels, list) and any(
        isinstance(label, str) and label in ARC_RUNNER_LABELS for label in labels
    )


_HEAD_IS_REPO = (r"(?:github\.event\.pull_request\.head\.repo\.full_name == github\.repository"
                 r"|github\.repository == github\.event\.pull_request\.head\.repo\.full_name)")
# The label the guard selects for same-repository work must be self-hosted, and
# the fallback for everything else a GitHub-hosted runner. Checking both stops
# an inverted guard (`head == repo && 'ubuntu-latest' || 'self-hosted'`).
_PICK = r"(?:fromJSON\('(?P<sel>[^']*)'\)|'(?P<lit>[^']*)')"
_FALLBACK = r"'(?P<fb>(?:ubuntu|macos|windows)-[A-Za-z0-9._-]+)'"
# `${{ HEAD && self-hosted-labels || 'hosted' }}`: forks never get the Macs.
_GUARD_PLAIN = re.compile(r"^\$\{\{ " + _HEAD_IS_REPO + " && " + _PICK + r" \|\| " + _FALLBACK + r" \}\}$")
# `${{ (event_name != 'pull_request' || HEAD) && ... }}`: lets push events use
# the Macs. Only safe when every trigger is one where event_name cannot be a
# pull_request_target-style event (see SAFE_FOR_EVENT_GUARD).
_GUARD_EVENT = re.compile(r"^\$\{\{ \(github\.event_name != 'pull_request' \|\| " + _HEAD_IS_REPO
                          + r"\) && " + _PICK + r" \|\| " + _FALLBACK + r" \}\}$")
# `${{ event_name == 'pull_request' && HEAD && ... }}`: only a same-repository
# pull_request run gets the Macs; push, delete and every other event stay on the
# hosted fallback. Safe whatever else the workflow triggers on, because a
# pull_request_target event never matches the first term.
_GUARD_PR_ONLY = re.compile(r"^\$\{\{ github\.event_name == 'pull_request' && " + _HEAD_IS_REPO + " && " + _PICK
                            + r" \|\| " + _FALLBACK + r" \}\}$")
SAFE_FOR_EVENT_GUARD = frozenset({"pull_request", "push", "schedule", "workflow_dispatch", "merge_group"})


def _guard_picks_self_hosted(m: "re.Match[str]") -> bool:
    sel = m.group("sel") or m.group("lit") or ""
    return "self-hosted" in sel or any(label in sel for label in ARC_RUNNER_LABELS)


def has_fork_guard(runs_on, allow_event_form: bool = True) -> bool:
    """True when runs-on is a recognised fork guard.

    Only the exact forms in _GUARD_PLAIN, _GUARD_PR_ONLY and _GUARD_EVENT pass,
    plus the reviewed ARC routes (ARC_PR_ONLY_FALLBACK always, ARC_FORK_FALLBACK
    like the event form). Anything else, such as an inverted `!=` or a stray
    `||`, is rejected rather than guessed at. The guard must select self-hosted
    labels for same-repository work and a GitHub-hosted label otherwise. Pass
    allow_event_form=False for workflows with any trigger outside
    SAFE_FOR_EVENT_GUARD, which then only accept the plain and PR-only forms.
    """
    if not isinstance(runs_on, str):
        return False
    tokens = _expression_tokens(runs_on)
    if tokens == _expression_tokens(ARC_PR_ONLY_FALLBACK):
        return True
    if tokens == _expression_tokens(ARC_FORK_FALLBACK):
        return allow_event_form
    text = " ".join(runs_on.split())
    m = _GUARD_PLAIN.match(text) or _GUARD_PR_ONLY.match(text)
    if m is None and allow_event_form:
        m = _GUARD_EVENT.match(text)
    return m is not None and _guard_picks_self_hosted(m)


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
    # A reusable workflow runs with its caller's event, which can be a fork PR,
    # so its self-hosted jobs need a guard too. workflow_call is outside
    # SAFE_FOR_EVENT_GUARD, so only the plain and PR-only forms pass there.
    called = "workflow_call" in triggers
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
            if ((on_pr or called) and is_self_hosted(job.get("runs-on"))
                    and not has_fork_guard(job.get("runs-on"), set(triggers) <= SAFE_FOR_EVENT_GUARD)):
                out.append(Finding(repo, name, job_id, "fork-pr-self-hosted",
                                   "pull request code can run on a self-hosted runner "
                                   f"(runs-on {_runs_on_text(job.get('runs-on'))!r} has no fork guard)"))
            if "timeout-minutes" not in job:
                out.append(Finding(repo, name, job_id, "job-timeout", "no timeout-minutes"))
        if on_pr and not wf_cancels and not _cancels(job.get("concurrency")):
            out.append(Finding(repo, name, job_id, "pr-concurrency",
                               "pull request runs are not cancelled by a newer push"))
        # The PR-only route deliberately uses hosted runners for scheduled events.
        pr_only_route = job.get("runs-on")
        scheduled_hosted = (isinstance(pr_only_route, str) and
                            re.sub(r"\s+", "", pr_only_route) ==
                            re.sub(r"\s+", "", ARC_PR_ONLY_FALLBACK))
        if (hosted or scheduled_hosted) and any(cron_is_subhourly(c) for c in crons):
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

