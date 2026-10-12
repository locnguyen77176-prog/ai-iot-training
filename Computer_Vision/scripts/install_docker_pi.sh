#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo: sudo ./scripts/install_docker_pi.sh" >&2
  exit 2
fi

if [[ "$(dpkg --print-architecture)" != "arm64" ]]; then
  echo "ERROR: Raspberry Pi OS 64-bit (arm64) is required." >&2
  exit 3
fi

source /etc/os-release
CODENAME="${VERSION_CODENAME:-}"
if [[ "${CODENAME}" != "bookworm" && "${CODENAME}" != "trixie" ]]; then
  echo "ERROR: supported Debian base is bookworm or trixie; detected '${CODENAME}'." >&2
  exit 4
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "Docker Engine and Compose are already installed."
  docker --version
  docker compose version
  exit 0
fi

if dpkg-query -W -f='${Status}' docker.io 2>/dev/null | grep -q "install ok installed"; then
  echo "ERROR: the distro package docker.io is installed." >&2
  echo "Remove conflicting packages manually before installing Docker CE." >&2
  exit 5
fi

apt-get update
apt-get install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: ${CODENAME}
Components: stable
Architectures: arm64
Signed-By: /etc/apt/keyrings/docker.asc
EOF

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

TARGET_USER="${SUDO_USER:-}"
if [[ -n "${TARGET_USER}" && "${TARGET_USER}" != "root" ]]; then
  usermod -aG docker "${TARGET_USER}"
  echo "Added ${TARGET_USER} to the docker group. Log out/in or reboot before using Docker without sudo."
fi

docker run --rm hello-world
docker --version
docker compose version
