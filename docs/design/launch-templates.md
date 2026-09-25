# Launch templates

**Status: design, not built.** Grounded in architect consultations `594ee0cda7f647d0`
and `157b366382794c40`, 2026-09-24.

A **launch template** is one operator-named bundle that picks a preset for several
dimensions at once (cost, budget, and the settings that follow them), chosen on the
command line when a session starts:

```
thalamus pin <scope> --template <name>
thalamus spawn <scope> --template <name>
```

and from the console's spawn. It changes that one session without editing the
expert's manifest. Dimensions and presets are described in
[`concepts.md`](../concepts.md); every setting a template could cover, and what each
harness does with it, is in [`settings-table.md`](../../settings-table.md).

## Where a template is applied

Every launch path ends in one function, `launcher.launch_argv` (`launcher.py:487`):

- `thalamus pin <scope>` → `pin.launch` (`pin.py:1332`) → `_session_argv` (`pin.py:1069`)
- `thalamus spawn <scope>` → `pin.spawn` (`pin.py:1360`), which sets `-e THALAMUS_SCOPE`
- `thalamus roster` → `pin.roster` (`pin.py:1420`)
- Console `/api/spawn` (`server.py:2280`); `/api/recycle` (`server.py:2464`) re-runs the stored argv
- `quick.fork_argv` (`quick.py:373`); `thalamus delegate` (`delegate.py:113`)

`_session_argv` and `spawn` regenerate the scope's Claude agent file and codex profile
on **every** launch (`pin.py:1094`, `:1101`, `:1387`). The write is a plain
`write_text` to one shared path per scope, not temp-and-rename (`pin.py:707-724`).

## What a template can cover today

- **Ready now** — already per scope, already read by code: cost, budget, write
  boundary, capability boundary, scope MCP servers, scope skills (Claude).
- **Global today, must become per scope first**: permission posture, extraction model.
- **No switch exists, must be built first**: memory writing on/off, start context /
  conditioning / reflex on/off. The only off switch is `THALAMUS_SANDBOX`, which turns
  off every hook, guards included.
- **Not a template setting**: path ownership (an oracle boundary, not a preference),
  charter (prose), `tier`/`claim_kinds`/`allowlist` (ingest curation, not session
  behaviour).

## The carrier

### The rules

1. **A template file** is `<config_root>/templates/<name>.yaml`: a map from dimension
   to preset name. It names only the dimensions it sets.
2. **Composition: per-dimension replacement.** For a dimension the template names, its
   preset replaces the manifest's selection for that dimension entirely. For a dimension
   it omits, the manifest's selection (or `inherit`) stands. No merging of keys inside
   one dimension, and one dimension never sets another's value.
3. **One place decides.** `ExpertManifest.preset(dimension)` in `contract/manifest.py`
   takes the template's map and applies rule 2. `pin.py`, `budget.py`, `role-guard.sh`
   and the MCP server all resolve through it, so they cannot disagree. It ships in the
   same change as its first caller (`pin` reading `--template`), or `arch dead` fails.
4. **Resolved once, at launch.** Which template governs a session is fixed when the
   session starts and never re-decided mid-session, the same way its scope is. Hooks
   may keep re-reading preset files on each call (as `budget.limits` does), but the
   template name they apply does not change.
5. **The bare per-scope files keep meaning "manifest default".** A templated launch
   writes its own files and never overwrites `thalamus-<scope>.md` or the scope's
   codex profile.
6. **An expert always takes its own manifest unless its own launch names a template.**
   A template applies only to the session launched with `--template`. An expert that
   session spawns as a subagent resolves from its own manifest. The parent's
   session-total token cap still counts the subagent's spend, because that cap is the
   parent's budget, not the subagent's setting (`budget.py`, A0186).

### How it reaches each consumer

