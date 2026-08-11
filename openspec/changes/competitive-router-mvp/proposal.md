<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## Why

The bundled router is intentionally weak, while the strongest public baseline
uses nearly all available public budget. A competitive submission needs
evidence-driven model selection with explicit cost headroom before the August
27 deadline.

## What Changes

- Add a deterministic candidate-evaluation workflow that compares a safe
  baseline, a sparse lexical uplift model, and a compact nonlinear model under
  identical repeated validation folds.
- Reject candidates that exceed 92% of any official tier budget and require an
  absolute weighted-score improvement of `0.005` for the performance MVP.
- Bundle the selected prompt-only model as a strict, reproducible JSON artifact
  and make the existing `router-run` command use it without changing the v1
  input or output contract.
- Add regression, determinism, budget, artifact-integrity, and full-runtime
  verification, reusing the existing uv-based GitHub Actions quality and test
  jobs instead of creating a second workflow.
- Publish reproducible architecture and evidence documentation and prepare a
  Markdown technical-report draft.

## Capabilities

### New Capabilities

- `competitive-prompt-routing`: Covers evidence-based candidate selection,
  strict learned-artifact loading, safe tier routing, and unchanged
  prompt-only runtime behavior.

### Modified Capabilities

None.

## Impact

- Affects the offline baseline/training tools, the bundled router runtime,
  package resources, tests, public documentation, and existing CI coverage.
- Keeps `router-run`, v1 schemas, policy values, atomic output behavior, and
  standard-library-only runtime compatibility unchanged.
- May add training-only dependencies for the nonlinear experiment; no runtime
  dependency is added to the package or container.
- Does not automate GitHub/GHCR publication, contest-site submission, Asana,
  or alter the existing uv and tag-gated release automation.
