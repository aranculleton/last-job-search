#!/usr/bin/env bash
# Everything a fresh cloud container needs, in one idempotent command.
#
#     ./tools/setup_env.sh           LaTeX, Poppler, Bun and the Python side
#     ./tools/setup_env.sh --python  the Python side only (seconds, no apt)
#
# ## Why this exists
#
# Every session starts in a new container, and every one used to spend its
# first few minutes and a handful of model turns rediscovering the same four
# commands from CLAUDE.md, SETUP.md and RUNBOOK.md, which listed them three
# slightly different ways. The scheduled routines (daily follow-ups, the
# twice-weekly round) start the same way, so the cost repeated every weekday.
#
# The cheapest fix is not this script: it is the environment's own setup
# script, which runs before a session starts and is cached. Paste the one line
# below into the cloud environment's setup script (where it is, at the time of
# writing: python3 tools/claude_surfaces.py say cloud-environment) and this
# script becomes a no-op check:
#
#     apt-get update -qq && apt-get install -y --no-install-recommends texlive-luatex texlive-latex-extra texlive-xetex texlive-fonts-recommended poppler-utils && pip3 install --upgrade cffi && pip3 install pytest pypdf pyyaml openpyxl ruff
#
# It is deliberately NOT a SessionStart hook. tools/security_guards.py keeps
# the hook allowlist empty because a hook runs on every fork with no prompt,
# which is the vector the August 2026 Shai-Hulud wave used. A script a session
# chooses to run keeps that guard intact.
#
# `cffi` goes first because the system `cryptography` can be broken on a fresh
# container, which makes pypdf panic in pyo3 instead of raising ImportError.
# See SETUP.md.
#
# Exit 0 when everything is present afterwards, 1 when something is still
# missing, and it says which.

set -uo pipefail
cd "$(dirname "$0")/.."

PY_ONLY=0
[ "${1:-}" = "--python" ] && PY_ONLY=1

have() { command -v "$1" >/dev/null 2>&1; }

if [ "$PY_ONLY" = 0 ]; then
  if have lualatex && have xelatex && have pdftotext; then
    echo "setup_env: LaTeX and Poppler already present"
  elif have apt-get; then
    echo "setup_env: installing LaTeX and Poppler (a few minutes, once per container)"
    SUDO=""
    [ "$(id -u)" != 0 ] && have sudo && SUDO="sudo"
    $SUDO apt-get update -qq >/dev/null 2>&1 || true
    $SUDO apt-get install -y --no-install-recommends \
      texlive-luatex texlive-latex-extra texlive-xetex \
      texlive-fonts-recommended poppler-utils >/dev/null 2>&1 \
      || echo "setup_env: apt-get install failed; see SETUP.md"
  elif have brew; then
    # macOS: Poppler is small and installs unattended; TeX is a one-time install of
    # its own, too large to start without saying so.
    have pdftotext || brew install poppler >/dev/null 2>&1 \
      || echo "setup_env: brew install poppler failed; see SETUP.md"
    if ! { have lualatex && have xelatex; }; then
      echo "setup_env: TeX is not installed. Once, on this Mac:"
      echo "  brew install --cask mactex-no-gui && eval \"\$(/usr/libexec/path_helper)\""
    fi
  else
    echo "setup_env: no apt-get or brew here; install TeX Live and Poppler by hand (SETUP.md)"
  fi
  # texlive-fonts-extra is 1.7 GB and the resume used 1.5 MB of it, the two
  # icon packages moderncv loads. They are vendored in texmf/ instead
  # (texmf/README.md). fit_to_page.py points TEXMFHOME at it itself; the link
  # makes a compile by hand work too, since ~/texmf is kpathsea's default.
  if [ ! -e "$HOME/texmf" ]; then
    ln -s "$PWD/texmf" "$HOME/texmf" && echo "setup_env: linked ~/texmf to the repo's icon packages"
  elif [ "$(readlink -f "$HOME/texmf")" != "$(readlink -f "$PWD/texmf")" ]; then
    echo "setup_env: ~/texmf exists and is not the repo's; export TEXMFHOME=\"$PWD/texmf\" for hand compiles"
  fi
  # Bun runs the job-board CLIs (.agents/skills/*/cli). Claude's cloud containers
  # usually ship it; elsewhere both installs are per-user and ask for no password:
  # Homebrew's tap on a Mac that has brew, otherwise the official script, into
  # $BUN_INSTALL (~/.bun unless set), and adds that to the shell's profile where it can.
  BUN_BIN="${BUN_INSTALL:-$HOME/.bun}/bin"
  [ -x "$BUN_BIN/bun" ] && export PATH="$BUN_BIN:$PATH"
  if have bun; then
    :
  elif [ "$(uname -s)" = Darwin ] && have brew; then
    echo "setup_env: installing Bun"
    brew install oven-sh/bun/bun >/dev/null 2>&1 \
      || echo "setup_env: brew install oven-sh/bun/bun failed; see SETUP.md"
  elif have curl; then
    echo "setup_env: installing Bun"
    curl -fsSL https://bun.sh/install | bash >/dev/null 2>&1 \
      || echo "setup_env: the Bun installer failed; see SETUP.md"
    export PATH="$BUN_BIN:$PATH"
  else
    echo "setup_env: no curl here; install Bun by hand (SETUP.md)"
  fi
fi

# One package at a time, and only what is missing. A single `pip install
# --upgrade a b c` aborts on the first package it cannot touch, and on this
# image PyYAML belongs to Debian ("Cannot uninstall PyYAML, RECORD file not
# found"), which took openpyxl down with it. cffi is the one package upgraded
# even when present, for the pyo3 panic described above.
pip3 install --quiet --upgrade cffi >/dev/null 2>&1 || true
for pair in pytest:pytest pypdf:pypdf yaml:pyyaml openpyxl:openpyxl; do
  mod="${pair%%:*}"; pkg="${pair##*:}"
  python3 -c "import $mod" >/dev/null 2>&1 && continue
  echo "setup_env: installing $pkg"
  pip3 install --quiet "$pkg" >/dev/null 2>&1 || echo "setup_env: pip could not install $pkg"
done
python3 -m ruff --version >/dev/null 2>&1 || pip3 install --quiet ruff >/dev/null 2>&1 || true

missing=""
if [ "$PY_ONLY" = 0 ]; then
  for t in lualatex xelatex pdftotext bun; do have "$t" || missing="$missing $t"; done
fi
python3 -c "import pytest, pypdf, yaml, openpyxl" >/dev/null 2>&1 || missing="$missing python-packages"
python3 -m ruff --version >/dev/null 2>&1 || missing="$missing ruff"

if [ -n "$missing" ]; then
  echo "setup_env: still missing:$missing"
  exit 1
fi
echo "setup_env: ready"
