"""People on hold are one folded group at the foot of Contacts, never among who needs you.

The maintainer, 2026-11-10: "Held notes stay in the main list, and look like work to do ...
They have the full draft open, a 'Send it anyway' link and a 'Talking' badge ... held notes
move to their own collapsed group at the bottom ('On hold: 2, waiting for a role to be
posted'), with the draft folded away." The engine says who is on hold, why and until when
(`on_hold` on each person, `people_count.on_hold` for the group's shared reason:
tests/test_people_on_hold_are_a_group_of_their_own.py); the page draws them last, folded, each
card with its one line and nothing that reads as owed, and Send it anyway inside the folded
draft. Every person and employer is invented.
"""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import app_lists  # noqa: E402
import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

IVO = "quayside_foods_ivo"
LEORIC = "thornbury_bank_leoric"
WREN = "fernhill_freight_halloway"
ROLE = ("On hold until a role is posted at %s: they offered to refer you. Claude writes this "
        "when a role is posted.")
AWAY = "On hold: Wren is away until then. Claude checks again on Mon 23 Nov."


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


def _two_waiting_for_a_role():
    m = journeys._sample()
    ivo = next(p for p in m["people"] if p["id"] == IVO)
    ivo.update(group="held", owed=None, on_hold={"said": ROLE % "Quayside Foods", "role": True,
                                                 "until": None})
    leoric = copy.deepcopy(ivo)
    leoric.update(id=LEORIC, first_name="Leoric", employer="Thornbury Bank", rev="p-leoric",
                  related={}, on_hold={"said": ROLE % "Thornbury Bank", "role": True, "until": None})
    m["people"].append(leoric)
    m["people_count"] = {"on_hold": {"n": 2, "why": "waiting for a role to be posted"}}
    return m


def _one_with_a_draft():
    m = journeys._sample()
    wren = next(p for p in m["people"] if p["id"] == WREN)
    wren.update(group="held", owed=None, on_hold={"said": AWAY, "role": False, "until": "2026-11-23"})
    msg = next(x for x in m["messages"] if x["contact"] == WREN)
    msg.update(hold=AWAY, hold_why="person_hold")
    m["people_count"] = {"on_hold": {"n": 1, "why": None}}
    return m


# Someone in the book the page was published without: only in the whole list, behind "Show".
ORLA = "kestrel_mutual_orla"


def _whole_list(m):
    """The people's whole list as `app.py view` writes it beside the page (`view/list~people~*`,
    tools/app_lists.docs): everyone in the book, those on hold included, each as the engine's
    short record (app_model's `light`), and someone the page itself was published without."""
    def light(p):
        return {"id": p["id"], "first_name": p["first_name"], "employer": p.get("employer") or "",
                "status": p["status"], "status_word": p["status"].replace("_", " "),
                "group": p.get("group"), "route": "linkedin", "last": p.get("last"),
                "contacted": "90", "due": p.get("due"), "replied": False,
                "live": p.get("group") in ("now", "follow", "held")}
    rest = {"id": ORLA, "first_name": "Orla", "employer": "Kestrel Mutual",
            "status": "awaiting_reply", "group": "done", "last": "2026-06-02"}
    whole = [light(p) for p in m["people"]] + [light(rest)]
    return {"view/" + doc_id: doc for doc_id, doc in
            app_lists.docs({"people": whole}, m["made_at"], "r-" + m["made_at"])}


