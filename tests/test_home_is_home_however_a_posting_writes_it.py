"""Where a posting says the work may be done from, read the same way by both gates.

- A remote location that names a country and a region taking in home is remote from
  home: "Remote (US, EMEA)" failed for somebody in the UK, because the country checks
  ran before the region was read, while the text screen read the same list as home.
- The person's own country written as a code is home: "Remote, US" failed and "US
  residents only" was cut for somebody in the US whose home pattern left out the code,
  and a neighbour written as a code failed where the same country written out was flagged.
- A time zone is hours, not a home: "must be based in a US time zone" was cut as a
  requirement to live abroad.
- A country the profile's own list leaves out is still somewhere else: "Remote - Canada"
  passed clean for somebody in Germany. It is flagged, never passed or failed unread.

Every person here is invented: the example person, or the example with its home moved.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
EXAMPLE = os.path.join(ROOT, "profile.example")
sys.path.insert(0, TOOLS)

import prefilter  # noqa: E402
import text_screen  # noqa: E402

RESIDENCE = text_screen.CUTS["residence"][0]


def _ruling(sentence):
    return f'{RESIDENCE}: "{sentence}"'


# ------------------------------------------------------------- the example, in the UK

@pytest.mark.parametrize("loc", ["Remote (US, EMEA)", "Remote (Europe/US)", "Remote: EMEA, US",
                                 "Remote - USA / Europe", "Remote (Canada, Europe)",
                                 "Remote - North America or EMEA"])
def test_a_region_that_takes_in_home_passes_whatever_country_is_beside_it(loc):
    verdict, why = prefilter.location_verdict(loc)
    assert verdict == "PASS", why
    assert "takes in United Kingdom" in why


@pytest.mark.parametrize("loc", ["Remote, US", "Remote (US only)", "Remote - North America",
                                 "Remote - United States", "Remote, Germany"])
def test_a_remote_role_for_somewhere_else_still_fails(loc):
    assert prefilter.location_verdict(loc)[0] == "FAIL"


def test_a_country_the_profile_does_not_list_is_flagged_not_passed():
    verdict, why = prefilter.location_verdict("Remote, Japan")
    assert verdict == "FLAG" and "japan" in why


@pytest.mark.parametrize("sentence", ["Candidates must be based in a US time zone.",
                                      "You must be located within EU time zones."])
def test_a_time_zone_is_hours_not_a_home(sentence):
    assert text_screen.residence_cut(sentence) is None
    # and a ruling the earlier screen saved on it is one today's screen refuses
    assert text_screen.ruling_refused(_ruling(sentence))


@pytest.mark.parametrize("sentence", ["Must be based in the US (Eastern time preferred).",
                                      "Candidates must be based in the US or Spain.",
                                      "You must be located in the EU."])
def test_a_requirement_to_live_elsewhere_is_still_cut_and_its_ruling_stands(sentence):
    assert text_screen.residence_cut(sentence)
    assert not text_screen.ruling_refused(_ruling(sentence))


# ------------------------------------------------------------- the example, moved

def _home(tmp_path, country, location):
    prof = tmp_path / "profile"
    shutil.copytree(EXAMPLE, prof)
    pj = prof / "person.json"
    data = json.loads(pj.read_text(encoding="utf-8"))
    data.setdefault("identity", {})["country"] = country
    pj.write_text(json.dumps(data), encoding="utf-8")
    with open(prof / "search.py", "a", encoding="utf-8") as fh:
        fh.write(f"\n\n# An invented person living elsewhere.\nPORTAL_COUNTRY = {country!r}\n"
                 f"LOCATION = {location}\n")
    return prof


ASK = """
import json, sys
sys.path.insert(0, %r)
import prefilter, text_screen
locs, sentences = json.loads(sys.argv[1]), json.loads(sys.argv[2])
print(json.dumps({"loc": {l: prefilter.location_verdict(l)[0] for l in locs},
                  "cut": {s: bool(text_screen.residence_cut(s)) for s in sentences},
                  "refused": {s: text_screen.ruling_refused(%r + ': "' + s + '"')
                              for s in sentences}}))
