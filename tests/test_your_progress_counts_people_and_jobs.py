"""Your progress, on the Brief, counts people as well as jobs, chosen for the person.

The maintainer, 2026-11-10, on the panel that counted only applications: "should we change
things here to be both jobs and people, not just jobs? ... dont overwhelm but also make it
pretty, useful, and not make it look like im doing nothing ... be individual, what would fit a
particular person ... but make it work." So the engine (app_model._glance) picks at most four
tiles from what is true for this person now, from both sides; a nought is never shown beside
real work; one "what's working" line is said only when the person's own numbers carry it; and
the weeks' chart shows applications and messages sent.

Three invented people, none of them real: a nurse in Vancouver applying a lot and writing to
almost nobody, a remote software engineer writing to many and applying little, and a career
changer just starting. Their employers and contacts are invented too.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app_model  # noqa: E402

TODAY = dt.date(2026, 11, 10)


def _day(n: int) -> str:
    return (TODAY - dt.timedelta(days=n)).isoformat()


def _ctx(tracker=(), contacts=(), threads=()):
    ctx = app_model.Ctx(TODAY, dt.datetime(2026, 11, 10, 9, 0, tzinfo=dt.timezone.utc))
    ctx._got.update(tracker=list(tracker), contacts=list(contacts), threads=list(threads))
    return ctx


def _app(company, days_ago, status="applied", role="Staff Nurse"):
    return {"company": company, "role": role, "status": status, "applied_on": _day(days_ago),
            "date": _day(days_ago)}


def _person(cid, company, title="Software Engineer", status="awaiting_reply"):
    return {"contact_id": cid, "name": cid.replace("_", " ").title(), "title": title,
            "company": company, "status": status}


def _out(cid, days_ago, text="Hi, hope you're well. I'd love to hear what you're working on."):
    return {"contact_id": cid, "date": _day(days_ago), "direction": "out", "channel": "linkedin",
            "scenario": "first_note", "summary": "a note", "full_text": text}


def _in(cid, days_ago, text="Happy to chat, what times suit you?"):
    return {"contact_id": cid, "date": _day(days_ago), "direction": "in", "channel": "linkedin",
            "scenario": "detailed_generous", "summary": "a reply", "full_text": text}


def _accepted(cid, days_ago):
    return {"contact_id": cid, "date": _day(days_ago), "direction": "in", "channel": "linkedin",
            "scenario": "connection_accepted", "summary": "", "full_text": ""}


def _glance(ctx):
    done = app_model._done(ctx, {})
    return done, done["glance"]


def _tiles(g):
    return {t["k"]: t for t in g["tiles"]}


def _nurse():
    """Thirty applications to hospitals and clinics this month, two at interview, and one note."""
    tracker = [_app("Harbour Health %d" % i, 2 + i % 25) for i in range(28)]
    tracker += [_app("Tallowmere Clinic", 6, "interview"), _app("Quillfen Care", 12, "interview")]
    contacts = [_person("ana_reyes", "Brackenlow Hospital", "Nurse Manager")]
    return _ctx(tracker, contacts, [_out("ana_reyes", 3)])


def _engineer():
    """Forty first notes this month, recruiters answering far more than peers, two applications
    long ago, a call booked."""
    contacts, threads = [], []
    for i in range(12):
        cid = "rec_%d" % i
        contacts.append(_person(cid, "Brightloop %d" % i, "Talent Acquisition Partner",
                                "in_conversation" if i < 6 else "awaiting_reply"))
        threads.append(_out(cid, 25))
        if i < 6:
            threads.append(_in(cid, 22))
    for i in range(28):
        cid = "peer_%d" % i
        contacts.append(_person(cid, "Quillstack %d" % i, "Software Engineer",
                                "in_conversation" if i < 3 else "connected_no_reply"))
        threads.append(_out(cid, 24))
        threads.append(_accepted(cid, 20))
        if i < 3:
            threads.append(_in(cid, 18))
    contacts[0]["status"] = "call_booked"
    tracker = [_app("Quillstack 1", 70, role="Backend Engineer"), _app("Ferncode", 80, role="Backend Engineer")]
    return _ctx(tracker, contacts, threads)


def test_a_nurse_who_applies_a_lot_sees_her_applications_and_her_one_note():
    done, g = _glance(_nurse())
    t = _tiles(g)
    assert len(g["tiles"]) <= 4
    assert t["applied"]["n"] == 30 and t["interviews"]["n"] == 2
    # The rate from applied to interview, said only past five applications.
    assert t["interviews"]["share"] == "7% of applied"
    # People too, though she wrote to one person: her side of it is real work.
    assert t["sent"]["n"] == 1 and t["sent"]["label"] == "message sent"
    # Nothing is a nought beside real work, and nothing claims a pattern from one note.
    assert all(x["n"] > 0 for x in g["tiles"]), g["tiles"]
    assert g["working"] is None
    assert [k for k in ("replies", "offers", "accepted") if k in t] == []
    assert done["recent"]["counts"]["sent"] == 1


def test_an_engineer_who_networks_a_lot_sees_people_first_and_what_works():
    done, g = _glance(_engineer())
    t = _tiles(g)
    # Applied nothing this month: no "0 applied" beside forty notes.
    assert "applied" not in t and "interviews" not in t, g["tiles"]
    assert t["sent"]["n"] == 40 and t["replies"]["n"] == 9 and t["calls"]["n"] == 1
    assert t["replies"]["share"] == "22% answered"
    assert len(g["tiles"]) == 4 and all(x["n"] > 0 for x in g["tiles"])
    # The kind of person who answers, from his own numbers: 6 of 12 recruiters, 3 of 28 peers.
    assert g["working"] == "Recruiters answer most: 6 of 12 first notes; everyone else 3 of 28."
    # The weeks count his messages as well as his applications.
    assert sum(w["sent"] for w in done["weeks"]) == 40
    assert sum(w["applied"] for w in done["weeks"]) == 0


def test_a_career_changer_with_nothing_yet_sees_where_to_start_and_no_claim():
    _done, g = _glance(_ctx())
    assert [(x["k"], x["n"]) for x in g["tiles"]] == [("applied", 0), ("sent", 0)]
    assert g["working"] is None


def test_a_career_changer_with_two_notes_sees_the_notes_not_noughts():
    contacts = [_person("sam_okafor", "Mossgate Studio", "UX Designer"),
                _person("lee_marsh", "Kitebank", "Product Designer")]
    threads = [_out("sam_okafor", 4), _accepted("sam_okafor", 2), _out("lee_marsh", 3)]
    _done, g = _glance(_ctx((), contacts, threads))
    assert [(x["k"], x["n"], x["label"]) for x in g["tiles"]] == [
        ("sent", 2, "messages sent"), ("accepted", 1, "accepted your request")]
    assert g["working"] is None


def _warm_and_cold(warm_hits, warm_n, cold_hits, cold_n):
    tracker, contacts, threads = [], [], []
    for i in range(warm_n):
        company = "Talked %d" % i
        tracker.append(_app(company, 20, "interview" if i < warm_hits else "rejected"))
        cid = "inside_%d" % i
        contacts.append(_person(cid, company, "Operations Lead", "in_conversation"))
        threads += [_out(cid, 40), _in(cid, 38)]
    for i in range(cold_n):
        tracker.append(_app("Cold %d" % i, 20, "interview" if i < cold_hits else "rejected"))
    return _ctx(tracker, contacts, threads)


def test_applications_where_someone_talked_with_them_are_said_to_work_only_with_enough():
    _done, g = _glance(_warm_and_cold(3, 6, 1, 12))
    assert g["working"] == ("Where you'd talked to someone there, 3 of 6 applications got an "
                            "interview; elsewhere 1 of 12.")
    # The combined tile: interviews still live at an employer where someone talked with them.
    assert _tiles(g)["warm"]["n"] == 3
    # Too few to say anything: two of three is an anecdote.
    _done, g = _glance(_warm_and_cold(2, 3, 0, 12))
    assert g["working"] is None
    # And no line where talking did no better.
    _done, g = _glance(_warm_and_cold(1, 6, 4, 12))
    assert g["working"] is None or not g["working"].startswith("Where you'd")


def test_every_tile_reads_in_plain_words_with_its_number():
    for ctx in (_nurse(), _engineer()):
        _done, g = _glance(ctx)
        for x in g["tiles"]:
            assert x["label"] and x["short"] and x["side"] in ("jobs", "people", "both"), x
            assert x["label"] == app_model._GLANCE_WORDS[x["k"]][0][0 if x["n"] == 1 else 1]
