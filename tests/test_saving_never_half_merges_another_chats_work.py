"""Saving never half-merges another chat's work (the maintainer, 2026-11-04). A landing that
brought in another chat's unmerged branch said "this chat's version kept" of a clashing file
and still merged the other side's other lines into it: a resume's .tex kept this chat's skills
line but took the other chat's older bullets back, so the .tex and its .pdf disagreed, and the
other chat's draft.json and letters came in with no word. It also saved the other side's copy
as a *.from-another-chat file in the person's folders. Real git in a temp dir, invented names,
and the check faked, as in the landing tests."""
# ruff: noqa: F811  (the landing tests' `copy` fixture, imported and taken as a parameter)
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import land  # noqa: E402
import merge_state  # noqa: E402
import save_state  # noqa: E402
from tests.test_a_chat_lands_its_work_in_one_command import (  # noqa: E402,F401
    _append, _commit_days_ago, _land_other, _run, _stranger, copy, git, write)

FOLDER = "documents/applications/alder_freight_analyst_alder/"
TEX = "cv/Morgan_Ellis_Resume_Alder.tex"
PDF = "cv/Morgan_Ellis_Resume_Alder.pdf"
LETTER = "cover_letters/Morgan_Ellis_Cover_Letter_Alder.tex"
LETTER_PDF = "cover_letters/Morgan_Ellis_Cover_Letter_Alder.pdf"
DRAFT = FOLDER + "draft.json"
PREP = FOLDER + "interview_prep.md"
APP = (TEX, PDF, LETTER, LETTER_PDF, DRAFT)


def _resume(skills, bullets):
    return ("\\name{Morgan Ellis}\n\\section{Skills}\n%s\n\n\\section{Summary}\nA summary.\n"
            "A second line.\nA third line.\n\n\\section{Experience}\n%s\n" % (skills, bullets))


def _draft(summary):
    return json.dumps({"company": "Alder Freight", "role": "Analyst", "abbr": "Alder",
                       "summary": summary}, indent=1) + "\n"


def _save(repo, paths, message, days=0):
    for p in paths:
        git(repo, "add", "-f", p)
    _commit_days_ago(repo, message, days)


def _shown(origin, rel, branch="claude/chat-1"):
    return git(origin, "show", "%s:%s" % (branch, rel), check=False).stdout


def _tree(repo, rev="HEAD"):
    return git(repo, "ls-tree", "-r", "--name-only", rev).stdout.split()


def _copies_beside(repo):
    out = []
    for _dp, dirs, names in os.walk(str(repo)):
        dirs[:] = [d for d in dirs if d not in (".git", merge_state.SPARE_DIR)]
        out += [n for n in names if merge_state.SIDE in n]
    return out


def _application_on_master(copy):
    """The Alder application on master and in the chat: resume, letter, both PDFs, the
    draft and an interview prep."""
    origin, chat, other = _stranger(copy)
    write(other, TEX, _resume("Python, SQL", "\\item The first bullet."))
    write(other, PDF, "%PDF the first render\n")
    write(other, LETTER, "Dear Alder Freight, the first letter.\n")
    write(other, LETTER_PDF, "%PDF the first letter\n")
    write(other, DRAFT, _draft("the first summary"))
    write(other, PREP, "# Prep\n\nNothing yet.\n")
    _save(other, APP + (PREP,), "the Alder application", days=3)
    git(other, "push", "-q", "origin", "master")
    git(chat, "fetch", "-q", "origin", "master")
    git(chat, "merge", "-q", "--ff-only", "origin/master")
    return origin, chat, other


