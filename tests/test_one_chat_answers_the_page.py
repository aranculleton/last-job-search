"""One chat answers the page; every other chat neither publishes it nor watches it.

Every chat that ran `app.py start` used to publish the page, and a chat that publishes a
page watches it (code.claude.com/docs/en/artifacts), so one tap woke the setup chat, every
long chat from before 4.0 and each split screen, each at its whole size. The listener is now
recorded in the page's own database (`meta/listener`), claimed with a write only one chat
can win, with when it last answered (tools/app_listen.py). The database here is a folder
that keeps the real one's rules: a create is refused when the document exists, and a pinned
write when its version moved on. Every person, page and chat id is invented.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app_state  # noqa: E402

APP = os.path.join(ROOT, "tools", "app.py")
PAGE = "https://claude.ai/code/artifact/example-page"
NOW = "2026-10-25T18:00:00Z"

# The page's database as a folder: <db>/<collection>/<doc>.json holding {data, version}.
# A batch is all or nothing, under a lock taken with mkdir, which is atomic everywhere.
FAKE_DB = textwrap.dedent('''
    import json, os, shutil, sys, time

    def lock(db):
        while True:
            try:
                os.mkdir(os.path.join(db, ".lock"))
                return
            except FileExistsError:
                time.sleep(0.01)

    def dump(db, out):
        for coll in os.listdir(db):
            src = os.path.join(db, coll)
            if coll.startswith(".") or not os.path.isdir(src):
                continue
            os.makedirs(os.path.join(out, coll), exist_ok=True)
            for name in os.listdir(src):
                shutil.copy(os.path.join(src, name), os.path.join(out, coll, name))

    def apply(db, batch_path):
        with open(batch_path, encoding="utf-8") as fh:
            batch = json.load(fh)
        lock(db)
        try:
            for e in batch:
                p = os.path.join(db, e["collection"], e["doc_id"] + ".json")
                have = json.load(open(p, encoding="utf-8"))["version"] if os.path.exists(p) else None
                if have is not None and e.get("if_version") != have:
                    return False          # an existing document needs its version
                if have is None and (e["op"] == "update" or e.get("if_version") is not None):
                    return False
            for e in batch:
                p = os.path.join(db, e["collection"], e["doc_id"] + ".json")
                old = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None
                data = json.load(open(e["file_path"], encoding="utf-8")) if e.get("file_path") else {}
                if e["op"] == "update":
                    data = dict(old["data"], **data)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                json.dump({"data": data, "version": (old["version"] + 1) if old else 1},
                          open(p, "w", encoding="utf-8"))
            return True
        finally:
            os.rmdir(os.path.join(db, ".lock"))
''')

# One chat: read the page's database, ask app.py whether it answers, wait until the other
# chat has read it too (so both decide from the same empty page), then send its batch.
DRIVER = textwrap.dedent('''
    import json, os, subprocess, sys, time
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import fake_db
    app, db, me, other, work = sys.argv[1:6]
    dump = os.path.join(work, "dump-" + me)
    fake_db.dump(db, dump)
    r = subprocess.run([sys.executable, app, "listen", dump, "--chat", me,
                        "--out", os.path.join(work, "out-" + me)],
                       capture_output=True, text=True, encoding="utf-8")
    batches = [ln for ln in r.stdout.splitlines() if ln.endswith(".json")]
    open(os.path.join(work, "ready-" + me), "w").close()
    while not os.path.exists(os.path.join(work, "ready-" + other)):
        time.sleep(0.01)
    won = all(fake_db.apply(db, b) for b in batches) if batches else False
    print(json.dumps({"chat": me, "won": won, "said": r.stdout, "err": r.stderr}))
''')


class Copy:
    def __init__(self, root):
        self.root = str(root)
        self.state = os.path.join(self.root, "state")
        self.profile = app_state.profile_copy(os.path.join(self.root, "profile"))
        os.makedirs(self.state, exist_ok=True)
        self.db = os.path.join(self.root, "db")
        os.makedirs(self.db, exist_ok=True)
        with open(os.path.join(self.root, "fake_db.py"), "w", encoding="utf-8") as fh:
            fh.write(FAKE_DB)
        with open(os.path.join(self.root, "driver.py"), "w", encoding="utf-8") as fh:
            fh.write(DRIVER)
        sys.path.insert(0, self.root)

    def env(self, **extra):
        env = dict(os.environ, LJS_PROFILE=self.profile, LJS_STATE=self.state,
                   LJS_COPY="private", PYTHONIOENCODING="utf-8")
        for k in ("CLAUDE_CODE_REMOTE", "CLAUDE_CODE_REMOTE_SESSION_ID", "LJS_TODAY",
                  "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_BRIDGE_SESSION_ID", "LJS_CHAT"):
            env.pop(k, None)
        env.update(extra)
        return env

    def run(self, *args, ok=(0,), **env):
        r = subprocess.run([sys.executable, APP, *args], env=self.env(**env),
                           capture_output=True, encoding="utf-8", errors="replace", timeout=120)
        assert r.returncode in ok, r.stdout + r.stderr
        return r.stdout

    def page(self, current=True):
        """The page published at PAGE, its build part current or a version behind."""
        with open(os.path.join(self.profile, "app.json"), "w", encoding="utf-8") as fh:
            json.dump({"url": PAGE, "published_at": NOW, "by": "someone"}, fh)
        record = os.path.join(self.profile, "build_versions.json")
        with open(record, encoding="utf-8") as fh:
            got = json.load(fh)
        import build_versions
        got["page"] = {"version": build_versions.current("page") if current else 1,
                       "date": "2026-10-25"}
        with open(record, "w", encoding="utf-8") as fh:
            json.dump(got, fh)

    def dump(self, name="dump"):
        import fake_db
        out = os.path.join(self.root, name)
        shutil.rmtree(out, ignore_errors=True)
        os.makedirs(out)
        fake_db.dump(self.db, out)
        return out

    def send(self, said):
        import fake_db
        return all(fake_db.apply(self.db, ln) for ln in said.splitlines() if ln.endswith(".json"))

    def listener(self):
        p = os.path.join(self.db, "meta", "listener.json")
        return json.load(open(p, encoding="utf-8"))["data"] if os.path.exists(p) else {}

    def queue(self, wid, kind="draft", asked_at="2026-10-25T17:00:00Z"):
        os.makedirs(os.path.join(self.db, "work"), exist_ok=True)
        with open(os.path.join(self.db, "work", wid + ".json"), "w", encoding="utf-8") as fh:
            json.dump({"data": {"kind": kind, "status": "queued", "asked_at": asked_at,
                                "title": "A job", "to": "cloud"}, "version": 1}, fh)


@pytest.fixture
def copy(tmp_path):
    c = Copy(tmp_path)
    yield c
    sys.path.remove(c.root)


def _publish_steps(said: str) -> list[str]:
    return [ln for ln in said.splitlines()
            if "Publish it (Artifact" in ln or "publish the new file" in ln
            or "Build it again" in ln or "Build the person's page" in ln]


def test_two_chats_starting_at_once_make_one_listener(copy):
    """Two chats in two processes read the same empty page and both claim it: the page
    takes one claim, and each chat's next look agrees on which."""
    copy.page(current=True)
    work = os.path.join(copy.root, "work")
    os.makedirs(work)
    procs = [subprocess.Popen([sys.executable, os.path.join(copy.root, "driver.py"), APP, copy.db,
                               me, other, work], env=copy.env(), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, encoding="utf-8")
             for me, other in (("chat-a", "chat-b"), ("chat-b", "chat-a"))]
    got = []
    for p in procs:
        out, err = p.communicate(timeout=120)
        assert p.returncode == 0, err
        got.append(json.loads(out.strip().splitlines()[-1]))
    assert all("answers the page now" in g["said"] for g in got), got
    winners = [g["chat"] for g in got if g["won"]]
    assert len(winners) == 1, got
    winner = winners[0]
    loser = "chat-b" if winner == "chat-a" else "chat-a"
    assert copy.listener()["chat"] == winner
    # Each chat looks again: the winner answers, the loser stands aside.
    mine = copy.run("listen", copy.dump("d1"), "--chat", winner)
    assert mine.startswith("listen: this chat answers the page.") and copy.send(mine)
    theirs = copy.run("listen", copy.dump("d2"), "--chat", loser)
    assert theirs.startswith("listen: another chat answers the page")
    assert not [ln for ln in theirs.splitlines() if ln.endswith(".json")]
    assert copy.listener()["chat"] == winner and copy.listener()["answered_at"]
    # Their next starts say so: the loser neither publishes nor watches, and asks nothing.
    said = copy.run("start", "--on", "test", "--tools", "none", "--chat", loser)
    assert "Another chat answers the person's page" in said
    assert "neither publishes it nor watches it" in said and "on: false" in said
    assert not _publish_steps(said) and "Keep its watch on" not in said
    said = copy.run("start", "--on", "test", "--tools", "none", "--chat", winner)
    assert "This chat answers the person's page. Keep its watch on" in said


