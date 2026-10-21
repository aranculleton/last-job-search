"""One definition of a preference and of an equivalence route, used everywhere."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import bridges  # noqa: E402
import fit  # noqa: E402
import text_screen  # noqa: E402


def test_a_bonus_eligible_role_is_not_a_preference():
    # It made Python look optional in fit and a gap look like a nice-to-have in bridges.
    hard = "This bonus-eligible role requires strong Python."
    assert fit._demand(hard) == fit.DEMAND_HARD
    assert not bridges._PREFERENCE.search(hard)
    assert not fit.SOFT_WANT.search("You will join our asset management team and must know SQL.")


def test_a_real_preference_still_is_one():
    for s in ("Experience with Airflow would be a bonus.", "dbt is an asset.",
              "Familiarity with Looker.", "Snowflake preferred."):
        assert fit._demand(s) == fit.DEMAND_SOFT, s


def test_every_equivalence_route_counts_in_every_reader():
    assert fit.GRAD_ESCAPE is text_screen.ESCAPE
    for s in ("Master's degree or related experience", "PhD or an equivalent qualification"):
        assert text_screen.ESCAPE.search(s), s


def test_the_opportunity_score_reads_the_entry_bar_like_fit_does():
    # Two real bars: "3+ years of SQL" is what the recruiter screens on, the
    # 10 is someone's ideal hire. The highest is for screening, never for a score.
    import opportunity
    body = ("Requirements: you have 3+ years of SQL experience. You have at least 10+ years "
            "of experience in logistics operations. ") * 3
    r = opportunity.score({"title": "Data Analyst", "desc": body, "company": "Oakmere Foods"})
    assert not any("stated 10+" in w for w in r["why"]), r["why"]


def test_documents_meet_the_status_check_messages_meet():
    import check_claims
    names = {name for _, name, _, _ in check_claims.CHECKS}
    assert "unsupported-status" in names
    import re
    pat = next(p for _, n, p, _ in check_claims.CHECKS if n == "unsupported-status")
    assert re.search(pat, "As a British citizen I can start at once", re.I)


def test_analyses_is_a_noun_in_american_english_too():
    import locale_rules
    american = locale_rules.for_documents({"spelling": "american"})
    assert not american.wrong_spellings("I ran sensitivity analyses")
    assert american.wrong_spellings("the team analysed the data")


def test_an_employer_that_interviewed_you_lifts_its_next_role(monkeypatch, tmp_path, capsys):
    import json
    monkeypatch.setattr(fit, "interviewed_at", lambda: {"oakmere foods": "Supply Chain Analyst"})
    jobs = [{"title": "Data Analyst", "company": "Oakmere Foods", "desc": "SQL and Python."},
            {"title": "Data Analyst", "company": "Saltmarsh Analytics", "desc": "SQL and Python."}]
    src, out = tmp_path / "in.json", tmp_path / "out.json"
    src.write_text(json.dumps(jobs))
    monkeypatch.setattr(sys, "argv", ["fit.py", str(src), "--out", str(out)])
    fit.main()
    rows = {r["company"]: r for r in json.loads(out.read_text())}
    assert rows["Oakmere Foods"]["fit"] == rows["Saltmarsh Analytics"]["fit"] + fit.INTERVIEWED_BONUS
    assert any("interviewed you before" in w for w in rows["Oakmere Foods"]["fit_why"])


def test_a_skill_the_score_docks_is_a_gap_for_the_documents_too():
    # The example's FIT_MISSING docks Spark; its bridge map says nothing about it.
    # Named by what the posting wrote, with the score's reason as its note: named by the
    # reason, a pack asked "What is your experience with big-data engineering is not held?".
    found = [(g.asked, g.note) for g in bridges.gaps("You will build pipelines in PySpark every day.")]
    assert ("PySpark", "big-data engineering is not held") in found
    # A sentence the map already judged keeps the map's verdict, once.
    assert len(bridges.gaps("Chartered procurement (CIPS) is required.")) == 1


def test_the_score_and_the_screen_read_the_same_degrees():
    # The score kept a narrower pattern: these were flagged by the screen and cost
    # nothing in fit, and "M.S." and "doctoral" were docked by fit and never flagged.
    assert fit.GRAD is text_screen.DEGREE
    for s in ("An MBA is required.", "An advanced degree in statistics is required.",
              "A graduate degree is required.", "M.S. in statistics required.",
              "A doctoral degree is required.", "Ph.D. in economics required."):
        assert fit._degree_ask(s) == fit.DEMAND_HARD, s
        flags = text_screen.screen({"title": "Data Analyst", "desc": s})["flags"]
        assert any("graduate degree stated as required" in f for f in flags), s
    for s in ("Master data management experience required.", "Scrum Master certification.",
              "Bachelor's or Master's degree in Mathematics."):
        assert not fit._degree_ask(s), s


def test_the_years_caps_fit_documents_are_the_ones_it_charges(monkeypatch):
    # fit.YEARS_SLACK_CAP said one thing and the costs were written inline as another,
    # so changing the setting changed nothing.
    body = ("Requirements: you have 17+ years of experience in supply chain forecasting "
            "with SQL and Python, demand planning and inventory optimisation.")
    job = {"title": "Supply Chain Analyst", "company": "Oakmere Foods", "desc": body,
           "location_verdict": "PASS"}
    def cost():
        return next(int(w.split()[0]) for w in fit.fit(job)["fit_why"] if "stated 17+" in w)
    before = cost()
    assert fit.YEARS_HELD + 9 <= 17                  # the top band
    monkeypatch.setitem(fit.YEARS_SLACK_CAP, 9, 0.0)
    assert cost() == -fit.YEARS_COST[9] != before
