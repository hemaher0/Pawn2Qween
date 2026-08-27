# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Fit Train-only routing-quality artifacts from offline E5 features."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from typing import Any, Tuple

import numpy as np

from baselines import binomial_logistic_quality as binomial
from baselines import e5_artifact_publication as publication
from baselines import e5_training_features as feature_io
from baselines import hash_regex
from ossp_router import e5_artifact as compatibility
from ossp_router import e5_encoder as e5_onnx_encoder
from ossp_router.heuristic import episode_text
from ossp_router.protocol import MODEL_IDS, InputBatch, OutcomeBatch, load_input, load_outcomes


PROTOCOL_SEED = 20260827
FULL_FIT_SEED = PROTOCOL_SEED + 100
TRAINING_STEPS = 1_200
LEARNING_RATE = 0.03
WEIGHT_DECAY = 0.05


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
        and np.all(np.isfinite(biases)
    )):
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


def fit(args: argparse.Namespace) -> None:
    """Fit and atomically publish Train-only aggregate artifacts."""

    train_inputs = load_input(args.train_input)
    train_outcomes = load_outcomes(args.train_outcomes)
    texts = tuple(episode_text(episode) for episode in train_inputs.episodes)
    archive = feature_io.load_train_feature_archive(
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
    publication.write_bytes_atomic(
        args.binomial_output,
        publication.canonical_artifact_bytes(binomial.model_to_artifact(binomial_model)),
    )
    publication.write_bytes_atomic(
        args.compatibility_output,
        publication.canonical_artifact_bytes(
            publication.compatibility_model_to_artifact(compatibility_model)
        ),
    )
