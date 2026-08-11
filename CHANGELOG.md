<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- GitHub Actions quality and supported-Python test gates for changes to `main`.
- Tag-only GitHub Release automation with separate stable and latest prerelease
  channels.
- Release validation for project versions and version-specific changelog notes.

### Changed

- Consolidated Python packaging and task dependencies into `pyproject.toml` and
  a committed uv lock file.
- Corrected project copyright notices to preserve the original attribution and
  identify `hemaher0` contributions made after the root commit.
