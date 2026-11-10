"""Every move of a work item is a command pinned to the version it read, and a batch is one job.

The engine audit of 3 November 2026 found the work queue written partly by hand and partly
by code that forgot the rest of a batch: a draft batch's other postings were handed to a
second job half an hour in while the first still wrote them; one batch filled the cap; a
finished job's lock held its employer for half an hour; a job that stopped twice sat
"running" for good and blocked the helper's renewal; a question answered on the page came
back with the last try's batch and stage; a write with no version reset `_v` or was refused
with the whole batch; and the helper never renewed while anything waited. Each test below is
one finding's own steps (engine 1 to 12, 37 in the audit), on invented employers.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app  # noqa: E402
import app_listen  # noqa: E402
import page_db  # noqa: E402

APP = os.path.join(ROOT, "tools", "app.py")


def T(hhmm: str) -> dt.datetime:
    h, m = hhmm.split(":")
    return dt.datetime(2026, 11, 3, int(h), int(m), tzinfo=dt.timezone.utc)


def S(hhmm: str) -> str:
    return T(hhmm).strftime("%Y-%m-%dT%H:%M:%SZ")


def draft(company, status="queued", asked="2026-11-03T16:00:00Z", **kw):
    return dict({"kind": "draft", "status": status, "asked_at": asked,
                 "args": {"company": company}, "stages": page_db.progress("draft")["stages"]},
                **kw)


def db_of(work, locks=None):
    return {"work": {k: {"data": d, "version": v} for k, (d, v) in work.items()},
            "locks": {k: {"data": d, "version": v} for k, (d, v) in (locks or {}).items()},
            "chats": {}}


def entries(paths):
    out = []
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            for e in json.load(fh):
                body = {}
                if e.get("file_path"):
                    with open(e["file_path"], encoding="utf-8") as b:
                        body = json.load(b)
                out.append(dict(e, body=body))
    return out


def dump_dir(root, db):
    """`db` as a chat's read saves it: each record's fields with its `_v`."""
    for coll, docs in db.items():
        where = os.path.join(root, page_db.STORE.get(coll, coll))
        os.makedirs(where, exist_ok=True)
        for doc_id, doc in docs.items():
            doc_id = page_db.stored(coll, doc_id)[1]
            with open(os.path.join(where, doc_id.replace("~", "@") + ".json"), "w",
                      encoding="utf-8") as fh:
                json.dump(dict(doc["data"], _v=doc["version"]), fh)
    return root


def claimed_batch(tmp_path):
    """Three drafts queued together, claimed at 17:05 by one job, as `next` claims them."""
    db = db_of({"draft~lead": (draft("Larkspur Retail", asked="2026-11-03T16:00:00Z"), 3),
                "draft~two": (draft("Quillon Data", asked="2026-11-03T16:01:00Z"), 2),
                "draft~three": (draft("Fernhill Freight", asked="2026-11-03T16:02:00Z"), 2)})
    chosen = page_db.next_item(db, "cloud", T("17:05"), cap=page_db.HEAVY_CAP_CHATS)
    assert chosen["work"] == "draft~lead" and [w["work"] for w in chosen["with"]] == \
        ["draft~two", "draft~three"]
    d = dump_dir(str(tmp_path / "d"), db)
    batches = page_db.claim(db, chosen, "session_job", "cloud", T("17:05"), str(tmp_path / "c"))
    page_db.keep_landed(d, batches)
    return d


# ------------------------------------------------------------------ engine 1 and 6: a batch


def test_a_batchs_other_postings_are_never_taken_again_while_its_job_runs(tmp_path):
    """Engine 1: the leader pinned at 17:35, `next` at 17:40 handed the second posting out again
    (`again: 2`), with a lock of its own, while the first job still wrote it."""
    d = claimed_batch(tmp_path)
    got = page_db.pin(page_db.load(d), "draft~lead", T("17:35"), str(tmp_path / "p"),
                      stage="write", dump_dir=d, chat="session_job")
    page_db.keep_landed(d, got["batches"])
    # The pin renewed and moved every posting of the batch, each pinned to its own version.
    pinned = {e["doc_id"]: e for e in entries(got["batches"])}
    assert set(pinned) == {"draft~lead", "draft~two", "draft~three"}
    assert pinned["draft~two"]["if_version"] == 3 and pinned["draft~two"]["body"]["status"] == \
        "running" and pinned["draft~two"]["body"]["lease_until"] == S("18:05")
    db = page_db.load(d)
    db["work"]["draft~four"] = {"data": draft("Quillon Data", asked="2026-11-03T17:30:00Z"),
                                "version": 1}
    assert page_db.next_item(db, "cloud", T("17:40"), cap=page_db.HEAVY_CAP_CHATS) is None
    # Even unpinned (a pin refused), a posting of a live batch is the batch's: held with it.
    raw = db_of({"draft~lead": (draft("Larkspur Retail", status="running",
                                      claimed_by="session_job", lease_until=S("18:05")), 5),
                 "draft~two": (draft("Quillon Data", status="claimed", claimed_by="session_job",
                                     lease_until=S("17:35"), **{"with": "draft~lead"}), 3)})
    assert page_db.next_item(raw, "cloud", T("17:40"), cap=page_db.HEAVY_CAP_CHATS) is None
    assert page_db.held_locks(raw, T("17:40"))["emp~quillon_data"] == "draft~two"


def test_a_batch_takes_one_place_under_the_cap(tmp_path):
    """Engine 6: a batch of three claimed counted as three heavy jobs, so with the computer's
    cap of three a queued search and networking run waited behind one job."""
    d = claimed_batch(tmp_path)
    db = page_db.load(d)
    db["work"]["search~1"] = {"data": {"kind": "search", "status": "queued",
                                       "asked_at": "2026-11-03T16:30:00Z", "args": {}},
                              "version": 1}
    got = page_db.next_item(db, "computer", T("17:10"), cap=page_db.HEAVY_CAP)
    assert got is not None and got["work"] == "search~1"


def test_the_jobs_own_steps_name_every_posting_of_the_batch(monkeypatch):
    """Engine 12: the job's prompt named the leader only, so a chat following it drafted one
    of three and pinned one lease."""
    import app_setup
    monkeypatch.setattr(app_setup, "origin", lambda: ("example-owner", "example-copy"))
    monkeypatch.setattr(app_setup, "page_record", lambda: {"url": "https://claude.ai/artifact/x"})
    chosen = {"work": "draft~lead", "kind": "draft", "title": "Three drafts", "heavy": True,
              "with": [{"work": "draft~two", "version": 2}, {"work": "draft~three", "version": 2}],
              "stages": page_db.progress("draft")["stages"]}
    flat = " ".join(app.where_it_runs(chosen, "session_listener", "cloud")["create_session"]
                    ["prompt"].split())
    assert "draft~two" in flat and "draft~three" in flat and "Pin draft~lead alone" in flat
    assert "--stopped" in flat and "--question" in flat and "app.py version" in flat
    # One read of the queue, all of it, and no step that forbids the page's own tool.
    assert "collections work, holds" in flat and "No ArtifactData" not in flat


# ------------------------------------------------------------------ engine 3 and 38: locks


def test_a_finished_jobs_lock_never_holds_its_employer(tmp_path):
    """Engine 3: a lock whose job had finished is not in a read of the queue, and it held the
    next draft for that employer until its half hour ran out."""
    db = db_of({"draft~next": (draft("Quillon Data", asked="2026-11-03T17:07:51Z"), 4)},
               locks={"emp~quillon_data": ({"work": "draft~gone", "chat": "session_job",
                                            "since": S("17:00"), "until": S("17:30")}, 1)})
    got = page_db.next_item(db, "cloud", T("17:10"), cap=page_db.HEAVY_CAP_CHATS)
    assert got["work"] == "draft~next"
    # Its claim replaces the old lock, pinned to the version read.
    batches = page_db.claim(db, got, "session_listener", "cloud", T("17:10"), str(tmp_path / "c"))
    lock = next(e for e in entries(batches) if e["collection"] == "holds")
    assert lock["if_version"] == 1 and lock["body"]["work"] == "draft~next"


def test_finishing_one_posting_frees_its_own_employer_and_deletes_its_locks(tmp_path):
    """Engine 38: lock records were deleted only by hand. Each lock now names the posting that
    needs it, and `app.py done` deletes them, pinned."""
    d = claimed_batch(tmp_path)
    db = page_db.load(d)
    owners = {lid: doc["data"]["work"] for lid, doc in db["locks"].items()}
    assert owners == {"emp~larkspur_retail": "draft~lead", "emp~quillon_data": "draft~two",
                      "emp~fernhill_freight": "draft~three"}
    got = page_db.finish(db, "draft~two", T("17:30"), str(tmp_path / "f"),
                         summary="Your Quillon Data resume and letter are ready.",
                         chat="session_job", dump_dir=d)
    assert got["locks"] == ["emp~quillon_data"]
    gone = [e for e in entries(got["batches"]) if e["op"] == "delete"]
    assert [(e["doc_id"], e["if_version"]) for e in gone] == [("emp~quillon_data", 1)]


# ------------------------------------------------------------------ engine 4 and 39: stranded


def test_a_job_that_stopped_twice_is_ended_at_the_check_in(tmp_path, monkeypatch):
    """Engine 4: `search~x` running, attempt 2, lease out at 12:00: at 18:00 nothing took it,
    nothing failed it, the page refused every new search, and the renewal never fired."""
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "cloud")
    monkeypatch.setattr(app_listen, "history_tokens", lambda: 0)
    monkeypatch.setattr(app_listen, "_save_seen", lambda data: None)
    monkeypatch.setattr(app_listen, "seen", lambda: {})
    stuck = {"kind": "search", "status": "running", "attempt": 2, "lease_until": S("12:00"),
             "claimed_by": "session_gone", "asked_at": S("10:00"), "args": {}}
    stop = {"kind": "network", "status": "running", "attempt": 1, "lease_until": S("12:00"),
            "claimed_by": "session_gone", "asked_at": S("10:00"), "args": {}, "stop_asked": True}
    db = db_of({"search~x": (stuck, 7), "network~y": (stop, 4)},
               locks={"search": ({"work": "search~x", "until": S("12:30")}, 2)})
    assert page_db.next_item(db, "cloud", T("18:00")) is None        # never a third try
    got = page_db.fail_stranded(db, T("18:00"), str(tmp_path / "s"))
    assert got["ended"] == ["network~y", "search~x"]
    by = {e["doc_id"]: e for e in entries(got["batches"])}
    assert by["search~x"]["if_version"] == 7 and by["search~x"]["body"]["status"] == "failed"
    assert by["search~x"]["body"]["error"] == page_db.STRANDED_SAID
    assert by["network~y"]["body"]["status"] == "stopped"
    assert by["search"]["op"] == "delete" and by["search"]["if_version"] == 2
    # The listener's check-in sends it, and once it lands the helper may renew.
    d = dump_dir(str(tmp_path / "d"), dict(db, meta={"listener": {"data": {
        "chat": "session_old", "kind": "cloud", "since": "2026-11-02T08:00:00Z",
        "answered_at": S("17:00")}, "version": 9}}))
    monkeypatch.setattr(app_listen, "_remember", lambda *a, **k: None)
    seen = app.check_in(d, "session_old", T("18:00"), str(tmp_path / "o"))
    assert seen["stranded"] and page_db.load(d)["work"]["search~x"]["data"]["status"] == "failed"


# ------------------------------------------------------------------ engine 5: a question


def test_a_question_goes_to_the_page_by_command_and_the_answer_resumes_clean(tmp_path):
    """Engine 5: the item went `needs_you` by hand, then came back queued with `with` a
    finished leader, its old stage, steps and a waiting line, and was counted as part of a
    job that had ended."""
    d = claimed_batch(tmp_path)
    got = page_db.finish(page_db.load(d), "draft~two", T("17:20"), str(tmp_path / "q"),
                         question="Have you used Kafka at work?", chat="session_job", dump_dir=d)
    body = entries(got["batches"])
    item = next(e for e in body if e["doc_id"] == "draft~two")
    assert item["if_version"] == 3 and item["body"]["status"] == "needs_you"
    assert item["body"]["note"] == "Have you used Kafka at work?" and got["locks"] == \
        ["emp~quillon_data"]
    # The page's answer, as templates/app/app.js answerWork writes it.
    page_db.keep_landed(d, got["batches"])
    db = page_db.load(d)
    w = dict(db["work"]["draft~two"]["data"])
    w.update(status="queued", note=None, claimed_by=None, claimed_at=None, lease_until=None,
             answered_at=S("17:25"), stage=2, stage_line="Waiting on one question",
             steps=[{"at": S("17:10"), "text": "Read the posting"}],
             args=dict(w["args"], answers={"Have you used Kafka at work?": "yes, at Larkspur Retail"}))
    db["work"]["draft~two"] = {"data": w, "version": 5}
    db["work"]["draft~lead"]["data"].update(status="done")
    chosen = page_db.next_item(db, "cloud", T("17:30"), cap=page_db.HEAVY_CAP_CHATS)
    assert chosen["work"] == "draft~two"
    claim = {e["doc_id"]: e["body"] for e in entries(
        page_db.claim(db, chosen, "session_new", "cloud", T("17:30"), str(tmp_path / "c2")))}
    mine = claim["draft~two"]
    assert mine["with"] == {"__delete__": True} and mine["stage_line"] == {"__delete__": True}
    assert mine["stage"] == 0 and mine["steps"] == [{"at": S("17:30"),
                                                      "text": "Carrying on with your answer."}]


def test_done_stops_an_item_and_never_takes_another_chats(tmp_path):
    d = claimed_batch(tmp_path)
    got = page_db.finish(page_db.load(d), "draft~three", T("17:20"), str(tmp_path / "s"),
                         status="stopped", chat="session_job")
    item = next(e for e in entries(got["batches"]) if e["doc_id"] == "draft~three")
    assert item["body"]["status"] == "stopped" and item["body"]["result"]["summary"] == \
        page_db.STOPPED_SAID
    with pytest.raises(KeyError):
        page_db.finish(page_db.load(d), "draft~three", T("17:20"), str(tmp_path / "x"),
                       status="stopped", chat="session_other")


# ------------------------------------------------------------------ engine 2: versions


def test_a_write_is_pinned_to_the_version_read_even_when_its_maker_named_none(tmp_path):
    """Engine 2.1: `Writes.add` stamped `_v: 1` with no `if_version` on a record that exists
    (`search~setting~window~0` changed twice), so the store refused the whole batch."""
    db = db_of({"search~setting~window~0": ({"kind": "search", "status": "done"}, 4)})
    w = page_db.Writes(str(tmp_path), db=db)
    e = w.add("set", "work", "search~setting~window~0", {"kind": "search", "status": "queued"})
    assert e["if_version"] == 4
    with open(e["file_path"], encoding="utf-8") as fh:
        assert json.load(fh)["_v"] == 5
    assert "if_version" not in page_db.Writes(str(tmp_path / "b"), db=db).add(
        "set", "work", "new~1", {"kind": "talk"})


def test_a_refused_writes_named_version_is_kept_and_the_command_pins_to_it(tmp_path):
    """Engine 2.2: a record a hand write left at the wrong `_v` (store 6, `_v` 5) was refused
    however often it was read again. The version the refusal names goes back into the folder
    (`app.py version`), and the command run again pins to it."""
    d = claimed_batch(tmp_path)
    r = subprocess.run([sys.executable, APP, "version", d, "work/draft~lead", "9"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    got = page_db.pin(page_db.load(d), "draft~lead", T("17:20"), str(tmp_path / "p"),
                      stage="research", chat="session_job")
    lead = next(e for e in entries(got["batches"]) if e["doc_id"] == "draft~lead")
    assert lead["if_version"] == 9 and lead["body"]["_v"] == 10
    bad = subprocess.run([sys.executable, APP, "version", d, "work/nothing~here", "3"],
                         capture_output=True, text=True, encoding="utf-8")
    assert bad.returncode == 2 and "read it again" in bad.stderr


def test_every_move_of_an_item_has_its_command_and_the_skill_writes_none_by_hand():
    skill = " ".join(open(os.path.join(ROOT, ".claude", "skills", "app", "SKILL.md"),
                          encoding="utf-8").read().split())
    for said in ("--stopped", "--question", "app.py version"):
        assert said in skill, said
    assert "write `status: stopped`" not in skill and "as `status: needs_you` with the question" \
        not in skill
    # The whole queue is read, so a finished item's id is pinned when it is asked for again.
    assert "`work` where `status` in" not in skill


# ------------------------------------------------------------------ engine 7 and 8: the helper


def test_the_helper_renews_with_work_waiting_and_asks_again_if_none_came(monkeypatch):
    """Engine 7: three days on one helper against a 20-hour limit, because any queued item
    blocked the renewal; and `renewed_at` was kept before the new chat was ever made."""
    store = {}
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "cloud")
    monkeypatch.setattr(app_listen, "history_tokens", lambda: 0)
    monkeypatch.setattr(app_listen, "seen", lambda: dict(store))
    monkeypatch.setattr(app_listen, "_save_seen", lambda data: store.update(data))
    import app_setup
    monkeypatch.setattr(app_setup, "origin", lambda: ("example-owner", "example-copy"))
    # A helper the app started (`helper`): only such a chat is ever renewed, never the
    # person's own (the stranger audit, X-4).
    rec = {"chat": "session_old", "since": "2026-10-31T17:58:52Z", "helper": True}
    queued = db_of({"draft~a": (draft("Quillon Data"), 3),
                    "draft~b": (draft("Larkspur Retail", status="running",
                                      claimed_by="session_old", lease_until=S("18:20")), 4)})
    assert app_listen.renewal(rec, queued, "session_old", T("18:00")) is not None
    # Asked an hour ago and this chat still answers: not yet. Two hours on: asked again.
    assert app_listen.renewal(rec, queued, "session_old", T("19:00")) is None
    assert app_listen.renewal(rec, queued, "session_old", T("20:01")) is not None
    # A small job it is doing itself holds it.
    store.clear()
    mine = db_of({"reply~a": ({"kind": "reply", "status": "running", "claimed_by": "session_old",
                               "lease_until": S("18:20")}, 2)})
    assert app_listen.renewal(rec, mine, "session_old", T("18:00")) is None


def test_a_tap_whose_claim_ran_out_counts_as_waiting():
    """Engine 8: an action claimed by a chat that stopped never counted as waiting, so the
    listener that had gone was never judged gone."""
    db = {"actions": {"a1": {"data": {"at": S("09:00"), "claimed_by": "session_gone",
                                      "claimed_until": S("09:10")}, "version": 2}},
          "receipts": {}, "work": {}}
    assert app_listen.waiting_since(db, T("18:00")) == T("09:00")
    assert app_listen.lapsed({"chat": "session_gone", "answered_at": S("08:00")}, db, T("18:00"))
    live = {"actions": {"a1": {"data": {"at": S("17:55"), "claimed_by": "session_x",
                                        "claimed_until": S("18:05")}, "version": 2}},
            "receipts": {}}
    assert app_listen.waiting_since(live, T("18:00")) is None


# ------------------------------------------------------------------ engine 11: pruning


def test_pruning_at_the_cap_never_parts_a_receipt_from_its_action(tmp_path):
    """Engine 11: 80 old pairs pruned at a cap of 75 deleted 38 receipts and 37 actions, and
    the action left without its receipt was applied again."""
    old = "2026-08-01T10:00:00Z"
    db = {"receipts": {f"a{n:03d}": {"data": {"applied_at": old}, "version": 1} for n in range(80)},
          "actions": {f"a{n:03d}": {"data": {"at": old}, "version": 1} for n in range(80)},
          "work": {}}
    got = entries(page_db.prune(db, T("18:00"), str(tmp_path), cap=75))
    receipts = {e["doc_id"] for e in got if e["collection"] == "receipts"}
    actions = {e["doc_id"] for e in got if e["collection"] == "actions"}
    assert receipts == actions and len(receipts) == 37


# ------------------------------------------------------------------ engine 37: who wrote the page


def test_the_page_is_written_by_the_sessions_own_id_not_a_word(tmp_path):
    """Engine 37: the brief ran `app.py view ... --chat brief`, so meta/now.by was "brief",
    which no listener rule could compare with a chat."""
    env = dict(os.environ, LJS_CHAT="session_listener", LJS_COPY="private")
    r = subprocess.run([sys.executable, APP, "view", str(tmp_path / "v"), "--chat", "brief",
                        "--now", "2026-11-03T08:00:00Z"], env=env, capture_output=True,
                       text=True, encoding="utf-8", timeout=300)
    assert r.returncode in (0, 3), r.stdout + r.stderr
    if r.returncode == 3:
        pytest.skip("this checkout is behind master, so view would not write")
    batches = json.loads(r.stdout)["batches"]
    now = next(e for e in entries(batches) if e["collection"] == "meta")
    assert now["doc_id"] == "now" and now["body"]["by"] == "session_listener"


def test_every_read_that_claims_reads_the_locks():
    """Engine 10: claims built from reads with no `holds` wrote locks blind. The wake's read
    and a job's own read both take `holds`; a claim refused for a lock the read missed is
    read again (and `app.py version` keeps a version the refusal named)."""
    assert "holds" in app.WAKE_READS
    steps = " ".join(app.job_steps({"work": "search~1", "kind": "search", "stages": []},
                                   "session_listener", "https://claude.ai/artifact/x"))
    assert "collections work, holds" in steps and "collections work, holds and beats" in steps


def test_a_claim_writes_only_what_its_read_listed(tmp_path):
    """The maintainer's helper, 2026-11-10: `next --claim-out`'s claim wrote this chat's own
    heartbeat as new, pinned to nothing, while the page held it at 6, because the read for the
    next job took work and holds only. The read names the heartbeats now, and a claim from a
    read without them leaves the heartbeat out rather than write it blind."""
    db = db_of({"draft~lead": (draft("Larkspur Retail"), 3)})
    db["chats"] = {"session_job": {"data": {"kind": "cloud", "seen_at": "2026-11-03T16:00:00Z"}, "version": 6}}
    chosen = page_db.next_item(db, "cloud", T("17:05"), cap=page_db.HEAVY_CAP_CHATS)
    read = entries(page_db.claim(db, chosen, "session_job", "cloud", T("17:05"), str(tmp_path / "a")))
    beat = next(e for e in read if e["collection"] == page_db.STORE["chats"])
    assert beat["if_version"] == 6, beat
    blind = entries(page_db.claim(db_of({"draft~lead": (draft("Larkspur Retail"), 3)}), chosen, "session_job",
                                  "cloud", T("17:05"), str(tmp_path / "b"), beat=False))
    assert not [e for e in blind if e["collection"] == page_db.STORE["chats"]], blind
    # `next` knows from the folder whether the heartbeats were read.
    unread = db_of({"draft~lead": (draft("Larkspur Retail"), 3)})
    del unread["chats"]
    d = dump_dir(str(tmp_path / "d"), unread)
    assert not page_db.read_has(d, "beats")
    os.makedirs(os.path.join(d, "beats"))
    assert page_db.read_has(d, "beats") and page_db.read_has(d, "chats")


def test_a_refused_page_update_reads_again_what_other_chats_moved_on_and_says_so_in_one_line(tmp_path):
    """The maintainer's helper, 2026-11-10: a page update pinned screen/listener at 96 (the
    page had 106) and meta/now at 141 (154). The store names one record a refusal, so the
    save made again was refused for the next. `app.py version` reads again, in one go, the
    screens, meta and heartbeats the refused batch writes, and the save lands once. A job's
    chat is told exactly that in one line."""
    d = str(tmp_path / "d")
    os.makedirs(d)
    with open(os.path.join(d, page_db.SENT), "w", encoding="utf-8") as fh:
        json.dump([{"records": ["screen/listener", "meta/now", "screen/jobs"]}], fh)
    assert page_db.read_again(d, "screen/listener") == ["meta", "screen"]
    steps = " ".join(app.job_steps({"work": "prep~1", "kind": "prep", "stages": []},
                                   "session_job", "https://claude.ai/artifact/x"))
    assert app.REFUSED_ONCE in steps and "read those four again" not in steps
    assert "app.py version" in app.REFUSED_ONCE and "once more" in app.REFUSED_ONCE


def test_the_brief_ends_with_the_wake_that_ends_stranded_work():
    """Engine 39: the brief applied taps but never looked at work left stranded. Its last
    page step is the app skill's steps 1 to 3 (the wake), whose check-in ends it."""
    src = open(os.path.join(ROOT, "tools", "brief.py"), encoding="utf-8").read()
    assert "Then the app skill's steps 1 to 3, for work still waiting" in src
    assert "fail_stranded" in open(os.path.join(ROOT, "tools", "app.py"), encoding="utf-8").read()


def test_interview_preps_queued_together_are_one_job():
    # Several interviews ahead, each asked for on its card: one job takes them (the
    # maintainer, 2026-11-10: "can't multiple interviews be batched into one"), each keeping its
    # own work item, and the batch stops at its size.
    def prep(iv, at):
        return {"kind": "prep", "status": "queued", "asked_at": at, "args": {"interview": iv},
                "stages": page_db.progress("prep")["stages"]}
    ids = ["prep~iv-" + str(i) for i in range(page_db.PREP_BATCH + 1)]
    work = {w: (prep(w.split("~")[1], "2026-11-03T16:0" + str(i) + ":00Z"), 1) for i, w in enumerate(ids)}
    chosen = page_db.next_item(db_of(work), "cloud", T("17:05"), cap=page_db.HEAVY_CAP_CHATS)
    assert chosen["work"] == ids[0]
    assert [w["work"] for w in chosen["with"]] == ids[1:page_db.PREP_BATCH]
