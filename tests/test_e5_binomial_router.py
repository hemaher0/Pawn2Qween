# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import dataclasses
import hashlib
import io
import pathlib
import subprocess
import sys
import unittest
from types import SimpleNamespace
from contextlib import redirect_stderr
from unittest import mock

from ossp_router import e5_artifact as compatibility
from ossp_router import e5_router as router
from ossp_router import routing_allocator as allocator
from ossp_router import routing_artifacts
from ossp_router import routing_costs
from ossp_router import routing_features
from ossp_router import routing_quality
from ossp_router.heuristic import episode_text
from ossp_router.protocol import (
    MODEL_IDS,
    Episode,
    InputBatch,
    Message,
    load_bundled_policy,
)


ROOT = pathlib.Path(__file__).resolve().parents[1]


class _Encoder:
    def __init__(self, identity):
        self.identity = identity
        self.calls = []

    def encode_texts(self, texts):
        self.calls.append(tuple(texts))
        vectors = []
        for text in texts:
            index = hashlib.sha256(text.encode("utf-8")).digest()[0] % 384
            vector = [0.0] * 384
            vector[index] = 1.0
            vectors.append(tuple(vector))
        return tuple(vectors)


def _inputs() -> InputBatch:
    return InputBatch(
        schema_version=1,
        challenge_id="challenge",
        split="test",
        episodes=(
            Episode("private-id-a", prompt="first content"),
            Episode(
                "private-id-b",
                messages=(
                    Message("system", "system content"),
                    Message("user", "second content"),
                ),
            ),
        ),
    )


def _changed_inputs(inputs: InputBatch) -> InputBatch:
    return InputBatch(
        schema_version=inputs.schema_version,
        challenge_id="changed-challenge",
        split="changed-split",
        episodes=tuple(
            Episode(
                episode_id=f"changed-{index}",
                prompt=episode.prompt,
                messages=episode.messages,
            )
            for index, episode in enumerate(reversed(inputs.episodes))
        ),
    )


def _by_content(inputs: InputBatch, submission) -> dict[str, str]:
    decisions = {
        decision.episode_id: decision.model_id for decision in submission.decisions
    }
    return {
        episode_text(episode): decisions[episode.episode_id]
        for episode in inputs.episodes
    }


