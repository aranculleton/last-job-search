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
                        "error::EncodingWarning", "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
