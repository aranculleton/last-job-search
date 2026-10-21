"""A second language named only as a nice-to-have, or a nationality word, is not a cut.

The text screen cuts a posting for a language the candidate does not hold only when it
is "named as a requirement and not a nice-to-have". It read "Bilingual in Spanish is a
plus", "Fluency in Mandarin would be an advantage" and "Japanese is preferred but not
required" as requirements ("bilingual", "fluency" and the "requir" inside "not required"),
and "Spanish and Portuguese markets" and "Chinese supplier" as languages. Each cut was
written to seen_jobs.json resting on settings the person never changes, so the throttle
kept it for good. Those rulings are released by the throttle with nobody asking, and a
ruling today's screen makes still holds.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import exclude  # noqa: E402
import prefilter  # noqa: E402
import text_screen  # noqa: E402
import throttle  # noqa: E402
from lookup_score import norm  # noqa: E402

BODY = " You will build demand forecasts in SQL and Python for our planning team." * 8

NICE_TO_HAVE = (
    "Bilingual in Spanish is a plus.",
    "Fluency in Mandarin would be an advantage.",
    "Proficiency in Japanese is preferred but not required.",
    "Experience with Spanish and Portuguese markets is required.",
    "Required: experience analysing Chinese supplier lead times.",
    "Russian language skills would be beneficial.",
    "Japanese (JLPT N2) is a plus.",
    "Spanish (Latin America) market experience required.",
)
REQUIRED = (
    "Fluency in Spanish is required.",
    "Must speak Mandarin.",
    "Spanish is required.",
    "You must be fluent in English and Spanish.",
    "Native Japanese speaker required.",
    "Spanish (written and spoken) is required.",
    "Mandarin-speaking candidates are required.",
    "Fluent German required.",
    "Proficiency in written and spoken Russian is mandatory.",
    # A level written as a test or a grade, in brackets or not, is still a requirement.
    "Japanese (JLPT N2) required.",
    "Japanese (JLPT N2 or above) is required.",
    "Spanish, C1, essential.",
    "Mandarin (HSK 5) is mandatory.",
)


def _cuts(sentence):
    return text_screen.screen({"title": "Planning Analyst", "desc": sentence + BODY})["cuts"]


@pytest.mark.parametrize("sentence", NICE_TO_HAVE)
def test_a_language_asked_as_a_preference_or_a_market_is_not_cut(sentence):
    assert _cuts(sentence) == []


@pytest.mark.parametrize("sentence", REQUIRED)
def test_a_language_stated_as_a_requirement_is_still_cut(sentence):
    cuts = _cuts(sentence)
    assert cuts and "stated as a requirement" in cuts[0]


def test_the_profiles_own_language_is_read_as_before():
    assert _cuts("Fluency in Welsh is essential.")
    assert not _cuts("Welsh would be an advantage.")


# ---------------------------------------------------------------- rulings already saved

URL = "https://careers.example.com/jobs/{}"


def _entry(n, reason, day="2026-10-21"):
    return {"url": URL.format(n), "title": f"Planning Analyst {n}", "company": "Fernwick Foods",
            "location": "Salford, England, United Kingdom", "status": "excluded",
            "exclusion_reason": reason, "excluded_date": day, "first_seen": day}


@pytest.fixture
def seen(tmp_path, monkeypatch):
    """An invented seen_jobs.json holding rulings the earlier screen wrote, stamped the way
    tools/exclude.py stamps a round's cuts. No re-run version is what releases them here."""
    monkeypatch.setenv("LJS_RESCREEN", "off")
    path = str(tmp_path / "seen_jobs.json")
    old = [f'{lang} stated as a requirement: "{s}"' for lang, s in
           zip(("Spanish", "Mandarin", "Japanese", "Spanish", "Chinese"), NICE_TO_HAVE)]
    still = ['Spanish stated as a requirement: "Fluency in Spanish is required."',
             'Welsh stated as a requirement: "Fluency in Welsh is essential."',
             text_screen.ELIGIBILITY_CUT_REASON + ': "Must hold an active SC clearance."; '
             'Spanish stated as a requirement: "Bilingual in Spanish is a plus."']
    exclude.add_many([{"url": URL.format(i), "reason": r, "title": f"Planning Analyst {i}",
                       "company": "Fernwick Foods",
                       "location": "Salford, England, United Kingdom"}
                      for i, r in enumerate(old + still)], today="2026-10-21", path=path)
    return path, len(old)


def test_rulings_the_earlier_screen_made_on_a_preference_stop_blocking(seen):
    path, n_old = seen
    with open(path, encoding="utf-8") as fh:
        entries = json.load(fh)["seen"]
    # Each rests on the language settings, which have not changed: only the re-judge lifts it.
    assert all(isinstance(e.get("rests_on"), dict) for e in entries.values())
    urls, _ = throttle.ruled_out(entries)
    for e in entries.values():
        old = int(e["url"].rsplit("/", 1)[1]) < n_old
        assert (norm(e["url"]) in urls) is not old, e["exclusion_reason"]


def test_the_rounds_own_gate_lets_the_posting_through_and_todays_screen_ranks_it(seen):
    path, _ = seen
    check = prefilter.already_ruled_out(path, today=prefilter._dt.date(2026, 10, 23))
    job = {"url": URL.format(0), "title": "Planning Analyst 0", "company": "Fernwick Foods",
           "location": "Salford, England, United Kingdom"}
    assert check(job) == ""
    assert text_screen.screen({**job, "desc": NICE_TO_HAVE[0] + BODY})["text_screen"] == "pass"
    held = {**job, "url": URL.format(5), "title": "Planning Analyst 5"}
    assert check(held).startswith("excluded in seen_jobs.json")


def test_a_ruling_today_s_screen_makes_is_never_refused():
    """A posting it would cut again is not let through to be fetched every round."""
    for s in REQUIRED:
        cuts = _cuts(s)
        assert not text_screen.ruling_refused("; ".join(cuts)), cuts
    long = ("Our planning team works across many functions, markets and sites, and you will "
            "join it in a role where fluency in Spanish is essential to work with our "
            "suppliers every week of the year, in person and on the phone, and in writing.")
    cuts = _cuts(long)
    assert cuts and '"...' in cuts[0]
    assert not text_screen.ruling_refused("; ".join(cuts))


def test_words_the_screen_did_not_write_are_never_re_judged():
    assert not text_screen.ruling_refused("knockout at triage: Spanish stated as a requirement")
    assert not text_screen.ruling_refused(
        'Spanish stated as a requirement: "Bilingual in Spanish is a plus." Also a sales role.')
