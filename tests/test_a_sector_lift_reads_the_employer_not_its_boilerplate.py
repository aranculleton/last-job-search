"""A lift for the employer's sector or the work reads where the posting says so, never its
boilerplate: a travel requirement is no travel employer, a benefits line no sector, and
"stakeholder engagement" no consultancy.

From one person's rounds (2026-11-16, issue #306): over 73 postings the travel-industry lift
fired 11 times on "travel", none at a travel employer ("Travel Requirements: 15%", "travel to
customers in your region up to 30% of the time", "global travel coverage" in a benefits
list); the consulting lift fired 21 times on "stakeholder engagement"; and the work-life lift
20 times on a bare "hybrid", most of them office jobs. Every posting here is invented.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_state  # noqa: E402

SETTINGS = '''

# A test's own scoring words (tests/test_a_sector_lift_reads_the_employer_not_its_boilerplate.py),
# written the way a person's setup writes them: no entry says where it reads.
OPP_LEVERAGE = [
    (re.compile(r"\\b(airline|aviation|travel|tour|hotel|hospitality)\\b", re.I), 14,
     "a marquee name in travel"),
    (re.compile(r"\\b(consult|advisory|engagement)\\b", re.I), 10,
     "consulting delivery is the shape this employer hires for"),
    (re.compile(r"\\b(flexible (hours|working)|work[- ]life balance|hybrid|"
                r"4[- ]day (work )?week)\\b", re.I), 8, "signals of good work-life balance"),
    (re.compile(r"\\b(travel (up to )?[4-9]\\d ?%|(long hours|on[- ]call)\\b)", re.I), -12,
     "signals of long or unpredictable hours"),
    # Where the person's setup says where an entry reads: a media employer, and the work of
    # running experiments with the employer's own culture line set aside, in either order.
    (re.compile(r"\\b(media|streaming|content|audience)\\b", re.I), 14,
     "a marquee name to a media employer", "employer"),
    (re.compile(r"\\bexperiment\\w*", re.I), 12, "experiments are the work",
     "set_aside_self_portrait", "work"),
]
'''
DUTIES = ("You will build SQL and Python models for the credit risk team and present them to "
          "the people who act on them. ")
POSTINGS = {
    "travel_requirement": "Larkmoor Bank is hiring. " + DUTIES + "Travel Requirements: 15%.",
    "travel_to_customers": "Larkmoor Bank is hiring. " + DUTIES
                           + "You will travel to customers in your region up to 30% of the time.",
    "travel_benefit": "Larkmoor Bank is hiring. " + DUTIES
                      + "Benefits include a pension, dental care and global travel coverage.",
    "stakeholder_engagement": "Larkmoor Bank is hiring. " + DUTIES
                              + "You will lead stakeholder engagement across the risk function.",
    "bare_hybrid": "Larkmoor Bank is hiring. " + DUTIES
                   + "This role is hybrid, three days a week in our Leeds office.",
    "travel_employer": "About us: Skyrail Holidays is a travel company selling tours across "
                       "Europe. " + DUTIES,
    "flexible_hours": "Larkmoor Bank is hiring. " + DUTIES
                      + "We offer flexible hours and a 4-day week in summer.",
    "heavy_travel": "Larkmoor Bank is hiring. " + DUTIES + "Travel up to 50% of the time.",
    "consultancy": "About us: Fenmoor Advisory is a consulting firm working with lenders. "
                   + DUTIES,
    "content_duties": "Larkmoor Bank is hiring. " + DUTIES
                      + "You will write content about the models for a wide audience.",
    "media_employer": "Brightwave Media is a streaming service with ten million listeners. "
                      + DUTIES,
    "culture_line": "Larkmoor Bank is hiring. " + DUTIES
                    + "We pride ourselves on a culture of experimentation.",
    "experiments": "Larkmoor Bank is hiring. " + DUTIES
                   + "You will design experiments on the mobile app.",
}
EMPLOYERS = {"travel_employer": "Skyrail Holidays", "consultancy": "Fenmoor Advisory",
             "media_employer": "Brightwave Media"}


def _scored(tmp_path):
    prof = app_state.profile_copy(str(tmp_path / "profile"))
    with open(os.path.join(prof, "search.py"), "a", encoding="utf-8", newline="\n") as fh:
        fh.write(SETTINGS)
    rows = [{"title": "Data Analyst", "company": EMPLOYERS.get(k, "Larkmoor Bank"),
             "url": f"https://jobs.example/{k}", "location": "Leeds, England, United Kingdom",
             "date": "2026-11-14", "desc": v} for k, v in POSTINGS.items()]
    src, out = tmp_path / "in.json", tmp_path / "out.json"
    src.write_text(json.dumps(rows), encoding="utf-8")
    env = dict(os.environ, LJS_PROFILE=prof, PYTHONUTF8="1")
    run = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "opportunity.py"),
                          str(src), "--out", str(out), "--today", "2026-11-16"],
                         capture_output=True, text=True, encoding="utf-8", env=env, cwd=ROOT)
    assert run.returncode == 0, run.stderr
    why = {r["url"].rsplit("/", 1)[1]: " | ".join(r["why"])
           for r in json.loads(out.read_text(encoding="utf-8"))}
    return why, lambda: subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "opportunity.py"), str(src),
         "--leverage-words"], capture_output=True, text=True, encoding="utf-8", env=env, cwd=ROOT)


def test_boilerplate_earns_no_lift_and_the_employers_own_words_do(tmp_path):
    why, _ = _scored(tmp_path)
    for k in ("travel_requirement", "travel_to_customers", "travel_benefit", "heavy_travel"):
        assert "marquee name in travel" not in why[k], (k, why[k])
    assert "consulting delivery" not in why["stakeholder_engagement"]
    assert "work-life balance" not in why["bare_hybrid"]
    # The employer saying what it is, and terms said as terms, still lift.
    assert "+14 leverage: a marquee name in travel" in why["travel_employer"]
    assert "+10 leverage: consulting delivery" in why["consultancy"]
    assert "+8 leverage: signals of good work-life balance" in why["flexible_hours"]
    # A penalty for heavy travel reads the travel requirement.
    assert "-12 leverage: signals of long or unpredictable hours" in why["heavy_travel"]


def test_an_entry_that_names_the_employer_reads_what_the_employer_is(tmp_path):
    why, _ = _scored(tmp_path)
    assert "+14 leverage: a marquee name to a media employer" in why["media_employer"]
    # Content and an audience in a bank's duties are the work, not a media employer.
    assert "media employer" not in why["content_duties"], why["content_duties"]
    # A scope and the culture line set aside, in either order.
    assert "experiments are the work" not in why["culture_line"], why["culture_line"]
    assert "+12 leverage: experiments are the work" in why["experiments"], why["experiments"]


def test_the_diagnostic_says_what_each_entry_fired_on_and_where_it_read(tmp_path):
    _, words = _scored(tmp_path)
    run = words()
    assert run.returncode == 0, run.stderr
    n = len(POSTINGS)
    assert f"+14 (work) 1 of {n}: a marquee name in travel [travel 1]" in run.stdout, run.stdout
    assert f"+8 (terms) 1 of {n}: signals of good work-life balance" in run.stdout, run.stdout
    assert f"-12 (any) 1 of {n}: signals of long or unpredictable hours" in run.stdout
    assert f"+14 (employer) 1 of {n}: a marquee name to a media employer [" in run.stdout


def test_the_diagnostic_reads_a_kept_search_with_the_text_kept_beside_it(tmp_path):
    """A search's kept list holds no posting text; the text is kept beside it, in bodies/,
    under each link as tools/rescore.py keys it."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from lookup_score import norm
    prof = app_state.profile_copy(str(tmp_path / "profile"))
    with open(os.path.join(prof, "search.py"), "a", encoding="utf-8", newline="\n") as fh:
        fh.write(SETTINGS)
    rounds = tmp_path / "rounds"
    (rounds / "bodies").mkdir(parents=True)
    rows = [{"title": "Data Analyst", "company": EMPLOYERS.get(k, "Larkmoor Bank"),
             "url": f"https://jobs.example/{k}"} for k in POSTINGS]
    (rounds / "r1.json").write_text(json.dumps(rows), encoding="utf-8")
    (rounds / "bodies" / "r1.json").write_text(json.dumps(
        {"scored_with": "x", "bodies": {norm(f"https://jobs.example/{k}"): v
                                         for k, v in POSTINGS.items()}}), encoding="utf-8")
    env = dict(os.environ, LJS_PROFILE=prof, PYTHONUTF8="1")
    run = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "opportunity.py"),
                          str(rounds / "r1.json"), "--leverage-words"],
                         capture_output=True, text=True, encoding="utf-8", env=env, cwd=ROOT)
    assert run.returncode == 0, run.stderr
    assert f"+14 (work) 1 of {len(POSTINGS)}: a marquee name in travel [travel 1]" in run.stdout
