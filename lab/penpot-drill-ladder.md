# Penpot drill ladder — designer scope

A graded exercise for the `designer` scope's Penpot tooling. Each drill ends with an
assessment by the operator and a named change to a skill, hook, tool, or the
environment. The drills escalate on three axes the operator chose: **tool mechanics**,
**aesthetic judgement**, and **brief ambiguity**. Domains: **product UI**, **brand &
identity**, **iconography**.

Assessment surface: the Penpot editor in a browser on this box. Every drill also
produces a PNG export, so craft (layer hygiene, frames, layout) is graded in the file
and result is graded in the image.

## Arming

Penpot arms for this scope alone. The declaration is `config/mcp/designer.json`, which
`write_agent` copies into the generated agent's frontmatter, so the tools ride the
`--agent` flag itself and any launch path that names the agent arms them. A session that
should have Penpot and does not is caught by the session-start hook, which compares the
scope's declaration against the agent definition and prepends a stop-and-report warning.

If `mcp__penpot__*` tools are absent in a session that expects them, stop and report
rather than working around it — the warning exists because a designer with no design
tool used to be indistinguishable from one with a tool that happened to be idle.

## Instrument facts the drills are built on

Established by source survey and by live probes against the running stack.

- **A 500 is readable, and reading it beats inferring it.** The stack runs on docker's
  `default` context, not `desktop-linux`, and this box's operator is in the `docker`
  group — so no sudo is involved:

  ```
  docker --context default logs penpot-backend-1 --since 24h
  ```

  Validation failures arrive with the offending value, the schema that rejected it and
  a source line (`:code :data-validation`, `{:in [:layout], :schema [::sm/one-of
  #{:grid :flex}], :value "flex"}`). A bare `docker ps` answering from the wrong
  context looks exactly like the stack being unreachable; check `docker context ls`
  before concluding a diagnosis cannot be confirmed (lab/064).

- **68 tools. 25 author. 66 are headless.** Only `get_active_selection` and
  `execute_plugin_script` need the browser bridge on `:4402`.
- **The visual loop closes without a browser.** `export_frame_png` renders through the
  `penpot-exporter-1` container's own headless Chromium and returns base64. Decode to
  disk, `Read` the PNG, look at it. Both export tools render or return an error;
  there is no approximation dressed as a result.
- **Export takes an `object_id`.** Shapes parented to the page root are inside no frame
  and cannot be exported. Author into an explicit `create_frame` or there is nothing to
  look at.
- **A font renders only when `font-id` is written. Name the family as Penpot spells
  it.** Penpot's renderer keys font loading off `font-id`/`font-variant-id`, so a text
  node carrying `font-family` alone renders in the default — which is why the family
  string used to be inert. `set_font` and `create_text` now write all three.

  Spell the family the way the catalogue does: `set_font(font_family="Work Sans")`,
  not `"worksans"`. The id is derived as `gfont-` + the family lowercased with spaces
  hyphenated (`Work Sans` → `gfont-work-sans`), a rule validated against 1719 of the
  1958 catalogue entries in the shipped frontend bundle with zero mismatches. Pass
  `font_id` explicitly to override it. `sourcesanspro` is the built-in default and is
  not a `gfont-` id. Variants are `regular`, `500`, `italic`, `700italic` and so on,
  via `font_variant_id`.

  The renderer does not fetch Google's domain directly. The `@font-face` block in an
  exported SVG sources `http://penpot-frontend:8080/internal/gfonts/font/worksans/v24/
  ....woff2` — the frontend proxies the catalogue, so the outbound hop is the
  frontend's and not the exporter's. Outbound internet is not the constraint.

  **Nothing can refuse a wrong family.** The catalogue lives in the frontend bundle
  and no backend or DB surface carries it, so a well-formed id for a family Penpot
  does not have renders the default with no error. Do not read a rendered PNG and
  conclude the font resolved — that inference was made once here and was wrong; the
  family renders in a lookalike humanist sans and eyeballing cannot separate them. The
  check is `export_frame_svg` and reading `font-family` off the text element — which
  requires the workspace open below. A resolved family exports as
  `font-family: "Work Sans"` beside an `@font-face` for it; an unresolved one exports
  as `sourcesanspro` with no `@font-face`, and that is the difference to read.
  `list_fonts` reads custom team uploads only and returns `[]`; it is not a catalogue.
