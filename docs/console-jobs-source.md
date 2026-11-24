# The console's jobs source

The console's jobs pages read a program the console does not know: whatever runs your
scheduled jobs and keeps their run records. Anything that answers the paths in
[`jobs_source.openapi.json`](../packages/thalamus-console/src/thalamus_console/jobs_source.openapi.json)
can be a jobs source. That OpenAPI 3.1 document, shipped in the thalamus-console
package, is the one statement of every path, parameter, body, reply shape and
example; this page holds the rules the shapes cannot say.

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

- **The source writes the text and picks the status; the page prints it.** Every line,
  title and number a page shows arrives already composed. A status is a word and a tone,
  and the page prints the word in the tone's colour without deciding anything about it.
  A page shown a tone it does not know prints the word in the muted colour, so a newer
  source still says what it means.<!-- (A0267, cites-as-live) -->
- **Strings are text, never markup.** The pages build every element from data as text
  nodes; no source string is parsed as HTML.<!-- (A0267, cites-as-live) -->
- **A tone is a design decision.** The spec's tone list is closed and each run word has
  one tone. A new tone goes to the designer before it goes into the spec.
- **An error is one sentence** in `{"error": …}`; the page prints it.

## App widgets

An app widget is a small page a person or a job built. The source serves its files at
`apps/<app>/files/<path>` with the sandbox policy and CORS header the spec names, and
the console adds its own sandbox policy beside them, as on every reply.

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
