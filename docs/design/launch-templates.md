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
| Claude agent file | Written as `thalamus-<scope>--<template>.md`, temp-and-rename; the pin launches with `--agent thalamus-<scope>--<template>`. |
| Codex profile | Written as `thalamus-<scope>--<template>.config.toml` and launched with `--profile`, unless `-c` overrides can carry the keys (to measure). |
| Hooks (`budget.sh`, `role-guard.sh`, …) | Read `THALAMUS_TEMPLATE` from the environment and pass it to `ExpertManifest.preset` — the pattern `THALAMUS_MAX_*` already uses to override the manifest. |
| Subagents | Nothing to carry: an expert spawned as a subagent uses its own manifest (rule 6). Its hooks run under the parent's process and inherit `THALAMUS_TEMPLATE`, so a hook fired inside a subagent — the payload carries an `agent_id` (A0174) — ignores the variable. |
| MCP server | Reads `THALAMUS_TEMPLATE` at start, next to where it resolves the scope (`mcp_server.py:75`), if it needs it. |

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

## Open decisions

- **Template file location and CLI verbs.** `templates/<name>.yaml` beside `presets/`,
  managed by `thalamus template list|set|remove` like `thalamus preset`.

## Measure before building

1. Whether hook subprocesses and MCP servers see a variable added to the argv `env`
   prefix. `THALAMUS_MAX_*` and `THALAMUS_SCOPE` show this works for hooks on Claude
   Code; the MCP server and codex are not measured.
2. Whether a subagent's hooks inherit the parent's environment (they run under the
   same harness process on Claude Code), and whether a codex subagent's payload carries
   an `agent_id` the hook can use to ignore the inherited template.
3. Whether codex `-c key=value` overrides can replace per-template profile files.
4. Whether Cursor finds a subagent file by filename, so a `--<template>` filename is
   visible to it.
5. How often concurrent same-scope launches overwrite the shared agent file today (the
   write is not atomic: `pin.py:707-724`).

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
