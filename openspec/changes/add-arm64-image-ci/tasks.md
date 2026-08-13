<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## 1. ARM64 CI Contract

- [x] 1.1 Add a focused repository policy test that requires the tracked build
  script, dedicated ARM64 job, immutable checkout/QEMU/Buildx action pins,
  setup-before-build ordering, script invocation, read-only permissions, and a
  non-publishing workflow boundary.
- [x] 1.2 Run the focused policy test and confirm it fails for the missing ARM64
  job and script metadata before changing the implementation.

## 2. CI Implementation

- [x] 2.1 Add the repository SPDX header to `scripts/build-arm64.sh` while
  preserving its existing single-platform build and architecture check.
- [x] 2.2 Resolve and review immutable commits for the official Docker QEMU and
  Buildx setup actions.
- [x] 2.3 Add the parallel `arm64-image` job to `.github/workflows/ci.yml` with
  checkout, QEMU, Buildx, and the repository script in dependency order.

## 3. Verification

- [x] 3.1 Rerun the focused repository policy test and shell syntax check,
  confirming both pass after the implementation.
- [x] 3.2 Run strict OpenSpec validation, lock consistency, Ruff, REUSE, the
  supported local unit test suite, and package construction.
- [x] 3.3 Run the ARM64 build when a Docker daemon is available; otherwise
  record the environment limitation and use the first pull-request CI run as
  the cross-platform build evidence.
- [x] 3.4 Review the final diff for scope, immutable action pins, accidental
  publication commands, credentials, and release-trigger changes.

## 4. Public Disclosure Review

- [x] 4.1 Review the OpenSpec artifacts, affected implementation delta, and
  deterministic check results under `CONTRIBUTING.md`, then report exactly one
  `PASS`, `BLOCK`, or `NEEDS_CONFIRMATION` verdict before any commit, push,
  archive, or release action.
