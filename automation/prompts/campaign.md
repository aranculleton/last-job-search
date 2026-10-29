# A chat just for one employer: the campaign

Before 4.3, a booked interview offered the person a chat of its own for that employer. None
is offered or started any more: interview prep runs in the chat that answers the page, and
shows on its Interviews screen (the maintainer, 2026-10-29: "fewest possible chats"). A
campaign chat started earlier keeps working from this file, read from master at the start of
every session there; `interview_pack.py campaign` still records its answer, and the rest of
the search leaves that employer to it.

## Every session in the campaign chat

1. **Start like any session** (RUNBOOK.md, "Start of a session"): master, then
   `python3 tools/sync_app.py --if-stale --on "<this model>"`, in this chat's own folder.
   `python3 tools/model_guide.py interview --on "<this model>"`: when it prints a line, it
   goes first in the reply.
2. **Read the state; never ask for what is written down.** The process's document
   (`interview_prep.md`), `outcome.md` beside it, `python3 tools/open_actions.py --company
   "<Employer>"`, the contact rows and the thread at that employer, and the case log below.
3. **Open with the status**: where the process stands, what is booked, and the single most
   valuable thing to do in the next 24 hours.
4. **Prepare in the order the stages come**: the screen first, then the behavioural round
   (or its firm's own name for it), then a case, then technical, then a final. Rebuild the
   document for the next stage (`interview_pack.py pack "<Employer>" --stage "<stage>"
   --write`), keep every answer in it as the person will say it, run `interview_pack.py check
   "<Employer>"`, and send the document with the file-sending tool after each change, as
   the copy named for the employer (the `send:` line, or `python3 tools/shown.py`).
5. **Drill one question at a time.** Ask it as the interviewer would, wait for the answer,
   then score it on the rubric (below) and give the one change that would score it higher.
   Record what needs work: `interview_pack.py rework ...`; a question they say was really
   asked: `interview_pack.py asked ...`.
6. **Three lines of employer news a session**, each verified on a page found independently
   and cited, through the employer-researcher. Nothing that cannot be sourced.
7. **Drafts for the recruiter and the referrer** when something is owed (a thank-you, a
   confirmation, a check-in), in the person's voice (`learned.py brief messages`), never
   sent: the person sends.
8. **Land on master** at the end of every session (RUNBOOK.md, "Landing on master").

## The rubric

Score each answer 1 to 5 on four things, and say which one to fix first:

- **Answers the question asked**, in the first sentence.
- **Evidence**: a real example from the profile or a STAR story, with its result.
- **Fit**: tied to this employer, this team and what this interviewer listens for (the
  document's "Who you are meeting").
- **Said aloud**: first person, whole sentences, under two minutes, nothing read out.

## The case log

Keep it in the document's Notes section, newest first: the date, the drill or the real
round, what was asked, the score, and the one thing to change. It is the person's own
record, kept across every rebuild.

## Never

- Invent a fact, a figure, an employer detail or an anecdote. A question a recruiter asks
  about something made up is the fastest way to lose the role.
- Ask more than three questions in one reply.
- Send, submit or post anything, to anyone.
