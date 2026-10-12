#!/bin/sh
set -eu

cd /app

for model_file in \
  models/yolo26n_ncnn_int8/model.ncnn.param \
  models/yolo26n_ncnn_int8/model.ncnn.bin \
  models/osnet_x0_25_ncnn_model/model.ncnn.param \
  models/osnet_x0_25_ncnn_model/model.ncnn.bin
do
  if [ ! -s "${model_file}" ]; then
    echo "FATAL: missing or empty model file: ${model_file}" >&2
    exit 2
  fi
done

python -c "import ncnn; print('NCNN runtime:', ncnn.__file__)"

if [ "${RUN_NCNN_SMOKE:-1}" = "1" ]; then
  python scripts/smoke_ncnn.py --config "${VISIONFLOW_CONFIG:-config.pi.yaml}"
fi

exec python run_web.py --config "${VISIONFLOW_CONFIG:-config.pi.yaml}"
