"""LinkedIn's data export, read by one reader: the connections, the message history into the
log, and the invitations still waiting for the person to withdraw on LinkedIn.

The import read Connections.csv alone, so the app could not see who was written to on
LinkedIn itself, who replied, who was owed a reply, or that a resume had already gone; and
a backlog of requests nobody accepted, some six months old, was never offered for
withdrawal although it counts against how many LinkedIn lets a person send. Every name,
address and message here is invented (tests/fixtures/linkedin_export/README.md).
"""
import datetime
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import claude_surfaces  # noqa: E402
import export as E  # noqa: E402
import state  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "linkedin_export"
TODAY = datetime.date(2026, 10, 21)


def _book(tmp_path):
    """A copy of the invented contact book and log, and their paths."""
    c, t = tmp_path / "network_contacts.csv", tmp_path / "network_threads.csv"
    shutil.copy(FIX / "book_contacts.csv", c)
    shutil.copy(FIX / "book_threads.csv", t)
    return state.load_contacts(str(c)), state.load_threads(str(t)), str(c), str(t)


# ------------------------------------------------------------ one reader

def test_one_reader_finds_a_header_in_any_case_below_its_notes_and_names_what_is_missing(tmp_path):
    conns = tmp_path / "Connections.csv"
    conns.write_text("Notes:\n\"Some addresses are missing.\"\n\nfirst name,LAST NAME,url,"
                     "company,position,connected on\nWren,Halloway,"
                     "https://www.linkedin.com/in/example-wren-halloway,Fernhill Freight,"
                     "Head of Planning,01 Mar 2024\n", encoding="utf-8")
    got = E.read("connections", str(conns))
    assert got["usable"] and got["rows"][0]["First Name"] == "Wren"
    assert got["missing"] == ["Email Address"]
    # The connections path reads through it: a header in another case was read as nobody.
    assert [c["name"] for c in state.first_degree(str(conns))] == ["Wren Halloway"]
    # A message whose words run over several lines is one row, not several.
    msgs = tmp_path / "messages.csv"
    msgs.write_text("FROM,DATE,CONTENT\nJuno Castellan,2026-09-12 08:40:00 UTC,\"Line one.\n\n"
                    "Line two.\"\n", encoding="utf-8")
    got = E.read("messages", str(msgs))
    assert len(got["rows"]) == 1 and got["rows"][0]["CONTENT"] == "Line one.\n\nLine two."
    assert "ATTACHMENTS" in got["missing"] and got["usable"]
    # A file without a column it cannot do without, or not there at all, is named, not a crash.
    (tmp_path / "Invitations.csv").write_text("From,To\nMorgan Ellis,Juno Castellan\n",
                                              encoding="utf-8")
    assert not E.read("invitations", str(tmp_path))["usable"]
    assert E.describe([E.read("profile", str(tmp_path))]) == ["Profile.csv is not in it"]


def test_from_an_archive_only_the_files_named_are_opened(tmp_path, monkeypatch):
    archive = tmp_path / "Complete_LinkedInDataExport.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for name in ("messages.csv", "Invitations.csv", "Profile.csv"):
            z.write(FIX / name, name)
        z.writestr("guide_messages.csv", "FROM,DATE,CONTENT\nA guide,2026-01-01,private\n")
        z.writestr("Ad_Targeting.csv", "Audience\n25-34\n")
    opened = []
    real = zipfile.ZipFile.read
    monkeypatch.setattr(zipfile.ZipFile, "read",
                        lambda self, name, *a: opened.append(name) or real(self, name, *a))
    said = E.save([str(archive)], only="history", dest=str(tmp_path / "saved"))
    assert sorted(opened) == ["Invitations.csv", "messages.csv"]
    assert said == ("Saved messages.csv and Invitations.csv. I read only those from the archive; "
                    "the other 3 files in it were not opened. Not saved: Connections.csv (not "
                    "in it).")
    assert sorted(p.name for p in (tmp_path / "saved").iterdir()) == ["Invitations.csv",
                                                                       "messages.csv"]


