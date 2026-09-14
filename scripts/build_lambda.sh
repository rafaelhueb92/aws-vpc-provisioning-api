#!/usr/bin/env bash

set -euo pipefail

app_dir=$1
out_dir=$2
python_version=$3
platform="manylinux2014_x86_64"

rm -rf "${out_dir}"
mkdir -p "${out_dir}"

pip install --quiet --target "${out_dir}" \
  --platform "${platform}" --implementation cp \
  --python-version "${python_version}" --only-binary=:all: \
  -r "${app_dir}/requirements.txt"

cp -r "${app_dir}"/* "${out_dir}/"
find "${out_dir}" -type d -name "__pycache__" -exec rm -rf {} +

(
  cd "${out_dir}"
  zip -q -r lambda.zip . -x '*.pyc'
)

echo "Lambda package built at ${out_dir}/lambda.zip"
ls -lh "${out_dir}/lambda.zip"