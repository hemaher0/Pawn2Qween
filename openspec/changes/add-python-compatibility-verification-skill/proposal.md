<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## Why

Python compatibility checks currently depend on ad hoc interpreter and test-scope choices, which can miss the minimum supported version or overstate partial evidence. A repository-local workflow is needed now to make Python 3.9 and 3.11 verification repeatable, isolated, and honest before completion or commit claims.

## What Changes

- Add a repository-local Codex skill that selects focused or full unittest scope from repository evidence without asking the user to choose a tier.
- Add a deterministic Bash runner that executes identical unittest arguments under Python 3.9 and Python 3.11 with locked, default-only uv environments under `/tmp`.
- Define separate environment-failure and test-failure outcomes and require both supported versions to pass before reporting compatibility.
- Add skill metadata that permits implicit invocation for compatibility, unittest, completion-readiness, and pre-commit requests.
- Verify the workflow with fresh-agent scenarios, a known passing focused suite, an intentional missing test target, and the full suite.
- Keep raw agent evaluation traces non-public.

Non-goals include changing runtime, scoring, schemas, container behavior, release automation, production dependencies, existing production code, or project test code. The skill does not replace Ruff, REUSE, OpenSpec, build, container, or release gates and does not publish artifacts.

## Capabilities

### New Capabilities

- `python-compatibility-verification`: Defines evidence-based unittest scope selection, identical Python 3.9 and 3.11 execution, isolated locked environments, failure classification, and compatibility reporting.

### Modified Capabilities

None.

## Impact

The public candidate is limited to the new OpenSpec change and `.agents/skills/verifying-python-compatibility/` skill, runner, and UI metadata. It introduces no runtime API, dependency, lock-file, CI, dataset, or release changes. Raw agent traces, private evaluation inputs, environment-specific diagnostics, and any sensitive or non-redistributable material are excluded from the public tree.
