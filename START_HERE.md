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

Go to [claude.ai/code](https://claude.ai/code), start a new session, and choose your copy as
the repository.

The first time only, change two settings so it can make PDFs and reach job boards. Open the
cloud environment menu in the session's title bar and click **Edit**:

- **Setup script:** copy and paste this line exactly. You do not need to understand it: it
  installs the tools that turn your resume into a PDF, once, and they are kept for next time.

  ```
  apt-get update -qq && apt-get install -y --no-install-recommends texlive-luatex texlive-latex-extra texlive-xetex texlive-fonts-recommended poppler-utils && pip3 install --upgrade cffi && pip3 install pytest pypdf pyyaml openpyxl ruff
  ```

- **Network access:** the search has to reach job boards. Choose a level that allows general
  internet access, or keep a limited level and add these under **Allowed domains**:
  `linkedin.com`, `www.linkedin.com`, `freehire.me`, `boards-api.greenhouse.io`,
  `api.lever.co`, `api.ashbyhq.com`, `myworkdayjobs.com`. Leave **Allow package managers**
  ticked. The details are in
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
- **"Who should I talk to at Acme?"** finds people worth contacting and drafts a first note.
- **"What do I owe?"** lists replies and follow-ups that are due.
- **"Prep me for my interview at Acme"** gives you likely questions and your best answers.
- **"I got an interview"** or **"they replied"** updates the record and says what is next.

You do not need to remember any commands. If you react to something ("too formal", "not this
kind of company"), it remembers for next time.

**Which model to pick.** In the model menu, the strongest model (Opus today) is worth it for
writing applications, interview prep and setting up; the balanced one (Sonnet) is enough for
searching and keeping track. You do not have to remember this: Claude says so in one line
when the model you are on is more, or less, than a task needs.

Updates to the app reach your copy on their own, at the start of each session. Everything
about you stays in your copy, in the `profile/` folder, and is never sent back.

A short daily brief is optional, in a chat or as a phone notification;
[automation/README.md](automation/README.md) sets it up, and Claude can do most of it for you.

---

If something goes wrong, tell Claude what you see. It can read this repository's own
documentation and will say what to change and where.
