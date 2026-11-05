"""A chat lands its work on master with one background command, tools/land.py.

Landing took about fourteen steps (save, commit, the check, fetch, merge, push, open the pull
request, merge it, unsubscribe, a stash and a checkout of master), each re-reading the whole
chat, and chats ran the three-minute check in the foreground (2026-11-03). These run it on a
throwaway copy with a bare origin, never a real one, with the check faked by a parameter so
the real suite is not run: what it commits, that it merges master before the check, that a
red check, a conflict or nothing to land pushes nothing, that the app's files are never
committed, that a network failure is retried and a refusal is not, and that after the merge
the branch starts from master with no checkout dance.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import land  # noqa: E402

GREEN = [sys.executable, "-c", "print('  documents   SKIP  (no LaTeX here)'); print('Green.')"]
RED = [sys.executable, "-c",
       "print('  tests                     FAIL'); print('      AssertionError: boom'); "
       "print('1 passed, 1 failed, 0 skipped'); print('Not green. Do not push to master.'); "
       "raise SystemExit(1)"]
NEVER = [sys.executable, "-c", "raise SystemExit('the check ran')"]


def git(cwd, *args, check=True):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=check)


def write(repo, rel, text):
    p = os.path.join(str(repo), rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)


@pytest.fixture
def copy(tmp_path, monkeypatch):
    """(origin, chat, other): a bare origin holding master, a chat on a branch of its own, and
    a second chat's clone that can move master underneath it."""
    for k, v in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@example.com"),
                 ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@example.com")):
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("LJS_LAND_CHECK", raising=False)
    origin, seed = tmp_path / "origin.git", tmp_path / "seed"
    git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    git(tmp_path, "init", "-q", "-b", "master", str(seed))
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as fh:
        write(seed, ".gitignore", fh.read())
    write(seed, "tools/example.py", "print('the app')\n")
    write(seed, "profile/person.json", "{}\n")
    write(seed, "profile/notes.md", "first\n")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "the person's start")
    git(seed, "remote", "add", "origin", str(origin))
    git(seed, "push", "-q", "origin", "master")
    chat, other = tmp_path / "chat", tmp_path / "other"
    git(tmp_path, "clone", "-q", str(origin), str(chat))
    git(chat, "switch", "-q", "-c", "claude/chat-1")
    git(tmp_path, "clone", "-q", str(origin), str(other))
    return origin, chat, other


def _run(chat, *argv, check=GREEN, capsys=None):
    code = land.main(list(argv), root=str(chat), check=check, sleep=lambda s: None)
    return code, (capsys.readouterr().out if capsys else "")


def _branches(origin):
    return git(origin, "branch", "--format=%(refname:short)").stdout.split()


def test_the_work_is_saved_merged_with_master_checked_and_pushed(copy, capsys):
    origin, chat, other = copy
    # Another chat landed on master meanwhile; the check must see its work too.
    write(other, "documents/network/c1/draft.md", "theirs\n")
    git(other, "add", "-f", "documents/network/c1/draft.md")
    git(other, "commit", "-q", "-m", "another chat's work")
    git(other, "push", "-q", "origin", "master")
    write(chat, "job_search_tracker.csv", "company\nLarkspur\n")      # ignored: forced in
    write(chat, "cv/Morgan_Ellis_Resume_LK.log", "noise\n")           # build noise: never
    sees_both = [sys.executable, "-c",
                 "import os, sys; sys.exit(0 if os.path.exists('documents/network/c1/draft.md') "
                 "and os.path.exists('job_search_tracker.csv') else 1)"]
    code, out = _run(chat, "--message", "Tracker: Larkspur drafted", check=sees_both,
                     capsys=capsys)
    assert code == 0, out
    assert "land: ready claude/chat-1" in out
    assert 'head "claude/chat-1", base "master"' in out and 'title "Tracker: Larkspur drafted"' in out
    assert "merge_pull_request" in out and "python3 tools/land.py --after-merge" in out
    assert "claude/chat-1" in _branches(origin) and "master" in _branches(origin)
    pushed = git(origin, "ls-tree", "-r", "--name-only", "claude/chat-1").stdout.split()
    assert "job_search_tracker.csv" in pushed and "documents/network/c1/draft.md" in pushed
    assert "cv/Morgan_Ellis_Resume_LK.log" not in pushed
    assert "Tracker: Larkspur drafted" in git(chat, "log", "--format=%s").stdout
    # Master itself is never pushed to: only the pull request reaches it.
    assert git(origin, "rev-parse", "master").stdout == git(other, "rev-parse", "HEAD").stdout


def test_the_pull_request_names_what_the_check_skipped(copy, capsys):
    _origin, chat, _other = copy
    write(chat, "profile/notes.md", "second\n")
    code, out = _run(chat, capsys=capsys)
    assert code == 0 and "skipped: documents" in out
    assert land.DEFAULT_MESSAGE in git(chat, "log", "-1", "--format=%s").stdout


