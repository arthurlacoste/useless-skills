import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import versioning
import changelog


def test_is_stable_tag():
    assert versioning.is_stable_tag("v1.2.3")
    assert not versioning.is_stable_tag("1.2.3")
    assert not versioning.is_stable_tag("v1.2")
    assert not versioning.is_stable_tag("v1.2.3-rc1")
    assert not versioning.is_stable_tag("vx.2.3")


def test_select_latest_stable_tag():
    tags = ["v0.1.0", "v1.2.3", "v1.2.10", "v0.9.9", "edge", "v2.0.0-rc1"]
    assert versioning.select_latest_stable_tag(tags) == "v1.2.10"


def test_select_latest_stable_tag_empty():
    assert versioning.select_latest_stable_tag(["edge", "beta"]) is None


def test_read_version():
    assert versioning.read_version()


def test_version_file_matches_changelog_latest(tmp_path):
    changelog_path = tmp_path / "CHANGELOG.md"
    changelog_path.write_text("# Changelog\n\n## 0.1.0\n\n### Added\n\n- stuff\n")
    assert changelog.version_notes(changelog_path, "0.1.0").strip().startswith("### Added")
    assert changelog.version_notes(changelog_path, "9.9.9") == ""


def test_changelog_notes_stop_at_next_version(tmp_path):
    changelog_path = tmp_path / "CHANGELOG.md"
    changelog_path.write_text(
        "# Changelog\n\n## 0.2.0\n\n### Added\n\n- newer\n\n## 0.1.0\n\n### Fixed\n\n- older\n"
    )
    notes = changelog.version_notes(changelog_path, "0.2.0")
    assert "newer" in notes
    assert "older" not in notes
