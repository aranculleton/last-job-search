"""Several chats on one repo: state files merge row by row, and one chat owns an update.

Invented rows only (the example person's employers).
"""
from __future__ import annotations

import csv
import io
import json
import shutil
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import merge_state as M  # noqa: E402
import profile_upgrades as P  # noqa: E402

HEAD = "date,company,role,status,notes\n"
ROW_A = "2026-10-01,Oakmere Foods,Demand Planner,applied,\n"
ROW_B = "2026-10-02,Fernhill Freight,Planning Analyst,applied,\n"


def test_rows_both_chats_added_are_both_kept():
    out, problems = M.merge_csv(HEAD + ROW_A, HEAD + ROW_A + ROW_B,
                                HEAD + ROW_A + "2026-10-03,Larkspur Retail,Analyst,applied,\n",
                                "job_search_tracker.csv")
    assert not problems
    assert out == HEAD + ROW_A + ROW_B + "2026-10-03,Larkspur Retail,Analyst,applied,\n"


def test_a_status_change_and_a_new_row_meet_cleanly():
    ours = HEAD + ROW_A.replace("applied", "interview")
    theirs = HEAD + ROW_A + ROW_B
    out, problems = M.merge_csv(HEAD + ROW_A, ours, theirs, "job_search_tracker.csv")
    assert not problems and "interview" in out and "Fernhill" in out


def test_notes_both_chats_added_are_both_kept():
    base = HEAD + "2026-10-01,Oakmere Foods,Demand Planner,applied,sent\n"
    ours = base.replace("sent\n", "sent; 2026-10-08: followed up\n")
    theirs = base.replace("sent\n", "sent; 2026-10-09: recruiter replied\n")
    out, problems = M.merge_csv(base, ours, theirs, "job_search_tracker.csv")
    assert not problems
    assert "followed up" in out and "recruiter replied" in out


def test_the_same_field_changed_two_ways_is_left_for_a_person():
    ours = HEAD + ROW_A.replace("applied", "interview")
    theirs = HEAD + ROW_A.replace("applied", "rejected")
    out, problems = M.merge_csv(HEAD + ROW_A, ours, theirs, "job_search_tracker.csv")
    assert problems and "<<<<<<<" in out and "interview" in out and "rejected" in out


def test_a_log_takes_the_line_ending_the_repo_keeps_it_with():
    """Changed 2026-10-21, deliberately: this pinned that a merge keeps ours' CRLF. The state
    files are kept with plain endings (.gitattributes eol=lf), and a chat branch from before
    that rule wrote CRLF back into its merge with master, so the next sync stopped on a file
    whose rows had not changed. A state file now merges to plain endings; any other file keeps
    its own; an ending the attributes name is the one written."""
    head = "contact_id,date,direction,full_text\r\n"
    base = head + "reed,2026-10-01,out,Hi\r\n"
    ours, theirs = base + "reed,2026-10-05,in,Hello\r\n", base + "moss,2026-10-05,out,Hi\r\n"
    out, _ = M.merge_csv(base, ours, theirs, "network_threads.csv")
    assert out == (base + "reed,2026-10-05,in,Hello\r\nmoss,2026-10-05,out,Hi\r\n").replace(
        "\r\n", "\n")
    out, _ = M.merge_csv(base, ours, theirs, "contacts_by_hand.csv")
    assert out == base + "reed,2026-10-05,in,Hello\r\nmoss,2026-10-05,out,Hi\r\n"
    out, _ = M.merge_csv(base, ours, theirs, "network_threads.csv", ending="\r\n")
    assert "\r\n" in out and "\r\r" not in out


def test_seen_postings_merge_by_posting():
    base = {"seen": {"u1": {"status": "new"}}}
    ours = {"seen": {"u1": {"status": "excluded", "exclusion_reason": "language gate"}}}
    theirs = {"seen": {"u1": {"status": "new"}, "u2": {"status": "new"}}}
    out, problems = M.merge_json(base, ours, theirs)
    assert not problems
    assert out == {"seen": {"u1": ours["seen"]["u1"], "u2": {"status": "new"}}}


def _git(cwd, *args):
    return subprocess.run(["git", "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@example.com",
                           *args], capture_output=True, text=True)


def test_git_uses_it_for_a_real_merge(tmp_path):
    repo = str(tmp_path)
    _git(repo, "init", "-q", "-b", "master")
    os.makedirs(os.path.join(repo, "tools"))
    shutil.copyfile(os.path.join(ROOT, "tools", "merge_state.py"),
                    os.path.join(repo, "tools", "merge_state.py"))
    shutil.copyfile(os.path.join(ROOT, ".gitattributes"), os.path.join(repo, ".gitattributes"))
    tracker = os.path.join(repo, "job_search_tracker.csv")
    open(tracker, "w").write(HEAD + ROW_A)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "checkout", "-qb", "other")
    open(tracker, "a").write("2026-10-03,Larkspur Retail,Analyst,applied,\n")
    _git(repo, "commit", "-qam", "theirs")
    _git(repo, "checkout", "-q", "master")
    open(tracker, "a").write(ROW_B)
    _git(repo, "commit", "-qam", "ours")
    M.install(repo)
    r = _git(repo, "merge", "-q", "--no-edit", "other")
    assert r.returncode == 0, r.stdout + r.stderr
    assert open(tracker).read() == (HEAD + ROW_A + ROW_B
                                    + "2026-10-03,Larkspur Retail,Analyst,applied,\n")


