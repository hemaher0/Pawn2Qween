# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Serialize and atomically publish aggregate E5 training artifacts."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Mapping

from ossp_router import e5_artifact as compatibility


def compatibility_model_to_artifact(
    model: compatibility.E5BilinearCompatibilityModel,
) -> dict[str, object]:
    """Convert validated training output to its public aggregate schema."""

    return {
        "artifact_type": compatibility.ARTIFACT_TYPE,
        "schema_version": compatibility.SCHEMA_VERSION,
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


def canonical_artifact_bytes(value: Mapping[str, object]) -> bytes:
    """Serialize an aggregate artifact deterministically as UTF-8 JSON."""

    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_bytes_atomic(path: Path, value: bytes) -> None:
    """Publish bytes without exposing a partially written artifact."""

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
