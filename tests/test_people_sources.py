"""Where people are found, why each one is worth a note, and the shape of the note."""
import datetime
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools", "network"))
import compose  # noqa: E402
import sources  # noqa: E402
import why  # noqa: E402

TODAY = datetime.date(2026, 10, 17)


def test_the_plan_is_the_persons_own_and_every_kind_is_in_the_catalogue():
    kinds = [k for k, _ in sources.plan()]
    assert kinds[0] == "alumni_employer"            # Morgan's researched order
    assert "connections" not in kinds               # declined, and no export on file
    assert set(kinds) <= set(sources.KINDS)
    for k in sources.KINDS.values():
        assert k.scope in ("per_company", "per_run", "local") and k.label and k.finds


def test_an_unknown_kind_is_refused(monkeypatch):
    monkeypatch.setattr(sources._NET, "PEOPLE_SOURCES", (("crystal_ball", ""),), raising=False)
    with pytest.raises(sources.UnknownKind):
        sources.plan()


def test_a_plan_can_carry_its_own_query(monkeypatch):
    monkeypatch.setattr(sources._NET, "PEOPLE_SOURCES",
                        (("community", "the nursing body's branches",
                          '"Kestrel College of Nursing" branch committee {city} {unknown}'),),
                        raising=False)
    monkeypatch.setattr(sources, "_QUERY", {})
    sources.plan()
    q = sources.searches("community")
    assert q == ['"Kestrel College of Nursing" branch committee Manchester -site:linkedin.com']


def test_the_budget_holds_and_every_kind_gets_a_turn():
    rows = sources.ranked()
    per_company = sources.for_company("Oakmere Foods Ltd", rows)
    assert len(per_company) <= sources.SEARCHES_PER_COMPANY
    assert len({k for k, _ in per_company}) == len(per_company)   # one each before seconds
    assert all("Oakmere Foods" in q for _, q in per_company)
    once = sources.for_run(rows)
    assert len(once) <= sources.SEARCHES_PER_RUN
    assert {k for k, _, _ in once} >= {"alumni_employer", "alumni_school", "roster"}
    # Off LinkedIn means off LinkedIn.
    for kind, q in per_company:
        if not sources.KINDS[kind].linkedin:
            assert q.endswith("-site:linkedin.com")


def test_a_source_moves_up_only_on_enough_replies(monkeypatch):
    cases = ([{"attempt": "opener", "found_via": "community", "won": True}] * 4
             + [{"attempt": "opener", "found_via": "community", "won": False}]
             + [{"attempt": "opener", "found_via": "alumni_employer", "won": False}] * 5)
    import what_works
    monkeypatch.setattr(what_works, "message_cases", lambda *a, **k: cases)
    rows = sources.ranked([{"contact_id": "x"}], [])
    assert rows[0][0] == "community" and rows[0][2] == "replied 4 of 5"
    assert rows[1][0] == "alumni_employer"          # measured, so ahead of the unmeasured
    few = [{"attempt": "opener", "found_via": "press", "won": True}] * 2
    monkeypatch.setattr(what_works, "message_cases", lambda *a, **k: few)
    assert sources.ranked([{"contact_id": "x"}], [])[0][0] == "alumni_employer"   # 2 says nothing


def test_the_linkedin_check_finds_a_profile_by_name_and_employer():
    q = sources.linkedin_check("Rosalind Achterberg", "Kestrel Mutual Ltd")
    assert q == '"linkedin.com/in" "Rosalind Achterberg" "Kestrel Mutual"'


# ------------------------------------------------------------------ why them

ROLES = [{"company": "Oakmere Foods", "title": "Senior Data Scientist", "fit": 82}]


def test_why_them_says_why_in_plain_words():
    contact = {"name": "Tamsin Oyelaran", "title": "Data Science Manager", "company": "Oakmere Foods",
               "tier": "2", "route": "cold"}
    reading = {"shared": {"employers": [{"name": "Brindle & Hart Logistics"}]},
               "items": [{"kind": "post", "date": "2026-09-30", "text": "x"}], "reach": "request"}
    w = why.why_them(contact, reading, roles=ROLES, today=TODAY)
    assert w["score"] >= why.STRONG and w["band"] == "strong"
    assert "worked at Brindle & Hart Logistics, like you" in w["line"]
    assert any("you scored 82" in r for _, r in w["reasons"])
    cold = why.why_them({"title": "Data Science Manager", "company": "Oakmere Foods", "route": "cold"},
                        {}, roles=[], today=TODAY)
    assert cold["score"] < w["score"]


def test_a_pending_request_is_never_ranked():
    w = why.why_them({"title": "Data Science Manager"}, {"reach": "pending"}, roles=[], today=TODAY)
    assert w["skip"] and w["score"] == 0


def test_a_role_open_at_their_employer_counts_only_for_their_function():
    other = why.why_them({"title": "Head of Payroll", "company": "Oakmere Foods", "tier": "4"},
                         {}, roles=ROLES, today=TODAY)
    assert not any("you scored" in r for _, r in other["reasons"])


# ------------------------------------------------------------------ shapes

def test_the_shape_follows_the_person():
    assert compose.shape_for("Talent Acquisition Partner") == "recruiter"
    assert compose.shape_for("Data Scientist", {"reach": "message"}) == "connected"
    shared = {"shared": {"employers": [{"name": "Brindle & Hart Logistics"}]}}
    assert compose.shape_for("Data Scientist", shared) == "shared"
    assert compose.shape_for("Director of Data Science", shared) == "brief"
    talk = {"items": [{"kind": "talk", "text": "Forecasting fresh food demand"}]}
    assert compose.shape_for("Data Scientist", talk) == "their_work"
    assert compose.shape_for("Data Scientist", {}) == "brief"


def test_the_default_shape_is_the_note_it_always_was():
    args = dict(name="Corwin Haldane", common_ground="We both worked at Brindle & Hart Logistics",
                question="How did you find the move to Oakmere", their=("Oakmere",))
    assert compose.first_note(**args) == compose.first_note(**args, shape="shared")


def test_a_brief_note_drops_the_question_and_stays_short():
    note = compose.first_note("Corwin Haldane", "We both worked at Brindle & Hart Logistics",
                              question="How did you find the move", shape="brief",
                              their=("Oakmere",))
    assert "How did you find the move" not in note and len(note) <= compose.BRIEF_CHARS
    with pytest.raises(ValueError):
        compose.first_note("Corwin Haldane", "x", shape="loud")
