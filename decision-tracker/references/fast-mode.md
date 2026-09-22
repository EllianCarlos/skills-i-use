# Fast mode

Fast mode exists for one situation: the user already holds the context, and the
answer is one keystroke. Two kinds of work qualify.

**A review queue.** A batch of sign-offs the user asked for — review comments,
"proceed or stop" on a diff or a mock, a triage pass. The full form would cost
more in reading than the decisions are worth.

**Mechanical forks you hit while working.** Where does this file go? Keep or
exclude these twelve files? Which of the two names? These are small, reversible
and boring, but you cannot answer them for the user, and asking them one at a
time in chat is the worst possible shape: three round trips, three context
switches, and no record of what was chosen. Hold them and batch them. See
*Batching your own forks* below.

One question fills the screen. Beside it a column shows the whole queue and
what you have answered so far, so you can see the pattern in a file list
instead of judging each name blind. The user never touches the mouse and never
types, unless they choose a note or a free-text answer.

## Keys

```
  a   s   d   f   g   h   j   k   l   ;
  1   2   3       4           yes no skip note undo
                  ^ choice 4
```

| Key | On a Yes/No card | On a choice card |
|---|---|---|
| `j` | Yes / Proceed | nothing — the page says which keys to press |
| `f` | No / Stop | nothing — same |
| `a` `s` `d` `g` | — | the first, second, third and fourth choice |
| `k` | Skip; stays open in the log | same |
| `l` | Note on the answer just given. `Enter` keeps it, `Esc` drops it | same |
| `;` | Undo — clears the last answer and goes back to it | same |

Yes sits under the right index finger and No under the left, so the two real
answers are the two strongest fingers. Choices bind to the left hand and skip
`f` on purpose: `f` must mean No on every card, or a card that looks like the
last one will record the opposite of what the user meant. `k`, `l` and `;` mean
the same thing on every card too.

A choice card shows its keys next to the choices, and the legend at the foot of
the page always matches the card on screen. Press `j` on a choice card and it
tells you which keys that card takes, rather than recording anything.

A card can offer at most four entries, counting a free-text one. More than that
and the script refuses to render, because a card the user has to study is not a
fast card — split it.

After the last question comes a review screen: the counts, the elapsed time, and
every answer in a table. There `j` saves, `l` notes the last answer, and `;`
goes back. Nothing is written before the user presses `j` on that screen.

An unanswered question is written as **Skipped** and repeated under "Still
open". Fast mode never turns silence into a yes.

## Running it

```bash
python3 <skill-dir>/scripts/tracker.py /tmp/decisions.json --mode fast
```

Use `run_in_background: true` — the script blocks until the user saves. It
prints `URL:` immediately; give that to the user. Setting `"mode": "fast"` in
the spec has the same effect as the flag.

## Spec for fast mode

Same file as full mode, with a different set of fields.

```json
{
  "title": "Repo cleanup forks",
  "mode": "fast",
  "context": "Optional. One line, shown in the log rather than on each card.",
  "decisions": [
    {"id": "q1",
     "question": "Drop the in-memory cache before peak season?",
     "context": "It saves 40 ms p50 but has no eviction bound.",
     "impact": "Unbounded memory in the worst case."},

    {"id": "keep",
     "question": "Keep {item} in the repo?",
     "items": ["build.log", "notes.tmp", "src/main.py", ".env.local"]},

    {"id": "report-dir",
     "question": "Where must the coverage report go?",
     "impact": "Decides whether CI has to publish it.",
     "choices": ["docs/reports/", "~/reports/", "./ (here)"],
     "other": "somewhere else"},

    {"id": "q4",
     "question": "Is this layout the one to build?",
     "image": "/tmp/mock-v3.png"},

    {"id": "q5",
     "question": "Apply this migration in the same CR?",
     "text": "ALTER TABLE invoices ADD COLUMN settled_at timestamptz;"}
  ]
}
```

