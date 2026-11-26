# Studio runner fallback

Same-repository CI in the ghostnet-labs repos runs on the Mac Studio: the
macOS runners on the host (`mac`), the ARC pods in the `ci-k3s` VM (`arc`:
`ghostnet-linux-arm64`, `ghostnet-linux-arm64-large`, `ghostnet-gate`) and the
OpenWrt builders (`build`: `openwrt-build`). When the Studio is off, those jobs
wait 24 hours and GitHub cancels them, so the merge gates never pass (from
2026-11-22, docs #197's checks waited a day each and were cancelled).

With this fallback a job whose pool is offline runs on its GitHub-hosted
fallback instead (the same label fork PRs use), so hosted minutes are spent
only during an outage.

## How a workflow uses it

```yaml
jobs:
  studio:
    name: Studio runners
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    permissions:
      actions: read
    outputs:
      mac: ${{ steps.pick.outputs.mac }}
      arc: ${{ steps.pick.outputs.arc }}
      build: ${{ steps.pick.outputs.build }}
    steps:
      - id: pick
        uses: ghostnet-labs/docs/.github/actions/studio-runners@<docs sha>
        with:
          runner-token: ${{ secrets.RUNNER_READ_TOKEN }}
  gate:
    needs: studio
    if: ${{ !cancelled() && github.event.action != 'closed' }}
    runs-on: ${{ github.event.pull_request.head.repo.full_name == github.repository && needs.studio.outputs.mac != 'false' && fromJSON('["self-hosted", "macOS", "ARM64"]') || 'ubuntu-24.04' }}
```

`project/scripts/add_studio_fallback.py WORKFLOW --sha SHA JOB=POOL` writes
this for you. Runner policy (`project/scripts/check_runners.py`) accepts the
`needs.studio.outputs.<pool> != 'false' &&` term only in front of a fork-guarded
pick of that pool, and the `studio` job only as one step of the pinned action.

Safety:

- `!= 'false'`: an empty answer (the check crashed, or GitHub could not start
  it) keeps the self-hosted route. `!cancelled()` keeps a failed check from
  skipping the job, because a skipped required check would count as passed.
- Fork PRs never get the token and stay on hosted runners as before.

## How offline is decided

`studio_runners.py pick` (the action runs it, Python 3 standard library):

- **With `RUNNER_READ_TOKEN`**: the org runner list. `mac` and `build` are
  offline when none of their runners is online (retired `gh-ubuntu*` and
  `studio-ubuntu-*` registrations are ignored). ARC pods are listed only while
  they run, so `arc` is online while any ARC pod or any macOS runner on the same
  host is online, and offline when the macOS runners are offline too or when no
  pod is listed and an ARC job has waited 30+ minutes.
- **Without it**, or when GitHub rejects it: this repository's own recent jobs.
  A pool is offline when one of its jobs has waited 30+ minutes, or was
  cancelled after waiting 6+ hours without a runner, and no job on that pool got
  a runner after it was queued. A pool with no evidence of its own follows an
  offline Studio pool. This is slower to notice an outage and slower to notice
  the Studio is back (up to 48 hours), so set the token.

The job summary shows each pool's route and why, and every run that falls back
carries a `Studio runners offline` warning.

## Rescuing runs that were already waiting

Runs queued before the Studio went off keep waiting on it. "Handle passing PRs"
(hosted, in every repo) runs `studio_runners.py rescue`: for offline pools it
cancels and re-runs runs waiting 30+ minutes on them, and re-runs PR runs that
GitHub cancelled after a day without a runner, when they are the newest run of
their workflow on the PR's current head. It only touches runs whose workflow
has a `Studio runners` job (anything else would wait on the Studio again), at
most 5 per sweep and never past the third attempt. A PR opened before its repo
got the fallback needs its branch updated first; the sweep does that for
Claude PRs that are behind.

## The token

`RUNNER_READ_TOKEN` is a fine-grained personal access token with resource
owner `ghostnet-labs`, no repository access, and one organization permission:
**Self-hosted runners: Read-only**. It is an organization secret for the public
repos (<https://github.com/organizations/ghostnet-labs/settings/secrets/actions>)
and a repository secret in private setup
(<https://github.com/ghostnet-labs/setup/settings/secrets/actions>), whose
hourly guard comments on setup #87 when the fallback starts or ends and when the
token is rejected or close to expiry.

Tests: `python3 -m unittest discover -s tools/studio-runners`.
