"""A tweak on the page changes one thing, runs the checks every output gets, and keeps its word.

TWEAKS.md (2026-10-25): code-only changes (a look, a size, a colour, a bullet, who the
letter is addressed to, a first note built again from its parts) need no model call; a
wording change is staged so both audits run on it; the same tweak on the same draft is the
same result and never written twice; the person's words in the box are held like any
reaction; words asked for three times become a button of their own; and nothing section 4
rules out is in the table. LaTeX is stood in for by LJS_TWEAK_RENDER. Every person and
employer here is invented (tests/app_state.py).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "templates"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_alerts  # noqa: E402
import doc_design  # noqa: E402
import doc_style  # noqa: E402
import tweak  # noqa: E402
import untrusted  # noqa: E402
from app_state import NOW  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import KESTREL, Search  # noqa: E402

FAKE = '''import json, os, sys
step, path = sys.argv[1], sys.argv[2]
with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as fh:
    fh.write(step + " " + path + "\\n")
print("all checks passed (stand-in)")
'''
FOLDER = ("documents", "applications", "kestrel_mutual_claims_forecasting_analyst_kestrel")


class Tweaks(Search):
    def __init__(self, root):
        super().__init__(root)
        self.fake = os.path.join(root, "fake_render.py")
        with open(self.fake, "w", encoding="utf-8") as fh:
            fh.write(FAKE)
        self.log = os.path.join(root, "render.log")
        self.folder = os.path.join(self.state, *FOLDER)
        self.n_work = 0

    def env(self):
        # The tweak reads the page on the same clock as the page the test looks at
        # (`model --now NOW`): the tap that marks it applied is dated NOW, and on the
        # computer's own clock it falls out of Drafts 14 days later (RECENT_APPLIED_DAYS).
        env = dict(os.environ, LJS_PROFILE=self.profile, LJS_STATE=self.state, LJS_COPY="private",
                   LJS_TWEAK_RENDER=f'"{sys.executable}" "{self.fake}"', FAKE_LOG=self.log,
                   LJS_TODAY=NOW)
        return env

    def renders(self) -> int:
        try:
            with open(self.log, encoding="utf-8") as fh:
                return sum(1 for ln in fh if ln.startswith("fit "))
        except OSError:
            return 0

    def tweak(self, cmd, output, target, changes=(), text=None, rev=None, **more):
        self.n_work += 1
        item = {"kind": "tweak", "status": "claimed",
                "args": {"target": {"id": target, "output": output, **({"rev": rev} if rev else {})},
                         "changes": list(changes), "text": text, **more}}
        path = os.path.join(self.dump, f"work_{self.n_work}.json")
        os.makedirs(self.dump, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"id": f"tweak~{target}", "version": 3, "data": item}, fh)
        extra = ["--round", more.pop("round")] if "round" in more else []
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "tweak.py"), cmd,
                            "--work", path, *extra], env=self.env(), capture_output=True,
                           encoding="utf-8", errors="replace", timeout=300)
        try:
            return json.loads(r.stdout)
        except ValueError:
            raise AssertionError(r.stdout + r.stderr) from None

    def draft(self):
        with open(os.path.join(self.folder, "draft.json"), encoding="utf-8") as fh:
            return json.load(fh)[0]

    def python(self, code):
        r = subprocess.run([sys.executable, "-c", code], env=self.env(), capture_output=True,
                           encoding="utf-8", errors="replace", timeout=120, cwd=ROOT)
        assert r.returncode == 0, r.stdout + r.stderr
        return r.stdout


@pytest.fixture
def t(tmp_path):
    return Tweaks(str(tmp_path))


# ------------------------------------------------------------------ the table


def test_every_row_has_a_writer_a_cost_and_nothing_section_4_rules_out():
    rows = tweak.table()
    assert {r["p"] for r in rows} == set(tweak.BY_P)
    for r in tweak.TWEAKS:
        assert r["how"] in ("design", "style", "bullets", "fill", "skills", "letter_length",
                            "contact_person", "parts", "redraft", "search", "pack", "brief",
                            "page"), r["p"]
        assert set(r["outputs"]) <= {"resume", "letter", "message", "jobs", "interview", "brief",
                                     "page"}
        said = " ".join([r["label"], r["hint"], *map(str, r["values"])]).lower()
        assert not any(w in said for w in tweak.NEVER_WORDS), (r["p"], said)
        if r["how"] == "redraft":
            assert r["state"] == 2 and len(r["values"]) <= 4        # labelled steps, no slider
        if r["how"] == "page":
            assert r["state"] == 0
    assert set(tweak.BY_P["R1"]["values"]) == set(doc_design.DESIGNS)
    assert set(tweak.BY_P["R5"]["values"]) == set(doc_style.STYLES)     # never a free colour
    assert "smaller" not in tweak.BY_P["R2"]["values"]                  # never under 11pt
    assert all(r["cost"] in app_alerts.COSTS.values() for r in rows)
    assert not any(re.search(r"token", r["cost"], re.I) for r in rows)


def test_the_model_carries_the_table_and_what_each_output_can_take(t):
    m = t.model()
    assert [r["p"] for r in m["tweaks"]["rows"]] == [r["p"] for r in tweak.TWEAKS]
    assert m["tweaks"]["buttons"] == []
    item = next(r for r in m["ready"] if r["id"] == KESTREL)
    assert item["tweaks_done"] == [] and item["near"] == []
    (msg,) = m["messages"]
    assert msg["parts"] is False and msg["tweaks_done"] == []


# ------------------------------------------------------------------ code only


def test_a_look_and_a_colour_are_code_only_and_the_same_tweak_twice_is_already_done(t):
    rev = next(r for r in t.model()["ready"] if r["id"] == KESTREL)["rev"]
    got = t.tweak("apply", "resume", KESTREL, [{"p": "R1", "v": "classic"}, {"p": "R5", "v": "navy"}],
                  rev=rev)
    assert got["status"] == "done", got
    assert got["summary"] == "Done: the classic look; navy colour."
    d = t.draft()
    assert (d["design"], d["style"], d["design_step"]) == ("classic", "navy", 0)
    assert t.renders() == 1
    done = next(r for r in t.model()["ready"] if r["id"] == KESTREL)["tweaks_done"]
    assert done[0]["key"] == got["key"] and done[0]["undo"] is True
    again = t.tweak("apply", "resume", KESTREL, [{"p": "R1", "v": "classic"}, {"p": "R5", "v": "navy"}])
    assert again["status"] == "cached" and t.renders() == 1          # no render, no writing


def test_an_undo_puts_the_version_before_back_and_a_repeat_reuses_the_kept_result(t):
    before = t.draft()
    first = t.tweak("apply", "resume", KESTREL, [{"p": "R2", "v": "larger"}, {"p": "R3", "v": "roomier"}])
    assert first["status"] == "done" and t.draft()["design"]["body_size"] == 12
    back = t.tweak("undo", "resume", KESTREL, undo=first["key"])
    assert back["status"] == "done" and t.draft() == before
    # The same tweak on the same draft again: its kept result, not a second working-out.
    redo = t.tweak("apply", "resume", KESTREL, [{"p": "R2", "v": "larger"}, {"p": "R3", "v": "roomier"}])
    assert redo["status"] == "done" and redo["summary"].startswith("Done again from the kept result")
    assert t.draft()["design"]["body_size"] == 12
    assert t.tweak("undo", "resume", KESTREL, undo="0000000000")["status"] == "refused"


def test_a_tweak_on_something_changed_or_sent_is_refused_and_writes_nothing(t):
    before = t.draft()
    stale = t.tweak("apply", "resume", KESTREL, [{"p": "R1", "v": "modern"}], rev="not-the-rev")
    assert stale["status"] == "refused" and "changed since you saw it" in stale["summary"]
    wrong = t.tweak("apply", "resume", KESTREL, [{"p": "R5", "v": "#ff0000"}])
    assert wrong["status"] == "refused"
    aid = t.act("ready.applied", KESTREL)
    assert t.apply()["ok"] == [aid]
    sent = t.tweak("apply", "resume", KESTREL, [{"p": "R1", "v": "modern"}])
    assert sent["status"] == "refused" and "Make a copy for another role" in sent["summary"]
    assert t.draft() == before and t.renders() == 0


def test_the_letter_is_addressed_to_a_name_or_the_team(t):
    got = t.tweak("apply", "letter", KESTREL, [{"p": "L5", "v": "Kit Marden"}])
    assert got["status"] == "done" and t.draft()["contact_person"] == "Kit Marden"
    t.tweak("apply", "letter", KESTREL, [{"p": "L5", "v": "the team"}])
    assert "contact_person" not in t.draft()


# ------------------------------------------------------------------ a first note from its parts


def _compose_pell(t):
    t.python(
        "import sys; sys.path[:0] = ['tools', 'tools/network']\n"
        "import compose, reading\n"
        "n = compose.first_note('Pell Ansgar', common_ground='We were both at Leeds', "
        "question='How is the claims analytics team set up?', variant_key='kestrel_mutual_ansgar', "
        "their=('Kestrel Mutual',), card_only=True)\n"
        "reading.write_draft('kestrel_mutual_ansgar', str(n), 'Pell Ansgar', card_only=True)\n")


def test_a_first_note_is_built_again_from_its_parts_with_no_model(t):
    _compose_pell(t)
    (msg,) = t.model()["messages"]
    assert msg["parts"] is True
    got = t.tweak("apply", "message", msg["id"], [{"p": "M5", "v": "me_first"}], rev=msg["rev"])
    assert got["status"] == "done", got
    (after,) = t.model()["messages"]
    assert after["text"].startswith("Hi Pell, hope you're well. I work in")
    assert after["parts"] is True and after["tweaks_done"][0]["undo"] is True
    # Words the table already has are its own values, read by code: no model, nothing held.
    short = t.tweak("apply", "message", after["id"], text="make it shorter")
    assert short["status"] == "done"
    assert "How is the claims" not in t.model()["messages"][0]["text"]   # a brief note asks no question
    pending = t.python("import sys; sys.path.insert(0, 'tools'); import learned; "
                       "print(len(learned.pending()))")
    assert pending.strip() == "0"
    # One the composer refuses is refused in its words, and the note stays as it was.
    text = t.model()["messages"][0]["text"]
    no = t.tweak("apply", "message", after["id"], [{"p": "M5", "v": "me_second"}])
    assert no["status"] == "refused" and "two reasons" in no["summary"]
    assert t.model()["messages"][0]["text"] == text


def test_a_note_with_no_parts_is_a_rewrite_never_a_guess(t):
    (msg,) = t.model()["messages"]
    got = t.tweak("apply", "message", msg["id"], [{"p": "M5", "v": "me_first"}])
    assert got["status"] == "needs_model" and "not written from its parts" in got["summary"]


# ------------------------------------------------------------------ wording: both audits


def _posting(t):
    with open(os.path.join(t.folder, "job_posting.md"), "w", encoding="utf-8") as fh:
        fh.write(untrusted.fence("Claims Forecasting Analyst. Build forecasts in Python and SQL; "
                                 "Looker dashboards a plus."))
    d = [dict(t.draft(), posting_from="job_posting.md", summary="Analyst who builds forecasts.",
              claim_map=[{"field": "summary", "sentence": "Analyst who builds forecasts.",
                          "evidence": ["E1"]}, {"field": "p1", "sentence": "x", "evidence": []}])]
    with open(os.path.join(t.folder, "draft.json"), "w", encoding="utf-8") as fh:
        json.dump(d, fh)


def test_a_wording_change_is_staged_for_both_audits_with_only_its_fields(t):
    _posting(t)
    got = t.tweak("apply", "resume", KESTREL, [{"p": "R8", "v": "plainer"}])
    assert got["status"] == "needs_model" and t.renders() == 0
    rd = got["round"]
    (pick,) = json.load(open(os.path.join(rd, "picks.json"), encoding="utf-8"))
    assert pick["company"] == "Kestrel Mutual" and pick["role"] == "Claims Forecasting Analyst"
    assert untrusted.unfence(open(pick["file"], encoding="utf-8").read()).startswith("Claims Forecasting")
    staged = json.load(open(os.path.join(rd, f"draft_{pick['slug']}.json"), encoding="utf-8"))
    assert "posting" not in staged and staged["summary"] == "Analyst who builds forecasts."
    pkt = json.load(open(got["packet"], encoding="utf-8"))
    assert list(pkt["fields"]) == ["summary"] and [c["field"] for c in pkt["claim_map"]] == ["summary"]
    assert pkt["asked"] == ["Summary words: plainer"] and pkt["wish"] is None
    assert any("stage_picks.py audit" in s for s in got["steps"])
    assert any("own model" in s for s in got["steps"])


def test_the_persons_own_words_are_fenced_and_held_like_any_reaction(t):
    _posting(t)
    got = t.tweak("apply", "letter", KESTREL, text="less about the airline work, more forecasting")
    assert got["status"] == "needs_model"
    pkt = json.load(open(got["packet"], encoding="utf-8"))
    assert pkt["wish"].startswith(untrusted.WISH_RULE) and "BEGIN-UNTRUSTED-" in pkt["wish"]
    assert "less about the airline work" in untrusted.unfence(pkt["wish"])
    pending = json.loads(t.python(
        "import sys, json; sys.path.insert(0, 'tools'); import learned; "
        "print(json.dumps(learned.pending()))"))
    assert pending[0]["said"].startswith("less about the airline work")
    assert pending[0]["cue"] == "page tweak" and pending[0]["output"] == "letter"


def test_an_audited_redraft_comes_back_once_and_is_never_written_twice(t):
    _posting(t)
    work = [{"p": "R8", "v": "shorter"}]
    got = t.tweak("apply", "resume", KESTREL, work)
    rd = got["round"]
    with open(os.path.join(rd, "drafts.json"), "w", encoding="utf-8") as fh:
        json.dump([dict(t.draft(), summary="Analyst building forecasts in Python and SQL.",
                        posting="Claims Forecasting Analyst. Build forecasts in Python and SQL.")], fh)
    merged = t.tweak("merge", "resume", KESTREL, work, round=rd)
    assert merged["status"] == "done", merged
    assert t.draft()["summary"] == "Analyst building forecasts in Python and SQL."
    assert t.draft()["posting_from"] == "job_posting.md" and "posting" not in t.draft()
    logged = json.load(open(os.path.join(t.folder, "tweaks.json"), encoding="utf-8"))
    assert logged[got["key"]]["fields"] == {"summary": "Analyst building forecasts in Python and SQL."}
    # The same request on the draft it was made on: the kept words, no second writing.
    assert t.tweak("undo", "resume", KESTREL, undo=got["key"])["status"] == "done"
    again = t.tweak("apply", "resume", KESTREL, work)
    assert again["status"] == "done" and again["summary"].startswith("Done again from the kept")
    assert t.draft()["summary"] == "Analyst building forecasts in Python and SQL."


def test_a_redraft_that_changed_more_than_was_asked_is_refused(t):
    _posting(t)
    work = [{"p": "R8", "v": "plainer"}]
    rd = t.tweak("apply", "resume", KESTREL, work)["round"]
    with open(os.path.join(rd, "drafts.json"), "w", encoding="utf-8") as fh:
        json.dump([dict(t.draft(), summary="A new summary.", p4="A new closing.")], fh)
    before = t.draft()
    got = t.tweak("merge", "resume", KESTREL, work, round=rd)
    assert got["status"] == "refused" and "the closing" in got["summary"]
    assert t.draft() == before


# ------------------------------------------------------------------ words asked for again and again


def test_words_asked_for_three_times_become_a_button_of_their_own(t):
    for day in ("2026-10-01", "2026-10-10", "2026-10-20"):
        t.python("import sys; sys.path.insert(0, 'tools'); import learned; "
                 f"learned.skip('less about the airline work', 'one-off', today='{day}', "
                 "via='page tweak', output='letter')")
    out = t.python("import sys, json, datetime; sys.path.insert(0, 'tools'); import tweak; "
                   "print(json.dumps(tweak.promote(datetime.date(2026, 10, 25))))")
    (offer,) = json.loads(out)
    assert offer["kind"] == "button" and offer["times"] == 3 and offer["output"] == "letter"
    row = json.loads(t.python("import sys, json, datetime; sys.path.insert(0, 'tools'); import tweak; "
                              "o = tweak.promote(datetime.date(2026, 10, 25))[0]; "
                              "print(json.dumps(tweak.add_button(o)))"))
    assert t.model()["tweaks"]["buttons"][0]["id"] == row["id"]
    _posting(t)
    got = t.tweak("apply", "letter", KESTREL, [{"p": f"custom:{row['id']}"}])
    assert got["status"] == "needs_model"
    pkt = json.load(open(got["packet"], encoding="utf-8"))
    assert "less about the airline work" in untrusted.unfence(pkt["wish"])


def test_a_value_asked_for_again_and_again_is_offered_as_the_usual(t):
    for day, words in (("2026-10-02", "make it shorter"), ("2026-10-09", "shorter please"),
                       ("2026-10-21", "still too long, shorter")):
        t.python("import sys; sys.path.insert(0, 'tools'); import learned; "
                 f"learned.skip({words!r}, 'one-off', today='{day}', via='page tweak', "
                 "output='message')")
    out = t.python("import sys, json, datetime; sys.path.insert(0, 'tools'); import tweak; "
                   "print(json.dumps(tweak.promote(datetime.date(2026, 10, 25))))")
    (offer,) = json.loads(out)
    assert (offer["kind"], offer["p"], offer["v"]) == ("usual", "M1", "brief")
    assert offer["line"] == "You ask for length: brief a lot. Make it your usual?"
    # Older than 90 days, or fewer than three: nothing offered.
    out = t.python("import sys, json, datetime; sys.path.insert(0, 'tools'); import tweak; "
                   "print(json.dumps(tweak.promote(datetime.date(2027, 3, 1))))")
    assert json.loads(out) == []


# ------------------------------------------------------------------ undo from the page


def test_an_undo_tapped_on_the_page_is_queued_as_work(t):
    got = t.tweak("apply", "resume", KESTREL, [{"p": "R1", "v": "modern"}])
    item = next(r for r in t.model()["ready"] if r["id"] == KESTREL)
    aid = t.act("tweak.undo", KESTREL, value={"key": got["key"]}, rev=item["rev"])
    res = t.apply()
    assert res["ok"] == [aid], res
    batch = json.load(open(res["batches"][0], encoding="utf-8"))
    work = next(e for e in batch if e["collection"] == "work")
    assert work["doc_id"] == f"tweak~{KESTREL}~undo-{got['key']}"
    doc = json.load(open(work["file_path"], encoding="utf-8"))
    assert doc["kind"] == "tweak" and doc["args"]["undo"] == got["key"]


def test_not_applied_after_all_on_a_job_takes_back_its_tick(t):
    m = t.model()
    job = next(r for r in m["jobs"]["rows"] if r["id"] == "r9-1")
    a1 = t.act("job.applied", "r9-1", rev=job["rev"])
    assert t.apply()["ok"] == [a1]
    t.written_back()
    job = next(r for r in t.model()["jobs"]["rows"] if r["id"] == "r9-1")
    assert job["status"] == "applied"
    a2 = t.act("job.not_applied", "r9-1", rev=job["rev"])
    got = t.apply()
    assert got["ok"] == [a2], [t.receipt(a2)]
    assert next(r for r in t.model()["jobs"]["rows"] if r["id"] == "r9-1")["status"] != "applied"


# ------------------------------------------------------------------ near matches


def test_a_draft_and_a_job_say_which_asked_tools_the_person_has_one_like(t):
    _posting(t)
    path = os.path.join(t.state, "documents", "rounds", "r9.json")
    rows = json.load(open(path, encoding="utf-8"))
    rows[0]["near"] = [{"asked": "Looker", "have": "Power BI"}]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)
    m = t.model()
    assert m["jobs"]["rows"][0]["near"] == [{"asked": "Looker", "have": "Power BI"}]
    item = next(r for r in m["ready"] if r["id"] == KESTREL)
    assert item["near"] == [{"asked": "Looker", "have": "Power BI", "yes": False}]
