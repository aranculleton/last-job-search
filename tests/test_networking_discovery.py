"""Finding people: the right ones, once each, and nobody ruled out on a guess.

Found by reading the discovery code against the example person:

- "already contacted" matched on names alone: a Cyrillic name reduced to nothing and
  matched the first person at the employer, "Søren Møller" slugged to "s_ren_m_ller", and
  the profile URL every result carries was never compared;
- "Brindle & Hart" and "Brindle and Hart" were two employers, "Nestlé" keyed as "nestl";
- tier 1 took another job seeker's "I'm looking for", a marketing director's "we're
  hiring", a remote role in another country and an undated headline as live hiring;
- post permalinks, where those signals live, were thrown away by the documented filter;
- a result with no location read as somebody elsewhere, and an empty search wrote the
  employer off as having no relevant presence, for good;
- "Aylesbury" was Greater Manchester (it ends in "bury") and Manchester, New Hampshire
  was Manchester;
- a hiring post with a few emoji, and an in-house recruiter, were dropped as spam.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import discovery as D  # noqa: E402
import state  # noqa: E402
from company_key import key  # noqa: E402

TODAY = "2026-10-15"
BOOK = [{"contact_id": "fernhill_freight_halloway", "name": "Wren Halloway",
         "company": "Fernhill Freight", "linkedin_url": "https://www.linkedin.com/in/wren-example/"},
        {"contact_id": "larkspur_retail_castellan", "name": "Juno Castellan",
         "company": "Larkspur Retail", "linkedin_url": ""}]


# ------------------------------------------------------------------ once each

def test_a_name_in_another_script_matches_nobody_by_default():
    assert state.already_contacted(BOOK, name="Иван Петров", company="Fernhill Freight") is None
    assert state.contact_id("王 伟", "Acme") == "acme_伟"


def test_letters_nfkd_leaves_alone_are_folded():
    assert state._slug("Søren Møller") == "soren_moller"
    assert state._slug("Łukasz Wróbel") == "lukasz_wrobel"


def test_the_profile_url_finds_the_same_person_under_any_name_or_employer():
    hit = state.already_contacted(BOOK, name="W. Halloway", company="Larkspur Retail",
                                  linkedin_url="https://uk.linkedin.com/in/Wren-Example?trk=x")
    assert hit and hit["contact_id"] == "fernhill_freight_halloway"
    assert state.unique_contact_id("Wren Halloway", "Larkspur Retail", BOOK,
                                   linkedin_url="linkedin.com/in/wren-example") \
        == "fernhill_freight_halloway"


def test_one_employer_however_it_is_written():
    assert key("Brindle & Hart Logistics") == key("Brindle and Hart Logistics Ltd")
    assert key("Nestlé UK") == "nestle"
    assert key("Яндекс")                                            # not ""


# ------------------------------------------------------------------ tier 1

def _tier(snippet, title, location="Manchester, England, United Kingdom"):
    return D.classify_tier(snippet, title, location, "Manchester")[0]


def test_a_job_seekers_looking_for_is_not_a_hiring_signal():
    assert _tier("I'm looking for my next opportunity in data", "Senior Data Scientist") != 1
    assert _tier("I'm looking for a data analyst to join my team", "Head of Data") == 1


def test_a_hiring_post_outside_the_persons_function_is_not_tier_1():
    assert _tier("We're hiring for our brand team", "Director of Marketing") != 1


def test_remote_reaches_here_only_from_here_or_with_the_country_named():
    austin = "Austin, Texas, United States"
    assert _tier("We're hiring remote data scientists, US time zones only", "Head of Data",
                 austin) != 1
    assert _tier("We're hiring data analysts, remote across the UK", "Head of Data", austin) == 1


def test_an_undated_signal_is_kept_but_does_not_earn_tier_1():
    person = {"name": "Sasha Reed", "title": "Head of Data", "company": "Acme",
              "location": "Manchester", "snippet": "We're hiring data analysts",
              "last_activity": "2026-10-01"}
    kept = D.triage([person], "Manchester", TODAY, "Acme")["keep"][0]
    assert kept["tier"] != 1 and kept["undated_signal"] and "signal_date" not in kept
    dated = D.triage([dict(person, signal_date="2026-10-10")], "Manchester", TODAY,
                     "Acme")["keep"][0]
    assert dated["tier"] == 1


def test_every_post_permalink_shape_resolves_and_a_company_page_is_not_a_person():
    for kind in ("activity", "share", "ugcPost"):
        r = D.resolve_result(f"https://www.linkedin.com/posts/janesmith_hiring-{kind}-"
                             "7250000000000000000-abcd")
        assert r and r["kind"] == "post" and r["post_date"]
    r = D.resolve_result("https://www.linkedin.com/posts/acme-analytics_we-are-hiring-"
                         "activity-7250000000000000000-abcd", company="Acme Analytics")
    assert r["kind"] == "company_post" and r["profile_url"] is None


# ------------------------------------------------------------------ nobody ruled out on a guess

def test_a_result_with_no_location_is_unverified_not_elsewhere():
    out = D.triage([{"name": "Sasha Reed", "title": "Head of Data", "company": "Acme"}],
                   "Manchester", TODAY, "Acme")
    assert out["verdict"] == "has_presence"
    assert out["keep"][0]["location_unverified"] and out["keep"][0]["tier"] == 2


def test_nothing_back_is_not_no_presence_and_a_finding_expires():
    assert D.triage([], "Manchester", TODAY, "Acme")["verdict"] == "no_results"
    assert D.presence_record("no_results", TODAY) is None
    rec = D.presence_record("no_relevant_presence", TODAY)
    assert D.presence_blocks(rec, TODAY) and not D.presence_blocks(rec, "2027-02-01")


def test_places_match_on_words_and_a_foreign_region_is_not_home():
    assert not D._same_market("Aylesbury, England, United Kingdom", "Manchester")
    assert D._same_market("Bury, England, United Kingdom", "Manchester")
    assert not D._same_market("Manchester, New Hampshire, United States", "Manchester")
    assert D._same_market("Manchester, England, United Kingdom", "Manchester")


def test_a_home_city_of_two_words_still_has_a_metro(monkeypatch):
    monkeypatch.setattr(D, "_HOME_TOKENS", ["new", "york"])
    monkeypatch.setattr(D, "METRO", ("brooklyn",))
    monkeypatch.setattr(D, "_REGIONS", ())
    monkeypatch.setattr(D, "_COUNTRY", ())
    assert D._same_market("Brooklyn", "New York")


def test_a_hiring_post_with_emoji_and_an_inhouse_recruiter_are_kept():
    post = {"name": "Sasha Reed", "title": "Head of Data", "company": "Acme",
            "snippet": "We're hiring data analysts ➡️ Manchester ✅ hybrid 🚀"}
    assert D.disqualify(post, "Acme") is None
    recruiter = {"name": "Robin Vale", "title": "Talent Acquisition Partner"}
    assert D.disqualify(recruiter, "Acme") is None
    assert D.disqualify(recruiter) is not None                    # no company at all: still out
    tenure = {"name": "Sasha Reed", "title": "Head of Data",
              "snippet": "After 8 years at Acme I lead the data team"}
    assert D.disqualify(tenure, "Acme") is None


# ------------------------------------------------------------------ the searches

def test_a_search_uses_the_employers_everyday_name_and_never_site():
    assert D.search_name("Fernhill Freight Services Limited (UK)") == "Fernhill Freight Services"
    assert D.search_name("Acme Co., Ltd.") == "Acme"
    qs = D.queries_for("Fernhill Freight Services Limited (UK)")
    assert qs and all("Limited" not in q and "site:" not in q for q in qs)


def test_alumni_are_sorted_to_the_target_they_work_at():
    found = [{"name": "A", "company": "Acme Ltd"}, {"name": "B", "company": "Elsewhere"}]
    assert D.alumni_at(found, ["Acme"]) == {"Acme": [found[0]]}


def test_their_own_connections_are_read_and_marked(tmp_path):
    export = tmp_path / "Connections.csv"
    export.write_text("Notes:\n\"When exporting...\"\n\nFirst Name,Last Name,URL,Email Address,"
                      "Company,Position,Connected On\nWren,Halloway,"
                      "https://www.linkedin.com/in/wren-example,,Fernhill Freight,Head of Planning,"
                      "01 Mar 2024\n", encoding="utf-8")
    conns = state.first_degree(str(export))
    assert [c["name"] for c in state.connections_at(conns, "Fernhill Freight Ltd")] == \
        ["Wren Halloway"]
    marked = D.mark_first_degree([{"name": "Wren Halloway", "company": "Fernhill Freight"}], conns)
    assert marked[0]["first_degree"] and marked[0]["channel"] == "message"
    assert state.first_degree(str(tmp_path / "missing.csv")) == []