- **A text created through the MCP cannot be exported until the file has been opened
  once in the Penpot workspace.** `export_frame_svg` and `export_frame_png` return a
  bare 500 for any frame containing a text shape written by these tools. The exporter
  log gives the mechanism: `app.renderer.svg fn=:process-text-nodes`, then
  `locator.screenshot: Timeout 30000ms exceeded — waiting for locator('#screenshot-
  text-<uuid> foreignObject')`. Text laid out by the frontend carries `position-data`
  and renders as `<text textLength=...>` (51ms through the same step); text that has
  never been through the frontend has none, so the exporter falls to the foreignObject
  branch and waits for an element that never appears.

  Loading the file once at the workspace URL fixes it permanently, for that shape and
  every text already in the file. Measured both directions on one unmodified frame:
  500 before the open, full SVG after, nothing else changed. The frame renders fine
  the moment its text is deleted, so a 500 on a mixed frame is a text symptom and not
  a broken file.

  This binds the whole ladder, not just type work: any drill whose artifact carries a
  label must open the file in the workspace before its render check, or the check
  cannot run. It also means a PNG or SVG is not obtainable at all for unopened text —
  there is no degraded output to misread, which is the one mercy in it.
- **Set style at creation time.** `move_shape` and `resize_shape` write `x`/`y`/`width`/
  `height` without refreshing `selrect` and `points`. The five text-mutation tools
  (`set_font`, `set_font_size`, `set_text_align`, `set_text_style`, `set_text_content`)
  rebuild content from the first paragraph only and reset every property not passed.
  `set_stroke` is exempt: it works, and a stroke can be adjusted after creation.

  Creation itself is exact. Measured off a rendered export (lab/064): every shape
  created with explicit `x`/`y`/`width`/`height` and a `parent_id` landed on its
  specified pixel, across a 53-shape board. The hazard is in the mutators, not in
  `create_*`.
- **`modify_shape(attrs)` is the escape hatch, and it reaches enum-valued attributes
  too.** It emits raw operations for any kebab-case Penpot attribute: shadows and blur
  (maps), per-corner radii and rotation (numbers), gradient fills, and `blend-mode`,
  `constraints-h`/`-v`, `layout`, `layout-flex-dir`, stroke alignment, stroke cap and
  grow type. A misspelt enum member still returns a bare 500, and that 500 is the
  right answer — read it in the backend log rather than guessing which of several
  attributes in the batch was refused.
- **`set_layout` works, and padding is per-side.** `padding` sets all four sides;
  `padding_top`/`padding_right`/`padding_bottom`/`padding_left` override individually,
  and the tool emits `layout-padding-type` to match. 16 horizontal / 8 vertical is
  `padding_left=16, padding_right=16, padding_top=8, padding_bottom=8`.
- **Auto-layout is configuration, not reflow. Children do not move — including in the
  editor.** Setting `layout` stores the configuration and leaves every child at its
  authored coordinates, and the exporter's render page runs no layout pipeline, so a
  headless PNG shows the frame exactly as composed. Controlled: a frame with layout
  baked in at `add-obj` renders identically un-reflowed, so this is
  authoring-without-an-editor, not a property of how the attribute was written.

  Measured in the browser, closing the open question: a frame written headlessly with
  `layout: flex`, `row`, gap 16, padding 16, `align-items: start`, and two children
  parked overlapping at the bottom-right — where flex would never leave them — opened
  in the editor and **did not reflow**. Children read back at their authored
  coordinates after the open, and again after selecting the frame. All seven layout
  attributes store and read back intact. **Assessment does not mutate the design**, and
  composing with absolute coordinates is safe; auto-layout is inert-but-recognised
  metadata for whoever edits the file next.
- **A workspace deep link needs `team-id`, and without it the editor dies on a
  wholly unrelated error.** `#/workspace?file-id=…&page-id=…` loads far enough to look
  like a real failure and then throws a full-page *Internal Error*, because
  `get-font-variants` is called with `{}` and the backend refuses
  `[::sm/contains-any #{:team-id :file-id :project-id}]`. Nothing is wrong with the
  file — the same file opens correctly from the dashboard, or from:

  ```
  https://penpot.<tailnet>.ts.net/#/workspace?team-id=<team>&file-id=<file>&page-id=<page>
  ```

  Worth knowing because the failure names fonts, not the URL, and it looks identical
  to a corrupted file. The backend log stays silent; the evidence is in the browser
  console.
