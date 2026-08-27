# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Encode canonical prompt text with the pinned E5 FP32 ONNX model."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable, Sequence, Tuple

from baselines.e5_bilinear_compatibility import (
    EMBEDDING_DIMENSION,
    E5EncoderIdentity,
)


PINNED_ONNX_SHA256 = "ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665"
PINNED_TOKENIZER_SHA256 = (
    "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39"
)
PREFIX = "query: "
CONTENT_TOKEN_BUDGET = 480
HEAD_TOKENS = 240
TAIL_TOKENS = 240
MAX_LENGTH = 512
DEFAULT_MAX_BATCH_ROWS = 64
DEFAULT_MAX_BATCH_TOKENS = 4_096


def _default_tokenizer_factory(path: str) -> Any:
    try:
        from tokenizers import Tokenizer
    except ImportError as error:  # pragma: no cover - environment boundary
        raise RuntimeError("the E5 runtime tokenizer is unavailable") from error
    return Tokenizer.from_file(path)


def _default_session_factory(path: str) -> Any:
    try:
        import onnxruntime as ort
    except ImportError as error:  # pragma: no cover - environment boundary
        raise RuntimeError("the E5 ONNX runtime is unavailable") from error
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(
        path,
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )


class E5OnnxEncoder:
    """Deterministic content-only adapter for the pinned E5 ONNX model."""

    def __init__(
        self,
        model_dir: Path,
        *,
        identity: E5EncoderIdentity,
        tokenizer_factory: Callable[[str], Any] = _default_tokenizer_factory,
        session_factory: Callable[[str], Any] = _default_session_factory,
        max_batch_rows: int = DEFAULT_MAX_BATCH_ROWS,
        max_batch_tokens: int = DEFAULT_MAX_BATCH_TOKENS,
    ) -> None:
        if not isinstance(identity, E5EncoderIdentity):
            raise ValueError("identity must be an E5EncoderIdentity")
        if (
            identity.onnx_sha256 != PINNED_ONNX_SHA256
            or identity.tokenizer_sha256 != PINNED_TOKENIZER_SHA256
        ):
            raise ValueError("encoder identity does not match the packaged E5 files")
        if (
            isinstance(max_batch_rows, bool)
            or not isinstance(max_batch_rows, int)
            or max_batch_rows <= 0
        ):
            raise ValueError("max_batch_rows must be a positive integer")
        if (
            isinstance(max_batch_tokens, bool)
            or not isinstance(max_batch_tokens, int)
            or max_batch_tokens < MAX_LENGTH
        ):
            raise ValueError(f"max_batch_tokens must be at least {MAX_LENGTH}")
        self._identity = identity
        self._max_batch_rows = max_batch_rows
        self._max_batch_tokens = max_batch_tokens
        self._tokenizer = tokenizer_factory(str(model_dir / "onnx/tokenizer.json"))
        self._session = session_factory(str(model_dir / "onnx/model.onnx"))
        if self._session.get_providers() != ["CPUExecutionProvider"]:
            raise RuntimeError("E5 ONNX execution provider is not CPU-only")

    @property
    def identity(self) -> E5EncoderIdentity:
        """Return the immutable identity bound to this encoder."""

        return self._identity

    def _prepare(self, text: str) -> Tuple[Tuple[int, ...], bool]:
        raw = self._tokenizer.encode(text, add_special_tokens=False)
        content_ids = tuple(raw.ids)
        truncated = len(content_ids) > CONTENT_TOKEN_BUDGET
        if truncated:
            selected = content_ids[:HEAD_TOKENS] + content_ids[-TAIL_TOKENS:]
            content = self._tokenizer.decode(
                selected,
                skip_special_tokens=True,
            )
        else:
            content = text
        prepared = self._tokenizer.encode(
            PREFIX + content,
            add_special_tokens=True,
        )
        ids = tuple(prepared.ids)
        if not ids or len(ids) > MAX_LENGTH:
            raise RuntimeError("prepared E5 input has an invalid token length")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in ids):
            raise RuntimeError("E5 tokenizer returned invalid token IDs")
        return ids, truncated

    def _batches(
        self,
        prepared: Sequence[Tuple[Tuple[int, ...], bool]],
    ) -> Tuple[Tuple[int, ...], ...]:
        ordered = sorted(
            range(len(prepared)),
            key=lambda index: (len(prepared[index][0]), index),
        )
        batches = []
        start = 0
        while start < len(ordered):
            end = start
            longest = 0
            while end < len(ordered) and end - start < self._max_batch_rows:
                candidate_longest = max(
                    longest,
                    len(prepared[ordered[end]][0]),
                )
                candidate_rows = end - start + 1
                if (
                    end > start
                    and candidate_rows * candidate_longest > self._max_batch_tokens
                ):
                    break
                longest = candidate_longest
                end += 1
            batches.append(tuple(ordered[start:end]))
            start = end
        return tuple(batches)

    def _encode_batch(
        self,
        prepared: Sequence[Tuple[Tuple[int, ...], bool]],
    ) -> Tuple[Tuple[float, ...], ...]:
        try:
            import numpy as np
        except ImportError as error:  # pragma: no cover - environment boundary
            raise RuntimeError("NumPy is unavailable for E5 inference") from error
        pad_id = self._tokenizer.token_to_id("<pad>")
        if isinstance(pad_id, bool) or not isinstance(pad_id, int):
            raise RuntimeError("E5 tokenizer does not define a valid padding token")
        width = max(len(row[0]) for row in prepared)
        input_ids = np.full((len(prepared), width), pad_id, dtype=np.int64)
        attention_mask = np.zeros((len(prepared), width), dtype=np.int64)
        for row_index, (ids, _truncated) in enumerate(prepared):
            input_ids[row_index, : len(ids)] = np.asarray(ids, dtype=np.int64)
            attention_mask[row_index, : len(ids)] = 1
        input_names = {row.name for row in self._session.get_inputs()}
        permitted = {"input_ids", "attention_mask"}
        permitted_with_types = permitted | {"token_type_ids"}
        if input_names not in (permitted, permitted_with_types):
            raise RuntimeError("E5 ONNX model has incompatible inputs")
        feeds = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }
        if "token_type_ids" in input_names:
            feeds["token_type_ids"] = np.zeros_like(input_ids)
        outputs = self._session.run(None, feeds)
        if not outputs:
            raise RuntimeError("E5 ONNX model returned no output")
        hidden = np.asarray(outputs[0], dtype=np.float32)
        expected_shape = (len(prepared), width, EMBEDDING_DIMENSION)
        if hidden.shape != expected_shape:
            raise RuntimeError("E5 ONNX hidden-state shape is incompatible")
        mask = attention_mask[:, :, None].astype(np.float32)
        pooled = np.sum(hidden * mask, axis=1) / np.sum(mask, axis=1)
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        if (
            not np.all(np.isfinite(pooled))
            or not np.all(np.isfinite(norms))
            or np.any(norms <= 0.0)
        ):
            raise RuntimeError("E5 pooling produced invalid vectors")
        normalized = pooled / norms
        if not np.all(np.isfinite(normalized)):
            raise RuntimeError("E5 normalization produced invalid vectors")
        return tuple(tuple(float(value) for value in row) for row in normalized)

    def encode_texts(
        self,
        texts: Sequence[str],
    ) -> Tuple[Tuple[float, ...], ...]:
        """Encode texts once and return unit vectors in input order."""

        if isinstance(texts, (str, bytes)) or not isinstance(texts, Sequence):
            raise ValueError("texts must be a sequence")
        if not texts:
            return ()
        if any(not isinstance(text, str) or not text for text in texts):
            raise ValueError("texts must contain non-empty strings")
        prepared = tuple(self._prepare(text) for text in texts)
        result: list[Tuple[float, ...] | None] = [None] * len(prepared)
        for indices in self._batches(prepared):
            vectors = self._encode_batch(tuple(prepared[index] for index in indices))
            for index, vector in zip(indices, vectors):
                result[index] = vector
        if any(vector is None for vector in result):
            raise RuntimeError("E5 encoder did not return every input row")
        vectors = tuple(vector for vector in result if vector is not None)
        if any(
            len(vector) != EMBEDDING_DIMENSION
            or not math.isclose(
                math.sqrt(sum(value * value for value in vector)),
                1.0,
                rel_tol=0.0,
                abs_tol=2.0e-4,
            )
            for vector in vectors
        ):
            raise RuntimeError("E5 encoder returned invalid unit vectors")
        return vectors
