#!/usr/bin/env python3
"""Merge the state files two chats changed at once, row by row (a git merge driver).

Several chats run against one repo, each in its own container. Two of them adding a
tracker row, logging a message or ruling out a posting on the same afternoon is
normal, and git's line merge calls that a conflict whenever the two edits sit next to
each other, which at the end of an append-only file they always do. A row is the unit
that matters, so this merges rows:

- a row only one side added, changed or removed takes that side;
- a row both sides changed the same way is taken once;
- a row both sides changed differently is merged field by field, and the notes both
  sides added are both kept;
- a field both sides set to different values takes the later change: the record's own
  date where its writer keeps one (JSON_FILES), else each side's own history says when its
  value was set (the author date of the commit that set it, which a rebase keeps), and the
  merge says which it kept and what the other side had, so a person who wants the other can
  say so;
- a JSON file merges key by key all the way down, a list item by item, and a log its
  writer never shortens keeps every item either side has, so nothing either side added is
  lost; a record both sides wrote again takes the later one's values; a snapshot its writer
  writes whole is kept whole from the later side; and the app's own records (which version
  made what, where a slow board resumes) are settled by their own rule, never a person;
- every JSON state file is written back exactly as its writer writes it (JSON_FILES), and
  every JSON name the app's code uses is wired here or listed with why it cannot clash
  (JSON_NAMES);
- where neither change is later (no history to read, or the same moment), or a row one
  side removed while the other changed it, it is a real conflict. The CSV gets git's
  markers around the two versions of that row, the JSON keeps this side's value, the
  conflicts are listed, and the exit is 1, so git leaves the file for a person, as it
  would have anyway.

`tools/sync_app.py` sets `merge.ljs-state.driver` in the repo's git config on every
run and `.gitattributes` names the files. Where the driver is not set (a fresh clone
before its first sync, GitHub's own merge), git merges lines exactly as before.

    python3 tools/merge_state.py %O %A %B %P
"""
from __future__ import annotations

import csv
import datetime as dt
import fnmatch
import io
import json
import os
import platform
import re
import sys

# The floor in tools/python_floor.py, inline: git runs this file on its own, from a
# checkout where nothing else may be importable yet.
FLOOR = (3, 9)

