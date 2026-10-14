# Setup

Two paths. Most sessions take the first.

- **[Fresh cloud container](#a-fresh-cloud-container)** is how this repo normally runs:
  an ephemeral container, cloned at session start, reclaimed at session end. Nothing is
  preinstalled beyond Python and the repo itself.
- **[Local machine](#b-local-machine)** is for working on the pipeline itself, where a
  persistent LaTeX install and a real browser are worth having.

This file is about the machine. Starting your own search is [START_HERE.md](START_HERE.md):
make a private copy with **Use this template**, then say "set me up" and `/setup` builds
your profile. In a copy that already has a `profile/`, `/setup` updates the part you ask
about and never overwrites the rest; see [Resetting](#resetting) before starting over.

---

## A. Fresh cloud container

```bash
apt-get install -y --no-install-recommends \
  texlive-luatex texlive-latex-extra texlive-xetex \
  texlive-fonts-recommended poppler-utils

pip3 install --upgrade cffi pytest pypdf

python3 -m pytest tests -q          # over 450 green before anything else
```

That is the whole of it. Three notes on why each piece is there:

**`texlive-fonts-recommended` is named explicitly** because `--no-install-recommends`
will not pull it, and hyperref's xetex driver probes its `pzdr` metrics: the cover letter
fails without it. **`texlive-fonts-extra` is deliberately not installed.** moderncv loads
`fontawesome5` and `academicons`, which apt ships only in that 1.7 GB package; the 1.5 MB
actually used is vendored in `texmf/` and found through `TEXMFHOME` (`texmf/README.md`).
That cuts the TeX download from about 760 MB to about 160 MB. This is the same package set
CI's Debian leg installs, and that leg is what proves the documents compile without it.
For a compile by hand, `export TEXMFHOME="$PWD/texmf"` from the repo root first, or run
`./tools/setup_env.sh` once, which links `~/texmf` to it.

**`cffi` is upgraded first** because `pypdf` needs a working one, and the system
`cryptography` package can be broken on a fresh container in a way that makes
`tools/verify_pdf.py` fail with a pyo3 panic rather than a clean ImportError. The panic
looks like a bug in the verifier and is not.

**The test suite runs before anything else** because a red suite in a fresh container
usually means a missing dependency, and finding that out now costs a minute, whereas
finding it out three hours in costs the session.

### Portal CLIs

Only needed if you are running `/scrape` or `run_round.py` against live portals.
`linkedin-search` and `freehire-search` are on by default; the four Danish ones ship off as
reference implementations. A person switches any of them in `profile/search.py` `PORTALS`;
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
The fallback is `/apply <pasted posting text>`, which needs no network at all, and
`run_round.py --from-scraped <earlier kept.json>`, which re-runs every free stage on a
scrape that already succeeded.

### Disk

Writable disk is a fixed per-session allowance, so `df` misleads: "Avail" at 0 with low
"Used" means the allowance is spent, not that the machine is broken. A single search
round writes about 55MB of intermediates, which is why `run_round.py` prunes itself. On
"no space left on device", delete build artifacts and stale round directories; deletes
still succeed while writes fail.

---

## B. Local machine

### Python

3.10 or newer. CI runs the suite on 3.10 and 3.13.

```bash
python3 --version
pip3 install pytest pypdf
```

### Bun

For the portal search CLIs. [bun.sh](https://bun.sh) has the installer; on macOS
`brew install oven-sh/bun/bun` works, and on Windows use the PowerShell one-liner from
their site.

### LaTeX

- **Linux:** `sudo apt install texlive-full`, or the explicit package set from the
  container section above if you want it lean.
- **macOS:** [MacTeX](https://tug.org/mactex/), or TinyTeX for a user-level install.
- **Windows:** [MiKTeX](https://miktex.org/download).

The resume compiles with **lualatex**. pdflatex often fails on modern MiKTeX installs
with `fontawesome5` font-expansion errors, and lualatex handles the same source cleanly.
The cover letter compiles with **xelatex**, because `cover.cls` requires `fontspec` for
its bundled Lato and Raleway.

#### Minimal TeX install (TinyTeX, BasicTeX)

Full distributions work out of the box. Minimal ones need the package set named:

```bash
tlmgr install \
  moderncv fontawesome5 fontawesome6 academicons import luatexbase pgf \
  titlesec textpos xltxtra xunicode cite realscripts needspace
```

For BasicTeX or MacTeX, put the TeX binary directory on `PATH` first, usually via
`/Library/TeX/texbin`.

#### Basic MiKTeX on Windows

Basic MiKTeX ships a minimal package set and, by default, pops a GUI prompt for each
missing package. That blocks any non-interactive terminal, Claude Code's Bash tool
included. Turn it into a silent auto-install:

```powershell
initexmf --admin --set-config-value=[MPM]AutoInstall=1
initexmf --set-config-value=[MPM]AutoInstall=1
```

The first line is for an all-users install and needs an elevated shell; the second covers
a per-user install. Running both is harmless. To avoid on-the-fly installs entirely,
pre-install the same package set with `mpm --install=<name>`, dropping `--admin` for a
per-user install. `mpm --find=<name>` resolves a name that does not match.

### Smoke test

```bash
export TEXMFHOME="$PWD/texmf"   # vendored icon fonts, texmf/README.md
cd cv && lualatex -interaction=nonstopmode -halt-on-error main_example.tex && cd ..
cd cover_letters && xelatex -interaction=nonstopmode -halt-on-error cover_example.tex && cd ..
python3 tools/verify_pdf.py cv/main_example.pdf --min-chars 100
```

These are the two files CI compiles, so if they build here they build there.

---

## ATS text extraction

The verification stack extracts the compiled resume's text layer and checks what a parser
actually sees: contact details present as literal text, sane reading order, no `(cid:)`
markers or replacement characters.

The default extractor is **pypdf** (`pip install pypdf`, BSD, no Poppler needed). Poppler
`pdftotext` is the fallback, and `tools/verify_batch.sh` uses it directly:

- macOS: `brew install poppler`
- Debian/Ubuntu: `apt install poppler-utils`
- Windows: `choco install poppler`

`pdftotext -layout` must also pass `-enc UTF-8`. If neither extractor is present the
check degrades to a visual keyword review with a warning, and everything else works.

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

**Portal CLI does nothing.** Check Bun is installed and the portal is enabled: the
`enabled:` key at the top of `.agents/skills/<name>/SKILL.md`. Four of the six ship
`enabled: false` on purpose.

**LaTeX cannot find `moderncv`.** The distribution is minimal; see the package list
above. On the resume specifically, confirm you are running lualatex and not pdflatex.

**Cover letter fonts fall back to the body font.** The class expects them at
`cover_letters/OpenFonts/fonts/`. If the directory is present, the usual cause is
`\lettercontent{}` wrapping an `itemize` block, which is a known trap documented in the
verification checklist in CLAUDE.md along with the pattern that avoids it.

**A stale `.claude/settings.local.json`.** Shared permissions live in
`.claude/settings.json`, which is scoped and guard-enforced. An older local file sits on
top of it and silently widens what is pre-approved. Delete it, or trim it to genuine
personal overrides.

---

## Upstream

This repo is a fork. `.github/workflows/upstream-watch.yml` runs weekly and writes a
rolling issue listing the upstream commits this fork lacks, sorted into worth-reviewing
versus probably-skip. `python3 tools/upstream_triage.py --remote upstream --branch master`
produces the same report locally, and `python3 tools/check_upstream_updates.py` reports
which methodology files an update would touch, by `framework_version` marker.

Port by hand. A clean cherry-pick is not a correct one: see
[CONTRIBUTING.md](CONTRIBUTING.md#upstream).
