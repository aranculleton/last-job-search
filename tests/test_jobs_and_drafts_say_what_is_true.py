"""Jobs, Drafts and the Brief say what is true, counted once, in plain words.

The 3 November audit read a real page and found it saying what was not so: a posting
months old still listed as new, the card's age a day short of the age the search judged,
a role applied for in September shown as "Set aside" with "Bring back", the bar's reason
for the chat copied onto the card with a command in it, "10 roles on the shortlist" over a
page that said 4, "Searched 2 hours ago" and "Made Sat 31 Oct" read off when the files were
checked out, the resume the person must never send one tap away, "[check the tracker row]"
offered as an answer to copy into an employer's form, a brief line about someone linked to
nothing and shown again under Today, news five days old read as gathered and no more, the
brief counting one live application fewer than the page, and a chat's own title and a
command in the brief's opening line. Each test replays one of those on an invented person
(tools/app_state.py's small state). Every person and employer is invented.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_alerts  # noqa: E402
import app_model  # noqa: E402
import bar  # noqa: E402
import brief  # noqa: E402
import throttle  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import Search  # noqa: E402


def _json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def _row(rank, company, title, **extra):
    return dict({"priority": 100 - rank, "fit": 90 - rank, "title": title, "company": company,
                 "location": "Manchester", "portal": "linkedin",
                 "url": f"https://jobs.example/{company.split()[0].lower()}/{rank}",
                 "first_seen": "2026-10-25", "date": "2026-10-24"}, **extra)


def _pdf_with_text(path, text):
    """A real one-page PDF whose text layer is `text` (WinAnsi, so a dash is one byte)."""
    body = text.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    stream = b"BT /F1 10 Tf 40 800 Td (" + body + b") Tj ET"
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out, offsets = b"%PDF-1.4\n", []
    for n, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj " % n + o + b" endobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(out)


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    """One invented search with every case in it, and its model."""
    s = Search(str(tmp_path_factory.mktemp("jobs")))
    st = s.state
    rounds = os.path.join(st, "documents", "rounds")
    _json(os.path.join(rounds, "r9.json"), [
        # Posted two days ago by its board, four by the search's own count: one age, 4.
        _row(1, "Brindle Hart Logistics", "Demand Planning Analyst", date="2026-10-23",
             age_days=4, bar="pay", salary="GBP 44,000 to 52,000",
             bar_reason="tier 2 employer (brindle hart): major brand, strong pay band",
             fit_why=["+37 core match: SQL, Python, forecasting",
                      "+12 live contact at this employer (Wren Halloway), so this is not a "
                      "cold application", "-9 graduate degree stated without an equivalence route"]),
        # Posted in September: past the 14-day window, nobody has decided on it.
        _row(2, "Quayside Foods", "Data Analyst", date="2026-09-01"),
        # Applied for in September, and ruled out since: Applied, never Set aside.
        _row(3, "Larkspur Retail", "Inventory Planner", url="https://jobs.example/larkspur/inv",
             bar="none", bar_reason="no stated range, and " + bar.UNLISTED),
        _row(4, "Fernhill Freight", "Logistics Analyst",
             silent_application_note="APPLIED HERE ALREADY and never heard back",
             outreach_pending_note="Applying is fine, this is not a warm route. A message is "
                                   "already out and unanswered: Wren Halloway. Do not send another."),
    ])
    tracker = os.path.join(st, "job_search_tracker.csv")
    with open(tracker, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    columns = list(rows[0].keys())
    rows.append(dict.fromkeys(columns, "") | {
        "date": "2026-09-10", "company": "Larkspur Retail", "role": "Inventory Planner",
        "status": "applied", "fit_rating": "70", "source": "https://jobs.example/larkspur/inv"})
    with open(tracker, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)
    seen_path = os.path.join(st, "job_scraper", "seen_jobs.json")
    with open(seen_path, encoding="utf-8") as fh:
        seen = json.load(fh)
    seen["seen"]["https://jobs.example/larkspur/inv"] = {
        "url": "https://jobs.example/larkspur/inv", "title": "Inventory Planner",
        "company": "Larkspur Retail", "status": "excluded", "basis": "person",
        "exclusion_reason": "not this role", "excluded_date": "2026-10-20",
        "first_seen": "2026-10-20"}
    _json(seen_path, seen)
    # The resume the person must never send: another spelling, a dash and a banned word.
    _pdf_with_text(os.path.join(st, "documents", "cv", "Morgan_Ellis_CV_current.pdf"),
                   "Morgan Ellis. Organized supply data, Jan 2023 – Jan 2025. My resume.")
    # A screening answer left for the person.
    kestrel = os.path.join(st, "documents", "applications",
                           "kestrel_mutual_claims_forecasting_analyst_kestrel")
    with open(os.path.join(kestrel, "screening_answers.md"), "a", encoding="utf-8") as fh:
        fh.write("\n### How did you hear about this role?\n\n**[check the tracker row]**\n\nA note.\n")
    # Today's brief: a step naming someone in full, and a news part that found nothing new;
    # an earlier brief with news.
    briefs = os.path.join(st, "documents", "briefs")
    with open(os.path.join(briefs, "2026-10-25.md"), "w", encoding="utf-8") as fh:
        fh.write("# Brief, 2026-10-25\n\nTwo replies owed.\n\n## Next three\n\n"
                 "1. Send Juno Castellan the CV they asked for.\n\n## News\n\nQuiet week.\n")
    with open(os.path.join(briefs, "2026-10-21.md"), "w", encoding="utf-8") as fh:
        fh.write("# Brief, 2026-10-21\n\nAll quiet.\n\n## News\n\n"
                 "- Kestrel Mutual opens a Manchester analytics hub. ([Example News](https://news.example/1), 2026-10-20)\n")
    return s, s.model()


def _job(model, company):
    return next((r for r in model["jobs"]["rows"] if r["company"] == company), None)


def test_one_age_everywhere_the_age_the_search_judged(page):
    """The card said posted 3 days ago of a posting the window had judged 4 (audit 12)."""
    _, m = page
    assert _job(m, "Brindle Hart Logistics")["posted_days"] == 4


def test_a_posting_past_the_window_leaves_the_list_by_itself(page):
    """The week rule hung on a chat remembering to run a script (audit 10)."""
    _, m = page
    assert _job(m, "Quayside Foods") is None


def test_a_role_applied_for_is_applied_whatever_a_ruling_says(page):
    """Applied 16 Sept, it read "Set aside" with "Bring back" (audit 14)."""
    _, m = page
    assert _job(m, "Larkspur Retail")["status"] == "applied"


def test_the_bar_and_the_score_say_why_in_plain_words(page):
    """"tier 2 employer (rogers): major brand, strong pay band" and a command (audit 17)."""
    _, m = page
    brindle = _job(m, "Brindle Hart Logistics")
    assert "A major brand with a strong pay band." in brindle["notes"]
    assert not any("tier 2" in n or "`" in n or "tools/" in n for r in m["jobs"]["rows"]
                   for n in r["notes"])
    assert brindle["why"][0] == "Matches your skills: SQL, Python, forecasting"
    assert not any("Halloway" in w for w in brindle["why"]), "a contact's first name only"
    fernhill = _job(m, "Fernhill Freight")
    assert any(n.startswith("You applied here before") for n in fernhill["notes"])


def test_a_score_says_its_good_reasons_and_its_watch_outs_apart(page):
    """"Why 100: Matches your skills ... Asks for a graduate degree, with no other way in":
    a gap run on after the match read as a contradiction of the 100, and "with no other way
    in" as a riddle (the maintainer, 2026-11-04)."""
    _, m = page
    reasons = _job(m, "Brindle Hart Logistics")["reasons"]
    assert reasons["good"] == "Matches your skills: SQL, Python, forecasting."
    assert reasons["watch"] == ("Asks for a graduate degree, and does not say experience can "
                                "stand in for one.")
    assert app_model.reasons_of(["-8 stated 5+ years against 4 held"]) == {
        "good": "", "watch": "Asks for 5+ years; you have 4."}


