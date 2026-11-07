"""A referral that cannot happen is ended in one tap, and everything it held lets go.

The maintainer, 2026-11-07: a contact had said they would refer them, they applied and were
turned down at once, and there was no way to say so: "The referral is over" was a list of
choices with a Save, two redundant answers, and "Something else" with no box. Now the
referral's end is a short sheet of buttons, each done at once with Undo (DESIGN.md, the
trash): "I was turned down" closes the application there as rejected, "I withdrew" as
withdrawn, "Not happening" only stops the wait, and every one leaves nothing owed to the
referrer, so their card leaves To do. Something else opens the person's own box. Every
person and employer here is invented (tests/app_state.py, the sample page model).
"""
from __future__ import annotations

import copy
import csv
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

from test_a_tick_on_the_page_is_applied_once import Search  # noqa: E402

WREN = "fernhill_freight_halloway"
TAMSIN = "copperleaf_pay_tamsin"
APP_JS = os.path.join(ROOT, "templates", "app", "app.js")


@pytest.fixture
def search(tmp_path):
    s = Search(str(tmp_path))
    # Wren's employer has an application that went: applied, and waiting to hear.
    path = os.path.join(s.state, "job_search_tracker.csv")
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
        cols = list(rows[0])
    for r in rows:
        if r["company"] == "Fernhill Freight":
            r.update(status="applied", applied_on="2026-10-20", confirmed_by="chat",
                     confirmed_at="2026-10-20 09:00")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return s


def _person(search, cid):
    return next(p for p in search.model()["people"] if p["id"] == cid)


