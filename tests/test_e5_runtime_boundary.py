# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib
import inspect
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class E5RuntimeBoundaryTest(unittest.TestCase):
    def test_public_route_contract_is_owned_by_ossp_router(self) -> None:
        try:
            module = importlib.import_module("ossp_router.e5_router")
        except ModuleNotFoundError as exc:
            self.fail(f"stable runtime module is missing: {exc}")

        self.assertEqual(
            ("inputs", "policy", "tier", "artifacts"),
            tuple(inspect.signature(module.route).parameters),
        )
        self.assertEqual("Submission", inspect.signature(module.route).return_annotation)

    def test_product_runtime_never_imports_baselines(self) -> None:
        offenders = []
        for path in sorted((ROOT / "src/ossp_router").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if "from baselines" in text or "import baselines" in text:
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual([], offenders)

    def test_product_runtime_contains_no_artifact_publication_code(self) -> None:
        source = (ROOT / "src/ossp_router/e5_artifact.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("def model_to_artifact", source)

    def test_runtime_artifacts_are_package_resources(self) -> None:
        resource_root = ROOT / "src/ossp_router/resources"
        required = {
            "hash-regex-public.v1.json",
            "binomial-logistic-quality-public.v1.json",
            "e5-bilinear-compatibility-public.v1.json",
        }
        present = {path.name for path in resource_root.glob("*.json")}
        self.assertTrue(required <= present)


if __name__ == "__main__":
    unittest.main()
