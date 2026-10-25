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
import datetime
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


def _say(where, setting, tools, signed_in=True, fixes=(), detail=True):
    """The steps a person who asked how is given (`place.py how`); `detail=False` is what
    every chat says unasked."""
    out = place.check(where, setting, tools, signed_in, fixes, *REPO, detail=detail)
    for line in out:
        _clean(line)
    return "\n".join(out)


def test_a_cloud_chat_with_no_browser_says_finding_works_and_where_to_read():
    for where in ("desktop-cloud", "unknown"):
        said = _say(where, "browser", [])
        assert said.startswith(place.FINDING_WORKS)            # what works here, first
        # Numbered steps, one action a line, each part dated: one long sentence of
        # destinations lost a person who had only used the cloud (2026-10-20).
        assert "First, put your copy on your computer.\nAt the time of writing (checked" in said
        assert "\n1. Install GitHub Desktop from github.com/apps/desktop" in said
        assert "Then start a chat on it.\nAt the time of writing (checked" in said
        assert "\n2. Open its Code tab, at the top." in said
        # The set-up that works, said plainly; no paste offered to a person at a computer.
        assert place.TWO_CHATS in said and place.PASTE_TOP not in said
    # Not knowing the chat's tools, it asks the chat to look before it says anything.
    said = _say("desktop-cloud", "browser", [])
    unsure = _say("desktop-cloud", "browser", None)
    assert unsure.startswith("[only if this chat has no browser tool")
    assert unsure[len(place.IF_NO_BROWSER):] == said            # the words said are the same
    # A cloud chat the desktop app lends its browser to can read, and says plainly once that
    # this rests on a link Anthropic's documentation does not describe yet.
    assert _say("desktop-cloud", "browser", ["enable"]) == place.CLOUD_LINK_NOW
    assert _say("desktop-cloud", "browser", ["browser"]) == place.CLOUD_LINK_NOW
    assert "does not describe this yet" in place.CLOUD_LINK_NOW
    # One that cannot reach it says that link exists and is not documented, too.
    assert place.CLOUD_LINK_NOT in said


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
    assert _say("phone", "browser", ["enable"]) == place.CLOUD_LINK_NOW
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
    # Claude runs every install itself, into the person's own folders: no Homebrew, no
    # winget, no password (tools/installs.py). Apple's own window is the person's click.
    assert ("Python 3.9 or newer", "xcode-select --install", "dialog") in fixes
    assert "  - the Python packages: python3 tools/env_check.py --fix packages\n" in said
    assert "  - LaTeX, to make the PDFs: python3 tools/env_check.py --fix latex" in said
    assert "brew" not in said and "winget" not in said
    assert "[asks for your password]" not in said
    lines = [l for l in said.splitlines() if l.startswith("  - ")]
    assert len(lines) == len(fixes) and all(": " in l for l in lines)   # one command each
    # Every machine has its own commands, and only a computer is told to install anything.
    win = env_check.local_fixes("win32", have=NONE, module=lambda m: True, py_ok=False, pypdf="ok",
                                gh_signed_in=False)
    assert win[0] == ("Python 3.9 or newer",
                      "powershell -ExecutionPolicy Bypass -File tools/computer_setup.ps1", "")
    assert not [f for f in win if "winget" in f[1] or f[2] == "password"]
    assert ("GitHub sign-in for it", "gh auth login --web --git-protocol https", "sign-in") in win
    assert ("  - GitHub sign-in for it: gh auth login --web --git-protocol https  [yours: it "
            "signs you in") in said
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
        assert step.startswith(place.TWO_CHATS + " Two parts, once. First, put your copy on "
                               "your computer.\nAt the time of writing (checked")
        assert 'say "set me up"' in step
        _clean(step)
    for answer, where in (("computer", "local"), ("phone", "web"), ("phone", "phone"),
                          ("phone", "local"), ("both", "web"), ("both", "local")):
        step = place.next_step(answer, where, *REPO)
        assert "continue this in a chat on your computer" not in step.lower()
        _clean(step)
    _clean(place.QUESTION + " " + place.TRADE_OFF + " " + place.RECOMMEND)
    assert "local" not in place.TRADE_OFF.lower() and "cloud" not in place.TRADE_OFF.lower()


