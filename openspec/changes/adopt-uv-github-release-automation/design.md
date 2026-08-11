<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

## Context

See `proposal.md` for motivation and the two capability specs for observable behavior. The repository currently uses a minimal `pyproject.toml` only for the build backend, `setup.cfg` for package metadata, and three requirements files for task-specific dependencies. The runtime itself intentionally uses only the Python standard library and supports Python 3.9, while repository tooling can use Python 3.11. No GitHub Actions workflow or changelog-based release process exists.

The release process must distinguish the project's stable and latest prerelease channels, and an ordinary branch push must never publish a release. Package publication to PyPI and container publication are outside this change.

## Goals / Non-Goals

**Goals:**

- Make `pyproject.toml` and `uv.lock` the only dependency and packaging sources of truth.
- Keep default installs free of third-party runtime dependencies while making specialized tool sets explicit.
- Run reproducible quality, test, and build gates in GitHub Actions.
- Publish wheel and source distributions only from explicit supported tags after validation.
- Make release channel selection deterministic from the tag syntax.

**Non-Goals:**

- Automating version bumps, changelog authoring, or tag creation.
- Publishing packages or images outside GitHub Releases.
- Changing router APIs, scoring, challenge policy, or container runtime behavior.
- Adding a changelog requirement to every pull request.

## Decisions

### Use PEP 621 metadata and PEP 735 dependency groups

`pyproject.toml` will contain the existing setuptools package metadata, scripts, and package data. The default dependency list remains empty. Four groups divide repository tools by purpose: `dev`, `train`, `materialize`, and `deepmind`. Group-specific Python constraints allow the runtime package to keep Python 3.9 support while development defaults to Python 3.11. The `train` and `deepmind` groups declare a uv conflict because their deliberately pinned NumPy versions differ.

This replaces both continued split metadata and tool-specific requirements files. Optional project dependencies were considered, but these tools are contributor tasks rather than features installed by package consumers, so dependency groups better express their role.

### Pin uv and commit its universal lock file

The repository will declare uv 0.12.3 as the required version, commit `.python-version` with 3.11, and commit `uv.lock`. CI uses `uv lock --check` and locked synchronization to catch drift. The test matrix synchronizes without the development or specialized groups so Python 3.9 exercises the runtime-compatible package surface.

### Separate CI from release triggers

`ci.yml` runs only for pushes to `main` and pull requests targeting `main`. `release.yml` runs only for pushed tags matching `v*.*.*`. The release workflow still performs strict parsing, so the broad GitHub trigger cannot publish malformed tags. Workflow and ref concurrency groups cancel obsolete validation runs. Actions are pinned by immutable commit SHA, and workflow-level permissions default to `contents: read`.

One workflow triggered on every push with conditional release steps was considered. Separate triggers make the safety boundary visible and prevent ordinary pushes from even starting a release workflow.

### Validate release metadata with a small standard-library tool

`tools/prepare_release.py` parses accepted tags, maps alpha/beta/rc tags to their PEP 440 project versions, compares the tagged project version, extracts exactly one non-empty matching changelog section, and writes release notes plus GitHub step outputs. Unit tests cover tag classification and rejection paths. The tool uses no third-party dependency so it can run after a default locked sync.

Stable `vMAJOR.MINOR.PATCH` tags map to a non-prerelease GitHub Release with `--latest`. `vMAJOR.MINOR.PATCH-(alpha|beta|rc).N` tags map to the project `latest` channel, a GitHub prerelease, and `--latest=false`. The tag itself remains the release identifier; prerelease project versions use PEP 440 forms such as `2.0.0rc4`.

### Publish only after all gates complete

The release workflow has read-only quality and Python-version test jobs. A final publication job depends on both, builds wheel and source distributions from the tagged checkout, prepares changelog notes, and receives `contents: write` only for `gh release create`. The GitHub CLI verifies that the tag exists and attaches only the generated distributions.

### Keep unreleased notes separate from versioned notes

`CHANGELOG.md` follows Keep a Changelog headings and starts with `[Unreleased]`. Before a release tag is pushed, maintainers move relevant entries into a heading matching the tag without the leading `v`, using the SemVer-style prerelease spelling for latest-channel releases. Changelog completeness is enforced at release time rather than on every pull request.

## Risks / Trade-offs

- **[Python 3.9 cannot run development tools constrained to Python 3.11]** → CI separates the Python 3.11 quality job from default-only runtime tests across Python 3.9 and 3.11.
- **[A broad `v*.*.*` GitHub tag glob also starts workflows for unsupported tags]** → the preparation tool rejects any tag outside the two exact formats before publication.
- **[The project version must be edited before every tagged release]** → release validation fails safely and reports the expected and actual versions; automatic mutation of tagged source is intentionally avoided.
- **[Specialized groups carry incompatible NumPy pins]** → uv records an explicit group conflict and documentation shows separate commands.
- **[GitHub Release creation can fail after assets are built]** → no external package registry is mutated; maintainers can rerun the failed job for the unchanged tag after correcting repository permissions or transient GitHub failures.

## Migration Plan

1. Add release-preparation tests and the changelog parser.
2. Consolidate metadata and dependency groups in `pyproject.toml`, generate `uv.lock`, and add `.python-version`.
3. Migrate tests and documentation to uv, then delete `setup.cfg` and the three requirements files.
4. Update repository policy and license annotations for the new files.
5. Add CI and tag-only release workflows.
6. Run narrow tests, lock checks, lint, REUSE, supported-Python tests, and package builds.

Rollback is a normal revert of these repository files. No package registry, database, or production service migration is involved.
