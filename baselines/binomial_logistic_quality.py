# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Fit and run independent binomial logistic quality heads."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Any, Dict, Mapping, Sequence, Tuple


ARTIFACT_TYPE = "ossp-binomial-logistic-quality-v1"
SCHEMA_VERSION = 1
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


def _vector(
    value: Sequence[float],
    label: str,
    *,
    expected_length: int | None = None,
) -> Tuple[float, ...]:
    if isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    try:
        result = tuple(
            _number(item, f"{label}[{index}]") for index, item in enumerate(value)
        )
    except TypeError as error:
        raise ValueError(f"{label} must be a sequence") from error
    if expected_length is not None and len(result) != expected_length:
        raise ValueError(f"{label} must contain {expected_length} values")
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


@dataclass(frozen=True)
class BinomialLogisticHead:
    """One model's intercept and standardized-feature coefficients."""

    intercept: float
    coefficients: Tuple[float, ...]

    def __post_init__(self) -> None:
        intercept = _number(self.intercept, "head.intercept")
        coefficients = _vector(self.coefficients, "head.coefficients")
        if not coefficients:
            raise ValueError("head.coefficients must not be empty")
        object.__setattr__(self, "intercept", intercept)
        object.__setattr__(self, "coefficients", coefficients)


@dataclass(frozen=True)
class BinomialLogisticQualityModel:
    """Aggregate normalization state and one quality head per model."""

    feature_names: Tuple[str, ...]
    feature_mean: Tuple[float, ...]
    feature_scale: Tuple[float, ...]
    model_ids: Tuple[str, ...]
    heads: Tuple[BinomialLogisticHead, ...]

    def __post_init__(self) -> None:
        feature_names = _names(self.feature_names, "model.feature_names")
        feature_mean = _vector(
            self.feature_mean,
            "model.feature_mean",
            expected_length=len(feature_names),
        )
        feature_scale = _vector(
            self.feature_scale,
            "model.feature_scale",
            expected_length=len(feature_names),
        )
        if any(value <= 0.0 for value in feature_scale):
            raise ValueError("model.feature_scale values must be positive")
        model_ids = _names(self.model_ids, "model.model_ids")
        if isinstance(self.heads, (str, bytes)) or not isinstance(self.heads, Sequence):
            raise ValueError("model.heads must be a sequence")
        heads = tuple(self.heads)
        if len(heads) != len(model_ids):
            raise ValueError("model.heads must match model.model_ids")
        for index, head in enumerate(heads):
            if not isinstance(head, BinomialLogisticHead):
                raise ValueError(f"model.heads[{index}] must be a BinomialLogisticHead")
            if len(head.coefficients) != len(feature_names):
                raise ValueError(
                    f"model.heads[{index}].coefficients must match feature_names"
                )
        object.__setattr__(self, "feature_names", feature_names)
        object.__setattr__(self, "feature_mean", feature_mean)
        object.__setattr__(self, "feature_scale", feature_scale)
        object.__setattr__(self, "model_ids", model_ids)
        object.__setattr__(self, "heads", heads)


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: Sequence[str], label: str) -> None:
    missing = sorted(set(expected) - set(value))
    extra = sorted(set(value) - set(expected))
    if missing or extra:
        raise ValueError(f"{label} fields differ: missing={missing}, extra={extra}")


def _artifact_vector(value: Any, length: int, label: str) -> Tuple[float, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return _vector(value, label, expected_length=length)


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


def parse_artifact(value: Any) -> BinomialLogisticQualityModel:
    """Parse a strict JSON-compatible aggregate artifact."""

    root = _object(value, "artifact")
    _exact_keys(
        root,
        (
            "artifact_type",
            "schema_version",
            "feature_names",
            "feature_mean",
            "feature_scale",
            "model_ids",
            "heads",
        ),
        "artifact",
    )
    if root["artifact_type"] != ARTIFACT_TYPE:
        raise ValueError("unsupported artifact_type")
    if (
        isinstance(root["schema_version"], bool)
        or not isinstance(root["schema_version"], int)
        or root["schema_version"] != SCHEMA_VERSION
    ):
        raise ValueError("unsupported schema_version")
    if not isinstance(root["feature_names"], list):
        raise ValueError("artifact.feature_names must be an array")
    if not isinstance(root["model_ids"], list):
        raise ValueError("artifact.model_ids must be an array")
    feature_names = _names(root["feature_names"], "artifact.feature_names")
    model_ids = _names(root["model_ids"], "artifact.model_ids")
    feature_mean = _artifact_vector(
        root["feature_mean"], len(feature_names), "artifact.feature_mean"
    )
    feature_scale = _artifact_vector(
        root["feature_scale"], len(feature_names), "artifact.feature_scale"
    )
    raw_heads = _object(root["heads"], "artifact.heads")
    if set(raw_heads) != set(model_ids):
        raise ValueError("artifact.heads must match artifact.model_ids")
    heads = []
    for model_id in model_ids:
        raw_head = _object(raw_heads[model_id], f"artifact.heads[{model_id!r}]")
        _exact_keys(
            raw_head,
            ("intercept", "coefficients"),
            f"artifact.heads[{model_id!r}]",
        )
        heads.append(
            BinomialLogisticHead(
                intercept=_number(
                    raw_head["intercept"],
                    f"artifact.heads[{model_id!r}].intercept",
                ),
                coefficients=_artifact_vector(
                    raw_head["coefficients"],
                    len(feature_names),
                    f"artifact.heads[{model_id!r}].coefficients",
                ),
            )
        )
    return BinomialLogisticQualityModel(
        feature_names=feature_names,
        feature_mean=feature_mean,
        feature_scale=feature_scale,
        model_ids=model_ids,
        heads=tuple(heads),
    )


def _sigmoid(logit: float) -> float:
    if logit >= 0.0:
        return 1.0 / (1.0 + math.exp(-logit))
    exponential = math.exp(logit)
    return exponential / (1.0 + exponential)


def predict_model_qualities(
    model: BinomialLogisticQualityModel,
    features: Sequence[float],
) -> Mapping[str, float]:
    """Predict each model's quality from one raw feature vector."""

    raw = _vector(
        features,
        "features",
        expected_length=len(model.feature_names),
    )
    standardized = tuple(
        (value - mean) / scale
        for value, mean, scale in zip(raw, model.feature_mean, model.feature_scale)
    )
    if any(not math.isfinite(value) for value in standardized):
        raise ValueError("standardized features must remain finite")
    prediction = {}
    for model_id, head in zip(model.model_ids, model.heads):
        terms = tuple(
            coefficient * feature
            for coefficient, feature in zip(head.coefficients, standardized)
        )
        if any(not math.isfinite(value) for value in terms):
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
