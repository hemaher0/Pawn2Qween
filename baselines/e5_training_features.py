# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Materialize and validate content-aligned E5 features for offline training."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence, Tuple

import numpy as np

from ossp_router import e5_artifact as compatibility
from ossp_router import e5_encoder as e5_onnx_encoder
from ossp_router.heuristic import episode_text
from ossp_router.protocol import load_input
from tools import fetch_e5_model


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


def encode(args: argparse.Namespace) -> None:
    """Encode canonical Train and Dev inputs with the pinned local model."""

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
