"""Saving goes on when a file goes away while it runs, and a landed branch is left level with
its copy on GitHub (a live session, 2026-11-05).

An upgrade was making the PDFs again during a landing, and the whole save stopped on "git
refused: fatal: unable to stat 'cv/<name>.pdf': No such file or directory; nothing was
pushed". And after --after-merge the branch stood one merge commit (master's own) ahead of
its copy on GitHub, so a check for unpushed work held the chat until it was pushed by hand.
Real git in a temp dir, invented names, the check faked, as in the landing tests."""
# ruff: noqa: F811  (the landing tests' `copy` fixture, imported and taken as a parameter)
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import land  # noqa: E402
import save_state  # noqa: E402
from tests.test_a_chat_lands_its_work_in_one_command import (  # noqa: E402,F401
    _run, copy, git, write)

GOES = "cv/Morgan_Ellis_Resume_Alder.pdf"
STAYS = "cv/Morgan_Ellis_Resume_Birch.pdf"
REFUSED = "cv/Morgan_Ellis_Resume_Carrow.pdf"


def _pdfs(chat):
    for rel in (GOES, STAYS):
        write(chat, rel, "%PDF " + rel + "\n")
    write(chat, "profile/notes.md", "first\na note from today\n")


def _pushed(origin, branch="claude/chat-1"):
    return git(origin, "ls-tree", "-r", "--name-only", branch, check=False).stdout.split()


def test_a_file_that_goes_away_between_listing_and_staging_is_skipped(copy, capsys,
                                                                      monkeypatch):
    origin, chat, _other = copy
    _pdfs(chat)
    listed = save_state.paths

    def making_it_again(root):
        got = listed(root)
        # The save's own listing, then the upgrade takes it away for a moment: listed, and
        # gone by the time it is staged.
        if sys._getframe(1).f_code.co_name == "main" and os.path.exists(
                os.path.join(root, GOES)):
            os.remove(os.path.join(root, GOES))
        return got
    monkeypatch.setattr(save_state, "paths", making_it_again)
    code, out = _run(chat, "--message", "Notes", capsys=capsys)
    assert code == 0 and "land: ready claude/chat-1" in out, out
    pushed = _pushed(origin)
    assert STAYS in pushed and "profile/notes.md" in pushed and GOES not in pushed
    assert "Tell the person" not in out


def test_a_file_that_goes_away_while_git_stages_it_is_tried_once_more(copy, capsys,
                                                                      monkeypatch):
    """The words git gave in the live session, while it was staging the batch."""
    _origin, chat, _other = copy
    _pdfs(chat)
    real = save_state._git
    seen = []

    def racing(root, *args):
        if args[:2] == ("add", "-f") and not seen:
            seen.append(args)
            os.remove(os.path.join(root, GOES))
            return subprocess.CompletedProcess(args, 128, "", "fatal: unable to stat '%s': No "
                                               "such file or directory\n" % GOES)
        return real(root, *args)
    monkeypatch.setattr(save_state, "_git", racing)
    assert save_state.main([], root=str(chat)) == 0
    out = capsys.readouterr().out
    staged = git(chat, "diff", "--cached", "--name-only").stdout.split()
    assert STAYS in staged and "profile/notes.md" in staged and GOES not in staged
    assert "went away while this ran" in out and "Nothing to tell the person" in out
    assert "git refused" not in out


def test_a_file_git_will_not_take_is_named_and_the_rest_still_lands(copy, capsys, monkeypatch):
    origin, chat, _other = copy
    _pdfs(chat)
    write(chat, REFUSED, "%PDF a file git will not read\n")
    real = save_state._git

    def refusing(root, *args):
        if args[:1] == ("add",) and REFUSED in args:
            return subprocess.CompletedProcess(args, 128, "", "error: open(\"%s\"): Permission "
                                               "denied\nfatal: adding files failed\n" % REFUSED)
        return real(root, *args)
    monkeypatch.setattr(save_state, "_git", refusing)
    code, out = _run(chat, "--message", "Notes", capsys=capsys)
    assert code == 0 and "land: ready claude/chat-1" in out, out
    pushed = _pushed(origin)
    assert GOES in pushed and STAYS in pushed and REFUSED not in pushed
    said = [ln for ln in out.splitlines() if ln.startswith("land: left out 1 file(s) git")]
    assert len(said) == 1 and REFUSED in said[0] and "Tell the person once" in said[0], out
    assert "One of your files could not be saved just now" in said[0]


def _landed_and_merged(chat, other, capsys):
    write(chat, "profile/notes.md", "second\n")
    assert _run(chat, capsys=capsys)[0] == 0
    git(other, "fetch", "-q", "origin", "claude/chat-1")
    git(other, "merge", "-q", "--no-ff", "--no-edit", "FETCH_HEAD")     # GitHub merges it
    git(other, "push", "-q", "origin", "master")


def _nothing_unpushed(origin, chat):
    head = git(chat, "rev-parse", "HEAD").stdout.strip()
    assert git(chat, "rev-list", "--count", "origin/claude/chat-1..HEAD").stdout.strip() == "0"
    assert git(origin, "rev-parse", "claude/chat-1").stdout.strip() == head
    assert git(origin, "rev-parse", "master").stdout.strip() == head
    assert land.unpushed(str(chat)) == 0
    assert land.save_due(str(chat), "a chat", "2026-11-05") == []


def test_after_the_merge_the_branch_is_level_with_its_copy_on_github(copy, capsys):
    origin, chat, other = copy
    _landed_and_merged(chat, other, capsys)
    code, out = _run(chat, "--after-merge", capsys=capsys)
    assert code == 0 and "starts from master now" in out, out
    _nothing_unpushed(origin, chat)
    # The next piece of work lands as before, a plain fast-forward of the same branch.
    write(chat, "profile/notes.md", "third\n")
    code, out = _run(chat, capsys=capsys)
    assert code == 0 and "land: ready claude/chat-1 (1 commit(s) ahead of master)" in out


def test_after_the_merge_merges_that_hold_nothing_new_are_not_newer_work(copy, capsys,
                                                                         monkeypatch):
    """A page update took master after the push, and its merge could not be told clean (a
    git before 2.38): merged with master again, it holds nothing master lacks, so the branch
    starts from master, level, never commits ahead of GitHub."""
    origin, chat, other = copy
    write(chat, "profile/notes.md", "second\n")
    assert _run(chat, capsys=capsys)[0] == 0
    write(other, "profile/later.md", "later\n")
    git(other, "add", "profile/later.md")
    git(other, "commit", "-q", "-m", "a later chat")
    git(other, "push", "-q", "origin", "master")
    git(chat, "fetch", "-q", "origin", "master")
    git(chat, "merge", "-q", "--no-edit", "origin/master")             # the page update
    git(other, "fetch", "-q", "origin", "claude/chat-1")
    git(other, "merge", "-q", "--no-ff", "--no-edit", "FETCH_HEAD")
    git(other, "push", "-q", "origin", "master")
    monkeypatch.setattr(land, "_clean_merges", lambda root: False)
    code, out = _run(chat, "--after-merge", capsys=capsys)
    assert code == 0 and "starts from master now" in out, out
    _nothing_unpushed(origin, chat)
    assert os.path.exists(os.path.join(str(chat), "profile", "later.md"))
