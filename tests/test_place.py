"""A chat says once whether it is the right place for what the person set up.

Finding people works in any chat (tools/network/sources.py, the ladder); reading their
profiles needs a browser of the person's that the chat can use. So the check decides by
the tools a chat has, never by where it was started: a phone chat linked to the computer
reads as well as a chat on it. Each combination it can meet is pinned here. The words
follow the one rule for a path a person follows: the goal first, then the destination
"at the time of writing" with the official page beside it (tools/claude_surfaces.json),
and never press, click, tap or find. No em dashes, UK spelling, and never a request for
everyone's screenshots.
"""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import claude_surfaces  # noqa: E402
import env_check  # noqa: E402
import place  # noqa: E402
import python_floor  # noqa: E402
import routines  # noqa: E402

REPO = ("example-owner", "my-job-search")
US = re.compile(r"\b(?:color|favor|center|organiz|recogniz|realiz|customiz|analyz|"
                r"prioritiz|license)\w*", re.I)
NONE = lambda *_: None  # noqa: E731


def _clean(text: str) -> None:
    assert "\u2014" not in text, "an em dash"
    assert not US.search(text), US.search(text).group(0)
    assert not claude_surfaces.BANNED.search(text), claude_surfaces.BANNED.search(text).group(0)
    assert not any(w in text.lower() for w in ("cmd+", "ctrl+", "shift+"))
    # Every path is dated and sourced: "At the time of writing" and its official page.
    assert text.count("At the time of writing:") == text.count("(official page: https://")
    # Never everyone's profile: a paste is for the one or two who matter most.
    assert not re.search(r"(?:for|of) (?:each|every) (?:person|profile)|everyone's", text, re.I)


def _say(where, setting, tools, signed_in=True, fixes=()):
    out = place.check(where, setting, tools, signed_in, fixes, *REPO)
    for line in out:
        _clean(line)
    return "\n".join(out)


def test_a_cloud_chat_with_no_browser_says_finding_works_and_where_to_read():
    for where in ("desktop-cloud", "unknown"):
        said = _say(where, "browser", [])
        assert said.startswith(place.FINDING_WORKS)            # what works here, first
        assert "Continue this in a chat on your computer. At the time of writing: open the " \
               "Claude desktop app" in said and "the folder my-job-search" in said
        assert "github.com/example-owner/my-job-search, choose Code, then Open with GitHub " \
               "Desktop" in said
        assert said.endswith(place.PASTE_TOP)                  # offered, for the few only
    # Not knowing the chat's tools, it asks the chat to look before it says anything.
    said = _say("desktop-cloud", "browser", [])
    unsure = _say("desktop-cloud", "browser", None)
    assert unsure.startswith("[only if this chat has no browser tool")
    assert unsure[len(place.IF_NO_BROWSER):] == said            # the words said are the same
    # A cloud chat the desktop app lends its browser to is already the right place.
    assert _say("desktop-cloud", "browser", ["enable"]) == ""
    assert _say("desktop-cloud", "browser", ["browser"]) == ""


def test_a_chat_that_pastes_hears_nothing_anywhere():
    for where in ("desktop-cloud", "web", "phone", "unknown", "local"):
        assert _say(where, "paste", []) == ""
        assert _say(where, "", None) == ""


def test_a_phone_or_the_web_is_offered_the_computers_chat_and_never_an_install():
    for where in ("phone", "web"):
        said = _say(where, "browser", [])
        assert said.startswith(place.FINDING_WORKS)
        assert "/remote-control" in said and "code.claude.com/docs/en/remote-control" in said
        assert not re.search(r"\binstall", said, re.I)
    # A phone chat linked to the computer reads as well as one on it: by tools, not place.
    assert _say("phone", "browser", ["enable"]) == ""
    assert "sign in there yourself, once" in _say("phone", "browser", ["enable"], signed_in=False)


def test_a_chat_on_their_computer_signed_out_is_told_the_sign_in_is_theirs_once():
    said = _say("local", "browser", ["browser"], signed_in=False)
    assert said == place.SIGN_IN_ONCE
    # Chrome shares their own sign-ins: nothing to sign in to.
    assert _say("local", "browser", ["chrome"], signed_in=False) == ""


def test_a_chat_on_their_computer_signed_in_is_the_right_place():
    assert _say("local", "browser", ["browser"], signed_in=True) == ""
    assert _say("local", "paste", [], signed_in=True) == ""


def test_a_terminal_chat_with_no_browser_names_the_desktop_app_and_chrome():
    said = _say("local", "browser", [])
    assert said.startswith("Finding people works in this chat.")
    assert "Continue this in a chat on your computer" not in said      # it is on one
    assert "claude --chrome" in said and place.PASTE_TOP in said


