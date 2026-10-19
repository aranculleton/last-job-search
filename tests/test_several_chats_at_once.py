"""Several chats on one repo: state files merge row by row, and one chat owns an update.

Invented rows only (the example person's employers).
"""
from __future__ import annotations

import json
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


def test_a_log_keeps_the_file_line_ending():
    head = "contact_id,date,direction,full_text\r\n"
    base = head + "reed,2026-10-01,out,Hi\r\n"
    out, _ = M.merge_csv(base, base + "reed,2026-10-05,in,Hello\r\n",
                         base + "moss,2026-10-05,out,Hi\r\n", "network_threads.csv")
    assert out == base + "reed,2026-10-05,in,Hello\r\nmoss,2026-10-05,out,Hi\r\n"


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
    with open(os.path.join(ROOT, "tools", "merge_state.py")) as f, \
            open(os.path.join(repo, "tools", "merge_state.py"), "w") as g:
        g.write(f.read())
    with open(os.path.join(ROOT, ".gitattributes")) as f, \
            open(os.path.join(repo, ".gitattributes"), "w") as g:
        g.write(f.read())
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
        when = "2026-10-20T08:0%d:00" % i
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
