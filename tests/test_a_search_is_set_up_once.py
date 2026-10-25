"""A search is set up once, and every other chat finds it rather than starting again.

From a person's first day (2026-10-25): after the cloud chat had written the profile and
made the brief, and while another chat was drafting their applications, the chat they opened
on their computer asked for a resume and began setting them up again. It had looked only in
its own folder. And when it came to reading LinkedIn it read signed out without saying so,
then wrapped signing in in warnings. Now a chat looks here, on master and on every other
chat's unlanded branch before deciding there is no profile; a setup marks its own run so a
chat that finds it half written waits; the profile lands on master the moment it is written;
and the computer chat's message opens the search rather than setting it up. Invented names.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import claude_surfaces as C  # noqa: E402
import place  # noqa: E402

SETUP = os.path.join(ROOT, ".claude", "commands", "setup.md")
SECTIONS = os.path.join(ROOT, ".claude", "skills", "job-application-assistant",
                        "setup-sections.md")
REPO = ("example-owner", "my-job-search")


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c",
                           "user.email=t@example.com", *args], capture_output=True, text=True,
                          check=True).stdout


@pytest.fixture
def copies(tmp_path, monkeypatch):
    """An origin, the setup chat's clone and the computer chat's clone of one copy."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    _git(tmp_path, "-c", "init.defaultBranch=master", "clone", "-q", str(origin), "cloud")
    cloud = tmp_path / "cloud"
    _git(cloud, "checkout", "-q", "-b", "master")
    (cloud / "README.md").write_text("the app\n", encoding="utf-8")
    _git(cloud, "add", "-A")
    _git(cloud, "commit", "-qm", "the app")
    _git(cloud, "push", "-q", "origin", "master")
    _git(tmp_path, "clone", "-q", str(origin), "laptop")
    laptop = tmp_path / "laptop"
    monkeypatch.setattr(place, "ROOT", str(laptop))
    return origin, cloud, laptop


def _write_profile(cloud, mark=None):
    d = cloud / "profile"
    d.mkdir(exist_ok=True)
    (d / "person.json").write_text("{}", encoding="utf-8")
    got = {"works_on": "both"}
    if mark is not None:
        got["setup"] = mark
    (d / "place.json").write_text(json.dumps(got), encoding="utf-8")
    _git(cloud, "add", "-A")
    _git(cloud, "commit", "-qm", "profile")


def test_nothing_anywhere_is_the_one_case_for_setup(copies):
    _, _, laptop = copies
    got = place.setup_state(chat="laptop-chat")
    assert got["state"] == "none" and "run /setup" in got["do"] and got["say"] == ""


def test_a_profile_still_being_written_on_another_chats_branch_is_waited_for(copies):
    _, cloud, laptop = copies
    _git(cloud, "checkout", "-q", "-b", "claude/setting-up")
    _write_profile(cloud, {"started": "2026-10-25", "chat": "cloud-chat"})
    _git(cloud, "push", "-q", "origin", "claude/setting-up")
    got = place.setup_state(chat="laptop-chat")
    assert got["state"] == "going" and got["ref"] == "origin/claude/setting-up"
    assert got["say"] == ("Your setup is still going in your other chat; I'll be ready here "
                          "once it's done.")
    assert "start nothing" in got["do"]
    # Hours with nothing new: it stopped, and this chat may finish it.
    later = time.time() + (place.STALLED_HOURS + 1) * 3600
    assert place.setup_state(now=later, chat="laptop-chat")["state"] == "stopped"


def test_a_finished_profile_another_chat_never_landed_is_brought_in(copies):
    _, cloud, laptop = copies
    _git(cloud, "checkout", "-q", "-b", "claude/set-up")
    _write_profile(cloud, {"started": "2026-10-25", "chat": "cloud-chat",
                           "finished": "2026-10-25"})
    _git(cloud, "push", "-q", "origin", "claude/set-up")
    got = place.setup_state(chat="laptop-chat")
    assert got["state"] == "branch" and "git merge origin/claude/set-up" in got["do"]
    assert "never run /setup" in got["do"]


