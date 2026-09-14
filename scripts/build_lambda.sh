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

test -f "${out_dir}/handler.py" || {
  echo "Lambda handler was not staged" >&2
  exit 1
}

echo "Python code build"