"""The scoring baseline reads whatever corpus the person has.

tools/score_eval.py pins a person's screened-postings corpus (profile/tests/fixtures/
screened_postings): a baseline of what the scorer said, and on top of it what must hold
whatever the weights become. Those expectations named four files of one person's corpus,
so any other person's corpus failed on four files it never had, right after `--update`
re-recorded it, and ci_local.sh failed with it. Each fixture's name says what must happen
to it (`cut__*` or `pass__*`), and that is what is checked. Every posting is invented.
"""
from __future__ import annotations

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
