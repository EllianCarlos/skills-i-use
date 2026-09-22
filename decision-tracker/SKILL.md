---
name: decision-tracker
description: Builds a local HTML decision tracker that shows each open decision with its context, impact, cost and trade-offs, collects the user's answer plus an optional rationale, then writes a traceable markdown decision log. Use this whenever the user has more than one open decision, asks to track or log decisions, wants an ADR or a decision record, needs design trade-offs laid out side by side, or wants to approve or reject a queue of items fast with single keystrokes. Trigger it even when the user only says things like "I need to decide a few things", "ask me the open questions", "give me the options and let me pick", "let me sign off on these", or "just ask me yes or no". Also use it on your own initiative when you are mid-task and holding three or more mechanical forks you cannot answer for the user — where files go, keep or exclude which files, which of two conventions — instead of asking them one at a time in chat. Pass the argument `fast` for the keyboard-only mode.
---

# Decision Tracker

A decision costs the user two things: the time to understand the question, and
the risk of deciding badly. This skill attacks both. It puts every open
decision on one page, each with the small amount of context that actually
changes the answer, and it records what the user chose and why. The record is
the point — a decision nobody can trace later gets re-litigated.

Two modes. Pick the right one; the wrong one wastes the user's time.

| Mode | Use it when | The user answers with |
|---|---|---|
| `full` (default) | Competing designs, one-way doors, costs to weigh, anything a reader will question in six months | Radio buttons, free text, optional rationale |
| `fast` | Reversible calls with a small answer: sign-off queues, review comments, "proceed or stop" on an artifact, and the mechanical forks you hit while working | One keystroke: `j` yes, `f` no, `a`/`s`/`d`/`g` for named choices, `k` skip |

Enter `fast` mode when the user passes `fast` as an argument, or asks for a
quick pass, or says "just Y/N", "proceed or stop", or "approve these one by
one" — and also on your own initiative, for your own forks, as below. For fast
mode, read `references/fast-mode.md` — it holds the keys, the choice cards, the
item templates, the page behaviour and the output shape. Do not guess the key
bindings.

Mixed batch? Run `full` for the decisions that need weighing, then `fast` for
the rest. Each run writes its own log into the same directory and index. Do not
force a design trade-off into a Yes/No question — a forced binary is how bad
decisions get made quickly.

## Batching your own forks

Fast mode is not only for decisions the user brings you. Mid-task you hit small
forks you cannot answer for them: where a file goes, whether to keep or exclude
each of twelve files, which of two conventions to follow. Asking those one at a
time in chat is the worst shape available — three round trips, three context
switches, and no record.

So hold them. Carry on with everything that does not depend on the answer, and
when you are holding three or more, open one fast-mode page. One interruption,
three keystrokes, and the reasons end up in the log. Below three, or when a fork
blocks everything, just ask in chat — a page for one keystroke saves nothing.

Look before you ask. A fork the repo, the conventions, or the user's earlier
instructions already answer is not a fork; a page full of those teaches the user
that the page wastes their time. `references/fast-mode.md` has the detail on what
to hold and how to shape it.

## Workflow

1. **Collect the open decisions.** Take them from wherever they are: this
   conversation, a document or text the user pastes, a plan, a diff, a design
   review, a ticket queue, or a direct ask. If the user names a source, read it
   first.
2. **Write the spec** to `decisions.json` (schema below) in a temp directory.
   This is where the real work happens — see *Writing decision cards*.
3. **Start the tracker in the background.** The script blocks until the user
   submits, so a foreground call would hit the tool timeout:

   ```bash
   python3 <skill-dir>/scripts/tracker.py /tmp/decisions.json
   ```

   Run it with `run_in_background: true`. It prints the URL at once and tries to
   open a browser.
4. **Give the user the URL** and say how many decisions are waiting. Then stop
   talking. They are reading, not waiting on you.
5. **When the script exits** you are re-invoked with its output. It prints
   `SAVED: <path>`. Read the log, then report the decisions back in two or
   three lines, and name anything the user deferred — a deferred decision is
   still blocking work.
6. **Act on the decisions** if the user asked you to. The log is the record,
   not the goal.

Add `--mode fast` for fast mode. Add `--out-dir` only when the user names a
location.

## Writing decision cards

The quality of the page is the quality of these fields. A card that makes the
user open three other tabs has failed.

**One question per card, and close it.** "What do we do about auth?" is not a
decision, it is a topic. "Do we ship OAuth2 via the existing IdP, or static API
keys?" is a decision. If a card cannot be answered without a second question
hiding inside it, split the card.

**Context: at most three sentences, and only what changes the answer.** Not a
summary of the project. The test is subtractive — delete a sentence and ask
whether the user could still choose correctly. If yes, leave it deleted. If a
card needs a long context, the card is too big.

**Impact: say what differs between the options.** "This is important" tells the
user nothing. "Sets the integration effort for every partner, and decides
whether we own key rotation" tells them what they are buying.

