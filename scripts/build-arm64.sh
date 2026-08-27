#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

IMAGE_NAME="${IMAGE_NAME:-llm-router:test}"
REQUIRE_NATIVE_RUNTIME="${OSSP_REQUIRE_NATIVE_RUNTIME:-0}"
DOCKERFILE="$REPO_ROOT/container/Dockerfile"
BUILD_ROOT="$REPO_ROOT/build"
MODEL_DIR="$BUILD_ROOT/e5-model"
MODEL_SPEC="$REPO_ROOT/configs/e5-model.v1.json"
PREFLIGHT_REPORT="$BUILD_ROOT/e5-image-preflight.json"
FULL_RUNTIME_REPORT="$BUILD_ROOT/e5-full-runtime-check.json"
RECOVERY_JOURNAL_NAME="image-measurement-journal.json"
TRAIN_INPUT="$REPO_ROOT/data/materialized/train/inputs.json"
DEV_INPUT="$REPO_ROOT/data/materialized/dev/inputs.json"
PUBLIC_REGISTRY="$REPO_ROOT/data/public-data.v1.json"

mkdir -p "$BUILD_ROOT"
rm -f -- "$PREFLIGHT_REPORT" "$FULL_RUNTIME_REPORT"

if [[ "$REQUIRE_NATIVE_RUNTIME" != "0" && "$REQUIRE_NATIVE_RUNTIME" != "1" ]]; then
  echo "ERROR: OSSP_REQUIRE_NATIVE_RUNTIME must be 0 or 1" >&2
  exit 2
fi

for command_name in docker python3; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "ERROR: Required command is unavailable: $command_name" >&2
    exit 2
  fi
done

SERVER_ARCHITECTURE="$(docker info --format '{{.Architecture}}')"
if [[ "$SERVER_ARCHITECTURE" == "aarch64" ]]; then
  SERVER_ARCHITECTURE="arm64"
fi
if [[ "$REQUIRE_NATIVE_RUNTIME" == "1" \
  && "$SERVER_ARCHITECTURE" != "arm64" ]]; then
  echo "ERROR: OSSP_REQUIRE_NATIVE_RUNTIME=1 requires native linux/arm64 Docker" >&2
  exit 1
fi
if [[ "$REQUIRE_NATIVE_RUNTIME" == "1" \
  && ( ! -f "$TRAIN_INPUT" \
    || ! -f "$DEV_INPUT" \
    || ! -f "$PUBLIC_REGISTRY" ) ]]; then
  echo "ERROR: Materialized Train/Dev inputs are required for the native gate" >&2
  exit 1
fi

echo "==> Fetching and verifying the pinned E5 model"

python3 "$REPO_ROOT/tools/fetch_e5_model.py" \
  --spec "$MODEL_SPEC" \
  --output "$MODEL_DIR"

SOURCE_MANIFEST_SHA256="$(
  PYTHONPATH="$REPO_ROOT/src:$REPO_ROOT" \
    python3 "$REPO_ROOT/tools/benchmark_runtime.py" \
      --print-source-manifest-sha256
)"

OCI_LAYOUT=""
PREFLIGHT_WORK=""
BUILDER_NAME=""
BUILDER_ARGUMENTS=()

cleanup() {
  status=$?
  set +e
  if [[ -n "$BUILDER_NAME" ]]; then
    if ! docker buildx rm "$BUILDER_NAME" >/dev/null 2>&1; then
      echo "WARNING: Temporary Buildx builder cleanup failed: $BUILDER_NAME" >&2
      if [[ "$status" == "0" ]]; then
        status=1
      fi
    fi
  fi
  if [[ -n "$OCI_LAYOUT" ]]; then
    rm -rf -- "$OCI_LAYOUT"
  fi
  if [[ -n "$PREFLIGHT_WORK" ]]; then
    if [[ -f "$PREFLIGHT_WORK/$RECOVERY_JOURNAL_NAME" ]]; then
      echo "WARNING: Preserving recovery journal at $PREFLIGHT_WORK" >&2
    else
      rm -rf -- "$PREFLIGHT_WORK"
    fi
  fi
  exit "$status"
}
trap cleanup EXIT

