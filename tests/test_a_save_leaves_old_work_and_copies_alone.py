"""A save never sweeps in old unsaved work unannounced, and never leaves side copies beside
the person's documents or tests (the maintainer, 2026-11-04: 19-day-old work was swept in and
dozens of *.from-another-chat files were left beside resumes, letters and tests). Real git in
a temp dir; invented names."""
# ruff: noqa: F811  (the landing tests' `copy` fixture, imported and taken as a parameter)
import os
import sys

from tests import repo_files  # noqa: E402
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import land  # noqa: E402
import merge_state  # noqa: E402
import save_state  # noqa: E402
from tests.test_a_chat_lands_its_work_in_one_command import (  # noqa: E402,F401
    _commit_days_ago, _land_other, _no_copies_beside, _run, _stranger, copy, git, write)

RESUME = "cv/Resume_Alder_Freight.tex"
OWN_TEST = "profile/tests/test_my_floor.py"


def test_a_branch_nineteen_days_old_is_left_and_named_once(copy, capsys):
    origin, chat, other = _stranger(copy)
    git(other, "switch", "-q", "-c", "claude/lost-chat", "master")
    write(other, "profile/stories.md", "A story about Lindenmoor\n")
    _commit_days_ago(other, "work a chat could not save", 19)
    git(other, "push", "-q", "origin", "claude/lost-chat")
    write(chat, "profile/notes.md", "first\na note from today\n")
    code, out = _run(chat, "--message", "A note", capsys=capsys)
    assert code == 0, out
    said = [ln for ln in out.splitlines() if "claude/lost-chat" in ln]
    assert len(said) == 1 and "19 days old" in said[0] and "Tell the person once" in said[0], out
    assert "brought in work that waited" not in out
    assert git(origin, "show", "claude/chat-1:profile/stories.md", check=False).returncode != 0
    assert "claude/lost-chat" in git(origin, "branch", "--format=%(refname:short)").stdout
    # The next landing does not say it to the person again.
    write(chat, "profile/notes.md", "first\na second note\n")
    code, out = _run(chat, "--message", "Again", capsys=capsys)
    said = [ln for ln in out.splitlines() if "claude/lost-chat" in ln]
    assert len(said) == 1 and "Tell the person" not in said[0], out
    assert "claude/lost-chat" not in land.waiting(str(chat)) and \
        list(land.left_behind(str(chat))) == ["origin/claude/lost-chat"]


def test_a_branch_a_few_days_old_is_still_brought_in(copy, capsys):
    origin, chat, other = _stranger(copy)
    git(other, "switch", "-q", "-c", "claude/recent-chat", "master")
    write(other, "profile/stories.md", "A story about Lindenmoor\n")
    _commit_days_ago(other, "work a chat could not save", 4)
    git(other, "push", "-q", "origin", "claude/recent-chat")
    write(chat, "profile/notes.md", "first\na note from today\n")
    code, out = _run(chat, "--message", "A note", capsys=capsys)
    assert "land: brought in work that waited on origin/claude/recent-chat" in out, out


def test_unsaved_files_here_over_a_week_old_are_saved_and_named(copy, capsys):
    origin, chat, other = copy
    write(chat, "profile/stories.md", "An edit of the person's own\n")
    old = time.time() - 19 * 86400
    os.utime(os.path.join(str(chat), "profile", "stories.md"), (old, old))
    code, out = _run(chat, "--message", "Stories", capsys=capsys)
    assert code == 0 and "profile/stories.md" in out and "Tell the person once" in out, out
    assert "An edit of the person's own" in git(origin, "show",
                                               "claude/chat-1:profile/stories.md").stdout


def _both_change(copy, path, text_a, text_b, a_days_ago, b_days_ago):
    origin, chat, other = _stranger(copy)
    write(other, path, "base\n")
    _land_other(other, "base")
    git(chat, "fetch", "-q", "origin", "master")
    git(chat, "merge", "-q", "--ff-only", "origin/master")
    write(other, path, text_a)
    git(other, "add", "-A")
    git(other, "add", "-f", path)
    _commit_days_ago(other, "other chat", a_days_ago)
    git(other, "push", "-q", "origin", "master")
    write(chat, path, text_b)
    git(chat, "add", "-f", path)
    _commit_days_ago(chat, "this chat", b_days_ago)
    git(chat, "fetch", "-q", "origin", "master")
    return origin, chat, other


