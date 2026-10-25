"""A chat on a new computer finds the person's copy of the app by what GitHub recorded:
the template it was made from (tools/find_copy.py), not a name they have to remember.
The repositories here are invented."""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import find_copy  # noqa: E402


def _page(*repos, more=False):
    return {"data": {"viewer": {"repositories": {
        "pageInfo": {"hasNextPage": more, "endCursor": "c1" if more else None},
        "nodes": [{"nameWithOwner": n, "isPrivate": True,
                   "templateRepository": {"nameWithOwner": t} if t else None}
                  for n, t in repos]}}}}


def test_only_copies_of_the_app_are_named_newest_first_across_pages():
    # The app's own name in another case is still the app (GitHub names are not
    # case-sensitive); it is built from find_copy.APP rather than written out.
    pages = [_page(("morgan-ellis/my-job-search", find_copy.APP),
                   ("morgan-ellis/dotfiles", None), more=True),
             _page(("morgan-ellis/old-search", find_copy.APP.upper()),
                   ("morgan-ellis/notes", "someone/else"))]
    assert find_copy.copies(pages) == ["morgan-ellis/my-job-search", "morgan-ellis/old-search"]
    assert find_copy.copies([_page(("morgan-ellis/dotfiles", None))]) == []


def test_it_asks_github_page_by_page_through_gh(tmp_path, monkeypatch, capsys):
    calls = []

    class P:
        def __init__(self, out):
            self.returncode, self.stdout, self.stderr = 0, json.dumps(out), ""

    def run(cmd, **k):
        calls.append(cmd)
        return P(_page(("morgan-ellis/my-job-search", "aranculleton/last-job-search"),
                       more=len(calls) == 1))
    monkeypatch.setattr(find_copy.subprocess, "run", run)
    gh = tmp_path / "gh"
    gh.write_text("")
    assert find_copy.main(["--gh", str(gh)]) == 0
    assert capsys.readouterr().out.splitlines() == ["morgan-ellis/my-job-search"] * 2
    assert calls[0][1:3] == ["api", "graphql"] and calls[1][-1] == "after=c1"
