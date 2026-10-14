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
# only provides the machine. So it runs here, in about thirty seconds, and a
# clean run is the same evidence.
#
# CI's second Python leg exists because a bare `import tomllib` passed locally
# and failed on 3.10. That leg runs here too, the way CI runs it, on the
# system python3.10 or one uv fetches, and is reported SKIP only where neither
# exists.
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
  if ! python3 -c "import $mod" >/dev/null 2>&1; then
    skip "$name" "python3 -m $mod is not installed here"
    return
  fi
  run "$name" "$@"
}

echo
echo "ci_local: the checks .github/workflows/ci.yml runs"
echo

echo "lint"
run "skills, commands and settings" python3 tools/lint_skills.py
run_py_module ruff "ruff (bugs only, see .ruff.toml)" \
    python3 -m ruff check --no-cache tools/ templates/ tests/
# The scoring baseline is a person's own (their screened postings, in
# profile/tests/fixtures), so the app has none to check, and that is not a skip.
if [ -f profile/tests/fixtures/score_baseline.json ]; then
  run "scoring baseline" python3 tools/score_eval.py
else
  printf '  %-42s n/a   (a person'"'"'s own, in profile/tests/fixtures)\n' "scoring baseline"
fi
run "framework version guard" python3 tools/check_framework_version.py

echo
echo "security"
run "permissions, gitignore, manifests" python3 tools/security_guards.py
# The leak scan. In the app it reads the tree itself; in a person's repo it
# builds the app's tree from HEAD and scans that with the person's own
# denylist, so their data reaching an app-owned file fails here, long before
# anything could carry it to the app. Commit first: it reads HEAD.
if [ -f profile/person.json ]; then
  LEAK_OUT="$(mktemp -d)"
  run "leak scan (app tree built from HEAD)" python3 tools/build_app.py "$LEAK_OUT/app"
  rm -rf "$LEAK_OUT"
else
  run "leak scan (this tree)" python3 tools/leak_scan.py .
fi

echo
echo "tests"
run_py_module pytest "pytest (the app's suite, on the example person)" python3 -m pytest tests -q
# The person's own suite, against their profile, in its own process: the tools
# read the profile once at import, so the two suites cannot share one.
if [ -d profile/tests ]; then
  run_py_module pytest "pytest (profile/tests, on this person)" python3 -m pytest profile/tests -q
fi

echo
echo "python floor"
# CI's python-floor job, reproduced: a fresh 3.10 environment holding pytest and
# nothing else, so an import that only the main environment happens to have is
# caught as well as 3.11-only syntax. This file once said it could not catch
# that class of thing at all, while the containers these sessions run in
# shipped /usr/bin/python3.10.
FLOOR_NAME="tests on Python 3.10 (CI's floor leg)"
FLOOR_PY="$(command -v python3.10 || true)"
# The containers later stopped shipping /usr/bin/python3.10, which left this
# leg SKIP and the GitHub job the only thing that ran it. uv fetches a
# standalone 3.10 in about three seconds, so this leg runs here too and a
# private repo never needs a billed minute for it.
if [ -z "$FLOOR_PY" ] && command -v uv >/dev/null 2>&1; then
  FLOOR_PY="$(uv python find 3.10 2>/dev/null || true)"
  if [ -z "$FLOOR_PY" ]; then
    uv python install 3.10 >/dev/null 2>&1 || true
    FLOOR_PY="$(uv python find 3.10 2>/dev/null || true)"
  fi
fi
if [ -z "$FLOOR_PY" ]; then
  skip "$FLOOR_NAME" "no python3.10 here"
else
  FLOOR_ENV="${TMPDIR:-/tmp}/ci_local_py310"
  if ! "$FLOOR_ENV/bin/python" -c "import pytest" >/dev/null 2>&1; then
    rm -rf "$FLOOR_ENV"
    "$FLOOR_PY" -m venv "$FLOOR_ENV" >/dev/null 2>&1 \
      && "$FLOOR_ENV/bin/pip" install -q pytest >/dev/null 2>&1
  fi
  if "$FLOOR_ENV/bin/python" -c "import pytest" >/dev/null 2>&1; then
    run "$FLOOR_NAME" "$FLOOR_ENV/bin/python" -m pytest tests -q -p no:cacheprovider
    if [ -d profile/tests ]; then
      run "$FLOOR_NAME, profile/tests" "$FLOOR_ENV/bin/python" -m pytest profile/tests -q -p no:cacheprovider
    fi
  else
    skip "$FLOOR_NAME" "could not build a 3.10 venv with pytest (no venv module or no network)"
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
