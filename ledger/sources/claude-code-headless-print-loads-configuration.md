### Start faster with bare mode

Add `--bare` to reduce startup time by skipping auto-discovery of hooks, skills, custom commands, [subagents](/docs/en/sub-agents), installed plugins, MCP servers, auto memory, and CLAUDE.md. Without it, `claude -p` loads the same [context](/docs/en/how-claude-code-works#the-context-window) an interactive session would, including anything configured in the working directory or `~/.claude`.

Without `--bare`, a `-p` session runs the hooks in a project's `.claude/settings.json` and connects the servers in its `.mcp.json`, even in a folder you've never trusted. A `-p` session shows no workspace trust dialog and no per-server approval prompt. [What runs before you trust a folder](/docs/en/permissions#what-runs-before-you-trust-a-folder) covers each kind of repository content under `-p` and how to keep it out.
