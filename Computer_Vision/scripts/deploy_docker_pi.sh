#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

ARCH="$(uname -m)"
if [[ "${ARCH}" != "aarch64" && "${ARCH}" != "arm64" ]]; then
  echo "ERROR: Raspberry Pi OS 64-bit is required; detected ${ARCH}." >&2
  exit 2
fi

for model_file in \
  models/yolo26n_person_v1_320_ncnn_int8/model.ncnn.param \
  models/yolo26n_person_v1_320_ncnn_int8/model.ncnn.bin \
  models/osnet_x0_25_ncnn_model/model.ncnn.param \
  models/osnet_x0_25_ncnn_model/model.ncnn.bin
do
  [[ -s "${model_file}" ]] || { echo "ERROR: missing ${model_file}" >&2; exit 3; }
done

command -v docker >/dev/null || {
  echo "ERROR: Docker is not installed. Install Docker Engine first." >&2
  exit 4
}
docker compose version >/dev/null || {
  echo "ERROR: Docker Compose plugin is not installed." >&2
  exit 5
}

mkdir -p uploads
touch database.db
chmod +x docker/entrypoint.sh

VIDEO_DEVICE="${VIDEO_DEVICE:-/dev/video0}"
if [[ ! -e "${VIDEO_DEVICE}" ]]; then
  echo "ERROR: camera device ${VIDEO_DEVICE} does not exist." >&2
  echo "Example: VIDEO_DEVICE=/dev/video2 ./scripts/deploy_docker_pi.sh" >&2
  exit 6
fi

export VIDEO_DEVICE
if [[ "${PULL_IMAGE:-0}" == "1" ]]; then
  if [[ -z "${VISIONFLOW_IMAGE:-}" ]]; then
    echo "ERROR: set VISIONFLOW_IMAGE when PULL_IMAGE=1." >&2
    echo "Example: VISIONFLOW_IMAGE=user/visionflow-pi:latest PULL_IMAGE=1 $0" >&2
    exit 7
  fi
  docker compose -f docker-compose.pi.yml pull visionflow
  docker compose -f docker-compose.pi.yml up -d --no-build
else
  docker compose -f docker-compose.pi.yml build --pull
  docker compose -f docker-compose.pi.yml up -d
fi

CONTAINER_ID="$(docker compose -f docker-compose.pi.yml ps -q visionflow)"
echo "Waiting for VisionFlow healthcheck..."
for _ in $(seq 1 60)
do
  STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}starting{{end}}' "${CONTAINER_ID}" 2>/dev/null || true)"
  if [[ "${STATUS}" == "healthy" ]]; then
    IP_ADDR="$(hostname -I | awk '{print $1}')"
    echo "VisionFlow is healthy: http://${IP_ADDR:-127.0.0.1}:8000"
    docker compose -f docker-compose.pi.yml ps
    exit 0
  fi
  if [[ "${STATUS}" == "unhealthy" ]]; then
    docker compose -f docker-compose.pi.yml logs --tail=200 visionflow
    exit 8
  fi
  sleep 5
done

docker compose -f docker-compose.pi.yml logs --tail=200 visionflow
echo "ERROR: container did not become healthy within 5 minutes." >&2
exit 9
