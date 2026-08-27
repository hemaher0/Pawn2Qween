#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Materialize E5 features and fit aggregate routing-quality artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence, Tuple

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
for import_root in (ROOT, ROOT / "src"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from baselines import e5_bilinear_compatibility as compatibility  # noqa: E402
from baselines import e5_onnx_encoder  # noqa: E402
from baselines import binomial_logistic_quality as binomial  # noqa: E402
from baselines import hash_regex  # noqa: E402
from ossp_router.heuristic import episode_text  # noqa: E402
from ossp_router.protocol import (  # noqa: E402
    MODEL_IDS,
    TIERS,
    Decision,
    InputBatch,
    OutcomeBatch,
    RoutingPolicy,
    Submission,
    load_bundled_policy,
    load_input,
    load_outcomes,
)
from ossp_router.scoring import score_submissions  # noqa: E402
from tools import fetch_e5_model  # noqa: E402


PROTOCOL_SEED = 20260827
FULL_FIT_SEED = PROTOCOL_SEED + 100
TRAINING_STEPS = 1_200
LEARNING_RATE = 0.03
WEIGHT_DECAY = 0.05
_UNIT_NORM_TOLERANCE = 2.0e-4
_FEATURE_KEYS = frozenset(
    ("content_sha256", "embeddings", "truncated", "metadata_json")
)
_METADATA_KEYS = frozenset(
    (
        "content_only",
        "content_token_budget",
        "dev_rows",
        "dimensions",
        "head_tokens",
        "license",
        "max_length",
        "model_commit",
        "model_id",
        "pooling",
        "prefix",
        "runtime",
        "tail_tokens",
        "train_rows",
    )
)
_NUMBER = re.compile(r"\d+")
_SPACE = re.compile(r"\s+")
FOLD_COUNT = 4


@dataclass(frozen=True)
class FeatureArchive:
    """Validated content-aligned E5 vectors used only by offline fitting."""

    content_sha256: Tuple[str, ...]
    embeddings: np.ndarray
    truncated: np.ndarray
    metadata: Mapping[str, object]


def content_sha256(text: str) -> str:
    """Return the alignment digest for canonical prompt content."""

    if not isinstance(text, str) or not text:
        raise ValueError("content must be a non-empty string")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _validated_metadata(
    value: object,
    *,
    train_rows: int,
    dev_rows: int,
) -> Mapping[str, object]:
    if not isinstance(value, dict) or set(value) != _METADATA_KEYS:
        raise ValueError("feature metadata fields are incompatible")
    expected = {
        "content_only": True,
        "content_token_budget": e5_onnx_encoder.CONTENT_TOKEN_BUDGET,
        "dev_rows": dev_rows,
        "dimensions": compatibility.EMBEDDING_DIMENSION,
        "head_tokens": e5_onnx_encoder.HEAD_TOKENS,
        "license": "MIT",
        "max_length": e5_onnx_encoder.MAX_LENGTH,
        "model_commit": compatibility.PINNED_REVISION,
        "model_id": compatibility.PINNED_MODEL_ID,
        "pooling": "attention-mask mean pooling followed by L2 normalization",
        "prefix": e5_onnx_encoder.PREFIX,
        "runtime": "onnxruntime-fp32-cpu",
        "tail_tokens": e5_onnx_encoder.TAIL_TOKENS,
        "train_rows": train_rows,
    }
    if value != expected:
        raise ValueError("feature metadata does not match the pinned E5 pipeline")
    return dict(value)


def _validated_feature_values(
    *,
    texts: Sequence[str],
    embeddings: object,
    truncated: object,
) -> tuple[Tuple[str, ...], np.ndarray, np.ndarray]:
    if isinstance(texts, (str, bytes)) or not isinstance(texts, Sequence):
        raise ValueError("texts must be a sequence")
    digests = tuple(content_sha256(text) for text in texts)
    try:
        matrix = np.asarray(embeddings, dtype=np.float32)
    except (OverflowError, TypeError, ValueError) as error:
        raise ValueError("embeddings must form a numeric matrix") from error
    flags = np.asarray(truncated)
    expected_shape = (len(digests), compatibility.EMBEDDING_DIMENSION)
    if matrix.shape != expected_shape:
        raise ValueError("embeddings must align with texts and contain 384 columns")
    if flags.dtype != np.bool_ or flags.shape != (len(digests),):
        raise ValueError("truncated flags must be a content-aligned Boolean vector")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("embeddings must contain only finite values")
    norms = np.linalg.norm(matrix, axis=1)
    if not np.allclose(
        norms,
        np.ones(len(digests), dtype=np.float32),
        rtol=0.0,
        atol=_UNIT_NORM_TOLERANCE,
    ):
        raise ValueError("embeddings must be unit vectors")
    return digests, matrix, flags


def write_feature_archive(
    path: Path,
    *,
    texts: Sequence[str],
    embeddings: object,
    truncated: object,
    metadata: Mapping[str, object],
) -> None:
    """Atomically write one validated, content-aligned feature archive."""

    train_rows = metadata.get("train_rows")
    dev_rows = metadata.get("dev_rows")
    if (
        isinstance(train_rows, bool)
        or not isinstance(train_rows, int)
        or train_rows < 1
        or isinstance(dev_rows, bool)
        or not isinstance(dev_rows, int)
        or dev_rows < 0
        or train_rows + dev_rows != len(texts)
    ):
        raise ValueError("feature split row counts are invalid")
    clean_metadata = _validated_metadata(
        dict(metadata),
        train_rows=train_rows,
        dev_rows=dev_rows,
    )
    digests, matrix, flags = _validated_feature_values(
        texts=texts,
        embeddings=embeddings,
        truncated=truncated,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            np.savez_compressed(
                temporary,
                content_sha256=np.asarray(digests),
                embeddings=matrix,
                truncated=flags,
                metadata_json=np.asarray(
                    json.dumps(clean_metadata, sort_keys=True, separators=(",", ":"))
                ),
            )
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_feature_archive(
    path: Path,
    *,
    expected_texts: Sequence[str],
    train_rows: int,
    dev_rows: int,
) -> FeatureArchive:
    """Load an immutable feature archive after strict identity and row checks."""

    try:
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != _FEATURE_KEYS:
                raise ValueError("feature archive fields are incompatible")
            stored_digests = np.asarray(archive["content_sha256"])
            embeddings = np.asarray(archive["embeddings"], dtype=np.float32)
            truncated = np.asarray(archive["truncated"])
            raw_metadata = json.loads(str(archive["metadata_json"]))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith("feature archive"):
            raise
        raise ValueError("cannot load the E5 feature archive") from error
    metadata = _validated_metadata(
        raw_metadata,
        train_rows=train_rows,
        dev_rows=dev_rows,
    )
    expected_digests, embeddings, truncated = _validated_feature_values(
        texts=expected_texts,
        embeddings=embeddings,
        truncated=truncated,
    )
    if stored_digests.ndim != 1 or tuple(map(str, stored_digests)) != expected_digests:
        raise ValueError("feature content digests do not match the expected row order")
    embeddings.setflags(write=False)
    truncated.setflags(write=False)
    return FeatureArchive(
        content_sha256=expected_digests,
        embeddings=embeddings,
        truncated=truncated,
        metadata=metadata,
    )


def load_train_feature_archive(
    path: Path,
    *,
    expected_train_texts: Sequence[str],
) -> FeatureArchive:
    """Load a full archive while binding its Train prefix to canonical content."""

    try:
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != _FEATURE_KEYS:
                raise ValueError("feature archive fields are incompatible")
            stored_digests = np.asarray(archive["content_sha256"])
            embeddings = np.asarray(archive["embeddings"], dtype=np.float32)
            truncated = np.asarray(archive["truncated"])
            raw_metadata = json.loads(str(archive["metadata_json"]))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith("feature archive"):
            raise
        raise ValueError("cannot load the E5 feature archive") from error
    if not isinstance(raw_metadata, dict):
        raise ValueError("feature metadata fields are incompatible")
    train_rows = raw_metadata.get("train_rows")
    dev_rows = raw_metadata.get("dev_rows")
    if (
        isinstance(train_rows, bool)
        or not isinstance(train_rows, int)
        or isinstance(dev_rows, bool)
        or not isinstance(dev_rows, int)
        or train_rows != len(expected_train_texts)
        or dev_rows < 0
    ):
        raise ValueError("feature split row counts are invalid")
    metadata = _validated_metadata(
        raw_metadata,
        train_rows=train_rows,
        dev_rows=dev_rows,
    )
    total_rows = train_rows + dev_rows
    if embeddings.shape != (total_rows, compatibility.EMBEDDING_DIMENSION):
        raise ValueError("embeddings must align with the declared split rows")
    if truncated.dtype != np.bool_ or truncated.shape != (total_rows,):
        raise ValueError("truncated flags must align with the declared split rows")
    if not np.all(np.isfinite(embeddings)) or not np.allclose(
        np.linalg.norm(embeddings, axis=1),
        np.ones(total_rows, dtype=np.float32),
        rtol=0.0,
        atol=_UNIT_NORM_TOLERANCE,
    ):
        raise ValueError("embeddings must contain finite unit vectors")
    if stored_digests.shape != (total_rows,):
        raise ValueError("feature content digests must align with split rows")
    digests = tuple(map(str, stored_digests))
    if any(
        len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        for digest in digests
    ):
        raise ValueError("feature content digests must be lowercase SHA-256 values")
    expected = tuple(content_sha256(text) for text in expected_train_texts)
    if digests[:train_rows] != expected:
        raise ValueError("Train feature digests do not match canonical content order")
    embeddings.setflags(write=False)
    truncated.setflags(write=False)
    return FeatureArchive(
        content_sha256=digests,
        embeddings=embeddings,
        truncated=truncated,
        metadata=metadata,
    )


def _validated_targets(
    quality: object,
    generation_counts: object,
    *,
    rows: int,
) -> tuple[np.ndarray, np.ndarray]:
    try:
        observed = np.asarray(quality, dtype=np.float64)
        generations = np.asarray(generation_counts, dtype=np.float64)
    except (OverflowError, TypeError, ValueError) as error:
        raise ValueError("quality and generation counts must be numeric") from error
    expected_shape = (rows, len(MODEL_IDS))
    if observed.shape != expected_shape or generations.shape != expected_shape:
        raise ValueError(
            "quality and generation counts must align with rows and models"
        )
    if (
        not np.all(np.isfinite(observed))
        or np.any(observed < 0.0)
        or np.any(observed > 1.0)
    ):
        raise ValueError("quality must be finite and between zero and one")
    if (
        not np.all(np.isfinite(generations))
        or np.any(generations < 1.0)
        or not np.all(generations == np.rint(generations))
    ):
        raise ValueError("generation counts must be positive integers")
    rounded = np.rint(observed * generations)
    if np.any(np.abs(rounded - observed * generations) > 1.0e-8):
        raise ValueError("quality must correspond to integer successes")
    return observed, generations


def jeffreys_targets(
    quality: object,
    generation_counts: object,
) -> tuple[np.ndarray, np.ndarray]:
    """Return row/model-specific Jeffreys-smoothed targets and trial weights."""

    observed = np.asarray(quality)
    rows = observed.shape[0] if observed.ndim == 2 else 0
    observed, generations = _validated_targets(
        quality,
        generation_counts,
        rows=rows,
    )
    successes = np.rint(observed * generations) + compatibility.JEFFREYS_PSEUDOCOUNT
    trials = generations + 2.0 * compatibility.JEFFREYS_PSEUDOCOUNT
    return successes / trials, trials


def _configure_deterministic_torch_environment() -> None:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")


def _require_torch() -> Any:
    _configure_deterministic_torch_environment()
    try:
        import torch
    except ImportError as error:  # pragma: no cover - fit environment boundary
        raise RuntimeError("compatibility fitting requires PyTorch") from error
    return torch


def _build_bilinear_module(dimensions: int, model_count: int, *, seed: int) -> Any:
    torch = _require_torch()
    torch.manual_seed(seed)

    class BilinearCompatibility(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.query = torch.nn.Linear(
                dimensions,
                compatibility.LATENT_RANK,
                bias=False,
            )
            self.model_vectors = torch.nn.Parameter(
                torch.empty(model_count, compatibility.LATENT_RANK)
            )
            self.bias = torch.nn.Parameter(torch.zeros(model_count))
            torch.nn.init.normal_(self.query.weight, mean=0.0, std=0.05)
            torch.nn.init.normal_(self.model_vectors, mean=0.0, std=0.05)

        def forward(self, features: Any) -> Any:
            return self.bias.unsqueeze(0) + self.query(features) @ self.model_vectors.T

    return BilinearCompatibility()


def _optimizer_groups(module: Any) -> list[dict[str, object]]:
    return [
        {
            "params": [module.query.weight, module.model_vectors],
            "weight_decay": WEIGHT_DECAY,
        },
        {"params": [module.bias], "weight_decay": 0.0},
    ]


def fit_compatibility_model(
    embeddings: object,
    quality: object,
    generation_counts: object,
    *,
    train_input_sha256: str,
    train_outcome_sha256: str,
    seed: int,
    steps: int,
    device: str,
) -> compatibility.E5BilinearCompatibilityModel:
    """Fit the fixed rank-two prompt/model interaction on E5 vectors alone."""

    try:
        matrix = np.asarray(embeddings, dtype=np.float32)
    except (OverflowError, TypeError, ValueError) as error:
        raise ValueError("embeddings must form a numeric matrix") from error
    if (
        matrix.ndim != 2
        or matrix.shape[0] == 0
        or matrix.shape[1] != compatibility.EMBEDDING_DIMENSION
        or not np.all(np.isfinite(matrix))
    ):
        raise ValueError("embeddings must be a finite non-empty 384-column matrix")
    observed, generations = _validated_targets(
        quality,
        generation_counts,
        rows=matrix.shape[0],
    )
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if isinstance(steps, bool) or not isinstance(steps, int) or steps < 1:
        raise ValueError("steps must be a positive integer")
    if not isinstance(device, str) or not device:
        raise ValueError("device must be a non-empty string")

    torch = _require_torch()
    torch.use_deterministic_algorithms(True)
    mean = np.mean(matrix, axis=0, dtype=np.float64).astype(np.float32)
    fit = torch.as_tensor(matrix - mean, dtype=torch.float32, device=device)
    targets, trials = jeffreys_targets(observed, generations)
    target_tensor = torch.as_tensor(targets, dtype=torch.float32, device=device)
    trial_tensor = torch.as_tensor(trials, dtype=torch.float32, device=device)
    module = _build_bilinear_module(
        compatibility.EMBEDDING_DIMENSION,
        len(MODEL_IDS),
        seed=seed,
    ).to(device)
    with torch.no_grad():
        success_tensor = target_tensor * trial_tensor
        rates = success_tensor.sum(dim=0) / trial_tensor.sum(dim=0)
        module.bias.copy_(
            torch.logit(
                rates.clamp(
                    compatibility.LOGIT_EPSILON,
                    1.0 - compatibility.LOGIT_EPSILON,
                )
            )
        )
    optimizer = torch.optim.AdamW(
        _optimizer_groups(module),
        lr=LEARNING_RATE,
    )
    for _step in range(steps):
        optimizer.zero_grad(set_to_none=True)
        logits = module(fit)
        loss = (
            torch.nn.functional.binary_cross_entropy_with_logits(
                logits,
                target_tensor,
                weight=trial_tensor,
                reduction="sum",
            )
            / trial_tensor.sum()
        )
        if not bool(torch.isfinite(loss)):
            raise RuntimeError("compatibility training loss became non-finite")
        loss.backward()
        optimizer.step()

    with torch.inference_mode():
        projection = module.query.weight.detach().cpu().numpy().astype(np.float64)
        vectors = module.model_vectors.detach().cpu().numpy().astype(np.float64)
        biases = module.bias.detach().cpu().numpy().astype(np.float64)
    if not (
        np.all(np.isfinite(projection))
        and np.all(np.isfinite(vectors))
        and np.all(np.isfinite(biases))
    ):
        raise RuntimeError("compatibility training produced non-finite parameters")
    return compatibility.E5BilinearCompatibilityModel(
        model_ids=tuple(MODEL_IDS),
        encoder=compatibility.E5EncoderIdentity(
            model_id=compatibility.PINNED_MODEL_ID,
            revision=compatibility.PINNED_REVISION,
            onnx_sha256=e5_onnx_encoder.PINNED_ONNX_SHA256,
            tokenizer_sha256=e5_onnx_encoder.PINNED_TOKENIZER_SHA256,
            preprocessing_id=compatibility.PREPROCESSING_ID,
        ),
        embedding_mean=tuple(float(value) for value in mean),
        projection=tuple(tuple(float(value) for value in row) for row in projection),
        heads=tuple(
            compatibility.E5CompatibilityHead(
                vector=tuple(float(value) for value in vector),
                bias=float(bias),
            )
            for vector, bias in zip(vectors, biases)
        ),
        compatibility_weight=compatibility.RETAINED_BLEND_WEIGHT,
        training=compatibility.E5TrainingMetadata(
            train_input_sha256=train_input_sha256,
            train_outcome_sha256=train_outcome_sha256,
            seed=seed,
            rank=compatibility.LATENT_RANK,
            steps=steps,
            learning_rate=LEARNING_RATE,
            weight_decay=WEIGHT_DECAY,
            jeffreys_pseudocount=compatibility.JEFFREYS_PSEUDOCOUNT,
        ),
    )


def canonical_artifact_bytes(value: Mapping[str, object]) -> bytes:
    """Serialize one aggregate artifact deterministically as UTF-8 JSON."""

    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def file_sha256(path: Path) -> str:
    """Hash one local input without retaining its contents."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quality_and_generations(
    inputs: InputBatch,
    outcomes: OutcomeBatch,
) -> tuple[np.ndarray, np.ndarray]:
    """Align public aggregate outcomes to input and protocol-model order."""

    if (
        inputs.schema_version != outcomes.schema_version
        or inputs.challenge_id != outcomes.challenge_id
        or inputs.split != outcomes.split
    ):
        raise ValueError("inputs and outcomes do not describe the same split")
    by_key = {(row.episode_id, row.model_id): row for row in outcomes.outcomes}
    expected_keys = {
        (episode.episode_id, model_id)
        for episode in inputs.episodes
        for model_id in MODEL_IDS
    }
    if set(by_key) != expected_keys:
        raise ValueError("outcomes do not exactly cover every input and model")
    quality = np.asarray(
        [
            [
                float(by_key[(episode.episode_id, model_id)].score)
                for model_id in MODEL_IDS
            ]
            for episode in inputs.episodes
        ],
        dtype=np.float64,
    )
    generations = np.asarray(
        [
            [
                by_key[(episode.episode_id, model_id)].num_generations
                for model_id in MODEL_IDS
            ]
            for episode in inputs.episodes
        ],
        dtype=np.float64,
    )
    _validated_targets(quality, generations, rows=len(inputs.episodes))
    return quality, generations


def hash_feature_names(artifact: hash_regex.HashRegexArtifact) -> Tuple[str, ...]:
    """Return the exact raw hash-regex feature order used by the binomial heads."""

    dense = tuple(map(str, hash_regex.DENSE_FEATURE_NAMES))
    hashed = tuple(f"signed_hash_{index}" for index in range(artifact.hash_bins))
    return dense + hashed


def raw_hash_features(
    inputs: InputBatch,
    artifact: hash_regex.HashRegexArtifact,
) -> np.ndarray:
    """Build the raw binomial feature matrix in input order."""

    return np.asarray(
        [
            hash_regex.raw_feature_vector(episode, artifact.hash_bins)
            for episode in inputs.episodes
        ],
        dtype=np.float64,
    )


def _write_bytes_atomic(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(value)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _verified_encoder(
    model_spec_path: Path, model_dir: Path
) -> e5_onnx_encoder.E5OnnxEncoder:
    spec = fetch_e5_model.load_model_spec(model_spec_path)
    for file in spec.files:
        local_path = model_dir.joinpath(*file.path.parts)
        if (
            not local_path.is_file()
            or local_path.stat().st_size != file.size
            or fetch_e5_model.sha256_file(local_path) != file.sha256
        ):
            raise ValueError(
                "local E5 runtime files do not match the pinned model spec"
            )
    identity = compatibility.E5EncoderIdentity(
        model_id=spec.model_id,
        revision=spec.revision,
        onnx_sha256=e5_onnx_encoder.PINNED_ONNX_SHA256,
        tokenizer_sha256=e5_onnx_encoder.PINNED_TOKENIZER_SHA256,
        preprocessing_id=compatibility.PREPROCESSING_ID,
    )
    return e5_onnx_encoder.E5OnnxEncoder(model_dir, identity=identity)


def _encode_command(args: argparse.Namespace) -> None:
    train_inputs = load_input(args.train_input)
    dev_inputs = load_input(args.dev_input)
    texts = tuple(
        episode_text(episode) for episode in train_inputs.episodes + dev_inputs.episodes
    )
    encoder = _verified_encoder(args.model_spec, args.model_dir)
    embeddings = np.asarray(encoder.encode_texts(texts), dtype=np.float32)
    truncated = np.asarray(
        tuple(encoder._prepare(text)[1] for text in texts),  # noqa: SLF001
        dtype=bool,
    )
    metadata = {
        "content_only": True,
        "content_token_budget": e5_onnx_encoder.CONTENT_TOKEN_BUDGET,
        "dev_rows": len(dev_inputs.episodes),
        "dimensions": compatibility.EMBEDDING_DIMENSION,
        "head_tokens": e5_onnx_encoder.HEAD_TOKENS,
        "license": "MIT",
        "max_length": e5_onnx_encoder.MAX_LENGTH,
        "model_commit": compatibility.PINNED_REVISION,
        "model_id": compatibility.PINNED_MODEL_ID,
        "pooling": "attention-mask mean pooling followed by L2 normalization",
        "prefix": e5_onnx_encoder.PREFIX,
        "runtime": "onnxruntime-fp32-cpu",
        "tail_tokens": e5_onnx_encoder.TAIL_TOKENS,
        "train_rows": len(train_inputs.episodes),
    }
    write_feature_archive(
        args.output,
        texts=texts,
        embeddings=embeddings,
        truncated=truncated,
        metadata=metadata,
    )


def _fit_command(args: argparse.Namespace) -> None:
    train_inputs = load_input(args.train_input)
    train_outcomes = load_outcomes(args.train_outcomes)
    texts = tuple(episode_text(episode) for episode in train_inputs.episodes)
    archive = load_train_feature_archive(
        args.features,
        expected_train_texts=texts,
    )
    quality, generations = quality_and_generations(train_inputs, train_outcomes)
    hash_artifact = hash_regex.load_artifact(args.hash_artifact)
    raw_features = raw_hash_features(train_inputs, hash_artifact)
    names = hash_feature_names(hash_artifact)
    if raw_features.shape[1] != len(names):
        raise ValueError("hash-regex feature names do not align with raw features")
    binomial_model = binomial.fit_binomial_logistic_quality(
        raw_features,
        quality,
        generations,
        feature_names=names,
        model_ids=MODEL_IDS,
    )
    torch = _require_torch()
    if not torch.cuda.is_available():
        raise RuntimeError("the publication fit requires one CUDA device")
    compatibility_model = fit_compatibility_model(
        archive.embeddings[: len(train_inputs.episodes)],
        quality,
        generations,
        train_input_sha256=file_sha256(args.train_input),
        train_outcome_sha256=file_sha256(args.train_outcomes),
        seed=FULL_FIT_SEED,
        steps=TRAINING_STEPS,
        device="cuda",
    )
    _write_bytes_atomic(
        args.binomial_output,
        canonical_artifact_bytes(binomial.model_to_artifact(binomial_model)),
    )
    _write_bytes_atomic(
        args.compatibility_output,
        canonical_artifact_bytes(compatibility.model_to_artifact(compatibility_model)),
    )


def _predict_binomial_rows(
    model: binomial.BinomialLogisticQualityModel,
    features: np.ndarray,
) -> Tuple[Mapping[str, float], ...]:
    return tuple(
        binomial.predict_model_qualities(model, tuple(map(float, row)))
        for row in features
    )


def _predict_blended_rows(
    binomial_rows: Sequence[Mapping[str, float]],
    model: compatibility.E5BilinearCompatibilityModel,
    embeddings: np.ndarray,
) -> Tuple[Mapping[str, float], ...]:
    if len(binomial_rows) != len(embeddings):
        raise ValueError("binomial rows and E5 embeddings must align")
    return tuple(
        compatibility.blend_quality_logits(
            binomial_quality,
            compatibility.predict_compatibility_logits(
                model,
                tuple(map(float, embedding)),
            ),
            compatibility_weight=model.compatibility_weight,
        )
        for binomial_quality, embedding in zip(binomial_rows, embeddings)
    )


def _predicted_costs(
    inputs: InputBatch,
    artifact: hash_regex.HashRegexArtifact,
) -> Tuple[Mapping[str, float], ...]:
    return tuple(
        hash_regex.predict_episode(episode, artifact)[1] for episode in inputs.episodes
    )


def _route_all_tiers(
    inputs: InputBatch,
    policy: RoutingPolicy,
    artifact: hash_regex.HashRegexArtifact,
    scores: Sequence[Mapping[str, float]],
    costs: Sequence[Mapping[str, float]],
) -> tuple[Tuple[Submission, ...], Mapping[str, float]]:
    submissions = []
    predicted_ratios = {}
    for tier in TIERS:
        selected, ratio = hash_regex.select_models(
            scores,
            costs,
            budget_multiplier=float(policy.tiers[tier].budget_multiplier),
            safety_ratio=artifact.tier_safety_ratios[tier],
        )
        if tier == "premium":
            selected, ratio = hash_regex.fill_ax31_upgrades(
                selected,
                scores,
                costs,
                budget_multiplier=float(policy.tiers[tier].budget_multiplier),
                safety_ratio=hash_regex.PREMIUM_AX31_FILL_SAFETY_RATIO,
            )
        submissions.append(
            Submission(
                schema_version=inputs.schema_version,
                challenge_id=inputs.challenge_id,
                policy_id=policy.policy_id,
                split=inputs.split,
                tier=tier,
                decisions=tuple(
                    Decision(episode.episode_id, model_id)
                    for episode, model_id in zip(inputs.episodes, selected)
                ),
            )
        )
        predicted_ratios[tier] = float(ratio)
    return tuple(submissions), predicted_ratios


def _normalized_content_group(text: str) -> str:
    normalized = _SPACE.sub(" ", _NUMBER.sub("<number>", text.casefold())).strip()
    return content_sha256(normalized)


def _grouped_folds(
    texts: Sequence[str],
    quality: np.ndarray,
) -> Tuple[Tuple[np.ndarray, np.ndarray], ...]:
    try:
        from sklearn.model_selection import StratifiedGroupKFold
    except ImportError as error:  # pragma: no cover - evaluation environment boundary
        raise RuntimeError("grouped evaluation requires scikit-learn") from error
    groups = np.asarray([_normalized_content_group(text) for text in texts])
    strata = np.argmax(quality, axis=1)
    splitter = StratifiedGroupKFold(
        n_splits=FOLD_COUNT,
        shuffle=True,
        random_state=PROTOCOL_SEED,
    )
    folds = tuple(
        (np.asarray(fit, dtype=np.int64), np.asarray(held, dtype=np.int64))
        for fit, held in splitter.split(np.zeros(len(texts)), strata, groups)
    )
    coverage = np.zeros(len(texts), dtype=np.int8)
    for fit, held in folds:
        if set(groups[fit]) & set(groups[held]):
            raise ValueError("normalized content group crosses an OOF boundary")
        coverage[held] += 1
    if np.any(coverage != 1):
        raise ValueError("grouped OOF folds do not partition Train")
    return folds


def _fit_oof_surfaces(
    train_inputs: InputBatch,
    train_quality: np.ndarray,
    train_generations: np.ndarray,
    train_embeddings: np.ndarray,
    hash_artifact: hash_regex.HashRegexArtifact,
    *,
    train_input_sha256: str,
    train_outcome_sha256: str,
) -> tuple[
    Tuple[Mapping[str, float], ...],
    Tuple[Mapping[str, float], ...],
]:
    texts = tuple(episode_text(episode) for episode in train_inputs.episodes)
    features = raw_hash_features(train_inputs, hash_artifact)
    names = hash_feature_names(hash_artifact)
    control: list[Mapping[str, float] | None] = [None] * len(texts)
    candidate: list[Mapping[str, float] | None] = [None] * len(texts)
    for fold_index, (fit, held) in enumerate(_grouped_folds(texts, train_quality)):
        binomial_model = binomial.fit_binomial_logistic_quality(
            features[fit],
            train_quality[fit],
            train_generations[fit],
            feature_names=names,
            model_ids=MODEL_IDS,
        )
        compatibility_model = fit_compatibility_model(
            train_embeddings[fit],
            train_quality[fit],
            train_generations[fit],
            train_input_sha256=train_input_sha256,
            train_outcome_sha256=train_outcome_sha256,
            seed=PROTOCOL_SEED + fold_index,
            steps=TRAINING_STEPS,
            device="cuda",
        )
        fold_control = _predict_binomial_rows(binomial_model, features[held])
        fold_candidate = _predict_blended_rows(
            fold_control,
            compatibility_model,
            train_embeddings[held],
        )
        for row, control_value, candidate_value in zip(
            held,
            fold_control,
            fold_candidate,
        ):
            control[int(row)] = control_value
            candidate[int(row)] = candidate_value
    if any(value is None for value in control + candidate):
        raise RuntimeError("grouped OOF predictions are incomplete")
    return (
        tuple(value for value in control if value is not None),
        tuple(value for value in candidate if value is not None),
    )


def _subset_inputs(inputs: InputBatch, rows: Sequence[int]) -> InputBatch:
    return InputBatch(
        schema_version=inputs.schema_version,
        challenge_id=inputs.challenge_id,
        split=inputs.split,
        episodes=tuple(inputs.episodes[int(row)] for row in rows),
    )


def _subset_outcomes(outcomes: OutcomeBatch, inputs: InputBatch) -> OutcomeBatch:
    episode_ids = {episode.episode_id for episode in inputs.episodes}
    return OutcomeBatch(
        schema_version=outcomes.schema_version,
        challenge_id=outcomes.challenge_id,
        split=outcomes.split,
        outcomes=tuple(
            row for row in outcomes.outcomes if row.episode_id in episode_ids
        ),
    )


def _action_sha256(submissions: Sequence[Submission]) -> str:
    payload = {
        submission.tier: [decision.model_id for decision in submission.decisions]
        for submission in submissions
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _score_delta(
    candidate: Mapping[str, object], control: Mapping[str, object]
) -> Decimal:
    return Decimal(str(candidate["final_score"])) - Decimal(str(control["final_score"]))


def _budgets_pass(report: Mapping[str, object]) -> bool:
    tiers = report["tiers"]
    if not isinstance(tiers, Mapping):
        raise ValueError("score report tiers are invalid")
    return all(bool(tiers[tier]["budget_passed"]) for tier in TIERS)


def _json_safe(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    return value


def _evaluate_command(args: argparse.Namespace) -> None:
    policy = load_bundled_policy()
    hash_artifact = hash_regex.load_artifact(args.hash_artifact)
    binomial_model = binomial.parse_artifact(
        json.loads(args.binomial_artifact.read_text(encoding="utf-8"))
    )
    compatibility_model = compatibility.load_compatibility_artifact(
        args.compatibility_artifact
    )
    train_inputs = load_input(args.train_input)
    train_outcomes = load_outcomes(args.train_outcomes)
    dev_inputs = load_input(args.dev_input)
    train_texts = tuple(episode_text(episode) for episode in train_inputs.episodes)
    dev_texts = tuple(episode_text(episode) for episode in dev_inputs.episodes)
    archive = load_feature_archive(
        args.features,
        expected_texts=train_texts + dev_texts,
        train_rows=len(train_texts),
        dev_rows=len(dev_texts),
    )
    train_quality, train_generations = quality_and_generations(
        train_inputs,
        train_outcomes,
    )
    train_control, train_candidate = _fit_oof_surfaces(
        train_inputs,
        train_quality,
        train_generations,
        archive.embeddings[: len(train_texts)],
        hash_artifact,
        train_input_sha256=file_sha256(args.train_input),
        train_outcome_sha256=file_sha256(args.train_outcomes),
    )
    train_costs = _predicted_costs(train_inputs, hash_artifact)
    control_train_actions, control_train_ratios = _route_all_tiers(
        train_inputs,
        policy,
        hash_artifact,
        train_control,
        train_costs,
    )
    candidate_train_actions, candidate_train_ratios = _route_all_tiers(
        train_inputs,
        policy,
        hash_artifact,
        train_candidate,
        train_costs,
    )

    dev_features = raw_hash_features(dev_inputs, hash_artifact)
    dev_control = _predict_binomial_rows(binomial_model, dev_features)
    dev_candidate = _predict_blended_rows(
        dev_control,
        compatibility_model,
        archive.embeddings[len(train_texts) :],
    )
    dev_costs = _predicted_costs(dev_inputs, hash_artifact)
    control_dev_actions, control_dev_ratios = _route_all_tiers(
        dev_inputs,
        policy,
        hash_artifact,
        dev_control,
        dev_costs,
    )
    candidate_dev_actions, candidate_dev_ratios = _route_all_tiers(
        dev_inputs,
        policy,
        hash_artifact,
        dev_candidate,
        dev_costs,
    )
    train_groups = {_normalized_content_group(text) for text in train_texts}
    novel_rows = tuple(
        index
        for index, text in enumerate(dev_texts)
        if _normalized_content_group(text) not in train_groups
    )
    novel_inputs = _subset_inputs(dev_inputs, novel_rows)
    novel_costs = tuple(dev_costs[row] for row in novel_rows)
    control_novel_actions, control_novel_ratios = _route_all_tiers(
        novel_inputs,
        policy,
        hash_artifact,
        tuple(dev_control[row] for row in novel_rows),
        novel_costs,
    )
    candidate_novel_actions, candidate_novel_ratios = _route_all_tiers(
        novel_inputs,
        policy,
        hash_artifact,
        tuple(dev_candidate[row] for row in novel_rows),
        novel_costs,
    )

    action_hashes = {
        "train_control": _action_sha256(control_train_actions),
        "train_candidate": _action_sha256(candidate_train_actions),
        "dev_control": _action_sha256(control_dev_actions),
        "dev_candidate": _action_sha256(candidate_dev_actions),
        "novel_dev_control": _action_sha256(control_novel_actions),
        "novel_dev_candidate": _action_sha256(candidate_novel_actions),
    }
    dev_outcomes = load_outcomes(args.dev_outcomes)
    novel_outcomes = _subset_outcomes(dev_outcomes, novel_inputs)

    control_train_score = score_submissions(
        train_inputs, train_outcomes, control_train_actions, policy
    )
    candidate_train_score = score_submissions(
        train_inputs, train_outcomes, candidate_train_actions, policy
    )
    control_dev_score = score_submissions(
        dev_inputs, dev_outcomes, control_dev_actions, policy
    )
    candidate_dev_score = score_submissions(
        dev_inputs, dev_outcomes, candidate_dev_actions, policy
    )
    control_novel_score = score_submissions(
        novel_inputs, novel_outcomes, control_novel_actions, policy
    )
    candidate_novel_score = score_submissions(
        novel_inputs, novel_outcomes, candidate_novel_actions, policy
    )
    train_delta = _score_delta(candidate_train_score, control_train_score)
    dev_delta = _score_delta(candidate_dev_score, control_dev_score)
    novel_delta = _score_delta(candidate_novel_score, control_novel_score)
    all_budgets_passed = all(
        _budgets_pass(report)
        for report in (
            control_train_score,
            candidate_train_score,
            control_dev_score,
            candidate_dev_score,
            control_novel_score,
            candidate_novel_score,
        )
    )
    gate_passed = bool(
        train_delta > 0 and dev_delta > 0 and novel_delta >= 0 and all_budgets_passed
    )
    report = {
        "candidate": "e5-bilinear-public-artifact-phase2-confirmation-v1",
        "phase": "PHASE_2",
        "classification": "PASSED" if gate_passed else "FAILED",
        "config": {
            "protocol_seed": PROTOCOL_SEED,
            "full_fit_seed": FULL_FIT_SEED,
            "folds": FOLD_COUNT,
            "rank": compatibility.LATENT_RANK,
            "steps": TRAINING_STEPS,
            "learning_rate": LEARNING_RATE,
            "weight_decay": WEIGHT_DECAY,
            "blend_weight": compatibility.RETAINED_BLEND_WEIGHT,
        },
        "scores": {
            "train_grouped_oof": {
                "control": control_train_score,
                "candidate": candidate_train_score,
                "delta": str(train_delta),
            },
            "dev_held_out": {
                "control": control_dev_score,
                "candidate": candidate_dev_score,
                "delta": str(dev_delta),
            },
            "dev_without_normalized_train_overlap": {
                "rows": len(novel_rows),
                "control": control_novel_score,
                "candidate": candidate_novel_score,
                "delta": str(novel_delta),
            },
        },
        "predicted_budget_ratios": {
            "train_control": control_train_ratios,
            "train_candidate": candidate_train_ratios,
            "dev_control": control_dev_ratios,
            "dev_candidate": candidate_dev_ratios,
            "novel_dev_control": control_novel_ratios,
            "novel_dev_candidate": candidate_novel_ratios,
        },
        "action_sha256": action_hashes,
        "checks": {
            "dev_actions_frozen_before_dev_outcomes_loaded": True,
            "all_budgets_passed": all_budgets_passed,
            "gate_passed": gate_passed,
        },
    }
    _write_bytes_atomic(
        args.report,
        canonical_artifact_bytes(_json_safe(report)),
    )
    if not gate_passed:
        raise RuntimeError("the fixed Phase 2 artifact gate did not pass")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    encode = subparsers.add_parser("encode", help="materialize pinned ONNX vectors")
    encode.add_argument("--train-input", type=Path, required=True)
    encode.add_argument("--dev-input", type=Path, required=True)
    encode.add_argument("--model-spec", type=Path, required=True)
    encode.add_argument("--model-dir", type=Path, required=True)
    encode.add_argument("--output", type=Path, required=True)
    encode.set_defaults(run=_encode_command)

    fit = subparsers.add_parser("fit", help="fit aggregate Train-only artifacts")
    fit.add_argument("--train-input", type=Path, required=True)
    fit.add_argument("--train-outcomes", type=Path, required=True)
    fit.add_argument("--features", type=Path, required=True)
    fit.add_argument("--hash-artifact", type=Path, required=True)
    fit.add_argument("--binomial-output", type=Path, required=True)
    fit.add_argument("--compatibility-output", type=Path, required=True)
    fit.set_defaults(run=_fit_command)

    evaluate = subparsers.add_parser(
        "evaluate",
        help="confirm grouped Train OOF and held-out Dev routing",
    )
    evaluate.add_argument("--train-input", type=Path, required=True)
    evaluate.add_argument("--train-outcomes", type=Path, required=True)
    evaluate.add_argument("--dev-input", type=Path, required=True)
    evaluate.add_argument("--dev-outcomes", type=Path, required=True)
    evaluate.add_argument("--features", type=Path, required=True)
    evaluate.add_argument("--hash-artifact", type=Path, required=True)
    evaluate.add_argument("--binomial-artifact", type=Path, required=True)
    evaluate.add_argument("--compatibility-artifact", type=Path, required=True)
    evaluate.add_argument("--report", type=Path, required=True)
    evaluate.set_defaults(run=_evaluate_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        args.run(args)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
