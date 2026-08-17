# The console against its spec

Where `src/thalamus/console/static/` departs from
[`lab/d4v2-handoff-spec.md`](../../lab/d4v2-handoff-spec.md), what each departure
costs the reader, and who each one belongs to.

The spec is the input and is not edited to match the code. Where the two disagree
about a fact of the running system, the server wins and the spec is wrong; where they
disagree about a design, the spec wins and the client is wrong. Both kinds are below,
separated, because they close differently.

Measurements are from this box and are dated where a later change could move them.

---

## 1. Open questions for the designer

Four things here are not the implementer's to close. Each changes what the surface
*means* rather than how it is drawn.

### 1.1 The identity palette does not identify

`hashHue` (`static/app.js:43-47`) maps a scope name into a six-entry `PALETTE`. The
roster has nine scopes. The result, computed against the names in `config/experts/`:

| scope | hue |
|---|---|
| architect | `#e07a9c` rose |
| designer | `#4db6a6` teal |
| literature | `#c79bf0` orchid |
| teacher | `#e0a45c` amber |
| **dl, eval-methodology, frontend, homelab, qe** | **`#8fce6b` moss** |
| — | `#6db3f2` sky, assigned to nothing |

Five of nine scopes are one colour and one palette entry is unreachable.
`lab/d4-roster-critique.md` recorded this at seven scopes; two more have been added
since.

Underneath that is a harder problem. The palette is close to isoluminant, so even
where two rows do get different hues, the difference is carried by hue alone:

- **2 of 21** hue pairs meet the 1.41:1 luminance separation `lab/d3-identity-spec.md`
  declares for itself. The closest pair, sky against orchid, is **1.001:1**.
- Every hue clears the 3:1 non-text floor against `--bg` comfortably (6.69 to 10.09),
  so this is not a contrast failure. It is a *separation* failure.
- Against status, `--pending` and moss are **1.014:1** apart — and moss is the hue
  worn by five of the nine scopes.

The identity bar is declared redundant reinforcement (§2), and the row's name is the
real carrier, so nothing is unreadable. But the channel is doing close to no work,
and the design's own stated separation floor is met by two pairs out of twenty-one.

**Why it is not closed at the keyboard:** widening the palette means choosing hues,
and §2 rules that assigning meaning to a channel is the designer's. The luminance
budget is the blocker — `lab/d3-identity-spec.md`'s declared floor fits six levels
against nine scopes — which is exactly the designer's open thread
`roster-identity-palette-luminance-infeasible`. Three ways out (relax the floor, drop
to six identities, move identity to a non-colour channel) all change what the surface
claims.

### 1.5 The corrected status ramp cannot be applied as written

`lab/d3-identity-spec.md:62-66` specifies a corrected status ramp — `danger #c55b50`,
`warn #c18c4e`, `ok #54c5b3` — spaced to 1.41:1 minimum pairwise luminance so the
severity order survives a greyscale render. The shipped tokens are `--danger:
#e0685c`, `--ok: #45c08d`, `--pending: #e8b44a`, and there is no `--warn` token.

`--danger` carries text: `.viewcap.bad`, `.admin-state.bad`, `.chip.loose`, the
`needs you` chip, and `.pol-expiry` at .62rem. Measured on this box, 2026-08-16:

| value | `--bg` | `--panel` | `--panel-hi` |
|---|---|---|---|
| shipped `#e0685c` | 5.68 | 5.19 | 4.75 |
| spec `#c55b50` | 4.49 | **4.11** | **3.76** |

The ramp regresses every ground, and two of the three below the 4.5:1 text floor the
same design commits to. Lifting the hue until it clears 4.5 everywhere gives
`#cc6e64` (5.39 / 4.93 / 4.51) — and that collapses the ramp's own separation:

| pair | at `#cc6e64` | ramp's floor |
|---|---|---|
| danger/warn | **1.192:1** | 1.41:1 |
| warn/ok | 1.405:1 | 1.41:1 |
| danger/ok | 1.674:1 | 1.41:1 |

So on this palette the 4.5:1 text floor and the 1.41:1 severity separation are
jointly infeasible across three levels, the same luminance-budget problem §1.1 hits
with nine identities. The spec resolved it silently in favour of separation.

**Why it is not closed at the keyboard:** picking a value that satisfies a stated
floor would be the implementer's, but no value satisfies both stated floors, and
choosing which one yields decides whether the ramp's meaning is carried by colour or
by something else. Two ways out — take `--danger` off text so the 3:1 non-text floor
applies and the spec value stands (`#327e62` is the existing precedent for a token
split this way), or relax the separation floor — and both change what the channel
claims.

Until it is settled the shipped tokens stay, because they are the ones that clear the
text floor. `tests/test_console_contrast.py` now holds `danger` to AA on all three
grounds, so applying the ramp fails the suite rather than the reader.

