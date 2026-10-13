# Stale workflow runs

`stale_runs.py` lists every queued and running GitHub Actions run in the
ghostnet-labs repos and labels it. With `--cancel` it cancels only runs that
are provably wasted:

| Label | Meaning | Cancelled with `--cancel`? |
|---|---|---|
| `closed` | `pull_request` run whose PR is merged or closed | yes |
| `superseded` | run on an old head of an open PR, when the PR's current head already has a run of the same workflow | yes |
| `zombie` | queued or running longer than `--stale-hours` (default 3); shows its job count and the runner labels its queued jobs wait for | no, report only |
| `stuck-push` | push run with a newer push run of the same workflow on the same branch | no, report only |
| `off-limits` | matched `--skip-pr` / `--skip-run` | never |
| `live` | anything else, including every current-head run of an open PR | never |

Rules built into the code:

- never touches a current-head run of an open PR, or any push,
  `workflow_dispatch` or `schedule` run;
- a workflow whose name matches `--protect` (default `kernel`, case-insensitive)
  is cancelled only after its matrix expanded (more than one job). Cancelling
  the firmware Build Kernel placeholder leaves a "skipped" check that the
  Manet merge gate treats as final on that commit;
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

## Tests

```sh
python3 -m unittest discover -s tools/stale-runs -v
```
