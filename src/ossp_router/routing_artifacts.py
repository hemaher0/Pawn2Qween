# SPDX-FileCopyrightText: Copyright 2026 SK TELECOM CO., LTD.
# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Strict aggregate artifact types and boundary loaders for routing."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from numbers import Real
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, Tuple

from .e5_artifact import (
    E5BilinearCompatibilityModel,
    load_compatibility_artifact,
)
from .protocol import MODEL_IDS, TIERS, ProtocolError, load_json
from .routing_features import (
    DENSE_FEATURE_NAMES,
    MAX_HASH_BINS,
    MIN_HASH_BINS,
)


HASH_ARTIFACT_TYPE = "ossp-hash-regex-linear-v1"
HASH_FEATURE_VERSION = 1
BINOMIAL_ARTIFACT_TYPE = "ossp-binomial-logistic-quality-v1"
BINOMIAL_SCHEMA_VERSION = 1


class ContentEncoder(Protocol):
    @property
    def identity(self) -> object:
        ...

    def encode_texts(
        self,
        texts: Sequence[str],
    ) -> Tuple[Tuple[float, ...], ...]:
        ...


@dataclass(frozen=True)
class LinearHead:
    intercept: float
    coefficients: Tuple[float, ...]


@dataclass(frozen=True)
class HashRegexArtifact:
    hash_bins: int
    feature_mean: Tuple[float, ...]
    feature_scale: Tuple[float, ...]
    score_heads: Mapping[str, LinearHead]
    log_cost_heads: Mapping[str, LinearHead]
    tier_safety_ratios: Mapping[str, float]
    policy_id: str
    policy_digest: str
    training_summary: Mapping[str, Any]


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError(f"{label} must be a JSON object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: Sequence[str], label: str) -> None:
    missing = sorted(set(expected) - set(value))
    extra = sorted(set(value) - set(expected))
    if missing or extra:
        raise ProtocolError(f"{label} fields differ: missing={missing}, extra={extra}")


def _integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise ProtocolError(f"{label} is outside the allowed range")
    return value


def _protocol_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ProtocolError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ProtocolError(f"{label} must be a finite number")
    return result


def _protocol_vector(value: Any, length: int, label: str) -> Tuple[float, ...]:
    if not isinstance(value, list) or len(value) != length:
        raise ProtocolError(f"{label} must be an array of length {length}")
    return tuple(
        _protocol_number(item, f"{label}[{index}]")
        for index, item in enumerate(value)
    )


def _linear_head(value: Any, length: int, label: str) -> LinearHead:
    raw = _object(value, label)
    _exact_keys(raw, ("intercept", "coefficients"), label)
    return LinearHead(
        intercept=_protocol_number(raw["intercept"], f"{label}.intercept"),
        coefficients=_protocol_vector(
            raw["coefficients"],
            length,
            f"{label}.coefficients",
        ),
    )


def parse_hash_artifact(value: Any) -> HashRegexArtifact:
    root = _object(value, "artifact")
    _exact_keys(
        root,
        (
            "artifact_type",
            "schema_version",
            "feature_version",
            "hash_algorithm",
            "hash_bins",
            "dense_feature_names",
            "model_ids",
            "policy_id",
            "policy_sha256",
            "feature_mean",
            "feature_scale",
            "score_heads",
            "log_cost_heads",
            "tier_safety_ratios",
            "training_summary",
        ),
        "artifact",
    )
    if root["artifact_type"] != HASH_ARTIFACT_TYPE:
        raise ProtocolError("unsupported hash artifact type")
    if (
        _integer(root["schema_version"], "artifact.schema_version", 1, 1) != 1
        or _integer(
            root["feature_version"],
            "artifact.feature_version",
            HASH_FEATURE_VERSION,
            HASH_FEATURE_VERSION,
        )
        != HASH_FEATURE_VERSION
    ):
        raise ProtocolError("unsupported hash artifact version")
    if root["hash_algorithm"] != "fnv1a64-signed-word-1-2":
        raise ProtocolError("unsupported feature hash algorithm")
    hash_bins = _integer(
        root["hash_bins"],
        "artifact.hash_bins",
        MIN_HASH_BINS,
        MAX_HASH_BINS,
    )
    if hash_bins & (hash_bins - 1):
        raise ProtocolError("artifact.hash_bins must be a power of two")
    if root["dense_feature_names"] != list(DENSE_FEATURE_NAMES):
        raise ProtocolError("dense feature definition differs from the runtime")
    if root["model_ids"] != list(MODEL_IDS):
        raise ProtocolError("artifact.model_ids differs from the policy")
    length = len(DENSE_FEATURE_NAMES) + hash_bins
    mean = _protocol_vector(root["feature_mean"], length, "artifact.feature_mean")
    scale = _protocol_vector(root["feature_scale"], length, "artifact.feature_scale")
    if any(item <= 0 for item in scale):
        raise ProtocolError("artifact.feature_scale values must be positive")
    score_raw = _object(root["score_heads"], "artifact.score_heads")
    cost_raw = _object(root["log_cost_heads"], "artifact.log_cost_heads")
    if set(score_raw) != set(MODEL_IDS) or set(cost_raw) != set(MODEL_IDS):
        raise ProtocolError("artifact linear heads have the wrong model set")
    safety_raw = _object(root["tier_safety_ratios"], "artifact.tier_safety_ratios")
    if set(safety_raw) != set(TIERS):
        raise ProtocolError("artifact tier safety ratios are incomplete")
    safety = {
        tier: _protocol_number(
            safety_raw[tier],
            f"artifact.tier_safety_ratios.{tier}",
        )
        for tier in TIERS
    }
    if any(not 0 < item <= 1 for item in safety.values()):
        raise ProtocolError("artifact safety ratios must be in (0, 1]")
    policy_id = root["policy_id"]
    policy_digest = root["policy_sha256"]
    if not isinstance(policy_id, str) or not policy_id:
        raise ProtocolError("artifact.policy_id is invalid")
    if (
        not isinstance(policy_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", policy_digest) is None
    ):
        raise ProtocolError("artifact.policy_sha256 is invalid")
    training_summary = _object(root["training_summary"], "artifact.training_summary")
    return HashRegexArtifact(
        hash_bins=hash_bins,
        feature_mean=mean,
        feature_scale=scale,
        score_heads={
            model_id: _linear_head(
                score_raw[model_id],
                length,
                f"score_heads.{model_id}",
            )
            for model_id in MODEL_IDS
        },
        log_cost_heads={
            model_id: _linear_head(
                cost_raw[model_id],
                length,
                f"log_cost_heads.{model_id}",
            )
            for model_id in MODEL_IDS
        },
        tier_safety_ratios=safety,
        policy_id=policy_id,
        policy_digest=policy_digest,
        training_summary=dict(training_summary),
    )


def load_hash_artifact(path: Path) -> HashRegexArtifact:
    return parse_hash_artifact(load_json(path))


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
            _number(item, f"{label}[{index}]")
            for index, item in enumerate(value)
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
    feature_names: Tuple[str, ...]
    feature_mean: Tuple[float, ...]
    feature_scale: Tuple[float, ...]
    model_ids: Tuple[str, ...]
    heads: Tuple[BinomialLogisticHead, ...]

    def __post_init__(self) -> None:
        names = _names(self.feature_names, "model.feature_names")
        mean = _vector(
            self.feature_mean,
            "model.feature_mean",
            expected_length=len(names),
        )
        scale = _vector(
            self.feature_scale,
            "model.feature_scale",
            expected_length=len(names),
        )
        if any(item <= 0 for item in scale):
            raise ValueError("model.feature_scale values must be positive")
        model_ids = _names(self.model_ids, "model.model_ids")
        if isinstance(self.heads, (str, bytes)) or not isinstance(
            self.heads,
            Sequence,
        ):
            raise ValueError("model.heads must be a sequence")
        heads = tuple(self.heads)
        if len(heads) != len(model_ids):
            raise ValueError("model.heads must match model.model_ids")
        for index, head in enumerate(heads):
            if not isinstance(head, BinomialLogisticHead):
                raise ValueError(
                    f"model.heads[{index}] must be a BinomialLogisticHead"
                )
            if len(head.coefficients) != len(names):
                raise ValueError(
                    f"model.heads[{index}].coefficients must match feature_names"
                )
        object.__setattr__(self, "feature_names", names)
        object.__setattr__(self, "feature_mean", mean)
        object.__setattr__(self, "feature_scale", scale)
        object.__setattr__(self, "model_ids", model_ids)
        object.__setattr__(self, "heads", heads)


def _value_object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _value_exact_keys(
    value: Mapping[str, Any],
    expected: Sequence[str],
    label: str,
) -> None:
    missing = sorted(set(expected) - set(value))
    extra = sorted(set(value) - set(expected))
    if missing or extra:
        raise ValueError(f"{label} fields differ: missing={missing}, extra={extra}")


def _artifact_vector(value: Any, length: int, label: str) -> Tuple[float, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return _vector(value, label, expected_length=length)


def parse_binomial_artifact(value: Any) -> BinomialLogisticQualityModel:
    root = _value_object(value, "artifact")
    _value_exact_keys(
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
    if root["artifact_type"] != BINOMIAL_ARTIFACT_TYPE:
        raise ValueError("unsupported artifact_type")
    if (
        isinstance(root["schema_version"], bool)
        or not isinstance(root["schema_version"], int)
        or root["schema_version"] != BINOMIAL_SCHEMA_VERSION
    ):
        raise ValueError("unsupported schema_version")
    if not isinstance(root["feature_names"], list):
        raise ValueError("artifact.feature_names must be an array")
    if not isinstance(root["model_ids"], list):
        raise ValueError("artifact.model_ids must be an array")
    feature_names = _names(root["feature_names"], "artifact.feature_names")
    model_ids = _names(root["model_ids"], "artifact.model_ids")
    feature_mean = _artifact_vector(
        root["feature_mean"],
        len(feature_names),
        "artifact.feature_mean",
    )
    feature_scale = _artifact_vector(
        root["feature_scale"],
        len(feature_names),
        "artifact.feature_scale",
    )
    raw_heads = _value_object(root["heads"], "artifact.heads")
    if set(raw_heads) != set(model_ids):
        raise ValueError("artifact.heads must match artifact.model_ids")
    heads = []
    for model_id in model_ids:
        label = f"artifact.heads[{model_id!r}]"
        raw_head = _value_object(raw_heads[model_id], label)
        _value_exact_keys(raw_head, ("intercept", "coefficients"), label)
        heads.append(
            BinomialLogisticHead(
                intercept=_number(raw_head["intercept"], f"{label}.intercept"),
                coefficients=_artifact_vector(
                    raw_head["coefficients"],
                    len(feature_names),
                    f"{label}.coefficients",
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


def load_binomial_artifact(path: Path) -> BinomialLogisticQualityModel:
    return parse_binomial_artifact(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class RouterArtifacts:
    hash_model: HashRegexArtifact
    binomial_model: BinomialLogisticQualityModel
    compatibility_model: E5BilinearCompatibilityModel
    encoder: ContentEncoder


__all__ = (
    "BinomialLogisticHead",
    "BinomialLogisticQualityModel",
    "ContentEncoder",
    "HashRegexArtifact",
    "LinearHead",
    "RouterArtifacts",
    "load_binomial_artifact",
    "load_compatibility_artifact",
    "load_hash_artifact",
    "parse_binomial_artifact",
    "parse_hash_artifact",
)