def test_a_chat_branch_from_before_plain_endings_does_not_bring_crlf_back(tmp_path):
    """From the sync audit, 2026-10-21: the state files gained `eol=lf`. A chat branch from
    before it, its contact book saved with CRLF, merged master; the merged file kept ours'
    CRLF, git then showed it changed with no row changed, and the next sync stopped."""
    repo = str(tmp_path)
    _git(repo, "init", "-q", "-b", "master")
    _git(repo, "config", "core.autocrlf", "false")     # CRLF committed as it is, on Windows too
    os.makedirs(os.path.join(repo, "tools"))
    shutil.copyfile(os.path.join(ROOT, "tools", "merge_state.py"),
                    os.path.join(repo, "tools", "merge_state.py"))
    older = "".join("%s merge=ljs-state\n" % p for p in (
        "job_search_tracker.csv", "network_contacts.csv", "network_threads.csv"))
    with open(os.path.join(repo, ".gitattributes"), "w") as g:
        g.write(older)
    book = os.path.join(repo, "network_contacts.csv")
    rows = "contact_id,name,status\r\nc1,Juno Castellan,awaiting_reply\r\n" \
           "c2,Corwin Haldane,in_conversation\r\n"
    with open(book, "w", newline="") as fh:
        fh.write(rows)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "the release before")
    M.install(repo)
    _git(repo, "checkout", "-qb", "chat/c")
    with open(book, "w", newline="") as fh:
        fh.write(rows.replace("c2,Corwin Haldane,in_conversation", "c2,Corwin Haldane,call_booked"))
    _git(repo, "commit", "-qam", "a call booked")
    _git(repo, "checkout", "-q", "master")
    shutil.copyfile(os.path.join(ROOT, ".gitattributes"), os.path.join(repo, ".gitattributes"))
    _git(repo, "add", ".gitattributes")
    _git(repo, "add", "--renormalize", "network_contacts.csv")
    _git(repo, "commit", "-qm", "this release")
    _git(repo, "checkout", "-q", "chat/c")
    r = _git(repo, "merge", "-q", "--no-edit", "master")
    assert r.returncode == 0, r.stdout + r.stderr
    # Read as bytes: text mode would turn every CRLF into a plain line end on the way in.
    merged = subprocess.run(["git", "-C", repo, "show", "HEAD:network_contacts.csv"],
                            capture_output=True).stdout
    assert b"\r" not in merged and b"c2,Corwin Haldane,call_booked" in merged
    assert _git(repo, "status", "--porcelain", "--untracked-files=no").stdout == ""


# ------------------------------------------------------------------ one chat per update

def _repo_with_a_landed_sync(tmp_path, monkeypatch):
    origin, chat = str(tmp_path / "origin"), str(tmp_path / "chat")
    subprocess.run(["git", "init", "-q", "--bare", "-b", "master", origin], check=True)
    subprocess.run(["git", "clone", "-q", origin, chat], check=True, capture_output=True)
    _git(chat, "commit", "-q", "--allow-empty", "-m", "Sync from the app: 2 new commit(s)")
    monkeypatch.setattr(P, "ROOT", chat)
    return chat


def test_the_chat_whose_sync_brought_the_update_owns_it(tmp_path, monkeypatch):
    chat = _repo_with_a_landed_sync(tmp_path, monkeypatch)
    assert P.owner_elsewhere() == ""                  # not on master yet: this chat's own
    _git(chat, "push", "-q", "origin", "HEAD:master")
    _git(chat, "fetch", "-q", "origin")
    assert P.owner_elsewhere() != ""                  # landed by somebody: quiet
    assert P.owner_elsewhere(now=time.time() + 3 * 3600) == ""   # and handed over later
    P.claim()
    assert P.owner_elsewhere() == ""                  # the chat that claimed it keeps it


def test_a_chat_that_did_not_bring_it_plans_nothing(tmp_path, monkeypatch, capsys):
    chat = _repo_with_a_landed_sync(tmp_path, monkeypatch)
    _git(chat, "push", "-q", "origin", "HEAD:master")
    _git(chat, "fetch", "-q", "origin")
    monkeypatch.setattr(P, "pending", lambda: [(P.REGISTRY[0], "missing")])
    P.main(["--plan"])
    assert json.loads(capsys.readouterr().out) == []


def _two_chats_one_update(tmp_path):
    """The app, a person's repo, and two chats that each synced the same app commit in a
    commit of their own, a minute apart, before either landed."""
    app, origin = str(tmp_path / "app"), str(tmp_path / "origin")
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    subprocess.run(["git", "init", "-q", "-b", "master", app], check=True)
    _git(app, "commit", "-q", "--allow-empty", "-m", "app 3.8.0")
    subprocess.run(["git", "init", "-q", "--bare", "-b", "master", origin], check=True)
    subprocess.run(["git", "clone", "-q", origin, a], check=True, capture_output=True)
    _git(a, "commit", "-q", "--allow-empty", "-m", "the person's start")
    _git(a, "push", "-q", "origin", "HEAD:master")
    subprocess.run(["git", "clone", "-q", origin, b], check=True, capture_output=True)
    for i, chat in enumerate((a, b)):
        _git(chat, "fetch", "-q", app, "master")
        # A minute apart: two real chats never make the same commit, though a fast test can.
        # Minutes before now, never a fixed time: a chat's turn is OWNER_MINUTES from its
        # sync, read against the clock, and a fixed date failed these once the day moved on.
        when = "@%d +0000" % (int(time.time()) - 300 + 60 * i)
        subprocess.run(["git", "-C", chat, "-c", "user.name=t", "-c", "user.email=t@example.com",
                        "merge", "-q", "--no-ff", "--allow-unrelated-histories", "FETCH_HEAD",
                        "-m", "Sync from the app: 1 new commit(s)"], capture_output=True,
                       env=dict(os.environ, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when))
    return a, b


