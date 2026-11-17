"""A role prints the title its draft chose, from the titles the profile allows it.

A person can be allowed two titles for one role (their contract title for client-facing
work, a more technical one their manager agreed for data science postings). There was no
way to apply that per resume: `profile/roles.py` held one `title` a role, the renderer
printed it whatever the draft said, and the drafter had no field for it. A batch was
rendered in two passes with the profile edited between them; `verify_batch.sh` then failed
the heading line of every resume rendered under the other title, and a re-render from the
kept `draft.json` put the profile's one title back (issue 316).

Now a role may list `titles` in roles.py, each with the kind of posting it is for; a draft
picks one in `role_titles`, and the render, the round-trip check and a re-render from the
kept draft all read it there. A title the profile does not allow is refused. A role with one
title prints as it always did. The candidate is the example person; the employer invented.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import draft_audit  # noqa: E402
import draft_pack  # noqa: E402
import render_application as R  # noqa: E402
import verify_pdf as V  # noqa: E402
from test_the_resume_says_what_the_draft_put_on_it import DRAFT, needs_latex  # noqa: E402

ROLE = "Brindle & Hart Logistics"
DEFAULT = "Senior Operations Analyst"
# The second title profile.example/roles.py allows this role, for data postings.
OTHER = "Senior Data Analyst"


def _draft(**kw) -> dict:
    d = copy.deepcopy(DRAFT)
    d.update(kw)
    return d


def _title(d, key=ROLE) -> str:
    return next(j["title"] for j in R.build(d)["jobs"] if j["key"] == key)


def test_a_role_prints_the_profiles_title_unless_its_draft_chose_another():
    assert _title(_draft()) == DEFAULT
    assert _title(_draft(role_titles={ROLE: OTHER})) == OTHER
    # Written in other case or spacing, it prints as the profile writes it.
    assert _title(_draft(role_titles={ROLE: "  senior data   analyst"})) == OTHER
    # Naming the default is the default; the other roles print as they always did.
    assert _title(_draft(role_titles={ROLE: DEFAULT})) == DEFAULT
    assert _title(_draft(role_titles={ROLE: OTHER}), "Oakmere Foods") == "Supply Chain Data Analyst"


@pytest.mark.parametrize("bad", [{ROLE: "Head of Data Science"}, {"Acme Freight": OTHER},
                                 {"Oakmere Foods": OTHER}, {ROLE: 3}, [OTHER]])
def test_a_title_the_profile_does_not_allow_that_role_is_refused(bad):
    with pytest.raises(ValueError, match="role_titles"):
        R.build(_draft(role_titles=bad))
    found = draft_audit.malformed(_draft(role_titles=bad))
    assert [f for f in found if f["field"] == "role_titles"], found


def test_the_round_trip_check_reads_the_title_from_the_draft():
    groups = V.roundtrip_fields(_draft(role_titles={ROLE: OTHER}))
    heading = dict(dict(groups)[f"{ROLE}, its heading line"])
    assert heading["title"] == OTHER


def test_the_drafter_is_told_which_titles_a_role_may_print_and_for_which_postings():
    pack = draft_pack.static_pack()
    assert "- role_titles:" in pack
    assert f'{ROLE}: "{DEFAULT}" by default; "{OTHER}" for data and analytics postings' in pack
    # A profile whose roles have one title each is told nothing new.
    assert draft_pack.title_lines([dict(employer="Acme Freight", title="Analyst")]) == []


@needs_latex
def test_a_kept_draft_renders_and_verifies_with_its_own_title(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    import docpaths
    import fit_to_page as F
    (tmp_path / "cv").mkdir()
    kept = tmp_path / "draft.json"
    kept.write_text(json.dumps([_draft(role_titles={ROLE: OTHER})]), encoding="utf-8")
    # Rendered again from the kept draft, as a renderer fix reaching an unsent one is.
    apps, _ = F.load(str(kept))
    a = apps[0]
    R.resume(R.build(a))
    kept.write_text(json.dumps([a]), encoding="utf-8")
    tex, pdf = docpaths.resume_tex(a["abbr"]), docpaths.resume_pdf(a["abbr"])
    with open(tex, encoding="utf-8") as fh:
        assert "{" + OTHER + "}" in fh.read()
    F._compile("lualatex", os.path.basename(tex), os.path.dirname(tex), pdf)
    got = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "verify_pdf.py"), pdf,
                          "--roundtrip", str(kept), "--abbr", a["abbr"]],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert got.returncode == 0, got.stdout + got.stderr
