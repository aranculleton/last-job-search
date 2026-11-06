"""Two titles at one employer, and a job with no achievement on file, print as they are.

A promotion is two roles at one employer, and an early job is often listed by its title and
dates alone. The renderer, the allocator and the check keyed everything by employer: the
older title at the same employer overwrote the newer one, so the current achievements
printed under a title that ended years ago, with its dates, and the allocator gave the
current role the older role's floor and cap; a role with no bullets vanished. The check then
failed with "CHRONO" and nothing was kept, so the promised resume never came. Each role is
now its own entry: the most recent at an employer takes that employer's bullets, as every
profile was written, an older one takes its own (`lib=` in roles.py names them), and a role
with none prints as its title, employer and dates. A profile already written either way
renders right with no change; one that merged or dropped a job to pass the old check is
told so by the roles-per-employer upgrade.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

ROLES = '''
ROLES = [
    dict(employer="Brindle & Hart Logistics", title="Senior Operations Analyst",
         dates="Mar 2023 - Present", loc="Manchester, UK", short="BH",
         tenure_months=31, floor=2, cap=4),
    dict(employer="Brindle & Hart Logistics", title="Operations Analyst",
         dates="Jun 2022 - Feb 2023", loc="Manchester, UK", short="BO",
         tenure_months=9, floor=1, cap=2%(lib)s),
    dict(employer="Oakmere Foods", title="Supply Chain Data Analyst",
         dates="Sep 2020 - May 2022", loc="Leeds, UK", short="OF",
         tenure_months=20, floor=2, cap=4, known_as="Oakmere"),
    dict(employer="Saltmarsh Analytics", title="Graduate Analyst",
         dates="Sep 2019 - Aug 2020", loc="Manchester, UK", short="SA", ns=4,
         tenure_months=12, floor=1, cap=2, always_show="SALT_FORECAST", skills_context=False),
    dict(employer="Fernhill Freight", title="Trainee Analyst",
         dates="Jun 2019 - Aug 2019", loc="Leeds, UK", short="FF",
         tenure_months=3, floor=0, cap=1),
]
'''


def _profile(tmp_path, lib=False):
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d)
    text = (d / "roles.py").read_text(encoding="utf-8")
    start, end = text.index("ROLES = ["), text.index("\nEDUCATION")
    (d / "roles.py").write_text(text[:start] + ROLES.strip() % {
        "lib": ', lib="Brindle & Hart Logistics (Operations Analyst)"' if lib else ""}
        + "\n" + text[end:], encoding="utf-8")
    if lib:
        b = (d / "bullets.py").read_text(encoding="utf-8")
        b = b.replace('LIB = {\n', 'LIB = {\n "Brindle & Hart Logistics (Operations Analyst)": {\n'
                      '  "BO_SLOTTING": (\n    {"modelling", "automation"}, 8,\n'
                      '    r"Rebuilt the pick-face slotting rules for the Manchester depot, '
                      'cutting picker travel by 12\\%"),\n },\n', 1)
        (d / "bullets.py").write_text(b, encoding="utf-8")
    state = tmp_path / "state"
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), state)
    return dict(os.environ, LJS_PROFILE=str(d), LJS_STATE=str(state))


def _run(env, code):
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


BUILD = (
    "import json, sys; sys.path[:0] = ['tools', 'templates']\n"
    "import allocate, render_application as R\n"
    "a = dict(company='Kestrel Mutual', role='Operations Analyst', abbr='KestrelMutual',\n"
    "         summary='Operations analyst who builds weekly demand forecasts that move stock.',\n"
    "         tools='SQL, Python', posting='Forecast weekly demand with SQL and Python; slotting.',\n"
    "         p1='x', p2='y', lead='z', cl_bullets=[], p4='w')\n"
    "d = R.build(a)\n"
    "print(json.dumps({'jobs': [[j['employer'], j['title'], j['dates'], len(j['bullets'])]\n"
    "                            for j in d['jobs']],\n"
    "                  'cap': allocate.CAP['Brindle & Hart Logistics'],\n"
    "                  'floor': allocate.FLOOR['Brindle & Hart Logistics']}))\n")


def test_each_role_prints_under_its_own_title_and_dates(tmp_path):
    got = _run(_profile(tmp_path), BUILD)
    titles = [(e, t, d) for e, t, d, _n in got["jobs"]]
    assert titles == [
        ("Brindle & Hart Logistics", "Senior Operations Analyst", "Mar 2023 - Present"),
        ("Brindle & Hart Logistics", "Operations Analyst", "Jun 2022 - Feb 2023"),
        ("Oakmere Foods", "Supply Chain Data Analyst", "Sep 2020 - May 2022"),
        ("Saltmarsh Analytics", "Graduate Analyst", "Sep 2019 - Aug 2020"),
        ("Fernhill Freight", "Trainee Analyst", "Jun 2019 - Aug 2019")]
    counts = [n for *_x, n in got["jobs"]]
    assert counts[0] >= 2 and counts[1] == 0 and counts[4] == 0    # no bullets on file: a title line
    # The current role keeps its own floor and cap, never the older role's.
    assert (got["floor"], got["cap"]) == (2, 4)


def test_an_older_title_with_bullets_of_its_own_takes_them(tmp_path):
    got = _run(_profile(tmp_path, lib=True), BUILD)
    older = got["jobs"][1]
    assert older[:3] == ["Brindle & Hart Logistics", "Operations Analyst", "Jun 2022 - Feb 2023"]
    assert older[3] == 1


@pytest.mark.skipif(not shutil.which("pdflatex"), reason="no LaTeX on this machine")
def test_the_general_resume_renders_and_passes_its_check(tmp_path):
    pytest.importorskip("pypdf")
    env = _profile(tmp_path)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "stage_picks.py"), "general",
                        str(tmp_path / "general"), "--no-keep"], cwd=ROOT, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = r.stdout + r.stderr
    assert "CHRONO" not in out and "BATCH: ALL PASS" in out, out[-3000:]
    import pdftext
    pdf = os.path.join(str(tmp_path / "state"), "cv", "Morgan_Ellis_General_CV.pdf")
    text = re.sub(r"\s+", " ", pdftext.text(pdf))
    assert "Senior Operations Analyst" in text and "Mar 2023 - Present" in text
    assert "Jun 2022 - Feb 2023" in text and "Fernhill Freight" in text


def test_a_job_merged_or_dropped_from_the_roles_is_an_upgrade(tmp_path):
    env = _profile(tmp_path)
    # A chat that made the old check pass by deleting the trainee job from roles.py.
    path = tmp_path / "profile" / "roles.py"
    text = path.read_text(encoding="utf-8")
    start = text.index('    dict(employer="Fernhill Freight"')
    path.write_text(text[:start] + text[text.index("]\n", start):], encoding="utf-8")
    prof = tmp_path / "profile" / "01-candidate-profile.md"
    p = prof.read_text(encoding="utf-8")
    at = p.index("## Education")
    prof.write_text(p[:at] + "### Trainee Analyst - Fernhill Freight (Jun 2019 - Aug 2019), "
                    "Leeds\n\n" + p[at:], encoding="utf-8")
    got = _run(env, "import json, sys; sys.path.insert(0, 'tools'); import profile_upgrades as U\n"
                    "print(json.dumps(U.by_id('roles-per-employer').pending()))")
    assert "Trainee Analyst at Fernhill Freight" in got
