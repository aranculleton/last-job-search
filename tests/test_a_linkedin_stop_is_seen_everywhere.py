"""A LinkedIn stop on the person's computer (a check, an error page, a sign-out out of turn) is
seen everywhere: the cloud, the page and the next page load, from one record the computer
writes and everyone reads.

From the builder audit of 2026-11-10 (CC-9 to CC-12, CC-24, CC-27): the reading ledger is a
cache on each machine, so the cloud read its own empty one, never showed the pause, and queued
a new read for the computer the same day; a chat on the computer that met a sign-out waited
and asked in a chat nobody watched; a 429 page went unseen and `reading.py page` recorded
nothing; and a signed-in profile whose About said "sign in to view" was judged signed out.
Invented people and computers only.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_model  # noqa: E402
import computer  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW  # noqa: E402
from test_the_computer_side_just_works import BRIDGE  # noqa: E402

T = app_model.parse_time(NOW)


def _beat_db(**facts) -> dict:
    beat = computer.beat_fields("Studio Laptop", T - dt.timedelta(minutes=5), browser="shown",
                                linkedin="in", version="4.14.0", task=False, **facts)
    return {"chats": {computer.beat_id("Studio Laptop"): {"data": beat, "version": 2}},
            "work": {}}


# ------------------------------------------------------------------ CC-9


def test_a_stop_on_the_computer_is_seen_by_the_cloud_and_the_page(tmp_path, monkeypatch):
    import person
    import reading
    monkeypatch.setenv(person.STATE_ENV, str(tmp_path / "state"))
    # Measured on the computer, from its own ledger: the heartbeat carries it.
    assert computer.stop_here() is None
    reading.stop("LinkedIn showed a security check")
    got = computer.stop_here()
    assert got and got["kind"] == "check" and "security check" in got["why"]
    today = computer._day(T)
    stop = {"on": today, "kind": "check", "why": "LinkedIn showed a security check"}
    db = _beat_db(stop=stop)
    st = computer.state(db, T, envs=BRIDGE)
    assert st["state"] == "paused" and st["stopped"]["on"] == today
    # The cloud, with an empty ledger of its own, shows the pause and queues no read for the
    # computer while it holds.
    monkeypatch.setenv(person.STATE_ENV, str(tmp_path / "cloud"))
    monkeypatch.setattr(reading, "reads_now", lambda: "browser")
    model, _ = app_model.build(T.date(), T, only=("linkedin", "where"), computer=st)
    assert model["linkedin"]["reading"]["paused"] is True
    assert model["linkedin"]["reading"]["setting"] == "browser"
    assert model["where"]["reading"]["state"] == "paused"
    import app
    want = {"person": {"computer": True},
            "linkedin": {"reading": dict(model["linkedin"]["reading"], setting="browser",
                                         queue=[{"contact": "c-ana-1", "first_name": "Ana"}])}}
    assert app.computer_reads(want, {}, T) is None
    # The next day it is over by itself, and so is a stop said only by `--read stopped`.
    assert computer.stopped_today(db["chats"][computer.beat_id("Studio Laptop")]["data"],
                                  T + dt.timedelta(days=1)) is None
    old = _beat_db(read="stopped")
    assert computer.state(old, T, envs=BRIDGE)["state"] == "paused"
    assert computer.state(old, T + dt.timedelta(days=1), envs=BRIDGE)["state"] != "paused"
    # No stop: nothing paused, and the row says ready.
    assert computer.state(_beat_db(), T, envs=BRIDGE)["stopped"] is None


def test_the_heartbeat_command_measures_the_stop(tmp_path, monkeypatch):
    """`computer.py beat` reads the computer's ledger itself: the chat never types it."""
    import json
    import subprocess
    state = tmp_path / "state"
    env = dict(os.environ, LJS_STATE=str(state))
    dump = tmp_path / "dump"
    (dump / "beats").mkdir(parents=True)
    run = [sys.executable, "-c",
           "import sys; sys.path[:0] = [%r, %r]; import reading; "
           "reading.stop('HTTP ERROR 999')" % (os.path.join(ROOT, "tools"),
                                                 os.path.join(ROOT, "tools", "network"))]
    assert subprocess.run(run, env=env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace").returncode == 0
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "computer.py"), "beat",
                        str(dump), "--name", "Studio Laptop", "--browser", "shown",
                        "--linkedin", "in"], env=env, capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, r.stderr
    batch = json.loads(r.stdout)["batches"][0]
    entry = json.load(open(batch, encoding="utf-8"))[0]
    fields = entry.get("data")
    if fields is None:
        with open(entry["file_path"], encoding="utf-8") as fh:
            fields = json.load(fh)
    assert fields["stop"] and fields["stop"]["kind"] == "http_999", fields


