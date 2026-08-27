# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE_IMAGE = (
    "python:3.11.15-slim-bookworm@sha256:"
    "d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3"
)


class E5ContainerContractTest(unittest.TestCase):
    def test_container_entrypoint_exposes_e5_runtime_arguments(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "src")))
        with tempfile.TemporaryDirectory() as raw_directory:
            result = subprocess.run(
                [sys.executable, str(ROOT / "container/entrypoint.py"), "--help"],
                cwd=raw_directory,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        for option in (
            "--hash-artifact",
            "--binomial-artifact",
            "--compatibility-artifact",
            "--model-dir",
        ):
            self.assertIn(option, result.stdout)

    def test_final_image_contains_only_arm64_e5_runtime_requirements(self) -> None:
        dockerfile = (ROOT / "container/Dockerfile").read_text(encoding="utf-8")

        self.assertEqual(2, dockerfile.count(f"FROM {BASE_IMAGE}"))
        self.assertIn("--group e5-runtime", dockerfile)
        self.assertIn("--no-install-project", dockerfile)
        self.assertIn("tools/fetch_e5_model.py", dockerfile)
        self.assertIn("--check", dockerfile)
        self.assertIn("COPY --from=dependencies", dockerfile)
        self.assertIn("COPY --chown=65532:65532 baselines", dockerfile)
        self.assertIn(
            "COPY --from=dependencies --chown=65532:65532 "
            "/build/e5-model /opt/router/build/e5-model",
            dockerfile,
        )
        self.assertNotIn("COPY --chown=65532:65532 build/e5-model", dockerfile)
        self.assertIn("THIRD_PARTY_NOTICES.md", dockerfile)
        self.assertIn("configs/e5-model.v1.json", dockerfile)
        self.assertIn(
            'ENTRYPOINT ["/opt/e5-runtime/bin/python", "/opt/router/entrypoint.py"]',
            dockerfile,
        )
        self.assertIn("USER 65532:65532", dockerfile)
        self.assertNotIn("VOLUME", dockerfile)
        self.assertIn("ARG SOURCE_COMMIT_SHA=unbound", dockerfile)
        self.assertIn("ARG SOURCE_REPOSITORY_URL=unbound", dockerfile)
        self.assertIn("org.opencontainers.image.revision", dockerfile)
        self.assertIn("org.opencontainers.image.source", dockerfile)

    def test_arm64_build_fetches_model_and_runs_hard_limit_preflight(self) -> None:
        script = (ROOT / "scripts/build-arm64.sh").read_text(encoding="utf-8")

        self.assertIn("tools/fetch_e5_model.py", script)
        self.assertIn("configs/e5-model.v1.json", script)
        self.assertIn("type=oci", script)
        self.assertIn("tools/preflight_submission_image.py", script)
        self.assertIn("data/toy/inputs.json", script)
        self.assertIn("OSSP_REQUIRE_NATIVE_RUNTIME", script)
        self.assertIn("mktemp -d -p /tmp pawn2qween-e5-preflight", script)
        self.assertNotIn('PREFLIGHT_WORK="$BUILD_ROOT', script)
        self.assertIn("image-measurement-journal.json", script)
        self.assertIn("Preserving recovery journal", script)
        self.assertIn("Temporary Buildx builder cleanup failed", script)
        self.assertIn('rm -f -- "$PREFLIGHT_REPORT" "$FULL_RUNTIME_REPORT"', script)
        self.assertIn('--image "$IMAGE_ID"', script)
        self.assertIn("SOURCE_COMMIT_SHA", script)
        self.assertIn("SOURCE_REPOSITORY_URL", script)


if __name__ == "__main__":
    unittest.main()
