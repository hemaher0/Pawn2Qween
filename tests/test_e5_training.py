# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.metadata
import inspect
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

try:
    import numpy as np
except ModuleNotFoundError as error:
    raise unittest.SkipTest("E5 training tests require NumPy") from error

from ossp_router import e5_artifact as compatibility
from ossp_router.protocol import MODEL_IDS
from ossp_router.training import artifact_publication as publication
from ossp_router.training import e5_evaluation, e5_features, e5_fit


PROJECT_NAME = "ossp-2026-llm-router-challenge"


def _unit_embeddings(rows: int) -> np.ndarray:
    values = np.zeros((rows, compatibility.EMBEDDING_DIMENSION), dtype=np.float32)
    for row in range(rows):
        values[row, row % compatibility.EMBEDDING_DIMENSION] = 1.0
    return values


def _metadata(train_rows: int, dev_rows: int) -> dict[str, object]:
    return {
        "content_only": True,
        "content_token_budget": 480,
        "dev_rows": dev_rows,
        "dimensions": compatibility.EMBEDDING_DIMENSION,
        "head_tokens": 240,
        "license": "MIT",
        "max_length": 512,
        "model_commit": compatibility.PINNED_REVISION,
        "model_id": compatibility.PINNED_MODEL_ID,
        "pooling": "attention-mask mean pooling followed by L2 normalization",
        "prefix": "query: ",
        "runtime": "onnxruntime-fp32-cpu",
        "tail_tokens": 240,
        "train_rows": train_rows,
    }


