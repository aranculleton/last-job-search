#!/usr/bin/env python3
"""Proof that the app works on a computer with nothing extra installed first.

The platforms workflow (.github/workflows/platforms.yml) runs this on Linux, a Mac and
Windows, after taking away what a person would not have (Homebrew and MacTeX on the
Mac, winget on Windows, sudo and TeX on Linux):

    python3 tools/platform_check.py install      env_check --fix, then each tool runs
    python3 tools/platform_check.py documents    a resume and letter in black and two
                                                 colours, fitted and checked
    python3 tools/platform_check.py round        an offline round matches its golden
                                                 summary (tests/round_fixture.py)
    python3 tools/platform_check.py interview    an interview pack from the example person
    python3 tools/platform_check.py networking   a first note drafted and checked, the
                                                 surfacing check, a message logged, a
                                                 LinkedIn download with Windows-style names
                                                 and accents taken, the due list
    python3 tools/platform_check.py computer     a computer chat arriving in a copy that is
                                                 already set up, and its ordinary day
    python3 tools/platform_check.py all          install, documents, round, interview,
                                                 networking

Every step prints PASS or FAIL with what it saw and how long it took, keeps going after
a failure, and the run exits 1 when any failed. Nothing reaches the network but the
installs; the people, employers and postings are the example person's, all invented.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path[:0] = [TOOLS, os.path.join(ROOT, "tests"), os.path.join(ROOT, "templates")]
PY = sys.executable
EXAMPLE = os.path.join(ROOT, "profile.example")
RESULTS: list[tuple[str, bool, str]] = []


def run(cmd, cwd=ROOT, env=None, timeout=1800):
    """(exit code, what it printed)."""
    began = time.monotonic()
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
    except FileNotFoundError as exc:
        return 127, f"{exc}", 0.0
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout} s", time.monotonic() - began
    out = (p.stdout or b"") + (p.stderr or b"")
    # Decoded the way a reader would, whatever code page the child wrote in.
    return p.returncode, out.decode("utf-8", "replace"), time.monotonic() - began


def check(step: str, ok: bool, detail: str = "", took: float | None = None) -> bool:
    RESULTS.append((step, ok, detail))
    t = f" ({took:.1f} s)" if took is not None else ""
    print(f"{'PASS' if ok else 'FAIL'} {step}{t}" + (f"\n     {detail[-1500:]}" if detail and
                                                     not ok else f": {detail[:200]}" if detail
                                                     else ""), flush=True)
    return ok


def env_for(**extra) -> dict:
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_REMOTE", None)          # a person's own computer
    env.update(PYTHONDONTWRITEBYTECODE="1", **extra)
    return env


# ------------------------------------------------------------------ the steps

def step_install() -> None:
    code, out, took = run([PY, os.path.join(TOOLS, "env_check.py"), "--fix"], env=env_for(),
                          timeout=3600)
    check("install: env_check --fix", code == 0, out.strip(), took)
    print(out.strip(), flush=True)
    import local_path
    local_path.extend()
    for tool in ("lualatex", "xelatex"):
        check(f"install: {tool} found", bool(shutil.which(tool)), shutil.which(tool) or "")
    import pdftext
    check("install: the PDF reader is pypdf", pdftext.reader() == "pypdf", pdftext.reader())
    import portals
    portals.runtime.cache_clear()
    try:
        check("install: node or bun runs the portals", True, " ".join(portals.runtime()))
    except portals.NoRuntime as exc:
        check("install: node or bun runs the portals", False, str(exc))
    gh = shutil.which("gh")
    code, out, _ = run([gh, "--version"]) if gh else (127, "gh not found", 0)
    check("install: gh runs", code == 0, out.splitlines()[0] if out else "")
    print(f"info: Poppler's pdftotext here: {shutil.which('pdftotext') or 'no (not needed)'}")


def _draft() -> dict:
    from test_the_resume_says_what_the_draft_put_on_it import DRAFT
    return json.loads(json.dumps(DRAFT))


def step_documents() -> None:
    env = env_for(LJS_PROFILE=EXAMPLE)
    work = tempfile.mkdtemp(prefix="ljs_docs_")
    for style in ("black", "navy", "burgundy"):
        d = _draft()
        d["style"] = style
        drafts = os.path.join(work, f"drafts_{style}.json")
        with open(drafts, "w", encoding="utf-8") as fh:
            json.dump([d], fh, ensure_ascii=False)
        code, out, took = run([PY, os.path.join(TOOLS, "fit_to_page.py"), drafts], env=env)
        check(f"documents: {style} fitted to one page", code == 0 and "resume 1p" in out,
              out.strip(), took)
        code, out, took = run([PY, os.path.join(TOOLS, "verify_batch.py"), drafts], env=env)
        check(f"documents: {style} checked", code == 0 and "BATCH: ALL PASS" in out,
              out.strip().splitlines()[-1] if code == 0 else out.strip(), took)
    shutil.rmtree(work, ignore_errors=True)


def step_round() -> None:
    os.environ.update(LJS_RESCREEN="off", LJS_PROFILE=EXAMPLE)
    import person
    person.reset()
    import round_fixture as F
    work = tempfile.mkdtemp(prefix="ljs_round_")
    began = time.monotonic()
    out = os.path.join(work, "scrape")
    code, said = F.scrape(out)
    with open(F.SCRAPE_GOLDEN, encoding="utf-8") as fh:
        want = json.load(fh)
    with open(os.path.join(out, "kept.json"), encoding="utf-8") as fh:
        kept = F.by_address(json.load(fh))
    with open(F.KEPT, encoding="utf-8") as fh:
        golden_kept = F.by_address(json.load(fh))
    same = (code == want["exit"] and kept == golden_kept
            and F.scrape_summary(out) == {k: v for k, v in want.items() if k != "exit"})
    check("round: the scrape keeps and drops what it always did", same,
          "" if same else said[-1500:], time.monotonic() - began)
    began = time.monotonic()
    r = F.free_stages(F.KEPT, os.path.join(work, "r1"), work)
    with open(F.GOLDEN, encoding="utf-8") as fh:
        golden = json.load(fh)
    ok = r.returncode in (0, 2) and F.summary(os.path.join(work, "r1")) == golden
    check("round: the free stages rank and shortlist what they always did", ok,
          "" if ok else (r.stdout[-1000:] + r.stderr[-1000:]), time.monotonic() - began)
    shutil.rmtree(work, ignore_errors=True)


def _state() -> str:
    d = tempfile.mkdtemp(prefix="ljs_state_")
    shutil.copytree(os.path.join(EXAMPLE, "state"), d, dirs_exist_ok=True)
    return d


def step_interview() -> None:
    env = env_for(LJS_PROFILE=EXAMPLE, LJS_STATE=_state())
    code, out, took = run([PY, os.path.join(TOOLS, "interview_pack.py"), "pack",
                           "Larkspur Retail", "--today", "2026-10-25"], env=env)
    check("interview: a pack for the example person", code == 0 and "# Interview prep" in out,
          out.strip()[:300] if code == 0 else out.strip(), took)


def _export_zip(path: str, sep: str = "/") -> None:
    """A LinkedIn download with a contact whose name is not ASCII; with `sep` a backslash,
    as Windows PowerShell 5.1's Compress-Archive writes entry names. Invented people."""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"Basic_LinkedInDataExport_10-25-2026{sep}Connections.csv",
                   "Notes:\n\"\"\n\nFirst Name,Last Name,URL,Email Address,Company,Position,"
                   "Connected On\nZoë,Ñúñez-Ström,https://www.linkedin.com/in/example-zoe,,"
                   "Wrenfield Freight,Data Analyst,12 Oct 2026\n")
        z.writestr(f"Basic_LinkedInDataExport_10-25-2026{sep}messages.csv",
                   "CONVERSATION ID,CONVERSATION TITLE,FROM,SENDER PROFILE URL,TO,"
                   "RECIPIENT PROFILE URLS,DATE,SUBJECT,CONTENT,FOLDER\n")