# ------------------------------------------------------------------ CC-12


def _page(text: str, env: dict):
    import subprocess
    return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "network", "reading.py"),
                           "page", "-"], input=text, env=env, capture_output=True, text=True,
                          encoding="utf-8")


def test_what_reading_page_sees_is_recorded_and_stops_the_next_load(tmp_path, monkeypatch):
    """Chrome's "HTTP ERROR 429" page was not seen as a stop, and `reading.py page` only
    classified: a sign-in wall or a check seen there recorded nothing, so the next load went
    ahead and nothing reached the page."""
    import reading
    assert reading.page_kind("This page isn't working\nwww.linkedin.com\nHTTP ERROR 429")[0] == \
        "check"
    env = dict(os.environ, LJS_STATE=str(tmp_path / "state"))
    r = _page("This page isn’t working\nIf the problem continues, contact the site owner.\n"
              "HTTP ERROR 429\nReload", env)
    assert r.returncode == reading.EXIT["check"], r.stdout + r.stderr
    gate = subprocess_gate(env)
    assert gate.returncode != 0 and "stopped for today" in gate.stdout, gate.stdout
    # The sign-in wall after a sign-in today: a sign-out, recorded and classified.
    env2 = dict(os.environ, LJS_STATE=str(tmp_path / "state2"))
    import subprocess
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "network", "reading.py"),
                    "signin", "--done"], env=env2, capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
    wall = _page("Sign Up | LinkedIn\nauthwall\nJoin LinkedIn\nSign in\nJoin now", env2)
    assert wall.returncode in (reading.EXIT["signin"], reading.EXIT["check"]), wall.stdout
    assert "sign-in page" in wall.stdout, wall.stdout
    # Never signed in today: a wait for the person, as before, and nothing stops.
    env3 = dict(os.environ, LJS_STATE=str(tmp_path / "state3"))
    first = _page("Sign Up | LinkedIn\nauthwall\nJoin LinkedIn\nSign in\nJoin now", env3)
    assert first.returncode == reading.EXIT["signin"] and "stopped" not in first.stdout
    assert subprocess_gate(env3).returncode == 0


def subprocess_gate(env: dict):
    import subprocess
    return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "network", "reading.py"),
                           "gate"], env=env, capture_output=True, text=True, encoding="utf-8")


# ------------------------------------------------------------------ CC-27


SIGNED_IN_ABOUT = "\n".join([
    "Home", "My Network", "Jobs", "Messaging", "Notifications", "Me",
    "Ana Kestrel", "· 2nd", "Head of Pricing at Fernway Insurance", "· Contact info",
    "Connect", "Message", "More",
    "About",
    "I write about pricing. Sign in to view the slides from my talk on our team page, or join "
    "now to view the recording.",
    "Experience", "Head of Pricing", "Fernway Insurance"])


