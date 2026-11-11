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
# A path may hold spaces: the tests' own folder does under a user named "Zoë Quillfeather"
# (the computer check on Windows, 2026-11-04). Three spaces end it.
SEND = re.compile(r"^\d+\. (.+?\.json)   \((.*)\)$")


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
    refused = sends(said)[0][1]
    assert "Refused: another chat took the page or holds something claimed here" in refused
    assert "read again into a new folder and wake once more" in refused
    # A record stamped wrong is put right by the version the refusal names, never bounced on
    # (the maintainer, 4 November).
    assert f"python3 tools/app.py version \"{d}\" <collection>/<doc id> <that version>" in refused
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


def test_a_chat_refused_a_new_chat_for_nesting_runs_big_jobs_as_background_agents(ring):
    """At the eighth helper in a chain the platform refused it a new chat (2026-11-05): the
    job's create_session said so, with no way on. Its line now says what to do, and once
    `app.py nested` has kept it, a big job runs as a background agent instead."""
    ring.act("job.draft", "r9-3", value={"answers": {"already_applied": "no"}})
    said = ring.wake(ring.read("wake1"))
    assert "python3 tools/app.py nested" in said and "background agents" in said
    assert next_item(said)["run"] == "child session"
    assert all(land(ring, said)), said
    ring.queue("draft~second", kind="draft")
    assert "keeps answering the page" in ring.run("nested", "--chat", CHAT)
    said = ring.wake(ring.read("wake2"))
    item = next_item(said)
    assert item["work"] == "draft~second" and item["run"] == "background agent", said
    assert "create_session" not in item


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


def test_two_not_this_person_taps_get_their_receipts_in_the_pass_that_applies_them(ring):
    """Two "Not this person" taps were claimed again on every wake, their records moving from
    version 1 to 2 to 3 before any receipt landed, and a later wake said "2 applied before"
    (the maintainer's copy, 2026-11-05): a wake that stopped after its claim never applied
    them, and one whose receipts never landed claimed them again. A tap this chat holds is
    applied in the next pass with its receipt, and one applied already is only receipted:
    neither is claimed twice."""
    taps = [ring.act("person.stop", who, value={"why": "not the right person", "scope": "person"})
            for who in ("kestrel_mutual_ansgar", "fernhill_freight_halloway")]
    said = ring.wake(ring.read("wake1"))
    assert parts(said) == [[CHECK_IN, TAPS]], said
    assert all(land(ring, said)), said              # claimed, and that chat stopped there
    # The next ring, from a new read: applied with their receipts, never claimed again.
    said = ring.wake(ring.read("wake2"))
    assert TAPS not in [w for p in parts(said) for w in p], said
    assert APPLIED in [w for p in parts(said) for w in p], said
    assert all(land(ring, said)), said
    for aid in taps:
        assert ring.stored("receipts", aid)["data"]["result"] == "ok", (aid, said)
        assert ring.stored("actions", aid)["version"] == 2
    again = ring.wake(ring.read("wake3"))
    assert not [p for p in parts(again) if TAPS in p or APPLIED in p], again


def _sent_rows(ring, cid):
    import csv
    with open(os.path.join(ring.state, "network_threads.csv"), encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r["contact_id"] == cid
                and r["direction"] in ("out", "outbound")]


@pytest.mark.parametrize("second", ["same folder", "new read"])
def test_i_sent_it_is_claimed_and_applied_by_wake(ring, second):
    """"I sent it" taps were applied only by running app.py apply by hand, never by `wake`
    (the maintainer's copy, 2026-11-05). The tap changes the copy, so the first wake claims it
    and the next applies it, whether that is the same folder again (as it says) or a new read
    on the next ring: logged once, with its receipt."""
    model = json.loads(ring.run("model", "--now", NOW))
    msg = next(m for m in model["messages"] if m["contact"] == "kestrel_mutual_ansgar")
    before = len(_sent_rows(ring, "kestrel_mutual_ansgar"))
    aid = ring.act("msg.sent", msg["id"])
    d = ring.read("wake1")
    said = ring.wake(d)
    assert parts(said) == [[CHECK_IN, TAPS]], said
    assert all(land(ring, said)), said
    said = ring.wake(d if second == "same folder" else ring.read("wake2"))
    assert APPLIED in [w for p in parts(said) for w in p], said
    assert TAPS not in [w for p in parts(said) for w in p], said
    assert all(land(ring, said)), said
    assert ring.stored("receipts", aid)["data"]["result"] == "ok", ring.stored("receipts", aid)
    assert len(_sent_rows(ring, "kestrel_mutual_ansgar")) == before + 1
    again = ring.wake(ring.read("wake3"))
    assert not [p for p in parts(again) if TAPS in p or APPLIED in p], again
    assert len(_sent_rows(ring, "kestrel_mutual_ansgar")) == before + 1


