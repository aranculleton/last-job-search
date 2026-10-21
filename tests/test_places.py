"""One list of the person's places (tools/places.py), and gates that did not move.

The person-finder kept its own metro in networking.py, and it drifted from the
job search's: the example's search metro names Tameside, Sale, Stretford,
Ashton-under-Lyne and MediaCity, and its networking metro names none of them,
so a Head of Data in Stretford read as out of market for Manchester. Discovery
now reads both lists. The job search's location gates read the same places as
before and must give exactly the answers they gave: the tables below were taken
from the code before tools/places.py existed.
"""
import os
import datetime as dt
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import discovery as D  # noqa: E402
import person  # noqa: E402
import places  # noqa: E402
import prefilter  # noqa: E402
import text_screen  # noqa: E402

NETWORKING_METRO = tuple(person.module("networking").METRO)
ONLY_IN_SEARCH = ("tameside", "ashton-under-lyne", "sale", "stretford", "media city", "mediacity")


# ------------------------------------------------------------------ discovery

def test_the_example_lists_drift_which_is_why_discovery_reads_both():
    for place in ONLY_IN_SEARCH:
        assert place in places.METRO and place not in NETWORKING_METRO, place
    assert "greater manchester" in NETWORKING_METRO and "greater manchester" not in places.METRO


def test_discovery_metro_is_the_union_with_the_persons_own_list_first():
    assert D.METRO[:len(NETWORKING_METRO)] == NETWORKING_METRO
    assert set(D.METRO) == set(NETWORKING_METRO) | set(places.METRO)
    assert len(D.METRO) == len(set(D.METRO))


def test_no_networking_metro_means_the_search_metro():
    assert places.metro_with(()) == places.METRO
    assert places.metro_with(("northgate", "salford")) == (
        "northgate", "salford", *[p for p in places.METRO if p != "salford"])


def test_a_contact_in_a_town_only_the_search_names_is_in_market():
    for loc in ("Stretford", "Tameside, England", "Sale, England, United Kingdom",
                "Ashton-under-Lyne, England, United Kingdom", "MediaCity"):
        assert D._same_market(loc, "Manchester"), loc
        assert D.classify_tier("", "Head of Data", loc, "Manchester")[0] == 2, loc


def test_the_union_keeps_every_old_answer_that_was_no():
    assert not D._same_market("Aylesbury, England, United Kingdom", "Manchester")
    assert not D._same_market("Manchester, New Hampshire, United States", "Manchester")
    assert not D._same_market("Sale, Australia", "Manchester")
    assert not D._same_market("Stretford", "London")
    assert not D._same_market("Leeds, England, United Kingdom", "Manchester")


def test_a_whole_post_is_read_against_the_persons_own_list():
    # "Sale" is a town in the search metro and a word in "point of sale": a post
    # from somebody elsewhere is not hiring here because it says it.
    post = "We're hiring a data analyst for our point-of-sale analytics team"
    assert not D._signal_reaches_market(post, "Manchester")
    assert D.classify_tier(post, "Head of Data", "Leeds, England, United Kingdom",
                           "Manchester")[0] == 4
    assert D._signal_reaches_market("We're hiring analysts in Bolton", "Manchester")


