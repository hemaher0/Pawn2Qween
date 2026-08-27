# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.metadata
import io
import pathlib
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout


PROJECT_NAME = "ossp-2026-llm-router-challenge"


class E5RuntimePackagingTest(unittest.TestCase):
    def test_router_run_entrypoint_exposes_e5_runtime_options(self) -> None:
        distribution = importlib.metadata.distribution(PROJECT_NAME)
        entrypoint = next(
            item
            for item in distribution.entry_points
            if item.group == "console_scripts" and item.name == "router-run"
        )
        self.assertEqual("ossp_router.e5_router:main", entrypoint.value)

        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            entrypoint.load()(["--help"])

        self.assertEqual(0, raised.exception.code)
        help_text = output.getvalue()
        self.assertIn("--model-dir", help_text)
        self.assertIn("--binomial-artifact", help_text)
        self.assertIn("--compatibility-artifact", help_text)

    def test_installed_distribution_contains_e5_runtime_resources(self) -> None:
        script = """
from importlib import resources
from ossp_router import e5_router

root = resources.files("ossp_router.resources")
required = (
    "hash-regex-public.v1.json",
    "binomial-logistic-quality-public.v1.json",
    "e5-bilinear-compatibility-public.v1.json",
)
missing = [name for name in required if not root.joinpath(name).is_file()]
raise SystemExit(0 if not missing and callable(e5_router.main) else 1)
"""
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(
                [sys.executable, "-I", "-c", script],
                cwd=pathlib.Path(temporary),
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
