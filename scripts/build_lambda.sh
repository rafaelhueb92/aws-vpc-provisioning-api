#!/usr/bin/env bash
#
# Single implementation of the Lambda deployment package build, shared by the
# CI workflow (.github/workflows/deploy.yml) and the terraform local-exec
# (infra/lambda.tf).
#
# The package is staged in --out-dir (dependencies installed for the target
# platform plus the application source) and archived to <out-dir>/lambda.zip.
# A stamp file records the hash of every input, so the build is skipped when
# the package is already up to date. That is what keeps CI from building the
# same artifact twice: the workflow builds before `terraform plan` (so
# source_code_hash is real), and the local-exec that runs before
# `terraform apply` reuses it instead of repeating the work.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"

app_dir="app"
out_dir="infra/build"
python_version="3.12"
python_bin="${PYTHON_BIN:-python3}"
platform="manylinux2014_x86_64"
implementation="cp"
force=0

# Bump when the packaging recipe changes (layout, what gets copied, ...) so an
# already staged package is rebuilt instead of being reused.
recipe_version=2

# Paths that never belong in the artifact: the local virtualenv, tests, agent
# and tooling caches.
exclude_patterns=(
  venv
  test
  .abacusai
  __pycache__
  '*.pyc'
  .pytest_cache
  .ruff_cache
)

usage() {
  cat <<'USAGE'
Build the Lambda deployment package (dependencies + application source).

Usage: scripts/build_lambda.sh [options]

Options:
  --app-dir DIR          Application source directory (default: app)
  --out-dir DIR          Staging directory for the package (default: infra/build)
  --python-version VER   Target runtime version, e.g. 3.12 (default: 3.12)
  --python BIN           Interpreter used for pip (default: $PYTHON_BIN or python3)
  --platform TAG         Wheel platform tag (default: manylinux2014_x86_64)
  --implementation TAG   Wheel implementation tag (default: cp)
  --force                Rebuild even when the package is up to date
  -h, --help             Show this help

Relative paths are resolved against the repository root. The archive is
written to <out-dir>/lambda.zip and is only rebuilt when the application
sources, requirements.txt, target version or platform changed.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --app-dir) app_dir="$2"; shift 2 ;;
    --out-dir) out_dir="$2"; shift 2 ;;
    --python-version) python_version="$2"; shift 2 ;;
    --python) python_bin="$2"; shift 2 ;;
    --platform) platform="$2"; shift 2 ;;
    --implementation) implementation="$2"; shift 2 ;;
    --force) force=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown option '$1'" >&2; usage >&2; exit 2 ;;
  esac
done

resolve_path() {
  case "$1" in
    /*) printf '%s\n' "$1" ;;
    *) printf '%s\n' "${repo_root}/$1" ;;
  esac
}

app_dir="$(resolve_path "${app_dir}")"
out_dir="$(resolve_path "${out_dir}")"
zip_path="${out_dir}/lambda.zip"
stamp_file="${out_dir}/.build-stamp"

rsync_excludes=()
tar_excludes=()
for pattern in "${exclude_patterns[@]}"; do
  rsync_excludes+=(--exclude "${pattern}")
  tar_excludes+=(--exclude="${pattern}")
done

if [ ! -f "${app_dir}/requirements.txt" ]; then
  echo "error: ${app_dir}/requirements.txt not found" >&2
  exit 1
fi

hash_stream() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum | cut -d' ' -f1
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 | cut -d' ' -f1
  else
    openssl dgst -sha256 | awk '{ print $NF }'
  fi
}

hash_file() {
  hash_stream < "$1"
}

compute_stamp() {
  {
    printf 'recipe_version=%s\n' "${recipe_version}"
    printf 'excludes=%s\n' "${exclude_patterns[*]}"
    printf 'python_version=%s\n' "${python_version}"
    printf 'platform=%s\n' "${platform}"
    printf 'implementation=%s\n' "${implementation}"
    printf 'requirements=%s\n' "$(hash_file "${app_dir}/requirements.txt")"
    while IFS= read -r relative; do
      printf '%s=%s\n' "${relative}" "$(hash_file "${app_dir}/${relative}")"
    done < <(
      find "${app_dir}" -type f -name '*.py' \
        -not -path '*/venv/*' -not -path '*/test/*' \
        -not -path '*/__pycache__/*' -not -path '*/.abacusai/*' \
        | sed "s#^${app_dir}/##" | LC_ALL=C sort
    )
  } | hash_stream
}

current_stamp="$(compute_stamp)"

if [ "${force}" -eq 0 ] && [ -f "${zip_path}" ] && [ -f "${stamp_file}" ] \
  && [ "$(cat "${stamp_file}")" = "${current_stamp}" ]; then
  echo "lambda package is up to date (${current_stamp:0:12}); skipping build"
  ls -lh "${zip_path}"
  exit 0
fi

echo "building lambda package for python ${python_version} (${platform})"
rm -rf "${out_dir}"
mkdir -p "${out_dir}"

"${python_bin}" -m pip install --quiet --target "${out_dir}" \
  --platform "${platform}" --implementation "${implementation}" \
  --python-version "${python_version}" --only-binary=:all: \
  -r "${app_dir}/requirements.txt"

if command -v rsync >/dev/null 2>&1; then
  rsync -a "${rsync_excludes[@]}" "${app_dir}/" "${out_dir}/"
else
  (
    cd "${app_dir}"
    tar cf - "${tar_excludes[@]}" .
  ) | (
    cd "${out_dir}"
    tar xf -
  )
fi

(
  cd "${out_dir}"
  rm -f lambda.zip
  zip -q -r lambda.zip . -x 'lambda.zip' '.build-stamp' '*__pycache__*' '*.pyc'
)

printf '%s\n' "${current_stamp}" > "${stamp_file}"

ls -lh "${zip_path}"
unzip -l "${zip_path}" | grep -E 'handler\.py|_pydantic_core' \
  || echo "warning: expected entries (handler.py, _pydantic_core) not found in lambda.zip"
