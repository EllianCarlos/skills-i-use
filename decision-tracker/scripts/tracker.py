#!/usr/bin/env python3
"""Render a decision tracker page, collect the answers, write a markdown log.

The page is plain HTML. The full form needs no JavaScript at all: it is a
<form method="post">. Fast mode uses a small keydown handler, because
keyboard-only answering is the whole point of that mode.

Usage
  tracker.py decisions.json                     serve the full form, then write the log
  tracker.py decisions.json --mode fast         serve fast mode (j/f/k/l/; keys)
  tracker.py decisions.json --static page.html  write the page only (no server)
  tracker.py decisions.json --apply answers.json   write the log from saved answers

On success the script prints `SAVED: <path>` and exits 0.
"""

from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# ---------------------------------------------------------------- paths


def repo_root(start: Path) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    top = out.stdout.strip()
    return Path(top) if top else None


def resolve_out_dir(explicit: str | None) -> Path:
    """Repo `docs/decisions/` when inside a git repo, else `~/decisions/`."""
    if explicit:
        return Path(explicit).expanduser()
    root = repo_root(Path.cwd())
    if root is not None:
        return root / "docs" / "decisions"
    return Path.home() / "decisions"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug or "decisions")[:60]


def unique_path(directory: Path, stem: str) -> Path:
    candidate = directory / f"{stem}.md"
    n = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{n}.md"
        n += 1
    return candidate


# ---------------------------------------------------------------- spec


CHOICE_KEYS = ["a", "s", "d", "g"]  # `f` stays No on every card, so it is skipped


def expand_items(d: dict, at: int) -> list[dict]:
    """One card per entry in `items`, with {item} filled in.

    A mechanical batch ("keep or exclude each of these 30 files") is one
    question asked many times. Writing 30 near-identical cards by hand is
    wasted effort and drifts; this keeps the spec the size of the idea.
    """
    items = d.get("items")
    if not items:
        return [d]
    cards = []
    fields = ("question", "context", "impact", "text", "image")
    for n, item in enumerate(items):
        card = {k: v for k, v in d.items() if k != "items"}
        for f in fields:
            if isinstance(card.get(f), str):
                card[f] = card[f].replace("{item}", str(item))
        card["id"] = f"{d.get('id', f'd{at + 1}')}-{n + 1}"
        card["label"] = str(item)
        cards.append(card)
    return cards


def load_spec(path: Path) -> dict:
    spec = json.loads(path.read_text(encoding="utf-8"))
    raw = spec.get("decisions") or []
    if not raw:
        sys.exit(f"{path}: no decisions found (expected a non-empty 'decisions' list)")

    decisions: list[dict] = []
    for i, d in enumerate(raw):
        if not d.get("question"):
            sys.exit(f"{path}: decision {i + 1} has no 'question'")
        decisions.extend(expand_items(d, i))

    for i, d in enumerate(decisions):
        d.setdefault("id", f"d{i + 1}")
        choices = d.get("choices") or []
        if choices:
            # normalise "a string" into {"label": "a string"}
            d["choices"] = [
                {"label": c} if isinstance(c, str) else c for c in choices
            ]
            room = len(d["choices"]) + (1 if d.get("other") else 0)
            if room > len(CHOICE_KEYS):
                sys.exit(
                    f"{path}: decision '{d['id']}' offers {room} choices. "
                    f"A one-keystroke card holds at most {len(CHOICE_KEYS)} "
                    f"(keys {'/'.join(CHOICE_KEYS)}). Split the card, or drop a "
                    f"choice — a card the user has to study is not a fast card."
                )
            # in full mode the same content belongs in `options`
            if not d.get("options"):
                d["options"] = [{"name": c["label"]} for c in d["choices"]]
    spec["decisions"] = decisions
    spec.setdefault("title", "Decisions")
    return spec


def cost_line(cost) -> str:
    if not cost:
        return ""
    if isinstance(cost, str):
        return cost
    parts = [f"{k} {v}" for k, v in cost.items() if v]
    return " · ".join(parts)


def artifact_paths(spec: dict) -> list[Path]:
    """Absolute paths of every image referenced by the spec, in order."""
    found: list[Path] = []
    for d in spec["decisions"]:
        img = d.get("image")
        if img:
            found.append(Path(img).expanduser().resolve())
    return found


# ---------------------------------------------------------------- styling

