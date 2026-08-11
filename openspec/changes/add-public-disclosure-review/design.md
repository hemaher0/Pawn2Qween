<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## Context

See `proposal.md` for motivation and
`specs/public-disclosure-review/spec.md` for the behavior contract. The current
repository already states a clean-room and data boundary in `CONTRIBUTING.md`
and scans the working tree for selected credential formats, internal strings,
and model artifacts in `tests/test_repository_policy.py`. `AGENTS.md` prohibits
committing secrets but does not define a disclosure-review scope, verdict, or
publication stop condition. OpenSpec guidance likewise has no disclosure check
at proposal, apply, verify, or archive time.

The workflow does not require an independent reviewer and assigns semantic
review to the active Codex session. A separate AI API, GitHub Action, reviewer
account, or external service would add credentials and operational complexity
without improving the local workflow. Direct Git commands issued outside Codex
cannot be intercepted.

## Goals / Non-Goals

**Goals:**

- Make one policy authoritative for every artifact that can enter the public
  repository or a release.
- Give Codex a repeatable scope and output contract at each publication
  boundary.
- Combine semantic review with deterministic repository tests without adding a
  dependency or service.
- Keep non-public working evidence in the existing ignored local reference
  area while ensuring public artifacts stand on their own.
- Make project copyright notices match confirmed Git provenance without
  removing original or upstream rights.

**Non-Goals:**

- Guarantee review of manual Git operations performed without Codex.
- Ask GitHub Actions or another remote service to make semantic disclosure
  judgments.
- Replace source, license, DCO, security, or data-specific project policies.
- Rewrite published Git history or change the Apache-2.0 project license.
- Rename SKT challenge protocol filenames, container labels, or other
  compatibility identifiers merely because they contain an organization name.
- Publish local `references/` content or make it part of the OpenSpec source of
  truth.
- Change router runtime, scoring, challenge rules, or release triggers.

## Decisions

### Keep the policy source of truth in CONTRIBUTING.md

Expand the existing clean-room boundary into a `Public disclosure` section that
defines the three eligibility tests: redistribution authority, safe disclosure,
and durable public-project value. The same section lists prohibited categories,
states that ambiguity is non-public until resolved, and permits sanitized public
decisions that cannot reconstruct private evidence.

`AGENTS.md` will link to that section and define Codex procedure only. OpenSpec
configuration will add artifact and operation guidance that references the same
policy. Copying the full list into all three files was rejected because the
lists would drift and make future policy changes ambiguous.

### Treat Codex review as a required local workflow gate

Before Codex prepares or executes a commit, push, archive, or release, it first
identifies the exact public candidate:

- commit: the staged diff;
- push: commits present locally but absent from the target upstream;
- archive: the OpenSpec change, affected implementation delta, synced specs,
  and retained archive;
- release: the tag tree, version notes, and generated release assets.

Codex then runs the relevant deterministic checks, reads the candidate in
context, and returns `PASS`, `BLOCK`, or `NEEDS_CONFIRMATION`. Non-passing
verdicts pause the requested publication action. Findings include the scope,
file and location, sanitized reason, and remediation, but never echo a detected
secret value.

A Git hook was considered but rejected: it cannot perform the requested
semantic review without another model invocation, is not reliably distributed
with clones, and would create a misleading guarantee for manual operations.

### Divide deterministic and semantic responsibilities explicitly

`tests/test_repository_policy.py` remains the deterministic enforcement point.
It will verify the canonical policy text and agent/OpenSpec integration, retain
the existing secret and artifact scans, and add only stable patterns with low
false-positive risk. The test suite will not claim to establish authorship,
redistribution rights, confidentiality, private-evaluation provenance, or
embargo timing.

Codex owns those contextual judgments. When evidence is insufficient it returns
`NEEDS_CONFIRMATION` instead of inferring permission. An external secret scanner
or new library was rejected because the repository already has a focused
standard-library policy test and the change does not need another dependency.

### Integrate disclosure review through OpenSpec configuration

Add proposal rules requiring disclosure scope and exclusions, spec rules
requiring testable privacy and failure scenarios when relevant, task rules
requiring a final disclosure gate, and apply/archive guidance requiring Codex
review of the applicable candidate. These are forward-looking authoring rules;
the implementation will not rewrite unrelated archived history merely to add a
new heading.

