<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## Purpose

Define a repository-wide public-disclosure gate that combines deterministic
checks with local Codex semantic review before project material is published.

## ADDED Requirements

### Requirement: Public eligibility is explicit

Every public candidate SHALL be eligible for redistribution, safe to disclose,
and useful for understanding, reviewing, reproducing, operating, or maintaining
the public project. This policy SHALL cover code, documentation, data, CI
configuration, release artifacts, and OpenSpec artifacts. Material with
uncertain authorship, redistribution rights, confidentiality, or disclosure
timing MUST NOT be treated as public until the uncertainty is resolved.

#### Scenario: Project-authored maintainable material is proposed

- **WHEN** a project-authored artifact contains no prohibited information and
  provides durable public-project value
- **THEN** the artifact is eligible for the remaining automated and semantic
  disclosure checks

#### Scenario: Redistribution rights cannot be established

- **WHEN** the source or redistribution rights of an artifact cannot be
  established from available evidence
- **THEN** publication pauses with `NEEDS_CONFIRMATION`

### Requirement: Copyright notices follow confirmed repository provenance

Project copyright notices SHALL distinguish original root-commit material from
subsequent contributions. A path created after the root commit SHALL identify
`hemaher0` as its project copyright holder. A root-commit path modified by a
subsequent contribution SHALL retain the original SK TELECOM CO., LTD. notice
and add `hemaher0`. An unchanged root-commit path SHALL retain its original
notice. Third-party copyright and license notices MUST remain unchanged unless
separate authority establishes a correction. These attribution rules MUST NOT
change the Apache-2.0 license applied to original project material.

#### Scenario: A new path was authored after the root commit

- **WHEN** Git evidence shows that a project path did not exist in the root
  commit and was authored in a subsequent `hemaher0` contribution
- **THEN** its project copyright notice identifies `hemaher0` and does not
  attribute that new work to SK TELECOM CO., LTD.

#### Scenario: Original material received a subsequent contribution

- **WHEN** a path existed in the root commit and its current content includes a
  subsequent `hemaher0` contribution
- **THEN** its project copyright notices retain SK TELECOM CO., LTD. for the
  original material and add `hemaher0` for the subsequent contribution

#### Scenario: An original path remains unchanged

- **WHEN** a root-commit path has no subsequent content change
- **THEN** its original project copyright notice remains unchanged

#### Scenario: A path contains upstream third-party material

- **WHEN** an artifact has an upstream copyright or license notice
- **THEN** the provenance correction preserves that upstream attribution

### Requirement: Prohibited information stays outside the public candidate

A public candidate MUST NOT contain credentials, personal data, internal
locations or infrastructure, non-public URLs, confidential business material,
private evaluation inputs or results, embargoed vulnerability details, raw AI
conversation or reasoning records, or third-party material whose redistribution
rights are not established. A sanitized public statement MAY retain a durable
decision or general risk only when it cannot disclose or reconstruct the
prohibited source information.

#### Scenario: Private evaluation result appears in planning

- **WHEN** a proposal, design, task, report, or specification contains a private
  evaluation measurement
- **THEN** the public candidate is blocked until the measurement is removed or
  moved to an ignored local reference and the public artifact is sanitized

#### Scenario: Secret-like value is detected

- **WHEN** an automated check or Codex review finds a credential or secret-like
  value in the public candidate
- **THEN** the review reports its location without repeating the value and
  returns `BLOCK`

### Requirement: Codex reviews the artifact set that is about to become public

Codex SHALL perform a semantic public-disclosure review before it prepares or
executes a commit, push, OpenSpec archive, or release. Commit review SHALL cover
the staged candidate, push review SHALL cover local commits absent from the
target upstream, archive review SHALL cover the change artifacts and their
implementation delta, and release review SHALL cover the tagged tree, release
notes, and release assets. Codex SHALL consider deterministic policy-check
results as evidence without treating them as a substitute for semantic review.

#### Scenario: Codex prepares a push

- **WHEN** local commits are absent from the target upstream and Codex is asked
  to prepare or execute their push
- **THEN** Codex reviews the complete outgoing commit range before the push

#### Scenario: Direct manual Git operation bypasses Codex

- **WHEN** a Git operation is executed without Codex preparing or executing it
- **THEN** the workflow documents that semantic review was not automatically
  enforced while deterministic repository and CI checks remain available

### Requirement: Review verdicts are bounded and actionable

Codex SHALL report exactly one verdict: `PASS` when no disclosure finding
remains, `BLOCK` for a confirmed violation, or `NEEDS_CONFIRMATION` when required
facts or authority cannot be established. A non-passing result SHALL pause the
requested publication action. Findings SHALL identify the reviewed scope, file
and location when available, a sanitized reason, and the action required to
proceed; findings MUST NOT reproduce discovered secret values or unnecessarily
repeat prohibited content.

#### Scenario: Confirmed disclosure violation remains

- **WHEN** Codex confirms that a public candidate contains prohibited material
- **THEN** Codex returns `BLOCK`, identifies a sanitized remediation, and does
  not prepare or execute the publication action

#### Scenario: User confirmation resolves uncertainty

- **WHEN** Codex returned `NEEDS_CONFIRMATION` and the user supplies sufficient
  authority or source evidence
- **THEN** Codex re-evaluates the affected finding and returns the resulting
  verdict before continuing

### Requirement: Semantic review uses the active local Codex session

The semantic disclosure review SHALL be performed by the Codex session working
on the repository. The project MUST NOT add a separate AI API invocation, AI
credential, external semantic-review service, or AI-backed GitHub Actions job
for this capability. Deterministic checks MAY continue to run locally and in CI.

#### Scenario: CI validates a public candidate

- **WHEN** GitHub Actions runs repository policy tests
- **THEN** it performs deterministic checks without an AI API key or external
  semantic-review call

### Requirement: OpenSpec applies the disclosure boundary throughout a change

OpenSpec guidance SHALL require proposals to identify public-disclosure scope
and exclusions, apply and verify work to preserve and check that boundary, and
archive work to confirm that the final specifications and retained history are
public-safe. Non-public working evidence MAY remain under an ignored local
reference area, but public OpenSpec artifacts MUST remain understandable without
publishing or linking to inaccessible confidential details.

#### Scenario: Change uses private working evidence

- **WHEN** private working evidence informs a public-safe decision
- **THEN** the evidence remains in an ignored local reference and the OpenSpec
  artifact records only the independently publishable decision and rationale

#### Scenario: Completed change is archived

- **WHEN** Codex prepares to archive a completed OpenSpec change
- **THEN** it reviews the change artifacts, implementation delta, synced specs,
  and retained archive content before completing the archive