CSS = """
:root {
  --bg: #fbfaf8; --panel: #fff; --ink: #1c1b19; --muted: #6b6760;
  --rule: #e3dfd8; --accent: #2f5d50; --warn: #8a4b2a;
  --mono: ui-monospace, SFMono-Regular, Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #16171a; --panel: #1d1f23; --ink: #e9e7e3; --muted: #9a958c;
          --rule: #2e3237; --accent: #7fc0aa; --warn: #d79b6e; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.55
  -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
main { max-width: 52rem; margin: 0 auto; padding: 3rem 1.5rem 6rem; }
h1 { font-size: 1.6rem; letter-spacing: -.01em; margin: 0 0 .3rem; }
.sub { color: var(--muted); font-size: .9rem; margin: 0 0 2rem; }
.shared { border-left: 2px solid var(--accent); padding: .1rem 0 .1rem 1rem;
  color: var(--muted); margin: 0 0 2.5rem; }
.card { background: var(--panel); border: 1px solid var(--rule);
  border-radius: 6px; padding: 1.5rem; margin: 0 0 1.5rem; }
.card > header { display: flex; gap: .75rem; align-items: baseline; }
.num { font: 600 .8rem/1.6 var(--mono); color: var(--accent);
  border: 1px solid var(--rule); border-radius: 4px; padding: 0 .45rem; }
.card h2 { font-size: 1.12rem; margin: 0; line-height: 1.35; }
.ctx { color: var(--muted); margin: .9rem 0 0; }
dl.meta { display: grid; gap: .1rem .2rem; margin: 1.1rem 0 0;
  border-top: 1px solid var(--rule); padding-top: .8rem; }
dl.meta > div { display: grid; grid-template-columns: 8.5rem 1fr; gap: .5rem; }
dl.meta dt { font: .78rem/1.7 var(--mono); color: var(--muted);
  text-transform: uppercase; letter-spacing: .04em; }
dl.meta dd { margin: 0; font-size: .95rem; }
dd.oneway { color: var(--warn); font-weight: 600; }
table.opts { width: 100%; border-collapse: collapse; margin: 1.2rem 0 0;
  font-size: .92rem; }
table.opts th, table.opts td { text-align: left; vertical-align: top;
  padding: .5rem .6rem; border-bottom: 1px solid var(--rule); }
table.opts th { font: .78rem/1.7 var(--mono); color: var(--muted);
  text-transform: uppercase; letter-spacing: .04em; }
table.opts ul { margin: 0; padding-left: 1.1rem; }
.rec { margin: 1.1rem 0 0; font-size: .95rem; }
.rec b { color: var(--accent); }
fieldset { border: 0; border-top: 1px solid var(--rule); margin: 1.3rem 0 0;
  padding: 1.1rem 0 0; }
legend { font: .78rem/1.7 var(--mono); color: var(--muted);
  text-transform: uppercase; letter-spacing: .04em; padding: 0; }
label.opt { display: flex; gap: .6rem; align-items: center; padding: .35rem 0;
  cursor: pointer; }
label.opt input { accent-color: var(--accent); }
input[type=text], textarea { width: 100%; background: var(--bg);
  color: var(--ink); border: 1px solid var(--rule); border-radius: 4px;
  padding: .5rem .6rem; font: inherit; font-size: .95rem; }
textarea { resize: vertical; }
label.field { display: block; margin: 1rem 0 0; font-size: .9rem; }
label.field span { color: var(--muted); }
label.field textarea, label.field input { margin-top: .35rem; }
.actions { position: sticky; bottom: 0; background: var(--bg);
  border-top: 1px solid var(--rule); padding: 1.1rem 0; margin-top: 2rem; }
button { background: var(--accent); color: var(--bg); border: 0;
  border-radius: 5px; padding: .7rem 1.4rem; font: 600 .98rem/1 inherit;
  cursor: pointer; }
.hint { color: var(--muted); font-size: .85rem; margin: .7rem 0 0; }
code { font: .9em var(--mono); }
pre { background: var(--bg); border: 1px solid var(--rule); border-radius: 4px;
  padding: .8rem; overflow-x: auto; font: .85rem/1.5 var(--mono); }
img.artifact { max-width: 100%; border: 1px solid var(--rule);
  border-radius: 4px; margin: 1.1rem 0 0; }
kbd { font: .85em var(--mono); border: 1px solid var(--rule);
  border-bottom-width: 2px; border-radius: 4px; padding: .1rem .4rem;
  background: var(--panel); }
/* fast mode */
.fast { display: flex; flex-direction: column; min-height: 100vh;
  max-width: 62rem; margin: 0 auto; padding: 2rem 1.5rem; }
.split { display: grid; grid-template-columns: 1fr 15rem; gap: 2.5rem;
  flex: 1; align-items: start; }
@media (max-width: 52rem) {
  .split { grid-template-columns: 1fr; gap: 1.5rem; }
  .queue { order: -1; border-left: 0; padding-left: 0;
    border-top: 1px solid var(--rule); padding-top: .9rem;
    max-height: 9rem; overflow-y: auto; }
}
.stage h2 { font-size: 1.7rem; line-height: 1.25; margin: 0 0 1rem;
  letter-spacing: -.01em; }
.queue { border-left: 1px solid var(--rule); padding-left: 1.1rem;
  font-size: .85rem; position: sticky; top: 2rem; }
.queue h3 { font: .78rem/1.7 var(--mono); color: var(--muted);
  text-transform: uppercase; letter-spacing: .04em; margin: 0 0 .5rem; }
.queue ol { list-style: none; margin: 0; padding: 0; }
.queue li { display: grid; grid-template-columns: 1rem 1fr; gap: .45rem;
  padding: .2rem 0; color: var(--muted); align-items: baseline; }
.queue li.now { color: var(--ink); font-weight: 600; }
.queue li .mark { font: .8rem/1.5 var(--mono); text-align: center; }
.queue li.yes .mark, .queue li.choice .mark { color: var(--accent); }
.queue li.no .mark { color: var(--warn); }
.queue li .lbl { overflow-wrap: anywhere; }
.queue li .val { display: block; font: .75rem var(--mono);
  color: var(--accent); }
.choices { margin: 1.4rem 0 0; }
.choice-row { display: grid; grid-template-columns: 2.2rem 1fr; gap: .7rem;
  align-items: baseline; padding: .5rem 0; border-top: 1px solid var(--rule); }
.legend { border-top: 1px solid var(--rule); padding-top: 1rem;
  color: var(--muted); font-size: .88rem; display: flex; gap: 1.4rem;
  flex-wrap: wrap; margin-top: 2rem; }
.counter { font: .8rem var(--mono); color: var(--muted); margin-bottom: 1.4rem; }
.hintbar { color: var(--warn); font-size: .85rem; min-height: 1.3rem;
  margin: .6rem 0 0; }
#entry { display: none; margin: 1.2rem 0 0; }
#entry.on { display: block; }
table.summary { width: 100%; border-collapse: collapse; font-size: .93rem; }
table.summary th, table.summary td { text-align: left; padding: .45rem .6rem;
  border-bottom: 1px solid var(--rule); }
table.summary th { font: .78rem/1.7 var(--mono); color: var(--muted);
  text-transform: uppercase; }
td.a-yes { color: var(--accent); font-weight: 600; }
td.a-no { color: var(--warn); font-weight: 600; }
td.a-skip { color: var(--muted); }
"""


