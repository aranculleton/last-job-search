"""The person's own LinkedIn profile, looked over now and then for what would stop people
replying, and never every run.

The person asked for it in these terms: not always, only a genuine red flag or a reason
for people not to reply, never nitpicks, done once, or again when the rest of the profile
moves on, and never something that runs on every networking run and wastes tokens. So
`due` is plain Python that prints nothing until a look is worth it, `check` is mechanical,
and only what is left for judgement goes to a model, in a short brief. Every name and
profile here is the example person's or invented (tests/fixtures/linkedin_export).
"""
import copy
import datetime
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import learned  # noqa: E402
import own_profile as O  # noqa: E402
import person  # noqa: E402
import profile_upgrades as U  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "linkedin_export"
TODAY = datetime.date(2026, 10, 21)


@pytest.fixture
def profile(tmp_path, monkeypatch):
    """A copy of the example person with no answer on file about their own profile."""
    d = tmp_path / "profile"
    shutil.copytree(ROOT / "profile.example", d)
    asked = json.loads((d / "asked.json").read_text(encoding="utf-8"))
    asked.pop(O.UID, None)
    (d / "asked.json").write_text(json.dumps(asked), encoding="utf-8")
    st = tmp_path / "state"
    shutil.copytree(ROOT / "profile.example" / "state", st)
    monkeypatch.setenv(person.ENV, str(d))
    monkeypatch.setenv(person.STATE_ENV, str(st))
    person._modules.clear()
    person._data.clear()
    yield d
    person._modules.clear()
    person._data.clear()


def _clean():
    return O.from_export(str(FIX))


def _looked(days_ago, p=None):
    p = p or _clean()
    return O.record(p, O.check(p, TODAY), today=TODAY - datetime.timedelta(days=days_ago))


def _ids(p, answers=None):
    return [f["id"] for f in O.check(p, TODAY, answers=answers or {})["findings"]]


def _add_to_profile(profile_dir, text):
    path = profile_dir / "01-candidate-profile.md"
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


# ------------------------------------------------------------ due: free, and rarely

def test_it_is_due_once_when_never_looked_over_and_a_no_holds_for_a_month(profile):
    line = O.due(TODAY, [], [])
    assert line.startswith("Own LinkedIn profile: worth a look (never looked over).")
    assert O.ASK in line and "--no own-profile-review" in line
    U.record_no(O.UID, TODAY)
    assert O.due(TODAY, [], []) == ""
    assert O.due(TODAY + datetime.timedelta(days=U.REASK_DAYS), [], [])  # asked once more


def test_it_stays_silent_when_nothing_changed(profile, capsys):
    _looked(40)
    assert O.due(TODAY, [], []) == ""
    assert O.main(["due", "--today", TODAY.isoformat()]) == 0
    assert capsys.readouterr().out == ""                  # nothing printed costs nothing


def _snapshot(root):
    # The test state only (a temporary copy), walked by hand: tests/test_repo_files.py keeps
    # recursive globs for the repo itself going through repo_files.
    out = {}
    for d, _, names in os.walk(root):
        for n in names:
            with open(os.path.join(d, n), "rb") as fh:
                out[os.path.join(d, n)] = fh.read()
    return out


def test_due_reads_and_never_writes(profile):
    st = person.state()
    before = _snapshot(st)
    assert O.due(TODAY)                                   # never looked over
    assert _snapshot(st) == before


def test_a_changed_current_role_makes_it_due(profile):
    _looked(40)
    roles = profile / "roles.py"
    roles.write_text(roles.read_text(encoding="utf-8").replace(
        'title="Senior Operations Analyst"', 'title="Lead Operations Analyst"'), encoding="utf-8")
    person._modules.clear()
    line = O.due(TODAY, [], [])
    assert "changed since the last look: your current role" in line and O.ASK_AGAIN in line