def step_networking(root: str = ROOT, env: dict | None = None) -> None:
    env = env or env_for(LJS_PROFILE=EXAMPLE, LJS_STATE=_state())
    probe = (
        "import sys; sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[1] + '/network')\n"
        "import compose\n"
        "n = compose.first_note('Juno Castellan', common_ground='we both studied at Leeds')\n"
        "text = n if isinstance(n, str) else (n.get('text') if isinstance(n, dict) else str(n))\n"
        "print('NOTE', text)\n"
        "print('VALID', compose.validate(text, 'connection', name='Juno Castellan'))\n"
        "print('ADVICE', compose.advise(text, 'connection', name='Juno Castellan'))\n")
    code, out, took = run([PY, "-c", probe, os.path.join(root, "tools")], cwd=root, env=env)
    check("networking: a first note drafted, validated and advised", code == 0 and "NOTE" in out,
          out.strip(), took)
    code, out, took = run([PY, os.path.join(root, "tools", "network", "surface.py"),
                           "Juno Castellan"], cwd=root, env=env)
    check("networking: the surfacing check", code in (0, 1) and "Traceback" not in out,
          out.strip()[:300], took)
    note = os.path.join(tempfile.mkdtemp(prefix="ljs_note_"), "note.txt")
    with open(note, "w", encoding="utf-8") as fh:
        fh.write("Hi Juno, thanks for connecting. Zoë said you know the Leeds team well.\n")
    code, out, took = run([PY, os.path.join(root, "tools", "network", "state.py"), "message",
                           "larkspur_retail_castellan", "--text-file", note], cwd=root, env=env)
    check("networking: a message logged", code == 0 and "Traceback" not in out,
          out.strip()[:300], took)
    code, out, _ = run([PY, os.path.join(root, "tools", "network", "state.py"), "--help"],
                       cwd=root, env=env)
    code, helped, _ = run([PY, os.path.join(root, "tools", "network", "state.py"), "received",
                           "--help"], cwd=root, env=env)
    if code == 0 and "received" in helped and "usage: state.py received" in helped:
        code, out, took = run([PY, os.path.join(root, "tools", "network", "state.py"),
                               "received", "larkspur_retail_castellan", "--text-file", note],
                              cwd=root, env=env)
        check("networking: their reply logged (state.py received)", code == 0, out.strip(), took)
    else:
        print("info: state.py has no received command on this branch; not run", flush=True)
    for sep, label in (("/", "a LinkedIn download with accented names taken"),
                       ("\\", "a LinkedIn download zipped by Windows (backslash names) taken")):
        z = os.path.join(tempfile.mkdtemp(prefix="ljs_export_"), "Basic_LinkedInDataExport.zip")
        _export_zip(z, sep)
        code, out, took = run([PY, os.path.join(root, "tools", "network", "export.py"), "take",
                               z], cwd=root, env=env)
        check(f"networking: {label}", code == 0 and "Traceback" not in out, out.strip()[:400],
              took)
    code, out, took = run([PY, os.path.join(root, "tools", "open_actions.py"), "--due"],
                          cwd=root, env=env)
    check("networking: what is due today", code == 0 and "Traceback" not in out,
          out.strip().splitlines()[0] if out.strip() else "", took)


