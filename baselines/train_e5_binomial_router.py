#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Encode, fit, and evaluate the offline E5 routing artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
for import_root in (ROOT, ROOT / "src"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from baselines import e5_artifact_publication as publication  # noqa: E402
from baselines import e5_training_evaluation as evaluation  # noqa: E402
from baselines import e5_training_features as features  # noqa: E402
from baselines import e5_training_fit as fitting  # noqa: E402


# Compatibility exports keep the existing offline-training API stable while
# implementation responsibilities live in their stage-specific modules.
FeatureArchive = features.FeatureArchive
content_sha256 = features.content_sha256
write_feature_archive = features.write_feature_archive
load_feature_archive = features.load_feature_archive
load_train_feature_archive = features.load_train_feature_archive

PROTOCOL_SEED = fitting.PROTOCOL_SEED
FULL_FIT_SEED = fitting.FULL_FIT_SEED
TRAINING_STEPS = fitting.TRAINING_STEPS
LEARNING_RATE = fitting.LEARNING_RATE
WEIGHT_DECAY = fitting.WEIGHT_DECAY
jeffreys_targets = fitting.jeffreys_targets
fit_compatibility_model = fitting.fit_compatibility_model
_configure_deterministic_torch_environment = (
    fitting._configure_deterministic_torch_environment
)
_build_bilinear_module = fitting._build_bilinear_module
_optimizer_groups = fitting._optimizer_groups

canonical_artifact_bytes = publication.canonical_artifact_bytes
_evaluate_command = evaluation._evaluate_command


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    encode = subparsers.add_parser("encode", help="materialize pinned ONNX vectors")
    encode.add_argument("--train-input", type=Path, required=True)
    encode.add_argument("--dev-input", type=Path, required=True)
    encode.add_argument("--model-spec", type=Path, required=True)
    encode.add_argument("--model-dir", type=Path, required=True)
    encode.add_argument("--output", type=Path, required=True)
    encode.set_defaults(run=features.encode)

    fit = subparsers.add_parser("fit", help="fit aggregate Train-only artifacts")
    fit.add_argument("--train-input", type=Path, required=True)
    fit.add_argument("--train-outcomes", type=Path, required=True)
    fit.add_argument("--features", type=Path, required=True)
    fit.add_argument("--hash-artifact", type=Path, required=True)
    fit.add_argument("--binomial-output", type=Path, required=True)
    fit.add_argument("--compatibility-output", type=Path, required=True)
    fit.set_defaults(run=fitting.fit)

    evaluate = subparsers.add_parser(
        "evaluate",
        help="confirm grouped Train OOF and held-out Dev routing",
    )
    evaluate.add_argument("--train-input", type=Path, required=True)
    evaluate.add_argument("--train-outcomes", type=Path, required=True)
    evaluate.add_argument("--dev-input", type=Path, required=True)
    evaluate.add_argument("--dev-outcomes", type=Path, required=True)
    evaluate.add_argument("--features", type=Path, required=True)
    evaluate.add_argument("--hash-artifact", type=Path, required=True)
    evaluate.add_argument("--binomial-artifact", type=Path, required=True)
    evaluate.add_argument("--compatibility-artifact", type=Path, required=True)
    evaluate.add_argument("--report", type=Path, required=True)
    evaluate.set_defaults(run=evaluation._evaluate_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        args.run(args)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
