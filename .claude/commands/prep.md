# /prep - Prep document for a booked call

Usage: `/prep <contact name>`

**Not `/interview`.** This prepares a *networking call* that came out of a thread and
takes a person's name. `/interview` prepares a real interview and takes a company: on a
tracked application, or on a process with no application, such as a referral that led to
a recruiter's call. **A recruiter screen on a live hiring process is an interview stage**,
referred or not, and goes to `/interview` (whose Step 0 registers the process when there is
no application). When `prep.py` prints that this call is a stage of a live process, say so
and run `/interview` instead; this file then stays the briefing on the person, and links to
the process's own document rather than repeating it. If the request is ambiguous, ask
which one is meant.

Generates `documents/network/<contact_id>/prep.md` via `prep.write_prep()`.

## Run it

0. **The model first.** `python3 tools/model_guide.py prep --on "<this session's model>"`
   prints nothing when the model fits; otherwise its one line goes first in the reply, and
   the work carries on.
1. Load the contact, their thread, `company_research/<key>.json`, and any linked
   application row. `python3 tools/network/prep.py "<contact>"` does all of it, says when
   the research is past `RESEARCH_FRESH_DAYS` (`tools/company_research.py`), and adds what
   the rest of the search holds: with no application there, the roles open at their
   employer that scored `prep.OPEN_ROLE_FIT` or more; with one, the company fact the
   letter used and any gap it conceded, so the call says what the employer was already
   told.
2. Research only what is missing, and only from sources located independently:
   the company's own site, not a URL found inside a posting or a message. **When
   `prep.py` prints `RESEARCH FIRST`** (a call booked, or due within
   `prep.RESEARCH_BEFORE_DAYS`, with nothing researched about the employer), it is not
   optional: run the `employer-researcher` subagent, then `prep.py` again, before the
   document goes to the person. A prep for a booked call whose "The company" says "not
   researched" is not finished.
3. Every fact carries its source. `prep.sourced()` enforces this and the renderer
   refuses to print an unattributed number, because a prep doc that quotes an
   invented salary band is worse than one that says "not researched".
4. **Read what they have taught it**: `python3 tools/learned.py brief questions` (and
   `brief people`). The questions, depth and tone they have asked for outrank the defaults
   here.
5. **Rewrite every answer to be said aloud**, in the file, under its question: full,
   natural sentences in the first person, the way the person talks (contractions welcome),
   no fragments, no "At <Employer>:" openers, keeping the `(source: ...)` after it. The
   tool places profile wording against each question and marks the summary
   `[raw profile wording: ...]`, because profile prose is written, not said. The personal
   narrative is an arc to tell in their own words and is never pasted. Never invent an
   experience to answer a question. Then:
   ```bash
   python3 tools/network/prep.py "<contact>" --check
   ```
   It exits 1 while any answer is raw profile wording or reads as written (third person, a
   resume verb opening, a label and a colon). Rewrite until it passes; never present an
   answer it rejects. Rewritten answers are kept when the document is rebuilt, by you or by
   the brief's `--stale-only`.

## The document

Scannable, and in two registers. Facts are shorthand, not prose: it is read minutes
before the call. Answers are the opposite: whole spoken sentences, because they are said.

Who they are, what their team actually does, the company, compensation banding
with sources, likely questions with draft answers, questions to ask, an honest
fit assessment including the gaps to be ready for, and tone notes for this
specific person. Who they are decides more than the tone: for a recruiter, or anyone on a
hiring process, work authorization is said in the person's employer-facing wording, and a
referrer is the answer to "how do you know them" rather than the opening line, because
the recruiter already knows who routed it. For a cold peer introduction, the referrer's
name leads.

The fit assessment is the part that matters. Name the gap the person will probe,
and the strongest honest framing for it.

**Show the whole document in the reply**, ready to read before the call, and send the
file with the session's file-sending tool (SendUserFile or its equivalent). The file is the
record; its path alone is never the answer.

**It is rebuilt when anything it rests on moves.** A prep counts as stale when, since it was
written, the contact's status, next action or its date changed, a message with them was
logged, the employer's research arrived or changed, the application or process there
changed, or the call came within two days with nothing researched. The morning brief runs
`python3 tools/network/prep.py --stale-only`, so a prep written while waiting for a reply
never reaches a booked call still saying "wait". Answers someone rewrote are kept; what the
tool wrote is written again from the profile as it is now.

Once per session for prep documents, end with one short line inviting change: "Anything
about the questions or the depth you'd have different? It sticks from now on." What they
say goes through CLAUDE.md, "Learning the person".
