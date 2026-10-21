#!/usr/bin/env bash
# Every check CI runs, run here, so a capped Actions allowance cannot stop the
# search.
#
# ## Why this exists
#
# CLAUDE.md's rule is that master is the trunk and nothing reaches it without
# CI green. When the account hits its 2,000 monthly Actions minutes, that rule
# becomes a deadlock: no CI, therefore no green, therefore nothing lands on
# master, therefore every other chat starts from stale work.
#
# The rule is right and the dependency on GitHub was never the point of it.
# Every check in .github/workflows/ci.yml is a script in this repo; the runner
# only provides the machine. So it runs here, in under two minutes, and a
# clean run is the same evidence.
#
# CI's second Python leg runs the floor, 3.9 (a Mac's own python3): a bare
# `import tomllib` once passed locally and failed there. That leg runs here too,
# the way CI runs it, on the system python3.9 or one uv fetches, and is reported
# SKIP only where neither exists.
#
# On a private repo this is CI: .github/workflows/ci.yml runs only on a public
# repo (the app, whose minutes are free) or on a manual dispatch. What this cannot be is a second machine; the app's own CI is that,
# for every change made there.
#
#     ./tools/ci_local.sh            everything available
#     ./tools/ci_local.sh --quick    skip the LaTeX compile
#
# Exit 0 clean, 1 a real failure. Optional checks whose tooling is absent are
# reported as SKIP and never silently pass.

set -uo pipefail
cd "$(dirname "$0")/.."
# MacTeX's and Bun's own directories, which a chat's non-login shell does not have.
# shellcheck source=tools/local_path.sh
. tools/local_path.sh

# Which Python: the one the person set up for this repo when there is one (an
# active virtual environment, or .venv here), else python3. A Mac's own python3 is
# 3.9.6 and lacked PyYAML, so the first run said FAIL for a missing package while
# the person's working 3.10 sat in a venv the script never used. Said first.
PY="python3"
if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
  PY="$VIRTUAL_ENV/bin/python"
elif [ -x .venv/bin/python ]; then
  PY=".venv/bin/python"
fi

QUICK=0
[ "${1:-}" = "--quick" ] && QUICK=1

PASS=0; FAIL=0; SKIP=0
failed_names=""

run() {                       # run <name> <command...>
  local name="$1"; shift
  printf '  %-42s' "$name"
  if out=$("$@" 2>&1); then
    printf 'PASS\n'; PASS=$((PASS + 1))
  else
    printf 'FAIL\n'; FAIL=$((FAIL + 1)); failed_names="$failed_names\n    - $name"
    printf '%s\n' "$out" | tail -25 | sed 's/^/      /'
  fi
}

skip() {
  printf '  %-42s SKIP  (%s)\n' "$1" "$2"; SKIP=$((SKIP + 1))
}

# A check whose tooling is absent is not a failure, and the header above has
# promised SKIP for that since this file was written. It did not do it: `run`
# cannot tell "ruff found bugs" from "ruff is not installed", because both are a
# non-zero exit. With ruff missing from a fresh container the summary said
# "Not green. Do not push to master." with nothing wrong in the code. That is the worst possible failure for the one script standing in for CI:
# it either blocks a correct push or teaches the reader to ignore a red line.
run_py_module() {             # run_py_module <module> <name> <command...>
  local mod="$1" name="$2"; shift 2
  if ! "$PY" -c "import $mod" >/dev/null 2>&1; then
    skip "$name" "$PY -m $mod is not installed here"
    return
  fi
  run "$name" "$@"
}

echo
echo "ci_local: the checks .github/workflows/ci.yml runs"
echo "  python: $("$PY" -c 'import sys; print(sys.executable, "%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || echo "$PY: not found")"
if ! "$PY" -c 'import sys; sys.path.insert(0, "tools"); import python_floor; raise SystemExit(0 if python_floor.ok() else 1)' 2>/dev/null; then
  echo "  this Python is older than the app supports: $("$PY" -c 'import sys; sys.path.insert(0, "tools"); import python_floor; print(python_floor.how_to_install())' 2>/dev/null)"
fi
missing_mods=""
for pair in yaml:pyyaml pytest:pytest pypdf:pypdf; do
  "$PY" -c "import ${pair%%:*}" >/dev/null 2>&1 || missing_mods="$missing_mods ${pair##*:}"