OpenSpec public artifacts may record a public-safe decision derived from local
working evidence, but they must remain understandable without linking to
ignored confidential material. Private measurements and source artifacts stay
under the already ignored `references/` workspace. Merely moving a file within
a tracked public tree is not sanitization.

### Preserve automated CI as a deterministic backstop

The existing CI already runs repository policy tests. No workflow trigger,
permission, secret, or job is added. This keeps ordinary branch pushes free of
release behavior and ensures the new policy checks run wherever the current
test suite runs, while the local Codex review remains an agent workflow rather
than a remote AI integration.

### Use the root commit as the project-attribution boundary

Treat root commit `3cccbf602077a846c13b2cb1356eee1559a631db` as the
original project snapshot. The repository owner confirmed that changes after
that snapshot are `hemaher0` contributions. Classify paths by exact path
existence and content difference rather than similarity-based rename detection,
because short deleted dependency files can otherwise be misidentified as
unrelated new OpenSpec YAML files.

- A current project path absent from the root snapshot receives only the
  `Copyright 2026 hemaher0` project notice.
- A current project path present in the root snapshot and changed afterward
  retains `Copyright 2026 SK TELECOM CO., LTD.` and adds
  `Copyright 2026 hemaher0`.
- A current project path unchanged from the root snapshot keeps its original
  project notice.
- Upstream third-party notices remain authoritative and are not replaced by
  either project holder.

`REUSE.toml` annotations are split when one existing path group contains more
than one provenance class. `NOTICE` retains the original SK TELECOM CO., LTD.
notice and records the later `hemaher0` modifications. The SK Telecom employee
and company-email instructions are removed from `CONTRIBUTING.md` because they
do not apply to the current repository maintainer. This is a current-tree
correction committed linearly; it does not rewrite already published history.

## Risks / Trade-offs

- **[A manual Git operation can bypass Codex semantic review]** → document the
  boundary explicitly and retain deterministic tests in local and CI gates.
- **[Codex can miss contextual disclosure risk]** → review the complete
  publication candidate, require `NEEDS_CONFIRMATION` for uncertain authority,
  and keep deterministic checks as independent evidence.
- **[Pattern checks can flag harmless fixtures]** → use narrowly scoped stable
  patterns and preserve the existing technique of splitting literal examples
  inside the test implementation.
- **[Private evidence can leak through a summary]** → require public artifacts
  to stand independently and prohibit details that reconstruct the private
  source, not only verbatim copies.
- **[Policy copies can drift]** → keep normative criteria in
  `CONTRIBUTING.md` and test that agent and OpenSpec guidance point to it.
- **[File similarity can produce false provenance classifications]** → compare
  exact path presence and content against the root tree with rename detection
  disabled.
- **[A blanket replacement can erase original or upstream rights]** → use
  additive notices for modified original files and keep third-party mappings
  unchanged.

## Migration Plan

1. Add failing repository policy assertions for the canonical disclosure
   policy, Codex verdict contract, review boundaries, and OpenSpec guidance.
2. Expand `CONTRIBUTING.md`, add the concise Codex gate to `AGENTS.md`, and add
   proposal, task, apply, verify, and archive guidance to
   `openspec/config.yaml`.
3. Add proposal and task rules plus apply and archive guidance, with apply
   guidance covering verification before success.
4. Run focused repository policy tests, strict OpenSpec validation, Ruff,
   REUSE, and the supported-Python suite.
5. Before integrating or publishing the change, have Codex review the outgoing
   commit range using the newly documented contract.
6. Add failing policy assertions for root-only, later-only, and mixed
   attribution examples.
7. Correct SPDX headers, `NOTICE`, `REUSE.toml`, and contributor instructions
   using the root-commit provenance boundary.
8. Re-run OpenSpec, REUSE, policy, lint, and supported-Python verification, then
   perform the disclosure review again before committing the correction.

Rollback is a normal revert of the policy, agent guidance, configuration, and
tests plus the attribution correction. No public data, dependency, external
service, runtime migration, license change, or history rewrite is involved.
