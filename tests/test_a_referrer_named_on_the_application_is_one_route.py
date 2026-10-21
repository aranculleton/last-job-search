""""Apply and put me down as your referrer" is one route, said one way everywhere.

The reply guidance said the resume goes in through the portal with their name where it asks
for a referrer, not to them. Staging and the tracker note said it goes to them, not
through the portal, and once the row was applied RECONCILE asked the person to log a
message to the contact that never went. Now staging carries the route (`--referral-field`,
or what the contact said last), and the tracker note, outreach.md and RECONCILE follow it.
Every person, employer and message here is invented; the candidate is the example person.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import outreach  # noqa: E402
import record_drafts  # noqa: E402
import reply  # noqa: E402
import schema  # noqa: E402
import stage_picks  # noqa: E402
import state  # noqa: E402

TODAY = "2026-10-21"
CID = "kes_castellan"
NAME_ME = "Happy to help. Apply through the careers site and put me down as your referrer."
# How the portal route is said, word for word, in staging and the tracker note.
PORTAL = "it goes in through the portal, with their name where it asks for a referrer, not to them"
POSTING = ("Pricing Analyst. A permanent role in our Manchester team, hybrid. You will own the "
           "weekly pricing model in SQL and Python and work with the pricing lead.")


def _write(path, rows, columns):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in columns} for r in rows)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    _write(root / "network_contacts.csv",
           [{"contact_id": CID, "name": "Juno Castellan", "title": "Pricing Lead",
             "company": "Kestrel Mutual", "status": "in_conversation", "channel": "message"}],
           schema.CONTACT_COLUMNS)
    _write(root / "network_threads.csv",
           [{"contact_id": CID, "date": "2026-10-10", "direction": "out", "channel": "message",
             "scenario": "first_message", "summary": "First message sent",
             "full_text": "Hi Juno, a question about the pricing team at Kestrel."},
            {"contact_id": CID, "date": "2026-10-12", "direction": "in", "channel": "message",
             "scenario": "", "summary": "replied", "full_text": NAME_ME}],
           schema.THREAD_COLUMNS)
    _write(root / "job_search_tracker.csv", [], record_drafts.HEADER)
    monkeypatch.setenv("LJS_STATE", str(root))
    return root


def _pick():
    return {"company": "Kestrel Mutual", "title": "Pricing Analyst", "portal": "pasted",
            "url": "https://jobs.example/kestrel/12", "location": "Manchester", "desc": POSTING,
            "fit": 72}


def _record(repo, apps_in):
    meta = dict(apps_in[0])
    draft = {"company": "Kestrel Mutual", "role": "Pricing Analyst", "abbr": meta["abbr"],
             "for_contact": CID}
    [(_, row)] = record_drafts.record([draft], {meta["abbr"].upper(): meta}, TODAY,
                                      path=str(repo / "job_search_tracker.csv"))
    return draft, meta, row


def _findings(repo, tracker):
    contacts = state.load_contacts(str(repo / "network_contacts.csv"))
    threads = state.load_threads(str(repo / "network_threads.csv"))
    return [f["reason"] for f in state.resume_findings(contacts, threads, tracker)]


@pytest.mark.parametrize("flag", [True, None])
def test_apply_and_name_me_goes_through_the_portal_everywhere(repo, capsys, flag):
    portal = PORTAL
    # The guidance names the route and the flag that carries it.
    got = reply.guidance(reply.classify(NAME_ME), NAME_ME, contact_id=CID)
    assert "--referral-field" in got["which_resume"] and portal in got["which_resume"].lower()
    # Staged with the flag, or without it (read from what they said last): the same route.
    kw = {} if flag is None else {"referral_field": flag}
    staged = stage_picks.stage(str(repo / "r1"), ["1"], rows=[], root=str(repo),
                               shortlist=[_pick()], for_contact=CID, today=TODAY, **kw)
    assert staged[0].get("for_contact_route") == "portal"
    assert staged[0]["for_contact_channel"] == "referral"
    stage_picks._report(staged, str(repo / "r1"))
    said = capsys.readouterr().out
    assert portal in said and "it goes to them" not in said
    picks = json.loads((repo / "r1" / "picks.json").read_text(encoding="utf-8"))
    assert portal in Path(picks[0]["file"]).read_text("utf-8")
    apps_in = json.loads((repo / "r1" / "apps_in.json").read_text(encoding="utf-8"))
    draft, meta, row = _record(repo, apps_in)
    assert portal in row["notes"] and "it goes to them" not in row["notes"]
    assert row["channel"] == "referral" and row["contact_person"] == "Juno Castellan"
    # outreach.md says to apply naming them, and never to log a message to them.
    a = dict(draft, posting=POSTING, p1="x.", p2="y.", lead="", cl_bullets=[], p4="",
             summary="", tools="")
    md = (Path(outreach.write(a, meta, TODAY)) / "outreach.md").read_text(encoding="utf-8")
    assert "through the portal, with Juno Castellan named as your referrer" in md
    assert "state.py message" not in md
    # Applied through the portal under their name: nothing for RECONCILE to ask for, and
    # nothing owed to them.
    for status in ("drafted", "applied"):
        tracker = [dict(row, status=status)]
        assert _findings(repo, tracker) == [], status
        assert state.resumes_owed(state.load_contacts(str(repo / "network_contacts.csv")),
                                  state.load_threads(str(repo / "network_threads.csv")),
                                  tracker) == []


def test_a_row_made_before_the_route_was_kept_is_read_from_their_thread(repo):
    # A tracker row written before staging carried the route says "it goes to them", but
    # what they said was to apply and name them: RECONCILE asks for no message.
    row = {"date": "2026-10-13", "company": "Kestrel Mutual", "role": "Pricing Analyst",
           "channel": "referral", "status": "applied", "contact_person": "Juno Castellan",
           "notes": f"Made for Juno Castellan ({CID}), who asked for it: it goes to them, not "
                    "through the portal.",
           "cv_file": "cv/Morgan_Ellis_CV_Kestrel.tex", "source": "https://jobs.example/k/12"}
    assert _findings(repo, [row]) == []


def test_a_resume_they_asked_to_receive_still_goes_to_them(repo):
    ask = "Send me your CV and I'll pass it on to the pricing lead."
    _write(repo / "network_threads.csv",
           [{"contact_id": CID, "date": "2026-10-10", "direction": "out", "channel": "message",
             "scenario": "first_message", "summary": "First message sent",
             "full_text": "Hi Juno, a question about the pricing team at Kestrel."},
            {"contact_id": CID, "date": "2026-10-12", "direction": "in", "channel": "message",
             "scenario": "", "summary": "replied", "full_text": ask}],
           schema.THREAD_COLUMNS)
    staged = stage_picks.stage(str(repo / "r1"), ["1"], rows=[], root=str(repo),
                               shortlist=[_pick()], for_contact=CID, today=TODAY)
    assert staged[0]["for_contact_route"] == state.ROUTE_TO_THEM
    apps_in = json.loads((repo / "r1" / "apps_in.json").read_text(encoding="utf-8"))
    _, _, row = _record(repo, apps_in)
    assert state.route_words(state.ROUTE_TO_THEM) in row["notes"]
    # Applied, and nothing in their thread says it reached them: RECONCILE still asks.
    assert "resume_not_logged" in _findings(repo, [dict(row, status="applied")])
