"""Where a posting says the work can be done from, read the way it is written.

Three readings let a posting through, or cut one, on the wrong place:

- A remote role restricted to another country passed. "Remote (US only)",
  "Remote - US", "Remote, Germany only" and "Remote - EMEA" all read PASS for
  somebody living elsewhere, because the remote branch only failed a country
  written as a whole part on its own.
- "<home city>, CA" with no province beside it was read as California and failed,
  because only a home region or the country's name excused the code.
- The text screen lower-cased a sentence before looking for "US", so "able to
  join us in the office" was a requirement to live abroad and a role in the
  person's own city was cut. And "we only hire in the United States", "remote
  within the US" and "US residents only" were never read as one.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import prefilter  # noqa: E402
import places  # noqa: E402
import text_screen  # noqa: E402

BODY = " You will build planning models in SQL and Python for the North West network."


def test_a_remote_role_restricted_to_another_country_is_not_remote_from_home():
    for loc in ("Remote (US only)", "Remote, Germany only", "Remote, US-based",
                "Remote - US", "Remote - USA", "Remote, United States"):
        assert prefilter.location_verdict(loc)[0] == "FAIL", loc


def test_a_region_beside_remote_is_judged_by_whether_it_takes_in_home():
    # Changed on purpose. Every region beside "remote" was flagged for Tier 2, and the
    # gate knew only some region words, so "Remote - North America" passed for
    # somebody in the UK as remote from anywhere. The gate now reads the text
    # screen's list (places.REGION_WORDS) and judges each the way the screen does.
    for loc in ("Remote - North America", "Remote (Americas)", "Remote, Asia-Pacific",
                "Remote (EU residents)", "Remote - LATAM", "Remote, APAC"):
        assert prefilter.location_verdict(loc)[0] == "FAIL", loc
    for loc in ("Remote - EMEA", "Remote - Europe", "Remote - North America or EMEA",
                "Remote (UK)", "Remote - UK", "Remote", "Remote, Northgate",
                "Remote (US or UK)"):
        assert prefilter.location_verdict(loc)[0] == "PASS", loc
    assert prefilter.location_verdict("Remote - North America or EMEA")[1] == (
        "explicitly remote; EMEA takes in United Kingdom")


def test_a_region_is_read_for_the_persons_own_country(monkeypatch):
    # An invented market in North America, and one the region table cannot place.
    monkeypatch.setattr(places, "HOME_COUNTRY_RX", re.compile(r"\bcanada\b"))
    monkeypatch.setattr(prefilter, "_HOME_RX", re.compile(r"\bcanada\b"))
    monkeypatch.setattr(prefilter, "_HOME", "Canada")
    monkeypatch.setattr(prefilter, "OTHER_COUNTRIES", ["germany"])
    for loc in ("Remote - North America", "Remote (Americas)"):
        assert prefilter.location_verdict(loc)[0] == "PASS", loc
    for loc in ("Remote - Europe", "Remote - EMEA", "Remote, Asia-Pacific"):
        assert prefilter.location_verdict(loc)[0] == "FAIL", loc
    monkeypatch.setattr(places, "HOME_COUNTRY_RX", re.compile(r"\bwexland\b"))
    monkeypatch.setattr(prefilter, "_HOME_RX", re.compile(r"\bwexland\b"))
    monkeypatch.setattr(prefilter, "_HOME", "Wexland")
    for loc in ("Remote - North America", "Remote - EMEA"):
        assert prefilter.location_verdict(loc)[0] == "FLAG", loc


def test_a_restriction_to_the_neighbour_fails_where_naming_it_only_flags(monkeypatch):
    # An invented market whose neighbour is the United States.
    monkeypatch.setattr(prefilter, "_HOME_RX", re.compile(r"\b(?:wexland)\b"))
    monkeypatch.setattr(prefilter, "_HOME", "Wexland")
    monkeypatch.setattr(prefilter, "NEIGHBOUR_WORDS", re.compile(r"\b(?:united states|usa)\b"))
    monkeypatch.setattr(prefilter, "NEIGHBOUR_STATES", {"tx", "ny"})
    monkeypatch.setattr(prefilter, "OTHER_COUNTRIES", ["germany"])
    assert prefilter.location_verdict("Remote (United States only)")[0] == "FAIL"
    assert prefilter.location_verdict("Remote (US only)")[0] == "FAIL"
    assert prefilter.location_verdict("Remote - Austin, TX")[0] == "FLAG"
    assert prefilter.location_verdict("Remote - Wexland")[0] == "PASS"


def test_a_home_city_beside_the_country_code_is_home(monkeypatch):
    monkeypatch.setattr(prefilter, "REGIONS", {"wx": "WX", "wexmoor": "WX"})
    monkeypatch.setattr(prefilter, "_HOME_REGION", "WX")
    monkeypatch.setattr(prefilter, "METRO", ["northgate", "brindle"])
    monkeypatch.setattr(prefilter, "NEIGHBOUR_STATES", {"ca", "tx"})
    monkeypatch.setattr(prefilter, "NEIGHBOUR_METROS", re.compile(r"\b(?:brindle|larkspur)\b"))
    monkeypatch.setattr(prefilter, "_CC", "ca")
    assert prefilter.location_verdict("Northgate, CA")[0] == "PASS"
    assert prefilter.location_verdict("Remote - Northgate, CA")[0] == "PASS"
    # A city both countries have: not evidence either way, so never a FAIL.
    assert prefilter.location_verdict("Brindle, CA")[0] == "FLAG"
    # Off the metro list, alone with the code: the state.
    assert prefilter.location_verdict("Fernhill, CA")[0] == "FAIL"
    assert prefilter.location_verdict("Larkspur, CA")[0] == "FAIL"


def test_the_pronoun_us_is_not_the_united_states():
    for s in ("You must be based in Manchester and able to join us in the office.",
              "You need to live within reach of Bolton so you can join us on site.",
              "Candidates must be based in Trafford; tell us about your commute."):
        assert text_screen.residence_cut(s + BODY) is None, s


def test_only_hiring_in_another_country_is_a_requirement_to_live_there():
    for s in ("We only hire in the United States.", "This role is remote within the US.",
              "US residents only.", "This is a US-only role.",
              "We can only consider applicants located in Ireland.",
              "The role is limited to candidates in Germany.",
              "Open to Germany-based candidates only."):
        assert text_screen.residence_cut(s + BODY), s


def test_a_restriction_that_takes_in_home_or_only_describes_the_employer_is_not_cut():
    for s in ("We only hire in the UK.", "This role is remote within the UK or Ireland.",
              "Remote within EMEA.", "We are a US-based company with an office in Salford.",
              "Kestrel Mutual is the only US insurer with a Manchester analytics hub.",
              "Our platform is used by US residents and UK businesses alike.",
              "Larkspur Retail is the only US retailer in the index."):
        assert text_screen.residence_cut(s + BODY) is None, s


def test_a_home_town_beside_another_country_is_that_country():
    for s in ("Candidates must be based in Manchester, NH, US.",
              "Candidates must be based in Sale, Australia."):
        assert text_screen.residence_cut(s + BODY), s


def test_only_selling_somewhere_is_a_market_not_a_requirement():
    for s in ("We only sell in the US and Canada today.",
              "Our team only works in the US time zone for client calls."):
        assert text_screen.residence_cut(s + BODY) is None, s
    assert text_screen.residence_cut("We are only able to hire candidates in Ireland." + BODY)


def test_a_time_zone_is_hours_not_a_home():
    assert text_screen.residence_cut("This role is remote within US time zones." + BODY) is None
    assert text_screen.residence_cut("Remote within the US, EST hours preferred." + BODY)


def test_a_region_cuts_only_when_it_leaves_home_out(monkeypatch):
    """"Must be based in EMEA" cut a candidate in the UK, which EMEA takes in. A region
    cuts only when the person's country is outside it; one it cannot place never cuts."""
    import re
    body = " You will build planning models in SQL and Python."
    cut = lambda s: bool(text_screen.residence_cut(s + body))  # noqa: E731
    assert not cut("Candidates should be based in EMEA.")
    assert not cut("You must be based in Europe or the US.")
    assert cut("You must be located in the EU.") and cut("Candidates must be based in APAC.")
    # The same sentences for somebody in Canada.
    monkeypatch.setattr(places, "HOME_COUNTRY_RX", re.compile(r"\bcanada\b"))
    assert not cut("Candidates must be based in North America.")
    assert cut("Candidates must be based in Europe.")
    assert places.region_includes_home("the Americas") is True
    # A home the table cannot place: no region cuts.
    monkeypatch.setattr(places, "HOME_COUNTRY_RX", re.compile(r"\batlantis\b"))
    assert places.region_includes_home("EMEA") is None and not cut("Must be based in EMEA.")
