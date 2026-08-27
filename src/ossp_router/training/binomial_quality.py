# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Fit and run independent binomial logistic quality heads offline."""

from __future__ import annotations

import math
from numbers import Real
from typing import Any, Dict, Mapping, Sequence, Tuple

from ossp_router.routing_artifacts import (
    BINOMIAL_ARTIFACT_TYPE as ARTIFACT_TYPE,
    BINOMIAL_SCHEMA_VERSION as SCHEMA_VERSION,
    BinomialLogisticHead,
    BinomialLogisticQualityModel,
    parse_binomial_artifact,
)
from ossp_router.routing_quality import predict_binomial_quality


parse_artifact = parse_binomial_artifact

DEFAULT_INVERSE_REGULARIZATION = 0.01
DEFAULT_MAX_ITERATIONS = 2_000
DEFAULT_TOLERANCE = 1.0e-10
JEFFREYS_PSEUDOCOUNT = 0.5


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{label} must be a finite number") from error
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def _names(value: Sequence[str], label: str) -> Tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be a sequence")
    result = tuple(value)
    if not result or any(not isinstance(item, str) or not item for item in result):
        raise ValueError(f"{label} must contain non-empty strings")
    if len(set(result)) != len(result):
        raise ValueError(f"{label} must not contain duplicates")
    return result


def model_to_artifact(model: BinomialLogisticQualityModel) -> Dict[str, Any]:
    """Convert a validated model to a JSON-compatible aggregate artifact."""

    return {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "feature_names": list(model.feature_names),
        "feature_mean": list(model.feature_mean),
        "feature_scale": list(model.feature_scale),
        "model_ids": list(model.model_ids),
        "heads": {
            model_id: {
                "intercept": head.intercept,
                "coefficients": list(head.coefficients),
            }
            for model_id, head in zip(model.model_ids, model.heads)
        },
    }


def predict_model_qualities(
    model: BinomialLogisticQualityModel,
    features: Sequence[float],
) -> Mapping[str, float]:
    """Predict with the canonical runtime implementation."""

    try:
        values = tuple(features)
    except TypeError as error:
        raise ValueError("features must be a sequence") from error
    return predict_binomial_quality(model, values)


def _require_numpy() -> Any:
    try:
        import numpy as np
    except ImportError as error:  # pragma: no cover - environment-specific path
        raise RuntimeError(
            "training requires NumPy from the repository train dependency group"
        ) from error
    return np


def _objective(
    np: Any,
    design: Any,
    successes: Any,
    trials: Any,
    parameters: Any,
    l2_strength: float,
) -> float:
    logits = design @ parameters
    likelihood = np.sum(trials * np.logaddexp(0.0, logits) - successes * logits)
    penalty = 0.5 * l2_strength * np.dot(parameters[1:], parameters[1:])
    return float(likelihood + penalty)


def _fit_head(
    np: Any,
    standardized: Any,
    successes: Any,
    failures: Any,
    *,
    inverse_regularization: float,
    max_iterations: int,
    tolerance: float,
) -> BinomialLogisticHead:
    rows = standardized.shape[0]
    design = np.column_stack((np.ones(rows, dtype=np.float64), standardized))
    trials = successes + failures
    success_rate = float(np.sum(successes) / np.sum(trials))
    parameters = np.zeros(design.shape[1], dtype=np.float64)
    parameters[0] = math.log(success_rate / (1.0 - success_rate))
    l2_strength = 1.0 / inverse_regularization
    gradient_tolerance = tolerance * max(1.0, float(np.sum(trials)))

    for _iteration in range(max_iterations):
        logits = design @ parameters
        probabilities = np.exp(-np.logaddexp(0.0, -logits))
        gradient = design.T @ (trials * probabilities - successes)
        gradient[1:] += l2_strength * parameters[1:]
        if float(np.max(np.abs(gradient))) <= gradient_tolerance:
            return BinomialLogisticHead(
                intercept=float(parameters[0]),
                coefficients=tuple(float(value) for value in parameters[1:]),
            )

        curvature = trials * probabilities * (1.0 - probabilities)
        hessian = design.T @ (design * curvature[:, None])
        hessian[1:, 1:] += l2_strength * np.eye(standardized.shape[1], dtype=np.float64)
        try:
            step = np.linalg.solve(hessian, gradient)
        except np.linalg.LinAlgError as error:
            raise RuntimeError("binomial logistic Hessian is singular") from error

        current_objective = _objective(
            np, design, successes, trials, parameters, l2_strength
        )
        step_scale = 1.0
        candidate = parameters
        candidate_objective = current_objective
        for _backtrack in range(60):
            proposed = parameters - step_scale * step
            proposed_objective = _objective(
                np, design, successes, trials, proposed, l2_strength
            )
            if proposed_objective <= current_objective:
                candidate = proposed
                candidate_objective = proposed_objective
                break
            step_scale *= 0.5
        else:
            raise RuntimeError("binomial logistic line search did not converge")

        parameter_change = float(np.max(np.abs(candidate - parameters)))
        objective_change = abs(current_objective - candidate_objective)
        parameters = candidate
        if parameter_change <= tolerance * (
            1.0 + float(np.max(np.abs(parameters)))
        ) or objective_change <= tolerance * (1.0 + abs(current_objective)):
            return BinomialLogisticHead(
                intercept=float(parameters[0]),
                coefficients=tuple(float(value) for value in parameters[1:]),
            )

    raise RuntimeError("binomial logistic training did not converge")


