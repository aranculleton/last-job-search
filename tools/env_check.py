#!/usr/bin/env python3
"""Can this session do the whole job? One line per thing a search needs.

/setup runs this first, so a person hears about a missing tool or a blocked job
board while there is still time to change the cloud environment, not at the
end. It replaced an inline check that read any HTTP status as success (a host
the network policy refuses still "answered") and never looked at Ashby,
Workday, pypdf or bun.

    python3 tools/env_check.py          # report; exit 0 if all is well, 1 if anything is not

What it reads:
  tools     lualatex and xelatex (the documents), pdftotext (the text-layer
            check), pypdf (the same, and it can be installed but broken: a
            container's system `cryptography` makes it panic in pyo3 until
            `pip3 install --upgrade cffi`), bun (the portal CLIs)
  hosts     the portals the app calls, every portal the person has (the `url:`
            in its SKILL.md), and every host their employers' boards in
            profile/boards.py are read from, as openroles names them
            (`openroles.hosts`, so this file keeps no list of its own). Before
            any board is on file, the hosts of the three systems most employers
            use stand in. A proxy that answers CONNECT with 403 or 407 is the
            environment's network policy: the host goes under Allowed domains.
            Any other failure is the host or DNS. A host that answers at all,
            even 401 or 404, is reachable.

    python3 tools/env_check.py --allowlist   # the domains a custom network policy needs
    python3 tools/env_check.py --say         # what to tell the person when job sites are
                                             # blocked in a cloud chat, in plain words, or nothing
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import local_path  # noqa: E402

# Look where a person's computer keeps TeX and Bun before saying either is missing: a
# chat's shell on a Mac lacks /Library/TeX/texbin, and this said "install LaTeX" to
# someone whose LaTeX compiled both example documents.
local_path.extend()

HOSTS = (
    ("LinkedIn", "https://www.linkedin.com"),
    ("freehire", "https://freehire.me"),
)
# Before the person has an employer board on file: the systems most boards are on.
COMMON = ("greenhouse", "lever", "ashby")
POLICY = {"403", "407"}


def hosts() -> list[tuple[str, str]]:
    """The app's hosts, then each enabled portal of the person's that names a `url:`."""
    out = list(HOSTS)
    try:
        import portals
        for name, on in portals.enabled().items():
            u = portals.url(name)
            if on and name not in portals.APP_PORTALS and u.startswith("http"):
                out.append((name, u))
    except Exception:
        pass
    return out


def classify(exit_code: int, connect: str, code: str) -> str:
    """'reachable', 'blocked' (the network policy) or 'unreachable'."""
    if connect in POLICY:
        return "blocked"
    if exit_code == 0 and code not in ("", "000"):
        return "reachable"
    return "unreachable"


def probe(url: str) -> tuple[str, str]:
    """(verdict, detail) for one URL, through whatever proxy the session uses."""
    if not shutil.which("curl"):
        return "unreachable", "curl is not installed"
    p = subprocess.run(["curl", "-sS", "-o", "/dev/null", "--max-time", "8",
                        "-w", "%{http_connect} %{http_code}", url],
                       capture_output=True, text=True)
    connect, _, code = (p.stdout.strip() + "  ").partition(" ")
    code = code.strip()
    verdict = classify(p.returncode, connect.strip(), code)
    detail = {"reachable": f"HTTP {code}",
              "blocked": f"blocked by this chat's cloud settings (proxy {connect}): the fix is "
                         "below",
              "unreachable": (p.stderr.strip().splitlines() or [f"curl exit {p.returncode}"])[-1]
              }[verdict]
    return verdict, detail


def board_hosts() -> list[tuple[str, str]]:
    """(system, URL) for every host the person's employer boards are read from, each once,
    named by openroles; the common systems' hosts while no board is on file. Nothing is
    fetched here: a board's hosts follow from its token."""
    from openroles import Board, hosts as hosts_of
    from openroles.models import NAMES
    from openroles.providers import READERS
    try:
        import ats_boards
        boards = [(kind, token) for kind, token, *_ in getattr(ats_boards, "BOARDS", {}).values()
                  if kind in READERS]
    except Exception:
        boards = []
    # A system's own API host does not depend on the board, so any name stands in.
    boards = boards or [(kind, "example") for kind in COMMON]
    out: list[tuple[str, str]] = []
    for kind, token in boards:
        try:
            found = hosts_of(Board(kind, token))
        except Exception:
            continue
        for host in found:
            if all(host != u.split("//", 1)[1] for _, u in out):
                out.append((NAMES.get(kind, kind), f"https://{host}"))
    return out


