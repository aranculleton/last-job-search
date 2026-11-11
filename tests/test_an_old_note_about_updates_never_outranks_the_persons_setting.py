"""An old note in a chat's memory about the app's updates never outranks the person's setting.

The maintainer, 2026-11-11: "I keep having to tell all the chats, and for some reason they're
all stuck on something I said in October, like wait for updates when I say, BUT I HAVE BEEN
TRYING TO REVERSE THIS AND GET FULL AUTOMATIC UPDATES SINCE." Their profile said updates come
by themselves, the October rule was retired, and the start step removes a memory note that
disagrees with the setting, but only one learned.known_settings could read. That reader
writes the setting, so it reads only what is said plainly, and the notes the chats obeyed
were in other words: "Wait for him to say update before taking app updates", "Ask before
taking app updates", "If an update is waiting, say so in one plain line and wait.",
"app_updates is when_asked", and a memory file named for app updates whose body says only
"wait for him". The memory side now reads its own way, wider, judged only against a setting
the person wrote, and never touches an update that is theirs (a resume, a status update).
"""
from __future__ import annotations

import os
import re
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import computer  # noqa: E402
import person  # noqa: E402

AUTO = {computer.UPDATES_SETTING: "auto"}
WAIT = {computer.UPDATES_SETTING: "when_asked"}

OCTOBER = [
    "Wait for him to say update before taking app updates",
    "Ask before taking app updates",
    "If an update is waiting, say so in one plain line and wait.",
    "app_updates is when_asked",
    "Never take the app's update unless he says to update. If an update is waiting, say so in "
    "one plain line and wait.",
]
# What agrees with updates by themselves, and what is not about the app's updates at all.
AGREES_WITH_AUTO = [
    "Updates come by themselves; never ask him again",
    "app_updates is auto",
    "If he asks to update, run sync_app.py --update",
    "Never wait for his word on app updates",
]
THEIRS = [
    "Don't update my resume until I say",
    "Update my CV only when I say",
    "Send a status update to the recruiter and wait for a reply",
    "Apply the update to the tracker, then wait for him",
    # The review of 2026-11-11: the start step took the first out of a chat's memory.
    "Never ask recruiters for an update; wait two weeks.",
    "Don't ask recruiters for an update",
    "Stop asking hiring managers for an update",
    "Don't chase for an update until two weeks have passed",
    "No status update emails",
    "Don't update LinkedIn without checking with me",
    "only follow up when there is an update to share",
]


@pytest.fixture
def chat(tmp_path, monkeypatch):
    """A copy of the search and the auto memory a chat in it loads (a tmp HOME)."""
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    home = tmp_path / "home"
    copy = tmp_path / "search"
    copy.mkdir()
    mem = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(copy)) / "memory"
    mem.mkdir(parents=True)
    return str(copy), str(home), mem


def _remove(chat, settings):
    copy, home, _mem = chat
    found = computer.memory_conflicts(copy, home=home, settings=settings)
    removed, left = computer.memory_remove(found)
    assert left == []
    return removed


@pytest.mark.parametrize("words", OCTOBER)
def test_the_words_the_chats_obeyed_are_removed_where_updates_come_by_themselves(chat, words):
    _copy, _home, mem = chat
    note = mem / "feedback_rule.md"
    note.write_text(words + "\n", encoding="utf-8")
    removed = _remove(chat, AUTO)
    assert [(c["memory_says"], c["setting_says"]) for c in removed] == [("when_asked", "auto")]
    assert not note.exists()
    # Where the person chose to say when, the same note agrees with them and stays.
    note.write_text(words + "\n", encoding="utf-8")
    assert _remove(chat, WAIT) == [] and note.exists()