# The key that says two rows are the same row. A file not named here is merged with
# the whole row as its key, which suits a log: a row is only ever added.
KEYS = {
    "job_search_tracker.csv": ("date", "company", "role"),
    "network_contacts.csv": ("contact_id",),
    "network_threads.csv": None,
    "question_bank.csv": None,          # documents/interview/: a log, rows only added
}
# A log row both sides changed is still one row: the fields that say which message it is.
# Keyed by its whole row, a message one chat named the file of and another added the words
# of was two new rows and a removed one, and the merge kept both copies, saying nothing;
# the copy read as a second message sent and spent the one nudge (networking audit,
# 2026-10-25). Only a row in the common ancestor that both sides changed is paired this
# way: two messages each side added on one day are two messages, and both are kept.
SAME_MESSAGE = {"network_threads.csv": ("contact_id", "date", "direction", "channel")}
# Free text that both sides may have added to: kept from both, never a conflict.
NOTES = {"notes"}
# Lists of records inside a JSON state file, merged item by item the way rows are: each
# item is known by the fields that never change once it is written, so one side retiring
# a rule and the other adding one keeps both. Without this a list both sides added to was
# one value, and two chats recording a reaction on the same day stopped every merge of the
# person's rules (three times on 2026-10-24, each kept by hand).
LIST_KEYS = {
    "learned.json": {
        "entries": ("date", "area", "said", "rule"),
        "approved": ("date", "said", "text"),
        "skipped": ("date", "said", "why"),
        "offers": ("setting", "version"),
    },
    # The employers where the person wants more people written to (reading.py more-at):
    # a list at the top of the file, one row an employer.
    "more_at.json": {"": ("employer",)},
}
# Every JSON state file, by where it sits (a `*` is one folder), each merged the way its
# writer uses it. A "spot" is a place in the file: keys joined by "/", "" the whole file,
# and "#" any item of a list ("facts/#/roles").
#   lists      a list merged item by item. Its value is the fields an item is known by, ()
#              for the whole item (a list only ever added to: what either chat added is kept
#              once, ours first), or "fact" for a research fact's own identity (its page and
#              its words). {"key": ..., "keep": True} never lets one side's removal take an
#              item out: a log its writer never shortens. Otherwise an item one chat took
#              back (an undo, a list pruned to a week) stays out.
#   order      a list its writer keeps sorted by this field, sorted again after the merge
#   stamps     fields that date the record they sit in, written with it every time: where both
#              chats changed one value, the record dated later is the later change, or, for a
#              field marked "earlier", the earlier (the first to start, the first seen)
#   dated      values that are themselves when they were set: the later wins, or the earlier
#   whole      a snapshot, written whole: where both chats changed it, the one dated later is
#              kept whole, else the later commit's, never a mix of the two; or, marked
#              "merge", key by key where no date says (one day's short lists are one list)
#   pick       a record settled by a rule of its own (PICKERS), never left for a person
#   quiet      what it settles is the app's own record: nothing to tell the person
#   newest     a record published again and again and dated each time (`stamp`), such as the
#              page's address and what it holds: where the two sides hold different ones (the
#              fields `with` names), the one stamped later stands, those fields taken whole,
#              before anything else in the file is merged, whatever the copy both began from
#              held, so no merge moves it back to an older one or to another address (`key`)
#              published earlier
#   indent, sort ("all", "top" or None), ascii, newline   as its writer writes it, so a merge
#              rewrites no line it did not merge; "ours" reads it from the file itself, for one
#              Claude writes by hand
# A date counts for a side only where that side wrote it since the copy both began from,
# later than that copy's: an undo puts the older record back with its older date, which
# says nothing of when the undo was made, and each side's history decides instead.
_KEEP = {"key": (), "keep": True}
_FACTS = {"key": "fact", "keep": True}
JSON_FILES = {
    # ---- the page (4.0)
    # The page's address (app_setup.record_page, record_no_page: published_at, and the day
    # a chat said it cannot publish) and every No thanks to a suggestion, each dated with
    # its day (app_alerts.dismiss; undismiss takes one off). app_setup._write_json's format.
    # `code` and `caps` (what the published page holds) go with the publish dated later;
    # `introduced`, the day the person was told what their page is, is a date like `none`:
    # set on both sides, the later is kept, and nothing is asked of the person. Where the two
    # sides hold different page records (two chats that each published a page, or a branch
    # left days ago holding an older one), the one published later stands, whole, with what
    # it holds, as start adopts it (app_setup.adopt_page_elsewhere): every publish stamps it
    # anew, so the page in use is the newest. Keeping the first published let a branch left
    # nine days earlier put its abandoned page back over the one in use, and the next start
    # moved everything there (a report from a person's copy, 2026-11-04).
    "profile/app.json": {"stamps": ("published_at", "on"), "dated": ("none", "introduced"),
                         "newest": {"key": "url", "stamp": "published_at",
                                   "with": ("url", "published_at", "by", "title_name", "code",
                                            "caps")},
                         "indent": 2, "sort": "all"},
    # What the person answered on the page (app_actions._setup_*, app.py resume-saved and
    # propose): a record a step, written whole with its "at". history/jobs is the one list,
    # a job at a time, only ever added to; its undo takes the newest back. outside/<key> is
    # when they said they had done a step outside the page, as written before 4 November.
    "profile/setup_answers.json": {"lists": {"history/jobs": ()}, "stamps": ("at",),
                                   "dated": ("outside/*",), "indent": 2, "sort": "all"},
    # Each thing said once, and its day (app_setup.save_said: a card's Done, `app.py told`,
    # the start line about unsaved work): the later day stands.
    "profile/said_once.json": {"dated": ("*",), "indent": 2, "sort": "all"},
    # Their settings (app_actions._save_person_json) and the place each employer heard
    # (told.record): nothing in it dates a change, and its lists are settings (an order, the
    # words to avoid), each replaced whole, so a value both changed is settled by each
    # side's history or left for a person, as a row's field is.
    "profile/person.json": {"indent": 2},
    # Their own Tweak buttons (tweak.add_button): a row a button, known by its id and dated
    # when it was added; the oldest of a kind taken off for a new one is a removal.
    "profile/tweaks.json": {"lists": {"buttons": ("id",)}, "stamps": ("added",), "indent": 1},
    # The record of every tweak to one output (tweak._save_log): an entry a tweak's key,
    # only ever added, each dated with when it ran. The lists in an entry are written with it.
    "documents/applications/*/tweaks.json": {"stamps": ("at",), "indent": 1, "sort": "all"},
    "documents/network/*/tweaks.json": {"stamps": ("at",), "indent": 1, "sort": "all"},
    "documents/rounds/tweaks/tweaks.json": {"stamps": ("at",), "indent": 1, "sort": "all"},
    # ---- the profile
    # Which version of each part of the build made what this copy has (build_versions.record:
    # {method: {version, date}}). The app's own record: the higher version stands, always.
    "profile/build_versions.json": {"pick": {"*": "higher_version"}, "quiet": True,
                                    "indent": 2, "sort": "top", "ascii": True},
    # Employers judged against the person's bar (bar.judge): one record an employer, dated.
    "profile/employers_judged.json": {"stamps": ("date",), "indent": 2, "sort": "top"},
    # Every no to a question, dated (profile_upgrades.record_no).
    "profile/asked.json": {"stamps": ("no",), "indent": 2, "sort": "all", "ascii": True},
    # Where the person works, dated when asked (place.record); the day a chat first ran on
    # their computer (note_local) and setup's own mark (mark_setup): the first to start
    # setup holds it, and a first sighting is the earliest one.
    "profile/place.json": {"stamps": {"asked": "later", "started": "earlier"},
                           "dated": {"computer_chat": "earlier", "setup/finished": "earlier"},
                           "indent": 2, "ascii": True},
    # The scheduled tasks (routines.record): one entry a task, known by its key.
    "profile/routines.json": {"lists": {"routines": ("key",)}, "indent": 2},
    # What answering the page cost, a line a wake and a hand-over (helper_usage.record): a log
    # only ever added to, each entry known by when, which chat and what; kept a month, so an
    # entry one side let go of stays out.
    "documents/helper_usage.json": {"lists": {"entries": ("at", "chat", "kind")},
                                    "order": {"entries": "at"}, "indent": 1, "sort": "all"},
    # What the person booked that the app did not know of (upcoming.add): one entry each,
    # known by its id, so the page and a chat adding one each on the same day keep both.
    "documents/upcoming.json": {"lists": {"events": ("id",)}, "indent": 2},
    # The person's one answer per skill a posting asked about (skill_answers.ask, record): a
    # record a skill. Its answer is dated and kept whole from the side that answered later, so
    # two chats that each took an answer keep the later one; the applications that asked are
    # every one either side named, the later day standing; it was first asked on the earlier.
    # When each rule was set and in whose words (rules_view.note_set): each rule's record
    # taken whole from the side that set it later, so two chats changing two rules keep both.
    "documents/rules/set.json": {"whole": ("*",), "stamps": ("set_on",), "indent": 1},
    # Rules the person kept when asked "Still right?", and the month the Brief's line was set
    # aside: the later day of each stands.
    "documents/rules/review.json": {"dated": {"kept/*": "later", "brief_dismissed": "later"},
                                    "indent": 1},
    "documents/skill_answers.json": {
        "whole": ("skills/*/answer",), "stamps": ("at",),
        # A yes "just for this role" (skill_answers.record_role): every role either side named.
        "lists": {"skills/*/for": {"key": ("company", "role"), "keep": True},
                  "skills/*/roles": {"key": ("company", "role"), "keep": True}},
        "dated": {"skills/*/asked": "earlier", "skills/*/for/#/day": "later",
                  "skills/*/roles/#/at": "later"},
        "indent": 1, "sort": "all"},
    # The findings the person read and kept (profile_consistency.keep): only ever added to.
    "profile/consistency_reviewed.json": {
        "lists": {"reviewed": {"key": ("file", "fact", "said", "sentence"), "keep": True}},
        "stamps": ("date",), "indent": 1, "ascii": True},
    # Their own scoring baseline (score_eval --update): one record a posting.
    "profile/tests/fixtures/score_baseline.json": {"indent": 1, "sort": "all", "ascii": True},
    # Tips (tips.save) and the LinkedIn download's record (export.py): their writers' format.
    "profile/tips.json": {"indent": 2, "sort": "all", "ascii": True},
    "documents/network/linkedin_export.json": {"indent": 1, "sort": "all", "ascii": True},
    # The employers where more people may be written to (reading.more_at): sorted by name.
    "profile/more_at.json": {"lists": {"": ("employer",)}, "order": {"": "employer"},
                             "indent": 2},
    # ---- the search
    # Employers with no relevant presence (written by Claude, {"companies": {name: entry}}):
    # an entry dated when it was recorded, and renewed with a later review_after.
    "job_scraper/do_not_target.json": {"stamps": ("recorded", "review_after"),
                                       "indent": "ours", "ascii": "ours", "newline": "ours"},
    # The slow boards' resume point (scrape_wide.save_cursor), and where 3.7.0 kept it: one
    # record a portal; the further-along one stands.
    "documents/rounds/.sweep/cursor.json": {"pick": {"*": "further"}, "quiet": True,
                                            "indent": 1, "sort": "all", "ascii": True},
    "documents/rounds/.sweep.json": {"pick": {"*": "further"}, "quiet": True,
                                     "indent": 1, "sort": "all", "ascii": True},
    # A round's summary (run_round.write_summary), which a job brought back joins
    # (filtered.back): one row a posting, known by its link. Its two writers escape
    # differently, so the file's own way is kept.
    "documents/rounds/*.json": {"lists": {"": ("url",)}, "indent": 1, "ascii": "ours"},
    # ---- networking
    # Their own LinkedIn profile, as looked at (own_profile.record, answer, dismiss): the
    # looks and the dismissals only ever added to, each answer dated.
    "documents/network/own_profile_review.json": {
        "lists": {"reviews": {"key": ("date", "source"), "keep": True}, "dismissed": _KEEP},
        "stamps": ("date",), "indent": 2, "sort": "all"},
    # Kept here only where this computer's own ledger could not be written (reading._keep):
    # the list pages read this week (a log pruned to a week), the last sign-in, the day's
    # short list (one day's lists are one list) and a stop, each a snapshot.
    # The postings the person added on the page, scored (tools/added_jobs.py: a row a
    # posting, known by its link, else its employer and title), and the ones they keep past
    # the next search (app_actions job.keep: {link: its row}, dated with the day kept).
    "documents/rounds/added/jobs.json": {"lists": {"": ("url", "company", "title")},
                                         "indent": 1},
    "documents/rounds/kept/jobs.json": {"stamps": ("kept_on",), "indent": 1, "sort": "all"},
    # Each document put in the page's file store (app_model.record_assets: {repo path:
    # {asset, md5, at}}): two chats uploading different files keep both.
    "documents/page_assets.json": {"stamps": ("at",), "indent": 1, "sort": "all",
                                   "ascii": True},
    # The profiles queued for the page to read (reading.py queue_for_page: a row a contact,
    # taken off once read).
    "documents/network/page_reads_queue.json": {"lists": {"": ("contact",)}, "indent": 1,
                                                "sort": "all", "ascii": True},
    # An application's latest checks (verify_batch.py _record): the newer run stands whole.
    "documents/applications/*/verify.json": {"whole": ("",), "stamps": ("at",), "indent": 1,
                                             "ascii": True},
    # The way a rerun of the drafts handed this application on (remake_drafts.py): the later
    # run's record stands whole.
    "documents/applications/*/remake.json": {"whole": ("",), "stamps": ("date",), "indent": 1},
    # The page as a reader of LinkedIn (place.PAGE_READS_FILE): the later check or read stands.
    "documents/network/page_reader.json": {"whole": ("",), "stamps": ("checked_at", "last_read_at"),
                                           "indent": 1, "ascii": True},
    "documents/network/.page_reads.json": {"lists": {"reads": ("at", "url")}, "indent": 1,
                                           "ascii": True, "newline": False},
    "documents/network/.signed_in.json": {"whole": ("",), "stamps": ("at",), "indent": 1,
                                          "ascii": True, "newline": False},
    "documents/network/.shortlist.json": {"whole": {"": "merge"}, "stamps": ("date",),
                                          "lists": {"ids": _KEEP}, "indent": 1, "ascii": True,
                                          "newline": False},
    "documents/network/.reads_stopped.json": {"whole": ("",), "stamps": ("at", "lifted"),
                                              "indent": 1, "ascii": True, "newline": False},
    # The people-search filters the person narrowed by hand (reading.learn_search).
    "documents/network/.search_filters.json": {"indent": 1, "ascii": True},
    # The InMail balance LinkedIn showed, on its day (state.py inmail-credits): a snapshot.
    "documents/network/.inmail_credits.json": {"whole": ("",), "stamps": ("date",),
                                               "indent": 1, "ascii": True},
    # What each title search found at each employer, dated (sources.record_yield).
    "documents/network/.title_yield.json": {"stamps": ("date",), "indent": 1, "sort": "all",
                                            "ascii": True},
    # One person as read (reading.save over reading.merge): the newest read's page fields,
    # every source and finding kept, as its own merge does.
    "documents/network/*/reading.json": {
        "lists": {"sources": _KEEP, "items": {"key": ("kind", "text"), "keep": True}},
        "stamps": ("read_on",), "indent": 1},
    # What the person said a note to this reader may name (reading.keep_own_facts).
    "documents/network/*/own_facts.json": {
        "lists": {"kept": {"key": ("what",), "keep": True}}, "stamps": ("date",), "indent": 1},
    # The parts this contact's note was built from (parts.save): a snapshot of one note.
    "documents/network/*/draft.parts.json": {"whole": ("",), "indent": 1, "sort": "all",
                                             "newline": False},
    # What a parked draft's row said when it was set aside (state.park_draft), so putting the
    # row back as it was brings the draft back: a snapshot, the newer whole.
    "documents/network/*/draft.not-needed.json": {"whole": ("",), "newline": False},
    # The newest message of theirs a draft answered (state.save_answers): a snapshot of what
    # the draft was written against, the newer whole.
    "documents/network/*/draft.answers.json": {"whole": ("",), "newline": False},
    # Why this person was given an InMail rather than a note, and the other message kept
    # beside it (inmail_pick.py): a snapshot of one decision, the newer whole.
    "documents/network/*/inmail.json": {"whole": ("",), "indent": 1},
    # The resume made for this contact (general_resume.py --for-contact): which file, when,
    # and where the page gets it. A snapshot, the newer whole.
    "documents/network/*/resume.json": {"whole": ("",), "indent": 1},
    # ---- one application or interview process
    # The person's answer to a campaign chat (interview_pack.record_campaign), and what the
    # last build wrote into the living prep document (its built record): snapshots.
    "documents/applications/*/campaign.json": {"whole": ("",),
                                               "stamps": ("started", "declined"),
                                               "indent": 1, "ascii": True},
    "documents/applications/*/.interview_prep.built.json": {"whole": ("",), "indent": 1},
    # The kept draft both documents are rendered from (outreach.write, fit_to_page.save,
    # tweak), and what drafting it cost (draft_cost): each one object, written whole.
    "documents/applications/*/draft.json": {"whole": ("",), "indent": 1},
    "documents/applications/*/cost.json": {"whole": ("",), "indent": 1},
    # ---- research
    # One employer's research (company_research.save, which itself never drops a fact): every
    # fact kept, known by its page and its words, the later check of each standing; and
    # what each host taught a fetch (_hosts.json, note_host), dated.
    "company_research/*.json": {
        "lists": {"facts": _FACTS, "interview_process": _FACTS, "teams/*": _FACTS,
                  "sources": _FACTS, "facts/#/roles": _KEEP, "interview_process/#/roles": _KEEP,
                  "teams/*/#/roles": _KEEP, "do_not_claim": _KEEP, "not_found": _KEEP,
                  "not_verified": _KEEP},
        "stamps": ("quote_checked", "last_checked", "fetched_date"), "indent": 2},
}
_JSON_DEFAULT = {"lists": None, "order": None, "stamps": (), "dated": (), "whole": (),
                 "pick": None, "newest": None, "quiet": False, "indent": 2, "sort": None,
                 "ascii": False, "newline": True}


def _at(path: str, pattern: str) -> bool:
    """Is `path` the place `pattern` names, a `*` standing for one folder or key?"""
    a, b = path.split("/"), pattern.split("/")
    return len(a) == len(b) and all(fnmatch.fnmatchcase(x, y) for x, y in zip(a, b))


def _rule(table, spot: str):
    """What a JSON_FILES map of spots gives `spot`: its own entry, else the first pattern
    naming it (never the whole file for a pattern of one key), else None."""
    if not table:
        return None
    if spot in table:
        return table[spot]
    return next((v for p, v in table.items() if spot and p and _at(spot, p)), None)