def step_suite() -> None:
    code, out, took = run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
                          env=env_for(), timeout=5400)
    tail = "\n".join(out.strip().splitlines()[-40:])
    check("the test suite", code == 0, tail, took)


# ------------------------------------------------------------------ a computer chat

def _git(cwd, *args, env=None):
    return run(["git", "-C", cwd, *args], cwd=cwd, env=env)


def step_computer() -> None:
    """A copy already set up (the example person as its profile), cloned on this computer
    the way COMPUTER.md does, then the chat's ordinary day."""
    tmp = tempfile.mkdtemp(prefix="ljs computer ")      # a space in the path, as in Documents
    home = os.path.join(tmp, "home")
    os.makedirs(home)
    env = env_for(HOME=home, USERPROFILE=home, GIT_TERMINAL_PROMPT="0",
                  GIT_AUTHOR_NAME="Morgan Ellis", GIT_AUTHOR_EMAIL="morgan@example.com",
                  GIT_COMMITTER_NAME="Morgan Ellis", GIT_COMMITTER_EMAIL="morgan@example.com")
    for k in ("LJS_PROFILE", "LJS_STATE"):
        env.pop(k, None)
    app = os.path.join(tmp, "app")
    code, out, _ = run(["git", "clone", "-q", "--no-local", ROOT, app], cwd=tmp, env=env)
    if not check("computer: a stand-in for the app on GitHub", code == 0, out):
        return
    _git(app, "checkout", "-q", "-B", "master", env=env)
    _git(app, "tag", "-f", "v999.0.0", env=env)
    # The person's copy: the app, with the example person moved in as their own.
    seed = os.path.join(tmp, "seed")
    run(["git", "clone", "-q", app, seed], cwd=tmp, env=env)
    shutil.copytree(EXAMPLE, os.path.join(seed, "profile"),
                    ignore=shutil.ignore_patterns("state"))
    for name in os.listdir(os.path.join(EXAMPLE, "state")):
        src = os.path.join(EXAMPLE, "state", name)
        dst = os.path.join(seed, name)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy(src, dst)
    _git(seed, "add", "-A", "-f", "profile", env=env)
    for f in ("job_search_tracker.csv", "network_contacts.csv", "network_threads.csv",
              "job_scraper"):
        _git(seed, "add", "-f", f, env=env)
    _git(seed, "commit", "-q", "-m", "set up", env=env)
    origin = os.path.join(tmp, "origin.git")
    run(["git", "clone", "-q", "--bare", seed, origin], cwd=tmp, env=env)
    here = os.path.join(tmp, "My Job Search Ö")
    code, out, _ = run(["git", "clone", "-q", origin, here], cwd=tmp, env=env)
    if not check("computer: their copy cloned into a folder with a space and an accent",
                 code == 0, out):
        return
    cenv = dict(env, LJS_APP_URL=app)
    # COMPUTER.md step 5: what the copy needs on this computer, in its own .venv.
    code, out, took = run([PY, "tools/env_check.py", "--fix", "packages", "runtime"], cwd=here,
                          env=cenv, timeout=1800)
    check("computer: what this computer lacks, installed in the background", code == 0,
          out.strip(), took)
    code, out, took = run([PY, "tools/setup_state.py", "--no-fetch"], cwd=here, env=cenv)
    check("computer: an already set-up copy is ready and asks nothing",
          code == 0 and out.startswith("ready") and "?" not in out, out.strip(), took)
    for label, cmd, codes in (
            ("pull master", [PY, "tools/sync_app.py", "--pull"], (0,)),
            ("take the app's update", [PY, "tools/sync_app.py", "--on", "check", "--tools",
                                       "none"], (0,)),
            ("the day's check, once", [PY, "tools/sync_app.py", "--if-stale", "--on", "check",
                                       "--tools", "none"], (0,)),
            ("the place check", [PY, "tools/place.py"], (0, 1)),
            ("what is due today", [PY, "tools/open_actions.py", "--due"], (0,)),
            ("the contact book", [PY, "tools/network/state.py"], (0,))):
        code, out, took = run(cmd, cwd=here, env=cenv)
        check(f"computer: {label}", code in codes and "Traceback" not in out, out.strip(), took)
    step_networking(here, cenv)
    code, out, took = run([PY, "tools/save_state.py"], cwd=here, env=cenv)
    check("computer: saving stages the state", code == 0 and "Traceback" not in out,
          out.strip()[:300], took)
    _merge_two_chats(tmp, origin, cenv)
    shell = shutil.which("bash")
    if shell:
        code, out, took = run([shell, "tools/ci_local.sh", "--quick"], cwd=here, env=cenv,
                              timeout=3600)
        check("computer: the local checks before a merge (ci_local.sh --quick)", code == 0,
              "\n".join(out.strip().splitlines()[-30:]), took)
    shutil.rmtree(tmp, ignore_errors=True)


