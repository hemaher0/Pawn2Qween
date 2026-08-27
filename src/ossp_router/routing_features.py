# SPDX-FileCopyrightText: Copyright 2026 SK TELECOM CO., LTD.
# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Extract prompt-only dense and signed-hash routing features."""

from __future__ import annotations

import math
import re
from typing import Tuple

from .heuristic import episode_text, extract_features
from .protocol import Episode


DEFAULT_HASH_BINS = 256
MIN_HASH_BINS = 16
MAX_HASH_BINS = 16_384
_FNV_OFFSET = 14_695_981_039_346_656_037
_FNV_PRIME = 1_099_511_628_211
_UINT64_MASK = (1 << 64) - 1
_TOKEN = re.compile(r"[A-Za-z]+|[가-힣]+|\d+|[^\w\s]", re.UNICODE)
_FORMAL_REASONING = re.compile(
    r"\b(?:prove|derive|theorem|lemma|counterexample|induction|"
    r"증명|유도|정리|보조정리|반례|귀납)\b",
    re.IGNORECASE,
)
_PROGRAM_ANALYSIS = re.compile(
    r"```|\b(?:traceback|exception|complexity|big[- ]?o|"
    r"시간\s*복잡도|공간\s*복잡도|예외|스택\s*추적)\b",
    re.IGNORECASE,
)
_MULTI_CONSTRAINT = re.compile(
    r"\b(?:exactly|at least|at most|must|only|without|"
    r"정확히|이상|이하|반드시|오직|제외하고)\b",
    re.IGNORECASE,
)
_SIMPLE_TRANSFORM = re.compile(
    r"\b(?:summari[sz]e|rewrite|translate|list|extract|"
    r"요약|바꾸|번역|나열|추출)\b",
    re.IGNORECASE,
)

DENSE_FEATURE_NAMES = (
    "log_character_count",
    "log_word_count",
    "log_sentence_count",
    "log_message_count",
    "hangul_ratio",
    "log_code_marker_count",
    "log_math_marker_count",
    "numeric_density",
    "long_context",
    "log_reasoning_marker_count",
    "formal_reasoning",
    "program_analysis",
    "log_multi_constraint_count",
    "simple_transform",
)


def _stable_hash(value: str) -> int:
    digest = _FNV_OFFSET
    for byte in value.encode("utf-8"):
        digest ^= byte
        digest = (digest * _FNV_PRIME) & _UINT64_MASK
    return digest


def _normalized_tokens(text: str) -> Tuple[str, ...]:
    result = []
    for token in _TOKEN.findall(text):
        normalized = token.casefold()
        if normalized.isdecimal():
            normalized = "<number>"
        result.append(normalized)
    return tuple(result)


def raw_feature_vector(episode: Episode, hash_bins: int) -> Tuple[float, ...]:
    """Build dense regex features plus signed word unigram/bigram bins."""

    if (
        isinstance(hash_bins, bool)
        or not isinstance(hash_bins, int)
        or not MIN_HASH_BINS <= hash_bins <= MAX_HASH_BINS
        or hash_bins & (hash_bins - 1)
    ):
        raise ValueError("hash_bins must be an allowed power of two")
    extracted = extract_features(episode)
    text = episode_text(episode)
    dense = (
        math.log1p(extracted.character_count),
        math.log1p(extracted.word_count),
        math.log1p(extracted.sentence_count),
        math.log1p(extracted.message_count),
        extracted.hangul_ratio,
        math.log1p(extracted.code_marker_count),
        math.log1p(extracted.math_marker_count),
        extracted.numeric_density,
        float(extracted.long_context),
        math.log1p(extracted.reasoning_marker_count),
        float(bool(_FORMAL_REASONING.search(text))),
        float(bool(_PROGRAM_ANALYSIS.search(text))),
        math.log1p(len(_MULTI_CONSTRAINT.findall(text))),
        float(bool(_SIMPLE_TRANSFORM.search(text))),
    )
    bins = [0.0] * hash_bins
    tokens = _normalized_tokens(text)
    hashed_features = [f"w1:{token}" for token in tokens]
    hashed_features.extend(
        f"w2:{left}\x1f{right}" for left, right in zip(tokens, tokens[1:])
    )
    for value in hashed_features:
        digest = _stable_hash(value)
        index = digest & (hash_bins - 1)
        bins[index] += -1.0 if digest & (1 << 63) else 1.0
    norm = math.sqrt(sum(value * value for value in bins))
    if norm:
        bins = [value / norm for value in bins]
    return dense + tuple(bins)
