#!/usr/bin/env bash
# The maintainer's gate before anything is pushed to the app, which is public: first the scans
# only this machine can run (the maintainer's own names), the name guard and the version note,
# then the quick checks, stopping at the first failure. It runs no tests CI runs: the whole
# suite, the page's browser tests included, is the pull request's own CI run, free on the
# public app (MAINTAINING.md, "Before pushing"). Before 4.3 a session ran the whole suite by
# hand three times, an hour; in 4.3 this gate still ran the changed tests first, minutes
# before a push that CI then ran again (the maintainer, 2026-10-29).
#
#   tools/push_gate.sh <the maintainer's repo> [--text <file>]... [--push <branch>]
#
#   --text <file>   text that will be posted (a pull request description): scanned too
#   --push <branch> once every step passed, push HEAD there (never with force)
#
# Exit 0 only when every step passed; the first failure stops it, with nothing pushed. Nothing in the maintainer's repo is changed: the
# denylist is written from it into a folder of its own, kept for 12 hours.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
MAINT="${1:-}"
if [ -z "$MAINT" ] || [ ! -d "$MAINT/profile" ]; then
  echo "usage: tools/push_gate.sh <the maintainer's repo, with its profile/> [--text <file>]... [--push <branch>]"
  exit 2
fi
shift
TEXTS=()
BRANCH=""
while [ $# -gt 0 ]; do
  case "$1" in
    --text) TEXTS+=("$2"); shift 2 ;;
    --push) BRANCH="$2"; shift 2 ;;
    *) echo "push_gate: unknown option $1"; exit 2 ;;
  esac
done

PY="${PYTHON:-python3}"
WORK="${TMPDIR:-/tmp}/ljs-push-gate"
mkdir -p "$WORK"
step() {               # step <name> <command...>: run it, say PASS, or FAIL and stop there
  local name="$1"; shift
  if "$@" > "$WORK/step.log" 2>&1; then
    printf '  %-44s PASS\n' "$name"
  else
    printf '  %-44s FAIL\n' "$name"; sed 's/^/      /' "$WORK/step.log" | tail -15
    echo "push_gate: FAILED: $name. Nothing pushed."
    exit 1
  fi
}

git fetch -q origin master || { echo "push_gate: could not fetch origin master"; exit 1; }
BASE="$(git merge-base origin/master HEAD)"

# The denylist: the maintainer's own people, from their profile and the history of their
# tracker, contact book and message log (tools/build_app.py). Built once, kept 12 hours.
TOKENS="$WORK/tokens"
if [ ! -s "$TOKENS" ] || [ -n "$(find "$TOKENS" -mmin +720 2>/dev/null)" ]; then
  rm -rf "$WORK/app"
  (cd "$MAINT" && "$PY" tools/build_app.py "$WORK/app" --tokens-out "$TOKENS") > "$WORK/build.log" 2>&1 \
    || { echo "push_gate: could not build the denylist from $MAINT"; tail -5 "$WORK/build.log"; exit 1; }
fi

echo "private data first (nothing is pushed unless all of these pass)"
rm -rf "$WORK/tree" && mkdir -p "$WORK/tree" && git archive HEAD | tar -x -C "$WORK/tree"
# Only what the patches add: a line they remove is on master already, or was added by an
# earlier patch here and is read there, and taking out a name the person has since written
# down (a public guide, an invented greeting) must not fail for showing it go.
git log -p -U0 --format="commit %H%n%B" "$BASE..HEAD" -- . ':!tools/openroles' | grep -v '^-' > "$WORK/patches.txt" || true
git log --format="%B%n-----" "$BASE..HEAD" > "$WORK/messages.txt"
step "every patch since master" "$PY" tools/leak_scan.py --text "$WORK/patches.txt" --tokens "$TOKENS"
step "commit messages" "$PY" tools/leak_scan.py --text "$WORK/messages.txt" --tokens "$TOKENS"
for t in "${TEXTS[@]+"${TEXTS[@]}"}"; do
  step "text to post: $(basename "$t")" "$PY" tools/leak_scan.py --text "$t" --tokens "$TOKENS"
done
step "the exact tree, against the denylist" "$PY" tools/leak_scan.py "$WORK/tree" --tokens "$TOKENS"
step "structure (what git would commit)" "$PY" tools/leak_scan.py . --git

echo "names and the version note"
step "names in the change (name_guard)" "$PY" tools/name_guard.py diff origin/master
step "names in the commit messages" "$PY" tools/name_guard.py text "$WORK/messages.txt"
for t in "${TEXTS[@]+"${TEXTS[@]}"}"; do
  step "names in $(basename "$t")" "$PY" tools/name_guard.py text "$t"
done
# A change to what a build leaves behind needs its version note (tools/build_versions.py): the
# one test run here, in seconds, since CI failing on it costs a whole round.
step "version notes (test_build_versions)" "$PY" -m pytest -q -p no:cacheprovider tests/test_build_versions.py

echo "quick checks"
if "$PY" -m ruff --version > /dev/null 2>&1; then
  step "ruff (bugs only)" "$PY" -m ruff check --no-cache tools/ templates/ tests/
else
  printf '  %-44s SKIP (ruff not installed; CI runs it)\n' "ruff (bugs only)"
fi
step "skills, commands and settings" "$PY" tools/lint_skills.py
step "permissions, gitignore, manifests" "$PY" tools/security_guards.py
step "framework version" "$PY" tools/check_framework_version.py
step "public names stay, or are listed as gone" "$PY" tools/public_names.py check

# No test suite here: the pull request's CI runs every test, the page's in browsers too, free
# on the public app, and its fast checks are what a merge waits for (ci.yml, "Fast checks").
echo "push_gate: every step passed"
if [ -n "$BRANCH" ]; then
  git merge-base --is-ancestor origin/master HEAD || { echo "push_gate: HEAD does not contain origin/master; merge it first"; exit 1; }
  git push -q origin "HEAD:refs/heads/$BRANCH" && echo "push_gate: pushed $(git rev-parse --short HEAD) to $BRANCH"
fi
