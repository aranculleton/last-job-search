"""The icon packages moderncv needs are vendored, so texlive-fonts-extra is not.

texlive-fonts-extra is 1.7 GB and every fresh container downloaded it for the
1.5 MB the resume used: fontawesome5 and academicons. Those now live in
texmf/ and every compile path points TEXMFHOME at it. These tests pin both
halves, so nobody deletes the tree thinking it is clutter and nobody adds a
compile that forgets the variable.
"""
import os
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fit_to_page as F  # noqa: E402

TEXMF = os.path.join(ROOT, "texmf")


class VendoredTree(unittest.TestCase):
    def test_the_files_moderncv_loads_are_there(self):
        for rel in ("tex/latex/fontawesome5/fontawesome5.sty",
                    "tex/latex/fontawesome5/fontawesome5-utex-helper.sty",
                    "tex/latex/fontawesome5/fontawesome5.lua",
                    "tex/latex/academicons/academicons.sty",
                    "fonts/opentype/public/fontawesome5/FontAwesome5Free-Solid-900.otf",
                    "fonts/opentype/public/fontawesome5/FontAwesome5Free-Regular-400.otf",
                    "fonts/opentype/public/fontawesome5/FontAwesome5Brands-Regular-400.otf",
                    "fonts/truetype/public/academicons/academicons.ttf",
                    "README.md"):
            self.assertTrue(os.path.isfile(os.path.join(TEXMF, rel)), rel)

    def test_none_of_it_is_gitignored(self):
        files = [os.path.join(dp, f) for dp, _, fs in os.walk(TEXMF) for f in fs]
        r = subprocess.run(["git", "check-ignore", *files], cwd=ROOT,
                           capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "", "ignored files would vanish on clone")


class TexEnv(unittest.TestCase):
    def test_points_texmfhome_at_the_repo(self):
        self.assertEqual(F.tex_env({})["TEXMFHOME"], TEXMF)

    def test_keeps_a_texmfhome_already_set(self):
        env = F.tex_env({"TEXMFHOME": "/elsewhere"})
        self.assertEqual(env["TEXMFHOME"], "{%s,/elsewhere}" % TEXMF)

    def test_does_not_double_up(self):
        self.assertEqual(F.tex_env({"TEXMFHOME": TEXMF})["TEXMFHOME"], TEXMF)

    def test_compile_passes_it(self):
        seen = {}

        def fake(cmd, cwd=None, capture_output=False, env=None, **kw):
            seen["env"] = env
            raise RuntimeError("stop")
        real = F.subprocess.run
        F.subprocess.run = fake
        try:
            with self.assertRaises(RuntimeError):
                F._compile("lualatex", "x.tex", ROOT, os.path.join(ROOT, "nope.pdf"))
        finally:
            F.subprocess.run = real
        self.assertEqual(seen["env"]["TEXMFHOME"].split(",")[0].strip("{"), TEXMF)


