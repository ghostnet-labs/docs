#!/usr/bin/env python3
"""Fail-closed Manet CI gate and protected auto-merge, using only GitHub metadata."""
import argparse
import base64
import http.client
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

from workflow_triggers import pr_trigger, profile_gaps

GATE = "Manet merge gate"
AUTOMATION = "Handle passing PRs"
MAX_GATE_ATTEMPTS = 3
# A cancelled current-head run is re-run at most this many attempts in total, so a
# workflow that keeps getting cancelled (or a person who keeps cancelling it) cannot loop.
MAX_RERUN_ATTEMPTS = 3
HOLD_LABELS = {"hold", "do-not-merge", "blocked"}
# Adds labels only and runs from the base branch, so it is not a test to wait on.
LABELER = "Pull Request Labeler"
# Cross-repo audit of default branches. A workflow_dispatch on a PR branch
# attaches it to that head SHA, but it does not test the PR's diff.
AUDIT = "Audit runner policy"
# Firmware workflows and jobs that build only when a ci:kernel:* or ci:target:* label
# is added. Every other label event (hold, for one) skips them. A skipped run tested
# nothing, so it is ignored rather than passed: an earlier real run still decides.
LABEL_WORKFLOWS = {".github/workflows/label-kernel.yml", ".github/workflows/label-target.yml"}
LABEL_BUILDS = {"Build all affected Kernels from defined label", "Build target from defined label"}


def matches(path, pattern):
    pieces = []
    i = 0
    while i < len(pattern):
        if pattern[i:i + 3] == "**/":
            pieces.append("(?:.*/)?")
            i += 3
        elif pattern[i:i + 2] == "**":
            pieces.append(".*")
            i += 2
        elif pattern[i] == "*":
            pieces.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            pieces.append("[^/]")
            i += 1
        else:
            pieces.append(re.escape(pattern[i]))
            i += 1
    return re.fullmatch("".join(pieces), path) is not None


def needs_external_build(profile, files):
    return bool(profile.get("externalBuild")) and any(
        not (f.endswith(".md") or f.startswith(".github/") or f == ".gitignore")
        for f in files
    )


def evaluate(profile, files, runs, sha, number):
    """Return blockers; missing/old/queued/failed/cancelled CI can never pass."""
    required = {w["path"] for w in profile["workflows"]
                if w["paths"] is None or any(matches(f, p) for f in files for p in w["paths"])}
    latest = {}
    for run in runs:
        if run["head_sha"] != sha or run["event"] != "pull_request":
            continue
        if number not in [p["number"] for p in run.get("pull_requests", [])]:
            continue
        path = run["path"].split("@")[0]
        if path.endswith("manet-merge-gate.yml"):
            continue
        if path in LABEL_WORKFLOWS and run["status"] == "completed" and run["conclusion"] == "skipped":
            continue
        previous = latest.get(path)
        if previous is None or (run["id"], run.get("run_attempt", 1)) > (previous["id"], previous.get("run_attempt", 1)):
            latest[path] = run
    blockers = []
    for path in sorted(required | latest.keys()):
        run = latest.get(path)
        if not run:
            blockers.append(f"Missing applicable workflow: {path}")
        elif run["status"] != "completed" or run["conclusion"] != "success":
            blockers.append(f"{path}: {run['status']}/{run.get('conclusion')}")
    if needs_external_build(profile, files):
        blockers.append("Package changes need a current-head integration build; this feed has no build CI yet")
    return blockers


READ_ATTEMPTS = 5
RETRY_BASE_DELAY = 2
TRANSIENT_ERRORS = (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError)


def _transient(error):
    """Connection drops, short reads and timeouts, plus GitHub 5xx/429 responses."""
    if isinstance(error, urllib.error.HTTPError):
        return error.code == 429 or error.code >= 500
    return True


