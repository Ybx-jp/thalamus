"""An empty package. It carries no edge and must still count as an element.

The import channel's element predicate is *existence under a declared root*, and this
file is the witness for it: nothing imports it, it imports nothing, and `_collect_modules`
enters it anyway. The route channel uses a different predicate — see `web/sw.js` — and
the disagreement between the two is what this fixture holds still.

The roots here are `code/` and `web/`, not `src/`, because `qe`'s write boundary denies
`*/src/*` and a fixture tree is not an exception it should be arguing for.
"""
