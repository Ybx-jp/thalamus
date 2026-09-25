# Session settings by harness

Every setting that changes how a Thalamus session runs: where it is set, whether one
expert scope can differ from another, and what each harness does with it. As of
`master` 4a42972 (2026-09-24); line numbers drift, the names do not.

**Enforced** means the harness itself acts on the setting (a launch flag, a field it
reads at start, or a hook that denies the call). **Prose** means the model is told and
nothing stops it. **Absent** means there is nothing on that harness to carry it.
**Unknown** means nobody has measured it — not a synonym for absent
(`contract/boundaries.py`).

## The table

| Setting | Controls | Set in | Per scope? | Claude Code | codex | Cursor |
|---|---|---|---|---|---|---|
| Cost preset | Model class and effort | Manifest `cost:` → `<config_root>/presets/cost.yaml` | Yes | Enforced: agent frontmatter `model:` / `effort:` (`pin.py:671`) | Enforced: profile `model`, `model_reasoning_effort` (`pin.py:838`) | Not projected (#267) |
| Budget preset | Caps on turns and tool calls per prompt, tokens per session and per subagent, tool-output size | Manifest `budget:` → `presets/budget.yaml`; `THALAMUS_MAX_*` overrides | Yes | Enforced: `budget.sh` on PreToolUse + PostToolBatch; output caps as env vars on the launch command (`launcher.py:531`) | Enforced on PreToolUse; no turn cap, subagent tokens not counted; output cap as `tool_output_token_limit` in the profile | Not counted: the payload has no prompt id |
| Write boundary | Paths the scope may not write (`deny_globs`, `allow_globs`) | Manifest `write_boundary` | Yes | Enforced: `role-guard.sh` on Edit / Write / NotebookEdit | Enforced: `role-guard.sh` on `apply_patch` | Enforced: Cursor runs the Claude Code settings file's hooks (native) |
| Path ownership | Paths only one scope may write, `main` included (today `tests/qe/` → `qe`) | Hardcoded `PATH_OWNERSHIP` (`contract/ownership.py:46`) | Fixed | Enforced, fails closed | Enforced, fails closed | Enforced, through the Claude Code settings file |
| Capability boundary | Tools and skills the scope may not use (`deny_tools`, `deny_skills`, `allow_tools`) | Manifest `capability_boundary`; default `ROSTER_CAPABILITY_DEFAULT` | Yes | Enforced: Skill, Artifact, MCP tools | MCP tools enforced; other tools and skills unknown | Tools absent; skills unknown |
| Scope skills | Skills only this scope has | `config/skills/<scope>/<name>/SKILL.md` | Yes | Listed into the session-start context (`resolve-scope.sh:312`) — the session is told where they are | Absent (#269) | Absent (#269) |
| Scope MCP servers | Extra tools for the scope | `config/mcp/<scope>.json` | Yes | Enforced: agent frontmatter `mcpServers` | Enforced: profile `[mcp_servers.*]` | Global `~/.cursor/mcp.json` only |
| Permission posture | How much the harness asks before acting | Console gear panel → `~/.thalamus/launch/policy.json`; widening expires after 24 h; every change logged to `policy.jsonl` | **No — one per harness** | Enforced: `--permission-mode` | Enforced: `--sandbox` + `--ask-for-approval` | Enforced: `--auto-review` / `--force` |
| Extraction model | Which CLI and model distil sessions and run ingest | Console → `~/.thalamus/extractor/policy.json` | **No — global** | — | — | — |
| Memory writing | Distilling the session into memory at its end | Always wired (`session-end.sh`) | **No switch** | SessionEnd | SessionEnd | sessionEnd (`session-end.sh`, `distill.sh`) |
| Start context and conditioning | Open threads, the timestamp, nudges injected into the session | Always wired | **No switch** | Prose: SessionStart, UserPromptSubmit | Prose: SessionStart, UserPromptSubmit | Prose: sessionStart; the rest queued and delivered on postToolUse (`inject.sh`) |
| Memory reflex | Recalled memory injected after a tool result | Always wired | **No switch** | Prose: PostToolUse / PostToolUseFailure on Bash | Absent | Absent |
| Memory and graph guards | No mid-session memory writes, no raw graph access, Gremlin checks | Always wired | **No switch** | Enforced on Bash | Enforced on Bash | Enforced on beforeShellExecution |
| Room | Isolation between peer sessions in one room | `--room` / `THALAMUS_ROOM` at launch | Per launch | Enforced: `room-guard.sh` on SendMessage, `room-command-guard.sh` on Bash | No codex rooms: `pin` refuses to open one; the command guard is wired | Enforced on shell commands (`room-command-guard.sh`); Cursor has no messaging tool |
| `THALAMUS_SANDBOX` | Turns off every Thalamus hook | Set by the parent process (`agents.sandbox_env`) | Per process | Enforced | Enforced | Enforced |
| Charter | The expert's persona text | Manifest `name`, `domain` | Yes | Prose: agent file body | Prose: profile `developer_instructions` | Absent |
| `executor` | Sends the scope to `thalamus delegate` instead of a pinned session | Manifest | Yes | — (refuses to pin) | — | — |
| `tier` | Origin tier of what the scope's ingest writes | Manifest | Yes | Read by nothing; ingest always writes tier 2 (#283) | — | — |
| `claim_kinds`, `allowlist` | What the scope's ingest may write, and from where | Manifest | Yes | Enforced at ingest, not in sessions | — | — |

## What stands out

- **Posture and the extraction model are global.** Every scope on a harness launches
  with the same permission posture.
- **Memory writing, start context, conditioning and the reflex have no switch at all.**
  The only way to turn any of them off is `THALAMUS_SANDBOX`, which turns off every
  hook, guards included.
- **codex and Cursor trail Claude Code**: no reflex on either; scope skills and part
  of the capability boundary missing on both; cost and budget missing on Cursor.

## How a session knows its scope

`THALAMUS_SCOPE` on the launch environment, `CLAUDE_CODE_AGENT`, or the hook payload's
`agent_type` (`resolve-scope.sh:191-234`). The memory server resolves it once at start
(`mcp_server.py:75`).
