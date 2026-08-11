# Development Workflow

- Use OpenSpec for feature, behavior, or architecture changes.
- Follow the OpenSpec apply/verify workflow when a change has a spec.
- Use installed Superpowers skills for implementation, debugging, TDD, and verification when applicable.
- Do not duplicate detailed workflows here when an existing skill already defines them.

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
