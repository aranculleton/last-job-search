"""A ring from the page is answered in one command, and the chat takes few steps to do it.

Each model step of a chat re-reads its whole history, so a step is the cost. The chat that
answers the page took about fifteen before the person saw an answer: the update check, the
read, the check-in and its batch, the taps' claim, its batch, the taps applied, their batches,
`next` and its claim, each a step (2026-11-03). Now one read is followed by `app.py wake`,
which does all of that in code and prints the batches in the order they are sent, and the one
thing left to do. Claims and pinned writes are what they were: a tap that changes the copy is
applied only once its claim is accepted, and a chat of its own is started only once the
work's claim is.

Small work done here is claimed running at its first stage, with no progress pins after it; a
chat started for one big job takes no update check and is given its commands rather than told
to read the skill. The store here is the folder that keeps the real one's rules
(tests/test_one_chat_answers_the_page.py). Every person, employer, page and chat id is
invented.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app  # noqa: E402
import app_setup  # noqa: E402
import app_state  # noqa: E402
import page_db  # noqa: E402
import test_one_chat_answers_the_page as one  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import KESTREL, NOW  # noqa: E402

CHAT = "session_EXAMPLERING"
SEND = re.compile(r"^\d+\. (\S+\.json)   \((.*)\)$")


class Ring(one.Copy):
    """A person's copy with a small search in it, a published page, and its store."""

    def __init__(self, root):
        super().__init__(root)
        self.state = app_state.small(os.path.join(self.root, "small"))
        self.n = 0
        self.page()
        assert self.send(self.run("listen", self.dump(), "--chat", CHAT, "--listen"))

    def put(self, coll, doc_id, data, version=1):
        os.makedirs(os.path.join(self.db, coll), exist_ok=True)
        with open(os.path.join(self.db, coll, doc_id + ".json"), "w", encoding="utf-8") as fh:
            json.dump({"data": data, "version": version}, fh)

    def stored(self, coll, doc_id):
        p = os.path.join(self.db, coll, doc_id + ".json")
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)

    def act(self, action, item, value=None):
        model = json.loads(self.run("model", "--now", NOW))
        rows = [r for s in ("needs_you", "ready", "messages", "people", "settings")
                for r in model[s]] + model["jobs"]["rows"] + \
            [r for g in model["jobs"]["filtered"]["groups"] for r in g["items"]]
        rev = next(r["rev"] for r in rows if r["id"] == item)
        self.n += 1
        aid = f"act{self.n:02d}"
        doc = {"action": action, "item": item, "rev_seen": rev,
               "at": f"2026-10-25T17:{self.n:02d}:00Z", "tab": "t1"}
        if value is not None:
            doc["value"] = value
        self.put("actions", aid, doc)
        return aid

    def read(self, name):
        """One read of every collection a wake reads, as ArtifactData's out_dir saves it: the
        fields alone, with "~" spelled "@"."""
        out = os.path.join(self.root, name)
        os.makedirs(out)
        for coll in app.WAKE_READS:
            src = os.path.join(self.db, coll)
            if not os.path.isdir(src):
                continue
            os.makedirs(os.path.join(out, coll))
            for f in os.listdir(src):
                with open(os.path.join(src, f), encoding="utf-8") as fh:
                    doc = json.load(fh)
                with open(os.path.join(out, coll, f.replace("~", "@")), "w",
                          encoding="utf-8") as fh:
                    json.dump(doc["data"], fh)
        return out

    def wake(self, d, *args):
        return self.run("wake", d, "--chat", CHAT, "--kind", "cloud", "--on", "Opus 5.5",
                        "--now", NOW, *args)

    def tracker(self):
        with open(os.path.join(self.state, "job_search_tracker.csv"), encoding="utf-8") as fh:
            return fh.read()


@pytest.fixture
def ring(tmp_path):
    r = Ring(tmp_path)
    yield r
    sys.path.remove(r.root)


def sends(said):
    """[(batch file, why)] in the order printed."""
    return [m.groups() for m in map(SEND.match, said.splitlines()) if m]


def next_item(said):
    text = said[said.index("\nnext: ") + len("\nnext: "):]
    return json.JSONDecoder().raw_decode(text)[0]


def land(ring, said):
    import fake_db
    return [fake_db.apply(ring.db, path) for path, _ in sends(said)]


# ------------------------------------------------------------------ one read, one command

def parts(said):
    """What each batch holds, in the order they are sent: [[what, ...], ...]."""
    return [why.split(". Refused")[0].split("; ") for _, why in sends(said)]


