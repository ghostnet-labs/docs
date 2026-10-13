#!/usr/bin/env bash
# Extra packages for the gh-ubuntu VM (Linux ARM64 runners), idempotent.
# Run inside the VM as root:  sudo bash gh-ubuntu-extras.sh [--with-docker]
#
#  - libpam0g-dev and the Playwright browser libraries: openmanetd e2e.
#  - --with-docker: Docker plus Rosetta amd64 emulation for the docker-x86
#    label (luci Test x86_64, packages Build packages). NEVER run this in an
#    openwrt-build VM (gh-build, gh-build-2): the firmware pilot fails if
#    /usr/local/bin/runc exists there. Docker here uses distro packages, so
#    runc lands in /usr/bin.
#    The runner user in the docker group is root-equivalent: keep the
#    docker-x86 label off any job that fork PRs can reach.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }

apt-get update -qq
apt-get install -y --no-install-recommends libpam0g-dev git
# Playwright (chromium) runtime libraries; libasound2 was renamed on Ubuntu 24.04.
apt-get install -y --no-install-recommends libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
  libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
  libpango-1.0-0 libcairo2 fonts-liberation
apt-get install -y --no-install-recommends libasound2t64 || apt-get install -y --no-install-recommends libasound2

if [ "${1:-}" = "--with-docker" ]; then
  [ -e /proc/sys/fs/binfmt_misc/rosetta ] || \
    echo "WARNING: Rosetta binfmt is not registered; set rosetta.enabled and rosetta.binfmt in this VM's lima.yaml and restart it, or amd64 images will not run." >&2
  apt-get install -y --no-install-recommends docker.io
  systemctl enable --now docker
  # Daily prune so JIT slots (which wipe HOME and _work, not /var/lib/docker) cannot fill the disk.
  cat > /etc/cron.daily/docker-prune <<'CRON'
#!/bin/sh
docker system prune -f --filter until=72h >/dev/null 2>&1 || true
CRON
  chmod 0755 /etc/cron.daily/docker-prune
  echo "Docker installed. Add runner users to the docker group only for slots labelled docker-x86."
fi
echo "gh-ubuntu extras done"
