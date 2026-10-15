"""What an audit of a real contact book found in the networking tools.

- a connection request nobody accepted was listed as a nudge, a message with nowhere
  to go; someone who accepted a request with no note was owed a nudge on a note
  never sent;
- a held call counted as our message last, so the thread "went silent";
- a nudge opening on a one-word name lowercased it ("Hi Robin, larkspur opened..."),
  and validate() passed check-ins ("just checking in", "bumping this");
- any "we're hiring" made the poster tier 1, whatever the job;
- the question at the end of a first note was compulsory, which is what produced the
  made-up questions the person hated;
- every save rewrote a CRLF file as LF, so one logged message changed every line;
- "J. Smith" was greeted "Hi J,", and "I'm" at the start of a sentence was refused;
- a close the person chose was reported as "reopened" on every run, and two names
  for one employer never joined and nothing said so.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import company_key  # noqa: E402
import compose  # noqa: E402
import discovery as D  # noqa: E402
import reply  # noqa: E402
import state  # noqa: E402
import tone  # noqa: E402

TODAY = "2026-10-15"
CONTACT = {"contact_id": "acme_reed", "name": "Sasha Reed", "company": "Acme", "status": ""}


def _row(date, direction, scenario="", text="", channel="linkedin"):
    return {"contact_id": "acme_reed", "date": date, "direction": direction,
            "channel": channel, "scenario": scenario, "summary": "", "full_text": text}


def _kinds(rows, contact=CONTACT):
    return [i["kind"] for i in state.owed([contact], rows, TODAY)]


# ------------------------------------------------------------------ what is owed

def test_a_pending_request_is_never_a_nudge():
    recent = [_row("2026-10-01", "out", "connection_request", "Hi Sasha, we were both at Leeds.")]
    assert _kinds(recent) == []
    old = [_row("2026-09-01", "out", "connection_request", "Hi Sasha, we were both at Leeds.")]
    assert _kinds(old) == ["request_pending"]
    assert not reply.nudge_due(old, TODAY)["due"]
    assert "not been accepted" in reply.nudge_due(old, TODAY)["reason"]


def test_an_acceptance_of_a_bare_request_is_owed_a_first_message():
    rows = [_row("2026-09-01", "out", "connection_request"),
            _row("2026-09-03", "in", "accepted_no_reply")]
    assert _kinds(rows) == ["first_message"]
    assert "first message" in reply.nudge_due(rows, TODAY)["reason"]
    with_note = [_row("2026-09-01", "out", "connection_request", "Hi Sasha, we were both at Leeds."),
                 _row("2026-09-03", "in", "accepted_no_reply")]
    assert _kinds(with_note) == ["nudge"]


def test_a_held_call_is_a_conversation_not_our_message_last():
    rows = [_row("2026-08-01", "out", "first_note", "Hi Sasha"),
            _row("2026-08-02", "in", "", "Happy to talk"),
            _row("2026-08-10", "out", "call_held", channel="call")]
    assert state.derive_status(rows) == "in_conversation"
    assert _kinds(rows) == []
    assert not reply.nudge_due(rows, TODAY)["due"]


# ------------------------------------------------------------------ what is written

def test_a_nudge_keeps_the_capital_on_a_name_it_knows():
    assert compose.nudge("Robin Vale", "Larkspur opened a planning role").startswith(
        "Hi Robin, Larkspur opened")
    assert compose.nudge("Robin Vale", "Python is now in the stack").startswith("Hi Robin, Python")
    assert compose.nudge("Robin Vale", "Saw the planning team has grown").startswith("Hi Robin, saw")
    found = compose.validate("Hi Robin, larkspur has opened a role", "nudge")
    assert ("lowercase_name", "larkspur") in [(v.rule, v.text) for v in found]


def test_check_in_wording_is_refused_and_a_status_question_is_not():
    for text in ("Hi Robin, just checking in to see if you had a chance to look at my note",
                 "Hi Robin, bumping this to the top of your inbox",
                 "Hi Robin, did you get a chance to see my last message?"):
        assert "check_in" in [v.rule for v in compose.validate(text, "nudge")], text
    ok = compose.validate("Thanks Robin. Any update on the timing?", "reply")
    assert "check_in" not in [v.rule for v in ok]


def test_a_first_note_needs_no_made_up_question():
    note = compose.first_note("Sasha Reed", "we were both at Leeds", None,
                              ask="Would you have fifteen minutes for a call one week?")
    assert "?" in note and note.count("?") == 1
    try:
        compose.first_note("Sasha Reed", "we were both at Leeds", None, ask=None)
    except ValueError:
        pass
    else:
        raise AssertionError("a note with nothing to answer was composed")


def test_greetings_never_use_an_initial_a_title_alone_or_a_credential():
    assert tone.first_name("J. Smith") == "J. Smith"
    assert tone.first_name("Dr Smith") == "Dr Smith"
    assert tone.first_name("Ph.D. Jane Doe") == "Jane"
    assert tone.first_name("Halloway, Wren") == "Wren"


def test_the_data_driven_rules_are_named():
    assert tone.DATA_DRIVEN_RULES <= set(tone.RULES)


# ------------------------------------------------------------------ who is worth it

def _tier(snippet, title="Head of Data"):
    return D.classify_tier(snippet, title, "Manchester, England, United Kingdom", "Manchester")[0]


def test_tier_1_is_a_hiring_post_about_their_own_work():
    assert _tier("Our marketing team is hiring a content writer in Manchester") != 1
    assert _tier("We are hiring a sales analyst for our Manchester team") != 1
    assert _tier("We're hiring data analysts in Manchester") == 1
    assert _tier("We're hiring in Manchester!") == 1                # no role named: the title decides


# ------------------------------------------------------------------ the files

def test_a_save_keeps_the_files_line_endings(tmp_path):
    p = tmp_path / "threads.csv"
    p.write_bytes(b"contact_id,date,direction,channel,scenario,summary,full_text\r\n"
                  b"acme_reed,2026-09-01,out,linkedin,,s,Hi Sasha\r\n")
    before = p.read_bytes()
    state.save_threads(state.load_threads(str(p)), str(p))
    assert p.read_bytes() == before


def test_a_close_the_person_chose_is_not_reported_as_reopened():
    rows = [_row("2026-09-01", "out", "first_note", "Hi Sasha"),
            _row("2026-09-02", "in", "", "Not for me, thanks")]
    closed = dict(CONTACT, status="closed", notes="")
    assert any(p["reason"] == "reopened" for p in state.reconcile([closed], rows))
    chosen = dict(closed, notes="closed on purpose: they asked not to be contacted")
    assert not any(p["reason"] == "reopened" for p in state.reconcile([chosen], rows))


def test_two_names_for_one_employer_are_reported_never_merged():
    pairs = company_key.near_misses({"Fernhill"}, {"Fernhill Freight", "Larkspur Retail"})
    assert pairs == [("Fernhill", "Fernhill Freight")]
    assert company_key.key("Fernhill") != company_key.key("Fernhill Freight")