def _files_like(chat, needle):
    out = []
    for _dp, dirs, names in os.walk(str(chat)):
        dirs[:] = [d for d in dirs if d != ".git"]
        out += [n for n in names if needle in n]
    return out


def test_a_resume_two_chats_made_keeps_the_later_with_no_copy_anywhere(copy):
    origin, chat, other = _both_change(copy, RESUME, "other chat's resume\n",
                                       "this chat's resume\n", 3, 0)
    ok, said = land.merge_in(str(chat), "origin/master")
    assert ok, said
    with open(os.path.join(str(chat), RESUME), encoding="utf-8") as fh:
        assert fh.read() == "this chat's resume\n"
    assert _files_like(chat, "from-another-chat") == []
    assert any("the later one is kept" in ln for ln in said), said


def test_the_other_chats_resume_stays_when_it_is_the_later(copy):
    origin, chat, other = _both_change(copy, RESUME, "other chat's resume\n",
                                       "this chat's resume\n", 0, 3)
    ok, said = land.merge_in(str(chat), "origin/master")
    assert ok, said
    with open(os.path.join(str(chat), RESUME), encoding="utf-8") as fh:
        assert fh.read() == "other chat's resume\n"
    assert _files_like(chat, "from-another-chat") == []


def test_a_test_of_their_own_keeps_the_later_and_the_other_goes_in_one_folder(copy):
    origin, chat, other = _both_change(copy, OWN_TEST, "# other\n", "# mine\n", 3, 0)
    ok, said = land.merge_in(str(chat), "origin/master")
    assert ok, said
    with open(os.path.join(str(chat), OWN_TEST), encoding="utf-8") as fh:
        assert fh.read() == "# mine\n"
    assert _files_like(chat, "from-another-chat") == []
    kept = os.listdir(os.path.join(str(chat), merge_state.SPARE_DIR))
    assert len(kept) == 1
    assert git(chat, "status", "--porcelain", "--", merge_state.SPARE_DIR).stdout == ""


def test_spare_copies_are_tidied_after_a_while(tmp_path):
    d = tmp_path / merge_state.SPARE_DIR
    d.mkdir()
    (d / "old").write_text("x")
    (d / "new").write_text("y")
    long_ago = time.time() - 40 * 86400
    os.utime(d / "old", (long_ago, long_ago))
    merge_state.tidy_spares(str(tmp_path))
    assert sorted(os.listdir(d)) == ["new"]


def test_a_save_clears_copies_older_versions_left_and_names_the_rest(copy, capsys):
    origin, chat, other = copy
    write(chat, "documents/cv/Resume_A.tex", "same\n")
    write(chat, "documents/cv/Resume_A.tex.from-another-chat", "same\n")
    write(chat, "cover_letters/Letter_B.tex", "the later letter\n")
    write(chat, "cover_letters/Letter_B.tex.from-another-chat", "an earlier letter\n")
    git(chat, "add", "-A", "-f")
    _commit_days_ago(chat, "older versions left copies", 3)
    write(chat, "cover_letters/Letter_B.tex", "the later letter, edited\n")
    git(chat, "add", "-A", "-f")
    _commit_days_ago(chat, "edited later", 0)
    write(chat, "profile/tests/test_c.py", "# beside\n")
    write(chat, "profile/tests/test_c.py.from-another-chat", "# a newer copy\n")
    later = time.time() + 5
    os.utime(os.path.join(str(chat), "profile/tests/test_c.py.from-another-chat"), (later, later))
    write(chat, "documents/Orphan.md.from-another-chat", "nothing beside it\n")
    assert save_state.main([], root=str(chat)) == 0
    out = capsys.readouterr().out
    left = _files_like(chat, "from-another-chat")
    assert sorted(left) == ["Orphan.md.from-another-chat", "test_c.py.from-another-chat"], left
    assert "cleared 2 extra copy" in out and "2 extra copy(ies)" in out and "tell the person" in out
    assert repo_files.tracked("documents/cv", root=chat, app_only=False) == ["documents/cv/Resume_A.tex"]
