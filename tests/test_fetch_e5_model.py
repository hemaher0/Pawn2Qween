# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

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

    def test_check_cli_reports_exact_local_files_as_checked(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = pathlib.Path(raw_directory)
            output = directory / "output"
            (output / "onnx").mkdir(parents=True)
            model_path = output / "onnx/model.onnx"
            tokenizer_path = output / "onnx/tokenizer.json"
            model_path.write_bytes(MODEL_BYTES)
            tokenizer_path.write_bytes(TOKENIZER_BYTES)
            stdout = io.StringIO()
            stderr = io.StringIO()

            try:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    status = fetcher.main(
                        [
                            "--spec",
                            str(self._write_spec(directory)),
                            "--output",
                            str(output),
                            "--check",
                        ]
                    )
            except SystemExit as error:
                status = error.code

            self.assertEqual(0, status, stderr.getvalue())
            self.assertEqual(
                f"checked: {model_path}\nchecked: {tokenizer_path}\n",
                stdout.getvalue(),
            )
            self.assertEqual(MODEL_BYTES, model_path.read_bytes())
            self.assertEqual(TOKENIZER_BYTES, tokenizer_path.read_bytes())

    def test_check_rejects_a_missing_file_without_creating_it(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = pathlib.Path(raw_directory)
            output = directory / "output"
            (output / "onnx").mkdir(parents=True)
            model_path = output / "onnx/model.onnx"
            tokenizer_path = output / "onnx/tokenizer.json"
            model_path.write_bytes(MODEL_BYTES)

            with (
                mock.patch.object(
                    fetcher,
                    "_download_file",
                    side_effect=AssertionError("check mode attempted a download"),
                ),
                self.assertRaisesRegex(
                    fetcher.ModelSpecError,
                    "onnx/tokenizer.json",
                ),
            ):
                fetcher.check_model(self._write_spec(directory), output)

            self.assertEqual(MODEL_BYTES, model_path.read_bytes())
            self.assertFalse(tokenizer_path.exists())

    def test_check_rejects_same_size_corruption_without_replacing_it(self) -> None:
        corrupt_model = b"MODEL-bytes"
        self.assertEqual(len(MODEL_BYTES), len(corrupt_model))
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = pathlib.Path(raw_directory)
            output = directory / "output"
            (output / "onnx").mkdir(parents=True)
            model_path = output / "onnx/model.onnx"
            tokenizer_path = output / "onnx/tokenizer.json"
            model_path.write_bytes(corrupt_model)
            tokenizer_path.write_bytes(TOKENIZER_BYTES)

            with (
                mock.patch.object(
                    fetcher,
                    "_download_file",
                    side_effect=AssertionError("check mode attempted a download"),
                ),
                self.assertRaisesRegex(
                    fetcher.ModelSpecError,
                    "SHA-256 mismatch for onnx/model.onnx",
                ),
            ):
                fetcher.check_model(self._write_spec(directory), output)

            self.assertEqual(corrupt_model, model_path.read_bytes())
            self.assertEqual(TOKENIZER_BYTES, tokenizer_path.read_bytes())

    def test_check_rejects_wrong_size_without_replacing_it(self) -> None:
        truncated_model = MODEL_BYTES[:-1]
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = pathlib.Path(raw_directory)
            output = directory / "output"
            (output / "onnx").mkdir(parents=True)
            model_path = output / "onnx/model.onnx"
            tokenizer_path = output / "onnx/tokenizer.json"
            model_path.write_bytes(truncated_model)
            tokenizer_path.write_bytes(TOKENIZER_BYTES)

            with (
                mock.patch.object(
                    fetcher,
                    "_download_file",
                    side_effect=AssertionError("check mode attempted a download"),
                ),
                self.assertRaisesRegex(
                    fetcher.ModelSpecError,
                    "size mismatch for onnx/model.onnx",
                ),
            ):
                fetcher.check_model(self._write_spec(directory), output)

            self.assertEqual(truncated_model, model_path.read_bytes())
            self.assertEqual(TOKENIZER_BYTES, tokenizer_path.read_bytes())

    def test_check_cli_returns_two_for_a_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = pathlib.Path(raw_directory)
            output = directory / "output"
            (output / "onnx").mkdir(parents=True)
            model_path = output / "onnx/model.onnx"
            tokenizer_path = output / "onnx/tokenizer.json"
            model_path.write_bytes(MODEL_BYTES)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = fetcher.main(
                    [
                        "--spec",
                        str(self._write_spec(directory)),
                        "--output",
                        str(output),
                        "--check",
                    ]
                )

            self.assertEqual(2, status)
            self.assertEqual("", stdout.getvalue())
            self.assertEqual(
                "error: missing model file: onnx/tokenizer.json\n",
                stderr.getvalue(),
            )
            self.assertEqual(MODEL_BYTES, model_path.read_bytes())
            self.assertFalse(tokenizer_path.exists())

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
