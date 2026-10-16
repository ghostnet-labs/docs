#!/usr/bin/env bash
# Install the pinned mikefarah yq into /usr/local/bin on a Linux runner VM,
# idempotent. Run inside the VM as root:  sudo bash install-yq.sh
# setup's "Setup state" test needs yq >= 4.47 (nested TOML encoding); the
# distro/older binaries (4.44.x) fail it. Keep YQ_VERSION >= CI_TOOL_MINIMUMS in verify-vm.sh.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
YQ_VERSION=v4.54.1
case "$(uname -m)" in
  aarch64|arm64) arch=arm64; sum=189088da0c6429ec5178dfaab1a114805f6cab0b61b165ab236efedf1d57a71b ;;
  x86_64|amd64)  arch=amd64; sum=8e34fc298390875de416e6a4afcb8cabeceb25d9aa8506c1a2f9353cf702ea5f ;;
  *) echo "unsupported arch $(uname -m)" >&2; exit 1 ;;
esac
if command -v yq >/dev/null 2>&1 && yq --version 2>/dev/null | grep -q "version ${YQ_VERSION}\$"; then
  echo "yq ${YQ_VERSION} already installed"; exit 0
fi
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
curl -fsSL "https://github.com/mikefarah/yq/releases/download/${YQ_VERSION}/yq_linux_${arch}" -o "$tmp"
echo "${sum}  ${tmp}" | sha256sum -c - >/dev/null || { echo "yq checksum mismatch" >&2; exit 1; }
install -m 0755 "$tmp" /usr/local/bin/yq
yq --version