class API:
    def __init__(self, token):
        self.token = token

    def call(self, path, data=None, method=None):
        url = path if path.startswith("https://api.github.com/") else "https://api.github.com/" + path
        request = urllib.request.Request(url, data=None if data is None else json.dumps(data).encode(),
            method=method, headers={"Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json"})
        # Only reads are retried: replaying a write after a dropped connection could act twice.
        attempts = READ_ATTEMPTS if request.get_method() == "GET" else 1
        for attempt in range(1, attempts + 1):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    body = response.read()
                return json.loads(body) if body else {}
            except TRANSIENT_ERRORS as error:
                if attempt == attempts or not _transient(error):
                    raise
                time.sleep(RETRY_BASE_DELAY * 2 ** (attempt - 1))

    def pages(self, path, key=None):
        results = []
        page = 1
        while True:
            data = self.call(path + ("&" if "?" in path else "?") + f"per_page=100&page={page}")
            items = data[key] if key else data
            results.extend(items)
            if len(items) < 100:
                return results
            page += 1


def _external_evidence(body):
    urls = re.findall(r"(?im)^External-Integration-PR:\s*(https://github\.com/[\w.-]+/[\w.-]+/pull/\d+)\s*$", body or "")
    commits = re.findall(r"(?im)^External-Integration-Commit:\s*([0-9a-f]{40})\s*$", body or "")
    if len(urls) != 1 or len(commits) != 1:
        return None
    return urls[0], commits[0]


def external_build_blockers(api, repo, pr, files, profile):
    if not needs_external_build(profile, files):
        return []
    evidence = _external_evidence(pr.get("body"))
    if not evidence:
        return ["External integration evidence is missing or ambiguous"]
    url, integration_commit = evidence
    owner, name, _, number = url.removeprefix("https://github.com/").split("/")
    integration_repo = f"{owner}/{name}"
    expected_repo = profile.get("externalBuildRepo")
    if expected_repo and integration_repo != expected_repo:
        return [f"External integration PR must be in {expected_repo}"]

    comparison = api.call(f"repos/{repo}/compare/{pr['head']['sha']}...{integration_commit}")
    if comparison.get("status") not in {"ahead", "identical"}:
        return ["External integration commit does not contain the current package PR head"]

    integration_pr = api.call(f"repos/{integration_repo}/pulls/{number}")
    if integration_pr.get("draft"):
        return ["External integration PR is still a draft"]
    integration_sha = integration_pr["head"]["sha"]
    pin_path = profile.get("externalBuildPinPath")
    if pin_path:
        pinned = api.call(f"repos/{integration_repo}/contents/{pin_path}?ref={integration_sha}")
        text = base64.b64decode(pinned["content"]).decode()
        if not re.search(rf"\^{re.escape(integration_commit)}(?:\s|$)", text, re.MULTILINE):
            return [f"External integration PR current head does not pin {integration_commit}"]

    checks = api.pages(f"repos/{integration_repo}/commits/{integration_sha}/check-runs", "check_runs")
    blockers = ["External integration: " + b for b in check_blockers(checks)]
    gates = [c for c in checks if c["name"] == GATE and c["app"]["id"] == 15368]
    if not gates or max(gates, key=rank)["conclusion"] != "success":
        blockers.append("External integration: current-head Manet merge gate has not passed")
    status = api.call(f"repos/{integration_repo}/commits/{integration_sha}/status")
    if status["statuses"] and status["state"] != "success":
        blockers.append("External integration: commit status has not passed")
    return blockers


