"""A button under a Chat answer opens the exact card, in place, with no reload.

The maintainer, 2026-11-10: an answer said "it's in Contacts" and the person went to find it.
Each answer that changed something now carries buttons the engine made from what the work
wrote (tools/touched.py), each a `page:<place>/<id>` the page understands: tapping one goes
to the screen, scrolls that card into view and marks it, never leaving or reloading the page.
A card since set aside or gone opens its screen with a short note, never an error. Every
person and employer is the sample's, invented.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

CLOCK = "2026-10-25T18:30:00Z"
SEARCH = "search~20261025T1800-ab12"
KINDS = [
    ("contacts", "Updated in Contacts", "page:contacts/larkspur_retail_castellan",
     '#main [data-item="larkspur_retail_castellan"]', "#contacts"),
    ("jobs", "Updated in Jobs", "page:jobs/r12-1,r12-3", '#main [data-item="r12-1"]', "#jobs"),
    ("drafts", "Ready in Jobs", "page:drafts/app-ellerwick-insight",
     '#main [data-item="app-ellerwick-insight"]', "#drafts"),
    ("interviews", "Ready in Coming up", "page:interviews/int-harbourline-risk",
     '#main [data-item="int-harbourline-risk"]', "#interviews"),
    ("you", "Updated in Your profile", "page:you/skills", "#main #pf-skills", "#profile"),
    ("work", "Running in Claude's work", "page:work/" + SEARCH, '[data-work="' + SEARCH + '"]',
     None),
]


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


def _seed(extra=()):
    seed = {"talk/cloud-1": {"to": "cloud", "conv": "1", "title": "Questions",
                             "created_at": "2026-10-25T09:00:00Z", "_v": 1},
            "work/" + SEARCH: {"kind": "search", "title": "Find jobs", "to": "cloud",
                               "status": "running", "stage": 1, "asked_at": "2026-10-25T18:00:00Z",
                               "claimed_at": "2026-10-25T18:01:00Z", "_v": 1}}
    goes = [(k, label, to) for k, label, to, _s, _h in KINDS] + list(extra)
    for i, (kind, label, to) in enumerate(goes):
        seed["talk/cloud-1/messages/q%02d" % i] = {"from": "you", "text": "Do the %s one" % kind,
                                                   "at": "2026-10-25T18:%02d:00Z" % (2 + i * 2), "_v": 1}
        seed["talk/cloud-1/messages/a%02d" % i] = {"from": "cloud", "text": "Done: the %s change." % kind,
                                                   "at": "2026-10-25T18:%02d:30Z" % (2 + i * 2),
                                                   "go": [{"label": label, "to": to}], "_v": 1}
    return seed


PROBE = r"""((sel) => {
  const el = document.querySelector(sel);
  const box = el && (el.closest('.card') || el);
  const r = box ? box.getBoundingClientRect() : null;
  return {marker: window.__ljsMarker || null, found: !!el,
          inView: !!r && r.bottom > 0 && r.top < window.innerHeight && r.height > 0,
          marked: !!box && (box.classList.contains('flash') || !!box.closest('.flash')),
          toasts: [...document.querySelectorAll('#toasts')].map((t) => t.textContent).join(' ')};
})(%s)"""


def _steps(kind, sel):
    return [{"hash": "chat", "wait": 200,
             "eval": "(window.__ljsMarker = 'kept', [...document.querySelectorAll('#main .page-go button')].map((b) => b.textContent))"},
            {"open": "go:talk:a%02d:0" % [k for k, *_ in KINDS].index(kind), "wait": 300,
             "eval": PROBE % repr(sel)}]


@pytest.mark.parametrize("kind", [k for k, *_ in KINDS])
def test_each_button_opens_its_card_in_view_without_a_reload(run, tmp_path, vp, kind):
    _k, label, _to, sel, hash_ = next(x for x in KINDS if x[0] == kind)
    got = _go(run, tmp_path, _steps(kind, sel), vp, seed=_seed(), clock=CLOCK)
    labels = got["after"][0]["eval"]
    assert labels == [x[1] for x in KINDS], labels
    seen = got["after"][1]["eval"]
    # The same page: the marker set before the tap is still there.
    assert seen["marker"] == "kept", seen
    assert seen["found"] and seen["inView"], (kind, seen, got["after"][1]["hash"])
    if hash_:
        assert got["after"][1]["hash"].startswith(hash_), got["after"][1]["hash"]
    assert "no longer" not in seen["toasts"] and "set aside" not in seen["toasts"], seen
    if kind in ("contacts", "jobs", "drafts", "interviews", "you"):
        assert seen["marked"], seen


def test_a_contacts_button_opens_their_card_with_the_message_to_them_unfolded(run, tmp_path):
    look = r"""(() => { const c = document.querySelector('#main [data-item="larkspur_retail_castellan"]');
      const d = c && c.querySelector('details.pdraft'); return {card: !!c, open: d ? d.open : null}; })()"""
    got = _go(run, tmp_path, _steps("contacts", "#main") + [{"eval": look}], WIDE,
              seed=_seed(), clock=CLOCK)
    r = got["after"][2]["eval"]
    assert r["card"] and r["open"] in (True, None), r


def test_a_link_to_a_set_aside_job_or_a_gone_card_says_so_and_never_fails(run, tmp_path, vp):
    extra = [("aside", "Updated in Jobs", "page:jobs/r12-6"),
             ("gone", "Updated in Contacts", "page:contacts/nobody_by_that_id")]
    n = len(KINDS)
    toasts = "[...document.querySelectorAll('#toasts')].map((t) => t.textContent).join(' ')"
    got = _go(run, tmp_path, [
        {"hash": "chat", "wait": 200, "eval": "(window.__ljsMarker = 'kept', 1)"},
        {"open": "go:talk:a%02d:0" % n, "wait": 300, "eval": "[window.__ljsMarker, " + toasts + "]"},
        {"hash": "chat", "wait": 200},
        {"open": "go:talk:a%02d:0" % (n + 1), "wait": 300, "eval": "[window.__ljsMarker, " + toasts + "]"},
    ], vp, seed=_seed(extra), clock=CLOCK)
    marker, said = got["after"][1]["eval"]
    assert marker == "kept" and "This was set aside." in said, said
    assert got["after"][1]["hash"].startswith("#jobs"), got["after"][1]["hash"]
    marker, said = got["after"][3]["eval"]
    assert marker == "kept" and "This is no longer on your page." in said, said
    assert got["after"][3]["hash"].startswith("#contacts"), got["after"][3]["hash"]


def test_a_place_written_in_an_answers_words_is_a_link_never_an_address(run, tmp_path):
    seed = _seed()
    seed["talk/cloud-1/messages/z1"] = {"from": "cloud", "at": "2026-10-25T18:29:00Z", "_v": 1,
                                        "text": "Juno's reply is on page:contacts/larkspur_retail_castellan now."}
    got = _go(run, tmp_path, [{"hash": "chat", "wait": 200,
                               "eval": "[...document.querySelectorAll('#main .talk-text')].map((p) => p.textContent).pop()"}],
              WIDE, seed=seed, clock=CLOCK)
    text = got["after"][0]["eval"]
    assert "page:" not in text and "Juno" in text, text
