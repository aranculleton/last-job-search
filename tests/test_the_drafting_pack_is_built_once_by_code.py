"""The drafting pack: what every drafter read for itself, built once by code.

Each drafter in the `draft-applications` workflow read the same static files before writing
a word (the profile, the writing guides, the positioning brief, the bridges, the field
contract, the renderer and two letters), then carried them through forty-odd tool calls.
`tools/draft_pack.py` compiles what a draft needs into one file: the same bytes for every
posting in a batch, so it is the prompt-cache prefix, with every fact under an id a claim
can cite, the person's rules ahead of the app's, and a rebuild whenever an input changes.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import bullet_library  # noqa: E402
import draft_pack  # noqa: E402
import untrusted  # noqa: E402

FIXTURE = json.load(open(os.path.join(ROOT, "tests", "fixtures", "drafting_round.json"),
                         encoding="utf-8"))


def _round(base):
    rd = base / "r1"
    (rd / "picks").mkdir(parents=True)
    f = rd / "picks" / "01_kestrel_mutual.md"
    f.write_text(f"# {FIXTURE['company']} | {FIXTURE['role']}\n\n"
                 + untrusted.fence(FIXTURE["posting"]) + "\n", encoding="utf-8")
    (rd / "picks.json").write_text(json.dumps([{
        "file": str(f), "company": FIXTURE["company"], "role": FIXTURE["role"],
        "slug": FIXTURE["slug"], "abbr": FIXTURE["abbr"], "ask_first": ["SAP"],
        "skills_no": ["SAP"]}]), encoding="utf-8")
    return rd


def test_the_static_part_is_the_same_bytes_for_every_posting_and_every_build(tmp_path):
    a, b = _round(tmp_path / "a"), _round(tmp_path / "b")
    draft_pack.build(str(a), today="2026-10-21")
    draft_pack.build(str(b))
    pack_a = (a / "pack.md").read_bytes()
    assert pack_a == (b / "pack.md").read_bytes()
    # Nothing particular to a posting is in it, so it can be every prompt's first bytes.
    assert FIXTURE["posting"].splitlines()[0] not in pack_a.decode("utf-8")
    args = json.loads((a / "draft_args.json").read_text(encoding="utf-8"))
    assert args["pack"].encode("utf-8") == pack_a and args["today"] == "2026-10-21"
    assert args["pack_hash"] == draft_pack.rules_hash()
    brief = args["picks"][0]["brief"]
    assert "BEGIN-UNTRUSTED" in brief and FIXTURE["posting"].splitlines()[0] in brief
    # The person's answers and what the profile holds for this posting's asks travel with it.
    assert "No (never named anywhere): SAP" in brief
    assert "- SAP: bridge, have SQL over the warehouse-management system." in brief


def test_every_fact_the_profile_holds_is_in_the_pack_under_an_id_a_claim_can_cite():
    ev = draft_pack.evidence()
    text = draft_pack.static_pack()
    # Every resume bullet id, the ids committed drafts already name.
    assert set(bullet_library.TEXT) <= set(ev)
    for f in draft_pack.facts():
        # Each piece of work is printed once, under the first id of its group, and every
        # id in the group stands for the whole group's words.
        printed = [x for x in draft_pack.facts() if x.get("group", x["id"]) == f.get("group", f["id"])]
        assert any(re.search(r"(?<![\w.])" + re.escape(x["id"]) + r"\b", text)
                   for x in printed), f["id"]
        assert f["text"] in ev[f["id"]]
    for special in ("LOC", "AUTH", "SKILLS"):
        assert ev[special]
    assert "LOC: Manchester, UK" in text and "No sponsorship required" in text
    assert "CERT." in text and "EDU." in text and "SUMMARY" in text
    # A role that has ended is marked for the tense check, the current one is not.
    assert "Oakmere Foods | Sep 2020 - Feb 2023 | ended: past tense" in text
    assert "Brindle & Hart Logistics | Mar 2023 - Present | current" in text


def _profile_copy(tmp_path, monkeypatch):
    dst = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), dst)
    monkeypatch.setenv("LJS_PROFILE", str(dst))
    return dst


def test_additional_detail_and_reserve_experience_get_ids_and_reserve_is_marked(tmp_path, monkeypatch):
    dst = _profile_copy(tmp_path, monkeypatch)
    md = dst / "01-candidate-profile.md"
    text = md.read_text(encoding="utf-8")
    text = text.replace(
        "- Owned the Power BI service-level reporting used by 30+ operations managers, replacing eleven spreadsheets\n",
        "- Owned the Power BI service-level reporting used by 30+ operations managers, replacing eleven spreadsheets\n"
        "\n**Additional detail available for tailoring:**\n"
        "- Trained four shift planners to read the weekly forecast and its error bands\n")
    text = text.replace("## Education", "## Reserve Experience (opt-in per role)\n\n"
                        "### Volunteer Analyst - Ellerwick Trust (Jan 2018 - Jun 2019)\n"
                        "- Counted towpath footfall for a lottery bid\n\n## Education")
    md.write_text(text, encoding="utf-8")
    facts = {f["text"]: f for f in draft_pack.facts()}
    detail = facts["Trained four shift planners to read the weekly forecast and its error bands"]
    reserve = facts["Counted towpath footfall for a lottery bid"]
    assert detail["kind"] == "detail" and detail["id"].startswith("BH.")
    assert reserve["kind"] == "reserve" and reserve["id"].startswith("RSV.")
    pack = draft_pack.static_pack()
    assert f" {detail['id']} (detail): Trained four shift planners" in pack
    assert "RESERVE (opt-in: say why in stretches) Volunteer Analyst" in pack


def test_the_pack_follows_what_the_person_taught_it_and_says_when_it_is_out_of_date(tmp_path, monkeypatch):
    dst = _profile_copy(tmp_path, monkeypatch)
    rd = _round(tmp_path)
    draft_pack.build(str(rd))
    before, pack = draft_pack.rules_hash(), draft_pack.static_pack()
    assert draft_pack.current(str(rd))
    (dst / "learned.json").write_text(json.dumps({"entries": [{
        "date": "2026-10-20", "area": "documents", "said": "no questions up top",
        "rule": "Never open a letter on a question.", "applied_to": [],
        "never_say": ["game plan"], "status": "active"}]}), encoding="utf-8")
    assert draft_pack.rules_hash() != before
    assert not draft_pack.current(str(rd))
    after = draft_pack.static_pack()
    assert "Never open a letter on a question." not in pack
    assert "- Never open a letter on a question." in after
    assert '"game plan"' in after
    # The person's rules come before the app's.
    assert after.index("The person's") < after.index("The app's")


def test_the_pack_is_under_its_target_for_the_example_person():
    size = draft_pack.approx_tokens(draft_pack.static_pack())
    assert size["by_chars"] < draft_pack.TARGET_TOKENS
    assert size["by_words"] < draft_pack.TARGET_TOKENS


def test_the_worked_example_is_cut_from_a_draft_that_passes_the_audit():
    # The example teaches the claim map's shape, so it must be one the audit accepts.
    shown = [c for c in draft_pack.EXAMPLE["claim_map"] if isinstance(c, dict)]
    full = FIXTURE["draft"]["claim_map"]
    for c in shown:
        assert c in full, c["sentence"]
    assert draft_pack.EXAMPLE["summary"] == FIXTURE["draft"]["summary"]
    assert draft_pack.EXAMPLE["p1"] == FIXTURE["draft"]["p1"]