def snapshot(api, repo, number, profile):
    pr = api.call(f"repos/{repo}/pulls/{number}")
    records = api.pages(f"repos/{repo}/pulls/{number}/files")
    files = [f["filename"] for f in records]
    files.extend(f["previous_filename"] for f in records if "previous_filename" in f)
    runs = api.pages(f"repos/{repo}/actions/runs?head_sha={pr['head']['sha']}&event=pull_request", "workflow_runs")
    blockers = evaluate(profile, files, runs, pr["head"]["sha"], number)
    blockers.extend(profile_blockers(api, repo, pr["head"]["sha"], records, profile))
    if needs_external_build(profile, files):
        blockers = [b for b in blockers if not b.startswith("Package changes need a current-head integration build")]
        blockers.extend(external_build_blockers(api, repo, pr, files, profile))
    if len(records) != pr["changed_files"]:
        blockers.append("Incomplete changed-file inventory; cannot establish applicable tests")
    checks = api.pages(f"repos/{repo}/commits/{pr['head']['sha']}/check-runs", "check_runs")
    blockers.extend(check_blockers(checks))
    status = api.call(f"repos/{repo}/commits/{pr['head']['sha']}/status")
    if status["statuses"] and status["state"] != "success":
        blockers.append("Commit status has not passed")
    return pr, blockers


WORKFLOW_DIR = ".github/workflows/"
PROFILE_BLOCKER = "Workflow profile: "


def profile_blockers(api, repo, sha, records, profile):
    """Block a PR that adds or changes a pull_request workflow the merge profile does not describe.

    Without this the gate does not wait for that workflow, so the PR can merge with its tests
    red or unfinished (openmanetd build-frontend.yml and packages board-tests.yml, 2026-11-13).
    Only workflows the PR touches are checked, so an older gap never blocks unrelated PRs.
    """
    changed = sorted({r["filename"] for r in records
                      if r["filename"].startswith(WORKFLOW_DIR) and r["filename"].endswith((".yml", ".yaml"))
                      and r.get("status") != "removed" and "/" not in r["filename"][len(WORKFLOW_DIR):]})
    workflows = {}
    for path in changed:
        data = api.call(f"repos/{repo}/contents/{path}?ref={sha}")
        workflows[path] = base64.b64decode(data["content"]).decode()
    gaps = profile_gaps(profile, workflows)
    name = repo.split("/")[-1]
    return [f"{PROFILE_BLOCKER}{path} {problem}. Fix: in a ghostnet-labs/docs checkout run "
            f"`python3 project/scripts/sync_merge_profile.py {name} <this repo's .github/workflows dir>`, "
            f"open the docs PR (https://github.com/ghostnet-labs/docs/compare), then bump this repo's "
            f"manet-merge-gate.yml docs pin. Entry needed: "
            + json.dumps({"path": path, "paths": pr_trigger(workflows[path])[1]})
            for path, (_, problem) in sorted(gaps.items()) if path in workflows]


def cancelled_head_runs(runs, sha, number):
    """Newest current-head pull_request run of each workflow, where that run was cancelled.

    A cancelled check never turns green by itself: GitHub starts nothing new, the gate
    fails on it, and the PR sits until someone re-runs it (firmware #92, 2026-11-07:
    all three board builds and both gates cancelled while queued). The merge gate is
    left out because stale_gate_run() re-runs it once the rest has passed.
    """
    latest = {}
    for run in runs:
        if run["head_sha"] != sha or run["event"] != "pull_request":
            continue
        if number not in [p["number"] for p in run.get("pull_requests", [])]:
            continue
        path = run["path"].split("@")[0]
        if path.endswith("manet-merge-gate.yml"):
            continue
        previous = latest.get(path)
        if previous is None or (run["id"], run.get("run_attempt", 1)) > (previous["id"], previous.get("run_attempt", 1)):
            latest[path] = run
    return [run for _, run in sorted(latest.items())
            if run["status"] == "completed" and run["conclusion"] == "cancelled"]


