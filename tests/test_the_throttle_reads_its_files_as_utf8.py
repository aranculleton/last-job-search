"""The throttle names UTF-8 on every file it opens.

It opened the contact book and do_not_target.json with the platform's default
encoding, which is cp1252 on Windows: a contact or an employer whose name it
cannot spell stopped the read, and a referral hold read from that book held
nothing back. Python warns on every open that leaves the encoding to the
platform when asked (-X warn_default_encoding); run that way, the throttle's
reads must raise nothing.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


@pytest.mark.skipif(sys.version_info < (3, 10), reason="EncodingWarning arrived in 3.10")
def test_no_read_is_left_to_the_platforms_encoding(tmp_path):
    contacts = tmp_path / "contacts.csv"
    contacts.write_text("contact_id,name,title,company,status,next_action\n"
                        "c1,Shirin Example,Responsable données,Brindle Hart,"
                        "referral_in_progress,attendre\n", encoding="utf-8")
    dnt = tmp_path / "dnt.json"
    dnt.write_text('{"companies": {"Fernhill Freight": {"reason": "bureau de vente",'
                   ' "review_after": "2099-01-01"}}}', encoding="utf-8")
    code = ("import sys; sys.path.insert(0, %r); import throttle; "
            "assert throttle.referral_holds(%r); assert throttle.load_do_not_target(%r); "
            "throttle.expired_do_not_target(%r)"
            % (os.path.join(ROOT, "tools"), str(contacts), str(dnt), str(dnt)))
    r = subprocess.run([sys.executable, "-X", "warn_default_encoding", "-W",
                        "error::EncodingWarning", "-c", code], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-800:]


def test_the_score_lookup_reads_seen_jobs_as_utf8_whatever_the_computer_defaults_to(
        tmp_path, monkeypatch):
    # seen_jobs.json is written UTF-8 (ensure_ascii=False); lookup_score read it with the
    # platform's default, cp1252 on Windows, so an accented employer was misread.
    import builtins
    import json
    import lookup_score
    path = tmp_path / "seen_jobs.json"
    path.write_text(json.dumps({"seen": {"u": {"company": "Société Générale Logistique"}}},
                               ensure_ascii=False), encoding="utf-8")
    real = builtins.open

    def cp1252_default(file, mode="r", *a, **k):
        if "b" not in mode and "encoding" not in k and not a:
            k["encoding"] = "cp1252"
        return real(file, mode, *a, **k)
    monkeypatch.setattr(lookup_score, "SEEN", str(path))
    monkeypatch.setattr(builtins, "open", cp1252_default)
    assert lookup_score.load_seen()["u"]["company"] == "Société Générale Logistique"


def test_the_score_lookup_refuses_a_conflicted_tracker(tmp_path, monkeypatch):
    import csv_store
    import lookup_score
    path = tmp_path / "job_search_tracker.csv"
    path.write_text("date,company,role,status,source\n<<<<<<< ours\n"
                    "2026-09-01,Acme,Analyst,applied,https://x.example/1\n=======\n>>>>>>> theirs\n",
                    encoding="utf-8")
    monkeypatch.setattr(lookup_score, "TRACKER", str(path))
    with pytest.raises(csv_store.Conflicted):
        lookup_score.tracker_rows_for(None, "Acme")
