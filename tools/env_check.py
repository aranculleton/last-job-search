#!/usr/bin/env python3
"""Can this session do the whole job? One line per thing a search needs.

/setup runs this first, so a person hears about a missing tool or a blocked job
board while there is still time to change the cloud environment, not at the
end. It replaced an inline check that read any HTTP status as success (a host
the network policy refuses still "answered") and never looked at Ashby,
Workday, pypdf or bun.

    python3 tools/env_check.py          # report; exit 0 if all is well, 1 if anything is not
    python3 tools/env_check.py --fix    # install what is missing (tools/installs.py): on a
                                        # computer into the person's own folders with no
                                        # password; in a cloud chat, ./tools/setup_env.sh

What it reads:
  tools     lualatex and xelatex (the documents), pypdf (the text-layer check, which
            can be installed but broken: a container's system `cryptography` makes it
            panic in pyo3 until `pip3 install --upgrade cffi`), Node or Bun (the portal
            CLIs), and on a computer GitHub's command line and its sign-in
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


def https_host() -> str:
    """The host Python's own HTTPS is tried on: one curl tries too, not LinkedIn's."""
    urls = [u for _, u in hosts()]
    return next((u for u in urls if "linkedin" not in u), urls[0] if urls else "")


def https_check(url: str) -> tuple[str, str]:
    """(verdict, detail) for Python's own HTTPS (urllib) to one host: "ok" when a TLS reply
    came back verified, "certificates" when this Python could not check the certificate,
    "unknown" when the host was not reached at all (curl's line says why)."""
    import ssl
    import urllib.error
    import urllib.request
    local_path.trust_store()
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return "ok", f"HTTP {r.status}"
    except urllib.error.HTTPError as e:      # any status is a reply over verified TLS
        return "ok", f"HTTP {e.code}"
    except (urllib.error.URLError, ssl.SSLError, OSError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, ssl.SSLCertVerificationError) or \
                "CERTIFICATE_VERIFY_FAILED" in str(reason):
            fix = (f"`{FIX} python` gives the app a Python that reads the Mac's certificates"
                   if sys.platform == "darwin" else
                   "set SSL_CERT_FILE to this computer's certificate bundle")
            return "certificates", f"this Python cannot check certificates ({sys.executable}); {fix}"
        return "unknown", f"not reached ({str(reason)[:80]})"


def probe(url: str) -> tuple[str, str]:
    """(verdict, detail) for one URL, through whatever proxy the session uses."""
    if not shutil.which("curl"):
        return "unreachable", "curl is not installed"
    # os.devnull, not /dev/null: Windows' own curl.exe cannot open /dev/null, so every job
    # site was reported unreachable there (it is "nul" on Windows).
    p = subprocess.run(["curl", "-sS", "-o", os.devnull, "--max-time", "8",
                        "-w", "%{http_connect} %{http_code}", url],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
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
    one fix as numbered steps from the registry, and what happens meanwhile.

    It replaced "the network policy refused it (proxy 403); add the host under the cloud
    environment's Allowed domains", which a person new to all of it could not act on: they
    had never heard of an environment (2026-10-20). Full is recommended over a list of
    sites because a list needs a new entry for each new employer's board. Cut from 107 words
    to under 60 (2026-10-25): it said "done" twice, said it would "search again" when nothing
    had been searched, and explained the cloud before the fix."""
    import claude_surfaces
    names = [n for n in dict.fromkeys(names) if n]
    what = ", ".join(names[:3]) + (" and others" if len(names) > 3 else "")
    return "\n".join(
        [f"This chat can't reach job sites yet{' (' + what + ')' if what else ''}. To let it, once:"]
        + claude_surfaces.steps("cloud-internet")[1:]
        + ["I won't search before then: it would only find old jobs. Say \"done\" once it's "
           "changed."])


def blocked_notes() -> list[str]:
    """What Claude is told beside `blocked_say`, never the person: the steps' entry, once it
    is old enough to re-check (claude_surfaces.notes). Printed to stderr, apart from the
    words said word for word."""
    import claude_surfaces
    return claude_surfaces.notes("cloud-internet")


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


TOOLS = os.path.join(ROOT, "tools")
# What the tools themselves import: the repo's .venv first (local_path.use_venv), where
# env_check --fix puts the packages a system Python refuses.
VENV_FIRST = "import sys; sys.path.insert(0, sys.argv[1]); import local_path; local_path.use_venv(); "


def app_python() -> str:
    """The Python the app's commands run under here: the repo's .venv's where it starts
    (an app command started by another one runs itself again under it), else this one."""
    return local_path.venv_python() if local_path.venv_runs() else sys.executable


def module_state(name: str) -> bool:
    """Is a Python module importable here? Asked apart, like pypdf, so a broken one cannot crash this."""
    return subprocess.run([app_python(), "-c", VENV_FIRST + f"import {name}", TOOLS],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace").returncode == 0


def pypdf_state() -> str:
    """'ok', 'missing' or 'broken'. Run apart, because a pyo3 panic kills the
    interpreter rather than raising."""
    p = subprocess.run([app_python(), "-c", VENV_FIRST + "import pypdf; pypdf.PdfReader", TOOLS],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode == 0:
        return "ok"
    return "missing" if "No module named" in p.stderr else "broken"


# A cloud session sets CLAUDE_CODE_REMOTE. Its fixes are the environment's Setup
# script and network allowlist; on the person's own computer they are a one-time
# install and there is no network policy at all.
CLOUD = os.environ.get("CLAUDE_CODE_REMOTE", "").lower() == "true"


def _install(what: str) -> str:
    """What installs `what` where this session runs, in one plain phrase."""
    if CLOUD:
        return "./tools/setup_env.sh installs it for this session"
    return "`python3 tools/env_check.py --fix` installs it (no password)"


FIX = "python3 tools/env_check.py --fix"


LINUX_MANAGERS = (("apt-get", "sudo apt-get install -y {}"), ("dnf", "sudo dnf install -y {}"),
                  ("pacman", "sudo pacman -S --noconfirm {}"),
                  ("zypper", "sudo zypper install -y {}"))


def linux_install(package: str, have=None) -> str:
    """The one command that installs a system package on this Linux, by the package manager
    it has (Debian and Ubuntu, Fedora, Arch, openSUSE), apt-get where none is found."""
    have = have or shutil.which
    for tool, cmd in LINUX_MANAGERS:
        if have(tool):
            return cmd.format(package)
    return LINUX_MANAGERS[0][1].format(package)


def local_fixes(system=None, have=None, module=None, py_ok=None, pypdf=None,
                gh_signed_in=None, newer=None) -> list:
    """What this computer is missing, as [(what, the one command, whose)].

    The person's own computer, never a cloud session. Almost everything is one command
    Claude runs itself, `env_check.py --fix`, which installs into the person's own
    folders with no password, no Homebrew and no winget (tools/installs.py). `whose` is ""
    for those; "sign-in" where the person signs in themselves (GitHub); "dialog" where a
    window of their computer's own asks them to click (Apple's command line tools, on a
    Mac with no Git or Python); and "password" only for what Linux installs from the
    system (Git, Perl), which asks for it. A Python too old for the app is not one of
    those on Linux: uv installs a current one with no password (python_floor.linux_route).
    `newer` is whether a Mac still needs the current Python (installs.needs_python). Every
    argument is injectable so each machine can be tested from any other.
    """
    import python_floor
    here = system is None                    # this computer, not one a test describes
    system = system or sys.platform
    have = have or shutil.which
    module = module or module_state
    py_ok = python_floor.ok() if py_ok is None else py_ok
    pypdf = pypdf or pypdf_state()
    mac, win = system == "darwin", system.startswith("win")
    if newer is None:
        made = local_path.venv_version()
        newer = here and mac and sys.version_info[:2] < python_floor.CURRENT and not (
            made and made >= python_floor.CURRENT and local_path.venv_runs())
    out = []
    # Linux is the one place a missing Git needs the system's own package manager, and so
    # the person's password at a terminal: Claude's shell has no terminal for sudo. Which
    # manager is read from what the computer has, not assumed to be Ubuntu's. A Python too
    # old for the app is uv's, there and on a Mac with no password.
    if not py_ok:
        out.append(("Python 3.9 or newer",
                    "xcode-select --install" if mac else
                    "powershell -ExecutionPolicy Bypass -File tools/computer_setup.ps1" if win
                    else python_floor.linux_route(),
                    "dialog" if mac else ""))
    elif newer:
        want = python_floor.CURRENT
        out.append((f"Python {want[0]}.{want[1]} (this Mac's own is "
                    f"{sys.version_info[0]}.{sys.version_info[1]}, which no longer gets "
                    "security fixes)", f"{FIX} python", ""))
    if not have("git"):
        out.append(("Git", "xcode-select --install" if mac else f"{FIX} git" if win
                    else linux_install("git", have), "dialog" if mac else "" if win
                    else "yours"))
    if [m for m in ("pytest", "yaml") + (("tzdata",) if win else ()) if not module(m)] \
            or pypdf != "ok":
        out.append(("the Python packages", f"{FIX} packages", ""))
    if not (have("lualatex") and have("xelatex")):
        out.append(("LaTeX, to make the PDFs", f"{FIX} latex", ""))
    if not (have("node") or have("bun")):
        out.append(("Bun, for the job searches", f"{FIX} runtime", ""))
    # A chat on a computer has no GitHub tools of its own: `gh` is how its work
    # reaches GitHub, where the other chats and the brief read it.
    gh = not have("gh")
    if gh:
        out.append(("GitHub's command line, so your work reaches GitHub", f"{FIX} gh", ""))
    if gh or gh_signed_in is False or (gh_signed_in is None and not _gh_signed_in(have)):
        out.append(("GitHub sign-in for it", "gh auth login --web --git-protocol https",
                    "sign-in"))
    return out


def _gh_signed_in(have) -> bool:
    if not have("gh"):
        return False
    try:
        return subprocess.run(["gh", "auth", "status"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] in (["--help"], ["-h"]):
        print("usage: python3 tools/env_check.py [--fix [what ...] | --allowlist | --say | "
              "--https [url]]")
        return 0
    if argv[:1] == ["--fix"]:
        if CLOUD:
            # A cloud container is root and has apt: the one script, as its setup line runs.
            return subprocess.call(["bash", os.path.join(ROOT, "tools", "setup_env.sh")])
        import installs
        return installs.main(argv[1:] or ["all"])
    if argv[:1] == ["--allowlist"]:
        print("\n".join(allowlist()))
        return 0
    if argv[:1] == ["--https"]:
        url = argv[1] if argv[1:] else https_host()
        verdict, detail = https_check(url)
        print(f"Python {sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]} "
              f"HTTPS to {url}: {verdict}, {detail}")
        return 1 if verdict == "certificates" else 0
    if argv[:1] == ["--say"]:
        names = blocked_names()
        if names:
            print(blocked_say(names))
            for note in blocked_notes():
                print(note, file=sys.stderr)
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
                                 ("yaml", "pyyaml", "the skills check"),
                                 *((("tzdata", "tzdata", "time zones, which Windows lacks"),)
                                   if sys.platform == "win32" else ())):
        have = module_state(module)
        fix = (f"missing; pip3 install {package}" if CLOUD else "missing; " + _install(package))
        line(f"{package} ({why})", have, "" if have else fix)
    latex = [t for t in ("lualatex", "xelatex") if not shutil.which(t)]
    line("LaTeX (lualatex, xelatex)", not latex, "" if not latex else "missing; " + _install("latex"))
    state = pypdf_state()
    line("pypdf (reads the PDFs)", state == "ok",
         {"ok": "", "missing": "missing; " + _install("pypdf"),
          "broken": "installed but panics; pip3 install --upgrade cffi"}[state])
    run = "node" if shutil.which("node") else "bun" if shutil.which("bun") else ""
    line("Node or Bun (portal searches)", bool(run),
         run if run else "missing; " + _install("bun"))
    if not CLOUD:
        gh = bool(shutil.which("gh"))
        line("GitHub's command line (gh)", gh, "" if gh else "missing; " + _install("gh"))

    if https_host():
        verdict, detail = https_check(https_host())
        line("Python's own HTTPS (urllib)", verdict != "certificates", detail)

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
        for note in blocked_notes():
            print(note, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    if sys.argv[1:2] != ["--fix"]:
        # Report under the Python the app's commands run under (the repo's .venv), so what
        # it says is installed is what they import. --fix runs where it was started, so a
        # .venv that cannot start can still be made again.
        local_path.run_in_venv()
    sys.exit(main())
