"""The chat that starts Claude on the person's computer asks for what it needs on their page,
starts a chat there only in Auto, and takes the app's updates at every wake; the computer is
said to be off only where their list of computers shows it; and a LinkedIn sign-in on the
computer is made in that chat, seen as soon as it is made.

Found on the maintainer's Mac on 2026-11-12: after the one-time Allow in "Job search: starts
chats on your computer", that chat's own Auto was lost, so creating the chat on the computer in
Auto was refused; it said "There's now a card on your page" while To do showed none (it had
written the card into a file of its own copy, never saved, which no drawing of the page reads)
and the work's line said the computer was off while it was on. Left in Accept edits, it started
the chat on the computer anyway, which came up in Manual and stopped on its first command. It
took the app's updates only once, when it was made. And a chat on the computer that met a
sign-out looked at the same login address, read before the person signed in, for half an hour.
Every person, chat and computer here is invented.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_model  # noqa: E402
import computer  # noqa: E402
from test_a_computer_chat_is_seen_to_its_end import BELL, NOW, T, URL, _apply, _as  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import _db, _w  # noqa: E402
from test_the_computer_side_just_works import BRIDGE, _beat  # noqa: E402

WID = "network~read~1"
WORK = (WID, _w("network", "Harbourline Bank", to="computer", title="People at Harbourline Bank",
                asked="2026-10-25T17:00:00Z"))
STARTER = {"chat": "session_starterEXAMPLE", "bell": BELL, "made_at": "2026-10-20T08:00:00Z",
           "ready_at": "2026-10-20T08:02:00Z"}
ASLEEP = {"environments": [dict(BRIDGE["environments"][1], state="inactive")]}


def _with_starter(db: dict, **kw) -> dict:
    return dict(db, meta={"computer_starter": {"data": dict(STARTER, **kw), "version": 3}})


def _asks(db: dict, on: str, at, tmp_path, name: str = "w") -> dict:
    return _apply(db, computer.starter_waits(db, on, at, str(tmp_path / name)))


def _starter_route(monkeypatch, tmp_path, db, at=T):
    """The route as the starter itself takes it: every tool, on the cloud."""
    import app_setup
    _as(monkeypatch, "cloud", tmp_path)
    monkeypatch.setattr(app_setup, "origin", lambda: ("someone", "my-job-search"))
    return computer.route(db, at, chat=STARTER["chat"], envs=BRIDGE, url=URL,
                          tools=["create_session", "get_session", "list_triggers",
                                 "confirm_repository_trust", "ArtifactData", "Artifact",
                                 "ArtifactComments", "list_environments"])


# ------------------------------------------------------------------ (a) every wake


def test_every_wake_of_the_starter_begins_with_the_days_check():
    """It ran the day's check once, when it was made, so a starter kept for weeks never took
    the app's updates."""
    prompt = computer.starter_prompt(URL, "github.com/someone/my-job-search")
    paras = prompt.split("\n")
    sync = next(p for p in paras if "sync_app.py --if-stale" in p)
    assert "every wake" in sync and sync.lstrip().startswith("Every turn of this chat"), sync
    assert "First, once" not in sync
    # Before the once-only steps and the every-wake steps alike.
    assert prompt.index("sync_app.py --if-stale") < prompt.index("First, once")
    assert prompt.index("sync_app.py --if-stale") < prompt.index("every time this chat is woken")


# ------------------------------------------------------------------ (b) Auto or nothing


def test_a_chat_on_the_computer_is_started_in_auto_or_not_at_all(tmp_path, monkeypatch):
    got = _starter_route(monkeypatch, tmp_path, _with_starter(_db(WORK)))
    assert got["route"] == "computer session" and got["call"]["permission_mode"] == "auto"
    then = " ".join(got["then"].split())
    # Refused Auto: nothing is made in another mode or without one.
    assert "without permission_mode" not in then.replace("never make it in any other mode or "
                                                         "without permission_mode", "")
    assert "never make it in any other mode or without permission_mode" in then
    assert "computer.py starter-waits <dump> --on mode" in then
    # Never the file of its own copy that no drawing of the page reads.
    assert "app.py mode-refused" not in then
    # The starter's own words say the same.
    prompt = computer.starter_prompt(URL, "github.com/x/y")
    assert "started only in Auto, never in any other mode" in prompt


