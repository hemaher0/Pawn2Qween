<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## 1. Disclosure Contract Tests

- [x] 1.1 Add failing tests in `tests/test_repository_policy.py` that require `CONTRIBUTING.md` to define redistribution authority, safe disclosure, durable public-project value, prohibited categories, sanitization, and the default-block rule for uncertainty.
- [x] 1.2 Add failing tests that require `AGENTS.md` to direct Codex to review staged commits, outgoing push ranges, OpenSpec archives, and releases; report only `PASS`, `BLOCK`, or `NEEDS_CONFIRMATION`; pause non-passing publication; and avoid repeating discovered secret values.
- [x] 1.3 Add failing tests that require `/references` to remain ignored, require OpenSpec proposal/task/apply/archive guidance including completion verification, and confirm CI workflows add no AI API key or semantic-review invocation.
- [x] 1.4 Run `uv run --locked python -m unittest tests.test_repository_policy` and confirm the new contract tests fail for the missing policy and workflow text.

## 2. Canonical Policy and Codex Workflow

- [x] 2.1 Expand `CONTRIBUTING.md` with the canonical repository-wide public eligibility rule, prohibited-content list, sanitized-decision boundary, uncertainty rule, and local ignored-reference handling.
- [x] 2.2 Add a concise `Public disclosure review` section to `AGENTS.md` that references `CONTRIBUTING.md`, defines the four candidate scopes and three verdicts, pauses non-passing publication actions, and assigns semantic review to the active Codex session without a separate AI API.
- [x] 2.3 Update `openspec/config.yaml` so proposals record disclosure scope and exclusions, tasks include the final disclosure gate, apply guidance preserves and verifies the public boundary, and archive reviews synced specs plus retained history.
- [x] 2.4 Add a concise `[Unreleased]` changelog entry for the repository-wide public-disclosure workflow.
- [x] 2.5 Re-run `uv run --locked python -m unittest tests.test_repository_policy` and confirm the disclosure contract and existing public-tree checks pass.

## 3. OpenSpec and Repository Verification

- [x] 3.1 Run `openspec validate add-public-disclosure-review --strict` and resolve every structural or scenario error without weakening the disclosure requirements.
- [x] 3.2 Run `uv lock --check`, `uv run --locked ruff check .`, and `uv run --locked reuse lint` to verify lock consistency, code quality, and SPDX coverage.
- [x] 3.3 Run the supported Python 3.9 and 3.11 unittest suites with locked default-only environments and record the exact test and skip counts.
- [x] 3.4 Review the complete outgoing commit range using the new Codex contract, return a sanitized `PASS`, `BLOCK`, or `NEEDS_CONFIRMATION` verdict, and do not prepare integration or publication unless the verdict is `PASS`.

## 4. Copyright Provenance Correction

- [x] 4.1 Add failing repository policy assertions for a root-only SK TELECOM CO., LTD. file, a post-root `hemaher0` file, a modified mixed-attribution file, the combined `NOTICE`, and removal of SK Telecom employee-only contribution instructions.
- [x] 4.2 Run the focused repository policy tests and confirm the new provenance assertions fail against the incorrect current notices.
- [x] 4.3 Classify exact paths against root commit `3cccbf602077a846c13b2cb1356eee1559a631db` with rename detection disabled, then correct tracked SPDX notices and new local OpenSpec notices without changing third-party attribution.
- [x] 4.4 Update `NOTICE`, split `REUSE.toml` annotations by provenance, and replace inapplicable SK Telecom employee contribution instructions with repository-neutral DCO guidance.
- [x] 4.5 Re-run the focused policy tests, strict OpenSpec validation, `uv lock --check`, Ruff, and REUSE lint.
- [x] 4.6 Run the full locked default-only unittest suite on Python 3.9 and Python 3.11 in the actual ownership environment.
- [x] 4.7 Review the complete correction candidate under the disclosure contract, preserve independent unstaged work, and create one linear signed-off correction commit only after a `PASS` verdict.
