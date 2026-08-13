<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## 1. Establish Skill-TDD Baseline

- [x] 1.1 Run a fresh-agent focused verification scenario without the new skill and retain the raw trace only in session or ignored temporary storage.
- [x] 1.2 Run a fresh-agent broad completion scenario without the new skill and retain the raw trace only in session or ignored temporary storage.
- [x] 1.3 Record sanitized failure categories and confirm that at least one control demonstrates a workflow gap before implementation.

## 2. Implement the Repository-Local Skill

- [x] 2.1 Initialize `.agents/skills/verifying-python-compatibility/` with the official Skill Creator generator, including scripts and UI metadata.
- [x] 2.2 Replace the generated instructions with the evidence-based focused-versus-full selection, two-version execution, escalation, and reporting contract.
- [x] 2.3 Implement the deterministic Bash runner with locked default-only uv setup, separate Python 3.9 and 3.11 temporary environments, interpreter checks, independent runs, and aggregated failure status.
- [x] 2.4 Make the runner executable and confirm UI metadata permits implicit invocation and references `$verifying-python-compatibility` in the default prompt.

## 3. Verify Structure and Runner Behavior

- [x] 3.1 Validate Bash syntax and the complete skill directory with the Skill Creator validator.
- [x] 3.2 Run `tests.test_repository_policy` through the runner and confirm Python 3.9 and Python 3.11 both pass the identical focused target.
- [x] 3.3 Run an intentional missing unittest target and confirm both versions execute, both are classified as test failures, and the runner exits with test-failure status.
- [x] 3.4 Confirm execution leaves `uv.lock`, the repository `.venv`, production code, and project test code unchanged.

## 4. Validate Agent Workflow

- [x] 4.1 Repeat the focused fresh-agent scenario with the new skill and confirm evidence-based focused selection, identical two-version execution, and honest reporting.
- [x] 4.2 Repeat the broad completion scenario with the new skill and confirm full discovery selection, identical two-version execution, and separate environment/test failure handling.
- [x] 4.3 Refine only observed workflow gaps, rerun affected checks, and confirm `SKILL.md` remains concise and contains no placeholders.

## 5. Complete Repository Verification

- [x] 5.1 Run the complete unittest discovery suite through the runner and record Python 3.9 and Python 3.11 test and skip counts exactly as emitted.
- [x] 5.2 Run lock validation, Ruff, REUSE, strict OpenSpec validation, and Git whitespace checks.
- [x] 5.3 Verify the final diff contains only the planned OpenSpec and skill artifacts and no raw agent traces or unintended repository changes.
- [x] 5.4 Review the complete public candidate and deterministic evidence against `CONTRIBUTING.md`, record exactly one `PASS`, `BLOCK`, or `NEEDS_CONFIRMATION` verdict, and stop before integration if the verdict is not `PASS`.
- [x] 5.5 On `PASS`, review the staged diff and create a signed-off local commit without pushing or publishing artifacts.