def test_two_chats_that_synced_the_same_update_do_not_both_apply_it(tmp_path, monkeypatch):
    a, b = _two_chats_one_update(tmp_path)
    monkeypatch.setattr(P, "ROOT", b)
    P.claim()                                         # chat b claimed it, as its sync does
    assert P.owner_elsewhere() == ""                  # nothing has landed: b's to do
    # Chat a lands its sync, and applies an upgrade on master.
    _git(a, "commit", "-q", "--allow-empty", "-m", "Profile upgrade: move-and-area")
    _git(a, "push", "-q", "origin", "HEAD:master")
    _git(b, "fetch", "-q", "origin")
    # b's claim no longer holds: the same update reached master through a first.
    assert P.owner_elsewhere() != ""
    assert P.done_on_master() == {"move-and-area"}
    # Checked right before it starts, an upgrade on master is merged, never made again.
    assert P.main(["--check", "move-and-area"]) == 0
    # The person's word that no other chat is open hands them over anyway.
    P.claim(taken=True)
    assert P.owner_elsewhere() == ""


def test_a_chat_whose_own_sync_landed_first_keeps_the_update(tmp_path, monkeypatch):
    a, _b = _two_chats_one_update(tmp_path)
    _git(a, "push", "-q", "origin", "HEAD:master")
    _git(a, "fetch", "-q", "origin")
    monkeypatch.setattr(P, "ROOT", a)
    P.claim()
    assert P.owner_elsewhere() == "" and P.done_on_master() == set()


def _people(*chats):
    for chat in chats:
        os.makedirs(os.path.join(chat, "profile"), exist_ok=True)


def test_the_first_chat_to_take_an_update_tells_the_other_before_anything_lands(
        tmp_path, monkeypatch):
    a, b = _two_chats_one_update(tmp_path)
    _people(a, b)
    monkeypatch.setattr(P, "ROOT", a)
    assert P.push_claim() == "claimed"
    monkeypatch.setattr(P, "ROOT", b)
    assert P.push_claim() == "taken"                  # git took a's push and refused b's
    assert P.done_on_master() == set()                # nothing has landed anywhere
    assert P.owner_elsewhere() != ""                  # and b already knows a has them
    # The person's word that no other chat is open still hands them over.
    P.claim(taken=True)
    assert P.owner_elsewhere() == ""
    monkeypatch.setattr(P, "ROOT", a)
    P.fetch_master()
    assert P.owner_elsewhere() == ""                  # a's own claim is a's


