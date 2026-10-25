#!/usr/bin/env python3
"""What one drafting batch cost, per posting and per stage, written where it is kept.

The `draft-applications` workflow records what a script can see: each stage's model, the
size of its prompt, and the output tokens the shared budget counter moved by. It cannot
see the clock, an agent's tool calls or its input tokens; the Workflow tool's own run
summary shows those for every agent, by label (`research:<slug>`, `draft:<slug>`,
`audit:<slug>`, `outreach:<slug>`, the pick's slug, so two roles at one employer are two
labels). This joins the two:

    python3 tools/draft_cost.py <round_dir> --result <the workflow's return value, saved as JSON>
                                            [--usage <usage.json>]

`usage.json` is a list of {"label", "tokens", "tool_calls", "seconds"} copied from the run
summary; any field it lacks is recorded as not available, never guessed. Written:
`<round_dir>/cost.json` for the batch, and `cost.json` beside each application in
`documents/applications/<folder>/` whose folder exists (RUNBOOK step 3 makes it). The last
line printed is the batch total.

Token counts from a prompt's size are characters / 4: an approximation, said as one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402
import local_path  # noqa: E402

STAGES = ("research", "draft", "audit", "outreach")
# What the workflow cannot record, and where it comes from instead.
NOT_IN_SCRIPT = ("seconds", "tool_calls", "tokens")


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _usage_by_label(usage) -> dict:
    out = {}
    for row in usage or []:
        if isinstance(row, dict) and row.get("label"):
            out[str(row["label"])] = row
    return out


def per_posting(result, usage=None) -> dict:
    """{slug: {"company", "role", "stages": [...], "totals": {...}}} for the batch."""
    by_label = _usage_by_label(usage)
    out = {}
    # The workflow labels each agent by the pick's slug ("draft:kestrel_mutual_2"). Runs
    # before that labelled it by the company, which two roles at one employer share: such
    # a label is read only for a company with one posting in the batch, never for two.
    companies = [((item or {}).get("pick") or {}).get("company") for item in result or []]
    for item in result or []:
        pick = (item or {}).get("pick") or {}
        slug = pick.get("slug")
        if not slug:
            continue
        stages = []
        for c in item.get("cost") or []:
            row = dict(c)
            got = by_label.get(f"{c.get('stage')}:{slug}")
            if got is None and companies.count(pick.get("company")) == 1:
                got = by_label.get(f"{c.get('stage')}:{pick.get('company')}")
            got = got or {}
            for k in NOT_IN_SCRIPT:
                row[k] = got.get(k) if got.get(k) is not None else None
            stages.append(row)
        totals = {"calls": sum(int(s.get("calls") or 1) for s in stages),
                  "approx_prompt_tokens": sum(int(s.get("approx_prompt_tokens") or 0) for s in stages)}
        for k in NOT_IN_SCRIPT:
            vals = [s[k] for s in stages if s.get(k) is not None]
            totals[k] = sum(vals) if vals and len(vals) == len(stages) else None
        out[slug] = {"company": pick.get("company"), "role": pick.get("role"),
                     "abbr": pick.get("abbr"), "stages": stages, "totals": totals}
    return out


def batch_line(rows: dict) -> str:
    n = len(rows)
    calls = sum(r["totals"]["calls"] for r in rows.values())
    audits = sum(1 for r in rows.values() for s in r["stages"] if s.get("stage") == "audit")
    approx = sum(r["totals"]["approx_prompt_tokens"] for r in rows.values())
    parts = [f"{n} posting(s), {calls} agent call(s), {audits} model audit(s), prompts about "
             f"{approx} tokens (characters / 4)"]
    for k, label in (("tokens", "tokens"), ("tool_calls", "tool calls"), ("seconds", "seconds")):
        vals = [r["totals"][k] for r in rows.values()]
        parts.append(f"{sum(vals)} {label}" if vals and all(v is not None for v in vals)
                     else f"{label} not available (copy them from the Workflow run summary)")
    return "batch: " + "; ".join(parts)


def write(round_dir: str, result, usage=None) -> tuple[str, list[str], str]:
    rows = per_posting(result, usage)
    line = batch_line(rows)
    batch = {"postings": rows, "total": line,
             "not_recorded_by_the_workflow": list(NOT_IN_SCRIPT),
             "note": "approx_prompt_tokens is characters / 4; output_tokens_shared_counter is "
                     "the shared budget counter's movement while a stage ran, so concurrent "
                     "stages over-count it"}
    path = os.path.join(round_dir, "cost.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(batch, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    kept = []
    try:
        import outreach
    except Exception:
        outreach = None
    for slug, r in rows.items():
        if outreach is None or not r.get("company"):
            continue
        folder = outreach.app_folder(r["company"], r.get("role") or "", r.get("abbr") or "")
        if os.path.isdir(folder):
            with open(os.path.join(folder, "cost.json"), "w", encoding="utf-8") as fh:
                json.dump(dict(r, slug=slug), fh, indent=1, ensure_ascii=False)
                fh.write("\n")
            kept.append(local_path.rel(os.path.join(folder, "cost.json"), person.state()))
    return path, kept, line


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("round_dir")
    ap.add_argument("--result", required=True, help="the workflow's return value, as JSON")
    ap.add_argument("--usage", help="per-agent figures from the Workflow tool's run summary")
    a = ap.parse_args(argv)
    result = _load(a.result)
    usage = _load(a.usage) if a.usage else None
    path, kept, line = write(a.round_dir, result, usage)
    print(f"wrote {path}")
    for k in kept:
        print(f"wrote {k}")
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