def _merge_two_chats(tmp: str, origin: str, env: dict) -> None:
    """Two chats each add a message to the log; the second merges the first's, row by row."""
    a, b = os.path.join(tmp, "chat a"), os.path.join(tmp, "chat b")
    for d in (a, b):
        run(["git", "clone", "-q", origin, d], cwd=tmp, env=env)
        run([PY, "-c", "import sys; sys.path.insert(0, 'tools'); import merge_state; "
             "merge_state.install('.')"], cwd=d, env=env)
    rows = {a: "larkspur_retail_castellan,2026-10-24,out,message,Hi Juno from chat A",
            b: "fernhill_freight_halloway,2026-10-24,out,message,Hi Wren from chat B"}
    with open(os.path.join(a, "network_threads.csv"), encoding="utf-8") as fh:
        head = fh.readline().strip().split(",")
    for d, row in rows.items():
        vals = dict(zip(["contact_id", "date", "direction", "channel", "summary"],
                        row.split(",")))
        with open(os.path.join(d, "network_threads.csv"), "a", encoding="utf-8",
                  newline="") as fh:
            fh.write(",".join(vals.get(h, "") for h in head) + "\n")
        _git(d, "commit", "-q", "-am", f"a message from {os.path.basename(d)}", env=env)
    _git(a, "push", "-q", "origin", "HEAD:master", env=env)
    _git(b, "fetch", "-q", "origin", env=env)
    code, out, took = _git(b, "merge", "-q", "--no-edit", "origin/master", env=env)
    with open(os.path.join(b, "network_threads.csv"), encoding="utf-8") as fh:
        text = fh.read()
    ok = code == 0 and "Hi Juno from chat A" in text and "Hi Wren from chat B" in text \
        and "<<<<<<<" not in text
    check("computer: two chats' new messages merge row by row", ok, out.strip(), took)


STEPS = {"install": step_install, "documents": step_documents, "round": step_round,
         "interview": step_interview, "networking": step_networking, "suite": step_suite,
         "computer": step_computer}
ALL = ("install", "documents", "round", "interview", "networking")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    names = list(ALL) if argv == ["all"] else argv
    unknown = [n for n in names if n not in STEPS]
    if unknown:
        print(f"platform_check: no step {', '.join(unknown)}", file=sys.stderr)
        return 2
    print(f"platform: {sys.platform}, Python {sys.version.split()[0]} at {PY}", flush=True)
    for name in names:
        began = time.monotonic()
        try:
            STEPS[name]()
        except Exception as exc:  # noqa: BLE001  a step that crashes is a failed step
            import traceback
            check(f"{name}: ran to the end", False, traceback.format_exc())
        print(f"time: {name} {time.monotonic() - began:.1f} s", flush=True)
    bad = [s for s, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(bad)} passed, {len(bad)} failed"
          + (": " + "; ".join(bad) if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