def test_a_chat_the_claim_reached_starts_nothing(tmp_path, monkeypatch, capsys):
    a, b = _two_chats_one_update(tmp_path)
    _people(a, b)
    monkeypatch.setattr(P, "ROOT", a)
    P.push_claim()
    monkeypatch.setattr(P, "ROOT", b)
    monkeypatch.setattr(P, "pending", lambda: [(P.REGISTRY[0], "missing")])
    monkeypatch.setattr(P, "run_instant", lambda rows: [])
    import merge_state
    import sync_app
    monkeypatch.setattr(merge_state, "install", lambda root: None)
    monkeypatch.setattr(sync_app, "own_tests_after_sync", lambda root: None)
    assert P.main(["--after-sync"]) == 0
    said = capsys.readouterr().out
    assert "belong to another chat" in said
    # Said once: the line read "its sync has not reached master yet, and none of its
    # changes has reached master yet" (the sync audit, 2026-10-21).
    assert said.count("reached master yet") == 1, said
    # The day's record is written in the repo the sync ran in. Into the repo running the
    # tests, it told every other worktree sharing its git folder that it was behind
    # (2026-10-21: helpers' test runs in four worktrees went red on one another's record).
    assert os.path.exists(os.path.join(b, ".git", "ljs-last-sync-head"))
    assert P.main(["--plan"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def _worktrees_of_one_repo(tmp_path):
    """A person's repo on one computer, with two chats each in a worktree of its own (as
    `sync_app.py --worktree` makes them), and the app commit both are about to take."""
    main = str(tmp_path / "repo")
    subprocess.run(["git", "init", "-q", "-b", "master", main], check=True)
    _git(main, "commit", "-q", "--allow-empty", "-m", "the person's start")
    _git(main, "remote", "add", "origin", str(tmp_path / "origin.git"))
    app = str(tmp_path / "app")
    subprocess.run(["git", "init", "-q", "-b", "master", app], check=True)
    _git(app, "commit", "-q", "--allow-empty", "-m", "app 3.9.1")
    a, b = str(tmp_path / "repo-a"), str(tmp_path / "repo-b")
    _git(main, "worktree", "add", "-q", "-b", "chat/a", a)
    _git(main, "worktree", "add", "-q", "-b", "chat/b", b)
    _git(main, "fetch", "-q", app, "master:refs/remotes/app/master")
    return main, a, b


def _take_the_update(chat):
    import sync_app
    r = _git(chat, "merge", "-q", "--no-ff", "--allow-unrelated-histories", "app/master",
             "-m", "Sync from the app: 1 new commit(s)")
    assert r.returncode == 0, r.stderr
    sync_app._record_check(chat)


def test_two_chats_that_took_the_same_update_never_call_each_other_older(tmp_path, monkeypatch):
    """From the sync audit, 2026-10-21: the record of the last sync sat in the git folder
    every worktree shares, so a second chat's sync of the same update told the first that it
    was older, its --plan stopped, and nobody applied the upgrades."""
    import sync_app
    monkeypatch.setattr(sync_app, "is_the_app", lambda root=None: False)
    main, a, b = _worktrees_of_one_repo(tmp_path)
    _take_the_update(a)
    _take_the_update(b)                               # its own merge commit, a minute later
    assert sync_app.behind_sync(a) == "" and sync_app.behind_sync(b) == ""
    # Each keeps its own day's check: one chat's sync is not the other's.
    _git(main, "worktree", "add", "-q", "-b", "chat/c", str(tmp_path / "repo-c"))
    for chat, stamped in ((a, True), (b, True), (str(tmp_path / "repo-c"), False)):
        monkeypatch.setattr(sync_app, "ROOT", chat)
        assert (sync_app.last_checked() != "") is stamped, chat
    # An /upgrade worktree made from a commit before the sync is still told so.
    old = str(tmp_path / "upgrade-old")
    _git(main, "worktree", "add", "-q", "--detach", old, "master")
    assert "older than the last update" in sync_app.behind_sync(old)
    # One made from where a chat's sync left it is not.
    new = str(tmp_path / "upgrade-new")
    _git(main, "worktree", "add", "-q", "--detach", new,
         _git(a, "rev-parse", "HEAD").stdout.strip())
    assert sync_app.behind_sync(new) == ""


def test_the_app_itself_keeps_no_record_of_a_sync_and_is_never_behind_one(tmp_path):
    """The app takes no updates, so a record in its git folder only ever came from its own
    tests, and `behind_sync` then stopped `--plan` in every other worktree of it."""
    import sync_app
    app = str(tmp_path / "app")
    _git(str(tmp_path), "init", "-q", app)
    # The app as this run knows it: LJS_APP_URL moves it (a rehearsal sets it for every
    # command, the local CI included), and with the fixed URL here this failed there.
    _git(app, "remote", "add", "origin", sync_app.app_url())
    _git(app, "commit", "-q", "--allow-empty", "-m", "one")
    sync_app._record_check(app)
    assert not os.path.exists(os.path.join(app, ".git", "ljs-last-sync-head"))
    with open(os.path.join(app, ".git", "ljs-last-sync-head"), "w") as fh:
        fh.write(_git(app, "rev-parse", "HEAD").stdout)
    _git(app, "commit", "-q", "--allow-empty", "-m", "two")
    _git(app, "checkout", "-q", "HEAD~1")
    assert sync_app.behind_sync(app) == ""


def test_a_claim_is_never_staked_over_a_sync_that_landed(tmp_path, monkeypatch, capsys):
    a, b = _two_chats_one_update(tmp_path)
    _people(a, b)
    _git(a, "push", "-q", "origin", "HEAD:master")    # a's sync landed, from an older copy
    monkeypatch.setattr(P, "ROOT", b)
    monkeypatch.setattr(P, "pending", lambda: [(P.REGISTRY[0], "missing")])
    monkeypatch.setattr(P, "run_instant", lambda rows: [])
    import merge_state
    import sync_app
    monkeypatch.setattr(merge_state, "install", lambda root: None)
    monkeypatch.setattr(sync_app, "own_tests_after_sync", lambda root: None)
    P.main(["--after-sync"])
    said = capsys.readouterr().out
    assert "another chat's sync of this update reached master first" in said
    assert "none of its changes has reached master yet" in said
    refs = _git(b, "ls-remote", "origin", P.CLAIM_REFS + "*")
    assert refs.stdout.strip() == ""                  # b pushed no claim of its own
    monkeypatch.setattr(P, "ROOT", a)
    P.claim()                                         # as a's own sync did
    P.fetch_master()
    assert P.owner_elsewhere() == ""                  # so a, whose sync landed, keeps them


def test_the_chat_that_claimed_keeps_the_update_when_the_other_lands_first(tmp_path,
                                                                             monkeypatch):
    a, b = _two_chats_one_update(tmp_path)
    _people(a, b)
    monkeypatch.setattr(P, "ROOT", a)
    assert P.push_claim() == "claimed"
    monkeypatch.setattr(P, "ROOT", b)
    assert P.push_claim() == "taken"
    assert P.owner_elsewhere() != ""                  # b waits on a's claim
    # Told why, as it is: a took it and nothing of a's has reached master. The sync said
    # a's sync had "brought this update in" and b had it "by merging master" (2026-10-21).
    assert P.owner()[1] == "claimed"
    assert "has not reached master yet" in P.OWNER_WHY[P.owner()[1]]
    _git(b, "push", "-q", "origin", "HEAD:master")    # and lands its sync first
    monkeypatch.setattr(P, "ROOT", a)
    P.fetch_master()
    assert P.owner_elsewhere() == ""                  # a is not told to wait on b


def test_a_claim_push_keeps_the_persons_own_ssh_command(tmp_path, monkeypatch):
    a, _b = _two_chats_one_update(tmp_path)
    _people(a)
    _git(a, "config", "core.sshCommand", "ssh -i ~/.ssh/work_key")
    monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)
    monkeypatch.setattr(P, "ROOT", a)
    seen = {}
    real = subprocess.run

    def run(cmd, *args, **kw):
        if "push" in cmd:
            seen["ssh"] = kw["env"]["GIT_SSH_COMMAND"]
        return real(cmd, *args, **kw)

    monkeypatch.setattr(P.subprocess, "run", run)
    P.push_claim()
    assert seen["ssh"] == "ssh -i ~/.ssh/work_key -o BatchMode=yes"


def test_no_claim_is_pushed_from_the_app(tmp_path, monkeypatch):
    a, _b = _two_chats_one_update(tmp_path)           # no profile/: the app itself
    monkeypatch.setattr(P, "ROOT", a)
    assert P.push_claim() == ""
    assert _git(a, "ls-remote", "origin", P.CLAIM_REFS + "*").stdout.strip() == ""


# ------------------------------------------------------------------ the later change wins

CONTACTS = "contact_id,name,status,next_action\n"
JUNO = "oakmere_castellan,Juno Castellan,awaiting_reply,\n"


def _two_sides(tmp_path, ours_at, theirs_at, ours_status="call_booked",
               theirs_status="in_conversation"):
    """A person's repo where two chats changed one contact's status, each at its own time."""
    repo = str(tmp_path / "repo")
    os.makedirs(os.path.join(repo, "tools"))
    _git(repo, "init", "-q", "-b", "master")
    for f in ("tools/merge_state.py", ".gitattributes"):
        shutil.copyfile(os.path.join(ROOT, f), os.path.join(repo, f))
    book = os.path.join(repo, "network_contacts.csv")
    open(book, "w").write(CONTACTS + JUNO)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")

    def change(status, when, msg):
        open(book, "w").write(CONTACTS + JUNO.replace("awaiting_reply", status))
        subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@example.com",
                        "commit", "-qam", msg], check=True, capture_output=True,
                       env=dict(os.environ, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when))

    _git(repo, "checkout", "-qb", "other")
    change(theirs_status, theirs_at, "theirs")
    _git(repo, "checkout", "-q", "master")
    change(ours_status, ours_at, "ours")
    M.install(repo)
    return repo, book


