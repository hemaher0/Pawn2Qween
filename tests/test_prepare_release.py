# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "prepare_release.py"


def load_release_module():
    if not MODULE_PATH.is_file():
        raise AssertionError("tools/prepare_release.py does not exist")
    spec = importlib.util.spec_from_file_location("prepare_release", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PrepareReleaseTest(unittest.TestCase):
    def test_stable_tag_is_classified_as_latest_stable_release(self) -> None:
        release = load_release_module().parse_release_tag("v1.2.3")

        self.assertEqual("1.2.3", release.changelog_version)
        self.assertEqual("1.2.3", release.project_version)
        self.assertEqual("stable", release.channel)
        self.assertFalse(release.prerelease)
        self.assertTrue(release.make_latest)
        self.assertEqual("Stable v1.2.3", release.title)

    def test_prerelease_tag_is_classified_as_latest_channel(self) -> None:
        release = load_release_module().parse_release_tag("v2.0.0-rc.4")

        self.assertEqual("2.0.0-rc.4", release.changelog_version)
        self.assertEqual("2.0.0rc4", release.project_version)
        self.assertEqual("latest", release.channel)
        self.assertTrue(release.prerelease)
        self.assertFalse(release.make_latest)
        self.assertEqual("Latest v2.0.0-rc.4", release.title)

    def test_alpha_and_beta_tags_use_pep440_project_versions(self) -> None:
        module = load_release_module()

        self.assertEqual(
            "3.1.0a2",
            module.parse_release_tag("v3.1.0-alpha.2").project_version,
        )
        self.assertEqual(
            "3.1.0b7",
            module.parse_release_tag("v3.1.0-beta.7").project_version,
        )

    def test_invalid_version_tag_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid release tag"):
            load_release_module().parse_release_tag("v1.2")

    def test_release_notes_are_limited_to_the_requested_version(self) -> None:
        changelog = """# Changelog

## [Unreleased]

- Future work.

## [1.2.3] - 2026-08-11

### Added

- Stable release assets.

## [1.2.2] - 2026-08-01

- Older release.
"""

        notes = load_release_module().extract_release_notes(changelog, "1.2.3")

        self.assertEqual("### Added\n\n- Stable release assets.\n", notes)

    def test_missing_release_notes_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing changelog section"):
            load_release_module().extract_release_notes(
                "# Changelog\n\n## [Unreleased]\n\n- Work.\n",
                "1.2.3",
            )

    def test_duplicate_release_notes_are_rejected(self) -> None:
        changelog = """# Changelog

## [1.2.3] - 2026-08-11

- First.

## [1.2.3] - 2026-08-10

- Duplicate.
"""
        with self.assertRaisesRegex(ValueError, "duplicate changelog section"):
            load_release_module().extract_release_notes(changelog, "1.2.3")

    def test_empty_release_notes_are_rejected(self) -> None:
        changelog = """# Changelog

## [1.2.3] - 2026-08-11

## [1.2.2] - 2026-08-01

- Older release.
"""
        with self.assertRaisesRegex(ValueError, "empty changelog section"):
            load_release_module().extract_release_notes(changelog, "1.2.3")

    def test_prepare_release_writes_notes_and_github_outputs(self) -> None:
        module = load_release_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            project = root / "pyproject.toml"
            changelog = root / "CHANGELOG.md"
            notes = root / "release-notes.md"
            github_output = root / "github-output.txt"
            project.write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
            changelog.write_text(
                "# Changelog\n\n## [1.2.3] - 2026-08-11\n\n- Ready.\n",
                encoding="utf-8",
            )

            module.prepare_release(
                tag="v1.2.3",
                project_path=project,
                changelog_path=changelog,
                notes_path=notes,
                github_output_path=github_output,
            )

            self.assertEqual("- Ready.\n", notes.read_text(encoding="utf-8"))
            self.assertEqual(
                "channel=stable\n"
                "prerelease=false\n"
                "make_latest=true\n"
                "title=Stable v1.2.3\n",
                github_output.read_text(encoding="utf-8"),
            )

    def test_prepare_release_rejects_project_version_mismatch(self) -> None:
        module = load_release_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            project = root / "pyproject.toml"
            changelog = root / "CHANGELOG.md"
            project.write_text('[project]\nversion = "1.2.2"\n', encoding="utf-8")
            changelog.write_text(
                "# Changelog\n\n## [1.2.3] - 2026-08-11\n\n- Ready.\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "project version mismatch"):
                module.prepare_release(
                    tag="v1.2.3",
                    project_path=project,
                    changelog_path=changelog,
                    notes_path=root / "release-notes.md",
                    github_output_path=root / "github-output.txt",
                )

    def test_cli_prepares_release_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            project = root / "pyproject.toml"
            changelog = root / "CHANGELOG.md"
            notes = root / "release-notes.md"
            github_output = root / "github-output.txt"
            project.write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
            changelog.write_text(
                "# Changelog\n\n## [1.2.3] - 2026-08-11\n\n- Ready.\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--tag",
                    "v1.2.3",
                    "--project",
                    str(project),
                    "--changelog",
                    str(changelog),
                    "--notes-output",
                    str(notes),
                    "--github-output",
                    str(github_output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(notes.is_file())
            self.assertTrue(github_output.is_file())


if __name__ == "__main__":
    unittest.main()
