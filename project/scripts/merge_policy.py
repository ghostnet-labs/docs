#!/usr/bin/env python3
"""Fail-closed Manet CI gate and protected auto-merge, using only GitHub metadata."""
import argparse
import json
import os
from pathlib import Path
import re
import time
import urllib.request

GATE = "Manet merge gate"
AUTOMATION = "Handle passing PRs"


def matches(path, pattern):
    # GitHub path filters: * excludes slash, ** includes it, ? matches one char.
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
        # Include additional PR workflows (e.g. label-triggered builds) that ran.
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
    if profile.get("externalBuild") and any(not (f.endswith(".md") or f.startswith(".github/") or f == ".gitignore") for f in files):
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


def snapshot(api, repo, number, profile):
    pr = api.call(f"repos/{repo}/pulls/{number}")
    files = [f["filename"] for f in api.pages(f"repos/{repo}/pulls/{number}/files")]
    runs = api.pages(f"repos/{repo}/actions/runs?head_sha={pr['head']['sha']}&event=pull_request", "workflow_runs")
    blockers = evaluate(profile, files, runs, pr["head"]["sha"], number)
    return pr, blockers


def reviews_clear(reviews):
    latest = {}
    for review in sorted(reviews, key=lambda r: r["id"]):
        if review["state"] in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
            latest[review["user"]["login"]] = review["state"]
    return "CHANGES_REQUESTED" not in latest.values()


def protection_ready(rules):
    types = {r["type"] for r in rules}
    checks = [r for r in rules if r["type"] == "required_status_checks"]
    return {"pull_request", "required_review_thread_resolution"} <= types and any(
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
    # Machine-readable dependencies, one URL per line; never guess from prose.
    for dependency in re.findall(r"(?im)^Depends-on:\s*(https://github\.com/[\w.-]+/[\w.-]+/pull/\d+)\s*$", pr.get("body") or ""):
        owner, name, _, n = dependency.removeprefix("https://github.com/").split("/")
        if not api.call(f"repos/{owner}/{name}/pulls/{n}")["merged"]:
            blockers.append("Unmerged dependency: " + dependency)
    checks = api.pages(f"repos/{repo}/commits/{pr['head']['sha']}/check-runs", "check_runs")
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
    # Use a protected SHA-pinned merge once everything is green. GitHub rejects
    # auto-merge for an already-clean PR, and its merge endpoint still enforces rules.
    result = api.call(f"repos/{repo}/pulls/{number}/merge", {
        "sha": pr["head"]["sha"], "merge_method": "merge"}, method="PUT")
    if not result.get("merged"):
        raise RuntimeError("GitHub did not merge the validated PR")
    print(f"PR {number} merged as {result['sha']}")


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
        # workflow_run events sometimes lack pull_requests (e.g. fork/label runs).
        # Reconcile open PR metadata; no PR checkout, artifacts or caches are used.
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
        # Fail terminal errors promptly; missing workflows may still be registering.
        if any("completed/" in b or "Package changes" in b for b in blockers) or time.monotonic() >= deadline:
            raise SystemExit(1)
        time.sleep(30)


if __name__ == "__main__":
    main()