def test_a_chat_that_is_not_the_listener_says_it_once_and_asks_for_a_republish(copy):
    copy.page(current=False)
    copy.send(copy.run("listen", copy.dump(), "--chat", "helper-1", "--listen"))
    copy.run("listen", copy.dump(), "--chat", "big-chat")          # it sees the helper
    said = copy.run("start", "--on", "test", "--tools", "none", "--chat", "big-chat")
    assert not _publish_steps(said), said
    assert "Publishing makes this chat watch" not in said
    assert "python3 tools/app.py republish" in said
    again = copy.run("start", "--on", "test", "--tools", "none", "--chat", "big-chat")
    assert "Another chat answers" not in again                      # said once a chat
    # Its republish request is one item, however many chats ask, and only the listener takes it.
    out = copy.run("republish", os.path.join(copy.root, "rp"))
    assert copy.send(out) and not copy.send(copy.run("republish", os.path.join(copy.root, "rp2")))
    dump = copy.dump()
    assert copy.run("next", dump, "--chat", "big-chat", "--kind", "cloud") == ""
    got = json.loads(copy.run("next", dump, "--chat", "helper-1", "--kind", "cloud"))
    assert got["kind"] == "republish" and got["already"] is False and got["locks"] == []
    stages = json.loads(copy.run("progress", "republish"))
    assert [s["key"] for s in stages["stages"]] == ["build", "publish"]


