#!/usr/bin/env bash
# Every place the app runs that CI's ordinary jobs do not: the page in Safari's engine (the
# Claude app on an iPhone, Safari on a Mac), in Firefox, in a Mac's and in Windows' shapes of
# type, on a device set to French or German, and 14 hours ahead of London and 10 behind; the
# rest of the app with the clock a month, three months and over a year on (what breaks by
# itself later), in the far time zones, from a folder with spaces, an accent and an
# apostrophe in its path, and on the newest Python.
#
# A layout that fitted in one font pushed a phone sideways in another, and the clock check
# was a step done by hand and skipped (2026-10-29). CI's Everywhere workflow runs this on a
# release pull request, weekly and by hand: free on the public app, never on a private copy,
# and one job each for the page and the rest, so a failure is one short summary to read.
#
#   tools/everywhere.sh page  [variant...]   the page's browser tests in each variant
#   tools/everywhere.sh suite [variant...]   the rest of the suite in each variant
#   tools/everywhere.sh list                 the variants
#
# EVERYWHERE_TESTS="tests/test_a.py tests/test_b.py" runs only those files: to reproduce a
# failure the summary named, cheaply, before a fix is pushed.
#
# A variant this machine cannot run (no Safari engine, no time-machine, no newest Python) is
# reported SKIP, never passed; with EVERYWHERE_STRICT=1, as CI sets, a SKIP fails. Exit 0
# only when every variant ran and passed. The last lines name each failure and its failing
# tests: read those, never the whole log.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
PY="${PY:-python3}"
OUT="${TMPDIR:-/tmp}/ljs-everywhere"
mkdir -p "$OUT"

PAGE_VARIANTS="safari firefox mac-type windows-type french german ahead behind"
SUITE_VARIANTS="30-days 90-days 400-days ahead behind odd-folder newest-python"
BROWSER_TESTS="$(grep -lE 'app_page/harness\.js|journeys\.browser\(\)|_node_env|test_the_page_journeys import|import test_the_page_journeys' tests/*.py)"
PY_NEWEST="${PY_NEWEST:-python3.14}"

kind="${1:-}"
[ $# -gt 0 ] && shift
case "$kind" in
  page) wanted="${*:-$PAGE_VARIANTS}" ;;
  suite) wanted="${*:-$SUITE_VARIANTS}" ;;
  list) echo "page:  $PAGE_VARIANTS"; echo "suite: $SUITE_VARIANTS"; exit 0 ;;
  *) echo "usage: tools/everywhere.sh page|suite [variant...] | list"; exit 2 ;;
esac

results=""
note() { results="$results$1"$'\n'; }

# The page asks for the system's own type (system-ui): this makes it the named font, and
# says so only if Chrome's engine really draws the page in it.
type_as() {
  local font="$1" conf="$OUT/fonts-$2.conf"
  {
    echo '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>'
    echo '<include ignore_missing="yes">/etc/fonts/fonts.conf</include>'
    echo '<selectfont><rejectfont><glob>*DejaVuSans*</glob><glob>*FreeSans*</glob>'
    [ "$font" = "Inter" ] || echo '<glob>*Inter*</glob>'
    echo '</rejectfont></selectfont>'
    for f in sans-serif system-ui; do echo "<alias binding=\"strong\"><family>$f</family><prefer><family>$font</family></prefer></alias>"; done
    echo '</fontconfig>'
  } > "$conf"
  FONTCONFIG_FILE="$conf" FONT="$font" NODE_PATH="${NODE_PATH:-}${NODE_PATH:+:}$(npm root -g 2>/dev/null)" node -e '
    const pw = require("playwright");
    (async () => {
      const b = await pw.chromium.launch(); const p = await b.newPage();
      const w = await p.evaluate((f) => {
        const m = (x) => { const s = document.createElement("span"); s.style.font = "16px " + x; s.textContent = "The quick brown fox jumps over the lazy dog"; document.body.appendChild(s); const r = s.getBoundingClientRect().width; s.remove(); return r; };
        return [m("system-ui, sans-serif"), m(JSON.stringify(f))];
      }, process.env.FONT);
      await b.close();
      process.exit(Math.abs(w[0] - w[1]) > 0.5 ? 1 : 0);
    })().catch(() => process.exit(1));' > /dev/null 2>&1 && echo "$conf"
}

