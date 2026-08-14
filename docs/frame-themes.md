# Frame themes

The console's desktop surface can render the terminal *inside* a region of a
background image, with artwork around it — a sign, a panel, a screen, whatever the
image contains.

This page documents it as a **primitive**: a small contract you can target from
anything. A generator ships in `tools/`, but it is only one way to produce the
contract, and nothing here depends on using it.

Entirely optional, and off by default. Without `--frames` — or with a file that
yields no usable frames — the theme controls are not drawn at all and the rest of
the console is unaffected. Thalamus ships no artwork.

## Why data and not an emulator

Terminal emulators paint background art on the GPU. None of that crosses a wire, so
bridging the console to an emulator's own rendering would return the same plain text
tmux already gives and render exactly zero themes. What travels instead is a
measurement: where the text region sits inside the image, as fractions. Any consumer
that can scale an image and position a box can reproduce the look from that.

Fractions rather than pixels because consumers scale the image into a viewport of
unknown size. A fraction holds at any size; a pixel offset does not.

## The contract

One file and two endpoints. Produce the file however you like.

### The frame file

Named by `thalamus console --frames PATH`. There is no default: the file names
absolute image paths on one machine, so a shipped package has no business guessing
one. If you also use WezTerm, `$WEZTERM_CONFIG_DIR/frames.lua` is the conventional
place and the same file serves both.

It is Lua by convention — WezTerm consumes the same file — but **the server never
executes it**. It is scraped with a regular expression, which constrains the shape:

```lua
return {
  { name = "example-frame.png", path = "/absolute/path/to/example-frame.png",
    panel = { left = 0.22000, right = 0.21500, top = 0.25400, bottom = 0.13800 } },
}
```

| Field | Meaning |
|---|---|
| `name` | Identifier. The client requests `/frame/<name>`. Must be unique |
| `path` | **Absolute** path to the image on the server's disk |
| `panel` | Inset of the text region from each edge, as a fraction of the whole image |

Rules the parser actually enforces — worth knowing if you generate this yourself:

- **Field order is fixed**: `name`, then `path`, then `panel`, and inside `panel`
  `left`, `right`, `top`, `bottom`. The pattern is positional. Reordering keys is
  valid Lua and will silently not match.
- Strings are double-quoted. Whitespace and line breaks between fields are free.
- Anything before or after the entries is ignored, so comments are fine.
- An entry whose `path` is missing from disk, or whose extension is not
  `.png/.gif/.jpg/.jpeg/.webp`, is **dropped silently**. A stale file degrades to
  fewer frames, never to a broken background.

**`panel` holds insets, not coordinates.** `left = 0.22` means the region starts 22%
in from the left edge; `right = 0.215` means it ends 21.5% in from the *right* edge.
Width is `1 - left - right`. Read as `x0, x1` it puts the text box in the wrong place
and mirrors it — this is the single easiest thing to get wrong here.

### Endpoints

| Endpoint | Returns |
|---|---|
| `GET /api/frames` | `{"frames": [{"name": …, "panel": {…}}, …]}` — names and geometry only |
| `GET /frame/<name>` | the image bytes, `max-age=86400` |

`path` is never exposed to the client and never taken from a request: `/frame/<name>`
looks the name up in the parsed list and serves the path recorded there, so a request
cannot reach an arbitrary file. Frames are re-parsed when the file's mtime changes, so
edits appear without a restart.

The trust boundary is the frame file, not the request. Whoever writes it can name any
absolute path with an image extension, and the console will serve it — the same trust
already extended to `--dir`. That is the reason there is no default frame file.

The service worker deliberately does **not** cache `/frame/<name>`: the art is
multi-MB and desktop-only, and caching it would pin megabytes in the storage of the
one device that can never display it.

## Try it with no artwork

The awkward part of evaluating this feature is that it needs a picture with a suitable
region in it before anything is visible. So don't find one:

```sh
uv sync --extra frames                 # pillow, numpy, scipy — only these tools need them
./tools/make-sample-frame.py --out ~/frames    # a synthetic scene with a flat panel
./tools/build-frames.py --dir ~/frames         # detects it, bakes the scrim, writes frames.lua
thalamus console --frames ~/frames/frames.lua
```

