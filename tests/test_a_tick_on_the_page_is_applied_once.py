"""What the person does on the page reaches the repo exactly once, and can be taken back.

The page writes an action; a chat runs `tools/app.py apply` over a dump of the page's
database. Each action goes through the writer the chat commands use (confirm.py,
exclude.py, state.py, learned.py, the settings), once: a receipt or the run's own ledger
stops a second application, an action made on something that has changed since is refused
with nothing written, and every receipt carries the undo that takes it back. `next` gives
each queued piece of work to one chat only, never two jobs at one employer at once. Every
person and employer here is invented (tests/app_state.py).
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_actions  # noqa: E402
import app_model  # noqa: E402
import app_state  # noqa: E402
import page_db  # noqa: E402

APP = os.path.join(ROOT, "tools", "app.py")
NOW = app_state.NOW
KESTREL = "app-kestrel_mutual_claims_forecasting_analyst"


class Search:
    """An invented search in a folder of its own: its state, its profile, a page dump."""

    def __init__(self, root):
        self.state = app_state.small(os.path.join(root, "state"))
        self.profile = app_state.profile_copy(os.path.join(root, "profile"))
        self.dump = os.path.join(root, "dump")
        self.n = 0

    def run(self, *args, ok=(0,)):
        env = dict(os.environ, LJS_PROFILE=self.profile, LJS_STATE=self.state, LJS_COPY="private")
        env.pop("LJS_TODAY", None)
        r = subprocess.run([sys.executable, APP, *args], env=env, capture_output=True,
                           encoding="utf-8", errors="replace", timeout=120)
        assert r.returncode in ok, r.stdout + r.stderr
        return r.stdout

    def model(self):
        return json.loads(self.run("model", "--now", NOW))

    def item(self, item_id):
        m = self.model()
        for section in ("needs_you", "ready", "messages", "people", "settings"):
            for it in m[section]:
                if it["id"] == item_id:
                    return it
        for it in m["jobs"]["rows"]:
            if it["id"] == item_id:
                return it
        for g in m["jobs"]["filtered"]["groups"]:
            for it in g["items"]:
                if it["id"] == item_id:
                    return it
        raise KeyError(item_id)

    def act(self, action, item=None, value=None, rev=None, **extra):
        self.n += 1
        aid = f"act{self.n:02d}"
        doc = {"action": action, "at": f"2026-10-25T17:{self.n:02d}:00Z", "tab": "t1", **extra}
        if item is not None:
            doc["item"] = item
            doc["rev_seen"] = rev if rev is not None else self.item(item)["rev"]
        if value is not None:
            doc["value"] = value
        self.put("actions", aid, doc, version=1)
        return aid

    def put(self, collection, doc_id, data, version=None):
        d = os.path.join(self.dump, collection)
        os.makedirs(d, exist_ok=True)
        body = dict(data, **({"__version__": version} if version is not None else {}))
        with open(os.path.join(d, doc_id + ".json"), "w", encoding="utf-8") as fh:
            json.dump(body, fh)

    def apply(self, *extra):
        return json.loads(self.run("apply", self.dump, "--chat", "cloud-1", "--now", NOW, *extra))

    def receipt(self, aid):
        with open(os.path.join(self.dump, "out", "files", "receipts", aid + ".json"),
                  encoding="utf-8") as fh:
            return json.load(fh)

    def written_back(self):
        """The receipts the chat sent, as the next dump holds them."""
        for f in os.listdir(os.path.join(self.dump, "out", "files", "receipts")):
            with open(os.path.join(self.dump, "out", "files", "receipts", f),
                      encoding="utf-8") as fh:
                self.put("receipts", f[:-5], json.load(fh), version=1)

    def tracker_row(self, company):
        with open(os.path.join(self.state, "job_search_tracker.csv"), encoding="utf-8") as fh:
            return next(r for r in csv.DictReader(fh) if r["company"] == company)

    def files_hash(self):
        h = hashlib.sha256()
        for base in (self.state, self.profile):
            for dp, dns, fns in sorted(os.walk(base)):
                dns.sort()
                for f in sorted(fns):
                    with open(os.path.join(dp, f), "rb") as fh:
                        h.update(f.encode() + fh.read())
        return h.hexdigest()


@pytest.fixture
def search(tmp_path):
    return Search(str(tmp_path))


def test_every_action_in_the_table_has_a_writer_and_an_undo():
    for name, (kinds, writer, undo) in app_actions.ACTIONS.items():
        assert writer, name
        if name != "undo":
            assert kinds, name
            assert undo in app_actions.ACTIONS or name in app_actions.NO_UNDO, name


def test_a_tick_is_applied_once_through_confirm(search):
    aid = search.act("ready.applied", KESTREL)
    got = search.apply()
    assert got["ok"] == [aid]
    row = search.tracker_row("Kestrel Mutual")
    assert (row["status"], row["applied_on"], row["confirmed_by"]) == (
        "applied", "2026-10-25", "page")
    assert row["confirmed_at"] == "2026-10-25 17:01"     # the tap's own time, the person's zone
    rcpt = search.receipt(aid)
    assert rcpt["result"] == "ok" and rcpt["undo"]["action"] == "ready.not_applied"
    with open(got["batches"][0], encoding="utf-8") as fh:
        batch = json.load(fh)
    assert batch == [{"op": "set", "collection": "receipts", "doc_id": aid,
                      "file_path": batch[0]["file_path"]}]

    # Run again before the receipts are back: the ledger re-sends them, nothing is written.
    before = search.files_hash()
    again = search.apply()
    assert again["again"] == [aid] and again["ok"] == []
    assert search.files_hash() == before
    # The receipts written back: nothing is pending at all.
    search.written_back()
    os.remove(os.path.join(search.dump, app_actions.LEDGER))
    assert search.apply()["ok"] == [] and search.files_hash() == before


def test_an_action_on_something_that_changed_is_refused_and_writes_nothing(search):
    old = search.item(KESTREL)["rev"]
    phone = search.act("ready.applied", KESTREL, rev=old)
    search.apply()
    before = search.files_hash()
    laptop = search.act("ready.not_applying", KESTREL, rev=old)   # the other device's answer
    got = search.apply()
    assert got["stale"] == [laptop]
    assert search.receipt(laptop)["result"] == "stale"
    assert search.files_hash() == before
    assert search.tracker_row("Kestrel Mutual")["status"] == "applied"
    assert phone in got["again"]


def test_every_kind_of_answer_can_be_taken_back(search):
    dismiss = search.act("job.dismiss", "r9-1", value={"why": "too far to travel"})
    applied = search.act("ready.applied", KESTREL)
    sent = search.act("msg.sent", "msg-kestrel_mutual_ansgar")
    tips = search.act("setting.set", "setting-tips", value="off")
    got = search.apply()
    assert got["ok"] == [dismiss, applied, sent, tips]
    m = search.model()
    assert {r["id"]: r["status"] for r in m["jobs"]["rows"]}["r9-1"] == "dismissed"
    assert m["messages"] == []
    assert {s["key"]: s["value"] for s in m["settings"]}["tips"] == "off"
    with open(os.path.join(search.profile, "learned.json"), encoding="utf-8") as fh:
        assert json.load(fh)["entries"][0]["said"] == "too far to travel"

    search.written_back()
    undos = [search.act("undo", undoes=a) for a in (dismiss, applied, sent, tips)]
    got = search.apply()
    assert got["ok"] == undos, [search.receipt(u) for u in undos]
    m = search.model()
    assert {r["id"]: r["status"] for r in m["jobs"]["rows"]}["r9-1"] == "new"
    assert search.tracker_row("Kestrel Mutual")["status"] == "drafted"
    assert [x["id"] for x in m["messages"]] == ["msg-kestrel_mutual_ansgar"]
    assert {s["key"]: s["value"] for s in m["settings"]}["tips"] == "on"
    with open(os.path.join(search.profile, "learned.json"), encoding="utf-8") as fh:
        assert json.load(fh)["entries"][0]["status"] == "retired"
    assert search.receipt(undos[0])["action"] == "undo"
    assert search.receipt(undos[0])["ran"] == "job.bring_back"
    # What the page shows the person under each answer is plain words.
    jargon = re.compile(r"\b(?:repo\w*|branch|commit|db|database|rev|json|csv|state\.py|"
                        r"confirm\.py|exclude\.py|receipt|batch|null|None)\b", re.I)
    for a in (dismiss, applied, sent, tips, *undos):
        note = search.receipt(a)["note"]
        assert note and not jargon.search(note), note


def test_no_more_roles_from_an_employer_turns_it_down_by_name_until_brought_back(search):
    """The bin's "No more roles from them" (the maintainer, 2026-10-26): the employer is
    turned down the way bar.py reads it, by its company key, and Bring back lifts it."""
    row = {r["id"]: r for r in search.model()["jobs"]["rows"]}["r9-1"]

    def why():
        env = dict(os.environ, LJS_PROFILE=search.profile, LJS_STATE=search.state)
        code = "import sys; sys.path.insert(0, %r); import bar; print(bar.excluded_by_name(%r))" % (
            os.path.join(ROOT, "tools"), row["company"])
        return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                              encoding="utf-8", timeout=60).stdout.strip()

    assert not why()
    a = search.act("job.dismiss", "r9-1", value={"why": "employer", "scope": "employer"})
    assert search.apply()["ok"] == [a]
    assert why(), "the employer is now turned down by name"
    u = search.act("undo", undoes=a)
    assert search.apply()["ok"] == [u]
    assert not why(), "Bring back takes it off again"


def test_follow_ups_at_an_employer_judged_wanting_leave_to_do_and_say_so(search):
    """A charity or a small firm the person's bar clears for nothing does not fill To do (the
    maintainer, 2026-10-26); the brief judges employers nobody has, and one line says how many."""
    before = [d for d in search.model()["due"] if d["company"] == "Fernhill Freight" and d["kind"] != "reply"]
    assert before, "the invented search owes a follow-up at Fernhill Freight"
    env = dict(os.environ, LJS_PROFILE=search.profile, LJS_STATE=search.state)
    bar = os.path.join(ROOT, "tools", "bar.py")
    out = subprocess.run([sys.executable, bar, "unjudged", "--contacts"], env=env, capture_output=True,
                         encoding="utf-8", timeout=60).stdout
    assert "Fernhill Freight" in out, out
    subprocess.run([sys.executable, bar, "judge", "Fernhill Freight", "none", "small firm, pay under the bar"],
                   env=env, check=True, capture_output=True, timeout=60)
    after = search.model()["due"]
    assert not [d for d in after if d["company"] == "Fernhill Freight" and d["kind"] not in ("reply", "hidden")]
    hidden = [d for d in after if d["kind"] == "hidden"]
    assert hidden and hidden[0]["title"].endswith("at employers you turned down not shown")


def test_progress_counts_a_reply_only_after_a_message_of_theirs(search):
    done = search.model()["done"]
    assert set(done["recent"]) == {"days", "counts", "funnel"} and done["recent"]["days"] == 30
    assert done["recent"]["counts"]["applied"] <= done["counts"]["applied"]
    assert done["recent"]["counts"]["replies"] <= done["counts"]["replies"]


def test_an_undo_after_another_change_is_refused(search):
    applied = search.act("ready.applied", KESTREL)
    search.apply()
    search.written_back()
    later = search.act("ready.not_applied", KESTREL)       # changed again since
    search.apply()
    search.written_back()
    undo = search.act("undo", undoes=applied)
    got = search.apply()
    assert got["stale"] == [undo]
    assert search.tracker_row("Kestrel Mutual")["status"] == "drafted"
    assert search.receipt(later)["result"] == "ok"


def test_a_draft_request_queues_work_and_writes_nothing_in_the_repo(search):
    before = search.files_hash()
    aid = search.act("job.draft", "r9-3", value={"answers": {"already_applied": "no"}})
    got = search.apply()
    assert got["ok"] == [aid] and search.files_hash() == before
    with open(got["batches"][0], encoding="utf-8") as fh:
        batch = json.load(fh)
    work = next(e for e in batch if e["collection"] == "work")
    assert work["doc_id"].startswith("draft~") and "if_version" not in work
    with open(work["file_path"], encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["status"] == "queued" and doc["kind"] == "draft"
    assert doc["args"]["company"] == "Dovecote Freight" and doc["answers"]["already_applied"] == "no"
    assert [s["name"] for s in doc["stages"]][0] == "Getting started"


def test_a_filtered_posting_comes_back_and_a_question_is_answered(search):
    back = search.act("job.bring_back", "r9-f1")
    said = search.act("ready.applied", "q-app-dovecote_freight_inventory_analyst")
    plan = search.act("setting.set", "setting-linkedin_plan", value={"value": "free"})
    got = search.apply()
    assert got["ok"] == [back, said, plan]
    m = search.model()
    assert [r["company"] for r in m["jobs"]["rows"]][-1] == "Quayside Foods"
    assert [q for q in m["needs_you"] if q["kind"] == "confirm"] == []
    assert search.tracker_row("Dovecote Freight")["status"] == "applied"
    with open(os.path.join(search.profile, "networking.py"), encoding="utf-8") as fh:
        assert 'LINKEDIN_PLAN = "free"' in fh.read()
    assert {s["key"]: s["value"] for s in m["settings"]}["linkedin_plan"] == "free"


def test_a_receipt_names_nobody_in_full(search):
    pell = search.item("kestrel_mutual_ansgar")
    aid = search.act("person.stop", "kestrel_mutual_ansgar", rev=pell["rev"],
                     value={"why": "not right now"})
    sent = search.act("msg.unsent", "kestrel_mutual_ansgar", rev=pell["rev"])
    search.apply()
    for a in (aid, sent):
        text = json.dumps(search.receipt(a))
        assert "Ansgar" not in text and "@" not in text
    assert search.receipt(sent)["result"] == "stale"      # the stop changed them first


def test_actions_another_chat_claimed_are_left_to_it(search):
    aid = search.act("ready.applied", KESTREL)
    claimed = search.apply("--claim")
    assert claimed["claimed"] == [aid]
    with open(claimed["batches"][0], encoding="utf-8") as fh:
        entry = json.load(fh)[0]
    assert entry["if_version"] == 1 and entry["collection"] == "actions"
    with open(os.path.join(search.dump, "actions", aid + ".json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    doc.update(claimed_by="computer-1", claimed_until="2026-10-25T18:30:00Z")
    search.put("actions", aid, doc, version=2)
    before = search.files_hash()
    got = search.apply()
    assert got["ok"] == [] and search.files_hash() == before


# ------------------------------------------------------------------ next: who takes the work


def _db(*items, locks=None, chats=None):
    work = {wid: {"data": d, "version": n + 1} for n, (wid, d) in enumerate(items)}
    return {"work": work, "locks": locks or {}, "chats": chats or {}}


def _w(kind, company="", to=None, status="queued", asked="2026-10-25T10:00:00Z", **kw):
    d = {"kind": kind, "status": status, "asked_at": asked, "args": {"company": company}}
    if to:
        d["to"] = to
    d.update(kw)
    return d


def test_next_gives_one_job_per_employer_and_the_oldest_first():
    now = app_model.parse_time(NOW)
    db = _db(("d1", _w("draft", "Kestrel Mutual", status="running", claimed_by="c",
                       stage_at="2026-10-25T17:55:00Z")),
             ("d2", _w("draft", "Kestrel Mutual", asked="2026-10-25T09:00:00Z")),
             ("d3", _w("draft", "Larkspur Retail", asked="2026-10-25T11:00:00Z")),
             ("d4", _w("draft", "Fernhill Freight", asked="2026-10-25T10:30:00Z")))
    got = page_db.next_item(db, "cloud", now)
    assert got["work"] == "d4"            # Kestrel is held by d1; d4 was asked before d3
    assert got["locks"] == ["emp~fernhill_freight"] and got["version"] == 4


def test_a_finished_or_stalled_job_frees_its_lock():
    now = app_model.parse_time(NOW)
    locks = {"emp~kestrel_mutual": {"data": {"work": "d1", "until": "2026-10-25T19:00:00Z"},
                                    "version": 3}}
    db = _db(("d1", _w("draft", "Kestrel Mutual", status="done")),
             ("d2", _w("draft", "Kestrel Mutual")), locks=locks)
    got = page_db.next_item(db, "cloud", now)
    assert got["work"] == "d2"
    db["work"]["d1"]["data"].update(status="running", stage_at="2026-10-25T09:00:00Z")
    assert page_db.next_item(db, "cloud", now)["work"] == "d2"   # no step for hours: stalled


def test_the_chat_that_answers_the_page_takes_its_work_and_a_brief_waits_for_the_cloud():
    """One chat answers the page (tools/app_listen.py), so work never waits for a chat of the
    other kind: a setting that sent it there stranded it (4.3). Only a brief, which comes with
    the computer off, waits for a chat in the cloud."""
    now = app_model.parse_time(NOW)
    assert page_db.next_item(_db(("s1", _w("search", to="cloud"))), "computer", now)["work"] == "s1"
    assert page_db.next_item(_db(("s1", _w("search", to="computer"))), "cloud", now)["work"] == "s1"
    only_brief = _db(("b1", _w("brief", to="computer")))
    assert page_db.next_item(only_brief, "computer", now) is None
    assert page_db.next_item(only_brief, "cloud", now)["work"] == "b1"


def test_the_heavy_cap_holds_and_urgent_work_goes_first():
    """Three big jobs side by side (a search, a networking run and an interview prep, the
    maintainer's own example, 2026-10-29), an urgent one more, and light work any time."""
    now = app_model.parse_time(NOW)
    assert page_db.HEAVY_CAP == 3
    two = [(f"n{i}", _w("network", f"Employer {i}", status="running",
                        stage_at="2026-10-25T17:59:00Z")) for i in range(2)]
    third = _db(*two, ("d1", _w("draft", "Kestrel Mutual", asked="2026-10-25T11:00:00Z")))
    assert page_db.next_item(third, "cloud", now)["work"] == "d1"   # a third runs beside them
    running = [(f"n{i}", _w("network", f"Employer {i}", status="running",
                            stage_at="2026-10-25T17:59:00Z")) for i in range(3)]
    db = _db(*running, ("d1", _w("draft", "Kestrel Mutual", asked="2026-10-25T11:00:00Z")),
             ("t1", _w("talk", asked="2026-10-25T12:00:00Z")))
    assert page_db.next_item(db, "cloud", now)["work"] == "t1"     # the fourth waits; talk goes
    db["work"]["d2"] = {"data": _w("prep", "Thornbury Bank", priority=2), "version": 9}
    assert page_db.next_item(db, "cloud", now)["work"] == "d2"     # urgent takes one more place
    db["work"]["d2"]["data"]["stop_asked"] = True
    assert page_db.next_item(db, "cloud", now)["work"] == "t1"


def test_next_writes_its_claim_pinned_with_its_locks(search):
    search.put("work", "draft~abc", _w("draft", "Kestrel Mutual"), version=5)
    search.put("locks", "emp~kestrel_mutual", {"work": "draft~old", "until": "2026-10-24T00:00:00Z"},
               version=2)
    out = search.run("next", search.dump, "--chat", "cloud-1", "--kind", "cloud",
                     "--now", NOW, "--claim-out", os.path.join(search.dump, "claim"))
    got = json.loads(out)
    with open(got["batches"][0], encoding="utf-8") as fh:
        batch = json.load(fh)
    assert [(e["collection"], e["doc_id"], e.get("if_version")) for e in batch] == [
        ("work", "draft~abc", 5), ("holds", "emp~kestrel_mutual", 2), ("beats", "cloud-1", None)]
    # A chat of the other kind may be offered the same item; the claim is pinned to version 5,
    # so only one write of the two can win.
    again = json.loads(search.run("next", search.dump, "--chat", "c2", "--kind", "computer",
                                  "--now", NOW))
    assert again["work"] == "draft~abc" and again["version"] == 5


def test_a_fact_to_confirm_is_answered_where_its_mark_was(search):
    path = os.path.join(search.profile, "01-candidate-profile.md")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text + "\nNotice period: [CONFIRM: your notice period]\n")
    item = next(q for q in search.model()["needs_you"] if q["id"].startswith("q-fact-"))
    assert item["title"] == "Your notice period?"
    aid = search.act("needs.answer", item["id"], value={"text": "one month"})
    assert search.apply()["ok"] == [aid]
    with open(path, encoding="utf-8") as fh:
        assert fh.read().endswith("\nNotice period: one month\n")
    search.written_back()
    undo = search.act("undo", undoes=aid)
    assert search.apply()["ok"] == [undo]
    with open(path, encoding="utf-8") as fh:
        assert fh.read().endswith("\nNotice period: [CONFIRM: your notice period]\n")


