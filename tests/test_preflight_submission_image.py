# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from unittest import mock

from ossp_router.runtime import AttemptKind, AttemptResult
from tools import preflight_submission_image as preflight


class SubmissionImagePreflightTest(unittest.TestCase):
    @staticmethod
    def _write_input(path: pathlib.Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "challenge_id": "preflight-test",
                    "split": "toy",
                    "episodes": [{"episode_id": "toy-001", "prompt": "Hello"}],
                }
            ),
            encoding="utf-8",
        )

    def test_reads_the_single_arm64_oci_root_digest(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            layout = pathlib.Path(raw_directory)
            digest = "sha256:" + "a" * 64
            (layout / "index.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 2,
                        "manifests": [
                            {
                                "digest": digest,
                                "platform": {
                                    "architecture": "arm64",
                                    "os": "linux",
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(digest, preflight.read_arm64_root_digest(layout))

    def test_preflight_cross_binds_sizes_and_constrained_smoke(self) -> None:
        manifest_digest = "sha256:" + "a" * 64
        config_digest = "sha256:" + "b" * 64
        metadata = {
            "Id": config_digest,
            "RepoDigests": [],
            "Os": "linux",
            "Architecture": "arm64",
            "Config": {"Volumes": None},
        }
        smoke_result = AttemptResult(
            kind=AttemptKind.VALID,
            detail="valid submission",
            returncode=0,
            measurement_elapsed_ns=2_500_000_000,
            output_bytes=512,
            output_sha256="c" * 64,
        )
        with tempfile.TemporaryDirectory() as raw_directory:
            target = pathlib.Path(raw_directory)
            (target / "index.json").write_text("{}", encoding="utf-8")
            input_path = target / "input.json"
            self._write_input(input_path)
            work_directory = target / "operator"
            with (
                mock.patch.object(
                    preflight,
                    "read_arm64_root_digest",
                    return_value=manifest_digest,
                ),
                mock.patch.object(
                    preflight,
                    "measure_oci_layout",
                    return_value=(manifest_digest, config_digest, 123),
                ),
                mock.patch.object(
                    preflight,
                    "inspect_image_runtime_metadata",
                    return_value=metadata,
                ),
                mock.patch.object(preflight, "validate_image_configuration"),
                mock.patch.object(
                    preflight,
                    "measure_local_rootfs",
                    return_value=456,
                ) as measure_rootfs,
                mock.patch.object(
                    preflight,
                    "run_constrained_smoke",
                    return_value=smoke_result,
                ),
                mock.patch.object(
                    preflight,
                    "docker_server_platform",
                    return_value="linux/amd64",
                ),
            ):
                report = preflight.preflight_submission_image(
                    docker="docker",
                    image="router:test",
                    oci_layout=target,
                    input_path=input_path,
                    tier="balanced",
                    work_directory=work_directory,
                )

        measure_rootfs.assert_called_once_with(
            "docker",
            config_digest,
            work_directory,
        )
        self.assertTrue(report["passed"])
        self.assertEqual(123, report["image_size"]["compressed_layers_bytes"])
        self.assertEqual(456, report["image_size"]["rootfs_apparent_bytes"])
        self.assertEqual(
            "oci-manifest-layer-descriptors-v1",
            report["image_size"]["compressed_layers_measurement_method"],
        )
        self.assertEqual(
            "docker-export-tar-apparent-size-v1",
            report["image_size"]["rootfs_measurement_method"],
        )
        self.assertEqual(2.5, report["smoke"]["elapsed_seconds"])
        self.assertEqual("toy-smoke", report["workload"]["basis"])
        self.assertEqual(1, report["workload"]["episodes"])
        self.assertEqual(64, len(report["workload"]["sha256"]))
        self.assertFalse(report["submission_ready"])
        self.assertEqual(
            "not-run",
            report["full_native_runtime_gate"]["status"],
        )
        self.assertTrue(report["limitations"])
        self.assertEqual("linux/amd64", report["runtime"]["docker_server_platform"])
        self.assertFalse(report["runtime"]["native_arm64"])

    def test_preflight_rejects_an_unrelated_loaded_image(self) -> None:
        manifest_digest = "sha256:" + "a" * 64
        config_digest = "sha256:" + "b" * 64
        metadata = {
            "Id": "sha256:" + "c" * 64,
            "RepoDigests": [],
            "Os": "linux",
            "Architecture": "arm64",
            "Config": {"Volumes": None},
        }
        with tempfile.TemporaryDirectory() as raw_directory:
            target = pathlib.Path(raw_directory)
            input_path = target / "input.json"
            self._write_input(input_path)
            with (
                mock.patch.object(
                    preflight,
                    "read_arm64_root_digest",
                    return_value=manifest_digest,
                ),
                mock.patch.object(
                    preflight,
                    "measure_oci_layout",
                    return_value=(manifest_digest, config_digest, 123),
                ),
                mock.patch.object(
                    preflight,
                    "inspect_image_runtime_metadata",
                    return_value=metadata,
                ),
                mock.patch.object(preflight, "validate_image_configuration"),
            ):
                with self.assertRaisesRegex(RuntimeError, "config digest"):
                    preflight.preflight_submission_image(
                        docker="docker",
                        image="router:test",
                        oci_layout=target,
                        input_path=input_path,
                        tier="balanced",
                        work_directory=target / "operator",
                    )


if __name__ == "__main__":
    unittest.main()
