"""A profile read wrong is read again from the page it was read from, never by hand.

The 2026-11-10 audit (NW-11): `read` refused a second read ("a profile is opened once, and
that reading stands") and the page's text was never kept, so a misread (a grouped Experience
taken for a move, NW-1) could only be fixed by editing reading.json by hand. Now the text a
read was made from is kept beside its reading, and `reading.py reparse <id>` reads it again
with today's reader: the page's own fields are rewritten, and what was found elsewhere, the
day it was read and how it was read stay as they were. Invented people and employers only.
"""
from __future__ import annotations

import datetime
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import reading  # noqa: E402
import state  # noqa: E402

TODAY = datetime.date(2026, 11, 10)
ROW = {"contact_id": "harbourline_thackeray", "name": "Wenna Thackeray",
       "company": "Harbourline Insurance", "status": "not_contacted", "location": "Toronto"}
PAGE = "\n".join([
    "Wenna Thackeray", "Director of Pricing at Harbourline Insurance",
    "Toronto, Ontario, Canada", "Contact info", "Connect", "About",
    "I run pricing for a home and auto book.", "Experience", "Harbourline Insurance",
    "Permanent Full-time · 3 yrs 8 mos", "Director, Pricing, Data and Analytics",
    "Jan 2024 - Present · 1 yr 11 mos", "Manager, Pricing", "Mar 2022 - Jan 2024 · 1 yr 11 mos",
    "Education", "University of Leeds", "2010 - 2013"])


@pytest.fixture
def here(tmp_path, monkeypatch):
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    monkeypatch.setattr(reading.person, "today", lambda: TODAY)
    monkeypatch.setenv("LJS_LEDGER", str(tmp_path / "ledger"))
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: [dict(ROW)])
    # The book's path is fixed when state is imported, so a read's save went to the shared
    # example state and left a later test's contacts gone; it goes to this test's folder.
    save = state.save_contacts
    monkeypatch.setattr(state, "save_contacts",
                        lambda rows, path=str(tmp_path / "network_contacts.csv"): save(rows, path))
    return tmp_path


def test_the_page_a_read_was_made_from_is_kept_and_read_again(here, capsys):
    page = here / "pasted.txt"
    page.write_text(PAGE, encoding="utf-8")
    assert reading.main(["read", ROW["contact_id"], str(page), "--source", "paste"]) == 0
    kept = reading.page_path(ROW["contact_id"])
    assert os.path.isfile(kept) and "Permanent Full-time" in open(kept, encoding="utf-8").read()
    # A reading saved by an older reader: the title taken for the employer, a finding kept
    # from elsewhere since.
    bad = reading.load(ROW["contact_id"])
    good_experience = bad["experience"]
    bad.update(current="Director, Pricing, Data and Analytics",
               experience=[{"employer": "Director, Pricing, Data and Analytics",
                            "title": "Jan 2024 - Present", "dates": "", "place": ""}])
    bad["items"].append({"kind": "talk", "date": "2026-10-01",
                         "url": "https://example.org/talk", "text": "Pricing a home book"})
    reading.save(ROW["contact_id"], bad)
    capsys.readouterr()
    assert reading.main(["reparse", ROW["contact_id"]]) == 0
    out = capsys.readouterr().out
    got = reading.load(ROW["contact_id"])
    assert got["current"] == "Harbourline Insurance"
    assert got["experience"] == good_experience
    assert any(i.get("url") == "https://example.org/talk" for i in got["items"])
    assert got["read_on"] == bad["read_on"] and got["sources"] == bad["sources"]
    assert "verdict: KEEP" in out


def test_a_reading_with_no_page_kept_says_what_to_do(here, capsys):
    reading.save(ROW["contact_id"], {"name": ROW["name"], "company": ROW["company"],
                                     "read_on": "2026-11-01", "sources": [], "items": []})
    assert reading.main(["reparse", ROW["contact_id"]]) == reading.EXIT["error"]
    assert "no page kept" in capsys.readouterr().out


def test_a_reading_kept_no_page_is_read_once_more_with_fix_unless_closed(here, monkeypatch):
    page = here / "pasted.txt"
    page.write_text(PAGE, encoding="utf-8")
    reading.save(ROW["contact_id"], {
        "name": ROW["name"], "company": ROW["company"], "read_on": "2026-11-09",
        "sources": [{"kind": "paste", "url": "", "date": "2026-11-09"}],
        "current": "Director, Pricing, Data and Analytics", "headline": "Director",
        "experience": [{"employer": "Director, Pricing, Data and Analytics", "title": "",
                        "dates": "Jan 2024 - Present", "place": ""}],
        "items": [{"kind": "post", "date": "2026-11-01", "url": "", "text": "misread line"}]})
    assert reading.main(["read", ROW["contact_id"], str(page), "--source", "paste",
                         "--fix"]) == 0
    got = reading.load(ROW["contact_id"])
    assert got["current"] == "Harbourline Insurance"
    assert [e["employer"] for e in got["experience"]] == ["Harbourline Insurance"] * 2
    assert not any(i["text"] == "misread line" for i in got["items"])
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: [dict(ROW, status="closed")])
    with pytest.raises(SystemExit, match="closed"):
        reading.main(["read", ROW["contact_id"], str(page), "--source", "paste", "--fix"])


# The independent review of NW-11 (2026-11-11): reparse and --fix set every page field to the
# newest page's value, wiping what an older read had kept; the kept page held whole activity
# feeds, other people's posts included; and reparse never filled the contact's blank employer.
WITH_POSTS = PAGE + "\n" + "\n".join([
    "Activity", "Dara Whitlock posted this • 1w", "We are hiring a pricing analyst in Leeds."])


def test_the_kept_page_holds_only_the_parts_a_read_takes_never_others_posts(here):
    page = here / "pasted.txt"
    page.write_text(WITH_POSTS, encoding="utf-8")
    assert reading.main(["read", ROW["contact_id"], str(page), "--source", "paste"]) == 0
    kept = reading.kept_page(ROW["contact_id"])
    assert "Director, Pricing, Data and Analytics" in kept and "About" in kept
    assert "Dara Whitlock" not in kept and "hiring" not in kept


def test_a_reparse_keeps_what_the_page_does_not_say_and_fills_the_employer(here, monkeypatch):
    rows = [dict(ROW, company="")]
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: rows)
    monkeypatch.setattr(state, "save_contacts", lambda got, *a, **k: None)
    reading.save(ROW["contact_id"], {"name": ROW["name"], "company": "", "read_on": "2026-11-09",
                                     "sources": [{"kind": "paste", "url": "", "date": "2026-11-09"}],
                                     "about": "Prices home and auto cover.",
                                     "headline": "Director", "items": []})
    reading.keep_page(ROW["contact_id"], "\n".join([
        "Wenna Thackeray", "Director of Pricing at Harbourline Insurance", "Experience",
        "Harbourline Insurance", "Permanent Full-time · 3 yrs 8 mos",
        "Director, Pricing, Data and Analytics", "Jan 2024 - Present · 1 yr 11 mos"]))
    assert reading.main(["reparse", ROW["contact_id"]]) == 0
    got = reading.load(ROW["contact_id"])
    assert got["about"] == "Prices home and auto cover."          # the page said none
    assert got["current"] == "Harbourline Insurance"
    assert rows[0]["company"] == "Harbourline Insurance"
