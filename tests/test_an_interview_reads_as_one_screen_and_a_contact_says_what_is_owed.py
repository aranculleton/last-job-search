"""An interview reads on the page as its pack does; a contact says what is owed; a profile can
be pasted; the brief is moved and rested from the page.

FUNCTIONS_SPEC.md (2026-10-25) gaps 16 and 23 and CAPABILITY_MAP G14, engine half. An
interview carries the pack's one screen, its stages with any time and who each is with, the
round's format, the files they hold and who referred the person, and the questions to practise
with the person's own answers; "Keep this to work on" writes the pack's own To rework line,
once. A contact carries a level-1 alert for a reply owed more than three days and for a call
today or tomorrow with no prep, and one suggestion to tell a referrer where the process they
started has got to. A profile pasted on a phone is kept the way a chat keeps a paste, its
words leave the page's database, and a note that rested on nothing read is queued for its
rewrite once. The brief's days, time and a break are changed through tools/routines.py, the
one break the search has. Every person and employer here is invented.
"""
from __future__ import annotations

import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import interview_pack as P  # noqa: E402
import page_db  # noqa: E402
import reading  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, Search  # noqa: E402
from test_interview_pack import _pack, _section  # noqa: E402
from test_interview_pack import app  # noqa: E402,F401  the pack's own invented application

INTERVIEW = "int-thornbury_bank_risk_analyst"
FOLDER = ("documents", "applications", "thornbury_bank_risk_analyst_thornbury")
JUNO, WREN, PELL = "larkspur_retail_castellan", "fernhill_freight_halloway", "kestrel_mutual_ansgar"


@pytest.fixture
def search(tmp_path):
    return Search(str(tmp_path))


def _interview(search):
    return next(i for i in search.model()["interviews"] if i["id"] == INTERVIEW)


def _person(model, cid):
    return next(p for p in model["people"] if p["id"] == cid)


def _add_threads(search, rows):
    path = os.path.join(search.state, "network_threads.csv")
    with open(path, encoding="utf-8") as fh:
        head = next(csv.reader(fh))
    with open(path, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=head, extrasaction="ignore")
        for r in rows:
            w.writerow(r)


# ------------------------------------------------------------------ the pack, read as written


def test_the_one_screen_practice_and_format_are_read_as_the_pack_wrote_them(app):  # noqa: F811
    text = _pack()
    screen = _section(text, "On one screen")
    got = P.one_screen(text)
    numbered = [ln for ln in screen if ln[:1].isdigit()]
    assert [q["question"] for q in got["questions"]] == [
        ln.split(". ", 1)[1].split(" -> ")[0] for ln in numbered]
    assert got["questions"][0]["answer"] == "story: One report in place of eleven spreadsheets"
    assert len(got["hooks"]) == P.HOOKS and all(h["source"] for h in got["hooks"])
    assert got["money"] and got["assessing"] and got["hear"]
    assert got["do_not_say"][-1]["text"].startswith("No claim in the room beyond the paper")
    practice = P.practice(text)
    asked = [ln for ln in _section(text, "Likely questions") if ln.startswith("- **Q.** ")]
    assert len(practice["questions"]) == len(asked)
    # A reason that holds its own brackets is read whole, never cut at the first one.
    first = practice["questions"][0]
    assert first["question"] == "How do you handle conflicting numbers?"
    assert first["why"].startswith("asked here before (Phone screen, 2026-03-02)")
    assert practice["bands"] == ["Strong", "Solid", "Gap"] and practice["min_quote_words"] == 3
    assert P.format_of(text) == {"names": ["A technical interview"], "assumed": False,
                                 "told": []}


def test_an_answer_the_person_wrote_is_what_the_practice_holds(app):  # noqa: F811
    text = _pack()
    q = "Tell me about your experience with Demand forecasting."
    mine = ("I rebuilt the weekly forecast in Python and SQL, and error fell from 22% to "
            "14% across the network.")
    # Written where the pack leaves room for it, in place of its "to write" line.
    head, block = text.split("### %s\n" % q, 1)
    block = block.replace(P.TO_WRITE, mine, 1)
    text = head + "### %s\n" % q + block
    got = next(x for x in P.practice(text)["questions"] if x["question"] == q)
    assert got["answer"] == mine and got["draft"] is False
    # A draft written for them to confirm is still theirs to make true.
    drafted = text.replace(mine, "Draft: " + mine, 1)
    assert next(x for x in P.practice(drafted)["questions"] if x["question"] == q)["draft"]


# ------------------------------------------------------------------ the interview on the page


