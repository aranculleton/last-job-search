"""Merging a release PR is the release: the newest CHANGELOG version is tagged and
published once, and no tag is ever moved, replaced or deleted.

3.3.0 sat merged and unpublished because publishing was a step on the GitHub website
that nothing reminded anyone of, and a session cannot push a tag.
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import release  # noqa: E402

TEXT = """# Changelog

## [Unreleased]

## [3.3.0] - 2026-10-19

### Added

- **Something new.** It does a thing.

## [3.2.5] - 2026-10-18

### Fixed

- **An old fix.**
"""


def test_the_newest_released_section_is_found_with_its_notes():
    got = release.sections(TEXT)
    assert [s["version"] for s in got] == ["3.3.0", "3.2.5"]
    assert got[0]["date"] == "2026-10-19"
    assert got[0]["notes"].startswith("### Added") and "An old fix" not in got[0]["notes"]


@pytest.mark.parametrize("existing,why", [
    (["v3.2.5", "v3.2.0"], ""),
    (["v3.3.0", "v3.2.5"], "v3.3.0 is already tagged"),
    (["v3.4.0"], "v3.3.0 is not newer than v3.4.0"),
])
def test_a_version_is_published_once_and_never_behind_the_newest_tag(existing, why):
    assert release.decide(release.sections(TEXT)[0], existing) == why


def test_only_unreleased_publishes_nothing():
    assert release.decide(None, []) .startswith("no released section")


def test_the_real_changelog_has_a_newest_version_with_notes():
    newest = release.sections()[0]
    assert newest["notes"] and newest["version"].count(".") == 2


def test_the_workflow_runs_only_in_the_app_and_never_moves_a_tag():
    yaml = pytest.importorskip("yaml")
    wf = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    doc = yaml.safe_load(wf)
    job = doc["jobs"]["release"]
    assert job["if"] == "github.repository == 'aranculleton/last-job-search'"
    assert doc["permissions"] == {"contents": "write"}
    assert "tools/release.py publish" in wf
    src = (ROOT / "tools/release.py").read_text(encoding="utf-8")
    for never in ("--force", "tag -d", "release delete", "push --delete", "--clobber",
                  ":refs/tags", "push --tags", "tag -f"):
        assert never not in wf and never not in src, never