def _page_stage_kinds() -> set:
    """The kinds whose stages the page reads: the engine's own table, embedded when the page
    is built (app_page.tables()), never a copy kept in app.js."""
    import app_page
    with open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8") as fh:
        js = fh.read()
    assert "ljs-tables" in js and not re.search(r"const STAGES = \{\n\s+search:", js), "no copy of the table in the page"
    page = app_page.render({"model": 1})
    assert '<script type="application/json" id="ljs-tables">' in page
    return set(app_page.tables()["stages"])


def _page_work_kinds() -> set:
    """Every kind of work the page asks for (requestWork and createWork calls)."""
    with open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8") as fh:
        js = fh.read()
    return set(re.findall(r"\bkind: \"(\w+)\",\s*(?:to|title)\b", js))


# Kinds of work the page asks for that the work list does not have yet: each is the engine
# builder's to add (CAPABILITY_MAP and the LinkedIn flows). Until it is, `next` skips it, so
# the list is kept here, named, and the test fails once one exists.
ENGINE_TODO_KINDS: dict = {}


def test_the_page_and_the_work_list_name_the_same_kinds_of_work():
    """A kind the page asks for that the work list does not know is never claimed: `next`
    skips it for ever (the page's "Make the files downloadable" did exactly that)."""
    assert set(page_db.STAGES) == set(page_db.WORK_KINDS)
    assert _page_stage_kinds() == set(page_db.WORK_KINDS)
    asked = _page_work_kinds()
    assert {"search", "draft", "files", "talk", "brief"} <= asked, asked
    # An update is queued by the engine from the page's "Update now" (app.update_now), so
    # it is one kind the work list has that the page never asks for by itself.
    assert "app.update_now" in app_actions.ACTIONS and "update" in page_db.WORK_KINDS
    assert asked <= set(page_db.WORK_KINDS) | set(ENGINE_TODO_KINDS), asked - set(page_db.WORK_KINDS) - set(ENGINE_TODO_KINDS)
    assert not set(ENGINE_TODO_KINDS) & set(page_db.WORK_KINDS), ("the work list has these now: take them off ENGINE_TODO_KINDS",
                                                                  set(ENGINE_TODO_KINDS) & set(page_db.WORK_KINDS))
    due = {a.split(":", 1)[1] for a in app_model._DUE_WORK.values()} | {"resume_for_contact"}
    assert due <= set(page_db.WORK_KINDS), due - set(page_db.WORK_KINDS)   # the page's askDue
    now = app_model.parse_time(NOW)
    for kind in sorted(page_db.WORK_KINDS):
        to = "cloud" if "cloud" in page_db.WORK_KINDS[kind]["can"] else "computer"
        db = _db(("w1", _w(kind, "Kestrel Mutual", to=to)))
        got = page_db.next_item(db, to, now)
        assert got and got["work"] == "w1", kind


