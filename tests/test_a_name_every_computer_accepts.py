"""Every file name the app makes from a person's or an employer's name opens on Windows.

Windows refuses CON, PRN, AUX, NUL, COM1-9 and LPT1-9 as a file or folder name, in any
case and with any extension. A contact "Wren Con" with no employer got the id `con`, which
names their folder in documents/network/, and research about an employer keyed "prn" went
to `prn.json`: a repo holding either cannot be checked out on Windows. An employer written
in Chinese or Greek keyed to nothing, so its research could never be saved. Invented
names throughout.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import company_research  # noqa: E402
import safe_name  # noqa: E402
import state  # noqa: E402


def test_reserved_names_are_known_in_any_case_and_with_an_extension():
    for stem in ("con", "CON", "Prn", "aux.json", "nul.md", "com1", "LPT9.txt", "nul "):
        assert safe_name.reserved(stem), stem
    for stem in ("console", "acme_con", "comet", "lpt", "com10", "prn-co", ""):
        assert not safe_name.reserved(stem), stem


def test_windows_safe_marks_only_what_windows_refuses():
    assert safe_name.windows_safe("con") == "con_"
    assert safe_name.windows_safe("aux.notes") == "aux_.notes"
    assert safe_name.windows_safe("acme_rook") == "acme_rook"
    assert safe_name.windows_safe("trailing. ") == "trailing"


def test_a_contact_id_is_never_a_reserved_name():
    assert state.contact_id("Wren Con", "") == "con_"
    assert state.contact_id("Juno Nul", "") == "nul_"
    assert state.contact_id("Jo Lpt1", "") == "lpt1_"
    assert state.contact_id("Pell Aux", "Kestrel Mutual") == "kestrel_mutual_aux"
    for cid in ("con_", "nul_", "lpt1_"):
        assert not safe_name.reserved(cid)


def test_a_name_in_another_script_keeps_its_letters():
    # Wren Allard, the fixtures' invented contact, written in Greek letters.
    assert state.contact_id("Ρεν Άλαρντ", "Ωμέγα") == "ωμεγα_αλαρντ"
    assert state.contact_id("诺 卡斯特兰", "翠鸟物流")   # Juno Castellan, invented


def test_research_file_names_are_safe_and_keep_any_script():
    assert company_research.file_key("PRN") == "prn-co"
    assert company_research.file_key("Nul") == "nul-co"
    assert company_research.file_key("Kestrel Mutual") == "kestrel-mutual"
    assert company_research.file_key("Ωμέγα") == "ωμεγα"
    assert company_research.file_key("株式会社ファーンヒル")
    for k in ("PRN", "Nul", "COM1"):
        assert not safe_name.reserved(company_research.file_key(k))


def test_research_for_an_employer_in_another_script_can_be_saved(tmp_path):
    company = "株式会社ファーンヒル"   # Fernhill, the fixtures' invented employer
    path = company_research.target(company, root=str(tmp_path))
    assert os.path.basename(path) != ".json"
    assert os.path.basename(path).endswith(".json")


def test_names_are_capped_in_bytes_not_letters():
    long = "データ" * 200
    cut = safe_name.cap_bytes(long, 200)
    assert len(cut.encode("utf-8")) <= 200 and cut and long.startswith(cut)
    assert safe_name.cap_bytes("short") == "short"