def test_an_application_this_chat_changed_keeps_every_file_as_this_chat_has_it(copy, capsys):
    """The maintainer's case: another chat's branch, a day old and never landed, changed the
    Alder resume's bullets, its PDF, the draft and the letter; this chat changed the skills
    line and made the PDF again. Every file of the application stays as this chat has it,
    none of the other's comes in, and the person is told once in plain words. What the other
    chat changed that this chat did not (a story, a tracker row, the interview prep, which is
    not made from the draft) still comes in: that is what the sweep is for."""
    origin, chat, other = _application_on_master(copy)
    git(other, "switch", "-q", "-c", "claude/other-chat", "master")
    write(other, TEX, _resume("Python, SQL", "\\item An older bullet, put back."))
    write(other, PDF, "%PDF the other chat's render\n")
    write(other, LETTER, "Dear Alder Freight, the other chat's letter.\n")
    write(other, LETTER_PDF, "%PDF the other chat's letter\n")
    write(other, DRAFT, _draft("the other chat's summary"))
    write(other, PREP, "# Prep\n\nThe other chat's prep for the first call.\n")
    write(other, "profile/stories.md", "A story about Lindenmoor\n")
    _append(other, "job_search_tracker.csv", "2026-11-03,Birch Mutual,Analyst,drafted\n")
    _save(other, APP + (PREP, "profile/stories.md", "job_search_tracker.csv"),
          "the other chat's work", days=1)
    git(other, "push", "-q", "origin", "claude/other-chat")

    mine = _resume("Python, SQL, Claude Code", "\\item The first bullet.")
    write(chat, TEX, mine)
    write(chat, PDF, "%PDF this chat's render\n")
    _save(chat, (TEX, PDF), "Alder: the skills line")
    code, out = _run(chat, "--message", "Alder resume", capsys=capsys)
    assert code == 0, out
    assert "land: brought in work that waited on origin/claude/other-chat" in out, out

    assert _shown(origin, TEX) == mine
    assert _shown(origin, PDF) == "%PDF this chat's render\n"
    assert _shown(origin, DRAFT) == _draft("the first summary")
    assert _shown(origin, LETTER) == "Dear Alder Freight, the first letter.\n"
    assert _shown(origin, LETTER_PDF) == "%PDF the first letter\n"
    assert "The other chat's prep" in _shown(origin, PREP)
    assert "Lindenmoor" in _shown(origin, "profile/stories.md")
    assert "Birch Mutual" in _shown(origin, "job_search_tracker.csv")
    assert not [p for p in _tree(origin, "claude/chat-1") if merge_state.SIDE in p]
    assert _copies_beside(chat) == []
    told = [ln for ln in out.splitlines() if "Tell the person once" in ln]
    assert len(told) == 1 and "your application to Alder Freight" in told[0], out
    assert "the one you have now is kept" in told[0]
    # The other chat's version is not lost: it is in the saved history.
    assert "An older bullet" in git(chat, "show", "HEAD^2:" + TEX).stdout


def test_a_file_this_chat_changed_keeps_this_chats_whole_copy(copy, capsys):
    """A plan both chats changed in different places was merged line by line. This chat's
    whole copy stands now. The person's own profile is the exception, where what they told
    either chat is kept (both changes merged), and so are the tracker's rows."""
    origin, chat, other = _stranger(copy)
    plan = "documents/plan.md"
    write(other, plan, "Plan\n\nFirst: the base.\n\nA\nB\nC\n\nLast: the base.\n")
    write(other, "profile/CLAUDE.md", "# Their own rules\n\n- One rule.\n\nA\nB\nC\n\n- Two.\n")
    _land_other(other, "the plan")
    git(chat, "fetch", "-q", "origin", "master")
    git(chat, "merge", "-q", "--ff-only", "origin/master")
    git(other, "switch", "-q", "-c", "claude/other-chat", "master")
    write(other, plan, "Plan\n\nFirst: the other chat's.\n\nA\nB\nC\n\nLast: the base.\n")
    write(other, "profile/CLAUDE.md",
          "# Their own rules\n\n- One rule, said in the other chat.\n\nA\nB\nC\n\n- Two.\n")
    _append(other, "job_search_tracker.csv", "2026-11-03,Birch Mutual,Analyst,drafted\n")
    _save(other, (plan, "profile/CLAUDE.md", "job_search_tracker.csv"), "other", days=1)
    git(other, "push", "-q", "origin", "claude/other-chat")

    mine = "Plan\n\nFirst: the base.\n\nA\nB\nC\n\nLast: this chat's.\n"
    write(chat, plan, mine)
    write(chat, "profile/CLAUDE.md",
          "# Their own rules\n\n- One rule.\n\nA\nB\nC\n\n- Two, said in this chat.\n")
    _append(chat, "job_search_tracker.csv", "2026-11-04,Penrose Data,Analyst,drafted\n")
    code, out = _run(chat, "--message", "The plan", capsys=capsys)
    assert code == 0 and "brought in work that waited on origin/claude/other-chat" in out, out
    assert _shown(origin, plan) == mine
    assert any("this chat's whole copy kept of 1 file(s)" in ln and plan in ln
               for ln in out.splitlines()), out
    rules = _shown(origin, "profile/CLAUDE.md")
    assert "said in the other chat" in rules and "said in this chat" in rules
    tracker = _shown(origin, "job_search_tracker.csv")
    assert "Birch Mutual" in tracker and "Penrose Data" in tracker