def test_a_tweak_and_a_draft_for_one_employer_never_run_at_once():
    now = app_model.parse_time(NOW)
    draft = ("d1", _w("draft", "Kestrel Mutual", status="running", stage_at="2026-10-25T17:59:00Z"))
    tweak = ("t1", {"kind": "tweak", "status": "queued", "asked_at": "2026-10-25T10:00:00Z",
                    "args": {"target": {"id": "app-kestrel", "company": "Kestrel Mutual"}}})
    assert page_db.locks_for(tweak[1]) == ["emp~kestrel_mutual"]
    assert page_db.locks_for({"kind": "tweak", "args": {"target": {
        "id": "msg-c1", "output": "message", "contact": "c1"}}}) == ["contact~c1"]
    assert page_db.next_item(_db(draft, tweak), "cloud", now) is None
    assert page_db.next_item(_db(tweak), "cloud", now)["work"] == "t1"


def test_an_update_that_changes_stored_records_waits_for_running_work_and_goes_first():
    """UX decisions, "Updates while work runs": a code-only update holds only its own lock; one
    that changes how a record file is stored waits for running jobs to land, and work asked for
    meanwhile starts after it."""
    now = app_model.parse_time(NOW)
    running = ("d1", _w("draft", "Kestrel Mutual", status="running",
                       stage_at="2026-10-25T17:59:00Z"))
    code = ("u1", _w("update", asked="2026-10-25T09:00:00Z", args={"sha": "a", "migration": False}))
    db = _db(running, code, ("t1", _w("talk", asked="2026-10-25T12:00:00Z")))
    assert page_db.next_item(db, "cloud", now)["work"] == "u1"
    migration = ("u2", _w("update", asked="2026-10-25T09:00:00Z",
                          args={"sha": "b", "migration": True}))
    db = _db(running, migration, ("t1", _w("talk", asked="2026-10-25T12:00:00Z")))
    assert page_db.after_update(db)
    assert page_db.next_item(db, "cloud", now) is None          # the draft is still running
    db["work"]["d1"]["data"]["status"] = "done"
    assert page_db.next_item(db, "cloud", now)["work"] == "u2"   # it goes first
    db["work"]["u2"]["data"].update(status="running", stage_at="2026-10-25T17:59:30Z")
    assert page_db.next_item(db, "cloud", now) is None          # the talk starts after it
    db["work"]["u2"]["data"]["status"] = "done"
    assert page_db.next_item(db, "cloud", now)["work"] == "t1"
