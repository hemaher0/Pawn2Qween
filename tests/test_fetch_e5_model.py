# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import io
import json
import pathlib
import tempfile
import unittest

from tools import fetch_e5_model as fetcher


MODEL_BYTES = b"model-bytes"
TOKENIZER_BYTES = b"tokenizer-bytes"


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _spec() -> dict[str, object]:
    return {
        "schema_version": 1,
        "model_id": "intfloat/multilingual-e5-small",
        "revision": "fd1525a9fd15316a2d503bf26ab031a61d056e98",
        "license": "MIT",
        "source": "https://huggingface.co/intfloat/multilingual-e5-small",
        "files": [
            {
                "path": "onnx/model.onnx",
                "sha256": _digest(MODEL_BYTES),
                "size": len(MODEL_BYTES),
            },
            {
                "path": "onnx/tokenizer.json",
                "sha256": _digest(TOKENIZER_BYTES),
                "size": len(TOKENIZER_BYTES),
            },
        ],
    }


class FetchE5ModelTest(unittest.TestCase):
    def _write_spec(self, directory: pathlib.Path, value=None) -> pathlib.Path:
        path = directory / "model.json"
        path.write_text(
            json.dumps(_spec() if value is None else value), encoding="utf-8"
        )
        return path

    def test_fetch_streams_verified_files_from_the_exact_revision(self) -> None:
        requested: list[str] = []

        def opener(url: str, *, timeout: int):
            requested.append(url)
            self.assertEqual(120, timeout)
            payload = TOKENIZER_BYTES if url.endswith("tokenizer.json") else MODEL_BYTES
            return io.BytesIO(payload)

        with tempfile.TemporaryDirectory() as raw_directory:
            directory = pathlib.Path(raw_directory)
            output = directory / "output"

            results = fetcher.fetch_model(
                self._write_spec(directory),
                output,
                opener=opener,
            )

            self.assertEqual(
                ("downloaded", "downloaded"), tuple(row.status for row in results)
            )
            self.assertEqual(MODEL_BYTES, (output / "onnx/model.onnx").read_bytes())
            self.assertEqual(
                TOKENIZER_BYTES,
                (output / "onnx/tokenizer.json").read_bytes(),
            )
            self.assertEqual(2, len(requested))
            for url in requested:
                self.assertIn(
                    "/resolve/fd1525a9fd15316a2d503bf26ab031a61d056e98/",
                    url,
                )
                self.assertNotIn("/resolve/main/", url)

    def test_valid_cached_files_do_not_call_the_network(self) -> None:
        def forbidden_opener(url: str, *, timeout: int):
            self.fail(f"network called for cached file: {url}, timeout={timeout}")

        with tempfile.TemporaryDirectory() as raw_directory:
            directory = pathlib.Path(raw_directory)
            output = directory / "output"
            (output / "onnx").mkdir(parents=True)
            (output / "onnx/model.onnx").write_bytes(MODEL_BYTES)
            (output / "onnx/tokenizer.json").write_bytes(TOKENIZER_BYTES)

            results = fetcher.fetch_model(
                self._write_spec(directory),
                output,
                opener=forbidden_opener,
            )

            self.assertEqual(("cached", "cached"), tuple(row.status for row in results))

    def test_corrupt_download_leaves_no_destination_or_temporary_file(self) -> None:
        def corrupt_opener(url: str, *, timeout: int):
            del url, timeout
            return io.BytesIO(b"wrong")

        with tempfile.TemporaryDirectory() as raw_directory:
            directory = pathlib.Path(raw_directory)
            output = directory / "output"

            with self.assertRaises(fetcher.ModelSpecError):
                fetcher.fetch_model(
                    self._write_spec(directory),
                    output,
                    opener=corrupt_opener,
                )

            self.assertFalse((output / "onnx/model.onnx").exists())
            self.assertEqual([], [path for path in output.rglob("*") if path.is_file()])

    def test_spec_rejects_unknown_fields_unsafe_paths_and_mutable_source(self) -> None:
        invalid_values = []
        unknown = _spec()
        unknown["unknown"] = True
        invalid_values.append(unknown)
        unsafe = _spec()
        unsafe["files"][0]["path"] = "../model.onnx"
        invalid_values.append(unsafe)
        mutable = _spec()
        mutable["revision"] = "main"
        invalid_values.append(mutable)
        wrong_source = _spec()
        wrong_source["source"] = "https://example.com/model"
        invalid_values.append(wrong_source)

        with tempfile.TemporaryDirectory() as raw_directory:
            directory = pathlib.Path(raw_directory)
            for index, value in enumerate(invalid_values):
                with self.subTest(index=index):
                    with self.assertRaises(fetcher.ModelSpecError):
                        fetcher.load_model_spec(self._write_spec(directory, value))

    def test_spec_requires_exact_runtime_file_set(self) -> None:
        value = _spec()
        value["files"] = value["files"][:1]

        with tempfile.TemporaryDirectory() as raw_directory:
            directory = pathlib.Path(raw_directory)
            with self.assertRaises(fetcher.ModelSpecError):
                fetcher.load_model_spec(self._write_spec(directory, value))


if __name__ == "__main__":
    unittest.main()
