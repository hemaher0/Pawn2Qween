# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Train and evaluate the maintained E5 routing artifacts offline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from ossp_router.protocol import (
    ProtocolError,
    load_bundled_policy,
    load_policy,
)
from ossp_router.routing_features import DEFAULT_HASH_BINS

from . import hash_training


def _run_hash(args: argparse.Namespace) -> None:
    policy = (
        load_policy(args.policy)
        if args.policy is not None
        else load_bundled_policy()
    )
    report = hash_training.train(
        input_path=args.input,
        outcomes_path=args.outcomes,
        artifact_path=args.artifact,
        report_path=args.report,
        policy=policy,
        hash_bins=args.hash_bins,
        requested_folds=args.folds,
        alpha_candidates=args.alphas,
        safety_grid_size=args.safety_grid_size,
        validation_input_path=args.validation_input,
        validation_outcomes_path=args.validation_outcomes,
    )
    print(
        "OK: wrote hash cost artifact "
        f"(Train score {report['fitted_train_self_check']['final_score']})."
    )


def _run_encode(args: argparse.Namespace) -> None:
    from . import e5_features

    e5_features.encode(args)


def _run_fit(args: argparse.Namespace) -> None:
    from . import e5_fit

    e5_fit.fit(args)


def _run_evaluate(args: argparse.Namespace) -> None:
    from . import e5_evaluation

    e5_evaluation._evaluate_command(args)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    hash_parser = subparsers.add_parser(
        "hash",
        help="fit hash features, cost heads, and tier safety ratios",
    )
    hash_parser.add_argument("--input", type=Path, required=True)
    hash_parser.add_argument("--outcomes", type=Path, required=True)
    hash_parser.add_argument("--artifact", type=Path, required=True)
    hash_parser.add_argument("--report", type=Path, required=True)
    hash_parser.add_argument("--validation-input", type=Path)
    hash_parser.add_argument("--validation-outcomes", type=Path)
    hash_parser.add_argument("--policy", type=Path)
    hash_parser.add_argument("--hash-bins", type=int, default=DEFAULT_HASH_BINS)
    hash_parser.add_argument("--folds", type=int, default=5)
    hash_parser.add_argument(
        "--alphas",
        type=hash_training.positive_float_list,
        default=hash_training.positive_float_list("0.1,1,10,100"),
    )
    hash_parser.add_argument("--safety-grid-size", type=int, default=121)
    hash_parser.set_defaults(run=_run_hash)

    encode = subparsers.add_parser("encode", help="materialize pinned ONNX vectors")
    encode.add_argument("--train-input", type=Path, required=True)
    encode.add_argument("--dev-input", type=Path, required=True)
    encode.add_argument("--model-spec", type=Path, required=True)
    encode.add_argument("--model-dir", type=Path, required=True)
    encode.add_argument("--output", type=Path, required=True)
    encode.set_defaults(run=_run_encode)

    fit = subparsers.add_parser("fit", help="fit aggregate Train-only artifacts")
    fit.add_argument("--train-input", type=Path, required=True)
    fit.add_argument("--train-outcomes", type=Path, required=True)
    fit.add_argument("--features", type=Path, required=True)
    fit.add_argument("--hash-artifact", type=Path, required=True)
    fit.add_argument("--binomial-output", type=Path, required=True)
    fit.add_argument("--compatibility-output", type=Path, required=True)
    fit.set_defaults(run=_run_fit)

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
    evaluate.set_defaults(run=_run_evaluate)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        args.run(args)
    except (OSError, ProtocolError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
