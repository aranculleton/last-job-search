"""A probe, never merged: where the focus goes in Safari's engine for a Coming up row's More."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00.000Z"
EVENT = "up-ev20261020120000"
SCREEN = "up-app-larkspur-supply-phone-screen-2026-10-28"

STATE = r"""(() => { const a = document.activeElement;
  const r = a && a.getBoundingClientRect ? a.getBoundingClientRect() : null;
  const dets = [...document.querySelectorAll('details[open]')].map((d) => d.getAttribute('data-k'));
  const dlg = [...document.querySelectorAll('dialog[open]')].map((d) => d.className);
  const sum = document.querySelector('summary[data-k="up-more:%s"]');
  const sr = sum ? sum.getBoundingClientRect() : null;
  const at = sr ? document.elementFromPoint(sr.x + sr.width / 2, sr.y + sr.height / 2) : null;
  const panel = sum && sum.parentElement.querySelector('.menu-panel');
  const items = panel ? [...panel.querySelectorAll('button')].map((b) => ({k: b.getAttribute('data-k'), vis: b.checkVisibility ? b.checkVisibility() : null, r: (() => { const q = b.getBoundingClientRect(); return [Math.round(q.x), Math.round(q.y), Math.round(q.width), Math.round(q.height)]; })()})) : null;
  return {active: a ? (a.getAttribute('data-k') || a.id || a.tagName) : null, activeTag: a && a.tagName, activeRect: r ? [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)] : null,
    openDetails: dets, openDialogs: dlg, sumRect: sr ? [Math.round(sr.x), Math.round(sr.y), Math.round(sr.width), Math.round(sr.height)] : null,
    atSum: at ? (at.getAttribute('data-k') || at.className || at.tagName) : null, items, sy: window.scrollY, ih: window.innerHeight}; })()"""


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.mark.parametrize("vp", [WIDE], ids=["wide"])
def test_probe(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "interviews", "eval": STATE % EVENT},
        {"open": "up-more:" + EVENT, "eval": STATE % EVENT},
        {"press": "Tab", "eval": STATE % EVENT},
        {"press": "Enter", "wait": 800, "eval": STATE % EVENT},
        {"press": "Escape", "wait": 800, "eval": STATE % EVENT},
        {"open": "up-more:" + SCREEN, "eval": STATE % SCREEN},
        {"press": "Tab", "eval": STATE % SCREEN},
        {"press": "Tab", "eval": STATE % SCREEN},
        {"press": "Enter", "wait": 800, "eval": STATE % SCREEN},
    ], vp, clock=T)
    import json
    keep = ("active", "openDetails", "openDialogs", "atSum", "sy", "sumRect")
    trace = [{k: (a.get("eval") or {}).get(k) for k in keep} for a in got["after"]]
    raise AssertionError("PROBE " + json.dumps(trace, separators=(",", ":")))
