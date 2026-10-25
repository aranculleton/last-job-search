#!/usr/bin/env bash
# Everything a fresh cloud container needs, in one idempotent command.
#
#     ./tools/setup_env.sh           LaTeX, Bun and the Python side, in a cloud container
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
# MacTeX's and Bun's own directories, which a chat's non-login shell does not have.
# shellcheck source=tools/local_path.sh
. tools/local_path.sh

# A cloud container (Claude's, or any other run as root with apt) is set up here. A
# person's own computer is not: nothing here asks for a password, uses Homebrew or
# winget, or runs sudo there. `python3 tools/env_check.py --fix` installs what it lacks
# into the person's own folders instead (tools/installs.py), and this says so.
CONTAINER=0
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || { [ "$(id -u)" = 0 ] && have apt-get; }; then
  CONTAINER=1
fi
if [ "$CONTAINER" = 0 ]; then
  echo "setup_env: this is your own computer, so nothing is installed from here."
  echo "setup_env: \`python3 tools/env_check.py --fix\` installs what is missing, into your own folders, with no password."
fi

if [ "$PY_ONLY" = 0 ] && [ "$CONTAINER" = 1 ]; then
  if have lualatex && have xelatex; then
    echo "setup_env: LaTeX already present"
  elif have apt-get; then
    echo "setup_env: installing LaTeX (a few minutes, once per container)"
    apt-get update -qq >/dev/null 2>&1 || true
    # poppler-utils stays in the set: pdftotext is the text check's second reader where
    # pypdf cannot run, and the line pasted into a cloud environment's setup names it.
    if ! out=$(apt-get install -y --no-install-recommends \
        texlive-luatex texlive-latex-extra texlive-xetex \
        texlive-fonts-recommended poppler-utils 2>&1); then
      echo "setup_env: apt-get install failed:"
      printf '%s\n' "$out" | tail -3 | sed 's/^/  /'
    fi
  fi
fi
if [ "$PY_ONLY" = 0 ]; then
  # texlive-fonts-extra is 1.7 GB and the resume used 1.5 MB of it, the two
  # icon packages moderncv loads. They are vendored in texmf/ instead
  # (texmf/README.md), and every compile the app runs sets TEXMFHOME to this
  # copy's own texmf/ in its own environment (fit_to_page.py, ci_local.sh, CI).
  # Nothing in the home directory is created, changed or removed. A ~/texmf link
  # broke when the repo moved, and then, with two local chats in two worktrees,
  # each run re-pointed the one link at its own copy and took it from the other.
  # A ~/texmf that is already there is the person's, and is left exactly as it is.
  echo "setup_env: the resume's icon fonts come from this repo's texmf/, through TEXMFHOME, which every compile the app runs sets itself; ~/texmf is not used or changed"
  if [ -e "$HOME/texmf" ] || [ -L "$HOME/texmf" ]; then
    echo "setup_env: ~/texmf exists and is left as it is; no compile the app runs reads it"
  fi
  # Node or Bun runs the job-board CLIs (.agents/skills/*/cli, tools/portals.py
  # runtime()). Claude's cloud containers ship both; where neither is here, Bun's own
  # release, unpacked by Python (tools/installs.py): no unzip, no password.
  BUN_BIN="${BUN_INSTALL:-$HOME/.bun}/bin"
  [ -x "$BUN_BIN/bun" ] && export PATH="$BUN_BIN:$PATH"
  if ! have node && ! have bun && [ "$CONTAINER" = 1 ]; then
    echo "setup_env: installing Bun"
    python3 tools/installs.py runtime | sed 's/^/setup_env: /'
    export PATH="$BUN_BIN:$PATH"
  fi
fi

# One package at a time, and only what is missing. A single `pip install
# --upgrade a b c` aborts on the first package it cannot touch, and on this
# image PyYAML belongs to Debian ("Cannot uninstall PyYAML, RECORD file not
# found"), which took openpyxl down with it. cffi is the one package upgraded
# even when present, for the pyo3 panic described above.
if [ "$CONTAINER" = 1 ]; then
  pip3 install --quiet --upgrade cffi >/dev/null 2>&1 || true
  for pair in pytest:pytest pypdf:pypdf yaml:pyyaml openpyxl:openpyxl; do
    mod="${pair%%:*}"; pkg="${pair##*:}"
    python3 -c "import $mod" >/dev/null 2>&1 && continue
    echo "setup_env: installing $pkg"
    pip3 install --quiet "$pkg" >/dev/null 2>&1 || echo "setup_env: pip could not install $pkg"
  done
  python3 -m ruff --version >/dev/null 2>&1 || pip3 install --quiet ruff >/dev/null 2>&1 || true
fi

missing=""
if [ "$PY_ONLY" = 0 ]; then
  for t in lualatex xelatex; do have "$t" || missing="$missing $t"; done
  have node || have bun || missing="$missing node-or-bun"
fi
python3 -c "import sys; sys.path.insert(0, 'tools'); import local_path; local_path.use_venv(); import pytest, pypdf, yaml, openpyxl" >/dev/null 2>&1 || missing="$missing python-packages"
if [ "$CONTAINER" = 1 ]; then
  python3 -m ruff --version >/dev/null 2>&1 || missing="$missing ruff"
fi

if [ -n "$missing" ]; then
  echo "setup_env: still missing:$missing"
  [ "$CONTAINER" = 0 ] && echo "setup_env: \`python3 tools/env_check.py --fix\` installs them"
  exit 1
fi
echo "setup_env: ready"
