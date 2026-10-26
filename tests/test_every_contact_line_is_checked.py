"""Every contact line the resume prints is checked on the page, and a profile with no phone
can be verified.

The batch checked the email and the phone and nothing else, so a LinkedIn address whose
"%" commented out the LinkedIn line and the right-to-work line after it lost both without a
CONTACT flag. And `docpaths.values()` read the phone with no default while the renderer
treats it as optional: a person with no phone on their resume got "verify_batch: cannot read
the profile" on every batch.

The application is invented; the candidate is the example person.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def _profile(tmp_path, **identity):
    dst = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), dst)
    p = dst / "person.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    for k, v in identity.items():
        if v is None:
            data["identity"].pop(k, None)
        else:
            data["identity"][k] = v
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return str(dst)


def _batch(tmp_path, monkeypatch, profile, drop=()):
    """verify_batch over one invented application whose page is every line it needs, less
    the lines in `drop`; every other tool answers clean."""
    monkeypatch.setenv("LJS_PROFILE", profile)
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    import docpaths
    import person
    import verify_batch as B
    person.reset()
    for p in (docpaths.resume_pdf("Acme"), docpaths.letter_pdf("Acme")):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(b"%PDF-1.4\n")
    v = docpaths.values()
    contact = [c for c in json.loads(v["CONTACT_LINES"]) if c not in drop]
    page = "\n".join(contact + [v["H_EXPERIENCE"]]
                     + [line for n in json.loads(v["ROLE_NAMES"])
                        for line in (n, "• Built the weekly forecast", "• Ran the reporting")]
                     + [v["H_EDUCATION"]])
    monkeypatch.setattr(B.pdftext, "text", lambda pdf: page)
    monkeypatch.setattr(B.pdftext, "pages", lambda pdf: 1)
    monkeypatch.setattr(B.pdftext, "reader", lambda: "pypdf")
    monkeypatch.setattr(B, "section_layout", lambda tex, want: "")
    monkeypatch.setattr(B, "resume_bullets", lambda *a: [])
    monkeypatch.setattr(B, "_run3", lambda args: (
        0, "letters clean\n" if args[0].endswith("audit_letters.py") else "", ""))
    drafts = tmp_path / "drafts.json"
    drafts.write_text(json.dumps([{"abbr": "Acme"}]), encoding="utf-8")
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = B.main([str(drafts)])
    person.reset()
    return code, said.getvalue(), v


def test_the_contact_lines_are_every_line_the_resume_prints(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_PROFILE", os.path.join(ROOT, "profile.example"))
    import docpaths
    import person
    person.reset()
    assert docpaths.contact_lines() == [
        "Manchester, UK", "+44 7700 900123", "morgan.ellis@example.com",
        "linkedin.com/in/morgan-ellis-example", "Right to work in the UK"]


def test_a_page_with_every_contact_line_passes(tmp_path, monkeypatch):
    code, said, _v = _batch(tmp_path, monkeypatch, os.path.join(ROOT, "profile.example"))
    assert "CONTACT" not in said, said
    assert code == 0, said


def test_a_lost_linkedin_or_right_to_work_line_is_a_contact_finding(tmp_path, monkeypatch):
    for gone in ("linkedin.com/in/morgan-ellis-example", "Right to work in the UK"):
        code, said, _v = _batch(tmp_path, monkeypatch, os.path.join(ROOT, "profile.example"),
                                drop=(gone,))
        assert " CONTACT" in said and code == 1, said
        assert "contact lines not on the page: " + gone in said


def test_a_profile_with_no_phone_is_verified(tmp_path, monkeypatch):
    code, said, v = _batch(tmp_path, monkeypatch, _profile(tmp_path, phone=None))
    assert "cannot read the profile" not in said
    assert v["PHONE"] == "" and "+44" not in v["CONTACT_LINES"]
    assert code == 0 and "CONTACT" not in said, said
