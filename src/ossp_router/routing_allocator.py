# SPDX-FileCopyrightText: Copyright 2026 SK TELECOM CO., LTD.
# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Allocate protocol models under a batch-level predicted budget."""

from __future__ import annotations

import math
from typing import Mapping, Optional, Sequence, Tuple

from .protocol import MODEL_IDS


PREMIUM_AX31_FILL_SAFETY_RATIO = 0.65


def allocate_tier(
    predicted_scores: Sequence[Mapping[str, float]],
    predicted_costs: Sequence[Mapping[str, float]],
    *,
    tier: str,
    budget_multiplier: float,
    safety_ratio: float,
) -> Tuple[Tuple[str, ...], float, Optional[float]]:
    """Run the retained initial allocation and optional premium fill."""

    selected, ratio = select_models(
        predicted_scores,
        predicted_costs,
        budget_multiplier=budget_multiplier,
        safety_ratio=safety_ratio,
    )
    fill_safety = None
    if tier == "premium":
        fill_safety = PREMIUM_AX31_FILL_SAFETY_RATIO
        selected, ratio = fill_ax31_upgrades(
            selected,
            predicted_scores,
            predicted_costs,
            budget_multiplier=budget_multiplier,
            safety_ratio=fill_safety,
        )
    return selected, ratio, fill_safety


def select_models(
    predicted_scores: Sequence[Mapping[str, float]],
    predicted_costs: Sequence[Mapping[str, float]],
    *,
    budget_multiplier: float,
    safety_ratio: float,
) -> Tuple[Tuple[str, ...], float]:
    """Select one model per row with a batch-level Lagrangian budget."""

    if len(predicted_scores) != len(predicted_costs) or not predicted_scores:
        raise ValueError("scores and costs must be non-empty arrays of equal length")
    light_total = math.fsum(row[MODEL_IDS[0]] for row in predicted_costs)
    effective_ratio = max(1.0, budget_multiplier * safety_ratio)
    cap = light_total * effective_ratio

    def choose(penalty: float) -> Tuple[Tuple[str, ...], float]:
        selected = []
        for scores, costs in zip(predicted_scores, predicted_costs):
            model_id = max(
                MODEL_IDS,
                key=lambda candidate: (
                    scores[candidate]
                    - penalty * costs[candidate] / light_total,
                    -MODEL_IDS.index(candidate),
                ),
            )
            selected.append(model_id)
        total = math.fsum(
            costs[model_id]
            for costs, model_id in zip(predicted_costs, selected)
        )
        return tuple(selected), total

    selected, total = choose(0.0)
    if total > cap:
        low = 0.0
        high = 1.0
        selected, total = choose(high)
        while total > cap and high < 2**60:
            low = high
            high *= 2.0
            selected, total = choose(high)
        for _iteration in range(80):
            middle = (low + high) / 2.0
            candidate, candidate_total = choose(middle)
            if candidate_total <= cap:
                high = middle
                selected, total = candidate, candidate_total
            else:
                low = middle
    if total > cap:
        selected = tuple(MODEL_IDS[0] for _row in predicted_scores)
        total = light_total
    return selected, total / light_total


def fill_ax31_upgrades(
    selected: Sequence[str],
    predicted_scores: Sequence[Mapping[str, float]],
    predicted_costs: Sequence[Mapping[str, float]],
    *,
    budget_multiplier: float,
    safety_ratio: float,
) -> Tuple[Tuple[str, ...], float]:
    """Lock existing choices and fill unused budget with AX31 upgrades."""

    if (
        len(selected) != len(predicted_scores)
        or len(selected) != len(predicted_costs)
        or not selected
    ):
        raise ValueError("selections and predictions must have equal lengths")
    if any(model_id not in MODEL_IDS for model_id in selected):
        raise ValueError("selections contain an unknown model")
    if not 0 < safety_ratio <= 1:
        raise ValueError("fill safety ratio must be in (0, 1]")

    light_id, ax31_id, _premium_id = MODEL_IDS
    light_total = math.fsum(row[light_id] for row in predicted_costs)
    current_total = math.fsum(
        costs[model_id]
        for costs, model_id in zip(predicted_costs, selected)
    )
    cap = max(
        current_total,
        light_total * max(1.0, budget_multiplier * safety_ratio),
    )

    def choose(penalty: float) -> Tuple[Tuple[str, ...], float]:
        filled = []
        for model_id, scores, costs in zip(
            selected,
            predicted_scores,
            predicted_costs,
        ):
            if model_id != light_id:
                filled.append(model_id)
                continue
            incremental_score = scores[ax31_id] - scores[light_id]
            incremental_cost = costs[ax31_id] - costs[light_id]
            if incremental_score - penalty * incremental_cost / light_total > 0:
                filled.append(ax31_id)
            else:
                filled.append(light_id)
        total = math.fsum(
            costs[model_id]
            for costs, model_id in zip(predicted_costs, filled)
        )
        return tuple(filled), total

    filled, total = choose(0.0)
    if total > cap:
        low = 0.0
        high = 1.0
        filled, total = choose(high)
        while total > cap and high < 2**60:
            low = high
            high *= 2.0
            filled, total = choose(high)
        for _iteration in range(80):
            middle = (low + high) / 2.0
            candidate, candidate_total = choose(middle)
            if candidate_total <= cap:
                high = middle
                filled, total = candidate, candidate_total
            else:
                low = middle
    if total > cap:
        return tuple(selected), current_total / light_total
    return filled, total / light_total
