"""The eval loop — measuring what memory is worth (docs/04).

Layer 1 lives here: the PostToolUse tap records every memory-tool call verbatim,
`traces` types those lines, `attribution` judges used-vs-ignored against the retained
transcript, `sync` lands the result in the graph as Trace nodes, and `report` reads it
back out. The trace store is the property graph itself — the loop grades the same
substrate it reads, no side database.
"""