- **A revision is a successful write, and only that.** A 53-shape board reconciled
  exactly to its revision number; failed writes consume none. Expensive in undo steps
  and a real race if the file is open elsewhere — but cheap in wall clock, because the
  calls parallelise. 54 creates went out in 6 batched messages (lab/064). Avoid the
  call-per-message loop, not the model.
- **The PNG never needs to enter context.** `export_frame_png` overflows the
  tool-result ceiling and the harness spills it to a file under the session's
  `tool-results/`. The payload is JSON-in-JSON with the image under `content_base64`;
  decode straight off that file and `Read` the result. No base64 crosses into the
  conversation, so looking at a 2x export is nearly free. The overflow error is the
  mechanism, not an obstacle.
- **Every tool call is its own file revision.** A 40-shape screen is 40 round trips, 40
  undo steps, and a real race if the file is open elsewhere. No transaction tool.

- **A path cannot be read back — but its bounding box can, and that is the only
  machine-checkable assertion vector work has.** `get_shape_details` returns
  `content: null` and `selrect: None` for any path, because the DB reader never decodes
  the binary v2 `PathData` blob. `x`/`y`/`width`/`height` still come back, and they are
  the **true cubic extent**, not the endpoint box. Proved with an arc whose control
  points push outside its endpoints: apex predicted analytically at y=30
  ((60+3·20+3·20+60)/8), read back `y: 30, height: 30`, where an endpoints-only selrect
  would report height 0. Compute a path's expected extent and assert it (lab/065).
- **Dash geometry is a stroke-width derivative unless you override it. Pass `dash`
  and `gap`.** `stroke-style: "dashed"` on its own does not dash at a size — Penpot's
  `calculate-dasharray` returns `(or dash w+10),(or gap w+10)`, so the pattern is
  computed from *stroke width* and never from the shape. A 2px stroke dashes at 12,12
  whatever it is drawn around: on a 16×16 boundary (perimeter ~64) that is 2.7 dashes,
  which lands as four corner brackets and reads as a crop frame. At 24px icon scale
  pass `dash=2, gap=2`.

  Requires Penpot ≥ 2.17.0, which added `:stroke-dash`/`:stroke-gap` to
  `schema:stroke-attrs`; this box runs 2.17.0 exactly. The schema is `:closed true` and
  types both as numbers, so the fields are omitted when unset rather than sent as null.

  Still unreachable, in every version: **dash offset** (no field anywhere, always 0),
  **`dotted` and `mixed` geometry** (dash/gap are read only on the `dashed` branch, so
  those two keep width-derived patterns), and **arbitrary multi-segment dasharrays**
  (`mixed` is the only multi-segment pattern and its four numbers are fixed by width).
  Penpot's *plugin* API exposes no dash accessor at all, so `execute_plugin_script` is
  not a route to this — only the RPC/changes path the MCP already uses.

  Dashing is also the only affordable enclosure at icon scale, which is why this
  mattered beyond style: against lab/065's ~100px² ink budget a solid 20×16 container
  plus a node ring costs 173.7px² (1.74× over), while the same boundary dashed at 2,2
  costs 105.7px² and at 2,3 costs 92.1px² — inside budget. A dashed boundary is roughly
  half the ink of a solid one.
- **Round caps are authorable through `modify_shape`, and they survive a read-back.**
  `set_stroke` exposes no cap parameter, but writing the whole `strokes` array reaches
  `stroke-cap-start` / `stroke-cap-end`. Confirmed both in the rendered SVG
  (`stroke-linecap: round`) and through `get_shape_details` — unlike path content, caps
  round-trip. This is what makes a consistent terminal style possible across a set.
- **Writing the `strokes` array wholesale drops every field you omit.** Setting caps
  without restating `stroke-opacity` loses it. Write the full stroke map every time —
  the text-mutation reset hazard applies to `modify_shape`'s array writes too.
- **Paths take absolute canvas coordinates.** Frames are placed in the same space, so
  writing a frame-relative coordinate as an absolute silently puts the shape elsewhere
  and still returns 200.