def test_a_signed_in_profile_that_says_sign_in_to_view_in_its_about_is_signed_in():
    """Its signed-out phrases were read over every section's text before the signed-in
    markers, so a signed-in profile whose About or posts said "sign in to view" was judged
    signed out, and a needless sign-in was asked for."""
    import json
    import reading
    assert reading.signed_in(SIGNED_IN_ABOUT) is True
    extract = json.dumps({"url": "https://www.linkedin.com/in/example-ana-kestrel",
                          "nav": "Home\nMy Network\nJobs\nMessaging\nNotifications\nMe",
                          "top": "Ana Kestrel\n· 2nd\nHead of Pricing at Fernway Insurance",
                          "sections": [{"heading": "About", "text":
                                        "About\nSign in to view my slides, or join now to view "
                                        "the talk."}]})
    assert reading.signed_in(extract) is True
    assert reading.page_kind(SIGNED_IN_ABOUT)[0] == "profile"
    # A post that says "join now" in passing is no sign-in page either.
    post = "Ana Kestrel\nPosts\nOur meetup is open: join now and bring a friend.\nMore"
    assert reading.page_kind(post)[0] != "signin"
    # Signed out still reads as signed out, by its address, its bar and its card.
    guest = json.loads(extract)
    guest.update(nav="LinkedIn\nArticles\nPeople\nJobs\nJoin now\nSign in",
                 top="Ana Kestrel\nHead of Pricing at Fernway Insurance\n"
                     "Sign in to view Ana's full profile")
    assert reading.signed_in(json.dumps(guest)) is False
    assert reading.signed_in("Ana Kestrel\nSign in to view Ana's full profile\nJoin now\n"
                             "Sign in\n") is False
    assert reading.page_kind("Sign in\nEmail or phone\nPassword\nNew to LinkedIn? Join now")[0] \
        == "signin"


# ------------------------------------------------------------------ CC-10


def test_a_chat_the_app_started_on_the_computer_never_waits_on_its_own_chat(monkeypatch):
    """A sign-out mid-run told the chat to tell the person to "say done", look every 20
    seconds and ask again after five minutes, in a chat nobody watches, while its prompt said
    never to ask there: its lease ran out and a second chat started on the same job."""
    import app_listen
    import app_setup
    import reading
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "computer")
    monkeypatch.setattr(app_setup, "current_claim", lambda: {"work": "network~read~1"})
    steps = "\n".join(reading.signin_steps())
    assert "--signin linkedin" in steps and "--work network~read~1" in steps
    # Each look after a wait opens the feed afresh (computer.py signin-seen), never an address
    # read before the wait (decided 2026-11-12, the maintainer's Mac).
    assert "computer.py signin-wait" in steps and "signin-seen" in steps
    assert "--url <that address>" not in steps
    assert "say done" not in steps and "ask once more" not in steps
    said = reading._job_signin_said("network~read~1", "the session expired")
    assert "nobody reads it" in said and "--signin linkedin" in said
    # A chat the person opened on the computer, or one with no job, asks them as before.
    monkeypatch.setattr(app_setup, "current_claim", lambda: {})
    assert "ask once more" in "\n".join(reading.signin_steps())
    monkeypatch.setattr(app_setup, "current_claim", lambda: {"work": "network~read~1"})
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "cloud")
    assert reading.app_job_here() == ""


# ------------------------------------------------------------------ CC-24


def test_signed_out_leaves_the_computer_row_once_the_page_sees_a_sign_in(monkeypatch):
    """The computer's row said signed out until the next chat ran there, after the person had
    signed in from the page."""
    import place
    db = _beat_db()
    db["chats"][computer.beat_id("Studio Laptop")]["data"]["linkedin"] = "out"
    assert computer.state(db, T, envs=BRIDGE)["state"] == "signed_out"
    later = app_model.stamp(T - dt.timedelta(minutes=1))
    # Softened, never cleared: the page's reader may be another browser (the independent
    # review, 2026-11-11). No card, and a word that is not a warning.
    unsure = computer.state(db, T, envs=BRIDGE, page_signin=later)
    assert unsure["state"] == "signin_unsure" and "next time" in unsure["line"]
    assert unsure["action"] is None and not unsure["card"]
    earlier = app_model.stamp(T - dt.timedelta(hours=2))
    assert computer.state(db, T, envs=BRIDGE, page_signin=earlier)["state"] == "signed_out"
    # What the page draws reads the page's own record of the sign-in.
    monkeypatch.setattr(place, "page_reads_record", lambda: {"ok": True, "checked_at": later})
    assert computer.page_signed_in_at() == later
    monkeypatch.setattr(computer, "_works_on", lambda: "computer")
    assert computer.seen(db, T)["state"] == "signin_unsure"
    monkeypatch.setattr(place, "page_reads_record", lambda: {"ok": False, "checked_at": later})
    assert computer.seen(db, T)["state"] == "signed_out"