def test_the_lost_auto_is_one_card_and_the_works_line_with_the_chat_named(tmp_path):
    db = _asks(_with_starter(_db(WORK)), "mode", T, tmp_path)
    st = computer.state(db, T, envs=BRIDGE)
    assert st["state"] == "starter_waits" and st["say"] == "starter_mode" and st["asks"] == "mode"
    assert st["line"] == ("Claude needs your OK once: open the chat “Job search: starts chats on "
                          "your computer” and switch it to Accept edits and then back to Auto.")
    # On To do at once, nothing to wait out first: nothing moves until they do it.
    assert st["card"]
    card = computer.card(st)
    assert card["title"] == "Claude needs your OK once"
    assert card["open"] == {"label": "Open it",
                            "url": "https://claude.ai/code/session_starterEXAMPLE"}
    assert computer.STARTER_TITLE in card["body"] and "People at Harbourline Bank" in card["body"]
    steps = card["steps"]
    assert [s.split(".")[0] for s in steps] == [str(n) for n in range(1, len(steps) + 1)]
    assert any("Accept edits" in s for s in steps) and any("choose Auto" in s for s in steps)
    assert not any("Allow" in s for s in steps)          # only what is still needed
    # The page's helper rings it as ever, so their next tap after switching starts the chat.
    import app_listen
    app_listen_kind = app_listen.chat_kind
    try:
        app_listen.chat_kind = lambda: "cloud"
        got = computer.route(db, T + timedelta(minutes=1), chat="session_helperEXAMPLE",
                             envs=BRIDGE, tools=["create_session"])
    finally:
        app_listen.chat_kind = app_listen_kind
    assert got["route"] == "ring starter", got


# ------------------------------------------------------------------ (c) the Allow


def test_the_allow_question_is_asked_on_the_page_while_it_waits(tmp_path, monkeypatch):
    got = _starter_route(monkeypatch, tmp_path, _with_starter(_db(WORK)))
    then = " ".join(got["then"].split())
    # Recorded before the question, cleared once it is answered.
    assert then.index("starter-waits <dump> --on allow") < then.index("confirm_repository_trust")
    assert then.index("confirm_repository_trust") < then.index("starter-waits <dump> --on none")
    db = _asks(_with_starter(_db(WORK)), "allow", T, tmp_path)
    st = computer.state(db, T, envs=BRIDGE)
    assert st["say"] == "starter_allow" and st["card"]
    assert st["line"] == ("Claude needs your OK once: open the chat “Job search: starts chats on "
                          "your computer”, tap Allow, then switch it to Accept edits and back to "
                          "Auto.")
    card = computer.card(st)
    assert card["title"] == "Claude needs your OK once" and card["open"]["url"].endswith(
        STARTER["chat"])
    assert any("choose Allow" in s for s in card["steps"])
    # The steps are the registry's, like every other Claude screen's.
    import claude_surfaces
    assert card["steps"] == [ln for ln in claude_surfaces.steps("computer-allow", page=True)
                             if ln[:1].isdigit()]
    assert any("Accept edits" in s for s in card["steps"])     # Auto is cleared by the Allow
    # It waits on the question itself: never rung meanwhile, rung again once it is old.
    _as(monkeypatch, "cloud", tmp_path)
    helper = dict(chat="session_helperEXAMPLE", envs=BRIDGE, tools=["create_session"])
    assert computer.route(db, T + timedelta(minutes=2), **helper)["route"] == "starter waits"
    later = T + timedelta(seconds=computer.ALLOW_WAIT_S + 60)
    assert computer.route(db, later, **helper)["route"] == "ring starter"
    # Answered: the card goes.
    done = _asks(db, "none", T + timedelta(minutes=3), tmp_path, "n")
    assert computer.state(done, T + timedelta(minutes=3), envs=BRIDGE)["state"] != \
        "starter_waits"


# ------------------------------------------------------------------ (d) never off while on


def test_the_computer_is_off_only_where_its_list_shows_it_not_on(tmp_path):
    old = dict(_db(WORK), chats=_beat(age_s=26 * 3600))
    # No list kept, an old check-in: not said off.
    st = computer.state(old, T)
    assert st["state"] != "off" and st["line"] != computer.SAY["off"], st
    # Its list shows it on: never off.
    assert computer.state(old, T, envs=BRIDGE)["line"] != computer.SAY["off"]
    # Its list shows it not on: off.
    assert computer.state(old, T, envs=ASLEEP)["state"] == "off"


