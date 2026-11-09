"""Who to write to is one call, from each person's own settings (acceptance test T13).

A "find 10 people" run on 2026-11-09 put names from search results on its list and only then
found that recruiters there hired for sales, for corporate finance or for engineers, that
five employers already had two people waiting on a reply, and that someone had been written
to a fortnight before; it swapped people out, searched again and stopped at eight.
`candidates.py check` now filters on the search result's headline, runs every list check
and ranks by who is likeliest to help, in one call, before anyone reaches the list.

Three made-up people, none of them the maintainer: a nurse in Vancouver, a remote software
engineer and a career changer with no laptop. Each runs in its own process with its own
profile, as a person's copy does.
"""
from __future__ import annotations

import csv
import datetime
import json
import os
import shutil
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The app's own day, never a fixed one: these commands count from it (person.today), and
# the suite runs with the clock moved on too (tools/everywhere.sh, 30 to 400 days).
_DAY = datetime.date.today()
TODAY = _DAY.isoformat()
WEEK_AGO = (_DAY - datetime.timedelta(days=7)).isoformat()
SIX_DAYS_AGO = (_DAY - datetime.timedelta(days=6)).isoformat()


def _profile(tmp_path, networking="", search="", employers="", roles=""):
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d)
    for name, extra in (("networking.py", networking), ("search.py", search),
                        ("employers.py", employers), ("roles.py", roles)):
        if extra:
            with open(d / name, "a", encoding="utf-8") as fh:
                fh.write("\n\nimport re\n" + extra + "\n")
    (tmp_path / "state").mkdir()
    return d


def _book(tmp_path, rows):
    path = tmp_path / "state" / "network_contacts.csv"
    cols = ["contact_id", "name", "company", "title", "status", "first_contacted", "channel"]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def _run(tmp_path, people, *args):
    f = tmp_path / "people.json"
    f.write_text(json.dumps(people), encoding="utf-8")
    env = dict(os.environ, LJS_PROFILE=str(tmp_path / "profile"),
               LJS_STATE=str(tmp_path / "state"), LJS_LEDGER=str(tmp_path / "ledger"),
               LJS_TODAY=TODAY, LJS_COPY="private")
    got = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "network", "candidates.py"),
                          "check", str(f), *args], env=env, capture_output=True,
                         encoding="utf-8", timeout=180)
    assert got.returncode == 0, got.stdout + got.stderr
    return got.stdout


def _check(tmp_path, people, *args):
    return json.loads(_run(tmp_path, people, "--json", *args))


def _p(name, title, company, location, slug):
    return {"name": name, "title": title, "company": company, "location": location,
            "linkedin_url": f"https://www.linkedin.com/in/{slug}-example"}


def _names(rows):
    return [r["name"] for r in rows]


def _out(got):
    return {o["name"]: o["why"] for o in got["out"]}


# ---------------------------------------------------------------- a nurse in Vancouver

NURSE_NET = '''
HOME_CITY = "Vancouver"
FUNCTION_TITLE = re.compile(r"\\b(nurs\\w*|clinical|patient care|paediatric\\w*|pediatric\\w*)\\b", re.I)
TITLE_SETS = {"hiring_authority": ["Nurse Manager", "Director of Nursing"],
              "senior_ic": ["Clinical Nurse Specialist", "Charge Nurse"],
              "function": ["Registered Nurse", "Paediatric Nurse"],
              "recruiting": ["Nurse Recruiter", "Clinical Recruiter"]}
PER_EMPLOYER_PER_RUN = 1
'''
NURSE_SEARCH = '''
OTHER_COUNTRIES = ["united states", "usa", "united kingdom", "australia"]
LOCATION = dict(LOCATION, home_country="Canada", home_country_rx=re.compile(r"\\b(canada)\\b"),
                home_country_alone=["canada"], other_countries=OTHER_COUNTRIES, outside=[],
                metro_name="Metro Vancouver", metro=["vancouver", "burnaby", "surrey"])
'''
NURSE_EMP = 'TIER_1 = {"fraserline health", "coastwell children\'s hospital"}\n'


