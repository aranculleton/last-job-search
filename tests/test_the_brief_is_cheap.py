"""The scheduled brief reads little and calls the model few times, with nothing lost.

A brief run cost 1.5M to 2.5M tokens (the cost audit of 2026-10-25): two prompt files of
14,000 characters, then some thirty calls, each re-reading the whole chat, most of them to
read state files the code could have read. Code gathers it now (tools/brief.py), a small
agent finds the news, and the prompt says what is left. These keep it that way, and keep
every promise the brief made.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import cost_meter  # noqa: E402

PROMPTS = os.path.join(ROOT, "automation", "prompts")


def _read(name):
    with open(os.path.join(PROMPTS, name), encoding="utf-8") as fh:
        return fh.read()


def test_the_prompt_files_a_brief_reads_stay_small():
    assert len(_read("morning_brief.md")) <= 4500
    assert len(_read("_common.md")) <= 5600


def test_the_brief_is_gathered_by_code_and_the_news_by_the_small_agent():
    brief = _read("morning_brief.md")
    for must in ("python3 tools/brief.py --start", "--write", "news-reader",
                 "python3 tools/brief.py news", "followup_drafts.py context --due",
                 "followup_drafts.py check - --pack", "Never run a search here",
                 "silence is the alarm"):
        assert must in brief, must
    # The model reads no state file, pack or earlier brief itself.
    for never in ("network_threads.csv", "open_actions.py", "followup_pack_", "documents/briefs/*"):
        assert never not in brief, never


def test_every_promise_of_the_brief_is_still_made():
    common, brief = _read("_common.md"), _read("morning_brief.md")
    assert "Always deliver" in common and "Your final reply is the message" in common
    assert "sync_app.py --if-stale" in common and "/upgrade 20" in common and "/upgrade 20" in brief
    assert "An update is waiting" in common and "once" in common
    assert "Each run stands alone" in common             # a chat bound to the task as a fresh one
    assert "at most three" in brief                       # the questions, at the end


def test_the_meter_counts_fewer_calls_and_fewer_tokens_after(tmp_path):
    assert len(cost_meter.AFTER) < len(cost_meter.BEFORE) / 2
    state = cost_meter.scratch_state()
    try:
        before = cost_meter.measure(cost_meter.BEFORE, None, state)
        after = cost_meter.measure(cost_meter.AFTER, None, state)
    finally:
        import shutil
        shutil.rmtree(os.path.dirname(state), ignore_errors=True)
    assert after["calls"] < before["calls"]
    assert after["processed_tokens"] < 0.5 * before["processed_tokens"]
    text = cost_meter.report(before, after, "the working tree")
    assert "ESTIMATED tokens (characters / 4; no tokenizer)" in text
    assert cost_meter.tokens(5) == 2 and cost_meter.tokens(0) == 0
