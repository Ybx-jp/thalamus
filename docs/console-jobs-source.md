# The console's jobs source

The console's jobs pages read a program the console does not know: whatever runs your
scheduled jobs and keeps their run records. This page is the wire contract that
program serves. Anything that answers these paths can be a jobs source.

`thalamus console --jobs-source URL --jobs-token-file PATH` forwards
`/api/jobs/<path>` to `URL/v1/console/<path>` with `Authorization: Bearer <token>`
added by the console. Status codes and bodies pass through unchanged.

Every reply the console relays from a source carries the console's own
`Content-Security-Policy: sandbox allow-scripts` and `X-Content-Type-Options: nosniff`,
whatever the source sent. The console sends the source's own policy as well, on a
separate line. A browser enforces both, so a source can tighten the policy but never
loosen it. A page the source serves, even one opened in a tab of its own, runs in an
opaque origin and cannot use the console's API.<!-- (A0265, cites-as-live) -->

A source must answer each request directly and must not redirect. The console never
follows a redirect, so the token cannot travel to another host. It answers a redirect
with 502. It also answers 502 when a reply's body is shorter than its declared length
or larger than the console's cap, rather than passing on part of a
reply.<!-- (A0266, cites-as-live) -->

## Rules every answer follows

- JSON objects only. An error is `{"error": "<sentence>"}` with a 4xx or 5xx status;
  the page prints the sentence.
- **The source composes; the console prints.** Every status is
  `{"word": str, "tone": "ok" | "danger" | "pending" | "muted" | "accent"}`. The page
  shows the word in the tone's colour and never decides a status itself. An unknown
  tone renders as `muted`, so a newer source still shows its word.
- Lines (`line`, `sub`, `note`) are display text the source wrote for that place.
- Every string is rendered as text, never as markup.

In the examples, `weekly-digest` is a job with three stages (`gather`, `draft`,
`check`) whose stage prompts the source tunes and versions in git.

## Jobs

`GET jobs` — the list.

```json
{"summary": "4 jobs · 2 scopes",
 "banner": {"title": "tune changed weekly-digest:draft", "line": "43ade4c · 10 h ago · replay gate passed", "change": "43ade4c"},
 "groups": [{"name": "news", "note": "notifications muted to Dec 7",
             "jobs": [{"id": "weekly-digest", "name": "weekly-digest",
                       "line": "weekly Mon 20:00 · 3 stages · on 43ade4c · ran 10 h ago",
                       "status": {"word": "notable", "tone": "ok"}}]}]}
```

`banner` is null when nothing waits to be read. A group named `""` is shown as "no
scope yet".

`GET jobs/<job>[?run=<run id>]` — one job, its stages for a chosen run (default newest).

```json
{"id": "weekly-digest", "name": "weekly-digest", "scope": "news",
 "header": {"line": "news · weekly Mon 20:00 · next run in 9 h", "sub": "config 43ade4c · 3 prompts"},
 "runs": [{"id": "r1", "label": "Nov 23 00:51", "version": "b39469d", "status": {"word": "notable", "tone": "ok"}}],
 "run": {"id": "r1", "label": "Nov 23 00:51", "version": "b39469d", "status": {"word": "notable", "tone": "ok"}},
 "drift": {"title": "draft changed after this run", "line": "43ade4c · by tune", "change": "43ade4c"},
 "stages": [{"name": "draft", "status": {"word": "notable", "tone": "ok"}, "reached": true,
             "lines": ["no tools · 21 s · $0.27"], "mono": ["in  last week's items"], "out": "6 drafts",
             "changed": true, "progress": {"used": 45, "cap": 60, "segments": [{"n": 12, "label": "search"}, {"n": 33, "label": "fetch"}]}}],
 "actions": {"run_now": true, "replay": true},
 "auto_apply": true, "auto_apply_job": "weekly-digest:draft",
 "gate_rule": "gate: ≥3 pairs · kept not lower · no more failures · cost ≤ 2×",
 "pinned": {"title": "run Nov 23 00:51 is the replay fixture", "line": "its prompts and inputs are stored"},
 "replay_note": "Re-runs this run's stored input with today's prompts. A replay publishes nothing."}
```

