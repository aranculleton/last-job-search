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


@unittest.skipUnless(shutil.which("lualatex") and shutil.which("kpsewhich"),
                     "no TeX Live here")
class KpathseaFindsIt(unittest.TestCase):
    def test_fontawesome5_resolves_to_the_vendored_copy_or_the_system(self):
        r = subprocess.run(["kpsewhich", "fontawesome5.sty"], env=F.tex_env(),
                           capture_output=True, text=True)
        self.assertTrue(r.stdout.strip(), "fontawesome5.sty not found with tex_env()")


if __name__ == "__main__":
    unittest.main()
