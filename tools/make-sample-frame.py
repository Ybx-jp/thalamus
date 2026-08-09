#!/usr/bin/env python3
"""Generate a synthetic frame image, so the theme can be exercised with no artwork.

The frame pipeline is easy to describe and annoying to try: it needs a picture with a
sign in it before anything is visible, and "find a suitable image" is a bad first step
for someone evaluating whether the feature works at all. This draws one — a flat panel
in a gradient scene, with a shape deliberately overlapping the panel edge so the
scrim in build-frames.py has something to do.

    ./tools/make-sample-frame.py --out ~/frames    # → ~/frames/sample-frame.png
    ./tools/build-frames.py --dir ~/frames         # detect, scrim, write frames.lua

Needs pillow only.
"""
import argparse
import os

from PIL import Image, ImageDraw

# The panel is the thing the detector must find: one flat, dark, connected region.
# Everything else in the image only exists to prove it is found rather than assumed.
PANEL_RGB = (14, 17, 22)
PANEL_INSET = 0.18          # fraction of each edge the panel sits in from


def scene(w, h):
    """A vertical gradient — cheap, and gives the detector real 'art' to reject."""
    im = Image.new('RGB', (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / max(h - 1, 1)
        d.line([(0, y), (w, y)],
               fill=(int(24 + 96 * t), int(30 + 52 * t), int(58 + 40 * t)))
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True, metavar='PATH',
                    help='directory to write the image into (feed the same one to '
                         'build-frames.py --dir)')
    ap.add_argument('--size', default='1600x1000', help='WxH, default 1600x1000')
    ap.add_argument('--name', default='sample-frame.png')
    args = ap.parse_args()

    w, h = (int(v) for v in args.size.lower().split('x'))
    im = scene(w, h)
    d = ImageDraw.Draw(im)

    x0, y0 = int(w * PANEL_INSET), int(h * PANEL_INSET)
    x1, y1 = w - x0, h - y0

    # A blob crossing the panel boundary. Without something intruding, a scrim run
    # looks like a no-op and you can't tell the step happened.
    d.ellipse([x1 - int(w * 0.10), y0 - int(h * 0.09),
               x1 + int(w * 0.09), y0 + int(h * 0.12)], fill=(232, 196, 122))

    # Panel last, so it reads as a flat region the blob sits behind at the seam.
    d.rectangle([x0, y0, x1, y1], fill=PANEL_RGB)
    d.rectangle([x0, y0, x1, y1], outline=(92, 128, 160), width=3)

    out_dir = os.path.expanduser(args.out)
    os.makedirs(out_dir, exist_ok=True)
    dest = os.path.join(out_dir, args.name)
    im.save(dest)
    print(f'wrote {dest} ({w}x{h}, panel {x0},{y0}..{x1},{y1})')
    print(f'next: ./tools/build-frames.py --dir {out_dir}')


if __name__ == '__main__':
    main()