def rerun_cancelled(api, repo, number, sha):
    """Re-run cancelled current-head runs, up to MAX_RERUN_ATTEMPTS attempts each."""
    runs = api.pages(f"repos/{repo}/actions/runs?head_sha={sha}&event=pull_request", "workflow_runs")
    for run in cancelled_head_runs(runs, sha, number):
        name = run.get("name") or run["path"]
        if run.get("run_attempt", 1) >= MAX_RERUN_ATTEMPTS:
            print(f"PR {number}: {name} run {run['id']} was cancelled again after "
                  f"{run.get('run_attempt', 1)} attempts; left for a person")
            continue
        try:
            api.call(f"repos/{repo}/actions/runs/{run['id']}/rerun", {}, method="POST")
            print(f"PR {number}: {name} run {run['id']} was cancelled on the current head; re-running it")
        except urllib.error.HTTPError as error:
            # 403: already running again or the token lacks actions: write.
            print(f"PR {number}: could not re-run cancelled run {run['id']}: HTTP {error.code}")


def reviews_clear(reviews):
    latest = {}
    for review in sorted(reviews, key=lambda r: r["id"]):
        if review["state"] in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
            latest[review["user"]["login"]] = review["state"]
    return "CHANGES_REQUESTED" not in latest.values()


def _skipped(check):
    return check["status"] == "completed" and check["conclusion"] == "skipped"


def rank(check):
    """Sort key for "the check that decides": the newest one that ran, then the newest.

    A skipped check tested nothing. Closing a PR runs its pull_request workflows with
    every job skipped, and GitHub can file those checks after the reopen's real ones
    (firmware #92, 2026-11-07: the closed-event "PR gate" got a higher id than the live
    one), so newest-id alone would let a skip outvote a real run on the same commit.
    """
    return (not _skipped(check), check["id"])


def check_blockers(checks):
    latest = {}
    for check in checks:
        if check["name"] in {GATE, AUTOMATION, LABELER, AUDIT}:
            continue
        if check["name"] in LABEL_BUILDS and check["status"] == "completed" and check["conclusion"] == "skipped":
            continue
        key = (check["name"], check["app"]["id"])
        if key not in latest or rank(check) > rank(latest[key]):
            latest[key] = check
    blockers = []
    for check in latest.values():
        allowed_skip = "Upload ccache cache to s3" in check["name"] or "Check packages for ${{ inputs.target }}/${{ inputs.subtarget }}" in check["name"]
        if check["status"] != "completed" or (check["conclusion"] != "success" and not (check["conclusion"] == "skipped" and allowed_skip)):
            blockers.append(f"Check {check['name']}: {check['status']}/{check.get('conclusion')}")
    return blockers


def requires_up_to_date(profile):
    """True unless the profile opts out of testing every PR on the current base.

    A repo opts out with "requireUpToDate": false when a later full build on the
    base branch covers what PR builds skip (firmware: the scheduled 8-board build).
    """
    return (profile or {}).get("requireUpToDate", True)


def protection_ready(rules, profile=None):
    checks = [r for r in rules if r["type"] == "required_status_checks"]
    pull_requests = [r for r in rules if r["type"] == "pull_request"]
    strict_needed = requires_up_to_date(profile)
    return any(r["parameters"].get("required_review_thread_resolution") for r in pull_requests) and any(
        (r["parameters"]["strict_required_status_checks_policy"] or not strict_needed) and
        any(c["context"] == GATE and c.get("integration_id") == 15368
            for c in r["parameters"]["required_status_checks"]) for r in checks)


def stale_gate_run(gates, gate_blockers):
    """Return the run id of a finished, unsuccessful gate whose own blockers have cleared.

    A gate can only poll for one hosted-runner job (6 hours), so a longer build
    outlives it. Re-running it makes the gate re-check the current head in full.
    """
    if gate_blockers or not gates:
        return None
    gate = max(gates, key=rank)
    if gate["status"] != "completed" or gate["conclusion"] == "success":
        return None
    found = re.search(r"/actions/runs/(\d+)/", gate.get("details_url") or "")
    return int(found.group(1)) if found else None


