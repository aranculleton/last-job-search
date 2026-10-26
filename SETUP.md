# Setup

Two paths. Most sessions take the first.

- **[Fresh cloud container](#a-fresh-cloud-container)** is how this repo normally runs:
  an ephemeral container, cloned at session start, reclaimed at session end. Nothing is
  preinstalled beyond Python and the repo itself.
- **[Local machine](#b-local-machine)** is for running the search on your own computer, or
  working on the pipeline itself, where a persistent LaTeX install is worth having.

This file is about the machine. Starting your own search is [START_HERE.md](START_HERE.md):
make a private copy with **Use this template**, then say "set me up" and `/setup` builds
your profile. In a copy that already has a `profile/`, `/setup` updates the part you ask
about and never overwrites the rest; see [Resetting](#resetting) before starting over.

---

## A. Fresh cloud container

Nobody using the app needs this section: the line START_HERE.md has you paste into the cloud
environment's setup script does all of it, and `./tools/setup_env.sh` repeats it in a session
if that was skipped. By hand, it is:

```bash
apt-get install -y --no-install-recommends \
  texlive-luatex texlive-latex-extra texlive-xetex \
  texlive-fonts-recommended poppler-utils

pip3 install --upgrade cffi
pip3 install -r requirements.txt

node --version || bun --version || python3 tools/installs.py runtime   # the job-board CLIs; Claude's cloud containers ship both

python3 -m pytest tests -q          # the app's own tests, for working on the app; a setup never waits on them
```

Three notes on why each piece is there:

**`texlive-fonts-recommended` is named explicitly** because `--no-install-recommends`
will not pull it, and hyperref's xetex driver probes its `pzdr` metrics: the cover letter
fails without it. **`texlive-fonts-extra` is deliberately not installed.** moderncv loads
`fontawesome5` and `academicons`, which apt ships only in that 1.7 GB package; the 1.5 MB
actually used is vendored in `texmf/` and found through `TEXMFHOME` (`texmf/README.md`).
That cuts the TeX download from about 760 MB to about 160 MB. This is the same package set
CI's Debian leg installs, and that leg is what proves the documents compile without it.
`tools/fit_to_page.py` sets `TEXMFHOME` for every compile it runs, so `File fontawesome5.sty
not found` means a compile ran without it: for a compile by hand,
`export TEXMFHOME="$PWD/texmf"` from the repo root first. Nothing
is linked into your home directory: each copy of the app (each worktree, if two chats run
at once) uses its own `texmf/`, and a `~/texmf` you already have is left alone.

**`cffi` is upgraded first** because `pypdf` needs a working one, and the system
`cryptography` package can be broken on a fresh container in a way that makes
`tools/verify_pdf.py` fail with a pyo3 panic rather than a clean ImportError. The panic
looks like a bug in the verifier and is not: `pip3 install --upgrade cffi` fixes it.

**The test suite runs before anything else** because a red suite in a fresh container
usually means a missing dependency, and finding that out now costs a minute, whereas
finding it out three hours in costs the session.

### Portal CLIs

Only needed if you are running `/scrape` or `run_round.py` against live portals.
`linkedin-search` and `freehire-search` are on by default and work in any country. Boards for
your own market are built for you by `/add-portal` (and offered by `/setup`), and every round
searches them. A person switches any portal in `profile/search.py` `PORTALS`;
`python3 tools/portals.py` prints what a round will search.

```bash
for tool in freehire-search linkedin-search; do
  (cd .agents/skills/$tool/cli && bun install)
done
```

Both have zero runtime dependencies and run under plain `bun`. `bun install` only pulls
TypeScript dev types, so it is optional for a run and required only for `bun run typecheck`.

### When a portal is unreachable

Egress in a cloud session goes through a policy proxy. If `/scrape` or `run_round.py`
cannot reach a portal, check for `connect_rejected` entries:

```bash
curl -sS "$HTTPS_PROXY/__agentproxy/status"
```

That is an environment policy denial, not a bug, and it is not something to route around.
The fix is the cloud chat's network access: START_HERE.md, step 3, sets it to Full, which
the person is told in plain words (`python3 tools/env_check.py --say`). To allow only the job
sites instead, choose Custom, keep the default package managers, and add what
`python3 tools/env_check.py --allowlist` prints: to start with `linkedin.com`,
`www.linkedin.com`, `freehire.me`, `boards-api.greenhouse.io`, `api.lever.co`,
`api.ashbyhq.com`, `*.myworkdayjobs.com`, and `api.openalex.org` for a field that publishes.
Each new employer board can need one more, so a custom list needs keeping up. Meanwhile the
fallback is `/apply <pasted posting text>`, which needs no network at all, and
`run_round.py --from-scraped <earlier kept.json>`, which re-runs every free stage on a
scrape that already succeeded (the earlier round must have run with `--keep-intermediates`,
or its `00_scrape/` is already deleted).

### Disk

Writable disk is a fixed per-session allowance, so `df` misleads: "Avail" at 0 with low
"Used" means the allowance is spent, not that the machine is broken. A single search
round writes about 55MB of intermediates, which is why `run_round.py` prunes itself. On
"no space left on device", delete build artifacts and stale round directories; deletes
still succeed while writes fail.

---

## B. Local machine

On a person's own computer Claude installs everything itself, into the person's own
folders, with no password, no Homebrew and no winget:

```bash
python3 tools/env_check.py --fix    # what is missing, one plain line each
python3 tools/env_check.py          # what is here
```

A computer with nothing set up yet, not even this copy, starts from
[COMPUTER.md](COMPUTER.md): Git, GitHub's command line and the clone come first, then this.
What `--fix` does for each tool, and how to do it by hand (`tools/installs.py` has the code):

### Python

3.9 or newer starts every command: a Mac's own `python3` (3.9.6, from Apple's command line
tools, which a first `git` command offers to install) does. 3.9 has had no security fixes
since October 2025, so on a Mac `--fix` (and `--fix python`) also installs Python 3.13 into
your own folders, with no password and no Homebrew: uv by its own installer
(`curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh`, into
`~/.local/bin`, https://docs.astral.sh/uv/getting-started/installation/), then
`uv python install 3.13` (into `~/.local/share/uv/python`,
https://docs.astral.sh/uv/reference/storage/), and the `.venv` below is made with it.
Apple's `python3` is left as it was: no `--default`, no new command on your PATH, no shell
startup file changed. An app command started by `python3` runs itself again under the
`.venv`'s Python when that is another version (`tools/local_path.py`, `run_in_venv()`), so
nothing is typed differently. A Linux whose Python is older than 3.9 gets the same route
(`python3 tools/python_floor.py` prints the one command); any other Linux keeps its own.
Python's own HTTPS (`python3 tools/env_check.py --https`) finds the system's certificates:
a Python whose OpenSSL has none where it looks (python.org's for a Mac, before its
"Install Certificates" step, https://docs.python.org/3/using/mac.html) is pointed at
`/etc/ssl/cert.pem` through `SSL_CERT_FILE`; uv's Python already looks there.
CI runs the suite on 3.9 and 3.13, so nothing in the app may need a newer one. On
Windows, the Python install manager from
python.org (`tools/computer_setup.ps1` adds it with `Add-AppxPackage`, as its page says)
gives `python`, `py` and `python3`; where only `python` works, `--fix python` adds a
`python3` command.

The packages (`requirements.txt`) go in the repo's own `.venv`, made with that Python on a
Mac and with the computer's own Python elsewhere:

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
```

Every tool reads that `.venv` itself (`tools/local_path.py`, `use_venv()`), so the
commands stay `python3 tools/...`. Debian and Ubuntu leave pip out of venv (the
`python3-venv` package, which needs the password): `--fix` then makes it with
`--without-pip` and installs pip with PyPA's `get-pip.py`. `pip install --user` is never
used: Debian, Ubuntu and Homebrew's Python refuse it ("externally managed", PEP 668).
`./tools/ci_local.sh` uses an active virtual environment, or `.venv`, before the system
`python3`, and says which it used on its first line.

### Node or Bun

For the portal search CLIs: a portal's committed build runs under Node, or under Bun
where there is no Node (`tools/portals.py` `runtime()`). `--fix` installs Bun from its
own release into `~/.bun/bin`, unpacked by Python (no `unzip`, no password).

### LaTeX

TinyTeX ([yihui.org/tinytex](https://yihui.org/tinytex/)), a TeX Live in one folder of
the person's own: `~/Library/TinyTeX` on a Mac, `~/.TinyTeX` on Linux, `%APPDATA%\TinyTeX`
on Windows (`%ProgramData%\TinyTeX` when that path has a space or a letter outside ASCII).
`--fix` runs its official installer, then `tlmgr update --self` (a fresh TinyTeX refuses
any install before it), the package set below, and a test compile of both example
documents. By hand on a Mac or Linux:

```bash
curl -fsSL https://tinytex.yihui.org/install-bin-unix.sh | sh -s "" --no-path
```

The empty first word matters: the script reads its first word as a folder to keep the
download in, so the documented `sh -s --no-path` stops with an error. `--no-path` keeps it
from asking for the password to change the system's PATH; the app finds TinyTeX itself
(`tools/local_path.py`). On Linux it needs Perl and xz, which most systems have.

A LaTeX that is already there is kept when it compiles both templates: MacTeX, MiKTeX,
TeX Live from apt. One that cannot compile them and cannot be changed without the
password gets TinyTeX beside it, found first.

The resume compiles with **lualatex**. pdflatex often fails on modern MiKTeX installs
with `fontawesome5` font-expansion errors, and lualatex handles the same source cleanly.
The cover letter compiles with **xelatex**, because `cover.cls` requires `fontspec` for
its bundled Lato and Raleway.

#### The package set

```bash
tlmgr install \
  moderncv fontawesome5 fontawesome6 academicons import luatexbase pgf \
  titlesec textpos xltxtra xunicode cite realscripts needspace
```

(`tools/installs.py` `TEX_PACKAGES`, the same list.) For BasicTeX or MacTeX, put the TeX
binary directory on `PATH` first, usually via `/Library/TeX/texbin`.

#### MiKTeX on Windows

MiKTeX asks before installing each missing package, and with nobody to answer, a compile
waits for ever. `--fix` turns that into a silent install, the per-user setting MiKTeX's
own [Just enough TeX](https://miktex.org/kb/just-enough-tex) gives, which needs no
administrator:

```powershell
initexmf --set-config-value=[MPM]AutoInstall=yes
```

Every LaTeX run the app makes also stops after five minutes and says why
(`tools/fit_to_page.py`), so a prompt nobody sees cannot hold a chat.

### GitHub's command line

`--fix` installs `gh` from its release archive into `~/.local/bin` (Mac, Linux) or
`%LOCALAPPDATA%\Programs\gh\bin` (Windows). Signing in is the person's, once: Claude
starts `gh auth login --web --git-protocol https`, and they copy the code it shows into
the page GitHub opens.

### Smoke test

```bash
export TEXMFHOME="$PWD/texmf"   # vendored icon fonts, texmf/README.md
cd cv && lualatex -interaction=nonstopmode -halt-on-error main_example.tex && cd ..
cd cover_letters && xelatex -interaction=nonstopmode -halt-on-error cover_example.tex && cd ..
python3 tools/verify_pdf.py cv/main_example.pdf --min-chars 100
```

These are the two files CI compiles, so if they build here they build there.

### Proof on every computer

`.github/workflows/platforms.yml` runs `tools/platform_check.py` on Linux, a Mac and
Windows after taking away Homebrew, MacTeX, winget and sudo: the install route from
scratch, the documents in three colours, an offline round, an interview pack, a
networking day and the suite, plus Windows PowerShell 5.1 running
`tools/computer_setup.ps1` and a computer chat on Windows with no `python3`.

---

## ATS text extraction

The verification stack extracts the compiled resume's text layer and checks what a parser
actually sees: contact details present as literal text, sane reading order, no `(cid:)`
markers or replacement characters.

Every PDF is read with **pypdf** (`requirements.txt`, BSD): the page count, the text and
the fonts (`tools/pdftext.py`), for `fit_to_page.py`, `verify_batch` and `verify_pdf.py`
alike, so no system package is needed. Only pypdf sees a text layer whose words run
together; Poppler's `pdftotext` infers the spaces. Poppler is still used where it is
installed and pypdf cannot run at all (a broken `cryptography` makes it panic; see
Troubleshooting), and then the batch says the spacing check was skipped, never passed.

---

## Salary benchmarking

`salary_lookup.py` reads `salary_data.json`, which is licensed third-party data and is
deliberately not committed. "salary_data.json not found" is the expected state, and the
workflow skips the step. `tools/convert_salary_excel.py` converts a spreadsheet into the
JSON shape if you have one. Details in
[`tools/README_SALARY_TOOL.md`](tools/README_SALARY_TOOL.md).

This matters less than it sounds: most postings omit salary, and one with no stated range
is not penalised in scoring.

---

## Research papers (OpenAlex)

Only for a field whose people publish, where `/setup` sets `OPENALEX = True` in
`profile/networking.py`. `tools/network/openalex.py` reads a free key from openalex.org out of
the environment variable `OPENALEX_API_KEY` and never writes it down; without one, a cloud
container's shared address has usually spent the keyless daily allowance. In a cloud
environment, put it in the environment's variables, which anyone who uses that environment
can read, or keep it out of sight as a network secret for `api.openalex.org` (Bearer), where
your plan offers those. On your own computer, export it in your shell's profile.

---

## Resetting

`/reset` removes your profile, your search's state or your documents folder, after you
confirm. `/setup` builds a profile again by interview, from a `documents/` folder, or from
a pasted resume.

Neither is a routine operation. `profile/01-candidate-profile.md` is the
source of truth for every fact that reaches an employer, it takes several sessions of
`/expand` to build, and it holds more than any one resume shows on purpose: per-role
"additional detail available for tailoring" blocks and a reserve experience section that
the bullet allocator draws on. Overwriting it loses the tailoring surface, not just the
summary.

---

## Troubleshooting

**`tools/verify_pdf.py` panics instead of erroring.** A broken system `cryptography`
package under `pypdf`. `pip3 install --upgrade cffi`.

**Portal CLI does nothing.** Check Node or Bun is here (`python3 tools/env_check.py`) and that the portal is
on: `python3 tools/portals.py` prints what the next round searches. The app's two portals are
switched in `profile/search.py` `PORTALS`, never in their `SKILL.md`, which a sync puts back.

**LaTeX cannot find `moderncv`.** The distribution is minimal; see the package list
above. On the resume specifically, confirm you are running lualatex and not pdflatex.

**Cover letter fonts fall back to the body font.** The class expects them at
`cover_letters/OpenFonts/fonts/`. If the directory is present, the usual cause is
`\lettercontent{}` wrapping an `itemize` block, which is a known trap documented in the
verification checklist (`.claude/skills/job-application-assistant/verification-checklist.md`)
along with the pattern that avoids it.

**A stale `.claude/settings.local.json`.** Shared permissions live in
`.claude/settings.json`, which is scoped and guard-enforced. An older local file sits on
top of it and silently widens what is pre-approved. Delete it, or trim it to genuine
personal overrides.

---

## Upstream

For the app's maintainer only: [MAINTAINING.md](MAINTAINING.md#upstream).