def test_said_once_in_a_chat_and_again_only_when_it_changes(tmp_path, monkeypatch):
    # Told weekly, a person who had already chosen heard "two chats work best, ask me how
    # to move" again and again for no reason (2026-10-20). A choice is offered once.
    monkeypatch.setattr(place, "_told_path", lambda: str(tmp_path / "told.json"))
    monkeypatch.setattr(place, "setting", lambda: "browser")
    monkeypatch.setattr(place, "repo", lambda: REPO)
    monkeypatch.setattr(place, "has_local", lambda: False)
    env = {"CLAUDE_CODE_REMOTE": "true", "CLAUDE_CODE_ENTRYPOINT": "remote_desktop",
           "CLAUDE_CODE_REMOTE_SESSION_ID": "cse_EXAMPLE1"}
    day = datetime.date(2026, 10, 19)
    first = place.report([], once=True, env=env, today=day)
    assert first.startswith("Place check (Claude: tell the person this at the end of your reply")
    assert "said once in a chat, and again only when it changes" in first
    assert "never hold back work that does not need it" in first
    assert place.report([], once=True, env=env, today=day) == ""
    for days in (place.RETELL_DAYS, 30, 90):
        assert place.report([], once=True, env=env,
                            today=day + datetime.timedelta(days=days)) == ""
    # A record from before dates were kept counts as told.
    import json
    (tmp_path / "told.json").write_text(json.dumps(
        {"said": {"cse_EXAMPLE1": place._digest(place.check(
            "desktop-cloud", "browser", [], False, (), *REPO))}}))
    assert place.report([], once=True, env=env, today=day) == ""
    # A chat that was told an older wording (one open before an update) hears the new one,
    # once, and then nothing again.
    monkeypatch.setattr(place, "SHORT_CLOUD", "Finding people works in this chat, still.")
    assert "still." in place.report([], once=True, env=env)
    assert place.report([], once=True, env=env) == ""
    assert place.report([], once=True, env={**env, "CLAUDE_CODE_REMOTE_SESSION_ID": "cse_EXAMPLE2"})


def test_a_computer_missing_a_tool_hears_it_again_weekly_until_it_is_there(tmp_path, monkeypatch):
    import env_check
    monkeypatch.setattr(place, "_told_path", lambda: str(tmp_path / "told.json"))
    monkeypatch.setattr(place, "setting", lambda: "paste")
    monkeypatch.setattr(place, "repo", lambda: REPO)
    monkeypatch.setattr(place, "note_local", lambda today=None: False)
    monkeypatch.setattr(env_check, "local_fixes",
                        lambda: [("LaTeX, to make the PDFs",
                                  "python3 tools/env_check.py --fix latex", "")])
    env = {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "local-EXAMPLE"}
    day = datetime.date(2026, 10, 19)
    assert "--fix latex" in place.report([], once=True, env=env, today=day)
    assert place.report([], once=True, env=env, today=day + datetime.timedelta(days=3)) == ""
    later = day + datetime.timedelta(days=place.RETELL_DAYS)
    assert "--fix latex" in place.report([], once=True, env=env, today=later)


def test_a_person_with_a_chat_on_their_computer_is_never_asked_to_move():
    for works in ("computer", "both"):
        for where in ("desktop-cloud", "web", "unknown"):
            assert place.check(where, "paste", [], False, (), *REPO, works=works,
                               has_local=True) == []
            said = place.check(where, "browser", [], False, (), *REPO, works=works,
                               has_local=True)
            assert said == [place.SHORT_HAS_LOCAL]
            assert "move" not in said[0] and "Ask me how" not in said[0]


