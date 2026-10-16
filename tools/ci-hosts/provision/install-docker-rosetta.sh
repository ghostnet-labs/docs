#!/usr/bin/env bash
# Install Docker in a Lima build VM and check x86-64 containers work through Rosetta.
# Run inside the VM as root: limactl shell <vm> sudo bash install-docker-rosetta.sh
# Needs Justin's typed approval first: the runner user joins the docker group, which is
# root-equivalent on same-repo PR code. Rosetta must already be enabled in the VM's lima.yaml
# (rosetta: {enabled: true, binfmt: true}) and containerd off (containerd: {system: false, user: false}).
set -euo pipefail

RUNNER_USER="${RUNNER_USER:-$(logname 2>/dev/null || echo "${SUDO_USER:-}")}"
if [ -z "$RUNNER_USER" ]; then
  echo "Set RUNNER_USER to the runner's login." >&2
  exit 1
fi

# 1. Lima's own containerd units shadow Ubuntu's containerd and point at binaries that are gone,
# so dockerd fails with 203/EXEC. Move them aside before installing Docker (kept, not deleted).
DISABLED=/usr/local/lib/lima-containerd-disabled/systemd
mkdir -p "$DISABLED"
for unit in containerd buildkit stargz-snapshotter; do
  src="/usr/local/lib/systemd/system/$unit.service"
  if [ -e "$src" ]; then
    systemctl disable --now "$unit.service" 2>/dev/null || true
    mv "$src" "$DISABLED/"
  fi
done
systemctl daemon-reload

# 2. Ubuntu's docker.io, which brings containerd and runc under /usr/sbin and /usr/bin.
if ! command -v docker >/dev/null; then
  apt-get update
  apt-get install -y docker.io
fi

# 3. x86-64 images need the Rosetta binfmt handler that lima.yaml registers.
if [ ! -e /proc/sys/fs/binfmt_misc/rosetta ]; then
  echo "Rosetta binfmt is not registered; enable rosetta with binfmt in this VM's lima.yaml." >&2
  exit 1
fi

# 4. The runner user may use Docker.
usermod -aG docker "$RUNNER_USER"
systemctl enable --now docker

# 5. The board-build preflight fails when /usr/local/bin/runc exists (it breaks dockerd on arm64 hosts).
if [ -e /usr/local/bin/runc ]; then
  echo "/usr/local/bin/runc exists; move it aside before building." >&2
  exit 1
fi

docker version --format 'docker {{.Server.Version}}'
docker run --rm hello-world >/dev/null && echo "arm64 containers work"
docker run --rm --platform linux/amd64 hello-world >/dev/null && echo "amd64 containers work"
echo "/usr/local/bin/runc absent (good)"
