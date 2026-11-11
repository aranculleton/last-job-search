## What changed and why

<!-- One pull request for one version's work or one fix, on a branch started from
     origin/master (MAINTAINING.md, "Builder"). -->

## The failing case (for fixes)

<!-- Almost every invariant in tools/ carries a comment naming the application it
     shipped as a defect on. Continue that: what went wrong, on what input, through
     the path the pipeline really runs. A test that only fails on a hand-built input
     the real code path never receives is not a reproduction. -->

## Verification

<!-- What you actually ran. On the app:
       tools/push_gate.sh <the maintainer's repo> --text <this description> --push <branch>
       python3 -m pytest tests/<each test file you changed> -q   (pytest, never unittest discover)
     The whole suite is this pull request's own CI run; it is never run by hand.
     On a private copy, ./tools/ci_local.sh --quick is the CI: say it was green, and name any SKIP.
     In a touched portal CLI: bun run typecheck && bun test
     If this touches document generation, also:
       python3 tools/fit_to_page.py <drafts.json>
       tools/verify_batch.sh <drafts.json>
     and say that you read the PDFs, not the .tex. -->

## State files touched

<!-- job_search_tracker.csv, network_contacts.csv, network_threads.csv,
     seen_jobs.json, do_not_target.json. Say which, so a parallel session merging
     this knows where to look for conflicts. None is a fine answer. -->
