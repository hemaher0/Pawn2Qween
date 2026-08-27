# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import math
import pathlib
import tempfile
import types
import unittest

try:
    import numpy as np
except ModuleNotFoundError as error:
    raise unittest.SkipTest("E5 encoder tests require NumPy") from error

from ossp_router import e5_artifact as compatibility
from ossp_router import e5_encoder as encoder_module


class _Encoding:
    def __init__(self, ids):
        self.ids = list(ids)


class _Tokenizer:
    def __init__(self):
        self.prepared_texts = []
        self.decoded_ids = []

    def token_to_id(self, token):
        return 0 if token == "<pad>" else None

    def encode(self, text, *, add_special_tokens):
        if not add_special_tokens:
            if text.startswith("tokens:"):
                return _Encoding(range(int(text.removeprefix("tokens:"))))
            return _Encoding(range(len(text.split())))
        self.prepared_texts.append(text)
        payload = text.removeprefix(encoder_module.PREFIX)
        if payload == "decoded":
            body = [7]
        else:
            body = [len(word) + 1 for word in payload.split()]
        return _Encoding([101, *body, 102])

    def decode(self, ids, *, skip_special_tokens):
        if not skip_special_tokens:
            raise AssertionError("selected content must skip special tokens")
        self.decoded_ids.append(tuple(ids))
        return "decoded"


class _Session:
    def __init__(self, *, providers=None, inputs=None, output_mode="valid"):
        self._providers = providers or ["CPUExecutionProvider"]
        self._inputs = inputs or ("input_ids", "attention_mask")
        self.output_mode = output_mode
        self.feeds = []

    def get_providers(self):
        return list(self._providers)

    def get_inputs(self):
        return [types.SimpleNamespace(name=name) for name in self._inputs]

    def run(self, output_names, feeds):
        self.assert_output_names(output_names)
        self.feeds.append(
            {key: np.array(value, copy=True) for key, value in feeds.items()}
        )
        rows, width = feeds["input_ids"].shape
        dimensions = (
            encoder_module.EMBEDDING_DIMENSION - 1
            if self.output_mode == "wrong-shape"
            else encoder_module.EMBEDDING_DIMENSION
        )
        hidden = np.zeros((rows, width, dimensions), dtype=np.float32)
        if self.output_mode != "zero":
            hidden[:, :, 0] = 1.0
            hidden[:, :, 1] = feeds["input_ids"]
        if self.output_mode == "nan":
            hidden[0, 0, 0] = np.nan
        return [hidden]

    @staticmethod
    def assert_output_names(output_names):
        if output_names is not None:
            raise AssertionError("encoder must request all model outputs")


def _identity(**changes):
    values = {
        "model_id": compatibility.PINNED_MODEL_ID,
        "revision": compatibility.PINNED_REVISION,
        "onnx_sha256": encoder_module.PINNED_ONNX_SHA256,
        "tokenizer_sha256": encoder_module.PINNED_TOKENIZER_SHA256,
        "preprocessing_id": compatibility.PREPROCESSING_ID,
    }
    values.update(changes)
    return compatibility.E5EncoderIdentity(**values)


def _encoder(directory, tokenizer, session, **kwargs):
    return encoder_module.E5OnnxEncoder(
        pathlib.Path(directory),
        identity=_identity(),
        tokenizer_factory=lambda path: tokenizer,
        session_factory=lambda path: session,
        **kwargs,
    )


class E5OnnxEncoderTest(unittest.TestCase):
    def test_prefixes_once_and_keeps_240_head_plus_240_tail_tokens(self) -> None:
        tokenizer = _Tokenizer()
        session = _Session()
        with tempfile.TemporaryDirectory() as directory:
            encoder = _encoder(directory, tokenizer, session)

            encoder.encode_texts(("plain text", "tokens:481"))

        self.assertEqual(
            ("query: plain text", "query: decoded"), tuple(tokenizer.prepared_texts)
        )
        self.assertEqual(1, len(tokenizer.decoded_ids))
        expected = tuple(range(240)) + tuple(range(241, 481))
        self.assertEqual(expected, tokenizer.decoded_ids[0])

    def test_pooling_excludes_padding_and_preserves_input_order(self) -> None:
        tokenizer = _Tokenizer()
        session = _Session()
        with tempfile.TemporaryDirectory() as directory:
            encoder = _encoder(directory, tokenizer, session)
            together = encoder.encode_texts(("a", "a bb ccc"))
            alone = encoder.encode_texts(("a",))

        self.assertEqual(2, len(together))
        self.assertEqual(encoder_module.EMBEDDING_DIMENSION, len(together[0]))
        self.assertEqual(alone[0], together[0])
        self.assertNotEqual(together[0], together[1])
        for vector in together:
            self.assertAlmostEqual(
                1.0,
                math.sqrt(sum(value * value for value in vector)),
                places=6,
            )
        mixed_feed = session.feeds[0]
        self.assertEqual((2, 5), mixed_feed["attention_mask"].shape)
        self.assertEqual((1, 1, 1, 0, 0), tuple(mixed_feed["attention_mask"][0]))
        self.assertEqual((1, 1, 1, 1, 1), tuple(mixed_feed["attention_mask"][1]))

    def test_empty_input_returns_empty_tuple_without_running_session(self) -> None:
        tokenizer = _Tokenizer()
        session = _Session()
        with tempfile.TemporaryDirectory() as directory:
            encoder = _encoder(directory, tokenizer, session)

            result = encoder.encode_texts(())

        self.assertEqual((), result)
        self.assertEqual([], session.feeds)

    def test_constructor_rejects_provider_fallback_and_identity_mismatch(self) -> None:
        tokenizer = _Tokenizer()
        fallback = _Session(
            providers=["AzureExecutionProvider", "CPUExecutionProvider"]
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                _encoder(directory, tokenizer, fallback)
            with self.assertRaises(ValueError):
                encoder_module.E5OnnxEncoder(
                    pathlib.Path(directory),
                    identity=_identity(onnx_sha256="e" * 64),
                    tokenizer_factory=lambda path: tokenizer,
                    session_factory=lambda path: _Session(),
                )

    def test_rejects_unexpected_inputs_and_invalid_outputs(self) -> None:
        cases = (
            _Session(inputs=("input_ids", "attention_mask", "unexpected")),
            _Session(output_mode="wrong-shape"),
            _Session(output_mode="zero"),
            _Session(output_mode="nan"),
        )
        with tempfile.TemporaryDirectory() as directory:
            for session in cases:
                with self.subTest(session=session):
                    encoder = _encoder(directory, _Tokenizer(), session)
                    with self.assertRaises(RuntimeError):
                        encoder.encode_texts(("plain",))

    def test_rejects_empty_text_and_impossible_batch_limits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                _encoder(
                    directory,
                    _Tokenizer(),
                    _Session(),
                    max_batch_rows=0,
                )
            encoder = _encoder(directory, _Tokenizer(), _Session())
            with self.assertRaises(ValueError):
                encoder.encode_texts(("",))


if __name__ == "__main__":
    unittest.main()
