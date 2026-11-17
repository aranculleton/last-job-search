"""A time said in the device's own zone names its day where that is not the day it is filed under.

On a device in another zone every time says both, "13:00 London time (3:00 here)" (the
maintainer, 2026-11-11), and the time here never said its day: a booking at 13:00 London time
on Wed 28 Oct is 3:00 on Thu 29 Oct in Kiritimati, and under "Wed 28 Oct" its "(3:00 here)" read
as Wednesday there (issue 334, found by the everywhere check's ahead variant). Where the device's
day differs, the time here names it, "(Thu 3:00 here)"; on the same day it is as it was. Coming
up's rows, the Brief's Coming up panel and an interview's card all say it, and on a phone and a
computer the time here keeps whole, on one line, inside the time's own column.

The device's zone is set by each test, both ways from London (the sample's person's zone): 14
hours ahead, where every booking falls on the next day there, 11 behind, where a morning one
falls on the day before, and 10 behind, where every one is on the same day. Every person and
employer is the sample's, invented.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go, _sample  # noqa: E402

T = "2026-10-25T09:00:00Z"
SAMPLE = _sample()
PERSON_ZONE = SAMPLE["person"]["time_zone"]
TIMED = [u for u in SAMPLE["upcoming"] if u.get("start")]
LARKSPUR = next(u for u in TIMED if u["id"].startswith("up-app-larkspur"))


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _when(start, device):
    return dt.datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(ZoneInfo(device))


def _day_there(u, device):
    """The device's weekday where its day is not the row's own, else None."""
    t = _when(u["start"], device)
    return None if t.date().isoformat() == u["day"] else t.strftime("%a")


def _said(day, device, start):
    """What the time here should say: its day where named, then the device's clock."""
    t = _when(start, device)
    return "(" + (day + " " if day else "") + str(t.hour) + ":" + t.strftime("%M") + " here)"


def _norm(s):
    # The clock's hour is said as the device's English says it ("3:00" or "03:00").
    return re.sub(r"\b0(\d:\d\d)", r"\1", " ".join(s.split()))


ZONES = ["Pacific/Kiritimati", "Pacific/Pago_Pago", "Pacific/Honolulu"]

# Each Coming up row: its day's heading, its time column and the time here, and whether the time
# here keeps one line inside the column with no word of the column broken in two.
ROWS = r"""(() => [...document.querySelectorAll('#main [data-k="up-days"] > .up-day')].flatMap((d) =>
  [...d.querySelectorAll('.up-row')].map((r) => {
    const w = r.querySelector(':scope > .up-when'), here = w.querySelector('.up-here');
    const wr = w.getBoundingClientRect(), hr = here ? here.getBoundingClientRect() : null;
    const broken = [];
    for (const n of [...w.childNodes].filter((x) => x.nodeType === 3)) {
      const s = n.textContent; let top = null;
      for (let i = 0; i < s.length; i++) {
        const g = document.createRange(); g.setStart(n, i); g.setEnd(n, i + 1);
        const q = [...g.getClientRects()].find((x) => x.width > 0);
        if (!q) continue;
        if (top !== null && Math.abs(q.top - top) > 2 && s[i - 1] !== ' ' && s[i] !== ' ') broken.push(s.slice(Math.max(0, i - 6), i + 6));
        top = q.top;
      }
    }
    return {id: r.dataset.item, head: d.querySelector('h3').textContent.trim(), here: here ? here.textContent.trim() : null,
      lines: here ? (() => { const g = document.createRange(); g.selectNodeContents(here);
        return new Set([...g.getClientRects()].filter((x) => x.width > 0).map((x) => Math.round(x.bottom))).size; })() : 0, cut: here ? [Math.round(hr.left - wr.left), Math.round(wr.right - hr.right)] : null,
      spill: w.scrollWidth - w.clientWidth, broken};
  })))()"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
@pytest.mark.parametrize("device", ZONES)
def test_coming_up_names_the_day_of_the_time_here_where_it_is_another_day(run, tmp_path, device, vp):
    got = _go(run, tmp_path, [{"hash": "interviews", "ready": "document.querySelectorAll('#main .up-row .up-here').length > 0", "eval": ROWS}],
              vp, clock=T, zone=device)
    rows = {r["id"]: r for r in got["after"][0]["eval"]}
    seen = 0
    for u in TIMED:
        r = rows.get(u["id"])
        if not r:
            continue
        seen += 1
        day = _day_there(u, device)
        assert r["here"] is not None and _norm(r["here"]) == _said(day, device, u["start"]), (device, u["id"], u["day"], r)
        # Filed under the person's own day, as it was.
        on = dt.date.fromisoformat(u["day"])
        assert r["head"] == "%s %d %s" % (on.strftime("%a"), on.day, on.strftime("%b")), r
        # The time here whole on one line inside the time's own column, and no word of the column
        # broken in two to make room for it.
        assert r["lines"] == 1 and min(r["cut"]) >= -1 and r["spill"] <= 0 and not r["broken"], (device, vp, r)
    assert seen >= 3, rows


@pytest.mark.parametrize("device", ZONES)
def test_the_briefs_coming_up_and_an_interviews_card_name_it_too(run, tmp_path, device):
    day = _day_there(LARKSPUR, device)
    said = _said(day, device, LARKSPUR["start"])
    got = _go(run, tmp_path, [
        {"hash": "brief", "ready": "!!document.querySelector('#main .bp-up-row .up-when')",
         "eval": "[...document.querySelectorAll('#main .bp-up-row .up-when')].map((w) => w.textContent.trim())"},
        {"hash": "interviews/int-larkspur-supply", "read": "#main article[data-item=\"int-larkspur-supply\"]"},
    ], PHONE, clock=T, zone=device)
    brief = [_norm(w) for w in got["after"][0]["eval"]]
    assert "Wed 28 Oct · 13:00 London time " + said in brief, (device, brief)
    card = _norm(got["after"][1]["text"])
    assert "Wed 28 Oct, 13:00 London time " + said in card, (device, card)


def test_on_the_persons_own_zone_a_time_is_said_once_with_no_day_beside_it(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "interviews", "ready": "document.querySelectorAll('#main .up-row').length > 0", "eval": ROWS}],
              WIDE, clock=T, zone=PERSON_ZONE)
    rows = got["after"][0]["eval"]
    assert rows and all(r["here"] is None for r in rows), rows