def page(title: str, body: str, script: str = "") -> str:
    tag = f"<script>\n{script}\n</script>" if script else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
{body}
{tag}
</body>
</html>
"""


# ---------------------------------------------------------------- full form


def render_full(spec: dict, action: str, static: bool) -> str:
    esc = html.escape
    out: list[str] = ["<main>", f"<form method='post' action='{action}' id='f'>"]
    out.append(f"<h1>{esc(spec['title'])}</h1>")
    out.append(
        "<p class='sub'>Answer what you can. Anything you leave empty is "
        "recorded as deferred, never as a silent yes.</p>"
    )
    if spec.get("context"):
        out.append(f"<div class='shared'>{esc(spec['context'])}</div>")

    img_index = 0
    for i, d in enumerate(spec["decisions"]):
        out.append(f"<section class='card' id='{esc(d['id'])}'>")
        out.append(
            f"<header><span class='num'>{i + 1}</span>"
            f"<h2>{esc(d['question'])}</h2></header>"
        )
        if d.get("context"):
            out.append(f"<p class='ctx'>{esc(d['context'])}</p>")

        rows = []
        if d.get("impact"):
            rows.append(("Impact", esc(d["impact"]), ""))
        cost = cost_line(d.get("cost"))
        if cost:
            rows.append(("Cost", esc(cost), ""))
        rev = (d.get("reversibility") or "").strip()
        if rev:
            cls = "oneway" if re.search(r"one.?way|irreversible", rev, re.I) else ""
            rows.append(("Reversibility", esc(rev), cls))
        if d.get("deadline"):
            rows.append(("Decide by", esc(str(d["deadline"])), ""))
        if rows:
            out.append("<dl class='meta'>")
            for label, value, cls in rows:
                attr = f" class='{cls}'" if cls else ""
                out.append(f"<div><dt>{label}</dt><dd{attr}>{value}</dd></div>")
            out.append("</dl>")

        options = d.get("options") or []
        if any(o.get("pros") or o.get("cons") for o in options):
            out.append(
                "<table class='opts'><tr><th>Option</th><th>Pros</th>"
                "<th>Cons</th></tr>"
            )
            for o in options:
                pros = "".join(f"<li>{esc(p)}</li>" for p in o.get("pros") or [])
                cons = "".join(f"<li>{esc(c)}</li>" for c in o.get("cons") or [])
                out.append(
                    f"<tr><td><b>{esc(o.get('name', '?'))}</b></td>"
                    f"<td><ul>{pros}</ul></td><td><ul>{cons}</ul></td></tr>"
                )
            out.append("</table>")

        if d.get("text"):
            out.append(f"<pre>{esc(d['text'])}</pre>")
        if d.get("image"):
            src = f"/artifact/{img_index}" if not static else esc(d["image"])
            img_index += 1
            out.append(f"<img class='artifact' src='{src}' alt='artifact'>")

        if d.get("recommendation"):
            out.append(
                f"<p class='rec'>Recommendation: <b>{esc(d['recommendation'])}</b>"
                + (f" — {esc(d['recommendation_why'])}" if d.get("recommendation_why") else "")
                + "</p>"
            )

        out.append("<fieldset><legend>Your decision</legend>")
        if options:
            for j, o in enumerate(options):
                name = esc(o.get("name", f"option {j + 1}"))
                out.append(
                    f"<label class='opt'><input type='radio' name='c{i}' "
                    f"value='{name}'> {name}</label>"
                )
            out.append(
                f"<label class='opt'><input type='radio' name='c{i}' "
                f"value='__other__'> Something else:</label>"
                f"<input type='text' name='o{i}' placeholder='your own answer'>"
            )
            out.append(
                f"<label class='opt'><input type='radio' name='c{i}' "
                f"value='__defer__'> Defer — I need more information</label>"
            )
        else:
            out.append(
                f"<input type='text' name='o{i}' placeholder='your decision'>"
            )
            out.append(
                f"<label class='opt'><input type='checkbox' name='c{i}' "
                f"value='__defer__'> Defer — I need more information</label>"
            )
        out.append("</fieldset>")
        out.append(
            f"<label class='field'>Rationale <span>(optional — write it if a "
            f"reader six months from now would ask &ldquo;why?&rdquo;)</span>"
            f"<textarea name='r{i}' rows='2'></textarea></label>"
        )
        out.append("</section>")

    out.append("<div class='actions'>")
    out.append(
        "<button type='submit'>Save all decisions</button>"
        if not static
        else "<button type='submit'>Download answers.json</button>"
    )
    out.append(
        "<p class='hint'>The log is written as markdown. The page tells you "
        "the exact path.</p></div>"
    )
    out.append("</form></main>")

    script = ""
    if static:
        script = STATIC_JS
    return page(spec["title"], "\n".join(out), script)


STATIC_JS = """
document.getElementById('f').addEventListener('submit', function (e) {
  e.preventDefault();
  var fd = new FormData(e.target), n = 0;
  while (fd.has('c' + n) || fd.has('o' + n) || fd.has('r' + n)) n++;
  var answers = [];
  for (var i = 0; i < n; i++) {
    answers.push({ index: i, choice: fd.get('c' + i) || '',
                   other: fd.get('o' + i) || '', rationale: fd.get('r' + i) || '' });
  }
  var blob = new Blob([JSON.stringify({ mode: 'full', answers: answers }, null, 2)],
                      { type: 'application/json' });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'answers.json'; a.click();
});
"""


# ---------------------------------------------------------------- fast mode


def short_label(d: dict) -> str:
    """The text for the side queue. Short enough to scan in a column."""
    if d.get("label"):
        return str(d["label"])
    q = d["question"].rstrip("?")
    return q if len(q) <= 38 else q[:36].rstrip() + "…"


def render_fast(spec: dict, action: str, static: bool) -> str:
    items = []
    img_index = 0
    for d in spec["decisions"]:
        item = {
            "id": d["id"],
            "q": d["question"],
            "label": short_label(d),
            "context": d.get("context", ""),
            "impact": d.get("impact", ""),
            "cost": cost_line(d.get("cost")),
            "text": d.get("text", ""),
            "img": "",
            "choices": [
                {"label": c["label"], "value": c.get("value", c["label"])}
                for c in (d.get("choices") or [])
            ],
            "other": d.get("other", ""),
        }
        if d.get("image"):
            item["img"] = d["image"] if static else f"/artifact/{img_index}"
            img_index += 1
        items.append(item)

    data = json.dumps(items).replace("</", "<\\/")
    body = f"""<div class='fast'>