def test_a_red_check_pushes_its_branch_with_no_pull_request_and_the_next_chat_finds_it(copy,
                                                                                      capsys):
    """A cloud container is gone when its chat ends: work only committed there was lost, and
    a person's own tests failing after an update made every landing red (the release review,
    2026-11-03). Red still pushes the chat's branch, never a pull request, and --waiting
    names it for the next chat or run."""
    origin, chat, other = copy
    write(chat, "profile/notes.md", "second\n")
    code, out = _run(chat, "--message", "Notes", check=RED, capsys=capsys)
    assert code == 1
    assert out.startswith("land: not green; the work waits on claude/chat-1, pushed with no "
                          "pull request") and "AssertionError: boom" in out
    assert "tests                     FAIL" in out and "1 passed, 1 failed" in out
    assert "create_pull_request" not in out and "land: ready" not in out
    assert "claude/chat-1" in _branches(origin)
    assert git(origin, "log", "-1", "--format=%s", "claude/chat-1").stdout.strip() == "Notes"
    assert git(chat, "status", "--porcelain", "--untracked-files=no").stdout == ""
    # The next chat, in a fresh container, finds it and is told how to bring it in.
    git(other, "fetch", "-q", "origin")
    assert land.waiting(str(other)) == ["origin/claude/chat-1"]
    code, out = _run(other, "--waiting", capsys=capsys)
    assert code == 0 and "waiting on: origin/claude/chat-1 (today)" in out
    assert "the next landing brings each in" in out
    # The chat's own branch is never listed to itself, and a branch of the app's is never one.
    assert land.waiting(str(chat)) == []
    git(other, "switch", "-q", "-c", "claude/app-change")
    write(other, "tools/example.py", "print('changed')\n")
    git(other, "commit", "-q", "-am", "an app change")
    git(other, "push", "-q", "origin", "claude/app-change")
    git(other, "fetch", "-q", "origin")
    assert land.waiting(str(other)) == ["origin/claude/chat-1"]


