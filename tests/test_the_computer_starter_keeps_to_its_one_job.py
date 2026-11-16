"""The chat that starts Claude's chats on the person's computer ("Job search: starts chats on
your computer", the starter) does that one job: it starts the chat with the tools it has,
reads its own mode at every wake, says the card's own steps where the person writes to it,
hears none of the page's work from the update check or the hook, and never leaves an earlier
chat in the person's list for them to delete.

Found in the maintainer's copy on 2026-11-16 (issues #275, #277, #278, #279, #280, #282): the
starter listed create_session among its tools and was told "This chat has no tool for part of
this"; after its worker restarted in the default mode, a read waited two days, found only by a
refused create_session, behind a card that said "Claude needs your OK" when nothing asked
anything; the starter gave other steps than the card; the update check told it to bring the
page up to date and start the improvements, and the hook held its turn until it did; and the
computer's earlier own chat stayed beside the new one. Every person, chat and computer here is
invented.
"""
from __future__ import annotations

import io
import json
import os
import sys
from datetime import timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_listen  # noqa: E402
import app_model  # noqa: E402
import computer  # noqa: E402
from test_a_computer_chat_is_seen_to_its_end import NOW, T, URL, _apply, _as  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import _db, _w  # noqa: E402
from test_the_computer_side_just_works import BRIDGE  # noqa: E402
from test_the_computers_own_chat_takes_work_with_no_tap import (  # noqa: E402
    COPY, LISTENER, STARTER, _cloud, _dump, _run, _with, _write)

WID = "network~read~1"
WORK = (WID, _w("network", "Harbourline Bank", to="computer", title="People at Harbourline Bank",
                asked=NOW))
# The opening of the starter's prompt as 4.16.1 made it: a starter made then is still known.
OLD_PROMPT = ("This chat starts the chats on my computer for my job search, and nothing else. It "
              "never answers my page, never publishes it and never messages another chat. Its "
              "copy is github.com/someone/my-job-search; my page is " + URL + ".")
# A cloud chat passes its tools as it has them: MCP-prefixed, comma and space separated, or
# one a line, and only the ones it has loaded (list_triggers and confirm_repository_trust,
# named only by the refusal steps, left out).
CLOUD_TOOLS = ("Bash, Read, Edit, mcp__claude-code-remote__create_session, "
               "mcp__claude-code-remote__get_session, mcp__claude-code-remote__list_environments, "
               "mcp__claude-code-remote__archive_session, Artifact, ArtifactData")