def test_the_first_publish_makes_the_publisher_the_listener_and_offers_the_pin_once(copy):
    said = copy.run("start", "--on", "test", "--tools", "none", "--chat", "setup-chat")
    assert "which makes it the page's listener" in said and _publish_steps(said)
    out = copy.run("published", PAGE, "--chat", "setup-chat")
    assert "this chat is the page's listener now" in out
    batch = [ln.rsplit(": ", 1)[-1] for ln in out.splitlines() if ln.endswith(".json")]
    assert batch and copy.send("\n".join(batch)) and copy.listener()["chat"] == "setup-chat"
    assert "action pin" in out and "pinned yes|no" in out
    import claude_surfaces
    assert claude_surfaces.entry("find-page")["ask"] in out
    copy.run("pinned", "no")
    with open(os.path.join(copy.profile, "app.json"), encoding="utf-8") as fh:
        assert json.load(fh)["pin"]["answer"] == "no"
    assert "action pin" not in copy.run("published", PAGE, "--chat", "setup-chat")
    # Nothing it keeps is written into the profile but the address and the answer.
    assert sorted(os.listdir(copy.profile)) == sorted(set(os.listdir(app_state.EXAMPLE))
                                                      - {"state", "tests"} | {"app.json"})


def test_a_listener_that_stopped_answering_is_taken_over_and_a_quiet_one_is_not(copy):
    copy.page()
    first = copy.run("listen", copy.dump(), "--chat", "old-chat", "--now", "2026-10-25T09:00:00Z")
    assert copy.send(first)
    # Quiet for hours with nothing waiting: it still answers, and nobody takes it.
    said = copy.run("listen", copy.dump(), "--chat", "new-chat", "--now", NOW)
    assert said.startswith("listen: another chat answers the page (it last answered 9 hours ago)")
    # A tap that waited twenty minutes with no answer: the next chat takes it, pinned.
    copy.queue("draft~abc", asked_at="2026-10-25T17:40:00Z")
    said = copy.run("listen", copy.dump(), "--chat", "new-chat", "--now", NOW)
    assert "this chat answers the page now" in said and copy.send(said)
    rec = copy.listener()
    assert rec["chat"] == "new-chat" and rec["took_from"] == "old-chat"
    # The old chat's next look stands it aside.
    assert copy.run("listen", copy.dump(), "--chat", "old-chat", "--now", NOW).startswith(
        "listen: another chat answers the page")


