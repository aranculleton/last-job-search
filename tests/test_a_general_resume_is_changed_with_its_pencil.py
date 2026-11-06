"""The general resume is changed with its pencil, as a resume made for a posting is.

The maintainer, 2026-11-06: "You can't choose which bullets go on a general resume, and the
fact-checking against the profile only runs on resumes made for a posting." The general
resume keeps its draft beside its PDF (documents/cv/general/draft.json), its card on the page
carries its bullets, and the Tweak panel the pencil opens changes it through tools/tweak.py:
a bullet ticked is swapped for another true one from the same job, code only, then made and
checked by the checks every resume gets and kept again as the one to send; its summary
reworded goes through both audits, as an application's does. Which bullets is never kept as a
usual for every resume. LaTeX is stood in for (LJS_TWEAK_RENDER). Every person and employer
here is invented (tests/app_state.py).
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

from test_a_tweak_changes_one_thing_and_keeps_its_word import Tweaks  # noqa: E402

MADE = r'''
import json, os, sys
sys.path[:0] = ["tools", "tools/network", "templates"]
import docpaths, general_resume as G, render_application as R
a = G.draft()
R.check_batch([a])
a["abbr"] = R.final_abbr(a)
R.jobs_for(a)
a["claim_map"] = G.claim_map(a)          # as make() keeps it
G.keep_draft(a)
pdf, txt = G.keep_paths()
os.makedirs(os.path.dirname(pdf), exist_ok=True)
with open(pdf, "wb") as fh:
    fh.write(b"%PDF-1.4 the first one")
with open(txt, "w", encoding="utf-8") as fh:
    fh.write(G.plain_text(a))
os.makedirs(os.path.dirname(docpaths.resume_pdf(a["abbr"])), exist_ok=True)
with open(docpaths.resume_pdf(a["abbr"]), "wb") as fh:
    fh.write(b"%PDF-1.4 made again after the change")
print(json.dumps({"pdf": pdf, "abbr": a["abbr"]}))
'''


@pytest.fixture
def t(tmp_path):
    t = Tweaks(str(tmp_path))
    t.made = json.loads(t.python(MADE))
    return t


def _draft(t):
    import general_resume
    path = os.path.join(t.state, *general_resume.DRAFT_DIR, "draft.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)[0]


def test_its_card_carries_its_bullets_and_the_tweak_swaps_the_ones_ticked(t):
    r = t.model()["resume"]
    bullets = r["bullets"]
    assert bullets and all(b["id"] and b["employer"] and b["text"] for b in bullets), r
    first = bullets[0]
    assert first["text"] and "\\" not in first["text"]          # plain words, never LaTeX
    got = t.tweak("apply", "resume", "resume-current", [{"p": "R6", "v": [first["id"]]}],
                  rev=r["rev"])
    assert got["status"] == "done", got
    assert got["summary"].startswith("Done: another bullet from "), got
    now = [b for j in _draft(t)["jobs"] for b in j["bullets"]]
    assert first["id"] not in now and len(now) == len(bullets)
    # Made and checked by the checks every resume gets, then kept again as the one to send.
    assert t.renders() == 1
    with open(t.made["pdf"], "rb") as fh:
        assert fh.read() == b"%PDF-1.4 made again after the change"
    # The card shows the new bullets, under a new rev: a tap on the old one is refused.
    after = t.model()["resume"]
    assert after["rev"] != r["rev"] and first["id"] not in [b["id"] for b in after["bullets"]]
    stale = t.tweak("apply", "resume", "resume-current", [{"p": "R6", "v": [after["bullets"][0]["id"]]}],
                    rev=r["rev"])
    assert stale["status"] == "refused" and "changed since" in stale["summary"], stale


def test_which_bullets_is_never_kept_as_a_usual(t):
    r = t.model()["resume"]
    got = t.tweak("apply", "resume", "resume-current", [{"p": "R6", "v": [r["bullets"][0]["id"]]}],
                  rev=r["rev"], keep={"scope": "all", "params": ["R6"]})
    assert got["status"] == "done" and "Kept as your usual" not in got["summary"], got


def test_its_summary_reworded_goes_through_both_audits(t):
    r = t.model()["resume"]
    got = t.tweak("apply", "resume", "resume-current", [{"p": "R8", "v": "shorter"}], rev=r["rev"])
    assert got["status"] == "needs_model", got
    assert any("stage_picks.py audit" in s for s in got["steps"]), got
    assert any("grounding-auditor" in s for s in got["steps"]), got
    staged = os.path.join(got["round"], "draft_general.json")
    with open(staged, encoding="utf-8") as fh:
        assert json.load(fh)["general"] is True
    # The code audit asks only grounding questions of it: no posting's rules (a requirement
    # map, a posting's skill to write into the work), and its summary rests on its claim map.
    said = json.loads(t.python(
        "import json, sys; sys.path[:0] = ['tools', 'tools/network', 'templates']\n"
        "import draft_audit\n"
        f"d = json.load(open({staged!r}, encoding='utf-8'))\n"
        "got = draft_audit.mechanical(d, {'company': 'General'}, d.get('posting', ''), None)\n"
        "print(json.dumps(got))"))
    assert said["findings"] == [], said["findings"]
    assert not [f for f in said["flags"] if f["flag"] == "unmapped"], said["flags"]


def test_one_made_before_its_draft_was_kept_asks_for_a_fresh_one(t):
    import general_resume
    os.remove(os.path.join(t.state, *general_resume.DRAFT_DIR, "draft.json"))
    r = t.model()["resume"]
    assert r["bullets"] == []
    got = t.tweak("apply", "resume", "resume-current", [{"p": "R5", "v": "navy"}], rev=r["rev"])
    assert got["status"] == "refused" and got["summary"].startswith("Make a fresh one first"), got
