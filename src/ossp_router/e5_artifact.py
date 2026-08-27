# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Validate and run the aggregate E5 rank-two compatibility artifact."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from ossp_router.protocol import MODEL_IDS


ARTIFACT_TYPE = "ossp-e5-bilinear-compatibility-v1"
SCHEMA_VERSION = 1
EMBEDDING_DIMENSION = 384
LATENT_RANK = 2
PINNED_MODEL_ID = "intfloat/multilingual-e5-small"
PINNED_REVISION = "fd1525a9fd15316a2d503bf26ab031a61d056e98"
PREPROCESSING_ID = "e5-query-head-tail-mean-pool-l2-v1"
RETAINED_BLEND_WEIGHT = 0.5
LOGIT_EPSILON = 1.0e-5
JEFFREYS_PSEUDOCOUNT = 0.5
_SHA256 = re.compile(r"[0-9a-f]{64}")


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


def _integer(value: Any, label: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    return value


def _vector(
    value: Sequence[float],
    label: str,
    *,
    expected_length: int,
) -> Tuple[float, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be a sequence")
    result = tuple(
        _number(item, f"{label}[{index}]") for index, item in enumerate(value)
    )
    if len(result) != expected_length:
        raise ValueError(f"{label} must contain {expected_length} values")
    return result


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: Sequence[str], label: str) -> None:
    missing = sorted(set(expected) - set(value))
    extra = sorted(set(value) - set(expected))
    if missing or extra:
        raise ValueError(f"{label} fields differ: missing={missing}, extra={extra}")


@dataclass(frozen=True)
class E5EncoderIdentity:
    """Identity of the frozen encoder required by the aggregate model."""

    model_id: str
    revision: str
    onnx_sha256: str
    tokenizer_sha256: str
    preprocessing_id: str

    def __post_init__(self) -> None:
        model_id = _text(self.model_id, "encoder.model_id")
        revision = _text(self.revision, "encoder.revision")
        preprocessing_id = _text(
            self.preprocessing_id,
            "encoder.preprocessing_id",
        )
        if model_id != PINNED_MODEL_ID:
            raise ValueError("encoder.model_id does not match the pinned E5 model")
        if revision != PINNED_REVISION:
            raise ValueError("encoder.revision does not match the pinned E5 revision")
        if preprocessing_id != PREPROCESSING_ID:
            raise ValueError("encoder.preprocessing_id is unsupported")
        object.__setattr__(self, "model_id", model_id)
        object.__setattr__(self, "revision", revision)
        object.__setattr__(
            self,
            "onnx_sha256",
            _sha256(self.onnx_sha256, "encoder.onnx_sha256"),
        )
        object.__setattr__(
            self,
            "tokenizer_sha256",
            _sha256(self.tokenizer_sha256, "encoder.tokenizer_sha256"),
        )
        object.__setattr__(self, "preprocessing_id", preprocessing_id)


@dataclass(frozen=True)
class E5CompatibilityHead:
    """One protocol model's latent vector and bias."""

    vector: Tuple[float, ...]
    bias: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "vector",
            _vector(
                self.vector,
                "head.vector",
                expected_length=LATENT_RANK,
            ),
        )
        object.__setattr__(self, "bias", _number(self.bias, "head.bias"))


