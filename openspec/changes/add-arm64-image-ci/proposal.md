<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## Why

The official container runtime is `linux/arm64`, but the current main-branch CI
checks only the Python package and does not build the submitted container for
that platform. An automated ARM64 image gate will catch Dockerfile, build
context, and architecture regressions before they reach `main`.

## What Changes

- Add a dedicated CI job for pushes to `main` and pull requests targeting
  `main` that configures QEMU and Docker Buildx using immutable action pins.
- Run the repository-owned `scripts/build-arm64.sh` entry point to build a
  single-platform `linux/arm64` image, load it into Docker, and verify the
  resulting image architecture.
- Add repository policy coverage for the ARM64 job, pinned setup actions, and
  the checked-in build script.
- Keep container publication, registry credentials, runtime benchmarks, and
  GitHub Release behavior outside this change.
- Limit public-disclosure scope to the workflow, build script, policy tests,
  and OpenSpec artifacts. Exclude secrets, private evaluation data, generated
  images, build caches, and benchmark results from the public candidate.

## Capabilities

### New Capabilities

- `arm64-container-ci`: Main-branch validation of the official ARM64 container
  build without publishing an image.

### Modified Capabilities

None.

## Impact

The change affects `.github/workflows/ci.yml`, `scripts/build-arm64.sh`,
repository policy tests, and their OpenSpec artifacts. It adds no production
dependency or external service, grants no write permission, and does not alter
the router runtime, scoring, schemas, release triggers, or release assets.