def test_a_profile_on_master_is_pulled_and_a_profile_here_is_never_set_up_again(copies):
    _, cloud, laptop = copies
    _write_profile(cloud)                         # from before setup marked its runs
    _git(cloud, "push", "-q", "origin", "master")
    got = place.setup_state(chat="laptop-chat")
    assert got["state"] == "landed" and "sync_app.py --pull" in got["do"]
    _git(laptop, "pull", "-q", "origin", "master")
    got = place.setup_state(chat="laptop-chat")
    assert got["state"] == "here" and "never run /setup again" in got["do"]


def test_the_chat_setting_up_carries_on_and_others_wait(copies, monkeypatch):
    _, cloud, laptop = copies
    _write_profile(cloud, {"started": "2026-10-25", "chat": "cloud-chat"})
    _git(cloud, "push", "-q", "origin", "master")
    _git(laptop, "pull", "-q", "origin", "master")
    assert place.setup_state(chat="cloud-chat", fetch=False)["state"] == "self"
    assert place.setup_state(chat="laptop-chat", fetch=False)["state"] == "going"


def test_setup_marks_its_start_and_its_end(tmp_path, monkeypatch):
    import person
    d = tmp_path / "profile"
    d.mkdir()
    monkeypatch.setenv(person.ENV, str(d))
    with pytest.raises(SystemExit, match="person.json first"):
        place.mark_setup("started")
    (d / "person.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CODE_REMOTE_SESSION_ID", "cse_EXAMPLE1")
    import datetime
    place.mark_setup("started", datetime.date(2026, 10, 25))
    place.record("both", datetime.date(2026, 10, 25))          # its answer is kept beside it
    place.mark_setup("finished", datetime.date(2026, 10, 25))
    got = json.loads((d / "place.json").read_text(encoding="utf-8"))
    assert got["works_on"] == "both"
    assert got["setup"] == {"started": "2026-10-25", "chat": "cse_EXAMPLE1",
                            "finished": "2026-10-25"}


def test_setup_looks_first_lands_the_profile_at_once_and_never_starts_again():
    text = open(SETUP, encoding="utf-8").read()
    step0 = text[text.index("## Step 0"):text.index("## Step 1")]
    assert "python3 tools/place.py state" in step0
    assert step0.index("place.py") < text.index("Let's set up your job search")
    assert "never for a resume" in step0 and "that is `/reset`" in step0
    assert "Your search is already set up; this computer is ready for it too." in step0
    assert "\"On a new computer\"" in step0
    step2 = text[text.index("## Step 2"):text.index("## Step 3")]
    assert "python3 tools/place.py started" in step2 and "land it on master" in step2
    step5 = text[text.index("## Step 5"):]
    assert "python3 tools/place.py finished" in step5
    claude = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    start = claude[claude.index("## Start of every session"):claude.index("## App-owned files")]
    assert "place.py state" in start and "never set up again" in start


def test_the_message_a_computer_chat_starts_from_opens_the_search():
    paste = place.computer_paste(*REPO)
    assert paste.startswith("Open my job search on this computer.")
    assert "github.com/example-owner/my-job-search" in paste and "COMPUTER.md" in paste
    for said in (paste, place.next_step("both", "web", *REPO),
                 "\n".join(C.steps("local-chat", name="my-job-search", owner="example-owner"))):
        assert "set me up" not in said.lower() and "set up my job search" not in said.lower()


def test_profile_reading_on_a_computer_is_written_without_asking():
    assert place.default_profile_reads("local") == "browser"
    assert place.default_profile_reads("desktop-cloud") == "browser"
    for where in ("phone", "web", "unknown"):
        assert place.default_profile_reads(where) == ""
    sections = open(SECTIONS, encoding="utf-8").read()
    assert 'written without asking: `"browser"`' in sections


