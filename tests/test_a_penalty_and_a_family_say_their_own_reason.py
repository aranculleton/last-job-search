"""A penalty a profile states counts on a strong posting, and says its own reason.

The opportunity score summed every brand-leverage entry and then capped the sum at 30. A
person who stated a penalty there (a negative entry, "long or unpredictable hours") got
nothing for it on a strong posting: four entries worth 50 less 12 is 38, still capped to 30,
so the penalty bit only on postings that were already weak, and changed no ranking. The two
uncapped lists a profile could use instead, the job families, took no reason, and printed
every hit as "<points> job family looks wrong": a penalty for a stated preference said
something untrue, and a lift for a family the person wants said "+10 job family looks wrong".

The cap now holds the lifts alone, a penalty counts in full, and a family entry may carry its
own reason as a third element, as a leverage entry does. Run through the real path: a
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

# A test's own scoring words (tests/test_a_penalty_and_a_family_say_their_own_reason.py).
OPP_LEVERAGE = [
    (re.compile(r"\\bfreight\\b", re.I), 14, "freight is the sector of the person's own work"),
    (re.compile(r"\\bforecast", re.I), 14, "forecasting is the work"),
    (re.compile(r"\\bpricing\\b", re.I), 12, "pricing is the work"),
    (re.compile(r"\\bstakeholders?\\b", re.I), 10, "the person presents to the people who act"),
    (re.compile(r"\\b(long hours|on[- ]call)\\b", re.I), -12,
     "long or unpredictable hours, which cost the person evenings"),
]
'''
FAMILIES = '''
OPP_TITLE_FAMILY = [
    (re.compile(r"\\bpricing analyst\\b", re.I), 10, "a pricing title, the family the person ranks up"),
]
OPP_WRONG_FAMILY = [
    (re.compile(r"\\blive coding test\\b", re.I), -8, "the hiring process names a live coding test"),
    (re.compile(r"\\baudit\\b", re.I), -18),
]
'''

BODY = ("Northwind Analytics prices freight for carriers across the North West. You will "
        "build pricing and demand forecasts in SQL and Python and present them to the "
        "stakeholders who set the rates each week. {extra}Salary: £50,000 - £58,000 per year. "
        "Hybrid, three days a week in our Manchester office. This is a permanent role in a "
        "team of six analysts who share the work and the weekly review with operations. You "
        "will also look after the rate cards and the reports that go out to customers.")


def _posting(n, title, extra=""):
    return {"title": title, "company": "Northwind Analytics", "url": f"https://jobs.example/{n}",
            "location": "Manchester, England, United Kingdom", "date": "2026-10-01",
            "desc": BODY.format(extra=extra)}


def _scored(tmp_path, postings, settings=SETTINGS):
    prof = app_state.profile_copy(str(tmp_path / "profile"))
    with open(os.path.join(prof, "search.py"), "a", encoding="utf-8", newline="\n") as fh:
        fh.write(settings)
    src, out = tmp_path / "in.json", tmp_path / "out.json"
    src.write_text(json.dumps(postings), encoding="utf-8")
    env = dict(os.environ, LJS_PROFILE=prof, PYTHONUTF8="1")
    run = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "opportunity.py"), str(src),
                          "--out", str(out), "--today", "2026-10-14", "--explain"],
                         capture_output=True, text=True, encoding="utf-8", env=env, cwd=ROOT)
    assert run.returncode == 0, run.stderr
    return {r["url"].rsplit("/", 1)[1]: r for r in json.loads(out.read_text(encoding="utf-8"))}


def test_a_penalty_stated_as_leverage_counts_on_a_strong_posting(tmp_path):
    got = _scored(tmp_path, [_posting(1, "Freight Analyst"),
                             _posting(2, "Freight Analyst", "The role is on call one weekend "
                                      "in four, with long hours at quarter end. ")])
    steady, long_hours = got["1"], got["2"]
    # Four lifts worth 50 count 25 on both (each after the strongest at half the one before,
    # issue 327), and would reach the cap of 30 without that; the penalty is swallowed by
    # neither.
    assert steady["opportunity"] - long_hours["opportunity"] == 12, (steady["why"],
                                                                     long_hours["why"])
    assert "-12 leverage: long or unpredictable hours, which cost the person evenings" \
        in long_hours["why"], long_hours["why"]
    assert not any(w.startswith("+-") for w in long_hours["why"]), long_hours["why"]


def test_a_family_entry_says_its_own_reason_and_one_without_keeps_the_old_words(tmp_path):
    got = _scored(tmp_path, [_posting(3, "Pricing Analyst"),
                             _posting(4, "Freight Analyst", "Every hire sits a live coding test. "),
                             _posting(5, "Freight Analyst", "You will support the audit team. ")],
                  SETTINGS + FAMILIES)
    assert "+10 a pricing title, the family the person ranks up" in got["3"]["why"], got["3"]["why"]
    assert not any("looks wrong" in w for w in got["3"]["why"]), got["3"]["why"]
    assert "-8 the hiring process names a live coding test" in got["4"]["why"], got["4"]["why"]
    assert "-18 job family looks wrong" in got["5"]["why"], got["5"]["why"]