class E5TrainingTest(unittest.TestCase):
    def test_router_train_entrypoint_exposes_each_offline_stage(self) -> None:
        distribution = importlib.metadata.distribution(PROJECT_NAME)
        entrypoint = next(
            item
            for item in distribution.entry_points
            if item.group == "console_scripts" and item.name == "router-train"
        )
        self.assertEqual("ossp_router.training.cli:main", entrypoint.value)

        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            entrypoint.load()(["--help"])

        self.assertEqual(0, raised.exception.code)
        self.assertIn("{hash,encode,fit,evaluate}", output.getvalue())

    def test_cli_delegates_each_offline_stage_to_one_module(self) -> None:
        root = pathlib.Path(__file__).resolve().parents[1]
        cli = (root / "src/ossp_router/training/cli.py").read_text(
            encoding="utf-8"
        )
        feature_stage = (root / "src/ossp_router/training/e5_features.py").read_text(
            encoding="utf-8"
        )
        fit_stage = (root / "src/ossp_router/training/e5_fit.py").read_text(
            encoding="utf-8"
        )
        evaluation_stage = (
            root / "src/ossp_router/training/e5_evaluation.py"
        ).read_text(encoding="utf-8")

        self.assertLessEqual(len(cli.splitlines()), 200)
        self.assertIn("e5_features", cli)
        self.assertIn("e5_fit", cli)
        self.assertIn("e5_evaluation", cli)
        self.assertNotIn("load_outcomes", feature_stage)
        self.assertNotIn("import torch", feature_stage)
        self.assertNotIn("dev_outcomes", fit_stage)
        self.assertNotIn("E5OnnxEncoder", evaluation_stage)

    def test_deterministic_cuda_environment_is_set_before_torch_import(self) -> None:
        original = os.environ.pop("CUBLAS_WORKSPACE_CONFIG", None)
        try:
            e5_fit._configure_deterministic_torch_environment()

            self.assertEqual(":4096:8", os.environ["CUBLAS_WORKSPACE_CONFIG"])
        finally:
            if original is None:
                os.environ.pop("CUBLAS_WORKSPACE_CONFIG", None)
            else:
                os.environ["CUBLAS_WORKSPACE_CONFIG"] = original

    def test_script_can_be_invoked_directly_from_repository_root(self) -> None:
        root = pathlib.Path(__file__).resolve().parents[1]

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ossp_router.training.cli",
                "--help",
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("{hash,encode,fit,evaluate}", result.stdout)

    def test_feature_archive_requires_ordered_digests_and_unit_vectors(self) -> None:
        texts = ("first prompt", "second prompt", "dev prompt")
        embeddings = _unit_embeddings(len(texts))
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = pathlib.Path(raw_directory)
            path = directory / "features.npz"
            e5_features.write_feature_archive(
                path,
                texts=texts,
                embeddings=embeddings,
                truncated=np.asarray((False, True, False), dtype=bool),
                metadata=_metadata(train_rows=2, dev_rows=1),
            )

            archive = e5_features.load_feature_archive(
                path,
                expected_texts=texts,
                train_rows=2,
                dev_rows=1,
            )

            self.assertEqual(
                (3, compatibility.EMBEDDING_DIMENSION), archive.embeddings.shape
            )
            self.assertFalse(archive.embeddings.flags.writeable)
            self.assertEqual((False, True, False), tuple(archive.truncated))
            self.assertEqual(
                tuple(e5_features.content_sha256(text) for text in texts),
                archive.content_sha256,
            )

            with self.assertRaises(ValueError):
                e5_features.load_feature_archive(
                    path,
                    expected_texts=tuple(reversed(texts)),
                    train_rows=2,
                    dev_rows=1,
                )

            invalid = embeddings.copy()
            invalid[0] *= 2.0
            with path.open("wb") as stream:
                np.savez_compressed(
                    stream,
                    content_sha256=np.asarray(
                        tuple(e5_features.content_sha256(text) for text in texts)
                    ),
                    embeddings=invalid,
                    truncated=np.zeros(len(texts), dtype=bool),
                    metadata_json=np.asarray(
                        json.dumps(_metadata(train_rows=2, dev_rows=1))
                    ),
                )
            with self.assertRaises(ValueError):
                e5_features.load_feature_archive(
                    path,
                    expected_texts=texts,
                    train_rows=2,
                    dev_rows=1,
                )

    def test_jeffreys_targets_use_each_generation_count(self) -> None:
        quality = np.asarray(
            ((0.0, 0.5, 1.0), (0.25, 0.75, 0.5)),
            dtype=np.float64,
        )
        counts = np.asarray(((2, 4, 8), (4, 4, 2)), dtype=np.float64)

        targets, trials = e5_fit.jeffreys_targets(quality, counts)

        expected_successes = np.rint(quality * counts) + 0.5
        np.testing.assert_allclose(expected_successes / (counts + 1.0), targets)
        np.testing.assert_array_equal(counts + 1.0, trials)

    def test_compatibility_fit_is_deterministic_rank_two_and_round_trips(self) -> None:
        embeddings = _unit_embeddings(12)
        quality = np.asarray(
            [
                (
                    (row % 3) / 2.0,
                    ((row + 1) % 3) / 2.0,
                    ((row + 2) % 3) / 2.0,
                )
                for row in range(len(embeddings))
            ],
            dtype=np.float64,
        )
        counts = np.full_like(quality, 4.0)
        arguments = {
            "train_input_sha256": "1" * 64,
            "train_outcome_sha256": "2" * 64,
            "seed": e5_fit.FULL_FIT_SEED,
            "steps": 20,
            "device": "cpu",
        }

        first = e5_fit.fit_compatibility_model(
            embeddings,
            quality,
            counts,
            **arguments,
        )
        second = e5_fit.fit_compatibility_model(
            embeddings,
            quality,
            counts,
            **arguments,
        )
        first_bytes = publication.canonical_artifact_bytes(
            publication.compatibility_model_to_artifact(first)
        )
        second_bytes = publication.canonical_artifact_bytes(
            publication.compatibility_model_to_artifact(second)
        )

        self.assertEqual(first_bytes, second_bytes)
        self.assertEqual(compatibility.LATENT_RANK, len(first.projection))
        np.testing.assert_allclose(embeddings.mean(axis=0), first.embedding_mean)
        parsed = compatibility.parse_compatibility_artifact(
            json.loads(first_bytes.decode("utf-8"))
        )
        for row in embeddings[:3]:
            expected = compatibility.predict_compatibility_logits(
                first, tuple(map(float, row))
            )
            actual = compatibility.predict_compatibility_logits(
                parsed, tuple(map(float, row))
            )
            for model_id in MODEL_IDS:
                self.assertAlmostEqual(expected[model_id], actual[model_id], places=7)

    def test_compatibility_fit_cannot_receive_binomial_predictions(self) -> None:
        parameters = inspect.signature(e5_fit.fit_compatibility_model).parameters

        self.assertEqual(
            {
                "embeddings",
                "quality",
                "generation_counts",
                "train_input_sha256",
                "train_outcome_sha256",
                "seed",
                "steps",
                "device",
            },
            set(parameters),
        )
        self.assertFalse(any("binomial" in name for name in parameters))

    def test_optimizer_regularizes_factors_but_not_bias(self) -> None:
        import torch

        module = e5_fit._build_bilinear_module(
            compatibility.EMBEDDING_DIMENSION,
            len(MODEL_IDS),
            seed=e5_fit.FULL_FIT_SEED,
        )

        groups = e5_fit._optimizer_groups(module)

        self.assertEqual(
            (compatibility.LATENT_RANK, compatibility.EMBEDDING_DIMENSION),
            tuple(module.query.weight.shape),
        )
        self.assertEqual(
            (len(MODEL_IDS), compatibility.LATENT_RANK),
            tuple(module.model_vectors.shape),
        )
        self.assertEqual(e5_fit.WEIGHT_DECAY, groups[0]["weight_decay"])
        self.assertEqual(0.0, groups[1]["weight_decay"])
        self.assertEqual(
            {id(module.bias)}, {id(value) for value in groups[1]["params"]}
        )
        self.assertEqual(
            {id(module.query.weight), id(module.model_vectors)},
            {id(value) for value in groups[0]["params"]},
        )
        self.assertTrue(
            all(
                isinstance(value, torch.Tensor)
                for group in groups
                for value in group["params"]
            )
        )

    def test_public_artifact_contains_no_row_level_state(self) -> None:
        embeddings = _unit_embeddings(6)
        quality = np.full((6, len(MODEL_IDS)), 0.5, dtype=np.float64)
        counts = np.full_like(quality, 2.0)
        model = e5_fit.fit_compatibility_model(
            embeddings,
            quality,
            counts,
            train_input_sha256="3" * 64,
            train_outcome_sha256="4" * 64,
            seed=e5_fit.FULL_FIT_SEED,
            steps=2,
            device="cpu",
        )

        serialized = publication.canonical_artifact_bytes(
            publication.compatibility_model_to_artifact(model)
        ).decode("utf-8")

        for forbidden in (
            "episode_id",
            "prompt",
            "content_sha256",
            "embedding_rows",
            "outcomes",
            "predictions",
            "dev_score",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_evaluate_hashes_dev_actions_before_loading_dev_outcomes(self) -> None:
        source = inspect.getsource(e5_evaluation._evaluate_command)

        freeze_position = source.index('"dev_candidate": _action_sha256')
        outcome_load_position = source.index(
            "dev_outcomes = load_outcomes(args.dev_outcomes)"
        )
        self.assertLess(freeze_position, outcome_load_position)


if __name__ == "__main__":
    unittest.main()
