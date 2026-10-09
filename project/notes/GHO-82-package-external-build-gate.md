# GHO-82 — Package external integration gate

Package code changes do not build in the packages repository. Their protected Manet merge gate therefore requires machine-readable firmware integration evidence instead of a local build.

Package PRs provide exactly one `External-Integration-PR` and one 40-character `External-Integration-Commit` line. The central merge policy verifies that the integration commit contains the current package PR head, that the integration PR is in the configured firmware repository, that the integration PR current head pins that exact package commit in `feeds.conf.default`, and that the integration PR current-head checks and Manet gate are successful.

The path is fail-closed: missing, ambiguous, stale, mismatched, draft, or failed evidence blocks the package PR. Documentation-only and `.github/`-only package changes continue not to require a firmware integration build. No branch protection or required check is relaxed.