# ------------------------------------------------------------------ CC-20


def test_one_owner_for_each_look_at_linkedins_sign_in():
    """The networking skill said the page looks once a day and no chat opens LinkedIn;
    COMPUTER.md said the chat on the computer reads a LinkedIn page for its heartbeat. One
    table names the owner of each case, and both documents send the reader to it."""
    import re
    with open(os.path.join(ROOT, "COMPUTER.md"), encoding="utf-8") as fh:
        doc = fh.read()
    head = "### Who looks at LinkedIn's sign-in (for Claude)"
    assert head in doc
    table = doc[doc.index(head):].split("\n### ", 1)[0]
    rows = [r for r in table.splitlines() if r.startswith("| ") and "---" not in r][1:]
    owners = {cmd: row for row in rows
              for cmd in ("linkedin-check", "beat --linkedin", "signed-in") if cmd in row}
    assert set(owners) == {"linkedin-check", "beat --linkedin", "signed-in"}
    assert "the page" in owners["linkedin-check"]
    assert "opens nothing extra" in owners["beat --linkedin"]
    assert "signin-wait" in owners["signed-in"]
    assert not re.search(r"reads one LinkedIn page", doc)
    with open(os.path.join(ROOT, ".claude", "skills", "networking", "SKILL.md"),
              encoding="utf-8") as fh:
        skill = fh.read()
    assert "COMPUTER.md, \"Who looks at LinkedIn's sign-in\"" in skill


# ------------------------------------------------------------------ CC-11


def test_a_sign_in_that_keeps_failing_stops_answering_itself(tmp_path):
    """The page answers a sign-in question by itself once its own reader sees LinkedIn signed
    in, which may not be the browser on the computer (a phone, another window), and "I've
    signed in" can be tapped without signing in. Each answer sent the job back, a new chat met
    the sign-in page again, and nothing counted the rounds."""
    import json
    import page_db
    from test_a_tick_on_the_page_is_applied_once import _db, _w
    q = "LinkedIn is signed out in Claude's browser."
    item = dict(_w("network", "Harbourline Bank", to="computer"), status="running",
                claimed_by="mac-1", claimed_as="computer", claimed_at=NOW)
    seen = []
    for n in (1, 2, 3):
        db = _db(("network~read~1", item))
        got = page_db.finish(db, "network~read~1", T, str(tmp_path / f"f{n}"), question=q,
                             chat_kind="computer", chat="mac-1", signin="linkedin")
        entry = json.load(open(got["batches"][0], encoding="utf-8"))[0]
        with open(entry["file_path"], encoding="utf-8") as fh:
            fields = json.load(fh)
        seen.append(fields)
        # Answered on the page: back in the queue, and claimed again by a new chat.
        item = dict(item, **{k: v for k, v in fields.items()
                             if k not in ("status", "claimed_by")},
                    status="running", claimed_by="mac-1")
    assert [f["signin_stops"] for f in seen] == [1, 2, 3]
    assert seen[0]["needs"]["signin"] == "linkedin" and seen[1]["needs"]["signin"] == "linkedin"
    # The third time: no sign-in the page answers by itself, and words that send them to the
    # computer.
    third = seen[2]
    assert "signin" not in third["needs"], third["needs"]
    assert "on your computer" in third["note"] and "signed out" not in third["note"].lower()
    import computer
    assert computer.waits_on_signin(dict(item, **dict(third, status="needs_you"))) is False


# ------------------------------------------------------------------ CC-13