def test_a_conflict_that_cannot_be_settled_pushes_the_work_from_before_the_merge(copy, capsys):
    """Only a file of the app's is never settled (merge_state.settle): two copies of the app
    that disagree are not a person's choice. The work waits, as before, and loses nothing."""
    origin, chat, other = copy
    write(other, "tools/example.py", "print('theirs')\n")
    git(other, "commit", "-q", "-am", "theirs")
    git(other, "push", "-q", "origin", "master")
    write(chat, "tools/example.py", "print('mine')\n")
    git(chat, "commit", "-q", "-am", "an app file changed here")
    write(chat, "profile/notes.md", "mine\n")
    code, out = _run(chat, "--message", "Mine", check=NEVER, capsys=capsys)
    assert code == 2
    assert out.startswith("land: a conflict in tools/example.py; the work waits on claude/chat-1")
    assert "create_pull_request" not in out
    assert git(chat, "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False).returncode != 0
    # Pushed as it was before the merge: the chat's own commit, master's not in it.
    assert git(origin, "rev-parse", "claude/chat-1").stdout == git(chat, "rev-parse", "HEAD").stdout
    assert git(origin, "log", "-1", "--format=%s", "claude/chat-1").stdout.strip() == "Mine"
    assert git(origin, "merge-base", "--is-ancestor", "master", "claude/chat-1",
               check=False).returncode != 0


def _stranger(copy):
    """The copy with the row-by-row merge's files on master, as a person's copy has them:
    .gitattributes, tools/merge_state.py and a tracker. Clones made after carry them, but no
    clone has the driver set: config is never committed."""
    origin, chat, other = copy
    with open(os.path.join(ROOT, ".gitattributes"), encoding="utf-8") as fh:
        write(other, ".gitattributes", fh.read())
    for name in ("merge_state.py", "personal_paths.py", "python_floor.py"):
        with open(os.path.join(ROOT, "tools", name), encoding="utf-8") as fh:
            write(other, "tools/" + name, fh.read())
    write(other, "job_search_tracker.csv", "date,company,role,status\n"
                                           "2026-11-01,Alder Freight,Analyst,applied\n")
    write(other, "profile/CLAUDE.md", "# Their own rules\n\n- One rule.\n")
    write(other, "profile/search.py", "SALARY_FLOOR = 50000\n")
    git(other, "add", "-A")
    git(other, "add", "-f", "job_search_tracker.csv")
    git(other, "commit", "-q", "-m", "the app's merge files and a tracker")
    git(other, "push", "-q", "origin", "master")
    git(chat, "fetch", "-q", "origin", "master")
    git(chat, "merge", "-q", "--ff-only", "origin/master")
    assert git(chat, "config", "--get", "merge.ljs-state.driver", check=False).stdout == ""
    return origin, chat, other


def _append(repo, rel, text):
    with open(os.path.join(str(repo), rel), "a", encoding="utf-8") as fh:
        fh.write(text)


def _land_other(other, message):
    """Another chat lands straight onto master (its pull request merged)."""
    git(other, "add", "-A")
    git(other, "add", "-f", "job_search_tracker.csv")
    git(other, "commit", "-q", "-m", message)
    git(other, "push", "-q", "origin", "master")


def test_a_job_chats_rows_land_beside_anothers_without_the_sync_having_run(copy, capsys):
    """X-2 (the stranger audit, 2026-11-03): a page job runs in a fresh clone that never ran
    the sync, so the row-by-row driver was not set, and two appended tracker rows conflicted
    as plain lines: the job's drafts waited on a branch while its card said Done. The
    landing sets the driver itself before it merges."""
    origin, chat, other = _stranger(copy)
    _append(other, "job_search_tracker.csv", "2026-11-03,Birch Mutual,Analyst,applied\n")
    _land_other(other, "a tap: applied")
    _append(chat, "job_search_tracker.csv", "2026-11-03,Penrose Data,Analyst,drafted\n")
    write(chat, "documents/applications/penrose_analyst/letter.md", "To Penrose Data, a letter\n")
    code, out = _run(chat, "--message", "Draft Penrose", capsys=capsys)
    assert code == 0 and "land: ready claude/chat-1" in out, out
    tracker = git(origin, "show", "claude/chat-1:job_search_tracker.csv").stdout
    assert "Birch Mutual" in tracker and "Penrose Data" in tracker and "<<<<" not in tracker
    assert "documents/applications/penrose_analyst/letter.md" in git(
        origin, "ls-tree", "-r", "--name-only", "claude/chat-1").stdout


def test_two_chats_changing_the_same_rule_both_land_and_the_person_is_asked(copy, capsys):
    """X-13 (the stranger audit, 2026-11-03): a conflict in a file the row merge does not
    cover (the person's own rules, a setting) aborted the merge, and the whole chat's work,
    tracker rows and drafts included, waited on a branch every later chat tried and left.
    Each such file is settled now, losing neither side, and the rest lands."""
    import profile_upgrades
    origin, chat, other = _stranger(copy)
    write(other, "profile/CLAUDE.md", "# Their own rules\n\n- One rule, said the first way.\n")
    write(other, "profile/search.py", "SALARY_FLOOR = 55000\n")
    _land_other(other, "chat A: a rule and a setting")
    write(chat, "profile/CLAUDE.md", "# Their own rules\n\n- One rule, said the second way.\n")
    write(chat, "profile/search.py", "SALARY_FLOOR = 60000\n")
    _append(chat, "job_search_tracker.csv", "2026-11-03,Harrow Logistics,Analyst,drafted\n")
    write(chat, "documents/applications/harrow_ops/letter.md", "To Harrow Logistics, a letter\n")
    code, out = _run(chat, "--message", "Harrow", capsys=capsys)
    assert code == 0 and "land: ready claude/chat-1" in out, out
    assert "profile/CLAUDE.md: both versions kept" in out
    shown = lambda rel: git(origin, "show", "claude/chat-1:" + rel).stdout  # noqa: E731
    shown_at = lambda rev, rel: git(origin, "show", rev + ":" + rel).stdout  # noqa: E731
    rules = shown("profile/CLAUDE.md")
    assert "said the first way" in rules and "said the second way" in rules
    assert "<<<<" not in rules and ">>>>" not in rules
    assert profile_upgrades.CONFIRM.search(rules)
    # A setting: this chat's kept, the person asked, and the other in the saved history,
    # never saved beside it in their folders (the maintainer, 2026-11-04).
    search = shown("profile/search.py")
    assert "SALARY_FLOOR = 60000" in search and profile_upgrades.CONFIRM.search(search)
    assert not [p for p in git(origin, "ls-tree", "-r", "--name-only", "claude/chat-1")
                .stdout.split() if "from-another-chat" in p]
    other_rev = search.split("git show ", 1)[1].split(":", 1)[0]
    assert "SALARY_FLOOR = 55000" in shown_at(other_rev, "profile/search.py")
    compile(search, "search.py", "exec")
    # And the rest of the chat's work is on the branch the pull request takes to master.
    assert "Harrow Logistics" in shown("job_search_tracker.csv")
    assert "To Harrow Logistics, a letter" in shown("documents/applications/harrow_ops/letter.md")


def test_work_stranded_by_an_older_version_comes_back_at_the_next_landing(copy, capsys,
                                                                         monkeypatch):
    """X-13, X-30 and X-34 healing an existing copy: a branch an older version left waiting
    on a conflict, which every chat aborted, is brought in by the next landing anywhere
    after the update, settled, and landed; a chat cloned before it was pushed sees it too."""
    origin, chat, other = _stranger(copy)
    late = str(chat) + "-late"
    git(origin, "clone", "-q", str(origin), late)          # a chat kept open since before
    # The stranded branch: an older landing that stopped on a conflict, pushed and left.
    git(other, "switch", "-q", "-c", "claude/chat-b")
    write(other, "profile/CLAUDE.md", "# Their own rules\n\n- One rule, chat B's way.\n")
    _append(other, "job_search_tracker.csv", "2026-11-01,Osprey Media,Analyst,drafted\n")
    _land_other_branch = ["add", "-A"]
    git(other, *_land_other_branch)
    git(other, "add", "-f", "job_search_tracker.csv")
    git(other, "commit", "-q", "-m", "chat B's work")
    git(other, "push", "-q", "origin", "claude/chat-b")
    git(other, "switch", "-q", "master")
    write(other, "profile/CLAUDE.md", "# Their own rules\n\n- One rule, chat A's way.\n")
    _land_other(other, "chat A")
    # The kept-open chat lands its own small change: chat B's work comes with it.
    git(late, "switch", "-q", "-c", "claude/kept-open")
    write(late, "profile/notes.md", "a note\n")
    code, out = _run(late, "--message", "A note", capsys=capsys)
    assert code == 0 and "land: brought in work that waited on origin/claude/chat-b" in out, out
    shown = lambda rel: git(origin, "show", "claude/kept-open:" + rel).stdout  # noqa: E731
    assert "Osprey Media" in shown("job_search_tracker.csv")
    assert "chat B's way" in shown("profile/CLAUDE.md") and "chat A's way" in shown(
        "profile/CLAUDE.md")
    # Once that lands, nothing waits any more.
    git(other, "fetch", "-q", "origin", "claude/kept-open")
    git(other, "merge", "-q", "--no-ff", "--no-edit", "FETCH_HEAD")
    git(other, "push", "-q", "origin", "master")
    assert _run(late, "--waiting", capsys=capsys)[1].strip() == "land: nothing waiting"


OWN_TEST = "profile/tests/test_my_floor.py"
PLAN = "documents/plan.md"


def _own_test(check):
    return ("import search\n\n\ndef test_floor():\n    assert %s\n\n\n"
            "def test_name():\n    assert search.__name__ == 'search'\n" % check)


def _commit_all(repo, message):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def _base_with_own_files(copy):
    """The person's own test and a plan on master, taken into the chat."""
    origin, chat, other = _stranger(copy)
    write(other, OWN_TEST, _own_test("search.SALARY_FLOOR > 0"))
    write(other, PLAN, "Plan\n\nFirst: the base.\n\nSecond: kept.\n")
    _land_other(other, "the person's own test and plan")
    git(chat, "fetch", "-q", "origin", "master")
    git(chat, "merge", "-q", "--ff-only", "origin/master")
    return origin, chat, other


def _no_copies_beside(chat):
    # Every file in the chat's folder, git's own excepted: a side copy is left untracked.
    from tests import repo_files
    root = pathlib.Path(chat)
    return [str(p.relative_to(root)) for p in repo_files.files("**/*.from-another-chat*", root=root)
            if ".git" not in p.relative_to(root).parts]


@pytest.mark.parametrize("into", ["newer", "older"])
def test_a_branch_holding_only_older_copies_leaves_the_newer_ones_alone(copy, into):
    """A branch left days ago, brought in whole, held the same change to the person's own
    test and plan that this chat made and then changed again: it brought nothing of its own
    to either, so either way round the newer copies stand, with no copy beside them and no
    [CONFIRM: ...] line (a report from a person's copy, 2026-11-04: eight of their tests were
    marked and a dozen copies left beside files). A file both sides truly changed is still
    settled as before, both kept and the person asked."""
    origin, chat, other = _base_with_own_files(copy)
    git(chat, "switch", "-q", "-c", "claude/upgrade-old")
    write(chat, OWN_TEST, _own_test("search.SALARY_FLOOR >= 0"))
    write(chat, PLAN, "Plan\n\nFirst: the base, made clearer.\n\nSecond: kept.\n")
    write(chat, "profile/search.py", "SALARY_FLOOR = 55000\n")
    _commit_all(chat, "Profile upgrade: own-tests")
    git(chat, "switch", "-q", "claude/chat-1")
    write(chat, OWN_TEST, _own_test("search.SALARY_FLOOR >= 0"))
    write(chat, PLAN, "Plan\n\nFirst: the base, made clearer.\n\nSecond: kept.\n")
    _commit_all(chat, "Save the search's work")
    newer_test = _own_test("search.SALARY_FLOOR >= 0, 'a floor of nothing or more'")
    newer_plan = "Plan\n\nFirst: the base, made clearer still.\n\nSecond: kept.\n"
    write(chat, OWN_TEST, newer_test)
    write(chat, PLAN, newer_plan)
    write(chat, "profile/search.py", "SALARY_FLOOR = 60000\n")
    _commit_all(chat, "Save the search's work")
    if into == "older":
        git(chat, "switch", "-q", "claude/upgrade-old")
    ok, said = land.merge_in(str(chat), "claude/upgrade-old" if into == "newer"
                             else "claude/chat-1")
    assert ok, said
    with open(os.path.join(str(chat), OWN_TEST), encoding="utf-8") as fh:
        assert fh.read() == newer_test
    with open(os.path.join(str(chat), PLAN), encoding="utf-8") as fh:
        assert fh.read() == newer_plan
    # The setting both truly changed: the other's copy is kept out of the person's folders
    # (the maintainer, 2026-11-04), never beside it.
    assert _no_copies_beside(chat) == []
    import merge_state
    assert [n for n in os.listdir(os.path.join(str(chat), merge_state.SPARE_DIR))
            if n.startswith("profile__search.py.")]
    with open(os.path.join(str(chat), "profile", "search.py"), encoding="utf-8") as fh:
        assert "[CONFIRM: two of your chats changed this file" in fh.read()
    assert any(OWN_TEST in ln and "the newer one is kept" in ln for ln in said), said


def test_a_branch_whose_merges_crossed_keeps_the_newer_copy_it_never_changed(copy):
    """Where earlier merges crossed (each branch brought in work the other also has), git's
    common ancestor is a blend of two, and a file the old branch never changed itself
    conflicts all the same. The copy it holds is one a common ancestor held, so the newer
    one stands, alone."""
    origin, chat, other = _base_with_own_files(copy)
    base = git(chat, "rev-parse", "HEAD").stdout.strip()
    git(chat, "switch", "-q", "-c", "claude/one", base)
    write(chat, OWN_TEST, _own_test("search.SALARY_FLOOR >= 0"))
    _commit_all(chat, "chat one")
    git(chat, "switch", "-q", "-c", "claude/two", base)
    write(chat, OWN_TEST, _own_test("search.SALARY_FLOOR > 1"))
    _commit_all(chat, "chat two")
    # This chat brought both in and settled them, then changed the test again.
    git(chat, "switch", "-q", "claude/chat-1")
    git(chat, "merge", "-q", "--no-edit", "claude/one")
    git(chat, "merge", "-q", "--no-edit", "claude/two", check=False)
    write(chat, OWN_TEST, _own_test("search.SALARY_FLOOR >= 1"))
    _commit_all(chat, "both brought in")
    newer = _own_test("search.SALARY_FLOOR >= 1, 'one or more'")
    write(chat, OWN_TEST, newer)
    _commit_all(chat, "Save the search's work")
    # The old branch brought both in the other way round, kept chat two's copy, and made
    # its own change elsewhere.
    git(chat, "switch", "-q", "-c", "claude/upgrade-old", base)
    git(chat, "merge", "-q", "--no-ff", "--no-edit", "claude/two")
    git(chat, "merge", "-q", "--no-edit", "claude/one", check=False)
    write(chat, OWN_TEST, _own_test("search.SALARY_FLOOR > 1"))
    _commit_all(chat, "kept chat two's")
    write(chat, "profile/notes.md", "the old branch's own note\n")
    _commit_all(chat, "a note")
    git(chat, "switch", "-q", "claude/chat-1")
    assert len(git(chat, "merge-base", "--all", "HEAD", "claude/upgrade-old").stdout.split()) == 2
    ok, said = land.merge_in(str(chat), "claude/upgrade-old")
    assert ok, said
    with open(os.path.join(str(chat), OWN_TEST), encoding="utf-8") as fh:
        assert fh.read() == newer
    with open(os.path.join(str(chat), "profile", "notes.md"), encoding="utf-8") as fh:
        assert fh.read() == "the old branch's own note\n"
    assert _no_copies_beside(chat) == []


def _commit_days_ago(repo, message, days):
    """Commit everything, dated `days` ago."""
    when = "@%d +0000" % int(time.time() - days * 86400)
    git(repo, "add", "-A")
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", message], check=True,
                   capture_output=True, env=dict(os.environ, GIT_AUTHOR_DATE=when,
                                                 GIT_COMMITTER_DATE=when))


