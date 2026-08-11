<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## Purpose

Provide one reproducible Python project workflow for installation, testing, packaging, training, and public-data tooling while keeping the distributed router runtime dependency-free.

## ADDED Requirements

### Requirement: Python project metadata has one source of truth
The repository SHALL declare its package metadata, supported Python range, command-line entry points, package data, and dependency groups in `pyproject.toml`, and SHALL commit a lock file generated from that declaration.

#### Scenario: A contributor checks out the repository
- **WHEN** a contributor synchronizes the project from the committed lock file
- **THEN** uv installs versions consistent with `pyproject.toml` and `uv.lock` without reading legacy setuptools metadata or requirements files

### Requirement: Runtime compatibility remains independent of tool dependencies
The distributed router package SHALL support Python 3.9 or newer and SHALL have no mandatory third-party runtime dependency. Development tooling SHALL use Python 3.11 or newer.

#### Scenario: The package is installed without optional groups
- **WHEN** a user installs or synchronizes only the default project dependencies on a supported Python version
- **THEN** the router package installs without NumPy, PyArrow, REUSE, Ruff, or DeepMind reproduction dependencies

### Requirement: Specialized dependency sets are selectable
The project SHALL expose separate dependency groups for development checks, baseline training, public-data materialization, and DeepMind Mathematics reproduction. Mutually incompatible NumPy dependency sets SHALL not be selected together.

#### Scenario: A contributor performs one specialized task
- **WHEN** the contributor selects the group documented for that task
- **THEN** uv installs the pinned task dependencies without requiring unrelated specialized groups

#### Scenario: Conflicting training groups are selected
- **WHEN** the baseline training and DeepMind reproduction groups are selected together
- **THEN** dependency resolution fails with a declared group conflict instead of choosing an unintended NumPy version

### Requirement: Project verification is lock-reproducible
The documented local workflow and continuous integration SHALL verify lock consistency, linting, license compliance, unit tests, and package builds through uv using committed dependency state.

#### Scenario: Project metadata changes without refreshing the lock
- **WHEN** continuous integration checks a commit whose lock file no longer matches project metadata
- **THEN** the quality job fails before the project is released
