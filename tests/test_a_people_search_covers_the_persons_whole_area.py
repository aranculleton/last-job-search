"""A people search covers the person's whole area, and an employer is set aside only when
nobody there fits.

Two causes of the same people run that stopped at 8 of the 20 asked for (2026-11-12):

- #257: `candidates.py search "<employer>" --place "<city>"` narrowed every LinkedIn people
  search to the city's own location number, so everyone who lists the metro area or a town
  around it was never seen. The filter is now every number kept for the person's area (the
  metro region, their home city, the towns their job search covers and their metro list),
  and `place-ids` says a city's number leaves the rest out.
- #258: a check that left nobody at an employer recorded "nobody who fits" and skipped it
  for 30 days, though the people who fit were only held back (already written to, or the
  employer's limit of people waiting on a reply reached). That is "full for now", lifted
  when a reply or a close frees a place; and an empty result from a filter narrower than
  their area is never recorded as nobody there.

The example person lives in Manchester. Invented employers and people only.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import candidates  # noqa: E402
import reading  # noqa: E402

TODAY = dt.date(2026, 11, 12)
EMP = "Kestrel Mutual"
FITS = {"name": "Rafe Lindqvist", "title": "Head of Supply Chain Analytics", "company": EMP,
        "location": "Salford, England, United Kingdom",
        "linkedin_url": "https://www.linkedin.com/in/rafe-lindqvist-example"}


@pytest.fixture
def here(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    monkeypatch.setattr(reading.person, "state", lambda *p: str(state_dir.joinpath(*p)))
    reading.learn_company_id(EMP, "5678")
    return state_dir


def _places(url: str) -> list:
    return json.loads(parse_qs(urlsplit(url).query)["geoUrn"][0])


def _waiting(n: int, replied: int = 0):
    """`n` people at the employer written to and waiting on a reply, the first `replied` of
    whom have answered since."""
    names = ["Ines Harrow", "Bram Ostler", "Tamsin Vale"]
    contacts, threads = [], []
    for i in range(n):
        cid = f"w{i}"
        contacts.append({"contact_id": cid, "name": names[i], "company": EMP,
                         "status": "in_conversation" if i < replied else "awaiting_reply",
                         "first_contacted": "2026-11-05"})
        threads.append({"contact_id": cid, "date": "2026-11-05", "direction": "out",
                        "channel": "connection", "summary": "first note", "full_text": "Hello"})
        if i < replied:
            threads.append({"contact_id": cid, "date": "2026-11-10", "direction": "in",
                            "channel": "connection", "summary": "reply", "full_text": "Hi"})
    return contacts, threads


# ------------------------------------------------------------------ #257: the whole area


def test_a_search_in_the_home_city_uses_every_number_kept_for_the_area(here):
    reading.learn_place_ids(["Manchester=1001"])
    url = reading.search_url(EMP, "Manchester", "planning")
    assert _places(url) == ["1001"]
    # The city alone leaves out everyone who lists the metro area or a town around it.
    _ids, gaps = reading.place_filter("Manchester")
    assert gaps and gaps[0] == "Greater Manchester"
    reading.learn_place_ids(["Salford=1002", "Stockport=1003"])
    assert _places(reading.search_url(EMP, "Manchester", "planning")) == ["1001", "1002", "1003"]
    # The metro region's own number covers its towns: the area is whole.
    reading.learn_place_ids(["Greater Manchester=1000"])
    assert _places(reading.search_url(EMP, "Manchester")) == ["1001", "1000", "1002", "1003"]
    assert reading.place_filter("Manchester")[1] == []
    # A search by title in the city covers the same area.
    assert _places(reading.title_search_url("demand planner", "Manchester")) == \
        ["1001", "1000", "1002", "1003"]


def test_a_place_outside_the_area_keeps_its_own_number(here):
    reading.learn_place_ids(["Manchester=1001", "Leeds=2001"])
    assert _places(reading.search_url(EMP, "Leeds")) == ["2001"]
    assert reading.place_filter("Leeds")[1] == []
    with pytest.raises(LookupError):
        reading.search_url(EMP, "Sheffield")


def test_place_ids_says_a_city_leaves_out_its_suburbs_and_offers_the_metro(here, capsys):
    assert reading.main(["place-ids", "Manchester=1001"]) == reading.EXIT["ok"]
    out = " ".join(capsys.readouterr().out.split())
    assert "Greater Manchester" in out and "place-ids \"Greater Manchester=<number>\"" in out
    assert "town around it" in out
    assert reading.main(["place-ids", "Greater Manchester=1000"]) == reading.EXIT["ok"]
    out = " ".join(capsys.readouterr().out.split())
    assert "town around it" not in out


def test_candidates_search_says_when_the_area_is_not_whole(here, capsys):
    reading.learn_place_ids(["Manchester=1001"])
    assert candidates.main(["search", EMP, "--place", "Manchester", "--all"]) == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "Greater Manchester" in out and "place-ids" in out


# ------------------------------------------------------------------ #258: full for now


def test_people_held_back_at_a_full_employer_are_full_for_now_never_nobody_who_fits(here):
    reading.learn_place_ids(["Greater Manchester=1000"])
    contacts, threads = _waiting(2)
    got = candidates.check([FITS], EMP, 5, contacts=contacts, threads=threads, today=TODAY,
                           place="Manchester")
    assert not got["chosen"]
    candidates.record_seen(got["seen"], "Manchester", TODAY)
    rec = candidates._where()[candidates.company_key(EMP)]["manchester"]
    assert rec["fit"] == 0 and rec["held"] == 1
    assert not candidates.nobody_fits(rec)
    # While the employer is full it waits, said as full for now, never as nobody who fits.
    (name, _why, skip), = candidates.order([EMP], "Manchester", contacts=contacts,
                                           today=TODAY, threads=threads)
    assert "full for now" in skip and "nobody who fits" not in skip
    # A reply frees a place: it is searched again at once, not in 30 days.
    contacts, threads = _waiting(2, replied=1)
    (_n, _w, skip), = candidates.order([EMP], "Manchester", contacts=contacts, today=TODAY,
                                       threads=threads)
    assert skip == ""
    # Nor is it held back under Held back for now as an employer with nobody who fits.
    import holds
    assert EMP not in [n for n, _d, _p in holds._nobody_fits(TODAY)]


def test_nobody_who_fits_is_still_said_when_nobody_fits(here):
    reading.learn_place_ids(["Greater Manchester=1000"])
    candidates.record_seen({EMP: (6, 0, 0)}, "Manchester", TODAY)
    (_n, _w, skip), = candidates.order([EMP], "Manchester", contacts=[], today=TODAY)
    assert "nobody who fits" in skip


def test_an_empty_result_from_a_city_only_filter_is_never_nobody_in_the_area(here):
    reading.learn_place_ids(["Manchester=1001"])
    got = candidates.check([], EMP, 5, contacts=[], threads=[], today=TODAY, place="Manchester")
    candidates.record_seen(got["seen"], "Manchester", TODAY)
    assert candidates.company_key(EMP) not in candidates._where()
    (_n, _w, skip), = candidates.order([EMP], "Manchester", contacts=[], today=TODAY)
    assert skip == ""
    # Over the whole area, an empty result is a finding.
    reading.learn_place_ids(["Greater Manchester=1000"])
    candidates.record_seen(got["seen"], "Manchester", TODAY)
    (_n, _w, skip), = candidates.order([EMP], "Manchester", contacts=[], today=TODAY)
    assert "nobody who fits" in skip


def test_a_record_made_before_held_back_was_told_apart_is_searched_again(here):
    """Records from before this fix cannot tell nobody from full: the run of 2026-11-12 met
    its employers skipped for a month on them."""
    path = candidates._where_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({candidates.company_key(EMP): {"manchester": {
            "employer": EMP, "date": "2026-11-10", "found": 2, "fit": 0}}}, fh)
    (_n, _w, skip), = candidates.order([EMP], "Manchester", contacts=[], today=TODAY)
    assert skip == ""