| Consumer | Carrier |
|---|---|
| Launch argv | `launch_argv` resolves the template and adds `THALAMUS_TEMPLATE=<name>` to the `env K=V` prefix that already carries `THALAMUS_SCOPE` and the output caps (`launcher.py:531-541`). The prefix is on the argv, so it survives `respawn-window` and `/api/recycle`. |
| Claude agent file | A templated definition named `thalamus-<scope>--<template>`, selected with `--agent`. It cannot be written into `.claude/agents` or `~/.claude/agents`: Cursor reads those folders as subagents and identifies a file by its frontmatter `name`<!-- (A0196, cites-as-live) -->, and Claude Code loads the same folders as subagents (which `write_all_agents` relies on). Either way the file becomes a subagent any session in the workspace can call, which rule 6 forbids, and a file reusing the name `thalamus-<scope>` would replace the default for Cursor. Where the definition lives instead is open (below). |
| Codex profile | No per-template file. The launch keeps `--profile thalamus-<scope>` and adds `-c` overrides for the keys the template changes (`model`, `model_reasoning_effort`, `tool_output_token_limit`); a `-c` value outranks the profile's<!-- (A0195, cites-as-live) -->. |
| Hooks (`budget.sh`, `role-guard.sh`, …) | Read `THALAMUS_TEMPLATE` from the environment and pass it to `ExpertManifest.preset` — the pattern `THALAMUS_MAX_*` already uses to override the manifest. The argv prefix reaches the hooks on Claude Code<!-- (A0192, cites-as-live) --> and on codex<!-- (A0020, cites-as-live) -->. |
| Subagents | Nothing to carry: an expert spawned as a subagent uses its own manifest (rule 6). Its hooks inherit `THALAMUS_TEMPLATE` from the parent, and on Claude Code `CLAUDE_CODE_AGENT=thalamus-<scope>--<template>` with it, since a hook inside a subagent runs with the session's environment<!-- (A0201, cites-as-live) -->. So a hook that sees an `agent_id` in its payload ignores both. The payload carries one inside a subagent on Claude Code (A0174)<!-- (A0192, cites-as-live) --> and on codex, where the PreToolUse field is undocumented and measured on 0.154.0<!-- (A0194, cites-as-live) -->. |
| MCP server | Reads `THALAMUS_TEMPLATE` at start, next to where it resolves the scope (`mcp_server.py:75`), if it needs it. On Claude Code every stdio server inherits the prefix, including one declared in a subagent's frontmatter<!-- (A0192, cites-as-live) -->, so a server armed for a subagent expert starts with the parent's template in its environment and, unlike a hook, receives no payload naming the subagent. On codex a stdio server gets only an allowlist plus the variables its `env_vars` names<!-- (A0193, cites-as-live) -->; the launch has to add `-c 'mcp_servers.thalamus.env_vars=[…]'`, and today `THALAMUS_SCOPE` does not reach it either (#289). |

### Permission posture

Posture is the one setting with an audit trail: widening expires after 24 hours and every
change is written to `policy.jsonl`. A template must not become a second way to widen it.
When posture becomes a template dimension, a template may only narrow posture relative
to the global setting; widening still goes through `launch_policy.select()` and its
expiry and ledger.

### Per harness

Which dimensions each harness can carry is in [`settings-table.md`](../../settings-table.md).
A template naming a dimension a harness cannot carry should say so at launch rather
than launch silently without it.

## Decided by the operator (2026-09-24)

- Build: choose a template on the command line; one template spans dimensions.
- Not requested: default → user → project → session layers.
- Presets are the operator's, named, in the config root; the product ships no fixed
  list.
- Experts always take their manifest unless the launch adds CLI arguments; a template
  does not pass to subagents.
- Templates live in `<config_root>/templates/<name>.yaml`, beside `presets/`, and are
  managed by `thalamus template list | set | remove`, the same shape as
  `thalamus preset`.

## Measured (2026-09-25)

Claude Code 2.1.282, codex-cli 0.154.0, cursor-agent 2026.08.11. Each probe ran against
a control differing in the one variable; the table above states the results.

1. **The argv `env` prefix reaches hooks everywhere and MCP servers on Claude Code
   only.** Claude Code: hooks and every stdio MCP server, subagent-declared ones
   included.<!-- (A0192, cites-as-live) -->
   codex: hooks yes; a stdio MCP server only through `env_vars`.<!-- (A0193, cites-as-live) -->
2. **Subagent hooks inherit the parent's environment and can tell they are in a
   subagent**, by `agent_id`, on both harnesses.<!-- (A0194, cites-as-live) -->
3. **`-c` overrides replace per-template codex profile files** for the scalar keys a
   template changes.<!-- (A0195, cites-as-live) -->
   Per-template `[mcp_servers.*]` tables through `-c` were not measured.
4. **Cursor knows a subagent by its frontmatter `name`**, and reads `.claude/agents`, so
   a templated file there is live to it under whatever name it
   carries.<!-- (A0196, cites-as-live) -->
5. **Concurrent same-scope launches are rare today.** In the pin ledger from 2026-08-09
   to 2026-09-25, 142 pinned-window sessions started on expert scopes; one pair of the
   same scope started within 10 seconds of each other, from a probe in a scratch
   directory. The six pairs of any two expert scopes within 2 seconds were room
   bring-ups. `spawn` rewrites every scope's agent file (`write_all_agents`), so a room
   brought up by `spawn` rewrites files other members are starting from. Today those
   bytes are identical, and the hazard is only the moment between truncate and write.
   A template would make them differ, which is why rule 5 keeps templated launches off
   the shared files. codex sessions are not in this count: their `SessionStart` fires at
   the first submitted turn, not at launch.

## Open

- **Where the templated Claude definition lives.** It needs a location `--agent`
  resolves and no harness scans for subagents (item 4). `claude --agents <json>`
  defines an agent for one session without a file. Whether it carries `mcpServers`
  and survives `respawn-window` has not been measured, and a charter on the argv would
  sit in `ps` and in tmux's `pane_start_command`, which `panes.py` parses.
- **Scope resolution from a templated agent name.** `pin.resolve_pin` takes the scope
  from `CLAUDE_CODE_AGENT` only when the name after `thalamus-` is a manifest.
  `thalamus-<scope>--<template>` is not one, so resolution falls back to
  `THALAMUS_SCOPE`, and a Claude launch's argv does not carry that
  (`persona_flag_carries_scope`). The resolver, and `resolve-scope.sh` beside it, has
  to strip the `--<template>` suffix.

## Prior work

- **Resolve once into an immutable, uniquely named artifact.** Nix builds each
  configuration into a hash-named path so variants coexist, and switches between
  numbered generations by atomic rename (`scope:architect:claim:3c249b14e7c7db70`,
  `scope:architect:claim:d330292b3e0c8e73`, from Dolstra et al., *Nix: A Safe and
  Policy-Free System for Software Deployment*, LISA 2004). Rules 4 and 5 and the
  per-template filenames are an instantiation of that: a templated launch gets its own
  artifact and never mutates the shared default one.
- **Configuration fixed for the life of a process.** POSIX `sysconf` values "shall not
  change within the lifetime of the process", so one binary can run under differing
  configurations (`scope:architect:claim:97e5d66eb5f1f12b`,
  `scope:architect:claim:975c6317b9bf3cbe`). Rule 4 converges on it.
- **One choice per dimension, never set by another.** Kconfig `choice` with a default,
  and not Kconfig `select`, which sets a value without checking that value's own
  dependencies (architect consultation `157b366382794c40`). Rule 2 follows it.
- **Precedence stacks** (NixOS `mkDefault` / `mkForce`) are the model for layered
  settings and are not used, since layers were not requested
  (`scope:architect:claim:a301c8f6cc4f4a1b`).
- **Not grounded:** systemd drop-ins / `EnvironmentFile`, twelve-factor config, and
  container image config versus runtime environment. The architect scope's corpus holds
  none of them, and their hosts (`freedesktop.org`, `12factor.net`) are not on its
  allowlist. Adding them is a curation decision in `experts/architect.yaml`.

Sources: architect consultation `594ee0cda7f647d0` (this design), `157b366382794c40`
(feature dimensions).
