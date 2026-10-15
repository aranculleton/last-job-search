# /reply - Draft a reply inside a live thread

Usage: `/reply <contact name or company>`, then paste their message.

## Run it

1. **Load the thread.** `state.load_threads()` for that contact. The thread
   history is the context; do not re-research the person unless something
   material has changed.

2. **Classify.** `reply.classify(inbound, history, today)` returns the scenario,
   a confidence and the matched evidence. Show the user which scenario and why,
   because a misread scenario produces a confidently wrong reply.

3. **Check it is worth continuing.** `reply.should_continue()`. After two
   explicit nos, recommend a warm close instead of a reply. Say so plainly.
   A "not hiring, but happy to chat" is not a no, and a thread at `call_booked` or
   `referral_in_progress` is never stopped.

   **When the scenario is `gone_quiet`** (nothing pasted, and we spoke last), run
   `reply.nudge_due(rows, today)` before drafting anything. If it is not due, or one
   nudge has already gone out, draft nothing and say why: a second nudge costs more
   than it recovers. If it is due, the nudge is `compose.nudge()`, with a new reason
   to answer, and `reply.following_up_is_honest(rows, today)` says whether an apology
   for the gap is owed.

4. **Read what they have taught it**: `python3 tools/learned.py brief messages`; its rules
   outrank the guidance's defaults. For a nudge, also `python3 tools/what_works.py brief
   messages --channel <channel>`: the follow-ups that drew replies are the shape to match.
   **Get the guidance.** `reply.guidance()` gives the move, the target length
   derived from their message, what not to do, and any action owed outside the
   thread (send an email, book a slot).

5. **Draft, then validate.** `compose.validate()` plus `tone.restate_ratio()`
   against their message. A high ratio means the draft is parroting them back,
   which is the most common tell of a machine-written reply. Rewrite it.

6. **Record.** Their message goes into `network_threads.csv` now. Ours goes in only when
   they say it went, dated the day it went: a draft is not a message, and logging it early
   makes the thread read as waiting on them before anything was sent (the same rule
   `/network` keeps for a first note). Every row carries its full text in `full_text`: a
   message logged without its text can never become an example of what works.

   The log decides three statuses by itself (`state.DERIVABLE`: `not_contacted`,
   `awaiting_reply`, `replied_needs_response`). Everything else is stored on the contact
   row, and this step is what sets it: when the exchange makes it so, set `status` to
   `in_conversation`, `call_booked`, `referral_in_progress` (somebody inside has put the
   candidate's name forward; `throttle.referral_holds()` reads it to hold every cold
   application there) or a terminal one (`gone_cold`, `closed`,
   `converted_to_application`). Then set `next_action` and `next_action_due` to what is owed
   now: the call and its date, the action owed outside the thread from step 4, or, once our
   message has gone and nothing else is owed, the nudge on
   `state.add_business_days(<the day it went>, schema.FOLLOWUP_BUSINESS_DAYS)`. The morning
   brief reads `next_action_due`, so a date written here is a reminder nobody has to set.

7. **When this was their reply**, run `python3 tools/what_works.py event --contact <contact_id>`
   and add its line to what you present: which message drew the reply, and that it is now
   an example the next message like it is drafted against. It is counting, not a model call.

## Present

The scenario and the evidence for it. The draft, in full and ready to paste: never only
where it was saved. The `what_works.py event` line from step 7, when there is one. The recommendation on whether
the thread is worth continuing at all. Any action owed outside the thread, with
a date.

If the person is a genuine mismatch, say so instead of drafting something
optimistic. A polite two-line exit preserves the relationship at zero cost.

Once per session for messages, end with one short line inviting change: "Anything about
the tone or the wording you'd have different? It sticks from now on." What they say goes
through CLAUDE.md, "Learning the person".
