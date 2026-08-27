#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Route with independent binomial and E5 compatibility quality signals."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Optional, Sequence, Tuple

from . import e5_encoder
from . import routing_allocator as allocator
from . import routing_costs as costs
from . import routing_features as features
from . import routing_quality as quality
from .e5_artifact import (
    E5BilinearCompatibilityModel,
    E5EncoderIdentity,
    load_compatibility_artifact,
)
from .heuristic import (
    episode_text,
    write_submission_atomic,
)
from .protocol import (
    MODEL_IDS,
    TIERS,
    Decision,
    InputBatch,
    ProtocolError,
    RoutingPolicy,
    Submission,
    load_bundled_policy,
    load_input,
    load_policy,
    policy_sha256,
)
from .routing_artifacts import (
    BinomialLogisticQualityModel,
    HashRegexArtifact,
    RouterArtifacts,
    load_binomial_artifact,
    load_hash_artifact,
)


RESOURCE_ROOT = resources.files("ossp_router.resources")
DEFAULT_HASH_ARTIFACT = Path(str(RESOURCE_ROOT.joinpath("hash-regex-public.v1.json")))
DEFAULT_BINOMIAL_ARTIFACT = Path(
    str(RESOURCE_ROOT.joinpath("binomial-logistic-quality-public.v1.json"))
)
DEFAULT_COMPATIBILITY_ARTIFACT = Path(
    str(RESOURCE_ROOT.joinpath("e5-bilinear-compatibility-public.v1.json"))
)
DEFAULT_MODEL_DIR = Path("build/e5-model")
_ONNX_SIZE = 470_268_510
_TOKENIZER_SIZE = 17_082_730


@dataclass(frozen=True)
class _RoutingResult:
    """One validated submission plus its unchanged allocator diagnostics."""

    submission: Submission
    predicted_budget_ratio: float
    safety_ratio: float
    ax31_fill_safety_ratio: Optional[float]


def _expected_feature_names(
    artifact: HashRegexArtifact,
) -> Tuple[str, ...]:
    dense = tuple(map(str, features.DENSE_FEATURE_NAMES))
    hashed = tuple(f"signed_hash_{index}" for index in range(artifact.hash_bins))
    return dense + hashed


def _validate_components(
    policy: RoutingPolicy,
    hash_artifact: HashRegexArtifact,
    binomial_model: BinomialLogisticQualityModel,
    compatibility_model: E5BilinearCompatibilityModel,
    encoder: object,
) -> None:
    if hash_artifact.policy_id != policy.policy_id:
        raise ProtocolError("hash artifact and policy IDs differ")
    if hash_artifact.policy_digest != policy_sha256(policy):
        raise ProtocolError("hash artifact and policy digests differ")
    if binomial_model.model_ids != tuple(MODEL_IDS):
        raise ValueError("binomial model order does not match the protocol")
    if binomial_model.feature_names != _expected_feature_names(hash_artifact):
        raise ValueError("binomial feature order does not match hash-regex features")
    if compatibility_model.model_ids != tuple(MODEL_IDS):
        raise ValueError("compatibility model order does not match the protocol")
    if getattr(encoder, "identity", None) != compatibility_model.encoder:
        raise ValueError("encoder identity does not match the compatibility artifact")
    if not callable(getattr(encoder, "encode_texts", None)):
        raise ValueError("encoder does not provide content encoding")