def test_only_the_notes_about_the_apps_updates_leave_a_list_of_rules(chat):
    copy, _home, mem = chat
    index = mem / "MEMORY.md"
    index.write_text("# Memory\n\n" + "".join(f"- {w}\n" for w in OCTOBER[:4] + AGREES_WITH_AUTO
                                               + THEIRS + ["Canadian spelling in resumes"]),
                     encoding="utf-8")
    local = os.path.join(copy, "CLAUDE.local.md")
    with open(local, "w", encoding="utf-8") as fh:
        fh.write("Notes for this computer.\n\n" + OCTOBER[2] + "\n")
    _remove(chat, AUTO)
    kept = index.read_text(encoding="utf-8")
    for w in OCTOBER[:4]:
        assert w not in kept, w
    for w in AGREES_WITH_AUTO + THEIRS + ["Canadian spelling in resumes"]:
        assert w in kept, w
    with open(local, encoding="utf-8") as fh:
        assert fh.read() == "Notes for this computer.\n"


@pytest.mark.parametrize("settings", [AUTO, WAIT])
def test_an_update_that_is_someone_elses_news_stays_whatever_the_setting(chat, settings):
    copy, _home, mem = chat
    index = mem / "MEMORY.md"
    text = "".join(f"- {w}\n" for w in THEIRS)
    index.write_text(text, encoding="utf-8")
    local = os.path.join(copy, "CLAUDE.local.md")
    with open(local, "w", encoding="utf-8") as fh:
        fh.write(THEIRS[4] + "\n")
    assert _remove(chat, settings) == []
    assert index.read_text(encoding="utf-8") == text
    with open(local, encoding="utf-8") as fh:
        assert fh.read() == THEIRS[4] + "\n"


def test_a_memory_file_named_for_app_updates_goes_whole_with_its_index_line(chat):
    """Claude Code keeps one topic per file, with a name, and its lines need not say what
    they are about (code.claude.com/docs/en/memory)."""
    _copy, _home, mem = chat
    topic = mem / "feedback_app_updates.md"
    topic.write_text("---\nname: App updates\ndescription: How to handle new versions\n"
                     "type: feedback\n---\n\nWait for him to say \"update\" before taking one. "
                     "If one is there, say so in one plain line.\n\n**Why:** he likes to choose "
                     "when.\n", encoding="utf-8")
    index = mem / "MEMORY.md"
    index.write_text("- [App updates](feedback_app_updates.md): how to handle new versions\n"
                     "- [Spelling](feedback_spelling.md): Canadian\n", encoding="utf-8")
    removed = _remove(chat, AUTO)
    assert removed and not topic.exists()
    assert index.read_text(encoding="utf-8") == "- [Spelling](feedback_spelling.md): Canadian\n"


def test_a_note_that_takes_updates_without_asking_goes_where_they_wait_for_the_persons_word(chat):
    _copy, _home, mem = chat
    note = mem / "MEMORY.md"
    note.write_text("- Take app updates without asking\n- Only take the app's updates when he "
                    "says\n- " + OCTOBER[2] + "\n", encoding="utf-8")
    removed = _remove(chat, WAIT)
    assert [(c["memory_says"], c["setting_says"]) for c in removed] == [("auto", "when_asked")]
    kept = note.read_text(encoding="utf-8")
    assert "without asking" not in kept and "when he says" in kept and OCTOBER[2] in kept


def test_nothing_is_removed_where_the_person_wrote_no_setting(chat, tmp_path, monkeypatch):
    """fb2068da: a copy whose profile/person.json has not caught up holds no setting to judge by."""
    copy, home, mem = chat
    prof = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), prof,
                    ignore=shutil.ignore_patterns("state", "tests", "__pycache__"))
    monkeypatch.setenv(person.ENV, str(prof))
    person._modules.clear()
    person._data.clear()
    try:
        note = mem / "MEMORY.md"
        note.write_text("- " + "\n- ".join(OCTOBER[:4]) + "\n", encoding="utf-8")
        assert computer.memory_conflicts(copy, home=home) == []
        person.put(["app_updates"], "auto")
        person._data.clear()
        assert {c["memory_says"] for c in computer.memory_conflicts(copy, home=home)} == {"when_asked"}
    finally:
        person._modules.clear()
        person._data.clear()