OCI_LAYOUT="$(mktemp -d "$BUILD_ROOT/e5-oci-layout.XXXXXXXX")"
PREFLIGHT_WORK="$(mktemp -d -p /tmp pawn2qween-e5-preflight.XXXXXXXX)"

CURRENT_DRIVER=""
while IFS=: read -r key value; do
  if [[ "$key" == "Driver" ]]; then
    CURRENT_DRIVER="${value//[[:space:]]/}"
    break
  fi
done < <(docker buildx inspect)

if [[ "$CURRENT_DRIVER" != "docker-container" ]]; then
  BUILDER_CANDIDATE="ossp-e5-arm64-$$-$RANDOM$RANDOM"
  echo "==> Creating temporary OCI-capable Buildx builder: $BUILDER_CANDIDATE"
  if ! docker buildx create \
    --name "$BUILDER_CANDIDATE" \
    --driver docker-container \
    --bootstrap >/dev/null; then
    echo "ERROR: Buildx builder creation failed; inspect $BUILDER_CANDIDATE before cleanup" >&2
    exit 1
  fi
  BUILDER_NAME="$BUILDER_CANDIDATE"
  BUILDER_ARGUMENTS=(--builder "$BUILDER_NAME")
fi

echo "==> Building $IMAGE_NAME for linux/arm64"

docker buildx build \
  "${BUILDER_ARGUMENTS[@]}" \
  --platform linux/arm64 \
  --pull \
  --tag "$IMAGE_NAME" \
  --output type=docker \
  --output "type=oci,dest=$OCI_LAYOUT,tar=false,name=$IMAGE_NAME" \
  --build-arg "SOURCE_MANIFEST_SHA256=$SOURCE_MANIFEST_SHA256" \
  --file "$DOCKERFILE" \
  "$REPO_ROOT"

echo "==> Measuring image and running the constrained E5 smoke"

PYTHONPATH="$REPO_ROOT/src:$REPO_ROOT" \
  python3 "$REPO_ROOT/tools/preflight_submission_image.py" \
    --image "$IMAGE_NAME" \
    --oci-layout "$OCI_LAYOUT" \
    --input "$REPO_ROOT/data/toy/inputs.json" \
    --tier balanced \
    --work-directory "$PREFLIGHT_WORK" \
    --report "$PREFLIGHT_REPORT"

IMAGE_ID="$(
  python3 -c \
    'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["image"]["loaded_config_digest"])' \
    "$PREFLIGHT_REPORT"
)"
if [[ ! "$IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "ERROR: Preflight report did not bind an immutable local image ID" >&2
  exit 1
fi

if [[ "$SERVER_ARCHITECTURE" == "arm64" \
  && -f "$TRAIN_INPUT" \
  && -f "$DEV_INPUT" \
  && -f "$PUBLIC_REGISTRY" ]]; then
  echo "==> Running the native ARM64 full public runtime gate"
  PYTHONPATH="$REPO_ROOT/src:$REPO_ROOT" \
    python3 "$REPO_ROOT/tools/check_runtime.py" \
      --image "$IMAGE_ID" \
      --train-input "$TRAIN_INPUT" \
      --dev-input "$DEV_INPUT" \
      --registry "$PUBLIC_REGISTRY" \
      --report "$FULL_RUNTIME_REPORT"
elif [[ "$REQUIRE_NATIVE_RUNTIME" == "1" ]]; then
  echo "ERROR: Native linux/arm64 Docker and materialized Train/Dev inputs are required" >&2
  exit 1
else
  echo "INCONCLUSIVE: Native linux/arm64 full Train+Dev latency remains required"
fi

echo "OK: $IMAGE_NAME passed ARM64 packaging, size, and constrained smoke checks"