def test_a_starter_being_made_or_starting_a_chat_says_starting_on_the_computer(tmp_path):
    old = dict(_db(WORK), chats=_beat(age_s=26 * 3600))
    making = _with_starter(old, bell="", made_at=app_model.stamp(T - timedelta(minutes=2)))
    st = computer.state(making, T)
    assert st["state"] == "starting_chat" and st["line"] == "Starting on your Studio Laptop.", st
    rung = _with_starter(old, rung_at=app_model.stamp(T - timedelta(minutes=1)))
    assert computer.state(rung, T, envs=BRIDGE)["line"] == "Starting on your Studio Laptop."
    # Long after, with nothing back: no longer said to be starting.
    stale = _with_starter(old, rung_at=app_model.stamp(T - timedelta(hours=3)))
    assert computer.state(stale, T, envs=BRIDGE)["state"] != "starting_chat"


# ------------------------------------------------------------------ (e) the card reaches To do


def test_the_starters_ask_reaches_to_do_wherever_the_page_is_drawn(tmp_path, monkeypatch):
    """The ask is the page's own record, read by every drawing of the page (computer.seen),
    ranked above an old check-in, and kept through the starter's own wake."""
    import person
    from test_a_tick_on_the_page_is_applied_once import Search
    old = dict(_db(WORK), chats=_beat(age_s=26 * 3600))
    db = _asks(_with_starter(old), "mode", T, tmp_path)
    # Its next wake keeps it: only its own word, or a chat started there, clears it.
    woke = _apply(db, computer.starter_woke(db, T + timedelta(seconds=1), str(tmp_path / "k")))
    assert computer.starter_asks(woke) == "mode"
    s = Search(str(tmp_path / "copy"))
    monkeypatch.setenv(person.ENV, s.profile)
    monkeypatch.setenv(person.STATE_ENV, s.state)
    monkeypatch.setattr(computer, "_works_on", lambda: "computer")
    person._modules.clear()
    person._data.clear()
    try:
        seen = computer.seen(woke, T + timedelta(seconds=2))
        assert seen["state"] == "starter_waits", seen               # never off
        built, _ = app_model.build(T.date(), T, only=("needs_you", "where"), computer=seen)
    finally:
        person._modules.clear()
        person._data.clear()
    card = next(c for c in built["needs_you"] if c["id"] == "q-setup-computer")
    assert card["title"] == "Claude needs your OK once" and card["open"]["url"].endswith(
        STARTER["chat"])
    row = built["where"]["computer"]
    assert row["say"] == computer.SAY["starter_mode"] and row["asks"] == "mode"
    # A chat started on the computer since: the ask is over.
    started = _apply(woke, computer.started(woke, WID, "session_macEXAMPLE", "env_bridge1",
                                            "Studio Laptop", T + timedelta(minutes=5),
                                            str(tmp_path / "s")))
    assert computer.starter_asks(started) == ""


def test_the_starter_waits_command_writes_the_pages_own_record(tmp_path):
    dump = tmp_path / "dump"
    (dump / "meta").mkdir(parents=True)
    with open(dump / "meta" / "computer_starter.json", "w", encoding="utf-8") as fh:
        json.dump({"data": STARTER, "version": 3}, fh)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "computer.py"),
                        "starter-waits", str(dump), "--on", "mode", "--now", NOW],
                       capture_output=True, text=True, encoding="utf-8",
                       env=dict(os.environ, LJS_STATE=str(tmp_path / "state")))
    assert r.returncode == 0, r.stderr
    batch = json.loads(r.stdout)["batches"][0]
    entry = json.load(open(batch, encoding="utf-8"))[0]
    assert (entry["collection"], entry["doc_id"]) == ("meta", "computer_starter")


# ------------------------------------------------------------------ the sign-in on the computer


def _signin_item(**kw) -> dict:
    item = _w("network", "Harbourline Bank", to="computer", title="Reading 3 profiles",
              status="needs_you", note="LinkedIn is signed out.",
              needs={"question": "LinkedIn is signed out in Claude's browser.",
                     "signin": "linkedin"},
              asked_you_at=app_model.stamp(T - timedelta(minutes=3)),
              computer_session={"id": "session_macEXAMPLE", "at": NOW,
                                "computer": "Studio Laptop"})
    item.update(kw)
    return item


def _run(tmp_path, cmd, item, *extra):
    dump = tmp_path / f"d{len(list(tmp_path.iterdir()))}"
    (dump / "work").mkdir(parents=True)
    with open(dump / "work" / (WID.replace("~", "@") + ".json"), "w", encoding="utf-8") as fh:
        json.dump({"data": item, "version": 4}, fh)
    return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "computer.py"), cmd,
                           str(dump), "--work", WID, "--now", NOW, *extra],
                          env=dict(os.environ, LJS_STATE=str(tmp_path / "state")),
                          capture_output=True, text=True, encoding="utf-8")


