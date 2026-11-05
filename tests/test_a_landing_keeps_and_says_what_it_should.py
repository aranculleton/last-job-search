"""A landing keeps this chat's own work, merges what can be merged, and tells the person what
they need to hear, once, in every container (an independent review of the engine, 2026-11-05).

- A branch left behind only because master later changed a file both chats' rows merge into
  (the tracker) is brought in: rows never put older copies over newer ones.
- A branch left behind that holds work the search does not have is named to the person.
- An application this chat changed and master changed too keeps this chat's copy, and says so.
- Two chats' edits to different lines of one note both land; a real clash keeps the other
  side's copy in the spare folder, under documents/ too.
- "Tell the person once" is kept in the person's own committed record, so a fresh container
  does not say it again.
- What tools/save_state.py says to tell the person reaches the landing's own lines.

Real git in a temp dir, invented names, the check faked, as in the landing tests."""
# ruff: noqa: F811  (the landing tests' `copy` fixture, imported and taken as a parameter)
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import merge_state  # noqa: E402
from tests.test_a_chat_lands_its_work_in_one_command import (  # noqa: E402,F401
    PLAN, _append, _base_with_own_files, _commit_days_ago, _land_other, _run, _stranger, copy,
    git, write)

TRACKER = "job_search_tracker.csv"


def _shown(origin, rel, branch="claude/chat-1"):
    return git(origin, "show", f"{branch}:{rel}", check=False).stdout


def _branch_days_ago(other, name, days, files, start="master"):
    git(other, "fetch", "-q", "origin")
    git(other, "switch", "-q", "-c", name, "origin/" + start)
    for rel, text in files.items():
        if rel == TRACKER:
            _append(other, rel, text)
        else:
            write(other, rel, text)
    git(other, "add", "-f", *files)
    _commit_days_ago(other, "work a chat could not save", days)
    git(other, "push", "-q", "origin", name)
    git(other, "switch", "-q", "master")
    git(other, "merge", "-q", "--ff-only", "origin/master")


# ------------------------------------------------------------------ 6: left behind

def test_rows_master_added_later_never_leave_a_branch_behind(copy, capsys):
    origin, chat, other = _stranger(copy)
    _branch_days_ago(other, "claude/rows-old", 5,
                     {TRACKER: "2026-10-31,Birch Mutual,Analyst,drafted\n"})
    _append(other, TRACKER, "2026-11-05,Larkspur Retail,Planner,applied\n")
    _land_other(other, "a row from today")
    write(chat, "profile/notes.md", "first\na note from today\n")
    code, out = _run(chat, "--message", "A note", capsys=capsys)
    assert code == 0, out
    assert "land: brought in work that waited on origin/claude/rows-old" in out, out
    rows = _shown(origin, TRACKER)
    assert "Birch Mutual" in rows and "Larkspur Retail" in rows, rows


def test_a_branch_left_behind_holding_work_the_search_lacks_is_named_to_the_person(copy,
                                                                                  capsys):
    origin, chat, other = _base_with_own_files(copy)
    _branch_days_ago(other, "claude/plan-old", 5,
                     {PLAN: "Plan\n\nFirst: as it was.\n\nSecond: kept.\n",
                      "profile/stories.md": "A story about Lindenmoor\n"})
    write(other, PLAN, "Plan\n\nFirst: as it is now.\n\nSecond: kept.\n")
    _land_other(other, "the plan as it is now")
    write(chat, "profile/notes.md", "first\na note from today\n")
    code, out = _run(chat, "--message", "A note", capsys=capsys)
    assert code == 0, out
    said = [ln for ln in out.splitlines() if "claude/plan-old" in ln]
    assert len(said) == 1 and "Tell the person once" in said[0], out
    assert "profile/stories.md" not in _shown(origin, "profile/stories.md")


# ------------------------------------------------------------------ 9: this chat's application

APP_DRAFT = "documents/applications/alder_freight_analyst/draft.json"
APP_TEX = "cv/Morgan_Ellis_Resume_Alder.tex"


def test_this_chats_tweak_to_an_application_is_kept_over_masters_and_said(copy, capsys):
    origin, chat, other = _stranger(copy)
    write(other, APP_DRAFT, json.dumps({"company": "Alder Freight", "abbr": "Alder",
                                        "summary": "the first"}) + "\n")
    write(other, APP_TEX, "\\item the first\n")
    git(other, "add", "-f", APP_DRAFT, APP_TEX)
    _land_other(other, "an application")
    git(chat, "fetch", "-q", "origin", "master")
    git(chat, "merge", "-q", "--ff-only", "origin/master")
    # This chat tweaks it (a commit of its own, not landed yet)...
    write(chat, APP_DRAFT, json.dumps({"company": "Alder Freight", "abbr": "Alder",
                                       "summary": "this chat's tweak"}) + "\n")
    write(chat, APP_TEX, "\\item this chat's tweak\n")
    git(chat, "add", "-f", APP_DRAFT, APP_TEX)
    _commit_days_ago(chat, "a tweak", 1)
    # ...and another chat changed it later, on master.
    write(other, APP_DRAFT, json.dumps({"company": "Alder Freight", "abbr": "Alder",
                                        "summary": "the other chat's"}) + "\n")
    write(other, APP_TEX, "\\item the other chat's\n")
    git(other, "add", "-f", APP_DRAFT, APP_TEX)
    _land_other(other, "the other chat's change")
    code, out = _run(chat, "--message", "A tweak", capsys=capsys)
    assert code == 0, out
    assert "this chat's tweak" in _shown(origin, APP_TEX), _shown(origin, APP_TEX)
    assert "this chat's tweak" in _shown(origin, APP_DRAFT)
    said = [ln for ln in out.splitlines() if "Tell the person once" in ln]
    assert said and "Alder Freight" in said[0], out