def blocked_say(names) -> str:
    """What the person is told when a cloud chat cannot reach job sites: what happened, the
    one recommended fix as numbered steps from the registry, and what happens meanwhile.

    It replaced "the network policy refused it (proxy 403); add the host under the cloud
    environment's Allowed domains", which a person new to all of it could not act on: they
    had never heard of an environment (2026-10-20). Full is recommended over a list of
    sites because a list needs a new entry for each new employer's board."""
    import claude_surfaces
    names = [n for n in dict.fromkeys(names) if n]
    what = ", ".join(names[:3]) + (" and others" if len(names) > 3 else "")
    return "\n".join(
        [f"This chat can't reach the job sites{' (' + what + ')' if what else ''}: it runs on "
         "a computer in the cloud that only reaches a few websites until you allow more.",
         "Recommended, once:"]
        + claude_surfaces.steps("cloud-internet")
        + ["Until then I won't search: it would only find old jobs. Say \"done\" once it's "
           "changed."])


def blocked_names() -> list[str]:
    """The job sites this chat's cloud settings refuse, probed now; [] off the cloud."""
    if not CLOUD:
        return []
    # Side by side: the day's sync runs this, and one after another took a second a host.
    from concurrent.futures import ThreadPoolExecutor
    found = hosts() + board_hosts()
    with ThreadPoolExecutor(max_workers=8) as pool:
        verdicts = list(pool.map(lambda nu: probe(nu[1])[0], found))
    return [name for (name, _), v in zip(found, verdicts) if v == "blocked"]


def allowlist() -> list[str]:
    """Every domain a custom network policy has to allow for this person's search."""
    from urllib.parse import urlsplit
    out = [urlsplit(u).hostname for _, u in hosts() + board_hosts()]
    if "www.linkedin.com" in out:
        out.insert(out.index("www.linkedin.com"), "linkedin.com")
    return list(dict.fromkeys(h for h in out if h))


def module_state(name: str) -> bool:
    """Is a Python module importable here? Asked apart, like pypdf, so a broken one cannot crash this."""
    return subprocess.run([sys.executable, "-c", f"import {name}"],
                          capture_output=True, text=True).returncode == 0


def pypdf_state() -> str:
    """'ok', 'missing' or 'broken'. Run apart, because a pyo3 panic kills the
    interpreter rather than raising."""
    p = subprocess.run([sys.executable, "-c", "import pypdf; pypdf.PdfReader"],
                       capture_output=True, text=True)
    if p.returncode == 0:
        return "ok"
    return "missing" if "No module named" in p.stderr else "broken"


# A cloud session sets CLAUDE_CODE_REMOTE. Its fixes are the environment's Setup
# script and network allowlist; on the person's own computer they are a one-time
# install and there is no network policy at all.
CLOUD = os.environ.get("CLAUDE_CODE_REMOTE", "").lower() == "true"


def _install(what: str) -> str:
    """The one command that installs `what` where this session runs."""
    if CLOUD or shutil.which("apt-get"):
        return {"latex": "./tools/setup_env.sh installs it" + (" for this session" if CLOUD else ""),
                "poppler": "./tools/setup_env.sh installs it"}[what]
    if sys.platform == "darwin":
        return {"latex": "install it once: brew install --cask mactex-no-gui (SETUP.md, Local machine)",
                "poppler": "./tools/setup_env.sh installs it (brew install poppler)"}[what]
    if sys.platform.startswith("win"):
        return {"latex": "install it once: winget install MiKTeX.MiKTeX (SETUP.md, Local machine)",
                "poppler": "winget install oschwartz10612.Poppler"}[what]
    return "install it once (SETUP.md, Local machine)"


BREW = ('/bin/bash -c "$(curl -fsSL '
        'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"')


