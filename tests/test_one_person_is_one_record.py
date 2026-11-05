"""One person is one record: an import finds the record already there, a duplicate closed as
the same person gives what it holds to the one kept, and the page lists that one only.

A person's copy (2026-11-05): a recruiter was kept as his first name only, with no employer
and an id carrying his surname. LinkedIn's export gave his full name, his firm and a profile
address in another form, so the import listed him as new; a second record was added and his
old messages copied into it. Closed as a duplicate, the second still showed beside the first
on Contacts, and the one kept had no employer to show or be found by. Invented people only.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.join(ROOT, "tests")]

import export  # noqa: E402
import state  # noqa: E402
from test_the_message_log_says_what_happened import ME, _messages  # noqa: E402

THEM = "https://www.linkedin.com/in/" + "ACoAAB9x" + "ExampleRobinVale"   # the export's member-id form, built so no scan reads it as a real handle
NOTE = "Hi Robin, thanks for getting in touch about the analytics roles you are hiring for."


def _robin(**kw):
    return {"contact_id": "recruiter_vale", "name": "Robin", "company": "", "company_key": "",
            "title": "", "linkedin_url": "", "status": "replied_needs_response", "notes": "",
            "outcome": "", **kw}


def _t(cid, date, direction, text):
    return {"contact_id": cid, "date": date, "direction": direction, "channel": "message",
            "scenario": "", "summary": "logged", "full_text": text, "subject": ""}


def _export(tmp_path, connections=True):
    ex = tmp_path / "export"
    ex.mkdir()
    _messages(ex, [
        f"c1,,Morgan Ellis,{ME},Robin Vale,{THEM},2026-10-01 10:00:00 UTC,,\"{NOTE}\",INBOX,",
        f"c1,,Robin Vale,{THEM},Morgan Ellis,{ME},2026-10-04 09:00:00 UTC,,Happy to talk next "
        "week about the forecasting role,INBOX,"])
    if connections:
        (ex / "Connections.csv").write_text(
            "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
            f"Robin,Vale,{THEM},,Juniper Talent,Senior Recruiter,01 Oct 2026\n", encoding="utf-8")
    return str(ex)


def test_an_import_finds_him_by_a_message_already_logged_and_fills_what_he_lacks(tmp_path):
    contacts = [_robin()]
    threads = [_t("recruiter_vale", "2026-10-01", "out", NOTE)]
    plan = export.plan_history(contacts, threads, _export(tmp_path))
    assert plan["unmatched"] == [], plan["unmatched"]
    assert plan["joined"].get("logged message") == 1, plan["joined"]
    # Only the message not there yet is added, to the record already in the book.
    assert [(r["contact_id"], r["date"]) for r in plan["add"]
            if r["channel"] == "message"] == [("recruiter_vale", "2026-10-04")]
    filled = export.fill_who(plan["who"])
    assert contacts[0]["company"] == "Juniper Talent" and contacts[0]["title"] == "Senior Recruiter"
    assert state.profile_handle(contacts[0]["linkedin_url"]) == state.profile_handle(THEM)
    assert contacts[0]["name"] == "Robin Vale" and filled


def test_an_import_finds_him_by_first_name_and_the_surname_in_his_id(tmp_path):
    contacts = [_robin(), _robin(contact_id="harbour_okafor", name="Robin", company="Harbourline Bank",
                                 company_key="harbourline bank")]
    plan = export.plan_history(contacts, [], _export(tmp_path))
    assert plan["unmatched"] == [] and plan["joined"].get("first name") == 1, plan
    assert {r["contact_id"] for r in plan["add"]} == {"recruiter_vale"}
    # A first name alone, with no surname anywhere on the record, is nobody's.
    plan = export.plan_history([_robin(contact_id="recruiter_x")], [], str(tmp_path / "export"))
    assert [u["name"] for u in plan["unmatched"]] == ["Robin Vale"]


def test_closed_as_the_same_person_it_gives_the_kept_one_what_it_lacks(tmp_path):
    kept = _robin()
    second = _robin(contact_id="juniper_talent_vale", name="Robin Vale", company="Juniper Talent",
                    company_key="juniper talent", title="Senior Recruiter", linkedin_url=THEM,
                    status="replied_needs_response")
    contacts = [kept, second]
    threads = [_t("recruiter_vale", "2026-10-01", "out", NOTE),
               _t("juniper_talent_vale", "2026-10-01", "out", NOTE)]
    found = {p["reason"] for p in state.reconcile(contacts, threads)}
    assert "shared_message" in found, found
    got = state.same_person(contacts, "juniper_talent_vale", "recruiter_vale")
    assert got["filled"] == ["company", "company_key", "title", "linkedin_url"], got
    assert kept["company"] == "Juniper Talent" and "juniper_talent_vale" in kept["notes"]
    assert second["status"] == "closed" and second["outcome"] == "duplicate of recruiter_vale"
    assert state.duplicate_of(contacts) == {"juniper_talent_vale": "recruiter_vale"}
    found = {p["reason"] for p in state.reconcile(contacts, threads)}
    assert "shared_message" not in found and "duplicate_holds_more" not in found, found
    # Closed by hand without carrying anything over: reconcile says what the kept one lacks.
    kept2 = _robin()
    second2 = dict(second, status="closed", outcome="the same person as recruiter_vale", notes="")
    found = [p for p in state.reconcile([kept2, second2], threads)
             if p["reason"] == "duplicate_holds_more"]
    assert found and "company" in found[0]["detail"] and "same-person" in found[0]["detail"], found
    # "Not the same person as" is never read as a duplicate.
    assert state.duplicate_of([kept2, dict(second, status="closed", outcome="",
                                           notes="not the same person as recruiter_vale")]) == {}


def test_the_page_lists_the_kept_one_only_with_both_threads(tmp_path, monkeypatch):
    import csv
    import json
    import subprocess
    import app_state
    st = app_state.small(str(tmp_path / "state"))
    profile = app_state.profile_copy(str(tmp_path / "profile"))
    path = os.path.join(st, "network_contacts.csv")
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    cols = list(rows[0].keys())
    rows.append(dict.fromkeys(cols, "") | {
        "contact_id": "fernhill_wren_dup", "name": "Wren Halloway", "company": "",
        "status": "closed", "outcome": "duplicate of fernhill_freight_halloway"})
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    tpath = os.path.join(st, "network_threads.csv")
    with open(tpath, encoding="utf-8", newline="") as fh:
        trows = list(csv.DictReader(fh))
    tcols = list(trows[0].keys())
    trows.append(dict.fromkeys(tcols, "") | {
        "contact_id": "fernhill_wren_dup", "date": "2026-10-20", "direction": "inbound",
        "channel": "linkedin", "summary": "their note",
        "full_text": "Thanks for reaching out, the planning team is hiring in the new year."})
    with open(tpath, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=tcols)
        w.writeheader()
        w.writerows(trows)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "model", "--now",
                        "2026-10-25T18:00:00Z"], capture_output=True, encoding="utf-8", timeout=120,
                       env=dict(os.environ, LJS_STATE=st, LJS_PROFILE=profile))
    model = json.loads(r.stdout)
    ids = [p["id"] for p in model["people"]]
    assert "fernhill_wren_dup" not in ids and "fernhill_freight_halloway" in ids, ids
    kept = next(p for p in model["people"] if p["id"] == "fernhill_freight_halloway")
    assert "the planning team is hiring" in json.dumps(kept), kept
