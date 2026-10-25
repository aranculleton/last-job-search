# /threads - Pipeline state

What is owed, what is due, what has gone cold.

## Run it

1. `state.load_contacts()` and `state.load_threads()`.
2. `state.reconcile()` first. A stored status that disagrees with the message
   history is a bug: report it rather than papering over it. A `possible_duplicate`
   is two rows at one employer that may be one person (a nickname, an initial, a
   reversed name, a letter's typo): ask the person, and never merge them yourself.
3. `state.owed(contacts, threads, today)` returns both kinds of debt: threads
   where they replied and we have not, and threads where we are past the
   follow-up window with no nudge sent.
4. `state.platform_budget()` for the requests sent this week and the InMail credits left.
   The app sets no cap on connection requests: LinkedIn says when its own limit is reached,
   and no "N left" is ever said that LinkedIn did not give.
5. `state.link_to_applications()` to show where a thread and an application at
   the same employer relate.
6. `python3 tools/network/own_profile.py due`: it prints a line only when a look at their own
   LinkedIn profile is worth it. Act on that line alone, asking its question once at the end.

## Present

**Owed a reply** first, oldest first. These are live conversations going stale
and they are the highest-value thing in the pipeline.

**A resume owed** (`state.resumes_owed()`) rides with them: somebody asked for it and no
message logged since says one went. Say which file goes (the guidance names the two routes)
and the command that logs it with the file, `state.py message <id> --attached <file>`.

**First message owed** next (`first_message`): they accepted a request that
carried no note and nothing has been sent. Draft it with `compose.first_note()`; it is
not a nudge.

**Nudge due** then: past 5 to 7 business days, no nudge sent yet, or the person's own
rule where `profile/networking.py` sets `FOLLOW_UP_DAYS` and `MAX_UNANSWERED`
(`schema.follow_up_rule()` says which is in force). One nudge only, unless their rule
allows more. `compose.validate()` refuses check-in wording ("just checking in",
"bumping this", "did you get a chance"): a nudge carries something new to answer.

**Requests to withdraw** (`request_pending`): a connection request nobody accepted in
21 days. Nothing can be sent; say so and suggest withdrawing it. When they say they have
withdrawn it on LinkedIn, record it in the same turn:
`python3 tools/network/state.py withdraw <contact_id>...` (`--all-due` for every one
listed here). It logs a `request_withdrawn` row the derived status reads as closed and
closes the contact with the date and why, so the request leaves this list and the person
is never surfaced or written to again. Commit the two CSVs.
Requests sent from LinkedIn itself that the log never saw come from their export
(`python3 tools/network/export.py pending`, printed in the state view as PENDING INVITATIONS),
oldest first. They withdraw them on LinkedIn, one at a time (`python3 tools/claude_surfaces.py
steps linkedin-withdraw-invitation`); the app never does. Record the ones they name with
`python3 tools/network/export.py withdrawn <name>...` (or `--oldest <n>`).

**Gone cold** third, as a list to close out rather than chase. These are the threads whose
limit of unanswered messages is reached: the due list shows each one as a dated action
(`action_due`) on the app's own line, "If still silent by the date, close it: state.py set
<contact_id> --status gone_cold", on the day it falls due. Close the ones the person agrees
to with that command; a reply that comes later reopens the thread by itself.

**Anything the person tells you about a thread** (a call booked, a referral put in, a new
date, what was said) is written the same turn with
`python3 tools/network/state.py set <contact> --status <status> --next-action "<what>"
--due <YYYY-MM-DD> --note "<what happened>"`, never by editing the contact book: a note
with line breaks typed into the file broke it.

**Linked** last: threads and applications at the same employer, so a referral in
progress can be pointed at a live application.

Finish with the platform budget and the single highest-value next action.

A message the person says went is recorded by command, with its words: a first note with
`python3 tools/network/state.py sent <contact_id> --draft` (or `--text-file`), a nudge with
`state.py nudge <contact_id> --text-file <file>`, and any other later message with
`state.py message <contact_id> --text-file <file>` (`--texts <file.json>` for several at once).
Each writes the outbound row with its full text and the contact's `status`, `next_action` and
`next_action_due`, and the same words to the same person on one day are never logged twice. After a nudge, which is the only
one, `next_action` is to close the thread out if they stay silent, not another nudge.
