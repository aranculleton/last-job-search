"""A Workday title search reads every page its titles keep matching, not two.

Workday reports a search's total on its first page only, and 0 on every later
page. The search read the total afresh from each page, so every term stopped after
its second page: 40 postings at most from a board holding thousands, on every round.

A board this large is searched, not paged (PAGE_ALL_MAX), so the round's own path
is what is tested: the first page says how big the board is, and each title term is
then paged while its titles keep matching.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ats_boards  # noqa: E402
from openroles.providers import workday as wd  # noqa: E402


def _board(total=2000, last=None):
    """Postings that all match the term, the total on the first page only."""
    def answer(url, payload):
        offset, term = payload["offset"], payload["searchText"]
        if last is not None and offset > last:
            return {"total": 0, "jobPostings": []}, None
        posts = [{"title": f"Pricing Analyst {offset + i}", "locationsText": "Nowhere",
                  "externalPath": f"/job/Nowhere/Pricing-Analyst_R{offset + i}{term[:1]}"}
                 for i in range(wd.PAGE)]
        return {"total": total if offset == 0 else 0, "jobPostings": posts, "facets": []}, None
    return answer


def _searched(web):
    return [p["offset"] for _, p in web.calls if p and p.get("searchText")]


def test_a_term_is_paged_while_its_titles_keep_matching(boards_web):
    boards_web.routes["/wday/cxs/acme/External/jobs"] = _board()
    ats_boards.workday("Acme", "acme.wd3/External", queries=["Pricing Analyst"])
    assert _searched(boards_web) == [n * wd.PAGE for n in range(wd.SEARCH_PAGES)]


def test_it_stops_at_the_first_empty_page_and_at_the_total(boards_web):
    boards_web.routes["/wday/cxs/acme/External/jobs"] = _board(last=wd.PAGE * 2)
    ats_boards.workday("Acme", "acme.wd3/External", queries=["Pricing Analyst"])
    assert _searched(boards_web) == [0, 20, 40, 60]


def test_a_board_under_the_threshold_is_paged_not_searched(boards_web):
    boards_web.routes["/wday/cxs/acme/External/jobs"] = _board(total=30)
    ats_boards.workday("Acme", "acme.wd3/External", queries=["Pricing Analyst"])
    assert _searched(boards_web) == []
