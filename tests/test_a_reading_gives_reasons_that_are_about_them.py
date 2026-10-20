"""A reading gives reasons to write that are about the reader: their path, who they and
the person both know, and where they really work.

"I can imagine my experimentation background being useful on a team like yours" was
rejected as generic and presumptuous; the reason that worked was a parallel in the
reader's own career. Mutual connections were on the page and ignored. A top card said
one city while the current role's own place said another. Invented people only.
"""
from __future__ import annotations

import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import reading  # noqa: E402

TODAY = datetime.date(2026, 10, 20)

PAGE = """Skip to main content
Juno Castellan
· 2nd
Head of Data at Larkspur Software
Manchester, England, United Kingdom
Contact info
Followed by Ana Rook
Bo Venn and 3 other mutual connections
Connect
More
About
I run a small data team building forecasting tools for warehouses.
Experience
Head of Data
Larkspur Software · Full-time
Jan 2024 - Present · 1 yr 10 mos
Leeds, England, United Kingdom · Hybrid
Senior Analyst
Harbour Freight · Full-time
Mar 2019 - Dec 2023 · 4 yrs 10 mos
Liverpool, England, United Kingdom
Education
University of York
"""


def _read():
    return reading.parse(PAGE, name="Juno Castellan", company="Larkspur Software", today=TODAY)


def test_experience_is_read_role_by_role_with_its_place():
    exp = _read()["experience"]
    assert [(e["employer"], e["title"]) for e in exp] == [
        ("Larkspur Software", "Head of Data"), ("Harbour Freight", "Senior Analyst")]
    assert exp[0]["place"] == "Leeds, England, United Kingdom"


def test_a_top_card_city_unlike_the_current_roles_place_is_a_caution():
    r = _read()
    note = reading.place_note(r)
    assert "Manchester" in note and "Leeds" in note
    keep, why = reading.verdict(r, "Larkspur Software")
    assert keep and why.startswith("caution:") and "Leeds" in why
    r["experience"][0]["place"] = "Manchester, England"
    assert reading.place_note(r) == ""


def test_a_move_the_candidate_is_hoping_to_make_is_offered_as_an_inferred_parallel():
    # The example person works in logistics now; the reader came to software from freight.
    par = _read()["parallels"]
    assert par and par[0]["kind"] == "INFERRED"
    assert "from logistics (Harbour Freight)" in par[0]["text"]


def test_mutual_connections_are_kept_to_offer_never_to_assert(capsys):
    r = _read()
    assert r["mutuals"] == ["Ana Rook", "Bo Venn"]
    reading._show(r)
    out = capsys.readouterr().out
    assert "mention <name>?" in out and "never say how well they know them" in out
    assert "[INFERRED] path parallel" in out


def test_a_page_with_only_message_makes_the_channel_an_inmail(tmp_path, monkeypatch):
    import schema
    import state
    contacts = tmp_path / "c.csv"
    row = {k: "" for k in schema.CONTACT_COLUMNS}
    row.update(contact_id="larkspur_castellan", name="Juno Castellan",
               company="Larkspur Software", status="not_contacted", channel="connection")
    state.save_contacts([row], str(contacts))
    monkeypatch.setattr(state, "CONTACTS_CSV", str(contacts))
    monkeypatch.setattr(state, "load_contacts", lambda path=str(contacts): state._read_csv(
        path, schema.CONTACT_COLUMNS))
    monkeypatch.setattr(state, "save_contacts", lambda rows, path=str(contacts): state._write_csv(
        path, rows, schema.CONTACT_COLUMNS))
    monkeypatch.setattr(state, "load_threads", lambda *a, **k: [])
    r = {"reach": "message", "degree": "3rd"}
    assert reading.channel_for(r) == "inmail"
    line = reading.set_channel("larkspur_castellan", r, TODAY)
    assert "an InMail" in line and "left this month" in line
    assert state.load_contacts()[0]["channel"] == "inmail"
    assert reading.channel_for({"reach": "message", "degree": "1st"}) == "message"
    assert reading.channel_for({"reach": "request"}) == "connection"
