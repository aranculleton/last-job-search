"""The person's own list of computers, as the last chat that routed work for the computer saw
it, is kept on the page, and the page's row reads it: an on computer is never said to be off.

The maintainer's copy, 2026-11-11 (local review 2): the page's row and its To do card are
drawn by `app.py view` from the page's database alone (`computer.seen`), which never had the
list of computers, so a Mac connected and active that day was said to be off on a check-in 25
hours old, with "open Claude there and this starts by itself", which nothing did. Whoever
routes now keeps the list (`meta/computer_envs`) with its time, and the row uses it while it
is fresh. Every computer here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_model  # noqa: E402
import computer  # noqa: E402
from test_a_computer_chat_is_seen_to_its_end import T, _as  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import _db, _w  # noqa: E402
from test_the_computer_side_just_works import BRIDGE  # noqa: E402

WORK = ("network~read~1", _w("network", to="computer", title="Reading one profile"))


def _beat(db: dict, hours: float, name: str = "Studio Laptop") -> dict:
    seen = app_model.stamp(T - dt.timedelta(hours=hours))
    db.setdefault("chats", {})[computer.beat_id(name)] = {
        "data": {"kind": "computer", "computer": name, "seen_at": seen}, "version": 1}
    return db


def _kept(db: dict, envs, hours_ago: float, tmp_path) -> dict:
    """The page's database once the list `envs`, seen `hours_ago`, is kept on it."""
    at = T - dt.timedelta(hours=hours_ago)
    batches = computer.envs_kept(db, envs, at, str(tmp_path / f"kept-{hours_ago}"))
    assert batches, "a list of computers given is kept"
    entry = json.load(open(batches[0], encoding="utf-8"))[0]
    assert (entry["collection"], entry["doc_id"]) == computer.ENVS_DOC
    with open(entry["file_path"], encoding="utf-8") as fh:
        data = json.load(fh)
    out = dict(db)
    out["meta"] = dict(db.get("meta") or {}, computer_envs={"data": data, "version": 1})
    return out


def test_the_list_kept_holds_each_bridge_with_its_folder_state_and_time(tmp_path):
    envs = {"environments": BRIDGE["environments"] + [
        {"environment_id": "env_old", "name": "Studio Laptop:Projects:9f00", "kind": "bridge",
         "description": "Bridge environment (Studio Laptop)", "state": "inactive"}]}
    db = _kept(_db(WORK), envs, 0, tmp_path)
    rec = computer.envs_record(db)
    assert rec["at"] == app_model.stamp(T)
    got = {b["environment_id"]: b for b in rec["environments"]}
    assert set(got) == {"env_bridge1", "env_old"}            # bridges only, on or not
    assert got["env_bridge1"]["state"] == "active" and got["env_bridge1"]["name"].startswith(
        "Studio Laptop:Documents")
    assert got["env_old"]["state"] == "inactive"
    # Kept again only once it changes or has aged: every route writing it was a write a wake.
    assert computer.envs_kept(db, envs, T + dt.timedelta(minutes=5), str(tmp_path / "again")) == []


def test_the_row_reads_the_list_kept_while_it_is_fresh(tmp_path, monkeypatch):
    _as(monkeypatch, "cloud", tmp_path)
    monkeypatch.setattr(computer, "_works_on", lambda: "computer")
    db = _beat(_db(WORK), 25)
    # The case found: no list kept, a check-in 25 hours old: off.
    assert computer.seen(db, T)["state"] == "off"
    # The list kept an hour ago shows it on: the row and the card never say off.
    fresh = _kept(db, BRIDGE, 1, tmp_path)
    st = computer.seen(fresh, T)
    assert st["state"] not in ("off", "gone", "no_bridge") and st["line"] != computer.SAY["off"]
    assert not st["card"] and computer.card(st) is None
    # A list seven hours old is not known any more: the check-in decides again.
    stale = _kept(db, BRIDGE, 7, tmp_path)
    assert computer.seen(stale, T)["state"] == "off"


