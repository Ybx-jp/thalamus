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

Penpot arms only for this scope, only through `thalamus pin designer` — that path adds
`--mcp-config config/mcp/designer.json` (`pin.py:_claude_argv`). Launching by hand with
`claude --agent thalamus-designer` reproduces the pin flags but not the MCP config, and
produces a designer with no design tool and no error. See the open finding below.

## Instrument facts the drills are built on

Established by source survey, not by the deployment README (which is wrong on all three
counts: it says 68 tools / 22 authoring / a 46-22 live-headless split).

- **68 tools. 25 author. 66 are headless.** Only `get_active_selection` and
  `execute_plugin_script` need the browser bridge on `:4402`.
- **The visual loop closes without a browser.** `export_frame_png` renders through the
  `penpot-exporter-1` container's own headless Chromium and returns base64. Decode to
  disk, `Read` the PNG, look at it. `export_frame_svg` silently falls back to a crude
  local reimplementation on exporter failure — it tags itself with a `note` key, and
  that key is the difference between pixel-truth and a sketch.
- **Export takes an `object_id`.** Shapes parented to the page root are inside no frame
  and cannot be exported. Author into an explicit `create_frame` or there is nothing to
  look at.
- **Fonts that actually render offline:** `sourcesanspro` (default), `worksans`,
  `robotomono`, `vazirmatn`. The 1,910 catalogued Google families need outbound
  internet *and* a `font-id` on the text node, which no tool writes. `list_fonts`
  reads custom team uploads only and returns `[]`.
- **Set style at creation time.** `move_shape` and `resize_shape` write `x`/`y`/`width`/
  `height` without refreshing `selrect` and `points`. The five text-mutation tools
  (`set_font`, `set_font_size`, `set_text_align`, `set_text_style`, `set_text_content`)
  rebuild content from the first paragraph only and reset every property not passed.
- **`modify_shape(attrs)` is the escape hatch** — it emits raw set-ops for any
  kebab-case Penpot attribute, which is the only route to shadows, blur, blend modes,
  per-corner radii, rotation, constraints, and gradient fills.
- **Every tool call is its own file revision.** A 40-shape screen is 40 round trips, 40
  undo steps, and a real race if the file is open elsewhere. No transaction tool.

Proven broken (repro below, run 2026-08-11 against the live stack):

- **`create_path` cannot create a path.** Every call fails.
- **`export_frame_png` cannot export.** Every call fails, for an unrelated reason.

Suspected broken, not yet proven:

- `create_component` never emits the `add-component` change, so nothing registers in
  the assets panel.
- `create_group` hardcodes a 0,0,100x100 bounding box regardless of children.

## Confirmed defects

### P1 — `create_path` is dead on this Penpot version

Repro: `create_path` with segments `[{M,40,270},{L,140,180},{L,240,270},{Z}]` into a
frame. Returns `500 Internal Server Error` from `/api/rpc/command/update-file`.

Backend exception:

```
java.lang.IllegalArgumentException: No matching clause: :m (impl.cljc:687)
  at app.common.types.path.impl$from_plain.invokeStatic(impl.cljc:687)
     ... malli.core ... app.rpc$wrap_params_validation
```

`create.py:373` lowercases the SVG command letter and ships `{"command": "m"}`.
Penpot's `path.impl/from-plain` dispatches on `:move-to`/`:line-to`/`:curve-to`/
`:close-path` and has no clause for `:m`. This team's feature flags include
`fdata/path-data` and the file carries migration `0003-convert-path-content-v2`, so
the instance is on the v2 path format — the tool was written against something older.

Fails in `wrap_params_validation`, i.e. the request is rejected before touching file
state. No corruption, no partial write, no cleanup needed. Every other authoring tool
tested (`create_frame`, `create_rectangle`, `create_ellipse`, `create_text`) succeeded
against the same file in the same session, so this is specific to paths, not to writes.

Consequence for this ladder: **D2, D3 and D5 are all blocked.** There is no vector
primitive. Rect, ellipse, text and frame are the entire drawing vocabulary, and with
no boolean ops either, any form that is not a rounded box or an ellipse is currently
undrawable through this MCP.

### P2 — `export_frame_png` cannot authenticate to the exporter

Repro: `export_frame_png` on a frame that renders fine in the editor. Returns
`Export failed: Client error '400 Bad Request' for url '.../api/export'`.

The exporter's actual response names the field:

