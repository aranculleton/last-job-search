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
        src = re.sub(rf"^{name}\b[^\n]*\n(?:[ \t)\]}}][^\n]*\n)*", "", src, flags=re.M)
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


class YearsAreMeasuredFromThePerson(unittest.TestCase):
    """The bands were fixed at 7/9/11/13 years: right for four years held,
    wrong for everybody else."""

    POSTING = {"title": "Operations Analyst", "company": "Acme",
               "desc": "Requirements: at least 10 years of experience in operations."}

    def _years_note(self, held):
        import fit
        from unittest import mock
        with mock.patch.object(fit, "YEARS_HELD", held):
            res = fit.fit(self.POSTING)
        return [w for w in res["fit_why"] if "years" in w and "stated" in w]

    def test_twenty_years_held_is_not_docked_for_ten(self):
        self.assertEqual([w for w in self._years_note(20) if w.startswith("-")], [])
        self.assertEqual(self._years_note(20), [], "ten years is no stretch at twenty")

    def test_two_years_held_is_docked_for_ten(self):
        self.assertTrue([w for w in self._years_note(2) if w.startswith("-")])


class TheDocumentIsThePersons(unittest.TestCase):

    def _render(self, **doc):
        import importlib
        from unittest import mock
        sys.path.insert(0, os.path.join(ROOT, "templates"))
        rg = importlib.import_module("resume_gen")
        out = os.path.join(tempfile.mkdtemp(prefix="ljs_rg_"), "r.tex")
        a = {"company": "Acme", "role": "Analyst", "abbr": "ACME", "summary": "S.",
             "skills": "K", "jobs": [{"dates": "2020", "title": "T", "employer": "E",
                                      "loc": "L", "bullets": ["b"]}]}
        with mock.patch.dict(rg._DOC, doc), \
             mock.patch.object(rg.docpaths, "resume_tex", lambda abbr: out):
            rg.resume(a)
        return open(out, encoding="utf-8").read(), rg

    def test_a_graduate_can_lead_with_education(self):
        order = ["summary", "education", "experience", "skills", "certifications"]
        tex, rg = self._render(section_order=order)
        heads = rg._H
        self.assertLess(tex.index("\\section{%s}" % heads["education"]),
                        tex.index("\\section{%s}" % heads["experience"]))

    def test_an_order_that_drops_a_section_is_refused(self):
        with self.assertRaises(ValueError):
            self._render(section_order=["summary", "experience"])

    def test_the_letter_speaks_the_persons_language(self):
        import importlib
        from unittest import mock
        rg = importlib.import_module("resume_gen")
        out = os.path.join(tempfile.mkdtemp(prefix="ljs_rg_"), "l.tex")
        a = {"company": "Acme", "role": "Analyst", "abbr": "ACME", "p1": "x", "p2": "y",
             "lead": "z", "cl_bullets": [("a", "b")], "p4": "w", "letter_date": "1 May 2026"}
        with mock.patch.dict(rg._DOC, {"salutation_prefix": "Hej", "page_label": "Sida"}), \
             mock.patch.object(rg.docpaths, "letter_tex", lambda abbr: out):
            rg.letter(a)
        tex = open(out, encoding="utf-8").read()
        self.assertIn("{Hej ", tex)
        self.assertIn("{Sida \\thepage", tex)


class TheWeekIsThePersons(unittest.TestCase):

    def test_a_friday_saturday_weekend(self):
        import datetime
        from unittest import mock
        sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
        import state
        thu = datetime.date(2026, 10, 15)          # a Thursday
        with mock.patch.object(state, "WEEKEND", frozenset({4, 5})):
            self.assertEqual(state.add_business_days(thu, 1), datetime.date(2026, 10, 18))
        self.assertEqual(state.add_business_days(thu, 1), datetime.date(2026, 10, 16))


class ContractWorkCanBeTheTarget(unittest.TestCase):

    def test_opp_contract_none_docks_nothing(self):
        out = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0,'tools'); import opportunity as o; "
             "print(bool(o.CONTRACT.search('locum nurse, 6-month contract')))"],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
            env=dict(os.environ, LJS_PROFILE=self._profile(), PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(out.stdout.strip(), "False", out.stderr)

    def _profile(self):
        d = tempfile.mkdtemp(prefix="ljs_contract_")
        prof = os.path.join(d, "profile")
        shutil.copytree(EXAMPLE, prof)
        with open(os.path.join(prof, "search.py"), "a", encoding="utf-8") as fh:
            fh.write("\nOPP_CONTRACT = None\n")
        self.addCleanup(shutil.rmtree, d, True)
        return prof


NET_PROBE = r'''
import sys
sys.path.insert(0, "tools"); sys.path.insert(0, "tools/network")
import discovery, reply
print("director_of_nursing_in_function", bool(discovery.FUNCTION_TITLE.search("Director of Nursing")))
try:
    discovery.queries_for("Acme", location="Leeds", mode="cold")
    print("titles", "searched")
except discovery.NoTitles as e:
    print("titles", "refused", "TITLE_SETS" in str(e))
except TypeError:
    print("titles", "signature")
print("in_marketing_is_mismatch", bool(reply._hits("Thanks! I'm in marketing these days.", reply.MISMATCH)))
print("different_team_is_mismatch", bool(reply._hits("I'm in a different team entirely now.", reply.MISMATCH)))
'''


class NetworkingAssumesNoFunction(unittest.TestCase):
    """Discovery searched every employer for data scientists, counted only data
    titles as in function, and read "I'm in marketing" as a mismatch, for
    everybody. Those are the person's now."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="ljs_net_")
        prof = os.path.join(cls.tmp, "profile")
        shutil.copytree(EXAMPLE, prof)
        _strip(os.path.join(prof, "networking.py"),
               ["TITLE_SETS", "FUNCTION_TITLE", "HANDS_ON_TITLE", "HIRING_ROLE_NOUNS",
                "HIRING_HEADLINE_NOUNS", "OTHER_FUNCTIONS", "OTHER_FUNCTIONS_MOVED",
                "OWN_FUNCTION_WORDS"])
        env = dict(os.environ, LJS_PROFILE=prof, PYTHONDONTWRITEBYTECODE="1")
        out = subprocess.run([sys.executable, "-c", NET_PROBE], cwd=ROOT, env=env,
                             capture_output=True, text=True, timeout=120)
        cls.err = out.stderr
        cls.got = dict(line.split(" ", 1) for line in out.stdout.splitlines())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_unset_function_never_writes_an_employer_off(self):
        self.assertEqual(self.got.get("director_of_nursing_in_function"), "True", self.err)

    def test_no_titles_means_no_search_and_a_reason(self):
        self.assertEqual(self.got.get("titles"), "refused True", self.err)

    def test_another_function_is_not_assumed(self):
        self.assertEqual(self.got.get("in_marketing_is_mismatch"), "False", self.err)
        self.assertEqual(self.got.get("different_team_is_mismatch"), "True", self.err)

    def test_the_example_keeps_its_own_function(self):
        sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
        import discovery
        self.assertFalse(discovery.FUNCTION_TITLE.search("Director of Nursing"))
        self.assertTrue(discovery.FUNCTION_TITLE.search("Director of Analytics"))
