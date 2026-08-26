"""Where this checkout is.

The repo root is a fact about the tree the package was loaded from: no config, no
manifest, no I/O, nothing above it in the import graph. It sits in the vocabulary
layer because the modules that need it sit in three different ones —
`contract/manifest.py` anchors `config/` to it, `harness/pin.py` opens a pinned
session in it, and `substrate/writer.py` names it in the graph-down message — and a
home inside any one of those layers makes the other two read across a boundary. Held
in one place, the arithmetic is also written once rather than per caller.

This project runs from its checkout (`uv run`), so the tree the file sits in is the
project a pinned session should open in. `parents[3]` counts up from
`src/thalamus/contract/paths.py`; a module at a different depth cannot reuse that
expression and should import this name rather than write its own.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
