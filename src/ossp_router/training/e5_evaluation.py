# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Evaluate fixed offline routing artifacts on grouped Train OOF and Dev."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from decimal import Decimal
from typing import Mapping, Sequence, Tuple

import numpy as np

from ossp_router import e5_artifact as compatibility
from ossp_router.heuristic import episode_text
from ossp_router.protocol import (
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
from ossp_router.scoring import score_submissions
from ossp_router.routing_costs import predict_costs
from ossp_router.routing_allocator import allocate_tier
from ossp_router.routing_artifacts import HashRegexArtifact, load_hash_artifact

from . import artifact_publication as publication
from . import binomial_quality as binomial
from . import e5_features as feature_io
from . import e5_fit as fitting


_NUMBER = re.compile(r"\d+")
_SPACE = re.compile(r"\s+")
FOLD_COUNT = 4


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
    artifact: HashRegexArtifact,
) -> Tuple[Mapping[str, float], ...]:
    return tuple(predict_costs(episode, artifact) for episode in inputs.episodes)


def _route_all_tiers(
    inputs: InputBatch,
    policy: RoutingPolicy,
    artifact: HashRegexArtifact,
    scores: Sequence[Mapping[str, float]],
    costs: Sequence[Mapping[str, float]],
) -> tuple[Tuple[Submission, ...], Mapping[str, float]]:
    submissions = []
    predicted_ratios = {}
    for tier in TIERS:
        selected, ratio, _fill_safety = allocate_tier(
            scores,
            costs,
            tier=tier,
            budget_multiplier=float(policy.tiers[tier].budget_multiplier),
            safety_ratio=artifact.tier_safety_ratios[tier],
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
    return feature_io.content_sha256(normalized)


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
        random_state=fitting.PROTOCOL_SEED,
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
    hash_artifact: HashRegexArtifact,
    *,
    train_input_sha256: str,
    train_outcome_sha256: str,
) -> tuple[
    Tuple[Mapping[str, float], ...],
    Tuple[Mapping[str, float], ...],
]:
    texts = tuple(episode_text(episode) for episode in train_inputs.episodes)
    features = fitting.raw_hash_features(train_inputs, hash_artifact)
    names = fitting.hash_feature_names(hash_artifact)
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
        compatibility_model = fitting.fit_compatibility_model(
            train_embeddings[fit],
            train_quality[fit],
            train_generations[fit],
            train_input_sha256=train_input_sha256,
            train_outcome_sha256=train_outcome_sha256,
            seed=fitting.PROTOCOL_SEED + fold_index,
            steps=fitting.TRAINING_STEPS,
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
    """Evaluate the fixed artifacts without exposing Dev outcomes before routing."""

    policy = load_bundled_policy()
    hash_artifact = load_hash_artifact(args.hash_artifact)
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
    archive = feature_io.load_feature_archive(
        args.features,
        expected_texts=train_texts + dev_texts,
        train_rows=len(train_texts),
        dev_rows=len(dev_texts),
    )
    train_quality, train_generations = fitting.quality_and_generations(
        train_inputs,
        train_outcomes,
    )
    train_control, train_candidate = _fit_oof_surfaces(
        train_inputs,
        train_quality,
        train_generations,
        archive.embeddings[: len(train_texts)],
        hash_artifact,
        train_input_sha256=fitting.file_sha256(args.train_input),
        train_outcome_sha256=fitting.file_sha256(args.train_outcomes),
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

    dev_features = fitting.raw_hash_features(dev_inputs, hash_artifact)
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
            "protocol_seed": fitting.PROTOCOL_SEED,
            "full_fit_seed": fitting.FULL_FIT_SEED,
            "folds": FOLD_COUNT,
            "rank": compatibility.LATENT_RANK,
            "steps": fitting.TRAINING_STEPS,
            "learning_rate": fitting.LEARNING_RATE,
            "weight_decay": fitting.WEIGHT_DECAY,
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
    publication.write_bytes_atomic(
        args.report,
        publication.canonical_artifact_bytes(_json_safe(report)),
    )
    if not gate_passed:
        raise RuntimeError("the fixed Phase 2 artifact gate did not pass")
