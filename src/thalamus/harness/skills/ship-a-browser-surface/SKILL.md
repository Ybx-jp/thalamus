---
name: ship-a-browser-surface
description: How to take a change to one of this repo's browser surfaces — the console PWA, the graph viewer, pulse — from edit to believed-working, and how to verify an accessibility claim by measuring the rendered DOM rather than reading the stylesheet. Use BEFORE editing anything under src/thalamus/console/static/, src/thalamus/viewer/ or frontend/, BEFORE claiming a colour or target size conforms, when a change is correct on disk and wrong on the phone, and when adding a renderer that draws a session row.
---

# Ship a Browser Surface

Three surfaces, three build disciplines, one verification ladder. The failure this
skill exists to prevent is the one where the change is right and every check passes
and the operator's phone still shows something else.

## The three surfaces are not alike

| surface | source | build | tests |
|---|---|---|---|
| console PWA | `src/thalamus/console/static/` | **none** — files served as written | `tests/js/*.test.mjs` under node, driven by `tests/test_console_js.py` |
| graph viewer | `frontend/` (React 19, Vite, TS) | `npm run build` → `src/thalamus/viewer/static/` | `npm test` (vitest) |
| pulse | `src/thalamus/pulse/static/index.html` | none — one file | none |

The console is dependency-free on purpose: one of the server's jobs is restarting
the systemd unit that hosts it, so the fewer moving parts between a tap and a tmux
call the better. Do not add a bundler, a framework, or a package to it. The viewer
is the opposite and already carries its toolchain — use it there.

**The viewer's build output is committed.** A source change in `frontend/` that is
not rebuilt ships nothing; the served bundle is whatever was last written into
`src/thalamus/viewer/static/assets/`.

## The ladder — run in this order

The first three are seconds and catch most of it.

1. **`cd tests/js && node <each>.test.mjs`** — the whole JS suite, about a second,
   no Python. This is the inner loop.
2. **`uv run pytest tests/test_console_js.py -q`** — adds the two Python-side
   guards: one fails if a rename silently empties the JS suite, the other pins the
   JS status vocabulary to `dispatch.DELIVERABLE_STATUSES + (WAITING_STATUS,)` so a
   status added in Python cannot quietly widen the guard's blind spot.
3. **`uv run pytest -q`** — full suite.
4. **`uv run thalamus contract check`** — only if a live write path changed. A pure
   client change does not need it.
5. **`curl -s "$CONSOLE/api/panes" | python3 -m json.tool | head -40`** against
   the **live roster**, where `CONSOLE` is the console's bind address —
   `127.0.0.1:8378` unless you changed it. The tests use fixtures; every
   field-shape surprise in this client was found this way and not by a test.
6. **The deploy check, then the phone.** See below.

## Server truth before client theory

**When the phone disagrees with the server, get server truth first, every time.**

```sh
CONSOLE=127.0.0.1:8378                                    # the documented default bind
curl -s "$CONSOLE/api/panes" | head -c 400                # 1. the server
curl -s https://<host>/console/api/panes | head -c 400    # 2. the proxy
# 3. only now, the phone
```

Three commands, ten seconds. This has settled every disagreement of this kind so
far, and skipping it has cost whole sessions.

### The deploy check, which outranks every hazard below

The deployed console serves from whichever checkout its service was started in, which
is not necessarily the one you edited — a worktree, a second clone, or a merge that
never reached that checkout's disk is invisible to git, to the tests, and to the PR,
and the phone serves a stale tree while every check you ran was green.

Run all four from the checkout the service is running out of:

```sh
git rev-parse --short HEAD
git branch --show-current
md5sum src/thalamus/console/static/app.js
curl -s "$CONSOLE/app.js" | md5sum
```

The two md5s disagreeing is the whole diagnosis. Static files are read per-request,
so a **pure client change usually needs no restart** — but the checkout being on the
right commit is always required.

## Accessibility is measured on the rendered DOM, never reasoned from declared values

A declared hex is not what the reader sees. Anything that composites — `opacity`, a
translucent background, `backdrop-filter` — changes the effective colour, and a token
that passes as declared can fail as painted.

- **A token is conformant only on the grounds it is declared for.** The unit of
  conformance is the (foreground, ground) **pair**, not the colour. Assert every pair
  the stylesheet can produce, and assert separately that it produces no undeclared
  one — a declaration that outlives its subject reads as coverage while measuring
  nothing.