def test_a_chat_on_their_computer_is_recorded_once_and_keeps_their_answer(tmp_path, monkeypatch):
    import person
    d = tmp_path / "profile"
    d.mkdir()
    (d / "person.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv(person.ENV, str(d))
    place.record("both", datetime.date(2026, 10, 1))
    assert place.note_local(datetime.date(2026, 10, 20)) and place.has_local()
    assert not place.note_local(datetime.date(2026, 10, 21))
    assert place.works_on() == "both"
    place.record("computer", datetime.date(2026, 10, 22))
    assert place.has_local() and place.works_on() == "computer"


def test_the_computer_chat_line_is_committed_so_the_next_sync_can_pull(tmp_path, monkeypatch):
    """Found by tools/rehearse_sync.py on 2026-10-21: the line was written and never
    committed, so the next sync, which pulls master only into a clean folder, stopped."""
    import subprocess
    import person
    repo = tmp_path / "theirs"
    d = repo / "profile"
    d.mkdir(parents=True)
    (d / "person.json").write_text("{}", encoding="utf-8")
    (d / "place.json").write_text('{"works_on": "both"}\n', encoding="utf-8")

    def git(*args):
        return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c",
                               "user.email=t@example.com", *args], capture_output=True,
                              text=True, check=True).stdout
    git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "start")
    (repo / "notes.txt").write_text("theirs, staged\n", encoding="utf-8")
    git("add", "notes.txt")
    monkeypatch.setenv(person.ENV, str(d))
    monkeypatch.setenv("GIT_AUTHOR_NAME", "t")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "t")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@example.com")
    assert place.note_local(datetime.date(2026, 10, 21))
    assert "profile/place.json" not in git("status", "--porcelain")
    assert "Place: a chat on this computer" in git("log", "-1", "--format=%s")
    # Only that line went in: what they had staged stays staged, uncommitted.
    assert git("status", "--porcelain").strip() == "A  notes.txt"


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


def test_the_sync_runs_the_check_in_every_chat_not_only_the_days_first(sync_steps):
    # Run the sync both ways and read what it did, rather than search its source.
    rc, steps = sync_steps("--if-stale", stale=False)          # a day already checked
    assert rc == 0 and steps == ["network_check", "place_check"]
    rc, steps = sync_steps("--if-stale", stale=True)
    assert rc == 0 and steps[-2:] == ["model_check", "place_check"], steps


def test_an_existing_brief_is_found_by_its_registry_or_prompt_never_its_title():
    reg = {"routines": [{"key": "morning_brief", "name": "Job search: twice-weekly digest",
                         "trigger_id": "trig_EXAMPLE1",
                         "prompt_file": "automation/prompts/morning_brief.md"}]}
    listing = [{"id": "trig_EXAMPLE1", "name": "Job search: twice-weekly digest", "prompt": ""}]
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


def test_what_every_chat_says_unasked_is_two_or_three_short_sentences_and_no_links():
    """A block of 150 words and two URLs at the end of a reply was the part nobody read.
    Unasked it is short; the dated steps come only when the person asks how."""
    for where in ("desktop-cloud", "web", "phone", "unknown", "local"):
        for tools in ([], ["enable"], None):
            for signed_in in (True, False):
                for line in place.check(where, "browser", tools, signed_in, (), *REPO):
                    said = line.replace(place.IF_NO_BROWSER, "")
                    _clean(said)
                    assert len(said.split()) <= place.SHORT_WORDS, (where, tools, said)
                    assert "http" not in said and "At the time of writing" not in said
                    assert said.count(". ") + said.count(": ") <= 4
    short = place.check("desktop-cloud", "browser", [], False, (), *REPO)
    assert short == [place.SHORT_CLOUD + " " + place.SHORT_TWO_CHATS]
    assert "Ask me how" in place.SHORT_TWO_CHATS and "paste" not in short[0].lower()
    # Two chats, said wherever the person decides where to work.
    for answer, where in (("computer", "local"), ("both", "web"), ("computer", "web")):
        assert place.TWO_CHATS in place.next_step(answer, where, *REPO)
    # The steps are all still there for the person who asks.
    assert "At the time of writing (checked" in _say("desktop-cloud", "browser", [])


def test_an_existing_person_at_a_computer_hears_about_two_chats_without_browser_reads():
    """Two chats is said to a person with a computer in a cloud chat even when they do not
    read profiles in their browser: someone who set up in the cloud was never told."""
    for works in ("computer", "both"):
        for where in ("desktop-cloud", "web", "unknown"):
            short = place.check(where, "paste", [], False, (), *REPO, works=works)
            assert short == [place.SHORT_TWO_CHATS]
            _clean(short[0])
            said = "\n".join(place.check(where, "paste", [], False, (), *REPO, detail=True,
                                         works=works))
            assert said.startswith(place.TWO_CHATS) and "At the time of writing (checked" in said
        assert place.check("local", "paste", [], False, (), *REPO, works=works) == []
    assert place.check("web", "paste", [], False, (), *REPO, works="phone") == []
    assert place.check("web", "paste", [], False, (), *REPO) == []      # never asked yet
