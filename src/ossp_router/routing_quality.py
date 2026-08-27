# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Predict and blend prompt/model quality signals for inference."""

from __future__ import annotations

import math
from typing import Mapping, Sequence

from .e5_artifact import (
    blend_quality_logits,
    predict_compatibility_logits,
)
from .protocol import MODEL_IDS, Episode
from .routing_artifacts import BinomialLogisticQualityModel, HashRegexArtifact
from .routing_features import raw_feature_vector, standardize_feature_vector


def _finite_vector(
    value: Sequence[float],
    *,
    expected_length: int,
    label: str,
) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be a sequence")
    try:
        result = tuple(float(item) for item in value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{label} must contain finite numbers") from error
    if len(result) != expected_length or any(
        not math.isfinite(item) for item in result
    ):
        raise ValueError(
            f"{label} must contain {expected_length} finite numbers"
        )
    return result


def _sigmoid(logit: float) -> float:
    if logit >= 0.0:
        return 1.0 / (1.0 + math.exp(-logit))
    exponential = math.exp(logit)
    return exponential / (1.0 + exponential)


def predict_binomial_quality(
    model: BinomialLogisticQualityModel,
    features: Sequence[float],
) -> Mapping[str, float]:
    """Predict one probability per protocol model from raw features."""

    raw = _finite_vector(
        features,
        expected_length=len(model.feature_names),
        label="features",
    )
    standardized = tuple(
        (value - mean) / scale
        for value, mean, scale in zip(
            raw,
            model.feature_mean,
            model.feature_scale,
        )
    )
    if any(not math.isfinite(item) for item in standardized):
        raise ValueError("standardized features must remain finite")
    prediction = {}
    for model_id, head in zip(model.model_ids, model.heads):
        terms = tuple(
            coefficient * feature
            for coefficient, feature in zip(head.coefficients, standardized)
        )
        if any(not math.isfinite(item) for item in terms):
            raise ValueError(f"quality logit for {model_id!r} must remain finite")
        try:
            logit = head.intercept + math.fsum(terms)
        except (OverflowError, ValueError) as error:
            raise ValueError(
                f"quality logit for {model_id!r} must remain finite"
            ) from error
        if not math.isfinite(logit):
            raise ValueError(f"quality logit for {model_id!r} must remain finite")
        prediction[model_id] = _sigmoid(logit)
    return prediction


def predict_hash_quality_from_features(
    features: Sequence[float],
    artifact: HashRegexArtifact,
) -> Mapping[str, float]:
    """Predict bounded quality from an existing standardized vector."""

    return {
        model_id: min(
            1.0,
            max(
                0.0,
                artifact.score_heads[model_id].intercept
                + math.fsum(
                    coefficient * value
                    for coefficient, value in zip(
                        artifact.score_heads[model_id].coefficients,
                        features,
                    )
                ),
            ),
        )
        for model_id in MODEL_IDS
    }


def predict_hash_quality(
    episode: Episode,
    artifact: HashRegexArtifact,
) -> Mapping[str, float]:
    """Predict bounded per-model quality from the hash feature heads."""

    raw = raw_feature_vector(episode, artifact.hash_bins)
    return predict_hash_quality_from_features(
        standardize_feature_vector(
            raw,
            artifact.feature_mean,
            artifact.feature_scale,
        ),
        artifact,
    )


__all__ = (
    "blend_quality_logits",
    "predict_binomial_quality",
    "predict_compatibility_logits",
    "predict_hash_quality",
    "predict_hash_quality_from_features",
)
