<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

# Python Compatibility Verification Specification

## Purpose

Provide a repeatable repository workflow that selects an evidence-based unittest scope and verifies it honestly across every supported Python version without mutating project state.

## Requirements

### Requirement: Autonomous evidence-based scope selection
The verification workflow SHALL select focused or full unittest scope from the request, repository changes, affected implementation and call sites, existing tests, project instructions, and the active OpenSpec change. It SHALL state the selected scope and supporting evidence without asking the user to choose a verification tier.

#### Scenario: Reliable focused mapping
- **WHEN** repository evidence maps a localized change reliably to one or more unittest modules and the request is not a completion or pre-commit gate
- **THEN** the workflow selects those focused modules and explains the mapping

#### Scenario: Full verification required
- **WHEN** the request is for completion or pre-commit readiness, the change crosses behavioral areas, the focused mapping is ambiguous, credible regression risk remains, or project instructions require full verification
- **THEN** the workflow selects the complete unittest discovery suite

### Requirement: Identical supported-version execution
The verification workflow MUST run the identical selected unittest arguments under Python 3.9 and Python 3.11 and MUST attempt each supported-version run independently.

#### Scenario: Same target on both versions
- **WHEN** the workflow executes a selected unittest target
- **THEN** it passes the same unittest arguments unchanged to Python 3.9 and Python 3.11

#### Scenario: First version fails
- **WHEN** the Python 3.9 test run fails
- **THEN** the workflow still attempts the Python 3.11 diagnostic run and retains both outcomes

### Requirement: Isolated reproducible environments
The verification workflow SHALL use the committed lock, default-only dependencies, `PYTHONPATH=src`, and distinct temporary project environments for Python 3.9 and Python 3.11. It MUST verify the selected interpreter and MUST NOT mutate the repository `.venv`, weaken the lock, substitute a different interpreter, or change production or project test code.

#### Scenario: Supported-version environments are prepared
- **WHEN** verification begins with uv and the requested interpreters available
- **THEN** each supported version runs in its own locked default-only temporary environment with the expected interpreter

#### Scenario: Verification leaves repository inputs unchanged
- **WHEN** verification completes or fails
- **THEN** the repository `.venv`, lock file, production code, and project test code remain unchanged by the workflow

### Requirement: Failure classification and compatibility verdict
The verification workflow SHALL classify each supported version separately as passed, test-failed, or environment-failed. It MUST withhold a positive compatibility verdict unless both supported versions execute and pass.

#### Scenario: Environment preparation fails
- **WHEN** interpreter acquisition, uv, filesystem, network setup, or interpreter verification prevents a version's tests from running
- **THEN** the workflow reports that version as environment-failed rather than test-failed and does not claim compatibility

#### Scenario: A test fails on one version
- **WHEN** one supported version reports a unittest failure and the other version passes
- **THEN** the workflow reports the per-version outcomes and does not claim compatibility

#### Scenario: Both versions pass
- **WHEN** the identical selected target executes successfully under Python 3.9 and Python 3.11
- **THEN** the workflow reports a positive compatibility verdict with the scope reason, target, per-version outcomes, and observed test and skip counts when emitted

### Requirement: Public evaluation boundary
The verification workflow SHALL keep raw agent evaluation prompts, traces, and private inputs outside the public repository while preserving sanitized, durable requirements and conclusions in public artifacts.

#### Scenario: Fresh-agent evaluation is performed
- **WHEN** control or skill-enabled agent scenarios are used to validate the workflow
- **THEN** raw traces remain in session or ignored temporary storage and are not included in a public commit
