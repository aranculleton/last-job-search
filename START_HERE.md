# Start here

This is a job search that Claude runs for you, end to end: it finds postings, scores them
against you, writes a resume and cover letter for the ones you pick, checks them, and helps
you reach the right people. It never sends anything. You do that.

You need a GitHub account and Claude Code, which has no free tier: these steps use it through
a Claude subscription. Five steps, about fifteen minutes, and no coding. Using a different agent
tool instead? Start at [AGENTS.md](AGENTS.md).

---

## 1. Make your own private copy

On this page on GitHub, click the green **Use this template** button, then **Create a new
repository**.

- **Owner:** you.
- **Repository name:** anything, for example `my-job-search`.
- Tick **Private**. This matters: your copy will hold your work history, your salary
  expectations and the names of people you talk to.
- Click **Create repository**.

**Never fork this repository.** A fork of a public repository is public too, and everything
you put in it would be visible to anyone.

## 2. Let Claude see your copy

Go to [claude.ai/connect-github](https://claude.ai/connect-github) and connect your GitHub
account. When GitHub asks which repositories the Claude app may access, choose **Only select
repositories** and pick the copy you just made.

## 3. Open it in Claude Code

First, one question: **will you mostly work on a computer, or on your phone or the web?**
Finding people, searching for jobs and writing work the same everywhere. On a computer, in
the Claude desktop app, Claude can also read each person's LinkedIn profile before writing to
them, and your files sit on your disk; a few free tools go on once, and one or two ask for
your computer's password. On a phone or the web nothing is installed, but profiles cannot be
read there: you reach the chat on your computer from your phone. If you have a computer you
can use for this, choose the computer: it does more for you.

**Two chats work best.** One on your computer, for everything you do: job searches, resumes,
interview prep and networking. And your brief, in the cloud: it follows up for you and
arrives even when your computer is off. Claude sets the brief up when you say "set up my
brief".

- **A computer:** go to [On your own computer](#on-your-own-computer) below now, and skip
  the rest of this step.
- **A phone or the web:** carry on here.

Go to [claude.ai/code](https://claude.ai/code), start a new chat, and choose your copy.

**Once, so it can reach job sites (recommended, about a minute).** A cloud chat runs on a
computer in the cloud that can only reach a few websites until you allow more. Claude calls
that computer's settings an "environment". Do this from your first chat:

<!-- claude-surface: cloud-internet -->
Let this chat reach job sites. At the time of writing (checked 2026-10-20; official page:
https://code.claude.com/docs/en/cloud-environments):
1. At the top of this chat, open the small arrow after its title and choose Edit cloud
   environment.
2. Set Network access to Full, then save.
3. That is all: it reaches this chat within about a minute, with no new chat. Say "done" and
   I'll search again.
<!-- /claude-surface -->

**Optional, so each chat starts faster.** Without this, Claude installs the tools that turn
your resume into a PDF at the start of a chat, which takes a few minutes. Copy this line; you
do not need to understand it:

```
apt-get update -qq && apt-get install -y --no-install-recommends texlive-luatex texlive-latex-extra texlive-xetex texlive-fonts-recommended poppler-utils && pip3 install --upgrade cffi && pip3 install pytest pypdf pyyaml openpyxl ruff
```

<!-- claude-surface: cloud-setup-script -->
Make each new chat start with the PDF tools in place. At the time of writing (checked
2026-10-20; official page: https://code.claude.com/docs/en/cloud-environments):
1. At the top of this chat, open the small arrow after its title and choose Edit cloud
   environment.
2. Paste the line into Setup script, then save.
3. It applies from your next new chat. In this one, Claude installs the same tools itself.
<!-- /claude-surface -->

Skip both and Claude still works: it says, in a line, what it needs the first time it needs
it. (Want to allow only the job sites rather than every website? [SETUP.md](SETUP.md) lists
them.)

## 4. Say "set me up"

Claude checks your copy is private, then asks you about yourself in plain words: where you
live and would work, your right to work there, the kind of work you want, what you have done,
your salary hopes, and anything you will not do. If you have a resume or CV, paste it in and
it asks only about what is missing.

You will never be asked to name a job board or set a value. Claude researches your market
itself (which boards cover your city, what employers there post where, what pay looks like,
how documents are written locally) and writes your profile. At the end it makes a test resume
and cover letter so you can see the result.

## 5. Use it

Just talk to it. For example:

- **"Find me jobs"** gives you a scored shortlist with links, then asks which to take further.
- **Paste a posting** (or a link) and it writes a tailored resume and cover letter, and checks
  them.
- **"Who should I talk to at Acme?"** finds people worth contacting and drafts a first note,
  inside LinkedIn's limits (50 connection requests a week). It reads someone's profile in
  your own browser only if you agree to that, and starts with people you already know if you
  give it your LinkedIn connections export.
- **"What do I owe?"** lists replies and follow-ups that are due.
- **"Prep me for my interview at Acme"** gives you likely questions and your best answers.
- **"I got an interview"** or **"they replied"** updates the record and says what is next.
- **"Make me a dashboard"** or **"what should I learn?"** do what they say. It can also use
  your own resume template, or start your search over. It never asks for your email: new jobs
  and what is due reach you in Claude.

You do not need to remember any commands. If you react to something ("too formal", "not this
kind of company"), it remembers for next time, until you say you have changed your mind.

**Which model to pick.** In the model menu, the strongest model (Opus today) is worth it for
writing applications, interview prep and setting up; the balanced one (Sonnet) is enough for
searching and keeping track. You do not have to remember this: Claude says so in one line
when the model you are on is more, or less, than a task needs.

Each new version of the app reaches your copy by itself the first day you use it, in a new
chat or one you kept open. Nothing about you is ever sent back.

For a twice-weekly brief of what you owe and what changed, say **"set up my brief"**: Claude
sets it up ([automation/README.md](automation/README.md)).

## On your own computer

**Recommended if you have a computer.** It can read people's LinkedIn profiles for you, and
no website is blocked. Your brief still runs in the cloud, so it arrives when your computer
is off. You need a Claude plan (Pro, Max, Team or Enterprise).

1. Steps 1 and 2 above: your private copy, and letting Claude see it.
2. Put your copy on your computer:

   <!-- claude-surface: clone-copy -->
   Put your copy on your computer. At the time of writing (checked 2026-10-20; official
   page:
   https://docs.github.com/en/desktop/adding-and-cloning-repositories/cloning-a-repository-from-github-to-github-desktop):
   1. Install GitHub Desktop from github.com/apps/desktop and sign in with your GitHub
      account.
   2. On your copy's page on github.com, choose Code, then Open with GitHub Desktop.
   3. Choose where to keep it (your Documents folder is fine), then Clone.
   <!-- /claude-surface -->
3. Start a chat on it:

   <!-- claude-surface: local-chat -->
   Continue this in a chat on your computer. At the time of writing (checked 2026-10-20;
   official page: https://code.claude.com/docs/en/desktop-quickstart):
   1. Install the Claude desktop app from claude.ai/download if you do not have it, and sign
      in.
   2. Open its Code tab, at the top.
   3. Under the message box, choose Local, then Open folder beside it, and pick the folder
      GitHub Desktop made.
   4. Say "set me up" there ("carry on" if you set up in the cloud before). It checks what
      your computer needs and installs most of it itself.
   <!-- /claude-surface -->
4. Claude then lists anything your computer still needs, one command each, and runs most of
   them itself. The few marked as asking for your password are yours: paste each into
   Terminal (PowerShell on Windows), once. One of them signs GitHub's command line in, so your
   work is saved to your copy on GitHub, where your other chats and your brief see it. If your
   computer has no Python at all, that list cannot run, so here it is: on a Mac,
   `xcode-select --install`; on Windows, `winget install Python.Python.3.12`.
5. Say "set up my brief". Claude checks whether you already have one and never makes a
   second. It makes it itself where it can; otherwise it asks you to do this, once:

   <!-- claude-surface: routines-cloud -->
   Make the brief in the cloud. At the time of writing: type /schedule in a chat on your
   computer and answer its questions; or open claude.ai/code/routines in a browser and
   choose New routine; in the desktop app's Code tab it is Routines, then New routine, then
   Cloud (official page: https://code.claude.com/docs/en/routines). Checked 2026-10-18.
   <!-- /claude-surface -->

   A scheduled task that runs on your computer is never used for the brief:

   <!-- claude-surface: routines-local -->
   A desktop scheduled task made with Local runs on the computer, and only while the desktop
   app is running and the computer is awake, so it is never used for the brief. Checked
   2026-10-18.
   <!-- /claude-surface -->

**Already using it in the cloud?** Nothing moves: do steps 2 and 3 above, and say "carry on".
Cloud chats and chats on your computer share your copy on GitHub. Never delete the chat your
brief runs in. What Claude does with git and GitHub on your computer, if you are curious, is
in [RUNBOOK.md](RUNBOOK.md), step 4.

**On a phone, or in a browser,** there is nothing to install: use claude.ai/code as in step 3.
Finding people works there. To have profiles read too, paste the one or two that matter most,
or use the chat on your computer from your phone:

<!-- claude-surface: remote-control -->
Use the chat on your computer from your phone. At the time of writing: in the chat on your
computer, type /remote-control (in a terminal, run claude remote-control in the folder of
your copy), then open that chat from the Claude app on your phone (official page:
https://code.claude.com/docs/en/remote-control). Checked 2026-10-18.
<!-- /claude-surface -->

The brief is set up from a chat there, so a phone is enough for that too.

---

If something goes wrong, tell Claude what you see. It can read this repository's own
documentation and will say what to change and where.