`GET jobs/<job>/history[?replays=0|1]` — runs grouped under the commit they ran on.

```json
{"columns": ["gather", "draft", "check"], "more": false,
 "items": [{"type": "commit", "sha": "43ade4c", "subject": "Apply a replay-gated change", "line": "by tune · today 01:13 · HEAD", "head": true, "tag": "by tune", "change": "43ade4c"},
           {"type": "empty", "text": "no runs on this version yet · next Mon 20:00"},
           {"type": "replays", "title": "6 replays of 00:51", "line": "3 baseline · 3 candidate · 1 failed",
            "rows": ["baseline", "candidate"], "grid": [[{"word": "failed", "tone": "danger"}]], "note": "draft only"},
           {"type": "run", "id": "r1", "title": "Nov 23 00:51", "line": "notable · 5 kept · $1.04",
            "cells": [{"text": "$0.27", "tone": "ok"}], "span": null}]}
```

A run with one stage sends `span` (`{"text", "tone"}`) instead of `cells`.

`GET jobs/<job>/diff?from=<sha>&to=<sha>` — the change to this job's prompts and config
between two versions: `{"from", "to", "files": [File]}`, where a File is
`{"path", "added", "removed", "lines": [{"op": "+" | "-" | " ", "text"}]}`.

`GET changes/<sha>` — an applied change and the replay-gate receipt it passed.

```json
{"sha": "43ade4c", "job": "weekly-digest:draft", "title": "weekly-digest:draft prompt changed",
 "line": "applied by tune · today 01:13 · auto-apply is on",
 "gate": {"status": {"word": "replay gate · passed", "tone": "ok"}, "line": "3 paired replays of the Nov 23 00:51 run",
          "rows": [{"label": "findings kept", "before": "2", "after": "3"}],
          "checks": [{"label": "at least 3 pairs", "passed": true}],
          "note": "The gain rests on one baseline replay that failed."},
 "diff": [File], "auto_apply": true, "auto_apply_job": "weekly-digest:draft",
 "revert": {"available": true, "reason": null}}
```

`GET runs/<run id>[?findings=all]` — a run's telemetry and what it found.

```json
{"id": "r1", "title": "run Nov 23 00:51", "job": "weekly-digest", "status": {"word": "notable", "tone": "ok"},
 "line": "on b39469d · 3 stage configs stored · replayable",
 "tiles": [{"label": "cost", "value": "$1.04", "sub": "gather .27 · draft .46 · check .32"}],
 "findings": {"heading": "findings · 5 kept · 1 rejected", "more": 2,
              "items": [{"id": "f1", "title": "…", "kind": "vocabulary", "label": "useful" | "not_useful" | "wrong" | null},
                        {"id": "f2", "title": "…", "rejected": {"word": "rejected · numbers not in the input", "line": "…"}}]},
 "events": 162}
```

`GET runs/<run id>/events[?after=<seq>]` — the run's raw stream, 200 at a time:
`{"events": [{"seq", "type", "subtype", "text"}], "more": bool}`.

`GET repo[?jobs_only=0|1]` — the repository the jobs run from.

```json
{"name": "jobs-repo", "status": {"word": "clean", "tone": "muted"}, "line": "main · no remote · last commit 10 h ago",
 "summary": "11 · 1 by tune", "jobs": 4,
 "commits": [{"sha": "43ade4c", "subject": "…", "line": "01:13 · prompts · no runs yet", "tag": "by tune", "change": "43ade4c"}]}
```

`GET commits/<sha>` — one commit: `{"sha", "subject", "body", "line", "tag", "change",
"runs": [{"id", "label", "status"}], "files": [File]}`.

`GET graph` — the desktop canvas.