def test_a_branch_left_behind_is_never_brought_in_and_never_deleted(copy, capsys, monkeypatch):
    """A branch left nine days earlier changes files master has changed since: brought in by
    a landing, it put older copies over newer ones (a report from a person's copy,
    2026-11-04). It is left as it is, with one line, and kept on GitHub; start no longer says
    a landing brings it in. An old branch whose files master never changed since, and a fresh
    one that clashes (X-30), are still brought in."""
    origin, chat, other = _base_with_own_files(copy)
    git(other, "fetch", "-q", "origin")
    git(other, "merge", "-q", "--ff-only", "origin/master")
    git(other, "switch", "-q", "-c", "claude/upgrade-old")
    write(other, PLAN, "Plan\n\nFirst: the base, as it was nine days ago.\n\nSecond: kept.\n")
    write(other, "profile/notes.md", "an old note\n")
    _commit_days_ago(other, "Profile upgrade: an old one", 9)
    git(other, "push", "-q", "origin", "claude/upgrade-old")
    git(other, "switch", "-q", "-c", "claude/old-but-apart", "master")
    write(other, "profile/stories.md", "A story about Lindenmoor\n")
    _commit_days_ago(other, "a draft nobody else touched", 5)
    git(other, "push", "-q", "origin", "claude/old-but-apart")
    git(other, "switch", "-q", "master")
    write(other, PLAN, "Plan\n\nFirst: the base, as it is now.\n\nSecond: kept.\n")
    _land_other(other, "the plan as it is now")
    write(chat, "profile/notes.md", "first\nand a note from today\n")
    code, out = _run(chat, "--message", "A note", capsys=capsys)
    assert code == 0, out
    lines = [ln for ln in out.splitlines() if "claude/upgrade-old" in ln]
    assert lines == ["land: left origin/claude/upgrade-old as it is: its own work is 9 days "
                     "older than master's later changes to the same files (documents/plan.md), "
                     "so bringing it in would put older copies over newer ones. It stays on "
                     "GitHub, never deleted; nothing to tell the person"], out
    assert "land: brought in work that waited on origin/claude/old-but-apart" in out
    shown = lambda rel: git(origin, "show", "claude/chat-1:" + rel, check=False).stdout  # noqa: E731
    assert "as it is now" in shown(PLAN) and "nine days ago" not in shown(PLAN)
    assert shown("profile/notes.md") == "first\nand a note from today\n"
    assert "Lindenmoor" in shown("profile/stories.md")
    assert "claude/upgrade-old" in _branches(origin)
    git(other, "fetch", "-q", "origin")
    assert sorted(land.waiting(str(other))) == ["origin/claude/chat-1",
                                                "origin/claude/old-but-apart"]
    assert list(land.left_behind(str(other))) == ["origin/claude/upgrade-old"]
    monkeypatch.setattr(land, "fetch_waiting", lambda root: True)
    assert list(land.stranded(str(other))) == ["origin/claude/old-but-apart"]
    code, out = _run(other, "--waiting", capsys=capsys)
    assert "land: left origin/claude/upgrade-old as it is" in out
    assert "waiting on: origin/claude/chat-1 (today)" in out


