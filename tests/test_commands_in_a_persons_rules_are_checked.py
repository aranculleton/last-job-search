"""The commands a person's own rules name are checked: they exist, and do what the rule says.

A person's rule said "export.py history --from <zip>" every two weeks; without --apply that
command only shows what it would do, so the rule saved nothing, and nothing said so (audit
PD-9, the "rules enforced only by prose" cluster). The upgrade profile-commands lists each
`python3 tools/...` command in profile/CLAUDE.md whose tool or step the app does not have, or
that only previews without --apply, so the person's chat corrects the rule. Invented rules.
"""
from __future__ import annotations

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import profile_upgrades  # noqa: E402

RULES = """# The person

- **LinkedIn data export, every two weeks.** When it arrives:
  `python3 tools/network/export.py history --from <zip>`, then rebuild who is due.
- Before anyone is shown: `python3 tools/network/export.py take <zip>` first.
- Old notes: `python3 tools/nosuch_tool.py run` each Monday.
- A step the tool lacks: `python3 tools/brief.py reshuffle`.
- Applied the right way: `python3 tools/network/export.py history --from <zip> --apply`.
"""


def test_the_rules_commands_are_checked(tmp_path, monkeypatch):
    prof = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), prof,
                    ignore=shutil.ignore_patterns("state"))
    (prof / "CLAUDE.md").write_text(RULES, encoding="utf-8")
    monkeypatch.setenv("LJS_PROFILE", str(prof))
    import person
    person.reset()
    got = profile_upgrades.profile_command_problems()
    text = "\n".join(got)
    assert any("export.py history" in p and "--apply" in p for p in got), text
    assert any("nosuch_tool.py" in p and "the app has no" in p for p in got), text
    assert any("brief.py reshuffle" in p for p in got), text
    assert not any("export.py take" in p for p in got), text
    assert len(got) == 3, text
    u = profile_upgrades.by_id("profile-commands")
    assert u.needs == "nobody" and u.pending()


def test_the_example_person_has_none():
    assert profile_upgrades.profile_command_problems() == []


def test_a_command_named_without_python3_is_checked_too(tmp_path, monkeypatch):
    """The rule PD-9 is about names `tools/network/export.py history --from <zip>` with no
    python3 in front, and the check required one (review of fix/helpers, item 14)."""
    prof = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), prof,
                    ignore=shutil.ignore_patterns("state"))
    (prof / "CLAUDE.md").write_text("When it arrives: `tools/network/export.py history --from "
                                    "<zip>`, then rebuild who is due.\n", encoding="utf-8")
    monkeypatch.setenv("LJS_PROFILE", str(prof))
    import person
    person.reset()
    got = profile_upgrades.profile_command_problems()
    assert len(got) == 1 and "--apply" in got[0], got
