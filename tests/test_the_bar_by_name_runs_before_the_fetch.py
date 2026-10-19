"""An employer the bar excludes by name alone is dropped before hydrate fetches it.

The bar's name-only rules (an excluded sector, an employer declined by name, a
public agency named outright) were applied by the throttle, after hydrate had
fetched every such posting's body: one HTTP call per posting per round for a
verdict the employer's name already gave. They now run with the prefilter's
other live holds. A public body that clears the bar on a well-paid posting
needs the posting, so that rule stays at the throttle.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import bar  # noqa: E402
import prefilter  # noqa: E402


def _check(tmp_path):
    seen = tmp_path / "seen.json"
    seen.write_text('{"seen": {}}')
    return prefilter.already_ruled_out(str(seen))


def _job(company):
    return {"url": "https://careers.example.com/jobs/1", "title": "Data Analyst",
            "company": company, "location": "Manchester, England, United Kingdom"}


def test_an_excluded_sector_is_dropped_before_the_fetch(tmp_path):
    why = _check(tmp_path)(_job("Larkspur Casino Group"))
    assert why.startswith("candidate's bar: ") and "gambling" in why
    assert _check(tmp_path)(_job("Fernhill Freight")) == ""


def test_a_declined_or_named_public_employer_too_but_never_one_that_needs_the_posting(
        tmp_path, monkeypatch):
    monkeypatch.setattr(bar, "DECLINED", {"brindlehart": "declined by the candidate"})
    monkeypatch.setattr(bar, "NAMED_PUBLIC", re.compile(r"\bnorthgate council\b", re.I))
    monkeypatch.setattr(bar, "_NAMED_WHY", "a named public agency")
    monkeypatch.setattr(bar, "PUBLIC", re.compile(r"\bcouncil\b", re.I))
    monkeypatch.setattr(bar, "_PUBLIC_WHY", "public sector unless well paid")
    monkeypatch.setattr(bar, "company_key",
                        lambda n: "brindlehart" if "Brindle" in str(n) else str(n).lower())
    check = _check(tmp_path)
    assert check(_job("Brindle Hart")) == "candidate's bar: declined by the candidate"
    assert check(_job("Northgate Council")) == "candidate's bar: a named public agency"
    assert check(_job("Wexmoor Council")) == ""            # decided on the posting, later
    assert bar.verdict("Wexmoor Council")[0] == bar.EXCLUDED
