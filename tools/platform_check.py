#!/usr/bin/env python3
"""Proof that the app works on a computer with nothing extra installed first.

The platforms workflow (.github/workflows/platforms.yml) runs this on Linux, a Mac and
Windows, after taking away what a person would not have (Homebrew and MacTeX on the
Mac, winget on Windows, sudo and TeX on Linux):

    python3 tools/platform_check.py install      env_check --fix, then each tool runs
    python3 tools/platform_check.py python       the Python an app command runs under when
                                                 python3 starts it (on a Mac, a current one
                                                 in .venv, Apple's own untouched), and
                                                 Python's own HTTPS checking certificates
    python3 tools/platform_check.py documents    a resume and letter in black and two
                                                 colours, fitted and checked, the colour
                                                 present only where one was asked for
    python3 tools/platform_check.py general      a general resume with no posting behind it
                                                 for an accented name, the same three ways,
                                                 the name read back from the text layer
    python3 tools/platform_check.py seed         their own LinkedIn download (a byte-order
                                                 mark, Windows line ends, accents) read
                                                 into a profile seed
    python3 tools/platform_check.py round        an offline round matches its golden
                                                 summary (tests/round_fixture.py)
    python3 tools/platform_check.py interview    an interview pack from the example person
    python3 tools/platform_check.py networking   a first note drafted and checked, the
                                                 surfacing check, a message logged, a
                                                 LinkedIn download with Windows-style names
                                                 and accents taken, the due list
    python3 tools/platform_check.py computer     a computer chat arriving in a copy that is
                                                 already set up, and its ordinary day
    python3 tools/platform_check.py all          install, python, documents, general, seed,
                                                 round, interview, networking

Every step prints PASS or FAIL with what it saw and how long it took, keeps going after
a failure, and the run exits 1 when any failed. Nothing reaches the network but the
installs; the people, employers and postings are the example person's, all invented.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path[:0] = [TOOLS, os.path.join(ROOT, "tests"), os.path.join(ROOT, "templates")]
import local_path  # noqa: E402

# This check runs under the repo's .venv, as any app command does (it imports pypdf
# itself); every command it starts is started by the Python that started it, so each one
# shows it finds the venv's Python by itself (on a Mac, Apple's python3 and a current
# Python in .venv).
local_path.run_in_venv()
PY = os.environ.pop(local_path.REEXEC, "") or sys.executable
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
    # In the Python the app's commands use, which the install may have just made.
    app = local_path.venv_python() if local_path.venv_runs() else PY
    code, out, _ = run([app, "-c", "import sys; sys.path.insert(0, sys.argv[1]); "
                        "import pdftext; print(pdftext.reader())", TOOLS])
    check("install: the PDF reader is pypdf", out.strip() == "pypdf", out.strip())
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


def _version(python: str) -> str:
    code, out, _ = run([python, "-I", "-S", "-c", "import platform; print(platform.python_version())"])
    return out.strip() if code == 0 else ""


def step_python() -> None:
    """Which Python an app command runs under when `python3` (whichever this computer has)
    starts it: the repo's .venv's where that was made by another version. On a Mac, a
    current one; Apple's own python3 still runs; and Python's own HTTPS checks
    certificates."""
    import python_floor
    started = _version(PY)
    made = local_path.venv_version()
    other = local_path.venv_runs() and made and ".".join(map(str, made)) != \
        ".".join(started.split(".")[:2])
    code, out, took = run([PY, os.path.join(TOOLS, "python_floor.py"), "--which"], env=env_for())
    want = local_path.venv_python() if other else PY
    ran = out.strip().rsplit(" at ", 1)[-1]
    same = os.path.normcase(os.path.realpath(ran)) == os.path.normcase(os.path.realpath(want))
    check(f"python: {os.path.basename(PY)} ({started}) runs the app's commands under "
          + (".venv's Python" if other else "itself"), code == 0 and same, out.strip(), took)
    if sys.platform == "darwin":
        ok = bool(made) and tuple(made) >= python_floor.CURRENT and local_path.venv_runs()
        check(f"python: the app's Python on this Mac is {python_floor.CURRENT[0]}."
              f"{python_floor.CURRENT[1]} or newer", ok, f".venv made by {made}")
    code, out, took = run([PY, "-c", "import sys; print(sys.version.split()[0])"], env=env_for())
    check(f"python: {PY} itself still runs", code == 0, out.strip(), took)
    code, out, took = run([PY, os.path.join(TOOLS, "env_check.py"), "--https"], env=env_for())
    check("python: Python's own HTTPS checks the certificate (urllib)",
          code == 0 and ": ok," in out, out.strip(), took)


def _tests(name: str):
    """A module of the app's own test suite (tests/ is on sys.path above), loaded by name:
    the example draft and the offline round live there, and are not packages to install."""
    import importlib
    return importlib.import_module(name)


def _draft() -> dict:
    return json.loads(json.dumps(_tests("test_the_resume_says_what_the_draft_put_on_it").DRAFT))


def _doc_state(root: str = ROOT) -> str:
    """A state folder of its own for one batch, so nothing lands in the checkout: cv/, and
    cover_letters/ with the letter's class and fonts beside it (copied, as a symlink on
    Windows needs a setting a person has not turned on)."""
    d = tempfile.mkdtemp(prefix="ljs_docs_")
    os.makedirs(os.path.join(d, "cv"))
    os.makedirs(os.path.join(d, "cover_letters"))
    shutil.copy(os.path.join(root, "cover_letters", "cover.cls"), os.path.join(d, "cover_letters"))
    shutil.copytree(os.path.join(root, "cover_letters", "OpenFonts"),
                    os.path.join(d, "cover_letters", "OpenFonts"))
    return d


def _colours(pdf: str) -> set:
    """Every fill and stroke colour a PDF's pages set, as hex (black is 000000)."""
    import pdftext
    pdftext.pypdf_ok()
    from pypdf import PdfReader
    out = set()
    for page in PdfReader(pdf).pages:
        data = page.get_contents().get_data().decode("latin-1")
        for m in re.finditer(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(?:rg|RG)\b", data):
            out.add("%02X%02X%02X" % tuple(round(float(x) * 255) for x in m.groups()))
        for m in re.finditer(r"(?<![\d.])([\d.]+)\s+(?:g|G)\b", data):
            out.add("%02X" % round(float(m.group(1)) * 255) * 3)
    return out


def _batch(label: str, drafts: list, env: dict, name: str = "", root: str = ROOT) -> None:
    """One batch in black and two colours: fitted to one page, checked, its colour present
    only where a style asked for one, and `name` read back from the text layer."""
    import doc_style
    import pdftext
    for style in ("black", "navy", "burgundy"):
        here = _doc_state(root)
        senv = dict(env, LJS_STATE=here)
        ds = [dict(d, style=style) for d in drafts]
        path = os.path.join(here, "drafts.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(ds, fh, ensure_ascii=False)
        code, out, took = run([PY, os.path.join(root, "tools", "fit_to_page.py"), path],
                              cwd=root, env=senv)
        check(f"{label}: {style} fitted to one page", code == 0 and "resume 1p" in out
              and "resume 2p" not in out, out.strip(), took)
        code, out, took = run([PY, os.path.join(root, "tools", "verify_batch.py"), path],
                              cwd=root, env=senv)
        check(f"{label}: {style} checked", code == 0 and "BATCH: ALL PASS" in out,
              out.strip().splitlines()[-1] if code == 0 else out.strip(), took)
        pdfs = sorted(os.path.join(here, sub, f) for sub in ("cv", "cover_letters")
                      for f in os.listdir(os.path.join(here, sub)) if f.endswith(".pdf"))
        if not pdfs:
            check(f"{label}: {style} made its PDFs", False, "no PDF in " + here)
            continue
        accent = doc_style.STYLES[style][0]
        seen = set().union(*(_colours(p) for p in pdfs))
        if accent:
            check(f"{label}: {style} carries its colour #{accent}", accent in seen,
                  ", ".join(sorted(seen)))
        else:
            others = {c for c in seen if c not in ("000000", "2B2B2B", "6A6A6A")}
            check(f"{label}: black carries no colour", not others, ", ".join(sorted(seen)))
        if name:
            for pdf in pdfs:
                text = pdftext.text(pdf)
                ok = name in text and "\ufffd" not in text and "(cid:" not in text
                check(f"{label}: {style} {os.path.basename(os.path.dirname(pdf))} reads "
                      f"the name back", ok, text.strip().splitlines()[0] if text.strip() else "")


def step_documents() -> None:
    _batch("documents", [_draft()], env_for(LJS_PROFILE=EXAMPLE))


# The commands another part of the app adds for a person with no resume yet: a general
# resume for their main target role, staged with no posting, and the profile seed read
# from their LinkedIn download. (file, arguments, what it leaves in {dir}); the first
# whose file is there and whose --help names it is run. With none, the step says so and
# runs what this branch has: the example person's draft, under an accented name, with
# no posting behind it; and the export reader the networking side already uses.
GENERAL_ENTRY = (("tools/stage_picks.py", ("general", "{dir}"), "drafts.json"),
                 ("tools/general_resume.py", ("{dir}",), "drafts.json"))
SEED_ENTRY = (("tools/network/own_profile.py", ("seed", "--from", "{src}")),
              ("tools/profile_seed.py", ("{src}",)))
# An invented name with a letter from each of three alphabets' accents, which a code
# page, a font without the glyph or a LaTeX engine reading bytes loses first.
ACCENTED = {"name": "Zoë Ångström-Núñez", "first": "Zoë", "last": "Ångström-Núñez",
            "file_prefix": "Zoë_Ångström-Núñez"}


def _entry(entries, env, root: str = ROOT):
    """(command, what it leaves) for the first entry here, or None."""
    for path, args, *leaves in entries:
        cmd = args[0] if args and not args[0].startswith("{") else ""
        if not os.path.isfile(os.path.join(root, path)):
            continue
        code, out, _ = run([PY, os.path.join(root, path), *([cmd] if cmd else []), "--help"],
                           cwd=root, env=env)
        if code == 0 and "usage" in out.lower() and (not cmd or cmd in out):
            return [PY, os.path.join(root, path), *args], (leaves[0] if leaves else "")
    return None


def _accented_profile() -> str:
    """The example person under an accented name: the same profile, every file copied."""
    d = os.path.join(tempfile.mkdtemp(prefix="ljs_zoe_"), "profile")
    shutil.copytree(EXAMPLE, d)
    p = os.path.join(d, "person.json")
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    data["identity"].update(ACCENTED)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return d


def step_general(root: str = ROOT, env: dict | None = None) -> None:
    profile = _accented_profile()
    env = dict(env or env_for(), LJS_PROFILE=profile, LJS_STATE=_state())
    found = _entry(GENERAL_ENTRY, env, root)
    if found:
        work = tempfile.mkdtemp(prefix="ljs_general_")
        cmd, leaves = found
        cmd = [c.replace("{dir}", work) for c in cmd]
        code, out, took = run(cmd, cwd=root, env=env)
        made = os.path.join(work, leaves)
        if not check("general: staged with no posting (" + " ".join(cmd[1:3]) + ")",
                     code == 0 and os.path.isfile(made), out.strip(), took):
            return
        with open(made, encoding="utf-8") as fh:
            drafts = json.load(fh)
        drafts = drafts if isinstance(drafts, list) else [drafts]
    else:
        print("info: no general-resume command on this branch ("
              + ", ".join(e[0] for e in GENERAL_ENTRY) + "); rendering the example "
              "person's draft under an accented name instead", flush=True)
        d = _draft()
        d.pop("posting", None)
        drafts = [d]
    _batch("general", drafts, env, name=ACCENTED["name"], root=root)


def _seed_files() -> dict:
    """Their own profile as LinkedIn writes it: a byte-order mark, Windows line ends and
    letters outside ASCII in every file. Invented."""
    crlf = "\r\n"
    rows = {
        "Profile.csv": ["First Name,Last Name,Headline,Summary,Geo Location",
                        "Zoë,Ångström-Núñez,Analyste de données,Prévisions et données,"
                        "\"Montréal, Québec, Canada\""],
        "Positions.csv": ["Company Name,Title,Description,Location,Started On,Finished On",
                          "Ørkenvik Logistik,Analyste principale,\"Prévisions, SQL et Python\","
                          "Montréal,Mar 2023,",
                          "Brindle & Hart Logistics,Data Analyst,Forecasts by depot,"
                          "Manchester,Jan 2020,Feb 2023"],
        "Education.csv": ["School Name,Start Date,End Date,Notes,Degree Name,Activities",
                          "Université de Lumière,2016,2019,,Licence en économie,Échecs"],
        "Skills.csv": ["Name", "Prévision", "SQL", "Python", "Power BI"],
    }
    return {n: ("\ufeff" + crlf.join(r) + crlf).encode("utf-8") for n, r in rows.items()}


def step_seed() -> None:
    files = _seed_files()
    base = tempfile.mkdtemp(prefix="ljs_seed_")
    folder = os.path.join(base, "Basic_LinkedInDataExport_10-25-2026")
    os.makedirs(folder)
    for n, data in files.items():
        with open(os.path.join(folder, n), "wb") as fh:
            fh.write(data)
    z = os.path.join(base, "Basic_LinkedInDataExport_10-25-2026.zip")
    with zipfile.ZipFile(z, "w") as zf:
        for n, data in files.items():
            zf.writestr(f"Basic_LinkedInDataExport_10-25-2026/{n}", data)
    env = env_for(LJS_PROFILE=EXAMPLE, LJS_STATE=_state())
    found = _entry(SEED_ENTRY, env)
    if found:
        for src, label in ((z, "the ZIP"), (folder, "the folder")):
            cmd = [c.replace("{src}", src) for c in found[0]]
            code, out, took = run(cmd, env=env)
            ok = code == 0 and ("Ørkenvik" in out or "Analyste principale" in out)
            check(f"seed: {label} read into a profile seed (" + " ".join(cmd[1:3]) + ")",
                  ok and "Traceback" not in out, out.strip()[:400], took)
    else:
        print("info: no profile-seed command on this branch ("
              + ", ".join(e[0] for e in SEED_ENTRY) + "); reading the download with the "
              "export reader the networking side uses", flush=True)
    # The reader underneath, in a Python of its own, as a chat runs it: what comes back is
    # printed as JSON with every letter escaped, so the console's code page cannot touch it.
    probe = ("import json, sys; sys.path[:0] = [sys.argv[1], sys.argv[1] + '/network']\n"
             "import own_profile\n"
             "print(json.dumps(own_profile.from_export(sys.argv[2])))\n")
    want = {"company": "Ørkenvik Logistik", "title": "Analyste principale",
            "school": "Université de Lumière", "skill": "Prévision",
            "location": "Montréal, Québec, Canada"}
    for src, label in ((z, "the ZIP"), (folder, "the folder")):
        code, out, took = run([PY, "-c", probe, TOOLS, src], env=env)
        try:
            got = json.loads(out.strip().splitlines()[-1])
        except (ValueError, IndexError):
            check(f"seed: {label} read (own_profile.from_export)", False, out.strip(), took)
            continue
        seen = {"company": got["positions"][0]["company"] if got.get("positions") else "",
                "title": got["positions"][0]["title"] if got.get("positions") else "",
                "school": got["education"][0]["school"] if got.get("education") else "",
                "skill": (got.get("skills") or [""])[0], "location": got.get("location", "")}
        ok = seen == want and len(got.get("positions", [])) == 2 and len(got["skills"]) == 4
        check(f"seed: {label} read with its byte-order mark, line ends and accents "
              "(own_profile.from_export)", ok, json.dumps(seen, ensure_ascii=False), took)


def step_round() -> None:
    os.environ.update(LJS_RESCREEN="off", LJS_PROFILE=EXAMPLE)
    import person
    person.reset()
    F = _tests("round_fixture")
    work = tempfile.mkdtemp(prefix="ljs_round_")
    began = time.monotonic()
    out = os.path.join(work, "scrape")
    code, said = F.scrape(out)
    if not os.path.isfile(os.path.join(out, "kept.json")):
        check("round: the scrape keeps and drops what it always did", False, said[-1500:])
        return
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
    # The general resume again, from the copy in a folder with a space and an accent: where
    # the TeX engine reads its files from a path a code page can lose.
    import local_path
    local_path.extend()
    if shutil.which("lualatex") and shutil.which("xelatex"):
        step_general(here, dict(cenv, PATH=os.environ["PATH"]))
    else:
        print("info: no LaTeX on this computer; the general step checks the resume", flush=True)
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


STEPS = {"install": step_install, "python": step_python, "documents": step_documents,
         "general": step_general,
         "seed": step_seed, "round": step_round, "interview": step_interview,
         "networking": step_networking, "suite": step_suite, "computer": step_computer}
ALL = ("install", "python", "documents", "general", "seed", "round", "interview",
       "networking")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: python3 tools/platform_check.py <step>... | all\n\n" + __doc__.strip())
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
        except Exception:  # noqa: BLE001  a step that crashes is a failed step
            import traceback
            check(f"{name}: ran to the end", False, traceback.format_exc())
        print(f"time: {name} {time.monotonic() - began:.1f} s", flush=True)
    bad = [s for s, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(bad)} passed, {len(bad)} failed"
          + (": " + "; ".join(bad) if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
