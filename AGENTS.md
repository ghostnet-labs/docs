# Agent instructions

## Manet pull request completion

Justin's standing requirement (2026-10-04) applies to Manet/OpenMANET work across the ghostnet-labs project repositories:

- Always enable GitHub auto-merge once all checks have passed on the current PR head. Do not leave a passing PR waiting for Justin to merge manually or ask for another routine merge approval.
- First verify that every applicable CI/test/build check has completed successfully and that required reviews, unresolved review threads, merge conflicts and declared PR dependencies are satisfied. A queued, running, failed or cancelled check is not a pass. A skipped job is acceptable only when its workflow intentionally excludes it from the applicable checks; it is not evidence that a test ran.
- Complete the authorized work and mark a draft ready for review when it is actually complete; drafts are not merge-ready merely because checks are green.
- After changing or updating a PR, verify checks against the new head before enabling or re-enabling auto-merge. Confirm by reading back that auto-merge is enabled or the PR has merged.
- Preserve branch protections, required checks and review requirements. Do not force a merge or bypass a failed gate. Report any permission, configuration or unresolved approval blocker.
- If GitHub cannot queue auto-merge because the PR is already immediately mergeable, complete a normal protected merge only after the same checks and reviews are satisfied, then verify the merged state.
- An explicit instruction from Justin to hold a specific PR takes precedence.

Follow [project/README.md](project/README.md) for the ownership and consistency rules for Manet engineering records. Merging implementation does not establish hardware qualification or close remaining bench-validation gates.
