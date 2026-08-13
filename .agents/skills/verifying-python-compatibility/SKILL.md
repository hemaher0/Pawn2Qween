---
name: verifying-python-compatibility
description: Use when verifying Python behavior, supported-version compatibility, unittest results, completion readiness, or pre-commit readiness in Pawn2Qween.
---

<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

# Verifying Python Compatibility

## Contract

Select the test scope from repository evidence. Never ask the user to choose.
Run the identical unittest arguments under Python 3.9 and Python 3.11. Both
versions must pass before reporting compatibility.

## Select Scope

Inspect the request, `git status`, diffs, affected implementation and call sites,
existing tests, and the active OpenSpec change.

Use focused modules only when those sources establish a reliable mapping. Use
the full discovery suite for completion or pre-commit verification, cross-area
changes, ambiguous mappings, credible residual regression risk, or when project
instructions require it.

State the selected scope and evidence before execution.

## Run

Focused example:

```bash
.agents/skills/verifying-python-compatibility/scripts/run-python-compatibility.sh \
  tests.test_repository_policy
```

Full suite:

```bash
.agents/skills/verifying-python-compatibility/scripts/run-python-compatibility.sh \
  discover -s tests -p 'test_*.py'
```

If interpreter acquisition or network access is sandbox-blocked, retry through
the normal approval path. Do not weaken `--locked`, remove `--no-dev`, use the
repository `.venv`, or substitute another interpreter.

## Interpret and Report

Classify each version separately as passed, test-failed, or environment-failed.
A failure in one version does not erase the other diagnostic result. Report the
scope reason, unittest target, per-version test and skip counts when emitted,
and relevant failure output. Never claim an unexecuted check passed.

## Common Mistakes

| Mistake | Required response |
|---|---|
| Current Python passes | Run both supported versions. |
| Focused test passes before completion | Escalate to the full suite. |
| uv setup fails | Report environment failure; do not call it a test failure. |
| One version fails | Withhold the compatibility pass. |
