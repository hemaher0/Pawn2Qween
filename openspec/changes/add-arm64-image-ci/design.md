<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## Context

See `proposal.md` for motivation and
`specs/arm64-container-ci/spec.md` for observable behavior. The current CI has
parallel Python quality and supported-version test jobs on pushes to `main` and
pull requests targeting `main`. The container Dockerfile targets a pinned
multi-platform Python base and executes an ARM64 `RUN` instruction during a
cross-platform build. Repository automation pins actions by commit SHA, grants
`contents: read` by default, and enforces licensing and workflow boundaries in
repository policy tests.

An executable `scripts/build-arm64.sh` already expresses the local build and
architecture inspection sequence, but it is not tracked or invoked by CI and
does not yet carry repository SPDX metadata.

## Goals / Non-Goals

**Goals:**

- Add an independently visible ARM64 image gate to every existing CI trigger.
- Make the same checked-in script the local and CI entry point for this narrow
  build check.
- Support the standard hosted Linux runner without new infrastructure.
- Preserve action pinning, read-only permissions, and repository policy
  enforcement.

**Non-Goals:**

- Publish a container image or alter tag-gated GitHub Releases.
- Run the full official isolation, resource-limit, benchmark, or package
  inventory checks.
- Add caching, a self-hosted runner, registry credentials, or a new external
  service.
- Change runtime, scoring, schema, or submitted-image behavior.

## Decisions

### Add a parallel container-image job to the existing CI workflow

The workflow will gain a separate `arm64-image` job with the same existing
push and pull-request triggers. Keeping the build separate makes its status and
logs easy to diagnose and lets it run in parallel with Python quality and test
jobs. Adding the build as a step in `quality` was considered, but it would
serialize unrelated gates and obscure whether a failure came from packaging or
the container toolchain. A separate workflow was also considered, but it would
duplicate trigger, permission, and concurrency policy.

### Use QEMU and Buildx on the standard hosted Linux runner

The job will configure the official Docker QEMU and Buildx setup actions before
invoking the repository script. This supports the Dockerfile's ARM64 `RUN`
instruction on the standard x86_64 runner and keeps runner selection aligned
with the rest of CI. A native hosted ARM64 label was considered, but it adds a
runner-availability dependency and reduces portability. A self-hosted ARM64
runner would best match the official platform, but it introduces infrastructure
and trust boundaries that are disproportionate to an architecture build gate.

All action references will use reviewed immutable commit SHAs with version
comments, following the existing workflow convention.

### Keep the shell script as the build contract

CI will call `./scripts/build-arm64.sh` rather than duplicating the Buildx and
inspection commands in YAML. The script will receive only the missing SPDX
header; its single-platform `--load` build and `docker image inspect` check are
already the smallest behavior needed for this gate. Registry push flags,
runtime execution, and resource checks will not be added.

### Characterize the workflow contract with repository policy tests first

Repository policy tests will require the script, dedicated job, setup action
pins, setup-before-build ordering, script invocation, read-only/non-publishing
boundary, and SPDX markers. The test will be observed failing before workflow
and script edits, then rerun after the minimal implementation.

## Risks / Trade-offs

- **[ARM emulation makes the build slower than a native build]** → Keep the
  small build in its own parallel job and add caching only if measured CI time
  later justifies another change.
- **[A Docker setup action pin eventually becomes stale]** → Update pins through
  an explicit reviewed dependency change while the immutable reference keeps
  current runs reproducible.
- **[A transient base-registry or hosted-runner failure blocks CI]** → Fail
  visibly as an infrastructure error; do not weaken or silently skip the gate.
- **[Local environments may not expose a Docker daemon]** → Run deterministic
  policy, syntax, lint, and OpenSpec checks locally; let GitHub Actions provide
  the real cross-platform build evidence.

## Migration Plan

1. Add and run the focused repository policy test to establish the missing CI
   behavior.
2. Add SPDX metadata to the existing script and wire the pinned Docker setup
   actions plus script invocation into the CI workflow.
3. Run focused policy tests, shell syntax validation, repository quality gates,
   and strict OpenSpec validation.
4. Let the first pull-request CI run provide the actual emulated ARM64 build
   evidence.

Rollback is a normal revert of the workflow, script metadata, policy test, and
this OpenSpec change. No published image or external deployment state needs to
be removed.