def _transcript(path, first: str) -> str:
    """A conversation's file as Claude Code keeps it: a summary line, a meta line, then the
    message it was started with."""
    rows = [{"type": "summary", "summary": "x"},
            {"type": "user", "isMeta": True, "message": {"role": "user", "content": "caveat"}},
            {"type": "user", "message": {"role": "user",
                                         "content": [{"type": "text", "text": first}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": "ok"}}]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(json.dumps(r) for r in rows) + "\n")
    return str(path)


# ------------------------------------------------------------------ #279 its own tools


def test_the_starter_starts_the_chat_with_its_tools_named_as_a_cloud_chat_has_them(
        tmp_path, monkeypatch):
    _cloud(monkeypatch, tmp_path)
    envs = _write(tmp_path / "envs.json", BRIDGE)
    for n, tools in enumerate((CLOUD_TOOLS,
                               "Bash Read mcp__claude-code-remote__create_session Artifact",
                               "Bash\nmcp__claude-code-remote__create_session\nArtifactData")):
        dump = _dump(_with(_db(WORK)), tmp_path / f"d{n}")
        got = json.loads(_run("route", dump, "--chat", STARTER["chat"], "--envs", envs,
                              "--tools", tools, "--now", NOW))
        assert got["route"] == "computer session", (tools, got)
        assert "handback" not in got and computer.HAND_BACK not in got["then"], (tools, got)
        assert got["tool"] == "create_session" and got["call"]["permission_mode"] == "auto"
    # get_session alone is still no create_session: a chat without it is never told it can.
    had = computer.tools_had("mcp__claude-code-remote__get_session, ArtifactData")
    assert "create_session" not in had and "Artifact" not in had


# ------------------------------------------------------------------ #277, #280 its own mode


def test_every_wake_reads_its_own_mode_first_an_older_starter_included(tmp_path):
    """starter-woke's `then` is what every starter's prompt, 4.16.1's included, does at each
    wake before it routes: the mode is read there, never found from a refused create_session."""
    got = json.loads(_run("starter-woke", _dump(_with(_db(WORK)), tmp_path / "d"), "--now", NOW))
    then = got["then"]
    assert then == computer.MODE_CHECK
    assert "get_session with no session_id" in then and "starter-mode \"$D\" --mode" in then
    prompt = computer.starter_prompt(URL, COPY)
    woke = prompt.index("starter-woke")
    assert "where it prints a `then`, do that too, before anything below" in prompt
    assert woke < prompt.index("tools/computer.py route")


def test_out_of_auto_the_card_is_up_at_once_and_nothing_is_started(tmp_path, monkeypatch):
    db = _with(_db(WORK))
    # The worker restarted in the default mode; after an Allow, the mode shows none at all.
    for mode in ("default", "none", "acceptEdits"):
        got = json.loads(_run("starter-mode", _dump(db, tmp_path / f"d-{mode}"), "--mode", mode,
                              "--now", NOW))
        assert got["next"].startswith("not auto:") and "skip `queued`" in got["next"], got
        assert got["batches"], mode
    seen = _apply(db, computer.starter_mode(db, "default", T, str(tmp_path / "w"))["batches"])
    assert computer.starter_asks(seen) == "mode"
    st = computer.state(seen, T, envs=BRIDGE)
    assert st["say"] == "starter_mode" and st["card"], st
    # While the card is new it looks again by itself: switching it is all the person does.
    later = computer.starter_mode(seen, "default", T + timedelta(minutes=10), str(tmp_path / "l"))
    assert later["batches"] == [], "asked once, never again at each look"
    assert "run_in_background true" in later["next"] and \
        f"sleep {computer.MODE_LOOK_S}" in later["next"]
    old = T + timedelta(seconds=computer.MODE_LOOK_FOR_S + 60)
    assert "run_in_background" not in computer.starter_mode(seen, "default", old,
                                                            str(tmp_path / "o"))["next"]
    # Back in Auto: the card goes at once, and the route starts the chat on the computer.
    back = computer.starter_mode(seen, "auto", T + timedelta(minutes=20), str(tmp_path / "b"))
    assert back["next"].startswith("auto:") and back["batches"]
    again = _apply(seen, back["batches"])
    assert computer.starter_asks(again) == "" and \
        computer.state(again, T, envs=BRIDGE)["state"] != "starter_waits"
    _cloud(monkeypatch, tmp_path)
    got = computer.route(again, T, chat=STARTER["chat"], envs=BRIDGE, url=URL, tools=CLOUD_TOOLS)
    assert got["route"] == "computer session" and "handback" not in got
    # In Auto with nothing asked: nothing written, the wake carries on.
    calm = computer.starter_mode(_with(_db(WORK)), "auto", T, str(tmp_path / "n"))
    assert calm["batches"] == [] and calm["next"].startswith("auto: carry on")
    # Its Allow card already says to switch it back to Auto: never replaced by this one.
    allow = _apply(db, computer.starter_waits(db, "allow", T, str(tmp_path / "a")))
    assert computer.starter_mode(allow, "default", T, str(tmp_path / "a2"))["batches"] == []


def test_a_starter_already_stuck_out_of_auto_is_put_right_by_its_next_wake(tmp_path, monkeypatch):
    """An install updated with its starter already waiting days on its mode (a refusal wrote
    the ask): the next wake reads the mode, and once it is Auto the work starts, with no other
    step from the person."""
    db = _with(_db(WORK))
    stuck = _apply(db, computer.starter_waits(db, "mode", T - timedelta(days=2),
                                              str(tmp_path / "s")))
    st = computer.state(stuck, T, envs=BRIDGE)
    assert st["say"] == "starter_mode" and computer.card(st)["title"] == computer.MODE_CARD_TITLE
    woke = json.loads(_run("starter-woke", _dump(stuck, tmp_path / "d"), "--now", NOW))
    assert woke["then"] == computer.MODE_CHECK
    got = json.loads(_run("starter-mode", _dump(stuck, tmp_path / "d2"), "--mode", "auto",
                          "--now", NOW))
    fixed = _apply(stuck, got["batches"])
    assert computer.starter_asks(fixed) == ""
    _cloud(monkeypatch, tmp_path)
    assert computer.route(fixed, T, chat=STARTER["chat"], envs=BRIDGE, url=URL,
                          tools=CLOUD_TOOLS)["route"] == "computer session"


# ------------------------------------------------------------------ #275 the card and its steps


def test_the_mode_card_is_a_setting_and_the_starter_gives_the_cards_own_steps(tmp_path):
    db = _with(_db(WORK))
    seen = _apply(db, computer.starter_waits(db, "mode", T, str(tmp_path / "w")))
    card = computer.card(computer.state(seen, T, envs=BRIDGE))
    assert card["title"] == "Switch one chat back to Auto" and "OK" not in card["title"]
    assert "nothing pops up" in card["body"] and "setting" in card["body"], card["body"]
    import claude_surfaces
    assert card["steps"] == [ln for ln in claude_surfaces.steps("computer-auto-again", page=True)
                             if ln[:1].isdigit()]
    said = computer.starter_mode(seen, "default", T, str(tmp_path / "m"))["next"]
    menu = [s.split(". ", 1)[1] for s in card["steps"] if "menu" in s]
    assert len(menu) == 2 and all(s in said for s in menu), (menu, said)
    assert [s.split(". ", 1)[1] for s in computer.mode_steps()] == menu
    # Read again before saying it is still not in Auto: a switch just made can take a moment.
    assert said.index("read get_session again") < said.index(menu[0])
    assert "Nothing pops up here" in said and "Come back to this page" not in said


# ------------------------------------------------------------------ #278 no chat left behind


def test_an_earlier_computers_own_chat_is_put_away_once_another_has_taken_its_place(tmp_path):
    old = app_model.stamp(T - timedelta(days=2))
    titles = [computer.LISTENER_TITLE,
              computer.session_title("People at Harbourline Bank", "Studio Laptop")]
    listing = _write(tmp_path / "chats.json",
                     [{"title": t, "status": "idle", "updated_at": old} for t in titles])
    live = _dump(_with(_db(), LISTENER), tmp_path / "live")
    # Run by the computer's own chat: the other chat of that name is the one it replaced.
    said = _run("archivable", listing, "--dump", live, "--chat", LISTENER["chat"], "--now", NOW)
    assert f"archive: {computer.LISTENER_TITLE}" in said and titles[1] in said, said
    # Run by another chat while that one is live: it is kept, as ever.
    said = _run("archivable", listing, "--dump", live, "--chat", "session_macB", "--now", NOW)
    assert computer.LISTENER_TITLE not in said and titles[1] in said, said
    # The one there not answering (stale): this chat takes its place, so it goes.
    stale = _dump(_with(_db(), LISTENER, stale_at=app_model.stamp(T - timedelta(minutes=10))),
                  tmp_path / "stale")
    said = _run("archivable", listing, "--dump", stale, "--chat", "session_macB", "--now", NOW)
    assert f"archive: {computer.LISTENER_TITLE}" in said, said
    # An older prompt, with no --chat: kept as before.
    assert computer.LISTENER_TITLE not in _run("archivable", listing, "--dump", live, "--now",
                                               NOW)
    # Every job's prompt says which chat lists them.
    prompt = computer.session_prompt(WID, "People", URL, "their job search")
    assert "archivable \"$D/chats.json\" --dump \"$D\" --chat <your id>" in prompt


def test_the_starter_never_asks_the_person_to_delete_a_chat(tmp_path):
    # The page's own line for a job on the computer said they could delete its chat, and the
    # starter said the same to them.
    assert "delete" not in computer.runs_there("Studio Laptop")
    prompt = " ".join(computer.starter_prompt(URL, COPY).split())
    assert "never tell me to delete, archive or close a chat, and never say one was closed" in \
        prompt
    db = _with(_db(WORK))
    for mode in ("auto", "default"):
        said = computer.starter_mode(db, mode, T, str(tmp_path / mode))["next"]
        assert "never tell them to delete, archive or close a chat" in said.replace(
            "Never", "never"), said


# ------------------------------------------------------------------ #282 none of the page's work


def test_a_starter_is_known_by_its_word_its_record_or_its_first_message(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    monkeypatch.delenv(app_listen.ROLE_ENV, raising=False)
    old = _transcript(tmp_path / "old.jsonl", OLD_PROMPT)
    new = _transcript(tmp_path / "new.jsonl", computer.starter_prompt(URL, COPY))
    page = _transcript(tmp_path / "page.jsonl", "Open my job search page and answer it.")
    assert app_listen.starter_here(transcript=old) and app_listen.starter_here(transcript=new)
    assert not app_listen.starter_here(transcript=page)
    # In a cloud chat with no word given: its own conversation's file, the newest there.
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "cloud")
    import helper_usage
    monkeypatch.setattr(helper_usage, "session_file", lambda: old)
    assert app_listen.starter_here()
    monkeypatch.setattr(helper_usage, "session_file", lambda: page)
    assert not app_listen.starter_here()
    # Kept in its checkout once known, by its own id only.
    monkeypatch.setenv("LJS_CHAT", "session_starterEXAMPLE")
    app_listen.remember_starter()
    assert app_listen.starter_here()
    monkeypatch.setenv("LJS_CHAT", "session_helperEXAMPLE")
    assert not app_listen.starter_here()
    monkeypatch.setenv(app_listen.ROLE_ENV, "starter")
    assert app_listen.starter_here()


def test_the_update_check_gives_the_starter_the_update_and_nothing_else(
        sync_steps, monkeypatch, tmp_path, capsys):
    import sync_app
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    monkeypatch.delenv(app_listen.ROLE_ENV, raising=False)
    said = []
    for name in ("say_page", "app_watch_said", "setting_line", "plain_state_endings",
                 "lf_checkout"):
        monkeypatch.setattr(sync_app, name, lambda *a, n=name, **k: said.append(n) or "")
    # The day's first check, in the starter by its word: the update, and its record of the day.
    rc, steps = sync_steps("--if-stale", "--role", "starter", "--on", "m", "--tools", "none")
    assert rc == 0 and "sync" in steps and steps[-1] == "upgrades", steps
    assert not {"app_watch", "network_check", "model_check", "place_check"} & set(steps), steps
    assert not {"say_page", "app_watch_said", "setting_line"} & set(said), said
    monkeypatch.delenv(app_listen.ROLE_ENV, raising=False)
    # Already checked today, in a starter made before it said so (known by its first message).
    monkeypatch.setattr(app_listen, "starter_here", lambda *a, **k: True)
    said.clear()
    rc, steps = sync_steps("--if-stale", "--on", "m", "--tools", "none", stale=False)
    assert rc == 0 and not {"network_check", "place_check"} & set(steps), steps
    assert not {"say_page", "app_watch_said"} & set(said), said
    assert os.environ.get(app_listen.ROLE_ENV) == "starter"      # its processes know it too
    monkeypatch.delenv(app_listen.ROLE_ENV, raising=False)
    # Any other chat hears the rest, as ever.
    monkeypatch.setattr(app_listen, "starter_here", lambda *a, **k: False)
    said.clear()
    rc, steps = sync_steps("--if-stale", "--on", "m", "--tools", "none", stale=False)
    assert {"network_check", "place_check"} <= set(steps) and "say_page" in said


def test_nothing_of_the_pages_work_reaches_the_starter_from_the_files_an_update_brings(
        tmp_path, monkeypatch, capsys):
    """An older sync_app.py takes the update and runs these from the files it brought in: the
    improvements' check, the page's line and the hook each know the starter themselves."""
    import app_setup
    import learned
    import profile_upgrades
    import sync_app
    monkeypatch.setenv(app_listen.ROLE_ENV, "starter")
    # The improvements: nothing listed, claimed or said; the day's check still recorded.
    done = []
    monkeypatch.setattr(profile_upgrades, "pending", lambda: done.append("pending") or [])
    monkeypatch.setattr(sync_app, "_record_check", lambda *a, **k: done.append("record"))
    import merge_state
    monkeypatch.setattr(merge_state, "install", lambda *a, **k: done.append("driver"))
    assert profile_upgrades.main(["--after-sync"]) == 0
    assert done == ["driver", "record"] and capsys.readouterr().out == ""
    # The page's line: nothing, where any other chat is told to bring the page up to date.
    monkeypatch.setattr(app_setup, "page_record", lambda: {"url": URL})
    monkeypatch.setattr(app_setup, "set_up", lambda: True)
    monkeypatch.setattr(app_setup, "_page_current", lambda: True)
    assert app_setup.page_line(landed=True) == ""
    monkeypatch.delenv(app_listen.ROLE_ENV, raising=False)
    assert "Bring the person's page up to date now" in app_setup.page_line(landed=True)
    # The hook: the day's check line, a held turn, anything, for any chat but the starter.
    monkeypatch.setattr(learned, "_path", lambda: str(tmp_path / "learned.json"))
    monkeypatch.setattr(sync_app, "stale", lambda: True)
    monkeypatch.setattr(sync_app, "retry_due", lambda: True)
    for first, heard in ((OLD_PROMPT, False), ("Find me jobs at Harbourline Bank.", True)):
        event = {"hook_event_name": "UserPromptSubmit", "prompt": "What is on my list today",
                 "transcript_path": _transcript(tmp_path / "t.jsonl", first)}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
        assert learned._cli_hook() == 0
        out = capsys.readouterr().out
        assert ("sync_app.py --if-stale" in out) is heard, (first, out)