class E5BinomialRouterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_bundled_policy()
        cls.hash_artifact = routing_artifacts.load_hash_artifact(
            ROOT / "src/ossp_router/resources/hash-regex-public.v1.json"
        )
        cls.binomial_model = routing_artifacts.load_binomial_artifact(
            ROOT
            / "src/ossp_router/resources/binomial-logistic-quality-public.v1.json"
        )
        cls.compatibility_model = compatibility.load_compatibility_artifact(
            ROOT
            / "src/ossp_router/resources/e5-bilinear-compatibility-public.v1.json"
        )

    def _artifacts(self, encoder, *, binomial_model=None):
        return routing_artifacts.RouterArtifacts(
            hash_model=self.hash_artifact,
            binomial_model=binomial_model or self.binomial_model,
            compatibility_model=self.compatibility_model,
            encoder=encoder,
        )

    def test_route_extracts_hash_features_once_per_episode(self) -> None:
        inputs = _inputs()
        encoder = _Encoder(self.compatibility_model.encoder)

        with mock.patch.object(
            routing_features,
            "extract_features",
            wraps=routing_features.extract_features,
        ) as extract:
            submission = router.route(
                inputs,
                self.policy,
                "balanced",
                self._artifacts(encoder),
            )

        self.assertEqual(len(inputs.episodes), len(submission.decisions))
        self.assertEqual(len(inputs.episodes), extract.call_count)

    def test_encodes_content_once_and_composes_quality_with_unchanged_costs(
        self,
    ) -> None:
        inputs = _inputs()
        encoder = _Encoder(self.compatibility_model.encoder)
        raw = tuple(
            float(index) for index in range(len(self.binomial_model.feature_names))
        )
        binomial_quality = {model_id: 0.4 for model_id in MODEL_IDS}
        compatibility_logits = {model_id: 0.2 for model_id in MODEL_IDS}
        combined = {
            MODEL_IDS[0]: 0.1,
            MODEL_IDS[1]: 0.5,
            MODEL_IDS[2]: 0.9,
        }
        costs = {
            MODEL_IDS[0]: 1.0,
            MODEL_IDS[1]: 2.0,
            MODEL_IDS[2]: 3.0,
        }
        selected = (MODEL_IDS[0], MODEL_IDS[2])
        with (
            mock.patch.object(
                routing_features, "raw_feature_vector", return_value=raw
            ) as raw_feature,
            mock.patch.object(
                routing_quality,
                "predict_binomial_quality",
                return_value=binomial_quality,
            ) as predict_binomial,
            mock.patch.object(
                routing_quality,
                "predict_compatibility_logits",
                return_value=compatibility_logits,
            ) as predict_compatibility,
            mock.patch.object(
                routing_quality,
                "blend_quality_logits",
                return_value=combined,
            ) as blend,
            mock.patch.object(
                routing_costs,
                "predict_costs_from_features",
                return_value=costs,
            ) as predict_cost,
            mock.patch.object(
                allocator,
                "allocate_tier",
                return_value=(selected, 1.75, None),
            ) as allocate,
        ):
            submission = router.route(
                inputs,
                self.policy,
                "balanced",
                self._artifacts(encoder),
            )

        self.assertEqual(
            ("first content", "system content\nsecond content"),
            encoder.calls[0],
        )
        self.assertEqual(1, len(encoder.calls))
        self.assertEqual(2, raw_feature.call_count)
        self.assertEqual(2, predict_binomial.call_count)
        self.assertEqual(2, predict_compatibility.call_count)
        self.assertEqual(2, blend.call_count)
        self.assertEqual(2, predict_cost.call_count)
        self.assertEqual((combined, combined), tuple(allocate.call_args.args[0]))
        self.assertEqual((costs, costs), tuple(allocate.call_args.args[1]))
        self.assertEqual(
            self.hash_artifact.tier_safety_ratios["balanced"],
            allocate.call_args.kwargs["safety_ratio"],
        )
        self.assertEqual("balanced", allocate.call_args.kwargs["tier"])
        self.assertEqual(
            selected, tuple(row.model_id for row in submission.decisions)
        )
        for call in blend.call_args_list:
            self.assertEqual(0.5, call.kwargs["compatibility_weight"])
        for call in predict_binomial.call_args_list:
            self.assertEqual(raw, call.args[1])

    def test_premium_uses_existing_ax31_fill_with_unchanged_safety(self) -> None:
        inputs = _inputs()
        encoder = _Encoder(self.compatibility_model.encoder)
        filled = (MODEL_IDS[1], MODEL_IDS[0])
        with mock.patch.object(
            allocator,
            "allocate_tier",
            return_value=(filled, 1.5, 0.65),
        ) as allocate:
            submission = router.route(
                inputs,
                self.policy,
                "premium",
                self._artifacts(encoder),
            )

        self.assertEqual(
            filled, tuple(row.model_id for row in submission.decisions)
        )
        self.assertEqual(
            "premium",
            allocate.call_args.kwargs["tier"],
        )
        self.assertEqual(
            self.hash_artifact.tier_safety_ratios["premium"],
            allocate.call_args.kwargs["safety_ratio"],
        )

    def test_ids_and_row_order_do_not_change_content_decisions(self) -> None:
        original = _inputs()
        changed = _changed_inputs(original)
        for tier in ("fast", "balanced", "premium"):
            with self.subTest(tier=tier):
                first = router.route(
                    original,
                    self.policy,
                    tier,
                    self._artifacts(_Encoder(self.compatibility_model.encoder)),
                )
                second = router.route(
                    changed,
                    self.policy,
                    tier,
                    self._artifacts(_Encoder(self.compatibility_model.encoder)),
                )

                self.assertEqual(
                    _by_content(original, first),
                    _by_content(changed, second),
                )

    def test_rejects_incompatible_encoder_and_feature_order(self) -> None:
        encoder = _Encoder(
            dataclasses.replace(
                self.compatibility_model.encoder,
                onnx_sha256="f" * 64,
            )
        )
        with self.assertRaises(ValueError):
            router.route(
                _inputs(),
                self.policy,
                "fast",
                self._artifacts(encoder),
            )
        wrong_features = dataclasses.replace(
            self.binomial_model,
            feature_names=tuple(reversed(self.binomial_model.feature_names)),
        )
        with self.assertRaises(ValueError):
            router.route(
                _inputs(),
                self.policy,
                "fast",
                self._artifacts(
                    _Encoder(self.compatibility_model.encoder),
                    binomial_model=wrong_features,
                ),
            )

    def test_runtime_module_has_no_outcome_scoring_or_network_dependency(self) -> None:
        source = pathlib.Path(router.__file__).read_text(encoding="utf-8")

        for forbidden in (
            "load_outcomes",
            "ossp_router.scoring",
            "urllib",
            "requests",
            "httpx",
            "data/train",
            "data/dev",
        ):
            self.assertNotIn(forbidden, source)

    def test_script_can_be_invoked_directly(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ossp_router.e5_router",
                "--help",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--compatibility-artifact", result.stdout)

    def test_cli_failure_is_sanitized(self) -> None:
        stderr = io.StringIO()
        with (
            mock.patch.object(
                router,
                "load_input",
                side_effect=OSError("/private/location/input.json"),
            ),
            redirect_stderr(stderr),
        ):
            result = router.main(
                (
                    "--input",
                    "input.json",
                    "--tier",
                    "fast",
                    "--output",
                    "output.json",
                )
            )

        self.assertEqual(2, result)
        self.assertEqual(
            "error: router initialization or inference failed\n",
            stderr.getvalue(),
        )
        self.assertNotIn("private", stderr.getvalue())

    def test_cli_accepts_the_official_wrapper_arguments(self) -> None:
        inputs = _inputs()
        policy = load_bundled_policy()
        expected = mock.sentinel.submission
        compatibility_model = SimpleNamespace(encoder=mock.sentinel.identity)
        output = pathlib.Path("/challenge/output/submission.json")
        with (
            mock.patch.object(router, "load_input", return_value=inputs),
            mock.patch.object(router, "load_bundled_policy", return_value=policy),
            mock.patch.object(
                router,
                "load_hash_artifact",
                return_value=mock.sentinel.hash_artifact,
            ),
            mock.patch.object(
                router,
                "load_binomial_artifact",
                return_value=mock.sentinel.binomial_artifact,
            ),
            mock.patch.object(
                router,
                "load_compatibility_artifact",
                return_value=compatibility_model,
            ),
            mock.patch.object(
                router,
                "_load_encoder",
                return_value=mock.sentinel.encoder,
            ),
            mock.patch.object(router, "route", return_value=expected) as route,
            mock.patch.object(router, "write_submission_atomic") as write,
        ):
            result = router.main(
                (
                    "--input",
                    "/challenge/input/inputs.json",
                    "--tier",
                    "balanced",
                    "--output",
                    str(output),
                )
            )

        self.assertEqual(0, result)
        route.assert_called_once()
        write.assert_called_once_with(output, expected)


if __name__ == "__main__":
    unittest.main()