def json_rules(path: str) -> dict:
    """How the JSON file at `path` (from the top of the repo, as git names it) merges: its
    JSON_FILES entry, else its lists from LIST_KEYS by name, written as a merge always was."""
    rel = path.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    got = next((r for p, r in JSON_FILES.items() if _at(rel, p)), None)
    if got is None:
        got = {"lists": LIST_KEYS.get(os.path.basename(rel))}
    return dict(_JSON_DEFAULT, **got)


# Every JSON name the app's code writes, reads or matches, other than those a wired path
# above ends in, with where it lands: a wired pattern, or why two chats never change one
# copy of it differently. A name built in code (an f-string, a %, a suffix) is listed with
# the file that builds it. tests/test_every_json_file_merges_or_says_why.py reads the app's
# code (all but this file, whose tables name them) and fails on a name that is in neither,
# and on an entry no code names any more.
_ROUND = ("a round's own stage file, in that round's folder under rounds/, which git "
          "ignores and the round prunes; one chat runs a round")
_SCRATCH = ("the drafting pipeline's scratch round folder ($SCRATCH/<round>), never "
            "committed; one chat drafts a batch")
_GITDIR = "in this checkout's own git folder, never committed: each chat its own"
_APP = "the app's own file, read only; a person's copy never writes it"
_OUTSIDE = "kept on this computer outside the copy, never committed"
_READS = "a pattern that reads files named elsewhere here, or a suffix test; writes nothing"
_HASHED = ("a snapshot named by the hash of what it holds: two chats that write one write "
           "the same thing")
_PER_ROUND = ("named after the round that wrote it, once, and never written again; a round "
              "is run by one chat")
JSON_NAMES = {
    ".sent.json": "each view batch's records as they stood before it was sent, in the view's own folder, so a refused save can be put back and made again (page_db.keep_landed); never committed",
    ".refused.json": "the record a page save was refused for, in the view's own folder, read once by the next run; never committed",
    # run_round reads every round's summary to find a job set aside while a search ran; the
    # files themselves are wired as "documents/rounds/*.json" above.
    "tools/app.py: *.json": "a page dump's screen documents, read only to tell whether the dump holds the page's screens (app.py no_screen), in the chat's scratch folder; never committed",
    "tools/rules_view.py: *.json": "each search's left-out list, read only for how many each rule left out (rules_view.left_counts); merged as documents/rounds/filtered/*.json",
    "tools/run_round.py: *.json": "every round summary, read only, to hold a set-aside made during a search; written by write_summary, merged as documents/rounds/*.json",
    "tools/network/candidates.py: *.json": "every round summary, read only, for the employers a short people search widens to (candidates.employers); written by run_round.write_summary, merged as documents/rounds/*.json",
    **dict.fromkeys(("00_portal_health.json", "01_dropped.json", "01_prefiltered.json",
                     "02_hydrated.json", "03_screened.json", "03_screened_all.json",
                     "04_opportunity.json", "05_ranked.json", "06_shortlist.json",
                     "06_skipped.json", "kept.json", "dropped.json", "scraped.json",
                     "sent.json", "partial_rows.json", "tools/run_round.py: .json",
                     # a search limited to named employers: its names and the rows at them
                     "employers.json", "named.json"), _ROUND),
    **dict.fromkeys(("apps_in.json", "picks.json", "draft_args.json", "pack.json", "held.json",
                     "staged_roles.json", "packet.json", "drafts.json",
                     "tools/draft_audit.py: outreach_*.json",
                     "tools/draft_audit.py: model_audit_*.json",
                     "tools/draft_audit.py: audit_*.json", "tools/draft_audit.py: research_*.json",
                     "tools/draft_audit.py: rules_*.json", "tools/draft_audit.py: draft_*.json",
                     "tools/draft_audit.py: **.json", "tools/draft_audit.py: .json",
                     "tools/draft_pack.py: rules_*.json", "tools/draft_pack.py: .json",
                     "tools/draft_pack.py: research_*.json",
                     "tools/stage_picks.py: audit_*.json", "tools/stage_picks.py: draft_*.json",
                     "tools/stage_picks.py: audit_{}.json", "tools/stage_picks.py: draft_{}.json",
                     "tools/stage_picks.py: model_audit_{}.json",
                     "tools/stage_picks.py: outreach_{}.json",
                     "tools/stage_picks.py: research_{}.json",
                     "tools/tweak.py: draft_*.json", "tools/tweak.py: research_*.json",
                     ".wake.json"),
                    _SCRATCH),
    **dict.fromkeys(("ljs-app-watch.json", "ljs-job-sites.json", "ljs-listener.json",
                     "ljs-applied.json", "ljs-place.json", "ljs-tidy.json",
                     "ljs-reactions.json", "ljs-upgrades-listed.json", "ljs_own_tests.json",
                     ".reactions.json", "ljs-no-page.json", "ljs-page-held.json",
                     "ljs-job-chats.json", "ljs-tidy-planned.json", "ljs-versions.json",
                     "ljs-save-held.json", "ljs-land-result.json", ".mirror.json"), _GITDIR),
    # The page's records as this checkout last read them (page_reads, the mirror in its git
    # folder), each under its own record's name: the meta records read by name, and every file
    # of a collection copied whole.
    **dict.fromkeys(("now.json", "current.json", "tools/page_reads.py: .json"),
                    "the page database's records as this checkout last read them, in its git "
                    "folder (page_reads.MIRROR) or a dump folder; never committed"),
    ".reads.json": "a page dump folder's note of what was read, from when, in the chat's "
                   "scratch folder; never committed",
    # A dump folder's own note of each record's stamp as read (page_db._keep_read_stamp):
    # written into the chat's scratch folder beside the dump, never into the person's files.
    ".read-stamps.json": "a page dump folder's note of each record's stamp as read, in the chat's scratch folder; never committed",
    **dict.fromkeys(("claude_surfaces.json", "public_names.json", "removed_names.json",
                     "rule_map.json", "remote.json", "design_draft.json",
                     "tools/leak_scan.py: **.json", "tools/markets.py: *.json",
                     "tools/markets.py: .json", "tools/locale_rules.py: .json",
                     "tools/profile_upgrades.py: *.json"), _APP),
    **dict.fromkeys(("reading-ledger.json", "budget.json",
                     # a state folder outside git (a test's): the ledger in the computer's
                     # temporary folder, named for that folder (app_actions._kept_ledger_path)
                     "tools/app_actions.py: ljs-applied-*.json"), _OUTSIDE),
    # profile/tidy.json (tools/tidy.py): the old chats tidied away, a list only ever added
    # to, by the one chat that answers the page once a day; a second chat that took the page
    # over adds other chats' ids, never a different value for one already there.
    "tidy.json": "written by the chat that answers the page alone, once a day, a list only "
                 "added to: two chats never write one entry differently",
    # documents/briefs/watched.json (tools/brief.py, 4.7): the day each thing the brief's news
    # watches was last searched, written by the brief once a day.
    "watched.json": "written by the brief once a day, a day per watched thing: two chats can "
                    "differ only by a day, and either value moves the next search by a day at "
                    "most, so this side's stands",
    **dict.fromkeys(("tools/app_setup.py: .json", "tools/bar.py: *.json",
                     "tools/build_app.py: .json", "tools/company_research.py: *.json",
                     "tools/followup_drafts.py: *.json", "tools/stage_picks.py: .json",
                     "tools/network/why.py: *.json", "tools/profile_upgrades.py: .json",
                     "tools/person.py: .json", "tools/app_actions.py: .json", "FILE.json"), _READS),
    **dict.fromkeys((".parts.json", "tools/tweak.py: draft.*.parts.json"), _HASHED),
    # Wired under a pattern rather than by name.
    **dict.fromkeys(("_hosts.json", "tools/company_research.py: %s--%s.json",
                     "tools/network/prep.py: %s.json", "tools/personal_paths.py: *.json",
                     "tools/save_state.py: *.json", "tools/security_guards.py: *.json"),
                    "company_research/*.json"),
    ".sweep.json": "documents/rounds/.sweep.json",
    "tools/run_round.py: %s.json": "documents/rounds/*.json",
    # A search renamed when two took one name (land._round_clash): its summary and left-out
    # list under the new name, merged as the round files they are.
    "tools/land.py: r%d%s.json": "documents/rounds/*.json",
    "tools/network/parts.py: .json": ("a composed note's parts wait in this computer's "
                                      "ledger until a draft adopts them; " + _OUTSIDE),
    "tools/company_research.py: .json": ("company_research/<key>.json, wired; and a fetched "
                                         "page, " + _OUTSIDE),
    "tools/tweak.py: *.json": "company_research/*.json",
    "tools/tweak.py: .json": "a scratch round's files (" + _SCRATCH + "), and research read",
    "tools/app_model.py: *.json": ("reads the round summaries (wired) and a round's filtered "
                                   "list, " + _PER_ROUND),
    "tools/app_model.py: .json": "the same line: " + _PER_ROUND,
    "tools/filtered.py: *.json": ("documents/rounds/filtered/<round>.json, " + _PER_ROUND
                                  + "; and the round's summary, wired"),
    "tools/filtered.py: .json": "the same files: " + _PER_ROUND,
    "tools/design_check.py: drafts_*.json": "in a temporary folder of its own, deleted after",
    "tools/design_check.py: .json": "in a temporary folder of its own, deleted after",
    "tools/page_db.py: **.json": "the page database's dump folder, in the chat's scratchpad",
    "tools/page_db.py: *.json": "the page database's dump folder, in the chat's scratchpad",
    "tools/page_db.py: .json": "the page database's dump folder, in the chat's scratchpad",
    "applied.json": "the page actions' ledger, in the dump folder, never in the copy",
    ".mcp.json": "Claude Code's own setting, which tools/security_guards.py keeps out",
    "settings.json": "Claude Code's settings: the app's own (.claude/), or the person's own "
                     "computer's (~/.claude/), never a state file",
    "settings.local.json": "Claude Code's per-computer settings, never committed",
    "package.json": "a job site tool's own package file, the app's",
    "notion_sync.json": "left by a sync the app removed; nothing writes it",
    "salary_data.json": "licensed third-party salary data, which is never committed",
    "state.json": "gmail_sync/state.json, left by a mail sync the app removed, never committed",
}


# ------------------------------------------------------------------ fields


def merge_note(base: str, ours: str, theirs: str) -> str:
    """Both sides' additions to a notes field, ours first."""
    if ours == theirs or theirs == base:
        return ours
    if ours == base:
        return theirs
    if theirs.startswith(base) and ours.startswith(base):
        return ours + theirs[len(base):]
    if theirs in ours:
        return ours
    if ours in theirs:
        return theirs
    return ours + (" | " if ours and theirs else "") + theirs


