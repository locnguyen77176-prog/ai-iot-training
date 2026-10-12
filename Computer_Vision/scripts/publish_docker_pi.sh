#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

IMAGE="${VISIONFLOW_IMAGE:-}"
if [[ -z "${IMAGE}" ]]; then
  echo "ERROR: VISIONFLOW_IMAGE is required." >&2
  echo "Example: VISIONFLOW_IMAGE=dockerhub-user/visionflow-pi:latest $0" >&2
  exit 2
fi

command -v docker >/dev/null || {
  echo "ERROR: Docker is not installed." >&2
  exit 3
}
docker buildx version >/dev/null || {
  echo "ERROR: Docker Buildx is not installed." >&2
  exit 4
}

echo "Building and pushing ${IMAGE} for linux/arm64..."
docker buildx build \
  --platform linux/arm64 \
  --file Dockerfile.pi \
  --tag "${IMAGE}" \
  --push \
  .

echo "Published: ${IMAGE}"
