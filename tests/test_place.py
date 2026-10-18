"""A chat says once whether it is the right place for what the person set up.

Profiles read in the person's own browser need a chat on their computer, or a cloud
chat the desktop app lends its browser to; a phone has none. A person was left in a
cloud chat whose setting could never work there, with nothing telling them where to
go. Each combination the place check can meet is pinned here: the exact place to go,
"close this chat" only when it is true, no instruction to press a key or find a
setting without saying where, no em dashes and UK spelling.
"""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import env_check  # noqa: E402
import place  # noqa: E402
import python_floor  # noqa: E402
import routines  # noqa: E402

REPO = ("example-owner", "my-job-search")
US = re.compile(r"\b(?:color|favor|center|organiz|recogniz|realiz|customiz|analyz|"
                r"prioritiz|license)\w*", re.I)
NONE = lambda *_: None  # noqa: E731


def _clean(text: str) -> None:
    assert "—" not in text, "an em dash"
    assert not US.search(text), US.search(text).group(0)
    low = text.lower()
    assert not any(w in low for w in ("press ", "shortcut", "cmd+", "ctrl+", "find the setting",
                                      "open the panel", "go to settings"))
    # A click is said only with exactly where: a named tab or button.
    for m in re.finditer(r"click ([a-z]+(?:,? [a-z]+)?)", low):
        assert m.group(1) in ("the code", "code, then"), m.group(0)


def _say(where, setting, tools, signed_in=True, fixes=()):
    out = place.check(where, setting, tools, signed_in, fixes, *REPO)
    for line in out:
        _clean(line)
    return "\n".join(out)


def test_a_cloud_chat_with_the_browser_setting_and_no_browser_says_where_to_go():
    said = _say("desktop-cloud", "browser", [])
    assert said.startswith("Your setting reads LinkedIn profiles in the browser on your computer")
    assert "Close this chat. Open the Claude desktop app, click the Code tab, choose the folder " \
           "my-job-search" in said
    assert "github.com/example-owner/my-job-search, click Code, then Open with GitHub Desktop" in said
    assert 'Or say "paste"' in said and "this time" in said      # offered, never applied
    # Not knowing the chat's tools, it asks the chat to look before it says anything.
    unsure = _say("desktop-cloud", "browser", None)
    assert unsure.startswith("[only if this chat has no browser tool") and "Close this chat" in unsure
    assert unsure[len(place.IF_NO_BROWSER):] == said            # the words said are the same
    # A cloud chat the desktop app can lend its browser to is already the right place.
    assert _say("desktop-cloud", "browser", ["enable"]) == ""
    assert _say("desktop-cloud", "browser", ["browser"]) == ""


def test_a_cloud_chat_that_pastes_hears_nothing():
    for where in ("desktop-cloud", "web", "phone", "unknown"):
        assert _say(where, "paste", []) == ""
        assert _say(where, "", None) == ""


def test_a_phone_or_the_web_is_told_to_send_screenshots_and_nothing_about_installing():
    for where in ("phone", "web", "unknown"):
        said = _say(where, "browser", [])
        assert said == "On a phone or in a browser, send screenshots or a paste for each profile."
        assert not any(w in said.lower() for w in ("install", "desktop app", "close this chat"))


def test_a_chat_on_their_computer_signed_out_is_told_the_sign_in_is_theirs_once():
    said = _say("local", "browser", ["browser"], signed_in=False)
    assert "LinkedIn's sign-in page opens in the browser pane in the Claude desktop app" in said
    assert "sign in there yourself, once" in said and "Close this chat" not in said


def test_a_chat_on_their_computer_signed_in_is_the_right_place():
    assert _say("local", "browser", ["browser"], signed_in=True) == ""
    assert _say("local", "paste", [], signed_in=True) == ""


def test_a_terminal_chat_with_no_browser_offers_the_desktop_app_or_a_paste():
    said = _say("local", "browser", [])
    assert "This chat has no browser" in said and "Close this chat" in said and '"paste"' in said


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


def test_the_next_step_after_setups_question_says_close_this_chat_only_when_true():
    for where in ("web", "desktop-cloud", "phone"):
        step = place.next_step("computer", where, *REPO)
        assert step.startswith("Close this chat. Open the Claude desktop app, click the Code tab")
        assert 'say "set me up"' in step
        _clean(step)
    for answer, where in (("computer", "local"), ("phone", "web"), ("phone", "phone"),
                          ("phone", "local"), ("both", "web"), ("both", "local")):
        step = place.next_step(answer, where, *REPO)
        assert "close this chat" not in step.lower()
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