def test_every_form_of_a_profile_address_is_one_person():
    forms = ("https://ca.linkedin.com/in/Example-Juno-Castellan/",
             "uk.linkedin.com/in/example-juno-castellan?trk=public",
             "https://www.linkedin.com/in/%65xample-juno-castellan/en",
             "http://linkedin.com/in/example-juno-castellan")
    assert {state.profile_handle(f) for f in forms} == {"example-juno-castellan"}
    book = [{"contact_id": "larkspur_retail_castellan", "name": "Juno Castellan",
             "linkedin_url": "https://www.linkedin.com/in/example-juno-castellan"}]
    for f in forms:
        assert E.match_contact(book, "J. Castellan", f) == (book[0], "profile address")


# ------------------------------------------------------------ names

def test_letters_after_a_name_are_not_its_surname():
    # "<Given> <Surname>, FIRP, GMS" became the surname "GMS", the id "<employer>_gms" and a
    # name that matched nobody in the contact book.
    assert state.person_name("Corwin Haldane, FIRP, GMS") == "Corwin Haldane"
    assert state.contact_id("Corwin Haldane, FIRP, GMS", "Fernhill Freight") == \
        "fernhill_freight_haldane"
    assert state.person_name("Corwin Haldane, P.Eng.") == "Corwin Haldane"
    # A name written back to front keeps both halves, in capitals too.
    assert state.person_name("Haldane, Corwin") == "Haldane Corwin"
    assert state.person_name("HALDANE, CORWIN") == "HALDANE CORWIN"


# ------------------------------------------------------------ the history

def test_the_history_joins_by_address_and_by_a_bare_name_and_never_by_a_lookalike(tmp_path):
    contacts, threads, _c, _t = _book(tmp_path)
    plan = E.plan_history(contacts, threads, str(FIX))
    added = {(r["contact_id"], r["date"], r["direction"]) for r in plan["add"]}
    # The address in three forms is one person; the two messages the log holds are not added.
    assert ("larkspur_retail_castellan", "2026-09-13", "out") in added
    assert ("larkspur_retail_castellan", "2026-09-20", "in") in added
    assert ("larkspur_retail_castellan", "2026-09-10", "out") not in added
    assert ("larkspur_retail_castellan", "2026-09-12", "in") not in added
    resume = next(r for r in plan["add"] if r["date"] == "2026-09-13")
    assert "a resume attached (Morgan_Ellis_CV.pdf)" in resume["summary"]
    assert resume["full_text"] == "Thanks Juno, my CV is attached."
    # "Corwin Haldane, FIRP, GMS" is the book's Corwin Haldane, who has no address on file;
    # the note the log kept with no words is given its words rather than added twice.
    assert ("fernhill_freight_haldane", "2026-09-29", "in") in added
    assert [(r["date"], t[:9]) for r, t in plan["fill"]] == [("2026-09-25", "Hi Corwin")]
    # Bob Smith is not the book's Robert Smith, and another Wren Halloway at a different address is not her.
    assert {u["name"] for u in plan["unmatched"]} == {"Bob Smith", "Wren Halloway"}
    assert not {cid for cid, _d, _w in added} & {"kestrel_mutual_smith", "fernhill_freight_halloway"}
    # A request only the export knew, and an acceptance only Connections.csv says.
    assert ("kestrel_mutual_varga", "2026-03-02", "out") in added
    assert ("fernhill_freight_okonedo", "2026-09-20", "in") in added
    assert plan["groups"] == 1 and plan["joined"] == {"profile address": 3, "name": 1}


def test_two_rows_with_one_name_are_never_guessed_between(tmp_path):
    (tmp_path / "messages.csv").write_text(
        "CONVERSATION ID,FROM,SENDER PROFILE URL,TO,DATE,CONTENT\n"
        "c1,Juno Castellan,https://www.linkedin.com/in/example-someone-new,Morgan Ellis,"
        "2026-10-01 09:00:00 UTC,Hello\n", encoding="utf-8")
    book = [{"contact_id": "a_castellan", "name": "Juno Castellan", "company": "Larkspur Retail"},
            {"contact_id": "b_castellan", "name": "Juno Castellan", "company": "Kestrel Mutual"}]
    plan = E.plan_history(book, [], str(tmp_path))
    assert plan["add"] == [] and [a["name"] for a in plan["ambiguous"]] == ["Juno Castellan"]