def test_a_status_both_chats_changed_takes_the_later_change(tmp_path):
    repo, book = _two_sides(tmp_path, ours_at="2026-10-19T09:00:00", theirs_at="2026-10-19T15:00:00")
    r = _git(repo, "merge", "--no-edit", "other")
    assert r.returncode == 0, r.stdout + r.stderr
    text = open(book).read()
    assert "<<<<<<<" not in text and "in_conversation" in text and "call_booked" not in text
    said = r.stdout + r.stderr
    assert "kept 'in_conversation', the later change" in said and "'call_booked'" in said


def test_the_later_change_wins_whichever_side_it_is_on(tmp_path):
    repo, book = _two_sides(tmp_path, ours_at="2026-10-19T15:00:00", theirs_at="2026-10-19T09:00:00")
    r = _git(repo, "merge", "--no-edit", "other")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "call_booked" in open(book).read()


def test_a_change_with_no_later_side_is_still_left_for_a_person(tmp_path):
    repo, book = _two_sides(tmp_path, ours_at="2026-10-19T09:00:00", theirs_at="2026-10-19T09:00:00")
    r = _git(repo, "merge", "--no-edit", "other")
    assert r.returncode != 0
    text = open(book).read()
    assert "<<<<<<<" in text and "call_booked" in text and "in_conversation" in text


def test_without_git_history_a_both_changed_field_is_a_conflict_as_before():
    base = CONTACTS + JUNO
    ours = base.replace("awaiting_reply", "call_booked")
    theirs = base.replace("awaiting_reply", "in_conversation")
    out, problems = M.merge_csv(base, ours, theirs, "network_contacts.csv")
    assert problems and "<<<<<<<" in out
    settled = []
    out, problems = M.merge_csv(base, ours, theirs, "network_contacts.csv",
                                later=lambda k, f, o, t: "theirs", settled=settled)
    assert not problems and "in_conversation" in out and "call_booked" not in out
    assert settled and "both changed status" in settled[0]


def test_a_seen_posting_both_chats_changed_takes_the_later_change():
    base = {"seen": {"u1": {"status": "new"}}}
    ours = {"seen": {"u1": {"status": "excluded"}}}
    theirs = {"seen": {"u1": {"status": "applied"}}}
    settled = []
    out, problems = M.merge_json(base, ours, theirs, later=lambda p, o, t: "theirs",
                                 settled=settled)
    assert not problems and out == theirs and "seen/u1/status" in settled[0]


URL = "https://jobs.example.com/acme/1?ref=a/b"


