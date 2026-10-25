"""The scoring baseline reads whatever corpus the person has.

tools/score_eval.py pins a person's screened-postings corpus (profile/tests/fixtures/
screened_postings): a baseline of what the scorer said, and on top of it what must hold
whatever the weights become. Those expectations named four files of one person's corpus,
so any other person's corpus failed on four files it never had, right after `--update`
re-recorded it, and ci_local.sh failed with it. Each fixture's name says what must happen
to it (`cut__*` or `pass__*`), and that is what is checked. Every posting is invented.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BODY = (" You will own demand forecasting and inventory analytics for the North West network, "
        "working with operations and commercial teams in SQL and Python.") * 4
PASS = "Acme Freight | Supply Chain Analyst\nManchester, England, United Kingdom\n" + BODY
CUT = ("Acme Freight | Supply Chain Analyst\nManchester, England, United Kingdom\n"
       "Fluency in Welsh is essential for this role." + BODY)


def _corpus(tmp_path, files):
    profile = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), profile)
    corpus = profile / "tests" / "fixtures" / "screened_postings"
    corpus.mkdir(parents=True)
    for name, text in files.items():
        (corpus / name).write_text(text, encoding="utf-8")
    return profile


def _eval(profile, *args):
    return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "score_eval.py"), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, "LJS_PROFILE": str(profile)})


def test_a_corpus_of_its_own_is_clean_after_it_is_recorded(tmp_path):
    profile = _corpus(tmp_path, {"pass__acme_supply.txt": PASS, "cut__acme_welsh.txt": CUT})
    assert _eval(profile, "--update").returncode == 0
    r = _eval(profile)
    assert r.returncode == 0, r.stdout
    assert "MISSING" not in r.stdout


def test_a_fixture_that_no_longer_does_what_its_name_says_is_reported(tmp_path):
    profile = _corpus(tmp_path, {"cut__acme_supply.txt": PASS, "pass__acme_welsh.txt": CUT})
    assert _eval(profile, "--update").returncode == 0
    r = _eval(profile)
    assert r.returncode == 1
    assert "BROKE  cut__acme_supply: screened is False, expected True" in r.stdout
    assert "BROKE  pass__acme_welsh: screened is True, expected False" in r.stdout


def test_the_old_name_still_lists_the_hard_cuts(tmp_path):
    # score_eval.EXPECTATIONS is a public name, and a person's own tests (profile/tests) may
    # use one: a person's tests checked that every expectation in it has a reason and that
    # each of its postings is still cut, and both failed when the name went (2026-10-25). It
    # is back, read from the corpus there is: its `cut__` postings, all it ever listed.
    profile = _corpus(tmp_path, {"pass__acme_supply.txt": PASS, "cut__acme_welsh.txt": CUT})
    code = ("import json, score_eval as E\n"
            "rows = {r['stem']: r for r in map(E.evaluate, E.cases())}\n"
            "print(json.dumps({s: dict(w, now=rows[s]['screened'])\n"
            "                  for s, w in E.EXPECTATIONS.items()}))\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       encoding="utf-8", env={**os.environ, "LJS_PROFILE": str(profile),
                                              "PYTHONPATH": os.path.join(ROOT, "tools")})
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert list(got) == ["cut__acme_welsh"]
    assert got["cut__acme_welsh"]["why"] and got["cut__acme_welsh"]["now"] is True


def test_the_old_name_is_empty_with_no_corpus(tmp_path):
    profile = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), profile)
    r = subprocess.run([sys.executable, "-c", "import score_eval as E; print(len(E.EXPECTATIONS))"],
                       capture_output=True, text=True, encoding="utf-8",
                       env={**os.environ, "LJS_PROFILE": str(profile),
                            "PYTHONPATH": os.path.join(ROOT, "tools")})
    assert (r.returncode, r.stdout.strip()) == (0, "0"), r.stderr