CHECK_IN, TAPS, APPLIED, WORK = ("the check-in: this chat answers the page",
                                 "what the person did, claimed",
                                 "what the person did, applied, with its receipts",
                                 "the work below, claimed")


def test_a_tap_and_the_work_it_queues_are_answered_in_one_wake(ring):
    before = ring.tracker()
    aid = ring.act("job.draft", "r9-3", value={"answers": {"already_applied": "no"}})
    d = ring.read("wake1")
    said = ring.wake(d)
    # A tap that writes only to the page: the check-in, its claim and its receipt (with the
    # draft it queued) go as one batch, taken whole or not at all; the draft's claim follows,
    # since a batch writes a document once.
    assert parts(said) == [[CHECK_IN, TAPS, APPLIED], [WORK]], said
    assert "Refused: another chat took the page or holds something claimed here; read again " \
           "into a new folder and wake once more" in sends(said)[0][1]
    assert all(land(ring, said)), said
    assert ring.stored("receipts", aid)["data"]["result"] == "ok"
    # The draft the tap queued is claimed in the same wake, pinned to the version its own
    # creation left, and runs in a chat of its own, started only once the claim is accepted.
    item = next_item(said)
    work = ring.stored("work", item["work"])
    assert item["kind"] == "draft" and item["run"] == "child session"
    assert work["data"]["status"] == "claimed" and work["data"]["claimed_by"] == CHAT
    assert "only once the work's claim is accepted, make the create_session call" in said
    assert f"--work {item['work']}" in item["create_session"]["prompt"]
    assert ring.tracker() == before                  # a draft's tap writes nothing in the copy
    # Run again over the same folder (step 3 again): nothing more, and nothing to send.
    again = ring.wake(d)
    assert not sends(again) and "nothing else is waiting for this chat" in again


def test_a_tap_that_changes_the_copy_is_applied_only_once_its_claim_is_accepted(ring):
    aid = ring.act("ready.applied", KESTREL)
    ring.queue("talk~1", kind="talk")
    before = ring.tracker()
    d = ring.read("wake1")
    said = ring.wake(d)
    assert parts(said) == [[CHECK_IN, TAPS]], said
    assert "run this again with the same folder" in said and "next:" not in said
    assert ring.tracker() == before, "applied before its claim was accepted"
    assert all(land(ring, said))
    said = ring.wake(d)
    # Once the copy has changed, its receipts go on their own: a refusal after that would
    # leave them unsent.
    assert parts(said) == [[APPLIED], [WORK]], said
    assert all(land(ring, said)), said
    assert ring.tracker() != before
    assert ring.stored("receipts", aid)["data"]["result"] == "ok"
    # The talk is small work done here: its claim marks it running at its first stage, so
    # no progress pin follows it.
    item = next_item(said)
    assert item["work"] == "talk~1" and item["run"] == "here"
    talk = ring.stored("work", "talk~1")["data"]
    assert talk["status"] == "running" and talk["stage"] == 0 and talk["stage_at"] == NOW
    assert "no progress pin follows" in said


def test_a_tap_another_chat_holds_is_left_to_it_and_the_copy_is_untouched(ring):
    ring.act("ready.applied", KESTREL)
    before = ring.tracker()
    said = ring.wake(ring.read("wake1"))
    # Another chat claims the tap between this chat's read and its claim.
    doc = ring.stored("actions", "act01")
    ring.put("actions", "act01", dict(doc["data"], claimed_by="other-chat",
                                       claimed_until="2026-10-25T18:10:00Z"), version=2)
    assert land(ring, said) == [False]
    assert ring.tracker() == before and ring.stored("receipts", "act01") is None
    # The new read and wake leave it to that chat: a check-in, and nothing applied.
    again = ring.wake(ring.read("wake2"))
    assert parts(again) == [[CHECK_IN]] and all(land(ring, again))
    assert ring.tracker() == before and ring.stored("receipts", "act01") is None


def test_a_ring_with_nothing_waiting_only_checks_in_and_another_chat_writes_nothing(ring):
    said = ring.wake(ring.read("wake1"))
    assert parts(said) == [[CHECK_IN]]
    assert "nothing else is waiting for this chat. End the turn." in said
    assert all(land(ring, said))
    other = ring.run("wake", ring.read("wake2"), "--chat", "big-chat", "--now", NOW)
    assert not sends(other) and "does not answer the page: write nothing else" in other


def test_a_big_job_is_claimed_and_never_run_here(ring):
    ring.queue("search~1", kind="search")
    said = ring.wake(ring.read("wake1"))
    item = next_item(said)
    assert item["run"] == "child session" and item["heavy"] is True
    assert all(land(ring, said))
    assert ring.stored("work", "search~1")["data"]["status"] == "claimed"
    without = ring.run("next", ring.read("dump2"), "--chat", CHAT, "--kind", "cloud",
                       "--no-sessions", "--now", NOW)
    assert without == ""                                 # it is claimed: nobody else takes it


