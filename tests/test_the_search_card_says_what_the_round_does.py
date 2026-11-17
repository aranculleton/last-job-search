"""The job-scraper skill is a short card that says what the round actually does.

A chat running a search read the skill, about 27KB and 7,000 tokens, and carried it for every
later call. Its first section described a pipeline the round does not run: every posting
ranked against the framework, a small-model knockout, full scoring one posting per agent and
adversarial verification over 70. `run_round.py` runs none of it: its stages are rule counts
and say "0 model tokens", and the order is fit times opportunity. A chat that read the skill
could describe the list as model-checked, or score it again with a model (issue 312).

Now the skill is the operator card (the command, the exit codes, the lines to pass on, where
to stop), it says plainly how the round scores, the reasons live in `rules.md` beside it, the
model-tiered path stays in `manual-round.md`, and `tools/cost_meter.py search` measures what a
search chat reads, as it does the brief.
"""
from __future__ import annotations

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import cost_meter  # noqa: E402

SKILL = os.path.join(ROOT, ".claude", "skills", "job-scraper")


def _said(name):
    with open(os.path.join(SKILL, name), encoding="utf-8") as fh:
        return " ".join(fh.read().split())


def test_the_card_says_the_round_scores_by_rule_and_sends_the_model_path_elsewhere():
    card = _said("SKILL.md")
    assert "How a round scores: by rule, with no model." in card
    assert "spends no model tokens" in card and "fit (`fit.py`" in card
    assert "never as model-scored or checked" in card
    assert "The model-tiered path is `manual-round.md`" in card
    for gone in ("adversarial verification", "small-model knockout",
                 "Full scoring is one posting per agent", "against `04-job-evaluation.md`, gates first"):
        assert gone not in card, gone
    # The reasons are kept, beside it, and say the same about the round.
    rules = _said("rules.md")
    assert "`tools/run_round.py` spends no model tokens" in rules
    assert "Rank down, do not cut." in rules and "do_not_target.json" in rules
    assert "`rules.md` beside this file" in card


def test_the_card_names_what_a_chat_passes_on_and_where_it_stops():
    card = _said("SKILL.md")
    for line in ("Exit codes.", "shortlist: found N of M asked for", "portal health: <site> DOWN",
                 "employer job sites not read:", "Tell the person, in these words",
                 "--recut --out <the round's folder> --show <N>", '--employers "A, B, C"',
                 "Which of these should I take forward? And have you already applied to any of "
                 "them?"):
        assert line in card, line


def test_a_search_chat_reads_a_fraction_of_what_it_did():
    state = cost_meter.scratch_state()
    try:
        got = cost_meter.measure(cost_meter.SEARCH, None, state)
    finally:
        shutil.rmtree(os.path.dirname(state), ignore_errors=True)
    skill = next(s for s in got["steps"] if s["step"] == "read the job-scraper skill")
    runbook = next(s for s in got["steps"] if s["step"].startswith("read RUNBOOK.md"))
    assert 0 < skill["tokens"] <= 2300            # was about 7,000
    assert runbook["tokens"] > 0                  # the section was found
    assert "search" in cost_meter.PROCEDURES