| Field | Effect |
|---|---|
| `question` | Required. The card. |
| `items` | Expands into one card per entry, with `{item}` substituted into `question`, `context`, `impact`, `text` and `image`. The entry also becomes the card's label in the side column. |
| `choices` | 2 to 4 named answers on `a`/`s`/`d`/`g` instead of Yes/No. A plain string is shorthand for `{"label": "..."}`; add `"value"` when the recorded text must differ from the label. |
| `other` | Adds a final entry on the next free key that opens a one-line input. Use it when your shortlist might be wrong. |
| `context` `impact` `cost` | One line each. Shown on the card. |
| `text` `image` | The artifact to look at — a diff, a log line, SQL, a mock. |
| `label` | Overrides the side-column text. `items` sets this for you. |

Ignored in fast mode: `options`, `pros`, `cons`, `recommendation`,
`reversibility`, `deadline`. If a card needs `options` and pros and cons, it is
not a fast-mode card.

### Writing fast-mode questions

**Phrase every Yes/No question so that Yes is the action.** "Drop the cache?" is
answerable. "Cache handling?" is not. "Do not drop the cache?" inverts the key
and will record the opposite of what the user meant.

**Use `choices` the moment Yes/No would distort the question.** "Save to
docs/reports/?" followed by "Save to ~/reports/?" is two screens for one
decision, and a No on the first tells you nothing about where it should go.

**Keep the question under about twelve words.** It has to be read in two
seconds. Put the rest in `context`, one line.

**Do not put a one-way door in fast mode.** Reversibility is what justifies a
single keystroke. An irreversible call belongs in the full form, where the cost
and the trade-offs are visible.

**Order the queue so related questions sit together,** and use `items` when the
question repeats. The user then holds one mental context and answers six cards
from it, and the side column lets them see the whole set at once.

**Show the artifact rather than describing it.** `image` for a mock or a chart,
`text` for a diff, a log line, a SQL statement, a config block. A question about
something the user cannot see is a question they cannot answer honestly.

## Batching your own forks

When you are working and hit a fork you cannot answer for the user, do not stop
and ask. Write it down and carry on with everything that does not depend on the
answer. When you are holding three or more, open one fast-mode page.

The reason is arithmetic. Three chat questions cost three round trips and pull
the user back into your task three times. One page costs one interruption and
three keystrokes, and it leaves a record of what was chosen — which matters more
than it sounds, because "why is `.env.local` gitignored" is exactly the question
that comes back a month later.

What counts as a fork worth holding:

- A destination — which directory, which file name, which branch.
- An include-or-exclude call over a set of files or records.
- A choice between two conventions, where either is defensible.
- Anything where you would otherwise guess and hope.

What does not: something the repo, the conventions or the user's earlier
instructions already answer. Look first. A page full of questions you could have
answered yourself is worse than no page, because it teaches the user that the
page wastes their time.

If you are holding one or two forks and the work is finished, just ask in chat —
opening a page for a single keystroke is not a saving. If a fork blocks
everything else, open the page at once rather than sitting on it.

Tell the user what you are doing when you hand over the URL: how many forks, and
that you held them so they only get interrupted once.

## Output

The log is a separate file from any full-mode log, in the same directory and
index: `<repo>/docs/decisions/YYYY-MM-DD-<slug>-fast.md` inside a git
repository, or `~/decisions/` otherwise.

```markdown
---
type: decision-log
mode: fast
date: 2026-09-21
decided_by: ellianco
title: "Repo cleanup forks"
questions: 7
yes: 2
no: 3
chosen: 1
skipped: 1
elapsed_seconds: 38
---

# Fast decisions — Repo cleanup forks

Recorded 2026-09-21 14:02 by ellianco. 7 questions in 38 s. 2 yes, 3 no, 1 chosen, 1 skipped.

| # | Question | Answer | Key | Note | Seconds |
| --- | --- | --- | --- | --- | --- |
| 1 | Keep build.log in the repo? | **Yes** | `j` |  | 3 |
| 2 | Keep notes.tmp in the repo? | **No** | `f` | generated file | 4 |
| 6 | Where must the coverage report go? | **build/reports/coverage/** | `g` | CI publishes from build/ | 14 |
| 7 | Rename the old test files? | **Skipped** | `k` |  | 0 |

## Still open

- 7. Rename the old test files?
```

Read the seconds column back. A question that took 30 seconds was not really a
fast-mode question, and the note the user added on it usually says why. That is
the signal to put the next one like it in the full form.
