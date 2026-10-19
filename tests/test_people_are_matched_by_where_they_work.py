"""A person is at an employer when their result names it as where they work.

Four ways a real run got that wrong, each with the names invented here:

- A search for a one-word employer finds everyone with that first name, and a
  result naming no employer came back "likely" at the employer on the strength of
  the name. A post's author was kept the same way, because the check read the
  whole post title, author's name included. And a university in a title, read as a
  location, left its student "likely" at an employer it is not.
- The employer under another of its names was dropped as "works at <it>, not the
  employer": its ratings or analytics arm ("<Name> Ratings", "<Name> Data &
  Services") and its brand line ("<Brand>, AI by <Parent>" for "<Parent> <Brand>").
- "<function> @ <Employer>" was read as an employer called "<function> @ <Employer>".
- A comma made a title a location: "Data Science, Data & AI Strategy" and a team
  named after the bank it sits in, which no city matched, so the person ranked as
  out of market.
"""
import datetime
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "network"))
import discovery  # noqa: E402
import reading  # noqa: E402
import sources  # noqa: E402
import state  # noqa: E402

TODAY = datetime.date(2026, 10, 18)


def _url(handle):
    return "https://www.linkedin.com/in/example-person-" + handle


def _post(handle, day=datetime.date(2026, 10, 10)):
    ms = int(datetime.datetime(day.year, day.month, day.day, tzinfo=datetime.timezone.utc)
             .timestamp() * 1000)
    return f"https://www.linkedin.com/posts/{handle}_consulting-activity-{ms << 22}-AbCd"


def _harvest(results, company, **kw):
    return sources.harvest(results, company, today=TODAY, connections=[], contacts=[], **kw)


# ------------------------------------------------------------ a name is not an employer

def test_a_first_name_that_spells_a_one_word_employer_is_not_a_contact_there():
    results = [
        {"title": "Wren Halloway - Data Consultant", "url": _url("wren-h")},
        {"title": "Wren Achterberg on LinkedIn: three lessons from a year of consulting",
         "url": _post("example-wren-a")},
        {"title": "Corwin Haldane - Head of Data - Wren", "url": _url("corwin")},
    ]
    got = _harvest(results, "Wren", query="Wren Head of Data Manchester")
    assert [p["name"] for p in got["keep"]] == ["Corwin Haldane"]
    assert got["keep"][0]["profile_status"] == "verified"
    why = {p["name"]: w for p, w in got["dropped"]}
    assert why["Wren Halloway"].startswith("the search matched their name, not Wren")
    # A post is its author's only when the post itself names the employer.
    people = discovery.people_from_results(results, "Wren", today=TODAY)
    assert "Wren Achterberg" not in [p["name"] for p in people]
    # A name check looks for that name on purpose: the page that named them gave the
    # employer, so their profile stays as likely as before.
    check = _harvest(results[:1], "Wren", kind="profile_check", name="Wren Halloway",
                     known={"title": "Data Consultant", "evidence": "a speaker list"})
    assert [(p["name"], p["profile_status"]) for p in check["keep"]] == [("Wren Halloway", "likely")]
    # Nobody at the employer came back: the name matches are not a verdict on it.
    only_names = discovery.triage(discovery.people_from_results(results[:1], "Wren", today=TODAY),
                                  today=TODAY, target_company="Wren")
    assert only_names["verdict"] == "no_results" and not only_names["keep"]


def test_an_institution_in_the_title_is_where_they_are_never_a_place():
    title = "Tamsin Oyelaran - University of Larkspur, Faculty of Science"
    got = discovery.parse_result_title(title)
    assert (got["employer"], got["location"]) == ("University of Larkspur", "")
    run = _harvest([{"title": title, "url": _url("tamsin")}], "Wren")
    assert not run["keep"]
    assert any(p["name"] == "Tamsin Oyelaran" and w.startswith("works at University of Larkspur")
               for p, w in run["dropped"])
    # A word that only contains the employer's name is not the employer: "Garden" is
    # not "Arden". A substring test made this one "likely".
    parsed = discovery.parse_result_title("Rhian Pellow - Student at Garden City College")
    assert discovery.profile_status(parsed, _url("rhian"), "Arden") == "unconfirmed"


# ------------------------------------------------------------ the employer, by any of its names

@pytest.mark.parametrize("a,b", [
    ("Fernhill Ratings", "Fernhill"),
    ("Fernhill Ratings", "Fernhill Solutions"),
    ("Brindle's Analytics", "Brindle's"),
    ("Kestrel Data & Services", "Kestrel"),
    ("Quillfeather, AI by Brannock", "Brannock Quillfeather"),
    ("Quillfeather, AI by Brannock", "Brannock"),
    ("Kestrel Mutual Ltd", "Kestrel Mutual"),
])
def test_a_business_line_or_a_brand_line_is_the_same_employer(a, b):
    assert discovery.same_employer(a, b) and discovery.same_employer(b, a)


@pytest.mark.parametrize("a,b", [
    ("Fernhill Freight", "Fernhill"),          # another firm that starts the same way
    ("University of Larkspur", "Larkspur"),
    ("Royal Fernhill", "Fernhill"),
    ("", "Fernhill"),
])
def test_a_different_employer_that_shares_a_word_is_not_the_same(a, b):
    assert not discovery.same_employer(a, b)


