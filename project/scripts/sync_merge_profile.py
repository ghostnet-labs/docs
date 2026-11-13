#!/usr/bin/env python3
"""Update one repo's entry in merge_profiles.json from its workflow files.

Run from a ghostnet-labs/docs checkout:

    python3 project/scripts/sync_merge_profile.py openmanetd ../openmanetd/.github/workflows

Adds every workflow that runs on pull_request and is missing from the profile, copies the
workflow's on.pull_request.paths over a profile entry that disagrees, and drops entries whose
workflow no longer runs on pull_request. Then open a docs PR with the result.
"""
import argparse
import json
from pathlib import Path

from workflow_triggers import GATE_IGNORED, pr_trigger

PROFILES = Path(__file__).with_name("merge_profiles.json")


def sync(profile, workflows):
    """Return (new profile entry, list of change descriptions); workflows maps repo path to text."""
    listed = {w["path"]: dict(w) for w in profile["workflows"]}
    changes = []
    for path in sorted(workflows):
        if path in GATE_IGNORED:
            continue
        runs, paths = pr_trigger(workflows[path])
        if not runs:
            if path in listed:
                del listed[path]
                changes.append(f"remove {path} (no longer runs on pull_request)")
        elif path not in listed:
            listed[path] = {"path": path, "paths": paths}
            changes.append(f"add {path}")
        elif listed[path]["paths"] != paths:
            listed[path]["paths"] = paths
            changes.append(f"update paths of {path}")
    for path in sorted(set(listed) - set(workflows)):
        del listed[path]
        changes.append(f"remove {path} (workflow file is gone)")
    order = {w["path"]: i for i, w in enumerate(profile["workflows"])}
    entries = sorted(listed.values(), key=lambda w: (order.get(w["path"], len(order)), w["path"]))
    return dict(profile, workflows=entries), changes


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repo", help="repo name as it appears in merge_profiles.json")
    parser.add_argument("workflows_dir", type=Path, help="the repo's .github/workflows directory")
    args = parser.parse_args()
    profiles = json.loads(PROFILES.read_text())
    workflows = {f".github/workflows/{f.name}": f.read_text()
                 for f in sorted(args.workflows_dir.iterdir()) if f.suffix in (".yml", ".yaml")}
    profiles[args.repo], changes = sync(profiles[args.repo], workflows)
    PROFILES.write_text(json.dumps(profiles, indent=2) + "\n")
    print("\n".join(changes) if changes else "profile already matches the workflows")


if __name__ == "__main__":
    main()
