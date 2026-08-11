<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## 1. Release Contract

- [x] 1.1 Add unit tests for stable and prerelease tag parsing, version matching, changelog extraction, and invalid release inputs
- [x] 1.2 Implement the standard-library release preparation tool and add a Keep a Changelog-style `CHANGELOG.md`

## 2. uv Project Migration

- [x] 2.1 Consolidate package metadata, scripts, package data, and empty runtime dependencies into PEP 621 `pyproject.toml`
- [x] 2.2 Define `dev`, `train`, `materialize`, and `deepmind` groups with Python constraints and the train/deepmind conflict
- [x] 2.3 Add `.python-version`, generate `uv.lock` with uv 0.12.3, and verify lock consistency
- [x] 2.4 Migrate the installed-wheel test to uv and remove `setup.cfg` plus the three legacy requirements files

## 3. Documentation and Repository Policy

- [x] 3.1 Update setup, testing, training, and data-generation documentation and dependency error messages to use uv groups
- [x] 3.2 Document stable/latest release preparation, tag formats, changelog promotion, and tag-only publication
- [x] 3.3 Update package manifests, REUSE annotations, SPDX coverage, repository file policy, and OpenSpec project context for the new source of truth

## 4. GitHub Automation

- [x] 4.1 Add SHA-pinned main push and pull-request CI with lock, lint, license, build, and Python 3.9/3.11 test gates
- [x] 4.2 Add SHA-pinned tag-only release validation and publication jobs with read-only defaults and job-scoped write permission
- [x] 4.3 Add repository policy tests that enforce CI/release trigger, permission, channel, and legacy-file boundaries

## 5. Verification

- [x] 5.1 Run focused release, packaging, and repository policy tests
- [x] 5.2 Run uv lock checks, Ruff, REUSE, supported-Python tests, and wheel/source builds, documenting any environment-only baseline limitation
- [x] 5.3 Validate the OpenSpec change strictly and review the final diff for scope and accidental release triggers