# ------------------------------------------------------------------ the day's update check

def _updated(ring, d, current):
    """The wake as the code an update brought in runs it: the update's own words saved."""
    ring.page(current=current)
    said = os.path.join(ring.root, "sync.txt")
    with open(said, "w", encoding="utf-8") as fh:
        fh.write("sync_app: updated to the newest version.\nClaude: the update changed the "
                 "person's page itself. Republish it:\n1. python3 tools/app.py page --out x\n")
    head = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()
    return ring.run("wake", d, "--chat", CHAT, "--now", NOW,
                    **{app.WAKE_UPDATED: head, app.WAKE_SAID: said})


def test_an_update_that_changes_the_page_stops_the_wake_with_its_own_steps(ring):
    d = ring.read("wake1")
    said = _updated(ring, d, current=False)
    assert said.startswith("wake: the day's update check took an update that changes the "
                           "page's own code: this wake stops here and has written nothing.")
    # Start's own words for the check, and what the check printed, word for word.
    assert app_setup.SYNC_DO + app_setup.SYNC_PAGE in said
    assert "Claude: the update changed the person's page itself. Republish it:" in said
    assert "wake once more" in said and not sends(said)
    # An update that left the page and this skill alone: what it printed, then the wake.
    said = _updated(ring, ring.read("wake2"), current=True)
    assert "this command ran it; what it printed is below." in said
    assert "sync_app: updated to the newest version." in said
    assert sends(said) and "this wake stops here" not in said


def test_an_update_that_changes_this_skill_stops_the_wake(monkeypatch):
    monkeypatch.setattr(app_setup, "page_record", lambda: {})
    monkeypatch.setattr(app, "_git", lambda *a: (1, "") if a[0] == "diff" else (0, "abc"))
    assert app.update_stops("abc") == ["skill"]
    monkeypatch.setattr(app, "_git", lambda *a: (0, ""))
    assert app.update_stops("abc") == []


def test_a_wake_takes_the_days_check_only_when_it_is_due(monkeypatch):
    import sync_app
    monkeypatch.setattr(sync_app, "stale", lambda: False)
    assert app.days_check("Opus 5.5", CHAT) == {"ran": False}


# ------------------------------------------------------------------ the claim keeps the dump

def test_a_tap_claimed_then_applied_from_one_read_lands(tmp_path):
    """The claim leaves a pasted profile's words on the page until they are kept (changed
    2026-11-03, engine audit 9: taken with the claim, a chat that stopped before applying
    lost them); the receipt's batch removes them, pinned to the version the claim leaves,
    never the one read before it (that second pinned removal had the whole batch refused)."""
    import test_an_interview_reads_as_one_screen_and_a_contact_says_what_is_owed as T
    from test_a_tick_on_the_page_is_applied_once import Search
    search = Search(str(tmp_path))
    T._waiting_note(search)
    msg = next(m for m in search.model()["messages"] if m["contact"] == T.PELL)
    aid = search.act("profile.pasted", msg["id"], value={"text": T.PROFILE}, rev=msg["rev"])
    search.run("apply", search.dump, "--chat", "cloud-1", "--now", NOW, "--claim")
    kept = page_db.load(search.dump)["actions"][aid]
    assert kept["version"] == 2 and kept["data"]["claimed_by"] == "cloud-1"
    assert kept["data"]["value"]["text"] == T.PROFILE        # the words, kept for the apply
    claim = [e for b in glob.glob(os.path.join(search.dump, "out", "claim*.json"))
             for e in json.load(open(b, encoding="utf-8"))]
    for e in claim:
        assert "__delete__" not in open(e["file_path"], encoding="utf-8").read(), e
    got = search.apply()
    assert got["ok"] == [aid]
    entries = [e for b in got["batches"] for e in json.load(open(b, encoding="utf-8"))]
    gone = [e for e in entries if e["collection"] == "actions"]
    assert [(e["op"], e["doc_id"], e.get("if_version")) for e in gone] == [("update", aid, 2)]
    assert json.load(open(gone[0]["file_path"], encoding="utf-8"))["value"] == {
        "text": {"__delete__": True}}


