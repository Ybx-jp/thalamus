# The Limit Lab

One-page entries, each in the same shape: **what broke → why (root cause in harness
terms) → workaround or wall.**

Starts at M2, when the eval loop can actually measure the effect of a break. Entries
that end in *"wall"* are as valuable as ones that end in *"workaround"* — a
documented, measured limit of the harness is precisely the artifact this lab exists
to produce. See [docs/07-harness-integration.md](../docs/07-harness-integration.md).

Also the home for negative results from the eval loop
([docs/04](../docs/04-eval-loop.md)): *"the literature expert's retrievals were
ignored 70% of the time until X"* is worth more than a clean win.

## Entries

| # | Entry | Ends in |
|---|---|---|
| [001](001-sessionend-hook-snapshot.md) | The session that installs a SessionEnd hook is never distilled by it | workaround |
| [002](002-truncated-source-attribution.md) | Attribution against a truncated Source snapshot silently under-counts | workaround |
| [003](003-the-process-is-the-pin.md) | The process boundary that blocked pinning is the pinning mechanism | workaround |
