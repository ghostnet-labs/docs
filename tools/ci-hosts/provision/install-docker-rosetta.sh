#!/usr/bin/env bash
# Install Docker Engine in a Lima build VM and enable x86-64 containers through Rosetta.
# Run inside the VM as root: limactl shell <vm> sudo bash install-docker-rosetta.sh
# Needs Justin's typed approval first (the runner user joins the docker group, which is root-equivalent).
set -euo pipefail

RUNNER_USER="${RUNNER_USER:-$(logname 2>/dev/null || echo "$SUDO_USER")}"

# 1. Docker Engine from Docker's apt repository.
if ! command -v docker >/dev/null; then
  apt-get update
  apt-get install -y ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io
fi

# 2. x86-64 images: the Lima Rosetta mount registers binfmt for amd64.
if [ ! -x /mnt/lima-rosetta/rosetta ]; then
  echo "Rosetta is not mounted in this VM; enable rosetta in its lima.yaml first." >&2
  exit 1
fi
if [ ! -e /proc/sys/fs/binfmt_misc/rosetta ]; then
  update-binfmts --install rosetta /mnt/lima-rosetta/rosetta \
    --magic "\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x3e\x00" \
    --mask "\xff\xff\xff\xff\xff\xfe\xfe\x00\xff\xff\xff\xff\xff\xff\xff\xff\xfe\xff\xff\xff" \
    --credentials yes --preserve yes --fix-binary yes
fi

# 3. The runner user may use Docker.
usermod -aG docker "$RUNNER_USER"
systemctl enable --now docker

docker version --format 'docker {{.Server.Version}}'
docker run --rm --platform linux/amd64 hello-world >/dev/null && echo "amd64 containers work"
# Re-check that the board-build preflight still holds: Docker's containerd must not put runc in /usr/local/bin.
test ! -x /usr/local/bin/runc && echo "/usr/local/bin/runc absent (good)"
