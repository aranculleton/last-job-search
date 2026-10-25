"""What a letter's sentence cites is held to what that evidence says, by code.

Two holes let an invented claim through the code audit with nothing for the model to read:

- **Citing POSTING switched the employer-fact and number checks off for the sentence.**
  "Kestrel Mutual is the largest home insurer in the north of England, and its claims team
  is doubling this year", cited POSTING, was clean; so was the posting's "12 operations
  managers" put on the candidate's own reporting work, cited with a candidate fact and
  POSTING. A POSTING sentence may say the posting back; an employer fact needs research and
  a figure about the candidate needs a candidate fact that holds it.
- **The research a letter cites was never checked by code.** research_<slug>.json is
  written by the research agent and never went through company_research's quote check; the
  audit took numbers from the researcher's own `claim` as well as the quote; a one-word
  quote passed the substring check and was stamped `quote_checked`; and a search summary
  marked `read: false` was cited like any fact.
- **A lone surrogate stopped the audit of the whole batch.** A quote holding half an emoji
  ("\\ud83d", as a page cut short leaves it) raised UnicodeEncodeError in the research hash,
  the draft's md5 and the audit record, so no pick in the round was audited.

Every employer, posting and figure here is invented.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import company_research  # noqa: E402
import draft_audit  # noqa: E402
import draft_pack  # noqa: E402
from test_one_drafting_call_per_posting import FIXTURE, SLUG, WORKFLOW, make_round, store_pages  # noqa: E402,E501

GOOD = FIXTURE["draft"]
PICK = {"company": FIXTURE["company"], "role": FIXTURE["role"], "slug": FIXTURE["slug"],
        "abbr": FIXTURE["abbr"], "ask_first": ["SAP"], "skills_no": ["SAP"], "skills_yes": []}
P2_SECOND = ("A bad week for the weather turns that number into a staffing question, and "
             "staffing to a forecast is the problem my models answer for stock and vans.")
F1_SENTENCE = "Kestrel Mutual looks after 1.2 million policyholders across home and motor."


def _edited(field, old, new, cites=None, d=None):
    d = copy.deepcopy(d or GOOD)
    if field.startswith("cl_bullets"):
        i = int(field[len("cl_bullets["):-1])
        d["cl_bullets"][i]["text"] = d["cl_bullets"][i]["text"].replace(old, new)
    else:
        assert old in d[field]
        d[field] = d[field].replace(old, new)
    for c in d["claim_map"]:
        if c["field"] == field and old in c["sentence"]:
            c["sentence"] = c["sentence"].replace(old, new)
            if cites is not None:
                c["cites"] = cites
    return d


def _audit(d, research=None, posting=None):
    store_pages()
    return draft_audit.mechanical(dict(d, pack_hash=draft_pack.rules_hash()), PICK,
                                  FIXTURE["posting"] if posting is None else posting,
                                  FIXTURE["research"] if research is None else research,
                                  corpus={"openings": set(), "closings": set()})


def _flags(m):
    return {f["flag"] for f in m["flags"]}


def _rules(m):
    return {f["rule"] for f in m["findings"]}


# ------------------------------------------------------------------ POSTING citations

def test_an_employer_fact_cited_to_the_posting_is_held_back():
    d = _edited("p2", P2_SECOND, "Kestrel Mutual is the largest home insurer in the north of "
                "England, and its claims team is doubling this year.", cites=["POSTING"])
    m = _audit(d)
    assert m["gate"] == "model"
    assert "possible-employer-fact" in _flags(m)
    # "doubling" is a figure (2x) the posting never states.
    assert any(f["flag"] == "number-not-in-cited" and "2 x" in f["detail"] for f in m["flags"])


def test_a_sentence_that_says_the_posting_back_still_passes():
    m = _audit(GOOD)
    assert m["gate"] == "clean", (m["findings"], m["flags"])
    d = _edited("p1", "Your claims handling teams staff ahead of demand, so the weekly forecast "
                "is the plan they work to.", "Kestrel Mutual is hiring a Claims Forecasting "
                "Analyst so its claims handling teams can staff ahead of demand.")
    assert _audit(d)["gate"] == "clean"


@pytest.mark.parametrize("cites", [["BH_REPORT"], ["BH_REPORT", "POSTING"]])
def test_a_posting_figure_moved_onto_the_candidates_work_is_held_back_however_it_is_cited(cites):
    posting = FIXTURE["posting"] + "\nThe reporting covers 12 regional operations managers."
    d = _edited("cl_bullets[2]", "replaced eleven spreadsheets for more than 30 operations "
                "managers", "replaced eleven spreadsheets for 12 operations managers", cites=cites)
    m = _audit(d, posting=posting)
    assert any(f["flag"] == "number-not-in-cited" and f["field"] == "cl_bullets[2]"
               for f in m["flags"]), m["flags"]


# ------------------------------------------------------------------ research quotes

def _research(**fact):
    r = copy.deepcopy(FIXTURE["research"])
    r["facts"][0].update(fact)
    return r


def _with_hash(d, research):
    return dict(d, research_hash=draft_audit.research_hash(research))


def test_a_figure_only_the_researchers_claim_holds_is_not_evidence():
    # The quote says 1.2 million; the researcher's claim says 1.9 million.
    r = _research(claim="Kestrel Mutual looks after 1.9 million policyholders across home and motor")
    d = _with_hash(_edited("p2", "1.2 million", "1.9 million"), r)
    m = _audit(d, research=r)
    assert any(f["flag"] == "number-not-in-cited" and "1.9e+06" in f["detail"]
               for f in m["flags"]), m["flags"]


def test_a_quote_not_on_its_page_or_too_short_or_never_read_cannot_be_cited():
    store_pages()
    url = "https://www.kestrelmutual.example/news"
    company_research._store_page(url, "News", "We opened a claims centre in Leeds this year.", "page")
    cases = {
        "not-on-page": _research(url=url),
        "short": _research(claim="Kestrel Mutual grew its claims operation by 40% in 2026",
                           quote="claims"),
        "unread": _research(read=False),
        "unchecked": _research(url="https://www.kestrelmutual.example/never-fetched"),
    }
    for state, r in cases.items():
        m = _audit(_with_hash(GOOD, r), research=r)
        assert f"research:{state}" in _rules(m), (state, m["findings"])
    # The fixture's own fact, its quote on its kept page, is checked and may be cited.
    assert not [f for f in _audit(GOOD)["findings"] if f["rule"].startswith("research")]


def test_a_fact_the_cache_checked_when_it_was_saved_may_be_cited_after_its_page_is_gone(
        tmp_path, monkeypatch):
    # A later session: the pages tools/company_research.py fetch kept are gone with the
    # container, and the cache holds the fact stamped quote_checked when it was saved.
    monkeypatch.setenv("LJS_STATE", str(tmp_path / "state"))
    pages = tmp_path / "pages"
    url = "https://www.kestrelmutual.example/annual-review"
    quote = FIXTURE["research"]["facts"][0]["quote"]
    company_research._store_page(url, "Review", "Annual review. " + quote + ".", "page", str(pages))
    company_research.save(FIXTURE["company"], {"facts": [
        {"claim": "Looks after 1.2 million policyholders", "quote": quote, "url": url}]},
        pages=str(pages))
    r = _research(url=url)
    assert draft_audit.research_status(r, FIXTURE["company"])["F1"][0] == "checked"
    assert draft_audit.research_status(r, "Fernhill Freight")["F1"][0] == "unchecked"


def test_save_refuses_a_quote_too_short_to_mean_anything(tmp_path):
    pages = tmp_path / "pages"
    url = "https://www.kestrelmutual.example/about"
    company_research._store_page(url, "About", "Our claims team handles 9,000 claims a week.",
                                 "page", str(pages))
    with pytest.raises(company_research.QuoteNotFound, match="under 6 words"):
        company_research.save("Kestrel Mutual", {"facts": [
            {"claim": "Handles 9,000 claims a week", "quote": "claims", "url": url}]},
            root=str(tmp_path), pages=str(pages))
    path = company_research.save("Kestrel Mutual", {"facts": [
        {"claim": "Handles 9,000 claims a week",
         "quote": "Our claims team handles 9,000 claims a week.", "url": url}]},
        root=str(tmp_path), pages=str(pages))
    assert json.load(open(path, encoding="utf-8"))["facts"][0]["quote_checked"]


def test_a_draft_written_against_other_research_is_refused():
    other = _research(claim="Kestrel Mutual insures farms",
                      quote="we insure farms across the north of England and Wales")
    d = dict(GOOD, research_hash=draft_audit.research_hash(other))
    assert "research-mismatch" in _rules(_audit(d))
    # A draft that names no hash is a question for the model auditor, not a pass.
    d = {k: v for k, v in GOOD.items() if k != "research_hash"}
    assert "no-research-hash" in _flags(_audit(d))


def test_the_workflow_hashes_the_research_the_way_the_audit_does():
    node = subprocess.run(["node", "--version"], capture_output=True) if shutil.which("node") \
        else subprocess.CompletedProcess(["node"], 127)
    if node.returncode != 0:
        pytest.skip("node is not installed")
    probe = ("const src = require('fs').readFileSync(process.argv[1], 'utf8')"
             ".replace(/^export const meta/m, 'const meta');"
             "const body = src.split('// ------------------------------------------------------------------ research')[0];"
             "const f = new Function('args', body + '; return {researchHash, factLines};');"
             "const r = f({today: 'd', round_dir: '/r', picks: []});"
             "const res = JSON.parse(process.argv[2]);"
             "console.log(JSON.stringify([r.researchHash(res), r.factLines(res)]))")
    research = {"facts": [{"claim": "Café “opened”", "quote": "a quote \U0001F600",
                           "url": "u", "caution": "old", "read": False},
                          {"claim": None, "quote": "q"}, "not a fact"]}
    for r in (FIXTURE["research"], research, _HALF_AN_EMOJI):
        got = json.loads(subprocess.run(["node", "-e", probe, WORKFLOW, json.dumps(r)],
                                        capture_output=True, text=True, check=True).stdout)
        assert got == [draft_audit.research_hash(r), draft_pack.research_lines(r)]
    # A search summary is marked for the drafter in both copies of the lines.
    assert "NOT READ ON THE PAGE" in draft_pack.research_lines(research)


_HALF_AN_EMOJI = {"facts": [{"claim": "Kestrel Mutual looks after homes \ud83d",
                             "quote": "We look after 1.2 million homes across the north \ud83d",
                             "url": "https://kestrel.example/about\ud83d"},
                            {"claim": "A second fact", "quote": "a whole emoji \U0001F3E0 here"}]}


def _fnv_over_code_units(text):
    # UTF-16 code units, worked out by hand: a character past U+FFFF is two, anything else
    # (a lone surrogate included) is one, as JavaScript's charCodeAt reads them.
    h = 0x811C9DC5
    for ch in text:
        n = ord(ch)
        units = [0xD800 + ((n - 0x10000) >> 10), 0xDC00 + ((n - 0x10000) & 0x3FF)] \
            if n > 0xFFFF else [n]
        for u in units:
            h ^= u
            h = (h * 0x01000193) & 0xFFFFFFFF
    return "%08x" % h


def test_half_an_emoji_is_hashed_like_any_other_code_unit():
    want = _fnv_over_code_units(draft_pack.research_lines(_HALF_AN_EMOJI))
    assert draft_audit.research_hash(_HALF_AN_EMOJI) == want
    assert draft_audit.research_hash(FIXTURE["research"]) == \
        _fnv_over_code_units(draft_pack.research_lines(FIXTURE["research"]))
    # Valid text keeps the md5 it always had; a lone surrogate gets one too.
    plain = {"p4": "Café, naïve, Zoë \U0001F600"}
    import hashlib
    assert draft_audit.md5(plain) == hashlib.md5(json.dumps(
        plain, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    assert draft_audit.md5({"p4": "x \ud83d"}) != draft_audit.md5({"p4": "x \ud83e"})


def test_half_an_emoji_never_stops_the_batch_audit(tmp_path, monkeypatch, capsys):
    import stage_picks
    d = copy.deepcopy(GOOD)
    d["p4"] = d["p4"] + " \ud83d"
    rd = make_round(tmp_path, draft=d, slugs=(SLUG, SLUG + "_2"))
    res = copy.deepcopy(FIXTURE["research"])
    res["facts"][0]["quote"] += " \ud83d"
    (rd / f"research_{SLUG}.json").write_text(json.dumps(res), encoding="utf-8")
    results = stage_picks.audit(str(rd))
    assert [r["slug"] for r in results] == [SLUG, SLUG + "_2"]
    assert all(r["verdict"] in ("needs_model", "pass", "fixed", "reject") for r in results)
    record = json.loads((rd / f"audit_{SLUG}.json").read_text(encoding="utf-8"))
    assert record["draft"]["p4"].endswith("\ud83d")
    # And the drafter's --json view prints.
    monkeypatch.setattr(sys, "argv", ["stage_picks.py", "audit", str(rd), "--json"])
    stage_picks.main()
    assert json.loads(capsys.readouterr().out)[0]["slug"] == SLUG
