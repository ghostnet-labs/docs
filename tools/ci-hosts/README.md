# CI hosts

How the Mac CI hosts (Mac Studio, MacBook Pro) and their Lima VMs are set up,
so any VM can be rebuilt the same way and drift is detected.

| VM | Host | Role | Runners |
|---|---|---|---|
| `gh-ubuntu` | Mac Studio | `ubuntu`: light CI, e2e, optional Docker/x86 | `studio-ubuntu-1..5` (one-job) |
| `gh-build` | Mac Studio | `build`: OpenWrt builds | `studio-build-1` (one-job) |
| `gh-build-2` | Mac Studio | `build` | `studio-build-2` (one-job) |
| `gh-build` | MacBook Pro | `build` | `macbook-pro-build-1` |

Rules that must hold (checked by `verify-vm.sh`):

- `build` VMs: no `/usr/local/bin/runc`, containerd off, no Docker. The firmware
  Mac pilot fails if runc is there.
- `ubuntu` VM: `libpam0g-dev` and the Playwright libraries installed; Docker
  only when `provision/gh-ubuntu-extras.sh --with-docker` was run, and then the
  `docker-x86` label stays off jobs that fork PRs can reach.
- Root disk under 90%.

Files:

- `verify-vm.sh <ubuntu|build>`: read-only drift check. The runner watchdog
  (`tools/runner-status/runner_watchdog.py`) runs it in each VM hourly and the
  status page alerts on drift.
- `provision/gh-ubuntu-extras.sh`: idempotent packages for `gh-ubuntu`.
- `lima/*.yaml` and the runner setup scripts: to be added from the live hosts'
  current files (collected read-only, secrets removed) in a follow-up commit.

Nothing here is applied automatically. Installing into a live VM needs
Justin's approval.