- **`get_shape_svg` still dresses an approximation as a result.** It renders through
  `transformers/svg.py` — first fill, first stroke, no gradients, shadows, blur or
  clipping — and presents that as "SVG representation of a shape" with no caveat. It
  is the trap `export_frame_svg` used to carry, in a tool that still carries it. Use
  `export_frame_svg` when the answer has to be true.

Suspected broken, not yet proven:

- `create_component` never emits the `add-component` change, so nothing registers in
  the assets panel.
- `create_group` hardcodes a 0,0,100x100 bounding box regardless of children.

Three defects are fixed, and the fixes ship as `deploy/penpot/patches/` applied at
image build — the README carries the mechanism and the reasoning:

- **`create_path` speaks the v2 path format.** It sends `move-to`/`line-to`/
  `curve-to`/`close-path`, the names `path.impl/from-plain` dispatches on, and
  rejects the SVG commands Penpot has no clause for rather than posting a request
  the backend will refuse. A curved path's selrect is now the exact cubic extent,
  so the exporter no longer screenshots a box too small for its own curve.
- **Rendering authenticates.** Penpot's exporter takes a session cookie and nothing
  else, and no route exchanges an access token for a session, so `PENPOT_EMAIL` and
  `PENPOT_PASSWORD` in `deploy/penpot/.env` name the account the renderer signs in
  as. Point them at a read-only viewer account, not your own.
- **A mod-obj operation can carry a keyword.** `set_op` emits Penpot's `:assign`
  operation for attributes whose value needs string→keyword coercion — its handler
  runs the same `json-transformer` decode `add-obj` gets — and keeps `:set` for
  everything that already worked. Enum-valued attributes, `set_stroke` and
  `set_layout` are all live. Validation is unchanged: a bogus member reaches the
  schema *as a keyword* and is still refused.

Vector work is therefore live: D2, D3 and D5 have a path primitive, and the
render-and-look loop closes.

Absent entirely: boolean path ops, path editing, align and distribute, component
instances and variants, shared-library publish, color and typography assets, design
tokens, multi-line text, rich text runs, image placement on canvas, prototyping of
any kind, and PDF export (implemented in `tools/export.py`, never registered as a
tool).

No dedicated tool, but reachable through `modify_shape`: constraints
(`constraints-h`/`-v`, measured), per-item layout properties (`layout-item-h-sizing`,
`layout-item-align-self`, …) and grid track authoring (`layout-grid-rows`/`-columns`).
Only constraints have been probed; the rest are routed and untested.

## The ladder

### D0 — Instrument check

*Mechanics only. Not graded on aesthetics.*

One 400x300 frame holding a rectangle, an ellipse, and one line of text in a stated
palette. Export at `scale=2.0`, decode, look at it, hand it over.

Proves the round trip end to end and calibrates what "it worked" looks like. Expected
to surface: which font actually renders, and whether geometry survives.

### D1 — Product UI, fully specified

*High mechanics, zero ambiguity, low aesthetic latitude.*

A button matrix: three variants (primary, secondary, ghost) by three states (default,
hover, disabled), nine cells on an 8px grid, with padding redlines called out.

The brief leaves nothing to interpret, so this grades execution alone.

Run 2026-08-12 — file `D1 button matrix`, 53 shapes. **Assessed 2026-08-13: passed.**
The operator read the board as pixel-accurate and found nothing to criticise, while
noting they had no way to *measure* it on the canvas — the redlines assert a number
the assessment surface cannot check. Execution is therefore confirmed only to the
resolution of the eye, which is the ceiling for every drill graded this way. Surfaced
P3, since fixed, along with exact creation geometry, the revision/wall-clock split,
and the free render-and-look loop. Written up in lab/064.

### D2 — Iconography, mechanics ceiling

*Peak mechanics, aesthetic judgement enters as consistency.*

A six-icon set on a 24px grid at uniform 2px stroke, optically corrected rather than
mathematically aligned: node, edge, memory, recall, thread, expert.

This is where `create_path` is load-bearing. Grades vector craft and, harder,
consistency *across* a set — the thing no single icon reveals. Expected to surface: the
absence of boolean ops and of align/distribute, whether optical correction survives
being computed rather than eyeballed, and how much a path costs to iterate on when it
cannot be read back.

