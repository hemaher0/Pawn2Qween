<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## Why

The repository currently splits Python metadata and pinned tool dependencies across legacy setuptools and requirements files, and it has no automated CI or controlled release path. A single uv-native workflow and tag-gated GitHub automation will make development reproducible without turning ordinary pushes into releases.

## What Changes

- Consolidate package metadata and development, training, and data-generation dependencies in `pyproject.toml` plus `uv.lock`.
- Add a Python version declaration and document uv-based setup, testing, training, and data materialization commands.
- Add GitHub Actions CI for pushes and pull requests targeting `main`.
- Add tag-only GitHub Release automation with distinct stable and latest prerelease channels.
- Add `CHANGELOG.md` and validate version-specific notes before publishing a release.
- Remove `setup.cfg` and the three legacy requirements files after their consumers are migrated.
- Keep the runtime package dependency-free and leave the router protocol, scoring behavior, and container runtime unchanged.

## Capabilities

### New Capabilities

- `uv-project-workflow`: Reproducible Python project setup, dependency groups, locking, and local verification through uv.
- `github-release-automation`: Main-branch CI and tag-gated stable/latest GitHub Release publication with changelog validation.

### Modified Capabilities

None.

## Impact

The change affects Python packaging metadata, developer commands, dependency installation guidance, repository policy tests, GitHub Actions workflows, and release documentation. It does not add runtime dependencies, publish to PyPI or a container registry, or modify challenge behavior.
