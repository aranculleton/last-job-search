# The app's tests

Claude Code loads this file once a chat reads, writes or edits a file under `tests/`
(code.claude.com/docs/en/memory, "How CLAUDE.md files load").

- These are the app's tests. **Before changing one, read `MAINTAINING.md`, "Developer
  rules" and "Adding a test"**: reproduce on the real path, never weaken a pin to make a
  change pass, and never write to a person's state (a copy of their repo, or `LJS_STATE`
  pointing at a copy).
- A test that pins where a rule is written follows the rule when it moves: the rule's home
  is in `docs/rule_map.json`, and `tests/test_core_rules_have_a_home.py` holds every home.
- A person's own tests live in `profile/tests`, use the app's public names only, and are
  brought in line by Claude after an update (RUNBOOK.md, "Your own tests fail after an
  update").