- **A channel that composites may never be the sole carrier of meaning.** If colour
  carries a distinction, a second non-colour channel must carry it too — the word,
  the weight, the geometry, the height. Check by reading the surface in greyscale and
  asking what is lost.
- **Hue alone is not separation.** Two colours can pass a contrast check against
  their ground, sit far apart in hue, and still be one colour to a reader at dot
  size or in greyscale. Where a ramp's steps must be told apart, find the separation
  above the text floor or in a channel that is not colour at all.
- **Perceptual distance is the right unit for "are these two marks distinguishable",
  and literal hex disjointness is not.** Two registries can be provably disjoint by
  value and still be indistinguishable on screen.
- **The relative-luminance threshold constant is 0.04045**, and an instrument still
  using 0.03928 is not producing wrong verdicts. WCAG 2.2 carries both: the value was
  0.03928 before May 2021, taken from an older sRGB version, and the specification
  states the update "has no practical effect on the calculations in the context of
  these guidelines". So a repo whose two instruments disagree here has a consistency
  problem and not a correctness one — pin one constant so two tools cannot report
  different numbers for the same pair, and do not treat a measurement as suspect
  merely for having used the older one.
- Contrast floors: **4.5:1** for normal text, **3:1** at ≥24 px or ≥18.66 px bold,
  **3:1** for non-text where colour is the signal. Where a colour only *reinforces* a
  signal carried elsewhere, assert a **ceiling** instead, so it cannot quietly become
  the carrier.
- **Target size: 24 × 24 CSS px** is the normative floor (WCAG 2.2 SC 2.5.8, AA).
  Undersized targets are allowed when a 24 px diameter circle centred on each does
  not intersect another target's circle — so **spacing can substitute for size**, and
  that is often the cheaper fix in a dense row. Where two targets overlap, the
  overlapping area is excluded from the measurement unless both perform the same
  action. A design spec asking for more than 24 px is asking for more than
  conformance; **picking a value that satisfies a stated floor is closed at the
  keyboard**, so satisfy the higher of the two and do not send it back.

`tests/js/contrast-dom.js` measures composited pairs. It handles `opacity` and
background alpha; it does not model `backdrop-filter`, so a rule using one is outside
what it can see and needs measuring another way.

**There is a standing `OPACITIES` registry test that fails on any undeclared
`opacity < 1`.** It exists because composited text failed contrast. The sanctioned
replacements for a "receded" signal are italic, indentation, and a stated
non-composited colour.

## The one-owner guard, and how to not fight it blind

**The server reduces, the client renders.** A client that reads a field the server
has already reduced for policy is a second policy about one fact, and two policies
drift. The guard lives in `tests/js/dialogue.test.mjs` and is bound to **shape, not
spelling** — a word list was tried and fails in both directions.

Inside the dialogue and every row renderer, these fail (comments are exempt):

- comparing against a status literal (`=== "busy"`), `switch`/`case` on one,
  `.includes()` / `.test()` against a status regex;
- an object literal **keyed** by a status literal — a lookup table is an opinion with
  the `if` factored out. The ternary `cond ? "idle" : "busy"` stays legal, because it
  branches on `cond`;
- `\bpanes?\b` or `send-keys` — **a local variable named `pane` in a row renderer
  fails the build**;
- on row renderers, `.status` in any form.

**The legal way to render liveness**: print the server's composed display word
verbatim, branch on `observed` and `blocked`, and read the *stamps* to decide whether
to draw a clock. Branching on `blocked` is not a violation — `blocked` **is** the
reduction, and branching on it is how it gets rendered.

### Two extraction traps

- **`extractFunction` matches `function NAME(` at line start only.** Converting a
  renderer to `const sessionRow = (r) => …`, or nesting it, breaks extraction. It
  throws loudly — but it looks like a broken test rather than a broken refactor.
- **The guarded-renderer list is written by hand, and nothing detects it going
  short.** A renderer you add is unguarded until you add it to that list, and every
  check still passes while covering nothing. **Updating the list is part of adding a
  renderer, not a follow-up to it.**

Extracted functions are evaluated with `new Function`, so they may only close over
injected globals. A renderer that starts reading a module-scope `let` fails at eval
with a confusing "not defined".

## Traps that make a correct change look broken

- **A stale service-worker shell.** The shell is network-first, so online is always
  fresh and the SW hides nothing while the network is up. The failure is the
  opposite: a phone that briefly cannot reach the box falls back to a cached shell
  and looks fine while being arbitrarily old. The discriminator is a **full close
  from the recents switcher and reopen** — not a pull-to-refresh. The cache version
  needs bumping only to purge a renamed or removed file.
