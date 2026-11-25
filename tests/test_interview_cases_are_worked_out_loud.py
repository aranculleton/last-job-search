"""Practice cases for a case round, and the mock interview that uses them (issue 367).

A prep that said "expect a case" left the person to find one. Each case here is worked out
loud: a prompt said as the interviewer says it, five to eight steps with the sums in them,
the numbers to land, and a sketch narrow enough for a phone. The /interview instructions
play the named interviewer, dig three deep, praise nothing mid-mock and end on a scorecard
whose marks the next round's pack reads.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools")]

import interview_cases as C  # noqa: E402

TOOL = os.path.join(ROOT, "tools", "interview_cases.py")
COMMAND = os.path.join(ROOT, ".claude", "commands", "interview.md")


def _all():
    return [c for k in C.kinds() for c in C.cases_for(k)]


def test_every_case_has_every_key_and_nothing_else():
    assert _all()
    for c in _all():
        assert set(c) == set(C.KEYS) == {"id", "title", "type", "prompt", "steps", "numbers",
                                         "visual"}, c["id"]
        assert all(isinstance(c[k], str) and c[k].strip() for k in
                   ("id", "title", "type", "prompt", "visual")), c["id"]
        assert c["numbers"] and all(isinstance(n, str) and n for n in c["numbers"]), c["id"]


def test_every_case_is_worked_in_five_to_eight_steps_with_numbers_in_them():
    for c in C.CASES:
        assert 5 <= len(c["steps"]) <= 8, (c["id"], len(c["steps"]))
        with_sums = [s for s in c["steps"] if any(ch.isdigit() for ch in s)]
        assert len(with_sums) >= 3, c["id"]


def test_every_sketch_fits_a_phone():
    for c in C.CASES:
        lines = c["visual"].splitlines()
        assert len(lines) >= 3, c["id"]
        assert max(len(line) for line in lines) <= C.WIDTH == 40, c["id"]
        assert c["visual"].isascii(), c["id"]
        assert "\t" not in c["visual"], c["id"]


def test_the_ids_are_unique_and_no_text_carries_a_long_dash():
    ids = [c["id"] for c in C.CASES]
    assert len(ids) == len(set(ids))
    for c in C.CASES:
        text = " ".join([c["title"], c["prompt"], c["visual"]] + c["steps"] + c["numbers"])
        assert "—" not in text and "–" not in text, c["id"]


def test_the_named_operations_cases_are_there():
    ops = {c["id"]: c for c in C.cases_for("operations")}
    for want in ("ops-bottleneck", "ops-capacity", "ops-utilisation", "ops-backlog"):
        assert want in ops
    titles = " ".join(c["title"].lower() for c in ops.values())
    for word in ("bottleneck", "capacity", "utilisation", "backlog"):
        assert word in titles


def test_analytics_and_general_cases_are_there():
    ids = {c["id"] for c in C.cases_for("analytics")}
    assert {"data-metric-drop", "data-ab-readout", "data-forecast-error"} <= ids
    general = {c["id"] for c in C.cases_for("general")}
    assert {"gen-market-sizing", "gen-prioritisation"} <= general
    assert "general" in C.kinds() and C.kinds()[-1] == "general"


def test_a_kind_is_matched_loosely_from_any_words_for_it():
    assert C.kind_of("Operations") == "operations"
    assert C.kind_of("a logistics and supply chain company") == "operations"
    assert C.kind_of("technology company") == "analytics"
    assert C.kind_of("software product") == "analytics"
    assert C.kind_of("bank") == "finance"
    assert C.kind_of("a fintech start-up") == "finance"
    assert C.kind_of("professional services") == "consulting"
    assert C.kind_of("public sector") == "operations"
    first = C.cases_for("a logistics company")[0]
    assert first["type"] == "operations"


def test_words_it_cannot_place_fall_back_to_the_general_cases():
    for said in ("", None, "zzz", "a place that makes hats"):
        got = C.cases_for(said)
        assert got and {c["type"] for c in got} == {"general"}


def test_every_kind_ends_with_the_general_cases_each_once():
    for k in C.kinds():
        ids = [c["id"] for c in C.cases_for(k)]
        assert len(ids) == len(set(ids)), k
        assert ids[-len(C.GENERAL):] == list(C.GENERAL) or k == "consulting", k
        assert set(C.GENERAL) <= set(ids), k


def test_a_case_handed_out_is_a_copy():
    c = C.cases_for("operations")[0]
    c["steps"].append("changed")
    assert "changed" not in C.cases_for("operations")[0]["steps"]


def _run(*args):
    return subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True,
                          timeout=60)


def test_the_command_lists_shows_and_picks_by_kind():
    listed = _run("list")
    assert listed.returncode == 0
    assert all(c["id"] in listed.stdout for c in C.CASES)
    shown = _run("show", "ops-bottleneck")
    assert shown.returncode == 0
    assert "They say:" in shown.stdout and "Out loud:" in shown.stdout
    assert "Pack     135" in shown.stdout
    picked = _run("for", "supply", "chain")
    assert picked.returncode == 0 and "(operations)" in picked.stdout
    assert "ops-backlog" in picked.stdout
    missing = _run("show", "no-such-case")
    assert missing.returncode == 1 and "list" in missing.stderr
    assert _run().returncode == 2


def _command() -> str:
    with open(COMMAND, encoding="utf-8") as f:
        return " ".join(f.read().split())


def test_the_mock_plays_the_named_interviewer_three_deep_with_no_praise():
    text = _command()
    assert "### Mock interview as a named interviewer" in text
    assert "Dig at least three follow-ups deep on every technical answer" in text
    assert "**One question at a time.**" in text
    assert "**No praise during the mock.**" in text
    assert "python3 tools/interview_cases.py for" in text


def test_the_mock_ends_on_a_scorecard_whose_marks_are_kept():
    text = _command()
    assert "end with **the scorecard**" in text
    assert "got it / shaky / missed" in text
    assert "Practise next:" in text
    assert "python3 tools/interview_pack.py asked --company" in text
    assert "--landed yes|partly|no" in text


def test_timed_practice_is_ninety_seconds_and_records_nothing():
    text = _command()
    assert "### Timed spoken practice" in text
    assert "**90 seconds per answer**" in text
    assert "python3 tools/learned.py brief voice" in text
    assert "The app never records or transcribes anything." in text
