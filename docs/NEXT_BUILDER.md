# Notes for the next builder

Written at the end of 4.5.0 (2026-10-30) for the chat that builds the next version. Read
MAINTAINING.md first; this is only what 4.5 left.

## How to work (the maintainer, 2026-10-30)

- **Decide, never ask.** Every design, tooling and gate question is the builder's to settle
  (MAINTAINING.md, "The builder decides"). Make the call, do it, say it in one line.
- **Everything the maintainer sends during a build goes into the same release**, never a
  later one. When the work is done and green, release it without waiting to be told twice,
  and prepare the release (CHANGELOG, this file, the rehearsals) while the checks run.
- **Keep it cheap**: few steps, no polling, the whole suite on GitHub only.
- The push gate scans every patch and the whole tree. Its denylist is built by the
  maintainer's copy's own `tools/build_app.py`, cached 12 hours in `/tmp/ljs-push-gate`.
  Until that copy runs 4.5, its builder lacks 4.5's set-aside fix and flags "Visa", "Fetch"
  and "Mozilla" on files that never changed: build the tokens with this tree's builder from a
  throwaway clone of the copy (`python3 tools/build_app.py /tmp/ljs-push-gate/app
  --tokens-out /tmp/ljs-push-gate/tokens`), never by narrowing the gate.
- A `Fast checks` job can sit queued on GitHub with every check it waits for green, and
  GitHub may refuse to rerun it. A new push starts a fresh run.

## Left open

- The "?" explainer is on the rules Claude has learned only; other Settings have none yet.
- Icons were kept to the ones the page had; none were added.
- Pre-approving the GitHub tools a landing chat uses (merge, create pull request) was
  refused by Claude Code's own safety check when written into the settings; a chat may still
  be asked about them once.
- An interview with no application ("Something else" in I have an interview) opens Chat
  rather than a form.
- "Employers you follow" can be added on the page but not taken off there.
- No page door yet for `/expand`, `/upskill`, `/add-portal` or `/add-template`.
- The 4.2 newcomer journey findings were never closed as a list: the apply link, the
  searching state, applied shown the same everywhere, a double paste, forms rather than chat,
  and the wording.
- The README's pictures, video and wording predate the 4.5 page and are too long.

## Not tested against the live services

- The page writes that no longer ask (4.5): the cause is proven from a real chat's prompt
  log (a `~` and a digit in a file name), and the names are fixed and tested; a live chat
  with the new names has not run yet.
- The chat that answers the page renewing itself daily, a new chat taking the page from a
  quiet one, and the archiving of a finished job's chat or a replaced helper: tested on the
  lines the app prints, never with real sessions.
- The pin hand-off ("Pin my job search page to my sidebar." to the Artifact `pin` action):
  tested up to the hand-off.
- Safari's and Firefox's engines were not installed in the build container: 4.5's page
  changes ran in Chromium only. Everywhere runs them on this release.
- From 4.4 and still open: the pre-approved writes in a chat that was asked before, big jobs
  in chats of their own side by side, the page reading LinkedIn in the desktop app's browser
  (the whole flow is simulated), the daily tidy-up's session calls, the brief's bell from
  inside the Claude app, and the page store beyond the probe page.

## Platforms

- A release's Windows suite runs in three parts side by side (`LJS_SUITE_SHARD`), about 10
  minutes each. Windows runs on a release pull request, weekly and by hand.
- Safari's engine leaves the space before an inline-block link out of `innerText`; a page
  test that reads words around a link allows for it.
- GitHub's Chromium writes a day as "Sun, 25 Oct" with a comma; a test reading a date the
  page wrote with `fmtDay` allows for either form.
- Everywhere (`tools/everywhere.sh`, on releases and weekly) checks the page in Safari's
  engine, Firefox, a Mac's and Windows' type, French and German and the far time zones, and
  the rest with the clock moved on, from an odd folder and on the newest Python.

## The maintainer's own copy

- `tools/try_personal_tests.py` and `tools/rehearse_sync.py` pass on 4.5 against it (cloud
  and computer chats taking the update at once, its own tests, the quick local CI).