<div class='counter' id='counter'></div>
<div class='split'>
  <div class='stage' id='stage'></div>
  <aside class='queue'><h3 id='queueHead'>Queue</h3><ol id='queue'></ol></aside>
</div>
<form method='post' action='{action}' id='f'>
  <input type='hidden' name='payload' id='payload'>
</form>
<div class='legend' id='legend'></div>
</div>"""
    script = (
        "var ITEMS = " + data + ";\n"
        "var STATIC = " + ("true" if static else "false") + ";\n"
        "var CHOICE_KEYS = " + json.dumps(CHOICE_KEYS) + ";\n" + FAST_JS
    )
    return page(spec["title"] + " — fast mode", body, script)


FAST_JS = r"""
var at = 0, answers = [], started = Date.now(), last = Date.now();
var entryMode = null, entryTarget = null;   // 'note' | 'other'
var stage = document.getElementById('stage');
var queue = document.getElementById('queue');
var queueHead = document.getElementById('queueHead');
var counter = document.getElementById('counter');
var legend = document.getElementById('legend');

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Every answerable key on the current card, in screen order. Binary cards get
// j and f; a choice card binds its choices to the left hand instead, so that j
// and f never mean anything except yes and no.
function keysFor(it) {
  var out = [];
  if (it.choices && it.choices.length) {
    for (var i = 0; i < it.choices.length; i++) {
      out.push({ key: CHOICE_KEYS[i], label: it.choices[i].label,
                 value: it.choices[i].value, kind: 'choice' });
    }
    if (it.other) {
      out.push({ key: CHOICE_KEYS[it.choices.length], label: it.other,
                 value: '', kind: 'other' });
    }
  } else {
    out.push({ key: 'j', label: 'yes / proceed', value: '', kind: 'yes' });
    out.push({ key: 'f', label: 'no / stop', value: '', kind: 'no' });
  }
  return out;
}

function mark(a) {
  if (!a) return '·';
  if (a.answer === 'yes') return '✓';
  if (a.answer === 'no') return '✗';
  if (a.answer === 'choice') return a.key;
  return '–';
}

function drawQueue() {
  var h = '';
  for (var i = 0; i < ITEMS.length; i++) {
    var a = answers[i], cls = a ? a.answer : '';
    if (i === at) cls += ' now';
    var val = a && a.answer === 'choice'
      ? "<span class='val'>" + esc(a.value) + "</span>" : '';
    h += "<li class='" + cls + "'><span class='mark'>" + mark(a) +
         "</span><span class='lbl'>" + esc(ITEMS[i].label) + val + "</span></li>";
  }
  queue.innerHTML = h;
  var done = 0;
  for (var j = 0; j < ITEMS.length; j++) if (answers[j]) done++;
  queueHead.textContent = done + ' of ' + ITEMS.length + ' answered';
}

function drawLegend(it) {
  var parts = [];
  if (it) {
    var ks = keysFor(it);
    for (var i = 0; i < ks.length; i++) {
      parts.push("<span><kbd>" + ks[i].key + "</kbd> " + esc(ks[i].label) + "</span>");
    }
    parts.push("<span><kbd>k</kbd> skip</span>");
  } else {
    parts.push("<span><kbd>j</kbd> save</span>");
  }
  parts.push("<span><kbd>l</kbd> note</span>");
  parts.push("<span><kbd>;</kbd> undo</span>");
  legend.innerHTML = parts.join('');
}

