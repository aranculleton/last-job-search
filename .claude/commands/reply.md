# /reply - Draft a reply inside a live thread

Usage: `/reply <contact name or company>`, then paste their message.

## Run it

1. **Load the thread.** `state.load_threads()` for that contact. The thread
   history is the context; do not re-research the person unless something
   material has changed.

2. **Classify.** `reply.classify(inbound, history, today)` returns the scenario,
   a confidence and the matched evidence. Show the user which scenario and why,
   because a misread scenario produces a confidently wrong reply.

   **When their message needs no answer** ("I'll get back to you next week", "will let
   you know"), draft nothing either: log it inbound (step 6), then `python3
   tools/network/state.py no-reply <contact_id> --why "<what they said>"`, so no reply is
   owed until they write again or the day to look again (their follow-up rule, or
   `--look-again <date>`). A short thanks is the person's call, never a reply owed.

   **When the scenario is `auto_reply`** (an out-of-office, a "no longer with the
   company"), draft nothing. Log it inbound with scenario `auto_reply` (step 6) and tell
   the person what `reply.guidance()` gives as the next action: wait until they are back,
   or close the contact and find who holds the role now. It is not a reply.

3. **Check it is worth continuing.** `reply.should_continue()`. After two
   explicit nos, recommend a warm close instead of a reply. Say so plainly.
   A "not hiring, but happy to chat" is not a no, and a thread at `call_booked` or
   `referral_in_progress` is never stopped.

   **When the scenario is `gone_quiet`** (nothing pasted, and we spoke last), run
   `reply.nudge_due(rows, today)` before drafting anything. If it is not due, or the
   nudges the person's follow-up rule allows have gone out (one, unless MAX_UNANSWERED in
   profile/networking.py allows more), draft nothing and say why: one more costs more
   than it recovers. If it is due, code drafts it first: `python3 tools/followup_drafts.py
   --contact <contact_id>` gives the nudge the state supports (a draft on the row or in an
   earlier pack, or a posting the search found at their employer), already through
   `compose.validate()` and `compose.advise()`. Show a clean one as it is; only when it says
   needs writing is the nudge `compose.nudge()` with a new reason to answer, and
   `reply.following_up_is_honest(rows, today)` says whether an apology for the gap is owed.

4. **Read what they have taught it**: `python3 tools/learned.py brief messages --channel
   <channel> --reader <reader>`: the messages they approved first, then the rules, which
   outrank the guidance's defaults. A reply they approve is kept with `learned.py approve`. For a nudge, also `python3 tools/what_works.py brief
   messages --channel <channel>`: the follow-ups that drew replies are the shape to match.
   **Get the guidance.** `reply.guidance()` gives the move, the target length
   derived from their message, what not to do, and any action owed outside the
   thread (send an email, book a slot).

5. **Draft, then validate.** `python3 tools/followup_drafts.py check <file.json>` runs
   the whole gate in one call (`[{"id": "<contact_id>", "text": "<the draft>"}]`):
   `compose.validate()` plus `tone.restate_ratio()` against their message, then
   `compose.advise()`. A high ratio means the draft is parroting them back,
   which is the most common tell of a machine-written reply. Rewrite it. Then
   `compose.advise(draft, "reply", company=<their employer>)`: rewrite what it warns about (a phrase that reads as
   generated, stacked hedges, a claim about them written as fact); a soft exit is allowed
   in a reply. If the person reacts to the draft, the reaction is recorded before the next
   draft (`learned.py record` or `skip`): the composers refuse to draft over one.

6. **Record.** Their message goes into `network_threads.csv` now, by command, with their
   words as they came: `python3 tools/network/state.py received <contact_id> --text-file
   <file>` (`--scenario <the scenario from step 2>`; `--date` when it came another day;
   `--channel` when it came another way than the thread runs). Never by hand. Ours goes in only when
   they say it went, dated the day it went: a draft is not a message, and logging it early
   makes the thread read as waiting on them before anything was sent (the same rule
   `/network` keeps for a first note). Every row carries its full text in `full_text`: a
   message logged without its text can never become an example of what works. Ours is logged
   by command, with the words as sent: `python3 tools/network/state.py message <contact_id>
   --text-file <file>` (a nudge after silence: `state.py nudge <contact_id> --text-file
   <file>`); `--texts <file.json>` takes several at once. A second message to them on a
   day one already went is refused, with the one already logged shown: another chat may
   have answered them first. `--also` logs it when both really went.

   **A resume they asked for** (`send_resume`, or a `referral_offered` that wants one) is
   one of two files, and `reply.guidance()` names both in `which_resume`, beside the next
   action (show it with the action owed outside the thread): for a role they named, one drafted for
   them (`python3 tools/stage_picks.py single <dir> ... --for-contact <contact_id>`, so the
   tracker row and the folder are filed under them; add `--referral-field` when they said
   to apply and name them as the referrer: it goes in through the portal, never to them,
   so no message is logged and RECONCILE asks for none); with no role named, the person's
   current one (`stage_picks.py single <dir> --for-contact <contact_id>` says which and
   records it). When it goes, the message is logged with the file: `state.py message
   <contact_id> --attached <file> --text-file <file>`. A resume sent from another chat is
   never left as a sentence: `state.py` RECONCILE names any that is.

   The log decides three statuses by itself (`state.DERIVABLE`: `not_contacted`,
   `awaiting_reply`, `replied_needs_response`). Everything else is stored on the contact
   row, and this step is what sets it: when the exchange makes it so, set `status` to
   `in_conversation`, `call_booked`, `referral_in_progress` (somebody inside has put the
   candidate's name forward; `throttle.referral_holds()` reads it to hold every cold
   application there) or a terminal one (`gone_cold`, `closed`,
   `converted_to_application`). Then set `next_action` and `next_action_due` to what is owed
   now: the call and its date, the action owed outside the thread from step 4, or, once our
   message has gone and nothing else is owed, the nudge on
   `state.follow_up_on(<the day it went>)` (the person's FOLLOW_UP_DAYS, else six business
   days). The morning
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

End with the line `python3 tools/tips.py reply` prints, if it prints one (it decides when: the first time, then now and then). What they say back
goes through RUNBOOK.md, "Learning the person".