def test_a_sign_in_made_during_the_wait_is_seen_at_the_next_look(tmp_path):
    # The address read before the wait (the login page) is never judged: the wait only waits,
    # then says to open the feed afresh.
    waited = _run(tmp_path, "signin-wait", _signin_item(), "--every", "0", "--url",
                  "https://www.linkedin.com/login/?session_redirect=x")
    assert waited.stdout.startswith("look now"), waited.stdout + waited.stderr
    assert computer.FEED_URL in waited.stdout and "signin-seen" in waited.stdout
    # They signed in meanwhile: the feed opened afresh shows it, and the chat carries on, with
    # the sign-in tab it opened closed.
    seen = _run(tmp_path, "signin-seen", _signin_item(), "--url",
                "https://www.linkedin.com/feed/", "--title", "Feed | LinkedIn")
    assert seen.stdout.startswith("signed-in:"), seen.stdout + seen.stderr
    assert "close the sign-in tab" in seen.stdout and "computer.py signed-in" in seen.stdout
    # Any LinkedIn page but a sign-in or check page is signed in; those are not.
    assert computer.signin_seen("https://www.linkedin.com/in/someone-example/") == "signed-in"
    assert computer.signin_seen("https://www.linkedin.com/login") == "waiting"
    assert computer.signin_seen("https://www.linkedin.com/checkpoint/challenge/x") == "verifying"
    assert computer.signin_seen("https://www.linkedin.com/feed/", "LinkedIn Login, Sign in") == \
        "waiting"
    still = _run(tmp_path, "signin-seen", _signin_item(), "--url",
                 "https://www.linkedin.com/login")
    assert still.stdout.startswith("look:") and "signin-wait" in still.stdout


def test_the_sign_in_card_opens_the_chat_on_the_computer_and_never_linkedin(tmp_path):
    import page_db
    db = _db((WID, _signin_item(status="running", needs=None, note=None, asked_you_at=None,
                                claimed_by="session_macEXAMPLE")))
    made = page_db.finish(db, WID, T, str(tmp_path / "f"), status="needs_you",
                          question="LinkedIn is signed out in Claude's browser.",
                          signin="linkedin", chat_kind="computer", chat="session_macEXAMPLE")
    batches = made["batches"] if isinstance(made, dict) else made
    entry = json.load(open(batches[0], encoding="utf-8"))[0]
    fields = entry.get("data")
    if fields is None:
        fields = json.load(open(entry["file_path"], encoding="utf-8"))
    needs = fields["needs"]
    assert needs["chat"] == "session_macEXAMPLE" and needs["signin"] == "linkedin"
    assert needs["say"] == ("Sign in to LinkedIn once, in the chat on your Studio Laptop: tap "
                            "Open the chat, then sign in on the page already open there. Being "
                            "signed in beside your page does not count.")
    assert "linkedin.com" not in json.dumps(needs)
    # The page draws that: its one button the chat's own link, nothing opening LinkedIn.
    js = open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8").read()
    box = js[js.index("function signinBox("):]
    box = box[:box.index("const tried = S.signinFor")]
    assert '"https://claude.ai/code/" + chat' in box and "Open the chat" in box
    assert "openReading" not in box and "linkedin.com" not in box


# ------------------------------------------------------------------ a computer that reconnects


def test_a_computer_that_reconnects_under_a_new_name_is_the_same_computer(tmp_path,
                                                                          monkeypatch):
    """A bridge's name ends in a code that changes when it reconnects ("Mac:Documents:cc73",
    then "Mac:Documents:f6be"), its environment id the same: nothing the app keeps or compares
    is that name, so the computer, its folder and the chat started there are the same."""
    mac = BRIDGE["environments"][1]
    before = {"environments": [dict(mac, name="Studio Laptop:Documents:cc73")]}
    after = {"environments": [dict(mac, name="Studio Laptop:Documents:f6be")]}
    assert [(b["id"], b["computer"], b["folder"]) for b in computer.bridges(before)] == \
        [(b["id"], b["computer"], b["folder"]) for b in computer.bridges(after)]
    db = _with_starter(dict(_db(WORK), chats=_beat()))
    one = _starter_route(monkeypatch, tmp_path, db)
    import app_setup
    monkeypatch.setattr(app_setup, "origin", lambda: ("someone", "my-job-search"))
    two = computer.route(db, T, chat=STARTER["chat"], envs=after, url=URL,
                         tools=["create_session"])
    assert one["call"]["environment_id"] == two["call"]["environment_id"] == "env_bridge1"
    assert computer.state(db, T, envs=before)["state"] == \
        computer.state(db, T, envs=after)["state"]


