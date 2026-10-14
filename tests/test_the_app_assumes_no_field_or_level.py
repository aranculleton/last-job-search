"""The app assumes nobody's field and nobody's level.

The first person set up outside data analysis found three things the app had
decided for them: their resume's Skills block printed under a data analyst's
headings ("Languages and modelling"), every "junior" and "graduate" title was
docked 25 points as below their level when those were the roles they wanted,
and their bullets' themes could not match any posting because the cue list
knew only a data analyst's words.
Each is now the profile's, and a profile that does not say gets no assumption.
And the leak scan made them rename a "Projects" entry on their resume, because a
placeholder where an employer goes became a denylist entry that matched the
app's own headings.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "profile.example")
sys.path.insert(0, os.path.join(ROOT, "tools"))

import allocate  # noqa: E402
import build_app  # noqa: E402
import skills_block  # noqa: E402

PROBE = r'''
import sys
sys.path.insert(0, "tools")
import allocate, fit, opportunity, skills_block
print("fit_docks_junior", bool(fit.JUNIOR.search("junior designer")))
print("opp_docks_junior", bool(opportunity.JUNIOR.search("graduate designer")))
print("opp_docks_head", bool(opportunity.SENIOR_UP.search("head of design")))
print("own_theme_cued", "typography" in allocate.CUE_RE)
try:
    skills_block.lines("SQL")
    print("skills", "rendered")
except skills_block.NoHeadings as e:
    print("skills", "refused", "LABELS" in str(e))
'''


def _strip(path, names):
    """Remove each top-level assignment of these names from a profile module."""
    src = open(path, encoding="utf-8").read()
    for name in names:
        src = re.sub(rf"^{name}\b[^\n]*\n(?:[ \t)\]][^\n]*\n)*", "", src, flags=re.M)
    open(path, "w", encoding="utf-8").write(src)


class AProfileThatDoesNotSayGetsNoAssumption(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="ljs_noassume_")
        prof = os.path.join(cls.tmp, "profile")
        shutil.copytree(EXAMPLE, prof)
        _strip(os.path.join(prof, "search.py"),
               ["FIT_BELOW_LEVEL", "OPP_BELOW_LEVEL", "OPP_ABOVE_LEVEL"])
        _strip(os.path.join(prof, "skills.py"), ["LABELS", "MERGE", "MAX_PER_LINE"])
        with open(os.path.join(prof, "bullets.py"), "a", encoding="utf-8") as fh:
            fh.write('\nTHEME_CUES = {"typography": ["typography", "type design"]}\n')
        env = dict(os.environ, LJS_PROFILE=prof, PYTHONDONTWRITEBYTECODE="1")
        out = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, env=env,
                             capture_output=True, text=True, timeout=120)
        cls.err = out.stderr
        cls.got = dict(line.split(" ", 1) for line in out.stdout.splitlines())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_no_title_is_docked_for_its_level(self):
        self.assertEqual(self.got.get("fit_docks_junior"), "False", self.err)
        self.assertEqual(self.got.get("opp_docks_junior"), "False", self.err)
        self.assertEqual(self.got.get("opp_docks_head"), "False", self.err)

    def test_no_skills_headings_means_no_skills_block_and_a_reason(self):
        self.assertEqual(self.got.get("skills"), "refused True", self.err)

    def test_a_profile_adds_its_own_themes(self):
        self.assertEqual(self.got.get("own_theme_cued"), "True", self.err)


class TheExamplePersonSaysAll_of_It(unittest.TestCase):

    def test_the_example_names_its_own_headings(self):
        self.assertTrue(skills_block.LABELS)
        self.assertTrue(skills_block.lines("SQL, Python"))

    def test_every_example_theme_has_a_cue(self):
        self.assertEqual(allocate.uncued_themes(), [])


class APlaceholderIsNotAPerson(unittest.TestCase):

    def test_placeholders_are_skipped(self):
        for name in ("Projects", "Selected Projects", "Freelance", "Self-employed",
                     "Career break", "Projects, Bristol", "Personal Projects (2024)"):
            with self.subTest(name=name):
                self.assertTrue(build_app._generic_employer(name))

    def test_a_real_employer_with_a_generic_word_in_it_is_kept(self):
        for name in ("Acme Projects", "Independent Bookshop", "Portfolio Partners",
                     "Oakmere Foods"):
            with self.subTest(name=name):
                self.assertFalse(build_app._generic_employer(name))


if __name__ == "__main__":
    unittest.main()