def local_fixes(system=None, have=None, module=None, py_ok=None, pypdf=None,
                gh_signed_in=None) -> list:
    """What this computer is missing, as [(what, the one command, whose)].

    The person's own computer, never a cloud session: one list, one exact command
    each. `whose` is "" where Claude runs it itself, "password" where it asks for the
    computer's password and "sign-in" where the person signs in themselves, because
    those two are the person's to run. Every argument is injectable so each machine
    can be tested from any other.
    """
    import python_floor
    system = system or sys.platform
    have = have or shutil.which
    module = module or module_state
    py_ok = python_floor.ok() if py_ok is None else py_ok
    pypdf = pypdf or pypdf_state()
    mac, win = system == "darwin", system.startswith("win")
    pip = "python -m pip install --user" if win else "pip3 install --user"
    out = []
    if not py_ok:
        cmd = ("xcode-select --install" if mac else "winget install Python.Python.3.12" if win
               else "sudo apt-get install -y python3")
        out.append(("Python 3.9 or newer", cmd, "" if win else "password"))
    for mod, package in (("pytest", "pytest"), ("yaml", "pyyaml")):
        if not module(mod):
            out.append((package, f"{pip} {package}", ""))
    if pypdf != "ok":
        out.append(("pypdf", f"{pip} --upgrade cffi" if pypdf == "broken" else f"{pip} pypdf",
                    ""))
    latex = not (have("lualatex") and have("xelatex"))
    poppler, bun, gh = not have("pdftotext"), not have("bun"), not have("gh")
    if mac:
        if (latex or poppler or gh) and not have("brew"):
            out.append(("Homebrew (installs what follows)", BREW, "password"))
        if latex:
            out.append(("LaTeX, to make the PDFs", "brew install --cask mactex-no-gui", "password"))
        if poppler:
            out.append(("Poppler, to check the PDFs", "brew install poppler", ""))
    elif win:
        if latex:
            out.append(("LaTeX, to make the PDFs",
                        "winget install MiKTeX.MiKTeX (or the installer at https://miktex.org/download)",
                        "password"))
        if poppler:
            out.append(("Poppler, to check the PDFs", "winget install oschwartz10612.Poppler", "password"))
    elif latex or poppler:
        out.append(("LaTeX and Poppler, for the PDFs", "./tools/setup_env.sh", "password"))
    if bun:
        out.append(("Bun, for the job searches",
                    'powershell -c "irm bun.sh/install.ps1 | iex"' if win
                    else "curl -fsSL https://bun.sh/install | bash", ""))
    # A chat on a computer has no GitHub tools of its own: `gh` is how its work
    # reaches GitHub, where the other chats and the brief read it.
    if gh:
        out.append(("GitHub's command line, so your work reaches GitHub",
                    "brew install gh" if mac else "winget install GitHub.cli" if win
                    else "sudo apt-get install -y gh", "password" if not (mac or win) else ""))
    if gh or gh_signed_in is False or (gh_signed_in is None and not _gh_signed_in(have)):
        out.append(("GitHub sign-in for it", "gh auth login", "sign-in"))
    return out


def _gh_signed_in(have) -> bool:
    if not have("gh"):
        return False
    try:
        return subprocess.run(["gh", "auth", "status"], capture_output=True, text=True,
                              timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--allowlist"]:
        print("\n".join(allowlist()))
        return 0
    if argv[:1] == ["--say"]:
        names = blocked_names()
        if names:
            print(blocked_say(names))
        return 0
    bad = 0
    print("where: " + ("a cloud session" if CLOUD else "this computer"))

    def line(name, ok, detail=""):
        nonlocal bad
        bad += not ok
        print(f"  {name:28} {'ok' if ok else 'NO'}{'  ' + detail if detail else ''}")

    print("tools")
    import python_floor
    line(f"Python {python_floor.FLOOR[0]}.{python_floor.FLOOR[1]}+ (this is "
         f"{sys.version_info[0]}.{sys.version_info[1]})", python_floor.ok(),
         "" if python_floor.ok() else python_floor.how_to_install())
    for module, package, why in (("pytest", "pytest", "the checks before a merge"),
                                 ("yaml", "pyyaml", "the skills check")):
        have = module_state(module)
        fix = (f"missing; pip3 install {package}" if CLOUD
               else f"missing; pip3 install --user {package} (no password needed)")
        line(f"{package} ({why})", have, "" if have else fix)
    latex = [t for t in ("lualatex", "xelatex") if not shutil.which(t)]
    line("LaTeX (lualatex, xelatex)", not latex, "" if not latex else "missing; " + _install("latex"))
    line("pdftotext (Poppler)", bool(shutil.which("pdftotext")),
         "" if shutil.which("pdftotext") else "missing; " + _install("poppler"))
    state = pypdf_state()
    line("pypdf", state == "ok", {"ok": "", "missing": "missing; pip3 install pypdf",
                                  "broken": "installed but panics; pip3 install --upgrade cffi"}[state])
    line("bun (portal searches)", bool(shutil.which("bun")),
         "" if shutil.which("bun") else "missing; ./tools/setup_env.sh installs it (the portal CLIs need it)")

    print("job boards")
    blocked = []
    for name, url in hosts() + board_hosts():
        verdict, detail = probe(url)
        line(f"{name} ({url.split('//')[1]})", verdict == "reachable", detail)
        if verdict == "blocked":
            blocked.append(name)
    print()
    print("all good" if not bad else f"{bad} problem(s) above")
    if blocked:
        print("\nTell the person, in these words, once:")
        print(blocked_say(blocked))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