def test_a_branch_that_took_an_update_and_could_not_land_is_still_listed(copy, capsys):
    """X-31 (the stranger audit, 2026-11-03): a chat that took the day's update and then
    landed red pushed a branch whose diff held the app's files (its sync's merge), and
    waiting() never listed it, so its work was lost. The app's commits a branch's own update
    brought in are the app's; only the branch's own commits decide."""
    origin, chat, other = copy
    # The app's release, as the sync merges it: commits from the app's own history.
    git(other, "switch", "-q", "--orphan", "app-release")
    write(other, "tools/tidy.py", "print('the new release')\n")
    git(other, "add", "tools/tidy.py")
    git(other, "commit", "-q", "-m", "the app: a new release")
    git(other, "switch", "-q", "-f", "master")
    git(other, "switch", "-q", "-c", "claude/chat-x-77")
    git(other, "merge", "-q", "--no-ff", "--allow-unrelated-histories", "-m",
        "Sync from the app: 1 new commit(s)", "app-release")
    write(other, "documents/applications/northgate_risk/letter.md", "To Northgate, a letter\n")
    git(other, "add", "-f", "documents/applications/northgate_risk/letter.md")
    git(other, "commit", "-q", "-m", "a draft")
    git(other, "push", "-q", "origin", "claude/chat-x-77")
    fresh = str(chat) + "-fresh"
    git(origin, "clone", "-q", str(origin), fresh)
    assert land.waiting(fresh) == ["origin/claude/chat-x-77"]
    # A branch whose own commit changes an app file is still never listed.
    git(other, "switch", "-q", "-c", "claude/edits-the-app", "master")
    write(other, "tools/example.py", "print('edited by hand')\n")
    git(other, "commit", "-q", "-am", "an app file edited")
    git(other, "push", "-q", "origin", "claude/edits-the-app")
    git(fresh, "fetch", "-q", "origin")
    assert land.waiting(fresh) == ["origin/claude/chat-x-77"]