engine_runs() {
  NODE_PATH="${NODE_PATH:-}${NODE_PATH:+:}$(npm root -g 2>/dev/null)" ENGINE="$1" node -e '
    require("playwright")[process.env.ENGINE].launch().then((b) => b.close()).catch(() => process.exit(1));' > /dev/null 2>&1
}

# One variant: its name, why it could not run (empty when it can), the interpreter, the
# folder, then env assignments, then -- and pytest's arguments.
run() {
  local name="$1" cannot="$2" py="$3" dir="$4"; shift 4
  local envs=()
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do envs+=("$1"); shift; done
  shift
  if [ -n "$cannot" ]; then
    printf '  %-16s SKIP (%s)\n' "$name" "$cannot"; note "$name: SKIP, $cannot"; return
  fi
  local log="$OUT/$kind-$name.txt" par=""
  "$py" -c "import xdist" > /dev/null 2>&1 && par="-n auto --dist loadfile"
  # shellcheck disable=SC2086
  (cd "$dir" && env ${envs[@]+"${envs[@]}"} "$py" -m pytest -q -p no:cacheprovider $par -rf --tb=line "$@") > "$log" 2>&1
  local code=$? last
  last="$(grep -aE '[0-9]+ (passed|failed|error)' "$log" | tail -1)"
  if [ $code -eq 0 ]; then
    printf '  %-16s PASS  %s\n' "$name" "$last"
  else
    printf '  %-16s FAIL  %s\n' "$name" "${last:-exit $code, see $log}"
    note "$name: FAIL, ${last:-exit $code}"
    while IFS= read -r l; do note "    ${l:0:300}"; done < <(grep -aE '^(FAILED|ERROR) ' "$log" | head -8)
  fi
}

echo "everywhere: $kind ($wanted)"
if [ "$kind" = page ]; then
  # shellcheck disable=SC2086
  set -- ${EVERYWHERE_TESTS:-$BROWSER_TESTS}
  for v in $wanted; do
    case "$v" in
      safari) run safari "$(engine_runs webkit || echo "Safari's engine is not installed here")" "$PY" "$ROOT" LJS_PW_ENGINE=webkit -- "$@" ;;
      firefox) run firefox "$(engine_runs firefox || echo "Firefox is not installed here")" "$PY" "$ROOT" LJS_PW_ENGINE=firefox -- "$@" ;;
      mac-type) c="$(type_as Inter mac)"; run mac-type "$([ -n "$c" ] || echo "the Inter font is not installed here")" "$PY" "$ROOT" "FONTCONFIG_FILE=$c" -- "$@" ;;
      windows-type) c="$(type_as "Liberation Sans" windows)"; run windows-type "$([ -n "$c" ] || echo "the Liberation Sans font is not installed here")" "$PY" "$ROOT" "FONTCONFIG_FILE=$c" -- "$@" ;;
      french) run french "" "$PY" "$ROOT" LJS_PW_LOCALE=fr-CA -- "$@" ;;
      german) run german "" "$PY" "$ROOT" LJS_PW_LOCALE=de-DE -- "$@" ;;
      ahead) run ahead "" "$PY" "$ROOT" LJS_PW_TZ=Pacific/Kiritimati -- "$@" ;;
      behind) run behind "" "$PY" "$ROOT" LJS_PW_TZ=Pacific/Honolulu -- "$@" ;;
      *) echo "everywhere: no page variant $v"; exit 2 ;;
    esac
  done
