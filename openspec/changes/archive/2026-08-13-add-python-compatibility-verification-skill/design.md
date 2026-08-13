<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## Context

See `proposal.md` for motivation. The repository supports Python 3.9 and newer while development tooling normally runs on Python 3.11. Existing checks can be invoked ad hoc, and the repository `.venv` is not a trustworthy compatibility boundary. The workflow must remain repository-local, preserve the committed uv lock, avoid production and project-test edits, and comply with the public-disclosure policy in `CONTRIBUTING.md`.

## Goals / Non-Goals

**Goals:**

- Separate agent judgment about test scope from deterministic two-version execution.
- Make partial, failed, or unexecuted evidence impossible to report as a compatibility pass when the workflow is followed.
- Preserve useful per-version diagnostics even when one run fails.
- Keep evaluation traces outside the public candidate while retaining reproducible acceptance criteria.

**Non-Goals:**

- Generalize the runner to arbitrary projects, test frameworks, or Python versions.
- Replace existing lint, licensing, OpenSpec, build, container, CI, or release gates.
- Install a production dependency or modify the runtime, project tests, lock file, or repository `.venv`.
- Publish commits, images, releases, or raw agent evaluation material.

## Decisions

### Split scope selection from execution

`SKILL.md` owns evidence gathering, focused-versus-full selection, escalation, and reporting. A Bash runner accepts only the already selected unittest arguments and executes them unchanged for both versions. This keeps contextual judgment visible while making environment setup and result aggregation deterministic.

An all-Bash solution was rejected because reliable scope selection depends on semantic repository evidence. A prose-only skill was rejected because repeated shell construction would invite interpreter, environment, and argument drift.

### Use one fixed repository-local runner

The runner is intentionally specific to Pawn2Qween. It resolves the repository root from its own path, verifies `pyproject.toml` and `uv.lock`, and checks that the actual interpreter matches each requested version. The fixed contract is smaller and easier to audit than a configurable multi-project abstraction.

A generic runner with flags for versions, environment roots, and test frameworks was rejected because there is no demonstrated second consumer and additional configuration would weaken invariants.

### Isolate uv state under temporary roots

Both runs share task-specific uv cache and interpreter-install roots under `/tmp`, but use separate project environments for Python 3.9 and Python 3.11. Each environment is synchronized from the committed lock with default-only dependencies before executing with synchronization disabled. This avoids repository `.venv` mutation while retaining repeatability and cache reuse.

Reusing one virtual environment was rejected because it can silently preserve the wrong interpreter or dependencies. Using the repository `.venv` was rejected because it is shared mutable state.

### Continue after individual failures and aggregate statuses

The runner attempts Python 3.9 first and Python 3.11 second. It records test failures separately from environment failures, continues to the second run, and exits with environment failure taking precedence over test failure. This exposes the minimum supported version early without sacrificing the other diagnostic result.

Fail-fast execution was rejected because it hides whether the failure is version-specific. Treating all nonzero outcomes alike was rejected because a test assertion and an unavailable interpreter require different follow-up actions.

### Validate behavior with skill TDD

Fresh-context control scenarios first identify concrete failure modes without the new skill. Skill-enabled repeats must then demonstrate correct scope selection, two-version execution, and honest reporting. The deterministic runner additionally receives a known passing target, an intentional missing target, and full-suite coverage.

Persisting raw traces in the public tree was rejected because they lack durable maintenance value and can cross the public-disclosure boundary.

## Risks / Trade-offs

- [Temporary uv state can be stale or incomplete] → Synchronize each version from the committed lock and verify the active interpreter before tests.
- [Network or interpreter acquisition can be sandbox-blocked] → Classify setup separately and retry through the normal approval path without weakening constraints.
- [Agent-selected focused scope can miss regressions] → Require full discovery for completion, pre-commit, broad, ambiguous, or residual-risk cases.
- [Running both versions costs more time] → Reuse cache and interpreter roots while preserving separate project environments; compatibility claims still require both runs.
- [A signal can terminate the runner before aggregation] → Accept interruption semantics; ordinary setup and test failures remain independently collected.

## Migration Plan

1. Add and validate the OpenSpec change.
2. Establish fresh-agent control failures without adding public trace files.
3. Generate the repository-local skill, implement the runner, and validate metadata and shell syntax.
4. Exercise focused success, intentional test failure, skill-enabled scenarios, and full two-version verification.
5. Commit the reviewed OpenSpec and skill artifacts locally without pushing.

Rollback consists of reverting the local skill commit and OpenSpec commit. No runtime data, external system, or repository environment migration is required.
