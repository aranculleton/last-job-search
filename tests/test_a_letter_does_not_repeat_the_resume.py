"""A letter bullet that repeats a resume bullet is flagged.

06-cover-letter-templates.md cuts "any bullet duplicating the resume" first,
and nothing looked: the letter's three bullets are written by the drafter from
the same profile the allocator draws the resume from, so a letter could carry a
resume line word for word beside the resume itself. verify_batch.sh already
caught six words in a row shared by two resume bullets; that check is now one
Python function, and the letter audit runs it against the bullets the allocator
chose for the same draft.
"""
from __future__ import annotations

import os
import re
import sys
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import audit_letters as AU  # noqa: E402

JOBS = [{"employer": "Brindle & Hart Logistics", "bullets": ["BH_FORECAST", "BH_ROUTING"]}]


def _letter(text):
    return {"company": "Wrenfield Freight Ltd", "role": "Supply Chain Analyst", "jobs": JOBS,
            "p1": "Chilled volumes swing by the week. At Brindle & Hart I forecast them by depot.",
            "p2": "Wrenfield moves goods across the North West.", "lead": "Where I would start:",
            "cl_bullets": [{"label": "Forecasting", "text": text}], "p4": "I am in Manchester."}


def test_a_bullet_copied_from_the_resume_is_flagged():
    copied = "Weekly forecasts that cut forecast error from 22% to 14% across 2,400 SKUs."
    [(label, run)] = AU.resume_repeats(_letter(copied))
    assert label == "Forecasting" and run == "forecast error from 22% to 14%"
    with mock.patch.object(AU, "pdf_text", lambda abbr: "Dear Wrenfield Freight hiring team,\n"):
        flags, _ = AU.audit(_letter(copied))
    assert any("repeats the resume" in f for f in flags)


def test_the_same_evidence_in_other_words_is_not():
    own = "Depot-level forecasts that the planners load trailers from, with error down by a third."
    assert AU.resume_repeats(_letter(own)) == []


def test_the_shared_phrase_check_counts_as_verify_batch_did():
    bullets = ["built weekly demand forecasts across six depots for the planners",
               "rebuilt weekly demand forecasts across six depots in dbt",
               "owned the service reporting"]
    assert set(AU.shared_runs(bullets)) == {"weekly demand forecasts across six depots"}
    with open(os.path.join(ROOT, "tools", "verify_batch.sh"), encoding="utf-8") as fh:
        assert re.search(r"from audit_letters import [^\n]*\bshared_runs\b", fh.read())


def test_a_figure_is_one_word():
    """Five words and a figure split at its comma are not six words of prose."""
    assert AU.resume_repeats(_letter("Forecasts for depots across 2,400 SKUs and 6 centres.")) == []
