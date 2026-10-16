#!/usr/bin/env python3
"""Insert the runner policy step into a repo's Manet merge gate workflow.

  add_runner_policy_gate.py .github/workflows/manet-merge-gate.yml <docs-commit-sha>

The step checks out check_runners.py and the allowlist from the docs commit
named by the sha (a pin of its own, separate from the gate's policy pin),
checks out the PR's merge result, and runs the check against its workflow
files before the gate starts waiting for other checks. It only parses YAML;
nothing from the change is executed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

MARKER = "      - name: Verify merge policy regression suite\n"
BLOCK = """      - name: Check out the runner policy
        uses: actions/checkout@v4
        with:
          repository: ghostnet-labs/docs
          ref: {ref}
          path: runner-policy
          sparse-checkout: |
            project/scripts/check_runners.py
            project/ci/runner-allowlist.json
          sparse-checkout-cone-mode: false
          persist-credentials: false
      - name: Check out this change's workflows
        uses: actions/checkout@v4
        with:
          path: change
          sparse-checkout: .github/workflows
          persist-credentials: false
      - name: Check the runner policy
        # Parses the workflow files only; nothing from the change is executed.
        env:
          REPO_NAME: ${{{{ github.event.repository.name }}}}
        run: |
          python3 -c 'import yaml' 2>/dev/null || {{
            python3 -m venv "$RUNNER_TEMP/runner-policy-venv"
            "$RUNNER_TEMP/runner-policy-venv/bin/pip" install --quiet pyyaml==6.0.2
            PATH="$RUNNER_TEMP/runner-policy-venv/bin:$PATH"
          }}
          python3 runner-policy/project/scripts/check_runners.py --repo "$REPO_NAME" \\
            --workflows change/.github/workflows \\
            --allowlist runner-policy/project/ci/runner-allowlist.json
"""


def patch(text: str, ref: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", ref):
        raise ValueError("ref must be a full 40-character commit sha")
    if "runner-policy" in text:
        raise ValueError("gate already has a runner policy step")
    if text.count(MARKER) != 1:
        raise ValueError("gate workflow lacks the expected 'Verify merge policy regression suite' step")
    return text.replace(MARKER, BLOCK.format(ref=ref) + MARKER)


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(args[0])
    path.write_text(patch(path.read_text(), args[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