def _agreed(search):
    p = _person(search, WREN)
    aid = search.act("referral.agreed", WREN, value="Operations Analyst", rev=p["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    search.written_back()
    assert _person(search, WREN)["status"] == "referral_in_progress"


# ------------------------------------------------------------------ the engine


def test_turned_down_closes_the_application_and_owes_the_referrer_nothing(search):
    _agreed(search)
    before = search.tracker_row("Fernhill Freight")
    assert before["status"] not in ("rejected", "withdrawn")
    p = _person(search, WREN)
    end = search.act("referral.ended", WREN, value={"why": "rejected"}, rev=p["rev"])
    assert search.apply()["ok"] == [end], search.receipt(end)
    note = search.receipt(end)["note"]
    assert "Fernhill Freight said no" in note and "application is closed" in note, note
    assert search.tracker_row("Fernhill Freight")["status"] == "rejected"
    m = search.model()
    juno = next(p for p in m["people"] if p["id"] == WREN)
    assert juno["status"] == "in_conversation" and juno["owed"] is None, juno
    assert juno["group"] not in ("now", "follow"), juno
    assert not [d for d in m["due"] if WREN in str(d.get("contact") or d.get("item") or "")], \
        "nothing about the referral is left on To do"
    assert not [r for r in m["referrals"] if r["contact"] == WREN and r["stage"] != "ended"]
    # Undo puts back every part: the person waiting on and the application open.
    search.written_back()
    back = search.act("undo", None, value={"undoes": end})
    assert search.apply()["ok"] == [back], search.receipt(back)
    assert search.tracker_row("Fernhill Freight")["status"] == before["status"]
    assert search.tracker_row("Fernhill Freight")["notes"] == before["notes"]
    assert _person(search, WREN)["status"] == "referral_in_progress"


def test_withdrew_and_not_happening_each_reach_the_engine(search):
    _agreed(search)
    p = _person(search, WREN)
    end = search.act("referral.ended", WREN, value={"why": "not_happening"}, rev=p["rev"])
    assert search.apply()["ok"] == [end], search.receipt(end)
    assert "No longer waiting for Wren" in search.receipt(end)["note"]
    # Not happening leaves the application as it was: only the wait stops.
    assert search.tracker_row("Fernhill Freight")["status"] not in ("rejected", "withdrawn")
    assert _person(search, WREN)["owed"] is None
    search.written_back()
    back = search.act("undo", None, value={"undoes": end})
    assert search.apply()["ok"] == [back]
    search.written_back()
    p = _person(search, WREN)
    out = search.act("referral.ended", WREN, value={"why": "withdrawn"}, rev=p["rev"])
    assert search.apply()["ok"] == [out], search.receipt(out)
    assert search.tracker_row("Fernhill Freight")["status"] == "withdrawn"
    assert "you withdrew from Fernhill Freight" in search.receipt(out)["note"]


# ------------------------------------------------------------------ the page


def _sheet_calls(src):
    """Each `sheet({...})` call's argument text, braces balanced, strings skipped."""
    for m in re.finditer(r"\bsheet\(\{", src):
        i, depth, quote = m.end() - 1, 0, None
        j = i
        while j < len(src):
            c = src[j]
            if quote:
                if c == "\\":
                    j += 2
                    continue
                if c == quote:
                    quote = None
            elif c in "\"'`":
                quote = c
            elif c in "{[(":
                depth += 1
            elif c in "}])":
                depth -= 1
                if depth == 0:
                    yield src[i:j + 1]
                    break
            j += 1


def test_no_sheet_is_a_choice_and_then_a_save():
    """DESIGN.md, the trash: several answers are a short sheet of buttons, the one tapped
    done at once, never a choice and then a second button. A sheet whose only field is a
    list of choices that must be made (or saved) breaks it, wherever it is."""
    src = open(APP_JS, encoding="utf-8").read()
    bad = []
    for call in _sheet_calls(src):
        fields = re.search(r"fields: \[(.*)\]", call, re.S)
        if not fields:
            continue
        kinds = re.findall(r"\btype: \"(\w+)\"", fields.group(1))
        if kinds == ["radio"] and (re.search(r"required: true", fields.group(1))
                                   or re.search(r"submit: \"(?:Save|Next)\"", call)):
            bad.append(re.search(r"title: ([^,]+)", call).group(1))
    assert not bad, f"a choice and then Save: {bad}"


def test_the_referral_ends_in_one_tap_from_its_sheet_and_from_the_trash(tmp_path):
    from test_the_page_journeys import _go, _item, _sample, browser, PHONE, WIDE
    gen = browser()
    run = next(gen)
    try:
        for vp in (PHONE, WIDE):
            m = _sample()
            nxt = copy.deepcopy(m)
            p = _item(nxt, TAMSIN)
            p.update(status="in_conversation", owed=None, group="talking", next_action="", due=None, rev="p-tamsin2")
            got = _go(run, tmp_path, [
                {"hash": "contacts", "more": TAMSIN, "click": "The referral is over: Tamsin", "read": "dialog"},
                {"click": "I was turned down", "within": "dialog", "receipts": True, "view": {"people": nxt["people"]}},
                {"hash": "contacts", "read": '[data-item="%s"]' % TAMSIN},
            ], vp, model=m)
            sheet = got["after"][0]["dialog"]
            # Plain choices, each one tap: no list to pick from and no Save.
            for word in ("I was turned down", "I withdrew", "Not happening", "Something else"):
                assert word in sheet, sheet
            for word in ("Not this time", "I was hired", "How it ended", "Save"):
                assert word not in sheet, sheet
            ended = [a for a in got["actions"] if a["action"] == "referral.ended"]
            assert len(ended) == 1 and ended[0]["item"] == TAMSIN and ended[0]["value"] == {"why": "rejected"}, got["actions"]
            assert "The referral is over" not in got["after"][2]["text"]
            # Something else: the sheet closes and the person's own box opens, its field focused.
            got = _go(run, tmp_path, [
                {"hash": "contacts", "more": TAMSIN, "click": "The referral is over: Tamsin"},
                {"click": "Something else", "within": "dialog", "exact": True, "eval": "(() => { const a = document.activeElement; return a && a.tagName === 'TEXTAREA' && !!a.closest('[data-item=\"%s\"]') ? 'focused' : (a ? a.tagName + ':' + (a.id || '') : 'none'); })()" % TAMSIN},
            ], vp, model=_sample())
            assert got["after"][1]["eval"] == "focused", got["after"][1]["eval"]
            # The person's trash says the same, first, while the referral is in flight.
            got = _go(run, tmp_path, [
                {"hash": "todo", "read": "#main"},
                {"hash": "contacts", "click": "Not Tamsin at Copperleaf Pay?", "read": "dialog"},
                {"click": "I was turned down", "within": "dialog"},
                {"hash": "todo", "read": "#main"},
            ], vp, model=_sample())
            assert "Tamsin" in got["after"].pop(0)["text"], "she is on To do before"
            sheet = got["after"][0]["dialog"]
            assert sheet.index("I was turned down") < sheet.index("Something else"), sheet
            ended = [a for a in got["actions"] if a["action"] == "referral.ended"]
            assert ended and ended[0]["value"] == {"why": "rejected"}
            # Off To do at once, before Claude has caught up: nothing is owed to Tamsin now.
            assert "Tamsin" not in got["after"][2]["text"], got["after"][2]["text"][:2000]
    finally:
        try:
            next(gen)
        except StopIteration:
            pass
