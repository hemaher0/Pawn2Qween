#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

IMAGE_NAME="llm-router:test"
DOCKERFILE="$REPO_ROOT/container/Dockerfile"

echo "==> Building $IMAGE_NAME for linux/arm64"

docker buildx build \
  --platform linux/arm64 \
  -t "$IMAGE_NAME" \
  --load \
  -f "$DOCKERFILE" \
  "$REPO_ROOT"

echo
echo "==> Inspecting image"

ARCH="$(docker image inspect "$IMAGE_NAME" --format '{{.Architecture}}')"

echo "Architecture: $ARCH"

if [[ "$ARCH" != "arm64" ]]; then
  echo "ERROR: Expected arm64, got $ARCH" >&2
  exit 1
fi

echo "OK: $IMAGE_NAME is arm64"
