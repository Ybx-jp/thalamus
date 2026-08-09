"""The graph viewer: the operator's view over the whole memory graph.

FastAPI + Cytoscape, served by `thalamus visualize`. This is a *window onto* what
docs/03-master-plane.md calls the master plane — the main session scope — not the
master plane itself. Note it currently queries the substrate directly, bypassing the
contract — see docs/09-schema-and-federation.md, gap G4.

Not to be confused with `thalamus.console`, the tmux control surface for the pinned
roster (docs/console.md).
"""