Run 2026-08-13 — file `D2 icon set`, 27 shapes, awaiting assessment. Optical correction
computed rather than eyeballed did survive: the centroid-not-bounding-box rule
generalises to measuring the **ink centroid** off the render and moving the composition
until it lands on (12,12), which five of six icons hit within 1.1px. Two findings
outrank the deliverable, both in lab/065:

- **The ink budget is arithmetic, and it constrains every drill at icon scale.** A 24px
  icon at 2px stroke affords roughly 100px² of ink out of 576. A ⌀8 node ring costs
  37.7; a closed 20×16 container costs **136 before any content**. A solid enclosure is
  therefore unaffordable, and so is three nodes with two edges (~147). The set only
  converged once every icon was built to about two rings plus a connector: spread fell
  from 2.31× to 1.25×.
- **Internal consistency buys nothing against the world's existing icon sets.** Five
  first-pass icons had to be redrawn for collisions — camera (twice, from unrelated
  starts), logout, RSS/wifi, and the Mars symbol. At 24px an enclosure containing a
  centred circle *is* a camera. The move is not to escape collision but to pick one
  whose misreading is semantically adjacent.

### D3 — Brand and identity, directional brief

*Aesthetic judgement leads. Ambiguity rises.*

Thalamus has no visual identity. Produce one board: a wordmark, a mark, a colour system
with stated rationale, and a type pairing.

Grades point of view — whether the work argues for something or merely assembles.
Expected to surface: that a "system" cannot live in Penpot as assets here, because no
tool writes shared colours or typographies, so the system has to be expressed as
drawn artefact plus written spec.

Run 2026-08-14 — file `D3 identity board`, spec in `lab/d3-identity-spec.md`, awaiting
assessment. The prediction held exactly: every colour and typography tool on this MCP
is a getter, so the system ships as board plus document with nothing but discipline
linking them.

The point of view came from measurement rather than taste, which is the part worth
carrying forward. Thalamus already had three identities — the console's chosen palette,
the viewer's Tailwind defaults, the diagrams' GitHub greys — so the argument became
*keep what was chosen, retire what was defaulted, invent nothing*. Two findings fell
out of measuring the shipped console with `thalamus.eval.legibility`:

- **Status is encoded in hue alone.** The console's signal colours sit within 1.13:1 of
  each other in luminance; `danger` and `muted` are 1.09:1 apart and collapse to the
  same grey desaturated. The shipped ramp is not even monotonic — `warn` desaturates
  brighter than `ok`. Corrected to 1.41:1 minimum pairwise, hues preserved. This is a
  live WCAG 1.4.1 exposure on a shipped surface, and the natural hand-off to `qe`.
- **`--faint` (`#4d5661`) measures 2.54:1**, below the 3:1 non-text floor. Legal as a
  hairline, illegal as anything meaning-carrying.

### D4 — Product UI against a built surface, high ambiguity

*Ambiguity leads. Critique is part of the deliverable.*

Redesign the console PWA's roster view for a phone. No spec exists. Go look at the
built surface first, report drift from design intent as findings, then design against
what is actually there.

Grades whether the right questions get asked before pixels move, and exercises the
charter's critique-as-finding boundary. Expected to surface: how much of a design
decision survives contact with an already-shipped surface.

### D5 — Capstone

*All three axes at maximum, in one piece.*

A hero illustration of the memory graph that is both beautiful and structurally true to
the architecture. Near-zero specification.

Grades everything at once and is the only drill where a wrong-but-pretty answer and a
right-but-ugly answer are both failures.

## Protocol

**One drill per pinned session.** Each drill runs in a fresh `thalamus pin designer`
session, distills into the scope's episodic memory on exit, and is assessed before the
next begins. Whether the next session's recall actually carries the previous drill's
lesson forward is itself a measurement, not an assumption.

**A broken tool stops the drill.** On hitting a defect, produce a minimal reproduction,
diagnose it precisely, write the defect report, and stop — do not route around it to
deliver something that looks finished. Workarounds hide defects behind competent output
and convert a design exercise into a workaround-engineering exercise. This is the
charter's critique-as-finding boundary applied to the instrument itself.

Each drill closes with a named change to a skill, hook, tool, or the environment. A
drill that produces a deliverable and no change has not been assessed.

## Open findings

