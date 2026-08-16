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

Two things here are not the implementer's to close. Both change what a row *means*
rather than how it is drawn.

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

Separately and **already decided**: `lab/d3-identity-spec.md:62-66` specifies a
corrected status ramp — `danger #c55b50`, `warn #c18c4e`, `ok #54c5b3` — which was
never applied. The shipped tokens are `--danger: #e0685c`, `--ok: #45c08d`,
`--pending: #e8b44a`, and there is no `--warn` token at all. Applying a ramp that has
already been designed is implementation, not design.

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

### 2.2 All of §5, permission mode

No `permission_mode` consumer exists in the client. `permission_mode_read` appears
nowhere in `src/` or `tests/`, so §5.2's third outcome — *"cannot read this session's
mode"* — is unreachable by construction. The server does serve `permission_mode` on
`/api/read` as §5.1 requires.

What ships instead is the raw `mode` keycap (`index.html:184`) sending `shift-tab`.
There is no segmented picker, no `cycle mode` degradation, no `awaiting readback`
state, and no readback loop — so the control fires blind, which is the problem §5.2
was written to solve: the keycap **cycles**, and you cannot know how many presses you
need without knowing where you are.

---

## 3. Drift from a decided spec

Each of these has a settled answer in the spec and a different one in the code.

| what | spec | shipped | costs |
|---|---|---|---|
| terminal row's identity bar | §4.3: becomes "a solid full-height block, not a 4 px rule" | `style.css:1050` changes only the colour; the `width: 4px` at `style.css:1000` is never overridden | one of the five structural channels that make a terminal row detectable without reading. The other four hold |
| band dismiss control | §2: destructive control ≥ 60 × 60 px | `style.css:1075-1078` is 60 × 44, under a comment asserting "≥60 px" — true of the width only | the one control in the band that cannot be undone |
| roster and the workspace filter | the roster is the landing view (§2.1); the filter is a standing choice | `renderRoster` (`app.js:1027`) is handed every window while the rail filters through `visibleWindows()` (`app.js:1019`) | filter to one project, return to the roster, see everything |
| group header label | §3.3: `project`, or `basename(repo_root)` | `style.css:960` uppercases it | a path basename is shown in a case it does not have |
| state slot position | §3: line 1 is identity bar, name, state slot (right) | the `⋯` expander (`app.js:1558-1570`) is appended after the slot, so `margin-left: auto` no longer puts it rightmost | the slot is no longer the row's right edge |
| §8 extraction list | §8: "keep the extraction list pointed at whatever draws the row" | `tests/js/dialogue.test.mjs:216-224` names seven renderers; `renderRoster` and `groupHeader` also draw roster content and are absent | nothing today — neither reads a reduced field — but the guard has stopped short of the code |

One more, and it is the spec's defect rather than the client's: §4.3's table gives one
sentence, `restart exceeded {n}s grace`, for a row covering **both** `recycling` and
`closing`. `app.js:1296-1300` emits it faithfully for both, so a close that overruns
its grace reports itself as a restart.

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
  warranted; its position is not specified.
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
row, the 44 px group header, the 4 px identity bar, the 25 px control separation, and
the 60 px per-session controls. §7 is complete — neither `#admin-windows` nor
`#distill-list` survives.

Literal identity/status hue disjointness holds and is tested. §1.1 above is about
perceptual distance, which is a different measurement and is not asserted anywhere.