def _two_sides_seen(tmp_path, ours, theirs, base="new"):
    """A person's repo where two chats changed one posting in seen_jobs.json, keyed, as
    there, by a URL with slashes in it; theirs is the later change."""
    repo = str(tmp_path / "repo")
    os.makedirs(os.path.join(repo, "tools"))
    os.makedirs(os.path.join(repo, "job_scraper"))
    _git(repo, "init", "-q", "-b", "master")
    for f in ("tools/merge_state.py", ".gitattributes"):
        shutil.copyfile(os.path.join(ROOT, f), os.path.join(repo, f))
    seen = os.path.join(repo, "job_scraper", "seen_jobs.json")

    def write(value):
        with open(seen, "w") as fh:
            json.dump({"seen": {URL: value}}, fh, indent=2)

    write(base)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")

    def change(value, when, msg):
        write(value)
        subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@example.com",
                        "commit", "-qam", msg], check=True, capture_output=True,
                       env=dict(os.environ, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when))

    _git(repo, "checkout", "-qb", "other")
    change(theirs, "2026-10-19T15:00:00", "theirs")
    _git(repo, "checkout", "-q", "master")
    change(ours, "2026-10-19T09:00:00", "ours")
    M.install(repo)
    return repo, seen


def test_a_posting_keyed_by_a_url_takes_the_later_change(tmp_path):
    repo, seen = _two_sides_seen(tmp_path, ours={"status": "excluded"},
                                 theirs={"status": "applied"}, base={"status": "new"})
    r = _git(repo, "merge", "--no-edit", "other")
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.load(open(seen))["seen"][URL] == {"status": "applied"}
    assert "the later change" in r.stdout + r.stderr


def test_a_list_both_chats_added_to_is_never_settled_by_one_side(tmp_path):
    repo, seen = _two_sides_seen(tmp_path, ours={"notes": ["a", "ours"]},
                                 theirs={"notes": ["a", "theirs"]}, base={"notes": ["a"]})
    r = _git(repo, "merge", "--no-edit", "other")
    assert r.returncode != 0                     # left for a person, as before
    said = r.stdout + r.stderr
    assert "the later change" not in said and "notes" in said


def test_a_name_outside_ascii_merges_whatever_the_locale(tmp_path, monkeypatch):
    for k, v in (("LC_ALL", "C"), ("LANG", "C"), ("PYTHONUTF8", "0"),
                 ("PYTHONCOERCECLOCALE", "0")):
        monkeypatch.setenv(k, v)
    repo, book = _two_sides(tmp_path, ours_at="2026-10-19T09:00:00",
                            theirs_at="2026-10-19T15:00:00")
    for side in ("other", "master"):              # a name both histories carry
        _git(repo, "checkout", "-q", side)
        text = open(book, encoding="utf-8").read().replace("Juno", "\u0141ucja")
        open(book, "w", encoding="utf-8").write(text)
        _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qam",
             "name")
    _git(repo, "checkout", "-q", "master")
    r = _git(repo, "merge", "--no-edit", "other")
    assert "UnicodeDecodeError" not in r.stdout + r.stderr


def test_a_rebase_takes_the_later_change_too(tmp_path):
    repo, book = _two_sides(tmp_path, ours_at="2026-10-19T09:00:00", theirs_at="2026-10-19T15:00:00")
    _git(repo, "checkout", "-q", "other")
    r = _git(repo, "rebase", "master")
    assert r.returncode == 0, r.stdout + r.stderr
    text = open(book).read()
    assert "<<<<<<<" not in text and "in_conversation" in text


def test_the_plan_says_which_listed_upgrades_are_already_in_place(tmp_path, monkeypatch, capsys):
    _repo_with_a_landed_sync(tmp_path, monkeypatch)
    rows = [(P.REGISTRY[0], "missing"), (P.REGISTRY[1], "missing")]
    P.remember_listed(rows)                           # what the sync printed
    monkeypatch.setattr(P, "pending", lambda: rows[:1])   # one done since, by anyone
    assert P.main(["--plan"]) == 0
    out = capsys.readouterr()
    assert [r["id"] for r in json.loads(out.out)] == [rows[0][0].id]
    assert "Already in place since the sync listed them" in out.err
    assert rows[1][0].id in out.err and rows[0][0].id not in out.err


def test_a_state_file_rewritten_with_crlf_endings_changes_only_its_changed_row(tmp_path):
    """From a real repo on 2026-10-21: a chat edited the contact book with a writer that
    ended every line in CRLF, and the commit changed every line, so the diff was unreadable
    and the row-by-row merge saw every row changed by both sides."""
    repo = tmp_path / "r"
    repo.mkdir()
    _git(str(repo), "init", "-q")
    shutil.copy(os.path.join(ROOT, ".gitattributes"), repo / ".gitattributes")
    rows = ["contact_id,name,status"] + ["c%d,Person %d,awaiting_reply" % (i, i) for i in range(20)]
    book = repo / "network_contacts.csv"
    book.write_bytes(("\n".join(rows) + "\n").encode())
    _git(str(repo), "add", "-A")
    _git(str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "1")
    rows[5] = "c4,Person 4,in_conversation"
    book.write_bytes(("\r\n".join(rows) + "\r\n").encode())
    _git(str(repo), "add", "-A")
    stat = _git(str(repo), "diff", "--cached", "--numstat").stdout.split()
    assert stat[:2] == ["1", "1"], stat
    assert b"\r" not in subprocess.run(["git", "-C", str(repo), "show", ":network_contacts.csv"],
                                       capture_output=True).stdout


