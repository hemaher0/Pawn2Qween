<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## 1. Evaluation Foundation

- [ ] 1.1 Materialize the complete 1,760 Train and 880 Dev inputs from pinned sources and verify their recorded SHA-256 values.
- [ ] 1.2 Add deterministic five-fold, three-repeat assignment and literal Decimal safety-cap tests before implementing the evaluation helpers.
- [ ] 1.3 Implement candidate evidence records, cap rejection, and deterministic ranking with no prompt text, episode IDs, private evaluation results, or non-public inputs in reports.
- [ ] 1.4 Refit and measure the Train-only safe hash-regex baseline on the fixed folds, recording per-fold score and cost evidence.

## 2. Candidate Experiments

- [ ] 2.1 Add failing tests for content-only bounded word and character hashing, then implement the sparse feature vector.
- [ ] 2.2 Add failing tests for uplift and relative-cost targets plus byte-deterministic ridge artifacts, then implement the sparse trainer.
- [ ] 2.3 Evaluate the sparse candidate on the fixed repeated folds and record its safe-baseline improvement and cap status.
- [ ] 2.4 Add failing strict-parser and evaluator tests for bounded shallow trees, then implement the training-only nonlinear candidate and pure-Python evaluator.
- [ ] 2.5 Evaluate the nonlinear candidate on the same folds and apply the deterministic safe-first ranking.
- [ ] 2.6 If the `0.005` gate is missed, run exactly one follow-up configuration for each of the two best safe candidates and hard-select the final safe winner.
- [ ] 2.7 Evaluate the selected candidate once on untouched Dev and record whether the performance MVP passed without retuning the winner.

## 3. Runtime Integration

- [ ] 3.1 Add strict artifact validation tests covering field sets, dimensions, feature versions, model coverage, policy digest, finite values, and bounded tree structure.
- [ ] 3.2 Train the selected configuration on combined Train and Dev twice and require byte-identical final artifacts.
- [ ] 3.3 Bundle the selected artifact and add a standard-library loader that fails closed on incompatibility.
- [ ] 3.4 Add failing CLI integration tests, then make the existing `router-run` path use competitive routing without changing arguments, schema, exit codes, atomic writes, or file mode.
- [ ] 3.5 Add content-decision tests for changed IDs, reordered input, repeated execution, prompt form, and message form.

## 4. Quality Gates and Documentation

- [ ] 4.1 Verify that new default-only tests run in the existing uv-based Python 3.9/3.11 CI jobs; only if training-tool tests require it, extend the existing workflow with the `train` dependency group without adding a duplicate workflow or changing Docker, publishing, or release behavior.
- [ ] 4.2 Document architecture, artifact provenance, exact training and public-data evaluation commands, selected public Train/Dev evidence, dependencies, licenses, and limitations.
- [ ] 4.3 Prepare an evidence-backed Markdown technical-report draft including public Train/Dev score/cost comparison, runtime results, SBOM notes, and AI coding-tool disclosure, with no private evaluation result.

## 5. Release Verification

- [ ] 5.1 Run the complete unittest and Ruff suites and fix every failure without skipping or weakening tests.
- [ ] 5.2 Run Train, Dev, and combined official self-checks twice per tier and verify byte-identical submissions.
- [ ] 5.3 Run changed-ID/order audits and stratified cost stress, recording worst observed tier costs and the stricter 92% release-gate result.
- [ ] 5.4 Build and inspect the `linux/arm64` release-candidate image under the official isolation and resource limits, confirming no training dependency is present.
- [ ] 5.5 Record fresh commands, exit codes, test counts, hashes, public Train/Dev score/cost values, image size, and tier runtimes in the final verification evidence.