def test_an_interview_carries_its_stages_time_who_files_and_practice(search):
    i = _interview(search)
    aid = search.act("outcome.interview", INTERVIEW, rev=i["rev"],
                     value={"stage": "Panel interview", "on": "2026-10-28", "time": "2pm",
                            "with": "Shirin Example, Head of Risk"})
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    with open(os.path.join(search.state, *FOLDER, "outcome.md"), encoding="utf-8") as fh:
        md = fh.read()
    assert "- [ ] Panel interview (scheduled 2026-10-28 14:00, with Shirin Example, Head of " \
           "Risk)" in md
    i = _interview(search)
    assert (i["when"], i["time"], i["all_day"], i["zone"]) == ("2026-10-28", "14:00", False,
                                                               "Europe/London")
    # Who it is with, as the page may hold it: a first name and a title, never a surname.
    assert i["with"] == "Shirin, Head of Risk"
    assert [(s["label"], s["done"], s["time"]) for s in i["stages"]] == [
        ("Phone screen", True, None), ("Panel interview", False, "14:00")]
    assert [(f["name"], f["to"]) for f in i["sent_files"]] == [
        ("Morgan_Ellis_CV_Thornbury.pdf", None), ("Morgan_Ellis_Cover_Letter_Thornbury.pdf", None)]
    assert i["referrer"] is None
    assert [q["question"] for q in i["practice"]["questions"]] == [
        "Tell me about a forecast you built", "How do you check your data"]
    assert "Example" not in json.dumps(search.model())


def test_keep_this_to_work_on_is_kept_once_and_undo_takes_it_off(search):
    i = _interview(search)
    value = {"question": "Tell me about a forecast you built",
             "note": "lead with the error it cut, then the stock it freed"}
    aid = search.act("interview.rework", INTERVIEW, rev=i["rev"], value=value)
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    assert search.receipt(aid)["note"].startswith("Kept to work on")
    kept = _interview(search)["practice"]["reworked"]
    assert kept == ['- 2026-10-25, mock: "Tell me about a forecast you built": lead with the '
                    'error it cut, then the stock it freed']
    search.written_back()
    again = search.act("interview.rework", INTERVIEW, rev=i["rev"], value=value)
    assert search.apply()["ok"] == [again]
    assert search.receipt(again)["note"] == "Already kept to work on."
    assert _interview(search)["practice"]["reworked"] == kept
    search.written_back()
    back = search.act("undo", None, value={"undoes": aid})
    assert search.apply()["ok"] == [back], search.receipt(back)
    assert _interview(search)["practice"]["reworked"] == []


# ------------------------------------------------------------------ what a contact is owed


def test_a_reply_owed_more_than_three_days_is_an_alert_on_the_contact(search):
    (a,) = _person(search.model(), JUNO)["alerts"]
    assert a["kind"] == "reply_owed" and a["text"].startswith("Juno replied 43 days ago")
    assert a["action"]["kind"] == "reply" and a["action"]["id"] == f"reply~{JUNO}"
    _add_threads(search, [{"contact_id": JUNO, "date": "2026-10-23", "direction": "inbound",
                           "channel": "linkedin", "scenario": "detailed_generous",
                           "summary": "replied", "full_text": "Thanks, and good luck!"}])
    assert _person(search.model(), JUNO)["alerts"] == []        # two days: not yet