def merge_fields(base: dict | None, ours: dict, theirs: dict,
                 decide=None) -> tuple[dict, list[str], list[str]]:
    """One row both sides changed: field by field. `decide(field, ours, theirs)` says which
    side made the later change ("ours", "theirs", or "" when neither is known to be later).
    Returns (row, conflicting fields, what was settled by which change was later)."""
    base = base or {}
    out, clash, settled = {}, [], []
    for k in list(ours) + [k for k in theirs if k not in ours]:
        b, o, t = base.get(k), ours.get(k), theirs.get(k)
        if o == t or t == b:
            out[k] = o if k in ours else t
        elif o == b:
            out[k] = t
        elif k in NOTES and all(isinstance(v, str) or v is None for v in (b, o, t)):
            out[k] = merge_note(b or "", o or "", t or "")
        else:
            side = decide(k, o, t) if decide else ""
            if side:
                kept, other = (o, t) if side == "ours" else (t, o)
                out[k] = kept
                settled.append(f"{k}: kept {kept!r}, the later change; the other side had "
                               f"{other!r}")
            else:
                out[k], clash = o, clash + [k]
    return out, clash, settled


# ------------------------------------------------------------------ CSV


# The byte-order mark a spreadsheet's "CSV UTF-8" starts a file with. Read as part of the
# first column's name ("\ufeffcontact_id"), the marked side's rows had no key, the other
# side's read as removed, and every contact_id in the merged book came back empty with no
# conflict said (networking audit, 2026-10-25). It is dropped from each side on reading,
# so the merge is row by row and the file is written back without it.
_MARK = "\ufeff"


def _unmark(text: str) -> str:
    return text[len(_MARK):] if text.startswith(_MARK) else text


def decode(raw: bytes) -> str:
    """One side of the merge as text, read the way every tool reads a state file
    (csv_store.decode): the mark dropped, a file a spreadsheet saved in Windows' own
    encoding read as that. Raises ValueError for a file that cannot be read for sure (UTF-8
    with a damaged character), and the merge is left to git's line merge, which loses
    nothing."""
    try:
        import csv_store
    except ImportError:  # git runs this alone: without its neighbour, UTF-8 or nothing
        return _unmark(raw.decode("utf-8"))
    text, how = csv_store.decode(raw)
    if how == csv_store.DAMAGED:
        raise ValueError("a character in it is not readable text")
    return text


def _read(text: str) -> tuple[list[str], list[dict]]:
    rows = list(csv.reader(io.StringIO(_unmark(text), newline="")))
    if not rows:
        return [], []
    head = rows[0]
    return head, [dict(zip(head, (r + [""] * len(head))[:len(head)]))
                  for r in rows[1:] if r]


def _pair_edits(B: dict, O: dict, T: dict, ident) -> None:
    """A base row neither side kept as it was, where each side holds exactly one new row
    that is the same message (`ident`): that row changed on both sides. Theirs and the
    base are put under our key, in place, so the row is merged field by field."""
    def same(row):
        return tuple(str(row.get(f) or "").strip() for f in ident)

    new_o = [k for k in O if k not in B]
    new_t = [k for k in T if k not in B]
    for k in [k for k in B if k not in O and k not in T]:
        mine = [x for x in new_o if same(O[x]) == same(B[k])]
        theirs = [x for x in new_t if same(T[x]) == same(B[k])]
        if len(mine) == 1 and len(theirs) == 1 and mine[0] not in T:
            T[mine[0]] = T.pop(theirs[0])
            B[mine[0]] = B.pop(k)
            new_o.remove(mine[0])
            new_t.remove(theirs[0])


def _keyed(rows: list[dict], fields) -> dict:
    """{key: row}, with the n-th repeat of a key kept apart as (key, n)."""
    out, n = {}, {}
    for r in rows:
        k = tuple(r.get(f, "") for f in fields) if fields else tuple(r.values())
        n[k] = n.get(k, 0) + 1
        out[(k, n[k])] = r
    return out


# The fields that say what follows on a contact row. The app writes them from the message
# log (state.write_follow_ups), and a chat or the person writes them from what they know.
FOLLOWS = ("status", "next_action", "next_action_due")


def _app_words():
    """The test for a next action in the app's own words (state._APP_ACTION), or None where
    this checkout cannot read it: the merge then settles the field as before."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        for p in (os.path.join(here, "network"), here):
            if p not in sys.path:
                sys.path.insert(0, p)
        import state  # noqa: E402  the app's own words live there
        return lambda v: bool(state._APP_ACTION.fullmatch(" ".join(str(v or "").split())))
    except Exception:  # noqa: BLE001  an old or half-merged checkout: as before
        return None


def _own_side(b: dict | None, o: dict, t: dict) -> str:
    """On a contact row both sides changed, the side whose next action was written by a chat
    or the person, where the other side's is the app's own words: "ours", "theirs" or "".
    The app's is worked out from the message log as that side saw it, and a background
    upgrade's copy of the log was older than the chat's: its "no more follow-ups" won as the
    later change over a reply the chat had just logged (2026-10-24). Its line can always be
    worked out again; theirs cannot."""
    b = b or {}
    if not ({"next_action"} <= set(o) and o.get("next_action") != t.get("next_action")
            and b.get("next_action") not in (o.get("next_action"), t.get("next_action"))):
        return ""
    app = _app_words()
    if app is None:
        return ""
    mine, other = app(o.get("next_action")), app(t.get("next_action"))
    if mine == other:
        return ""
    own = "theirs" if mine else "ours"
    kept = t if own == "theirs" else o
    return own if str(kept.get("next_action") or "").strip() else ""


def merge_csv(base: str, ours: str, theirs: str, name: str, later=None,
              settled: list | None = None, ending: str | None = None) -> tuple[str, list[str]]:
    """`later(key, field, ours, theirs)` says which side changed a field last (see
    `git_later`); what it settled is appended to `settled`. `ending` is the line ending to
    write: by default a state file's is plain (LF), as .gitattributes asks, and any other
    file keeps ours'."""
    fields = KEYS.get(name)
    hb, rb = _read(base)
    ho, ro = _read(ours)
    ht, rt = _read(theirs)
    head = ho + [h for h in ht if h not in ho]
    if fields and not all(f in head for f in fields):
        fields = None
    if fields is None:
        # A log is keyed by its whole row, so read every side under one header.
        rb, ro, rt = ([{h: r.get(h, "") for h in head} for r in rs] for rs in (rb, ro, rt))
    B, O, T = _keyed(rb, fields), _keyed(ro, fields), _keyed(rt, fields)
    if fields is None and all(f in head for f in SAME_MESSAGE.get(name, ("",))):
        _pair_edits(B, O, T, SAME_MESSAGE[name])
    out, problems = [], []

    def place(k):
        b, o, t = B.get(k), O.get(k), T.get(k)
        if o is None and t is None:
            return None
        if o is None or t is None:                 # one side removed it, or one side added it
            kept = o if t is None else t
            if b is None:
                return kept
            if kept == b:
                return None                        # removed on one side, untouched on the other
            problems.append(f"{name}: a row one side removed and the other changed: "
                            f"{', '.join(k[0])}")
            return ("conflict", o, t)
        if o == t or t == b:
            return o
        if o == b:
            return t
        decide = (lambda f, ov, tv: later(k, f, ov, tv)) if later and fields else None
        own = _own_side(b, o, t) if name == "network_contacts.csv" else ""
        if own:
            first = decide

            def decide(f, ov, tv, first=first):     # noqa: F811  what follows: their own
                return own if f in FOLLOWS else (first(f, ov, tv) if first else "")
        row, clash, done = merge_fields(b, o, t, decide)
        if own:
            done = [d.replace("the later change", "the next step a chat or the person wrote, "
                              "over one the app worked out from an older copy of the "
                              "messages") if d.split(":", 1)[0] in FOLLOWS else d for d in done]
        if settled is not None:
            settled.extend(f"{name}: {', '.join(k[0])}: both changed {d}" for d in done)
        if clash:
            problems.append(f"{name}: {', '.join(k[0])}: both changed {', '.join(clash)}")
            return ("conflict", o, t)
        return row

    for k in O:
        out.append(place(k))
    for k in T:
        if k not in O:
            out.append(place(k))
    if ending is None:
        # The state files are kept with plain endings (.gitattributes: eol=lf). Ours' ending
        # was kept, so a chat branch from before that rule wrote CRLF back into a merge with
        # master, and the next sync stopped on a file no row of which had changed (2026-10-21).
        ending = "\n" if name in KEYS or not ours.split("\n", 1)[0].endswith("\r") \
            else "\r\n"
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=head, restval="", extrasaction="ignore",
                       lineterminator=ending)
    w.writeheader()
    for r in out:
        if r is None:
            continue
        if isinstance(r, tuple):
            _, o, t = r
            buf.write("<<<<<<< ours" + ending)
            if o is not None:
                w.writerow(o)
            buf.write("=======" + ending)
            if t is not None:
                w.writerow(t)
            buf.write(">>>>>>> theirs" + ending)
            continue
        w.writerow(r)
    return buf.getvalue(), problems


# ------------------------------------------------------------------ JSON

# A day, or a moment, as the app's writers stamp them: 2026-10-25, 2026-10-25T17:05:00Z.
_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?"
                    r"(?:Z|[+-]\d{2}:\d{2})?)?")


def _when(value):
    """(day, moment or None) for a stamp, for ordering; None for anything else. A moment
    with no zone is read as UTC, the zone the writers stamp in."""
    if not isinstance(value, str) or not _STAMP.fullmatch(value.strip()):
        return None
    s = value.strip()
    try:
        if len(s) == 10:
            return dt.date.fromisoformat(s), None
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError:
        return None
    t = (t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)).astimezone(dt.timezone.utc)
    return t.date(), t


def _later_of(a, b) -> str:
    """"a" or "b", whichever stamp is later, or "" where they cannot be told apart (the same
    moment, or a day against a moment on that day)."""
    x, y = _when(a), _when(b)
    if not x or not y:
        return ""
    p, q = (x[1], y[1]) if x[1] and y[1] else (x[0], y[0])
    return "a" if p > q else "b" if q > p else ""


def _ways(table) -> dict:
    """{name: "later" or "earlier"} from a JSON_FILES `stamps` or `dated` entry."""
    if isinstance(table, dict):
        return dict(table)
    return {k: "later" for k in table or ()}


def _fresh(v, b, way: str = "later") -> bool:
    """Did a side write this date since the copy both began from? A date later than the
    base's (or with none there); for an earliest-wins date, any date that differs from it."""
    if _when(v) is None:
        return False
    if _when(b) is None:
        return True
    return v != b if way == "earlier" else _later_of(v, b) == "a"