""" % (TOOLS, RESIDENCE)


def _ask(prof, locs=(), sentences=()):
    env = {**os.environ, "LJS_PROFILE": str(prof)}
    out = subprocess.run([sys.executable, "-c", ASK, json.dumps(list(locs)),
                          json.dumps(list(sentences))],
                         env=env, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


US = """dict(
    home_country="United States", home_country_rx=re.compile(r"\\b(united states|usa)\\b"),
    home_country_alone=["united states", "usa"], region_word="state",
    regions={"new york": "NY", "ny": "NY"}, home_region="NY", home_region_name="New York",
    home_region_alone=[], home_region_reason="New York-wide, includes remote",
    metro_name="New York City", metro=["new york", "brooklyn"], outside=["chicago", "austin"],
    other_countries=["united kingdom", "germany", "india", "mexico"],
    neighbour=dict(states=["bc"], words=re.compile(r"\\bcanada\\b"),
                   metros=re.compile(r"\\bvancouver\\b"),
                   remote_reason="remote but anchored in the neighbour",
                   onsite_reason="on-site in the neighbour"),
    flag_places=[])"""

MEXICO = """dict(
    home_country="Mexico", home_country_rx=re.compile(r"\\bmexico\\b"),
    home_country_alone=["mexico"], region_word="state", regions={"jalisco": "JAL"},
    home_region="JAL", home_region_name="Jalisco", home_region_alone=[],
    home_region_reason="Jalisco-wide, includes remote", metro_name="Guadalajara",
    metro=["guadalajara", "zapopan"], outside=["monterrey"],
    other_countries=["spain", "colombia", "united kingdom"],
    neighbour=dict(states=["tx", "az"], words=re.compile(r"\\b(united states|usa)\\b"),
                   metros=re.compile(r"\\b(houston|phoenix)\\b"),
                   remote_reason="remote but anchored in the neighbour",
                   onsite_reason="on-site in the neighbour"),
    flag_places=[])"""

GERMANY = """dict(
    home_country="Germany", home_country_rx=re.compile(r"\\b(germany|deutschland)\\b"),
    home_country_alone=["germany"], region_word="state", regions={"berlin": "BE"},
    home_region="BE", home_region_name="Berlin", home_region_alone=[],
    home_region_reason="Berlin-wide, includes remote", metro_name="Berlin", metro=["berlin"],
    outside=["munich", "hamburg"],
    other_countries=["france", "united kingdom", "uk", "united states", "usa"],
    neighbour={}, flag_places=[])"""


def test_home_written_as_a_code_is_home(tmp_path):
    got = _ask(_home(tmp_path, "US", US),
               ["Remote, US", "Remote - US", "Remote (US only)", "Remote (US, EMEA)", "Remote, UK"],
               ["This role is remote within the US.", "US residents only.",
                "We only hire in the US.", "This role is remote within the UK."])
    assert got["loc"] == {"Remote, US": "PASS", "Remote - US": "PASS",
                          "Remote (US only)": "PASS", "Remote (US, EMEA)": "PASS",
                          "Remote, UK": "FAIL"}
    assert got["cut"] == {"This role is remote within the US.": False, "US residents only.": False,
                          "We only hire in the US.": False,
                          "This role is remote within the UK.": True}
    # A ruling the earlier screen saved on the person's own country lets go; a real one holds.
    assert got["refused"] == {s: not cut for s, cut in got["cut"].items()}


def test_a_uk_home_whose_pattern_leaves_out_the_code(tmp_path):
    prof = _home(tmp_path, "GB", 'dict(LOCATION, home_country_rx=re.compile('
                                 'r"\\b(united kingdom|great britain|britain)\\b"))')
    got = _ask(prof, ["Remote, UK", "Remote - U.K."], ["This role is remote within the UK."])
    assert set(got["loc"].values()) == {"PASS"}
    assert got["cut"] == {"This role is remote within the UK.": False}


def test_the_neighbour_written_as_a_code_is_flagged_like_the_neighbour_written_out(tmp_path):
    got = _ask(_home(tmp_path, "MX", MEXICO), ["Remote, US", "Remote - United States"])
    assert got["loc"] == {"Remote, US": "FLAG", "Remote - United States": "FLAG"}


def test_a_country_the_profile_does_not_list_is_flagged_for_somebody_in_germany(tmp_path):
    got = _ask(_home(tmp_path, "DE", GERMANY),
               ["Remote - Canada", "Remote, Japan", "Remote, Germany", "Remote (Canada, Europe)"])
    assert got["loc"] == {"Remote - Canada": "FLAG", "Remote, Japan": "FLAG",
                          "Remote, Germany": "PASS", "Remote (Canada, Europe)": "PASS"}