def test_a_nurse_in_vancouver(tmp_path):
    _profile(tmp_path, NURSE_NET, NURSE_SEARCH, NURSE_EMP)
    _book(tmp_path, [])
    van = "Vancouver, British Columbia, Canada"
    people = [
        _p("Ana Rook", "Nurse Recruiter", "Fraserline Health", van, "ana-rook"),
        _p("Bo Venn", "Senior Sales Recruiter", "Fraserline Health", van, "bo-venn"),
        _p("Juno Orrin", "IT Recruiter", "Coastwell Children's Hospital", van, "juno-orrin"),
        _p("Riley Reed", "Clinical Nurse Manager, Paediatrics", "Coastwell Children's Hospital",
           van, "riley-reed"),
        _p("Wren Allard", "Registered Nurse", "Coastwell Children's Hospital",
           "Seattle, Washington, United States", "wren-allard"),
        _p("Quinn Pell", "Software Engineer", "Fraserline Health", van, "quinn-pell"),
        _p("Sasha Lee", "Charge Nurse", "Fraserline Health", van, "sasha-lee"),
        _p("Tamsin Oyelaran", "Nurse Recruiter", "Quickmart Pharmacy", van, "tamsin-o"),
        _p("Ana Rook", "Nurse Recruiter", "Fraserline Health", van, "ana-rook"),
    ]
    got = _check(tmp_path, people, "--want", "3")
    out = _out(got)
    assert "not your function" in out["Bo Venn"] and "Sales" in out["Bo Venn"]
    assert "not your function" in out["Juno Orrin"]
    assert "United States" in out["Wren Allard"]
    assert "not your function" in out["Quinn Pell"]
    assert "bar" in out["Tamsin Oyelaran"]
    # One a run at an employer, as she set: the best at each.
    assert _names(got["chosen"]) == ["Ana Rook", "Riley Reed"]
    assert got["short"] == 1
    assert sum(1 for r in got["ranked"] if r["name"] == "Ana Rook") == 1      # once on one list
    blob = json.dumps(got).lower()
    assert "data" not in blob


# ---------------------------------------------------------------- a remote software engineer

ENG_NET = '''
HOME_CITY = ""
FUNCTION_TITLE = re.compile(r"\\b(software|engineer\\w*|developer|backend|frontend|platform|devops)\\b", re.I)
TITLE_SETS = {"hiring_authority": ["Engineering Manager", "Head of Engineering"],
              "senior_ic": ["Staff Software Engineer", "Principal Engineer"],
              "function": ["Software Engineer", "Backend Engineer"],
              "recruiting": ["Technical Recruiter"]}
REPLY_RATES = {"recruiter": (6, 10), "peer": (1, 40), "senior_peer": (1, 20)}
'''
ENG_EMP = 'TIER_1 = {"nimbus cloud", "larkspur systems"}\n'


def test_a_remote_software_engineer(tmp_path):
    _profile(tmp_path, ENG_NET, "", ENG_EMP)
    # Two people at one employer already waiting on a reply, written to last week.
    _book(tmp_path, [
        {"contact_id": "larkspur_a", "name": "Corwin Haldane", "company": "Larkspur Systems",
         "status": "awaiting_reply", "first_contacted": WEEK_AGO, "channel": "connection"},
        {"contact_id": "larkspur_b", "name": "Zoe Ruiz", "company": "Larkspur Systems",
         "status": "awaiting_reply", "first_contacted": SIX_DAYS_AGO, "channel": "connection"},
    ])
    uk = "United Kingdom"
    people = [
        _p("Idris Corrie", "Staff Software Engineer", "Nimbus Cloud", uk, "idris"),
        _p("Rhian Pellow", "Technical Recruiter", "Nimbus Cloud", uk, "rhian"),
        _p("Mira Stavros", "Recruiter, Finance & Accounting", "Nimbus Cloud", uk, "mira"),
        _p("Hal Okonedo", "Account Executive", "Nimbus Cloud", uk, "hal"),
        _p("Pip Varga", "Engineering Manager, Platform", "Larkspur Systems", uk, "pip"),
        _p("Zoe Ruiz", "Senior Developer", "Larkspur Systems", uk, "zoe-ruiz"),
    ]
    got = _check(tmp_path, people, "--want", "5")
    out = _out(got)
    assert "not your function" in out["Mira Stavros"]
    assert "Account Executive".lower() in out["Hal Okonedo"].lower() or "revenue" in out["Hal Okonedo"]
    assert "waiting on a reply" in out["Pip Varga"]           # the employer's limit, at once
    assert "Zoe Ruiz" in out                                   # already written to
    # Their own reply rates: recruiters answer them most, so the recruiter comes first.
    assert _names(got["chosen"]) == ["Rhian Pellow", "Idris Corrie"]
    assert "recruiters answer you more often" in got["chosen"][0]["why"]


# ---------------------------------------------------------------- a career changer, no laptop

CHANGER_NET = '''
PROFILE_READS = "paste"
FUNCTION_TITLE = re.compile(r"\\b(ux|ui|user experience|user research\\w*|product design\\w*|designer)\\b", re.I)
TITLE_SETS = {"hiring_authority": ["Head of Design", "Design Manager"],
              "senior_ic": ["Senior Product Designer"],
              "function": ["Product Designer", "UX Designer", "UX Researcher"],
              "recruiting": ["Design Recruiter"]}
'''
CHANGER_ROLES = '''
ROLES = [dict(employer="Harbour Kitchens", title="Sous Chef", dates="Jan 2018 - Aug 2025",
              loc="Manchester, UK", short="HK", tenure_months=90, floor=2, cap=4)]
'''