def _decide(b, o, t, way: str = "later") -> tuple[str, str]:
    if _fresh(o, b, way) and _fresh(t, b, way):
        side = _later_of(o, t)
        if way == "earlier":
            side = {"a": "b", "b": "a"}.get(side, "")
        if side == "a":
            return "ours", f"dated {o}, the other {t}"
        if side == "b":
            return "theirs", f"dated {t}, the other {o}"
    return "", ""


def _by_date(spot: str, base, ours, theirs, rules: dict | None, recs) -> tuple[str, str]:
    """Which side changed the value at `spot` later, by the dates its writer keeps (JSON_FILES
    `stamps` and `dated`): ("ours" or "theirs", the two dates), or ("", "") where no date
    says. `recs` is every record above the value, outermost first, as (base, ours, theirs);
    the nearest that holds a stamp is the one asked, and no record further out."""
    if not rules:
        return "", ""
    stamps = _ways(rules.get("stamps"))
    dated = _ways(rules.get("dated"))
    key = spot.rsplit("/", 1)[-1]
    way = stamps.get(key) or _rule(dated, spot)
    if way:
        return _decide(base, ours, theirs, way)
    for b, o, t in reversed(recs):
        held = [f for f in stamps if f in o or f in t]
        if held:
            for f in held:
                side, why = _decide(b.get(f), o.get(f), t.get(f), stamps[f])
                if side:
                    return side, why
            return "", ""
    return "", ""


def _newest(base, rec, rules) -> str:
    """A snapshot's newest date that its side wrote since the copy both began from."""
    if not isinstance(rec, dict):
        return ""
    base = base if isinstance(base, dict) else {}
    got = [rec[f] for f in _ways(rules.get("stamps")) if f in rec and _fresh(rec[f], base.get(f))]
    best = ""
    for v in got:
        if not best or _later_of(v, best) == "a":
            best = v
    return best


def _whole(base, ours, theirs, rules) -> tuple[str, str]:
    """Which snapshot is newer, by the newest date each side wrote into it."""
    o, t = _newest(base, ours, rules), _newest(base, theirs, rules)
    side = _later_of(o, t) if o and t else ""
    if side == "a":
        return "ours", f"dated {o}, the other {t}"
    if side == "b":
        return "theirs", f"dated {t}, the other {o}"
    return "", ""


def _ways_whole(table) -> dict:
    """{spot: "commit" or "merge"} from a JSON_FILES `whole` entry: where no date says
    which snapshot is newer, the later commit's, or ("merge") key by key."""
    if isinstance(table, dict):
        return dict(table)
    return {k: "commit" for k in table or ()}


def _record_side(base: dict, ours: dict, theirs: dict, rules: dict) -> tuple[str, str]:
    """Where both sides wrote this record again since the copy both began from, which wrote
    it later, by its first stamp that says: ("ours" or "theirs", the two dates), else ""."""
    stamps = _ways(rules.get("stamps"))
    for f, way in stamps.items():
        if f in ours and f in theirs:
            side, why = _decide(base.get(f), ours[f], theirs[f], way)
            if side:
                return side, why
    return "", ""


def _version(rec):
    v = rec.get("version") if isinstance(rec, dict) else rec
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _higher_version(base, ours, theirs) -> tuple[str, str]:
    """build_versions.json: the higher version of one part of the build stands; at one
    version, the later date; else this side's. Never a conflict: both are the app's own."""
    a, b = _version(ours), _version(theirs)
    if a is not None and b is not None and a != b:
        return ("ours", f"version {a} against {b}") if a > b else \
            ("theirs", f"version {b} against {a}")
    da = ours.get("date") if isinstance(ours, dict) else None
    db = theirs.get("date") if isinstance(theirs, dict) else None
    side = _later_of(da, db)
    if side:
        return ("ours" if side == "a" else "theirs"), "the same version, recorded later"
    if a is None and b is not None:
        return "theirs", "the only version recorded"
    return "ours", "the same version"


def _further(base, ours, theirs) -> tuple[str, str]:
    """The sweep cursor: the later round's place for a portal stands; on one day, the one
    that sent more from the same starting place, which is the further along."""
    if not (isinstance(ours, dict) and isinstance(theirs, dict)):
        return "", ""
    side = _later_of(ours.get("date"), theirs.get("date"))
    if side:
        return ("ours" if side == "a" else "theirs"), "the later round"
    try:
        a, b = int(ours.get("sent") or 0), int(theirs.get("sent") or 0)
    except (TypeError, ValueError):
        return "", ""
    if a != b:
        return ("ours", f"{a} sent against {b}") if a > b else ("theirs", f"{b} sent against {a}")
    if ours.get("next") == theirs.get("next"):
        return "ours", "the same place"
    return "", ""


PICKERS = {"higher_version": _higher_version, "further": _further}


# Kept for a person's own tests that call it (tools/public_names.py): the page record now
# merges by `newest_written`, the newer whole record winning (2026-11-04).
def first_written(base, ours, theirs, rule: dict, settled: list | None = None) -> tuple:
    """JSON_FILES `first`: where each side holds a different `key` that neither held in the
    copy both began from, the side stamped first keeps its record, every field `with` names
    copied onto the other side, so the merge that follows takes them whole and never mixes
    one page's address with what the other page holds. (ours, theirs), changed or not."""
    if not (isinstance(ours, dict) and isinstance(theirs, dict)):
        return ours, theirs
    base = base if isinstance(base, dict) else {}
    key = rule["key"]
    a, b = ours.get(key), theirs.get(key)
    if not a or not b or a == b or base.get(key) in (a, b):
        return ours, theirs
    side = _later_of(ours.get(rule["stamp"]), theirs.get(rule["stamp"]))
    if not side:
        return ours, theirs
    first, second = (theirs, ours) if side == "a" else (ours, theirs)
    kept = dict(second)
    for f in rule["with"]:
        if f in first:
            kept[f] = first[f]
        else:
            kept.pop(f, None)
    if settled is not None:
        settled.append(f"{key}: both sides wrote one: kept {_show(first[key])}, the first "
                       f"(dated {first.get(rule['stamp'])}); the other side had "
                       f"{_show(second[key])}")
    return (kept, theirs) if side == "a" else (ours, kept)


def newest_written(base, ours, theirs, rule: dict, settled: list | None = None) -> tuple:
    """JSON_FILES `newest`: where the two sides hold different records (the fields `with`
    names), the side stamped later (`stamp`) keeps its record, every one of those fields
    copied onto the other side, so the merge that follows takes it whole and never mixes one
    page's address with what another page holds. The copy both began from plays no part: a
    side that went back to an older record (a branch left for days, a record taken from one)
    holds the older stamp, and the newer stands. (ours, theirs), changed or not."""
    if not (isinstance(ours, dict) and isinstance(theirs, dict)):
        return ours, theirs
    fields = rule["with"]
    if all(ours.get(f) == theirs.get(f) for f in fields):
        return ours, theirs
    side = _later_of(ours.get(rule["stamp"]), theirs.get(rule["stamp"]))
    if not side:
        return ours, theirs
    newer, older = (ours, theirs) if side == "a" else (theirs, ours)
    kept = dict(older)
    for f in fields:
        if f in newer:
            kept[f] = newer[f]
        else:
            kept.pop(f, None)
    key, stamp = rule["key"], rule["stamp"]
    if settled is not None and older.get(key) and newer.get(key) != older.get(key):
        settled.append(f"{key}: both sides hold one: kept {_show(newer.get(key))}, the one "
                       f"published later (dated {newer.get(stamp)}); the other side had "
                       f"{_show(older[key])} (dated {older.get(stamp)})")
    return (ours, kept) if side == "a" else (kept, theirs)

# A research fact's own identity, as company_research._fact_id gives it: its page (the
# link, scheme and host lower-cased, no trailing slash) and its words (the quote, else the
# claim, with case, curly quotes, dashes and spacing folded), so one fact two chats saved
# is one fact (tests hold the two to the same answer).
_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
                         "\u2013": "-", "\u2014": "-", "\u00a0": " ", "\u202f": " "})


def _norm_url(u) -> str:
    from urllib.parse import urlsplit
    u = str(u or "").strip()
    parts = urlsplit(u)
    if not parts.netloc:
        return u.lower()
    return "%s://%s%s%s" % (parts.scheme.lower(), parts.netloc.lower(),
                            parts.path.rstrip("/") or "/",
                            ("?" + parts.query) if parts.query else "")