BEHIND = "GitHub merge criteria are not satisfied: behind"
# PRs opened by Claude threads carry this footer; Justin's own (Codex) branches are never
# updated without his say-so.
CLAUDE_FOOTER = re.compile(r"Generated (?:with|by) \[Claude Code\]")


def update_behind(updater, repo, number, pr):
    """Merge the base into a PR whose only blocker is being behind it.

    The push must come from a token other than the workflow's GITHUB_TOKEN:
    GitHub starts no workflows for GITHUB_TOKEN pushes, so the PR would sit
    with no checks on its new head.
    """
    if not CLAUDE_FOOTER.search(pr.get("body") or ""):
        print(f"PR {number}: behind its base; not a Claude PR, so left for its author")
        return
    if updater is None:
        print(f"PR {number}: behind its base; no UPDATE_TOKEN, so the branch was not updated")
        return
    try:
        updater.call(f"repos/{repo}/pulls/{number}/update-branch",
                     {"expected_head_sha": pr["head"]["sha"]}, method="PUT")
    except urllib.error.HTTPError as error:
        # 422: the head moved or the update would conflict; 403: token lacks access.
        print(f"PR {number}: could not update the branch (HTTP {error.code}); left as is")
        return
    print(f"PR {number}: behind its base; merged the base into the branch so checks re-run")


def handle(api, repo, number, profile, updater=None):
    pr, blockers = snapshot(api, repo, number, profile)
    gate_blockers = list(blockers)
    if pr["state"] != "open" or pr["draft"] or pr["base"]["ref"] != profile["branch"]:
        return
    if pr["head"]["repo"]["full_name"] != repo:
        print(f"PR {number}: external fork needs explicit review; no automatic merge")
        return
    held = any(l["name"].lower() in HOLD_LABELS for l in pr["labels"])
    if held:
        blockers.append("Explicit merge hold")
    elif any(b.endswith(": completed/cancelled") for b in gate_blockers):
        # A held PR's builds are cancelled on purpose (hold-builds.yml re-runs them
        # when the label comes off), so only unheld PRs get their runs back.
        rerun_cancelled(api, repo, number, pr["head"]["sha"])
    for dependency in re.findall(r"(?im)^Depends-on:\s*(https://github\.com/[\w.-]+/[\w.-]+/pull/\d+)\s*$", pr.get("body") or ""):
        owner, name, _, n = dependency.removeprefix("https://github.com/").split("/")
        if not api.call(f"repos/{owner}/{name}/pulls/{n}")["merged"]:
            blockers.append("Unmerged dependency: " + dependency)
    checks = api.pages(f"repos/{repo}/commits/{pr['head']['sha']}/check-runs", "check_runs")
    blockers.extend(check_blockers(checks))
    gates = [c for c in checks if c["name"] == GATE and c["app"]["id"] == 15368]
    if not gates or max(gates, key=rank)["conclusion"] != "success":
        blockers.append("Current-head Manet merge gate has not passed")
        run_id = stale_gate_run(gates, gate_blockers)
        # Cap re-runs so a gate that fails for some other reason cannot loop.
        if run_id and api.call(f"repos/{repo}/actions/runs/{run_id}").get("run_attempt", 1) < MAX_GATE_ATTEMPTS:
            try:
                api.call(f"repos/{repo}/actions/runs/{run_id}/rerun", {}, method="POST")
                print(f"PR {number}: applicable workflows now pass; re-running gate run {run_id}")
            except urllib.error.HTTPError as error:
                print(f"PR {number}: could not re-run gate run {run_id}: HTTP {error.code}")
    status = api.call(f"repos/{repo}/commits/{pr['head']['sha']}/status")
    if status["statuses"] and status["state"] != "success":
        blockers.append("Commit status has not passed")
    if not reviews_clear(api.pages(f"repos/{repo}/pulls/{number}/reviews")):
        blockers.append("Changes requested in review")
    rules = api.call(f"repos/{repo}/rules/branches/{profile['branch']}")
    if not protection_ready(rules, profile):
        blockers.append("Required gate, current-base testing, PR-only merging or conversation resolution is not enforced")
    # "unstable" only means a check GitHub doesn't require is not green. Every check that
    # matters was read above; what is left is this sweep's own run, often "cancelled" when a
    # newer sweep replaced it, which must not hold the PR until someone re-runs the sweep.
    mergeable = {"clean", "unstable"}
    # Without the up-to-date rule a PR behind its base is still mergeable.
    if not requires_up_to_date(profile):
        mergeable.add("behind")
    if pr["mergeable_state"] not in mergeable:
        blockers.append(BEHIND if pr["mergeable_state"] == "behind"
                        else "GitHub merge criteria are not satisfied: " + pr["mergeable_state"])
    if blockers == [BEHIND]:
        update_behind(updater, repo, number, pr)
        return
    if blockers:
        print(f"PR {number}: " + "; ".join(blockers))
        return
    try:
        result = api.call(f"repos/{repo}/pulls/{number}/merge", {
            "sha": pr["head"]["sha"], "merge_method": "merge"}, method="PUT")
    except urllib.error.HTTPError as error:
        # 405: GitHub refused the merge (a rule still blocks it); 409: the head
        # moved. Leave the PR open and carry on with the other PRs.
        if error.code not in (405, 409):
            raise
        print(f"PR {number}: GitHub refused the merge (HTTP {error.code}); left open")
        # A sibling PR merged after this one went green (firmware #98, 2026-11-13): the
        # profile allows "behind", but a branch rule can still refuse a branch that is.
        # Merge the base in with the update token so checks re-run, instead of leaving a
        # green PR stuck until someone pushes by hand.
        if error.code == 405 and pr["mergeable_state"] == "behind":
            update_behind(updater, repo, number, pr)
        return
    if not result.get("merged"):
        raise RuntimeError("GitHub did not merge the validated PR")
    print(f"PR {number} merged as {result['sha']}")


