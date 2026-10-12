#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

docker image inspect visionflow-pi:latest >/dev/null
mkdir -p dist
docker save visionflow-pi:latest | gzip -1 > dist/visionflow-pi-arm64.tar.gz
sha256sum dist/visionflow-pi-arm64.tar.gz > dist/visionflow-pi-arm64.tar.gz.sha256
echo "Exported dist/visionflow-pi-arm64.tar.gz"
