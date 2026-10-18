"""Discovery as a real run found it (2026-10-18), with invented people.

Over five employers, the plan's press, team-page and speaker-list searches named 21
people worth writing to and none with a LinkedIn address; its LinkedIn searches found
9 with one; its alumni searches found nobody. So a find by name is marked, ranked
below a findable one and never sent a request, an old press page keeps its person
for checking instead of dropping them, and a run that cannot fill its batch says so.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools", "network"))
import discovery  # noqa: E402
import sources  # noqa: E402
import why  # noqa: E402

TODAY = datetime.date(2026, 10, 18)


def test_an_old_press_page_keeps_its_person_to_check_and_old_activity_still_drops():
    press = {"name": "Corwin Haldane", "title": "Head of Data Science", "company": "Kestrel Mutual",
             "location": "Manchester", "date": "2018-03-01", "found_via": "press"}
    profile = dict(press, found_via="title_search", linkedin_url="https://www.linkedin.com/in/example-corwin")
    out = discovery.triage([press, profile], today=TODAY, target_company="Kestrel Mutual")
    kept = [p for p in out["keep"] if p["found_via"] == "press"]
    assert kept and "check they still hold this role" in kept[0]["reverify"]
    assert kept[0]["name_only"]
    assert any(p["found_via"] == "title_search" for p, _ in out["dropped"])


def test_a_find_by_name_ranks_below_one_who_can_be_found():
    base = {"name": "Corwin Haldane", "title": "Senior Data Scientist", "company": "Kestrel Mutual",
            "tier": "3"}
    found = why.why_them({**base, "linkedin_url": "https://www.linkedin.com/in/example-corwin"}, today=TODAY,
                         roles=[])
    named = why.why_them({**base, "name_only": True}, today=TODAY, roles=[])
    assert named["score"] < found["score"]
    assert any("find them on LinkedIn" in w for _, w in named["reasons"])
    emailed = why.why_them({**base, "email": "c@example.com"}, today=TODAY, roles=[])
    assert not any("find them on LinkedIn" in w for _, w in emailed["reasons"])


def test_the_title_read_on_their_page_outranks_the_contact_books():
    contact = {"name": "Corwin Haldane", "title": "Head of Data", "company": "Kestrel Mutual",
               "linkedin_url": "https://www.linkedin.com/in/example-corwin"}
    reading = {"headline": "Director, Group Finance", "sources": [{"kind": "browser"}]}
    seen = why.why_them(contact, reading, today=TODAY, roles=[])
    assert not any("can hire: Head of Data" in w for _, w in seen["reasons"])


def test_the_past_employer_whose_alumni_reply_leads_every_day(monkeypatch):
    # The real run's best route (6 of 7 alumni replied) lost its place to a third
    # employer on alternate days when the order was recency alone.
    import types
    import reading
    monkeypatch.setattr(reading, "_roles", lambda: types.SimpleNamespace(ROLES=[
        {"employer": "Corrie Freight", "dates": "Jan 2025 - Present"},
        {"employer": "Fenwick Lane Insurance", "dates": "Mar 2022 - Dec 2024"},
        {"employer": "Harrow Point Media", "dates": "Jun 2019 - Feb 2022"},
        {"employer": "Pellow Robotics", "dates": "Sep 2017 - May 2019"}], EDUCATION=""))
    book = [{"route": "alumni_employer", "route_detail": "Harrow Point Media", "status": s}
            for s in ("in_conversation", "in_conversation", "call_booked", "awaiting_reply")]
    for n in range(3):
        order = sources._alumni_order(TODAY + datetime.timedelta(days=n), contacts=book)
        assert order[0] == "Harrow Point Media" and "Corrie Freight" not in order
    assert sources._alumni_order(TODAY, contacts=[])[0] == "Fenwick Lane Insurance"


def test_a_run_that_cannot_fill_its_batch_says_so_and_never_pads():
    line = sources.short_batch(2, 8, {"roster": 2, "alumni_employer": 0}, have_connections=False,
                               browser=True)
    assert line.startswith("I found 2 of the 8") and "stopped rather than pad" in line
    assert "connections" in line and "People tab" in line and "names of anyone" in line
    assert "—" not in line
    assert sources.short_batch(8, 8, {}) == ""