done
if [ -n "$missing_mods" ]; then
  echo "  missing for this Python:$missing_mods ($PY -m pip install --user$missing_mods;"
  echo "  the checks that need them say SKIP or FAIL below for that reason, not the code's)"
fi
echo

echo "lint"
run "skills, commands and settings" "$PY" tools/lint_skills.py
run_py_module ruff "ruff (bugs only, see .ruff.toml)" \
    "$PY" -m ruff check --no-cache tools/ templates/ tests/
# The scoring baseline is a person's own (their screened postings, in
# profile/tests/fixtures), so the app has none to check, and that is not a skip.
if [ -f profile/tests/fixtures/score_baseline.json ]; then
  run "scoring baseline" "$PY" tools/score_eval.py
else
  printf '  %-42s n/a   (a person'"'"'s own, in profile/tests/fixtures)\n' "scoring baseline"
fi
run "framework version guard" "$PY" tools/check_framework_version.py
# A person's scheduled tasks: a missing prompt file, a mistyped id or a cron
# with no CRON_TZ fails here rather than at seven in the morning. The app's
# own tests check the example's registry.
if [ -f profile/routines.json ]; then
  run "scheduled-task registry" "$PY" tools/routines.py check profile/routines.json
else
  printf '  %-42s n/a   (a person'"'"'s own, in profile/routines.json)\n' "scheduled-task registry"
fi

echo
echo "security"
run "permissions, gitignore, manifests" "$PY" tools/security_guards.py
# The leak scan. In the app it reads the tree itself; in a person's repo it
# builds the app's tree from HEAD and scans that with the person's own
# denylist, so their data reaching an app-owned file fails here, long before
# anything could carry it to the app. Commit first: it reads HEAD.
if [ -f profile/person.json ]; then
  LEAK_OUT="$(mktemp -d)"
  run "leak scan (app tree built from HEAD)" "$PY" tools/build_app.py "$LEAK_OUT/app"
  rm -rf "$LEAK_OUT"
else
  run "leak scan (what git would commit)" "$PY" tools/leak_scan.py . --git
  # A stranger from a real search is on no denylist: a full name the app has never
  # carried, in what this branch adds, is reported (tools/name_guard.py).
  if git rev-parse -q --verify origin/master >/dev/null; then
    run "new names are invented ones" "$PY" tools/name_guard.py diff origin/master
  else
    skip "new names are invented ones" "no origin/master to compare with"
  fi
fi

echo
echo "tests"
run_py_module pytest "pytest (the app's suite, on the example person)" "$PY" -m pytest tests -q
# The person's own suite, against their profile, in its own process: the tools
# read the profile once at import, so the two suites cannot share one.
if [ -d profile/tests ]; then
  before=$FAIL
  # No compiled copies in profile/tests/__pycache__ for a forced add to commit.
  PYTHONDONTWRITEBYTECODE=1 run_py_module pytest "pytest (profile/tests, on this person)" \
    "$PY" -m pytest profile/tests -q
  # A failure here is often an update that changed or removed what the test pinned: say
  # which, and what to do, rather than leave a list of names to guess from.
  if [ "$FAIL" -gt "$before" ]; then
    "$PY" tools/sync_app.py --own-tests 2>&1 | sed 's/^/      /'
  fi
  "$PY" tools/sync_app.py --own-test-risks 2>/dev/null | sed 's/^/  /'
fi

echo
echo "python floor"
# CI's python-floor job, reproduced: a fresh environment on the oldest Python the
# app supports (tools/python_floor.py: 3.9, a Mac's own python3), holding pytest
# and nothing else, so an import that only the main environment happens to have is
# caught as well as syntax or a keyword newer than the floor. zip(strict=), a 3.10
# keyword, crashed the merge driver and the message checks on a Mac's 3.9.6 before
# this leg moved down to 3.9. uv fetches a standalone 3.9 in seconds where the
# system has none, so a private repo never needs a billed minute for it.
FLOOR_VERSION=3.9
FLOOR_NAME="tests on Python $FLOOR_VERSION (CI's floor leg)"
FLOOR_PY="$(command -v python$FLOOR_VERSION || true)"
if [ -z "$FLOOR_PY" ] && command -v uv >/dev/null 2>&1; then
  FLOOR_PY="$(uv python find $FLOOR_VERSION 2>/dev/null || true)"
  if [ -z "$FLOOR_PY" ]; then
    uv python install $FLOOR_VERSION >/dev/null 2>&1 || true
    FLOOR_PY="$(uv python find $FLOOR_VERSION 2>/dev/null || true)"
  fi