# ------------------------------------------------------------------ 10: line merges, spares

def test_two_chats_edits_to_different_lines_of_one_note_both_land(copy, capsys):
    origin, chat, other = _stranger(copy)
    note = "documents/prep/call_notes.md"
    write(other, note, "one\ntwo\nthree\nfour\nfive\nsix\n")
    _land_other(other, "a note")
    git(chat, "fetch", "-q", "origin", "master")
    git(chat, "merge", "-q", "--ff-only", "origin/master")
    write(chat, note, "one, from this chat\ntwo\nthree\nfour\nfive\nsix\n")
    write(other, note, "one\ntwo\nthree\nfour\nfive\nsix, from the other chat\n")
    _land_other(other, "the other chat's line")
    code, out = _run(chat, "--message", "A line", capsys=capsys)
    assert code == 0, out
    assert _shown(origin, note) == "one, from this chat\ntwo\nthree\nfour\nfive\nsix, from the other chat\n"


def test_a_real_clash_in_a_document_keeps_the_other_side_in_the_spare_folder(copy, capsys):
    origin, chat, other = _stranger(copy)
    note = "documents/prep/call_notes.md"
    write(other, note, "one\n")
    _land_other(other, "a note")
    git(chat, "fetch", "-q", "origin", "master")
    git(chat, "merge", "-q", "--ff-only", "origin/master")
    write(chat, note, "one, from this chat\n")
    write(other, note, "one, from the other chat\n")
    _land_other(other, "the other chat's line")
    code, out = _run(chat, "--message", "A line", capsys=capsys)
    assert code == 0, out
    kept = _shown(origin, note)
    spare = os.path.join(str(chat), merge_state.SPARE_DIR)
    lost = "one, from this chat\n" if "other chat" in kept else "one, from the other chat\n"
    copies = [open(os.path.join(spare, n), encoding="utf-8").read() for n in os.listdir(spare)] \
        if os.path.isdir(spare) else []
    assert lost in copies, (kept, copies)


# ------------------------------------------------------------------ 12: said once, committed

def test_a_fresh_container_does_not_tell_the_person_again(copy, capsys, tmp_path):
    origin, chat, other = _stranger(copy)
    git(other, "switch", "-q", "-c", "claude/lost-chat", "master")
    write(other, "profile/stories.md", "A story about Lindenmoor\n")
    _commit_days_ago(other, "work a chat could not save", 19)
    git(other, "push", "-q", "origin", "claude/lost-chat")
    git(other, "switch", "-q", "master")
    write(chat, "profile/notes.md", "first\na note from today\n")
    code, out = _run(chat, "--message", "A note", capsys=capsys)
    said = [ln for ln in out.splitlines() if "claude/lost-chat" in ln]
    assert len(said) == 1 and "Tell the person once" in said[0], out
    # Its pull request is merged on GitHub.
    git(other, "fetch", "-q", "origin")
    git(other, "merge", "-q", "--no-ff", "--no-edit", "origin/claude/chat-1")
    git(other, "push", "-q", "origin", "master")
    # A fresh container: a new clone, its own branch, nothing in its .git.
    fresh = tmp_path / "fresh"
    git(tmp_path, "clone", "-q", str(origin), str(fresh))
    git(fresh, "switch", "-q", "-c", "claude/chat-2")
    write(fresh, "profile/notes.md", "first\na note from today\nand another\n")
    code, out = _run(fresh, "--message", "Another note", capsys=capsys)
    said = [ln for ln in out.splitlines() if "claude/lost-chat" in ln]
    assert len(said) == 1 and "Tell the person" not in said[0], out


# ------------------------------------------------------------------ 15: save_state's words

def test_what_the_save_says_to_tell_the_person_is_passed_on(copy, capsys, monkeypatch):
    _origin, chat, _other = copy
    monkeypatch.setattr(merge_state, "clear_old_copies",
                        lambda root: ([], ["profile/notes.md.from-another-chat"]))
    write(chat, "profile/notes.md", "first\na note from today\n")
    code, out = _run(chat, "--message", "A note", capsys=capsys)
    assert code == 0, out
    said = [ln for ln in out.splitlines() if ln.startswith("land: ") and
            "tell the person once" in ln.lower() and "extra copy" in ln]
    assert len(said) == 1, out