1. **The hand-launch path arms no design tool and says nothing.**
   `claude --agent thalamus-designer --permission-mode auto` reproduces two of the
   three flags `pin.py::_claude_argv` builds and silently drops `--mcp-config`. The
   failure is invisible from inside the session — the scope prompt claims a design
   tool the process does not have. Owner is `main` or `architect`; `designer`'s
   `write_boundary` denies `*.py`, and moving the config into `config/experts/
   designer.yaml` is ruled out by `pin.py:558` (the manifest is harness-agnostic
   because Cursor reads it, and `--mcp-config` is Claude Code's schema).

2. **A component copy does not inherit an enum-valued attribute from its main.**
   Penpot's `components-changed` and `frames-changed` match
   `(= (:type operation) :set)`, and the attributes that need `:assign` are all in
   `sync-attrs` — so writing one on a main component synchronises nothing to its
   copies, and does not invalidate the frame thumbnail. Nothing that worked before is
   affected; the exposure is confined to attributes that used to be a hard 500. Owner
   is `architect`. The revisit trigger is a drill that actually needs the inheritance.

3. **Dash geometry at icon scale — closed 2026-08-13, fixed in `patches/0003`.** It
   needed a tool argument, not a model change: Penpot 2.17.0 added `:stroke-dash` and
   `:stroke-gap` to `schema:stroke-attrs`, and this box runs exactly 2.17.0. `set_stroke`
   now takes `dash` and `gap`. See the dash instrument fact above for how to author and
   what is still unreachable.

4. **Typography was unwritable, blocking D3 — closed 2026-08-13, fixed in
   `patches/0004`.** `build_text_content` emitted `font-family` and never `font-id`, so
   every text rendered in the default. `text-font-attrs` always carried both; nothing
   wrote them. `set_font` and `create_text` now do, and D3's type pairing is deliverable.
   Owner was `architect`. See the font instrument fact above.

   Verified at the render 2026-08-14, not just at the read-back: a Work Sans text
   exports as `font-family: "Work Sans"` with a matching `@font-face`. The verification
   is what surfaced defect 6 below, which had to be cleared first to obtain any render
   of a new text at all.

   This one sat because it was filed as an instrument fact with no owner and no revisit
   trigger, so nothing tracked it — a defect that blocks a drill belongs here, where it
   has both, not only in the prose above.

5. **Whether an editor open reflows a headlessly-configured frame — closed 2026-08-13,
   negative.** It does not, and neither does selecting the frame. See the auto-layout
   instrument fact above for the measurement. Nothing is left open here: the layout
   has to be touched in the UI before Penpot recomputes anything, so the assessment
   surface is read-only with respect to child geometry.

6. **A frame containing MCP-written text exports as a bare 500 until the file is opened
   once in the workspace — open, owner `architect`.** The exporter times out waiting for
   a `foreignObject` that only appears for text the frontend has laid out; see the
   instrument fact above for the log line and the two-directional measurement. The
   workaround is one browser load per file and it holds afterwards, so this blocks
   nothing today, but every render check on a labelled artifact now depends on a manual
   step outside the tool surface — which is the kind of dependency the ladder exists to
   find. Worth architect deciding whether the MCP can write `position-data` itself, or
   whether the export tools should say this instead of returning a naked 500.

7. **`create_text(font_weight=...)` is inert — the weight never renders. Open, owner
   `architect`.** Exactly the shape of the defect `patches/0004` just fixed, one field
   over: Penpot selects a face by `font-variant-id`, and `create_text` writes
   `font-weight` while leaving the variant at `regular`. A board authored at 500 and 600
   exported with every weight at 400 and only two `@font-face` blocks. Writing
   `font-variant-id` through `modify_shape` fixes it and the export then carries four
   faces — Mono 400/500, Sans 400/600. The tool should derive the variant from
   `font_weight`, or say it cannot.

8. **`set_font` silently resets font size, fill colour and letter-spacing to defaults.
   Open, owner `architect`.** Measured on the wordmark: 56px → 16px, `#CDD8E4` →
   `#000000`, letter-spacing -1 → 0, from a call that named only the family and variant.
   Black text at 16px on a `#0e1116` board is invisible, so the failure is silent in the
   worst way — the tool returns success and the artefact looks deleted. The general
   text-mutation reset hazard was already recorded above; this is the measured case, and
   the reason every font change on this board went through `modify_shape` with the whole
   content map restated instead.
