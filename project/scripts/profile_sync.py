#!/usr/bin/env python3
"""Keep merge_profiles.json and each repo's docs pin in step with the repos' workflows.

Runs from .github/workflows/manet-profile-sync.yml with the MANET_UPDATE_TOKEN secret.
Without that secret it prints a skip line and exits 0, so the manual fix printed by the
merge gate (sync_merge_profile.py) stays the process until the secret exists.

1. Profile: read every repo's workflows on its profile branch. If merge_profiles.json on docs
   main disagrees, open one docs PR (branch bot/profile-sync) with the corrected profile.
2. Pins: once docs main's profile matches the workflows, any repo whose manet-merge-gate.yml or
   manet-auto-merge.yml pins a docs commit with a different merge_policy.py or a different
   profile entry gets a PR (branch bot/docs-pin) moving both pins to docs main.

The PRs are ordinary PRs: the Manet merge gate and "Handle passing PRs" sweep decide when
they merge. Opened with the PAT so their workflows run.
"""
import base64
import json
import os
import re
import sys

from merge_policy import API
from sync_merge_profile import sync

ORG = "ghostnet-labs"
DOCS = f"{ORG}/docs"
PROFILE_PATH = "project/scripts/merge_profiles.json"
POLICY_PATH = "project/scripts/merge_policy.py"
PROFILE_BRANCH = "bot/profile-sync"
PIN_BRANCH = "bot/docs-pin"
PIN_FILES = (".github/workflows/manet-merge-gate.yml", ".github/workflows/manet-auto-merge.yml")
# Only the checkout that runs the policy; the stale-run tool checkout has a `path:` key between.
PIN = re.compile(r"(repository:\s*['\"]?" + re.escape(DOCS) + r"['\"]?\n\s+ref:\s*['\"]?)([0-9a-f]{40})(['\"]?\n\s+persist-credentials)")


def file_text(api, repo, path, ref):
    try:
        data = api.call(f"repos/{repo}/contents/{path}?ref={ref}")
    except Exception as error:  # noqa: BLE001 - a missing file is an answer, anything else is re-raised
        if getattr(error, "code", None) == 404:
            return None, None
        raise
    return base64.b64decode(data["content"]).decode(), data["sha"]


def repo_workflows(api, repo, branch):
    listing = api.call(f"repos/{repo}/contents/.github/workflows?ref={branch}")
    out = {}
    for item in listing:
        if item["type"] == "file" and item["name"].endswith((".yml", ".yaml")):
            out[item["path"]] = file_text(api, repo, item["path"], branch)[0]
    return out


def desired_profiles(api, profiles):
    """(new profiles, {repo: changes}) from each repo's workflows on its profile branch."""
    new, changes = {}, {}
    for name, profile in profiles.items():
        new[name], repo_changes = sync(profile, repo_workflows(api, f"{ORG}/{name}", profile["branch"]))
        if repo_changes:
            changes[name] = repo_changes
    return new, changes


def reset_branch(api, repo, branch, base_sha):
    ref = f"repos/{repo}/git/refs"
    try:
        api.call(f"{ref}/heads/{branch}", {"sha": base_sha, "force": True}, "PATCH")
    except Exception as error:  # noqa: BLE001
        if getattr(error, "code", None) != 422 and getattr(error, "code", None) != 404:
            raise
        api.call(ref, {"ref": f"refs/heads/{branch}", "sha": base_sha}, "POST")


def put_file(api, repo, branch, path, text, message):
    _, sha = file_text(api, repo, path, branch)
    body = {"message": message, "content": base64.b64encode(text.encode()).decode(), "branch": branch}
    if sha:
        body["sha"] = sha
    api.call(f"repos/{repo}/contents/{path}", body, "PUT")


def open_pr(api, repo, branch, base, title, body):
    existing = api.call(f"repos/{repo}/pulls?state=open&head={repo.split('/')[0]}:{branch}")
    if existing:
        api.call(f"repos/{repo}/pulls/{existing[0]['number']}", {"title": title, "body": body}, "PATCH")
        return existing[0]["html_url"]
    return api.call(f"repos/{repo}/pulls", {"title": title, "head": branch, "base": base, "body": body}, "POST")["html_url"]


def profile_pr(api, profiles, new, changes):
    main = api.call(f"repos/{DOCS}/git/ref/heads/main")["object"]["sha"]
    reset_branch(api, DOCS, PROFILE_BRANCH, main)
    lines = [f"- {repo}: {change}" for repo, items in sorted(changes.items()) for change in items]
    put_file(api, DOCS, PROFILE_BRANCH, PROFILE_PATH, json.dumps(new, indent=2) + "\n",
             "ci(gate): sync merge profiles with repo workflows")
    return open_pr(api, DOCS, PROFILE_BRANCH, "main", "ci(gate): sync merge profiles with repo workflows",
                   "Opened by project/scripts/profile_sync.py. Each repo's pull_request workflows differ from "
                   "merge_profiles.json, so the merge gate would not wait for them (or would wait for a run that "
                   "never starts):\n\n" + "\n".join(lines))


def pin_stale(api, name, profile_main, pinned_sha, policy_main):
    policy, _ = file_text(api, DOCS, POLICY_PATH, pinned_sha)
    profiles, _ = file_text(api, DOCS, PROFILE_PATH, pinned_sha)
    pinned_profile = (json.loads(profiles) if profiles else {}).get(name)
    return policy != policy_main or pinned_profile != profile_main


def pin_prs(api, profiles):
    """Open a pin-bump PR in each repo whose pinned docs commit has an out-of-date policy or profile."""
    docs_main = api.call(f"repos/{DOCS}/commits?sha=main&path=project/scripts&per_page=1")[0]["sha"]
    policy_main, _ = file_text(api, DOCS, POLICY_PATH, docs_main)
    opened = []
    for name, profile in profiles.items():
        repo, branch = f"{ORG}/{name}", profile["branch"]
        if name == "docs":
            continue
        files = {path: file_text(api, repo, path, branch)[0] for path in PIN_FILES}
        stale = False
        for text in files.values():
            for match in PIN.finditer(text or ""):
                stale = stale or (match.group(2) != docs_main and pin_stale(api, name, profile, match.group(2), policy_main))
        if not stale:
            continue
        base = api.call(f"repos/{repo}/git/ref/heads/{branch}")["object"]["sha"]
        reset_branch(api, repo, PIN_BRANCH, base)
        title = f"ci(policy): bump docs merge policy pin to {docs_main[:7]}"
        for path, text in files.items():
            if text and PIN.search(text):
                put_file(api, repo, PIN_BRANCH, path, PIN.sub(lambda m: m.group(1) + docs_main + m.group(3), text), title)
        opened.append(open_pr(api, repo, PIN_BRANCH, branch, title,
                              f"Opened by project/scripts/profile_sync.py in {DOCS}. The pinned docs commit has an older "
                              f"merge_policy.py or this repo's merge profile than docs main ({docs_main})."))
    return opened


def run(api):
    profiles = json.loads(file_text(api, DOCS, PROFILE_PATH, "main")[0])
    new, changes = desired_profiles(api, profiles)
    if changes:
        print("profile PR:", profile_pr(api, profiles, new, changes))
        return 0
    for url in pin_prs(api, profiles):
        print("pin PR:", url)
    print("profiles match the workflows")
    return 0


def main():
    token = os.environ.get("MANET_UPDATE_TOKEN", "")
    if not token:
        print("skip: MANET_UPDATE_TOKEN is not set; the merge gate message shows the manual fix")
        return 0
    return run(API(token))


if __name__ == "__main__":
    sys.exit(main())
