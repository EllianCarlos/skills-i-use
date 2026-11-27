---
name: work-status-summary
description: Gathers the overall status of a piece of work, checks it against the live systems it points at, and reports it as a short summary, a status table (concise item names, pointers, status, next steps), blockers that need the user, and an ordered list of next steps. Reads the long-session tracker (`STATUS.md` or a path the user names) when there is one, and builds the table from the conversation, git, PRs, tickets and job runs when there is not. Use this when the user asks "where are we", "what's the status", "what's left", "summarize the work", "what's next", "catch me up", wants a standup or handoff note, or returns to a session after a break or a compaction.
---

# Work Status Summary

A status report is only worth reading if it is true now. A PR listed as
"in review" that merged an hour ago, or a job listed as running that failed
overnight, sends the user to the wrong place. So this skill reads the live
state of every unfinished item before it writes a single status, and it says
plainly which items it could not check.

## Workflow

1. **Find the source.** In this order:
   - a tracker path the user names;
   - a tracker named in the conversation or a compaction summary;
   - `STATUS.md` at the project root (the `long-working-session` skill
     writes it there by default).

   If there is no tracker, build the item list from the conversation, the
   compaction summary, files created or edited, `git status` and `git log`
   on the branches involved, open PRs or CRs, tickets and job runs. One item
   per deliverable, not per step.

2. **Check live state for every item that is not `done` or `dropped`.** Use
   the cheapest read that answers the question, and only reads:

   | Pointer | Check |
   |---|---|
   | File or directory | Exists; uncommitted changes (`git status`) |
   | Branch or commit | `git log`, ahead/behind the base, pushed or not |
   | GitHub PR | `gh pr view <n> --json state,reviewDecision,statusCheckRollup` |
   | CR, ticket, task | That system's CLI or MCP read tool |
   | CI run, job, deploy | Its status command or API |
   | Process you started | Whether it is still running, and its last log lines |

   Run independent checks in parallel. If a check is not possible (no
   access, no tool, the system is down), keep the last known status and mark
   the item as not checked. Never fill the gap with what you expect.

3. **Update the tracker** if one exists: correct each status from what you
   read, fill in pointers you found, add rows for work you discovered. Edit
   rows in place. If there was no tracker, offer to create one with the
   `long-working-session` skill rather than creating it unasked.

4. **Write the report** in the shape below.

## Report shape

```markdown
**Summary**: <one to three sentences: the goal, how far along it is, the
single most important thing right now>

| Item | Pointer | Status | Next |
|---|---|---|---|
| Daily invoice job | [PR #412](https://github.com/org/repo/pull/412) | review | address 2 comments |
| Refund job | `/abs/path/jobs/refund.py` | doing | port retry logic |
| Prod cutover | `/abs/path/docs/cutover.md` | blocked | needs owner sign-off |
| Scheduler config | `/abs/path/infra/scheduler.yaml` | done | |

**Needs you**
- Prod cutover: sign-off from the service owner.

**Next steps**
1. Address the 2 review comments on PR #412.
2. Port the retry logic in the refund job.
3. Ask for cutover sign-off once both jobs are merged.

**Not checked**: <items whose live state could not be read, and why>
```

Rules for each part:

- **Summary**: state the position, not the history. "Two of five jobs
  migrated; the invoice job is in review and is the critical path." Not a
  narrative of what was done.
- **Table**: same columns and status words as the `long-working-session`
  tracker (`todo`, `doing`, `review`, `blocked`, `done`, `dropped`,
  `unknown`). Item names of two to five words. Order rows by what needs
  attention: `blocked`, then `review`, `doing`, `todo`, `unknown`, and
  `done` and `dropped` last. Make links clickable markdown links and file
  pointers absolute paths. If the table would run past about 15 rows, collapse
  the `done` rows into one line ("8 items done") under the table and keep the
  file as the full record.
- **Needs you**: only what the user alone can do or decide: an approval, a
  sign-in, a choice, a merge. Leave the section out when it is empty.
- **Next steps**: ordered by dependency and impact, each one concrete enough
  to start. Three to seven items. Name the item each step belongs to.
- **Not checked**: leave it out when every item was checked. Otherwise it is
  required; a status the user believes was verified, and was not, is the
  failure this skill exists to prevent.

## Scope

When the user asks about one part of the work ("where is the refund job?"),
check and report that part only, with the same honesty rules, and skip the
full table.

When the user asks for a standup or handoff note, use the same content in
the shape they ask for, and keep the facts, links and "not checked" notes
intact.

This skill reads and reports. It does not merge, retry, close or re-run
anything it finds. Those actions go into the next steps, and you take them
only when the user asks.
