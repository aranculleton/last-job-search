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
your computer's password. On a phone or the web nothing is installed, and you paste the one
or two profiles that matter most, or reach the chat on your computer from your phone. If you
have a computer you can use for this, choose the computer: it does more for you.

- **A computer:** go to [On your own computer](#on-your-own-computer) below now, and skip
  the rest of this step.
- **A phone or the web:** carry on here.

Go to [claude.ai/code](https://claude.ai/code), start a new session, and choose your copy as
the repository.

The first time only, change two settings of the cloud environment so it can make PDFs and
reach job boards:

<!-- claude-surface: cloud-environment -->
Change the cloud environment's settings. At the time of writing: on the new-session screen
at claude.ai/code, open the environment selector under the message box and edit the
environment (in a running chat: the caret after its title, then Edit cloud environment); its
Setup script and Network access are the two settings (official page:
https://code.claude.com/docs/en/cloud-environments). Checked 2026-10-18.
<!-- /claude-surface -->

- **The setup script:** copy and paste this line exactly. You do not need to understand it:
  it installs the tools that turn your resume into a PDF, once, and they are kept for next time.

  ```
  apt-get update -qq && apt-get install -y --no-install-recommends texlive-luatex texlive-latex-extra texlive-xetex texlive-fonts-recommended poppler-utils && pip3 install --upgrade cffi && pip3 install pytest pypdf pyyaml openpyxl ruff
  ```

- **The network setting:** the search has to reach job boards. Choose full internet access, or
  a custom list that keeps the default package managers and adds these allowed domains:
  `linkedin.com`, `www.linkedin.com`, `freehire.me`, `boards-api.greenhouse.io`,
  `api.lever.co`, `api.ashbyhq.com`, `*.myworkdayjobs.com`, and `api.openalex.org` if your
  field publishes research papers. The details are in
  [the cloud environment docs](https://code.claude.com/docs/en/cloud-environments#network-access).

Save, and start a new session so the settings apply. If you skip this, Claude can still
help, but it will stop and say what is missing the first time it needs it.

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
- **"Check my email"**, **"make me a dashboard"** or **"what should I learn?"** do what they
  say. It can also read your LinkedIn job alerts into each search, use your own resume
  template, or start your search over. You connect Gmail yourself, once, at
  [claude.ai/customize/connectors](https://claude.ai/customize/connectors).

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

Everything works the same in a chat on your computer in the Claude desktop app, with your
copy on your own disk, and the desktop app's own browser is where people's LinkedIn profiles
are read. The brief runs in the cloud, so it arrives when your computer is off. Signed in
with an Anthropic API key instead of a plan, everything works except the brief: scheduled
tasks and cloud chats need a paid plan.

1. Steps 1 and 2 above. Step 2 is what lets the brief, in the cloud, read your copy.
2. Install the Claude desktop app: [claude.ai/download](https://claude.ai/download).
3. Put your copy on your computer, then start a chat there on it:

   <!-- claude-surface: clone-copy -->
   Put your copy on your computer. At the time of writing: on github.com/you/of your copy,
   choose Code, then Open with GitHub Desktop, and choose where to keep it (official page:
   https://docs.github.com/en/desktop/adding-and-cloning-repositories/cloning-a-repository-from-github-to-github-desktop).
   Checked 2026-10-18.
   <!-- /claude-surface -->

   <!-- claude-surface: local-chat -->
   Continue this in a chat on your computer. At the time of writing: open the Claude desktop
   app, go to its Code tab, choose Local and then the folder of your copy (official page:
   https://code.claude.com/docs/en/desktop-quickstart). Checked 2026-10-18.
   <!-- /claude-surface -->
4. Say "set me up". Claude checks what your computer has and installs what it can itself.
   What is left is one list, one command each, marked where it asks for your computer's
   password or signs you in; paste each into Terminal (PowerShell on Windows), once. If your
   computer has no Python at all, that list cannot run, so here it is: on a Mac,
   `xcode-select --install` (it asks for your password); on Windows,
   `winget install Python.Python.3.12`. Until LaTeX is in, Claude can search and write but
   cannot make or check the PDFs.
5. Say "set up my brief". Claude checks whether you already have one and never makes a
   second. It always runs in the cloud, so it arrives when your computer is off. Claude makes
   it itself where the chat has the tool for it; otherwise it asks you to do this, once:

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

**How your work reaches GitHub from here.** A chat on your computer has no GitHub tools of
its own, so Claude uses GitHub's command line, `gh`: step 4's list installs it, and
`gh auth login` (yours, once) signs it in through your web browser. Claude then works on a
branch and lands it on master itself: it merges master into the branch first
(`git fetch origin master && git merge origin/master`, so two chats' changes to your tracker
or contact book are merged row by row on your computer), runs the checks, then
`gh pr create --base master --head <branch>` and `gh pr merge <number> --merge --delete-branch`.
You do none of it; it is written here so you know what it is doing.

**Already using it in the cloud?** Nothing moves: open your copy locally as in step 3 and
carry on. Cloud and local chats can be mixed, because your copy on GitHub is what they share,
and Claude merges each chat's work into it, so the brief sees it. Never archive the chats
your brief is bound to.

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