def test_after_a_gap_longer_than_its_claim_the_next_person_waits_for_a_check(
        tmp_path, monkeypatch, capsys):
    """A Mac that slept past its claim's lease woke and went on reading until its next pin was
    refused, while another chat had taken the work: every profile load is automated activity on
    the person's LinkedIn account. `next` checks the claim only after such a gap, counted from
    the claim or its last pin (a chat reading on without pinning lapses too), on the work the
    chat holds now, and never for a chat whose work is over (the independent review,
    2026-11-11)."""
    import argparse
    import json
    import app_listen
    import app_setup
    import page_db
    import person
    import reading
    from test_a_tick_on_the_page_is_applied_once import _w
    monkeypatch.setenv(person.STATE_ENV, str(tmp_path / "state"))
    monkeypatch.setattr(app_setup, "_local_file", lambda name: str(tmp_path / name))
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "computer")
    monkeypatch.setattr(reading, "gate_state", lambda *a, **k: {"kind": "go"})
    monkeypatch.setattr(reading, "next_up", lambda contacts=None: {
        "contact_id": "c_ana", "name": "Ana Kestrel", "company": "Harbourline Bank",
        "linkedin_url": "https://www.linkedin.com/in/example-ana"})
    clock = [1_000_000.0]
    monkeypatch.setattr(reading, "_now_ts", lambda: clock[0])

    def nxt(dump=""):
        rc = reading._cli_next(argparse.Namespace(wait=False, timeout=1, mode="card",
                                                  dump=dump))
        return rc, capsys.readouterr().out

    def dump_with(wid="network~read~1", **item):
        d = tmp_path / f"d{len(list(tmp_path.glob('d*')))}"
        (d / "work").mkdir(parents=True)
        with open(d / "work" / (wid.replace("~", "@") + ".json"), "w", encoding="utf-8") as fh:
            json.dump({"data": dict(_w("network", "Harbourline Bank", to="computer"), **item),
                       "version": 7}, fh)
        return str(d)

    def stamp(ts):
        return app_model.stamp(dt.datetime.fromtimestamp(ts, dt.timezone.utc))
    app_setup.record_claim("network~read~1", "mac-job-7", now_ts=clock[0])
    assert reading.app_job_here() == "network~read~1"
    # No gap since the claim: no check, the next person at once.
    rc, out = nxt()
    assert rc == reading.EXIT["ok"] and out.startswith("next: Ana Kestrel"), out
    # Reading on without a pin for longer than the claim lasts: checked, though `next` ran
    # every few minutes all along.
    for _ in range(6):
        clock[0] += 5 * 60
        rc, out = nxt()
    assert rc == reading.EXIT["claim"] and "next:" not in out and "collection work" in out, out
    # A pin renews it: no check.
    app_setup.renew_claim("network~read~1", clock[0])
    clock[0] += 60
    assert nxt()[0] == reading.EXIT["ok"]
    # Away past the lease, and another chat took it meanwhile: stopped, in plain words.
    clock[0] += page_db.LEASE_S + 60
    taken = dump_with(status="running", claimed_by="mac-job-8", claimed_as="computer",
                      claimed_at=stamp(clock[0]), lease_until=stamp(clock[0] + 600))
    rc, out = nxt(taken)
    assert rc == reading.EXIT["claim"] and "next:" not in out and "another chat" in out, out
    # Still this chat's and live: carry on, and no check for the next person.
    ours = dump_with(status="running", claimed_by="mac-job-7", claimed_as="computer",
                     claimed_at=stamp(clock[0]), lease_until=stamp(clock[0] + 600))
    rc, out = nxt(ours)
    assert rc == reading.EXIT["ok"] and out.startswith("next:"), out
    clock[0] += 60
    assert nxt()[0] == reading.EXIT["ok"]
    # Ended on the page while it was away: stopped too.
    clock[0] += page_db.LEASE_S + 60
    ended = dump_with(status="stopped", claimed_by="mac-job-7", stop_asked=True)
    rc, out = nxt(ended)
    assert rc == reading.EXIT["claim"] and "ended" in out and "next:" not in out
    # The first job done, a second taken by the same chat: gated on the second, never the first.
    app_setup.end_claim("network~read~1")
    app_setup.record_claim("network~read~2", "mac-job-7", now_ts=clock[0])
    assert reading.app_job_here() == "network~read~2"
    clock[0] += page_db.LEASE_S + 60
    second = dump_with("network~read~2", status="running", claimed_by="mac-job-7",
                       claimed_as="computer", claimed_at=stamp(clock[0]),
                       lease_until=stamp(clock[0] + 600))
    rc, out = nxt(second)
    assert rc == reading.EXIT["ok"] and out.startswith("next:"), out
    # All its work done: the chat holds nothing, nothing is gated, and days later its reads
    # (a person typing into it) go ahead, and a sign-in is asked in the chat again.
    app_setup.end_claim("network~read~2")
    assert reading.app_job_here() == ""
    clock[0] += 3 * 86400
    assert nxt()[0] == reading.EXIT["ok"]
    assert "ask once more" in "\n".join(reading.signin_steps())


