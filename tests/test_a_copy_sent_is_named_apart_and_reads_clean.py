"""Every copy sent has a name of its own, opens anywhere, and holds only what the person reads.

The interview audit (2026-10-25) found the names tools/shown.py gave could collide: every
bracket with a digit in it was dropped, so two openings of one role under two requisition
numbers, and "(Level 2)" beside "(Level 3)", went out under one name; a long role name was
cut at 120 characters and took the label with it, so a prep, a record and the form answers
shared a name; two people of one name at one employer shared a call prep's name; the cap
counted letters, not bytes, and a Japanese name ran past what a disk allows; and the
copies carried the tools' own comments. A copy checked after a hand edit was never made
again. Every person and employer here is invented.
"""
from __future__ import annotations

import csv
import io
import os
import sys
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import outreach  # noqa: E402
import person  # noqa: E402
import prep  # noqa: E402
import record_drafts  # noqa: E402
import safe_name  # noqa: E402
import schema  # noqa: E402
import shown  # noqa: E402

FIRM = "Fernhill Freight"


def _state(tmp_path, monkeypatch, roles=(), contacts=()):
    st = tmp_path / "state"
    st.mkdir()
    monkeypatch.setenv(person.STATE_ENV, str(st))
    with open(st / "job_search_tracker.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=record_drafts.HEADER)
        w.writeheader()
        for company, role in roles:
            row = {k: "" for k in record_drafts.HEADER}
            row.update(date="2026-10-01", company=company, role=role, status="interview")
            w.writerow(row)
    with open(st / "network_contacts.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=schema.CONTACT_COLUMNS)
        w.writeheader()
        for cid, name, company, title in contacts:
            row = {k: "" for k in schema.CONTACT_COLUMNS}
            row.update(contact_id=cid, name=name, company=company, title=title)
            w.writerow(row)
    return st


def _write(path, text="x\n"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return str(path)


def _living(company, role):
    return _write(os.path.join(outreach.app_folder(company, role), "interview_prep.md"))


def test_two_openings_under_two_requisition_numbers_keep_their_numbers(tmp_path, monkeypatch):
    roles = ("Data Scientist II (R_1506034)", "Data Scientist II (R_1609921)")
    _state(tmp_path, monkeypatch, roles=[(FIRM, r) for r in roles])
    names = {shown.name_for(_living(FIRM, r)) for r in roles}
    assert len(names) == 2
    assert all("R_1" in n for n in names)


def test_one_opening_loses_its_number_and_a_level_is_never_dropped(tmp_path, monkeypatch):
    roles = ("Planner (R_2045511)", "Analyst (Level 2)", "Analyst (Level 3)")
    _state(tmp_path, monkeypatch, roles=[(FIRM, r) for r in roles])
    assert shown.name_for(_living(FIRM, roles[0])) == "Fernhill Freight Planner interview prep"
    levels = {shown.name_for(_living(FIRM, r)) for r in roles[1:]}
    assert levels == {"Fernhill Freight Analyst (Level 2) interview prep",
                      "Fernhill Freight Analyst (Level 3) interview prep"}


def test_a_long_name_is_cut_in_the_part_that_says_whose_never_the_label(tmp_path, monkeypatch):
    role = "Senior " + "supply chain network optimisation " * 8 + "Lead"
    _state(tmp_path, monkeypatch, roles=[(FIRM, role)])
    folder = outreach.app_folder(FIRM, role)
    kinds = {}
    for stem in ("interview_prep", "outcome", "screening_answers"):
        name = shown.name_for(_write(os.path.join(folder, stem + ".md")))
        assert len(name.encode("utf-8")) <= shown.MAX_NAME_BYTES
        kinds[stem] = name
    assert kinds["interview_prep"].endswith("interview prep")
    assert kinds["outcome"].endswith("interview record")
    assert kinds["screening_answers"].endswith("form answers")
    assert len(set(kinds.values())) == 3


def test_a_name_in_another_script_is_capped_in_bytes(tmp_path, monkeypatch):
    # 72 letters of Japanese are over 200 bytes, and with the employer past what a disk allows.
    who, company = "ジュノ・カステラン" * 8, "株式会社ファーンヒル物流" * 3   # invented
    st = _state(tmp_path, monkeypatch, contacts=[("fernhill_castellan", who, company, "")])
    name = shown.name_for(_write(st / "documents" / "network" / "fernhill_castellan" / "prep.md"))
    assert len(name.encode("utf-8")) <= shown.MAX_NAME_BYTES
    assert name.endswith("call prep") and name.startswith("ジュノ")


def test_two_people_of_one_name_at_one_employer_get_a_prep_name_each(tmp_path, monkeypatch):
    st = _state(tmp_path, monkeypatch, contacts=[
        ("fernhill_allard", "Wren Allard", FIRM, "Data Scientist"),
        ("fernhill_allard_w", "Wren Allard", FIRM, "Head of Planning"),
        ("brindle_okoro", "Juno Okoro", "Brindle Hart", ""),
        ("brindle_okoro_j", "Juno Okoro", "Brindle Hart", "")])
    net = st / "documents" / "network"
    a = shown.name_for(_write(net / "fernhill_allard" / "prep.md"))
    b = shown.name_for(_write(net / "fernhill_allard_w" / "prep.md"))
    assert a == "Wren Allard, Data Scientist (Fernhill Freight) call prep"
    assert b == "Wren Allard, Head of Planning (Fernhill Freight) call prep"
    c = shown.name_for(_write(net / "brindle_okoro" / "prep.md"))
    d = shown.name_for(_write(net / "brindle_okoro_j" / "prep.md"))
    assert c != d and c.startswith("Juno Okoro 1") and d.startswith("Juno Okoro 2")


def test_a_name_windows_refuses_is_never_given():
    assert shown._clean("CON") == "CON_"
    assert not safe_name.reserved(shown._clean("nul"))


def test_the_copy_holds_none_of_the_tools_comments_and_is_made_again(tmp_path, monkeypatch):
    st = _state(tmp_path, monkeypatch, roles=[(FIRM, "Planner")])
    doc = _write(os.path.join(outreach.app_folder(FIRM, "Planner"), "interview_prep.md"),
                 "# Interview prep\n<!-- stages: 2026-10-01 -->\n\nSay this.<!-- quoted -->\n\n"
                 "<!-- generated answers: {\"q1\": \"abc\"}\n-->\n\n## Notes\nKeep.\n")
    sent = st / shown.copy(doc)
    text = sent.read_text(encoding="utf-8")
    assert "<!--" not in text and "generated answers" not in text
    assert text == "# Interview prep\n\nSay this.\n\n## Notes\nKeep.\n"
    with open(doc, "a", encoding="utf-8") as fh:
        fh.write("Added by hand.\n")
    assert "Added by hand." in (st / shown.copy(doc)).read_text(encoding="utf-8")


def test_a_passing_check_on_a_call_prep_makes_the_copy_again(tmp_path, monkeypatch):
    st = _state(tmp_path, monkeypatch, contacts=[("fernhill_allard", "Wren Allard", FIRM, "")])
    doc = _write(st / "documents" / "network" / "fernhill_allard" / "prep.md",
                 "# Call prep\n\nNothing written yet.\n")
    out = io.StringIO()
    with redirect_stdout(out):
        code = prep.main(["fernhill_allard", "--check", "--root", str(st),
                          "--contacts", str(st / "network_contacts.csv")])
    assert code == 0
    assert "send: documents/to_send/Wren Allard (Fernhill Freight) call prep.md" in \
        out.getvalue()
    assert os.path.isfile(st / "documents" / "to_send" / "Wren Allard (Fernhill Freight) "
                          "call prep.md")
    assert doc
