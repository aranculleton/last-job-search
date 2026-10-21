"""What a drafting batch cost is recorded per posting and per stage, and kept.

The only measurement of the drafting path was a person reading the Workflow tool's run
summary by eye. The workflow now returns, for each posting, one cost record per stage (the
model, the prompt's size, the shared output counter's movement), and `tools/draft_cost.py`
joins it with whatever the run summary showed (tokens, tool calls, seconds), writes it
beside the batch and each application, and prints one line for the batch. What nobody
recorded is said to be missing, never guessed.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import draft_cost  # noqa: E402
import outreach  # noqa: E402
from test_one_drafting_call_per_posting import run_workflow  # noqa: E402


def test_the_workflow_returns_a_cost_record_for_every_stage_it_ran():
    got = run_workflow({"A": "clean", "B": "model"}, pack="P" * 400, pack_hash="h")
    cost = {r["pick"]["slug"]: r["cost"] for r in got["out"]}
    # Updated 2026-10-21: every draft that will be sent gets the model audit, so the clean
    # draft A has an audit stage too.
    assert [c["stage"] for c in cost["a"]] == ["research", "draft", "audit"]
    assert [c["stage"] for c in cost["b"]] == ["research", "draft", "audit"]
    draft = cost["a"][1]
    assert draft["static_prefix_chars"] == 400 and draft["prompt_chars"] > 400
    assert draft["approx_prompt_tokens"] == -(-draft["prompt_chars"] // 4)
    assert cost["a"][0]["model"] == "sonnet" and draft["model"].startswith("inherited")
    # The harness gives the script no budget counter: recorded as not available.
    assert draft["output_tokens_shared_counter"] is None


def test_the_batch_and_each_application_keep_it_and_one_line_says_the_total(tmp_path):
    got = run_workflow({"A": "clean", "B": "model"}, pack="P")
    for r in got["out"]:
        r["pick"]["company"], r["pick"]["role"] = {"a": ("Kestrel Mutual", "Analyst"),
                                                   "b": ("Fernhill Freight", "Planner")}[r["pick"]["slug"]]
    folder = outreach.app_folder("Kestrel Mutual", "Analyst", "")
    os.makedirs(folder, exist_ok=True)
    # Labels by company, as runs before 2026-10-21 wrote them, and by slug, as they do now.
    usage = [{"label": "research:Kestrel Mutual", "tokens": 1000, "tool_calls": 3, "seconds": 20},
             {"label": "draft:Kestrel Mutual", "tokens": 9000, "tool_calls": 4, "seconds": 70},
             {"label": "audit:a", "tokens": 2000, "tool_calls": 2, "seconds": 30}]
    path, kept, line = draft_cost.write(str(tmp_path), got["out"], usage)
    batch = json.load(open(path, encoding="utf-8"))
    a = batch["postings"]["a"]
    assert a["totals"]["tokens"] == 12000 and a["totals"]["tool_calls"] == 9
    assert a["totals"]["seconds"] == 120
    # Fernhill's figures were never copied in: not available, not zero.
    assert batch["postings"]["b"]["totals"]["tokens"] is None
    assert kept == [os.path.relpath(os.path.join(folder, "cost.json"),
                                    os.environ["LJS_STATE"])]
    assert json.load(open(os.path.join(folder, "cost.json")))["slug"] == "a"
    assert line.startswith("batch: 2 posting(s), 6 agent call(s), 2 model audit(s)")
    assert "tokens not available" in line
