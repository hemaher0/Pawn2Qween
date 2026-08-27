#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Preflight one local ARM64 submission image against the hard limits."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
for import_root in (ROOT, ROOT / "src"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from ossp_router.image_evidence import (  # noqa: E402
    _measure_export_tar,
    measure_oci_layout,
)
from ossp_router.protocol import (  # noqa: E402
    TIERS,
    ProtocolError,
    dumps_json,
    load_input,
)
from ossp_router.runtime import (  # noqa: E402
    OFFICIAL_CONTAINER_PLATFORM,
    OCI_LAYER_MEASUREMENT_METHOD,
    PHASE_C_CANDIDATE_LIMITS,
    ROOTFS_MEASUREMENT_METHOD,
    AttemptKind,
    AttemptResult,
    ImagePreflightRejected,
    InfrastructureUnavailable,
    inspect_image_runtime_metadata,
    prepare_operator_directory,
    validate_image_configuration,
)
from tools import check_runtime  # noqa: E402


_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_MAX_INDEX_BYTES = 1024 * 1024


def _json_object(path: Path) -> Mapping[str, Any]:
    try:
        if path.stat().st_size > _MAX_INDEX_BYTES:
            raise ValueError("OCI index is too large")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read OCI index: {error}") from error
    if not isinstance(value, Mapping):
        raise ValueError("OCI index must be an object")
    return value


def read_arm64_root_digest(oci_layout: Path) -> str:
    """Return the single linux/arm64 root descriptor from a Buildx layout."""

    manifests = _json_object(oci_layout / "index.json").get("manifests")
    if not isinstance(manifests, list):
        raise ValueError("OCI index manifests must be an array")
    candidates = []
    for descriptor in manifests:
        if not isinstance(descriptor, Mapping):
            continue
        platform = descriptor.get("platform")
        digest = descriptor.get("digest")
        if (
            isinstance(platform, Mapping)
            and platform.get("os") == "linux"
            and platform.get("architecture") == "arm64"
            and isinstance(digest, str)
            and _DIGEST.fullmatch(digest) is not None
        ):
            candidates.append(digest)
    if len(candidates) != 1:
        raise ValueError("OCI layout must contain one linux/arm64 root descriptor")
    return candidates[0]


def measure_local_rootfs(
    docker: str,
    image: str,
    work_directory: Path,
) -> int:
    """Measure the merged filesystem with the official bounded export reader."""

    operator_directory = prepare_operator_directory(
        work_directory,
        "local image preflight directory",
        parents=True,
    )
    return _measure_export_tar(
        (docker,),
        image,
        OFFICIAL_CONTAINER_PLATFORM,
        operator_directory / "image-measurement-journal.json",
    )


def run_constrained_smoke(
    docker: str,
    image_id: str,
    input_path: Path,
    tier: str,
    work_directory: Path,
) -> AttemptResult:
    """Run one real router invocation with the official isolation limits."""

    operator_directory = prepare_operator_directory(
        work_directory,
        "local image preflight directory",
        parents=True,
    )
    inputs = load_input(input_path)
    with tempfile.TemporaryDirectory(
        prefix="smoke-",
        dir=operator_directory,
    ) as raw_target:
        target = Path(raw_target)
        target.chmod(0o700)
        return check_runtime._run_once(
            docker=docker,
            image_id=image_id,
            input_path=input_path,
            inputs=inputs,
            tier=tier,
            target=target,
            repetition=1,
        )


def docker_server_platform(docker: str) -> Optional[str]:
    """Return the Docker server platform used for the screening run."""

    return check_runtime._runtime_platform(docker)


def preflight_submission_image(
    *,
    docker: str,
    image: str,
    oci_layout: Path,
    input_path: Path,
    tier: str,
    work_directory: Path,
) -> Dict[str, Any]:
    """Cross-bind OCI size evidence, a loaded image, and one hard-limit smoke."""

    if tier not in TIERS:
        raise ValueError("unknown routing tier")
    root_digest = read_arm64_root_digest(oci_layout)
    local_digest = f"local/e5-preflight@{root_digest}"
    selected_digest, config_digest, compressed_bytes = measure_oci_layout(
        oci_layout,
        local_digest,
    )
    metadata = inspect_image_runtime_metadata(
        (docker,),
        image,
        platform=OFFICIAL_CONTAINER_PLATFORM,
    )
    validate_image_configuration(metadata)
    if metadata.get("Os") != "linux" or metadata.get("Architecture") not in {
        "arm64",
        "aarch64",
    }:
        raise RuntimeError("loaded image is not linux/arm64")
    image_id = metadata.get("Id")
    if image_id != config_digest:
        raise RuntimeError("loaded image ID does not match the OCI config digest")

    rootfs_bytes = measure_local_rootfs(docker, image_id, work_directory)
    limits = PHASE_C_CANDIDATE_LIMITS
    if compressed_bytes > limits.oci_compressed_image_bytes:
        raise RuntimeError("compressed image layers exceed the hard limit")
    if rootfs_bytes > limits.rootfs_apparent_bytes:
        raise RuntimeError("merged root filesystem exceeds the hard limit")

    smoke_result = run_constrained_smoke(
        docker,
        image_id,
        input_path,
        tier,
        work_directory,
    )
    smoke = check_runtime._result_record(smoke_result, 1)
    input_payload = input_path.read_bytes()
    inputs = load_input(input_path)
    server_platform = docker_server_platform(docker)
    native_arm64 = server_platform == OFFICIAL_CONTAINER_PLATFORM
    passed = smoke_result.kind is AttemptKind.VALID
    limitations = [
        "This local toy smoke does not run the required full Train+Dev "
        "native ARM64 latency gate."
    ]
    if not native_arm64:
        limitations.append(
            "The Docker server is not native linux/arm64; smoke latency is "
            "compatibility evidence only."
        )
    return {
        "schema_version": 1,
        "report_type": "submission-image-local-preflight",
        "evidence_scope": "hard-limits-and-compatibility-screening",
        "image": {
            "requested_reference": image,
            "loaded_config_digest": image_id,
            "oci_manifest_digest": selected_digest,
            "platform": OFFICIAL_CONTAINER_PLATFORM,
        },
        "image_size": {
            "compressed_layers_bytes": compressed_bytes,
            "compressed_layers_limit_bytes": limits.oci_compressed_image_bytes,
            "compressed_layers_measurement_method": OCI_LAYER_MEASUREMENT_METHOD,
            "rootfs_apparent_bytes": rootfs_bytes,
            "rootfs_apparent_limit_bytes": limits.rootfs_apparent_bytes,
            "rootfs_measurement_method": ROOTFS_MEASUREMENT_METHOD,
            "passed": True,
        },
        "runtime": {
            "docker_server_platform": server_platform,
            "official_platform": OFFICIAL_CONTAINER_PLATFORM,
            "native_arm64": native_arm64,
            "cpu_cores": limits.cpu_cores,
            "memory_bytes": limits.memory_bytes,
            "memory_swap_total_bytes": limits.memory_swap_total_bytes,
            "processes_and_threads_total": limits.processes_and_threads_total,
            "wall_time_seconds": limits.wall_time_seconds,
        },
        "workload": {
            "basis": "toy-smoke",
            "episodes": len(inputs.episodes),
            "bytes": len(input_payload),
            "sha256": hashlib.sha256(input_payload).hexdigest(),
        },
        "smoke": smoke,
        "passed": passed,
        "submission_ready": False,
        "full_native_runtime_gate": {
            "required": True,
            "status": "not-run",
        },
        "limitations": limitations,
    }


def write_report_atomic(path: Path, report: Mapping[str, Any]) -> None:
    """Atomically replace one generated local preflight report."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise OSError("report path must not be a symbolic link")
    payload = dumps_json(report).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.close(descriptor)
        descriptor = -1
        temporary.chmod(0o644)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--oci-layout", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--tier", choices=TIERS, default="balanced")
    parser.add_argument("--work-directory", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--docker-command", default="docker")
    return parser


def _print_summary(report: Mapping[str, Any]) -> None:
    sizes = report["image_size"]
    smoke = report["smoke"]
    print(
        "OCI compressed layers: "
        f"{sizes['compressed_layers_bytes']} / "
        f"{sizes['compressed_layers_limit_bytes']} bytes"
    )
    print(
        "Merged rootfs apparent size: "
        f"{sizes['rootfs_apparent_bytes']} / "
        f"{sizes['rootfs_apparent_limit_bytes']} bytes"
    )
    print(
        "Constrained E5 smoke: "
        f"{'PASS' if smoke['passed'] else 'FAIL'} "
        f"({smoke['elapsed_seconds']} / {report['runtime']['wall_time_seconds']} s)"
    )
    for limitation in report["limitations"]:
        print(f"INCONCLUSIVE: {limitation}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        docker = check_runtime._resolve_docker(args.docker_command)
        report = preflight_submission_image(
            docker=docker,
            image=args.image,
            oci_layout=args.oci_layout,
            input_path=args.input,
            tier=args.tier,
            work_directory=args.work_directory,
        )
        write_report_atomic(args.report, report)
    except (
        ImagePreflightRejected,
        InfrastructureUnavailable,
        OSError,
        ProtocolError,
        RuntimeError,
        ValueError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    _print_summary(report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