function entryBox() {
  return "<div id='entry'><label class='field'><span id='entryLabel'></span>" +
         "<input type='text' id='entryInput'></label></div>" +
         "<p class='hintbar' id='hint'></p>";
}

function drawItem() {
  var it = ITEMS[at];
  var h = "<h2>" + esc(it.q) + "</h2>";
  if (it.context) h += "<p class='ctx'>" + esc(it.context) + "</p>";
  var meta = '';
  if (it.impact) meta += "<div><dt>Impact</dt><dd>" + esc(it.impact) + "</dd></div>";
  if (it.cost) meta += "<div><dt>Cost</dt><dd>" + esc(it.cost) + "</dd></div>";
  if (meta) h += "<dl class='meta'>" + meta + "</dl>";
  if (it.text) h += "<pre>" + esc(it.text) + "</pre>";
  if (it.img) h += "<img class='artifact' src='" + it.img + "' alt='artifact'>";
  if (it.choices && it.choices.length) {
    var ks = keysFor(it), rows = '';
    for (var i = 0; i < ks.length; i++) {
      rows += "<div class='choice-row'><kbd>" + ks[i].key + "</kbd><div>" +
              esc(ks[i].label) + "</div></div>";
    }
    h += "<div class='choices'>" + rows + "</div>";
  }
  h += entryBox();
  stage.innerHTML = h;
  counter.textContent = (at + 1) + ' of ' + ITEMS.length;
  drawQueue();
  drawLegend(it);
  last = Date.now();
}

function drawSummary() {
  var rows = '', yes = 0, no = 0, chosen = 0, skip = 0;
  for (var i = 0; i < ITEMS.length; i++) {
    var a = answers[i] || { answer: 'skip', note: '', seconds: 0 };
    if (a.answer === 'yes') yes++;
    else if (a.answer === 'no') no++;
    else if (a.answer === 'choice') chosen++;
    else skip++;
    var label = a.answer === 'yes' ? 'Yes' : a.answer === 'no' ? 'No'
              : a.answer === 'choice' ? esc(a.value) : 'Skipped';
    rows += "<tr><td>" + (i + 1) + "</td><td>" + esc(ITEMS[i].q) +
            "</td><td class='a-" + a.answer + "'>" + label + "</td><td>" +
            esc(a.note || '') + "</td></tr>";
  }
  counter.textContent = 'review';
  var secs = Math.round((Date.now() - started) / 1000);
  var head = [yes + ' yes', no + ' no'];
  if (chosen) head.push(chosen + ' chosen');
  head.push(skip + ' skipped');
  stage.innerHTML = "<h2>" + head.join(' · ') + ", in " + secs + " s</h2>" +
    "<table class='summary'><tr><th>#</th><th>Question</th><th>Answer</th>" +
    "<th>Note</th></tr>" + rows + "</table>" + entryBox() +
    "<p class='hint'>Press <kbd>j</kbd> to save, <kbd>l</kbd> to note the " +
    "last answer, <kbd>;</kbd> to go back to the last question.</p>";
  drawQueue();
  drawLegend(null);
}

function record(kind, value, key) {
  answers[at] = { id: ITEMS[at].id, index: at, answer: kind, value: value || '',
                  key: key || '', note: '',
                  seconds: Math.round((Date.now() - last) / 1000) };
  at++;
  if (at >= ITEMS.length) drawSummary(); else drawItem();
}

function undo() {
  if (at > ITEMS.length - 1) at = ITEMS.length - 1;
  else if (at > 0) at--;
  else return;
  answers[at] = null;
  drawItem();
}

function hint(msg) {
  var h = document.getElementById('hint');
  if (h) h.textContent = msg;
}

function openEntry(mode, label, value, target) {
  var box = document.getElementById('entry');
  if (!box) {
    if (at >= ITEMS.length) drawSummary(); else drawItem();
    box = document.getElementById('entry');
    if (!box) return;
  }
  entryMode = mode;
  entryTarget = target;
  box.className = 'on';
  document.getElementById('entryLabel').textContent = label;
  var input = document.getElementById('entryInput');
  input.value = value || '';
  input.focus();
}

function openNote() {
  var idx = at > 0 ? at - 1 : 0;
  if (!answers[idx]) return;
  openEntry('note', 'Note on your last answer (Enter to keep, Esc to drop) ',
            answers[idx].note, idx);
}

function closeEntry(keep) {
  var input = document.getElementById('entryInput');
  var typed = input ? input.value.trim() : '';
  var mode = entryMode, target = entryTarget;
  entryMode = null;
  entryTarget = null;
  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  if (mode === 'note') {
    if (keep) answers[target].note = typed;
    if (at >= ITEMS.length) drawSummary();
    else { var box = document.getElementById('entry'); if (box) box.className = ''; }
    return;
  }
  if (mode === 'other') {
    if (keep && typed) { record('choice', typed, target); return; }
    var b = document.getElementById('entry');
    if (b) b.className = '';
    if (keep && !typed) hint('Nothing typed, so nothing was recorded.');
  }
}

