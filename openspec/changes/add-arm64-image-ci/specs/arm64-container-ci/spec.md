<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## Purpose

Ensure every main-branch change proves that the submitted container can be
built for the official `linux/arm64` platform without publishing an image.

## ADDED Requirements

### Requirement: Main-branch changes validate the ARM64 container image

The repository SHALL run a dedicated container-image job for pushes to `main`
and pull requests targeting `main`. The job SHALL build the submitted image as
the single platform `linux/arm64`, load it into the job-local container engine,
and verify that the resulting image architecture is `arm64`.

#### Scenario: A pull request targets main

- **WHEN** a commit is added to a pull request targeting `main`
- **THEN** continuous integration builds and verifies the `linux/arm64` image

#### Scenario: A commit is pushed to main

- **WHEN** a commit is pushed directly to `main`
- **THEN** continuous integration builds and verifies the `linux/arm64` image

#### Scenario: The image cannot be built or has the wrong architecture

- **WHEN** the ARM64 build fails or inspection does not report `arm64`
- **THEN** the container-image job fails and does not report a successful gate

### Requirement: Cross-platform build support is reproducible

The container-image job MUST configure ARM emulation and an isolated Docker
Buildx builder before starting the image build. Every third-party action used
by the job SHALL be pinned to an immutable commit SHA.

#### Scenario: The hosted runner is not ARM64

- **WHEN** the job runs on the repository's standard Linux hosted runner
- **THEN** the configured emulator and builder allow the ARM64 Dockerfile steps
  to execute without requiring a self-hosted runner

#### Scenario: Workflow action references are reviewed

- **WHEN** repository policy validation inspects the ARM64 job
- **THEN** every checkout, emulation, and builder action reference is an
  immutable commit SHA rather than a mutable tag

### Requirement: ARM64 validation does not publish artifacts

The container-image job SHALL retain the workflow's read-only repository
permission and MUST NOT authenticate to a container registry, push an image,
create a release, or upload the job-local image as a release asset.

#### Scenario: ARM64 validation succeeds

- **WHEN** the job builds and verifies an ARM64 image successfully
- **THEN** the image remains ephemeral to the CI runner and no external
  publication state is changed