```
-- Spec failed --  {:file-id ..., :objects ..., :page-id ..., :token nil,
                                                                     ^^^
   ...} should satisfy render-params
```

Cause: two auth mechanisms that do not meet. `compose.yml` configures the MCP with
`PENPOT_ACCESS_TOKEN`, so `api.connect()` sets an `Authorization: Token …` header and
never logs in — the cookie jar stays empty (verified: `COOKIES: []`). But
`api.export_object` (`services/api.py:229`) authenticates to the exporter by scanning
that jar for an `auth-token` cookie, finds nothing, and posts with `cookies={}`. The
exporter needs a session token to load the page in its headless Chromium, gets `nil`,
and rejects on spec.

So the exporter is healthy and the credential never reaches it. The two configured
auth modes are not interchangeable: `PENPOT_EMAIL`/`PENPOT_PASSWORD` would populate
the jar and make export work, at the cost of storing a password.

**`export_frame_svg` hides this.** On the same failure it silently falls back to
`transformers/svg.py`, a local reimplementation that supports first-fill, first-stroke,
and no gradients, shadows, blur or clipping. It returns success with a `note` key. Any
SVG "export" taken while P2 is open is a sketch of the design, not the design.

Consequence: **the render-and-look loop is closed.** I cannot see my own output. Every
drill would be authored blind until this is fixed, which makes aesthetic judgement
untestable — the axis the operator ranked second.

Absent entirely: boolean path ops, path editing, align and distribute, grid track
authoring, per-item layout properties, constraint setting, component instances and
variants, shared-library publish, color and typography assets, design tokens,
multi-line text, rich text runs, image placement on canvas, prototyping of any kind,
and PDF export (implemented in `tools/export.py`, never registered as a tool).

## The ladder

### D0 — Instrument check

*Mechanics only. Not graded on aesthetics.*

One 400x300 frame holding a rectangle, an ellipse, and one line of text in a stated
palette. Export at `scale=2.0`, decode, look at it, hand it over.

Proves the round trip end to end and calibrates what "it worked" looks like. Expected
to surface: whether the export path is live or falling back, which font actually
renders, and whether geometry survives.

### D1 — Product UI, fully specified

*High mechanics, zero ambiguity, low aesthetic latitude.*

A button matrix: three variants (primary, secondary, ghost) by three states (default,
hover, disabled), nine cells on an 8px grid, with padding redlines called out.

The brief leaves nothing to interpret, so this grades execution alone. Expected to
surface: whether `set_layout` flex is usable for real composition, the cost of the
one-call-one-revision model at ~40 shapes, and whether text survives being built.

### D2 — Iconography, mechanics ceiling

*Peak mechanics, aesthetic judgement enters as consistency.*

A six-icon set on a 24px grid at uniform 2px stroke, optically corrected rather than
mathematically aligned: node, edge, memory, recall, thread, expert.

This is where `create_path` is load-bearing and is suspected broken. Grades vector
craft and, harder, consistency *across* a set — the thing no single icon reveals.
Expected to surface: the path bug, the absence of boolean ops and of align/distribute,
and whether optical correction is possible without a canvas to eyeball.

### D3 — Brand and identity, directional brief

*Aesthetic judgement leads. Ambiguity rises.*

Thalamus has no visual identity. Produce one board: a wordmark, a mark, a colour system
with stated rationale, and a type pairing.

Grades point of view — whether the work argues for something or merely assembles.
Expected to surface: that a "system" cannot live in Penpot as assets here, because no
tool writes shared colours or typographies, so the system has to be expressed as
drawn artefact plus written spec.

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

1. **`deploy/penpot/README.md` misstates the tool counts** — "68 tools, 22 of them
   authoring" and an implied 46/22 headless split. Actual: 68 total, 25 authoring, 66
   headless. Consequence is not cosmetic: it reads as though authoring needs a browser
   open, which would rule out exactly the unattended work the scope is for.
2. **The hand-launch path arms no design tool and says nothing.**
   `claude --agent thalamus-designer --permission-mode auto` reproduces two of the
   three flags `pin.py::_claude_argv` builds and silently drops `--mcp-config`. The
   failure is invisible from inside the session — the scope prompt claims a design
   tool the process does not have. Owner is `main` or `architect`; `designer`'s
   `write_boundary` denies `*.py`, and moving the config into `config/experts/
   designer.yaml` is ruled out by `pin.py:558` (the manifest is harness-agnostic
   because Cursor reads it, and `--mcp-config` is Claude Code's schema).
