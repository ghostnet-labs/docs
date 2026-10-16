#!/usr/bin/env bash
# Install the OpenWrt firmware build dependencies in a Lima build VM (arm64).
# Run inside the VM as root: limactl shell <vm> sudo bash install-build-deps.sh
# The list matches the dpkg-query check in firmware build-firmware.yml. gcc-multilib is not
# packaged for arm64 and is not needed. It also refuses to continue if Lima's containerd put
# runc in /usr/local/bin, which breaks the dockerd package build on an arm64 host.
set -euo pipefail

if [ -x /usr/local/bin/runc ]; then
  echo "/usr/local/bin/runc exists: set 'containerd: {system: false, user: false}' in the VM's lima.yaml," >&2
  echo "then move Lima's nerdctl-full binaries out of /usr/local/bin before building." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y build-essential clang flex g++ gawk git gettext libncurses-dev libssl-dev \
  python3-setuptools rsync unzip golang-go zlib1g-dev swig file wget libnl-3-dev libnl-genl-3-dev \
  libgps-dev libcap-dev pkg-config libopus-dev libopusfile-dev portaudio19-dev net-tools \
  libpcre3-dev upx-ucl

dpkg-query -W build-essential clang flex gawk git gettext libncurses-dev libssl-dev \
  python3-setuptools rsync unzip golang-go zlib1g-dev swig file wget libnl-3-dev libnl-genl-3-dev \
  libgps-dev libcap-dev pkg-config libopus-dev libopusfile-dev portaudio19-dev net-tools \
  libpcre3-dev upx-ucl >/dev/null && echo "build dependencies present"
