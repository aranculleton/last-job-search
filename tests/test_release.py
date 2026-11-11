"""Merging a release PR is the release: the newest CHANGELOG version is tagged and
published once, and no tag is ever moved, replaced or deleted.

3.3.0 sat merged and unpublished because publishing was a step on the GitHub website
that nothing reminded anyone of, and a session cannot push a tag.
"""
import json
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import release  # noqa: E402
import repo_files  # noqa: E402
from test_a_beginner_is_told_in_plain_words import _plain  # noqa: E402

TEXT = """# Changelog

## [Unreleased]

## [3.3.0] - 2026-10-19

### Added

- **Something new.** It does a thing at great length, over several lines, the way a
  CHANGELOG entry does. Profile upgrade: method-networking.
- **A question for you.** It asks once. Profile upgrade: `connections-export`.
- **Headings that stop short** read as sentences too.
- **Or end on a colon:** like this.

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
    # Issues too: a release closes the bugs from the maintainer's copy it fixed.
    assert doc["permissions"] == {"contents": "write", "issues": "write"}
    assert "tools/release.py publish" in wf
    # Merging the version's own pull request is the release: it lands on master and changes
    # CHANGELOG.md, the section `cut` named, which is what starts this workflow.
    on = doc.get("on", doc.get(True))
    assert on["push"]["branches"] == ["master"] and "CHANGELOG.md" in on["push"]["paths"]
    src = (ROOT / "tools/release.py").read_text(encoding="utf-8")
    for never in ("--force", "tag -d", "release delete", "push --delete", "--clobber",
                  ":refs/tags", "push --tags", "tag -f"):
        assert never not in wf and never not in src, never


def test_the_notes_a_person_reads_are_one_line_per_change_and_one_on_what_to_do():
    notes = release.short(release.sections(TEXT)[0]["notes"])
    lines = notes.splitlines()
    # The section's first entry is its headline, said first, on its own.
    assert lines[:3] == ["Something new. (set up for you)", "", "**New**"]
    assert "- A question for you. (Claude asks you once)" in lines
    assert "- Headings that stop short." in lines and "- Or end on a colon." in lines
    # A big release shows the first few of each kind and counts the rest.
    many = release.short("### Fixed\n\n" + "".join(f"- **Fix {i}.**\n" for i in range(13)))
    fixed = [ln for ln in many.splitlines() if ln.startswith("- ")]
    assert fixed[:release.MAX_PER_GROUP] == [f"- Fix {i}." for i in range(1, release.MAX_PER_GROUP + 1)]
    assert fixed[-1].startswith("- And 4 more (https://") and len(fixed) == release.MAX_PER_GROUP + 1
    # A release of fixes alone has nothing to set up, and says only that it is taken.
    fixes = release.short("### Fixed\n\n- **An old fix.**\n")
    assert fixes.splitlines()[-1] == "What to do: nothing. Your next chat takes this update."
    assert "at great length" not in notes and "Profile upgrade" not in notes
    assert lines[-1] == ("What to do: nothing. Your next chat takes this update and sets it up, "
                         "and asks you 1 short question once.")


def test_a_released_versions_notes_are_rewritten_and_its_tag_never_touched(monkeypatch):
    calls = []

    class Done:
        def __init__(self, out=""):
            self.returncode, self.stdout, self.stderr = 0, out, ""

    def fake(args):
        calls.append(args)
        return Done("the old wall of text") if args[:2] == ["release", "view"] else Done()
    monkeypatch.setattr(release, "_gh", fake)
    monkeypatch.setattr(release, "tags", lambda: ["v3.3.0", "v3.2.5"])
    sample = release.sections(TEXT)
    monkeypatch.setattr(release, "sections", lambda text=None: sample)
    assert release.publish() == 0
    assert [c[:2] for c in calls] == [["release", "view"], ["release", "edit"]]
    assert not any(c[:2] == ["release", "create"] for c in calls)


# ------------------------------------------------------------------ cut: the version names itself

# 4.15.0's rename of [Unreleased] was a second pull request with the whole of CI, and took
# 1h55m from the merge to the tag (the release audit, 2026-11-11). `cut` names and dates the
# version on its own pull request, so merging that is the release.

UNRELEASED = """# Changelog

## [Unreleased]

### Fixed

- **A fix.** Over two
  lines.

### Added

- **Something new.**

### Changed

- **A change.**

## [3.3.0] - 2026-10-19

### Fixed