def test_never_more_than_once_in_thirty_days(profile):
    _looked(10)
    roles = profile / "roles.py"
    roles.write_text(roles.read_text(encoding="utf-8").replace(
        'title="Senior Operations Analyst"', 'title="Lead Operations Analyst"'), encoding="utf-8")
    person._modules.clear()
    assert O.due(TODAY, [], []) == ""
    assert O.due(TODAY + datetime.timedelta(days=O.CAP_DAYS - 10), [], [])


def _notes(n, start=datetime.date(2026, 9, 1)):
    contacts, threads = [], []
    for i in range(n):
        cid = f"acme_person{i}"
        contacts.append({"contact_id": cid, "name": f"Person {i}", "company": "Acme"})
        threads.append({"contact_id": cid, "date": (start + datetime.timedelta(days=i)).isoformat(),
                        "direction": "out", "channel": "connection",
                        "scenario": "connection_note", "summary": "first note",
                        "full_text": f"Hi {i}, I work in supply-chain analytics in Manchester."})
    return contacts, threads


def test_a_run_of_unanswered_first_notes_too_long_for_chance_makes_it_due(profile):
    # N = ceil(ln 0.05 / ln(1 - p)): 11 at the default 25%, 29 at a 10% reply rate.
    assert O.run_needed(0.25) == 11 and O.run_needed(0.10) == 29
    _looked(60)
    contacts, threads = _notes(11)
    line = O.due(TODAY, contacts, threads)
    assert "your last 11 first notes went unanswered past their nudge window" in line
    assert "less than 1 time in 20" in line
    contacts, threads = _notes(10)
    assert O.due(TODAY, contacts, threads) == ""
    # One answered among them breaks the run.
    contacts, threads = _notes(11)
    threads.append({"contact_id": "acme_person10", "date": "2026-09-14", "direction": "in",
                    "channel": "connection", "summary": "replied", "full_text": "Happy to chat."})
    assert O.due(TODAY, contacts, threads) == ""
    # Notes still inside their window are neither answered nor not.
    contacts, threads = _notes(11, start=TODAY - datetime.timedelta(days=12))
    assert O.due(TODAY, contacts, threads) == ""


def test_their_own_reply_rate_sets_the_run_once_they_have_enough_notes(profile):
    contacts, threads = _notes(20, start=datetime.date(2026, 6, 1))
    for i in range(5):
        threads.append({"contact_id": f"acme_person{i}", "date": "2026-06-25", "direction": "in",
                        "channel": "connection", "summary": "replied", "full_text": "Sure."})
    p, decided, whose = O.reply_rate(contacts, threads, TODAY)
    assert (round(p, 2), decided, whose) == (0.25, 20, "yours")
    assert O.reply_rate([], [], TODAY)[2] == "default"


# ------------------------------------------------------------ check: red flags only

def test_a_clean_profile_has_no_red_flags_and_no_nitpicks(profile):
    p = _clean()
    assert O.check(p, TODAY)["findings"] == []
    short = copy.deepcopy(p)
    short["headline"], short["skills"] = "Operations analyst", []
    assert _ids(short) == []                     # headline length and skills are not flags