# ------------------------------------------------------------ no warnings, no consent

BANNED = re.compile(r"\b(?:risk\w*|restrict\w*|User Agreement|terms|ban(?:s|ned)?|suspend\w*|"
                    r"robots\.txt|your call|consent\w*|stop any time)\b", re.I)


def _place_texts():
    """Everything the place check can say: its constants and every combination it meets."""
    out = [v for k, v in vars(place).items() if k.isupper() and isinstance(v, str)]
    for where in ("local", "desktop-cloud", "web", "phone", "unknown"):
        for tools in ([], ["browser"], ["enable"], ["chrome"], None):
            for signed_in in (True, False):
                for detail in (True, False):
                    for os_name in ("", "win32", "darwin", "linux"):
                        out += place.check(where, "browser", tools, signed_in, (), *REPO,
                                           detail=detail, works="both", os_name=os_name)
    for answer in ("computer", "phone", "both"):
        for where in ("local", "desktop-cloud", "web", "phone"):
            out.append(place.next_step(answer, where, *REPO))
    return out


def test_setup_and_the_place_check_carry_no_warning_or_consent_words():
    """The person was walled in with disclaimers before LinkedIn was read at all (2026-10-25).
    Setup's own instructions, every line the place check says, and the first pages a person
    reads carry none."""
    texts = {"setup.md": open(SETUP, encoding="utf-8").read()}
    for i, t in enumerate(_place_texts()):
        texts[f"place #{i}"] = t
    for rel in ("START_HERE.md", "HELP.md"):
        texts[rel] = open(os.path.join(ROOT, rel), encoding="utf-8").read()
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    texts["README get started"] = readme[readme.index("## Get started"):
                                         readme.index("## What you can say to it")]
    found = [f"{k}: {m.group(0)}" for k, t in texts.items() for m in [BANNED.search(t)] if m]
    assert found == [], found


# ------------------------------------------------------------ Windows

MAC_ONLY = re.compile(r"\b(?:Terminal|Finder|Applications folder|Cmd\b|Command|Homebrew|brew|"
                      r"xcode|macOS only|\.dmg)", re.I)


def test_a_windows_computer_gets_its_own_short_steps_and_nothing_mac_only():
    win = C.entry("windows-computer")
    said = C.say("windows-computer", name="my-job-search", owner="example-owner")
    assert "Start menu" in said and "Ctrl+Shift+B" in said and "Code tab" in said
    assert not MAC_ONLY.search(said), MAC_ONLY.search(said)
    assert "Chrome or Edge" in win["claim"] and "WSL" in win["claim"]
    assert C.official(win).startswith("https://code.claude.com/docs/")
    # The computer chat's steps are the same on Windows, and none is the Mac's alone.
    steps = C.steps("local-chat", name="my-job-search", owner="example-owner")
    assert "Windows" in steps[1]
    assert not any(MAC_ONLY.search(s) for s in steps), steps
    # A chat on a Windows computer is told the Windows way, never Terminal.
    for tools in ([], None):
        said = "\n".join(place.check("local", "browser", tools, True, (), *REPO, detail=True,
                                     os_name="win32"))
        assert C.say("windows-computer", "my-job-search", "example-owner", goal=False) in said
        assert not MAC_ONLY.search(said.replace(place.IF_NO_BROWSER, "")), said


def test_the_apps_own_browser_is_the_default_and_nobody_is_told_to_install_chrome():
    said = "\n".join(place.check("local", "browser", [], True, (), *REPO, detail=True))
    assert "whatever browser you use" in said
    assert "If you already use Chrome or Edge" in said
    assert not re.search(r"install (?:Google )?Chrome", said, re.I)
    claim = C.entry("chrome")["claim"]
    assert "nobody is told to install Chrome" in claim and "Brave" in claim
    assert "not verified" in C.entry("linux-computer")["claim"]