### 1.2 `/clear` puts two rows on screen for one session

`/clear` ends a session and starts another in the same tmux pane.
`harness/hooks/claude-code/session-start.sh:167` admits `source_kind == "clear"`
explicitly and writes a pin-ledger row for it, so the window's `session_id` changes
while the window itself continues. The pin ledger shows how ordinary this is: pane
`%0` has carried 8 session ids, `%37` five, `%38` four.

The distill join (`static/app.js:1368-1370`) matches a record's `session` against the
window's *current* `session_id[:8]`. The pre-`/clear` session's record therefore joins
nothing, falls to the record-only path (`app.js:1375`), and draws a second row —
grey-barred, not tappable, no controls — directly beside the live window it came from.

§4.4's premise is "a record outliving its **window**". It has no case for a record
outliving its **session id while the window is still alive**, so two rows is the spec
rendered faithfully and the roster still misreports how many sessions exist.

**Why it is not closed at the keyboard:** the available fix is to join on scope and
directory instead of on the id, which infers a continuity nothing recorded. That is
the move §3.3 and §3.4 forbid in the grouping keys — "a guessed hierarchy is worse
than none, because it looks identical to a real one" — and the failure direction rule
("under-group, never over-group") points the same way. The question underneath is what
a row *is*: a window, a session, or a session-in-a-window. §3.4's `no project
recorded` group is the precedent for answering it honestly rather than by inference.

### 1.3 What the workspace filter is allowed to scope

The rail filters through `visibleWindows()` (`app.js:138-140`), which narrows on the
selected workspace and room. `renderRoster` (`app.js:1037`) is handed every window.
Pick a project, return to the roster, and the filter is not there.

The spec cannot settle this: neither `workspace` nor `filter` occurs anywhere in its
943 lines. §2.1 decides only *which surface is resident when the console opens* — it
never contemplates a standing choice that scopes the list.

**Why it is not closed at the keyboard:** §2.1's argument for landing on the roster is
that `needs you` is on screen before the first touch, so the operator's first tap is
informed rather than exploratory. A filtered roster answers *what needs me in this
project*; an unfiltered one answers *what needs me*. Both are defensible and they are
different surfaces — a blocked session in another project is either on screen or it is
not. That is the design deciding what the landing view is for, not the implementer
deciding how to draw it.

The shipped split is not a third option, though. It is the rail and the roster
disagreeing about the same sessions, which is the defect the spec opens by naming:
three lists that disagree, replaced by one row per session. Whichever way this is
ruled, both surfaces take the same answer.

### 1.4 The permission-mode ladder does not match the modes that exist

§5.2 specifies a segmented picker over `manual｜acceptEdits｜auto`, where selecting a
segment presses `BTab` k times to walk there. Both halves are contradicted by the
data. Counted over every permission-mode record in `~/.claude/projects` on this box,
2026-08-16:

| value | records | on §5.2's ladder |
|---|---|---|
| `auto` | 3649 | yes |
| `default` | 2255 | **no** |
| `dontAsk` | 194 | **no** |
| `bypassPermissions` | 98 | excluded by decision-log |
| `acceptEdits` | 4 | yes |
| `plan` | 1 | **no** |
| `manual` | **0** | yes |

`manual` is not a value this system produces. A segment labelled `manual` could never
match a readback, so its confirmed outcome is unreachable and it would sit in
`could not confirm` forever. `default` is presumably the mode it means, but that
substitution is a claim about what the word denotes, not a rename.

The order is not recoverable either. Across the explicit change records `default` is
followed by both `auto` and `plan`, and `auto` by both `acceptEdits` and `default` —
because most records are launch-time sets rather than keypresses. So the cycle's
length and sequence are unknown, and k is not computable from anything we hold.

**Why it is not closed at the keyboard:** which modes are on the ladder decides what
the control can express, and one of them is `bypassPermissions`, which §5.2 excludes
by name — a cycle-only mechanism can still walk a session into it, and the readback
then reports it rather than preventing it. Picking the membership, and picking a word
for the mode the transcripts call `default`, are both claims about what the surface
means. The same question decides whether the session view's raw `mode` keycap should
survive alongside a mode control, or whether one affordance replaces the other.

---

## 2. Specified and never built

### 2.1 The poll still carries every screen

§1 specifies a per-window opaque change token, with the pane mirror moving to the
focused-window request: *"The poll carries no screens."* The token exists —
`/api/panes` serves `screen_rev` per window (`server.py:screen_rev`) and the client
compares it for equality and never parses it (`app.js:revOf`, read at `app.js:977`
and `app.js:988`, stored at `app.js:1066`). The split does not. The focused window's
mirror is still fed from the poll payload (`app.js:290`, `app.js:1054`), so `lines`
must keep carrying **every** window's text — including the windows nobody is looking
at — until an endpoint serves a single window's screen.

Measured on this box, 2026-08-16, three windows: `/api/panes` returns **25,019 bytes,
of which 23,058 is `lines`**, **uncompressed at every layer**, at a 1.2 s poll.
Dropping `lines` once nothing reads it leaves 2,061. At nine windows the payload is
one `capture-pane` subprocess per window per poll.

### 2.2 §5.2's segmented picker

The rest of §5 is built. The opened row draws the session's mode
(`app.js:modeControl`), fed by an on-demand `/api/read` fired when the row opens and
never by the poll, as §5.1 requires. The server serves both fields on every response
the endpoint can return (`server.PERMISSION_MODE_READ`), so all three of §5.2's
outcomes are drawn: `awaiting readback` outlined while a press is outstanding,
`could not confirm — mode unchanged on screen?` after five readbacks, and `cannot read
this session's mode (<reason>)` when the read status is not `ok`.

