"""Each choice in a bin changes what it says it changes, and its undo puts all of it back.

The maintainer, 2026-10-29, asked that the bin's choices really change things under the
hood. A person's bin: not this person (closed); not the employer any more (them,
everyone there not yet written to, and the employer turned down by name); in touch another
way (no note drafted, the route kept). A job's bin: pay, place and field teach the next
ranking a rule about roles like it, not a note about one posting. Every person and employer
is invented (tests/app_state.py).
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

from test_a_tick_on_the_page_is_applied_once import Search  # noqa: E402

ANSGAR = "kestrel_mutual_ansgar"


@pytest.fixture
def search(tmp_path):
    s = Search(str(tmp_path))
    path = os.path.join(s.state, "network_contacts.csv")
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
        cols = list(rows[0].keys())
    base = next(r for r in rows if r["contact_id"] == ANSGAR)
    rows.append(dict(base, contact_id="kestrel_mutual_orrin", name="Orrin Vale",
                     status="not_contacted", next_action="", next_action_due=""))
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return s


def _status(search, cid):
    with open(os.path.join(search.state, "network_contacts.csv"), encoding="utf-8") as fh:
        return next(r for r in csv.DictReader(fh) if r["contact_id"] == cid)["status"]


def _declined(search, company):
    env = dict(os.environ, LJS_PROFILE=search.profile, LJS_STATE=search.state)
    code = "import sys; sys.path.insert(0, %r); import bar; print(bar.excluded_by_name(%r))" % (
        os.path.join(ROOT, "tools"), company)
    return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                          encoding="utf-8", timeout=60).stdout.strip()


def test_not_this_person_closes_them_alone(search):
    a = search.act("person.stop", ANSGAR, value={"why": "not the right person", "scope": "person"})
    assert search.apply()["ok"] == [a]
    assert _status(search, ANSGAR) == "closed"
    assert _status(search, "kestrel_mutual_orrin") == "not_contacted"
    assert not _declined(search, "Kestrel Mutual")


def test_not_the_employer_any_more_closes_everyone_unwritten_there_and_turns_it_down(search):
    a = search.act("person.stop", ANSGAR, value={"why": "not interested in Kestrel Mutual any more",
                                                 "scope": "employer", "employer": "Kestrel Mutual"})
    assert search.apply()["ok"] == [a]
    assert _status(search, ANSGAR) == "closed"
    assert _status(search, "kestrel_mutual_orrin") == "closed"      # not yet written to: closed too
    assert _status(search, "fernhill_freight_halloway") == "awaiting_reply"   # another employer
    assert _declined(search, "Kestrel Mutual"), "no more roles from it either"
    note = search.receipt(a)["note"]
    assert "and 1 more there" in note and "Kestrel Mutual" in note
    # Undo puts every part back.
    search.written_back()
    u = search.act("undo", undoes=a)
    assert search.apply()["ok"] == [u], search.receipt(u)
    assert _status(search, ANSGAR) == "not_contacted"
    assert _status(search, "kestrel_mutual_orrin") == "not_contacted"
    assert not _declined(search, "Kestrel Mutual")


def test_in_touch_another_way_drafts_no_note_and_keeps_the_route(search):
    a = search.act("person.stop", ANSGAR, value={"why": "already in touch another way", "scope": "other"})
    assert search.apply()["ok"] == [a]
    assert _status(search, ANSGAR) == "in_conversation"
    assert all(m["id"] != "msg-" + ANSGAR for m in search.model()["messages"])
    assert not _declined(search, "Kestrel Mutual")
    folder = os.path.join(search.state, "documents", "network", ANSGAR)
    assert os.path.exists(os.path.join(folder, "draft.not-needed.md")), "the note is kept, not deleted"
    search.written_back()
    u = search.act("undo", undoes=a)
    assert search.apply()["ok"] == [u], search.receipt(u)
    assert _status(search, ANSGAR) == "not_contacted"
    assert any(m["id"] == "msg-" + ANSGAR for m in search.model()["messages"])


@pytest.mark.parametrize("why,words", [
    ("pay", "the pay was not enough for them"),
    ("place", "the place did not suit them"),
    ("field", "Not their field: rank lower roles like"),
])
def test_a_job_binned_for_its_pay_place_or_field_teaches_the_next_ranking(search, why, words):
    a = search.act("job.dismiss", "r9-1", value={"why": why})
    assert search.apply()["ok"] == [a]
    with open(os.path.join(search.profile, "learned.json"), encoding="utf-8") as fh:
        entry = json.load(fh)["entries"][-1]
    assert entry["area"] == "jobs" and words in entry["rule"], entry
    assert {r["id"]: r["status"] for r in search.model()["jobs"]["rows"]}["r9-1"] == "dismissed"


def test_a_closed_posting_or_this_role_alone_teaches_nothing(search):
    for why in ("closed", "not this role"):
        s = search
        a = s.act("job.dismiss", "r9-1", value={"why": why})
        assert s.apply()["ok"] == [a]
        path = os.path.join(s.profile, "learned.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                assert not [e for e in json.load(fh).get("entries", []) if e.get("area") == "jobs"]
        s.written_back()
        u = s.act("undo", undoes=a)
        assert s.apply()["ok"] == [u]


def test_an_interview_and_an_application_put_in_the_bin_are_closed_in_the_tracker(search):
    m = search.model()
    iv = m["interviews"][0]
    a = search.act("outcome.withdrawn", iv["id"], value={"on": "2026-10-25"}, rev=iv["rev"])
    got = search.apply()
    assert got["ok"] == [a], search.receipt(a)
    live = [x for x in search.model()["interviews"] if x["id"] == iv["id"] and x.get("status") != "done"]
    assert not live or all(x.get("status") in ("withdrawn", "closed", "done") for x in live)
    app = next(x for x in m["applications"] if x["status"] == "applied")
    b = search.act("outcome.no_response", app["id"], value={"on": "2026-10-25"}, rev=app["rev"])
    got = search.apply()
    assert got["ok"] == [b], search.receipt(b)
    after = next(x for x in search.model()["applications"] if x["id"] == app["id"])
    assert after["status"] in ("no_response", "closed"), after["status"]