def test_the_wake_link_opens_a_chat_that_takes_over_and_the_listener_hands_to_a_helper(copy):
    copy.page()
    assert copy.send(copy.run("listen", copy.dump(), "--chat", "big-chat"))
    taken = copy.run("listen", copy.dump(), "--chat", "woken-chat", "--listen")
    assert copy.send(taken) and copy.listener()["chat"] == "woken-chat"
    handed = copy.run("listen", copy.dump(), "--chat", "woken-chat", "--hand", "session_EXAMPLEHELPER")
    assert "handed to the helper chat" in handed and copy.send(handed)
    rec = copy.listener()
    assert rec["chat"] == "session_EXAMPLEHELPER" and rec["helper"] is True
    assert copy.run("listen", copy.dump(), "--chat", "session_EXAMPLEHELPER",
                    "--helper").startswith("listen: this chat answers the page.")
    # A listener that is not the helper is told to start one once setup is done; the
    # helper itself is not.
    said = copy.run("start", "--on", "Opus 5.5", "--tools", "none", "--chat", "session_EXAMPLEHELPER",
                    "--helper")
    assert "give the page a small chat of its own" not in said
    copy.run("listen", copy.dump(), "--chat", "session_EXAMPLEHELPER", "--listen")


def test_start_names_the_helper_with_its_model_and_never_a_session_for_another_reason(copy):
    copy.page()
    assert copy.send(copy.run("listen", copy.dump(), "--chat", "big-chat"))
    said = copy.run("start", "--on", "Opus 5.5", "--tools", "none", "--chat", "big-chat")
    assert "give the page a small chat of its own" in said
    assert "Job search helper" in said and "model sonnet" in said
    assert "--hand <the new session's id>" in said


