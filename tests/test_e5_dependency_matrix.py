# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class E5DependencyMatrixTest(unittest.TestCase):
    def test_runtime_and_training_dependencies_are_independent(self) -> None:
        project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('e5-runtime = [', project)
        self.assertIn('e5-train = [', project)
        training_group = project.split("e5-train = [", 1)[1].split("]", 1)[0]
        self.assertNotIn("include-group", training_group)
        self.assertIn('"numpy==2.0.2"', training_group)
        self.assertIn('"scikit-learn==1.7.2"', project)
        self.assertIn(
            '"torch==2.8.0; sys_platform == \'linux\' '
            'and platform_machine == \'x86_64\'"',
            project,
        )
        self.assertIn(
            'e5-train = {requires-python = ">=3.11,<3.12"}',
            project,
        )

    def test_runtime_ci_never_installs_training_dependencies(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        runtime_job = workflow.split("  e5-runtime:\n", 1)[1].split(
            "  e5-training:\n", 1
        )[0]

        self.assertIn("--group e5-runtime", runtime_job)
        self.assertNotIn("--group e5-train", runtime_job)
        self.assertNotIn("tests.test_binomial_quality_training", runtime_job)
        self.assertNotIn("tests.test_e5_training", runtime_job)

    def test_training_ci_uses_only_the_python_311_training_group(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        training_job = workflow.split("  e5-training:\n", 1)[1].split(
            "  arm64-image:\n", 1
        )[0]

        self.assertIn('python-version: "3.11"', training_job)
        self.assertIn("uv sync --locked --no-dev --group e5-train", training_job)
        self.assertIn("tests.test_e5_training", training_job)
        self.assertIn("tests.test_hash_router", training_job)
        self.assertNotIn("OSSP_TEST_E5_RUNTIME", training_job)


if __name__ == "__main__":
    unittest.main()