def test_committed_crlf_state_files_are_made_plain_once_so_the_next_sync_can_pull(tmp_path):
    """Found by tools/rehearse_sync.py on a real repo (2026-10-21): its tracker was committed
    with CRLF endings and its contact book and message log mixed. Once .gitattributes asked
    for plain endings, every fresh checkout read them as changed, and the next sync stopped.
    The sync now makes them plain once, in a commit of their own that changes no row."""
    import sync_app
    repo = str(tmp_path / "r")
    os.makedirs(repo)
    _git(repo, "init", "-q")
    # Committed with CRLF, as another computer committed them: Git for Windows' own
    # core.autocrlf would turn them into plain endings on the way in, and there would be
    # nothing left to make plain.
    _git(repo, "config", "core.autocrlf", "false")
    rows = ["contact_id,name,status", "c1,Juno Castellan,awaiting_reply",
            "c2,Corwin Haldane,in_conversation"]
    with open(os.path.join(repo, "network_contacts.csv"), "wb") as fh:
        fh.write(("\r\n".join(rows) + "\r\n").encode())
    with open(os.path.join(repo, "job_search_tracker.csv"), "wb") as fh:
        fh.write(b"company,role\r\nOakmere Foods,Analyst\n")      # mixed
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "old")
    shutil.copy(os.path.join(ROOT, ".gitattributes"), os.path.join(repo, ".gitattributes"))
    _git(repo, "add", ".gitattributes")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "attrs")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    old_env = dict(os.environ)
    os.environ.update(env)
    try:
        said = sync_app.plain_state_endings(repo)
        assert "no row changed" in said and "network_contacts.csv" in said
        assert _git(repo, "status", "--porcelain").stdout.strip() == ""
        assert b"\r" not in subprocess.run(["git", "-C", repo, "show", "HEAD:network_contacts.csv"],
                                           capture_output=True).stdout
        assert _git(repo, "diff", "--ignore-cr-at-eol", "HEAD~1", "HEAD").stdout == ""
        assert sync_app.plain_state_endings(repo) == ""                 # once
    finally:
        os.environ.clear()
        os.environ.update(old_env)


def test_their_uncommitted_edits_are_never_folded_into_the_line_ending_commit(tmp_path):
    import sync_app
    repo = str(tmp_path / "r")
    os.makedirs(repo)
    _git(repo, "init", "-q")
    shutil.copy(os.path.join(ROOT, ".gitattributes"), os.path.join(repo, ".gitattributes"))
    _git(repo, "add", ".gitattributes")
    _git(repo, "-c", "core.autocrlf=false", "-c", "user.name=t", "-c", "user.email=t@example.com",
         "commit", "-qm", "attrs")
    path = os.path.join(repo, "network_contacts.csv")
    with open(path, "wb") as fh:
        fh.write(b"contact_id,status\r\nc1,awaiting_reply\r\n")
    # Committed with CRLF in the index by switching the attribute off for one add.
    _git(repo, "-c", "core.attributesFile=/dev/null", "add", "--renormalize", ".")
    subprocess.run(["git", "-C", repo, "update-index", "--add", "--cacheinfo",
                    "100644,%s,network_contacts.csv" % subprocess.run(
                        ["git", "-C", repo, "hash-object", "-w", "--no-filters", path],
                        capture_output=True, text=True).stdout.strip()], check=True)
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "crlf")
    with open(path, "wb") as fh:
        fh.write(b"contact_id,status\r\nc1,call_booked\r\n")           # their edit
    assert sync_app.plain_state_endings(repo) == ""
    assert b"call_booked" in open(path, "rb").read()


def _rule(day, said, rule, status="active"):
    return {"date": day, "area": "messages", "said": said, "rule": rule,
            "applied_to": [], "never_say": [], "status": status}


def test_the_persons_rules_both_chats_recorded_are_both_kept():
    """Two chats each recording one of the person's reactions on the same day stopped the
    merge of profile/learned.json, a list being one value: three times on 2026-10-24, each
    kept by hand. Its records merge one by one, like rows."""
    old = _rule("2026-10-20", "too formal", "Write as you would say it.")
    base = {"entries": [old], "approved": [], "skipped": [], "offers": []}
    ours = {**base, "entries": [dict(old, status="retired", retired_for="2026-10-24"),
                                _rule("2026-10-24", "shorter", "Two sentences at most.")]}
    theirs = {**base, "entries": [old, _rule("2026-10-24", "no exclamation marks",
                                             "Never end on an exclamation mark.")],
              "skipped": [{"date": "2026-10-24", "said": "fine", "why": "no reaction"}]}
    text, problems = M.merge(json.dumps(base), json.dumps(ours), json.dumps(theirs),
                             "profile/learned.json")
    assert not problems
    got = json.loads(text)
    assert [e["said"] for e in got["entries"]] == ["too formal", "shorter", "no exclamation marks"]
    assert got["entries"][0]["status"] == "retired"             # ours retired it; theirs left it
    assert got["skipped"] == theirs["skipped"]


def test_a_rule_retired_on_one_side_and_changed_on_the_other_is_still_a_conflict():
    old = _rule("2026-10-20", "too formal", "Write as you would say it.")
    base = {"entries": [old]}
    ours = {"entries": [dict(old, status="retired")]}
    theirs = {"entries": [dict(old, status="paused")]}
    _text, problems = M.merge(json.dumps(base), json.dumps(ours), json.dumps(theirs),
                              "profile/learned.json")
    assert problems and "entries item 1" in problems[0]


