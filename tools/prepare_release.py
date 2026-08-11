# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

"""Validate a release tag and prepare GitHub Release metadata."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence


STABLE_TAG_RE = re.compile(r"v(?P<version>\d+\.\d+\.\d+)")
PRERELEASE_TAG_RE = re.compile(
    r"v(?P<base>\d+\.\d+\.\d+)-(?P<kind>alpha|beta|rc)\.(?P<number>\d+)"
)
PEP440_PRERELEASE_KIND = {"alpha": "a", "beta": "b", "rc": "rc"}
CHANGELOG_SECTION_RE = re.compile(
    r"^## \[(?P<version>[^]]+)\](?: - [^\n]+)?\s*$",
    re.MULTILINE,
)
PROJECT_SECTION_RE = re.compile(
    r"^\[project\]\s*$\n(?P<body>.*?)(?=^\[|\Z)",
    re.MULTILINE | re.DOTALL,
)
PROJECT_VERSION_RE = re.compile(
    r"^version\s*=\s*(?P<quote>['\"])(?P<version>[^'\"]+)(?P=quote)\s*$",
    re.MULTILINE,
)
ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ReleaseTag:
    changelog_version: str
    project_version: str
    channel: str
    prerelease: bool
    make_latest: bool
    title: str


def parse_release_tag(tag: str) -> ReleaseTag:
    """Parse one supported SemVer tag into release metadata."""

    match = STABLE_TAG_RE.fullmatch(tag)
    if match is not None:
        version = match.group("version")
        return ReleaseTag(
            changelog_version=version,
            project_version=version,
            channel="stable",
            prerelease=False,
            make_latest=True,
            title=f"Stable {tag}",
        )

    match = PRERELEASE_TAG_RE.fullmatch(tag)
    if match is not None:
        kind = match.group("kind")
        changelog_version = tag.removeprefix("v")
        project_version = (
            f"{match.group('base')}{PEP440_PRERELEASE_KIND[kind]}"
            f"{match.group('number')}"
        )
        return ReleaseTag(
            changelog_version=changelog_version,
            project_version=project_version,
            channel="latest",
            prerelease=True,
            make_latest=False,
            title=f"Latest {tag}",
        )

    raise ValueError(f"invalid release tag: {tag}")


def extract_release_notes(changelog: str, version: str) -> str:
    """Return the non-empty body of exactly one versioned changelog section."""

    sections = list(CHANGELOG_SECTION_RE.finditer(changelog))
    matches = [match for match in sections if match.group("version") == version]
    if not matches:
        raise ValueError(f"missing changelog section: {version}")
    if len(matches) > 1:
        raise ValueError(f"duplicate changelog section: {version}")

    match = matches[0]
    index = sections.index(match)
    end = sections[index + 1].start() if index + 1 < len(sections) else len(changelog)
    notes = changelog[match.end() : end].strip()
    if not notes:
        raise ValueError(f"empty changelog section: {version}")
    return notes + "\n"


def read_project_version(pyproject: str) -> str:
    """Read the static version from the PEP 621 project table."""

    project_sections = list(PROJECT_SECTION_RE.finditer(pyproject))
    if len(project_sections) != 1:
        raise ValueError("pyproject.toml must contain exactly one [project] table")

    versions = list(PROJECT_VERSION_RE.finditer(project_sections[0].group("body")))
    if len(versions) != 1:
        raise ValueError("[project] must contain exactly one static version")
    return versions[0].group("version")


def prepare_release(
    *,
    tag: str,
    project_path: Path,
    changelog_path: Path,
    notes_path: Path,
    github_output_path: Path,
) -> ReleaseTag:
    """Validate release inputs and write notes plus GitHub step outputs."""

    release = parse_release_tag(tag)
    project_version = read_project_version(project_path.read_text(encoding="utf-8"))
    if project_version != release.project_version:
        raise ValueError(
            "project version mismatch: "
            f"tag requires {release.project_version}, found {project_version}"
        )

    notes = extract_release_notes(
        changelog_path.read_text(encoding="utf-8"),
        release.changelog_version,
    )
    notes_path.write_text(notes, encoding="utf-8")
    github_output_path.write_text(
        f"channel={release.channel}\n"
        f"prerelease={str(release.prerelease).lower()}\n"
        f"make_latest={str(release.make_latest).lower()}\n"
        f"title={release.title}\n",
        encoding="utf-8",
    )
    return release


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a release tag and prepare GitHub Release metadata."
    )
    parser.add_argument("--tag", required=True, help="Git tag to release")
    parser.add_argument(
        "--project",
        type=Path,
        default=ROOT / "pyproject.toml",
        help="Path to pyproject.toml",
    )
    parser.add_argument(
        "--changelog",
        type=Path,
        default=ROOT / "CHANGELOG.md",
        help="Path to CHANGELOG.md",
    )
    parser.add_argument(
        "--notes-output",
        type=Path,
        required=True,
        help="Path for the extracted release notes",
    )
    parser.add_argument(
        "--github-output",
        type=Path,
        required=True,
        help="Path supplied by the GITHUB_OUTPUT environment variable",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    prepare_release(
        tag=args.tag,
        project_path=args.project,
        changelog_path=args.changelog,
        notes_path=args.notes_output,
        github_output_path=args.github_output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
