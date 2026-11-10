"""A name searched for in Contacts is found whatever the filters, employer or none.

The maintainer, 2026-11-10: "A contact with no employer doesn't come up in a name search the
way the others do ... which makes it look as though he's missing." He was on the page, waiting
on a reply ("Replied: your turn"), and a filter left on hid him from the search for his first
name, with nothing saying so. A name search now always finds everyone whose name matches:
those a filter hides are said under the list ("1 more hidden by your filter"), with a tap that
shows them. A contact with no employer is labelled by their name alone, never "Name at ".
Every person and employer here is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import WIDE, _go  # noqa: E402

LONE = "contact_quillby_no_firm"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _model():
    m = journeys._sample()
    juno = next(p for p in m["people"] if p["id"] == "larkspur_retail_castellan")
    lone = {k: v for k, v in juno.items() if k not in ("related", "owed")}
    # Someone with no employer on record, waiting on a reply from the person.
    lone.update(id=LONE, first_name="Odalys", employer="", title=None, rev="p-lone",
                thread=[{"from": "them", "on": "2026-10-21", "text": "Hi Morgan, good to hear from you."}],
                owed={"label": "Draft a reply", "kind": "reply", "id": "reply~" + LONE,
                      "args": {"contact": LONE}, "logged": True, "reply": True})
    m["people"].append(lone)
    return m


CLICK = "(() => { const b = document.querySelector('[data-k=\"%s\"]'); if (b) b.click(); return !!b; })()"
SEARCH = r"""(() => { const i = document.querySelector('#main input[data-k="q:contacts"]');
  i.value = %r; i.dispatchEvent(new Event('input', {bubbles: true})); return !!i; })()"""
SHOWN = r"""(() => ({ids: [...document.querySelectorAll('#main ul.people > [data-item]')].map((e) => e.getAttribute('data-item')),
  line: (document.querySelector('#main [data-hidden-by-filter]') || {textContent: ''}).textContent,
  names: [...document.querySelectorAll('#main ul.people h3')].map((e) => e.textContent)}))()"""


def test_a_name_hidden_by_a_filter_is_said_and_one_tap_shows_them(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "contacts", "eval": SEARCH % "odalys"},
        {"tick": 400},
        {"eval": SHOWN},
        # A filter that leaves her out: people waiting on them.
        {"eval": CLICK % "filter:contacts"},
        {"tick": 200},
        {"eval": CLICK % "fchip:contacts:status:waiting"},
        {"tick": 200},
        {"eval": CLICK % "filter-done"},
        {"tick": 400},
        {"eval": SHOWN},
        {"eval": CLICK % "byfilter:contacts"},
        {"tick": 400},
        {"eval": SHOWN},
    ], WIDE, model=_model())
    ev = [x.get("eval") for x in got["after"]]
    alone, filtered, tapped = ev[2], ev[9], ev[12]
    # No filter: found by her first name, named by it alone.
    assert alone["ids"] == [LONE], alone
    assert [n.strip() for n in alone["names"]] == ["Odalys"], alone["names"]
    assert not any(n.rstrip().endswith(" at") or "undefined" in n for n in alone["names"])
    # The filter hides her: never a silent empty list, the line says so.
    assert ev[3] is True and ev[5] is True and ev[7] is True, ev
    assert LONE not in filtered["ids"], filtered
    assert filtered["line"].startswith("1 more hidden by your filter:"), filtered
    assert "Show them" in filtered["line"] and "Nothing matches" not in str(filtered)
    # One tap shows her, the filter still on.
    assert ev[10] is True and tapped["ids"] == [LONE] and not tapped["line"], tapped
