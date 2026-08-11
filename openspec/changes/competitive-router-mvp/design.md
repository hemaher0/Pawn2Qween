<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## Context

See `proposal.md` for motivation and
`specs/competitive-prompt-routing/spec.md` for the observable contract. The
current package exposes a standard-library prompt heuristic as `router-run`
and includes a stronger offline NumPy ridge baseline. The public data contains
1,760 Train and 880 Dev episodes after deterministic materialization. Runtime
evaluation is offline on `linux/arm64` with 2 CPUs, 2 GiB memory, and 90 seconds
per tier.

The current hash-regex artifact was calibrated against public Dev and consumed
almost the full public budget. Using its public score as the optimization
target without a new validation boundary would leave insufficient headroom for
normal variation across evaluation datasets.

## Goals / Non-Goals

**Goals:**

- Separate candidate discovery from Dev confirmation and final combined-data
  training.
- Make score and budget evidence reproducible and directly comparable.
- Preserve the public runtime contract while replacing the weak bundled
  decision policy.
- Keep learned runtime evaluation deterministic, strict, bounded, and free of
  third-party dependencies.
- Produce enough evidence to justify the selected design in a technical report.

**Non-Goals:**

- Optimize against private data or infer private source composition.
- Add online inference, a neural runtime, an interactive UI, or a new schema.
- Automate publication, registry credentials, contest upload, or Asana.
- Replace or redesign the existing uv package, CI, or tag-gated release
  automation.

## Decisions

### Use a fixed candidate funnel instead of selecting an algorithm upfront

Three candidates share one evaluation harness: a conservatively recalibrated
hash-regex baseline, a sparse word/character uplift model, and a shallow tree
model exported to bounded JSON. Each primary candidate receives one experiment.
Only the two highest-ranked safe candidates may receive one follow-up experiment
when the `0.005` gate is missed.

This keeps preparation evidence-driven without allowing unlimited search. A
single preselected algorithm was rejected because the user intentionally chose
to make the technical selection during Sprint 0. An unrestricted model search
was rejected because the dataset is small and the deadline is fixed.

### Hold Dev back until candidate selection

Train uses deterministic five-fold validation repeated three times with seed
`20260811`. All candidates and the safe baseline receive identical folds.
Candidate selection uses only those repeated Train results. Dev is evaluated
once after selection as a confirmation, and the final artifact may then be fit
on combined Train and Dev.

This makes the comparison less biased than the existing Dev-calibrated
baseline. Training on all public data from the beginning was rejected because
it would leave no independent confirmation set.

### Apply safety rejection before score ranking

Actual official scorer reports are compared with literal Decimal caps Fast
`1.15`, Balanced `1.84`, and Premium `3.68`. A candidate that exceeds any cap
in any fold is excluded. Safe candidates are ordered by weighted score, maximum
cost ratio, serialized artifact size, and measured runtime.

The caps are 92% of official tier budgets and allow for possible distribution
shift. Maximizing score directly up to the official cap was rejected because a
small shift can zero an entire tier.

### Predict model uplift and relative cost in the sparse candidate

The sparse candidate uses existing structural features, signed word
unigram/bigram hashing, and a separately normalized signed character 3/4/5-gram
block. Character work is bounded to 65,536 code points. Targets are score delta
and log-cost ratio against `ax31-light`; the light values are reconstructed as
zero deltas at runtime.

Relative targets remove shared prompt difficulty and length components. A much
larger embedding or tokenizer dependency was rejected because it increases
license, image, and ARM runtime risk without enough public data to justify it.

### Bound and strictly validate the nonlinear candidate

The nonlinear experiment uses training-only shallow ensembles with maximum
depth 3 and at most 48 estimators per target. The exported format contains only
finite scalar metadata and node arrays. The runtime validates feature indexes,
child indexes, acyclicity/depth, leaf finiteness, model coverage, and declared
field sets before evaluation.

Keeping a training library in the container was rejected. If the tree candidate
does not beat the sparse model after serialization and runtime measurement, it
is discarded rather than retained as unused complexity.

### Bundle one strict artifact and fail closed

The selected trainer writes sorted, indented JSON atomically and records the
policy digest, input/outcome digests, feature version, seed, and configuration.
The package bundles exactly one selected artifact. The runtime checks the
artifact before producing decisions and returns the existing error path when it
is incompatible.

Silent fallback to the weak heuristic was rejected because reported validation
would then differ from submitted behavior. The old heuristic remains available
as baseline code but is no longer the default `router-run` strategy.

### Extend the existing uv CI without adding another workflow

The existing CI workflow already checks the lock file, runs Ruff and REUSE,
builds distributions, and executes the default-only unittest suite on Python
3.9 and 3.11. New standard-library runtime tests are discovered by those jobs
without workflow changes. If training-tool tests require the existing `train`
dependency group, extend the current CI workflow narrowly for those tests
instead of creating a duplicate quality workflow. Keep Docker builds,
publication, and release behavior outside this change; the existing release
workflow remains tag-gated.

## Risks / Trade-offs

- **Small public dataset encourages feature and hyperparameter overfitting** →
  fix folds and seeds, limit primary and follow-up experiments, and hold Dev
  back until selection.
- **A safe public cost estimate can shift across evaluation datasets** → reject
  at 92% of the cap, report worst-fold cost, and add stratified resampling
  stress before release.
- **Character features can dominate long-context runtime** → cap sampled code
  points and benchmark all 2,640 public episodes under container limits.
- **Tree serialization can add parser and runtime risk** → enforce strict size,
  depth, and node limits; select it only when measured evidence wins.
- **Full public materialization depends on external pinned sources** → verify
  upstream hashes and stop experiments rather than silently use partial base
  inputs.
- **Docker and GHCR are unavailable until the host is configured** → treat
  Docker/WSL integration as an environment prerequisite and keep publication
  behind explicit approval.
- **Training-only checks can expand CI time and dependency scope** → use the
  existing dependency group only where default-only jobs cannot cover the
  tests, keep runtime jobs `--no-dev`, and leave release automation unchanged.

## Migration Plan

1. Add the evaluation harness and reproduce a safe baseline without changing
   `router-run`.
2. Evaluate and hard-select one candidate using the spec gates.
3. Generate the selected artifact twice and require byte identity.
4. Add the strict runtime and tests, then switch the existing command to it.
5. Run full-data, audit, and ARM64 checks before documenting evidence.
6. Roll back by reverting the integration commit, which restores the existing
   heuristic entry point and removes the bundled competitive artifact.

Public Git, GHCR, and technical-submission metadata are handled only after a
separate user approval and are not part of applying this OpenSpec change.
