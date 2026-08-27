# SPDX-FileCopyrightText: Copyright 2026 SK TELECOM CO., LTD.
# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Predict monotonic per-model costs from prompt features."""

from __future__ import annotations

import math
from typing import Mapping, Sequence

from .protocol import MODEL_IDS, Episode
from .routing_artifacts import HashRegexArtifact, LinearHead
from .routing_features import raw_feature_vector, standardize_feature_vector


def _linear(head: LinearHead, values: Sequence[float]) -> float:
    return head.intercept + math.fsum(
        coefficient * value
        for coefficient, value in zip(head.coefficients, values)
    )


def standardized_features(
    episode: Episode,
    artifact: HashRegexArtifact,
) -> tuple[float, ...]:
    raw = raw_feature_vector(episode, artifact.hash_bins)
    return standardize_feature_vector(
        raw,
        artifact.feature_mean,
        artifact.feature_scale,
    )


def predict_costs_from_features(
    features: Sequence[float],
    artifact: HashRegexArtifact,
) -> Mapping[str, float]:
    """Predict monotonic costs from an existing standardized vector."""

    predicted = {
        model_id: math.exp(
            min(
                50.0,
                max(
                    -50.0,
                    _linear(artifact.log_cost_heads[model_id], features),
                ),
            )
        )
        for model_id in MODEL_IDS
    }
    light = predicted[MODEL_IDS[0]]
    predicted[MODEL_IDS[1]] = max(
        predicted[MODEL_IDS[1]],
        light * (1.0 + 1e-12),
    )
    predicted[MODEL_IDS[2]] = max(
        predicted[MODEL_IDS[2]],
        predicted[MODEL_IDS[1]] * (1.0 + 1e-12),
    )
    return predicted


def predict_costs(
    episode: Episode,
    artifact: HashRegexArtifact,
) -> Mapping[str, float]:
    """Return positive costs ordered monotonically by protocol model."""

    return predict_costs_from_features(
        standardized_features(episode, artifact),
        artifact,
    )