def test_a_cards_place_is_the_town_where_the_posting_adds_its_country(page):
    """"Toronto, Ontario, Canada" took the card's line of facts onto a second line (the
    maintainer, 2026-11-04); "Remote, UK" says how it is worked and stays whole."""
    _, m = page
    assert _job(m, "Brindle Hart Logistics")["place_short"] == "Manchester"
    assert [app_model.short_place(p) for p in ("Toronto, Ontario, Canada", "Remote, UK",
                                               "Toronto, ON (Hybrid)", "Manchester (hybrid)", "")] \
        == ["Toronto", "Remote, UK", "Toronto (Hybrid)", "Manchester (hybrid)", ""]


def test_the_note_about_an_unanswered_message_names_who_has_it(page):
    """"Someone here has your message and has not replied" sat under a box saying someone
    there had replied, and read as one person said two ways (the maintainer, 2026-11-04)."""
    _, m = page
    notes = _job(m, "Fernhill Freight")["notes"]
    assert "Wren has your message and has not replied: applying is fine, a second message is not." in notes
    assert not any("Halloway" in n or n.startswith("Someone here") for n in notes)


def test_a_tool_asked_for_and_the_one_you_have_is_one_plain_sentence():
    """"Asked for SAS, you have Python: shown as Python." (2026-11-04), said once: never
    beside the card's own suggestion offering the same tool."""
    job = {"near": [{"asked": "SAS", "have": "Python"}], "suggest": None}
    assert app_model.near_words(job, "CV") == "It asks for SAS. You have Python, so your CV names Python."
    offered = dict(job, suggest={"kind": "near", "text": "The posting asks for SAS; you have Python."})
    assert app_model.near_words(offered, "CV") == ""


