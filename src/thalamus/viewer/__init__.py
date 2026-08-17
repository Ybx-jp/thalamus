"""The graph viewer: the operator's view over the whole memory graph.

FastAPI + Cytoscape, served by `thalamus visualize`. This is a *window onto* the master
plane — the main session scope — not the master plane itself. Note it currently queries
the substrate directly, bypassing the contract.

Not to be confused with `thalamus.console`, the tmux control surface for the pinned
roster.
"""
