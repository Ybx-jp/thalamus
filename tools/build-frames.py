#!/usr/bin/env python3
"""Turn a directory of images into frame themes for `thalamus console --frames`.

For each image: find the sign/panel the terminal text should sit in, darken any
figures leaning into it so text stays legible, and record the panel geometry as
fractions of the image. Consumers scale the image into a viewport of unknown size,
so fractions hold where pixel offsets would not.

Usage:
    build-frames.py --dir ~/frames [--scrim 0.74]
    thalamus console --frames ~/frames/frames.lua

Detection can be overridden per file in `panels.json` beside the images:
    { "my-image.png": {"left": 346, "top": 222, "right": 1333, "bottom": 872} }

This is ONE producer of the frame file, not the definition of it. The file is a
contract — anything emitting {name, path, panel} works, and hand-authoring is a
first-class path. The generator ships because without it the geometry is
reproducible only by hand. WezTerm consumes the same file, so pointing `--dir` at
`$WEZTERM_CONFIG_DIR/frames` makes one frame serve both. Format and workflow:
docs/frame-themes.md.

Needs pillow, numpy and scipy — `uv sync --extra frames`. Nothing else in Thalamus
wants them, which is why they are an optional extra and this lives outside the
package.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp')
DARK = 60        # luminance below this counts as "panel", not "art"
TOL = 20         # per-channel distance from the panel colour that still counts as panel
TEXT_INSET = 18  # keep glyphs off the glowing border
RADIUS = 42
FEATHER = 9


def luminance(im):
    a = np.asarray(im.convert('RGB'), dtype=np.float32)
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def largest_dark_rect(dark):
    """Biggest all-dark axis-aligned rectangle (maximal rectangle in histogram)."""
    h, w = dark.shape
    heights = np.zeros(w, dtype=int)
    best = (0, 0, 0, 0, 0)
    for y in range(h):
        heights = np.where(dark[y], heights + 1, 0)
        stack = []
        for i, cur in enumerate(list(heights) + [0]):
            start = i
            while stack and stack[-1][1] > cur:
                idx, hh = stack.pop()
                area = hh * (i - idx)
                if area > best[0]:
                    best = (area, idx, y - hh + 1, i - 1, y)
                start = idx
            stack.append((start, cur))
    return best[1:]  # x0, y0, x1, y1


def detect_panel(im):
    """Find the sign.

    Seed with the largest rectangle that touches no artwork, read the panel's
    flat colour out of it, then take every pixel of that colour connected to the
    seed. Growing the seed by darkness alone doesn't work: figures leaning over
    the sign make the border rows only ~30% dark, and the threshold you'd need to
    grow past them also runs off the sign into dark scenery behind it. Colour
    identity has a hard edge where the sign ends; darkness doesn't.
    """
    a = np.asarray(im.convert('RGB'), dtype=np.int16)
    h, w = a.shape[:2]
    x0, y0, x1, y1 = largest_dark_rect(luminance(im) < DARK)

    panel_rgb = np.median(a[y0:y1 + 1, x0:x1 + 1].reshape(-1, 3), axis=0)
    same = np.abs(a - panel_rgb).max(axis=2) <= TOL
    lab, _n = ndimage.label(same)
    comp = lab == lab[(y0 + y1) // 2, (x0 + x1) // 2]

    ys, xs = np.nonzero(comp)
    return dict(left=int(xs.min()), top=int(ys.min()),
                right=int(xs.max()), bottom=int(ys.max()))


def build(path, panel, scrim, built_dir):
    im = Image.open(path).convert('RGB')
    w, h = im.size

    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [panel['left'] + 6, panel['top'] + 6, panel['right'] - 6, panel['bottom'] - 6],
        radius=RADIUS, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(FEATHER))

    a = np.asarray(im, dtype=np.float32)
    navy = np.median(a[np.asarray(mask) > 200], axis=0) if (np.asarray(mask) > 200).any() \
        else np.array([16., 15., 27.])
    m = (np.asarray(mask, dtype=np.float32) / 255.0)[..., None] * scrim
    out = Image.fromarray((a * (1 - m) + navy * m).astype(np.uint8))

    os.makedirs(built_dir, exist_ok=True)
    dest = os.path.join(built_dir, os.path.splitext(os.path.basename(path))[0] + '.png')
    out.save(dest)

    t = dict(left=panel['left'] + TEXT_INSET, top=panel['top'] + TEXT_INSET,
             right=panel['right'] - TEXT_INSET, bottom=panel['bottom'] - TEXT_INSET)
    return dest, navy, dict(
        left=t['left'] / w, right=(w - t['right']) / w,
        top=t['top'] / h, bottom=(h - t['bottom']) / h)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--dir', required=True, metavar='PATH',
                    help='directory of source images; frames.lua is written here')
    ap.add_argument('--scrim', type=float, default=0.74,
                    help='0 = leave art untouched, 1 = erase figures inside the panel')
    args = ap.parse_args()

    src_dir = os.path.expanduser(args.dir)
    built_dir = os.path.join(src_dir, 'built')
    panels_json = os.path.join(src_dir, 'panels.json')
    frames_lua = os.path.join(src_dir, 'frames.lua')

    os.makedirs(src_dir, exist_ok=True)
    overrides = {}
    if os.path.exists(panels_json):
        with open(panels_json) as fh:
            overrides = json.load(fh)

    images = sorted(f for f in os.listdir(src_dir)
                    if f.lower().endswith(EXTS) and not f.startswith('.'))
    if not images:
        sys.exit('no images in %s -- drop some in and re-run' % src_dir)

    entries = []
    for name in images:
        path = os.path.join(src_dir, name)
        im = Image.open(path)
        w, h = im.size
        # Animated backgrounds animate, but only frame 1 is measured for geometry.
        animated = getattr(im, 'n_frames', 1) > 1

        if name in overrides:
            panel, how = overrides[name], 'panels.json'
        else:
            panel, how = detect_panel(im), 'detected'

        area = ((panel['right'] - panel['left']) * (panel['bottom'] - panel['top'])) / (w * h)
        if animated:
            # Scrimming an animation would flatten it to one frame; use it as-is.
            dest = path
            t = dict(left=panel['left'] + TEXT_INSET, top=panel['top'] + TEXT_INSET,
                     right=panel['right'] - TEXT_INSET, bottom=panel['bottom'] - TEXT_INSET)
            frac = dict(left=t['left'] / w, right=(w - t['right']) / w,
                        top=t['top'] / h, bottom=(h - t['bottom']) / h)
            note = 'animated, not scrimmed'
        else:
            dest, _navy, frac = build(path, panel, args.scrim, built_dir)
            note = ''

        flag = '  <-- panel looks too small, check panels.json' if area < 0.12 else ''
        print('%-34s %4dx%-4d panel %d,%d..%d,%d  (%s, %d%% of image) %s%s'
              % (name, w, h, panel['left'], panel['top'], panel['right'], panel['bottom'],
                 how, round(area * 100), note, flag))
        entries.append((name, dest, frac))

    with open(frames_lua, 'w') as f:
        f.write('-- generated by build-frames.py; edit panels.json to correct geometry\n')
        f.write('return {\n')
        for name, dest, fr in entries:
            # JSON string escaping is a safe subset of Lua's.
            f.write('  { name = %s, path = %s,\n' % (json.dumps(name), json.dumps(dest)))
            f.write('    panel = { left = %.5f, right = %.5f, top = %.5f, bottom = %.5f } },\n'
                    % (fr['left'], fr['right'], fr['top'], fr['bottom']))
        f.write('}\n')
    print('\nwrote %s (%d frame%s).\n  thalamus console --frames %s     # F12 toggles, F9 cycles'
          % (frames_lua, len(entries), '' if len(entries) == 1 else 's', frames_lua))


if __name__ == '__main__':
    main()