def test_people_at_the_employer_under_another_name_are_kept_and_filed_under_its_name():
    results = [
        {"title": "Corwin Haldane - Partner @ Quillfeather, AI by Brannock", "url": _url("corwin")},
    ]
    got = _harvest(results, "Brannock Quillfeather")
    assert [p["name"] for p in got["keep"]] == ["Corwin Haldane"]
    p = got["keep"][0]
    assert p["profile_status"] == "verified" and p["company"] == "Brannock Quillfeather"

    results = [
        {"title": "Fenella Quarrie - Lead Data Scientist - Fernhill Ratings", "url": _url("fenella")},
        {"title": "Hal Okonedo - Head of Data - Fernhill Analytics", "url": _url("hal")},
    ]
    got = _harvest(results, "Fernhill")
    assert {p["name"] for p in got["keep"]} == {"Fenella Quarrie", "Hal Okonedo"}
    # Filed under the employer searched, so the contact joins an application there.
    assert {p["company"] for p in got["keep"]} == {"Fernhill"}
    assert all(p["profile_status"] == "verified" for p in got["keep"])


def test_a_read_page_naming_the_brand_line_has_not_moved_on():
    page = {"name": "Corwin Haldane", "company": "Brannock Quillfeather", "headline": "Partner",
            "current": "Quillfeather, AI by Brannock", "location": "", "items": [], "about": ""}
    assert reading.verdict(page, "Brannock Quillfeather") == (True, "")
    assert not reading.verdict(dict(page, current="Fenwick Lane Insurance"),
                               "Brannock Quillfeather")[0]


def test_a_connection_at_a_business_line_is_a_connection_at_the_employer():
    conns = [{"name": "Hal Okonedo", "company": "Fernhill Analytics", "title": "Head of Data",
              "linkedin_url": _url("hal")},
             {"name": "Rhian Pellow", "company": "Fernhill Freight", "title": "Data Analyst",
              "linkedin_url": _url("rhian")}]
    assert [c["name"] for c in state.connections_at(conns, "Fernhill")] == ["Hal Okonedo"]


# ------------------------------------------------------------ "<function> @ <Employer>"

def test_a_function_at_an_employer_is_a_job_there():
    got = discovery.parse_result_title("Bastian Merriweather - Data @ Larkspur Retail")
    assert (got["headline"], got["employer"]) == ("Data @ Larkspur Retail", "Larkspur Retail")
    run = _harvest([{"title": "Bastian Merriweather - Data @ Larkspur Retail",
                     "url": _url("bastian")}], "Larkspur Retail")
    assert [p["name"] for p in run["keep"]] == ["Bastian Merriweather"]
    assert run["keep"][0]["profile_status"] == "verified"


# ------------------------------------------------------------ a comma is not a place

@pytest.mark.parametrize("title,company,want", [
    ("Rosalind Achterberg - Data Science, Data & AI Strategy", "",
     ("Data Science, Data & AI Strategy", "", "")),
    ("Rosalind Achterberg - Northgate Bank, Data Governance Team", "",
     ("Northgate Bank, Data Governance Team", "", "")),
    ("Rosalind Achterberg - Northgate Bank, Data Governance Team", "Northgate Bank",
     ("Data Governance Team", "Northgate Bank", "")),
    # Places stay places: the profile's own, a country its location gate knows, a
    # place's shape, and a job with its place.
    ("Idris Corrie - Manchester, England, United Kingdom", "",
     ("", "", "Manchester, England, United Kingdom")),
    ("Idris Corrie - Lyon, Rhone, France", "", ("", "", "Lyon, Rhone, France")),
    ("Idris Corrie - San Francisco Bay Area", "", ("", "", "San Francisco Bay Area")),
    ("Idris Corrie - Manchester", "", ("", "", "Manchester")),
    ("Anna Lee - Head of Data, Greater Manchester", "", ("Head of Data", "", "Greater Manchester")),
    ("Anna Lee - Head of Data at Kestrel Mutual, Greater Manchester", "",
     ("Head of Data at Kestrel Mutual, Greater Manchester", "Kestrel Mutual", "Greater Manchester")),
    ("Gideon Ashworth - Former President and CEO, Kestrel Mutual", "",
     ("Former President and CEO", "Kestrel Mutual", "")),
    # A name is not a place because it has a place's word in it.
    ("Gideon Ashworth - Kestrel State Bank", "", ("", "Kestrel State Bank", "")),
    ("Gideon Ashworth - Greater Kestrel Analytics", "", ("", "Greater Kestrel Analytics", "")),
])
def test_a_title_with_a_comma_is_a_place_only_when_it_names_one(title, company, want):
    got = discovery.parse_result_title(title, company) if company else \
        discovery.parse_result_title(title)
    assert (got["headline"], got["employer"], got["location"]) == want


def test_a_team_title_ranks_on_its_job_not_as_somebody_out_of_market():
    results = [{"title": "Rosalind Achterberg - Data Science, Data & AI Strategy",
                "url": _url("rosalind")},
               {"title": "Corwin Haldane - Kestrel Mutual, Data Governance Team",
                "url": _url("corwin")}]
    got = _harvest(results, "Kestrel Mutual")
    assert not any("not in" in w for _, w in got["dropped"]), got["dropped"]
    by = {p["name"]: p for p in got["keep"]}
    assert by["Rosalind Achterberg"]["location"] == "" and by["Rosalind Achterberg"]["location_unverified"]
    assert by["Corwin Haldane"]["profile_status"] == "verified"
    assert by["Corwin Haldane"]["title"] == "Data Governance Team"