def test_a_background_agents_branch_is_where_the_next_landing_looks(copy, capsys):
    """X-35 (the stranger audit, 2026-11-03): a background agent works on Claude Code's own
    worktree-agent-... branch, and its red landing pushed it there, where --waiting never
    looked. It is looked for now, and any other name is pushed under claude/."""
    origin, chat, other = copy
    git(chat, "switch", "-q", "-c", "worktree-agent-a1b2c3d4e5f6")
    write(chat, "profile/notes.md", "an agent's work\n")
    code, out = _run(chat, "--message", "Agent work", check=RED, capsys=capsys)
    assert code == 1 and "the work waits on worktree-agent-a1b2c3d4e5f6" in out
    git(chat, "switch", "-q", "-c", "feature-of-mine", "origin/master")
    write(chat, "profile/other.md", "another\n")
    code, out = _run(chat, "--message", "Mine", check=RED, capsys=capsys)
    assert code == 1 and "the work waits on claude/feature-of-mine" in out, out
    git(other, "fetch", "-q", "origin")
    assert sorted(land.waiting(str(other))) == ["origin/claude/feature-of-mine",
                                                "origin/worktree-agent-a1b2c3d4e5f6"]


def test_a_save_github_refuses_tells_the_person_how_to_connect_again(copy, capsys):
    """X-26 (the stranger audit, 2026-11-03): with the copy's connection to Claude lapsed,
    every landing failed with "the push was refused" and nothing else, so each chat's work
    died with its computer and the person was never told a reconnect would fix it."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_a_beginner_is_told_in_plain_words import _plain
    origin, chat, _other = copy
    hook = os.path.join(str(origin), "hooks", "pre-receive")
    with open(hook, "w", encoding="utf-8") as fh:
        fh.write("#!/bin/sh\necho 'Permission to stranger-ex/my-job-search.git denied to "
                 "claude[bot].' >&2\necho 'fatal: The requested URL returned error: 403' >&2\n"
                 "exit 1\n")
    os.chmod(hook, 0o755)
    write(chat, "profile/notes.md", "second\n")
    code, out = _run(chat, capsys=capsys)
    assert code == 2 and "Permission to" in out and "nothing was pushed" in out
    assert land.REFUSED_SAY in out and "claude_surfaces.py steps connect-github" in out
    _plain(land.REFUSED_SAY)
    # A push turned away because the branch moved is not a lapsed connection.
    moved = subprocess.CompletedProcess([], 1, "", " ! [rejected] HEAD -> claude/x "
                                                  "(fetch first)\nerror: failed to push")
    assert land._trouble(moved) == ""


def test_a_full_disk_is_said_as_a_full_disk(copy, capsys, monkeypatch):
    """X-45 (the stranger audit, 2026-11-03): git's message for a full disk names index.lock,
    and the landing called it another command running, waited, and said nothing."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_a_beginner_is_told_in_plain_words import _plain
    full = subprocess.CompletedProcess([], 128, "", "fatal: sha1 file '.git/index.lock' write "
                                                    "error. Out of diskspace")
    assert land._said(full) == "the disk here is full" and land._trouble(full) == "disk"
    import save_state
    monkeypatch.setattr(save_state, "main", lambda argv, root: print(
        "save_state: git refused: fatal: Unable to create '.git/index.lock': No space left on "
        "device") or 1)
    _origin, chat, _other = copy
    code, out = _run(chat, check=NEVER, capsys=capsys)
    assert code == 2 and "saving stopped: the disk here is full" in out
    assert "another git command" not in out and land.DISK_FULL_SAY in out
    _plain(land.DISK_FULL_SAY)


def test_work_written_while_a_landing_ran_is_said_to_need_another(copy, capsys):
    """X-62 (the stranger audit, 2026-11-03): a second turn's change, made while a landing
    held the lock, was in no commit, and nothing started a landing for it after."""
    _origin, chat, _other = copy
    write(chat, "profile/notes.md", "second\n")
    meanwhile = [sys.executable, "-c",
                 "open('profile/later.md', 'w').write('a quick tap'); print('Green.')"]
    code, out = _run(chat, check=meanwhile, capsys=capsys)
    assert code == 0 and "land: ready" in out
    assert "were written while this ran" in out and "profile/later.md" in out


