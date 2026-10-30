# The app's code

Claude Code loads this file once a chat reads, writes or edits a file under `tools/`
(code.claude.com/docs/en/memory, "How CLAUDE.md files load"). Running a tool does not load
it, so nothing here is needed to use the app.

- **Before changing any file here, read `MAINTAINING.md`, "Developer rules"**, whichever
  repo the chat started in: the change is made in the app, on a branch, with CI green and the
  leak scan passed on the exact tree; a change an existing user would have to act on is a
  profile upgrade (`tools/profile_upgrades.py`); a change to a part of the build that leaves
  something behind is a new version in `tools/build_versions.py`.
- **In a person's own copy, never edit a file here.** Everything under `tools/` is the app's
  (`tools/personal_paths.py` is the line), and the next sync puts it back. If that person is
  not the app's maintainer, never trouble them with the app's problems: do what
  they asked the best honest way the app allows.
- `tools/openroles/` is vendored from openroles and never edited here.
- A rule that can be enforced in Python is enforced in Python, and the words a tool prints
  for a person stay plain (`tests/test_a_beginner_is_told_in_plain_words.py`).