def test_each_red_flag_fires_on_its_case(profile):
    base = _clean()

    def case(**changes):
        p = copy.deepcopy(base)
        for k, v in changes.items():
            p[k] = v
        return p
    assert _ids(case(location="London, England, United Kingdom")) == ["location"]
    assert _ids(case(location="")) == ["location"]
    positions = copy.deepcopy(base["positions"])
    positions[0]["finished"] = "Sep 2026"
    assert _ids(case(positions=positions))[0] == "current-role"
    positions = copy.deepcopy(base["positions"])
    positions[0]["finished"] = "Sep 2026"
    positions.insert(0, {"company": "Kestrel Mutual", "title": "Data Lead", "started": "Oct 2026",
                         "finished": "", "description": "x", "location": ""})
    assert "current-role" in _ids(case(positions=positions))
    positions = copy.deepcopy(base["positions"])
    positions[1]["title"] = "Logistics Coordinator"
    assert _ids(case(positions=positions)) == ["role:oakmere-foods"]
    positions = copy.deepcopy(base["positions"])
    positions[1]["started"] = "Jan 2020"                 # eight months off
    assert _ids(case(positions=positions)) == ["role:oakmere-foods"]
    positions[1]["started"] = "Aug 2020"                 # a month off is a typo, not a story
    assert _ids(case(positions=positions)) == []
    positions = copy.deepcopy(base["positions"])
    positions[1]["finished"] = ""                        # a job that ended, shown as current
    found = O.check(case(positions=positions), TODAY, answers={})["findings"]
    assert [f["id"] for f in found] == ["role:oakmere-foods"] and "still shows" in found[0]["what"]
    positions = copy.deepcopy(base["positions"][:2])     # on the resume, not on LinkedIn
    assert _ids(case(positions=positions)) == ["role:saltmarsh-analytics"]
    positions = copy.deepcopy(base["positions"]) + [{
        "company": "Kestrel Mutual", "title": "Data Analyst", "started": "Mar 2021",
        "finished": "Dec 2021", "description": "", "location": ""}]
    assert _ids(case(positions=positions)) == ["role-extra:kestrel-mutual"]
    thin = copy.deepcopy(base["positions"])
    for x in thin:
        x["description"] = ""
    assert _ids(case(summary="Operations analyst in Manchester.", positions=thin)) == ["thin"]
    assert _ids(case(summary="Operations analyst in Manchester.")) == []
    assert _ids(case(), answers={"photo": {"answer": "no"}}) == ["photo"]
    assert _ids(case(), answers={"photo": {"answer": "yes"}}) == []


def test_a_phrase_they_banned_on_their_profile_is_a_flag(profile):
    learned.record("documents", "never say I'm relocating, I live here", "never write relocating",
                   never_say=["relocating"], today=TODAY.isoformat())
    p = _clean()
    p["headline"] += " | relocating to Manchester"
    assert _ids(p) == ["never-say"]


def test_a_confidential_search_on_show_is_a_flag_only_when_it_is_confidential(profile):
    p = _clean()
    p["headline"] = "Open to work | Senior Operations Analyst"
    assert _ids(p) == []                                 # an open search may say so
    assert [q for q, _ in O.check(p, TODAY, answers={})["questions"]] == ["photo"]
    md = profile / "01-candidate-profile.md"
    md.write_text(md.read_text(encoding="utf-8").replace(
        "| **Notice period** |", "| **Status** | Employed. Searching confidentially. |\n"
        "| **Notice period** |"), encoding="utf-8")
    assert _ids(p) == ["confidential-visible"]
    assert [q for q, _ in O.check(p, TODAY, answers={})["questions"]] == ["photo", "open-to-work"]
    clean = _clean()
    assert _ids(clean, answers={"open-to-work": {"answer": "yes"}}) == ["confidential-open-to-work"]


def test_a_certificate_the_profile_says_is_not_held_fires_and_so_does_a_held_one_missing(profile):
    _add_to_profile(profile, "- dbt Analytics Engineering (in progress)\n\n<!-- Earlier CVs "
                             "listed Tableau Desktop Specialist (2022). That is not held and "
                             "must never be listed. -->\n")
    p = _clean()
    p["certifications"] = [{"name": "Power BI Data Analyst Associate (PL-300)"},
                           {"name": "Tableau Desktop Specialist"},
                           {"name": "dbt Analytics Engineering Certification"},
                           {"name": "MCIPS Diploma in Procurement"}]
    assert _ids(p) == ["cert-not-held:tableau-desktop-specialist",
                       "cert-in-progress:dbt-analytics-engineering-certification",
                       "cert-not-held:mcips-diploma-in-procurement"]
    p["certifications"] = []
    assert _ids(p) == ["cert-missing:microsoft-certified-power-bi-data-analyst-associate"]