def test_the_page_is_told_how_to_say_nobody_is_listening_and_what_is_true_of_its_privacy(copy):
    model = json.loads(copy.run("model", "--now", NOW))
    lis = model["listener"]
    assert lis["doc"] == "meta/listener" and lis["answered"] == "answered_at"
    assert lis["quiet_after_s"] == 600
    url = lis["wake"]["url"]
    assert url.startswith("https://claude.ai/code?prompt=Look%20after%20my%20job%20search%20page")
    assert "app.py%20start%20--listen" in url
    priv = model["app"]["privacy"]
    assert "unless you share it" in priv
    for word in ("first names", "employers", "drafts", "setup answers"):
        assert word in priv
    assert "—" not in priv
    # The model still keeps its contract, rev included.
    path = os.path.join(copy.root, "model.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(model, fh)
    assert "keeps the contract" in copy.run("check", "--model", path)
    assert json.loads(copy.run("model", "--now", NOW))["rev"] == model["rev"]


def test_a_child_chat_gets_the_model_its_work_needs(copy):
    copy.page()
    assert copy.send(copy.run("listen", copy.dump(), "--chat", "helper-1", "--listen"))
    copy.queue("search~1", kind="search")
    got = json.loads(copy.run("next", copy.dump(), "--chat", "helper-1", "--kind", "cloud",
                              "--on", "Opus 5.5"))
    assert got["kind"] == "search" and got["model"] == "sonnet"
    os.remove(os.path.join(copy.db, "work", "search~1.json"))
    copy.queue("draft~1", kind="draft")
    got = json.loads(copy.run("next", copy.dump(), "--chat", "helper-1", "--kind", "cloud",
                              "--on", "Sonnet 5.5"))
    assert got["kind"] == "draft" and got["model"] == "opus"


def test_every_page_version_republishes_a_wording_fix_too(monkeypatch):
    import build_versions as B
    versions = B.METHODS["page"]["versions"]
    monkeypatch.setitem(B.METHODS["page"], "versions",
                        versions + ((versions[-1][0] + 1, "2026-10-26", False, "a word"),))
    assert [v[0] for v in B.behind("page", {"page": versions[-1][0]})] == [versions[-1][0] + 1]
    assert B.METHODS["page"]["every_version"] is True
    assert "never publishing it from here" in B.METHODS["page"]["run"]
    # Other methods keep the rule: a wording version asks nobody to redo anything.
    assert B.behind("upskill", {"upskill": 4}) == [v for v in B.METHODS["upskill"]["versions"]
                                                   if v[0] > 4 and v[2]]


# ------------------------------------------------------------------ after an update
#
# A person's chat took a new version (2026-10-26) and left their page as it was. They had to
# say there should be an update, then ask for the page, then ask why it had not just done
# it; the chat said a safety check had blocked its first try, set up a helper chat, offered
# the pin and reported a leftover timer. Whatever took the update (the day's check from
# `app.py start`, `--if-stale`, `--update` when they said "update"), the sync now ends with
# the page's own steps, printed by the code the update just brought in.

def _after_sync(copy, chat, landed=False):
    """What the sync prints after an update, from the file the update brought in: the same
    process sync_app.upgrades() runs, with the word it passes when the run took one."""
    import sync_app
    env = copy.env(LJS_CHAT=chat, **({sync_app.LANDED: "1"} if landed else {}))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "profile_upgrades.py")],
                       env=env, capture_output=True, encoding="utf-8", errors="replace",
                       timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def _never_asks(said):
    import app_listen
    claude = said[said.index("Claude: "):]
    assert "never ask the person first" in claude and "never chained" in claude
    assert "set no timer or reminder" in claude
    for word in ("Shall I", "Would you like", "Do you want", "pin"):
        assert word not in claude, word
    said_to_them = [ln for ln in claude.splitlines() if "Tell the person" in ln]
    assert said_to_them and all(app_listen.SAY_UPDATED in ln or app_listen.SAY_UPDATING in ln
                                for ln in said_to_them)


def test_an_update_that_changed_the_page_republishes_it_at_once_and_never_asks(copy):
    import app_listen
    copy.page(current=False)
    assert copy.send(copy.run("listen", copy.dump(), "--chat", "helper-1", "--listen"))
    said = _after_sync(copy, "helper-1")
    _never_asks(said)
    assert "Republish it:" in said and "python3 tools/app.py page --out" in said
    assert "Artifact, action publish" in said and f"published {PAGE}" in said
    # A refusal is tried once more, and only a second one is said, in its one line.
    assert "read the page again and publish once more" in said
    assert app_listen.SAY_NOT_UPDATED in said
    # The republish is the sync's own step, never also a background agent's: listed as an
    # upgrade as well, it came back later with nothing changed.
    assert "upgrade.md" not in said and "Profile upgrades: none pending." in said
    # Any other chat asks the listener at once, and does not wait for it.
    copy.run("listen", copy.dump(), "--chat", "big-chat")
    other = _after_sync(copy, "big-chat")
    _never_asks(other)
    assert "python3 tools/app.py republish" in other and "Do not wait for it" in other
    assert "Artifact, action publish" not in other and app_listen.SAY_UPDATING in other
    # A chat on a new copy, which has seen no chat answer, asks the page which chat does, then
    # does the one that applies: both are printed, neither is a question.
    os.remove(os.path.join(copy.state, "." + app_listen.CACHE))
    new = _after_sync(copy, "chat-new")
    _never_asks(new)
    assert "python3 tools/app.py listen" in new and "app.py republish" in new
    assert "Artifact, action publish" in new
    # Once published, the sync says nothing more about the page.
    copy.page(current=True)
    assert "Claude: " not in _after_sync(copy, "helper-1")