def test_work_waiting_a_day_or_more_is_known(copy, capsys, monkeypatch):
    """X-30 (the stranger audit, 2026-11-03): work that has not reached master was invisible.
    What has waited past a day's landings is named, with its age, for the start to say."""
    origin, chat, other = copy
    git(other, "switch", "-q", "-c", "claude/red-days-ago")
    write(other, "profile/notes.md", "old work\n")
    git(other, "add", "-A")
    monkeypatch.setenv("GIT_COMMITTER_DATE", time.strftime(
        "%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 2 * 86400)))
    git(other, "commit", "-q", "-m", "old work")
    monkeypatch.delenv("GIT_COMMITTER_DATE")
    git(other, "push", "-q", "origin", "claude/red-days-ago")
    got = land.stranded(str(chat), fetch=True)
    assert list(got) == ["origin/claude/red-days-ago"] and got["origin/claude/red-days-ago"] >= 1


def test_nothing_ahead_of_master_lands_nothing_and_runs_no_check(copy, capsys):
    origin, chat, _other = copy
    code, out = _run(chat, check=NEVER, capsys=capsys)
    assert (code, out.strip()) == (0, "land: nothing to land")
    assert "claude/chat-1" not in _branches(origin)


def test_a_file_of_the_apps_is_never_committed(copy, capsys):
    _origin, chat, _other = copy
    write(chat, "tools/example.py", "print('edited here')\n")
    git(chat, "add", "tools/example.py")
    write(chat, "profile/notes.md", "second\n")
    code, out = _run(chat, capsys=capsys)
    assert code == 0 and "left out 1 file(s) of the app's" in out
    changed = git(chat, "diff", "--name-only", "origin/master", "HEAD").stdout.split()
    assert changed == ["profile/notes.md"]
    # Left as it was, in the working tree, for whoever made it.
    with open(os.path.join(str(chat), "tools", "example.py"), encoding="utf-8") as fh:
        assert fh.read() == "print('edited here')\n"


def test_work_on_master_itself_gets_a_branch_and_master_is_never_pushed(copy, capsys):
    origin, chat, _other = copy
    git(chat, "switch", "-q", "master")
    before = git(origin, "rev-parse", "master").stdout
    write(chat, "profile/notes.md", "second\n")
    code, out = _run(chat, capsys=capsys)
    assert code == 0
    made = [b for b in _branches(origin) if b.startswith("claude/land-")]
    assert len(made) == 1 and f"land: ready {made[0]}" in out
    assert git(origin, "rev-parse", "master").stdout == before


def test_after_the_merge_the_branch_starts_from_master_with_no_checkout_dance(copy, capsys):
    origin, chat, other = copy
    write(chat, "profile/notes.md", "second\n")
    assert _run(chat, capsys=capsys)[0] == 0
    # Not merged yet: it says so and changes nothing.
    head = git(chat, "rev-parse", "HEAD").stdout
    code, out = _run(chat, "--after-merge", capsys=capsys)
    assert code == 1 and "not on master yet" in out
    assert git(chat, "rev-parse", "HEAD").stdout == head
    # GitHub merges the pull request (a merge commit), and another chat lands after it.
    git(other, "fetch", "-q", "origin", "claude/chat-1")
    git(other, "merge", "-q", "--no-ff", "--no-edit", "FETCH_HEAD")
    write(other, "profile/later.md", "later\n")
    git(other, "add", "profile/later.md")
    git(other, "commit", "-q", "-m", "a later chat")
    git(other, "push", "-q", "origin", "master")
    code, out = _run(chat, "--after-merge", capsys=capsys)
    assert code == 0 and "landed" in out
    assert git(chat, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "claude/chat-1"
    assert git(chat, "rev-parse", "HEAD").stdout == git(origin, "rev-parse", "master").stdout
    assert os.path.exists(os.path.join(str(chat), "profile", "later.md"))
    # The next piece of work lands the same way, its push a plain fast-forward of the branch.
    write(chat, "profile/notes.md", "third\n")
    code, out = _run(chat, capsys=capsys)
    assert code == 0 and "land: ready claude/chat-1 (1 commit(s) ahead of master)" in out


def _fake(results):
    calls = []

    def run(root, *args):
        calls.append(args)
        code, err = results[min(len(calls), len(results)) - 1]
        return subprocess.CompletedProcess(["git", *args], code, "", err)
    return run, calls


def test_a_network_failure_is_retried_with_waits_and_a_refusal_is_not():
    hung = (128, "fatal: unable to access 'https://github.com/x/y/': Could not resolve host")
    run, calls = _fake([hung, hung, (0, "")])
    waits = []
    r = land._retried("/nowhere", "push", "-u", "origin", "HEAD", sleep=waits.append, run=run)
    assert r.returncode == 0 and waits == [2, 4] and len(calls) == 3
    run, calls = _fake([hung])
    waits = []
    assert land._retried("/nowhere", "push", sleep=waits.append, run=run).returncode == 128
    assert waits == [2, 4, 8, 16] and len(calls) == 5
    refused = (1, "! [remote rejected] HEAD -> claude/x (permission denied) 403")
    run, calls = _fake([refused])
    waits = []
    assert land._retried("/nowhere", "push", sleep=waits.append, run=run).returncode == 1
    assert waits == [] and len(calls) == 1


def test_it_never_force_pushes_and_runs_each_git_command_alone():
    with open(os.path.join(ROOT, "tools", "land.py"), encoding="utf-8") as fh:
        text = fh.read()
    assert "--force" not in text and "+HEAD" not in text and "shell=True" not in text
    assert '"push", "-q", "-u", "origin", "HEAD"' in text


def test_the_app_itself_is_never_landed_this_way(copy, capsys):
    origin, chat, _other = copy
    git(chat, "remote", "set-url", "origin", "https://github.com/" + land.APP_REPO + ".git")
    os.remove(os.path.join(str(chat), "profile", "person.json"))
    code, out = _run(chat, check=NEVER, capsys=capsys)
    assert code == 2 and "the app itself" in out
    git(chat, "remote", "set-url", "origin", str(origin))


def test_a_refused_merge_is_landed_again_here_then_merged(copy, capsys):
    """Two chats landing at once: each merges master here with the row-by-row driver, but
    GitHub's merge has no driver, so the second pull request is not mergeable (the release
    review, 2026-11-03). The steps say what to do, and landing again does it."""
    origin, chat, other = copy
    write(chat, "profile/notes.md", "second\n")
    code, out = _run(chat, capsys=capsys)
    assert code == 0 and land.MERGE_REFUSED in out
    assert "merge refused" in land.MERGE_REFUSED and "python3 tools/land.py" in land.MERGE_REFUSED
    with open(os.path.join(ROOT, "RUNBOOK.md"), encoding="utf-8") as fh:
        assert "merge refused" in fh.read()
    # The other chat's landing reaches master first; landing again takes it in, same branch.
    write(other, "profile/theirs.md", "theirs\n")
    git(other, "add", "profile/theirs.md")
    git(other, "commit", "-q", "-m", "the other chat")
    git(other, "push", "-q", "origin", "master")
    code, out = _run(chat, capsys=capsys)
    assert code == 0 and "land: ready claude/chat-1" in out
    assert git(origin, "merge-base", "--is-ancestor", "master", "claude/chat-1",
               check=False).returncode == 0


def test_after_the_merge_a_page_update_that_took_master_since_is_no_reason_to_stay(copy, capsys):
    """A page update (app_setup.take_master) merged master into the branch after the push,
    so HEAD was never on master and --after-merge said "not merged" for ever (the release
    review, 2026-11-03). The commit the landing pushed is what is looked for."""
    origin, chat, other = copy
    write(chat, "profile/notes.md", "second\n")
    assert _run(chat, capsys=capsys)[0] == 0
    write(other, "profile/later.md", "later\n")
    git(other, "add", "profile/later.md")
    git(other, "commit", "-q", "-m", "a later chat")
    git(other, "push", "-q", "origin", "master")
    git(chat, "fetch", "-q", "origin", "master")
    git(chat, "merge", "-q", "--no-edit", "origin/master")          # the page update
    git(other, "fetch", "-q", "origin", "claude/chat-1")
    git(other, "merge", "-q", "--no-ff", "--no-edit", "FETCH_HEAD")  # GitHub merges the PR
    git(other, "push", "-q", "origin", "master")
    code, out = _run(chat, "--after-merge", capsys=capsys)
    assert code == 0 and "starts from master now" in out
    assert git(chat, "rev-parse", "HEAD").stdout == git(origin, "rev-parse", "master").stdout


def test_after_the_merge_newer_work_of_its_own_is_kept(copy, capsys):
    origin, chat, other = copy
    write(chat, "profile/notes.md", "second\n")
    assert _run(chat, capsys=capsys)[0] == 0
    write(chat, "profile/newer.md", "newer\n")
    git(chat, "add", "profile/newer.md")
    git(chat, "commit", "-q", "-m", "newer work")
    git(other, "fetch", "-q", "origin", "claude/chat-1")
    git(other, "merge", "-q", "--no-ff", "--no-edit", "FETCH_HEAD")
    git(other, "push", "-q", "origin", "master")
    code, out = _run(chat, "--after-merge", capsys=capsys)
    assert code == 0 and "newer work of its own" in out
    assert git(chat, "merge-base", "--is-ancestor", "origin/master", "HEAD",
               check=False).returncode == 0
    assert os.path.exists(os.path.join(str(chat), "profile", "newer.md"))


def test_a_landing_holds_a_lock_and_a_second_one_waits_for_it(copy, capsys, monkeypatch):
    """A page update takes no master while a landing runs (app_setup.take_master reads the
    same lock), and two landings never run in one checkout at once."""
    _origin, chat, _other = copy
    lock = os.path.join(land.git_dir(str(chat)), land.LOCK_FILE)
    seen = []
    monkeypatch.setattr(land, "_check_command",
                        lambda root, check: seen.append(land.landing(str(chat))) or GREEN)
    write(chat, "profile/notes.md", "second\n")
    assert _run(chat, capsys=capsys)[0] == 0
    assert seen == [True] and not os.path.exists(lock) and not land.landing(str(chat))
    monkeypatch.undo()
    # Another landing's lock, live: nothing is done.
    with open(lock, "w", encoding="utf-8") as fh:
        fh.write(land.lock_text())
    write(chat, "profile/notes.md", "third\n")
    code, out = _run(chat, check=NEVER, capsys=capsys)
    assert code == 2 and "another landing is running" in out
    # One left by a landing killed long ago is stale, and ignored: aged by its stamp, and
    # where it has none, by the file.
    with open(lock, "w", encoding="utf-8") as fh:
        fh.write(land.lock_text(time.time() - land.LOCK_STALE_S - 60))
    assert not land.landing(str(chat))
    with open(lock, "w", encoding="utf-8") as fh:
        fh.write("%d\n" % os.getpid())
    os.utime(lock, (1, 1))
    assert not land.landing(str(chat))


def test_a_git_command_refused_for_another_ones_index_lock_is_tried_again(copy, capsys):
    """git refuses at once while another command holds index.lock (a page update, the
    update check): the landing stopped with exit 2 (2026-11-03). It waits a moment instead."""
    import threading
    _origin, chat, _other = copy
    lock = os.path.join(land.git_dir(str(chat)), "index.lock")
    with open(lock, "w", encoding="utf-8") as fh:
        fh.write("")
    threading.Timer(0.3, os.remove, [lock]).start()
    write(chat, "profile/notes.md", "second\n")
    code, out = _run(chat, capsys=capsys)
    assert code == 0 and "land: ready claude/chat-1" in out, out

