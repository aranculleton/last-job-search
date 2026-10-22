"""Each job, process and contact has its own prep document, and it is sent under its name.

A person's report, 2026-10-22: the prep documents seemed to be one and the same, all called
"prep.md". Each was its own file, in a folder of its own, but every interview prep was sent
as "interview_prep.md" and every call prep as "prep.md", so two employers' documents looked
the same in the chat. What is sent is now a copy named for whose it is (tools/shown.py).

And a copy of a real repo held four older packs for the round its document was preparing,
under four names chats had given them: three were listed as earlier rounds, so their
stories counted as told already, and none was folded into the document.

Every person and employer here is invented.
"""
from __future__ import annotations

import csv
import io
import os
import sys
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import interview_pack as P  # noqa: E402
import outreach  # noqa: E402
import person  # noqa: E402
import prep  # noqa: E402
import record_drafts  # noqa: E402
import schema  # noqa: E402
import shown  # noqa: E402

FIRM = "Fernhill Freight"
ROLES = ("Demand Planner (R_2045511)", "Pricing Analyst")
LIVING_FOR = "Round 2 (technical)"


def _state(tmp_path, monkeypatch, process=False):
    st = tmp_path / "state"
    st.mkdir()
    monkeypatch.setenv(person.STATE_ENV, str(st))
    with open(st / "job_search_tracker.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=record_drafts.HEADER)
        w.writeheader()
        for role in ROLES:
            row = {k: "" for k in record_drafts.HEADER}
            row.update(date="2026-10-01", company=FIRM, role=role, status="interview",
                       channel="portal")
            if process:
                row["notes"] = "process, no portal application: led by Wren Allard"
            w.writerow(row)
    with open(st / "network_contacts.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=schema.CONTACT_COLUMNS)
        w.writeheader()
        for cid, name in (("fernhill_allard", "Wren Allard"), ("fernhill_okoro", "Juno Okoro")):
            row = {k: "" for k in schema.CONTACT_COLUMNS}
            row.update(contact_id=cid, name=name, company=FIRM)
            w.writerow(row)
    return st


def _write(path, text="x\n"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def test_two_roles_at_one_employer_and_two_contacts_have_a_document_each(tmp_path,
                                                                          monkeypatch):
    st = _state(tmp_path, monkeypatch)
    folders = {outreach.app_folder(FIRM, r) for r in ROLES}
    assert len(folders) == 2
    preps = {prep.prep_path({"contact_id": c}, str(st))
             for c in ("fernhill_allard", "fernhill_okoro")}
    assert len(preps) == 2 and all(p.endswith(os.sep + "prep.md") for p in preps)


def test_a_document_is_sent_under_whose_it_is(tmp_path, monkeypatch):
    st = _state(tmp_path, monkeypatch)
    living = _write(os.path.join(outreach.app_folder(FIRM, ROLES[0]), "interview_prep.md"))
    stage = _write(os.path.join(outreach.app_folder(FIRM, ROLES[1]),
                                "interview_prep_recruiter_screen.md"))
    call = _write(str(st / "documents" / "network" / "fernhill_allard" / "prep.md"))
    loose = _write(str(st / "documents" / "network" / "nobody_known" / "prep.md"))
    # The requisition number is the employer's filing, not part of the name.
    assert shown.name_for(living) == "Fernhill Freight Demand Planner interview prep"
    assert shown.name_for(stage) == "Fernhill Freight Pricing Analyst recruiter screen interview prep"
    assert shown.name_for(call) == "Wren Allard (Fernhill Freight) call prep"
    assert shown.name_for(loose) == "nobody known call prep"
    sent = shown.copy(call)
    assert sent == "documents/to_send/Wren Allard (Fernhill Freight) call prep.md"
    assert open(st / sent, encoding="utf-8").read() == "x\n"
    # The copies are made again on every send; git never keeps them.
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as fh:
        assert "documents/to_send/**" in fh.read().splitlines()


def test_a_name_holds_nothing_a_file_name_cannot():
    assert shown._clean('Acme: "Ops" / Planning?') == "Acme Ops Planning"


def test_the_prep_tools_print_the_copy_to_send(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch)
    living = _write(os.path.join(outreach.app_folder(FIRM, ROLES[1]), "interview_prep.md"))
    out = io.StringIO()
    with redirect_stdout(out):
        P._send_line(living)
    assert "send: documents/to_send/Fernhill Freight Pricing Analyst interview prep.md" in \
        out.getvalue()
    with open(os.path.join(ROOT, "tools", "network", "prep.py"), encoding="utf-8") as fh:
        assert "shown.copy(written, a.root)" in fh.read()


def test_an_older_pack_for_the_same_round_is_not_an_earlier_round():
    for name in ("interview_prep_round2_technical.md", "interview_prep_round_2.md",
                 "interview_prep_technical_round_2.md", "interview_prep_round_2_technical.md"):
        assert P._pack_for_round(name, LIVING_FOR), name
    for name in ("interview_prep_screen.md", "interview_prep_round_20.md",
                 "interview_prep_round_1.md"):
        assert not P._pack_for_round(name, LIVING_FOR), name


def test_an_older_pack_for_the_round_is_offered_to_fold_in(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch)
    folder = outreach.app_folder(FIRM, ROLES[0])
    _write(os.path.join(folder, "interview_prep.md"),
           "# Interview prep\n<!-- stages: %s -->\n\n## Notes\n" % LIVING_FOR)
    _write(os.path.join(folder, "interview_prep_round2_technical.md"))
    _write(os.path.join(folder, "interview_prep_screen.md"))      # an earlier round's record
    _write(os.path.join(folder, "cheat_sheet.md"))                 # kept by hand beside it
    got = {os.path.basename(r["path"]) for r in P.handkept_notes()}
    assert got == {"interview_prep_round2_technical.md", "cheat_sheet.md"}
    # Folded in: not offered again.
    with open(os.path.join(folder, "interview_prep.md"), "a", encoding="utf-8") as fh:
        for f in sorted(got):
            fh.write("- %s %s on 2026-10-22.\n" % (P.FOLDED, P._rel(os.path.join(folder, f))))
    assert P.handkept_notes() == []
    # An application with no living document has nothing to fold into.
    other = outreach.app_folder(FIRM, ROLES[1])
    _write(os.path.join(other, "interview_prep_round_2.md"))
    assert P.handkept_notes() == []
