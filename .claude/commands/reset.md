# /reset - Start a person's search over

You are clearing a person's data out of their repo so they can start again with `/setup`, or
hand the repo on. Everything a person owns is listed in `tools/personal_paths.py`; this
command removes the parts they choose and never touches an app-owned file.

**This command is destructive.** Nothing is deleted until the person explicitly confirms, and
a deletion that has been pushed is still in the repo's history: say so before they confirm.

**In the app itself** (`origin` is `https://github.com/aranculleton/last-job-search`) there is
nothing to reset: the app holds no person. Say so and stop.

---

## Step 0: Parse Scope from Arguments

Check `$ARGUMENTS` for a scope keyword:

- `profile` - removes `profile/`, everything about the person
- `state` - removes the search's state: the tracker, the contact book and its message log, the
  seen-jobs and do-not-target files, and cached company research
- `documents` - deletes the files they placed in, or the search wrote to, `documents/`
- `all` - all three

If `$ARGUMENTS` is empty or does not contain a recognized scope keyword, ask:

> **What would you like to reset?**
>
> - **`profile`** - Removes your profile (`profile/`): who you are, your history, your market
>   settings, your voice. Run `/setup` afterwards to build a new one.
> - **`state`** - Removes your job-search tracker, your contact book and every message logged
>   in it, the record of postings already seen, and cached company research.
> - **`documents`** - Deletes everything in `documents/`: your resume or CV, LinkedIn export,
>   diplomas, references, saved postings, application folders, interview and networking prep,
>   rounds and briefs.
> - **`all`** - All three.
>
> Reply with `profile`, `state`, `documents`, or `all`.

Wait for the response before continuing.

---

## Step 1: Show Exactly What Will Be Cleared

Before doing anything, show precisely what will go.

### If scope includes `profile`:

List every file under `profile/` (Glob `profile/**/*`), including the person's own tests under
`profile/tests/`. Present as:

```
## Profile reset will remove:

profile/
  - [each file] or "(no profile)"
```

If there is no `profile/`, say so and skip this scope.

### If scope includes `state`:

Report which of these exist, with the row count of each CSV:

```
## State reset will remove:

- job_search_tracker.csv       [n rows, or "(none)"]
- network_contacts.csv         [n rows, or "(none)"]
- network_threads.csv          [n rows, or "(none)"]
- job_scraper/seen_jobs.json
- job_scraper/do_not_target.json
- company_research/*.json      [n files]
- upskill/*.md                 [n files]
- rounds/                      (local working files, never committed)
```

### If scope includes `documents`:

Use Glob to list all files present in `documents/cv/`, `documents/linkedin/`, `documents/diplomas/`, `documents/references/`, `documents/postings/`, `documents/applications/`, `documents/interview/`, `documents/network/`, `documents/rounds/`, `documents/briefs/`, and `documents/shortlists/`. Present as:

```
## Documents reset will delete:

documents/cv/
  - [filename] or "(empty)"

documents/linkedin/
  - [filename] or "(empty)"

documents/diplomas/
  - [filename] or "(empty)"

documents/references/
  - [filename] or "(empty)"

documents/postings/
  - [filename] or "(empty)"

documents/applications/
  - [subfolder/filename] or "(empty)"

documents/interview/
  - [filename] or "(empty)"

documents/network/
  - [filename] or "(empty)"

documents/rounds/
  - [filename] or "(empty)"

documents/briefs/
  - [filename] or "(empty)"

documents/shortlists/
  - [filename] or "(empty)"

documents/README.md - NOT deleted (instructions file)
```

If all document subfolders are already empty, state "All document subfolders are already empty - nothing to delete." and skip the confirmation step for this scope.

The rendered resumes and letters themselves (`cv/<Prefix>_*`, `cover_letters/<Prefix>_*`) go
with `documents`: list them in this preview too. The app's templates and fonts in those
folders (`cv/main_example.tex`, `cover_letters/cover.cls`, `cover_letters/cover_example.tex`,
`cover_letters/OpenFonts/`) are app-owned and are never deleted.

---

## Step 2: Require Explicit Confirmation

Present the confirmation prompt:

> **This cannot be undone here,** and anything already pushed stays in this repo's history.
>
> Type **`RESET`** (all caps) to confirm, or anything else to cancel.

Wait for the response.

- If they type exactly `RESET`: proceed to Step 3.
- If they type anything else: abort and say "Reset cancelled. Nothing was changed."

---

## Step 3: Execute the Reset

### Profile reset

```bash
git rm -r -q --ignore-unmatch profile/
rm -rf profile/
```

### State reset

```bash
git rm -q --cached --ignore-unmatch job_search_tracker.csv network_contacts.csv network_threads.csv \
    job_scraper/seen_jobs.json job_scraper/do_not_target.json
rm -f job_search_tracker.csv network_contacts.csv network_threads.csv
rm -f job_scraper/seen_jobs.json job_scraper/do_not_target.json
git rm -q --ignore-unmatch 'company_research/*.json' 'upskill/*.md'
rm -f company_research/*.json upskill/*.md
rm -rf rounds/
```

### Documents reset

For each non-empty document subfolder, delete all files within it using Bash `rm`. Do not delete the folder itself, and do not delete `documents/README.md` or the `.gitkeep` files.

```bash
rm -f documents/cv/*
rm -f documents/linkedin/*
rm -f documents/diplomas/*
rm -f documents/references/*
rm -f documents/postings/*
rm -rf documents/applications/*/
rm -f documents/interview/*
rm -f documents/network/*
rm -f documents/rounds/*
rm -f documents/briefs/*
rm -f documents/shortlists/*
```

Then the rendered documents, never the app's templates and fonts:

```bash
python3 - <<'EOF'
import glob, os, sys
sys.path.insert(0, "tools")
from personal_paths import is_personal
for p in glob.glob("cv/*") + glob.glob("cover_letters/*"):
    if os.path.isfile(p) and is_personal(p):
        os.remove(p)
EOF
```

Commit the removal (stage exactly the paths above, never anything else), so the next session
does not bring the old files back from master.

---

## Step 4: Confirm What Was Done and Next Steps

After the reset is complete, report:

```
## Reset complete

### Cleared
[List each file/folder that was actually removed]

### Unchanged
[List anything that was already empty or was intentionally preserved]
```

Then say what to do next, based on what was reset:

**If profile was reset:**
> Your profile is gone. Run `/setup` to build a new one: it reads anything you put in
> `documents/` and otherwise asks you a few plain questions.

**If state was reset:**
> The tracker, the contact book and the record of postings seen are empty. The next `/scrape`
> treats every posting as new.

**If documents were reset:**
> The `documents/` folder is now empty. Add your career documents and run `/setup` to
> populate your profile. See `documents/README.md` for instructions on what to put where.

**If everything was reset:**
> This repo now holds the app and nothing of yours. Run `/setup` to start again.