def fit_binomial_logistic_quality(
    features: Sequence[Sequence[float]],
    quality: Sequence[Sequence[float]],
    generation_counts: Sequence[Sequence[float]],
    *,
    feature_names: Sequence[str],
    model_ids: Sequence[str],
    inverse_regularization: float = DEFAULT_INVERSE_REGULARIZATION,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    tolerance: float = DEFAULT_TOLERANCE,
) -> BinomialLogisticQualityModel:
    """Fit one deterministic binomial logistic head per model."""

    names = _names(feature_names, "feature_names")
    models = _names(model_ids, "model_ids")
    inverse_regularization = _number(inverse_regularization, "inverse_regularization")
    if inverse_regularization <= 0.0:
        raise ValueError("inverse_regularization must be positive")
    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, int)
        or max_iterations <= 0
    ):
        raise ValueError("max_iterations must be a positive integer")
    tolerance = _number(tolerance, "tolerance")
    if tolerance <= 0.0:
        raise ValueError("tolerance must be positive")

    np = _require_numpy()
    try:
        matrix = np.asarray(features, dtype=np.float64)
        observed = np.asarray(quality, dtype=np.float64)
        generations = np.asarray(generation_counts, dtype=np.float64)
    except (OverflowError, TypeError, ValueError) as error:
        raise ValueError("training values must form numeric matrices") from error

    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError("features must be a non-empty two-dimensional matrix")
    if matrix.shape[1] != len(names):
        raise ValueError("features columns must match feature_names")
    expected_targets = (matrix.shape[0], len(models))
    if observed.shape != expected_targets:
        raise ValueError("quality shape must match rows and model_ids")
    if generations.shape != expected_targets:
        raise ValueError("generation_counts shape must match rows and model_ids")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("features must contain only finite values")
    if (
        not np.all(np.isfinite(observed))
        or np.any(observed < 0.0)
        or np.any(observed > 1.0)
    ):
        raise ValueError("quality values must be finite and between zero and one")
    if (
        not np.all(np.isfinite(generations))
        or np.any(generations < 1.0)
        or not np.all(generations == np.rint(generations))
    ):
        raise ValueError("generation_counts must contain positive integers")

    mean = matrix.mean(axis=0)
    scale = matrix.std(axis=0)
    if not np.all(np.isfinite(mean)) or not np.all(np.isfinite(scale)):
        raise ValueError("feature normalization must remain finite")
    scale = np.where(scale > 1.0e-12, scale, 1.0)
    standardized = (matrix - mean) / scale

    rounded_successes = np.rint(observed * generations)
    heads = []
    for model_index in range(len(models)):
        successes = rounded_successes[:, model_index] + JEFFREYS_PSEUDOCOUNT
        failures = (
            generations[:, model_index]
            - rounded_successes[:, model_index]
            + JEFFREYS_PSEUDOCOUNT
        )
        heads.append(
            _fit_head(
                np,
                standardized,
                successes,
                failures,
                inverse_regularization=inverse_regularization,
                max_iterations=max_iterations,
                tolerance=tolerance,
            )
        )

    return BinomialLogisticQualityModel(
        feature_names=names,
        feature_mean=tuple(float(value) for value in mean),
        feature_scale=tuple(float(value) for value in scale),
        model_ids=models,
        heads=tuple(heads),
    )
