"""Interview prep that prepares someone (issue 367): each round still to come is a `round`
on the page, practised with cards that come back on a schedule, three follow-ups deep on every
technical answer, a plan for the day when it is in person, and a readiness the brief says in
one line. The next pack starts from what was shaky.

Every person, employer and answer here is invented: the example person (`profile.example/`),
the made-up application `tests/test_interview_pack.py` builds, and the small state
`tests/app_state.py` gives the page's own tests.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.dirname(os.path.abspath(__file__))]

import interview_pack as P  # noqa: E402
import interview_round as R  # noqa: E402
from test_interview_pack import COMPANY, ROLE, ROW, _ctx, app  # noqa: E402,F401

ROUND_KEYS = ("who", "format", "in_person", "cheat_sheet", "stories", "numbers", "cards",
              "logistics", "cases", "readiness")
READY_KEYS = ("score", "practised", "cases_done", "mocks_done", "logistics_confirmed", "next")
DAY_KEYS = ("address", "entrance", "floor", "travel", "arrive_by", "bring", "wear", "timeline",
            "time_zone", "final_five", "whiteboard", "confirmed")


def _read(path) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _mark(at, mark):
    return {"at": at, "mark": mark}


@pytest.fixture
def mirror(tmp_path, monkeypatch):
    """The copy's own record of the page's last read, where the practice marks are kept."""
    where = tmp_path / "mirror"
    (where / "practice").mkdir(parents=True)
    monkeypatch.setenv("LJS_PAGE_MIRROR", str(where))
    return where


def _keep(mirror, doc_id, data):
    with open(mirror / "practice" / ("%s.json" % doc_id.replace("~", "@")), "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump({"data": data, "version": 1}, fh)


# ------------------------------------------------------------------ spaced repetition

def test_a_card_comes_back_after_1_3_7_and_14_days():
    assert R.INTERVALS == (1, 3, 7, 14)
    assert R.schedule([])["due"] is None                     # never marked: due now
    got = [_mark("2026-03-0%dT09:00:00Z" % d, "got") for d in range(1, 6)]
    # got moves to the next interval each time, and stays at 14.
    assert [R.schedule(got[:n])["interval"] for n in range(1, 6)] == [1, 3, 7, 14, 14]
    assert R.schedule(got[:2])["due"] == "2026-03-05T09:00:00Z"
    # shaky repeats the interval it is on; a first shaky is 1 day.
    assert R.schedule([_mark("2026-03-01T09:00:00Z", "shaky")])["interval"] == 1
    assert R.schedule(got[:3] + [_mark("2026-03-04T09:00:00Z", "shaky")])["interval"] == 7
    # missed puts it back to 1 day, whatever it was on.
    assert R.schedule(got[:4] + [_mark("2026-03-05T09:00:00Z", "missed")])["interval"] == 1
    # Read oldest first, whatever order the page wrote them in.
    assert R.schedule(list(reversed(got[:3])))["interval"] == 7
    assert [R.next_step(None, m) for m in R.MARKS] == [0, 0, 0]
    assert [R.next_step(2, m) for m in R.MARKS] == [3, 2, 0]


# ------------------------------------------------------------------ readiness

def test_practice_order_is_missed_then_due_then_shaky_then_new():
    now = dt.datetime(2026, 3, 10, 12, tzinfo=dt.timezone.utc)
    cards = [{"id": i} for i in ("new", "got_later", "shaky_later", "due", "missed")]
    marks = {"got_later": [_mark("2026-03-08T09:00:00Z", "got"), _mark("2026-03-10T09:00:00Z", "got")],
             "shaky_later": [_mark("2026-03-08T09:00:00Z", "got"),
                             _mark("2026-03-10T09:00:00Z", "shaky")],
             "due": [_mark("2026-03-08T09:00:00Z", "got")],
             "missed": [_mark("2026-03-10T11:00:00Z", "missed")]}
    assert [c["id"] for c in R.order_cards(cards, marks, now)] == [
        "missed", "due", "shaky_later", "new", "got_later"]


def test_readiness_is_read_from_the_practice_marks():
    cards = [{"id": "int-x~q1", "q": "A"}, {"id": "int-x~q2", "q": "B"},
             {"id": "int-x~q3", "q": "C"}]
    docs = R.docs_from({"practice": {
        "int-x~q1": {"data": {"card": "int-x~q1", "interview": "int-x",
                              "marks": [_mark("2026-03-01T09:00:00Z", "got")]}, "version": 2},
        "int-x~q2": {"data": {"card": "int-x~q2", "interview": "int-x",
                              "marks": [_mark("2026-03-01T09:00:00Z", "shaky")]}, "version": 1},
        "mock1": {"data": {"kind": "mock", "interview": "int-x", "at": "2026-03-02", "score": 3}},
        "case1": {"data": {"kind": "case", "interview": "int-x", "at": "2026-03-02"}},
        "other": {"data": {"card": "int-y~q1", "interview": "int-y",
                           "marks": [_mark("2026-03-01T09:00:00Z", "got")]}},
    }})
    mine = R.for_interview(docs, "int-x")
    assert mine["mocks"] == 1 and mine["cases"] == 1 and set(mine["cards"]) == {"int-x~q1", "int-x~q2"}
    now = dt.datetime(2026, 3, 1, 12, tzinfo=dt.timezone.utc)
    got = R.readiness(cards, mine["cards"], mine["mocks"], mine["cases"], 2, False, False, now)
    assert set(got) == set(READY_KEYS)
    assert got["practised"] == [1, 3] and got["mocks_done"] == 1 and got["cases_done"] == 1
    assert 0 < got["score"] < 100
    assert got["next"] == "Go over the 1 card you were shaky on"
    # Nothing practised: the first thing is to go through the cards once, and the score is 0.
    none = R.readiness(cards, {}, now=now)
    assert none["score"] == 0 and none["next"].startswith("Go through your 3 answer cards")
    # In person, the logistics count until they are confirmed.
    all_got = {c["id"]: [_mark("2026-03-01T09:00:00Z", "got")] for c in cards}
    site = R.readiness(cards, all_got, 1, 0, 0, True, False, now)
    assert site["next"].startswith("Check the address") and site["score"] < 100
    assert R.readiness(cards, all_got, 1, 0, 0, True, True, now)["score"] == 100


# ------------------------------------------------------------------ the round on the page

def _model(tmp_path, mirror_dir=None):
    import app_state
    state = app_state.small(str(tmp_path / "s"))
    env = dict(os.environ, LJS_PROFILE=app_state.EXAMPLE, LJS_STATE=state, LJS_COPY="private")
    env.pop("CLAUDE_CODE_REMOTE", None)
    if mirror_dir:
        env["LJS_PAGE_MIRROR"] = str(mirror_dir)
    out = tmp_path / "model.json"
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "model", "--now",
                    app_state.NOW, "--out", str(out)], env=env, check=True,
                   capture_output=True)
    return json.loads(out.read_text(encoding="utf-8"))


def test_every_upcoming_round_carries_the_whole_contract(tmp_path):
    model = _model(tmp_path)
    item = next(i for i in model["interviews"] if i["company"] == "Thornbury Bank")
    rnd = item["round"]
    assert set(ROUND_KEYS) <= set(rnd)
    assert isinstance(rnd["in_person"], bool) and rnd["in_person"] is False
    assert rnd["logistics"] is None and isinstance(rnd["cases"], list)
    assert rnd["who"] and all(set(w) >= {"name", "role", "probes"} and w["probes"]
                              for w in rnd["who"])
    assert 0 < len(rnd["cheat_sheet"]) <= 8
    # Six to eight stories, each saying where in the profile it comes from.
    assert 6 <= len(rnd["stories"]) <= 8
    for s in rnd["stories"]:
        assert set(s) >= {"id", "title", "trigger", "bullets", "source", "questions"}
        assert " at " in s["source"]
    # Every number is one the profile holds, with the role it is from.
    with open(os.path.join(ROOT, "profile.example", "01-candidate-profile.md"),
              encoding="utf-8") as fh:
        profile = fh.read()
    assert rnd["numbers"] and all(n["value"].split()[0] in profile for n in rnd["numbers"])
    assert any(n["value"] == "22% to 14%" for n in rnd["numbers"])
    # A card for each likely question, with a stable id, and every technical one three deep.
    assert [c["q"] for c in rnd["cards"]] == ["Tell me about a forecast you built",
                                              "How do you check your data"]
    for c in rnd["cards"]:
        assert set(c) >= {"id", "q", "trigger", "bullets", "follow"}
        assert c["id"] == R.card_id(item["id"], c["q"])
    deep = rnd["cards"][0]["follow"][0]
    assert deep["follow"][0]["follow"][0]["question"]
    assert set(rnd["readiness"]) == set(READY_KEYS)
    assert rnd["readiness"]["practised"] == [0, 2]
    # A stage already held has no round.
    assert all(i["round"] is None for i in model["interviews"] if i["past"])
    # The fields the page reads besides: each story's home question, each card's part of the
    # prep and who asks it, a plan a day up to the interview, and nothing invented.
    assert all(s["home"] is None or s["home"] in s["questions"] for s in rnd["stories"])
    assert all(c["section"] == "Likely questions" for c in rnd["cards"])
    assert all("about" in w for w in rnd["who"]) and rnd["project"] is None
    assert [p["day"] for p in rnd["plan"]] == ["2026-10-25", "2026-10-26", "2026-10-27",
                                               "2026-10-28"]
    assert rnd["plan"][-1]["focus"].startswith("The interview")


def test_the_round_reads_the_marks_and_puts_shaky_cards_first(tmp_path):
    iid = "int-thornbury_bank_risk_analyst"
    first, second = (R.card_id(iid, q) for q in ("Tell me about a forecast you built",
                                                 "How do you check your data"))
    where = tmp_path / "mirror"
    (where / "practice").mkdir(parents=True)
    _keep(where, first, {"card": first, "interview": iid,
                         "marks": [_mark("2026-10-22T09:00:00Z", "got"),
                                   _mark("2026-10-24T09:00:00Z", "got")]})
    _keep(where, second, {"card": second, "interview": iid,
                          "marks": [_mark("2026-10-24T09:00:00Z", "shaky")]})
    _keep(where, "mock~1", {"kind": "mock", "interview": iid, "at": "2026-10-24", "score": 3})
    rnd = next(i for i in _model(tmp_path, where)["interviews"]
               if i["company"] == "Thornbury Bank")["round"]
    assert [c["id"] for c in rnd["cards"]] == [second, first]
    assert rnd["cards"][0]["last"] == "shaky"            # due again; the got one is not
    assert all(c["who"] == "the head of risk" for c in rnd["cards"])
    assert rnd["readiness"]["practised"] == [1, 2] and rnd["readiness"]["mocks_done"] == 1
    assert "shaky" in rnd["readiness"]["next"]
    assert any(line.startswith("Shaky last time") for line in rnd["cheat_sheet"])


# ------------------------------------------------------------------ the pack

def _block(text, question):
    body = text.split("### %s\n" % question, 1)[1]
    return body.split("\n### ", 1)[0].split("\n## ", 1)[0]


def test_every_technical_answer_is_prepared_three_follow_ups_deep(app, mirror):  # noqa: F811
    text = _read(P.write_pack(_ctx()))
    technical = [q["question"] for q in P.practice(text)["questions"] if P.technical(q["question"])]
    assert technical
    for q in technical:
        block = _block(text, q)
        assert "      **If they follow up" not in block            # never deeper than asked
        assert "    **If they follow up" in block, q                # a third level under each
        follow = next(x for x in P.practice(text)["questions"] if x["question"] == q)["follow"]
        assert follow and all(f["follow"] and f["follow"][0]["follow"] for f in follow)
    # The third level asks about the method the profile records, or asks for it plainly.
    lines = text.splitlines()
    thirds = [ln for ln in lines if ln.startswith("    **If they follow up")]
    assert thirds
    for i, ln in enumerate(lines):
        if ln.startswith("    **If they follow up") and "the method" in ln:
            assert lines[i + 1].strip().startswith("> FILL IN: ")
    # A FILL IN is a note, never words to say and never a placeholder the check holds on.
    assert not any("FILL IN" in why for _w, why in P.check(P.living_path(_ctx())))


def test_the_third_follow_up_names_the_recorded_method():
    chains = P.tech_follow_chains("Tell me about a model you built", ["XGBoost"])
    assert len(chains) == P.TECH_FOLLOW_N and all("XGBoost" in third for _a, _b, third in chains)
    lines = P.tech_follow_lines("Tell me about a model you built", ["XGBoost"])
    assert not any("FILL IN" in ln for ln in lines)
    bare = P.tech_follow_lines("Tell me about a model you built")
    assert sum(ln.strip().startswith("> FILL IN:") for ln in bare) == P.TECH_FOLLOW_N
    gap = R.follow_chain("How do you validate a forecast?")
    assert gap[0]["follow"][0]["follow"][0]["answer"].startswith("FILL IN: ")


def test_a_round_in_person_gets_the_day_and_its_logistics_are_recorded(app, mirror):  # noqa: F811
    text = _read(P.write_pack(_ctx()))
    assert "## On the day" not in text                               # a video round: none
    out = io.StringIO()
    with redirect_stdout(out):
        assert P.main(["logistics", COMPANY, "--role", ROLE, "--stage", "Technical interview",
                       "--address", "14 Example Quay, Warrington", "--arrive-by", "9:15",
                       "--bring", "The forecast slides on paper", "--today", "2026-03-11"]) == 0
    said = out.getvalue()
    assert "Saved" in said and "entrance" in said                    # what is still to ask
    saved = os.path.join(app, R.LOGISTICS)
    with open(saved, "rb") as fh:
        assert b"\r\n" not in fh.read()
    text = _read(P.write_pack(_ctx()))
    day = text.split("## On the day\n", 1)[1].split("\n## ", 1)[0]
    assert "14 Example Quay, Warrington" in day and "09:15" in day
    assert "FILL IN: which entrance" in day and "FILL IN: which floor" in day
    assert "FILL IN: what is the address" not in day
    assert "The forecast slides on paper" in day and "Not confirmed yet" in day
    for part in ("**Wear:**", "**A whiteboard or a paper case:**", "**The last five minutes:**",
                 "**After:**", "**The day, in order:**"):
        assert part in day
    # Confirmed, it says so, and the page's logistics carry it.
    with redirect_stdout(io.StringIO()):
        assert P.main(["logistics", COMPANY, "--role", ROLE, "--stage", "Technical interview",
                       "--confirmed", "--today", "2026-03-11"]) == 0
    held = R.load_logistics(app, "Technical interview")
    assert held["confirmed"] and held["address"] == "14 Example Quay, Warrington"
    stage = {"label": "Technical interview", "date": "2026-03-14", "with": "Shirin Example"}
    rnd = R.build(app, _read(P.living_path(_ctx())), stage, ROW, "int-x", [],
                  dt.datetime(2026, 3, 11, tzinfo=dt.timezone.utc))
    assert rnd["in_person"] is True and set(rnd["logistics"]) == set(DAY_KEYS)
    assert rnd["logistics"]["confirmed"] is True and rnd["logistics"]["entrance"] is None
    assert rnd["readiness"]["logistics_confirmed"] is True


def test_the_next_pack_starts_from_the_cards_that_were_shaky(app, mirror):  # noqa: F811
    text = _read(P.write_pack(_ctx()))
    asked = [q["question"] for q in P.practice(text)["questions"]]
    iid = R.interview_id(COMPANY, ROLE)
    missed_q, shaky_q = asked[-1], asked[-2]
    for q, mark in ((missed_q, "missed"), (shaky_q, "shaky"), (asked[0], "got")):
        cid = R.card_id(iid, q)
        _keep(mirror, cid, {"card": cid, "interview": iid,
                            "marks": [_mark("2026-03-10T09:00:00Z", mark)]})
    qs = P.likely_questions(_ctx())
    assert [q["question"] for q in qs[:2]] == [shaky_q, missed_q]
    assert "shaky" in qs[0]["why"] and "missed" in qs[1]["why"]
    # Rebuilt, the document leads with them too.
    rebuilt = P.practice(_read(P.write_pack(_ctx())))["questions"]
    assert [q["question"] for q in rebuilt[:2]] == [shaky_q, missed_q]


# ------------------------------------------------------------------ the brief

def test_the_brief_says_each_rounds_readiness_in_one_line(app, mirror, monkeypatch):  # noqa: F811
    import brief
    P.write_pack(_ctx())
    tracker = [dict(ROW)]
    lines = R.brief_lines(tracker, dt.date(2026, 3, 11), docs=[])
    assert len(lines) == 1 and "\n" not in lines[0]
    assert lines[0].startswith("Fernhill Freight, Technical interview on Sat 14 Mar: 0% ready. "
                               "Next: Go through your ")
    # A round already held, or none booked, says nothing.
    assert R.brief_lines(tracker, dt.date(2026, 3, 20), docs=[]) == []
    # The brief itself carries it, in the message and the record. Its tracker is this test's
    # (open_actions names the file once, when first imported, maybe by another test).
    import csv_store
    import open_actions
    import person
    monkeypatch.setattr(open_actions, "_tracker", lambda path=None: csv_store.tracker(
        person.state("job_search_tracker.csv")))
    b = brief.gather(dt.date(2026, 3, 11))
    assert b["readiness"] == lines
    assert lines[0] in "\n".join(brief.message_lines(b))
    assert "- " + lines[0] in brief.record_text(b)