def test_a_computer_missing_python_gets_one_list_with_the_password_ones_marked():
    fixes = env_check.local_fixes("darwin", have=NONE, module=lambda m: False, py_ok=False,
                                  pypdf="missing", gh_signed_in=False)
    said = _say("local", "paste", [], fixes=fixes)
    assert said.startswith("This computer is missing a few things. Each is one command")
    assert "  - Python 3.9 or newer: xcode-select --install  [asks for your password]" in said
    assert "  - pytest: pip3 install --user pytest\n" in said              # Claude runs it
    assert "brew install --cask mactex-no-gui  [asks for your password]" in said
    lines = [l for l in said.splitlines() if l.startswith("  - ")]
    assert len(lines) == len(fixes) and all(": " in l for l in lines)   # one command each
    # Every machine has its own commands, and only a computer is told to install anything.
    win = env_check.local_fixes("win32", have=NONE, module=lambda m: True, py_ok=False, pypdf="ok",
                                gh_signed_in=False)
    assert win[0] == ("Python 3.9 or newer", "winget install Python.Python.3.12", "")
    assert ("GitHub sign-in for it", "gh auth login", "sign-in") in win
    assert "  - GitHub sign-in for it: gh auth login  [yours: it signs you in" in said
    assert _say("web", "paste", [], fixes=fixes) == ""
    # Too old a Python to run any of this is told in one sentence by every tool.
    assert python_floor.message("3.8.10", "darwin").startswith("Python 3.9 or newer is needed")


def test_nothing_missing_says_nothing():
    have = lambda t: "/usr/bin/" + t  # noqa: E731
    assert env_check.local_fixes("darwin", have=have, module=lambda m: True, py_ok=True,
                                 pypdf="ok", gh_signed_in=True) == []


def test_the_next_step_after_setups_question_moves_them_only_when_true():
    for where in ("web", "desktop-cloud", "phone"):
        step = place.next_step("computer", where, *REPO)
        assert step.startswith("Continue this in a chat on your computer. At the time of writing")
        assert 'say "set me up"' in step
        _clean(step)
    for answer, where in (("computer", "local"), ("phone", "web"), ("phone", "phone"),
                          ("phone", "local"), ("both", "web"), ("both", "local")):
        step = place.next_step(answer, where, *REPO)
        assert "continue this in a chat on your computer" not in step.lower()
        _clean(step)
    _clean(place.QUESTION + " " + place.TRADE_OFF + " " + place.RECOMMEND)
    assert "local" not in place.TRADE_OFF.lower() and "cloud" not in place.TRADE_OFF.lower()


def test_said_once_per_chat(tmp_path, monkeypatch):
    monkeypatch.setattr(place, "_told_path", lambda: str(tmp_path / "told.json"))
    monkeypatch.setattr(place, "setting", lambda: "browser")
    monkeypatch.setattr(place, "repo", lambda: REPO)
    env = {"CLAUDE_CODE_REMOTE": "true", "CLAUDE_CODE_ENTRYPOINT": "remote_desktop",
           "CLAUDE_CODE_REMOTE_SESSION_ID": "cse_EXAMPLE1"}
    first = place.report([], once=True, env=env)
    assert first.startswith("Place check (Claude: tell the person this once in this chat")
    assert "never hold back work that does not need it" in first
    assert place.report([], once=True, env=env) == ""
    assert place.report([], once=True, env={**env, "CLAUDE_CODE_REMOTE_SESSION_ID": "cse_EXAMPLE2"})


def test_the_answer_is_recorded_only_in_a_profile_that_exists(tmp_path, monkeypatch):
    import person
    monkeypatch.setattr(person, "exists", lambda *p: False)
    with pytest.raises(SystemExit, match="no profile yet"):
        place.record("computer")
    monkeypatch.setattr(person, "exists", lambda *p: True)
    monkeypatch.setattr(place, "_profile_file", lambda: str(tmp_path / "place.json"))
    place.record("phone")
    assert json.loads((tmp_path / "place.json").read_text())["works_on"] == "phone"
    with pytest.raises(SystemExit):
        place.record("tablet")


def test_the_sync_runs_the_check_in_every_chat_not_only_the_days_first():
    src = (ROOT / "tools" / "sync_app.py").read_text(encoding="utf-8")
    already = src[src.index('print("sync_app: already checked today.")'):]
    assert already.index("place_check(a.tools)") < already.index("return 0")
    assert "model_check(a.on)\n        place_check(a.tools)" in src


def test_an_existing_brief_is_found_by_its_registry_or_prompt_never_its_title():
    reg = {"routines": [{"key": "morning_brief", "name": "Job search: brief (Mon and Thu)",
                         "trigger_id": "trig_EXAMPLE1",
                         "prompt_file": "automation/prompts/morning_brief.md"}]}
    listing = [{"id": "trig_EXAMPLE1", "name": "Job search: brief (Mon and Thu)", "prompt": ""}]
    got = routines.existing_brief(reg, listing)
    assert got["state"] == "registered" and "never create a second" in got["say"]
    assert routines.existing_brief(reg, [])["state"] == "registered"
    # Registered, but gone from the account: ask before making another.
    assert routines.existing_brief(reg, [{"id": "trig_OTHER", "name": "x", "prompt": ""}])["state"] == "ask"
    # Not registered, but its stored prompt is the brief's: found, whatever it is called.
    stub = routines.DEFAULT_STUB.format(label="morning brief", Label="Morning brief",
                                        prompt_file="automation/prompts/morning_brief.md",
                                        relay_id="")
    found = routines.existing_brief({}, [{"id": "trig_EXAMPLE2", "name": "Mon/Thu summary",
                                          "prompt": stub}])
    assert found["state"] == "found" and found["id"] == "trig_EXAMPLE2"
    # A title alone decides nothing: it is asked about, never attached and never duplicated.
    named = routines.existing_brief({}, [{"id": "trig_EXAMPLE3", "name": "Job search: morning brief",
                                          "prompt": "something else"}])
    assert named["state"] == "ask"
    assert routines.existing_brief({}, [])["state"] == "none"