def test_a_clash_keeps_this_chats_whole_file_and_no_copy_in_the_persons_folders(copy):
    """A clash in a file no other rule covers (a note, a setting): this chat's whole file,
    with nothing of the other's merged into it, and the other's whole file kept out of the
    person's folders (the saved history, and a folder here that is never saved). A setting
    also asks the person, with where Claude finds the other version."""
    origin, chat, other = _stranger(copy)
    notes = "networking/notes.md"
    write(other, notes, "Notes\n\nOne: base.\n\nA\nB\nC\n\nTwo: base.\n")
    _land_other(other, "notes")
    git(chat, "fetch", "-q", "origin", "master")
    git(chat, "merge", "-q", "--ff-only", "origin/master")
    write(other, notes, "Notes\n\nOne: the other chat's.\n\nA\nB\nC\n\nTwo: the other's.\n")
    write(other, "profile/search.py", "SALARY_FLOOR = 55000\n")
    _land_other(other, "the other chat")
    mine = "Notes\n\nOne: base.\n\nA\nB\nC\n\nTwo: this chat's.\n"
    write(chat, notes, mine)
    write(chat, "profile/search.py", "SALARY_FLOOR = 60000\n")
    _save(chat, (notes, "profile/search.py"), "this chat")
    git(chat, "fetch", "-q", "origin", "master")
    ok, said = land.merge_in(str(chat), "origin/master")
    assert ok, said
    with open(os.path.join(str(chat), notes), encoding="utf-8") as fh:
        assert fh.read() == mine
    assert any(notes in ln and "this chat's whole version kept" in ln for ln in said), said
    assert _copies_beside(chat) == []
    assert not [p for p in _tree(chat) if merge_state.SIDE in p]
    assert len(os.listdir(os.path.join(str(chat), merge_state.SPARE_DIR))) == 2
    assert git(chat, "status", "--porcelain", "--", merge_state.SPARE_DIR).stdout == ""
    with open(os.path.join(str(chat), "profile", "search.py"), encoding="utf-8") as fh:
        search = fh.read()
    assert "SALARY_FLOOR = 60000" in search and merge_state.ASK_SIDE in search
    compile(search, "search.py", "exec")
    rev, path = re.search(r"git show (\S+):(\S+)", search).groups()
    assert git(chat, "show", "%s:%s" % (rev, path)).stdout == "SALARY_FLOOR = 55000\n"


@pytest.mark.parametrize("later", ["this chat", "master"])
def test_an_application_both_sides_changed_comes_whole_from_the_later(copy, later):
    """Merging master: an application this chat and a landed chat both changed comes whole
    from the side that changed it last, its .tex, .pdf and draft together, never a .tex
    merged line by line beside a .pdf made from one side."""
    origin, chat, other = _application_on_master(copy)
    theirs = _resume("Python, SQL", "\\item The landed chat's bullet.")
    write(other, TEX, theirs)
    write(other, PDF, "%PDF the landed chat's render\n")
    write(other, DRAFT, _draft("the landed chat's summary"))
    _save(other, (TEX, PDF, DRAFT), "the landed chat", days=2 if later == "this chat" else 0)
    git(other, "push", "-q", "origin", "master")
    mine = _resume("Python, SQL, Claude Code", "\\item The first bullet.")
    write(chat, TEX, mine)
    write(chat, PDF, "%PDF this chat's render\n")
    _save(chat, (TEX, PDF), "this chat", days=0 if later == "this chat" else 2)
    git(chat, "fetch", "-q", "origin", "master")
    ok, said = land.merge_in(str(chat), "origin/master")
    assert ok, said
    got = {p: git(chat, "show", "HEAD:" + p).stdout for p in (TEX, PDF, DRAFT)}
    if later == "this chat":
        assert got == {TEX: mine, PDF: "%PDF this chat's render\n",
                       DRAFT: _draft("the first summary")}
    else:
        assert got == {TEX: theirs, PDF: "%PDF the landed chat's render\n",
                       DRAFT: _draft("the landed chat's summary")}
    assert any("an application both sides changed" in ln for ln in said), said


def test_copies_an_older_version_saved_in_the_persons_folders_are_cleared_by_the_next_save(
        copy, capsys):
    """The copies a settle saved beside a note or a setting before this: cleared by the next
    save where the file beside is identical or newer. One the person is still asked about
    (a [CONFIRM: ...] naming it) is left until they answer, and not named again."""
    origin, chat, other = copy
    write(chat, "networking/notes.md", "the note in use\n")
    write(chat, "networking/notes.md.from-another-chat", "the other chat's note\n")
    write(chat, "rounds/r1.md", "same\n")
    write(chat, "rounds/r1.md.from-another-chat", "same\n")
    write(chat, "profile/search.py", "# [CONFIRM: two of your chats changed this file at the "
          "same time; the later version is kept here and the other is saved beside it as "
          "search.py.from-another-chat: which one stays]\nSALARY_FLOOR = 60000\n")
    write(chat, "profile/search.py.from-another-chat", "SALARY_FLOOR = 55000\n")
    git(chat, "add", "-A", "-f")
    _commit_days_ago(chat, "an older version saved copies", 2)
    assert save_state.main([], root=str(chat)) == 0
    out = capsys.readouterr().out
    assert sorted(_copies_beside(chat)) == ["search.py.from-another-chat"], out
    assert "cleared 2 extra copy" in out and "tell the person" not in out, out
    git(chat, "commit", "-q", "-m", "the save")
    assert not [p for p in _tree(chat) if p.startswith(("networking/", "rounds/"))
                and merge_state.SIDE in p]
    # Once the person has answered, the next save clears the last one.
    write(chat, "profile/search.py", "SALARY_FLOOR = 60000\n")
    git(chat, "add", "-A", "-f")
    git(chat, "commit", "-q", "-m", "the person chose")
    assert save_state.main([], root=str(chat)) == 0
    assert _copies_beside(chat) == []
