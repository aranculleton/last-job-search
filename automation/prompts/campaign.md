# A chat just for one employer: the campaign

When a live process reaches a booked interview (or a referral turns into a recruiter's
call), `interview_pack.py pack --write` offers the person, once, a chat of its own for that
employer. This file is that chat's instructions, read from master at the start of every
session there, so improving them is an ordinary pull request.

## Starting it (the chat that made the offer)

On a yes, in a cloud chat that has the tool: `create_session` on the person's **private**
repo (never the app's), titled `Job search: <Employer> campaign`, with this as its prompt:

> Read `automation/prompts/campaign.md` from master and follow it, for `<Employer>`, the
> `<role>` process. Its document is `<the folder>/interview_prep.md`.

Without that tool (a chat on the person's computer), give them the steps to open a new chat
on their computer (`python3 tools/claude_surfaces.py steps local-chat`) and that prompt in a
code block to paste there. Nothing else: the new chat makes its own folder itself
(`python3 tools/sync_app.py --worktree <employer>`, CLAUDE.md), and they are never told how. Then, either way: `python3 tools/interview_pack.py campaign "<Employer>" --yes
"<the chat's title or id>"`. From then on `open_actions.py --due` and the brief show that
employer as handled by its campaign chat, and the rest of the search leaves it alone. On a
no: `campaign "<Employer>" --no`, and it is never offered again for this process.

## Every session in the campaign chat

1. **Start like any session** (CLAUDE.md, "Start of every session"): master, then
   `python3 tools/sync_app.py --if-stale --on "<this model>"`, in this chat's own folder: a
   look at the app, never an update unless the person says so.
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
8. **Land on master** at the end of every session (CLAUDE.md, "Master is the trunk").

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