else
  skips=(); for b in $BROWSER_TESTS; do skips+=("--ignore=$b"); done
  # The clock moved on for every Python the suite starts, its tools' own included: a
  # sitecustomize on PYTHONPATH that moves the date and leaves waiting alone (time-machine).
  # libfaketime moved the C library's clocks too and broke Python's own sleep with "Invalid
  # argument" in 300 tests that have nothing to do with dates (2026-10-29).
  shift="$OUT/clock-shift"; mkdir -p "$shift"
  cat > "$shift/sitecustomize.py" <<'PYEND'
import os
_days = os.environ.get("LJS_CLOCK_SHIFT_DAYS")
if _days:
    import subprocess
    import time
    import time_machine
    # A plain timestamp: given a UTC datetime, time-machine sets TZ=UTC in every process and
    # would hide the time-zone bugs this check is for.
    time_machine.travel(time.time() + int(_days) * 86400, tick=True).start()
    # git keeps the real clock unless told: its commits are dated on the moved one too, so a
    # commit's age is read on the same clock as everything else.
    _init = subprocess.Popen.__init__

    def _popen(self, *a, **kw):
        env = dict(kw.get("env") if kw.get("env") is not None else os.environ)
        stamp = "%d +0000" % time.time()
        for k in ("GIT_COMMITTER_DATE", "GIT_AUTHOR_DATE"):
            env.setdefault(k, stamp)
        kw["env"] = env
        return _init(self, *a, **kw)
    subprocess.Popen.__init__ = _popen
PYEND
  noclock=""; "$PY" -c "import time_machine" > /dev/null 2>&1 || noclock="no time-machine here (pip install time-machine)"
  set -- tests "${skips[@]}"
  if [ -n "${EVERYWHERE_TESTS:-}" ]; then
    # shellcheck disable=SC2086
    set -- $EVERYWHERE_TESTS
  fi
  for v in $wanted; do
    case "$v" in
      30-days|90-days|400-days)
        run "$v" "$noclock" "$PY" "$ROOT" "PYTHONPATH=$shift${PYTHONPATH:+:$PYTHONPATH}" "LJS_CLOCK_SHIFT_DAYS=${v%-days}" -- "$@" ;;
      ahead) run ahead "" "$PY" "$ROOT" TZ=Pacific/Kiritimati -- "$@" ;;
      behind) run behind "" "$PY" "$ROOT" TZ=Pacific/Pago_Pago -- "$@" ;;
      odd-folder)
        # A person's folder with a space, an accent and an apostrophe in it: a path a script
        # left unquoted splits or breaks here. The checkout is copied there, history and all.
        odd="$OUT/a folder/Zoë Quillfeather's copy"
        rm -rf "$OUT/a folder" && mkdir -p "$odd" && cp -a "$ROOT/." "$odd/"
        run odd-folder "" "$PY" "$odd" -- "$@" ;;
      newest-python)
        np=""; command -v "$PY_NEWEST" > /dev/null 2>&1 && "$PY_NEWEST" -c "import pytest" > /dev/null 2>&1 || np="no $PY_NEWEST with pytest here"
        run newest-python "$np" "$PY_NEWEST" "$ROOT" -- "$@" ;;
      *) echo "everywhere: no suite variant $v"; exit 2 ;;
    esac
  done
fi

bad="$(printf '%s' "$results" | grep -cE ': FAIL' || true)"
skipped="$(printf '%s' "$results" | grep -cE ': SKIP' || true)"
if [ -n "$results" ]; then
  echo "everywhere: what needs looking at"
  printf '%s' "$results"
fi
if [ "$bad" -gt 0 ] || { [ "${EVERYWHERE_STRICT:-}" = 1 ] && [ "$skipped" -gt 0 ]; }; then
  echo "everywhere: $kind FAILED ($bad failed, $skipped not run)"
  exit 1
fi
if [ "$skipped" -gt 0 ]; then echo "everywhere: $kind passed ($skipped not run here)"; else echo "everywhere: $kind passed"; fi
