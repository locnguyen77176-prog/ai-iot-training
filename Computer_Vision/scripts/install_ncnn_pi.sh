#!/usr/bin/env bash
set -euo pipefail

NCNN_VERSION="${NCNN_VERSION:-20260526}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_ROOT="${TMPDIR:-/tmp}/visionflow-ncnn-${NCNN_VERSION}"

sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  build-essential cmake git ninja-build python3-dev python3-venv libgomp1

python3 -m venv "${PROJECT_DIR}/.venv"
"${PROJECT_DIR}/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
"${PROJECT_DIR}/.venv/bin/python" -m pip install -r "${PROJECT_DIR}/requirements-pi.txt"

if [[ ! -d "${BUILD_ROOT}/.git" ]]; then
  git clone --branch "${NCNN_VERSION}" --depth 1 --recurse-submodules \
    https://github.com/Tencent/ncnn.git "${BUILD_ROOT}"
fi

EXTRA_CMAKE_ARGS="-DNCNN_VULKAN=OFF -DNCNN_OPENMP=ON -DNCNN_BUILD_TOOLS=OFF -DNCNN_BUILD_EXAMPLES=OFF -DNCNN_BUILD_BENCHMARK=OFF" \
  CMAKE_BUILD_PARALLEL_LEVEL=4 \
  "${PROJECT_DIR}/.venv/bin/python" -m pip install --no-deps "${BUILD_ROOT}"

"${PROJECT_DIR}/.venv/bin/python" -c "import ncnn; print('NCNN Python OK:', ncnn.__file__)"
echo "Ready. Run: .venv/bin/python run_web.py --config config.pi.yaml"