def test_a_call_tomorrow_with_no_prep_is_an_alert_until_its_prep_is_made(search):
    p = _person(search.model(), WREN)
    aid = search.act("person.call_booked", WREN, value={"on": "2026-10-26"}, rev=p["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    (a,) = _person(search.model(), WREN)["alerts"]
    assert a["kind"] == "call_no_prep" and "tomorrow" in a["text"]
    assert a["action"]["id"] == f"prep~call~{WREN}"
    prep = os.path.join(search.state, "documents", "network", WREN, "prep.md")
    os.makedirs(os.path.dirname(prep), exist_ok=True)
    with open(prep, "w", encoding="utf-8") as fh:
        fh.write("# Call prep\n")
    assert _person(search.model(), WREN)["alerts"] == []


def test_a_referrer_is_told_where_it_stands_until_the_person_writes_to_them(search):
    p = _person(search.model(), WREN)
    aid = search.act("referral.agreed", WREN, value="Operations Analyst", rev=p["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    path = os.path.join(search.state, "job_search_tracker.csv")
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
        head = list(rows[0])
    rows.append(dict.fromkeys(head, "") | {
        "date": "2026-10-12", "company": "Fernhill Freight", "role": "Operations Analyst",
        "channel": "referral", "status": "interview",
        "notes": "2026-10-24: interview, Phone screen booked for 2026-10-29 (page)"})
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=head)
        w.writeheader()
        w.writerows(rows)
    s = _person(search.model(), WREN)["suggest"]
    assert s["kind"] == "tell_referrer"
    assert s["text"] == "Tell Wren where it stands: interview, Phone screen booked for 2026-10-29."
    assert s["action"]["kind"] == "reply" and s["action"]["args"]["contact"] == WREN
    _add_threads(search, [{"contact_id": WREN, "date": "2026-10-25", "direction": "outbound",
                           "channel": "linkedin", "scenario": "update", "summary": "update",
                           "full_text": "The screen is booked for Thursday: thank you again."}])
    assert _person(search.model(), WREN)["suggest"] is None


# ------------------------------------------------------------------ a pasted profile


PROFILE = ("Pell Ansgar\nClaims Analytics Lead at Kestrel Mutual\nManchester\nAbout\n"
           "I lead the claims analytics team: reserving, fraud signals and the weekly "
           "forecast the operations floor works from.\nExperience\nClaims Analytics Lead\n"
           "Kestrel Mutual\n2021 - Present\nEducation\nUniversity of Leeds\n")


def _read_kept(search, cid) -> bool:
    """Is a reading kept for them, asked of their copy as reading.py itself would."""
    import subprocess
    env = dict(os.environ, LJS_PROFILE=search.profile, LJS_STATE=search.state)
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path[:0] = ['tools', "
                        "'tools/network']\nimport reading\n"
                        f"print(reading.has_read(reading.load({cid!r})))"],
                       env=env, cwd=ROOT, capture_output=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip() == "True"


def _waiting_note(search):
    path = os.path.join(search.state, "documents", "network", PELL, "draft.md")
    with open(path, encoding="utf-8") as fh:
        note = fh.read().strip()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"{reading.WAITS_ON_A_READ}: nothing was read about Pell.\n\n{note}\n")


def test_a_pasted_profile_is_kept_as_a_paste_and_the_note_rewritten_once(search):
    _waiting_note(search)
    msg = next(m for m in search.model()["messages"] if m["contact"] == PELL)
    (alert,) = [a for a in msg["alerts"] if a["kind"] == "read_first"]
    assert alert["action"]["action"] == "profile.pasted" and alert["action"]["input"] == "text"
    assert msg["paste"]["action"] == "profile.pasted"
    aid = search.act("profile.pasted", msg["id"], value={"text": PROFILE}, rev=msg["rev"])
    claimed = json.loads(search.run("apply", search.dump, "--chat", "cloud-1", "--now", NOW,
                                    "--claim"))
    batch = json.load(open(claimed["batches"][0], encoding="utf-8"))
    wipe = next(e for e in batch if e["doc_id"] == aid)
    assert json.load(open(wipe["file_path"], encoding="utf-8"))["value"] == {
        "text": {"__delete__": True}}
    got = search.apply()
    assert got["ok"] == [aid], search.receipt(aid)
    r = search.receipt(aid)
    assert r["note"].startswith("Kept what Pell's profile says.")
    assert _read_kept(search, PELL)
    work = [e for b in got["batches"] for e in json.load(open(b, encoding="utf-8"))
            if e["collection"] == "work"]
    (w,) = work
    assert w["doc_id"] == page_db.safe_id(f"network~rewrite~{PELL}")
    body = json.load(open(w["file_path"], encoding="utf-8"))
    assert body["kind"] == "network" and body["args"]["rewrite"] is True


def test_a_paste_too_short_to_be_a_profile_is_refused(search):
    _waiting_note(search)
    msg = next(m for m in search.model()["messages"] if m["contact"] == PELL)
    aid = search.act("profile.pasted", msg["id"], value="Pell Ansgar", rev=msg["rev"])
    got = search.apply()
    assert aid not in got["ok"]
    assert "too short" in search.receipt(aid)["note"]


# ------------------------------------------------------------------ the brief, from the page


def test_the_brief_moves_from_the_page_and_a_chat_moves_its_task(search):
    s = search.model()["schedule"]
    assert (s["id"], s["when"], s["paused"]) == ("schedule", "Mondays and Thursdays at 7:56",
                                                 None)
    aid = search.act("brief.move", "schedule", value={"days": ["tue", "fri"], "time": "07:20"},
                     rev=s["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    r = search.receipt(aid)
    assert r["note"].startswith("Your brief comes Tuesdays and Fridays at 7:20 from now on.")
    assert "A chat makes the change" in r["note"]
    reg = json.load(open(os.path.join(search.profile, "routines.json"), encoding="utf-8"))
    assert [c["tool"] for c in reg["owed"]] == ["update_trigger"]
    s2 = search.model()["schedule"]
    assert s2["when"] == "Tuesdays and Fridays at 7:20" and s2["waiting"] == 1
    search.written_back()
    back = search.act("undo", None, value={"undoes": aid})
    assert search.apply()["ok"] == [back], search.receipt(back)
    assert search.model()["schedule"]["when"] == "Mondays and Thursdays at 7:56"


def test_a_break_from_the_brief_row_is_the_one_break(search):
    s = search.model()["schedule"]
    aid = search.act("brief.pause", "schedule", value={"until": "2026-11-08"}, rev=s["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    m = search.model()
    assert m["schedule"]["paused"]["until"] == "2026-11-08"
    assert m["search"]["pause"] == {"until": "2026-11-08", "since": "2026-10-25"}
    search.written_back()
    again = search.act("brief.pause", "schedule", value="2026-11-08",
                       rev=m["schedule"]["rev"])
    assert search.apply()["ok"] == [again]
    assert search.receipt(again)["note"] == "Your search is paused until 2026-11-08 already."
    search.written_back()
    res = search.act("brief.resume", "schedule", rev=m["schedule"]["rev"])
    assert search.apply()["ok"] == [res], search.receipt(res)
    assert search.receipt(res)["note"].startswith("Welcome back")
    assert search.model()["schedule"]["paused"] is None


def test_a_day_that_has_passed_is_refused_in_plain_words(search):
    s = search.model()["schedule"]
    aid = search.act("brief.pause", "schedule", value="2026-10-20", rev=s["rev"])
    got = search.apply()
    assert aid not in got["ok"]
    assert search.receipt(aid)["note"] == "Pick a day after today."


# ------------------------------------------------------------------ who answers, and the footer


def test_the_model_says_who_answers_the_page_its_privacy_line_and_the_brief(search):
    m = search.model()
    assert m["listener"]["doc"] == "meta/listener" and m["listener"]["seen"]["helper"] is False
    assert m["listener"]["seen"]["seen_recently"] is False
    assert m["app"]["privacy"].startswith("Only you can open this page")
    assert m["schedule"]["actions"] == {"move": "brief.move", "pause": "brief.pause",
                                        "resume": "brief.resume"}


def test_republish_is_a_kind_of_page_work():
    assert page_db.progress("republish")["stages"][0]["name"] == "Building the new page"
    assert "republish" in page_db.WORK_KINDS


# ------------------------------------------------------------------ a call that is an interview, a resume sent


def _set(search, cid, **fields):
    path = os.path.join(search.state, "network_contacts.csv")
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
        head = list(rows[0])
    for r in rows:
        if r["contact_id"] == cid:
            r.update(fields)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=head)
        w.writeheader()
        w.writerows(rows)


def test_a_call_with_a_recruiter_is_made_an_interview_once(search):
    _set(search, PELL, title="Talent Acquisition Partner", status="call_booked",
         next_action="Recruiter call", next_action_due="2026-10-29")
    p = _person(search.model(), PELL)
    assert p["is_process_stage"] is True
    aid = search.act("process.register", PELL, value={"contact": PELL, "role": "Claims Analyst"},
                     rev=p["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    assert search.receipt(aid)["note"].startswith(
        "Now an interview: Recruiter screen at Kestrel Mutual on 2026-10-29.")
    m = search.model()
    i = next(x for x in m["interviews"] if x["company"] == "Kestrel Mutual")
    assert (i["role"], i["next_stage"], i["when"]) == ("Claims Analyst", "Recruiter screen",
                                                       "2026-10-29")
    assert _person(m, PELL)["is_process_stage"] is False
    search.written_back()
    again = search.act("process.register", PELL, value={"contact": PELL, "role": "Claims Analyst"},
                       rev=_person(m, PELL)["rev"])
    assert search.apply()["ok"] == [again]
    assert search.receipt(again)["note"] == "Already an interview at Kestrel Mutual."


def test_a_resume_sent_to_a_contact_is_logged_with_its_file(search):
    ready = next(x for x in search.model()["ready"] if x["company"] == "Kestrel Mutual")
    resume = next(f for f in ready["files"] if f["kind"] == "resume")
    aid = search.act("ready.sent_to_contact", ready["id"], rev=ready["rev"],
                     value={"text": "Here's my resume, as promised. Thank you for passing it on.",
                            "channel": "linkedin_message", "on": "2026-10-25",
                            "attached": resume["name"], "contact": PELL})
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    assert search.receipt(aid)["note"].startswith("Your CV logged as sent to Pell")   # their word
    with open(os.path.join(search.state, "network_threads.csv"), encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["contact_id"] == PELL]
    assert rows[-1]["full_text"].startswith("Here's my resume") and \
        resume["path"] in json.dumps(rows[-1])
