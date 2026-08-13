# 062 — The pin that a phone tap undoes

**Date:** 2026-08-12 · **Harness:** Cursor CLI `2026.08.11-e8db854` · **Verdict:** a
launcher, one silent unpin closed before it shipped, and a record for what "pinned"
covers

lab/061 closed the boundary gap and left the ceiling: `role-guard.sh` binds on Cursor,
but `pin.py` launches `claude` in both paths and the guard short-circuits on `main`, so
the boundary bound only where the operator exported `THALAMUS_SCOPE` by hand — three
sessions. This entry is the launcher, and the thing it nearly shipped without.

## The unpin

`tmux new-window -e VAR=x` sets the initial process environment and **is not stored in
the session environment**. `respawn-window` — exactly what the console's restart button
runs — re-executes the window's argv with those variables gone. Claude Code never felt
it because `--agent thalamus-<scope>` rides the argv and re-selects the scope. Cursor
has no `--agent`, so a Cursor window pinned only by `-e` comes back inheriting the
session env's `THALAMUS_SCOPE=main`.

Measured, both arms, in a throwaway session whose session env holds
`THALAMUS_SCOPE=main` as the roster's does:

| launch argv | before recycle | after recycle |
|---|---|---|
| `env THALAMUS_SCOPE=qe agent --trust` | `qe` | **`qe`** |
| `agent --trust` (window `-e` only) | `qe` | **`main`** |

`role-guard.sh` tests the scope and exits before it loads any manifest when the answer
is `main`. So the failure is a **bounded window becoming an unbounded one, from a phone
tap, with no row anywhere recording it** — and the fix is the shape `pin._with_room`
already uses for rooms, for the same measured reason.

Two experts found this independently within the same hour, from different directions:
one read `_with_room`'s own docstring, which had recorded the tmux behaviour all along;
the other reproduced it live. It had been written down and was load-bearing for a
harness that did not exist yet when it was written.

## What a Cursor pin is

`--agent` fuses four things, and the fusion is why nobody noticed they were separable
until a harness arrived carrying two of them:

| component | claude | cursor |
|---|---|---|
| routing tag | ✓ | ✓ (environment only — no picker to disagree with) |
| boundary | ✓ | ✓ (NATIVE, via the vendor's settings.json translation) |
| persona | ✓ | **absent** |
| per-scope MCP arming | ✓ | **native** — global `~/.cursor/mcp.json`, already written by `init` |
| recycle survival | ✓ (`--agent` rides the argv) | ✓ (the `env` prefix does) |

**Persona has no carrier and will not get one.** The only flag that could replace a
system prompt is `--system-prompt <file>` — hidden from `--help` and marked
*"Anysphere/OpenAI team only"* in the vendor's own bundle. It was never unmeasured; the
grep was free and nobody had run it. So a pinned Cursor session **routes and is bounded
and does not think like the expert**, and `contract/pinning.py` says that in a row
rather than in prose.

## No permission mode, deliberately

Claude Code pins launch under `--permission-mode auto`, chosen so a member never sits
at a prompt. Cursor has nothing that keeps that property: `--auto-review` is the nearest
architecture and *prompts on whatever its classifier will not auto-run*, and
`--force`/`--yolo` ("Run Everything") is strictly more permissive than `auto` rather
than equivalent to it. Passing neither leaves a Cursor window on the operator's own
config, where it can stop at a prompt — acceptable only because rooms have no Cursor
referent, so nothing dispatches into it and no `waiting` status is being violated.

`--trust` is passed, because without it a fresh workspace parks on a hotkey-driven
modal where a stray literal `q` was measured killing the process outright.

The config file was refused as the mechanism, and not for being global: a session can
rewrite it mid-run (`/config`, `/run-everything`, `/sandbox` are live slash commands),
so policy expressed there is a preference, not a constraint.

## No pane claim

The pane claim joins a window to its transcript for the console's read view. On Claude
Code it is gated on `CLAUDE_CODE_ENTRYPOINT=cli`, a gate that exists because an
unconditional claim once hijacked a live window's console view for five hours.

Cursor offers no discriminator: **no environment marker of its own**, and a
`sessionStart` payload identical between `agent -p` and an interactive session
(`is_background_agent: false`, `composer_mode: null` in both). A cwd-based substitute —
"claim only if the cwd is not an extraction sandbox" — was proposed and refused on the
sharper argument that the incident's own reproduction was a headless run in the *repo*
cwd, so the gate would screen a population the incident was not drawn from. This
settles the open question that had been waiting on exactly this probe, in the negative:
no claim, and the cost is that a Cursor window has no read view.

## Corrections to lab/061, from the same measurements

- **`~/.claude/agents/` is not read by Cursor.** `computeAgentsDirs()` is
  workspace-rooted (`.cursor/agents` plus, under third-party extensibility,
  `.claude/agents`). The home directory is not in it.
- **`~/.claude/skills/` *is* read, at user scope** — so every skill `thalamus init`
  links for Claude Code is offered to every Cursor session on the box. Eleven on this
  machine, six of them Thalamus's. That belongs to the deployment gates.
- **A Cursor session in this checkout can spawn the derived `thalamus-<scope>`
  subagents**, so lab/061's "never a differently-pinned expert" was false. The parser
  honours `name`, `description`, `tools`, `model`, `prompt`, `permissionMode` and drops
  `mcpServers`. Whether such a subagent reaches the Thalamus tools through the global
  config, and what Cursor's `tools:` list does with `mcp__thalamus__`-namespaced names,
  is unmeasured.

## Residuals

- **The population is still small.** The launcher exists; the enforcement claim over it
  is one verified block plus a recycle test. A before/after that says the launcher
  *changed* enforcement needs a denominator, and that belongs to eval-methodology.
- **`SPAWN_SETTLE_S = 1.2` under-covers `agent`**, whose death modes (trust, auth)
  resolve after network round-trips — so `spawn` can still report success for a window
  that dies a second later, which is the shape of the failure that once took the whole
  roster down.
- **Cursor has no alternate screen** (`alternate_on=0`), so `capture-pane` returns
  stale frames rather than a viewport. For the console that is misinformation, not
  merely incompleteness, and the read view is absent anyway.
- **`/exit` and `/quit` both exist** and killed an idle trusted `agent` pane in under a
  second, so the console's recycle verb carries — but a keystroke that leaks into the
  composer turns `/exit` into a prompt, which parks at a permission prompt and rides
  out the full 240-second grace to a force kill, skipping `sessionEnd` and leaving the
  session recoverable only as an unresolved scope.
