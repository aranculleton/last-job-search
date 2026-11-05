"""What a search left out reads by the rule that cut it, and every rule can be changed or dropped.

The maintainer's Jobs page showed "13168 left out by the search" as one flat list under
"Title · 5183": "surely there's a far better way to display this information. What if I want
to change it or filter it or spot something wrong or change my mind or preferences ... from
13k?" Now the left-out list is one row a rule in plain words (tools/rules_view.py left_view),
each with its count, three examples, its rows held for a search box (never all of them), a
few from across it to check, and the setting its pencil changes; Settings has Your rules,
every rule as one sentence with the day it was set, the person's words, what it left out
lately, its pencil and its bin; a rule old and busy asks "Still right?" there, quietly, and
the Brief says so at most once a month. A bilingual title ("<English> // <French>") is no
longer cut as French. Every person and employer is invented; the scale is a real copy's.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app_actions  # noqa: E402
import app_model  # noqa: E402
import filtered  # noqa: E402
import person  # noqa: E402
import prefilter  # noqa: E402
import profile_set  # noqa: E402
import rules_view  # noqa: E402
import text_screen  # noqa: E402

TODAY = dt.date(2026, 11, 5)
NOW = dt.datetime(2026, 11, 5, 21, tzinfo=dt.timezone.utc)
BILINGUAL = "Staff Data Analyst // Analyste de données principal"


# ------------------------------------------------------------------ a title in two languages

def test_a_bilingual_title_is_not_cut_as_the_other_language(monkeypatch):
    # The text screen read the whole title as French.
    assert text_screen.title_language(BILINGUAL) == ""
    assert text_screen.screen({"title": BILINGUAL, "desc": "SQL reporting. " * 20})["cuts"] == []
    assert text_screen.title_language("Analyste de données principal") == "French"
    # The person's own title rule, a French title pattern on NEGATIVE, cut it at the search.
    monkeypatch.setattr(prefilter, "NEGATIVE", [(r"\banalyste\b", "a title in French")])
    assert prefilter.title_verdict(BILINGUAL)[0] == "PASS"
    assert prefilter.title_verdict("Analyste de données principal") == ("FAIL", "a title in French")
    # A French requirement in the posting itself is still cut, whatever the title.
    said = text_screen.screen({"title": BILINGUAL, "desc": "SQL reporting. " * 20
                               + "Fluency in French is required for this role."})["cuts"]
    assert said and "French stated as a requirement" in said[0]
    # A ruling the old screen made on such a title is released by itself.
    assert text_screen.ruling_refused(f'job title is in French: "{BILINGUAL}"')
    assert not text_screen.ruling_refused('job title is in French: "Analyste de données principal"')


# ------------------------------------------------------------------ 13,168 left out, by rule

SHAPES = [  # (how many, stage, rule, reason, title)
    (5183, "search", "title", "title: title matches none of the role families in profile/search.py "
     "POSITIVE", "Warehouse Supervisor {n}"),
    (2100, "screen", "screen", 'French stated as a requirement: "Fluency in French is required"',
     "Data Analyst {n}"),
    (3004, "search", "location", "location: on-site outside the Greater Manchester (london)",
     "Supply Analyst {n}"),
    (412, "shortlist", "candidate's bar", "candidate's bar: turned down on the page, "
     "2026-07-01: not for me", "Planning Analyst {n}"),
    (90, "shortlist", "already on your list or applied for", "already on your list, from "
     "search r7", "Inventory Analyst {n}"),
    (1900, "search", "age", "age: posted 40 days ago, past the 14-day hard limit",
     "Demand Planner {n}"),
    (379, "screen", "screen", "stated range tops out at £21,000, below £32,000: a different job "
     "level", "Junior Analyst {n}"),
    (100, "throttle", "company throttle", "company throttle: three already this week",
     "Operations Analyst {n}"),
]


def _left(st, name="r20"):
    found = []
    for s, (count, stage, rule, reason, title) in enumerate(SHAPES):
        for n in range(count):
            company = "Saltmere Logistics" if stage == "shortlist" and rule.startswith("cand") \
                else f"Employer {n % 97}"
            found.append({"title": title.format(n=n), "company": company,
                          "location": "London" if rule == "location" else "Manchester",
                          "url": f"https://jobs.example/{s}/{n}", "stage": stage,
                          "rule": rule, "reason": reason})
    assert len(found) == 13168
    rounds = st / "documents" / "rounds"
    (rounds / "filtered").mkdir(parents=True, exist_ok=True)
    (rounds / f"{name}.json").write_text(json.dumps([{
        "title": "Data Analyst", "company": "Kettlewell Foods", "location": "Manchester",
        "url": "https://jobs.example/kept/1", "fit": 80, "priority": 82,
        "first_seen": "2026-11-04"}]), encoding="utf-8")
    filtered.add(str(rounds), name, found)
    return found


@pytest.fixture
def state(tmp_path, monkeypatch):
    st = tmp_path / "state"
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), st)
    monkeypatch.setenv("LJS_STATE", str(st))
    import run_round
    from company_key import key as company_key
    monkeypatch.setattr(run_round, "declined_now", lambda: {
        company_key("Saltmere Logistics"): "turned down on the page, 2026-07-01: not for me"})
    return st


def test_thirteen_thousand_left_out_read_as_one_row_a_rule(state):
    _left(state)
    t0 = time.monotonic()
    ctx = app_model.Ctx(TODAY, NOW)
    jobs = app_model._jobs(ctx, {})
    took = time.monotonic() - t0
    f = jobs["filtered"]
    assert f["count"] == 13168
    by = {g["label"]: g for g in f["groups"]}
    assert {k: g["count"] for k, g in by.items()} == {
        "Not your field": 5183, "Outside your places": 3004, "Needs French": 2100,
        "Older than your search window": 1900, "An employer you turned down": 412,
        "Pay under your cut line": 379, "Enough already at that employer": 100,
        "Already applied or a copy": 90}
    assert [g["label"] for g in f["groups"]][:2] == ["Not your field", "Outside your places"]
    field = by["Not your field"]
    assert field["examples"] == ["Warehouse Supervisor 0", "Warehouse Supervisor 1",
                                 "Warehouse Supervisor 2"]
    assert field["last"] == "2026-11-04" and len(field["items"]) == 20
    assert field["edit"] == {"what": "roles"}
    assert by["Needs French"]["edit"] == {"what": "languages", "language": "French"}
    assert by["Outside your places"]["edit"] == {"what": "places"}
    assert by["Already applied or a copy"]["edit"] is None
    # Check a few: five from across the whole rule, the first and the last among them.
    titles = [r["title"] for r in field["check"]]
    assert len(titles) == 5 and titles[0] == "Warehouse Supervisor 0" \
        and titles[-1] == "Warehouse Supervisor 5182"
    # Held for the search box: a few hundred a rule, never all thirteen thousand.
    whole, shown, _folded, doc = ctx._got["lists"]["filtered"]
    assert doc and len(whole) <= rules_view.HELD_MAX
    assert max(sum(1 for r in whole if r["g"] == g["id"]) for g in f["groups"]) \
        == rules_view.HELD_PER_RULE
    assert all(g["held"] <= rules_view.HELD_PER_RULE for g in f["groups"])
    assert len(json.dumps(jobs)) < 120_000
    assert took < 20, f"Jobs took {took:.1f}s to build over 13,168 left out"
    # A whole rule's rows come back by its id, as before.
    t = {}
    app_model._filtered("r20", t)
    assert t["filtered~field"]["kind"] == "filtered_group" and len(t["filtered~field"]["ns"]) == 5183
    # The list's first line counts each rule, for Your rules to read a month of searches.
    head = rules_view._head(str(state / "documents" / "rounds" / "filtered" / "r20.json"))
    assert head["kinds"]["field"] == 5183 and head["kinds"]["language:French"] == 2100


# ------------------------------------------------------------------ Your rules

@pytest.fixture
def profile(tmp_path, monkeypatch, state):
    """A copy of the example profile with dozens of rules: 30 employers turned down, the
    sectors it rules out, and learned rules."""
    prof = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), prof, ignore=shutil.ignore_patterns("state"))
    monkeypatch.setenv("LJS_PROFILE", str(prof))
    person.reset()
    declined = {f"brindlewood {n}": f"turned down on the page, 2026-0{1 + n % 7}-1{n % 9}: "
                                    f"not for me ({n})" for n in range(30)}
    profile_set.set_line("search.py", "BAR_DECLINED", declined)
    (prof / "learned.json").write_text(json.dumps({"entries": [
        {"area": "messages", "said": "never say reach out", "rule": "Never write reach out in "
         "a message.", "date": "2026-06-01", "status": "active"},
        {"area": "jobs", "said": "no night shifts", "rule": "Rank lower roles with night "
         "shifts.", "date": "2026-10-20", "status": "active"}]}), encoding="utf-8")
    import run_round
    monkeypatch.setattr(run_round, "declined_now", lambda: dict(declined))
    yield prof
    person.reset()


def test_every_rule_reads_as_one_sentence_with_what_it_left_out(state, profile):
    _left(state)
    rows = rules_view.your_rules(TODAY, {})
    by = {r["id"]: r for r in rows}
    assert len(rows) >= 38
    assert by["rule~languages"]["sentence"] == ("You work in English; a job that needs another "
                                               "language is left out.")
    assert by["rule~languages"]["left_out"] == 2100
    assert by["rule~roles"]["left_out"] == 5183 and by["rule~roles"]["edit"] == {"what": "roles"}
    assert by["rule~places"]["sentence"].startswith("You search in Manchester, Salford")
    one = by["rule~declined~brindlewood 3"]
    assert one["sentence"] == "No more roles from Brindlewood 3: Not for me (3)."
    assert one["set_on"] == "2026-04-13" and one["drop"] == {"kind": "declined",
                                                              "key": "brindlewood 3"}
    sector = next(r for r in rows if r["kind"] == "sector")
    assert sector["sentence"] == ("Left out: A sector you will not work in (gambling and "
                                  "tobacco).")
    learned = [r for r in rows if r["kind"] == "learned"]
    assert [r["words"] for r in learned] == ["never say reach out", "no night shifts"]
    assert learned[0]["set_on"] == "2026-06-01"


def test_an_old_busy_rule_asks_still_right_quietly_once_a_month(state, profile):
    _left(state)
    rules_view.note_set("rule~roles", "only analyst roles", "2026-06-01")
    rules_view.note_set("rule~places", "manchester for now", "2026-10-01")
    # brindlewood 3 was turned down in April (its own words say so) and cut none since.
    rows = rules_view.your_rules(TODAY, {})
    by = {r["id"]: r for r in rows}
    assert by["rule~roles"]["still_right"]                            # 157 days, 5,183 cut
    assert by["rule~places"]["review_on"] == "2026-10-31" and by["rule~places"]["still_right"]
    assert not by["rule~declined~brindlewood 3"]["still_right"]
    assert not by["rule~languages"]["still_right"]                    # no day it was set
    line = rules_view.review_line(rows, TODAY)
    assert line == "2 of your rules are 5 months old: Your rules"
    # Set aside, the line is not said again this month; next month it may be.
    rules_view.dismiss_brief(TODAY.isoformat())
    assert rules_view.review_line(rows, TODAY) is None
    assert rules_view.review_line(rows, dt.date(2026, 12, 2)) is not None
    # Kept as it is: not asked about for another three months.
    rules_view.keep_rule("rule~roles", TODAY.isoformat())
    rules_view.keep_rule("rule~places", TODAY.isoformat())
    again = {r["id"]: r for r in rules_view.your_rules(TODAY, {})}
    assert not again["rule~roles"]["still_right"]
    assert not again["rule~places"]["still_right"] and not again["rule~places"].get("review_on")
    # Never a To do: nothing about rules is in what the page asks the person to do.
    m, _ = app_model.build(TODAY, NOW, only=("needs_you", "rules"))
    assert "rule" not in json.dumps(m["needs_you"]).lower()


class _W:
    def add(self, *a, **k):
        pass


def _run(action, target, value=None):
    act = {"action": action, "at": "2026-11-05T21:00:00Z", "value": value or {}}
    return app_actions.Run("a1", act, target, {"work": {}}, _W(), "cloud-1", "UTC", NOW)


def test_a_rule_is_dropped_or_changed_through_its_own_writer(state, profile):
    rows = {r["id"]: r for r in rules_view.your_rules(TODAY, {})}
    # An employer turned down comes off BAR_DECLINED, and the undo puts it back.
    one = rows["rule~declined~brindlewood 3"]
    got = app_actions._rule_drop(_run("rule.drop", {"kind": "your_rule", "id": one["id"],
                                                    "drop": one["drop"]}))
    assert "brindlewood 3" not in profile_set.get("search.py", "BAR_DECLINED")
    app_actions._rule_undrop(_run("rule.undrop", {}, got["undo"]["value"]))
    assert "brindlewood 3" in profile_set.get("search.py", "BAR_DECLINED")
    # A kind of employer ruled out, written as patterns no page can edit, is named off.
    sector = next(r for r in rows.values() if r["kind"] == "sector")
    app_actions._rule_drop(_run("rule.drop", {"kind": "your_rule", "id": sector["id"],
                                              "drop": sector["drop"]}))
    assert profile_set.get("search.py", "BAR_EXCLUDED_OFF") == [sector["drop"]["why"]]
    assert not [r for r in rules_view.your_rules(TODAY, {}) if r["kind"] == "sector"]
    # A learned rule is retired, kept as history.
    first = rows["rule~learned~1"]
    app_actions._rule_drop(_run("rule.drop", {"kind": "your_rule", "id": first["id"],
                                              "drop": first["drop"]}))
    import learned
    assert learned.load()[0]["status"] == "retired"
    # A language added: a job needing it is no longer left out, and the day is kept.
    app_actions._search_set(_run("search.set", {"kind": "search", "id": "search-settings"},
                                 {"what": "languages", "add": "French",
                                  "said": "I work in French too, for now"}))
    assert profile_set.get("search.py", "LANGUAGES_HELD") == ["english", "french"]
    lang = {r["id"]: r for r in rules_view.your_rules(TODAY, {})}["rule~languages"]
    assert lang["sentence"].startswith("You work in English and French")
    assert lang["set_on"] == "2026-11-05" and lang["review_on"] == "2026-12-05"
    with pytest.raises(app_actions.Refused):
        app_actions._rule_drop(_run("rule.drop", {"kind": "your_rule", "id": "rule~roles",
                                                  "drop": None}))


def test_bar_reads_a_kind_of_employer_turned_back_on():
    import bar
    assert all(why not in bar.EXCLUDED_OFF for _rx, why in bar.EXCLUDED_RULES)