@dataclass(frozen=True)
class E5TrainingMetadata:
    """Aggregate public Train provenance and retained fit configuration."""

    train_input_sha256: str
    train_outcome_sha256: str
    seed: int
    rank: int
    steps: int
    learning_rate: float
    weight_decay: float
    jeffreys_pseudocount: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "train_input_sha256",
            _sha256(self.train_input_sha256, "training.train_input_sha256"),
        )
        object.__setattr__(
            self,
            "train_outcome_sha256",
            _sha256(self.train_outcome_sha256, "training.train_outcome_sha256"),
        )
        object.__setattr__(self, "seed", _integer(self.seed, "training.seed"))
        rank = _integer(self.rank, "training.rank", minimum=1)
        if rank != LATENT_RANK:
            raise ValueError("training.rank must be two")
        object.__setattr__(self, "rank", rank)
        object.__setattr__(
            self,
            "steps",
            _integer(self.steps, "training.steps", minimum=1),
        )
        learning_rate = _number(self.learning_rate, "training.learning_rate")
        if learning_rate <= 0.0:
            raise ValueError("training.learning_rate must be positive")
        object.__setattr__(self, "learning_rate", learning_rate)
        weight_decay = _number(self.weight_decay, "training.weight_decay")
        if weight_decay < 0.0:
            raise ValueError("training.weight_decay must not be negative")
        object.__setattr__(self, "weight_decay", weight_decay)
        pseudocount = _number(
            self.jeffreys_pseudocount,
            "training.jeffreys_pseudocount",
        )
        if pseudocount != JEFFREYS_PSEUDOCOUNT:
            raise ValueError("training.jeffreys_pseudocount must be 0.5")
        object.__setattr__(self, "jeffreys_pseudocount", pseudocount)


@dataclass(frozen=True)
class E5BilinearCompatibilityModel:
    """Validated aggregate state for rank-two prompt/model compatibility."""

    model_ids: Tuple[str, ...]
    encoder: E5EncoderIdentity
    embedding_mean: Tuple[float, ...]
    projection: Tuple[Tuple[float, ...], ...]
    heads: Tuple[E5CompatibilityHead, ...]
    compatibility_weight: float
    training: E5TrainingMetadata

    def __post_init__(self) -> None:
        if isinstance(self.model_ids, (str, bytes)) or not isinstance(
            self.model_ids, Sequence
        ):
            raise ValueError("model.model_ids must be a sequence")
        model_ids = tuple(self.model_ids)
        if model_ids != tuple(MODEL_IDS):
            raise ValueError("model.model_ids must match the protocol model order")
        if not isinstance(self.encoder, E5EncoderIdentity):
            raise ValueError("model.encoder must be an E5EncoderIdentity")
        embedding_mean = _vector(
            self.embedding_mean,
            "model.embedding_mean",
            expected_length=EMBEDDING_DIMENSION,
        )
        if isinstance(self.projection, (str, bytes)) or not isinstance(
            self.projection, Sequence
        ):
            raise ValueError("model.projection must be a sequence")
        projection = tuple(
            _vector(
                row,
                f"model.projection[{index}]",
                expected_length=EMBEDDING_DIMENSION,
            )
            for index, row in enumerate(self.projection)
        )
        if len(projection) != LATENT_RANK:
            raise ValueError("model.projection must contain two rows")
        if isinstance(self.heads, (str, bytes)) or not isinstance(self.heads, Sequence):
            raise ValueError("model.heads must be a sequence")
        heads = tuple(self.heads)
        if len(heads) != len(model_ids) or any(
            not isinstance(head, E5CompatibilityHead) for head in heads
        ):
            raise ValueError("model.heads must match the protocol models")
        compatibility_weight = _number(
            self.compatibility_weight,
            "model.compatibility_weight",
        )
        if compatibility_weight != RETAINED_BLEND_WEIGHT:
            raise ValueError("model.compatibility_weight must be 0.5")
        if not isinstance(self.training, E5TrainingMetadata):
            raise ValueError("model.training must be E5TrainingMetadata")
        object.__setattr__(self, "model_ids", model_ids)
        object.__setattr__(self, "embedding_mean", embedding_mean)
        object.__setattr__(self, "projection", projection)
        object.__setattr__(self, "heads", heads)
        object.__setattr__(self, "compatibility_weight", compatibility_weight)


