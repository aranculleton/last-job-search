"""One company-research cache: one reader, one writer, one freshness rule.

`company_research/<key>.json` was written and read in several places with no shared
code. The freshness rule lived only in prose, the one code reader (the call prep)
never checked `fetched_date`, and /network kept a second, dated record in the same
file with nothing to merge it in. tools/company_research.py is now the one place:
these pin its lookup, its merge, its freshness, and that the prose points at it
rather than restating a number. Every employer and fact here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "network"))

import company_research as C  # noqa: E402
import discovery as D  # noqa: E402
import prep  # noqa: E402

TODAY = dt.date(2026, 10, 15)
FACT = {"claim": "Oakmere Foods opened a second bakery site in Bolton",
        "quote": "Our second bakery site in Bolton opened this spring.",
        "url": "https://oakmere.example/news/bolton", "date_seen": "2026-10-01",
        "page_title": "Oakmere Foods news"}


def _write(root, name, data):
    folder = root / C.DIR
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(json.dumps(data), encoding="utf-8")


def _days_ago(n):
    return (TODAY - dt.timedelta(days=n)).isoformat()


# ------------------------------------------------------------------ load and save

def test_nothing_cached_is_an_empty_miss(tmp_path):
    assert C.load("Oakmere Foods", TODAY, root=tmp_path) == ({}, None, False)
    assert C.path("Oakmere Foods", root=tmp_path) is None


def test_saved_research_reads_back_with_its_age(tmp_path):
    written = C.save("Oakmere Foods", {"fetched_date": _days_ago(3), "facts": [FACT]},
                     root=tmp_path)
    assert os.path.basename(written) == "oakmere-foods.json"
    data, age, fresh = C.load("Oakmere Foods plc", TODAY, root=tmp_path)
    assert data["facts"] == [FACT] and data["company"] == "Oakmere Foods"
    assert (age, fresh) == (3, True)


def test_a_save_merges_and_never_freshens_the_research(tmp_path):
    _write(tmp_path, "oakmere-foods.json",
           {"company": "Oakmere Foods", "fetched_date": _days_ago(60), "facts": [FACT],
            "do_not_claim": ["Do not call Oakmere the largest bakery in the North West"]})
    C.save("Oakmere Foods", {"network_presence": {"verdict": "no_relevant_presence"}},
           root=tmp_path)
    data, age, fresh = C.load("Oakmere Foods", TODAY, root=tmp_path)
    assert data["facts"] == [FACT] and data["do_not_claim"]
    assert data["network_presence"]["verdict"] == "no_relevant_presence"
    assert (age, fresh) == (60, False)


def test_research_for_another_employer_is_refused(tmp_path):
    with pytest.raises(ValueError):
        C.save("Oakmere Foods", {"company": "Saltmarsh Analytics", "facts": [FACT]},
               root=tmp_path)
    assert C.path("Oakmere Foods", root=tmp_path) is None


# ------------------------------------------------------------------ freshness

def test_fresh_is_inside_the_constant_and_stale_is_past_it(tmp_path):
    edge = C.RESEARCH_FRESH_DAYS
    assert C.is_fresh({"fetched_date": _days_ago(edge)}, TODAY)
    assert not C.is_fresh({"fetched_date": _days_ago(edge + 1)}, TODAY)
    assert C.age_days({"fetched_date": _days_ago(edge + 1)}, TODAY.isoformat()) == edge + 1


def test_a_file_with_no_date_is_read_but_never_fresh(tmp_path):
    _write(tmp_path, "oakmere-foods.json", {"company": "Oakmere Foods", "facts": [FACT]})
    data, age, fresh = C.load("Oakmere Foods", TODAY, root=tmp_path)
    assert data["facts"] == [FACT] and age is None and fresh is False
    assert "not fresh" in C.describe("Oakmere Foods", TODAY, root=tmp_path)


# ------------------------------------------------------------------ key matching

def test_a_hand_named_file_is_found_through_the_company_key(tmp_path):
    _write(tmp_path, "brindle-and-hart-logistics-ltd.json",
           {"company": "Brindle and Hart Logistics Ltd", "fetched_date": _days_ago(1)})
    for spelling in ("Brindle & Hart Logistics", "Brindle and Hart Logistics", "BRINDLE & HART LOGISTICS LTD"):
        data, _age, fresh = C.load(spelling, TODAY, root=tmp_path)
        assert data["company"] == "Brindle and Hart Logistics Ltd" and fresh, spelling


def test_a_save_updates_the_hand_named_file_rather_than_starting_a_second(tmp_path):
    _write(tmp_path, "brindle-and-hart-logistics-ltd.json",
           {"company": "Brindle and Hart Logistics Ltd", "fetched_date": _days_ago(1)})
    written = C.save("Brindle & Hart Logistics", {"team_context": "A twelve-person planning team"},
                     root=tmp_path)
    assert os.path.basename(written) == "brindle-and-hart-logistics-ltd.json"
    assert sorted(os.listdir(tmp_path / C.DIR)) == ["brindle-and-hart-logistics-ltd.json"]


def test_an_employer_that_keys_to_nothing_reads_nothing(tmp_path):
    _write(tmp_path, "oakmere-foods.json", {"company": "Oakmere Foods"})
    assert C.load("", TODAY, root=tmp_path) == ({}, None, False)
    with pytest.raises(ValueError):
        C.save("", {"facts": []}, root=tmp_path)


def test_the_cli_says_where_the_file_is_and_whether_it_is_fresh(tmp_path, capsys):
    _write(tmp_path, "oakmere-foods.json", {"company": "Oakmere Foods", "fetched_date": _days_ago(40)})
    C.main(["Oakmere Foods", "--today", TODAY.isoformat(), "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert "company_research/oakmere-foods.json" in out and "40 days" in out and "stale" in out
    findings = tmp_path / "findings.json"
    findings.write_text(json.dumps({"fetched_date": TODAY.isoformat(), "facts": [FACT]}),
                        encoding="utf-8")
    C.main(["Oakmere Foods", "--save", str(findings), "--root", str(tmp_path)])
    assert C.load("Oakmere Foods", TODAY, root=tmp_path)[2] is True


# ------------------------------------------------------------------ the readers use it

def test_prep_reads_the_file_the_module_finds(tmp_path):
    _write(tmp_path, "brindle-and-hart-logistics-ltd.json",
           {"company": "Brindle and Hart Logistics Ltd", "fetched_date": _days_ago(1)})
    got = prep.load_research("Brindle & Hart Logistics", str(tmp_path))
    # The same data, and the file it came from, which a fact read from it is cited by.
    assert got.pop("_cache_file") == "company_research/brindle-and-hart-logistics-ltd.json"
    assert got == C.load("Brindle & Hart Logistics", root=tmp_path)[0]
    assert prep._research_source(dict(got, _cache_file="company_research/x--gb.json")) \
        .startswith("company_research/x--gb.json, fetched ")
    assert prep.RESEARCH_FRESH_DAYS == C.RESEARCH_FRESH_DAYS


def test_prep_flags_stale_research_by_its_own_date(tmp_path):
    contact = {"name": "Juno Castellan", "company": "Oakmere Foods"}
    research = {"company": "Oakmere Foods", "facts": [FACT],
                "fetched_date": _days_ago(C.RESEARCH_FRESH_DAYS + 5)}
    stale = prep.prep_markdown(contact, research, today=TODAY.isoformat())
    assert "Researched %d days ago" % (C.RESEARCH_FRESH_DAYS + 5) in stale
    research["fetched_date"] = _days_ago(C.RESEARCH_FRESH_DAYS)
    assert "Researched " not in prep.prep_markdown(contact, research, today=TODAY.isoformat())


def test_prep_still_reads_the_older_shapes(tmp_path):
    # The workflow once wrote `team`; hand-written files write `source_url`.
    contact = {"name": "Juno Castellan", "company": "Oakmere Foods"}
    research = {"company": "Oakmere Foods", "fetched_date": _days_ago(2),
                "team": "Demand planning sits inside the supply chain group",
                "facts": [{"claim": FACT["claim"], "source_url": FACT["url"]}]}
    text = prep.prep_markdown(contact, research, today=TODAY.isoformat())
    assert "Demand planning sits inside the supply chain group" in text
    assert "%s (source: %s)" % (FACT["claim"], FACT["url"]) in text


def test_the_presence_record_goes_through_the_module_and_keeps_its_own_clock(tmp_path):
    _write(tmp_path, "saltmarsh-analytics.json",
           {"company": "Saltmarsh Analytics", "fetched_date": _days_ago(80), "facts": [FACT]})
    assert D.record_presence("Saltmarsh Analytics", "no_results", TODAY, root=tmp_path) is None
    D.record_presence("Saltmarsh Analytics Limited", "no_relevant_presence", TODAY, root=tmp_path)
    data, age, fresh = C.load("Saltmarsh Analytics", TODAY, root=tmp_path)
    assert data["facts"] == [FACT] and (age, fresh) == (80, False)
    assert D.PRESENCE_REVIEW_DAYS == C.PRESENCE_REVIEW_DAYS
    # Stale research beside it does not make the finding stale.
    assert D.presence_ruled_out("Saltmarsh Analytics", TODAY, root=tmp_path)
    later = TODAY + dt.timedelta(days=C.PRESENCE_REVIEW_DAYS)
    assert not D.presence_ruled_out("Saltmarsh Analytics", later, root=tmp_path)
    assert not D.presence_ruled_out("Oakmere Foods", TODAY, root=tmp_path)


# ------------------------------------------------------------------ the prose points at it

PROSE = (".claude/agents/employer-researcher.md", ".claude/commands/apply.md",
         ".claude/commands/interview.md", ".claude/workflows/draft-applications.js",
         ".claude/skills/job-application-assistant/04-job-evaluation.md",
         ".claude/skills/job-application-assistant/11-cost-model.md")


@pytest.mark.parametrize("rel", PROSE)
def test_no_reader_restates_the_freshness_number(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert not re.search(r"\b%d[- ]day|\b%d days" % (C.RESEARCH_FRESH_DAYS, C.RESEARCH_FRESH_DAYS),
                         text), rel


@pytest.mark.parametrize("rel", PROSE[:3] + PROSE[4:])
def test_every_reader_names_the_constant(rel):
    assert "RESEARCH_FRESH_DAYS" in (ROOT / rel).read_text(encoding="utf-8"), rel


def test_the_workflow_research_stage_follows_the_researcher_agent():
    text = (ROOT / ".claude" / "workflows" / "draft-applications.js").read_text(encoding="utf-8")
    assert ".claude/agents/employer-researcher.md" in text
    schema = text.split("const RESEARCH_SCHEMA", 1)[1].split("\n}\n", 1)[0]
    for field in ("team_context", "do_not_claim", "facts"):
        assert field in schema
    for old in ("team:", "cautions:"):
        assert old not in schema