function save() {
  for (var i = 0; i < ITEMS.length; i++) {
    if (!answers[i]) {
      answers[i] = { id: ITEMS[i].id, index: i, answer: 'skip', value: '',
                     key: '', note: '', seconds: 0 };
    }
  }
  var payload = { mode: 'fast', elapsed: Math.round((Date.now() - started) / 1000),
                  answers: answers };
  if (STATIC) {
    var blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = 'answers.json'; a.click();
    return;
  }
  document.getElementById('payload').value = JSON.stringify(payload);
  document.getElementById('f').submit();
}

document.addEventListener('keydown', function (e) {
  if (entryMode) {
    if (e.key === 'Enter') { e.preventDefault(); closeEntry(true); }
    else if (e.key === 'Escape') { e.preventDefault(); closeEntry(false); }
    return;
  }
  var done = at >= ITEMS.length;
  if (e.key === 'l') { e.preventDefault(); openNote(); return; }
  if (e.key === ';') { e.preventDefault(); undo(); return; }
  if (done) {
    if (e.key === 'j') { e.preventDefault(); save(); }
    return;
  }
  if (e.key === 'k') { e.preventDefault(); record('skip', '', 'k'); return; }

  var it = ITEMS[at], ks = keysFor(it), hit = null;
  for (var i = 0; i < ks.length; i++) if (ks[i].key === e.key) hit = ks[i];
  if (!hit) {
    if (e.key === 'j' || e.key === 'f') {
      e.preventDefault();
      var names = [];
      for (var n = 0; n < ks.length; n++) names.push(ks[n].key);
      hint('This card is a choice, not a yes/no. Press ' + names.join(', ') + '.');
    }
    return;
  }
  e.preventDefault();
  if (hit.kind === 'other') {
    openEntry('other', hit.label + ' — type it, Enter to record, Esc to drop ',
              '', hit.key);
  } else if (hit.kind === 'choice') {
    record('choice', hit.value || hit.label, hit.key);
  } else {
    record(hit.kind, '', hit.key);
  }
});