def test_a_finding_they_do_not_care_about_is_never_raised_again(profile):
    p = _clean()
    p["location"] = "London, England, United Kingdom"
    assert _ids(p) == ["location"]
    O.dismiss("location", "I keep London on there on purpose", today=TODAY)
    result = O.check(p, TODAY, answers={})
    assert result["findings"] == [] and result["dismissed"] == 1
    rule = learned.entries("other")[-1]
    assert rule["said"] == "I keep London on there on purpose"
    assert rule["applied_to"] == ["documents/network/own_profile_review.json"]


# ------------------------------------------------------------ the brief, and the record

def test_the_brief_is_compact_and_only_when_a_look_is_due_or_just_done(profile):
    p = _clean()
    U.record_no(O.UID, TODAY)
    assert O.brief(p, O.check(p, TODAY), TODAY) == ""          # not due, nothing done today
    _looked(0, p)
    text = O.brief(p, O.check(p, TODAY), TODAY)
    assert len(text) < O.BRIEF_MAX_CHARS and len(text.split()) < 1200
    assert "\"Nothing that would stop people replying\" is an expected answer" in text
    assert f"Headline: \"{p['headline']}\"" in text and "At most three findings" in text
    empty = dict(p, headline="", summary="")
    assert O.brief(empty, O.check(empty, TODAY), TODAY) == ""   # nothing left to judge


def test_each_look_is_kept_with_its_source_what_it_compared_answers_and_decision(profile, capsys):
    assert O.main(["check", "--from", str(FIX), "--today", TODAY.isoformat()]) == 0
    assert "No red flags" in capsys.readouterr().out
    assert O.main(["answer", "photo", "yes"]) == 0
    assert O.main(["decide", "--said", "leave it as it is", "--finding",
                   "the headline says what they do"]) == 0
    data = json.loads((Path(person.state(*O.REVIEW))).read_text(encoding="utf-8"))
    look = data["reviews"][-1]
    assert look["source"] == "export" and look["date"] == TODAY.isoformat()
    assert set(look["hashes"]) == {"role", "roles", "location", "certifications", "confidential",
                                   "export"} and look["hashes"]["export"]
    assert look["decided"] == "leave it as it is" and data["answers"]["photo"]["answer"] == "yes"
    assert look["answers"]["photo"]["answer"] == "yes"   # the look it answers keeps it too
    # Asked once: an answered question is not asked again.
    assert O.check(_clean(), TODAY)["questions"] == []


def test_a_paste_is_checked_the_same_way_and_a_browser_read_needs_their_setting(profile, tmp_path):
    pasted = tmp_path / "paste.json"
    pasted.write_text(json.dumps({"headline": "Analyst", "location": "London, UK",
                                  "summary": "x" * 600}), encoding="utf-8")
    p = O.from_paste(str(pasted))
    assert _ids(p) == ["location"]                  # parts not pasted are not checked
    with pytest.raises(ValueError, match="PROFILE_READS"):
        O.from_paste(str(pasted), "browser")        # the example person reads by paste


def test_the_first_look_is_offered_through_the_upgrades_and_a_look_settles_it(profile):
    u = U.by_id(O.UID)
    assert u.needs == "you" and u.ask.endswith("?") and "own LinkedIn profile" in u.ask
    assert u.pending().startswith("your own LinkedIn profile has never been looked over")
    U.record_no(O.UID, TODAY)
    assert u.pending() == ""                        # a no holds, and is asked again later
    asked = json.loads((profile / "asked.json").read_text(encoding="utf-8"))
    asked.pop(O.UID)
    (profile / "asked.json").write_text(json.dumps(asked), encoding="utf-8")
    _looked(0)
    assert u.pending() == ""
    assert u.steps().splitlines()[-1].endswith("nothing is sent.")
