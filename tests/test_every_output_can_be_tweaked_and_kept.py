"""Every output can be tweaked, a tweak can be kept for next time, and both can be taken back.

TWEAKS.md (2026-10-25), the rows a release promises: a letter's length, how full the page
is and how many skills show, a note's formality, the search's settings (through the
person's own setting files, a screening change lapsing the rulings made under the old
one), the interview pack and the brief. "Keep this for next time" writes the setting its
row names and a learned rule; an offer of a usual is answered once and asked again after
a month; several tweaks queued on one output run as one job; the one-time hint is seen
once. LaTeX is stood in for. Every person and employer here is invented.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import page_db  # noqa: E402
import tweak  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import KESTREL, NOW  # noqa: E402
from test_a_tweak_changes_one_thing_and_keeps_its_word import Tweaks, _compose_pell  # noqa: E402

THORNBURY = "int-thornbury_bank_risk_analyst"


@pytest.fixture
def t(tmp_path):
    return Tweaks(str(tmp_path))


def _py(t, code):
    return t.python("import sys, json; sys.path[:0] = ['tools', 'tools/network', 'templates']\n" + code)


def _person(t):
    with open(os.path.join(t.profile, "person.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _search(t):
    with open(os.path.join(t.profile, "search.py"), encoding="utf-8") as fh:
        return fh.read()


# ------------------------------------------------------------------ the table is whole


def test_the_table_has_every_row_the_release_promises():
    want = {"R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "L1", "L2", "L4", "L5",
            "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "J1", "J2", "J3", "J4", "J5", "J6", "J7",
            "J8", "J9", "J10", "J11", "J12", "I1", "I2", "I3", "I4", "I5", "B1", "B2", "B3",
            "B4", "B5", "P1", "P2", "P3", "P5"}
    assert set(tweak.BY_P) == want
    hows = {r["how"] for r in tweak.TWEAKS}
    assert hows == {"design", "style", "bullets", "fill", "skills", "letter_length",
                    "contact_person", "parts", "redraft", "search", "pack", "brief", "page"}
    # The work-rights news is never offered as off, and Owed is never a part to hide.
    assert "rights" not in tweak.BY_P["B3"]["values"]
    assert "owed" not in tweak.BY_P["B5"]["values"]


# ------------------------------------------------------------------ documents


def test_the_letters_length_the_pages_fill_and_the_skills_line_are_code(t):
    got = t.tweak("apply", "letter", KESTREL, [{"p": "L1", "v": "short"}])
    assert got["status"] == "done" and t.draft()["max_words"] == 205
    got = t.tweak("apply", "resume", KESTREL, [{"p": "R7", "v": "space"}, {"p": "R9", "v": "fewer"}])
    assert got["status"] == "done"
    d = t.draft()
    assert (d["fill"], d["skills_max"]) == ("space", "fewer")
    longer = t.tweak("apply", "letter", KESTREL, [{"p": "L1", "v": "full"}])
    assert longer["status"] == "needs_model"
    out = _py(t, "import fit_to_page, skills_block\n"
                 "print(fit_to_page.letter_words({'max_words': 205}), "
                 "fit_to_page.letter_words({'max_words': 150}), fit_to_page.letter_words({}), "
                 "skills_block.size_for({'skills_max': 'fewer'}), skills_block.size_for({}))")
    assert out.split() == ["205", "205", "250", "12", "18"]          # never under 205 words


def test_keep_for_next_time_writes_the_setting_and_a_rule_and_undo_takes_both_back(t):
    got = t.tweak("apply", "resume", KESTREL, [{"p": "R1", "v": "classic"}, {"p": "R5", "v": "navy"}],
                  keep={"scope": "kind:bank"})
    assert got["status"] == "done" and "Kept as your usual" in got["summary"]
    docs = _person(t)["documents"]
    assert docs["designs"]["kinds"]["bank"] == "classic" and docs["styles"]["kinds"]["bank"] == "navy"
    rules = json.loads(_py(t, "import learned; print(json.dumps(learned.load()))"))
    assert rules[-1]["via"] == "page tweak" and rules[-1]["status"] == "active"
    assert "person.json documents designs kinds bank" in rules[-1]["applied_to"]
    assert t.model()["tweaks"]["rules"]["resume"][0]["rule"] == rules[-1]["rule"]
    back = t.tweak("undo", "resume", KESTREL, undo=got["key"])
    assert back["status"] == "done"
    docs = _person(t).get("documents", {})
    assert "bank" not in (docs.get("designs") or {}).get("kinds", {})
    rules = json.loads(_py(t, "import learned; print(json.dumps(learned.load()))"))
    assert rules[-1]["status"] == "retired"


# ------------------------------------------------------------------ a note's formality


def test_a_note_made_formal_keeps_every_rule_or_offers_the_nearest_that_does(t):
    _compose_pell(t)
    (msg,) = t.model()["messages"]
    got = t.tweak("apply", "message", msg["id"], [{"p": "M2", "v": "formal"}])
    # "Hope you are well" reads as a stock phrase: refused, with the nearest that keeps
    # the rule, one plain line why, and nothing written.
    assert got["status"] == "refused" and "stock phrase" in got["summary"], got
    near = got["nearest"]
    assert {"p": "M3", "v": "none"} in near["changes"] and "I am looking" in near["text"]
    assert t.model()["messages"][0]["text"] == msg["text"]
    done = t.tweak("apply", "message", msg["id"], near["changes"])
    assert done["status"] == "done", done
    after = t.model()["messages"][0]
    assert after["text"] == near["text"] and after["parts"] is True
    # A later part change keeps the register it was given.
    t.tweak("apply", "message", after["id"], [{"p": "M5", "v": "me_first"}])
    assert "I am looking" in t.model()["messages"][0]["text"]
    redraft = t.tweak("apply", "message", after["id"], [{"p": "M7", "v": "warmer"}])
    assert redraft["status"] == "needs_model"


def test_a_tweak_never_tells_a_peer_what_only_a_recruiter_may_hear(t):
    _compose_pell(t)
    (msg,) = t.model()["messages"]
    got = t.tweak("apply", "message", msg["id"], [{"p": "M6", "v": "work_auth:on"}])
    assert got["status"] == "refused"
    assert got["summary"] == "Pell is a peer: a first note to a peer never states your work rights."
    assert got["nearest"]["changes"] == [] and got["nearest"]["text"] == msg["text"]
    ask = t.tweak("apply", "message", msg["id"], [{"p": "M4", "v": "another"}])
    assert ask["status"] == "refused" and ask["nearest"]["changes"] == [{"p": "M4", "v": "pointer"}]
    assert "speak to" in ask["nearest"]["text"]


# ------------------------------------------------------------------ the search


def test_a_search_window_runs_once_or_is_kept(t):
    once = t.tweak("apply", "jobs", "jobs", [{"p": "J6", "v": "7"}])
    assert once["status"] == "done" and once["then"] == [
        {"kind": "search", "title": "Finding jobs", "args": {"jobage": 7}}]
    assert "JOB_AGE_DAYS" not in _search(t)
    kept = t.tweak("apply", "jobs", "jobs", [{"p": "J6", "v": "30"}], keep={"scope": "all"})
    assert kept["status"] == "done" and "JOB_AGE_DAYS = 30" in _search(t)
    assert _py(t, "import run_round; print(run_round._job_age_days())").strip() == "30"
    assert t.tweak("undo", "jobs", "jobs", undo=kept["key"])["status"] == "done"
    assert "JOB_AGE_DAYS" not in _search(t)


def test_a_place_added_is_searched_and_kept_and_the_rulings_under_the_old_place_lapse(t):
    before = _search(t)
    got = t.tweak("apply", "jobs", "jobs", [{"p": "J7", "v": {"add": "Wigan, England, United Kingdom"}}])
    assert got["status"] == "done", got
    now = _search(t)
    assert '"Wigan, England, United Kingdom"' in now
    kept = json.loads(_py(t, "import tweak, profile_set\n"
                             "metro, _out = tweak._location_names()\n"
                             "print(json.dumps(profile_set.get('search.py', metro)))"))
    assert "wigan" in kept                                          # the location filter keeps it
    assert got["then"][0]["kind"] == "search"
    assert t.tweak("undo", "jobs", "jobs", undo=got["key"])["status"] == "done"
    assert _search(t) == before                                     # byte for byte


def test_a_title_the_filter_would_drop_is_refused_and_a_pay_floor_keeps_the_cut_line(t):
    no = t.tweak("apply", "jobs", "jobs", [{"p": "J8", "v": {"add": "Head Chef"}}])
    assert no["status"] == "refused" and "title filter" in no["summary"]
    yes = t.tweak("apply", "jobs", "jobs", [{"p": "J8", "v": {"add": "Planning Analyst"}}])
    assert yes["status"] == "done" and '"Planning Analyst"' in _search(t)
    low = t.tweak("apply", "jobs", "jobs", [{"p": "J12", "v": 20000}])
    assert low["status"] == "refused" and "cut line" in low["summary"]
    ok = t.tweak("apply", "jobs", "jobs", [{"p": "J12", "v": 45000}])
    assert ok["status"] == "done" and "SALARY_FLOOR = 45000" in _search(t)
    same = t.tweak("apply", "jobs", "jobs", [{"p": "J12", "v": 45000}])
    assert same["status"] == "cached"


def test_an_employer_to_watch_and_a_site_switched_off(t):
    got = t.tweak("apply", "jobs", "jobs", [{"p": "J9", "v": "Larkspur Retail"}])
    assert got["status"] == "done" and '"Larkspur Retail"' in _search(t)
    board = got["then"][0]
    assert board["kind"] == "research" and board["title"].startswith("Find Larkspur Retail")
    assert board["args"] == {"topic": "employers", "employer": "Larkspur Retail"}
    off = t.tweak("apply", "jobs", "jobs", [{"p": "J10", "v": {"freehire-search": False}}])
    assert off["status"] == "done" and '"freehire-search": False' in _search(t)


# ------------------------------------------------------------------ the interview pack


def test_the_pack_shows_less_and_is_built_again(t):
    folder = os.path.join(t.state, "documents", "applications", "thornbury_bank_risk_analyst_thornbury")
    os.remove(os.path.join(folder, "interview_prep.md"))
    got = t.tweak("apply", "interview", THORNBURY, [{"p": "I3", "v": ["Small talk", "The company"]}])
    assert got["status"] == "done", got
    assert _person(t)["prep"]["hide"] == ["Small talk", "The company"]
    text = open(os.path.join(folder, "interview_prep.md"), encoding="utf-8").read()
    assert "## Small talk" not in text and "## Your answers" in text
    never = t.tweak("apply", "interview", THORNBURY, [{"p": "I3", "v": ["Money and eligibility"]}])
    assert never["status"] == "refused"
    staged = t.tweak("apply", "interview", THORNBURY, [{"p": "I1", "v": {"format": "technical"}}])
    assert staged["status"] == "done" and "technical" in staged["summary"]
    drafts = t.tweak("apply", "interview", THORNBURY, [{"p": "I5", "v": "1"}])
    assert drafts["status"] == "needs_model", drafts
    pkt = json.load(open(drafts["packet"], encoding="utf-8"))
    assert len(pkt["questions"]) == 1 and pkt["drafts"] and pkt["words"] == 300
    # The model writes the one answer; anything else changed is refused and put back.
    path = os.path.join(folder, "interview_prep.md")
    text = open(path, encoding="utf-8").read()
    q = pkt["questions"][0]
    head = f"### {q}"
    start = text.index(head)
    end = text.index("\n### ", start + 1) if "\n### " in text[start + 1:] else text.index("\n## ", start)
    answer = (f"{head}\n{pkt['write'].split('the line ')[1].split(chr(34))[1]}\n"
              "I built the pricing model that the team used every week, and I walked the "
              "commercial lead through what it meant before each review.\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text[:start] + answer + text[end:] + "\nA stray line.\n")
    bad = t.tweak("merge", "interview", THORNBURY, [{"p": "I5", "v": "1"}], round=drafts["round"])
    assert bad["status"] == "refused" and "More changed" in bad["summary"]
    assert open(path, encoding="utf-8").read() == text
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text[:start] + answer + text[end:])
    ok = t.tweak("merge", "interview", THORNBURY, [{"p": "I5", "v": "1"}], round=drafts["round"])
    assert ok["status"] == "done", ok
    assert "marked Draft" in ok["summary"]
    assert t.tweak("undo", "interview", THORNBURY, undo=ok["key"])["status"] == "done"
    assert open(path, encoding="utf-8").read() == text


# ------------------------------------------------------------------ the brief


def test_the_brief_is_shorter_shows_less_news_and_never_drops_the_work_rights_watch(t):
    got = t.tweak("apply", "brief", "brief", [{"p": "B1", "v": "short"}, {"p": "B2", "v": "1"},
                                               {"p": "B3", "v": {"targets": False}},
                                               {"p": "B5", "v": ["tip"]}])
    assert got["status"] == "done", got
    b = _person(t)["brief"]
    assert (b["length"], b["news"], b["leave_out"], b["hide"]) == ("short", 1, ["targets"], ["tip"])
    lines = json.loads(_py(t, "import brief\n"
                              "b = {'weekday': 'Mon', 'counts': {'owed': 5, 'applications': 1, "
                              "'interviews': 0}, 'lead': 'x', 'owed': [{'text': str(i)} for i in "
                              "range(5)], 'set_aside': [], 'since_counts': {'sent': 0, 'replies': 0, "
                              "'interviews': 0, 'offers': 0, 'rejections': 0}, 'since': '2026-10-20', "
                              "'lines': [], 'next_three': ['a'], 'url': '', 'tip': 'A tip.'}\n"
                              "print(json.dumps(brief.message_lines(b, 2)))"))
    assert "A tip." not in lines and "<NEWS>" in lines
    rights = t.tweak("apply", "brief", "brief", [{"p": "B3", "v": {"rights": False}}])
    assert rights["status"] == "refused"


def test_the_briefs_days_and_time_change_the_schedule_and_name_the_call_to_make(t):
    got = t.tweak("apply", "brief", "brief", [{"p": "B4", "v": {"days": [2, 5], "time": "08:10"}}])
    assert got["status"] == "done", got
    reg = json.load(open(os.path.join(t.profile, "routines.json"), encoding="utf-8"))
    cron = next(r for r in reg["routines"] if r["key"] == "morning_brief")["cron"]
    assert cron.endswith(" 10 8 * * 2,5")
    assert got["tools"] == [{"name": "update_trigger", "trigger_id": "trig_EXAMPLEBRIEF",
                             "cron_expression": cron}]
    bad = t.tweak("apply", "brief", "brief", [{"p": "B4", "v": {"days": [2], "time": "8am"}}])
    assert bad["status"] == "refused"


# ------------------------------------------------------------------ offers, hints, one job


def test_an_offer_is_answered_on_the_page_and_a_not_now_waits_a_month(t):
    for day in ("2026-10-02", "2026-10-09", "2026-10-21"):
        _py(t, f"import learned; learned.skip('make it shorter', 'one-off', today='{day}', "
               "via='page tweak', output='message')")
    q = next(n for n in t.model()["needs_you"] if n["id"].startswith("q-tweak-"))
    assert q["title"] == "You ask for length: brief a lot. Make it your usual?"
    aid = t.act("tweak.offer", q["id"], value="no")
    got = t.apply()
    assert got["ok"] == [aid], [t.receipt(aid)]
    assert t.receipt(aid)["note"] == "No problem, I'll ask again in a month."
    assert not any(n["id"] == q["id"] for n in t.model()["needs_you"])
    def offered(day):
        return json.loads(_py(t, "import tweak, datetime; print(json.dumps([o['id'] for o in "
                                 f"tweak.promote(datetime.date{day})]))"))
    oid = q["id"][len("q-tweak-"):]
    assert oid not in offered((2026, 11, 19)) and oid in offered((2026, 11, 25))  # 30 days on


def test_the_hint_is_seen_once_on_any_device(t):
    assert t.model()["hints"] == {"tweak": False}
    aid = t.act("hint.seen", "hint-tweak", value={"hint": "tweak"}, rev="")
    assert t.apply()["ok"] == [aid]
    assert t.model()["hints"] == {"tweak": True}


def test_tweaks_queued_on_one_output_run_as_one_job():
    import app_model
    now = app_model.parse_time(NOW)
    def item(changes, at):
        return {"kind": "tweak", "status": "queued", "asked_at": at, "to": "either",
                "args": {"target": {"id": KESTREL, "output": "resume", "company": "Kestrel Mutual"},
                         "changes": changes}}
    db = {"work": {"t1": {"data": item([{"p": "R1", "v": "classic"}], "2026-10-25T10:00:00Z"), "version": 1},
                   "t2": {"data": item([{"p": "R5", "v": "navy"}], "2026-10-25T10:01:00Z"), "version": 2}},
          "locks": {}, "chats": {}}
    got = page_db.next_item(db, "cloud", now)
    assert got["work"] == "t1" and got["with"] == [{"work": "t2", "version": 2}]
    merged = tweak.merge_works([db["work"]["t1"]["data"], db["work"]["t2"]["data"]])
    assert [c["p"] for c in merged["args"]["changes"]] == ["R1", "R5"]


def test_two_claimed_tweaks_are_applied_with_one_render(t):
    works = []
    for n, change in enumerate(([{"p": "R1", "v": "modern"}], [{"p": "R5", "v": "teal"}])):
        path = os.path.join(t.dump, f"w{n}.json")
        os.makedirs(t.dump, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"kind": "tweak", "args": {"target": {"id": KESTREL, "output": "resume"},
                                                 "changes": change}}, fh)
        works += ["--work", path]
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "tweak.py"), "apply", *works],
                       env=t.env(), capture_output=True, encoding="utf-8", timeout=300)
    got = json.loads(r.stdout)
    assert got["status"] == "done" and t.renders() == 1
    assert (t.draft()["design"], t.draft()["style"]) == ("modern", "teal")
