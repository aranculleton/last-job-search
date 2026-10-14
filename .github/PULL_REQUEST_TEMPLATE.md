## What changed and why

<!-- One concern per PR. If this bundles several, say so and why they had to ship
     together. -->

## The failing case (for fixes)

<!-- Almost every invariant in tools/ carries a comment naming the application it
     shipped as a defect on. Continue that: what went wrong, on what input, through
     the path the pipeline really runs. A test that only fails on a hand-built input
     the real code path never receives is not a reproduction. -->

## Verification

<!-- What you actually ran:
       python3 tools/lint_skills.py
       python3 tools/security_guards.py
       python3 -m pytest tests -q          (pytest, NOT unittest discover)
     In a touched portal CLI: bun run typecheck && bun test
     If this touches document generation, also:
       python3 tools/fit_to_page.py <drafts.json>
       tools/verify_batch.sh <drafts.json>
     and say that you read the PDFs, not the .tex. -->

## State files touched

<!-- job_search_tracker.csv, network_contacts.csv, network_threads.csv,
     seen_jobs.json, do_not_target.json. Say which, so a parallel session merging
     this knows where to look for conflicts. None is a fine answer. -->
