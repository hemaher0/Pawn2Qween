#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

set -u -o pipefail

if (( $# == 0 )); then
  echo "usage: $0 <unittest-args...>" >&2
  exit 64
fi

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd -P)"
UV_CACHE_ROOT=/tmp/Pawn2Qween-uv-cache
UV_PYTHON_ROOT=/tmp/Pawn2Qween-uv-python

if [[ ! -f "$REPOSITORY_ROOT/pyproject.toml" || ! -f "$REPOSITORY_ROOT/uv.lock" ]]; then
  echo "ERROR: runner is not inside the Pawn2Qween repository" >&2
  exit 2
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is not available" >&2
  exit 2
fi

cd "$REPOSITORY_ROOT"

run_version() {
  local version="$1"
  local version_slug="$2"
  shift 2

  local project_environment="/tmp/Pawn2Qween-venv-${version_slug}"
  local -a uv_environment=(
    "UV_CACHE_DIR=$UV_CACHE_ROOT"
    "UV_PYTHON_INSTALL_DIR=$UV_PYTHON_ROOT"
    "UV_PROJECT_ENVIRONMENT=$project_environment"
    "UV_PYTHON=$version"
    "PYTHONPATH=src"
  )

  echo "==> Python $version: preparing locked default-only environment"
  if ! env "${uv_environment[@]}" uv sync --locked --no-dev; then
    echo "RESULT python=$version status=environment-failed" >&2
    return 2
  fi

  if ! env "${uv_environment[@]}" uv run --locked --no-dev --no-sync \
    python -c 'import sys; expected=tuple(map(int, sys.argv[1].split("."))); raise SystemExit(0 if sys.version_info[:2] == expected else 1)' \
    "$version"; then
    echo "RESULT python=$version status=environment-failed reason=interpreter-mismatch" >&2
    return 2
  fi

  echo "==> Python $version: running unittest $*"
  if ! env "${uv_environment[@]}" uv run --locked --no-dev --no-sync \
    python -m unittest "$@"; then
    echo "RESULT python=$version status=test-failed" >&2
    return 1
  fi

  echo "RESULT python=$version status=passed"
  return 0
}

overall_status=0
for version_spec in "3.9:py39" "3.11:py311"; do
  version="${version_spec%%:*}"
  version_slug="${version_spec##*:}"
  run_version "$version" "$version_slug" "$@"
  version_status=$?
  if (( version_status == 2 )); then
    overall_status=2
  elif (( version_status == 1 && overall_status == 0 )); then
    overall_status=1
  fi
done

exit "$overall_status"
