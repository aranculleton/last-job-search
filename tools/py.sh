#!/bin/sh
# Which Python runs the app's own commands, on every computer.
#
# `python3` is not a command on every computer that has Python. The python.org
# installer for Windows gives `python` and `py`, and the `python3` Windows finds
# instead is a Microsoft Store stand-in that prints a message and fails
# (https://docs.python.org/3/using/windows.html). The hooks, the merge driver and
# the local checks all said python3, so on Windows none of them ran.
#
#     sh tools/py.sh --which      the path of one Python 3.9 or newer, or one line and exit 1
#     sh tools/py.sh <args...>    that Python, run with the args (stdin passes through)
#
# The order: the Python this repo was set up with (an active virtual environment,
# then .venv here), because that is where its packages are, then python3, python,
# and Windows' `py -3`. Each one is tried by running it, so a Store stand-in, a
# virtual environment whose Python was since removed, or a Python older than 3.9
# is passed over rather than chosen. The try is `-I -S`, which starts in about
# ten milliseconds and reads nothing from the repo.
#
# POSIX sh on purpose: macOS and Linux have /bin/sh, and on Windows the hooks and
# the Bash tool run in Git Bash, which has it too
# (https://code.claude.com/docs/en/hooks#exec-form-and-shell-form).

root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." 2>/dev/null && pwd) || root=.

runs() {  # runs <python>: true when it starts and is 3.9 or newer
  [ -n "$1" ] || return 1
  "$1" -I -S -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
    >/dev/null 2>&1
}

pick() {
  for cand in \
      "${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/python}" \
      "${VIRTUAL_ENV:+$VIRTUAL_ENV/Scripts/python.exe}" \
      "$root/.venv/bin/python" \
      "$root/.venv/Scripts/python.exe"; do
    if [ -n "$cand" ] && [ -f "$cand" ] && runs "$cand"; then
      printf '%s\n' "$cand"
      return 0
    fi
  done
  for name in python3 python; do
    cand=$(command -v "$name" 2>/dev/null) || continue
    if runs "$cand"; then
      printf '%s\n' "$cand"
      return 0
    fi
  done
  # Windows' launcher: `py -3` is two words, so it is resolved to the one
  # executable it starts, which is what a caller can run. -X utf8: Python on
  # Windows writes to a pipe in the ANSI code page, so a Python under a folder
  # named "Zoë" printed a path Git Bash (UTF-8) could not use, and -I drops the
  # PYTHONUTF8 the app sets (https://docs.python.org/3/library/sys.html#sys.stdout,
  # https://docs.python.org/3/using/cmdline.html#cmdoption-X).
  if command -v py >/dev/null 2>&1; then
    cand=$(py -3 -X utf8 -I -S -c 'import sys; print(sys.executable if sys.version_info >= (3, 9) else "")' \
      2>/dev/null | tr -d '\r')
    if runs "$cand"; then
      printf '%s\n' "$cand"
      return 0
    fi
  fi
  return 1
}

if ! py=$(pick); then
  echo "No Python 3.9 or newer was found on this computer (tried python3, python and py -3)." >&2
  exit 1
fi
if [ "${1-}" = "--which" ]; then
  printf '%s\n' "$py"
  exit 0
fi
exec "$py" "$@"