def test_a_career_changer_with_no_laptop(tmp_path):
    _profile(tmp_path, CHANGER_NET, "", "", CHANGER_ROLES)
    _book(tmp_path, [])
    mcr = "Manchester, England, United Kingdom"
    people = [
        _p("Ana Rook", "UX Researcher", "Brightloom", mcr, "ana"),
        _p("Bo Venn", "Product Designer, ex-Harbour Kitchens", "Quillfield Studio", mcr, "bo"),
        _p("Juno Orrin", "Marketing Manager", "Brightloom", mcr, "juno"),
        _p("Riley Reed", "Data Scientist", "Quillfield Studio", mcr, "riley"),
        _p("Wren Allard", "Founder", "Pebblework", mcr, "wren"),
    ]
    got = _check(tmp_path, people, "--want", "3")
    out = _out(got)
    assert "not your function" in out["Juno Orrin"] and "not your function" in out["Riley Reed"]
    # Somebody who left the same kitchen comes first: shared background.
    assert got["chosen"][0]["name"] == "Bo Venn"
    assert "worked at Harbour Kitchens, like you" in got["chosen"][0]["why"]
    assert set(_names(got["chosen"])) == {"Bo Venn", "Ana Rook", "Wren Allard"}
    # And they are added to the contact book in one go, never twice.
    text = _run(tmp_path, people, "--want", "3", "--add")
    assert "3 chosen" in text
    _run(tmp_path, people, "--want", "3", "--add")
    with open(tmp_path / "state" / "network_contacts.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert sorted(r["name"] for r in rows) == ["Ana Rook", "Bo Venn", "Wren Allard"]


def test_a_short_run_says_so_and_widens_never_pads(tmp_path):
    _profile(tmp_path, NURSE_NET, NURSE_SEARCH, NURSE_EMP)
    _book(tmp_path, [])
    van = "Vancouver, British Columbia, Canada"
    text = _run(tmp_path, [_p("Ana Rook", "Nurse Recruiter", "Fraserline Health", van, "a")],
                "--want", "4")
    assert "1 chosen of the 4 wanted" in text
    assert "short: 3 more to find" in text and "Never padded" in text
    assert "coastwell children" in text.lower()                # the next employer to search


def test_the_one_surfacing_check_holds_the_per_employer_limit(tmp_path):
    """The check before anyone is shown passed people at an employer that already had two
    waiting on a reply, which only the short list held (2026-11-09). One check now."""
    _profile(tmp_path, ENG_NET, "", ENG_EMP)
    _book(tmp_path, [
        {"contact_id": "larkspur_a", "name": "Corwin Haldane", "company": "Larkspur Systems",
         "status": "awaiting_reply", "first_contacted": WEEK_AGO, "channel": "connection"},
        {"contact_id": "larkspur_b", "name": "Zoe Ruiz", "company": "Larkspur Systems",
         "status": "awaiting_reply", "first_contacted": SIX_DAYS_AGO, "channel": "connection"},
    ])
    people = [_p("Pip Varga", "Engineering Manager", "Larkspur Systems", "United Kingdom", "pip"),
              _p("Idris Corrie", "Staff Software Engineer", "Nimbus Cloud", "", "idris"),
              _p("Rhian Pellow", "Technical Recruiter", "Nimbus Cloud", "", "rhian"),
              _p("Hal Okonedo", "Backend Engineer", "Nimbus Cloud", "", "hal")]
    f = tmp_path / "list.json"
    f.write_text(json.dumps(people), encoding="utf-8")
    env = dict(os.environ, LJS_PROFILE=str(tmp_path / "profile"),
               LJS_STATE=str(tmp_path / "state"), LJS_LEDGER=str(tmp_path / "ledger"),
               LJS_TODAY=TODAY, LJS_COPY="private")
    got = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "network", "surface.py"),
                          "--file", str(f)], env=env, capture_output=True, encoding="utf-8",
                         timeout=120)
    lines = got.stdout.splitlines()
    assert any(x.startswith("NOT   Pip Varga") and "waiting on a reply" in x for x in lines), \
        got.stdout + got.stderr
    assert any(x.startswith("SHOW  Idris Corrie") for x in lines)
    assert any(x.startswith("SHOW  Rhian Pellow") for x in lines)
    # A list to write to, best first: the third at one employer is past its limit of two.
    assert any(x.startswith("NOT   Hal Okonedo") and "on this list" in x for x in lines), \
        got.stdout
