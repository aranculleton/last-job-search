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
  hosts     the job boards the app calls, and every board the person has a
            portal for (the `url:` in its SKILL.md). A proxy that answers
            CONNECT with 403 or 407 is the environment's network policy: the
            host goes under Allowed domains. Any other failure is the host or
            DNS. A host that answers at all, even 401 or 404, is reachable.

Workday has no host to probe until a person has a board on it (every Workday
site is `<tenant>.<wdN>.myworkdayjobs.com`), so it is probed through the first
Workday board in profile/boards.py, and otherwise reported as not yet checkable.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

HOSTS = (
    ("LinkedIn", "https://www.linkedin.com"),
    ("freehire", "https://freehire.me"),
    ("Greenhouse", "https://boards-api.greenhouse.io"),
    ("Lever", "https://api.lever.co"),
    ("Ashby", "https://api.ashbyhq.com"),
)
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
              "blocked": f"the network policy refused it (proxy {connect}); add the host "
                         f"under the cloud environment's Allowed domains",
              "unreachable": (p.stderr.strip().splitlines() or [f"curl exit {p.returncode}"])[-1]
              }[verdict]
    return verdict, detail


def workday_url() -> str | None:
    """The first Workday board in the profile, as a URL, or None."""
    try:
        import ats_boards
        for kind, token, *_ in getattr(ats_boards, "BOARDS", {}).values():
            if kind == "workday":
                host = ats_boards.workday_board(token)
                if host:
                    return f"https://{host[0]}"
    except Exception:
        return None
    return None


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
        return {"latex": "install MiKTeX once (SETUP.md, Local machine)",
                "poppler": "choco install poppler"}[what]
    return "install it once (SETUP.md, Local machine)"


def main() -> int:
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
    for name, url in hosts():
        verdict, detail = probe(url)
        line(f"{name} ({url.split('//')[1]})", verdict == "reachable", detail)
    wd = workday_url()
    if wd:
        verdict, detail = probe(wd)
        line(f"Workday ({wd.split('//')[1]})", verdict == "reachable", detail)
    else:
        print(f"  {'Workday':28} --  no Workday board on file yet; checked once one is "
              f"added (python3 tools/ats_boards.py --probe)")
    print()
    print("all good" if not bad else f"{bad} problem(s) above")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
