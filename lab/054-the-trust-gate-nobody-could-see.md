# 054 — The trust gate nobody could see

**Date:** 2026-08-10 · **Harness:** Cursor CLI `2026.08.04-aaa8809`, authenticated,
Free tier · **Verdict:** workaround (one flag), plus a wall that stays

The first time Thalamus code ran inside a live Cursor. Everything about the Cursor
port until today was tested against payload shapes read from Cursor's published
docs — `tests/test_cursor_hooks.py` drives synthetic events, and every claim about
the CLI was doc-derived. This entry is what a live CLI said instead.

## What broke

`thalamus extract --harness cursor` failed on every session, having done no work:

```
✗ 4d7fc5d4  extraction failed: agent -p --model composer-2.5 exited 1
  (run `agent --list-models` for the accepted identifiers): ⚠ Workspace Trust Requi
```

Two defects in one line.

**The gate.** Cursor refuses to run non-interactively in a directory it has not
been told to trust. It exits 1 and prints a human-readable prompt *instead of* the
JSON envelope. Extraction runs in a fresh `mkdtemp` on every invocation — that is
the sandbox that keeps distillation from distilling itself — so the sandbox is
never a trusted workspace and never can become one. Cursor distillation was
therefore broken for every session that would ever run, on every machine, from the
moment it shipped.

**The misattributed hint.** `MODEL_HINT` was appended to every non-zero exit, so a
workspace-trust refusal advised running `agent --list-models`. It points the reader
at the one thing that was not wrong. Cursor also writes this class of refusal to
stdout rather than stderr, so the error had to fall back or report nothing at all.

## Why it was invisible

Nothing here needed a rare condition. It needed only that no one had run it.

- Extraction is spawned **detached from SessionEnd**, so the failure lands in a log
  nobody reads. This is the same shape that hid three lost sessions before an
  explicit `--session` that matches nothing was made to exit non-zero.
- The Cursor conformance tests drive **hook payloads**, not the CLI. They would
  have passed forever.
- `agents.py` had **no test file at all**, which is how its other declarations
  drifted too (below).

The root cause is one line of design. `AgentCLI.argv()` returned
`[binary, "-p", "--model", model, "--output-format", "json"]` for both CLIs — a
single shared invocation shape, justified by a real near-identity: both take `-p`,
`--model` and `--output-format json`, and both return an envelope carrying
`result`, `is_error` and `duration_ms` under those exact names. The near-identity
is genuine and it is what made the seam invisible. One side has a **precondition**
the other lacks, and a method returning one argv had nowhere to say so.

## Workaround

`headless_preconditions: tuple[str, ...]` on `AgentCLI`, `("--trust",)` for Cursor
and `()` for Claude Code — the empty tuple being a declaration that nothing is
needed, not a gap to fill later. `--trust` and not `--force`/`--yolo`: the refusal
is about the workspace, and the broader flags would additionally allow every tool
call, authority the extraction pass has no use for since it reads a transcript
handed to it on stdin and calls nothing.

Trust is granted per directory and persists — `--trust` writes
`~/.cursor/projects/<sanitized-cwd>/.workspace-trusted` with
`{"trustedAt", "workspacePath", "trustMethod": "cli-flag"}` — so the flag is paid
once per sandbox rather than per token.

After the fix, end to end on a live session: hooks fired → pin-ledger row written
with the correct cwd and scope → sessionEnd pointer logged → transcript found →
`+ 4d7fc5d4  User asked a one-line arithmetic question (2+2)`.

## What else the live CLI overturned

Five declarations were wrong, and each had been wrong in a way nothing could catch.

| Claim | Where | Live result |
|---|---|---|
| `composer-2.5` is **unverified**, Composer has no public model id | `agents.py` | **Confirmed**, and `composer-2.5-fast` exists — the declined variant is real |
| "Cursor's envelope carries **no cost or token fields**" | docs/07 | **False.** It carries `usage{inputTokens, outputTokens, cacheReadTokens, cacheWriteTokens}`. The gap is *pricing*, not instrumentation |
| "`--permission-mode` / `--dangerously-skip-permissions` have no confirmed Cursor equivalent" | `arm_blockers` | **False.** `--force`, `--yolo`, `--sandbox`, `--auto-review`, and a `permissions.allow/deny` block in `cli-config.json`. Bundled in one row with `--max-turns`, which *is* absent — so the row could never be retired |
| "**No timestamps and no cwd** on any row; both come from the hooks' own ledgers" | docs/07, `cursor_transcripts.py` | **Half false.** Cursor writes `<timestamp>` into the user query text, and `chats/<hash>/<id>/meta.json` carries `cwd`, `createdAtMs`, `updatedAtMs` |
| "Nothing spells `claude` inline any more" | docs/07:216 | **False.** `pin.py:463` and `:626`. The doc contradicted itself two paragraphs later |
| "Parity with HOOK_WIRING is 8 of 9 scripts" | `install.py:101` | **Stale.** 11 Claude, 9 Cursor, 7 shared. Three scripts joined the Claude list after the comment and nothing noticed |

Confirmed rather than overturned: **`tool_result` blocks are absent for every
tool.** A live tool-use probe recorded the `tool_use` block with its full `input`
and then jumped straight to the assistant's final text. The ingress floor's
reasoning stands exactly as docs/05 states it.

Also newly named: `{"type": "turn_ended", "status": "success"}` closes every turn
and carries no `role`, so it was counted as an unreadable record. Every real
session reported at least one — which is the signal a genuine format change has to
raise, so it was being spent on structure. Recognised and skipped now.

## The wall that stays

**Discovery is asymmetric, and the Cursor side is the fragile one.** Claude Code
discovers sessions by globbing the filesystem (`transcripts.discover()`); Cursor
discovers them by reading the sessionEnd **hook log**. So a Cursor session that ran
before the hooks were installed is undiscoverable, even though its transcript is
sitting at a perfectly globbable path:

```
~/.cursor/projects/<sanitized-cwd>/agent-transcripts/<session-id>/<session-id>.jsonl
```

There is no `thalamus bootstrap --harness cursor` for the same reason. Every Cursor
session predating install is currently unrecoverable by policy rather than by
format — which is the wrong reason for memory to be lost, and it bites hardest on
exactly the machine Thalamus arrives at late.

Two further capability facts, recorded because they constrain what an adapter may
assume:

- **`agent ls` is an Ink TUI** and crashes with `Raw mode is not supported` when
  stdin is not a TTY. Present, but not machine-addressable — a capability state
  neither "provided" nor "absent" describes.
- **The config root is redirectable.** `XDG_CONFIG_HOME` moves it to
  `$XDG_CONFIG_HOME/cursor/` without moving `$HOME`, and `HOME` moves it too. Both
  then report `Not logged in`, so credentials follow the root. A structural
  analogue of `CLAUDE_CONFIG_DIR` exists, which is the room boundary's
  precondition — this refuted a prediction that it would not.

## What this says about the layer

Four capability states showed up today, where the registry has two:

1. **Provided** — `-p`, `--model`, `--output-format json`.
2. **Absent** — `--max-turns`, peer messaging, an agent picker.
3. **Provided natively, adapter should decline** — Cursor injects its own
   `<timestamp>`; `timestamp.sh` exists to supply exactly that on Claude Code.
4. **Present but not machine-addressable** — `agent ls`.

And `reports_cost: bool` is a wrong *type* rather than a wrong value: tokens yes,
dollars no. A boolean cannot say that, so it says the false half.