fi
if [ -z "$FLOOR_PY" ]; then
  skip "$FLOOR_NAME" "no python$FLOOR_VERSION here, and no uv to fetch one"
else
  FLOOR_ENV="${TMPDIR:-/tmp}/ci_local_py${FLOOR_VERSION/./}"
  if ! "$FLOOR_ENV/bin/python" -c "import pytest" >/dev/null 2>&1; then
    rm -rf "$FLOOR_ENV"
    "$FLOOR_PY" -m venv "$FLOOR_ENV" >/dev/null 2>&1 \
      && "$FLOOR_ENV/bin/pip" install -q pytest >/dev/null 2>&1
  fi
  if "$FLOOR_ENV/bin/python" -c "import pytest" >/dev/null 2>&1; then
    run "$FLOOR_NAME" "$FLOOR_ENV/bin/python" -m pytest tests -q -p no:cacheprovider
    if [ -d profile/tests ]; then
      PYTHONDONTWRITEBYTECODE=1 run "$FLOOR_NAME, profile/tests" "$FLOOR_ENV/bin/python" \
        -m pytest profile/tests -q -p no:cacheprovider
    fi
  else
    skip "$FLOOR_NAME" "could not build a $FLOOR_VERSION venv with pytest (no venv module or no network)"
  fi
fi

echo
echo "example templates"
# The same two guards the workflow runs, and they point opposite ways: an
# example that has gained real data, and a real profile that has been reverted
# to placeholders by an accidental /setup.
run "examples keep their placeholders" bash -c '
  fail=0
  check() { grep -q "$2" "$1" || { echo "missing placeholder $2 in $1"; fail=1; }; }
  check cv/main_example.tex "\\\\name{\[First\]}{\[Last\]}"
  check cv/main_example.tex "\\\\email{\[your\.email@example\.com\]}"
  check cover_letters/cover_example.tex "\[YOUR NAME\]"
  check cover_letters/cover_example.tex "Dear \[Hiring Manager / Team\]"
  exit $fail'
run "the real profile is not a template" bash -c '
  fail=0
  for f in profile/CLAUDE.md profile/01-candidate-profile.md; do
    [ -f "$f" ] || continue
    if grep -q "\[YOUR_NAME\]\|\[YOUR_EMAIL\]\|\[YOUR_PRIMARY_SKILLS\]" "$f"; then
      echo "$f reverted to template placeholders: the populated profile is lost"
      fail=1
    fi
  done
  exit $fail'

echo
echo "portal CLIs"
if command -v bun >/dev/null 2>&1; then
  for d in .agents/skills/*/cli; do
    [ -f "$d/package.json" ] || continue
    run "typecheck $(basename "$(dirname "$d")")" bash -c \
      "cd '$d' && bun install --silent && bun run typecheck"
  done
else
  skip "portal CLI typecheck" "bun is not installed"
fi

echo
echo "documents"
if [ "$QUICK" = "1" ]; then
  skip "example CV and cover letter compile" "--quick"
elif command -v lualatex >/dev/null 2>&1 && command -v xelatex >/dev/null 2>&1; then
  # The icon packages are vendored, not installed: texmf/README.md.
  export TEXMFHOME="$PWD/texmf"
  run "example CV compiles (lualatex)" bash -c \
    "cd cv && lualatex -interaction=nonstopmode main_example.tex"
  run "example letter compiles (xelatex)" bash -c \
    "cd cover_letters && xelatex -interaction=nonstopmode cover_example.tex"
  rm -f cv/*.aux cv/*.log cv/*.out cover_letters/*.aux cover_letters/*.log cover_letters/*.out
else
  skip "example CV and cover letter compile" "no lualatex/xelatex; see SETUP.md"
fi

echo
echo "-------------------------------------------------------------"
printf '%d passed, %d failed, %d skipped\n' "$PASS" "$FAIL" "$SKIP"
if [ "$FAIL" -gt 0 ]; then
  printf 'failed:%b\n' "$failed_names"
  echo "Not green. Do not push to master."
  exit 1
fi
if [ "$SKIP" -gt 0 ]; then
  echo "Green, with $SKIP check(s) skipped. Say which in the commit or the PR."
else
  echo "Green. Every check CI runs passed here."
fi