**Cost: time, money, resources, in concrete units.** Dev-days, dollars per
month, people, new infrastructure. `"unknown — need the traffic numbers"` is a
good value. An invented number is not: the user will weigh it as if it were
real, and that is worse than no number at all. Never make one up.

**Pros and cons only for genuinely competing designs.** They earn their space
when two options both defensibly win. On an operational Yes/No they are noise —
that card belongs in fast mode.

**Give a recommendation when you have one.** A tracker that only asks is slower
than one that proposes. State the recommendation and one line of why. The user
can override with a click, and the override is the interesting signal.

**Mark reversibility.** It is the single field that most changes how much care a
decision deserves. Write `"reversible, config change"` or `"one-way door once a
partner integrates"`. The page highlights a one-way door in a warning colour.

**Never invent a fact to fill a field.** Leave the field out, or write what you
would need to know. The log is a record the user will rely on later.

## Spec schema

Only `title` and `decisions[].question` are required. Leave out what you do not
know.

```json
{
  "title": "Payments API auth rollout",
  "context": "Optional. One paragraph of context shared by every decision.",
  "mode": "full",
  "decisions": [
    {
      "id": "auth-method",
      "question": "Which auth method do we ship for the public payments API?",
      "context": "At most three sentences. Only what changes the answer.",
      "impact": "What differs downstream between the options.",
      "cost": {"time": "3 dev-days", "money": "$0 new spend", "resources": "1 SDE"},
      "reversibility": "one-way door once a partner integrates",
      "deadline": "2026-10-05",
      "options": [
        {"name": "OAuth2 via the existing IdP",
         "pros": ["No new secret store", "Partners know the flow"],
         "cons": ["The IdP team owns our latency budget"]},
        {"name": "Static API keys",
         "pros": ["Ships in a day"],
         "cons": ["We build rotation tooling", "No scoping"]}
      ],
      "recommendation": "OAuth2 via the existing IdP",
      "recommendation_why": "rotation tooling costs more than the IdP dependency",
      "text": "Optional. Shown in a code block — a diff, a log line, a config.",
      "image": "Optional. Path to a local image the user must look at."
    }
  ]
}
```

Notes on behaviour that matters when you write the spec:

- `options` renders radio buttons, plus "Something else" with a text box, plus
  "Defer — I need more information". Omit `options` and the user gets a free
  text field instead. Use free text for an open question such as a limit or a
  name, where a shortlist would be a guess.
- Nothing on the page is a required field. An unanswered decision is recorded
  as **deferred**, never as a silent yes. This is deliberate: a form that
  refuses to submit makes users invent answers.
- `cost` also accepts a plain string when the breakdown does not apply.
- Three more fields exist for fast mode: `choices` (2–4 named answers on
  `a`/`s`/`d`/`g`), `other` (a free-text answer on the next free key), and
  `items` (one card per entry, with `{item}` substituted into the question). Use
  `items` for a mechanical batch — it keeps the spec the size of the idea instead
  of thirty near-identical cards. `references/fast-mode.md` has the detail.

## Where the log lands

Inside a git repository: `<repo>/docs/decisions/`. Anywhere else:
`~/decisions/`. The script creates the directory, names the file
`YYYY-MM-DD-<slug>.md`, never overwrites an existing log, and appends one row
to `INDEX.md` in the same directory so the whole history stays skimmable.

The log carries YAML frontmatter (date, author, counts, mode) so it is
greppable, then one section per decision: the decision, the rationale, the
impact, the cost, and the context as it was presented, folded into a
`<details>` block. Deferred decisions are listed again under "Still open".

Tell the user the path when you report back. `--out-dir` overrides it.

## No browser available

On a remote host or in a headless session, write the page to a file instead:

```bash
python3 <skill-dir>/scripts/tracker.py /tmp/decisions.json --static /tmp/tracker.html
```

The user opens that file, answers, and the page downloads `answers.json`. Then
write the log from it:

```bash
python3 <skill-dir>/scripts/tracker.py /tmp/decisions.json --apply ~/Downloads/answers.json
```

The markdown is built by the same code in both paths, so the log is identical.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `TIMEOUT: nobody submitted the form` | The default wait is 30 minutes. Raise it with `--timeout 7200`, or use `--static`. |
| The browser did not open | The script always prints `URL:`. Pass that URL to the user. Use `--no-open` to stop trying. |
| Port in use | The script walks 8765–8785, then takes any free port. Pin one with `--port`. |
| The page says "Not saved" | The markdown write failed. The page shows the exception; fix the path or permissions and rerun with `--apply`. |
| An image does not load | `image` must be a path that exists on this host. The server reads it and serves it at `/artifact/<n>`. |
| `offers 5 choices` and exits | A fast card holds four entries at most, counting `other`. Split the card or drop a choice. |
