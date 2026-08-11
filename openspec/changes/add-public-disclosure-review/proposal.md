<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## Why

The repository has deterministic checks for several secret and path patterns,
but it does not define one reusable public-disclosure decision or require a
semantic review of the content Codex is about to publish. A local Codex review
plus existing automated checks will keep public changes useful and lawful
without adding an AI API, credential, or external review service.

## What Changes

- Define one repository-wide public-disclosure policy for code, documentation,
  data, CI configuration, release artifacts, and OpenSpec artifacts.
- Require Codex to review the relevant public candidate before commit, push,
  OpenSpec archive, and release, reporting `PASS`, `BLOCK`, or
  `NEEDS_CONFIRMATION` with file-based findings that do not repeat discovered
  secret values.
- Treat ambiguous authorship, redistribution rights, confidentiality, or
  disclosure timing as `NEEDS_CONFIRMATION`; block confirmed disclosure
  violations until the public candidate is sanitized.
- Correct project copyright notices against Git provenance: retain the original
  root-commit holder for original material, identify `hemaher0` for subsequent
  additions and modifications, and preserve upstream third-party attribution.
- Add OpenSpec proposal, apply, verify, and archive guidance so public scope is
  considered throughout a change rather than only immediately before release.
- Extend repository policy tests for deterministic public-boundary rules while
  leaving contextual legal, privacy, evaluation, and business judgments to the
  local Codex review.

## Capabilities

### New Capabilities

- `public-disclosure-review`: Defines public eligibility, prohibited content,
  review scopes and verdicts, blocking behavior, and the boundary between
  deterministic checks and Codex semantic review.

### Modified Capabilities

None.

## Impact

The change affects `CONTRIBUTING.md`, `AGENTS.md`, `NOTICE`, `REUSE.toml`,
project SPDX notices, `openspec/config.yaml`, and repository policy tests. It
does not change the Apache-2.0 licensing of project material or the licenses
and attribution of third-party material. It adds no production dependency,
external service, AI API invocation, GitHub Action, runtime behavior, scoring
behavior, or release trigger. Codex can enforce the semantic gate only while
it is driving or preparing the relevant Git operation; direct manual Git
commands remain outside the agent workflow.