def test_a_tap_the_helper_before_claimed_is_taken_by_the_one_it_handed_to(ring):
    """The page handed to a fresh helper, the old one put away at the takeover: an "I sent
    it" it had claimed was held out of every wake until its claim ran out, with nothing to
    ring again, and only app.py apply by hand later took it (the maintainer's copy,
    2026-11-05). The chat it was handed to claims it and applies it; a claim by any other chat
    is still left to it."""
    model = json.loads(ring.run("model", "--now", NOW))
    msg = next(m for m in model["messages"] if m["contact"] == "kestrel_mutual_ansgar")
    aid = ring.act("msg.sent", msg["id"])
    doc = ring.stored("actions", aid)
    ring.put("actions", aid, dict(doc["data"], claimed_by="session_EXAMPLEOLD",
                                  claimed_until="2026-10-25T18:08:00Z", _v=2), version=2)
    listen = ring.stored("meta", "listen")
    ring.put("meta", "listen", dict(listen["data"], took_from="session_EXAMPLEOLD",
                                    handed_by="session_EXAMPLEOLD", _v=listen["version"] + 1),
             version=listen["version"] + 1)
    d = ring.read("wake1")
    said = ring.wake(d)
    assert parts(said)[0] == [CHECK_IN, TAPS], said
    assert all(land(ring, said)), said
    said = ring.wake(d)
    assert all(land(ring, said)), said
    assert ring.stored("receipts", aid)["data"]["result"] == "ok"
    assert len(_sent_rows(ring, "kestrel_mutual_ansgar")) == 1
    # Not handed over by it: its claim stands.
    listen = ring.stored("meta", "listen")
    ring.put("meta", "listen", dict(listen["data"], handed_by=None, _v=listen["version"] + 1),
             version=listen["version"] + 1)
    other = ring.act("person.stop", "fernhill_freight_halloway",
                     value={"why": "not the right person", "scope": "person"})
    doc = ring.stored("actions", other)
    ring.put("actions", other, dict(doc["data"], claimed_by="session_EXAMPLEOLD",
                                    claimed_until="2026-10-25T18:08:00Z", _v=2), version=2)
    said = ring.wake(ring.read("wake2"))
    assert not [p for p in parts(said) if TAPS in p or APPLIED in p], said


def test_a_tap_applied_whose_receipt_never_landed_is_receipted_not_claimed_again(ring):
    aid = ring.act("person.stop", "kestrel_mutual_ansgar",
                   value={"why": "not the right person", "scope": "person"})
    d = ring.read("wake1")
    assert all(land(ring, ring.wake(d)))
    ring.wake(d)                                     # applied; its receipts never sent
    assert ring.stored("receipts", aid) is None
    said = ring.wake(ring.read("wake2"))
    assert TAPS not in [w for p in parts(said) for w in p], said
    assert all(land(ring, said)), said
    assert ring.stored("receipts", aid)["data"]["result"] == "ok"
    assert ring.stored("actions", aid)["version"] == 2


# The maintainer's copy, 2026-11-11: a LinkedIn download's tap (export.take) waited through
# several wakes. Its files are in the page's own store, which only a chat can read, and the
# wake said so in a note above its last step, "then: nothing else is waiting for this chat.
# End the turn.", which each chat followed; the end of a batch named no file at all. The files
# to take are the wake's first step now, every one named, and following the steps takes it.