The **picker** is not built, and the reason is a measurement — see open question §1.4.
What ships is §5.2's own degraded branch, the single control that advances one step,
"which is exactly what the hardware does".

The `mode` keycap (`index.html:184`) still sends raw `shift-tab` in the session view.
It is left alone: that bar is a terminal keyboard, the key does what the key does, and
the readback loop has no meaning for a raw keystroke. Whether one mode affordance
should exist rather than two is part of §1.4.

**On-demand does not mean cheap, and the request is shaped for it.** `/api/read`
serves 60 transcript items on a cold open. The mode fetch passes a `since` past any
real `seq` so the envelope comes back without them: measured on this box,
2026-08-16, **34,229 bytes against 210** on the longest-running window. Reading one
standing string should not cost a transcript, which is the same argument §5.1 makes
against putting mode on the poll.

---

## 3. Drift from a decided spec

One item, and it is the spec's defect rather than the client's: §4.3's table gives one
sentence, `restart exceeded {n}s grace`, for a row covering **both** `recycling` and
`closing`. `app.js:1296-1300` emits it faithfully for both, so a close that overruns
its grace reports itself as a restart. The client is not free to invent the missing
sentence — what a terminal row says is the spec's to write.

---

## 4. Additions the spec does not cover

Not drift — the spec is silent, so these were the implementer's to decide, and they
are now the frontend scope's to keep or replace.

- **The `‹` back caret** (`index.html:36-37`, hidden in roster view at
  `style.css:947`). §2.1 settles that the roster is the landing view and that the
  mirror is one tap from a row; it names no return affordance.
- **Header control target sizes.** `.admin-btn` (`style.css:703-713`) sets no
  `min-height` or `min-width`, so the caret, `＋` and `⚙` sit near the 24 × 24 CSS px
  floor of WCAG 2.2 SC 2.5.8 — far under this design's own 60 px for anything
  consequential. SC 2.5.8's spacing exception applies and is not currently met either.
- **The `⋯` expander.** §6.1 requires some opened-row mechanism, so the control is
  warranted; its position is not specified. It sits outboard of the state slot, and
  the slot's lane is reserved on rows that carry no expander (`style.css`,
  `.srow-slot:last-child`) so the state column stays straight across a row that
  outlived its window. §3's "state slot (right)" is about the slot being the
  right-aligned element of line 1, which holds; putting a 44 px target inboard of it
  to make the slot the literal last child would be a worse row for a stricter reading.
- **`◈ room` on line 2.** The spec predates the room badge; §3's qualifier
  enumeration does not include it.

---

## 5. A contradiction inside the spec

§1's field table draws `detail` as "opened row only". §4.3's table makes it a property
of the band, carried verbatim by `state=error`. Both cannot hold. The client follows
§4.3 (`app.js:1632-1638`), rendering it on any terminal row.

---

## 6. What matches

Recorded so it is not re-audited: state precedence rank for rank including `dead`
above the liveness words, the clock taper (`M:SS` / `6h47m` / `6d 2h`), silent
success, the tri-state `observed`/`blocked`/`activity`, the monospace-versus-
proportional-italic split for non-observations, the truncation marker, the no-project
group and its second line, `revive` on a dead window, the anchor's absent close
control, `restart all` separated from `roster sync` by section and shape, the 60 px
row, the 44 px group header, the 4 px identity bar on a collapsed row and the 12 px
block on a terminal one, the 25 px control separation, and the 60 × 60 px destructive
controls — the per-session pair and the band's dismiss. §7 is complete — neither
`#admin-windows` nor `#distill-list` survives.

Every figure above was measured in a rendered browser against a console on a spare
port, the way `tests/js/contrast-dom.js` is driven. `tests/test_console_geometry.py`
is the CI half and reads declarations only — the weaker claim, and the one that would
have caught all four of the drifts that were found here, each of which was written
into the sheet rather than composited on the way to the screen.

Literal identity/status hue disjointness holds and is tested. §1.1 above is about
perceptual distance, which is a different measurement and is not asserted anywhere.
