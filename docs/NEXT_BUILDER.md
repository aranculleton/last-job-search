# Notes for the next builder

Written at the release of 4.18.0 (2026-11-25) by the weekly builder. This is background, never
a list of work: a builder starts only from the maintainer's notes (MAINTAINING.md, "Builder").

## Not tested at this release
- The round's screen, flashcards and in-person plan were seen on the sample page only; no real
  person's round with marks over several days has been used.
- The two request agents (#370) are instructions only: nothing checks that a chat ran them.
- The builder hand-over (app_bug.py handover) has never run for real.
- Platforms on Windows passed on a re-run; its first run timed out fetching job descriptions.

## Known red
- The maintainer's copy fails its own letter and note tests in the sync rehearsal, on master too.
- #367, #369 and #371 stay open with parts left, named in the release notes.
