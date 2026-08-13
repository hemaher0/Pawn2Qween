<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

# Development Workflow

- Use OpenSpec for feature, behavior, or architecture changes.
- Follow the OpenSpec apply/verify workflow when a change has a spec.
- Use installed Superpowers skills for implementation, debugging, TDD, and verification when applicable.
- Do not duplicate detailed workflows here when an existing skill already defines them.

## AI Working Artifacts

- Use the ignored `references/**` workspace for AI-authored working artifacts, including designs, implementation plans, notes, logs, reports, diagnostics, generated files, temporary harnesses, and experiments.
- `docs/` is reserved for published project documentation with durable value to users or maintainers.
- Canonical artifacts owned by another workflow stay in that workflow's configured location; OpenSpec artifacts remain under `openspec/`.
- Do not create or commit `docs/superpowers/`, even when an installed skill names that path as its default. These project instructions override skill defaults.
- Before committing or pushing, verify that AI working artifacts are absent from the public diff and commit history, not merely deleted from the final tree.

## Before Changing Code

- Read the relevant OpenSpec change or spec first when one exists.
- Inspect the existing implementation, call sites, tests, configuration, and relevant documentation before designing a replacement.
- Resolve discoverable facts from repository evidence; ask only about material scope, behavior, compatibility, or safety decisions.
- Prefer the smallest change that satisfies the requirement.
- Do not perform unrelated refactors.
- For behavior-preserving refactors, characterize unclear behavior with tests before restructuring it.
- Do not introduce abstractions for hypothetical future reuse; require a proven repeated pattern.

## Verification

For code changes:

- Run the narrowest relevant tests first.
- Run type checking, linting, and builds when affected.
- Use the `verification-before-completion` workflow before declaring the task complete.
- Never claim a test passed unless it was actually executed.

CI is the final merge gate.

## Tests

Prefer, in order:

1. Unit tests
2. Integration tests
3. Scenario or end-to-end tests when behavior crosses system boundaries

Bug fixes should include a regression test when practical.

## Changes

When externally observable behavior changes:

- Update the relevant OpenSpec artifact.
- Update documentation when necessary.
- Add or update a changelog or changeset when the change should appear in release notes.

Do not create release notes for purely internal changes unless required by the repository release process.

## Public Disclosure Review

- Apply the canonical public-disclosure policy in `CONTRIBUTING.md` to every artifact considered for a public repository or release.
- Before Codex prepares or executes a commit, push, OpenSpec archive, or release, the active local Codex session must review the applicable public candidate and relevant deterministic check results.
- Review the staged diff before a commit.
- Review commits present locally but absent from the target upstream before a push.
- Review the change artifacts, affected implementation delta, synced specs, and retained archive before an OpenSpec archive.
- Review the tagged tree, release notes, and release assets before a release.
- Report exactly one verdict: `PASS`, `BLOCK`, or `NEEDS_CONFIRMATION`. For either non-passing verdict, pause the publication action until the finding is remediated or the missing authority is supplied and re-evaluated.
- Findings must identify scope, location, sanitized reason, and required action, but must not repeat discovered secret values or unnecessarily reproduce prohibited content.
- Perform semantic review in the active local Codex session. Do not add a separate AI API, AI credential, external semantic-review service, or AI-backed GitHub Actions job.
- Direct Git operations performed without Codex are not automatically semantically reviewed; deterministic local and CI checks remain the backstop.

## Git and Repository Safety

Never:

- Commit secrets or credentials.
- Force-push protected branches.
- Modify generated files manually when a generator exists.
- Bypass failing tests to complete a task.
- Silently remove tests.
- Make unrelated dependency upgrades.

Ask before:

- Adding a new production dependency.
- Changing CI/CD workflows.
- Introducing a new external service.
- Performing destructive migrations.

## Agent Behavior

- Prefer existing repository conventions over inventing new ones.
- Prefer existing libraries and tools over custom infrastructure unless the custom implementation is part of the product's core value.
- Keep changes scoped to the requested task.
- Record important architectural or behavioral decisions in OpenSpec rather than leaving them only in chat history.