def _norm_text(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").translate(_QUOTES)).strip().casefold()


def fact_id(f) -> tuple:
    if not isinstance(f, dict):
        return ("", _norm_text(f))
    return (_norm_url(f.get("url") or f.get("source_url")),
            (_norm_text(f.get("quote")) or _norm_text(f.get("claim")))[:240])


def _show(value) -> str:
    """A value as the merge names it to the person's chat, kept short."""
    text = repr(value) if not isinstance(value, (dict, list)) else json.dumps(
        value, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= 200 else text[:197] + "..."


def _settle(settled, path, kept, other, why) -> None:
    if settled is not None:
        settled.append(f"{path or 'the whole file'}: both changed it: kept {_show(kept)}, "
                       f"the later change{f' ({why})' if why else ''}; the other side had "
                       f"{_show(other)}")


def merge_list(base, ours: list, theirs: list, fields, path: str,
               settled: list | None = None, rules: dict | None = None,
               spot: str | None = None, lists: dict | None = None) -> tuple[list, list[str]]:
    """A list of records both sides changed, item by item: ours in its order, then what
    only theirs added. An item both kept is merged field by field; one a side removed
    goes, unless the other side changed it, which is a conflict, or the list is one its
    writer never shortens (`{"keep": True}`), when it stays. With no `fields` an item is
    known by all of itself: a list only ever added to, unioned with nothing twice."""
    keep = isinstance(fields, dict) and bool(fields.get("keep"))
    fields = fields.get("key", ()) if isinstance(fields, dict) else fields
    spot = path if spot is None else spot

    def key(item):
        if fields == "fact":
            return ("fact",) + fact_id(item)
        if isinstance(item, dict) and fields and any(item.get(f) not in (None, "")
                                                     for f in fields):
            return tuple(json.dumps(item.get(f), sort_keys=True) for f in fields)
        return ("", json.dumps(item, sort_keys=True))

    def index(items):
        out: dict = {}
        for it in items:
            out.setdefault(key(it), it)
        return out

    b = index(base if isinstance(base, list) else [])
    o, t = index(ours), index(theirs)
    out, problems = [], []
    for n, item in enumerate(ours, 1):
        k = key(item)
        label = f"{path} item {n}"
        if k in t:
            merged, more = merge_json(b.get(k), item, t[k], label, None, settled, lists,
                                      rules, (), spot + "/#")
            out.append(merged)
            problems += more
        elif k in b and not keep:
            if item != b[k]:
                problems.append(label + " (removed on one side, changed on the other)")
                out.append(item)
        else:
            out.append(item)
    for k, item in t.items():
        if k in o:
            continue
        if k in b and not keep:
            if item != b[k]:
                problems.append(f"{path} item (removed on one side, changed on the other)")
                out.append(item)
        else:
            out.append(item)
    return out, problems


def merge_json(base, ours, theirs, path: str = "", later=None,
               settled: list | None = None, lists: dict | None = None,
               rules: dict | None = None, _recs: tuple = (),
               _spot: str | None = None) -> tuple[object, list[str]]:
    """Dicts merge key by key, all the way down; a list `lists` names, item by item
    (merge_list); anything else three ways. A value both sides changed takes the later
    change: by the dates its record keeps where `rules` (json_rules) names them, else by
    `later(path, ours, theirs)` where that knows; else it is left for a person. A snapshot
    (`whole`) is kept whole from one side, and a record with a rule of its own (`pick`) is
    settled by it."""
    spot = path if _spot is None else _spot
    if ours == theirs or theirs == base:
        return ours, []
    if ours == base:
        return theirs, []
    rules = rules or {}
    key = _rule(lists, spot)
    if key is not None and isinstance(ours, list) and isinstance(theirs, list):
        out, problems = merge_list(base, ours, theirs, key, path, settled, rules, spot, lists)
        field = _rule(rules.get("order"), spot)
        if field:
            out.sort(key=lambda r: str(r.get(field) if isinstance(r, dict) else r).lower())
        return out, problems
    pick = _rule(rules.get("pick"), spot)
    if pick:
        side, why = PICKERS[pick](base, ours, theirs)
        if side:
            kept, other = (ours, theirs) if side == "ours" else (theirs, ours)
            _settle(settled, path, kept, other, why)
            return kept, []
        return ours, [f"{path or '(the whole file)'} (both changed it: this side "
                      f"{_show(ours)}, the other {_show(theirs)}; nothing says which is later)"]
    whole = _rule(_ways_whole(rules.get("whole")), spot)
    if whole:
        side, why = _whole(base, ours, theirs, rules)
        if not side and later and whole == "commit":
            side, why = later(path, ours, theirs), ""
        if side:
            kept, other = (ours, theirs) if side == "ours" else (theirs, ours)
            _settle(settled, path, kept, other, why)
            return kept, []
    if not (isinstance(ours, dict) and isinstance(theirs, dict)):
        # A record its writer dates is written whole, so its date settles any value in it.
        # Otherwise only a single value is settled by the later change: a list both sides
        # added to would lose the other side's items, so it is left for a person as before.
        side, why = _by_date(spot, base, ours, theirs, rules, _recs)
        if not side:
            scalar = all(v is None or isinstance(v, (str, int, float, bool))
                         for v in (ours, theirs))
            side = later(path, ours, theirs) if later and path and scalar else ""
        if side:
            kept, other = (ours, theirs) if side == "ours" else (theirs, ours)
            _settle(settled, path, kept, other, why)
            return kept, []
        return ours, [f"{path or '(the whole file)'} (both changed it: this side "
                      f"{_show(ours)}, the other {_show(theirs)}; nothing says which is later)"]
    base = base if isinstance(base, dict) else {}
    recs = _recs + ((base, ours, theirs),)
    # A record both sides wrote again: every value the later one holds is its, even one it
    # left as it was and the other side changed earlier (a host checked again and found as
    # before). Values with rules of their own, lists merged item by item, notes and records
    # inside it are merged as their own.
    newer, why = _record_side(base, ours, theirs, rules)
    own = _ways(rules.get("stamps"))
    out, problems = {}, []
    for k in list(ours) + [k for k in theirs if k not in ours]:
        sub = f"{path}/{k}" if path else str(k)
        at = f"{spot}/{k}" if spot else str(k)
        if (newer and k in ours and k in theirs and k in base and ours[k] != theirs[k]
                and base[k] in (ours[k], theirs[k]) and k not in NOTES and k not in own
                and not (isinstance(ours[k], dict) and isinstance(theirs[k], dict))
                and _rule(lists, at) is None and _rule(_ways(rules.get("dated")), at) is None
                and _rule(rules.get("pick"), at) is None
                and _rule(_ways_whole(rules.get("whole")), at) is None):
            kept, other = (ours[k], theirs[k]) if newer == "ours" else (theirs[k], ours[k])
            if kept == base[k]:
                _settle(settled, sub, kept, other, why + ", the record written later")
            out[k] = kept
            continue
        if k not in theirs:
            if k in base and ours[k] != base[k]:
                problems.append(sub + " (removed on one side, changed on the other)")
            if k not in base or ours[k] != base[k]:
                out[k] = ours[k]
            continue
        if k not in ours:
            if k in base and theirs[k] != base[k]:
                problems.append(sub + " (removed on one side, changed on the other)")
                out[k] = theirs[k]
            elif k not in base:
                out[k] = theirs[k]
            continue
        if k in NOTES and all(isinstance(v, str) for v in (ours[k], theirs[k])):
            out[k] = merge_note(base.get(k) or "", ours[k], theirs[k])
            continue
        out[k], more = merge_json(base.get(k), ours[k], theirs[k], sub, later, settled, lists,
                                  rules, recs, at)
        problems += more
    return out, problems


def _form(text: str, rules: dict) -> tuple:
    """(indent, ascii, newline) the file is written with: its writer's, or, where JSON_FILES
    says "ours", read from this side's own text (a file Claude writes by hand)."""
    indent, ascii_, newline = rules.get("indent"), rules.get("ascii"), rules.get("newline")
    if indent == "ours":
        m = re.search(r"\n([ \t]+)\S", text)
        indent = (m.group(1) if "\t" in m.group(1) else len(m.group(1))) if m else None
    if ascii_ == "ours":
        ascii_ = bool(re.search(r"\\u[0-9a-fA-F]{4}", text)) and text.isascii()
    if newline == "ours":
        newline = text.endswith("\n")
    return indent, bool(ascii_), newline is not False


def dump(data, rules: dict, ours_text: str = "") -> str:
    """The merged file as its writer writes it (JSON_FILES `indent`, `sort`, `ascii`,
    `newline`)."""
    indent, ascii_, newline = _form(ours_text, rules)
    if rules.get("sort") == "top" and isinstance(data, dict):
        data = dict(sorted(data.items()))
    text = json.dumps(data, indent=indent, ensure_ascii=ascii_,
                      sort_keys=rules.get("sort") == "all")
    return text + ("\n" if newline else "")


# ------------------------------------------------------------------ the driver

# What git runs. Git runs a merge driver from the top of the working tree, so the path
# is relative and each worktree runs its own copy; a checkout too old to have this file
# merges lines the way git always did.
# merge_state exits 0 or 1 when it merged; anything else (an old Python, a crash,
# no Python at all) and git's own line merge runs instead, which marks every
# conflict in the file. The file is never left holding only this side's rows.
#
# It runs the Python that installed it, by its full path: `python3` is not a command on
# a Windows computer with python.org's Python (docs.python.org/3/using/windows.html), so
# a driver that said python3 fell back to the line merge there on every merge, and two
# chats' appended rows conflicted. Should that Python have gone since (removed, or a
# virtual environment deleted), the shell says 126 or 127 and tools/py.sh finds another.
# Git runs the driver in a shell (on Windows, the one Git Bash brings), so the path is
# written with forward slashes and single-quoted.
def _sh_quote(path: str) -> str:
    return "'" + path.replace("\\", "/").replace("'", "'\\''") + "'"


def driver(python: str = "") -> str:
    exe = _sh_quote(python or sys.executable or "python3")
    return ("if [ -f tools/merge_state.py ]; then "
            f"{exe} tools/merge_state.py %O %A %B %P; rc=$?; "
            "if [ $rc -ge 126 ] && [ -f tools/py.sh ]; then "
            "sh tools/py.sh tools/merge_state.py %O %A %B %P; rc=$?; fi; "
            "if [ $rc -le 1 ]; then exit $rc; fi; fi; "
            "git merge-file -L ours -L base -L theirs %A %O %B")


DRIVER = driver()


def install(root: str) -> None:
    """Point this repo's git config at the driver. Config is not committed, so every
    container sets it again: two quick config writes, and never an error."""
    import subprocess
    for k, v in (("name", "state files, row by row"), ("driver", driver())):
        subprocess.run(["git", "-C", root, "config", f"merge.ljs-state.{k}", v],
                       capture_output=True, text=True, check=False,
                       encoding="utf-8", errors="replace")


# ------------------------------------------------------------------ which change was later

# The other side of whatever git is doing. A merge names it in the driver's environment
# (GITHEAD_<sha>, which git sets for its conflict labels: MERGE_HEAD is written only after
# the driver has run); a rebase names the commit it is picking in its own todo list.
_THEIRS = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "REBASE_HEAD")


def _git(*args) -> str:
    import subprocess
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=30,
                           encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout if r.returncode == 0 else ""


def _theirs() -> str:
    # Any case: on Windows Python gives every name in os.environ in capitals
    # (https://docs.python.org/3/library/os.html#os.environ), so GITHEAD_<sha> came back
    # with its sha in capitals, matched nothing, and every change both chats made to one
    # row was left for a person there (2026-10-25).
    named = [k[len("GITHEAD_"):].lower() for k in os.environ
             if re.fullmatch(r"GITHEAD_[0-9a-fA-F]{40}([0-9a-fA-F]{24})?", k)]
    if len(named) == 1:
        return named[0]
    if named:
        return ""                                   # an octopus merge: no one other side
    for ref in _THEIRS:
        got = _git("rev-parse", "-q", "--verify", ref).strip()
        if got:
            return got
    gd = _git("rev-parse", "--git-dir").strip()
    try:
        with open(os.path.join(gd, "rebase-merge", "done"), encoding="utf-8") as fh:
            last = [ln.split() for ln in fh if ln.strip() and not ln.startswith("#")]
    except OSError:
        return ""
    return last[-1][1] if last and len(last[-1]) > 1 else ""


def git_later(path: str):
    """`later(key, field, ours, theirs)` for the file git is merging, read from each side's
    own history: when did each side's value appear, by the author date of the commit that
    set it (a rebase keeps it)? None where git has no other side to read, and the merge
    then leaves a field both sides changed for a person, as before."""
    theirs_ref = _theirs()
    if not theirs_ref:
        return None
    base_ref = _git("merge-base", "HEAD", theirs_ref).strip()
    if not base_ref:
        return None
    name = os.path.basename(path)
    fields = KEYS.get(name)
    cache: dict = {}

    def value(commit, key, field):
        if commit not in cache:
            text = _git("show", f"{commit}:{path}")
            if name.endswith(".json"):
                try:
                    cache[commit] = json.loads(text) if text.strip() else {}
                except ValueError:
                    cache[commit] = {}
            else:
                _head, rows = _read(text)
                cache[commit] = _keyed(rows, fields) if fields else {}
        got = cache[commit]
        if name.endswith(".json"):
            # A key can hold a slash itself (seen_jobs.json is keyed by URL), so the
            # path is walked by the longest key at each level that starts what is left.
            rest = key
            while rest:
                if not isinstance(got, dict):
                    return None
                part = max((k for k in got if rest == k or rest.startswith(k + "/")),
                           key=len, default=None)
                if part is None:
                    return None
                got, rest = got[part], rest[len(part) + 1:]
            return got
        row = got.get(key)
        return None if row is None else row.get(field)

    def introduced(ref, key, field, final) -> int:
        """When `final` became this side's value: the oldest of the newest run of commits
        that carry it. 0 where the side never set it since the two parted."""
        when = 0
        for ln in _git("log", "--format=%H %at", f"{base_ref}..{ref}", "--", path).splitlines():
            commit, _, at = ln.partition(" ")
            if value(commit, key, field) != final:
                break
            when = int(at) if at.isdigit() else 0
        return when

    def later(key, field, ours, theirs):
        a = introduced("HEAD", key, field, ours)
        b = introduced(theirs_ref, key, field, theirs)
        if a and b and a != b:
            return "ours" if a > b else "theirs"
        return ""

    if name.endswith(".json"):                     # a JSON value is found by its path alone
        return lambda where, ours, theirs: later(where, None, ours, theirs)
    return later


def eol(path: str) -> str | None:
    """The line ending .gitattributes asks for `path` ("\n" for eol=lf, "\r\n" for
    eol=crlf), or None when it names none or git cannot say."""
    got = _git("check-attr", "eol", "--", path).strip()
    value = got.rsplit(": ", 1)[-1] if got else ""
    return {"lf": "\n", "crlf": "\r\n"}.get(value)


def merge(base: str, ours: str, theirs: str, path: str, later=None,
          settled: list | None = None, ending: str | None = None,
          noted: list | None = None) -> tuple[str, list[str]]:
    """One file, merged. What a later change settled goes in `settled`, for the person to be
    told; what it settled in the app's own records (JSON_FILES `quiet`) in `noted`, where
    given, for nobody."""
    name = os.path.basename(path)
    base, ours, theirs = _unmark(base), _unmark(ours), _unmark(theirs)
    if name.endswith(".json"):
        try:
            b = json.loads(base) if base.strip() else {}
            o, t = json.loads(ours), json.loads(theirs)
        except ValueError as e:
            return ours, [f"{path}: not JSON on one side ({e})"]
        rules = json_rules(path)
        quiet = noted if rules["quiet"] and noted is not None else settled
        if rules["newest"]:
            o, t = newest_written(b, o, t, rules["newest"], quiet)
        merged, problems = merge_json(b, o, t, later=later, settled=quiet,
                                      lists=rules["lists"], rules=rules)
        return dump(merged, rules, ours), problems
    return merge_csv(base, ours, theirs, name, later=later, settled=settled, ending=ending)


# ------------------------------------------------------------------ a merge that stopped
#
# A merge of two chats' work that stopped on a file the row merge does not cover (the
# profile's own words, a setting, a draft) was aborted, and the whole chat's work waited on a
# branch that every later chat tried, stopped on and left: drafts, tracker rows and all,
# never on master, with a daily "the next run tries again" that never came true (the
# stranger audit, 2026-11-03, X-13). Each such file is settled here instead, losing neither
# side, so the rest of the work lands:
#
# - one side holding only a copy the other side already had and moved on from (the same
#   change made on both sides, the newer one changed it again; or, where earlier merges
#   crossed, the copy one of the merge's common ancestors held): the newer copy, with
#   nothing beside it and nothing asked, since the older side brought nothing of its own. A
#   branch left nine days earlier, brought in whole, put copies of the person's own tests
#   beside the newer ones and a [CONFIRM: ...] line on top of eight of them, though it had
#   changed none of them itself (a report from a person's copy, 2026-11-04);
# - the same improvement made by two chats (each side's own commits on the file are all
#   "Profile upgrade: <id>", the same ids): master's copy, as RUNBOOK.md has always said;
# - the person's own words in profile/ (.md, .txt): both versions kept, one after the
#   other, under a [CONFIRM: ...] line, which the page asks as a To do card (and a chat with
#   no page asks through the unconfirmed-facts upgrade), so the person decides which stays;
# - a document of theirs (under documents/, cv/ or cover_letters/) both chats changed: the
#   one committed later, never a copy beside it: a resume or a letter is made again by the
#   app, and a copy beside it was left by the dozen (a report from a person's copy,
#   2026-11-04). The other chat's version is kept in SPARE_DIR, out of their folders, which
#   the app tidies, as on every path here where one side is kept whole (the engine review,
#   2026-11-05); the person's own test (profile/tests/) the same;
# - anything else: this side's whole file, nothing of the other's merged into it, and the
#   other side's whole file in the saved history (the merge's other parent) and in SPARE_DIR
#   on this computer, never beside the person's files: a <file>.from-another-chat copy was
#   saved into their folders, and "this chat's version kept" was said of a line merge of the
#   two (the maintainer, 2026-11-04). A profile .py also gets the [CONFIRM: ...] line, as a
#   comment, with where Claude finds the other version under it;
# - a file one side removed and the other changed: the changed one is kept.
#
# Never an app file: a conflict there is left as it was, for the caller to stop on.

SIDE = ".from-another-chat"
_TEXT = (".md", ".txt")
ASK_BOTH = ("[CONFIRM: two of your chats changed this part at the same time, and both "
            "versions are kept below: which one stays]")
ASK_SIDE = ("[CONFIRM: two of your chats changed this file at the same time; this chat's "
            "version is kept here, and Claude can show you the other one: which one stays]")
SHOW_OTHER = "# The other chat's version, for Claude: git show {ref}:{path}"


def _g(root: str, *args: str, text: bool = True):
    import subprocess
    return subprocess.run(["git", "-C", root, *args], capture_output=True, check=False,
                          **({"text": True, "encoding": "utf-8", "errors": "replace"}
                             if text else {}))


def _blocks(text: str, keep: str) -> tuple[str, int]:
    """The file with each conflict block resolved: "ours", "theirs" or "both" (this side's
    lines, then the other's, under ASK_BOTH). (text, blocks found)."""
    out: list[str] = []
    state, o, t, n = "", [], [], 0
    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        if not state and bare.startswith("<<<<<<<"):
            state, o, t = "o", [], []
            continue
        if state == "o" and bare.startswith("|||||||"):
            state = "b"
            continue
        if state in ("o", "b") and bare == "=======":
            state = "t"
            continue
        if state == "t" and bare.startswith(">>>>>>>"):
            n += 1
            nl = "\r\n" if line.endswith("\r\n") else "\n"
            if keep == "both":
                both = o + t
                both = [ln if ln.endswith(("\n", "\r")) else ln + nl for ln in both]
                out += [ASK_BOTH + nl] + both
            else:
                out += o if keep == "ours" else t
            state = ""
            continue
        if state == "o":
            o.append(line)
        elif state == "t":
            t.append(line)
        elif not state:
            out.append(line)
    return "".join(out), n


def _same_upgrade(root: str, path: str) -> bool:
    """Both sides changed `path` only in "Profile upgrade: <id>" commits, the same ids."""
    base = _g(root, "merge-base", "HEAD", "MERGE_HEAD").stdout.strip()
    if not base:
        return False

    def ids(side: str) -> set:
        got = _g(root, "log", "--no-merges", "--format=%s", f"{base}..{side}", "--",
                 path).stdout.splitlines()
        if not got or not all(s.startswith("Profile upgrade: ") for s in got):
            return set()
        return {s.split(":", 1)[1].strip() for s in got}
    mine, theirs = ids("HEAD"), ids("MERGE_HEAD")
    return bool(mine) and mine == theirs


def _held_before(root: str, path: str, stages: dict) -> str:
    """For a conflicted file one side holds only an older copy of: "--ours" or "--theirs",
    the newer side; "" when each brought something of its own. A side's copy is older when
    it is the copy one of the merge's common ancestors held (git conflicts there only where
    earlier merges crossed and its base is a blend of several), or one the other side's own
    commits already wrote and then changed again (the same change made on both sides)."""
    if "2" not in stages or "3" not in stages or stages["2"] == stages["3"]:
        return ""
    held = set()
    for b in _g(root, "merge-base", "--all", "HEAD", "MERGE_HEAD").stdout.split():
        r = _g(root, "rev-parse", "-q", "--verify", f"{b}:{path}")
        if r.returncode == 0:
            held.add(r.stdout.strip())

    def older(st: str, mine: str, other: str) -> bool:
        if stages[st] in held:
            return True
        r = _g(root, "log", "--format=%H", "--find-object=" + stages[st], f"{mine}..{other}",
               "--", path)
        return r.returncode == 0 and bool(r.stdout.strip())
    ours_old = older("2", "HEAD", "MERGE_HEAD")
    theirs_old = older("3", "MERGE_HEAD", "HEAD")
    if theirs_old and not ours_old:
        return "--ours"
    if ours_old and not theirs_old:
        return "--theirs"
    return ""


# Where a copy goes that has to be kept but must not sit beside the person's files: one
# folder at the top, never saved (.gitignore) and cleared after SPARE_DAYS by every settle.
SPARE_DIR = ".other-chat-copies"
SPARE_DAYS = 30
_DOCS = ("documents/", "cv/", "cover_letters/")
_OWN_TESTS = "profile/tests/"


def _later_side(root: str, path: str) -> str:
    """"--ours" or "--theirs": the side whose last commit on `path` is later (ours on a tie)."""
    def when(ref):
        got = _g(root, "log", "-1", "--format=%ct", ref, "--", path).stdout.strip()
        return int(got) if got.isdigit() else 0
    return "--theirs" if when("MERGE_HEAD") > when("HEAD") else "--ours"


def _lost(stages: dict, keep: str) -> str:
    """The blob of the side not kept ("--ours" kept: theirs, stage 3)."""
    return stages["3" if keep == "--ours" else "2"]


def _spare(root: str, path: str, blob: str) -> str:
    """Keep a blob of the losing side in SPARE_DIR; its path (relative)."""
    rel = f"{SPARE_DIR}/{path.replace('/', '__')}.{blob[:8]}"
    os.makedirs(os.path.join(root, SPARE_DIR), exist_ok=True)
    data = _g(root, "cat-file", "blob", blob, text=False).stdout
    with open(os.path.join(root, rel), "wb") as fh:
        fh.write(data)
    return rel


def tidy_spares(root: str, now: float | None = None) -> None:
    """Remove what SPARE_DIR holds past SPARE_DAYS, its age on the files' own clock
    (file_clock; `now` is a now on it). Never raises."""
    base = os.path.join(root, SPARE_DIR)
    try:
        names = os.listdir(base)
        if not names:
            return
        try:
            import file_clock
            at = file_clock.now(base) if now is None else now
        except ImportError:  # the driver alone, without the app's folder: Python's clock
            import time
            at = time.time() if now is None else now
        for n in names:
            f = os.path.join(base, n)
            if at - os.path.getmtime(f) > SPARE_DAYS * 86400:
                os.remove(f)
    except OSError:
        pass


_WRITTEN = re.compile(r"^Written (\d{4}-\d{2}-\d{2})\b", re.M)


def _written(root: str, stages: dict) -> str:
    """For a conflicted file the app wrote and dated on both sides (a "Written <day>" line
    near its top, as every call prep has): "--ours" or "--theirs", whichever was written
    later (master's on the same day); "" when either side has no such line."""
    if "2" not in stages or "3" not in stages:
        return ""
    days = []
    for st in ("2", "3"):
        head = _g(root, "cat-file", "blob", stages[st]).stdout[:600]
        m = _WRITTEN.search(head)
        if not m:
            return ""
        days.append(m.group(1))
    return "--ours" if days[0] > days[1] else "--theirs"


def settle(root: str) -> tuple[list[str], list[str]]:
    """Settle every conflicted file of the person's in the merge stopped in `root`.
    (what was done, one line each, for Claude; the paths left as they were). Each settled
    file is staged; the caller commits the merge once nothing is left."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import personal_paths
    except Exception:  # noqa: BLE001  nothing settled: the caller stops as before
        return [], []
    files = [p for p in _g(root, "diff", "--name-only", "-z", "--diff-filter=U").stdout
             .split("\0") if p]
    done: list[str] = []
    left: list[str] = []
    tidy_spares(root)
    for p in files:
        if not personal_paths.is_personal(p):
            left.append(p)
            continue
        stages = {}
        for ln in _g(root, "ls-files", "-u", "-z", "--", p).stdout.split("\0"):
            meta, _, name = ln.partition("\t")
            parts = meta.split()
            if name == p and len(parts) == 3:
                stages[parts[2]] = parts[1]
        full = os.path.join(root, p)
        newer = _held_before(root, p, stages)
        if "2" not in stages or "3" not in stages:
            keep = "--ours" if "2" in stages else "--theirs"
            _g(root, "checkout", keep, "--", p)
            done.append(f"{p}: one chat removed it and the other changed it; the changed "
                        "one is kept")
        elif newer:
            _g(root, "checkout", newer, "--", p)
            done.append(f"{p}: one chat held only an older copy of it; the newer one is kept")
        elif _written(root, stages):
            # A document the app writes and dates ("Written 2026-11-04."), rebuilt by two chats
            # on different days: the later one is current and the next rebuild makes it so
            # anyway, so it is kept with no side copy. Two chats that took the 4.9.0 update a
            # day apart stopped on every call prep the update rebuilt (its rehearsal).
            keep = _written(root, stages)
            _g(root, "checkout", keep, "--", p)
            done.append(f"{p}: rebuilt by two chats; the later one is kept, and the other is "
                        f"saved as {_spare(root, p, _lost(stages, keep))}")
        elif p.startswith(_DOCS) and not _written(root, stages):
            # The later one, never a copy beside it; the other in the spare folder, out of
            # their folders, as on every other path (the engine review, 2026-11-05).
            keep = _later_side(root, p)
            _g(root, "checkout", keep, "--", p)
            done.append(f"{p}: changed by two chats; the later one is kept, and the other is "
                        f"saved as {_spare(root, p, _lost(stages, keep))}")
        elif p.startswith(_OWN_TESTS):
            keep = _later_side(root, p)
            lost = stages["3" if keep == "--ours" else "2"]
            _g(root, "checkout", keep, "--", p)
            done.append(f"{p}: changed by two chats; the later one is kept, and the other "
                        f"is saved as {_spare(root, p, lost)}")
        elif _same_upgrade(root, p):
            _g(root, "checkout", "--theirs", "--", p)
            done.append(f"{p}: the same improvement made by two chats; the other's copy "
                        f"is kept, and this one is saved as {_spare(root, p, stages['2'])}")
        else:
            try:
                with open(full, encoding="utf-8", newline="") as fh:
                    text = fh.read()
            except (OSError, UnicodeDecodeError):
                text = ""
            marked = "\n<<<<<<<" in "\n" + text and "\n>>>>>>>" in text
            if marked and p.startswith("profile/") and p.endswith(_TEXT):
                merged, _n = _blocks(text, "both")
                with open(full, "w", encoding="utf-8", newline="") as fh:
                    fh.write(merged)
                done.append(f"{p}: both versions kept, and the person is asked which "
                            "stays (a To do on the page)")
            else:
                # This chat's whole file: the clashing lines resolved its way with the other
                # side's other lines merged in was said as "this chat's version kept", and
                # was neither. The other side's whole file is in the saved history (the
                # merge's other parent) and in SPARE_DIR here, never beside the person's own.
                _g(root, "checkout", "--ours", "--", p)
                spare = _spare(root, p, stages["3"])
                other = _g(root, "rev-parse", "-q", "--verify", "MERGE_HEAD").stdout.strip()[:12]
                if p.startswith("profile/") and p.endswith(".py"):
                    with open(full, encoding="utf-8", newline="") as fh:
                        body = fh.read()
                    with open(full, "w", encoding="utf-8", newline="") as fh:
                        fh.write("# " + ASK_SIDE + "\n" + SHOW_OTHER.format(
                            ref=other or "MERGE_HEAD", path=p) + "\n" + body)
                done.append(f"{p}: this chat's whole version kept, nothing of the other's "
                            f"merged into it; the other's is in the saved history "
                            f"({other or 'the merge'}:{p}) and in {spare} on this computer")
        r = _g(root, "add", "-f", "--", p)
        if r.returncode != 0:
            done.pop()
            left.append(p)
    return done, left


def _still_asked(beside: str, copy_name: str) -> bool:
    """The file beside a copy still asks the person which of the two stays: a [CONFIRM: ...]
    line an older settle wrote naming the copy. Left for the person, who is asked already."""
    try:
        with open(beside, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError):
        return False
    return any("[CONFIRM" in ln and copy_name in ln for ln in text.splitlines())


def clear_old_copies(root: str) -> tuple[list[str], list[str]]:
    """Clear the *.from-another-chat copies an older version left beside the person's files
    (documents, their own tests, and since 2026-11-04 anywhere in their folders, as a settle
    saved one beside a setting or a note), once: where the file beside one is identical, or
    was changed as late or later than the copy was made. (cleared, undecided): any copy where
    the copy is the later one or has no file beside it is left, named. One the file beside it
    still asks the person about (a [CONFIRM: ...] naming it) is left and not named: the
    question is on the page already, and once it is answered the next save clears the copy.
    Never raises."""
    import local_path
    import personal_paths
    cleared: list[str] = []
    undecided: list[str] = []
    try:
        for full_dir, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", SPARE_DIR)]
            for n in names:
                if SIDE not in n:
                    continue
                full = os.path.join(full_dir, n)
                rel = local_path.rel(full, root)
                base_rel = rel[:rel.index(SIDE)]
                if not personal_paths.is_personal(base_rel):
                    continue
                beside = os.path.join(full_dir, n.split(SIDE)[0])
                if not os.path.isfile(beside):
                    undecided.append(rel)
                    continue
                if _still_asked(beside, n):
                    continue
                with open(full, "rb") as a, open(beside, "rb") as b:
                    same = a.read() == b.read()
                def last(path, disk):
                    got = _g(root, "log", "-1", "--format=%ct", "--", path).stdout.strip()
                    return int(got) if got.isdigit() else int(os.path.getmtime(disk))
                if same or last(base_rel, beside) >= last(rel, full):
                    if _g(root, "ls-files", "--error-unmatch", "--", rel).returncode == 0:
                        _g(root, "rm", "-f", "-q", "--", rel)
                    if os.path.exists(full):
                        os.remove(full)
                    cleared.append(rel)
                else:
                    undecided.append(rel)
    except OSError:
        pass
    return cleared, undecided


# Exit codes. 0 merged; 1 merged with real conflicts marked for a person. Anything
# else means this driver could not merge at all and wrote nothing, and the driver
# command (DRIVER) then runs git's own line merge, which marks every conflict: a
# state file is never left as one side's copy with the other side's rows lost.
COULD_NOT = 3


def main(argv: list[str]) -> int:
    if argv[:1] in (["-h"], ["--help"]):
        print("usage: python3 tools/merge_state.py %O %A %B %P  (git runs it as the merge "
              "driver for the state files; tools/sync_app.py sets that up)")
        return 0
    if sys.version_info[:2] < FLOOR:
        print(f"merge_state: Python {FLOOR[0]}.{FLOOR[1]} or newer is needed; this is "
              f"{platform.python_version()} (python3 tools/env_check.py says how to install it)",
              file=sys.stderr)
        return COULD_NOT
    # What it prints names people ("Łukasz"), and a cp1252 Windows terminal could not show
    # them: the driver stopped mid-merge and git fell back to its line merge.
    try:
        import python_floor
        python_floor.utf8_stdio()
    except Exception:  # noqa: BLE001  git runs this alone; nothing else need be importable
        pass
    if len(argv) != 4:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    base_p, ours_p, theirs_p, path = argv

    def read(p):
        with open(p, "rb") as f:
            return decode(f.read())

    settled: list[str] = []
    noted: list[str] = []
    try:
        text, problems = merge(read(base_p), read(ours_p), read(theirs_p), path,
                               later=git_later(path), settled=settled, ending=eol(path),
                               noted=noted)
    except Exception as e:  # noqa: BLE001  nothing is written; git's line merge takes over
        print(f"merge_state: could not merge {path} ({type(e).__name__}: {e}); "
              "git's line merge marks the conflicts instead", file=sys.stderr)
        return COULD_NOT
    with open(ours_p, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    for p in settled:
        print(f"merge_state: {p}. Claude: tell the person in plain words which of their two "
              "answers was kept and what the other said, never a file or field name; their "
              "word outranks this.", file=sys.stderr)
    for p in noted:
        print(f"merge_state: {p}. The app's own record: nothing to tell the person.",
              file=sys.stderr)
    for p in problems:
        print(f"merge_state: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
