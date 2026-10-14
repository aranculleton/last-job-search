"""The example person runs through scoring, so a profile shaped like it does too.

/setup writes a person's profile in the shape of profile.example/. A shape the
tools cannot read in the example becomes a crash in every new person's first
round: FIT_MISSING once held (pattern, label) pairs while tools/fit.py unpacks
(pattern, points, label), and nothing in the suite ever scored a posting against
the example, so it went unnoticed until an end-to-end setup hit it.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import fit  # noqa: E402

POSTING = {
    "title": "Senior Supply Chain Analyst",
    "company": "Fernhill Freight",
    "location": "Manchester, England, United Kingdom",
    "desc": (
        "You will own demand forecasting and inventory analytics for our network. "
        "Strong SQL and Python are required, with Power BI for reporting. "
        "Spark experience is essential for our data platform."),
}


def test_a_posting_scores_against_the_example_without_error():
    out = fit.fit(POSTING)
    assert isinstance(out, dict) and out
    text = repr(out)
    assert "big-data engineering" in text, "a stated must-have the profile lacks is weighed"


def test_the_example_roles_are_read_by_profile_facts():
    """Role headings are "### Title - Employer (dates)"; prep docs read them."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
    import profile_facts
    facts = profile_facts.build()
    assert [e["company"] for e in facts.get("employers", [])] == [
        "Brindle & Hart Logistics", "Oakmere Foods", "Saltmarsh Analytics"]
