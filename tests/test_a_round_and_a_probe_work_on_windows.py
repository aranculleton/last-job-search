"""A round named the Windows way, a mistyped round, and the job-site probe on Windows.

- `--out rounds\\r1\\`: the trailing backslash left the round with no name, and its
  shortlist was saved as documents/rounds/.json.
- argparse exits 2 on a mistyped option, which a round keeps for "the yield target was
  missed": a typo read as a thin market.
- Windows' own curl.exe cannot open /dev/null, so every job site was reported unreachable.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import env_check  # noqa: E402
import run_round  # noqa: E402


def test_the_round_folder_is_read_whichever_way_its_separators_lean():
    assert os.path.basename(os.path.abspath(run_round.round_dir("rounds\\r1\\"))) == "r1"
    assert run_round.round_dir("rounds/r1/") == os.path.normpath("rounds/r1")
    assert run_round.round_dir("rounds/r1") == os.path.normpath("rounds/r1")


def test_a_mistyped_option_is_a_broken_stage_not_a_thin_market():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "run_round.py"), "--out",
                        "x", "--pagez", "3"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ, LJS_PROFILE="profile.example"), timeout=120)
    assert r.returncode == 1 and "unrecognized arguments: --pagez" in r.stderr


def test_the_probe_writes_to_this_computers_null_device(monkeypatch):
    seen = {}

    class Done:
        returncode, stdout, stderr = 0, "000 200", ""

    def fake_run(argv, **kw):
        seen["argv"], seen["kw"] = argv, kw
        return Done()
    monkeypatch.setattr(env_check.shutil, "which", lambda name: "/usr/bin/curl")
    monkeypatch.setattr(env_check.subprocess, "run", fake_run)
    assert env_check.probe("https://example.com/")[0] == "reachable"
    assert seen["argv"][seen["argv"].index("-o") + 1] == os.devnull
    assert seen["kw"].get("encoding") == "utf-8"