drawItem();
"""


# ---------------------------------------------------------------- answers


def answers_from_form(spec: dict, fields: dict[str, list[str]]) -> dict:
    """Turn the urlencoded full-form POST into the canonical answers shape."""
    if "payload" in fields:
        return json.loads(fields["payload"][0])
    answers = []
    for i, _ in enumerate(spec["decisions"]):
        answers.append(
            {
                "index": i,
                "choice": (fields.get(f"c{i}") or [""])[0],
                "other": (fields.get(f"o{i}") or [""])[0],
                "rationale": (fields.get(f"r{i}") or [""])[0],
            }
        )
    return {"mode": "full", "answers": answers}


def settle_full(spec: dict, answers: list[dict]) -> list[dict]:
    """Resolve each raw answer into {decision, rationale, deferred}."""
    settled = []
    by_index = {a.get("index", n): a for n, a in enumerate(answers)}
    for i, d in enumerate(spec["decisions"]):
        a = by_index.get(i, {})
        choice = (a.get("choice") or "").strip()
        other = (a.get("other") or "").strip()
        rationale = (a.get("rationale") or "").strip()
        if choice == "__defer__":
            decision, deferred = "", True
        elif choice == "__other__":
            decision, deferred = other, not other
        elif choice:
            decision, deferred = choice, False
        elif other:
            decision, deferred = other, False
        else:
            decision, deferred = "", True
        settled.append(
            {"d": d, "decision": decision, "rationale": rationale, "deferred": deferred}
        )
    return settled


# ---------------------------------------------------------------- markdown


def fm_quote(value: str) -> str:
    return '"' + str(value).replace('"', '\\"') + '"'


def md_full(spec: dict, settled: list[dict], meta: dict) -> str:
    taken = [s for s in settled if not s["deferred"]]
    deferred = [s for s in settled if s["deferred"]]
    L: list[str] = []
    L.append("---")
    L.append("type: decision-log")
    L.append(f"mode: full")
    L.append(f"date: {meta['date']}")
    L.append(f"decided_by: {meta['author']}")
    L.append(f"title: {fm_quote(spec['title'])}")
    L.append(f"decisions: {len(settled)}")
    L.append(f"taken: {len(taken)}")
    L.append(f"deferred: {len(deferred)}")
    if meta.get("source"):
        L.append(f"source: {meta['source']}")
    L.append("---")
    L.append("")
    L.append(f"# {spec['title']}")
    L.append("")
    L.append(
        f"Recorded {meta['stamp']} by {meta['author']}. "
        f"{len(taken)} decided, {len(deferred)} deferred."
    )
    L.append("")
    if spec.get("context"):
        L.append(f"> {spec['context']}")
        L.append("")

    for i, s in enumerate(settled):
        d = s["d"]
        L.append(f"## {i + 1}. {d['question']}")
        L.append("")
        if s["deferred"]:
            L.append("- **Decision:** _deferred — not taken in this session_")
            if s["rationale"]:
                # the user may have written "blocked on ..." themselves; do not
                # emit "Blocked on: Blocked on ..."
                why = re.sub(r"(?i)^blocked on[:\s]+", "", s["rationale"]).strip()
                L.append(f"- **Blocked on:** {why or s['rationale']}")
        else:
            L.append(f"- **Decision:** **{s['decision']}**")
            if s["rationale"]:
                L.append(f"- **Rationale:** {s['rationale']}")
        if d.get("impact"):
            L.append(f"- **Impact:** {d['impact']}")
        cost = cost_line(d.get("cost"))
        if cost:
            L.append(f"- **Cost:** {cost}")
        if d.get("reversibility"):
            L.append(f"- **Reversibility:** {d['reversibility']}")
        if d.get("deadline"):
            L.append(f"- **Decide by:** {d['deadline']}")
        L.append("")

        trace: list[str] = []
        if d.get("context"):
            trace.append(d["context"])
            trace.append("")
        options = d.get("options") or []
        if options:
            trace.append("| Option | Pros | Cons |")
            trace.append("| --- | --- | --- |")
            for o in options:
                pros = "<br>".join(o.get("pros") or []) or "—"
                cons = "<br>".join(o.get("cons") or []) or "—"
                trace.append(f"| {o.get('name', '?')} | {pros} | {cons} |")
            trace.append("")
        if d.get("recommendation"):
            why = f" — {d['recommendation_why']}" if d.get("recommendation_why") else ""
            trace.append(f"Recommendation at the time: **{d['recommendation']}**{why}")
            trace.append("")
        if d.get("image"):
            trace.append(f"Artifact: `{d['image']}`")
            trace.append("")
        if trace:
            L.append("<details><summary>Context as presented</summary>")
            L.append("")
            L.extend(trace)
            L.append("</details>")
            L.append("")

    if deferred:
        L.append("## Still open")
        L.append("")
        for s in deferred:
            L.append(f"- {s['d']['question']}")
        L.append("")
    return "\n".join(L)


def fast_counts(spec: dict, payload: dict) -> dict:
    answers = payload.get("answers") or []
    by_index = {a.get("index", n): a for n, a in enumerate(answers)}
    counts = {"yes": 0, "no": 0, "choice": 0, "skip": 0}
    for i in range(len(spec["decisions"])):
        ans = by_index.get(i, {}).get("answer", "skip")
        counts[ans] = counts.get(ans, 0) + 1
    return counts


def fast_summary(counts: dict, elapsed) -> str:
    parts = [f"{counts['yes']} yes", f"{counts['no']} no"]
    if counts.get("choice"):
        parts.append(f"{counts['choice']} chosen")
    parts.append(f"{counts['skip']} skipped")
    return ", ".join(parts) + f" in {elapsed} s"


def md_fast(spec: dict, payload: dict, meta: dict) -> str:
    answers = payload.get("answers") or []
    by_index = {a.get("index", n): a for n, a in enumerate(answers)}
    counts = fast_counts(spec, payload)
    rows = []
    for i, d in enumerate(spec["decisions"]):
        a = by_index.get(i, {"answer": "skip", "note": "", "seconds": 0})
        ans = a.get("answer", "skip")
        if ans == "choice":
            label = a.get("value") or "?"
        else:
            label = {"yes": "Yes", "no": "No", "skip": "Skipped"}.get(ans, ans)
        key = a.get("key") or {"yes": "j", "no": "f", "skip": "k"}.get(ans, "")
        rows.append(
            (i + 1, d["question"], label, key, a.get("note", ""), a.get("seconds", 0), ans)
        )

    elapsed = payload.get("elapsed", 0)
    L: list[str] = []
    L.append("---")
    L.append("type: decision-log")
    L.append("mode: fast")
    L.append(f"date: {meta['date']}")
    L.append(f"decided_by: {meta['author']}")
    L.append(f"title: {fm_quote(spec['title'])}")
    L.append(f"questions: {len(rows)}")
    L.append(f"yes: {counts['yes']}")
    L.append(f"no: {counts['no']}")
    L.append(f"chosen: {counts['choice']}")
    L.append(f"skipped: {counts['skip']}")
    L.append(f"elapsed_seconds: {elapsed}")
    if meta.get("source"):
        L.append(f"source: {meta['source']}")
    L.append("---")
    L.append("")
    L.append(f"# Fast decisions — {spec['title']}")
    L.append("")
    L.append(
        f"Recorded {meta['stamp']} by {meta['author']}. "
        f"{len(rows)} questions in {elapsed} s. "
        f"{fast_summary(counts, elapsed).rsplit(' in ', 1)[0]}."
    )
    L.append("")
    if spec.get("context"):
        L.append(f"> {spec['context']}")
        L.append("")
    L.append("| # | Question | Answer | Key | Note | Seconds |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for n, q, label, key, note, secs, _ans in rows:
        L.append(f"| {n} | {q} | **{label}** | `{key}` | {note or ''} | {secs} |")
    L.append("")
    skipped = [r for r in rows if r[6] == "skip"]
    if skipped:
        L.append("## Still open")
        L.append("")
        for n, q, *_ in skipped:
            L.append(f"- {n}. {q}")
        L.append("")
    return "\n".join(L)


INDEX_HEADER = [
    "# Decision log index",
    "",
    "| Date | Log | Mode | Summary |",
    "| --- | --- | --- | --- |",
    "",
]


def append_index(out_dir: Path, log: Path, meta: dict, mode: str, summary: str) -> Path:
    index = out_dir / "INDEX.md"
    if not index.exists():
        index.write_text("\n".join(INDEX_HEADER), encoding="utf-8")
    line = f"| {meta['date']} | [{log.stem}]({log.name}) | {mode} | {summary} |\n"
    with index.open("a", encoding="utf-8") as fh:
        fh.write(line)
    return index


def write_log(spec: dict, payload: dict, out_dir: Path, author: str) -> Path:
    now = datetime.now()
    meta = {
        "date": now.strftime("%Y-%m-%d"),
        "stamp": now.strftime("%Y-%m-%d %H:%M"),
        "author": author,
        "source": str(Path.cwd()),
    }
    mode = payload.get("mode", "full")
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{meta['date']}-{slugify(spec['title'])}" + ("-fast" if mode == "fast" else "")
    log = unique_path(out_dir, stem)

    if mode == "fast":
        text = md_fast(spec, payload, meta)
        summary = fast_summary(fast_counts(spec, payload), payload.get("elapsed", 0))
    else:
        settled = settle_full(spec, payload.get("answers") or [])
        text = md_full(spec, settled, meta)
        taken = sum(1 for s in settled if not s["deferred"])
        summary = f"{taken} decided, {len(settled) - taken} deferred"

    log.write_text(text, encoding="utf-8")
    append_index(out_dir, log, meta, mode, summary)
    return log


# ---------------------------------------------------------------- server


class State:
    def __init__(self) -> None:
        self.saved: Path | None = None
        self.error: str | None = None
        self.done = threading.Event()


def make_handler(spec, mode, artifacts, out_dir, author, state):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):  # keep the console clean
            pass

        def _send(self, body: bytes, ctype="text/html; charset=utf-8", code=200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urllib.parse.urlparse(self.path).path
            if path in ("/", "/index.html"):
                render = render_fast if mode == "fast" else render_full
                self._send(render(spec, "/save", False).encode("utf-8"))
                return
            m = re.fullmatch(r"/artifact/(\d+)", path)
            if m:
                idx = int(m.group(1))
                if 0 <= idx < len(artifacts) and artifacts[idx].is_file():
                    ctype = mimetypes.guess_type(artifacts[idx].name)[0] or "application/octet-stream"
                    self._send(artifacts[idx].read_bytes(), ctype)
                    return
            self._send(b"not found", "text/plain; charset=utf-8", 404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("utf-8")
            try:
                fields = urllib.parse.parse_qs(raw, keep_blank_values=True)
                payload = answers_from_form(spec, fields)
                payload.setdefault("mode", mode)
                log = write_log(spec, payload, out_dir, author)
            except Exception as exc:  # report back in the browser, not just the shell
                state.error = f"{type(exc).__name__}: {exc}"
                body = page(
                    "Not saved",
                    f"<main><h1>Not saved</h1><pre>{html.escape(state.error)}</pre>"
                    "<p class='hint'>Nothing was written. Tell Claude what this "
                    "says.</p></main>",
                ).encode("utf-8")
                self._send(body, code=500)
                state.done.set()
                return
            state.saved = log
            body = page(
                "Saved",
                f"<main><h1>Saved</h1><p class='sub'>Your decisions are recorded "
                f"here:</p><pre>{html.escape(str(log))}</pre>"
                f"<p class='hint'>You can close this tab.</p></main>",
            ).encode("utf-8")
            self._send(body)
            state.done.set()

    return Handler


def pick_port(preferred: int | None) -> int:
    candidates = [preferred] if preferred else list(range(8765, 8786))
    for port in candidates:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------- main


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("spec", help="decisions JSON file")
    p.add_argument("--mode", choices=["full", "fast"], default="full")
    p.add_argument("--out-dir", default=None, help="where the markdown log goes")
    p.add_argument("--static", metavar="HTML", help="write the page only, no server")
    p.add_argument("--apply", metavar="JSON", help="write the log from saved answers")
    p.add_argument("--author", default=os.environ.get("USER") or "unknown")
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--timeout", type=int, default=1800, help="seconds to wait (0 = forever)")
    p.add_argument("--no-open", action="store_true")
    args = p.parse_args()

    spec = load_spec(Path(args.spec).expanduser())
    mode = spec.get("mode", args.mode) if args.mode == "full" else args.mode
    out_dir = resolve_out_dir(args.out_dir)

    if args.apply:
        payload = json.loads(Path(args.apply).expanduser().read_text(encoding="utf-8"))
        payload.setdefault("mode", mode)
        log = write_log(spec, payload, out_dir, args.author)
        print(f"SAVED: {log}")
        return 0

    if args.static:
        render = render_fast if mode == "fast" else render_full
        target = Path(args.static).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(spec, "#", True), encoding="utf-8")
        print(f"PAGE: {target}")
        print("Open it, answer, then download answers.json and run:")
        print(f"  python3 {Path(__file__).resolve()} {args.spec} --apply answers.json")
        return 0

    state = State()
    artifacts = artifact_paths(spec)
    port = pick_port(args.port)
    handler = make_handler(spec, mode, artifacts, out_dir, args.author, state)
    server = HTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"URL: {url}")
    print(f"MODE: {mode}")
    print(f"OUT_DIR: {out_dir}", flush=True)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    deadline = time.time() + args.timeout if args.timeout else None
    while not state.done.is_set():
        if deadline and time.time() > deadline:
            server.shutdown()
            print("TIMEOUT: nobody submitted the form", file=sys.stderr)
            return 2
        state.done.wait(0.5)
    time.sleep(0.3)  # let the browser finish reading the reply
    server.shutdown()

    if state.error:
        print(f"ERROR: {state.error}", file=sys.stderr)
        return 1
    print(f"SAVED: {state.saved}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