def test_a_list_that_shows_the_computer_not_on_says_off_not_switched_off(tmp_path):
    db = _beat(_db(WORK), 5)
    asleep = {"environments": [dict(BRIDGE["environments"][1], state="inactive")]}
    assert computer.state(db, T, envs=asleep)["state"] == "off"
    # A list with no bridge at all is a computer never switched on for Claude.
    assert computer.state(db, T, envs={"environments": []})["state"] == "no_bridge"


def test_nothing_says_it_starts_by_itself_when_nothing_starts_it():
    """With the computer off, nothing starts the work when Claude opens there: the person's
    next use of the page rings it (and Start it now), or the brief. "This starts by itself"
    sent them away to wait for nothing (the maintainer, 2026-11-11: 16 hours)."""
    for key in ("off", "gone"):
        assert "by itself" not in computer.SAY[key], key
        assert "by itself" not in computer.WAITING_SAY[key], key
    assert "next time you use this page" in computer.SAY["off"]


def test_the_brief_keeps_the_list_it_checks_with(tmp_path, monkeypatch, capsys):
    """The brief lists the computers every morning for its check: that list is kept too, so
    the page's row knows the computer is on from the morning without a chat routing."""
    import brief
    import page_db
    import place
    dump = tmp_path / "dump"
    for coll, doc, data in (("work", "network@read@1", WORK[1]),
                            ("meta", "listen", {"chat": "session_helper"})):
        os.makedirs(dump / coll, exist_ok=True)
        with open(dump / coll / f"{doc}.json", "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    envs = tmp_path / "envs.json"
    envs.write_text(json.dumps(BRIDGE), encoding="utf-8")
    computer.main(["check", str(dump), "--envs", str(envs), "--now", app_model.stamp(T)])
    said = capsys.readouterr().out
    line = next(ln for ln in said.splitlines() if "list of computers" in ln)
    path = line.rsplit(" ", 1)[-1]
    entry = json.load(open(path, encoding="utf-8"))[0]
    assert (entry["collection"], entry["doc_id"]) == page_db.stored(*computer.ENVS_DOC)
    # The brief reads the page's meta for it, so the write is pinned to the version read.
    monkeypatch.setattr(place, "works_on", lambda: "computer")
    lines = brief._computer_lines({"date": "2026-11-11"})
    assert lines and "meta" in lines[0].split("--envs")[0], lines


def test_a_chat_that_routes_with_the_list_keeps_it_first(tmp_path, monkeypatch, capsys):
    """Whoever routes work for the computer with the person's list keeps it on the page, and
    is told to send that before the call it prints (jobs.md, the brief, the starter)."""
    _as(monkeypatch, "cloud", tmp_path)
    dump = tmp_path / "dump"
    os.makedirs(dump / "work")
    with open(dump / "work" / "@".join(("network", "read", "1.json")), "w", encoding="utf-8") as fh:
        json.dump(WORK[1], fh)
    envs = tmp_path / "envs.json"
    envs.write_text(json.dumps(BRIDGE), encoding="utf-8")
    computer.main(["route", str(dump), "--chat", "session_helper", "--envs", str(envs),
                   "--tools", "create_session", "--now", app_model.stamp(T)])
    got = json.loads(capsys.readouterr().out)
    entry = json.load(open(got["batches"][0], encoding="utf-8"))[0]
    assert entry["doc_id"] == computer.ENVS_DOC[1]
    for doc in ((".claude", "skills", "app", "jobs.md"), ("tools", "brief.py")):
        with open(os.path.join(ROOT, *doc), encoding="utf-8") as fh:
            text = " ".join(fh.read().replace('" "', "").split())
        assert "its batches first" in text, doc
    assert "its batches first" in " ".join(computer.starter_prompt("u", "c").split())
