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
from pathlib import Path
from typing import Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
for import_root in (ROOT, ROOT / "src"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from baselines import binomial_logistic_quality as binomial  # noqa: E402
from baselines import e5_bilinear_compatibility as compatibility  # noqa: E402
from baselines import e5_onnx_encoder  # noqa: E402
from baselines import hash_regex  # noqa: E402
from ossp_router.heuristic import (  # noqa: E402
    episode_text,
    write_submission_atomic,
)
from ossp_router.protocol import (  # noqa: E402
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
    parse_submission,
    policy_sha256,
    submission_to_dict,
)


DEFAULT_HASH_ARTIFACT = ROOT / "baselines/hash-regex-public.v1.json"
DEFAULT_BINOMIAL_ARTIFACT = ROOT / "baselines/binomial-logistic-quality-public.v1.json"
DEFAULT_COMPATIBILITY_ARTIFACT = (
    ROOT / "baselines/e5-bilinear-compatibility-public.v1.json"
)
DEFAULT_MODEL_DIR = ROOT / "build/e5-model"
_ONNX_SIZE = 470_268_510
_TOKENIZER_SIZE = 17_082_730


@dataclass(frozen=True)
class E5BinomialPlan:
    """One validated submission plus its unchanged allocator diagnostics."""

    submission: Submission
    predicted_budget_ratio: float
    safety_ratio: float
    ax31_fill_safety_ratio: Optional[float]


def _expected_feature_names(
    artifact: hash_regex.HashRegexArtifact,
) -> Tuple[str, ...]:
    dense = tuple(map(str, hash_regex.DENSE_FEATURE_NAMES))
    hashed = tuple(f"signed_hash_{index}" for index in range(artifact.hash_bins))
    return dense + hashed


def _validate_components(
    policy: RoutingPolicy,
    hash_artifact: hash_regex.HashRegexArtifact,
    binomial_model: binomial.BinomialLogisticQualityModel,
    compatibility_model: compatibility.E5BilinearCompatibilityModel,
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


def make_e5_binomial_submission(
    inputs: InputBatch,
    policy: RoutingPolicy,
    hash_artifact: hash_regex.HashRegexArtifact,
    binomial_model: binomial.BinomialLogisticQualityModel,
    compatibility_model: compatibility.E5BilinearCompatibilityModel,
    encoder: e5_onnx_encoder.E5OnnxEncoder,
    tier: str,
) -> E5BinomialPlan:
    """Compose quality signals once and use the existing cost-aware allocator."""

    if inputs.schema_version != policy.schema_version:
        raise ProtocolError("input and policy schema versions differ")
    if tier not in TIERS:
        raise ProtocolError("unknown routing tier")
    _validate_components(
        policy,
        hash_artifact,
        binomial_model,
        compatibility_model,
        encoder,
    )
    texts = tuple(episode_text(episode) for episode in inputs.episodes)
    embeddings = encoder.encode_texts(texts)
    if len(embeddings) != len(inputs.episodes):
        raise RuntimeError("encoder output does not align with input rows")

    combined_quality = []
    predicted_costs = []
    for episode, embedding in zip(inputs.episodes, embeddings):
        raw_features = hash_regex.raw_feature_vector(
            episode,
            hash_artifact.hash_bins,
        )
        binomial_quality = binomial.predict_model_qualities(
            binomial_model,
            raw_features,
        )
        compatibility_logits = compatibility.predict_compatibility_logits(
            compatibility_model,
            embedding,
        )
        combined_quality.append(
            compatibility.blend_quality_logits(
                binomial_quality,
                compatibility_logits,
                compatibility_weight=compatibility_model.compatibility_weight,
            )
        )
        predicted_costs.append(hash_regex.predict_episode(episode, hash_artifact)[1])

    safety_ratio = hash_artifact.tier_safety_ratios[tier]
    selected, predicted_ratio = hash_regex.select_models(
        combined_quality,
        predicted_costs,
        budget_multiplier=float(policy.tiers[tier].budget_multiplier),
        safety_ratio=safety_ratio,
    )
    fill_safety = None
    if tier == "premium":
        fill_safety = hash_regex.PREMIUM_AX31_FILL_SAFETY_RATIO
        selected, predicted_ratio = hash_regex.fill_ax31_upgrades(
            selected,
            combined_quality,
            predicted_costs,
            budget_multiplier=float(policy.tiers[tier].budget_multiplier),
            safety_ratio=fill_safety,
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
    return E5BinomialPlan(
        submission=parse_submission(submission_to_dict(submission)),
        predicted_budget_ratio=predicted_ratio,
        safety_ratio=safety_ratio,
        ax31_fill_safety_ratio=fill_safety,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_encoder(
    model_dir: Path,
    identity: compatibility.E5EncoderIdentity,
) -> e5_onnx_encoder.E5OnnxEncoder:
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
    return e5_onnx_encoder.E5OnnxEncoder(model_dir, identity=identity)


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
        hash_artifact = hash_regex.load_artifact(args.hash_artifact)
        binomial_model = binomial.parse_artifact(
            json.loads(args.binomial_artifact.read_text(encoding="utf-8"))
        )
        compatibility_model = compatibility.load_compatibility_artifact(
            args.compatibility_artifact
        )
        encoder = _load_encoder(args.model_dir, compatibility_model.encoder)
        plan = make_e5_binomial_submission(
            inputs,
            policy,
            hash_artifact,
            binomial_model,
            compatibility_model,
            encoder,
            args.tier,
        )
        write_submission_atomic(args.output, plan.submission)
    except (OSError, ProtocolError, RuntimeError, ValueError, json.JSONDecodeError):
        print("error: router initialization or inference failed", file=sys.stderr)
        return 2
    print(
        "OK: submission created "
        f"(predicted cost ratio {plan.predicted_budget_ratio:.6f})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