```json
{"columns": ["sources", "collectors", "tables", "derived", "model jobs", "outputs", "phone"],
 "nodes": [{"id": "n1", "col": 4, "row": 3, "title": "weekly-digest", "line": "Mon 20:00 · 3 stages", "scope": "news",
            "status": {"word": "notable", "tone": "ok"}, "planned": false, "job": "weekly-digest",
            "stages": [{"name": "draft", "text": "$0.27"}]}],
 "edges": [["n0", "n1"]],
 "note": [{"col": 2, "row": 4, "text": "feeds the poll its list"}],
 "lane": {"repo": "jobs-repo main", "commits": [{"sha": "43ade4c", "time": "01:13", "tag": "by tune"}],
          "jobs": [{"name": "weekly-digest", "marks": [{"sha": "43ade4c", "text": "next", "tone": "accent"}]}]}}
```

## Writes

Each is a POST with a JSON body, forwarded only after the console's Origin check.

| Path | Body | Does |
|---|---|---|
| `findings/<id>/label` | `{"label": "useful" \| "not_useful" \| "wrong"}` | records the operator's label |
| `jobs/<job>/run` | `{}` | starts a live run, which goes through the job's own preflight |
| `runs/<run id>/replay` | `{"on": "HEAD"}` | re-runs a stored run's input on HEAD |
| `jobs/<key>/auto-apply` | `{"on": bool}` | turns auto-apply of gated changes on or off for a job |
| `changes/<sha>/revert` | `{}` | pauses auto-apply for the job, then reverts the change as a new commit |

A write answers `{"ok": true, …}` or an error.

## The board

`GET board` answers `{"widgets": [Widget], "version": sha | null}`. `POST board`
with `{"widgets": [Widget], "base": sha | null}` saves a layout and answers
`{"ok": true, "version": sha}`. It answers 409 when `base` is no longer the saved
version, so two editors cannot overwrite each other unseen.

A Widget is `{"id", "kind", "title", "binding": {…}, "show_when", "x", "y", "w", "h"}`.
`kind` is one of `number`, `series`, `table`, `tail`, `inbox`, `control`, `note`
or `app`. The binding is structured: a source table, a value, filters and windows,
each picked from `GET board/sources`. A source never runs SQL text a client sent.
`POST board/eval` with `{"widget": Widget, "range"?, "scope"?}` answers what that
widget shows, already composed; `"shown": false` hides it. For example, a number answers
`{"value": "7 of 16", "compare": "previous 6 weeks: 10 of 64", "foot": "games_weekly"}`.

## App widgets

An app widget is a small page a person or a job built. The source serves its files at
`apps/<app>/files/<path>` with this policy and CORS header on every response:

    Content-Security-Policy: sandbox allow-scripts; default-src 'none'; script-src 'self' 'wasm-unsafe-eval' blob:; worker-src blob:; connect-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'
    Access-Control-Allow-Origin: *

The board embeds it as `<iframe sandbox="allow-scripts">`, with no `allow-same-origin`
ever. The page therefore has an opaque origin. It cannot read the console's DOM, its
storage or its API responses, and any POST it sends carries `Origin: null` and is
refused. The CORS header lets the opaque page fetch its own static files, for example
an engine's WebAssembly. Nothing else in the tree carries that header.

The page gets data and writes rows only through the board, by `postMessage`:

| From | Message | Meaning |
|---|---|---|
| app | `{"thalamus": "app/ready"}` | loaded; send me my data |
| board | `{"thalamus": "app/data", "data": …, "error"?}` | the answer of `GET apps/<app>/data` |
| app | `{"thalamus": "app/write", "id", "row": {…}}` | store this row |
| board | `{"thalamus": "app/written", "id", "ok", "error"?, "data"?}` | the answer of `POST apps/<app>/write`, whose body is the row itself |
| app | `{"thalamus": "app/open"}` / `{"thalamus": "app/close"}` | open the app full screen / close it |

The board accepts a message only when `event.source` is one of its own app frames, and
it routes the message by that frame, never by an id in the body. A write is capped at
4 KB and one per second per app. `GET apps/<app>/data` returns only the fields the
app's grant names, and `POST apps/<app>/write` checks the row against the grant's
schema. Whatever an app is not granted never reaches its frame.