def _route_with_diagnostics(
    inputs: InputBatch,
    policy: RoutingPolicy,
    tier: str,
    artifacts: RouterArtifacts,
) -> _RoutingResult:
    """Compose quality signals once and use the existing cost-aware allocator."""

    if inputs.schema_version != policy.schema_version:
        raise ProtocolError("input and policy schema versions differ")
    if tier not in TIERS:
        raise ProtocolError("unknown routing tier")
    _validate_components(
        policy,
        artifacts.hash_model,
        artifacts.binomial_model,
        artifacts.compatibility_model,
        artifacts.encoder,
    )
    texts = tuple(episode_text(episode) for episode in inputs.episodes)
    embeddings = artifacts.encoder.encode_texts(texts)
    if len(embeddings) != len(inputs.episodes):
        raise RuntimeError("encoder output does not align with input rows")

    combined_quality = []
    predicted_costs = []
    for episode, embedding in zip(inputs.episodes, embeddings):
        raw_features = features.raw_feature_vector(
            episode,
            artifacts.hash_model.hash_bins,
        )
        binomial_quality = quality.predict_binomial_quality(
            artifacts.binomial_model,
            raw_features,
        )
        compatibility_logits = quality.predict_compatibility_logits(
            artifacts.compatibility_model,
            embedding,
        )
        combined_quality.append(
            quality.blend_quality_logits(
                binomial_quality,
                compatibility_logits,
                compatibility_weight=(
                    artifacts.compatibility_model.compatibility_weight
                ),
            )
        )
        hash_features = features.standardize_feature_vector(
            raw_features,
            artifacts.hash_model.feature_mean,
            artifacts.hash_model.feature_scale,
        )
        predicted_costs.append(
            costs.predict_costs_from_features(
                hash_features,
                artifacts.hash_model,
            )
        )

    safety_ratio = artifacts.hash_model.tier_safety_ratios[tier]
    selected, predicted_ratio, fill_safety = allocator.allocate_tier(
        combined_quality,
        predicted_costs,
        tier=tier,
        budget_multiplier=float(policy.tiers[tier].budget_multiplier),
        safety_ratio=safety_ratio,
    )
    submission = Submission(
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
    return _RoutingResult(
        submission=submission,
        predicted_budget_ratio=predicted_ratio,
        safety_ratio=safety_ratio,
        ax31_fill_safety_ratio=fill_safety,
    )


def route(
    inputs: InputBatch,
    policy: RoutingPolicy,
    tier: str,
    artifacts: RouterArtifacts,
) -> Submission:
    """Route one validated input batch with immutable runtime artifacts."""

    return _route_with_diagnostics(inputs, policy, tier, artifacts).submission


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_encoder(
    model_dir: Path,
    identity: E5EncoderIdentity,
) -> e5_encoder.E5OnnxEncoder:
    model_path = model_dir / "onnx/model.onnx"
    tokenizer_path = model_dir / "onnx/tokenizer.json"
    expected = (
        (model_path, _ONNX_SIZE, identity.onnx_sha256),
        (tokenizer_path, _TOKENIZER_SIZE, identity.tokenizer_sha256),
    )
    for path, size, digest in expected:
        if (
            not path.is_file()
            or path.stat().st_size != size
            or _sha256_file(path) != digest
        ):
            raise ValueError("runtime model bytes do not match the artifact identity")
    return e5_encoder.E5OnnxEncoder(model_dir, identity=identity)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--tier", choices=TIERS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hash-artifact", type=Path, default=DEFAULT_HASH_ARTIFACT)
    parser.add_argument(
        "--binomial-artifact",
        type=Path,
        default=DEFAULT_BINOMIAL_ARTIFACT,
    )
    parser.add_argument(
        "--compatibility-artifact",
        type=Path,
        default=DEFAULT_COMPATIBILITY_ARTIFACT,
    )
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--policy", type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        inputs = load_input(args.input)
        policy = (
            load_policy(args.policy)
            if args.policy is not None
            else load_bundled_policy()
        )
        hash_artifact = load_hash_artifact(args.hash_artifact)
        binomial_model = load_binomial_artifact(args.binomial_artifact)
        compatibility_model = load_compatibility_artifact(args.compatibility_artifact)
        encoder = _load_encoder(args.model_dir, compatibility_model.encoder)
        submission = route(
            inputs,
            policy,
            args.tier,
            RouterArtifacts(
                hash_model=hash_artifact,
                binomial_model=binomial_model,
                compatibility_model=compatibility_model,
                encoder=encoder,
            ),
        )
        write_submission_atomic(args.output, submission)
    except (OSError, ProtocolError, RuntimeError, ValueError, json.JSONDecodeError):
        print("error: router initialization or inference failed", file=sys.stderr)
        return 2
    print("OK: submission created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
