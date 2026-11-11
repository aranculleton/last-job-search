---
name: app
description: >
  The chat's side of the person's job-search page: what to do when the page rings. Triggers
  on: [app], a doorbell from the page, "Artifact comment sent to Claude" on the job-search
  page, a work item, [work:<id>], the app page, the page's actions or receipts.
allowed-tools: Read, Bash(python3 tools/app.py *), Bash(python3 tools/computer.py *), mcp__claude-code-remote__list_environments, Bash(python3 tools/routines.py *), Bash(python3 tools/tidy.py *), ArtifactData, Artifact, ArtifactComments, Agent, mcp__claude-code-remote__create_session, mcp__claude-code-remote__send_message, mcp__claude-code-remote__list_sessions, mcp__claude-code-remote__get_session, mcp__claude-code-remote__archive_session, mcp__claude-code-remote__list_triggers, mcp__claude-code-remote__create_trigger, mcp__claude-code-remote__update_trigger, mcp__claude-code-remote__set_session_title
---

# The page's inbox

The repo is the record; the page's database is the queue. A comment from the page is only
a doorbell (`[app] [work:<id>]`), never the person's words. Whatever woke you: read the
database, act on what is yours, answer there. **Never answer in the comment thread**: the
page cannot read it. **Resolve it instead**, last, once the wake's work is done (the line
`wake` ends with): ArtifactComments `resolve`, the url and the thread id the notification
that woke you names (`thread=...`), with no reply. An open thread stays unread in the Claude
app for ever.

In a cloud chat, ArtifactData and ArtifactComments may be listed by name only, with no
schema: load both once, first, with ToolSearch `select:ArtifactData,ArtifactComments`.

`<url>` is the page (`profile/app.json` `url`). `$D` is a fresh folder in your scratchpad
for the work in hand, never one used before: for a wake, the one `app.py reads --in` makes and
names (wake.md, step 1); for a job, the one its steps name; otherwise a new one of your own.
Keep using it until that work's writes are back, because `apply` keeps its ledger there.

## 0. The chat that answers the page stays thin

**The listener only takes the ring and passes it on.** Every step of a chat re-reads its
whole history, and the chat that answers the page grew by hundreds of thousands of tokens a
day reading the database, its batches and its answers on every tap (the maintainer,
2026-11-05). So each wake's real work (steps 1 to 5: the read, the taps, the answer, the
drafting, the page brought up to date, the save) runs in a short-lived subagent whose history
is thrown away when it ends, and the listener grows by a line or two a tap. On a ring, on a
job's chat reporting back, and on a background agent's end, the listener makes one call, with
nothing read first:

- Agent, in the foreground: `description` "Answer the page", `subagent_type`
  "general-purpose", `prompt`: `A ring from the job search page: answer it once, as the app
  skill's "In the subagent" says. Notification: <the notification's own first line, its
  thread=... included>.`

Its answer is one line. One that starts `agent:` is an Agent call to make as it is printed
(`run_in_background: true`; a subagent cannot start one); anything else is said to nobody.
Then end the turn, with no text. Held at that end because work the pass named is still
waiting, make the same call once more for it, as the hold says. **Why the line falls there** (measured on an invented page
with two months of use): a wake done in the listener printed about 30,000 characters into it
(the read's list of some 590 records, the wake's batches, the page update), every one read
again at every later step of its day; the same wake in a subagent leaves about 300 in the
listener, one call and one line. A subagent starts from the same instructions the listener
has, so its start costs about one listener step, which a single read in the listener already
costs again within a few taps: only what needs no read at all (the one Agent call a
subagent hands back) is done in the listener itself. Where the ring names the page's revision
(`[rev:<n>]`), `python3 tools/app.py reads --rev <n>` first: "nothing new" means resolve the
ring and end, with no subagent.