# Where things are drawn, in every engine (the harness's __drawnRect): the page is zoomed on a
# phone, and Safari measures a box before the zoom.
LOOK = r"""(() => {
  const main = [...document.querySelectorAll('#main ul.people:not([data-held-list]) > [data-item]')];
  const fold = document.querySelector('#main [data-on-hold]');
  const held = [...document.querySelectorAll('#main ul[data-held-list] > [data-item]')];
  const last = main[main.length - 1];
  const card = (e) => ({id: e.getAttribute('data-item'),
    state: (e.querySelector('.state-word') || {textContent: ''}).textContent.trim(),
    line: (e.querySelector('p.meta') || {textContent: ''}).textContent.replace(/\s+/g, ' ').trim(),
    buttons: [...e.querySelectorAll('.card-actions > button, .card-actions > a')].map((b) => b.textContent.trim()),
    filled: [...e.querySelectorAll('button.primary')].map((b) => b.textContent.trim()),
    draftOpen: e.querySelector('details.pdraft') ? e.querySelector('details.pdraft').open : null,
    copy: !!e.querySelector('.bubble-copy'), sent: !!e.querySelector('[data-k^="sent:"]'),
    anyway: !!e.querySelector('[data-k^="unhold:"]'),
    fits: e.__drawnRect().right <= window.innerWidth + 1 && e.__drawnRect().left >= -1});
  return {main: main.map((e) => e.getAttribute('data-item')),
    fold: fold ? fold.textContent.replace(/\s+/g, ' ').trim() : null,
    below: fold && last ? fold.__drawnRect().top >= last.__drawnRect().bottom - 1 : null,
    foldFits: fold ? fold.__drawnRect().right <= window.innerWidth + 1 : null,
    held: held.map(card), mainCards: main.map(card),
    summary: (document.querySelector('#main .sec .sum, #main .screen-sum, #main [data-sum]') || {textContent: ''}).textContent};
})()"""
TAP = "(() => { const b = document.querySelector('[data-k=\"%s\"]'); if (b) b.click(); return !!b; })()"
SEARCH = r"""(() => { const i = document.querySelector('#main input[data-k="q:contacts"]');
  i.value = %r; i.dispatchEvent(new Event('input', {bubbles: true})); return !!i; })()"""


def test_two_people_waiting_for_a_role_are_one_folded_group_at_the_foot(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "contacts", "ready": "!!document.querySelector('#main [data-on-hold]')", "eval": LOOK},
        {"open": "held:contacts", "ready": "!!document.querySelector('#main ul[data-held-list]')", "eval": LOOK},
        {"open": "held:contacts", "ready": "!document.querySelector('#main ul[data-held-list]')", "eval": LOOK},
    ], vp, model=_two_waiting_for_a_role())
    folded, open_, again = (got["after"][i]["eval"] for i in (0, 1, 2))
    # Folded by default, under everyone else, titled with its count and the reason they share.
    assert folded["fold"] == "On hold: 2, waiting for a role to be posted: Show", folded["fold"]
    assert IVO not in folded["main"] and LEORIC not in folded["main"] and not folded["held"]
    assert folded["below"] is True and folded["foldFits"] is True, folded
    # Shown: each card says it is on hold and why, with nothing that reads as owed and no
    # draft at all until there is a role to write it for.
    assert open_["fold"] == "On hold: 2, waiting for a role to be posted: Hide"
    assert [c["id"] for c in open_["held"]] == [IVO, LEORIC]
    for c, employer in zip(open_["held"], ("Quayside Foods", "Thornbury Bank")):
        assert c["state"] == "On hold", c
        assert c["line"] == ROLE % employer, c
        assert not c["filled"] and not c["copy"] and not c["sent"] and c["draftOpen"] is None, c
        assert "They replied" not in c["buttons"] and c["fits"], c
    assert again["fold"] == folded["fold"] and not again["held"]