# ------------------------------------------------------------------ review 15 (CC-3)


def test_every_sign_in_seen_sends_the_parked_job_back(tmp_path, monkeypatch, capsys):
    """Only signin-wait --url printed computer.py signed-in; a sign-in seen by signin --page,
    --done or --url said "carry on" and left this chat's job parked on the page."""
    import io
    import app_listen
    import app_setup
    import person
    import reading
    monkeypatch.setenv(person.STATE_ENV, str(tmp_path / "state"))
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "computer")
    monkeypatch.setattr(app_setup, "current_claim", lambda: {"work": "network~read~1"})
    page = "Home\nMy Network\nJobs\nMessaging\nNotifications\nMe\nAna Kestrel\n· 2nd\nMore\n"
    for argv, stdin in ((["signin", "--done"], ""),
                        (["signin", "--url", "https://www.linkedin.com/feed/"], ""),
                        (["signin", "--page", "-"], page)):
        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
        assert reading.main(argv) == reading.EXIT["ok"], argv
        out = capsys.readouterr().out
        assert "computer.py signed-in \"$D\" --work network~read~1" in out, (argv, out)
    # A chat holding no job here is told only to carry on.
    monkeypatch.setattr(app_setup, "current_claim", lambda: {})
    assert reading.main(["signin", "--done"]) == reading.EXIT["ok"]
    assert "computer.py signed-in" not in capsys.readouterr().out


# ------------------------------------------------------------------ review 10 (CC-12)


def test_an_error_number_in_someones_about_is_no_stop():
    """`error 429` was looked for over the first 120 lines, so an About that said "HTTP error
    429" read as LinkedIn's refusal, and `page` stopped the whole day's reads."""
    import reading
    about = "\n".join(["Home", "My Network", "Messaging", "Notifications", "Me",
                       "Ana Kestrel", "· 2nd", "Site reliability lead", "· Contact info",
                       "About", "I fix the HTTP error 429 pages nobody else wants to.",
                       "Experience", "Reliability lead", "Harbourline Bank"])
    assert reading.page_kind(about)[0] == "profile"
    for page in ("This page isn't working\nHTTP ERROR 429\nReload",
                 "This page isn’t working\nwww.linkedin.com\nHTTP ERROR 999"):
        assert reading.page_kind(page)[0] == "check", page


# ------------------------------------------------------------------ review 12


def test_a_stop_holds_to_the_end_of_the_computers_own_day(tmp_path, monkeypatch):
    """The stop was dated on the computer's clock and compared with the person's day: in
    another zone a stop made in the computer's evening was over in the cloud at once, or held
    a day too long."""
    import person
    import reading
    monkeypatch.setenv(person.STATE_ENV, str(tmp_path / "state"))
    reading.stop("LinkedIn showed a security check")
    got = computer.stop_here()
    end = dt.datetime.combine(dt.date.fromisoformat(got["on"]) + dt.timedelta(days=1),
                              dt.time(0)).astimezone()
    assert got["until"] == app_model.stamp(end)
    # A computer ten hours behind, stopped at 20:00 its time: still its day at 06:00 UTC,
    # though the person's day (UTC) has moved on; over once its own day ends.
    stop = {"on": "2026-10-25", "until": "2026-10-26T10:00:00Z", "kind": "check", "why": "x"}
    beat = {"stop": stop}
    at = dt.datetime(2026, 10, 26, 6, 0, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(computer, "_day", lambda t: t.astimezone(dt.timezone.utc).date().isoformat())
    assert computer.stopped_today(beat, at) is not None
    assert computer.stopped_today(beat, at + dt.timedelta(hours=5)) is None
