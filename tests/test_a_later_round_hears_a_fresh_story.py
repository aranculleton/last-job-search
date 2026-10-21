"""A later round at the same employer is prepared with a story it has not heard yet.

From the sync audit, 2026-10-21: every story the last build put on one screen was kept on
the next build, however it had been chosen, so the final round was prepared with the very
story the behavioural round had already told, while the same build with no earlier document
chose a fresh one. And an older build's story on two questions was carried on, so the
rebuild meant to choose stories across the whole plan changed nothing. A story the session
chose (--map) is now kept for the round it was chosen for, and only then; matching chooses
the rest again, preferring a story not yet told there.

Every person, employer, story and question here is invented; the candidate is the example
person.
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.dirname(os.path.abspath(__file__))]

import interview_pack as P  # noqa: E402
import outreach  # noqa: E402
import person  # noqa: E402
import test_a_referral_process_is_prepared_from_what_was_said as referral  # noqa: E402
from test_a_referral_process_is_prepared_from_what_was_said import (  # noqa: E402
    FIRM, ROLE, TODAY, _doc, _process)

case = referral.case
ROUND2, FINAL = "Round 2 (behavioural)", "Final round"
TOLD = "The forecast that freed safety stock"
FRESH = "The depot routes rebuilt"
END_TO_END = "Walk me through a project end to end."


def _second_story():
    with open(person.path(P.STORIES_FILE), "a", encoding="utf-8") as fh:
        fh.write("\n## STAR: the depot routes rebuilt\n"
                 "- **Situation:** van routes were planned by hand each week.\n"
                 "- **Task:** routes the depots would follow.\n"
                 "- **Action:** built a routing model in Python with the depot managers.\n"
                 "- **Result:** van miles down a tenth in a quarter.\n"
                 "- **Use for:** \"Walk me through a project end to end\", \"Tell me about a "
                 "model you built\"\n")


def _plan(text):
    screen = text.split("## On one screen\n", 1)[1].split("\n## ", 1)[0]
    return dict(re.findall(r"^\d+\. (.+?) -> story: (.+?)\s*$", screen, re.M))


def _folder():
    return outreach.app_folder(FIRM, ROLE)


def _kept(stage):
    """The stories a rebuild for `stage` keeps from the last build."""
    return P.gather(FIRM, ROLE, stage=stage, today=TODAY)["kept_map"]


def test_a_story_told_in_one_round_is_not_told_again_in_the_next(case):
    _process()
    _second_story()
    mapped = case / "map.json"
    mapped.write_text(json.dumps({END_TO_END: TOLD}), encoding="utf-8")
    assert P.main(["pack", FIRM, "--stage", ROUND2, "--format", "behavioural", "--today", TODAY,
                   "--write", "--map", str(mapped)]) == 0
    assert _plan(_doc()).get(END_TO_END) == TOLD
    assert P.main(["asked", "--company", FIRM, "--role", ROLE, "--stage", ROUND2,
                   "--question", END_TO_END, "--story", TOLD, "--landed", "yes",
                   "--date", TODAY]) == 0
    # The session's choice holds for its own round: rebuilt for it, it is still there.
    assert _kept(ROUND2) == {END_TO_END: TOLD}
    # The final round chooses afresh, and the story told already gives way.
    assert _kept(FINAL) == {}
    assert P.main(["pack", FIRM, "--stage", FINAL, "--today", TODAY, "--write"]) == 0
    doc = _doc()
    if END_TO_END in _plan(doc):
        assert _plan(doc)[END_TO_END] == FRESH
    likely = doc.split("## Likely questions\n", 1)[1].split("\n## ", 1)[0]
    assert "Story: %s" % TOLD not in likely.split("**Q.** %s" % END_TO_END, 1)[-1].split(
        "- **Q.**", 1)[0]
    assert "chosen over %s, told here in %s" % (TOLD, ROUND2) in doc


def test_an_older_builds_story_on_two_questions_is_kept_for_one(case):
    _process()
    folder = _folder()
    record = os.path.join(folder, ".interview_prep.built.json")
    if os.path.exists(record):
        os.remove(record)                            # a document from before the record
    path = os.path.join(folder, P.LIVING)
    text = _doc()
    # The older build answered its first two questions with one story.
    lines = re.findall(r"^\d+\. (.+?) -> .*$", text, re.M)
    first, second = lines[:2]
    for q in (first, second):
        text = re.sub(r"^(\d+\. %s -> ).*$" % re.escape(q), lambda m: m.group(1) + "story: "
                      + TOLD, text, count=1, flags=re.M)
    assert _plan(text) == {first: TOLD, second: TOLD}
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    stage = re.search(r"^Last updated \S+\. Next: (.+?)(?:, \d{4}|\.)", text, re.M).group(1)
    assert _kept(stage) == {first: TOLD}
