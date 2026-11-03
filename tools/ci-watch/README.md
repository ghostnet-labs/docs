# CI watch

`ci_watch.py` watches all eight ghostnet-labs repos every 10 minutes from a
LaunchAgent on the Mac Studio and alerts when something needs a person. No
Claude session is involved. It is read-only on GitHub: it never cancels,
re-runs, pushes, merges or deletes.

Justin's rule (2026-11-03): anything a local script can do, a local script
does. Scheduled Claude tasks are the last resort, for work that needs judgment
or writing.

## What it checks

| Check | Alerts when | Level |
|---|---|---|
| Actions guard (`tools/stale-runs/actions_guard.py`) | Actions off, a disabled workflow, a ready PR with no checks after 20 min, no workflow run for 3 h while PRs are open | crit |
| PR head checks | a check fails, times out or needs action on the current head | crit |
| Cancelled check | a check on the head was cancelled and nothing replaced it (often the "Handle passing PRs" sweep) | warn |
| Merge state | a merge conflict; green with auto-merge on but behind its base | warn |
| Stuck | checks still running after `--stuck-hours` (3) | warn |
| Idle | a ready PR untouched for `--idle-hours` (24) | warn |
| Runner page (`--runner-page`) | any warn or crit alert on the runner status page: offline runner, job queued 20+ min, hosted stall, minutes, disk, swap | as the page says |
| Itself | GitHub unreadable three runs in a row | crit |
| News | a PR opened, merged, closed, or no longer red | info |
| Branches (hourly) | lists branches already in the default branch that no open PR uses; never deletes | report only |

Each problem alerts once when it appears and once when it clears. A repo that
could not be read keeps its last state, so a network blip never looks like a
fix.

## Where alerts go

Pick any combination:

- `--notify`: a macOS banner on the Mac running it.
- `--ntfy TOPIC`: a push to the free [ntfy](https://ntfy.sh) phone app. Pick a
  long random topic name; anyone who knows it can read the alerts. Alerts hold
  repo names, PR numbers and titles, nothing else.
- `--issue N`: [ghostnet-labs/setup #87](https://github.com/ghostnet-labs/setup/issues/87)
  (Issues are off in the forks). Its body is the live report, refreshed on
  every change and at least hourly; each alert is added as a comment. If the
  "Updated" line is more than an hour old, the script has stopped. GitHub does
  not notify you about your own token's comments, so this is the place to
  look, not a pager.
- `--min-level warn` keeps info news (merged, opened) out of banners and
  pushes; the issue still gets everything.

The report is also written to `~/.local/state/ci-watch/report.md`
(`python3 ci_watch.py report` prints it).

## Token

It reuses the stale-runs token (`~/.config/stale-runs/token`) if there is no
`~/.config/ci-watch/token` or `CI_WATCH_TOKEN`. Reads need **Actions**,
**Checks**, **Commit statuses**, **Contents** and **Pull requests**, all
read-only. `--issue` also needs **Issues: Read and write**: either add it to
the token, or put a separate token in `~/.config/ci-watch/issue-token`.

Every GET carries the ETag of its last answer (`~/.cache/ci-watch/etags.json`);
"304 not changed" answers are free, so a quiet run costs about 30 counted calls
(the first run about 120).

## Install on the Mac Studio

```sh
git clone --depth 1 https://github.com/ghostnet-labs/docs ~/ci-watch-src
python3 ~/ci-watch-src/tools/ci-watch/ci_watch.py --branch-hours 0   # one run by hand
python3 ~/ci-watch-src/tools/ci-watch/ci_watch.py launchd \
  --notify --ntfy <topic> --issue 87 --runner-page http://localhost:8090 \
  > ~/Library/LaunchAgents/com.ghostnet.ci-watch.plist
launchctl load ~/Library/LaunchAgents/com.ghostnet.ci-watch.plist
tail -f ~/Library/Logs/ci-watch.log
```

Update with `git -C ~/ci-watch-src pull`; the next run picks it up. Stop with
`launchctl unload ~/Library/LaunchAgents/com.ghostnet.ci-watch.plist`.

## Scheduled tasks it replaces

| Scheduled task | Was | Now |
|---|---|---|
| PR check watch loop ("Live PR check state report" thread, every 10 min plus :00/:30 reports and the stall guard) | Claude | this script; the :00/:30 report is the issue body |
| CI runner watchdog (hourly) | Claude | `runner_status.py serve --notify` already detects it; this script forwards the page's alerts with `--runner-page` |
| Stale-state sweep, read-only parts (every 2 h): red, conflicting and idle PRs, behind PRs, merged branches | Claude | this script |
| Request :50 live snapshot | Claude | retired; the report is the snapshot |
| Firmware 7-day branch cleanup (one-shot) | Claude | the hourly merged-branch list; deleting still needs Justin's typed line |

Kept as Claude, because they need judgment or writing: the stale-state sweep's
Linear checks (is a ticket's deliverable really merged?) and scheduled-task
health, the compute comparison refresh (prices, Linear, rewriting the page),
the hourly Manet update when it is on (it summarizes what threads report), and
one-off follow-ups a thread sets for itself.

## Tests

```sh
python3 -m unittest discover -s tools/ci-watch -v
```