def test_importing_twice_adds_nothing_and_the_log_then_says_who_is_owed(tmp_path, capsys,
                                                                         monkeypatch):
    # Read from elsewhere, the export is saved where it is kept first: here, this test's own.
    monkeypatch.setenv("LJS_STATE", str(tmp_path / "state"))
    _contacts, _threads, c, t = _book(tmp_path)
    args = ["history", "--apply", "--from", str(FIX), "--contacts", c, "--threads", t,
            "--today", TODAY.isoformat()]
    assert E.main(args) == 0
    first = Path(t).read_text(encoding="utf-8")
    assert E.main(args) == 0
    assert Path(t).read_text(encoding="utf-8") == first
    assert "0 message rows to add and 0 already logged" in capsys.readouterr().out
    contacts, threads = state.load_contacts(c), state.load_threads(t)
    owed = {i["contact_id"]: i["kind"] for i in state.owed(contacts, threads, TODAY)}
    assert owed["larkspur_retail_castellan"] == "reply"       # their message came last
    assert owed["fernhill_freight_haldane"] == "reply"
    assert owed["fernhill_freight_okonedo"] == "first_message"   # accepted a bare request
    # The rows the log decides are brought in line, so the import is no list of contradictions.
    assert not [p for p in state.reconcile(contacts, threads)
                if p["reason"] in ("contradicts_log", "duplicate_message")]
    # Nothing was sent: every new row is the export's record of what already happened.
    assert all("from LinkedIn's export" in r["summary"] for r in threads[5:])


# ------------------------------------------------------------ invitations still waiting

def test_invitations_waiting_are_listed_oldest_first_never_the_accepted_or_the_recent(tmp_path):
    contacts, threads, _c, _t = _book(tmp_path)
    found = E.pending(contacts, threads, TODAY, str(FIX))
    assert [i["name"] for i in found["items"]] == ["Tamsin Varga", "Quillon Varga"]
    assert found["items"][0]["contact_id"] == "kestrel_mutual_varga"
    assert found["younger"] == 1                       # Pell Ansgar, six days ago
    assert E.PENDING_DAYS == state.REQUEST_WITHDRAW_DAYS  # one rule, one number
    lines = E.pending_lines(found)
    assert lines[0].startswith("PENDING INVITATIONS  2 sent from LinkedIn more than 3 weeks ago")
    # The person withdraws on LinkedIn; the steps come from the dated registry only.
    assert E.WITHDRAW_STEPS in lines[-1] and "You do it on LinkedIn, one at a time" in lines[-1]
    steps = "\n".join(claude_surfaces.steps("linkedin-withdraw-invitation", today=TODAY))
    assert "one at a time" in steps and "up to three weeks" in steps


def test_a_withdrawal_they_report_is_recorded_and_never_suggested_again(tmp_path):
    contacts, threads, _c, _t = _book(tmp_path)
    got = E.withdrawn(contacts, threads, ["Quillon Varga", "Nobody Here"], TODAY, str(FIX),
                      reason="not accepted in six months")
    assert [n for n, _cid in got["done"]] == ["Quillon Varga"] and got["unknown"] == ["Nobody Here"]
    # Someone not in the book becomes a closed row, found again by their address.
    row = state.already_contacted(contacts, linkedin_url="https://ca.linkedin.com/in/"
                                                         "example-quillon-varga/")
    assert row["status"] == "closed" and "not accepted in six months" in row["outcome"]
    assert state.derive_status(state.threads_for(threads, row["contact_id"])) == "closed"
    # The oldest, by count: Tamsin Varga, whose request only the export had.
    got = E.withdrawn(contacts, threads, [], TODAY, str(FIX), oldest=1)
    assert got["done"] == [("Tamsin Varga", "kestrel_mutual_varga")]
    assert E.pending(contacts, threads, TODAY, str(FIX))["items"] == []


def test_the_state_view_lists_the_invitations_waiting(tmp_path, capsys, monkeypatch):
    _contacts, _threads, c, t = _book(tmp_path)
    monkeypatch.setattr(E, "default_folder", lambda: str(FIX))
    assert state.main(["--contacts", c, "--threads", t, "--tracker", str(tmp_path / "none.csv"),
                       "--today", TODAY.isoformat()]) == 0
    out = capsys.readouterr().out
    assert "PENDING INVITATIONS" in out and "Quillon Varga: sent 2026-04-15" in out
    assert E.WITHDRAW_STEPS in out