- **WebAPK scope is baked at install time**, and Android installs match on **path
  prefix, ignoring the port**. Changing the mount path or the manifest scope orphans
  every already-installed icon and there is no migration — the operator must
  uninstall and reinstall. **Treat the mount path as immutable.** `chrome://webapks`
  on the phone is the only ground truth for what is installed.
- **Every URL the client requests must stay relative**, and the trailing-slash
  canonicalization in the console's `index.html` must run before any resource loads,
  because the tailnet proxy strips the mount path. That inline script is load-bearing
  and has no test.
- **The poll is single-flight, and a hung request wedges it.** `fetch` has no default
  timeout; a request stalled by a radio handoff neither resolves nor rejects, and the
  latch clears only on completion. Every fetch goes through the wrapper with an
  `AbortController` timeout, plus a backstop that force-releases the latch. It
  presents as "the session paused" with **no error anywhere**, and the connection
  indicator keeps saying "live" for several seconds after the last good poll.
  **A signal is single-use: once aborted, every later fetch given the same signal
  rejects immediately.** Construct a fresh controller per request — hoisting one to
  module scope to "avoid the allocation" wedges the client permanently after the
  first timeout. `abort()` rejects the fetch promise with `AbortError`; if the request
  had already fulfilled, reading the body rejects instead. `AbortSignal.timeout()`
  is the built-in for the timeout case and rejects with `TimeoutError`, which is
  distinguishable from a user abort — worth preferring when the two need telling
  apart.
- **Do not remove the hidden-element check in the selection guard.** Repaints are
  deferred while a text selection is live so the 1.2 s repaint cannot wipe it; when a
  view is hidden with a selection still anchored inside, the browser does not
  reliably collapse it, so without that check the guard answers "yes" forever and the
  pane freezes permanently.
- **Audit bare `.catch(() => {})`.** One swallowed a real exception and made a blank
  view look like a server problem; the diagnosis cost a session and came from `curl`.
- **The read view is opt-in and stored per device.** A device that never tapped the
  toggle shows the raw pane mirror. This gets reported as "the change didn't take"
  and is not a bug.
- **A restart button can unpin a session.** `tmux new-window -e VAR=x` sets only the
  initial process env and is not stored in the session environment, so the
  `respawn-window` behind a restart re-executes the argv without it. Claude survives
  because its pin rides the argv; a harness whose pin does not comes back silently
  unpinned.

## Changes that need the server, and the order

The client is a consumer; essentially nothing goes client-first.

- **A new field on the poll, or a new endpoint**: server lands it and it is confirmed
  on live `/api/panes` *before* the render is written. An unread field is inert;
  the reverse order gives the client `undefined`, which on this codebase usually
  renders nothing rather than throwing. There is no router — a new path is one `if`.
- **Anything that would make the client decide a policy fact** belongs on the server
  as a reduction. Ask for the reduction. **If handed a field that cannot be rendered
  without branching on its value, that is a bad reduction — push back.**
- **Genuinely two-sided**: the key-repeat clamp (one constant on each side, one
  meaning), the status vocabulary (pinned by a test precisely to force one change),
  and anything touching the mount path, the manifest scope, or a `localStorage` key —
  where the operator's installed app and stored toggles are a third party neither
  side can migrate.

## When the spec is silent

Where the specification does not cover the case, **the choice is yours: decide it at
the keyboard, record what you decided and why beside the code, and build.** Silence
is not a question to send back, and the round trip is the failure this scope exists
to prevent. The designer reviews the built surface afterward and files drift as a
finding.

Four classes go back to the designer instead of being closed here:

1. a choice that changes **which question the surface answers** — a precedence chain
   among states, where any total order compiles and the order *is* the design;
2. a choice that **assigns meaning to a channel** — whether a hue carries identity or
   status;
3. **the word itself**, where a term is a claim about the world rather than a label;
4. a silence that is **structural rather than omitted** — the spec does not cover the
   case because the design has not decided it.

Everything else is closed here, **including picking a value that satisfies a stated
floor**. A cost read on a comp — what a surface costs to build and which constraint
drives the cost — goes to the designer as advice that does not gate, and never
carries a substitute design.

**Record the closure where the reader will be standing.** A gap closed in a comment
beside the code it governs is a gap the next implementer finds; one closed in a
session summary is one they close again, differently.
