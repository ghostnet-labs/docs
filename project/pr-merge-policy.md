# Manet PR merge policy

Every project PR is completed through CI and GitHub's enforced merge rules. `AGENTS.md` records the instruction; the merge gate checks actual GitHub evidence.

## Criteria

- PR is complete, not a draft, targets the repository's selected branch and has no merge hold (`hold`, `do-not-merge`, `blocked`).
- Every workflow applicable to its changed paths has a successful current-head PR run. Missing workflows, old-head results, cancelled/failed/neutral/skipped runs and pending tests never qualify. Additional label-triggered workflows must also pass. Intentional skipped jobs within a successful workflow are distinct from skipped workflows.
- GitHub requires the stable `Manet merge gate` check from GitHub Actions, an up-to-date branch, a PR and resolution of review conversations. Existing required checks/reviews remain in place. Outstanding requests for changes block automation.
- Dependencies are declared as `Depends-on: https://github.com/OWNER/REPO/pull/NUMBER` on separate lines and must be merged. Substantive unresolved hardware or owner decisions stay drafts or carry a merge-hold label; merging code does not establish hardware qualification.
- Automation checks trusted policy code at a pinned revision. It reads GitHub metadata only: it never checks out a PR, executes PR code, downloads artifacts or restores PR caches with merge permissions.
- Once eligible, merge automatically through GitHub's protected endpoint with the expected head SHA. GitHub rejects enabling auto-merge for an already-clean PR; this protected merge is the equivalent completion step. An API race or protection failure never results in a forced merge.

## Test ownership

`project/scripts/merge_profiles.json` owns the reviewed workflow/path inventory for docs, firmware, openmanetd, OpenVLM, protobufs, LuCI and packages. Update it when changing workflow triggers. The gate waits for each applicable workflow to register and finish, so an empty check list cannot establish success.

Docs always checks GPIO records, agent-instruction links and the merge policy regression suite; its website also gets a PR Jekyll build. Firmware retains its board/kernel/toolchain/tools builds and existing PR gate. Go services retain Go/CodeQL and applicable frontend tests/builds. Protobufs retains Buf validation/breaking checks. LuCI retains formalities and its package build.

Packages retains `Build packages`, which compiles every package a PR touches in the pinned OpenWrt SDK for one aarch64 and one MIPS target, using the firmware's pinned feeds. A metadata or Markdown check cannot substitute for compiling packages. PRs that touch no package still run the workflow, with the compile steps skipped. The firmware integration-evidence check (GHO-82, `externalBuild`) remains in the policy for any profile that sets it.

## Operations

The always-running read-only gate excludes itself to avoid waiting forever. The handler runs after completed PR workflows, when a PR becomes ready or its labels change, and after review updates. A scheduled reconciliation also revisits roughly every 15 minutes, covering external dependency merges and resolved conversations without a local workflow event; GitHub runner delays can postpone it. It reconciles open same-repository PRs and leaves fork PRs for explicit review. Runtime errors fail the automation rather than silently treating missing evidence as a pass.

Strict up-to-date checks can require updating a PR after another merges. This intentionally demands fresh CI against the new base. Merge protections must be installed and verified before the handler will merge anything; workflow YAML alone does not enforce manual merges.

Changes to merge policy and workflow inventories need source review and regression tests. Pinned callers must be updated to the reviewed policy commit when publishing a policy change.

## Runner policy

`project/scripts/check_runners.py` keeps CI on the self-hosted Mac runners and stops stale runs from piling up. It fails a workflow job that runs only on GitHub-hosted runners, a pull request workflow whose runs a newer push does not cancel, a schedule that fires more than hourly on a hosted runner, a reusable workflow from another repository that is not pinned to a commit SHA, and a job without `timeout-minutes`. It also fails any job on a `pull_request` workflow that can run on a self-hosted runner without a fork guard, because a fork pull request could otherwise run its own code on the Macs. The guard is a `runs-on` expression that picks `self-hosted` only when the event is not a pull request or the pull request head repository is this repository, and falls back to a hosted runner otherwise. A form that picks `self-hosted` only when `github.event_name == 'pull_request'` and the head repository is this repository also passes, for jobs that must stay hosted on push, such as ones holding a registry token:

```yaml
runs-on: ${{ (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository) && fromJSON('["self-hosted", "Linux", "ARM64"]') || 'ubuntu-latest' }}
```

Exceptions live in `project/ci/runner-allowlist.json`, each with the rules it waives and the reason. Remove an entry when its workflow is fixed; the check warns about entries nothing uses. Docs runs the check on every PR in `Project record checks`, and `Runner policy audit` runs it hourly against every public repo's default branch.

`project/scripts/add_runner_policy_gate.py` adds the check to a repo's `Manet merge gate` job, where it runs against the workflows of the PR's merge result before the gate waits for the other checks. The step checks out `project/scripts/check_runners.py` and the allowlist from a docs commit pinned in its own `runner-policy` step, separate from the policy pin, so a runner policy change reaches a repo only through a PR that bumps that pin. The step rolls out to each repo's gate in a per-repo PR after the script lands, pinned to the docs commit that added it; until then, a repo's gate does not run the check.
