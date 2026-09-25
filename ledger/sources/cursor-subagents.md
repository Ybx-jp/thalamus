### File locations

| Type | Location | Scope |
|---|---|---|
| Project subagents | .cursor/agents/ | Current project only |
| | .claude/agents/ | Current project only (Claude compatibility) |
| | .codex/agents/ | Current project only (Codex compatibility) |
| User subagents | ~/.cursor/agents/ | All projects for current user |
| | ~/.claude/agents/ | All projects for current user (Claude compatibility) |
| | ~/.codex/agents/ | All projects for current user (Codex compatibility) |

Project subagents take precedence when names conflict. When multiple locations contain subagents with the same name, .cursor/ takes precedence over .claude/ or .codex/.

### Configuration fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| name | string | No | Derived from filename | Display name and identifier. Use lowercase letters and hyphens. |