def model_to_artifact(model: E5BilinearCompatibilityModel) -> Dict[str, object]:
    """Convert validated aggregate state to a JSON-compatible artifact."""

    return {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "model_ids": list(model.model_ids),
        "encoder": {
            "model_id": model.encoder.model_id,
            "revision": model.encoder.revision,
            "onnx_sha256": model.encoder.onnx_sha256,
            "tokenizer_sha256": model.encoder.tokenizer_sha256,
            "preprocessing_id": model.encoder.preprocessing_id,
        },
        "embedding_mean": list(model.embedding_mean),
        "projection": [list(row) for row in model.projection],
        "heads": {
            model_id: {
                "vector": list(head.vector),
                "bias": head.bias,
            }
            for model_id, head in zip(model.model_ids, model.heads)
        },
        "compatibility_weight": model.compatibility_weight,
        "training": {
            "train_input_sha256": model.training.train_input_sha256,
            "train_outcome_sha256": model.training.train_outcome_sha256,
            "seed": model.training.seed,
            "rank": model.training.rank,
            "steps": model.training.steps,
            "learning_rate": model.training.learning_rate,
            "weight_decay": model.training.weight_decay,
            "jeffreys_pseudocount": model.training.jeffreys_pseudocount,
        },
    }


def parse_compatibility_artifact(value: object) -> E5BilinearCompatibilityModel:
    """Parse a strict JSON-compatible aggregate artifact."""

    root = _object(value, "artifact")
    _exact_keys(
        root,
        (
            "artifact_type",
            "schema_version",
            "model_ids",
            "encoder",
            "embedding_mean",
            "projection",
            "heads",
            "compatibility_weight",
            "training",
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
    if not isinstance(root["model_ids"], list):
        raise ValueError("artifact.model_ids must be an array")
    model_ids = tuple(root["model_ids"])

    raw_encoder = _object(root["encoder"], "artifact.encoder")
    _exact_keys(
        raw_encoder,
        (
            "model_id",
            "revision",
            "onnx_sha256",
            "tokenizer_sha256",
            "preprocessing_id",
        ),
        "artifact.encoder",
    )
    encoder = E5EncoderIdentity(
        model_id=raw_encoder["model_id"],
        revision=raw_encoder["revision"],
        onnx_sha256=raw_encoder["onnx_sha256"],
        tokenizer_sha256=raw_encoder["tokenizer_sha256"],
        preprocessing_id=raw_encoder["preprocessing_id"],
    )

    if not isinstance(root["embedding_mean"], list):
        raise ValueError("artifact.embedding_mean must be an array")
    embedding_mean = _vector(
        root["embedding_mean"],
        "artifact.embedding_mean",
        expected_length=EMBEDDING_DIMENSION,
    )
    if not isinstance(root["projection"], list):
        raise ValueError("artifact.projection must be an array")
    projection = tuple(
        _vector(
            row,
            f"artifact.projection[{index}]",
            expected_length=EMBEDDING_DIMENSION,
        )
        for index, row in enumerate(root["projection"])
    )

    raw_heads = _object(root["heads"], "artifact.heads")
    if set(raw_heads) != set(model_ids):
        raise ValueError("artifact.heads must match artifact.model_ids")
    heads = []
    for model_id in model_ids:
        raw_head = _object(raw_heads[model_id], f"artifact.heads[{model_id!r}]")
        _exact_keys(
            raw_head,
            ("vector", "bias"),
            f"artifact.heads[{model_id!r}]",
        )
        if not isinstance(raw_head["vector"], list):
            raise ValueError(f"artifact.heads[{model_id!r}].vector must be an array")
        heads.append(
            E5CompatibilityHead(
                vector=_vector(
                    raw_head["vector"],
                    f"artifact.heads[{model_id!r}].vector",
                    expected_length=LATENT_RANK,
                ),
                bias=raw_head["bias"],
            )
        )

    raw_training = _object(root["training"], "artifact.training")
    _exact_keys(
        raw_training,
        (
            "train_input_sha256",
            "train_outcome_sha256",
            "seed",
            "rank",
            "steps",
            "learning_rate",
            "weight_decay",
            "jeffreys_pseudocount",
        ),
        "artifact.training",
    )
    training = E5TrainingMetadata(
        train_input_sha256=raw_training["train_input_sha256"],
        train_outcome_sha256=raw_training["train_outcome_sha256"],
        seed=raw_training["seed"],
        rank=raw_training["rank"],
        steps=raw_training["steps"],
        learning_rate=raw_training["learning_rate"],
        weight_decay=raw_training["weight_decay"],
        jeffreys_pseudocount=raw_training["jeffreys_pseudocount"],
    )
    return E5BilinearCompatibilityModel(
        model_ids=model_ids,
        encoder=encoder,
        embedding_mean=embedding_mean,
        projection=projection,
        heads=tuple(heads),
        compatibility_weight=root["compatibility_weight"],
        training=training,
    )


def load_compatibility_artifact(path: Path) -> E5BilinearCompatibilityModel:
    """Load a compatibility artifact from UTF-8 JSON."""

    return parse_compatibility_artifact(json.loads(path.read_text(encoding="utf-8")))


def _finite_sum(terms: Sequence[float], label: str) -> float:
    if any(not math.isfinite(term) for term in terms):
        raise ValueError(f"{label} must remain finite")
    try:
        result = math.fsum(terms)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{label} must remain finite") from error
    if not math.isfinite(result):
        raise ValueError(f"{label} must remain finite")
    return result


def predict_compatibility_logits(
    model: E5BilinearCompatibilityModel,
    embedding: Sequence[float],
) -> Mapping[str, float]:
    """Predict one compatibility logit per protocol model."""

    raw = _vector(
        embedding,
        "embedding",
        expected_length=EMBEDDING_DIMENSION,
    )
    centered = tuple(value - mean for value, mean in zip(raw, model.embedding_mean))
    if any(not math.isfinite(value) for value in centered):
        raise ValueError("centered embedding must remain finite")
    latent = tuple(
        _finite_sum(
            tuple(coefficient * value for coefficient, value in zip(row, centered)),
            f"latent[{index}]",
        )
        for index, row in enumerate(model.projection)
    )
    logits: Dict[str, float] = {}
    for model_id, head in zip(model.model_ids, model.heads):
        interaction = _finite_sum(
            tuple(
                coefficient * value for coefficient, value in zip(head.vector, latent)
            ),
            f"compatibility logit for {model_id!r}",
        )
        logit = head.bias + interaction
        if not math.isfinite(logit):
            raise ValueError(f"compatibility logit for {model_id!r} must remain finite")
        logits[model_id] = logit
    return logits


def _sigmoid(logit: float) -> float:
    if logit >= 0.0:
        return 1.0 / (1.0 + math.exp(-logit))
    exponential = math.exp(logit)
    return exponential / (1.0 + exponential)


def blend_quality_logits(
    binomial_quality: Mapping[str, float],
    compatibility_logits: Mapping[str, float],
    *,
    compatibility_weight: float,
) -> Mapping[str, float]:
    """Blend binomial probabilities and compatibility logits in logit space."""

    expected = set(MODEL_IDS)
    if set(binomial_quality) != expected:
        raise ValueError("binomial_quality must match the protocol models")
    if set(compatibility_logits) != expected:
        raise ValueError("compatibility_logits must match the protocol models")
    weight = _number(compatibility_weight, "compatibility_weight")
    if weight != RETAINED_BLEND_WEIGHT:
        raise ValueError("compatibility_weight must be 0.5")
    result: Dict[str, float] = {}
    for model_id in MODEL_IDS:
        probability = _number(
            binomial_quality[model_id],
            f"binomial_quality[{model_id!r}]",
        )
        if probability < 0.0 or probability > 1.0:
            raise ValueError("binomial quality values must be between zero and one")
        clipped = min(1.0 - LOGIT_EPSILON, max(LOGIT_EPSILON, probability))
        binomial_logit = math.log(clipped) - math.log1p(-clipped)
        compatibility_logit = _number(
            compatibility_logits[model_id],
            f"compatibility_logits[{model_id!r}]",
        )
        combined = (1.0 - weight) * binomial_logit + weight * compatibility_logit
        if not math.isfinite(combined):
            raise ValueError(f"combined quality logit for {model_id!r} must be finite")
        result[model_id] = _sigmoid(combined)
    return result
