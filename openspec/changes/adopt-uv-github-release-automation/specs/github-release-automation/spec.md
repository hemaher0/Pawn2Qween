<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## Purpose

Provide predictable GitHub validation and release channels in which ordinary development pushes are checked but only explicitly created version tags can publish release artifacts.

## ADDED Requirements

### Requirement: Main-branch changes run continuous integration
The repository SHALL run quality and supported-Python test jobs for pushes to `main` and pull requests targeting `main`. Redundant in-progress runs for the same workflow and ref SHALL be cancellable.

#### Scenario: A pull request targets main
- **WHEN** a commit is added to the pull request
- **THEN** GitHub Actions checks lock consistency, code quality, license compliance, tests, and package construction without publishing a release

#### Scenario: A commit is pushed to main
- **WHEN** the push does not create a supported version tag
- **THEN** continuous integration runs and no GitHub Release is created

### Requirement: Releases are triggered only by supported tags
The release workflow SHALL run only for tags matching the version-tag trigger and SHALL reject tags outside stable `vMAJOR.MINOR.PATCH` and prerelease `vMAJOR.MINOR.PATCH-(alpha|beta|rc).N` formats.

#### Scenario: A branch receives an ordinary push
- **WHEN** no version tag is pushed
- **THEN** the release workflow does not run

#### Scenario: An unsupported version tag reaches the workflow
- **WHEN** the tag does not match either accepted release format
- **THEN** release preparation fails before any GitHub Release is created

### Requirement: Release inputs are validated before publication
The release workflow SHALL require the tagged `pyproject.toml` version to match the tag using PEP 440 prerelease mapping, SHALL require exactly one non-empty version section in `CHANGELOG.md`, and SHALL complete the full quality and supported-Python test gates before publication.

#### Scenario: Release metadata is inconsistent
- **WHEN** the project version or changelog section does not correspond to the pushed tag
- **THEN** the workflow fails without creating or modifying a GitHub Release

### Requirement: Stable and latest channels are distinct
A stable tag SHALL create a non-prerelease GitHub Release marked as GitHub's latest release. An alpha, beta, or release-candidate tag SHALL create a prerelease in the project's `latest` channel without replacing GitHub's latest stable release.

#### Scenario: A stable tag passes validation
- **WHEN** `v1.2.3` is pushed from a matching project version and changelog section
- **THEN** GitHub receives a non-prerelease titled `Stable v1.2.3` and marks it latest

#### Scenario: A release-candidate tag passes validation
- **WHEN** `v2.0.0-rc.4` is pushed from project version `2.0.0rc4` with changelog section `2.0.0-rc.4`
- **THEN** GitHub receives a prerelease titled `Latest v2.0.0-rc.4` and preserves the latest stable designation

### Requirement: Releases contain only approved GitHub assets
Each successful release SHALL attach the wheel and source distribution built from the tagged source and SHALL use the matching changelog section as release notes. The workflow SHALL NOT publish to PyPI or a container registry.

#### Scenario: Publication succeeds
- **WHEN** every validation and build gate passes for a supported tag
- **THEN** the GitHub Release contains the wheel, source distribution, and version-specific notes, with write permission granted only to the publication job
