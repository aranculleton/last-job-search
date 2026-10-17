# /prep - Prep document for a booked call

Usage: `/prep <contact name>`

**Not `/interview`.** This prepares a *networking call* that came out of a thread and
takes a person's name. `/interview` prepares a real interview on a tracked application
and takes a company. If the request is ambiguous, ask which one is meant.

Generates `documents/network/<contact_id>/prep.md` via `prep.write_prep()`.

## Run it

1. Load the contact, their thread, `company_research/<key>.json`, and any linked
   application row. `python3 tools/network/prep.py "<contact>"` does all of it, says when
   the research is past `RESEARCH_FRESH_DAYS` (`tools/company_research.py`), and adds what
   the rest of the search holds: with no application there, the roles open at their
   employer that scored `prep.OPEN_ROLE_FIT` or more; with one, the company fact the
   letter used and any gap it conceded, so the call says what the employer was already
   told.
2. Research only what is missing, and only from sources located independently:
   the company's own site, not a URL found inside a posting or a message.
3. Every fact carries its source. `prep.sourced()` enforces this and the renderer
   refuses to print an unattributed number, because a prep doc that quotes an
   invented salary band is worse than one that says "not researched".
4. **Read what they have taught it**: `python3 tools/learned.py brief questions` (and
   `brief people`). The questions, depth and tone they have asked for outrank the defaults
   here.
5. Draft likely questions with answers in the user's voice, from
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

Once per session for prep documents, end with one short line inviting change: "Anything
about the questions or the depth you'd have different? It sticks from now on." What they
say goes through CLAUDE.md, "Learning the person".
