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
    # The title searches first, both of them: measured, the one kind that named people
    # at the employer in bulk. Then every other kind gets one before any gets a second.
    titles = sources.searches("title_search", "Oakmere Foods Ltd")[:sources.TITLE_SEARCHES]
    assert len(titles) == sources.TITLE_SEARCHES == 2
    assert per_company[:2] == [("title_search", q) for q in titles]
    rest = [k for k, _ in per_company[2:]]
    assert rest and "title_search" not in rest and len(set(rest)) == len(rest)
    assert all("Oakmere Foods" in q for _, q in per_company)
    once = sources.for_run(rows)
    assert len(once) <= sources.SEARCHES_PER_RUN
    assert {k for k, _, _ in once} >= {"alumni_employer", "alumni_school", "roster"}
    # Off LinkedIn means off LinkedIn.
    for kind, q in per_company:
        if not sources.KINDS[kind].linkedin:
            assert q.endswith("-site:linkedin.com")


def _history(monkeypatch, roles):
    import types
    import reading
    monkeypatch.setattr(reading, "_roles",
                        lambda: types.SimpleNamespace(ROLES=roles, EDUCATION=""))


def test_every_employer_they_left_gets_a_turn_and_the_current_one_none(monkeypatch):
    # Four employers, listed out of order. The searches used to be the first
    # employer's two and nothing else, so the current employer took both and the
    # three they had left were never searched.
    _history(monkeypatch, [
        {"employer": "Harrow Point Media", "dates": "Jun 2019 - Feb 2022"},
        {"employer": "Corrie Freight", "dates": "Jan 2025 - Present"},
        {"employer": "Pellow Robotics", "dates": "Sep 2017 - May 2019"},
        {"employer": "Fenwick Lane Insurance", "dates": "Mar 2022 - Dec 2024"},
    ])
    assert sources._past_employers() == ["Fenwick Lane Insurance", "Harrow Point Media",
                                         "Pellow Robotics"]
    qs = sources.searches("alumni_employer")
    assert len(qs) == sources.ALUMNI_EMPLOYER_SEARCHES == 3
    assert '"Fenwick Lane Insurance"' in qs[0]           # the one most recently left leads
    assert {q.split('"')[-2] for q in qs} == {"Fenwick Lane Insurance", "Harrow Point Media",
                                              "Pellow Robotics"}
    assert not any("Corrie Freight" in q for q in qs)
    # Inside the run's budget, the alumni searches still reach more than one employer,
    # and the older ones take turns behind the first, so over two days every one is reached.
    once = [q for k, _, q in sources.for_run() if k == "alumni_employer"]
    assert len({q.split('"')[-2] for q in once}) == len(once) >= 2
    reached = set()
    for day in (TODAY, TODAY + datetime.timedelta(days=1)):
        order = sources._alumni_order(day)
        assert order[0] == "Fenwick Lane Insurance"
        reached |= set(order[:2])
    assert reached == {"Fenwick Lane Insurance", "Harrow Point Media", "Pellow Robotics"}


def test_one_employer_left_gets_both_its_searches(monkeypatch):
    _history(monkeypatch, [{"employer": "Corrie Freight", "dates": "2025-Present"},
                           {"employer": "Harrow Point Media", "dates": "2019 to 2022"}])
    qs = sources.searches("alumni_employer")
    assert len(qs) == 2 and all('"Harrow Point Media"' in q for q in qs)


def test_an_open_ended_role_is_current_in_any_language():
    import reading
    for open_ended in ("Mar 2023 - Present", "2025-Present", "Juni 2022 - heute", "2021 -"):
        assert reading._ended(open_ended)[0], open_ended
    for done in ("Sep 2020 - Feb 2023", "2018-2020", "2019", ""):
        assert not reading._ended(done)[0], done


def test_an_employer_the_search_ruled_out_costs_no_searches():
    # The example excludes gambling; the job search's verdict is read, not repeated.
    assert sources.ruled_out("Northgate Betting Group")
    assert sources.for_company("Northgate Betting Group") == []
    assert sources.ruled_out("Oakmere Foods") == ""


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
    # Plain words with the name quoted, run with the LinkedIn domain filter: the literal
    # "linkedin.com/in" in the query cost results (measured 2026-10-18).
    assert q == '"Rosalind Achterberg" Kestrel Mutual'
    assert "linkedin.com" not in q


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


def test_someone_doing_the_same_work_says_so():
    # The example's FIT_CORE weighs forecasting and supply chain at 8.
    reading = {"about": "I lead demand forecasting for our supply chain team"}
    w = why.why_them({"title": "Analytics Lead", "company": "Oakmere Foods"}, reading,
                     roles=[], today=TODAY)
    assert "works on forecasting and supply chain, like you" in w["line"]
    plain = why.why_them({"title": "Analytics Lead", "company": "Oakmere Foods"}, {},
                         roles=[], today=TODAY)
    assert w["score"] - plain["score"] == 18


def test_an_application_there_is_named_and_a_closed_one_is_not():
    c = {"title": "Data Science Manager", "company": "Oakmere Foods"}
    live = why.why_them(c, {}, roles=[], today=TODAY,
                        applied=[{"role": "Senior Data Scientist", "status": "applied"}])
    assert any("you applied there: Senior Data Scientist (applied)" in r for _, r in live["reasons"])
    gone = why.why_them(c, {}, roles=[], today=TODAY,
                        applied=[{"role": "Senior Data Scientist", "status": "rejected"}])
    assert not any("you applied there" in r for _, r in gone["reasons"])


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
    # A peer with nothing shared and nothing of theirs gets the standard note, not the
    # senior reader's 220 (changed 2026-10-19: a peer could not fit one specific line).
    assert compose.shape_for("Data Scientist", {}) == "shared"
    assert compose.shape_for("Director of Data Science", {}) == "brief"


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


def test_a_route_moves_scores_only_on_a_clear_gap(monkeypatch):
    # Twenty a side since 2026-10-21 (what_works.MIN_GROUP, Fisher's exact test): ten
    # a side moved scores before, and groups that small swing on one reply.
    import what_works
    cases = ([{"attempt": "opener", "route": "alumni", "won": True}] * 16
             + [{"attempt": "opener", "route": "alumni", "won": False}] * 4
             + [{"attempt": "opener", "route": "cold", "won": False}] * 18
             + [{"attempt": "opener", "route": "cold", "won": True}] * 2)
    monkeypatch.setattr(what_works, "message_cases", lambda *a, **k: cases)
    odds = why.route_odds([], [])
    assert odds["alumni"][0] > 0 and "answered 16 of 20" in odds["alumni"][1]
    assert odds["cold"][0] < 0
    ten_a_side = cases[8:28]
    monkeypatch.setattr(what_works, "message_cases", lambda *a, **k: ten_a_side)
    assert why.route_odds([], []) == {}                        # ten a side: nothing moves
    few = cases[:3] + cases[20:23]
    monkeypatch.setattr(what_works, "message_cases", lambda *a, **k: few)
    assert why.route_odds([], []) == {}                        # too few: nothing moves


def test_a_post_from_today_counts_as_active():
    w = why.why_them({"title": "Data Analyst"}, {"items": [{"kind": "post", "date": TODAY.isoformat()}]},
                     roles=[], today=TODAY)
    assert any("active" in r for _, r in w["reasons"])