LINKEDIN_FIX = os.path.join(ROOT, "tests", "fixtures", "linkedin_export")
DOWNLOAD = {"a1" * 16: "messages.csv", "b2" * 16: "Connections.csv",
            "c3" * 16: "Invitations.csv"}


def _download_tapped(ring):
    import shutil
    for name, dest in (("book_contacts.csv", "network_contacts.csv"),
                       ("book_threads.csv", "network_threads.csv")):
        shutil.copyfile(os.path.join(LINKEDIN_FIX, name), os.path.join(ring.state, dest))
    ring.put("actions", "act-take", {
        "action": "export.take", "item": "linkedin-export", "rev_seen": "", "tab": "t1",
        "at": "2026-10-25T17:10:00Z",
        "value": {"assets": [{"id": k, "name": v} for k, v in DOWNLOAD.items()]}})
    return "act-take"


def test_a_linkedin_download_tapped_on_the_page_is_taken_in_the_first_wake(ring):
    import shutil
    aid = _download_tapped(ring)
    d = ring.read("wake1")
    claimed = ring.wake(d)
    assert parts(claimed) == [[CHECK_IN, TAPS]], claimed
    assert all(land(ring, claimed)), claimed
    said = ring.wake(d)                              # the claim accepted: applied
    steps = [ln for ln in said.splitlines() if ln.startswith("then: ")]
    # Its files are the first thing to do, each one named, and nothing ends the turn first.
    assert steps and steps[0].startswith("then: first, before anything below"), said
    assert all(k in steps[0] for k in DOWNLOAD), steps[0]
    assert f"--assets \"{d}/assets\"" in steps[0], steps[0]
    assert not [ln for ln in steps if ln.startswith("then: nothing else is waiting")], said
    # Following the step: each file read into the folder it names (an Artifact read saves it
    # as <asset id>.<its type>), then the command it gives.
    os.makedirs(os.path.join(d, "assets"))
    for k, name in DOWNLOAD.items():
        shutil.copyfile(os.path.join(LINKEDIN_FIX, name), os.path.join(d, "assets", k + ".csv"))
    got = json.loads(ring.run("apply", d, "--chat", CHAT, "--now", NOW,
                              "--assets", os.path.join(d, "assets")))
    assert got["ok"] == [aid], got
    import fake_db
    assert all(fake_db.apply(ring.db, p) for p in got["batches"]), got
    receipt = ring.stored("receipts", aid)["data"]
    assert receipt["result"] == "ok" and receipt["note"].startswith("Taken: "), receipt


