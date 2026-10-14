# /threads - Pipeline state

What is owed, what is due, what has gone cold.

## Run it

1. `state.load_contacts()` and `state.load_threads()`.
2. `state.reconcile()` first. A stored status that disagrees with the message
   history is a bug: report it rather than papering over it.
3. `state.owed(contacts, threads, today)` returns both kinds of debt: threads
   where they replied and we have not, and threads where we are past the
   follow-up window with no nudge sent.
4. `state.platform_budget()` for the week's remaining capacity.
5. `state.link_to_applications()` to show where a thread and an application at
   the same employer relate.

## Present

**Owed a reply** first, oldest first. These are live conversations going stale
and they are the highest-value thing in the pipeline.

**Nudge due** second: past 5 to 7 business days, no nudge sent yet. One nudge
only, ever.

**Gone cold** third, as a list to close out rather than chase.

**Linked** last: threads and applications at the same employer, so a referral in
progress can be pointed at a live application.

Finish with the platform budget and the single highest-value next action.
