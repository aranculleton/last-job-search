"""One strong reason to want a job is not outweighed by many small ones.

The opportunity score added every brand-leverage lift a posting fired in full, up to 30 in all
(issue 293 left the cap on the lifts alone). So a posting that named five things the person
finds a little familiar, six points each, outranked one that was squarely the work they want,
twenty points: 30 against 20, from words that each said very little (issue 327).

Now the lifts count strongest first: the strongest in full, the next at half, the next at a
quarter and so on, rounded to whole points, and together still no more than 30. A penalty
still counts in full. `--explain` says what each lift counted. Run through the real path: a
profile that states them, and tools/opportunity.py as a round runs it. Invented employers.
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

# A test's own scoring words
# (tests/test_one_strong_reason_to_want_a_job_is_not_drowned_by_many_small_ones.py).
OPP_LEVERAGE = [
    (re.compile(r"\\bpricing\\b", re.I), 20, "pricing is the work"),
    (re.compile(r"\\bfreight\\b", re.I), 6, "freight is a sector the person knows"),
    (re.compile(r"\\bwarehouse\\b", re.I), 6, "warehouse data is familiar"),
    (re.compile(r"\\bcarriers?\\b", re.I), 6, "carriers are customers the person has served"),
    (re.compile(r"\\breplenishment\\b", re.I), 6, "replenishment is close to the person's work"),
    (re.compile(r"\\broutes?\\b", re.I), 6, "route data is familiar"),
    (re.compile(r"\\bforecasts?\\b", re.I), 14, "forecasting is the work"),
    (re.compile(r"\\bsurge\\b", re.I), 24, "surge pricing is the person's own field"),
    (re.compile(r"\\b(long hours|on[- ]call)\\b", re.I), -12,
     "long or unpredictable hours, which cost the person evenings"),
]
'''

TAIL = ("The team is six analysts who share the work and the weekly review with operations, "
        "and you will look after the reports that go out to customers. This is a permanent "
        "role, hybrid, three days a week in our Manchester office, and the team meets every "
        "Monday to agree the week's priorities with the people who act on them.")


def _posting(n, work):
    return {"title": "Analyst", "company": "Northwind Analytics",
            "url": f"https://jobs.example/{n}",
            "location": "Manchester, England, United Kingdom", "date": "2026-10-01",
            "desc": f"Northwind Analytics is hiring an analyst. {work} {TAIL}"}


def _scored(tmp_path, postings):
    prof = app_state.profile_copy(str(tmp_path / "profile"))
    with open(os.path.join(prof, "search.py"), "a", encoding="utf-8", newline="\n") as fh:
        fh.write(SETTINGS)
    src, out = tmp_path / "in.json", tmp_path / "out.json"
    src.write_text(json.dumps(postings), encoding="utf-8")
    env = dict(os.environ, LJS_PROFILE=prof, PYTHONUTF8="1")
    run = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "opportunity.py"), str(src),
                          "--out", str(out), "--today", "2026-10-14", "--explain"],
                         capture_output=True, text=True, encoding="utf-8", env=env, cwd=ROOT)
    assert run.returncode == 0, run.stderr
    rows = {r["url"].rsplit("/", 1)[1]: r for r in json.loads(out.read_text(encoding="utf-8"))}
    return rows, run.stdout


def test_one_strong_lift_outranks_many_small_ones(tmp_path):
    rows, said = _scored(tmp_path, [
        _posting(1, "You will own pricing for the business, building the models the commercial "
                    "team acts on each week."),
        _posting(2, "You will analyse freight volumes, warehouse throughput, carrier "
                    "performance, replenishment cycles and route costs each week.")])
    strong, many = rows["1"], rows["2"]
    assert strong["opportunity"] > many["opportunity"], (strong["why"], many["why"])
    assert "+20 leverage: pricing is the work" in strong["why"], strong["why"]
    # Each lift says what it counted, strongest first; ties keep the profile's order.
    lifts = [w for w in many["why"] if " leverage: " in w]
    assert lifts == [
        "+6 leverage: freight is a sector the person knows",
        "+3 leverage: warehouse data is familiar (+6, the 2nd lift, counts half)",
        "+2 leverage: carriers are customers the person has served (+6, the 3rd lift, counts "
        "a quarter)",
        "+1 leverage: replenishment is close to the person's work (+6, the 4th lift, counts an "
        "eighth)",
        "+0 leverage: route data is familiar (+6, the 5th lift, counts a sixteenth)",
    ], many["why"]
    assert ("leverage lifts counted +12 of +30: the strongest in full, the next at half, the "
            "next at a quarter and so on, +30 at most") in many["why"], many["why"]
    # And --explain prints it, under the posting.
    assert "+3 leverage: warehouse data is familiar (+6, the 2nd lift, counts half)" in said
    # One lift alone says what it always said, and adds no line about counting.
    assert not any(w.startswith("leverage lifts counted") for w in strong["why"]), strong["why"]


def test_the_lifts_still_stop_at_30_and_a_penalty_still_counts_in_full(tmp_path):
    work = ("You will set surge pricing for freight and build the forecasts behind it, "
            "presenting them each week.")
    rows, _ = _scored(tmp_path, [_posting(3, work),
                                 _posting(4, work + " The role is on call one weekend in four.")])
    steady, on_call = rows["3"], rows["4"]
    lifts = [w for w in steady["why"] if " leverage: " in w]
    # 24 in full, 20 at half is 10, 14 at a quarter is 4 and 6 at an eighth is 1: 39, held
    # to 30, so the 2nd counts 6 and the rest nothing.
    assert lifts == [
        "+24 leverage: surge pricing is the person's own field",
        "+6 leverage: pricing is the work (+20, the 2nd lift, counts half, the lifts held to "
        "+30)",
        "+0 leverage: forecasting is the work (+14, the 3rd lift, counts a quarter, the lifts "
        "held to +30)",
        "+0 leverage: freight is a sector the person knows (+6, the 4th lift, counts an eighth, "
        "the lifts held to +30)",
    ], steady["why"]
    assert steady["opportunity"] - on_call["opportunity"] == 12, (steady["why"], on_call["why"])
    assert "-12 leverage: long or unpredictable hours, which cost the person evenings" \
        in on_call["why"], on_call["why"]