def _taps_now(ring, d, out):
    """app.taps_now over `d`, as the end of a batch runs it (view --end), in this copy."""
    code = ("import json, sys, datetime as dt; sys.path[:0] = [sys.argv[1]]; import app; "
            "now = dt.datetime(2026, 10, 25, 18, 0, tzinfo=dt.timezone.utc); "
            "print(json.dumps(app.taps_now(sys.argv[2], sys.argv[3], now, sys.argv[4])))")
    r = subprocess.run([sys.executable, "-c", code, os.path.join(ROOT, "tools"), d, CHAT, out],
                       env=ring.env(), capture_output=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def test_a_download_tapped_while_the_work_ran_names_every_file_to_take(ring):
    """The end of a batch applies the taps made meanwhile (app.taps_now): its line said only
    "once each is read there", so a chat had to read the taps to learn which files."""
    import fake_db
    _download_tapped(ring)
    got = _taps_now(ring, ring.read("late"), os.path.join(ring.root, "late-out"))
    assert got.get("claim"), got                     # it changes the copy: claimed first
    assert all(fake_db.apply(ring.db, p) for p in got["batches"]), got
    d = ring.read("late2")
    lines = _taps_now(ring, d, os.path.join(ring.root, "late-out2"))["lines"]
    fetch = [ln for ln in lines if ln.startswith("fetch: ")]
    assert fetch and all(k in fetch[0] for k in DOWNLOAD), lines
    assert f"--assets \"{d}/assets\"" in fetch[0] and "Artifact read each" in fetch[0], fetch


def test_every_small_question_waiting_is_taken_in_one_wake(ring):
    """One talk a wake, each followed by a new read, took ten questions about 15 minutes and
    some 30 reads (the maintainer's copy, 2026-11-05). Every small item waiting is claimed in
    the same pass, each its own claim, and named under next: and also:."""
    for i in range(3):
        ring.queue(f"talk~{i}", kind="talk", asked_at=f"2026-10-25T17:0{i}:00Z")
    said = ring.wake(ring.read("wake1"))
    assert all(land(ring, said)), said
    took = [next_item(said)["work"]] + [
        json.JSONDecoder().raw_decode(said[m.end():])[0]["work"]
        for m in re.finditer(r"\nalso: ", said)]
    assert sorted(took) == ["talk~0", "talk~1", "talk~2"], said
    for wid in took:
        doc = ring.stored("work", wid)["data"]
        assert doc["status"] == "running" and doc["claimed_by"] == CHAT, (wid, doc)
    assert "do each here, now, in order" in said and "More is waiting" not in said
    again = ring.wake(ring.read("wake2"))
    assert "nothing else is waiting for this chat" in again, again


def test_a_ring_with_nothing_waiting_only_checks_in_and_another_chat_writes_nothing(ring):
    said = ring.wake(ring.read("wake1"))
    assert parts(said) == [[CHECK_IN]]
    assert "nothing else is waiting for this chat. End the turn." in said
    assert all(land(ring, said))
    other = ring.run("wake", ring.read("wake2"), "--chat", "big-chat", "--now", NOW)
    assert not sends(other) and "does not answer the page: write nothing else" in other


def test_a_small_item_comes_with_its_own_row_of_the_table(ring):
    """`wake` prints the row of step 4's table for a small item it hands this chat, so the
    chat reads none of the table (E-3)."""
    ring.queue("talk~1", kind="talk")
    item = next_item(ring.wake(ring.read("wake1")))
    assert item["run"] == "here" and item["do"] == app.work_row("talk") and "chat.md" in item["do"]


def test_the_row_of_the_table_is_printed_once_for_each_kind(ring):
    """Ten tweaks taken in one pass printed the same row of step 4's table ten times, one under
    each (the review of 2026-11-11, E-3): it is printed with the first item of each kind."""
    for i in range(3):
        ring.queue(f"talk~{i}", kind="talk", asked_at=f"2026-10-25T17:0{i}:00Z")
    ring.queue("tweak~1", kind="tweak", asked_at="2026-10-25T17:05:00Z")
    said = ring.wake(ring.read("wake1"))
    items = [next_item(said)] + [json.JSONDecoder().raw_decode(said[m.end():])[0]
                                 for m in re.finditer(r"\nalso: ", said)]
    assert len(items) == 4, said
    rows = [(it["kind"], it.get("do")) for it in items]
    assert [k for k, do in rows if do] == ["talk", "tweak"], rows
    assert said.count(json.dumps(app.work_row("talk"))[1:-1]) == 1
    assert "as the `do` of the first of its kind says" in said


def test_a_big_job_is_claimed_and_never_run_here(ring):
    ring.queue("search~1", kind="search")
    said = ring.wake(ring.read("wake1"))
    item = next_item(said)
    # Only the call and what names the job: a big job's stages, locks and claim files were
    # lines the listener read for nothing (E-8); `run` says it is big.
    assert item["run"] == "child session" and not {"heavy", "stages", "locks"} & set(item)
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
    import job_prompt
    prompt = job_prompt.followed(
        app.where_it_runs(chosen, "listener-1", "cloud")["create_session"]["prompt"])
    flat = " ".join(prompt.split())
    # Its commands, from the skill's own table, and no reading the skill for them.
    assert "run_round.py --show <args.size>" in flat and "Read only those parts" not in flat
    assert app.work_row("search") in flat and app.work_row("draft") == app.work_row(
        "resume_for_contact")
    # One small read up front, work and holds alone: the screens are read at the finish, where
    # the page is brought up to date (read up front too, they were read twice or for nothing:
    # the second audit of 2026-11-10, C4). A search says where it is every ten minutes.
    assert "collections work and holds, each" in flat and ("$D/work/search" + "@1.json") in flat
    first = flat.split("2. ", 1)[0]
    assert "screen" not in first and "addr" not in first, first
    # Read at the finish through the copy kept (the review of 2026-11-11, 2C-4).
    assert "app.py reads --in" in flat and "--for-view" in flat and "--dump \"$D/page\"" in flat
    # The chat started on the computer reads them at the finish alone, too: up front only work,
    # holds, beats and the meta its route and starter steps need (the builder audit,
    # 2026-11-10, section 12).
    import computer
    mac = " ".join(computer.session_prompt("network~1", "People", one.PAGE, "their search").split())
    read = mac.split("3. ", 1)[1].split("4. ", 1)[0]
    assert "work, holds, beats and meta" in read and "screen" not in read.split("(")[0], read
    assert "every ten minutes or so (its lease is thirty)" in flat
    assert "five minutes" not in flat
    # The hook takes no update for it: the chat that answers the page took the day's.
    monkeypatch.setattr(learned, "_path", lambda: "/tmp/not-the-example/learned.json")
    monkeypatch.setattr(sync_app, "stale", lambda: True)
    # No check tried and failed lately (sync_app.retry_due): this checkout's own git folder
    # is not this test's, and in a person's copy it may hold one.
    monkeypatch.setattr(sync_app, "retry_due", lambda: True)
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
    # One command for the day's check, master and the app's update together (H-3): a second
    # step, --pull, printed nothing whenever master had nothing new.
    said = "\n".join(lines)
    assert said.count("tools/sync_app.py") == 1 and "--if-stale" in said, said
    assert "sync_app.py --pull" not in said


def test_start_brings_the_pages_data_up_to_date_through_the_copy_kept(ring):
    """It skipped the step when given a read of the page's meta (`start --dump`), which no step
    ever passed, so the check was dead and a current page was read whole again all the same.
    Since the second audit of 2026-11-10 (D4) the step reads through the copy this checkout
    keeps (`app.py reads --for-view`): a page already current costs a small read."""
    said = ring.run("start", "--on", "test", "--tools", "none", "--chat", CHAT)
    assert "python3 tools/app.py view" in said and "app.py reads" in said and "--for-view" in said


# ------------------------------------------------------------------ the skill says so

def test_the_skill_reads_once_and_wakes_once():
    import app_skill
    skill = " ".join(app_skill.text().split())
    one_to_three = skill[skill.index("## 1. Read, in one go"):skill.index("## 4.")]
    assert "python3 tools/app.py wake \"$D\" --chat <your chat id>" in one_to_three
    # What is read is printed by code (`app.py reads`, tools/page_reads.py): the small
    # collections whole, the rest only what changed, the screens only when another chat drew
    # the page (the maintainer, 2026-11-05). A whole read is every collection a wake reads.
    import page_reads
    # The folder is the code's to choose: told to name it short, every fresh subagent chose
    # `w1`, and a second ring read into the first one's finished wake (the review of
    # 2026-11-11, E-18).
    assert "python3 tools/app.py reads --in \"<your scratchpad>\"" in one_to_three
    assert "that is `$D` from here on" in one_to_three
    assert set(page_reads.FULL_READS) == set(app.WAKE_READS)
    for coll in page_reads.WHOLE + page_reads.KEPT:
        assert f"`{coll}`" in one_to_three, coll
    # Read once each, at the subagent's start: CLAUDE.md comes with it, the skill does not
    # (E-3: "already loaded on a wake" was not so in the subagent).
    assert "SKILL.md (the Skill tool) and this file are read once each" in one_to_three
    # What the reads saved is never shown in the chat: each later step re-reads all of it (a
    # helper's history grew by every listing, the maintainer's copy, 2026-11-05).
    assert "Never list, print or open what the reads saved" in one_to_three
    # Every small item waiting is named in one wake (`also:`), never one a read.
    assert "`also:`" in one_to_three
    progress = skill[skill.index("**Progress costs nothing extra**"):]
    assert "big jobs only" in progress[:400] and "every ten minutes" in progress[:1200]


# ------------------------------------------------------------------ the ring is resolved

def test_the_wake_ends_by_resolving_the_thread_it_came_on(ring):
    said = ring.wake(ring.read("wake1"))
    assert "ArtifactComments resolve" in said and "the thread this wake came on" in said
    assert "leave no reply" in said


def test_a_ring_resolves_its_own_thread_and_watches_only_once(ring):
    """Every ring made two calls it rarely needed (the efficiency audit, E-9): its check-in
    asked again for the watch the chat already had ("asking again does no harm"), and its
    last line had it list every open thread on the page and judge each. The watch is asked
    when a chat takes the page (Ring's own listen did) and never again while it keeps it, and
    a ring resolves the one thread it came on, and the other open rings only when no wake has
    for a few hours: each one left open kept the blue dot on Claude's comments button, which
    the helper clears (the maintainer, 2026-11-10; the review of 2026-11-11)."""
    import datetime as dt
    import fake_db

    def wake(name, at=NOW):
        said = ring.wake(ring.read(name), "--now", at)
        assert all(fake_db.apply(ring.db, b) for b, _why in sends(said))
        return said

    def last(said):
        return said[said.index("last, once this wake's work is done"):].split("\n")[0]

    def later(hours):
        t = dt.datetime.fromisoformat(NOW.replace("Z", "+00:00")) + dt.timedelta(hours=hours)
        return t.strftime("%Y-%m-%dT%H:%M:%SZ")
    first = wake("wake1")
    assert "keep this chat's watch" not in first, "the chat asked for its watch when it took the page"
    assert "the thread this wake came on" in last(first)
    assert "any other open thread" in last(first), "the first wake sweeps the old rings"
    soon = wake("wake1b", later(1))
    assert "the thread this wake came on" in last(soon)
    assert "any other open thread" not in last(soon), "an hour later nothing is swept again"
    assert "any other open thread" in last(wake("wake1c", later(4))), "a few hours later it is"
    # A record from before the app kept who asked: the watch is asked once, then not again.
    rec = ring.stored("meta", "listen")
    rec["data"].pop("watch_asked", None)
    ring.put("meta", "listen", rec["data"], rec["version"])
    assert wake("wake2").count("keep this chat's watch") == 1
    assert "keep this chat's watch" not in wake("wake3")


def test_old_rings_are_cleared_once_and_the_upgrade_notes_it(tmp_path, monkeypatch, capsys):
    import profile_upgrades
    monkeypatch.setattr(app_setup, "profile_dir", lambda: str(tmp_path))
    u = profile_upgrades.by_id("doorbells")
    assert u.needs == "nobody" and not u.pending()          # no page, nothing to clear
    (tmp_path / "app.json").write_text('{"url": "https://claude.ai/artifact/EXAMPLE"}')
    assert u.pending()
    assert app.main(["doorbells"]) == 0 and "resolve each thread" in capsys.readouterr().out
    assert u.pending()
    assert app.main(["doorbells", "--done"]) == 0
    assert not u.pending()


def test_rings_no_wake_resolved_are_cleared_every_day_not_once(tmp_path, monkeypatch):
    # Cleared once ever, the rings no wake resolved (one during a busy pass, a subagent's, a
    # quick answer's) piled up to 18 unread in the Claude app (the maintainer, 2026-11-05).
    # The daily tidy clears them each day; the one-time upgrade stays done.
    import datetime as dt
    monkeypatch.setattr(app_setup, "profile_dir", lambda: str(tmp_path))
    day = dt.date(2026, 11, 5)
    assert not app_setup.doorbells_due(day), "no page, nothing to clear"
    (tmp_path / "app.json").write_text('{"url": "https://claude.ai/artifact/EXAMPLE"}')
    assert app_setup.doorbells_due(day)
    app_setup.save_said(app_setup.DOORBELLS, "2026-11-05")
    assert not app_setup.doorbells_due(day), "cleared today"
    assert app_setup.doorbells_due(day + dt.timedelta(days=1)), "and due again tomorrow"
