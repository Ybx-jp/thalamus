### PostToolBatch decision control

`PostToolBatch` hooks can inject context for Claude. In addition to the [JSON output fields](#json-output) available to all hooks, your hook script can return these event-specific fields:

| `additionalContext` | Context string injected once before the next model call. See [Add context for Claude](#add-context-for-claude) for delivery details, what to put in it, and how resumed sessions handle past values |
