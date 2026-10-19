"""A Workday title search reads every page its titles keep matching, not two.

Workday reports a search's total on its first page only, and 0 on every later
page. The search read the total afresh from each page, so every term stopped after
its second page: 40 postings at most from a board holding thousands, on every round.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ats_boards  # noqa: E402


class _Board:
    """Pages of postings that all match the term, the total on the first page only."""

    def __init__(self, total=2000, last=None):
        self.total, self.last, self.offsets = total, last, []

    def page(self, facets, search, offset):
        self.offsets.append(offset)
        if self.last is not None and offset > self.last:
            return {"total": 0, "jobPostings": []}, None
        posts = [{"title": f"Pricing Analyst {offset + i}"} for i in range(ats_boards.PAGE)]
        return {"total": self.total if offset == 0 else 0, "jobPostings": posts}, None


def test_a_term_is_paged_while_its_titles_keep_matching():
    board = _Board()
    listing, errors = ats_boards._wd_search(board, {}, queries=["Pricing Analyst"])
    assert errors == []
    assert len(board.offsets) == ats_boards.SEARCH_PAGES
    assert len(listing) == ats_boards.SEARCH_PAGES * ats_boards.PAGE


def test_it_stops_at_the_first_empty_page_and_at_the_total():
    board = _Board(last=ats_boards.PAGE * 2)
    listing, _ = ats_boards._wd_search(board, {}, queries=["Pricing Analyst"])
    assert board.offsets == [0, 20, 40, 60] and len(listing) == 60
    small = _Board(total=30)
    ats_boards._wd_search(small, {}, queries=["Pricing Analyst"])
    assert small.offsets == [0, 20]
