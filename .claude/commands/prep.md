# /prep - Prep document for a booked call

Usage: `/prep <contact name>`

**Not `/interview`.** This prepares a *networking call* that came out of a thread and
takes a person's name. `/interview` prepares a real interview on a tracked application
and takes a company. If the request is ambiguous, ask which one is meant.

Generates `documents/network/<contact_id>/prep.md` via `prep.write_prep()`.

## Run it

1. Load the contact, their thread, `company_research/<key>.json`, and any linked
   application row.
2. Research only what is missing, and only from sources located independently:
   the company's own site, not a URL found inside a posting or a message.
3. Every fact carries its source. `prep.sourced()` enforces this and the renderer
   refuses to print an unattributed number, because a prep doc that quotes an
   invented salary band is worse than one that says "not researched".
4. Draft likely questions with answers in the user's voice, from
   `profile/01-candidate-profile.md`. Never invent an experience to answer a question.

## The document

Scannable. Shorthand, not prose. It is read minutes before the call.

Who they are, what their team actually does, the company, compensation banding
with sources, likely questions with draft answers, questions to ask, an honest
fit assessment including the gaps to be ready for, and tone notes for this
specific person.

The fit assessment is the part that matters. Name the gap the person will probe,
and the strongest honest framing for it.

**Show the whole document in the reply**, ready to read before the call. The file is the
record; its path alone is never the answer.