def test_an_update_that_left_the_page_code_alone_refreshes_its_data(copy):
    import app_listen
    copy.page(current=True)
    said = _after_sync(copy, "big-chat", landed=True)
    _never_asks(said)
    assert "python3 tools/app.py view" in said and app_listen.SAY_UPDATED in said
    assert "Artifact, action publish" not in said and "republish" not in said
    # A sync that took nothing says nothing about the page.
    assert "update just landed" not in _after_sync(copy, "big-chat")


def test_the_sync_tells_the_new_code_when_its_run_took_an_update(monkeypatch):
    import sync_app
    seen = []
    monkeypatch.setattr(sync_app.subprocess, "run",
                        lambda *a, **k: seen.append(k["env"]) or
                        subprocess.CompletedProcess(a, 0, "", ""))
    monkeypatch.setenv(sync_app.LANDED, "1")              # left over from an earlier run
    sync_app.upgrades("--after-sync")
    sync_app.upgrades("--after-sync", landed=True)
    assert sync_app.LANDED not in seen[0] and seen[1][sync_app.LANDED] == "1"
    import profile_upgrades
    assert profile_upgrades.LANDED == sync_app.LANDED


def test_a_start_before_the_days_check_leaves_the_page_to_it(copy, monkeypatch):
    """The day's check runs after start has printed, and the update it takes can change the
    page: publishing from start as well published the page twice, the old code first."""
    import app_listen
    import app_setup
    copy.page(current=False)
    env = copy.env()
    for k in set(os.environ) - set(env):
        monkeypatch.delenv(k)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(app_setup, "_sync_stale", lambda: True)
    code, lines = app_setup.start(on="test", tools="none")
    said = "\n".join(app_listen.shape(code, lines, chat="helper-1"))
    assert not _publish_steps(said), said
    check = [ln for ln in said.splitlines() if "sync_app.py --on" in ln]
    assert check and "the person's page is done at once, and is never a question" in check[0]
    # Not stale: start republishes it itself, unasked, and says the one line.
    monkeypatch.setattr(app_setup, "_sync_stale", lambda: False)
    code, lines = app_setup.start(on="test", tools="none")
    said = "\n".join(lines)
    assert _publish_steps(said) and "never asking first" in said
    assert app_listen.SAY_UPDATED in said and "publish once more" in said


def test_the_pin_is_offered_once_ever_even_when_nobody_answers(copy):
    first = copy.run("published", PAGE, "--chat", "setup-chat")
    assert "action pin" in first and "never mention pinning otherwise" in first
    with open(os.path.join(copy.profile, "app.json"), encoding="utf-8") as fh:
        assert json.load(fh)["pin"]["offered"]
    # No answer recorded: still never offered again, by a publish or by start.
    assert "action pin" not in copy.run("published", PAGE, "--chat", "setup-chat")
    for chat in ("setup-chat", "another-chat"):
        assert "action pin" not in copy.run("start", "--on", "test", "--tools", "none",
                                            "--chat", chat)
    # An answer given later is kept beside the offer.
    copy.run("pinned", "yes")
    with open(os.path.join(copy.profile, "app.json"), encoding="utf-8") as fh:
        pin = json.load(fh)["pin"]
    assert pin["answer"] == "yes" and pin["offered"] and pin["asked"]


def test_the_helper_is_announced_in_one_short_sentence(copy):
    import app_listen
    copy.page()
    assert copy.send(copy.run("listen", copy.dump(), "--chat", "big-chat"))
    said = copy.run("start", "--on", "Opus 5.5", "--tools", "none", "--chat", "big-chat")
    step = [ln for ln in said.splitlines() if "give the page a small chat of its own" in ln][0]
    assert ("Tell the person this one sentence, and nothing more about it: "
            f"\"{app_listen.SAY_HELPER}\"") in step
    assert "Keep it: it answers your page" not in step
