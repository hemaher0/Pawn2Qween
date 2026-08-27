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

- A pinned multilingual E5 ONNX encoder, deterministic aggregate rank-two
  compatibility head, reproducible Train-only artifacts, and an offline model
  fetch workflow.
- GitHub Actions quality and supported-Python test gates for changes to `main`.
- Tag-only GitHub Release automation with separate stable and latest prerelease
  channels.
- Release validation for project versions and version-specific changelog notes.
- Repository-wide public-disclosure policy and local Codex review gates for
  commits, pushes, and releases.

### Changed

- Isolated the packaged E5 submission runtime under `ossp_router`, split
  feature encoding, artifact fitting, and evaluation into offline-only stages,
  and added distinct locked dependency and CI boundaries for each path.
- Moved the maintained hash router and training implementation from
  `baselines` into `src/ossp_router`, added the common `router-train` CLI, and
  retained `baselines` only for small comparison examples.
- Switched the packaged `router-run` and submission container entry point to
  the E5-binomial router, with pinned ARM64 runtime dependencies, model
  packaging, image-size checks, and constrained preflight execution.
- Routing quality can now compose the independent binomial hash-regex signal
  with E5 prompt/model compatibility using a fixed equal-logit blend; existing
  cost prediction and budget-aware allocation remain unchanged.
- Consolidated Python packaging and task dependencies into `pyproject.toml` and
  a committed uv lock file.
- Corrected project copyright notices to preserve the original attribution and
  identify `hemaher0` contributions made after the root commit.
