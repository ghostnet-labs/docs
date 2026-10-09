#!/usr/bin/env python3
"""Fail-closed Manet CI gate and protected auto-merge, using only GitHub metadata."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import time
import urllib.request

GATE = "Manet merge gate"
AUTOMATION = "Handle passing PRs"


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


class API:
    def __init__(self, token):
        self.token = token

    def call(self, path, data=None, method=None):
        url = path if path.startswith("https://api.github.com/") else "https://api.github.com/" + path
        request = urllib.request.Request(url, data=None if data is None else json.dumps(data).encode(),
            method=method, headers={"Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)

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
    if not gates or max(gates, key=lambda c: c["id"])["conclusion"] != "success":
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


def reviews_clear(reviews):
    latest = {}
    for review in sorted(reviews, key=lambda r: r["id"]):
        if review["state"] in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
            latest[review["user"]["login"]] = review["state"]
    return "CHANGES_REQUESTED" not in latest.values()


def check_blockers(checks):
    latest = {}
    for check in checks:
        if check["name"] in {GATE, AUTOMATION}:
            continue
        key = (check["name"], check["app"]["id"])
        if key not in latest or check["id"] > latest[key]["id"]:
            latest[key] = check
    blockers = []
    for check in latest.values():
        allowed_skip = "Upload ccache cache to s3" in check["name"] or "Check packages for ${{ inputs.target }}/${{ inputs.subtarget }}" in check["name"]
        if check["status"] != "completed" or (check["conclusion"] != "success" and not (check["conclusion"] == "skipped" and allowed_skip)):
            blockers.append(f"Check {check['name']}: {check['status']}/{check.get('conclusion')}")
    return blockers


def protection_ready(rules):
    checks = [r for r in rules if r["type"] == "required_status_checks"]
    pull_requests = [r for r in rules if r["type"] == "pull_request"]
    return any(r["parameters"].get("required_review_thread_resolution") for r in pull_requests) and any(
        r["parameters"]["strict_required_status_checks_policy"] and
        any(c["context"] == GATE and c.get("integration_id") == 15368
            for c in r["parameters"]["required_status_checks"]) for r in checks)


def handle(api, repo, number, profile):
    pr, blockers = snapshot(api, repo, number, profile)
    if pr["state"] != "open" or pr["draft"] or pr["base"]["ref"] != profile["branch"]:
        return
    if pr["head"]["repo"]["full_name"] != repo:
        print(f"PR {number}: external fork needs explicit review; no automatic merge")
        return
    if any(l["name"].lower() in {"hold", "do-not-merge", "blocked"} for l in pr["labels"]):
        blockers.append("Explicit merge hold")
    for dependency in re.findall(r"(?im)^Depends-on:\s*(https://github\.com/[\w.-]+/[\w.-]+/pull/\d+)\s*$", pr.get("body") or ""):
        owner, name, _, n = dependency.removeprefix("https://github.com/").split("/")
        if not api.call(f"repos/{owner}/{name}/pulls/{n}")["merged"]:
            blockers.append("Unmerged dependency: " + dependency)
    checks = api.pages(f"repos/{repo}/commits/{pr['head']['sha']}/check-runs", "check_runs")
    blockers.extend(check_blockers(checks))
    gates = [c for c in checks if c["name"] == GATE and c["app"]["id"] == 15368]
    if not gates or max(gates, key=lambda c: c["id"])["conclusion"] != "success":
        blockers.append("Current-head Manet merge gate has not passed")
    status = api.call(f"repos/{repo}/commits/{pr['head']['sha']}/status")
    if status["statuses"] and status["state"] != "success":
        blockers.append("Commit status has not passed")
    if not reviews_clear(api.pages(f"repos/{repo}/pulls/{number}/reviews")):
        blockers.append("Changes requested in review")
    rules = api.call(f"repos/{repo}/rules/branches/{profile['branch']}")
    if not protection_ready(rules):
        blockers.append("Required gate, current-base testing, PR-only merging or conversation resolution is not enforced")
    if pr["mergeable_state"] != "clean":
        blockers.append("GitHub merge criteria are not satisfied: " + pr["mergeable_state"])
    if blockers:
        print(f"PR {number}: " + "; ".join(blockers))
        return
    result = api.call(f"repos/{repo}/pulls/{number}/merge", {
        "sha": pr["head"]["sha"], "merge_method": "merge"}, method="PUT")
    if not result.get("merged"):
        raise RuntimeError("GitHub did not merge the validated PR")
    print(f"PR {number} merged as {result['sha']}")


def terminal_blocker(blocker):
    return blocker.startswith("External integration") or any(
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
        for pr in api.pages(f"repos/{args.repo}/pulls?state=open"):
            handle(api, args.repo, pr["number"], profile)
        return
    deadline = time.monotonic() + args.timeout
    while True:
        pr, blockers = snapshot(api, args.repo, args.pr, profile)
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
