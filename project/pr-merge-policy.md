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

The packages feed currently has no standalone package-build CI. Its code changes are deliberately blocked by the gate until a current-head integration-build verifier is implemented. A metadata or Markdown check cannot substitute for compiling packages. Documentation/policy-only feed changes can pass without claiming a package build.

## Operations

The always-running read-only gate excludes itself to avoid waiting forever. The handler runs after completed PR workflows, when a PR becomes ready or its labels change, and after review updates. It reconciles open same-repository PRs and leaves fork PRs for explicit review. Runtime errors fail the automation rather than silently treating missing evidence as a pass.

Strict up-to-date checks can require updating a PR after another merges. This intentionally demands fresh CI against the new base. Merge protections must be installed and verified before the handler will merge anything; workflow YAML alone does not enforce manual merges.

Changes to merge policy and workflow inventories need source review and regression tests. Pinned callers must be updated to the reviewed policy commit when publishing a policy change.