Then reload the desktop surface and press `F12`. `make-sample-frame.py` deliberately
puts a shape across the panel boundary so the scrim step has visible work to do.

## Hand-authoring

You do not need the generator. If you already know where the region is — because you
drew the image, or exported bounds from a design tool — write the file directly:

```
left   = x0 / width          right  = (width  - x1) / width
top    = y0 / height         bottom = (height - y1) / height
```

where `x0,y0..x1,y1` is the text region in pixels. Keep the field order above. This is
the whole integration; any script, Makefile, or export step that can emit those four
numbers is a frame producer.

## The bundled generator

`tools/build-frames.py` turns images in a directory into frames. For each one it:

1. **Finds the region.** Seeds with the largest rectangle touching no artwork, reads
   that seed's flat colour, then takes every connected pixel of that colour. It keys on
   colour identity rather than darkness because anything overlapping the region's edge
   makes those rows only partly dark, and a threshold loose enough to grow past that
   also runs off the region into dark scenery behind it. Colour has a hard edge where
   the region ends; darkness doesn't.
2. **Bakes a legibility scrim** — darkens the region toward its own median colour so
   art intruding into it cannot fight the text. `--scrim 0` leaves art untouched, `1`
   erases everything inside the region. Default `0.74`.
3. **Writes the frame file**, insetting the recorded bounds by a few pixels so glyphs
   clear the border.

Built images are written to `built/` beside the originals, which are left alone.
Animated GIFs are passed through unscrimmed — compositing one would flatten it to a
single frame — and only their first frame is measured.

These tools are the only part of Thalamus that wants pillow/numpy/scipy, which is why
they are an optional extra rather than a dependency of a tmux bridge.

### When detection is wrong

The tool prints the region it found per image and flags any under 12% of image area.
Override with **pixel coordinates** (not insets) in `panels.json` beside the images
and re-run:

```json
{ "example-frame.png": { "left": 346, "top": 222, "right": 1333, "bottom": 872 } }
```

## How the client applies it

The image is drawn with `background-size: contain`, which letterboxes it inside the
viewport — so the fractions cannot be applied to the viewport directly. The client maps
them through the contain-fit using the image's `naturalWidth`/`naturalHeight` to
produce four pixel values, then absolutely positions the text box:

| Property | Meaning |
|---|---|
| `--panel-x`, `--panel-y` | text region origin, in viewport px |
| `--panel-w`, `--panel-h` | text region size, in viewport px |

Font size is fitted to the **region** width rather than the pane width, so a frame
stays legible at any window size.

Desktop only, gated on `matchMedia("(pointer: fine) and (min-width: 900px)")` — the
mobile surface never loads frame art. `F12` toggles, `F9` cycles, `F11` fullscreen.
`F12` and `F9` are claimed only once a frame file has yielded frames: `F12` is
Chrome's DevTools key, and taking it on every console to toggle a feature that is
off is a worse trade than losing the binding on the boxes that never opted in.

## The wider theming surface

Frames are the most visible customization hook, not the only one. The palette is CSS
custom properties on `:root` in `style.css`, and overriding them is enough to reskin
the interface without touching markup or logic:

| Property | Role |
|---|---|
| `--bg` | page background |
| `--panel`, `--panel-hi` | surfaces: bars, sheets, rows |
| `--hair` | hairline borders |
| `--ink`, `--muted`, `--faint` | text, in descending emphasis |
| `--danger` | destructive actions |
| `--mono`, `--ui` | type stacks |
| `--chan` | accent for the active channel — set per channel at runtime |
| `--tab` | each tab's own colour, carried alongside `--chan` |
| `--screen-size` | terminal font size, computed by the auto-fit |

`--chan` is the one that moves: it is rewritten whenever the active channel changes.
Channel colours are **derived, never configured** — `main` takes a fixed violet and
every other scope hashes its own name into a small palette, so adding an expert
manifest colours its tab with nothing to edit. A window in a room takes the *room's*
colour instead, so co-membership is what reads at a glance; the room badge carries the
name, because a palette this size cannot promise two rooms different colours.

Static files are read from disk on every request, so `style.css` and `app.js` edits are
live on reload with no restart.