def test_git_merges_the_persons_rules_from_two_chats(tmp_path):
    repo = str(tmp_path)
    _git(repo, "init", "-q", "-b", "master")
    for f in ("tools/merge_state.py", ".gitattributes"):
        os.makedirs(os.path.dirname(os.path.join(repo, f)) or repo, exist_ok=True)
        shutil.copyfile(os.path.join(ROOT, f), os.path.join(repo, f))
    os.makedirs(os.path.join(repo, "profile"))
    rules = os.path.join(repo, "profile", "learned.json")

    def write(entries):
        with open(rules, "w") as fh:
            json.dump({"entries": entries, "offers": []}, fh, indent=2)

    old = _rule("2026-10-20", "too formal", "Write as you would say it.")
    write([old])
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "checkout", "-qb", "other")
    write([old, _rule("2026-10-24", "no exclamation marks", "Never end on one.")])
    _git(repo, "commit", "-qam", "theirs")
    _git(repo, "checkout", "-q", "master")
    write([old, _rule("2026-10-24", "shorter", "Two sentences at most.")])
    _git(repo, "commit", "-qam", "ours")
    M.install(repo)
    r = _git(repo, "merge", "-q", "--no-edit", "other")
    assert r.returncode == 0, r.stdout + r.stderr
    assert [e["said"] for e in json.load(open(rules))["entries"]] == [
        "too formal", "shorter", "no exclamation marks"]


def test_a_next_step_a_chat_wrote_outranks_the_apps_from_an_older_copy_of_the_log():
    """2026-10-24: a chat logged a contact's reply asking for the resume and set the next
    step; a background upgrade, working from a copy made before that reply, wrote the app's
    "no more follow-ups" on the same row a minute later, and the merge kept it as the later
    change. The app's line is worked out from the log and can be again; the chat's cannot."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
    import state
    cid = "ana_rook"
    cols = ["contact_id", "name", "status", "next_action", "next_action_due", "notes"]

    def book(status, action, due, notes=""):
        return (",".join(cols) + "\n" + ",".join(
            '"%s"' % v.replace('"', '""') for v in (cid, "Ana Rook", status, action, due, notes))
            + "\n")

    base = book("awaiting_reply", "One nudge if no reply", "2026-10-20")
    chat = book("in_conversation", "Email the resume she asked for, then book the call",
                "2026-10-26", "2026-10-24: asked for the resume")
    upgrade = book("awaiting_reply", state.waiting_action(2, cid), "2026-11-05")
    assert state._APP_ACTION.fullmatch(state.waiting_action(2, cid))
    settled = []
    for ours, theirs, later in ((chat, upgrade, "theirs"), (upgrade, chat, "ours")):
        text, problems = M.merge_csv(base, ours, theirs, "network_contacts.csv",
                                     later=lambda k, f, o, t, w=later: w, settled=settled)
        assert not problems
        row = next(iter(csv.DictReader(io.StringIO(text))))
        assert (row["status"], row["next_action"], row["next_action_due"]) == (
            "in_conversation", "Email the resume she asked for, then book the call",
            "2026-10-26")
        assert row["notes"] == "2026-10-24: asked for the resume"
    assert any("over one the app worked out from an older copy" in s for s in settled)


def test_two_next_steps_of_the_apps_own_still_take_the_later():
    sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
    import state
    cid = "ana_rook"
    head = "contact_id,name,status,next_action,next_action_due\n"
    base = head + f"{cid},Ana Rook,awaiting_reply,Old words,2026-10-01\n"
    ours = head + f"{cid},Ana Rook,awaiting_reply,One nudge if no reply,2026-10-20\n"
    theirs = head + f'{cid},Ana Rook,awaiting_reply,"{state.waiting_action(2, cid)}",2026-11-05\n'
    text, problems = M.merge_csv(base, ours, theirs, "network_contacts.csv",
                                 later=lambda k, f, o, t: "theirs")
    assert not problems and "2026-11-05" in text


def test_the_employers_where_more_may_be_written_to_merge_by_employer():
    base = [{"employer": "Quayside Foods", "limit": 4, "said": "more there", "date": "2026-10-20"}]
    ours = base + [{"employer": "Larkspur Retail", "limit": 3, "said": "a few more",
                    "date": "2026-10-24"}]
    theirs = base + [{"employer": "Lanternfish", "limit": None, "said": "as many as it takes",
                      "date": "2026-10-24"}]
    text, problems = M.merge(json.dumps(base), json.dumps(ours), json.dumps(theirs),
                             "profile/more_at.json")
    assert not problems
    assert [r["employer"] for r in json.loads(text)] == ["Quayside Foods", "Larkspur Retail",
                                                          "Lanternfish"]


def test_the_other_side_is_read_from_gits_name_for_it_in_any_case(monkeypatch):
    """git names the other side of a merge in the driver's environment, GITHEAD_<sha>. On
    Windows Python gives every name in os.environ in capitals, so the sha came back as
    capitals, matched nothing, and every row both chats changed was left for a person there
    (the suite on Windows, 2026-10-25)."""
    sha = "0123456789abcdef0123456789abcdef01234567"
    for k in [k for k in os.environ if k.upper().startswith("GITHEAD_")]:
        monkeypatch.delenv(k)
    monkeypatch.setenv("GITHEAD_" + sha.upper(), "theirs")
    assert M._theirs() == sha
