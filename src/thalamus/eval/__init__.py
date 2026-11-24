"""The eval loop — measuring what memory is worth.

Core's half of layer 1 lives here: the PostToolUse tap records every memory-tool call
verbatim, `traces` types those lines, `attribution` judges used-vs-ignored against the
retained transcript, and `sync` lands the result in the graph as Trace nodes. The trace
store is the property graph itself — the loop grades the same substrate it reads, no
side database. The reports that read it back out are the thalamus-measure plugin's.
"""
