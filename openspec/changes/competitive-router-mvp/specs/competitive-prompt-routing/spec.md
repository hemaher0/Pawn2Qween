<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## Purpose

Provide a reproducible, prompt-only routing capability that selects competitive
models within conservative tier budgets while preserving the official runtime
and submission contracts.

## ADDED Requirements

### Requirement: Candidate evaluation is reproducible and comparable

The system SHALL evaluate every router candidate and the safe baseline with the
same fixed repeated-validation assignments, official scoring policy, and
recorded source-data hashes. Candidate evidence SHALL contain aggregate and
per-fold score and cost results without prompt text or episode IDs. Public
evidence SHALL be derived only from the approved public Train and Dev data and
SHALL NOT include private evaluation results.

#### Scenario: Repeating an evaluation

- **WHEN** the same materialized inputs, outcomes, policy, candidate
  configuration, and fixed seed are evaluated twice
- **THEN** the system produces byte-identical fold assignments and equivalent
  candidate ranking values

#### Scenario: Comparing candidates

- **WHEN** multiple candidates are evaluated in one experiment run
- **THEN** every candidate is scored against the same folds, safety caps, and
  safe-baseline result

#### Scenario: Publishing candidate evidence

- **WHEN** candidate evidence is prepared for a public report or repository
- **THEN** it contains only approved public Train and Dev measurements and
  excludes private evaluation results and non-public inputs

### Requirement: Unsafe candidates are rejected before ranking

The system MUST reject a candidate if any validation result exceeds Fast
`1.15`, Balanced `1.84`, or Premium `3.68` actual cost ratio. Among safe
candidates, ranking SHALL prefer weighted score, then lower maximum cost ratio,
then smaller artifact size, and then shorter runtime.

#### Scenario: One tier exceeds its safe cap

- **WHEN** a candidate exceeds the applicable safe cap in any validation fold
- **THEN** the system marks the candidate unsafe and excludes it from
  score-based winner selection

#### Scenario: Safe candidates have equal score

- **WHEN** two safe candidates have the same weighted validation score
- **THEN** the system selects the candidate with the lower maximum tier cost
  ratio before considering artifact size or runtime

### Requirement: Performance MVP uses an explicit improvement gate

The system SHALL report the performance MVP as passed only when a safe candidate
improves the mean repeated-validation weighted score by at least `0.005`
absolute over the safe baseline. If no candidate passes after the bounded
follow-up experiments, the system SHALL select the highest-ranked safe
candidate and report that the improvement gate was not met.

#### Scenario: Candidate meets the improvement threshold

- **WHEN** the highest-ranked safe candidate improves the safe baseline by
  `0.005` or more
- **THEN** the evaluation report marks the performance MVP as passed

#### Scenario: No candidate meets the improvement threshold

- **WHEN** all primary and bounded follow-up candidates improve by less than
  `0.005`
- **THEN** the report identifies the highest-ranked safe fallback and does not
  claim that the performance MVP passed

### Requirement: Runtime routing uses only allowed content

The runtime SHALL derive every model choice only from prompt or message content,
the requested tier, the bundled public policy, and a bundled learned artifact.
It MUST NOT use challenge ID, split, episode ID, input position, data-source
metadata, outcomes, network services, or candidate model outputs to choose a
model.

#### Scenario: IDs and order change

- **WHEN** the same content and tier are supplied with different opaque IDs and
  in a different order
- **THEN** the model selected for each content value remains unchanged

#### Scenario: Runtime is isolated

- **WHEN** the router runs without network access and with a read-only root file
  system
- **THEN** it produces a complete submission using only bundled files and the
  allowed output location

### Requirement: Official runtime interface remains compatible

The `router-run` command SHALL keep the required `--input`, `--tier`, and
`--output` arguments, write one atomic v1 submission with mode `0644`, return
`0` on success, and return `2` with a bounded error message for input, policy,
artifact, or output failures.

#### Scenario: Successful tier execution

- **WHEN** a valid prompt-only input and tier are supplied
- **THEN** the command writes exactly one valid submission containing one
  decision for every input episode and exits with code `0`

#### Scenario: Bundled artifact is incompatible

- **WHEN** the artifact feature version, model set, or policy digest is
  incompatible with the runtime
- **THEN** the command exits with code `2` without silently falling back to a
  different routing strategy

### Requirement: Learned artifacts are strict and reproducible

The trainer SHALL generate byte-identical artifacts for identical data,
configuration, policy, and seed. The runtime MUST reject unknown fields,
invalid dimensions, invalid tree indexes, non-finite numeric values, unsupported
feature versions, and policy digest mismatches.

#### Scenario: Training is repeated

- **WHEN** the selected trainer runs twice with identical inputs and
  configuration
- **THEN** both artifact files have identical bytes and SHA-256 digests

#### Scenario: Artifact contains undeclared data

- **WHEN** an artifact contains an unknown field or an invalid numeric or
  structural value
- **THEN** strict parsing fails before any routing decision is produced

### Requirement: Submitted runtime has no third-party dependency

The packaged router and container SHALL execute using only the Python standard
library. Training-only packages MUST NOT be installed in or copied into the
submitted image.

#### Scenario: Container package inventory is inspected

- **WHEN** the release image is built from the final code commit
- **THEN** its runtime files contain the selected JSON artifact and standard
  project code but no NumPy or nonlinear-training package
