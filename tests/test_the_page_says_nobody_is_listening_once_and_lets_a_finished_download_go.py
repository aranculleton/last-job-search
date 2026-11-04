"""Nobody listening is said once, with the button that works where the page is open, and a
LinkedIn download that is done leaves To do (the maintainer's phone, 2026-11-04).

- "Why is there a top Open Claude link that gives this pop up that opens my phone's
  browser?" With no chat answering the page, the line under the header said "Claude isn't
  listening right now" with Open Claude, and To do's first card said it again with Wake
  Claude. Open Claude starts a chat at claude.ai/code, which leaves the Claude app: on the
  phone, the app asked to open the browser. Nothing in tools/claude_surfaces.json says what a
  phone does with such a link, so on a phone it is never offered.
- "What's the 0 messages in next 7 days thing": a download Claude had already saved sat in
  To do as "Saved: 0 messages · Done. Only a chat can take this back", for a download that
  brought nothing new and had nothing to take back.

Every person and employer is invented (tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go, _sample  # noqa: E402


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


T = "2026-10-25T09:00:00.000Z"

# A search asked for half an hour ago, and the chat that answers the page quiet since before.
WAITING = {"work/search~late": {"kind": "search", "title": "Finding jobs", "to": "cloud", "args": {}, "asked_at": "2026-10-25T08:30:00Z",
                                "status": "queued", "stages": [], "stage": 0, "stage_at": None, "steps": [], "claimed_by": None,
                                "claimed_at": None, "stop_asked": False, "attempt": 1},
           "meta/listener": {"chat": "cloud-1", "title": "Job search helper", "kind": "cloud", "answered_at": "2026-10-25T07:30:00Z", "watching": True}}

# What the header and To do's card say, and every link out to claude.ai/code that can be seen.
SAID = r"""(() => {
  const p = document.getElementById('pulse');
  const shown = (e) => !!e.getClientRects().length && !e.closest('[hidden]');
  const card = document.querySelector('#main [data-item="listen"]');
  return {line: shown(p) ? p.textContent : '', dot: document.getElementById('conn').getAttribute('data-state'),
    dotWords: document.getElementById('conn').textContent,
    card: card ? card.textContent : '',
    buttons: card ? [...card.querySelectorAll('.card-actions .btn')].map((b) => b.textContent.trim()) : [],
    out: [...document.querySelectorAll('#pulse a, #main [data-item="listen"] a')].filter((a) => shown(a) && /claude\.ai\/code/.test(a.href)).map((a) => a.getAttribute('data-k'))};
})()"""

# Every link out to claude.ai/code that can be seen anywhere on the page.
LINKS_OUT = r"""[...document.querySelectorAll('a')].filter((a) => a.getClientRects().length && /claude\.ai\/code/.test(a.href)).map((a) => a.getAttribute('data-k'))"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_nobody_listening_is_said_once_with_wake_claude_its_one_button(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "todo", "eval": SAID}, {"hash": "brief", "eval": SAID}], vp, seed=WAITING, clock=T)
    r = got["after"][0]["eval"]
    assert "Claude isn't listening right now" in r["card"] and r["buttons"] == ["Wake Claude"], r
    assert "listening" not in r["line"], ("said once, on its card: not again in the line under the header", r)
    assert r["out"] == [], ("no link that leaves the Claude app where Wake Claude works", r)
    # The dot in the header still says it, so it never reads "Connected." over the card.
    assert r["dot"] == "unheard" and "Claude isn't listening right now" in r["dotWords"], r
    # On another screen too: the line under the header stays quiet, the badge on To do counts it.
    other = got["after"][1]["eval"]
    assert "listening" not in other["line"] and other["dot"] == "unheard", other


def test_with_nothing_to_hear_it_a_phone_is_never_sent_out_of_the_claude_app(run, tmp_path):
    fake = {"canSend": "no_session"}
    phone = _go(run, tmp_path, [{"hash": "todo", "eval": SAID}, {"eval": LINKS_OUT}, {"hash": "work", "read": '[data-work="search~late"]', "eval": LINKS_OUT}], PHONE,
                seed=WAITING, clock=T, fake=fake)
    r = phone["after"][0]["eval"]
    assert "Claude isn't listening right now" in r["card"] and "Open this page on a computer to start it now." in r["card"], r
    assert r["buttons"] == [] and "Open Claude" not in r["card"], ("no button that cannot work, and no link out", r)
    assert "Finding jobs" in phone["after"][2]["text"], "its card in Claude's work is there"
    assert phone["after"][1]["eval"] == [] and phone["after"][2]["eval"] == [], ("no link to claude.ai/code anywhere on a phone", phone["after"])
    # On a computer, where the link opens in the browser it came from, Open Claude is the one way.
    wide = _go(run, tmp_path, [{"hash": "todo", "eval": SAID}], WIDE, seed=WAITING, clock=T, fake=fake)["after"][0]["eval"]
    assert wide["buttons"] == ["Open Claude (opens Claude in a new tab)"] and wide["out"] == ["wake-open"], wide
    assert "listening" not in wide["line"], wide


# A download Claude saved a minute ago that brought nothing new, as the engine writes its receipt.
TAKE = {"action": "export.take", "item": "2026-10", "value": {"assets": []}, "at": "2026-10-25T08:58:00.000Z", "rev": None}
NOTHING = {"applied_at": "2026-10-25T08:59:00.000Z", "by": "cloud-1", "result": "ok", "nothing_new": True, "remove_assets": [],
           "note": "That download was taken before. Nothing in it was new."}
HEARD = {"chats/cloud-1": {"kind": "cloud", "seen_at": "2026-10-25T08:58:30.000Z", "watching": True},
         "meta/listener": {"chat": "cloud-1", "kind": "cloud", "answered_at": "2026-10-25T08:59:00.000Z"}}
LINE = "(document.querySelector('[data-k=\"det:info:linkedin-download\"] .state') || {}).textContent || ''"


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_a_finished_download_leaves_to_do_and_says_nothing_new_on_its_own_line(run, tmp_path, vp):
    seed = dict(HEARD, **{"actions/a-export": TAKE, "receipts/a-export": NOTHING})
    # The model still says the download is due: it catches up with the next update.
    got = _go(run, tmp_path, [{"hash": "todo", "count": '#main [data-item="linkedin-export"]'},
                              {"hash": "settings", "open": "info-sum:linkedin-download", "eval": LINE}], vp, seed=seed, clock=T)
    assert got["after"][0]["count"] == 0, "a download Claude has saved is finished: it leaves To do"
    assert "Saved: 0 messages" not in got["after"][0]["text"]
    line = got["after"][1]["eval"]
    assert line.startswith("Done. Nothing new in that download."), line
    assert "take this back" not in line, line


def test_the_next_download_is_asked_for_again_once_the_last_ones_line_has_gone(run, tmp_path):
    m = _sample()
    m["linkedin_export"] = dict(m["linkedin_export"], due=True, state="due")
    old = dict(NOTHING, applied_at="2026-10-21T08:59:00.000Z")
    seed = dict(HEARD, **{"actions/a-export": dict(TAKE, at="2026-10-21T08:58:00.000Z"), "receipts/a-export": old})
    got = _go(run, tmp_path, [{"hash": "todo", "read": '#main [data-item="linkedin-export"]'}], WIDE, model=m, seed=seed, clock=T)
    card = got["after"][0]["text"]
    assert card and "Saved:" not in card and "Done." not in card, card