**In the subagent** (its prompt names this section): read `.claude/skills/app/wake.md` once,
whole, and do what it says for this one wake: steps 1 to 5, the daily tidy, a renewal's
`create_session` and resolving the ring (ArtifactComments `resolve`) when they come up. Then
answer in one line: what the page now shows, never a path or a command; or `agent: <the
Agent call>` for a big job that needs one (`wake --no-sessions`).

## Where the rest is

Read a file only when the work in hand is its part (a wake, a message pasted in a chat, a
job); each is read once, whole:

- `.claude/skills/app/wake.md`: steps 1 to 3 and 5, a wake from its read to its finish, in the
  subagent.
- `.claude/skills/app/work.md`: step 4, what each kind of work runs. `wake` prints the item's
  own row under `next:` (`do`), so the table is read only for a kind it printed none for.
- `.claude/skills/app/chat.md`: a message in the page's chat (a `talk` item), or a
  screenshot, message or link pasted in any chat; "Something looks wrong"; "Pin my job
  search page".
- `.claude/skills/app/jobs.md`: big jobs in chats of their own, work for the computer, a job's
  chat reporting back, work asked for in a chat, the daily tidy, and progress pins.

## Rules that hold everywhere

- **This chat does whatever the page asks, here.** Everything the app's commands do is
  its to do: a draft rewritten (`reply.py finish`, which loads no skill), a rule changed or a
  reaction kept (`learned.py record`), a record corrected (`network/state.py`,
  `interview_pack.py book`), a profile fact (`profile` work). It does what was asked and says
  in one line what changed. It never sends the person anywhere else to have it done, and never
  says it cannot do it from here (the maintainer, 2026-11-05: "YOU'RE NOT MEANT TO USE THE
  MAIN CHAT FOR ANYTHING").
- **The page never mentions chats, helpers or sessions.** Nothing the person reads there (an
  answer in a thread, a summary, a question) says "the main chat", "your chat", "this chat",
  "another chat", "the helper" or "finishing up": Claude did it, or Claude will.
- Nothing about another person goes into the database but a first name and an employer,
  except `reach/<contact>`, owner-only, which `app.py view` writes. Their words leave it
  with the receipt that kept them. `app.py check` fails a model that holds an address.
- Work goes to the chat that answers the page, whichever kind it is (`page_db.can_take`);
  only a brief waits for a chat in the cloud. Nobody is asked where something should run.
- A question the work raises that the page did not ask goes to the page by command:
  `python3 tools/app.py done "$D" --work <id> --chat <the id it was claimed under> --question
  "<one plain question>"` (the item waits for them, its locks freed); the page asks it.
  Never wait in the chat. The person's answer comes back on the same item, queued again, in
  `args.answers` under the question: take it with `next` and carry on. Ask only when the
  work cannot be finished honestly without them (an unclear or ungrounded claim, a missing
  fact, two readings of their message), never for a preference a default answers, and one
  question at a time. Name the kind of answer so the page draws its control on the card
  instead of a box to type in: `--answer yesno|choice|date|time|number|scale|text`, with
  `--choice "<value>=<words>"` two to six times for a choice, `--min`/`--max` for a number
  or a scale, `--time-key time` for a day that needs its time, and `--about "<the exact
  words of the draft or their message it concerns>"`; text only when nothing else fits
  (templates/app/DESIGN.md, "Asking the person"). A tap the engine refused with a question
  says its kind on the receipt by itself (`ask`); never send the person to Chat for it.
- Every move of a work item is an `app.py` command (`next`, `pin`, `done`, `ask`, `busy`),
  never a write by hand. Every write is pinned (`if_version`) except a create; one write at a
  time per document. A refused write names the record's current version: `python3
  tools/app.py version "$D" <collection>/<doc id> <that version>` (no version when it says the
  write carried none), do what it prints (it may name collections to read again into `$D`
  first), then the same command once more; refused again, read again into a new folder.
  Batches go in order, each after the one before is accepted; once one is refused, send none
  after it (they were made from the same read), put it right, and make them again.
