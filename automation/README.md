# Automation: what runs on a clock

Everything here is described in `profile/routines.json`, the person's registry. The work
itself is written in `prompts/`, which is the part that changes most and the part that needs
nothing but a merge to master to change.

## What reaches the candidate's phone

The times are the person's (`profile/routines.json`, and "This search's automation" in
`profile/CLAUDE.md`).

| Routine | What |
|---|---|
| **Morning brief**, every day | What is owed, then a TLDR: news at employers the candidate is in process with, their target employers, their market, their work authorization. Weekdays include drafted replies and nudges; weekends only count them. |
| **Job round**, twice a week | A scored round and the top 8. Reply with picks in the "Job search ops" session and it drafts, verifies and records them. |

**If no morning brief has arrived two hours after its time, the automation is broken.** The brief is sent
every day even when nothing is due, so silence always means something failed. Tell any
Claude chat "the routines are down" and point it at this file.

## How it works, and why it is shaped like this

```
 schedule ──► "Job search ops" session ──fire_trigger──► relay routine ──► push + email
              (has the repo; does the work)               (fresh session; repeats the text)
```

Three facts force this shape:

1. **A routine created through the API cannot have a repository attached**, and the claude.ai
   editor would not attach one to these either. A routine with no repository cannot clone a
   private repo: the first three routines (25 Sep to 5 Oct) ran every morning, found nothing,
   and sent only "cannot reach the repo".
2. **A routine can fire into an existing session**, and a session created with the repo as its
   source keeps it. So the work routines fire into the ops session.
3. **A routine that fires into an existing session cannot send push or email notifications**;
   only a fresh-session routine can. So the ops session finishes the work and fires the relay
   routine with the message as its text, and the relay's own fresh session is what notifies.

Each work routine's stored prompt is a short stub (`stub` in `profile/routines.json`) that says: pull
master, read `prompts/_common.md` and the routine's own file, follow them. **So the
instructions live in git, not in the account.** Change a prompt file, merge it, and the next
run follows the new version. No routine needs editing for that.

## Changing something: say it to any Claude chat

| Ask | What the chat does |
|---|---|
| "Make the brief shorter", "add X to the TLDR", "stop drafting on Fridays" | Edits the prompt file, opens a PR, merges it. Takes effect on the next run. |
| "Move the brief to 7:30", "run the round on Wednesdays too" | Edits `cron` in `profile/routines.json`, calls `update_trigger` on that `trigger_id` with the new cron (written with the registry's `CRON_TZ=<timezone>`), merges. |
| "Switch everything to <city> time" | Changes `timezone` and every `cron` to `CRON_TZ=<IANA zone>` at the same local times, applies each with `update_trigger`, merges. |
| "Add a routine that does Y" | Writes `prompts/<key>.md`, adds an entry, creates the trigger with `create_trigger` and `persistent_session_id` set to `ops_session.id` and the prompt from `stub`, records the new `trigger_id`, merges. |
| "Pause the job round" | `update_trigger` with `enabled: false`. Say so in `profile/routines.json` (`"paused": "<date> <reason>"`). |

**Never test a work routine with `fire_trigger`.** A manual fire ignores the session a
routine is bound to and starts a fresh session with no repo, which fails exactly the way
the old routines did (found 2026-10-05: the forced run went to a new session on a cheaper
model and did nothing in 26 seconds). Only scheduled fires land in the ops session. To run
one now, create a one-off trigger with `run_once_at` a couple of minutes ahead,
`persistent_session_id` set to the ops session and the same stub prompt; it disables itself
after firing. `fire_trigger` is right only for the relay, which is meant to start fresh.

`tests/test_automation.py` checks the registry against the prompt files, so a typo in a
path or a missing prompt fails CI before it can fail at 07:56.

## If the ops session is lost

If the session is archived or deleted, the work routines fire into nothing and no brief
arrives. To rebuild:

1. `create_session` with `source_url` set to this private repository's own URL
   (`git remote get-url origin`; `profile/CLAUDE.md` names it), the same title, tag
   `job-search-ops` and permission mode `auto`.
2. For each `ops_session` routine, `delete_trigger` the old one and `create_trigger` a new one
   with the same name, cron and stub prompt, bound to the new session id. A trigger's bound
   session cannot be changed in place. Read the old trigger with `get_trigger` first: its
   stored prompt is the stub already filled in, which is what the new one takes.
3. Write the new ids into `profile/routines.json` and merge.
4. Test with a one-off `run_once_at` trigger (above), never `fire_trigger`.

**The repository matters.** The ops session must be created on the person's private repo,
never on the public app (`aranculleton/last-job-search`): a session on the app holds none of
the person's state, and anything it pushed would be public.

The ops session's conversation grows by one turn a run and is compacted automatically. It is
fine to open it and talk to it; replies to the job round's picks belong there.

## Cost

Each run is one turn in the ops session on the session's model, plus a cheap relay turn. News
gathering for the TLDR is done by a sonnet subagent with a cap of about ten searches. The
setup test on 2026-10-05 cost $0.82 for an empty run, most of it loading the repo's
instructions into a new session; later runs reuse that context from cache.
