# CI hosts

How the Mac CI hosts (Mac Studio, MacBook Pro) and their Lima VMs are set up,
so any VM can be rebuilt the same way and drift is detected.

| VM | Host | Role | Runners |
|---|---|---|---|
| `ci-k3s` | Mac Studio | k3s + ARC: Linux ARM64 CI as ephemeral pods | scale sets `ghostnet-linux-arm64` (2 GiB pods, max 2), `ghostnet-linux-arm64-large` (4 GiB pod, max 1) and `ghostnet-gate` (256 MiB pods for firmware's PR and merge gates) |
| `gh-ubuntu` | Mac Studio | retired 2026-11-03: stopped, kept for rollback until about 2026-11-10, then deleted | none (the `studio-ubuntu-1..5` one-job slots are unloaded) |
| `gh-build` | Mac Studio | `build`: OpenWrt builds, Docker allowed | `studio-build-1` (one-job) |
| `gh-build-2` | Mac Studio | `build` | `studio-build-2` (one-job) |
| `gh-build` | MacBook Pro | `build` | `macbook-pro-build-1` |

Rules that must hold (checked by `verify-vm.sh`):

- `build` VMs (`gh-build`, `gh-build-2`): no `/usr/local/bin/runc` (the firmware
  Mac pilot fails if it exists). Docker is allowed, but only the Ubuntu
  `docker.io` package, whose runc lives in `/usr/bin`.
- `ubuntu` VM (only while `gh-ubuntu` still exists): `libpam0g-dev` and the Playwright libraries installed; Docker
  only when `provision/gh-ubuntu-extras.sh --with-docker` was run, and then the
  `docker-x86` label stays off jobs that fork PRs can reach.
- Root disk under 90%.

Files:

- `provision/install-yq.sh`: installs the pinned mikefarah yq (checksum-verified) into a Linux runner VM; `verify-vm.sh` flags yq older than the minimum CI needs (`CI_TOOL_MINIMUMS`).
- `verify-vm.sh <ubuntu|build>`: read-only drift check. The runner watchdog
  (`tools/runner-status/runner_watchdog.py`) runs it in each VM hourly and the
  status page alerts on drift.
- `provision/gh-ubuntu-extras.sh`: idempotent packages for `gh-ubuntu`. Goes
  away with the VM.

`ci-k3s` has no drift role: its runners are pods built from an immutable image,
so the image and the scale-set values are what to review, not the VM. The
watchdog does not manage ARC pods; the ARC controller replaces them.
- `lima/*.yaml` and the runner setup scripts: to be added from the live hosts'
  current files (collected read-only, secrets removed) in a follow-up commit.

Nothing here is applied automatically. Installing into a live VM needs
Justin's approval.