def test_each_job_says_the_day_it_was_first_found(page):
    """Jobs said when the last search ran, never when each job was found: searches run more
    than once, and a role surfaced weeks ago may be one to put away (the maintainer,
    2026-11-05). The day is the earliest any search saw the posting."""
    _, m = page
    brindle = _job(m, "Brindle Hart Logistics")
    assert brindle["found_on"] == "2026-10-25" and brindle["found_days"] == 0
    import datetime as dt
    assert app_model.found_on({"first_seen": "2026-10-20"}, {"first_seen": "2026-10-12"}) == dt.date(2026, 10, 12)
    assert app_model.found_on({}, None, dt.date(2026, 10, 3)) == dt.date(2026, 10, 3)
    assert app_model.found_on({"added_on": "2026-10-30"}) == dt.date(2026, 10, 30)


def test_the_pay_the_search_read_is_on_the_card(page):
    """Every card said "Pay not stated" beside a note quoting the range (audit 7)."""
    _, m = page
    pay = _job(m, "Brindle Hart Logistics")["pay"]
    assert pay["stated"] and pay["text"] == "GBP 44,000 to 52,000"


def test_the_summary_counts_what_is_left_to_look_at(page):
    """"10 roles on the shortlist" counted the one applied for and the one set aside (13)."""
    _, m = page
    look = [r for r in m["jobs"]["rows"] if app_model.to_look_at(r)]
    assert m["jobs"]["summary"].startswith(f"{len(look)} roles from the last search to look at")
    assert "Larkspur Retail" not in {r["company"] for r in look}


def test_the_resume_that_breaks_the_persons_rules_is_never_offered(page):
    """"Get this one anyway" and "Free, instant" handed out a resume the person must never
    send (audit 23)."""
    import pdftext
    if not pdftext.reader():
        pytest.skip("no PDF reader here: the check reads the resume's own text")
    _, m = page
    r = m["resume"]
    assert r["get"] is None and r["file"]["asset"] is None
    said = " ".join(r["breaks"])
    assert "“Organized”" in said and "dashes" in said and "“resume”" in said


def test_a_screening_gap_is_the_persons_to_answer_never_a_copy(page):
    """One tap pasted "[check the tracker row]" into an employer's form (audit 25)."""
    _, m = page
    kestrel = next(a for a in m["ready"] if a["company"] == "Kestrel Mutual")
    gap = next(q for q in kestrel["screening"] if q["q"] == "How did you hear about this role?")
    assert gap == {"q": "How did you hear about this role?", "a": "", "fill": True}
    # Every other answer carries the note it was drafted with, so it can be judged first.
    assert kestrel["screening"][0]["a"] == "Yes" and kestrel["screening"][0]["why"] == "A note."


def test_a_brief_line_naming_someone_is_about_them(page):
    """"Send <name> the CV" linked nothing and stood under Today's "Reply to <name>" (34)."""
    _, m = page
    step = next(i for sec in m["brief"]["sections"] for i in sec["items"]
                if i["text"].startswith("Send Juno Castellan"))
    assert step["item"] == "larkspur_retail_castellan" and step["section"] == "people"


