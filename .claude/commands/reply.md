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

4. **Get the guidance.** `reply.guidance()` gives the move, the target length
   derived from their message, what not to do, and any action owed outside the
   thread (send an email, book a slot).

5. **Draft, then validate.** `compose.validate()` plus `tone.restate_ratio()`
   against their message. A high ratio means the draft is parroting them back,
   which is the most common tell of a machine-written reply. Rewrite it.

6. **Record.** Append both messages to `network_threads.csv`. Status derives from
   the messages, so it updates itself.

## Present

The scenario and the evidence for it. The draft. The recommendation on whether
the thread is worth continuing at all. Any action owed outside the thread, with
a date.

If the person is a genuine mismatch, say so instead of drafting something
optimistic. A polite two-line exit preserves the relationship at zero cost.