def test_no_location_spec_and_no_profile_still_import(tmp_path):
    code = ("import sys; sys.path[:0] = [%r, %r]; import places, discovery as D; "
            "print(places.LOCATION, D._OTHER_COUNTRIES, "
            "places.HOME_COUNTRY_RX.search('the uk'))"
            % (os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")))
    env = {**os.environ, "LJS_PROFILE": str(tmp_path / "nobody")}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                         text=True, cwd=str(tmp_path))
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["{}", "()", "None"]


# ------------------------------------------------------------------ the gates

def test_the_places_are_the_location_gates_own_lists():
    assert places.METRO == tuple(prefilter.METRO)
    assert places.REGIONS == prefilter.REGIONS
    assert places.OTHER_COUNTRIES == tuple(c.lower() for c in prefilter.OTHER_COUNTRIES)
    assert places.HOME_COUNTRY_RX is prefilter._HOME_RX


# The prefilter's answers for the example, as the code gave them before
# tools/places.py. Some are worth revisiting ("Manchester, NH" and "Sale, Wexmoor"
# pass on the metro name, with no region to say otherwise); this table is here so
# that any change to them is made on purpose.
GATE = {
    "PASS": [
        "Remote", "remote", "Remote - UK", "UK (Remote)", "United Kingdom (Remote)",
        "Remote, United Kingdom", "Remote, Northgate", "Manchester",
        "Manchester, England, United Kingdom", "Manchester, UK", "Hybrid - Manchester",
        "Manchester | Remote", "Greater Manchester", "Greater Manchester Area",
        "Manchester Area, United Kingdom", "Salford",
        "Salford, England, United Kingdom", "MediaCity UK, Salford", "Media City", "MediaCity",
        "Salford Quays", "Stockport, Cheshire", "Stockport, England, United Kingdom",
        "Trafford", "Stretford", "Stretford, England, United Kingdom", "Sale",
        "Sale, England, United Kingdom", "Sale, Wexmoor", "Altrincham", "Bolton", "Bolton, England",
        "Bury", "Bury, England, United Kingdom", "Bury St Edmunds, England", "Oldham",
        "Rochdale", "Wigan, England, United Kingdom", "Tameside", "Tameside, England",
        "Ashton-under-Lyne", "Ashton-under-Lyne, England, United Kingdom", "England",
        "England, United Kingdom", "England, UK", "UK", "United Kingdom"],
    "FLAG": [
        "", "Aylesbury, England, United Kingdom", "Leeds, England, United Kingdom",
        "Liverpool", "Warrington", "Preston, England", "Sheffield", "North West",
        "North West England", "New York, NY", "San Diego, CA", "Austin, TX", "EMEA", "Europe",
        "Northgate", "Northgate, Wexmoor", "Wexmoor", "Somewhere, Nowhere"],
    "FAIL": [
        # Changed on purpose: these passed as Greater Manchester. A home town's name
        # beside another country's state is that place (places.subdivision_abroad).
        "Manchester, NH", "Manchester, NH, US",
        "Remote, India", "Remote - Germany", "Remote - Canada",
        # Changed on purpose: the EU leaves out the UK, the example's home, so a role
        # remote within it is abroad (tools/places.py region_includes_home).
        "Remote (EU)",
        "Manchester, New Hampshire, United States", "Sale, Australia", "London",
        "London, England, United Kingdom", "On-site, London", "Birmingham, UK", "Bristol",
        "Edinburgh, Scotland", "Glasgow, Scotland, United Kingdom", "Cardiff, Wales, UK",
        "Newcastle", "Belfast, Northern Ireland", "Cambridge, England", "Cambridge, MA",
        "Cambridge, Massachusetts, United States", "Oxford", "Reading, England", "Scotland",
        "Scotland, United Kingdom", "Wales", "Northern Ireland", "Dublin, Ireland", "Ireland",
        "Berlin, Germany", "Paris, France", "Amsterdam, Netherlands", "Madrid, Spain",
        "Warsaw, Poland", "Bengaluru, India", "Sydney, Australia", "Canada",
        "New York, United States", "United States", "USA"],
}
# A remote title passes everything except a named country that is not home.
REMOTE_FAILS = [
    "Remote, India", "Remote - Germany", "Remote - Canada",
    "Manchester, New Hampshire, United States", "Sale, Australia",
    "Cambridge, Massachusetts, United States", "Dublin, Ireland", "Ireland", "Berlin, Germany",
    "Paris, France", "Amsterdam, Netherlands", "Madrid, Spain", "Warsaw, Poland",
    "Bengaluru, India", "Sydney, Australia", "Canada", "New York, United States",
    "United States", "USA",
    # Changed on purpose: a country code is read as written, so "US" is the United
    # States wherever a remote role names it.
    "Manchester, NH, US",
    "Remote (EU)"]
# A region named beside "remote" is judged by whether it takes in home. Changed on
# purpose: these were all flagged for Tier 2 while the gate kept its own list of
# region words. EMEA and Europe take in the UK, so a role remote within them passes;
# the EU does not, so it fails (above). A home the table cannot place still flags
# (tests/test_where_the_work_can_be_done_from.py).
# Changed on purpose: a remote role anchored in a US state is not a nominal office for
# somebody in the UK (places.subdivision_abroad), so these are flagged for Tier 2, as
# "Remote - Canada" is failed and the same places with the country named are.
REMOTE_FLAGS: list = ["Manchester, NH", "New York, NY", "San Diego, CA", "Austin, TX",
                      "Cambridge, MA"]
# fit.py prices a FLAG by its reason, so those are held to the word.
FLAG_REASONS = {
    "location not recognized; Tier 2 decides": [
        "Austin, TX", "EMEA", "Europe", "New York, NY", "North West England", "North West",
        "Northgate, Wexmoor", "Northgate", "San Diego, CA", "Somewhere, Nowhere", "Wexmoor"],
    "England city not on the Greater Manchester list; Tier 2 decides": [
        "Aylesbury, England, United Kingdom"],
    "a commutable northern city; considered, never auto-dropped": [
        "Leeds, England, United Kingdom", "Liverpool", "Preston, England", "Sheffield",
        "Warrington"],
    "no location stated; Tier 2 decides": [""],
}
WIDE =[loc for locs in GATE.values() for loc in locs]


def test_the_location_gate_gives_what_it_gave():
    for verdict, locs in GATE.items():
        for loc in locs:
            assert prefilter.location_verdict(loc)[0] == verdict, loc
            assert prefilter.location_verdict(loc, "Remote Sensing Analyst")[0] == verdict, loc
    for loc in WIDE:
        want = "FAIL" if loc in REMOTE_FAILS else "FLAG" if loc in REMOTE_FLAGS else "PASS"
        assert prefilter.location_verdict(loc, "Remote Data Analyst")[0] == want, loc
    for reason, locs in FLAG_REASONS.items():
        for loc in locs:
            assert prefilter.location_verdict(loc) == ("FLAG", reason), loc


_OLD_ABROAD_SHORT = re.compile(r"\b(?:us|usa|u\.s\.|uk|eu|emea|apac|latam|united states|"
                               r"united kingdom|europe)\b", re.I)


def _old_residence_cut(text):
    """text_screen.residence_cut as it was, reading search.py LOCATION itself."""
    loc = dict(getattr(person.module("search"), "LOCATION", {}) or {})
    home = loc.get("home_country_rx")
    others = [str(c).lower() for c in loc.get("other_countries", [])]
    for s in text_screen.sentences(text):
        if not text_screen.RESIDE.search(s):
            continue
        low = s.lower()
        if home is not None and home.search(low):
            continue
        if (any(re.search(r"\b" + re.escape(c) + r"\b", low) for c in others)
                or _OLD_ABROAD_SHORT.search(low)):
            return s[:220]
    return None


RESIDENCE = [
    ("Candidates must be based in the US or Spain.", True),
    ("You must be based in the UK or Ireland.", False),
    ("You must be located in the EU.", True),
    ("Must be based in one of our hub countries (US, UK, Spain, Kenya and Ghana).", False),
    ("You need to be based within commuting distance of Manchester.", False),
    # Changed on purpose: EMEA and Europe take in the UK, the example's home, so living
    # there is no requirement to live abroad (tools/places.py REGION_MEMBERS).
    ("Candidates should be based in EMEA.", False),
    ("Candidates must be based in APAC or LATAM.", True),
    ("We need to be based in Europe for this role.", False),
    ("Candidates must be based in Dublin, Ireland.", True),
    ("Candidates must be based in Sale, Australia.", True),
    ("Candidates must be based in Manchester, NH, US.", True),
    ("Candidates must be based in London.", False),
    ("You must live in Paris, France to apply.", True),
    ("This role is open only to candidates based in Berlin, Germany.", True),
]


def test_the_residence_cut_gives_what_it_gave():
    body = " You will build planning models in SQL and Python."
    for sentence, cut in RESIDENCE:
        assert bool(text_screen.residence_cut(sentence + body)) is cut, sentence
    for loc in WIDE:
        for shape in ("Candidates must be based in {}.", "You must live in {} to apply.",
                      "This role is open only to candidates based in {}."):
            text = shape.format(loc) + body
            if loc in HOME_NATION or loc in ("EMEA", "Europe"):
                # Changed on purpose: the old cut read "ireland" inside "Northern
                # Ireland" as the Republic. A home nation is home, so living there
                # is no requirement to live abroad (the location gate still reads it).
                assert text_screen.residence_cut(text) is None, text
                continue
            assert text_screen.residence_cut(text) == _old_residence_cut(text), text


HOME_NATION = ("Belfast, Northern Ireland", "Northern Ireland")


def test_a_country_written_in_capitals_still_fails_at_the_gate(monkeypatch):
    # prefilter kept the profile's list as written and compared it with the lower-cased
    # location; places.py lower-cases it. A profile writing "Germany" passed every
    # on-site role in Germany at the gate.
    import importlib
    spec = dict(person.module("search").LOCATION, other_countries=["Germany", "France"])
    monkeypatch.setattr(person.module("search"), "LOCATION", spec)
    try:
        importlib.reload(places)
        fresh = importlib.reload(prefilter)
        assert fresh.location_verdict("Berlin, Germany")[0] == "FAIL"
        assert fresh.location_verdict("Remote, France")[0] == "FAIL"
    finally:
        monkeypatch.undo()
        importlib.reload(places)
        importlib.reload(prefilter)


def test_a_row_is_placed_and_aged_once(monkeypatch):
    # annotate took decide's verdict and then worked out the place and the age again.
    calls = []
    real = prefilter.location_verdict
    monkeypatch.setattr(prefilter, "location_verdict",
                        lambda *a, **k: calls.append(a) or real(*a, **k))
    ok, row = prefilter.annotate({"title": "Data Analyst", "company": "Oakmere Foods",
                                  "location": "Manchester", "date": "2026-10-18"},
                                 dt.date(2026, 10, 20))
    assert ok and row["location_verdict"] == "PASS" and row["age_days"] == 2
    assert len(calls) == 1
