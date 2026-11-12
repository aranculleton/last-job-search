"""A burst of saves opens few pull requests, and none of them wakes the chat for nothing.

The maintainer's copy, 2026-11-06: every save opened a pull request, the cloud chat was
subscribed to each by itself, and each save woke the chat that answers the page twice more
("subscribed", "merged"): about a dozen saves in 20 minutes. Now a save in the background
asked for soon after the last one landed waits out the rest of a few minutes, so the taps
meanwhile go in one pull request; the chat's own calls unsubscribe as soon as the pull
request is opened; and a GitHub event that reaches a person's chat anyway is answered with
nothing read. Throwaway copies only, the check and GitHub faked.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import land  # noqa: E402
import learned  # noqa: E402

GREEN = [sys.executable, "-c", "print('Green.')"]


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=True)


@pytest.fixture
def chat(tmp_path, monkeypatch):
    for k, v in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@example.com"),
                 ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@example.com")):
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("LJS_LAND_CHECK", raising=False)
    origin, c = tmp_path / "origin.git", tmp_path / "chat"
    git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    git(tmp_path, "init", "-q", "-b", "master", str(c))
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as fh:
        (c / ".gitignore").write_text(fh.read(), encoding="utf-8")
    (c / "profile").mkdir()
    (c / "profile" / "person.json").write_text("{}\n", encoding="utf-8")
    (c / "profile" / "notes.md").write_text("0\n", encoding="utf-8")
    git(c, "add", "-A")
    git(c, "commit", "-q", "-m", "start")
    git(c, "remote", "add", "origin", str(origin))
    git(c, "push", "-q", "origin", "master")
    git(c, "fetch", "-q", "origin")
    git(c, "switch", "-q", "-c", "claude/page")
    return c


HELPER = "session_EXAMPLEPAGEHELPER"


def _answers_the_page(chat, monkeypatch, who=HELPER):
    """This checkout's own record that `who` answers the page (app_listen's cache)."""
    monkeypatch.setenv("LJS_CHAT", HELPER)
    d = git(chat, "rev-parse", "--absolute-git-dir").stdout.strip()
    with open(os.path.join(d, "ljs-listener.json"), "w", encoding="utf-8") as fh:
        json.dump({"listener": {"chat": who}}, fh)


def _finish(opened):
    def finish(r, ready):
        opened.append(ready["head"])
        git(r, "push", "-q", "origin", "HEAD:refs/heads/master")      # GitHub's merge
        return True, str(len(opened))
    return finish


def test_during_the_wait_the_work_is_already_on_its_branch(chat, monkeypatch):
    """The wait only delays the pull request: the work is committed and pushed to this chat's
    own branch before it starts, so a container that goes meanwhile loses nothing."""
    _answers_the_page(chat, monkeypatch)
    root, opened, seen = str(chat), [], []
    (chat / "profile" / "notes.md").write_text("one\n", encoding="utf-8")
    land.run_detached(root, "one", check=GREEN, sleep=lambda s: None, finish=_finish(opened))
    (chat / "profile" / "notes.md").write_text("two\n", encoding="utf-8")

    def sleep(_s):
        seen.append(git(chat, "ls-remote", "origin", "refs/heads/claude/page").stdout.split()[:1])
        if len(seen) == 1:
            got = subprocess.run(["git", "-C", root, "show",
                                  "origin/claude/page:profile/notes.md"], capture_output=True,
                                 text=True, encoding="utf-8", errors="replace")
            seen.append(got.stdout.strip())

    land.run_detached(root, "two", check=GREEN, sleep=sleep, finish=_finish(opened))
    assert seen and seen[1] == "two", seen


def test_a_chat_that_does_not_answer_the_page_never_waits(chat, monkeypatch):
    _answers_the_page(chat, monkeypatch, who="session_EXAMPLEOTHERCHAT")
    root, opened, waited = str(chat), [], []
    (chat / "profile" / "notes.md").write_text("one\n", encoding="utf-8")
    land.run_detached(root, "one", check=GREEN, sleep=lambda s: None, finish=_finish(opened))
    (chat / "profile" / "notes.md").write_text("two\n", encoding="utf-8")
    land.run_detached(root, "two", check=GREEN, sleep=waited.append, finish=_finish(opened))
    assert sum(waited) < 30 and len(opened) == 2, (waited, opened)


def test_a_dozen_saves_in_a_burst_make_one_or_two_pull_requests(chat, monkeypatch):
    _answers_the_page(chat, monkeypatch)
    root = str(chat)
    opened = []

    def finish(r, ready):
        opened.append(ready["head"])
        git(r, "push", "-q", "origin", "HEAD:refs/heads/master")      # GitHub's merge
        return True, str(len(opened))

    taps = iter(range(1, 13))

    def sleep(_s):
        # Taps while the save waits its turn: each one's work written, its save asked for.
        for n in (next(taps, None), next(taps, None), next(taps, None)):
            if n is not None:
                (chat / "profile" / "notes.md").write_text(f"{n}\n", encoding="utf-8")
                land._ask(root, f"tap {n}")

    (chat / "profile" / "notes.md").write_text("first\n", encoding="utf-8")
    assert land.run_detached(root, "first", check=GREEN, sleep=lambda s: None,
                             finish=finish) == 0
    # The next tap's save, moments later: the rest of the burst arrives while it waits.
    (chat / "profile" / "notes.md").write_text("second\n", encoding="utf-8")
    assert land.run_detached(root, "second", check=GREEN, sleep=sleep, finish=finish) == 0
    assert len(opened) == 2, opened
    # Every tap's work is on master: none was dropped for being batched.
    assert git(chat, "show", "origin/master:profile/notes.md").stdout.strip() == "12"


def test_the_first_save_of_a_quiet_spell_goes_at_once(chat):
    waited = []
    (chat / "profile" / "notes.md").write_text("one\n", encoding="utf-8")
    land.run_detached(str(chat), "one", check=GREEN, sleep=waited.append,
                      finish=lambda r, ready: (True, "1"))
    assert sum(waited) < 30, waited


def test_the_chats_own_calls_unsubscribe_before_the_merge(chat, capsys):
    (chat / "profile" / "notes.md").write_text("two\n", encoding="utf-8")
    assert land.main(["--message", "Notes"], root=str(chat), check=GREEN,
                     sleep=lambda s: None) == 0
    out = capsys.readouterr().out
    assert out.index("create_pull_request") < out.index("unsubscribe_pr_activity") < \
        out.index("merge_pull_request"), out


# The maintainer's copy, 2026-11-11: the page helper's agents opened a save's pull request and
# the chat was subscribed on every landing (subscription.created), CLAUDE.md's "never subscribe
# to it" notwithstanding: a cloud chat's own instructions say to subscribe to a pull request it
# opens, and an agent the page's chat runs may never see CLAUDE.md. The rule is printed in the
# step that opens it, with the unsubscribe once it is merged, and goes with every job's steps.

NEVER = "never call subscribe_pr_activity for it, whatever this chat's own instructions say"
AFTER = "unsubscribe_pr_activity for it at once, as soon as it is merged"


def test_the_step_that_opens_the_pull_request_says_never_to_subscribe(chat, capsys):
    (chat / "profile" / "notes.md").write_text("three\n", encoding="utf-8")
    assert land.main(["--message", "Notes"], root=str(chat), check=GREEN,
                     sleep=lambda s: None) == 0
    lines = capsys.readouterr().out.splitlines()
    opens = [ln for ln in lines if "create_pull_request" in ln]
    assert len(opens) == 1 and NEVER in opens[0] and AFTER in opens[0], lines
    # Once merged, the unsubscribe again, before the branch moves on.
    merge = next(i for i, ln in enumerate(lines) if "merge_pull_request" in ln)
    again = [i for i, ln in enumerate(lines) if i > merge and "unsubscribe_pr_activity" in ln]
    after = next(i for i, ln in enumerate(lines) if "--after-merge" in ln)
    assert again and again[0] < after and "as soon as it is merged" in lines[again[0]], lines
    # Without GitHub's tools the pull request is opened by hand, and the rule goes with it.
    rest = next(ln for ln in lines if "No GitHub tools in this chat" in ln)
    assert NEVER in rest and "2b" in rest, rest


def test_a_landing_that_merged_its_own_pull_request_says_never_to_subscribe(chat, capsys):
    def finish(r, ready):
        git(r, "push", "-q", "origin", "HEAD:refs/heads/master")      # GitHub's merge
        return True, "8"
    (chat / "profile" / "notes.md").write_text("four\n", encoding="utf-8")
    assert land.main(["--message", "Notes"], root=str(chat), check=GREEN,
                     sleep=lambda s: None, finish=finish) == 0
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if "unsubscribe_pr_activity" in ln)
    assert "pullNumber 8" in line and "it is merged" in line and NEVER in line, out


@pytest.mark.parametrize("sessions", [True, False], ids=["a job's chat", "a background agent"])
def test_a_job_that_lands_its_own_work_is_told_never_to_subscribe(sessions, monkeypatch):
    """A job's chat and the page helper's background agent land with land.py and make the
    calls it prints: their own steps carry the rule beside that step."""
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import app
    import app_setup
    import job_prompt
    import page_db
    monkeypatch.setattr(app_setup, "origin", lambda: ("example-owner", "example-copy"))
    monkeypatch.setattr(app_setup, "page_record",
                        lambda: {"url": "https://claude.ai/code/artifact/example-page"})
    chosen = {"work": "prep~1", "kind": "prep", "title": "Interview prep: an invented employer",
              "heavy": True, "stages": page_db.progress("prep")["stages"]}
    got = app.where_it_runs(chosen, HELPER, "cloud", no_sessions=not sessions)
    prompt = (got["create_session"] if sessions else got["agent"])["prompt"]
    said = " ".join(job_prompt.followed(prompt).split())
    at = said.index("python3 tools/land.py in the foreground")
    step = said[at:said.index("tools/app.py view", at) if sessions else len(said)]
    assert NEVER in step and AFTER in step, step


def test_a_github_event_in_a_persons_chat_is_answered_with_nothing_read(monkeypatch, tmp_path):
    monkeypatch.setattr(learned, "_path", lambda: str(tmp_path / "pending.json"))
    monkeypatch.setattr(learned.person, "in_example", lambda p: False)
    monkeypatch.setattr(learned, "_retired", lambda: "")
    got = learned.hook({"hook_event_name": "UserPromptSubmit", "prompt":
                        '<wake reason="external-event"><event source="github" type="pull_request" '
                        'action="closed">merged</event></wake>'})
    said = got["hookSpecificOutput"]["additionalContext"]
    assert "Read nothing" in said and "unsubscribe_pr_activity" in said
    assert learned.hook({"hook_event_name": "UserPromptSubmit", "prompt": "hello"}) == {}
    assert json.dumps(got)
