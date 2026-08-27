# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import math
import unittest

from ossp_router.training import binomial_quality as quality

NUMPY_AVAILABLE = importlib.util.find_spec("numpy") is not None


class BinomialLogisticQualityTest(unittest.TestCase):
    def test_prediction_uses_independent_model_heads(self) -> None:
        log_three = math.log(3.0)
        model = quality.BinomialLogisticQualityModel(
            feature_names=("signal",),
            feature_mean=(0.0,),
            feature_scale=(1.0,),
            model_ids=("model-a", "model-b"),
            heads=(
                quality.BinomialLogisticHead(0.0, (log_three,)),
                quality.BinomialLogisticHead(0.0, (-log_three,)),
            ),
        )

        prediction = quality.predict_model_qualities(model, (1.0,))

        self.assertAlmostEqual(0.75, prediction["model-a"], places=12)
        self.assertAlmostEqual(0.25, prediction["model-b"], places=12)

    def test_prediction_handles_extreme_logits_without_overflow(self) -> None:
        model = quality.BinomialLogisticQualityModel(
            feature_names=("signal",),
            feature_mean=(0.0,),
            feature_scale=(1.0,),
            model_ids=("positive", "negative"),
            heads=(
                quality.BinomialLogisticHead(1000.0, (0.0,)),
                quality.BinomialLogisticHead(-1000.0, (0.0,)),
            ),
        )

        prediction = quality.predict_model_qualities(model, (0.0,))

        self.assertEqual(1.0, prediction["positive"])
        self.assertEqual(0.0, prediction["negative"])

    @unittest.skipUnless(NUMPY_AVAILABLE, "NumPy is not installed")
    def test_prediction_accepts_numpy_feature_rows(self) -> None:
        import numpy as np

        model = quality.BinomialLogisticQualityModel(
            feature_names=("left", "right"),
            feature_mean=(0.0, 0.0),
            feature_scale=(1.0, 1.0),
            model_ids=("model-a",),
            heads=(quality.BinomialLogisticHead(0.0, (math.log(3.0), 0.0)),),
        )

        prediction = quality.predict_model_qualities(
            model, np.asarray((1.0, 0.0), dtype=np.float64)
        )

        self.assertAlmostEqual(0.75, prediction["model-a"], places=12)

    @unittest.skipUnless(NUMPY_AVAILABLE, "NumPy is not installed")
    def test_generation_counts_control_intercept_fit(self) -> None:
        model = quality.fit_binomial_logistic_quality(
            ((1.0,), (1.0,)),
            ((1.0,), (0.0,)),
            ((9,), (1,)),
            feature_names=("constant",),
            model_ids=("model-a",),
        )

        prediction = quality.predict_model_qualities(model, (1.0,))

        self.assertAlmostEqual(5.0 / 6.0, prediction["model-a"], places=10)

    @unittest.skipUnless(NUMPY_AVAILABLE, "NumPy is not installed")
    def test_fit_learns_regularized_opposite_feature_effects(self) -> None:
        model = quality.fit_binomial_logistic_quality(
            ((1.0,), (5.0,)),
            ((0.0, 1.0), (1.0, 0.0)),
            ((4, 4), (4, 4)),
            feature_names=("signal",),
            model_ids=("increasing", "decreasing"),
        )

        expected_effect = 0.03902451102005016
        self.assertEqual((3.0,), model.feature_mean)
        self.assertEqual((2.0,), model.feature_scale)
        self.assertAlmostEqual(0.0, model.heads[0].intercept, places=12)
        self.assertAlmostEqual(0.0, model.heads[1].intercept, places=12)
        self.assertAlmostEqual(
            expected_effect, model.heads[0].coefficients[0], places=12
        )
        self.assertAlmostEqual(
            -expected_effect, model.heads[1].coefficients[0], places=12
        )

    def test_artifact_round_trip_keeps_only_aggregate_state(self) -> None:
        model = quality.BinomialLogisticQualityModel(
            feature_names=("length", "numeric_density"),
            feature_mean=(10.0, 0.25),
            feature_scale=(2.0, 0.5),
            model_ids=("model-a",),
            heads=(quality.BinomialLogisticHead(0.5, (1.5, -2.0)),),
        )

        artifact = quality.model_to_artifact(model)

        self.assertEqual(
            {
                "artifact_type": "ossp-binomial-logistic-quality-v1",
                "schema_version": 1,
                "feature_names": ["length", "numeric_density"],
                "feature_mean": [10.0, 0.25],
                "feature_scale": [2.0, 0.5],
                "model_ids": ["model-a"],
                "heads": {
                    "model-a": {
                        "intercept": 0.5,
                        "coefficients": [1.5, -2.0],
                    }
                },
            },
            artifact,
        )
        self.assertEqual(model, quality.parse_artifact(artifact))

    def test_parser_rejects_undeclared_fields(self) -> None:
        model = quality.BinomialLogisticQualityModel(
            feature_names=("signal",),
            feature_mean=(0.0,),
            feature_scale=(1.0,),
            model_ids=("model-a",),
            heads=(quality.BinomialLogisticHead(0.0, (1.0,)),),
        )
        artifact = quality.model_to_artifact(model)
        artifact["undeclared"] = True

        with self.assertRaises(ValueError):
            quality.parse_artifact(artifact)

    def test_parser_rejects_non_integer_schema_version(self) -> None:
        model = quality.BinomialLogisticQualityModel(
            feature_names=("signal",),
            feature_mean=(0.0,),
            feature_scale=(1.0,),
            model_ids=("model-a",),
            heads=(quality.BinomialLogisticHead(0.0, (1.0,)),),
        )
        artifact = quality.model_to_artifact(model)
        artifact["schema_version"] = 1.0

        with self.assertRaises(ValueError):
            quality.parse_artifact(artifact)

    def test_parser_normalizes_numeric_overflow_to_value_error(self) -> None:
        model = quality.BinomialLogisticQualityModel(
            feature_names=("signal",),
            feature_mean=(0.0,),
            feature_scale=(1.0,),
            model_ids=("model-a",),
            heads=(quality.BinomialLogisticHead(0.0, (1.0,)),),
        )
        artifact = quality.model_to_artifact(model)
        artifact["heads"]["model-a"]["intercept"] = 10**10_000

        with self.assertRaises(ValueError):
            quality.parse_artifact(artifact)

    def test_predictor_rejects_wrong_feature_dimension(self) -> None:
        model = quality.BinomialLogisticQualityModel(
            feature_names=("signal",),
            feature_mean=(0.0,),
            feature_scale=(1.0,),
            model_ids=("model-a",),
            heads=(quality.BinomialLogisticHead(0.0, (1.0,)),),
        )

        with self.assertRaises(ValueError):
            quality.predict_model_qualities(model, (1.0, 2.0))

    def test_predictor_rejects_standardization_overflow(self) -> None:
        model = quality.BinomialLogisticQualityModel(
            feature_names=("signal",),
            feature_mean=(-1.0e308,),
            feature_scale=(1.0,),
            model_ids=("model-a",),
            heads=(quality.BinomialLogisticHead(0.0, (0.0,)),),
        )

        with self.assertRaises(ValueError):
            quality.predict_model_qualities(model, (1.0e308,))

    def test_predictor_rejects_logit_overflow(self) -> None:
        model = quality.BinomialLogisticQualityModel(
            feature_names=("signal",),
            feature_mean=(0.0,),
            feature_scale=(1.0,),
            model_ids=("model-a",),
            heads=(quality.BinomialLogisticHead(0.0, (1.0e308,)),),
        )

        with self.assertRaises(ValueError):
            quality.predict_model_qualities(model, (1.0e308,))

    @unittest.skipUnless(NUMPY_AVAILABLE, "NumPy is not installed")
    def test_fit_rejects_quality_outside_unit_interval(self) -> None:
        with self.assertRaises(ValueError):
            quality.fit_binomial_logistic_quality(
                ((1.0,),),
                ((1.01,),),
                ((1,),),
                feature_names=("signal",),
                model_ids=("model-a",),
            )

    @unittest.skipUnless(NUMPY_AVAILABLE, "NumPy is not installed")
    def test_fit_rejects_non_integer_generation_counts(self) -> None:
        with self.assertRaises(ValueError):
            quality.fit_binomial_logistic_quality(
                ((1.0,),),
                ((0.5,),),
                ((1.5,),),
                feature_names=("signal",),
                model_ids=("model-a",),
            )

    @unittest.skipUnless(NUMPY_AVAILABLE, "NumPy is not installed")
    def test_fit_normalizes_numeric_overflow_to_value_error(self) -> None:
        with self.assertRaises(ValueError):
            quality.fit_binomial_logistic_quality(
                ((10**10_000,),),
                ((0.5,),),
                ((1,),),
                feature_names=("signal",),
                model_ids=("model-a",),
            )


if __name__ == "__main__":
    unittest.main()