- **An old fix.**
"""
HEADLINE = "Interview packs open with where the process stands."


def _copy(tmp_path, text=UNRELEASED, note="Written at the release of 3.4.0.\n"):
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")
    (tmp_path / "docs" / "NEXT_BUILDER.md").write_text(note, encoding="utf-8")
    return str(tmp_path)


def _said(capsys) -> str:
    out = capsys.readouterr().out
    _plain(out)
    return out


def test_cut_names_the_version_and_opens_it_on_its_headline(tmp_path, monkeypatch, capsys):
    root = _copy(tmp_path)
    monkeypatch.setattr(release, "tags", lambda root=None: ["v3.3.0"])
    assert release.cut("3.4.0", HEADLINE, root=root, day="2026-10-20") == 0
    assert "Nothing is committed" in _said(capsys)
    text = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert text.startswith("# Changelog\n\n## [Unreleased]\n\n## [3.4.0] - 2026-10-20\n\n"
                           "### Changed\n\n- **" + HEADLINE + "**\n- **A change.**\n")
    newest = release.sections(text)[0]
    assert newest["version"] == "3.4.0" and newest["date"] == "2026-10-20"
    # Every entry kept, once, and the release before untouched.
    for entry in ("- **A fix.** Over two\n  lines.", "- **Something new.**", "- **A change.**"):
        assert text.count(entry) == 1 and entry in newest["notes"], entry
    assert text.count("### Changed") == 1
    assert text.endswith("## [3.3.0] - 2026-10-19\n\n### Fixed\n\n- **An old fix.**\n")
    # It is the release the workflow publishes once the pull request lands.
    assert release.decide(newest, ["v3.3.0"]) == ""
    # A section with no Changed heading of its own gets one, for the headline alone.
    root = _copy(tmp_path / "plain", UNRELEASED.replace("### Changed\n\n- **A change.**\n\n", ""))
    assert release.cut("3.4.0", HEADLINE, root=root, day="2026-10-20") == 0
    text = (tmp_path / "plain" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "### Changed\n\n- **" + HEADLINE + "**\n\n### Fixed\n" in text


@pytest.mark.parametrize("version,headline,text,note,why", [
    ("3.4.0", HEADLINE, "# Changelog\n\n## [Unreleased]\n\n### Fixed\n\n## [3.3.0] - 2026-10-19\n",
     None, "[Unreleased] has no entries"),
    ("3.3.0", HEADLINE, None, "3.3.0", "not newer than 3.3.0"),
    ("3.2.9", HEADLINE, None, "3.2.9", "not newer than 3.3.0"),
    ("3.5.0", HEADLINE, None, "3.5.0", "not newer than 3.6.0"),      # the newest tag
    ("v3.4", HEADLINE, None, None, "not a version number"),
    ("3.4.0", "x" * 141, None, None, "141 characters"),
    ("3.4.0", "", None, None, "the headline is empty"),
    ("3.4.0", "It is quicker. It is also kinder.", None, None, "more than one sentence"),
    ("3.4.0", "`ats_boards.py` reads more boards.", None, None, "code in it"),
    ("3.4.0", "The maintainer's own tests run faster.", None, None, "about the maintainer"),
    ("3.4.0", HEADLINE, None, "Written at the release of 3.4.10.", "does not name 3.4.0"),
    ("3.4.0", HEADLINE, None, "", "does not name 3.4.0"),
])
def test_cut_refuses_and_changes_nothing(tmp_path, monkeypatch, capsys, version, headline, text,
                                          note, why):
    root = _copy(tmp_path, text or UNRELEASED, note if note is not None else f"For {version}.")
    before = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    monkeypatch.setattr(release, "tags", lambda root=None: ["v3.3.0", "v3.6.0"]
                        if version == "3.5.0" else ["v3.3.0"])
    assert release.cut(version, headline, root=root) == 1
    assert why in _said(capsys)
    assert (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8") == before
    assert len("x" * 140) == release.HEADLINE_MAX and not release.headline_problem("x" * 140)


def test_cut_still_checks_the_changelog_when_github_cannot_be_read(tmp_path, monkeypatch, capsys):
    root = _copy(tmp_path, note="3.3.0")

    def offline(root=None):
        raise subprocess.CalledProcessError(128, "git ls-remote")
    monkeypatch.setattr(release, "tags", offline)
    assert release.cut("3.3.0", HEADLINE, root=root) == 1
    out = _said(capsys)
    assert "could not be read from here" in out and "not newer than 3.3.0" in out


def test_cut_needs_the_version_and_its_headline(capsys):
    assert release.main(["cut", "3.4.0"]) == 2
    assert 'cut X.Y.Z --headline "' in capsys.readouterr().out
    assert release.main(["cut", "--help"]) == 0
    assert "cut X.Y.Z --headline" in capsys.readouterr().out


def test_no_test_reads_unreleased_by_its_name_for_what_ships():
    """A test that found its entry under [Unreleased] by name failed the moment the release
    named the section (tests/test_an_interview_has_a_live_prep.py, 2026-11-11): a test finds
    the section that carries its entry instead."""
    by_name = re.compile(r"\.(?:index|find|rfind|split|partition|rpartition)\(\s*[\"']## \[Unreleased\]")
    found = [f"{p.name}:{n}" for p in repo_files.files("tests/**/*.py")
             for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
             if by_name.search(line)]
    assert found == []


# ------------------------------------------------------------------ the headline, then what is new

def test_the_notes_open_on_the_headline_then_new_changed_and_fixed():
    """4.15.0's notes showed eight fixes and "And 318 more" before its five new things, in the
    order the section was written (the release audit, 2026-11-11)."""
    section = ("### Changed\n\n- **The headline.**\n- **A change.**\n\n### Fixed\n\n- **A fix.**\n\n"
               "### Added\n\n- **A new thing.**\n\n### Removed\n\n- **Gone.**\n\n"
               "### Cheaper to run\n\n- **Cheaper.**\n\n### Fixed\n\n- **Another fix.**\n")
    assert release.short(section).splitlines()[:-1] == [
        "The headline.", "",
        "**New**", "- A new thing.", "",
        "**Changed**", "- A change.", "",
        "**Fixed**", "- A fix.", "- Another fix.", "",
        "**Removed**", "- Gone.", "",
        "**Cheaper to run**", "- Cheaper.", ""]


def test_the_newest_release_opens_on_a_headline_a_person_is_told_whole():
    """The one line a person who updates when they choose hears is the release's first entry
    (sync_app.brings), cut at 140 characters: `cut --headline` writes it, and every release
    since 4.15.0 opens on one."""
    newest = release.sections()[0]
    m = re.match(r"### Changed\n\n- \*\*(.+?)\*\*", newest["notes"])
    assert m, f"{newest['version']} does not open on a headline under its Changed heading"
    assert len(m.group(1)) <= release.HEADLINE_MAX, (len(m.group(1)), m.group(1))
    assert release.headline_problem(m.group(1)) == "", m.group(1)
    assert release.short(newest["notes"]).splitlines()[0].startswith(m.group(1).rstrip("."))


# ------------------------------------------------------------------ the copy's bugs it fixed


class _GitHub:
    """A fake `gh`: the open issues labelled fixed-unreleased, and every call made. No network."""

    def __init__(self, fixed=(), refuse=()):
        self.fixed, self.refuse, self.calls = list(fixed), set(refuse), []

    def __call__(self, args):
        self.calls.append(args)
        out, code = "", 0
        if args[:2] == ["issue", "list"]:
            out = json.dumps([{"number": n} for n in self.fixed])
        elif args[:2] == ["issue", "close"] and int(args[2]) in self.refuse:
            code = 1
        elif args[:2] == ["release", "view"]:
            out = "the old wall of text"
        return type("Done", (), {"returncode": code, "stdout": out, "stderr": ""})()


def test_a_release_closes_every_bug_fixed_since_the_last_one_and_takes_its_label_off(monkeypatch):
    gh = _GitHub(fixed=[211, 212])
    monkeypatch.setattr(release, "_gh", gh)
    monkeypatch.setattr(release, "tags", lambda: ["v3.2.5"])
    sample = release.sections(TEXT)
    monkeypatch.setattr(release, "sections", lambda text=None: sample)
    assert release.publish() == 0
    asked = gh.calls[1]
    assert asked[:2] == ["issue", "list"] and asked[asked.index("--label") + 1] == "fixed-unreleased"
    assert asked[asked.index("--state") + 1] == "open"
    for n in (211, 212):
        close = ["issue", "close", str(n), "--reason", "completed", "--comment", "Fixed in v3.3.0"]
        edit = ["issue", "edit", str(n), "--remove-label", "fixed-unreleased"]
        assert gh.calls.index(close) < gh.calls.index(edit)      # closed before its label goes


def test_an_issue_that_cannot_be_closed_keeps_its_label_and_the_release_still_stands(capsys):
    gh = _GitHub(fixed=[213, 214], refuse=[213])
    assert release.close_fixed("v3.3.0", gh=gh) == [214]
    assert ["issue", "edit", "213", "--remove-label", "fixed-unreleased"] not in gh.calls
    assert "#213 could not be closed" in capsys.readouterr().out


def test_notes_rewritten_for_a_release_already_out_close_nothing(monkeypatch):
    # An issue fixed after v3.3.0 went out must never be called fixed in it.
    gh = _GitHub(fixed=[215])
    monkeypatch.setattr(release, "_gh", gh)
    monkeypatch.setattr(release, "tags", lambda: ["v3.3.0", "v3.2.5"])
    sample = release.sections(TEXT)
    monkeypatch.setattr(release, "sections", lambda text=None: sample)
    assert release.publish() == 0
    assert not any(c[0] == "issue" for c in gh.calls)
