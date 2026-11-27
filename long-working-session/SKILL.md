---
name: long-working-session
description: Puts the agent in long-session mode, where the state of the work lives in a markdown status table on disk instead of in the agent's context. The table has one row per piece of work with a concise name, a pointer (path, URL, PR, ticket, run ID), a status and optional next steps, and the agent updates it at every state change. Use this when the user says the work will be long, spans many steps, many files, many PRs, or several sessions, or asks to "track this", "keep a status file", "keep a tracker", or "don't lose track". Use it mid-session too, including after one or more context compactions or a resumed session, to rebuild the table from what has already happened. Trigger it on your own initiative when a task clearly outgrows one context window, or when a compaction summary shows you have already lost detail.
---

# Long Working Session

A long session loses its memory in pieces. Each compaction drops detail, a
resumed session starts cold, and sub-agents never saw the conversation. What
survives is what is on disk. This skill moves the state of the work into one
small markdown table that the agent keeps current, so any later context, its
own or another agent's, can pick the work up from the file alone.

The table is the source of truth. When the file and your recollection
disagree, the file wins. When the file and the live system disagree (a PR you
listed as open is merged), the live system wins and you fix the file.

## The tracker file

The file is a single table. Nothing else, except an optional one-line `#`
heading that names the goal.

```markdown
# Migrate billing jobs to the new scheduler

| Item | Pointer | Status | Next |
|---|---|---|---|
| Scheduler config | `infra/scheduler.yaml` | done | |
| Daily invoice job | PR #412 | review | address 2 comments |
| Refund job | `jobs/refund.py` | doing | port retry logic |
| Prod cutover | runbook `docs/cutover.md` | blocked | needs owner sign-off |
| Old cron cleanup | | todo | after cutover |
```

Columns:

- **Item**: a short name, two to five words. It names a deliverable, not a
  step. "Refund job", not "Started looking at the refund job code".
- **Pointer**: where the thing lives, so a cold reader can open it in one
  move. A file path, PR or CR link, ticket ID, branch, commit, run or job ID,
  doc URL. File paths are relative to the tracker's directory, or absolute
  when they live elsewhere. Several pointers are fine, separated by commas.
  Leave it empty only when nothing exists yet.
- **Status**: one word from this set, nothing else.

  | Status | Meaning |
  |---|---|
  | `todo` | Not started |
  | `doing` | In progress now |
  | `review` | Waiting on someone else's review or a check |
  | `blocked` | Cannot move; the Next cell says on what |
  | `done` | Finished and verified |
  | `dropped` | Decided not to do; the Next cell says why |
  | `unknown` | State not confirmed yet (used when rebuilding) |

- **Next**: optional. The single next action, or what a `blocked` row waits
  on. Keep it to one short phrase. Leave it empty on `done` rows.

Keep every cell short. The table is an index that points at the detail; it is
not where the detail goes. Logs, findings, diffs and long notes live in the
files the Pointer column names.

## Where the file lives

1. If the user names a path, use it.
2. If a tracker already exists for this work, use it. Look for `STATUS.md`
   at the project root, and for any path mentioned in the conversation or a
   compaction summary.
3. Otherwise create `STATUS.md` at the root of the working directory.

The path must be stable across sessions. Never put it in a temp directory
that is cleaned up when the session ends.

Inside a git repository, do not commit the tracker unless the user asks.
Add it to `.git/info/exclude` (not `.gitignore`, which would itself be a
change to commit) and tell the user once.

Tell the user the absolute path when you create the file, and repeat it in
any handoff.

## Starting a session

When the user says up front that the work will be long:

1. Create the file with a heading that names the goal.
2. Add one row per deliverable you can already see. Rows for later phases are
   fine as `todo`.
3. Show the user the table and the path, then start the work.

Do not wait for a complete plan. Rows get added as work appears.

## Joining a session already in progress

When the skill is called mid-session, or after a compaction, the table has to
be rebuilt from evidence, not from guesses.

1. Read any tracker that already exists. If it exists, it is your starting
   point; skip to step 4.
2. Collect what happened from what you can still see: the conversation, the
   compaction summary, files you created or edited, `git status` and
   `git log` on the branches involved, open PRs or CRs, tickets you touched,
   jobs you started.
3. Write one row per deliverable. Use `unknown` for any row whose state you
   cannot confirm from that evidence, with `verify` in Next.
4. Check each `unknown` and each `doing` or `review` row against the live
   system when a cheap read exists (`gh pr view`, `git log`, a job status
   call). Update the status from what you read.
5. Show the user the table and the path. Name any row still `unknown`.

Never mark a row `done` from memory alone. `done` means you saw it finished.

## Keeping it current

Update the file at every state change, before you reply to the user about
that change:

- a row starts (`todo` to `doing`)
- a pointer appears (a PR is opened, a file is created, a job gets an ID)
- something finishes, gets blocked, goes to review, or is dropped
- new work is discovered (add a row)
- the next action changes

Edit the row in place. Do not append a second row for the same item. Keep
`done` and `dropped` rows; they are the history and they stop the work from
being redone. Remove rows only when the user asks.

After every compaction or resume, read the tracker before doing anything else,
and continue from its `doing` rows.

## Sub-agents and other sessions

A sub-agent starts with no history, so give it the tracker path and the row
it owns. Tell it to update only that row, and to put its findings in a file
the Pointer column can name. When it reports back, check the row against its
result yourself.

If two writers could edit the file at once, keep the edits on one writer (you)
and have the others report to you.

## Reporting

When the user asks where things stand, read the file, check live state for
anything not `done`, update the file, and answer from it. The
`work-status-summary` skill does this in full and adds a summary and an
ordered list of next steps.

At the end of the session, or when handing off, make sure every row is
current and the Next column is filled for every row that is not `done` or
`dropped`. A handoff is then the path to the file.