# ------------------------------------------------------------------ putting the chat away


def test_the_bell_is_read_before_it_is_rung_and_a_refused_ring_leaves_the_record(
        tmp_path, monkeypatch):
    """A chat on the Mac rang the starter's bell at the end of its job with a publish alone:
    the bell is the starter's page, so the publish was refused, the starter was never woken
    and that chat stayed in the sidebar."""
    said = computer.ring_steps(BELL, "/tmp/bell.html")
    assert said.index(f"Artifact read with url {BELL}") < said.index("Artifact publish")
    assert "read it first only" not in said and "Refused even so" in said
    prompt = computer.session_prompt(WID, "People", URL, "their job search")
    step8 = prompt[prompt.index("8. Wake"):prompt.index("9. Your last")]
    assert "the bell's read first, then its publish" in step8
    assert "waits to be put away" in step8
    # A helper with no Artifact tool hands back the read before the publish.
    done = dict(WORK[1], status="done",
                computer_session={"id": "session_macEXAMPLE", "at": NOW})
    db = _with_starter(_db((WID, done)))
    _as(monkeypatch, "cloud", tmp_path)
    got = computer.route(db, T + timedelta(hours=1), chat="session_helperEXAMPLE",
                         tools=["create_session"])
    assert got["route"] == "ring starter", got
    calls = [ln for ln in got["handback"] if ln.startswith("call: Artifact ")]
    assert '"action": "read"' in calls[0] and '"action": "publish"' in calls[1], calls
    # Refused even so, the page still lists it to be put away at the next wake.
    assert computer.waiting(db, T + timedelta(hours=1))["finished"] == [
        {"work": WID, "session": "session_macEXAMPLE"}]


# ------------------------------------------------------------------ work queued behind a run


def test_work_queued_behind_a_run_signed_in_waits_its_turn_never_a_sign_in_line(
        tmp_path, monkeypatch):
    """A second piece of work for the computer said "Claude's browser on your computer did not
    keep your LinkedIn sign-in" while a chat there was searching LinkedIn signed in: the line
    came from a check-in written before the person signed in."""
    import person
    from test_a_tick_on_the_page_is_applied_once import Search
    beat_at = T - timedelta(minutes=30)
    running = _w("network", "Fernhill Freight", to="computer", title="People at Fernhill Freight",
                 status="running", claimed_by="session_macEXAMPLE", claimed_as="computer",
                 claimed_at=app_model.stamp(beat_at - timedelta(minutes=1)),
                 stage_at=app_model.stamp(T - timedelta(minutes=2)),
                 lease_until=app_model.stamp(T + timedelta(minutes=20)),
                 computer_session={"id": "session_macEXAMPLE", "at": NOW})
    for facts in ({"linkedin": "out"}, {"cookies": "off"}):
        db = dict(_db(WORK, ("network~read~2", running)),
                  chats=_beat(age_s=30 * 60, **facts))
        st = computer.state(db, T, envs=BRIDGE)
        assert st["state"] not in ("signed_out", "forgets", "signin_unsure"), (facts, st)
        assert not st["card"]
        assert st["queued_line"] == "Waiting its turn on your Studio Laptop.", st
    # A check-in newer than the read still says what it says.
    late = dict(_db(WORK, ("network~read~2", running)), chats=_beat(age_s=60, linkedin="out"))
    assert computer.state(late, T, envs=BRIDGE)["state"] == "signed_out"
    # The page's work line is that turn.
    s = Search(str(tmp_path / "copy"))
    monkeypatch.setenv(person.ENV, s.profile)
    monkeypatch.setenv(person.STATE_ENV, s.state)
    person._modules.clear()
    person._data.clear()
    try:
        built, _ = app_model.build(T.date(), T, only=("where",), computer=st)
    finally:
        person._modules.clear()
        person._data.clear()
    assert built["where"]["computer"]["queued_line"] == "Waiting its turn on your Studio Laptop."
    js = open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8").read()
    line = js[js.index("function computerLine()"):]
    line = line[:line.index("\n  }\n")]
    assert "c.queued_line" in line
