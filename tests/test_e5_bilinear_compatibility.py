# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import copy
import json
import math
import pathlib
import tempfile
import unittest

from ossp_router import e5_artifact as compatibility
from ossp_router.protocol import MODEL_IDS


def _model() -> compatibility.E5BilinearCompatibilityModel:
    first_projection = [0.0] * compatibility.EMBEDDING_DIMENSION
    second_projection = [0.0] * compatibility.EMBEDDING_DIMENSION
    first_projection[0] = 1.0
    second_projection[1] = 1.0
    return compatibility.E5BilinearCompatibilityModel(
        model_ids=tuple(MODEL_IDS),
        encoder=compatibility.E5EncoderIdentity(
            model_id=compatibility.PINNED_MODEL_ID,
            revision=compatibility.PINNED_REVISION,
            onnx_sha256="a" * 64,
            tokenizer_sha256="b" * 64,
            preprocessing_id=compatibility.PREPROCESSING_ID,
        ),
        embedding_mean=(0.0,) * compatibility.EMBEDDING_DIMENSION,
        projection=(tuple(first_projection), tuple(second_projection)),
        heads=(
            compatibility.E5CompatibilityHead(vector=(2.0, -1.0), bias=0.5),
            compatibility.E5CompatibilityHead(vector=(0.0, 0.0), bias=-0.25),
            compatibility.E5CompatibilityHead(vector=(1.0, 1.0), bias=0.0),
        ),
        compatibility_weight=compatibility.RETAINED_BLEND_WEIGHT,
        training=compatibility.E5TrainingMetadata(
            train_input_sha256="c" * 64,
            train_outcome_sha256="d" * 64,
            seed=20260827,
            rank=compatibility.LATENT_RANK,
            steps=1200,
            learning_rate=0.03,
            weight_decay=0.05,
            jeffreys_pseudocount=0.5,
        ),
    )


class E5BilinearCompatibilityTest(unittest.TestCase):
    def test_projection_and_model_vectors_produce_literal_logits(self) -> None:
        embedding = [0.0] * compatibility.EMBEDDING_DIMENSION
        embedding[0] = 1.0
        embedding[1] = 2.0

        logits = compatibility.predict_compatibility_logits(_model(), embedding)

        self.assertAlmostEqual(0.5, logits[MODEL_IDS[0]], places=12)
        self.assertAlmostEqual(-0.25, logits[MODEL_IDS[1]], places=12)
        self.assertAlmostEqual(3.0, logits[MODEL_IDS[2]], places=12)

    def test_equal_logit_blend_has_literal_midpoint(self) -> None:
        log_four = math.log(4.0)
        binomial = {model_id: 0.8 for model_id in MODEL_IDS}
        compatibility_logits = {model_id: -log_four for model_id in MODEL_IDS}

        blended = compatibility.blend_quality_logits(
            binomial,
            compatibility_logits,
            compatibility_weight=0.5,
        )

        for model_id in MODEL_IDS:
            self.assertAlmostEqual(0.5, blended[model_id], places=12)

    def test_artifact_round_trip_preserves_only_aggregate_state(self) -> None:
        model = _model()

        artifact = compatibility.model_to_artifact(model)

        self.assertEqual(
            {
                "artifact_type",
                "schema_version",
                "model_ids",
                "encoder",
                "embedding_mean",
                "projection",
                "heads",
                "compatibility_weight",
                "training",
            },
            set(artifact),
        )
        serialized = json.dumps(artifact, sort_keys=True)
        for forbidden in (
            "prompt",
            "episode_id",
            "embedding_rows",
            "outcomes",
            "predictions",
            "dev_score",
            "/home/",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(model, compatibility.parse_compatibility_artifact(artifact))

        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "artifact.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            self.assertEqual(model, compatibility.load_compatibility_artifact(path))

    def test_parser_rejects_unknown_fields_wrong_dimensions_and_nonfinite_values(
        self,
    ) -> None:
        artifact = compatibility.model_to_artifact(_model())
        unknown = copy.deepcopy(artifact)
        unknown["undeclared"] = True
        wrong_mean = copy.deepcopy(artifact)
        wrong_mean["embedding_mean"] = wrong_mean["embedding_mean"][:-1]
        wrong_projection = copy.deepcopy(artifact)
        wrong_projection["projection"] = wrong_projection["projection"][:1]
        nonfinite = copy.deepcopy(artifact)
        nonfinite["heads"][MODEL_IDS[0]]["bias"] = float("nan")

        for invalid in (unknown, wrong_mean, wrong_projection, nonfinite):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    compatibility.parse_compatibility_artifact(invalid)

    def test_parser_rejects_wrong_encoder_identity_models_and_blend(self) -> None:
        artifact = compatibility.model_to_artifact(_model())
        wrong_encoder = copy.deepcopy(artifact)
        wrong_encoder["encoder"]["revision"] = "e" * 40
        wrong_models = copy.deepcopy(artifact)
        wrong_models["model_ids"] = list(reversed(MODEL_IDS))
        wrong_blend = copy.deepcopy(artifact)
        wrong_blend["compatibility_weight"] = 0.25

        for invalid in (wrong_encoder, wrong_models, wrong_blend):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    compatibility.parse_compatibility_artifact(invalid)

    def test_blend_is_mapping_order_invariant_and_handles_probability_endpoints(
        self,
    ) -> None:
        forward = {
            model_id: value for model_id, value in zip(MODEL_IDS, (0.0, 0.5, 1.0))
        }
        reverse = dict(reversed(tuple(forward.items())))
        logits = {model_id: 0.0 for model_id in reversed(MODEL_IDS)}

        first = compatibility.blend_quality_logits(
            forward,
            logits,
            compatibility_weight=compatibility.RETAINED_BLEND_WEIGHT,
        )
        second = compatibility.blend_quality_logits(
            reverse,
            logits,
            compatibility_weight=compatibility.RETAINED_BLEND_WEIGHT,
        )

        self.assertEqual(first, second)
        self.assertEqual(tuple(MODEL_IDS), tuple(first))
        self.assertTrue(all(0.0 < value < 1.0 for value in first.values()))

    def test_prediction_rejects_wrong_embedding_dimension_and_overflow(self) -> None:
        model = _model()

        with self.assertRaises(ValueError):
            compatibility.predict_compatibility_logits(model, (0.0,))
        overflow = [0.0] * compatibility.EMBEDDING_DIMENSION
        overflow[0] = 1.0e308
        with self.assertRaises(ValueError):
            compatibility.predict_compatibility_logits(model, overflow)


if __name__ == "__main__":
    unittest.main()
