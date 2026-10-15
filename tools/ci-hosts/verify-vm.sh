#!/usr/bin/env bash
# Drift check for one CI VM. Read-only. Usage: verify-vm.sh <ubuntu|build>
# Prints one line per problem ("FAIL: ...") and exits 0; no output = no drift.
# The runner-status watchdog pipes this into each Lima VM once an hour.
set -u
role="${1:-}"
fail() { echo "FAIL: $*"; }

case "$role" in
  build)
    # openwrt-build VMs: the firmware pilot fails if /usr/local/bin/runc exists.
    # Docker (Ubuntu docker.io, with its own containerd and runc in /usr/bin) is
    # allowed here since Justin approved it for gh-build and gh-build-2.
    [ -e /usr/local/bin/runc ] && fail "/usr/local/bin/runc exists (breaks the OpenWrt build)"
    if command -v docker >/dev/null 2>&1; then
      dpkg -s docker.io >/dev/null 2>&1 || fail "docker is not the Ubuntu docker.io package (runc could land in /usr/local/bin)"
      [ -e /usr/bin/runc ] || fail "docker is installed but /usr/bin/runc is missing"
    fi
    for c in make gcc git python3; do
      command -v "$c" >/dev/null 2>&1 || fail "missing build tool: $c"
    done
    ;;
  ubuntu)
    for pkg in libpam0g-dev libnss3 libgbm1 git; do
      dpkg -s "$pkg" >/dev/null 2>&1 || fail "missing package: $pkg (run provision/gh-ubuntu-extras.sh)"
    done
    if [ "${CI_HOSTS_REQUIRE_DOCKER:-0}" = 1 ]; then
      command -v docker >/dev/null 2>&1 || fail "docker is not installed"
      [ -e /proc/sys/fs/binfmt_misc/rosetta ] || fail "Rosetta amd64 binfmt is not registered (enable rosetta.binfmt in lima.yaml)"
    fi
    ;;
  *)
    echo "usage: $0 <ubuntu|build>" >&2
    exit 2
    ;;
esac

used=$(df -P / | awk 'NR==2 {gsub("%","",$5); print $5}')
[ "${used:-0}" -ge 90 ] && fail "root disk ${used}% full"
exit 0
