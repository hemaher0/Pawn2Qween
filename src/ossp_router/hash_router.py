# SPDX-FileCopyrightText: Copyright 2026 SK TELECOM CO., LTD.
# SPDX-License-Identifier: Apache-2.0

"""Compose hash quality, cost, and allocation components for inference."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from .protocol import (
    TIERS,
    Decision,
    Episode,
    InputBatch,
    ProtocolError,
    RoutingPolicy,
    Submission,
    parse_submission,
    policy_sha256,
    submission_to_dict,
)
from .routing_allocator import (
    PREMIUM_AX31_FILL_SAFETY_RATIO,
    fill_ax31_upgrades,
    select_models,
)
from .routing_artifacts import HashRegexArtifact
from .routing_costs import predict_costs
from .routing_quality import predict_hash_quality


@dataclass(frozen=True)
class HashRouterPlan:
    """One hash-router submission and its aggregate budget diagnostics."""

    submission: Submission
    predicted_budget_ratio: float
    safety_ratio: float
    ax31_fill_safety_ratio: Optional[float]


def predict_episode(
    episode: Episode,
    artifact: HashRegexArtifact,
) -> Tuple[Mapping[str, float], Mapping[str, float]]:
    """Predict quality and cost without mixing their implementations."""

    return predict_hash_quality(episode, artifact), predict_costs(episode, artifact)


def make_hash_submission(
    inputs: InputBatch,
    policy: RoutingPolicy,
    artifact: HashRegexArtifact,
    tier: str,
) -> HashRouterPlan:
    """Build one tier submission from the maintained hash inference modules."""

    if inputs.schema_version != policy.schema_version:
        raise ProtocolError("input and policy schema_version differ")
    if tier not in TIERS:
        raise ProtocolError(f"unknown tier: {tier}")
    if artifact.policy_id != policy.policy_id:
        raise ProtocolError("artifact and policy policy_id differ")
    if artifact.policy_digest != policy_sha256(policy):
        raise ProtocolError("artifact and policy SHA-256 differ")

    predictions = tuple(
        predict_episode(episode, artifact) for episode in inputs.episodes
    )
    scores = tuple(item[0] for item in predictions)
    costs = tuple(item[1] for item in predictions)
    safety = artifact.tier_safety_ratios[tier]
    selected, ratio = select_models(
        scores,
        costs,
        budget_multiplier=float(policy.tiers[tier].budget_multiplier),
        safety_ratio=safety,
    )
    fill_safety = None
    if tier == "premium":
        fill_safety = PREMIUM_AX31_FILL_SAFETY_RATIO
        selected, ratio = fill_ax31_upgrades(
            selected,
            scores,
            costs,
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
    return HashRouterPlan(
        submission=parse_submission(submission_to_dict(submission)),
        predicted_budget_ratio=ratio,
        safety_ratio=safety,
        ax31_fill_safety_ratio=fill_safety,
    )


__all__ = (
    "HashRouterPlan",
    "PREMIUM_AX31_FILL_SAFETY_RATIO",
    "fill_ax31_upgrades",
    "make_hash_submission",
    "predict_episode",
    "select_models",
)