def test_keep_landed_is_the_dump_as_the_store_will_hold_it(tmp_path):
    d = tmp_path / "d"
    (d / "work").mkdir(parents=True)
    (d / "work" / ("talk" + "@1.json")).write_text(json.dumps({"kind": "talk", "status": "queued",
                                                         "note": "x", "_v": 3}), encoding="utf-8")
    w = page_db.Writes(str(tmp_path / "out"))
    w.add("update", "work", "talk~1", {"status": "running", "note": {"__delete__": True}},
          if_version=3)
    w.add("set", "holds", "emp~fernhill", {"work": "talk~1"})
    page_db.keep_landed(str(d), w.save("b"))
    db = page_db.load(str(d))
    assert db["work"]["talk~1"] == {"data": {"kind": "talk", "status": "running"}, "version": 4}
    assert db["locks"]["emp~fernhill"]["version"] == 1


# ------------------------------------------------------------------ a chat for one big job

def test_a_chat_for_one_job_takes_no_update_and_is_given_its_commands(monkeypatch):
    import learned
    import sync_app
    monkeypatch.setattr(app_setup, "origin", lambda: ("example-owner", "example-copy"))
    monkeypatch.setattr(app_setup, "page_record", lambda: {"url": one.PAGE})
    chosen = {"work": "search~1", "kind": "search", "title": "Analyst roles", "heavy": True,
              "stages": page_db.progress("search")["stages"]}
    prompt = app.where_it_runs(chosen, "listener-1", "cloud")["create_session"]["prompt"]
    flat = " ".join(prompt.split())
    # Its commands, from the skill's own table, and no reading the skill for them.
    assert "run_round.py --show <args.size>" in flat and "Read only those parts" not in flat
    assert app.work_row("search") in flat and app.work_row("draft") == app.work_row(
        "resume_for_contact")
    # One read up front, with what step 5 needs; a search says where it is every ten minutes.
    assert "work, holds, screen, meta and addr" in flat and ("$D/work/search" + "@1.json") in flat
    assert "every ten minutes or so (its lease is thirty)" in flat
    assert "five minutes" not in flat
    # The hook takes no update for it: the chat that answers the page took the day's.
    monkeypatch.setattr(learned, "_path", lambda: "/tmp/not-the-example/learned.json")
    monkeypatch.setattr(sync_app, "stale", lambda: True)
    assert learned._update_due({"hook_event_name": "UserPromptSubmit", "prompt": prompt}) == ""
    assert learned._update_due({"hook_event_name": "UserPromptSubmit", "prompt": "hello"})


def test_start_for_a_job_has_no_update_check_and_no_view(ring, monkeypatch):
    env = ring.env()
    for k in set(os.environ) - set(env):
        monkeypatch.delenv(k)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(app_setup, "_sync_stale", lambda: True)
    _, lines = app_setup.start(on="test", tools="none", work="search~1")
    said = "\n".join(lines)
    assert "sync_app.py" not in said and "app.py view" not in said
    _, lines = app_setup.start(on="test", tools="none")
    assert "sync_app.py --pull" in "\n".join(lines)


def test_start_leaves_the_pages_data_alone_when_it_is_already_current(ring):
    said = ring.run("start", "--on", "test", "--tools", "none", "--chat", CHAT)
    assert "python3 tools/app.py view" in said
    model = json.loads(ring.run("model"))                # today's, as start builds it
    d = os.path.join(ring.root, "meta-read")
    os.makedirs(os.path.join(d, "meta"))
    with open(os.path.join(d, "meta", "now.json"), "w", encoding="utf-8") as fh:
        json.dump({"rev": model["rev"], "_v": 4}, fh)
    said = ring.run("start", "--on", "test", "--tools", "none", "--chat", CHAT, "--dump", d)
    assert "python3 tools/app.py view" not in said
    with open(os.path.join(d, "meta", "now.json"), "w", encoding="utf-8") as fh:
        json.dump({"rev": "an-older-rev", "_v": 4}, fh)
    said = ring.run("start", "--on", "test", "--tools", "none", "--chat", CHAT, "--dump", d)
    assert "python3 tools/app.py view" in said


# ------------------------------------------------------------------ the skill says so

def test_the_skill_reads_once_and_wakes_once():
    with open(os.path.join(ROOT, ".claude", "skills", "app", "SKILL.md"), encoding="utf-8") as fh:
        skill = " ".join(fh.read().split())
    one_to_three = skill[skill.index("## 1. Read, in one go"):skill.index("## 4.")]
    assert "python3 tools/app.py wake \"$D\" --chat <your chat id>" in one_to_three
    for coll in app.WAKE_READS:
        assert f"`{coll}`" in one_to_three, coll
    assert "already loaded on a wake" in one_to_three
    progress = skill[skill.index("**Progress costs nothing extra**"):]
    assert "big jobs only" in progress[:400] and "every ten minutes" in progress[:1200]
