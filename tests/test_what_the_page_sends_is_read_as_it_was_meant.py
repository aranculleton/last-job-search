"""What the person typed or tapped reaches its writer as they meant it.

FUNCTIONS_SPEC.md (2026-10-25) section 4, items 1 and 2: the page sent `value` as a bare
string where the writers read `value.on`, `value.why` and `value.text`, so a date given for
"When did you apply?" became today and a reason for Set aside was lost; a card's alert or
suggestion was sent with the whole page's rev instead of the card's, and refused as
changed; Bring back on a filtered group named an item nothing could find. The one shape of
`value` is an object (CONTRACT 6.13), a bare value is read as the field each action
expects, and every case here has its test. Every person and employer is invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_actions  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import KESTREL, Search  # noqa: E402


@pytest.fixture
def search(tmp_path):
    return Search(str(tmp_path))


# ------------------------------------------------------------------ one shape, read either way


@pytest.mark.parametrize("action,field", sorted(app_actions.BARE.items()))
def test_a_bare_value_is_the_field_each_action_reads(action, field):
    got = app_actions.value_of({"action": action, "value": "pay"})
    assert got[field] == "pay" and got["value"] == "pay"
    # The object shape is taken as it is, never wrapped again.
    assert app_actions.value_of({"action": action, "value": {field: "x"}}) == {field: "x"}
    assert app_actions.value_of({"action": action, "value": None}) == {}


@pytest.mark.parametrize("action", sorted(app_actions.DATED))
def test_a_bare_day_is_the_day_wherever_an_action_takes_one(action):
    got = app_actions.value_of({"action": action, "value": "2026-10-20"})
    assert got["until" if action in ("due.snooze", "brief.pause") else "on"] == "2026-10-20"


def test_every_action_with_a_bare_field_is_in_the_table():
    assert set(app_actions.BARE) <= set(app_actions.ACTIONS)
    assert set(app_actions.DATED) <= set(app_actions.BARE)


def test_a_date_typed_for_when_did_you_apply_is_the_one_recorded(search):
    aid = search.act("job.applied", "r9-1", value="2026-10-20")
    got = search.apply()
    assert got["ok"] == [aid], search.receipt(aid)
    row = search.tracker_row("Brindle Hart Logistics")
    assert row["applied_on"] == "2026-10-20"
    assert "2026-10-20" in search.receipt(aid)["note"]


def test_a_day_that_has_not_come_yet_is_refused(search):
    aid = search.act("job.applied", "r9-1", value={"on": "2026-11-30"})
    assert search.apply()["conflict"] == [aid]
    assert "not come yet" in search.receipt(aid)["note"]


def test_the_reason_picked_for_set_aside_is_kept_and_learned(search):
    aid = search.act("job.dismiss", "r9-4", value="pay")
    assert search.apply()["ok"] == [aid]
    with open(os.path.join(search.state, "job_scraper", "seen_jobs.json"), encoding="utf-8") as fh:
        seen = json.load(fh)["seen"]
    entry = next(e for e in seen.values() if isinstance(e, dict)
                 and e.get("url") == "https://jobs.example/larkspur/supply")
    assert entry["exclusion_reason"] == "pay"
    with open(os.path.join(search.profile, "learned.json"), encoding="utf-8") as fh:
        learned = json.load(fh)
    rows = learned if isinstance(learned, list) else learned.get("rules") or learned.get("entries")
    assert any("pay" in str(r.get("said") or "") for r in rows)


def test_a_draft_marked_applied_on_another_day_keeps_that_day(search):
    item = search.item(KESTREL)
    aid = search.act("ready.applied", KESTREL, value="2026-10-23", rev=item["rev"])
    assert search.apply()["ok"] == [aid]
    assert search.tracker_row("Kestrel Mutual")["applied_on"] == "2026-10-23"


# ------------------------------------------------------------------ the rev a card's buttons send


def _closed(search, rank=4):
    path = os.path.join(search.state, "documents", "rounds", "r9.json")
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    rows[rank - 1].update(link_status="closed",
                          link_check="closed: no longer on the board, checked 2026-10-24 09:00 UTC")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)


def test_every_button_on_an_alert_or_a_suggestion_carries_its_cards_rev(search):
    _closed(search)
    m = search.model()
    seen = 0
    for section in ("ready", "messages", "interviews"):
        for item in m[section]:
            for a in item["alerts"] + ([item["suggest"]] if item["suggest"] else []):
                act = a.get("action") or {}
                if act.get("type") == "act" and act.get("item") in (None, "", item["id"]):
                    assert act["rev"] == item["rev"]
                    seen += 1
    for item in m["jobs"]["rows"]:
        for a in item["alerts"] + ([item["suggest"]] if item["suggest"] else []):
            act = a.get("action") or {}
            if act.get("type") == "act" and act.get("item") in (None, "", item["id"]):
                assert act["rev"] == item["rev"]
                seen += 1
    assert seen, "the sample has at least one alert button that acts on its card"


def test_a_button_on_an_alert_applies_with_the_rev_it_carries(search):
    _closed(search)
    m = search.model()
    card = next(r for r in m["jobs"]["rows"] if r["id"] == "r9-4")
    button = card["alerts"][0]["action"]
    assert button["action"] == "job.dismiss"
    aid = search.act(button["action"], button["item"], value=button["value"], rev=button["rev"])
    got = search.apply()
    assert got["ok"] == [aid], search.receipt(aid)


def test_the_whole_pages_rev_is_never_compared_with_an_items(search):
    """An item's action is checked against that item's rev alone (CONTRACT 6.13): the page's
    top-level rev, sent where the item's was missing, is refused as stale even when nothing
    has changed, so the page has to send the item's own."""
    rev = search.model()["rev"]
    aid = search.act("job.dismiss", "r9-4", value={"why": "closed"}, rev=rev)
    assert search.apply()["stale"] == [aid]


# ------------------------------------------------------------------ a filtered group comes back


def test_bring_back_on_a_filtered_group_brings_back_every_posting_in_it(search):
    m = search.model()
    group = next(g for g in m["jobs"]["filtered"]["groups"] if g["reason"] == "location")
    assert group["id"] == "filtered~location" and group["rev"]
    aid = search.act("job.bring_back", "filtered~location", value="location",
                     rev=group["rev"])
    got = search.apply()
    assert got["ok"] == [aid], search.receipt(aid)
    companies = [r["company"] for r in search.model()["jobs"]["rows"]]
    assert companies.count("Quayside Foods") == 2
    search.written_back()
    back = search.act("undo", None, value={"undoes": aid})
    assert search.apply()["ok"] == [back]
    rows = search.model()["jobs"]["rows"]
    assert {r["status"] for r in rows if r["company"] == "Quayside Foods"} == {"dismissed"}


def test_a_group_sent_with_its_own_rev_applies_too(search):
    group = next(g for g in search.model()["jobs"]["filtered"]["groups"]
                 if g["reason"] == "screen")
    aid = search.act("job.bring_back", group["id"], rev=group["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    assert "Dovecote Freight" in [r["company"] for r in search.model()["jobs"]["rows"]
                                  if r["title"] == "Inventory Lead"]
