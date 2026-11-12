# Stale workflow runs

`stale_runs.py` lists every queued and running GitHub Actions run in the
ghostnet-labs repos and labels it. With `--cancel` it cancels only runs that
are provably wasted:

| Label | Meaning | Cancelled with `--cancel`? |
|---|---|---|
| `closed` | `pull_request` run whose PR is merged or closed | yes |
| `superseded` | run on an old head of an open PR, when the PR's current head already has a run of the same workflow | yes |
| `orphan` | push run still `queued` or `waiting` after `--orphan-hours` (default 24) whose commit is no longer the tip of its branch (the branch moved on or was deleted) | yes |
| `zombie` | queued or running longer than `--stale-hours` (default 3); shows its job count and the runner labels its queued jobs wait for | no, report only |
| `stuck-push` | push run with a newer push run of the same workflow on the same branch, younger than `--orphan-hours` | no, report only |
| `off-limits` | matched `--skip-pr` / `--skip-run` | never |
| `live` | anything else, including every current-head run of an open PR | never |

Rules built into the code:

- never touches a current-head run of an open PR, or any push,
  `workflow_dispatch` or `schedule` run;
- a workflow whose name matches `--protect` (default `kernel`, case-insensitive)
  is cancelled only after its matrix expanded (more than one job). Cancelling
  the firmware Build Kernel placeholder leaves a "skipped" check that the
  Manet merge gate treats as final on that commit;
- `--min-age-hours N` holds every cancel (closed, superseded, orphan) back for
  runs younger than N hours; the default 0 cancels as soon as a run is dead;
- an `orphan` needs the branch tip looked up (one `git/ref` call per branch,
  only for branches with an old unstarted push run); a lookup that fails for any
  reason other than 404 leaves the run alone;
- at most `--max-cancel` cancels per invocation (default 10).

It is Python 3 standard library only and needs no install.

```sh
python3 tools/stale-runs/stale_runs.py                    # dry run, prints a table
python3 tools/stale-runs/stale_runs.py --cancel \
  --skip-pr firmware#52 --skip-pr packages#22 --skip-run 38350977523
python3 tools/stale-runs/stale_runs.py --json             # for scripts
```

## API cost

Per repo: one open-PR list and one run list each for `queued`, `in_progress`
and `waiting` (32 requests for 8 repos). Every request carries the ETag of the
last answer, cached in `~/.cache/stale-runs/etags.json`; GitHub does not count
"304 not changed" answers against the 5,000-an-hour limit, so a quiet org
costs close to nothing. Extra calls happen only when needed: one job list per
protected or zombie run, and one run lookup per open PR that has an old-head
run. The first output line prints the counted calls and the free 304s.

## Token

A fine-grained token, resource owner ghostnet-labs, all repositories, with
**Actions: Read and write** (write is needed only for `--cancel`) and
**Pull requests: Read-only**. Put it in `~/.config/stale-runs/token`
(`chmod 600`) or `STALE_RUNS_TOKEN`. `GITHUB_TOKEN` is the last fallback.

## Run it every 15 minutes on the Mac Studio

```sh
git clone --depth 1 https://github.com/ghostnet-labs/docs ~/stale-runs-src
python3 ~/stale-runs-src/tools/stale-runs/stale_runs.py launchd --cancel \
  > ~/Library/LaunchAgents/com.ghostnet.stale-runs.plist
launchctl load ~/Library/LaunchAgents/com.ghostnet.stale-runs.plist
```

Output goes to `~/Library/Logs/stale-runs.log`. Leave out `--cancel` to only
log. Arguments after `launchd` are passed to every scheduled run, so add
`--skip-pr` / `--skip-run` there for work that must not be touched.

## Run it inside each repo's merge sweep

The "Handle passing PRs" workflow already holds `actions: write`, so it can
clear a repo's own dead runs with no Mac and no extra token. After the merge
step, add:

```yaml
      - name: Cancel dead runs older than a day
        if: always()
        continue-on-error: true
        env:
          GITHUB_TOKEN: ${{ github.token }}
        run: python3 tools/stale-runs/stale_runs.py --cancel --min-age-hours 24 --repos "${GITHUB_REPOSITORY#*/}"
```

`GITHUB_TOKEN` is the last token fallback, `continue-on-error` keeps a cancel
problem from ever holding up a merge, and `--min-age-hours 24` means the
sweep only removes runs that have been dead for a day. The checkout is of the
docs pin, so a repo gets the step by bumping the pin to a commit that has this
script. The Mac LaunchAgent can keep the default `--min-age-hours 0` for
immediate cleanup.

## Actions guard: catch Actions switched off

`actions_guard.py` is a second, read-only script in the same folder. It
exists because luci's workflows were off for four days (2026-10-30 to
2026-11-03) and nothing noticed. For every repo it reports:

| Finding | Meaning |
|---|---|
| `actions-off` | repository-level Actions permission is off (needs a token with repository administration; skipped otherwise) |
| `workflow-off` | a workflow is `disabled_fork`, `disabled_inactivity` or `disabled_manually` |
| `pr-no-checks` | a ready PR head has no check runs or statuses after 20 minutes |
| `runs-stale` | open PRs exist but the newest run is older than 3 hours |
| `runs-held` | a run queued 15+ min (`--held-minutes`) that GitHub has given no jobs: GitHub is holding it (fork enable banner), not waiting for a runner. PR runs on a commit that is no longer an open PR's head are ignored (old heads and closed PRs have nothing waiting on them), and so is a run that a newer run of the same workflow on the same commit replaced (GitHub refuses to cancel a frozen re-run) |

Exit 1 means a finding, so a LaunchAgent or any watchdog can page on it:

```sh
python3 tools/stale-runs/actions_guard.py          # table
python3 tools/stale-runs/actions_guard.py --json   # for a watchdog
```

When it fires with `workflow-off` on a fork, the fix is the green
"I understand my workflows, go ahead and enable them" button (or
Enable workflow) on the repo's Actions tab; it cannot be done through the API
with the tokens we use.

## Tests

```sh
python3 -m unittest discover -s tools/stale-runs -v
```