class NothingInTheHomeDirectory(unittest.TestCase):
    """Two local chats in two worktrees, one ~/texmf link: setup_env.sh re-pointed it at
    whichever copy ran last ("~/texmf pointed at another copy of the app; re-pointed at
    this one"), so each chat's run took it from the other. The repo's own texmf/ is found
    through TEXMFHOME, set by each compile, and the home directory is never touched."""

    def _setup_env(self, home):
        # Stand-ins for every tool the script would otherwise install, and a pip that
        # installs nothing, so the run is offline and changes nothing outside `home`.
        stubs = os.path.join(home, "stubs")
        os.makedirs(stubs, exist_ok=True)
        for tool in ("lualatex", "xelatex", "pdftotext", "bun", "pip3"):
            path = os.path.join(stubs, tool)
            with open(path, "w") as fh:
                fh.write("#!/bin/sh\nexit 0\n")
            os.chmod(path, 0o755)
        env = dict(os.environ, HOME=home, PATH=stubs + os.pathsep + os.environ.get("PATH", ""))
        env.pop("BUN_INSTALL", None)
        return subprocess.run(["bash", os.path.join(ROOT, "tools", "setup_env.sh")], cwd=ROOT,
                              env=env, capture_output=True, text=True, timeout=120)

    @unittest.skipUnless(shutil.which("bash"), "no bash here")
    def test_setup_env_leaves_a_link_to_another_copy_alone_and_says_what_is_used(self):
        import tempfile
        with tempfile.TemporaryDirectory() as home:
            other = os.path.join(home, "other-worktree", "texmf")
            os.makedirs(other)
            with open(os.path.join(other, "README.md"), "w") as fh:
                fh.write("# texmf: the two icon packages moderncv loads\n")
            os.symlink(other, os.path.join(home, "texmf"))
            r = self._setup_env(home)
            self.assertEqual(os.readlink(os.path.join(home, "texmf")), other, r.stdout)
            self.assertNotIn("re-pointed", r.stdout)
            self.assertIn("TEXMFHOME", r.stdout)

    @unittest.skipUnless(shutil.which("bash"), "no bash here")
    def test_setup_env_creates_nothing_and_keeps_a_dangling_link(self):
        import tempfile
        with tempfile.TemporaryDirectory() as home:
            r = self._setup_env(home)
            self.assertFalse(os.path.lexists(os.path.join(home, "texmf")), r.stdout)
            os.symlink(os.path.join(home, "moved-away"), os.path.join(home, "texmf"))
            r = self._setup_env(home)
            self.assertEqual(os.readlink(os.path.join(home, "texmf")),
                             os.path.join(home, "moved-away"), r.stdout)

    def test_no_app_script_links_texmf_into_the_home_directory(self):
        import re
        for name in os.listdir(os.path.join(ROOT, "tools")):
            if name.endswith((".sh", ".py")):
                with open(os.path.join(ROOT, "tools", name), encoding="utf-8") as fh:
                    text = fh.read()
                self.assertIsNone(re.search(r"\bln\b[^\n]*HOME[^\n]*texmf", text), name)

    def test_every_compile_in_ci_sets_texmfhome_itself(self):
        # Read as text, not with yaml: the Python floor leg installs pytest and nothing
        # else, and this check is worth running there too. A step starts at its `- `.
        import re
        with open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8") as fh:
            steps = re.split(r"\n(?=\s*- (?:name|uses|run):)", fh.read())
        compiles = [s for s in steps if re.search(r"\b(?:lualatex|xelatex) -", s)]
        self.assertGreaterEqual(len(compiles), 2)
        for step in compiles:
            self.assertIn('export TEXMFHOME="$PWD/texmf"', step, step.strip().splitlines()[0])
        with open(os.path.join(ROOT, "tools", "ci_local.sh"), encoding="utf-8") as fh:
            local = fh.read()
        first = min(local.find("lualatex -"), local.find("xelatex -"))
        self.assertLess(-1, local.find('export TEXMFHOME="$PWD/texmf"'))
        self.assertLess(local.find('export TEXMFHOME="$PWD/texmf"'), first)

    def test_no_document_says_the_setup_links_texmf(self):
        import re
        said = re.compile(r"link\w*\s+`?~/texmf`?\s+(?:to|here|at)", re.I)
        for rel in ("SETUP.md", "RUNBOOK.md", "START_HERE.md", "CLAUDE.md", "README.md",
                    "texmf/README.md"):
            path = os.path.join(ROOT, rel)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    self.assertIsNone(said.search(fh.read()), rel)


@unittest.skipUnless(shutil.which("lualatex") and shutil.which("kpsewhich"),
                     "no TeX Live here")
class KpathseaFindsIt(unittest.TestCase):
    def test_fontawesome5_resolves_to_the_vendored_copy_or_the_system(self):
        r = subprocess.run(["kpsewhich", "fontawesome5.sty"], env=F.tex_env(),
                           capture_output=True, text=True)
        self.assertTrue(r.stdout.strip(), "fontawesome5.sty not found with tex_env()")


if __name__ == "__main__":
    unittest.main()