def test_news_carried_from_an_earlier_brief_says_todays_search_found_nothing_newer(page):
    """"Gathered Thu 29 Oct" on a daily brief read as no search for five days (audit 35)."""
    _, m = page
    assert m["brief"]["news_date"] == "2026-10-21"
    assert m["brief"]["news_searched"] == "2026-10-25"


# ------------------------------------------------------------------ in the engine alone


def test_when_a_file_was_written_is_its_commit_not_its_checkout(tmp_path):
    """"Searched 2 hours ago" and "Made Sat 31 Oct" were when the files were checked out
    (audit 21, 24)."""
    f = tmp_path / "r1.json"
    f.write_text("[]", encoding="utf-8")
    env = dict(os.environ, GIT_AUTHOR_DATE="2026-09-02T10:00:00+00:00",
               GIT_COMMITTER_DATE="2026-09-02T10:00:00+00:00", GIT_AUTHOR_NAME="t",
               GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.com")
    for cmd in (["git", "init", "-q"], ["git", "add", "r1.json"], ["git", "commit", "-qm", "r1"]):
        subprocess.run(cmd, cwd=tmp_path, env=env, check=True, capture_output=True)
    os.utime(f, (dt.datetime(2026, 10, 31).timestamp(),) * 2)       # checked out later
    assert app_model.saved_at(str(f)) == dt.datetime(2026, 9, 2, 10, tzinfo=dt.timezone.utc)
    f.write_text("[1]", encoding="utf-8")                              # changed since
    # Its own time, set here: the disk's clock is not Python's where the clock was moved, and
    # a date compared with today's read UTC against the computer's zone.
    os.utime(f, (dt.datetime(2026, 11, 1, 18, tzinfo=dt.timezone.utc).timestamp(),) * 2)
    assert app_model.saved_at(str(f)) == dt.datetime(2026, 11, 1, 18, tzinfo=dt.timezone.utc)


def test_a_commit_time_git_writes_with_a_z_is_read_on_every_python(tmp_path, monkeypatch):
    """A newer git writes UTC as "...Z", which Python 3.9 cannot read: the time fell back to
    the checkout, and only the 3.9 job saw it (CI, 2026-11-03)."""
    f = tmp_path / "r1.json"
    f.write_text("[]", encoding="utf-8")
    real = subprocess.run

    def git(cmd, *a, **kw):
        if cmd[:2] == ["git", "log"]:
            return subprocess.CompletedProcess(cmd, 0, "2026-09-02T10:00:00Z\n", "")
        if cmd[:2] == ["git", "diff"]:
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        return real(cmd, *a, **kw)
    monkeypatch.setattr(app_model.subprocess, "run", git)
    assert app_model.saved_at(str(f)) == dt.datetime(2026, 9, 2, 10, tzinfo=dt.timezone.utc)


def test_the_brief_counts_live_applications_as_the_page_does():
    """The brief said 65 live beside the page's 66: it left out a process with no
    application of its own (audit 29)."""
    rows = [{"company": "Kestrel Mutual", "role": "Analyst", "status": "applied"},
            {"company": "Brindle Hart Logistics", "role": "Analyst", "status": "interview"},
            {"company": "Quayside Foods", "role": "Analyst", "status": "interview",
             "channel": "referral", "notes": throttle.PROCESS_NOTE},
            {"company": "Larkspur Retail", "role": "Analyst", "status": "rejected"},
            {"company": "Dovecote Freight", "role": "Analyst", "status": "drafted"}]
    page_live = sum(1 for r in rows if r["status"] not in throttle.UNSENT
                    and r["status"] not in throttle.FINAL)
    assert brief.live_counts(rows)["applications"] == page_live == 3


def test_the_briefs_opening_names_no_chat_and_no_command():
    """"its own chat (<employer> campaign (this chat)) has the prep" (audit 37)."""
    counts = {"processes": [{"company": "Kestrel Mutual", "status": "interview"}],
              "applications": 1}
    owned = brief._lead(counts, [], [], False, [], {"kestrel mutual": "Kestrel campaign (this chat)"},
                        dt.date(2026, 10, 25))
    plain = brief._lead(counts, [], [], False, [], {}, dt.date(2026, 10, 25))
    for line in (owned, plain):
        assert "(this chat)" not in line and "/interview" not in line and "campaign" not in line, line


class _Ctx:
    """Just what a job card's alerts read."""
    today = dt.date(2026, 10, 25)
    network = ({}, {}, {})
    live = {"larkspur_retail_castellan": "in_conversation"}
    by_contact = {}
    contacts = [{"contact_id": "larkspur_retail_castellan", "name": "Juno Castellan",
                 "company": "Larkspur Retail", "next_action": "", "notes": ""}]


def test_a_failed_check_is_said_once_with_one_full_stop_in_a_persons_words(tmp_path):
    """"A sentence was changed after the checks read it.." reached a draft's card (the
    maintainer, 2026-11-05): the verify step's line ends with its own full stop."""
    checks = app_model._with_verify({"passed": True, "line": "Made"},
                                    {"passed": False, "items": [{"said": app_model.VERIFY_WORDS["UNAUDITED"]}]})
    assert checks["line"] == "It was changed after it was last checked."
    item = {"id": "app-x", "company": "Kestrel Mutual", "role": "Analyst", "status": "drafted", "checks": checks,
            "apply": {"status": "open", "kind": "employer", "url": "https://jobs.example/k"}, "near": []}
    alerts, _ = app_alerts.for_ready(_Ctx(), item, {}, str(tmp_path))
    assert alerts[0]["text"] == "It was changed after it was last checked.", alerts[0]["text"]


def test_a_closed_posting_is_set_aside_for_its_reason_and_offers_no_one_to_ask():
    """Its "Set it aside" asked why again, from a list without "It has closed", and the card
    still said to ask someone about the role (audit 19, 8)."""
    item = {"id": "r9-2", "company": "Larkspur Retail", "status": "new",
            "apply": {"status": "closed", "checked_on": "2026-10-24"}, "deadline": None}
    alerts, suggest = app_alerts.for_job(_Ctx(), item)
    closed = next(a for a in alerts if a["kind"] == "closed")
    assert closed["action"]["value"] == {"why": "closed"}
    assert suggest is None
    open_item = dict(item, apply={"status": "open"})
    assert app_alerts.for_job(_Ctx(), open_item)[1]["kind"] == "warm"


def test_what_a_draft_needs_that_claude_can_do_is_queued_by_itself_once(tmp_path, monkeypatch):
    """"Make it again" and "Get my files ready" were buttons on a draft's card for what Claude
    can do with no one asking (the maintainer, 2026-11-05): the view queues the remake of a
    draft whose check failed with its fix in hand, and the upload of PDFs the page lacks, once
    each; a view run again queues nothing more."""
    import importlib
    app = importlib.import_module("app")
    monkeypatch.setattr(app_model, "files_missing", lambda ctx=None: [
        {"id": "app-y", "company": "Fernhill Freight", "files": ["Morgan_CV_Fernhill.pdf"], "paths": ["cv/Morgan_CV_Fernhill.pdf"]}])
    act = {"type": "work", "kind": "draft", "label": "Make it again", "id": "draft~app-x",
           "title": "Make it again: Kestrel Mutual", "args": {"application": "app-x", "redo": True}}
    model = {"ready": [{"id": "app-x", "status": "drafted", "alerts": [{"kind": "checks", "action": act}]}]}
    now = dt.datetime(2026, 11, 5, 9, tzinfo=dt.timezone.utc)
    batches = app.self_fixes({"work": {}}, model, str(tmp_path / "a"), now)
    made = {}
    for b in batches:
        for e in json.loads(open(b, encoding="utf-8").read()):
            made[e["doc_id"]] = json.loads(open(e["file_path"], encoding="utf-8").read())
    assert made["draft~app-x"]["kind"] == "draft" and made["draft~app-x"]["args"]["auto"] is True
    files = [w for w in made.values() if w["kind"] == "files"]
    assert files and files[0]["args"]["applications"] == ["app-y"], made
    db = {"work": {wid: {"data": w, "version": 1} for wid, w in made.items()}}
    db["work"]["files~app-y"]["data"]["status"] = "done"
    assert app.self_fixes(db, model, str(tmp_path / "b"), now) == [], "once each, never again"