def test_a_held_draft_is_folded_away_with_send_it_anyway_inside(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "contacts", "ready": "!!document.querySelector('#main [data-on-hold]')", "eval": LOOK},
        {"open": "held:contacts", "ready": "!!document.querySelector('#main ul[data-held-list]')", "eval": LOOK},
        # The one way on: Send it anyway, inside the folded draft.
        {"eval": TAP % "unhold:msg-wren-2"},
        {"ready": "!document.querySelector('#main [data-on-hold]')", "eval": LOOK},
    ], vp, model=_one_with_a_draft())
    folded, open_, sent = (got["after"][i]["eval"] for i in (0, 1, 3))
    assert folded["fold"] == "On hold: 1: Show" and WREN not in folded["main"], folded
    (card,) = open_["held"]
    assert card["id"] == WREN and card["state"] == "On hold" and card["line"] == AWAY, card
    # The draft is there, folded away, with no Copy and no I sent it; the way on is inside it.
    assert card["draftOpen"] is False and card["anyway"], card
    assert not card["copy"] and not card["sent"] and not card["filled"], card
    # Sent anyway: back in the list with the draft open, ready to copy and mark as sent.
    assert sent["fold"] is None and WREN in sent["main"], sent
    back = next(c for c in sent["mainCards"] if c["id"] == WREN)
    assert back["draftOpen"] is True and back["copy"] and back["sent"] and back["state"] != "On hold", back


def test_someone_on_hold_is_drawn_once_in_their_group_with_the_whole_list_in(run, tmp_path, vp):
    """The whole list beside the page holds everyone, those on hold too: brought into the main
    list for its fold, it drew a held person a second time there, the same card as in the On
    hold group, its held follow-up folded under it (the maintainer's page, 2026-11-12)."""
    m = _one_with_a_draft()
    # The engine's own count of what is ready to send never holds a held draft.
    m["to_send"] = {"n": m["to_send"]["n"] - 1, "ids": [i for i in m["to_send"]["ids"] if i != "msg-wren-2"]}
    look = "Object.assign(%s, {n: document.querySelectorAll('#main [data-item=\"%s\"]').length})" % (LOOK, WREN)
    got = _go(run, tmp_path, [
        {"hash": "contacts", "ready": "LJS.state().views.has('list~people~1') && "
                                      "!!document.querySelector('#main [data-on-hold]') && "
                                      "!!document.querySelector('#main [data-k=\"fold:contacts\"]')", "eval": look},
        # Everyone else, the whole list's own people with them: drawn once that list is in.
        {"open": "fold:contacts", "ready": "!!document.querySelector('#main [data-item=\"%s\"]')" % ORLA, "eval": look},
        {"open": "held:contacts", "ready": "!!document.querySelector('#main ul[data-held-list]')", "eval": look},
    ], vp, model=m, seed=_whole_list(m))
    folded, everyone, open_ = (got["after"][i]["eval"] for i in (0, 1, 2))
    assert WREN not in folded["main"] and folded["n"] == 0, folded
    assert folded["fold"] == "On hold: 1: Show", folded
    assert ORLA in everyone["main"] and WREN not in everyone["main"] and everyone["n"] == 0, everyone
    # Shown: in the group once, and nowhere else on the screen.
    assert [c["id"] for c in open_["held"]] == [WREN] and open_["n"] == 1, open_
    assert WREN not in open_["main"], open_
    (card,) = open_["held"]
    assert card["state"] == "On hold" and card["line"] == AWAY and card["draftOpen"] is False, card


def test_a_name_searched_for_still_finds_someone_on_hold(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "contacts", "ready": "!!document.querySelector('#main [data-on-hold]')", "eval": SEARCH % "leoric"},
        {"ready": "!document.querySelector('#main [data-on-hold]')", "eval": LOOK},
    ], WIDE, model=_two_waiting_for_a_role())
    found = got["after"][1]["eval"]
    assert found["main"] == [LEORIC] and found["mainCards"][0]["state"] == "On hold", found


def test_a_link_to_someone_on_hold_opens_the_group_on_their_card(run, tmp_path):
    """A link to a person opened the "more people" fold behind them, never the On hold group,
    so a link to someone on hold landed with their card still folded away (issue #251)."""
    got = _go(run, tmp_path, [
        {"hash": "contacts/" + LEORIC, "ready": "!!document.querySelector('#main [data-on-hold]')",
         "eval": LOOK},
    ], WIDE, model=_two_waiting_for_a_role())
    landed = got["after"][0]["eval"]
    assert LEORIC in [c["id"] for c in landed["held"]], landed
    assert landed["fold"] == "On hold: 2, waiting for a role to be posted: Hide", landed
