"""Nothing the app generates fails the person's own checker, and the checker blocks.

From the documents audit of 3 November 2026, each case below reproduced on the path that
made it, with invented people, employers and postings (the candidate is the example person):

- a stock answer naming the city one employer did not hear was printed as "Prepared"
  under its own warning (1); a "[FILL IN]" under a story's heading, a tenure the profile
  does not hold and a pay figure beside another band went in prep packs (10, 11, 20); an
  old pack kept saying what an employer heard after it changed (22);
- a nudge said "you offered to refer me" to someone who offered a recruiter's name (2);
  "I've made the move" and an employer's initials passed the message gate (5, 24); three
  "replies" went to people whose one row was a connection request with no words (6);
- a resume they sent with the file the same day was still "owed" (7), and a person kept on
  two rows was owed a second thank-you (8);
- the "do not send" resume was offered for download and to contacts (3);
- skills claimed on a yes given in a chat, and never written into the profile, went on a
  sent resume (4, 25);
- the pay answer on every form ignored the posting's own range (14);
- an employer that cleared none of the bar was drafted unjudged (15);
- a letter copied the employer's press release and said where the person is twice (16);
- a posting's degree routes ("BS 8+, MS 6+, PhD 2+") read as a two-year bar (17);
- a resume line of "References available upon request" and a certification "scheduled" in
  a month gone (21); a role over its cap off its territory, "available straight away"
  against a month's notice, a rule kept beside its replacement, text changed after the
  audit, and "flags": [] beside a batch that failed (23, 26).
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.dirname(os.path.abspath(__file__))]

import person  # noqa: E402
import schema  # noqa: E402

TODAY = "2026-11-03"


@pytest.fixture
def prof(tmp_path, monkeypatch):
    """A copy of the example person, and an empty state, both theirs to write."""
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d,
                    ignore=shutil.ignore_patterns("__pycache__", "state"))
    st = tmp_path / "state"
    st.mkdir()
    monkeypatch.setenv(person.ENV, str(d))
    monkeypatch.setenv(person.STATE_ENV, str(st))
    person.reset()
    yield d
    monkeypatch.undo()
    person.reset()


def _csv(path, rows, cols):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def _book(contacts, threads):
    _csv(person.state("network_contacts.csv"), contacts, schema.CONTACT_COLUMNS)
    _csv(person.state("network_threads.csv"), threads, schema.THREAD_COLUMNS)


def _contact(cid, name, company="Quillon Networks", status="awaiting_reply"):
    return {"contact_id": cid, "name": name, "company": company, "title": "Data Lead",
            "status": status, "route": "cold"}


# ------------------------------------------------------------------ the message gate (5, 24)

def test_a_banned_phrase_said_another_way_and_an_employers_initials_are_refused(prof):
    import compose
    import learned
    import voice_check
    rules = prof / "CLAUDE.md"
    rules.write_text(rules.read_text(encoding="utf-8") + (
        "\n- Never with the phrase \"I made the move\" (2026-10-17).\n"
        "- Always write \"Oakmere Foods\" in full: readers here do not know the initials.\n"),
        encoding="utf-8")
    assert [p for p, _w in learned.profile_never_phrases()] == ["I made the move", "OF"]
    learned.adopt_profile_rules(today=TODAY)
    text = ("Hi Ines, I've made the move since my note. As a fellow ex-OF person there, I'd "
            "love to hear how the team works.")
    found = [v.text for v in compose.validate(text, "nudge") if v.rule == "person_dislikes"]
    assert "I've made the move" in found and "OF" in found
    hard = {f["match"] for f in voice_check.check(text, source="note")
            if f["rule"] == "person-dislikes"}
    assert {"I've made the move", "OF"} <= hard
    # "I have made the move" is the same words; "of" in a sentence is a word, not initials.
    assert learned.dislikes("I have made the move") == ["I have made the move"]
    assert learned.dislikes("One of the teams I know of.") == []
    # A ban on initials never overrules an earlier rule because "of" sits inside a word.
    assert not learned.superseded([
        {"date": "2026-10-01", "area": "messages", "rule": "open with what they offered",
         "status": "active"},
        {"date": "2026-10-02", "area": "messages", "rule": "x", "never_say": ["OF"],
         "status": "active"}])


# ------------------------------------------------------- what they said, read from them (2, 6)

def test_a_follow_up_says_only_what_they_offered(prof):
    import compose
    import followup_drafts
    _book([_contact("dunmore", "Rafe Dunmore", status="awaiting_reply")], [
        {"contact_id": "dunmore", "date": "2026-09-16", "direction": "in", "channel": "message",
         "scenario": "reply", "full_text": "Happy to connect you with a recruiter if "
                                             "something appeals."},
        {"contact_id": "dunmore", "date": "2026-09-18", "direction": "out",
         "channel": "message", "full_text": "Thank you, the analytics role looks right."},
        {"contact_id": "dunmore", "date": "2026-10-02", "direction": "out",
         "channel": "message", "full_text": "Following up on my note of 18 September."}])
    said = ("Hi Rafe, in your last message you offered to refer me if a role came up at "
            "Quillon Networks, and I'd still be glad of that.")
    rules = {v.rule for v in compose.validate(said, "nudge", contact="dunmore", today=TODAY)}
    assert "not_in_their_messages" in rules
    offer = {"full_text": "Happy to connect you with a recruiter if something appeals."}
    reason, close = followup_drafts.offer_words(offer)
    assert "refer" not in reason and "put me in touch" in reason
    assert followup_drafts.offer_words({"full_text": "I can refer you if one opens."})[0] \
        == followup_drafts.OFFER_REASON


def test_a_connection_request_with_no_note_is_never_a_reply_owed(prof):
    import compose
    import state
    row = {"contact_id": "varga", "date": "2026-10-12", "direction": "in",
           "channel": "connection", "scenario": "invitation_received",
           "summary": "They asked to connect, from LinkedIn's export", "full_text": ""}
    _book([_contact("varga", "Ines Varga", status="replied_needs_response")], [row])
    assert state.derive_status([row]) == "connected_no_reply"
    owed = state.owed(state.load_contacts(person.state("network_contacts.csv")),
                      state.load_threads(person.state("network_threads.csv")), TODAY)
    assert [(o["contact_id"], o["kind"]) for o in owed] == [("varga", "first_message")]
    draft = ("Hi Ines, we connected a while back but never spoke, sorry for the slow reply. "
             "Would be great to hear what you're working on.")
    for kind in ("reply", "nudge"):
        rules = {v.rule for v in compose.validate(draft, kind, contact="varga", today=TODAY)}
        assert "nothing_to_reply_to" in rules, kind
    # With a note, they said something, and a reply is owed.
    noted = dict(row, full_text="Saw your post on forecasting, would like to connect.")
    assert state.derive_status([noted]) == "replied_needs_response"


# --------------------------------------------------------------- what is owed (7, 8)

def test_a_resume_sent_with_the_file_after_they_asked_is_not_owed(prof):
    import state
    contacts = [_contact("halvorsen", "Mira Halvorsen", status="replied_needs_response")]
    threads = [
        {"contact_id": "halvorsen", "date": "2026-10-03", "direction": "in",
         "channel": "message", "full_text": "Please share your resume."},
        {"contact_id": "halvorsen", "date": "2026-10-03", "direction": "out",
         "channel": "message", "summary": "Message sent, from LinkedIn's export; an "
                                          "attachment attached", "full_text": ""}]
    assert state.resumes_owed(contacts, threads) == []
    # Nothing went after the ask: it is owed.
    assert [o["contact_id"] for o in state.resumes_owed(contacts, threads[:1])] == ["halvorsen"]


def test_a_person_kept_on_two_rows_is_owed_nothing_the_other_row_answered(prof):
    import state
    contacts = [_contact("fenwick_vell", "Teo Vell", company="Fenwick Search",
                         status="awaiting_reply"),
                _contact("recruiter_vell", "Teo Vell", company="Fenwick Search",
                         status="awaiting_reply")]
    threads = [
        {"contact_id": "recruiter_vell", "date": "2026-10-22", "direction": "in",
         "channel": "message", "full_text": "Hope the move went well, keep in touch."},
        {"contact_id": "fenwick_vell", "date": "2026-10-22", "direction": "out",
         "channel": "message", "full_text": "Thanks so much!"}]
    assert not [o for o in state.owed(contacts, threads, TODAY) if o["kind"] == "reply"]
    # Another person of the same name at another employer is someone else.
    contacts[0]["company"] = "Brackwater Insurance"
    assert [o["contact_id"] for o in state.owed(contacts, threads, TODAY)
            if o["kind"] == "reply"] == ["recruiter_vell"]


# ------------------------------------------------------------- the resume to send (3)

def _text_pdf(path, line):
    """A real one-page PDF whose text layer is `line` (WinAnsi: \\226 is an en dash)."""
    stream = "BT /F1 11 Tf 72 720 Td (%s) Tj ET" % line
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font "
            "<< /F1 5 0 R >> >> /Contents 4 0 R >>",
            "<< /Length %d >>\nstream\n%s\nendstream" % (len(stream.encode("latin-1")), stream),
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out, offsets = b"%PDF-1.4\n", []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += ("%d 0 obj %s endobj\n" % (n, body)).encode("latin-1")
    xref = len(out)
    out += ("xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)).encode()
    out += "".join("%010d 00000 n \n" % o for o in offsets).encode()
    out += ("trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, xref)).encode()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(out)


def test_a_resume_that_breaks_their_rules_is_never_offered(prof):
    import app_model
    import docpaths
    import pdftext
    import stage_picks
    if not pdftext.reader():
        pytest.skip("no PDF reader here: the check reads the resume's own text")
    cvs = person.state("documents", "cv")
    bad = os.path.join(cvs, "Morgan_Ellis_CV_CURRENT_2026-09.pdf")
    _text_pdf(bad, "Standardized the reporting. Mar 2023 \\226 Present")
    assert docpaths.current_resume() == "documents/cv/Morgan_Ellis_CV_CURRENT_2026-09.pdf"
    assert docpaths.resume_problems(docpaths.current_resume())
    r = app_model._resume(None, {})
    # Named on its card and never offered: nothing to download and nothing to get ready, and
    # why in words (one shape with the jobs audit's 23, whose card says "Not to send").
    assert r["file"]["asset"] is None and r["get"] is None, r
    assert any("dash" in b for b in r["breaks"]) and any("Standardized" in b for b in r["breaks"]), r
    _book([_contact("pell", "Ada Pell")], [])
    got = stage_picks.general_resume_for("pell", today=TODAY)
    assert got["file"] == "" and got["problems"]
    # The one the app makes and checks is the one offered, beside the old file.
    good = os.path.join(cvs, docpaths.general_stem("current") + ".pdf")
    _text_pdf(good, "Standardised the reporting. Mar 2023 - Present")
    assert docpaths.current_resume() == "documents/cv/" + os.path.basename(good)
    r = app_model._resume(None, {})
    assert r["file"]["name"] == os.path.basename(good) and not r["breaks"] and r["get"], r


# ---------------------------------------------------------- a skill on a yes (4, 25)

def test_a_skill_claimed_on_a_yes_is_held_by_the_profile_or_refused(prof):
    import check_claims
    import stage_picks
    doc = "%% Tailored for: Quillon Networks\n" + check_claims.consent_header(["BigQuery"]) + \
        "\\section{Skills} SQL, BigQuery, Power BI\n"
    errors = [n for s, n, _x, _w in check_claims.check_text(doc) if s == "ERROR"]
    assert errors == ["ungrounded-yes"]
    # Recorded the way consent records it, the yes is in the profile, and the claim holds.
    assert stage_picks.profile_yes(["BigQuery"], company="Quillon Networks",
                                   role="Data Analyst", today=TODAY) == ["BigQuery"]
    text = (prof / "01-candidate-profile.md").read_text(encoding="utf-8")
    assert stage_picks.YES_HEADING in text and "- BigQuery: you said yes for Quillon" in text
    assert not [n for s, n, _x, _w in check_claims.check_text(doc) if s == "ERROR"]
    # Said no later, the line goes, and the claim is refused again.
    stage_picks.profile_yes(no=["BigQuery"])
    assert "BigQuery" not in (prof / "01-candidate-profile.md").read_text(encoding="utf-8")
    assert [n for s, n, _x, _w in check_claims.check_text(doc) if s == "ERROR"] == \
        ["ungrounded-yes"]


def test_a_no_written_in_the_same_tick_as_the_yes_is_still_read(prof):
    """On Windows a yes and then a no were written within one tick of the file clock, the
    profile kept its time, and the check still held the skill (the release run, 2026-11-04)."""
    import check_claims
    cv = prof / "01-candidate-profile.md"
    doc = "%% Tailored for: Quillon Networks\n" + check_claims.consent_header(["BigQuery"]) + \
        "\\section{Skills} SQL, BigQuery, Power BI\n"
    before = os.stat(cv)
    cv.write_text(cv.read_text(encoding="utf-8") + "\n- BigQuery: you said yes for Quillon\n",
                  encoding="utf-8")
    os.utime(cv, ns=(before.st_atime_ns, before.st_mtime_ns))
    held = [n for s, n, _x, _w in check_claims.check_text(doc) if s == "ERROR"]
    cv.write_text(cv.read_text(encoding="utf-8").replace(
        "\n- BigQuery: you said yes for Quillon\n", ""), encoding="utf-8")
    os.utime(cv, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert held == [] and [n for s, n, _x, _w in check_claims.check_text(doc)
                           if s == "ERROR"] == ["ungrounded-yes"]

def test_the_example_person_is_never_written_to(monkeypatch):
    import stage_picks
    monkeypatch.setenv(person.ENV, os.path.join(ROOT, "profile.example"))
    person.reset()
    assert stage_picks.profile_yes(["BigQuery"], company="Quillon Networks") == []


# ------------------------------------------------------------- the pay answer (14)

def test_the_pay_answer_moves_with_the_postings_own_range(prof):
    import screening_answers as S
    floor, low, high = S.salary_band()
    assert S.moved_band(low, high, high + 4000, high + 20000)[:2] == (high + 4000, high + 12000)
    lo2, hi2, why, decide = S.moved_band(low, high, low - 30000, low - 5000)
    assert decide and "below your band" in why and (lo2, hi2) == (low, high)
    assert S.moved_band(low, high, low + 2000, high + 9000)[:2] == (low + 2000, high)
    assert S.moved_band(low, high)[:2] == (low, high)
    sheet = S.render("Quillon Networks", "Data Analyst",
                     "Salary: £%s - £%s per year." % (f"{high + 4000:,}", f"{high + 20000:,}"))
    assert "GBP %s to %s" % (f"{high + 4000:,}", f"{high + 12000:,}") in sheet
    assert "never asks for less than they offer" in sheet


# --------------------------------------------------------------- the bar (15)

def test_an_employer_that_clears_none_of_the_bar_waits_on_the_person(prof, monkeypatch):
    import bar
    import opportunity
    assert bar.hold_question("Quillon Networks", "We build routers.") is None   # no bar set
    monkeypatch.setattr(opportunity, "TIER_2", {"larkspur retail"})
    q = bar.hold_question("Quillon Networks", "We build routers.")
    assert q["id"] == "bar" and "clears none of your bar" in q["question"]
    assert "python3" not in q["question"]
    bar.judge("Quillon Networks", "signal", "the network-analytics name in its field",
              today=TODAY)
    assert bar.hold_question("Quillon Networks", "We build routers.") is None


# ------------------------------------------------------------ the letter (16)

def test_a_letter_that_copies_their_words_or_says_where_twice_is_refused(prof):
    import draft_audit
    research = {"facts": [{"claim": "c", "quote": "Quillon Success delivers expert guidance and "
                           "best practices that accelerate time to value, enabling customers "
                           "to activate agentic capabilities with confidence."}]}
    d = {"summary": "Analyst.", "p1": "I am a data scientist in Manchester.",
         "p2": "Quillon Success delivers guidance that accelerates time to value for service "
               "providers as they activate agentic capabilities.",
         "lead": "Where:", "cl_bullets": [], "p4": "I am based in Manchester."}
    rules = [f["rule"] for f in draft_audit.copied_findings(d, research)]
    assert rules == ["copies-source", "located-twice"]
    d.update(p1="I build demand forecasts.",
             p2="Quillon's work with service providers is where my forecasting would help.")
    assert draft_audit.copied_findings(d, research) == []


# ------------------------------------------------------------ the years bar (17)

def test_a_degree_route_reads_the_bar_for_the_degree_held(prof):
    import fit
    import text_screen
    posting = ("Minimum requirements: BS with 8+ years of experience in quantitative finance, "
               "or MS with 6+ years, or PhD with 2+ years of experience.")
    assert text_screen.entry_years(posting)[:2] == (8, 8)
    scored = fit.fit({"title": "Data Scientist", "desc": "Python and SQL forecasting. " + posting,
                      "company": "Quillon Networks", "location": "Manchester"})
    assert any("stated 8+ years" in w for w in scored["fit_why"]), scored["fit_why"]
    assert text_screen.entry_years("Master's degree and 3+ years of experience required.")[:2] \
        == (3, 3)


# ------------------------------------------------------------ the resume's own rules (21, 23)

def test_a_resume_line_nobody_needs_a_passed_date_and_a_start_the_notice_forbids(prof):
    import check_claims
    import compose
    text = ("References available upon request. dbt certification in progress, scheduled "
            "September 2026. I am available straight away.")
    names = {n for s, n, _x, _w in check_claims.check_text(text) if s == "ERROR"}
    assert {"references-on-request", "stale-date", "available-now"} <= names
    assert not {n for s, n, _x, _w in check_claims.check_text(
        "Exam scheduled for March 2099. I could start after one month's notice.")
        if s == "ERROR"} & {"stale-date", "available-now"}
    rules = {v.rule for v in compose.validate(
        "Thanks Teo, I'm available straight away if anything comes up.", "reply")}
    assert "not_your_notice" in rules


def test_a_role_over_its_cap_off_its_territory_is_held_to_it(prof):
    import allocate
    import fit_to_page
    import verify_batch
    posting = "Weekly demand forecasting in Python and SQL for a grocer's depots."
    caps = allocate.caps_for(posting)
    assert caps["Saltmarsh Analytics"] == 1
    a = {"posting": posting, "jobs": [
        {"employer": "Brindle & Hart Logistics", "bullets": ["BH_FORECAST", "BH_PIPE"]},
        {"employer": "Saltmarsh Analytics", "bullets": ["SALT_FORECAST", "SALT_DASH"]}]}
    gone = fit_to_page.hold_to_caps(a, caps)
    assert len(gone) == 1 and len(a["jobs"][1]["bullets"]) == 1
    assert a["jobs"][0]["bullets"] == ["BH_FORECAST", "BH_PIPE"]
    assert verify_batch._caps({"posting": posting}) == caps
    assert verify_batch._caps({}) == {}          # no posting: no cap read, no false finding


def test_text_changed_after_the_audit_is_named(prof):
    import verify_batch
    entry = {"summary": "Operations analyst with seven years of forecasting.",
             "p1": "I build forecasts.", "p2": "", "lead": "", "cl_bullets": [], "p4": "",
             "claim_map": [{"field": "summary", "sentence": "Operations analyst with 7+ years "
                                                           "of forecasting."},
                           {"field": "p1", "sentence": "I build forecasts."}]}
    assert verify_batch._unaudited(entry) == [("summary", entry["summary"])]
    entry["claim_map"][0]["sentence"] = entry["summary"]
    assert verify_batch._unaudited(entry) == []
    assert verify_batch._unaudited({"summary": "Anything."}) == []


def test_the_page_says_a_batch_check_failed_on_this_application(prof, tmp_path):
    import app_model
    folder = tmp_path / "app"
    folder.mkdir()
    (folder / "verify.json").write_text(json.dumps({"at": TODAY, "flags": ["CLAIMS", "UNAUDITED",
                                                                         "SALT_GT_1"]}))
    got = app_model.verify_items(str(folder))
    said = [i["said"] for i in got["items"]]
    assert not got["passed"] and "a check failed" not in said and len(said) == 3


def test_an_applications_record_carries_what_the_whole_batch_checks_found_on_it(prof):
    import docpaths
    import verify_batch
    tex = docpaths.resume_tex("Quillon")
    os.makedirs(os.path.dirname(tex), exist_ok=True)
    with open(tex, "w", encoding="utf-8") as fh:
        fh.write("\\section{Summary} Analyst. References available upon request.\n")
    assert verify_batch._batch_flags("Quillon", {}, True) == ["CLAIMS"]
    with open(tex, "w", encoding="utf-8") as fh:
        fh.write("\\section{Summary} Analyst who builds weekly demand forecasts.\n")
    assert verify_batch._batch_flags("Quillon", {}, True) == []


def test_a_rule_set_twice_keeps_only_the_later_in_the_brief(prof):
    import learned
    rows = [{"date": "2026-10-19", "area": "messages", "status": "active",
             "rule": "ask which place to give each employer", "applied_to": ["networking.py OPENER"]},
            {"date": "2026-10-29", "area": "messages", "status": "active",
             "rule": "one employer hears one city, everyone else the other",
             "applied_to": ["networking.py OPENER"]}]
    over = learned.superseded(rows)
    assert list(over) == [learned.entry_key(rows[0])]
    # A list a rule adds to grows: both stand.
    for r in rows:
        r["applied_to"] = ["search.py BAR_DECLINED"]
    assert learned.superseded(rows) == {}


# ------------------------------------------------------------- the prep (1, 10, 11, 20, 22)

def test_a_stock_answer_naming_the_place_they_did_not_hear_is_left_out(prof):
    import interview_pack as P
    import told
    told.record("Quillon Networks", "Leeds")
    ctx = {"company": "Quillon Networks", "folder": str(prof), "facts": {"employers": []},
           "map": {}, "stories": [], "bank": [], "plan": {}, "form": [], "draft": None,
           "research": {}, "row": {"sector": "technology"},
           "answers": [{"question": "Why are you looking?", "alternatives": [], "use_for": [],
                        "confirm": False, "source": "profile/07-interview-prep.md",
                        "fill_in": "", "suits": (), "not_for": (),
                        "answer": "My partner and I settled in Manchester for good, and I "
                                  "want a team here."}]}
    out = P.answer_for({"question": "Why are you looking?"}, ctx)
    text = "\n".join(out["lines"])
    assert "left out for Quillon Networks: you told Quillon Networks you are in Leeds" in text
    assert "Prepared:" not in text and "python3" not in text
    assert out["prepared"] is None


def test_the_prep_check_reads_every_gap_number_and_place_it_says(prof):
    import interview_pack as P
    import told
    told.record("Quillon Networks", "Leeds")
    path = person.state("prep.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# Interview prep: Data Analyst at Quillon Networks\n\n"
                 "## Your answers\n\n### Tell me about yourself.\n\nI've got about four and a "
                 "half years' experience in forecasting.\n\n"
                 "## Stories\n\n### Drive: first onto the new platform\n\nI set up the "
                 "automation. [FILL IN: the hardest moment.] What I took from it was "
                 "[FILL IN].\n\n## Notes\n\n- You told Quillon Networks you are in Manchester "
                 "(source: profile/person.json identity.places_told): say the same.\n")
    found = P.check(path)
    whys = " | ".join(w for _q, w in found)
    assert "a placeholder still to fill: [FILL IN: the hardest moment.]" in whys
    assert "four and a half years" in whys
    assert "your profile now says Leeds" in whys
    assert P.failures(found)


def test_the_prep_says_one_band_counts_months_as_said_and_writes_plain_english(prof):
    import interview_pack as P
    assert P._a_or_an("analyst") == "an" and P._a_or_an("scientist") == "a"
    assert P._figures("around 70 to 80 thousand base") == [70000, 80000]
    ctx = {"form": [("What are your salary expectations?", "GBP 48,000 to 58,000")]}
    assert P.pay_differs("I'm looking for around 50 to 55 thousand.", ctx)
    assert P.pay_differs("I'm looking for 48,000 to 58,000.", ctx) == ""
    ctx = {"company": "Quillon Networks", "contacts": [
        {"contact_id": "a", "name": "Ada Pell", "company": "Quillon Networks"},
        {"contact_id": "b", "name": "Ada Pell", "company": "Quillon Networks"}],
        "threads": [{"contact_id": c, "date": "2026-09-10", "direction": "out",
                     "channel": "email", "summary": "a resume attached",
                     "full_text": "Here is my resume."} for c in ("a", "b")], "row": {}}
    assert len(P._held_by_contacts(ctx)) == 1


def test_one_status_in_an_outcome_after_it_is_resolved(prof, tmp_path):
    import interview_pack as P
    folder = tmp_path / "app"
    folder.mkdir()
    (folder / "outcome.md").write_text("# Outcome: Quillon - Analyst\n\n**Status:** in_progress"
                                       "\n\nStatus: in_progress\n\n## Notes\n", encoding="utf-8")
    text = P.record_result(str(folder), "Quillon", "Analyst", "no_response", TODAY)
    assert text.count("Status:") == 1 and "**Status:** no_response" in text
