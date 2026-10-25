"""The place check, the reads and the download questions agree, and say only what is left.

Since 2026-10-25 a profile with no PROFILE_READS reads in a browser (reading.py
reads_setting), so the place check reads the setting by that same rule rather than its own.
On their computer, in a chat with a browser tool, the once-a-chat check carries what is
still to do there (LinkedIn signed in, its download: `reading.py new-computer`) and nothing
when it is all done. And while a LinkedIn download is on its way, neither download question
is asked: the person has done their part.
"""
import datetime
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "network"))
import place  # noqa: E402
import profile_upgrades  # noqa: E402
import reading  # noqa: E402

REPO = ("example-owner", "my-job-search")
LOCAL = {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "local-EXAMPLE"}


def _profile(tmp_path, networking: str) -> Path:
    """The example person, with networking settings of the test's own."""
    d = tmp_path / "profile"
    shutil.copytree(ROOT / "profile.example", d, ignore=shutil.ignore_patterns("state"))
    (d / "networking.py").write_text(networking, encoding="utf-8")
    return d


def test_no_setting_reads_in_a_browser_the_same_as_reading_does(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_PROFILE", str(_profile(tmp_path, "LINKEDIN_PLAN = 'free'\n")))
    assert place.setting() == "browser" == reading.reads_setting(object())
    paste = tmp_path / "other"
    paste.mkdir()
    (paste / "networking.py").write_text('PROFILE_READS = "Paste"\n', encoding="utf-8")
    monkeypatch.setenv("LJS_PROFILE", str(paste))
    assert place.setting() == "paste"
    # No networking settings yet: nothing is read, so the check has nothing to say about it.
    monkeypatch.setenv("LJS_PROFILE", str(tmp_path / "none"))
    assert place.setting() == ""


def test_a_computer_with_a_browser_is_given_what_is_left_and_nothing_once_done(tmp_path,
                                                                                monkeypatch):
    monkeypatch.setattr(place, "_told_path", lambda: str(tmp_path / "told.json"))
    monkeypatch.setattr(place, "setting", lambda: "browser")
    monkeypatch.setattr(place, "repo", lambda: REPO)
    monkeypatch.setattr(place, "note_local", lambda today=None: False)
    monkeypatch.setattr(place, "has_local", lambda: True)
    import env_check
    monkeypatch.setattr(env_check, "local_fixes", lambda: [])
    left = ["1. the LinkedIn download, request: none taken yet: in the browser, ask LinkedIn"]
    monkeypatch.setattr(reading, "new_computer", lambda tools=(), today=None: list(left))
    day = datetime.date(2026, 10, 25)
    out = place.report(["browser"], once=True, env=LOCAL, today=day)
    assert out.startswith("On this computer (Claude: do these yourself, in order")
    assert left[0] in out
    assert place.report(["browser"], once=True, env=LOCAL, today=day) == ""
    # Done: nothing at all, never "nothing to do".
    monkeypatch.setattr(reading, "new_computer",
                        lambda tools=(), today=None: ["nothing to do: carry on"])
    assert place.computer_steps("local", ["browser"], day) == []
    # Not on the computer, or no browser tool: the check never runs it.
    called = []
    monkeypatch.setattr(reading, "new_computer",
                        lambda tools=(), today=None: called.append(tools) or list(left))
    assert place.computer_steps("local", [], day) == []
    assert place.computer_steps("local", None, day) == []
    assert place.computer_steps("phone", ["browser"], day) == []
    assert place.computer_steps("cloud", ["enable"], day) == []
    assert called == []
    assert place.computer_steps("local", ["chrome"], day) == left


def test_while_a_download_is_on_its_way_neither_download_question_is_asked(tmp_path,
                                                                            monkeypatch):
    state = tmp_path / "state"
    (state / "documents" / "linkedin").mkdir(parents=True)
    (state / "documents" / "network").mkdir(parents=True)
    monkeypatch.setenv("LJS_PROFILE", str(_profile(tmp_path, "LINKEDIN_PLAN = 'free'\n")))
    monkeypatch.setenv("LJS_STATE", str(state))
    assert profile_upgrades._connections_export()      # asked: nothing is on file
    (state / "documents" / "network" / "linkedin_export.json").write_text(
        json.dumps({"requested_on": datetime.date.today().isoformat()}), encoding="utf-8")
    assert profile_upgrades._download_on_its_way()
    assert profile_upgrades._connections_export() == ""
    (state / "documents" / "linkedin" / "Connections.csv").write_text(
        "First Name,Last Name\n", encoding="utf-8")
    monkeypatch.setattr(profile_upgrades.person, "local_state",
                        lambda *p: str(state.joinpath(*p)))
    assert profile_upgrades._linkedin_history() == ""
    monkeypatch.setattr(profile_upgrades, "_download_on_its_way", lambda: False)
    assert profile_upgrades._linkedin_history()          # asked once nothing is on its way