def terminal_blocker(blocker):
    return blocker.startswith(("External integration", PROFILE_BLOCKER)) or any(
        "completed/" + outcome in blocker
        for outcome in ("failure", "cancelled", "timed_out", "action_required", "skipped", "startup_failure", "stale"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["gate", "merge"])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", type=int)
    parser.add_argument("--sha")
    parser.add_argument("--timeout", type=int, default=20400)
    args = parser.parse_args()
    profile = json.loads(Path(__file__).with_name("merge_profiles.json").read_text())[args.repo.split("/")[1]]
    api = API(os.environ["GH_TOKEN"])
    if args.mode == "merge":
        update_token = os.environ.get("UPDATE_TOKEN")
        updater = API(update_token) if update_token else None
        for pr in api.pages(f"repos/{args.repo}/pulls?state=open"):
            handle(api, args.repo, pr["number"], profile, updater)
        return
    deadline = time.monotonic() + args.timeout
    while True:
        try:
            pr, blockers = snapshot(api, args.repo, args.pr, profile)
        except TRANSIENT_ERRORS as error:
            # The gate waits for hours; one GitHub outage longer than a read's retries
            # (firmware #82 on 2026-11-04: HTTP 500 on commits/{sha}/status) must not fail
            # it. Try again on the next poll until the deadline.
            if not _transient(error) or time.monotonic() >= deadline:
                raise
            print(f"GitHub API error ({error}); checking again in 30s", flush=True)
            time.sleep(30)
            continue
        if pr["head"]["sha"] != args.sha:
            raise SystemExit("PR head changed; this result is stale")
        if not blockers:
            print("All applicable workflows completed successfully on the current PR head")
            return
        print("\n".join(blockers), flush=True)
        if any(terminal_blocker(b) for b in blockers) or time.monotonic() >= deadline:
            raise SystemExit(1)
        time.sleep(30)


if __name__ == "__main__":
    main()
