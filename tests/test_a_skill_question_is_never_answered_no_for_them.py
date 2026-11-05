"""A skill question nobody answered is never a no: it waits on the person, once, for everyone.

Drafting chats running at the same time each asked the person about a skill a posting named
that their profile does not list, each kept the answer with its own pick, and a chat with
nobody there to answer recorded "no" so it could carry on: one resume recorded no to a skill
and another yes two hours later (the maintainer, 2026-11-04). Now the answer is one record per
skill (tools/skill_answers.py), every chat reads it, an unanswered question is put to the
person once on their page while the draft waits on it without the skill, the later explicit
answer wins (merged by its date between two chats), and a yes redoes every resume drafted that
day by itself. Every person and employer here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import page_db  # noqa: E402
import person  # noqa: E402
import skill_answers  # noqa: E402
import stage_picks  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import KESTREL  # noqa: E402
from test_a_tweak_changes_one_thing_and_keeps_its_word import Tweaks  # noqa: E402

POSTING = "You will build Looker dashboards and demand forecasts in SQL and Python."
DRAFT = {"company": "Kestrel Mutual", "role": "Operations Analyst", "summary": "s",
         "p1": "a.", "p2": "b.", "lead": "c", "cl_bullets": [], "p4": "d."}


def _stage(round_dir, company, title="Operations Analyst", posting=POSTING):
    row = {"company": company, "title": title, "url": "u", "portal": "pasted", "desc": posting}
    return stage_picks.stage(str(round_dir), ["1"], rows=[], root=str(round_dir),
                             shortlist=[row])[0]


def _at(hour):
    return dt.datetime(2026, 11, 4, hour, 0, tzinfo=dt.timezone.utc)


# ------------------------------------------------------------------ one question, never a no


def test_two_chats_drafting_at_once_put_one_question_to_the_person_and_neither_says_no(
        tmp_path, monkeypatch):
    monkeypatch.setattr(stage_picks, "_held_back", lambda *a, **k: "")
    a = _stage(tmp_path / "chat_a", "Kestrel Mutual")
    b = _stage(tmp_path / "chat_b", "Wrenfield Insurance")
    for p in (a, b):
        # Drafted without it meanwhile, and waiting on the person: never a no for them.
        assert p["skills_waiting"] == ["Looker"] and not p.get("skills_no")
        assert stage_picks.blocked(p) == [] and stage_picks.waits_on(p) == ["Looker"]
    (asked,) = skill_answers.open_questions()
    assert asked["skill"] == "Looker"
    assert {x["company"] for x in asked["for"]} == {"Kestrel Mutual", "Wrenfield Insurance"}
    # Put to them once on their page, for both applications, with two answers of one weight.
    targets: dict = {}
    (card,) = app_model._skill_questions(None, targets)
    assert card["id"] == "q-skill-looker" and card["kind"] == "consent"
    assert card["title"].count("?") == 1 and "?" not in card["body"]
    assert "Kestrel Mutual and Wrenfield Insurance ask for it" in card["body"]
    assert [o["value"] for o in card["options"]] == ["yes", "no"]
    assert targets[card["id"]] == {"kind": "skill_ask", "skill": "Looker", "rev": card["rev"]}
    # Assembled while nobody has answered: kept on the draft as waiting, never as declined.
    (tmp_path / "chat_a" / f"audit_{a['slug']}.json").write_text(
        json.dumps({"verdict": "pass", "draft": DRAFT, "changes": [], "residual_risks": []}),
        encoding="utf-8")
    (d,) = stage_picks.assemble(str(tmp_path / "chat_a"))[0]
    assert d["waiting_skills"] == ["Looker"] and "declined_skills" not in d
    assert skill_answers.answer("Looker") == ""


def test_the_later_explicit_answer_wins_and_only_the_person_answers(tmp_path):
    with pytest.raises(ValueError):
        skill_answers.record("Looker", "not sure")
    assert skill_answers.record("Looker", "no", by="chat", at=_at(12), profile=False)
    # A tap on the page made before that, applied after it: the chat's later answer stands.
    assert not skill_answers.record("Looker", "yes", by="page", at=_at(11), profile=False)
    assert skill_answers.answer("Looker") == "no"
    # An explicit no stays a no: the next posting that asks takes it, and asks nothing.
    p = _stage(tmp_path / "r1", "Kestrel Mutual")
    assert p["skills_no"] == ["Looker"] and not p.get("skills_waiting")
    assert stage_picks.question(p) == ""
    assert skill_answers.record("Looker", "yes", by="page", at=_at(13), profile=False)
    p = _stage(tmp_path / "r2", "Wrenfield Insurance")
    assert p["skills_yes"] == ["Looker"] and not p.get("skills_no")
    assert skill_answers.open_questions() == []
    # Spelled another way, it is the same skill.
    assert skill_answers.answer("looker ") == "yes" and skill_answers.key("Big Query") == \
        skill_answers.key("BigQuery")


def test_a_chat_with_a_skill_the_tool_missed_puts_it_to_the_person_instead_of_saying_no(
        tmp_path):
    p = _stage(tmp_path, "Kestrel Mutual")
    got = stage_picks.consent(str(tmp_path), p["slug"], ask=["Snowflake"])
    assert "Snowflake" in got["ask_first"] and "Snowflake" in got["skills_waiting"]
    assert not got.get("skills_no")
    assert {q["skill"] for q in skill_answers.open_questions()} == {"Looker", "Snowflake"}
    # Their own answer, given in this chat, is everyone's.
    got = stage_picks.consent(str(tmp_path), p["slug"], yes=["Snowflake"])
    assert got["skills_yes"] == ["Snowflake"] and "Snowflake" not in got["skills_waiting"]
    assert skill_answers.answer("Snowflake") == "yes"


# ------------------------------------------------------------------ two chats, two branches


@pytest.fixture
def repo(tmp_path, monkeypatch):
    from test_two_chats_writing_the_page_files_merge_key_by_key import Repo
    r = Repo(tmp_path, monkeypatch)
    yield r
    person.reset()


def _two_chats(repo, base, theirs, ours):
    with open(os.path.join(repo.root, "README"), "w", encoding="utf-8") as fh:
        fh.write("a copy\n")
    base()
    repo.commit("base")
    repo.side("other", new=True)
    theirs()
    repo.commit("theirs", when="2026-11-04T15:00:00Z")
    repo.side("master")
    ours()
    repo.commit("ours", when="2026-11-04T11:00:00Z")
    r = repo.merge()
    return r, r.stdout + r.stderr


def _merged(repo):
    with open(os.path.join(repo.root, "documents", "skill_answers.json"), encoding="utf-8") as fh:
        text = fh.read()
    assert text == json.dumps(json.loads(text), indent=1, sort_keys=True,
                              ensure_ascii=False) + "\n"
    return json.loads(text)["skills"]["looker"]


def test_two_chats_answering_on_two_branches_keep_the_later_answer(repo):
    r, said = _two_chats(
        repo, lambda: skill_answers.ask("Looker", "Kestrel Mutual", "Analyst", day="2026-11-04"),
        lambda: (skill_answers.ask("Looker", "Wrenfield Insurance", "Analyst", day="2026-11-04"),
                 skill_answers.record("Looker", "yes", at=_at(15), profile=False)),
        lambda: skill_answers.record("Looker", "no", at=_at(11), profile=False))
    assert r.returncode == 0, said
    got = _merged(repo)
    assert got["answer"]["said"] == "yes" and got["answer"]["at"] == "2026-11-04T15:00:00Z"
    assert {x["company"] for x in got["for"]} == {"Kestrel Mutual", "Wrenfield Insurance"}


def test_a_chat_that_only_asked_never_undoes_the_answer_another_chat_took(repo):
    r, said = _two_chats(
        repo, lambda: None,
        lambda: skill_answers.record("Looker", "yes", at=_at(10), profile=False),
        lambda: skill_answers.ask("Looker", "Kestrel Mutual", "Analyst", day="2026-11-04",
                                  at=_at(16)))
    assert r.returncode == 0, said
    got = _merged(repo)
    assert got["answer"]["said"] == "yes"
    assert got["for"][0]["company"] == "Kestrel Mutual"


# ------------------------------------------------------------------ a yes redoes today's resumes


@pytest.fixture
def t(tmp_path):
    return Tweaks(str(tmp_path))


def _asked_today(t, day="2026-10-25", **draft):
    """Looker asked about by the Kestrel Mutual draft (tests/app_state.py), drafted `day`."""
    with open(os.path.join(t.folder, "draft.json"), encoding="utf-8") as fh:
        apps = json.load(fh)
    apps[0].update(draft)
    with open(os.path.join(t.folder, "draft.json"), "w", encoding="utf-8") as fh:
        json.dump(apps, fh)
    os.makedirs(os.path.join(t.state, "documents"), exist_ok=True)
    with open(os.path.join(t.state, "documents", "skill_answers.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"skills": {"looker": {"skill": "Looker", "asked": "2026-10-25T09:00:00Z",
                                         "for": [{"company": "Kestrel Mutual",
                                                  "role": "Claims Forecasting Analyst",
                                                  "day": day}]}}}, fh)


def _py(t, code):
    return t.python("import sys, json; sys.path[:0] = ['tools', 'tools/network', 'templates']\n"
                    + code)


def _answers(t):
    return json.loads(_py(t, "import skill_answers; print(json.dumps(skill_answers.load()))"))


def test_a_yes_on_the_page_redoes_every_resume_drafted_that_day_by_itself(t):
    # A chat recorded no for this one before the rule: the person's yes still redoes it.
    _asked_today(t, declined_skills=["Looker"])
    card = t.item("q-skill-looker")
    assert card["title"] == "Can you claim Looker and back it up in an interview?"
    assert card["about"] == {"company": "Kestrel Mutual"}
    assert app_model.check(t.model()) == []
    aid = t.act("needs.answer", "q-skill-looker", "yes")
    got = t.apply()
    assert got["ok"] == [aid], got
    assert "Claude puts it on the resume drafted today" in t.receipt(aid)["note"]
    wid = skill_answers.work_id(KESTREL, "Looker")
    with open(page_db.body_path(os.path.join(t.dump, "out"), "work", wid), encoding="utf-8") as fh:
        work = json.load(fh)
    assert work["kind"] == "tweak" and work["status"] == "queued"
    assert work["args"]["target"] == {"id": KESTREL, "output": "resume"}
    assert work["args"]["changes"] == [{"p": "yes", "v": {"skill": "Looker"}}]
    # The chat that answers the page runs it as any tweak: code alone, checked again.
    done = t.tweak("apply", "resume", KESTREL, work["args"]["changes"])
    assert done["status"] == "done", done
    d = t.draft()
    assert d["consented_skills"] == ["Looker"] and "declined_skills" not in d
    assert t.renders() == 1
    assert _answers(t)["skills"]["looker"]["answer"]["said"] == "yes"
    # Asked no more, and nothing left to redo.
    assert not [n for n in t.model()["needs_you"] if n["id"] == "q-skill-looker"]
    assert "Nothing to redo" in _py(t,
        "import skill_answers; skill_answers.main(['redo', '--today', '2026-10-25'])")


def test_a_yes_redoes_only_the_resumes_drafted_that_day(t):
    _asked_today(t, day="2026-10-24", waiting_skills=["Looker"])
    aid = t.act("needs.answer", "q-skill-looker", "yes")
    assert t.apply()["ok"] == [aid]
    assert not os.path.exists(page_db.body_path(os.path.join(t.dump, "out"), "work",
                                                skill_answers.work_id(KESTREL, "Looker")))
    assert "Claude puts it" not in t.receipt(aid)["note"]


def test_a_yes_a_chat_took_is_put_on_todays_resumes_by_the_next_chat_that_looks(t):
    _asked_today(t, waiting_skills=["Looker"])
    # The yes was given in another chat; this copy has its record now, and a resume drafted
    # today without it. Bringing the page up to date says to redo it, unasked.
    _py(t, "import skill_answers; skill_answers.record('Looker', 'yes', profile=False)")
    view = json.loads(t.run("view", os.path.join(t.dump, "view_out"), "--now",
                            "2026-10-25T18:00:00Z"))
    line = " ".join(view.get("for_claude") or [])
    assert "Kestrel Mutual (Looker)" in line and "skill_answers.py redo" in line
    out = _py(t, "import skill_answers; skill_answers.main(['redo', '--today', '2026-10-25'])")
    assert "Kestrel Mutual, Claims Forecasting Analyst: redone with Looker." in out
    d = t.draft()
    assert d["consented_skills"] == ["Looker"] and "waiting_skills" not in d
    # Done once, never again.
    assert "Nothing to redo" in _py(t,
        "import skill_answers; skill_answers.main(['redo', '--today', '2026-10-25'])")


def test_ive_used_it_too_on_the_panel_puts_it_on_the_resume_and_answers_it_for_every_one(t):
    # The page's "I've used Tableau too" was refused as no change at all.
    got = t.tweak("apply", "resume", KESTREL,
                  [{"p": "near", "v": {"asked": "Tableau", "have": "Power BI", "used": True}}])
    assert got["status"] == "done", got
    assert t.draft()["consented_skills"] == ["Tableau"]
    assert _answers(t)["skills"]["tableau"]["answer"]["said"] == "yes"
