#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Fetch and verify the pinned E5 ONNX runtime files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "configs/e5-model.v1.json"
DEFAULT_OUTPUT = ROOT / "build/e5-model"
PINNED_MODEL_ID = "intfloat/multilingual-e5-small"
PINNED_REVISION = "fd1525a9fd15316a2d503bf26ab031a61d056e98"
PINNED_SOURCE = "https://huggingface.co/intfloat/multilingual-e5-small"
REQUIRED_FILES = frozenset(("onnx/model.onnx", "onnx/tokenizer.json"))
CHUNK_SIZE = 1024 * 1024


class ModelSpecError(ValueError):
    """Raised when model provenance or downloaded bytes are invalid."""


@dataclass(frozen=True)
class E5ModelFile:
    path: PurePosixPath
    sha256: str
    size: int


@dataclass(frozen=True)
class E5ModelSpec:
    model_id: str
    revision: str
    license: str
    source: str
    files: Tuple[E5ModelFile, ...]


@dataclass(frozen=True)
class FetchResult:
    path: Path
    status: str


def _exact_object(
    value: Any,
    expected: Iterable[str],
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ModelSpecError(f"{label} must be an object")
    expected_keys = set(expected)
    missing = sorted(expected_keys - set(value))
    extra = sorted(set(value) - expected_keys)
    if missing or extra:
        raise ModelSpecError(f"{label} fields differ: missing={missing}, extra={extra}")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ModelSpecError(f"{label} must be a non-empty string")
    return value


def _sha256(value: Any, label: str) -> str:
    result = _text(value, label)
    if len(result) != 64 or any(
        character not in "0123456789abcdef" for character in result
    ):
        raise ModelSpecError(f"{label} must be a lowercase SHA-256 digest")
    return result


def _relative_path(value: Any, label: str) -> PurePosixPath:
    result = PurePosixPath(_text(value, label))
    if (
        result.is_absolute()
        or not result.parts
        or any(part in ("", ".", "..") for part in result.parts)
    ):
        raise ModelSpecError(f"{label} must be a safe relative POSIX path")
    return result


def load_model_spec(path: Path) -> E5ModelSpec:
    """Load the exact public E5 runtime-file specification."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelSpecError(f"cannot read model spec: {error}") from error
    root = _exact_object(
        value,
        ("schema_version", "model_id", "revision", "license", "source", "files"),
        "model spec",
    )
    if (
        isinstance(root["schema_version"], bool)
        or not isinstance(root["schema_version"], int)
        or root["schema_version"] != 1
    ):
        raise ModelSpecError("model spec schema_version must be 1")
    model_id = _text(root["model_id"], "model_id")
    revision = _text(root["revision"], "revision")
    license_name = _text(root["license"], "license")
    source = _text(root["source"], "source")
    if model_id != PINNED_MODEL_ID:
        raise ModelSpecError("model_id does not match the pinned E5 model")
    if revision != PINNED_REVISION:
        raise ModelSpecError("revision does not match the pinned E5 revision")
    if license_name != "MIT":
        raise ModelSpecError("E5 model license must be MIT")
    if source != PINNED_SOURCE:
        raise ModelSpecError("source does not match the pinned public repository")
    raw_files = root["files"]
    if not isinstance(raw_files, list):
        raise ModelSpecError("files must be an array")
    files = []
    for index, raw_file in enumerate(raw_files):
        row = _exact_object(
            raw_file,
            ("path", "sha256", "size"),
            f"files[{index}]",
        )
        size = row["size"]
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ModelSpecError(f"files[{index}].size must be a positive integer")
        files.append(
            E5ModelFile(
                path=_relative_path(row["path"], f"files[{index}].path"),
                sha256=_sha256(row["sha256"], f"files[{index}].sha256"),
                size=size,
            )
        )
    paths = tuple(file.path.as_posix() for file in files)
    if len(paths) != len(set(paths)):
        raise ModelSpecError("model file paths must be unique")
    if set(paths) != REQUIRED_FILES:
        raise ModelSpecError("files must contain exactly the ONNX model and tokenizer")
    return E5ModelSpec(
        model_id=model_id,
        revision=revision,
        license=license_name,
        source=source,
        files=tuple(files),
    )


def sha256_file(path: Path) -> str:
    """Hash one file without loading it into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_url(spec: E5ModelSpec, file: E5ModelFile) -> str:
    source = spec.source.rstrip("/")
    revision = urllib.parse.quote(spec.revision, safe="")
    relative_path = urllib.parse.quote(file.path.as_posix(), safe="/")
    return f"{source}/resolve/{revision}/{relative_path}"


def _is_valid_cached_file(path: Path, file: E5ModelFile) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == file.size
        and sha256_file(path) == file.sha256
    )


def _download_file(
    spec: E5ModelSpec,
    file: E5ModelFile,
    destination: Path,
    *,
    opener: Callable[..., Any],
) -> str:
    if _is_valid_cached_file(destination, file):
        return "cached"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            digest = hashlib.sha256()
            total = 0
            with opener(_download_url(spec, file), timeout=120) as response:
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    digest.update(chunk)
                    total += len(chunk)
                    temporary.write(chunk)
            temporary.flush()
            os.fsync(temporary.fileno())
        if total != file.size:
            raise ModelSpecError(
                f"size mismatch for {file.path}: expected {file.size}, got {total}"
            )
        actual_sha256 = digest.hexdigest()
        if actual_sha256 != file.sha256:
            raise ModelSpecError(f"SHA-256 mismatch for {file.path}")
        os.replace(temporary_path, destination)
        temporary_path = None
        return "downloaded"
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def fetch_model(
    spec_path: Path,
    output_root: Path,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> Tuple[FetchResult, ...]:
    """Fetch and verify every file in the pinned public specification."""

    spec = load_model_spec(spec_path)
    results = []
    for file in spec.files:
        destination = output_root.joinpath(*file.path.parts)
        results.append(
            FetchResult(
                path=destination,
                status=_download_file(
                    spec,
                    file,
                    destination,
                    opener=opener,
                ),
            )
        )
    return tuple(results)


def check_model(
    spec_path: Path,
    output_root: Path,
) -> Tuple[FetchResult, ...]:
    """Verify every local file in the pinned public specification."""

    spec = load_model_spec(spec_path)
    results = []
    for file in spec.files:
        destination = output_root.joinpath(*file.path.parts)
        if not destination.is_file():
            raise ModelSpecError(f"missing model file: {file.path}")
        actual_size = destination.stat().st_size
        if actual_size != file.size:
            raise ModelSpecError(
                f"size mismatch for {file.path}: "
                f"expected {file.size}, got {actual_size}"
            )
        if sha256_file(destination) != file.sha256:
            raise ModelSpecError(f"SHA-256 mismatch for {file.path}")
        results.append(
            FetchResult(
                path=destination,
                status="checked",
            )
        )
    return tuple(results)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        results = (
            check_model(args.spec, args.output)
            if args.check
            else fetch_model(args.spec, args.output)
        )
    except (OSError, ModelSpecError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for result in results:
        print(f"{result.status}: {result.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
