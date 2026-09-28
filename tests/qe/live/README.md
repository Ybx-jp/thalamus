# `live/` — real sessions, real distillation, one VM per expert configuration

The tier the rest of `tests/qe/` stops short of. A cell here is a throwaway VM that
builds the checkout, serves itself its own graph on its own loopback, installs the harness
against a config directory of fixture expert manifests, and then runs real headless
sessions pinned to those scopes — Claude Code, and codex — which end, fire the real
SessionEnd hook, and distill on `codex/gpt-5.6-luna` into that graph. The whole graph,
the guard ledger, the budget state, the generated personas and the transcripts come back,
and the oracle judges them on the host.

It costs model spend, so it is on demand, not per push.

## Files

| file | runs where | |
|---|---|---|
| `matrix.py` | both | the configurations and the sessions each runs, as data. Stdlib only |
| `cell.py` | guest | preparation steps and the session driver: graph, config dir, install, sessions, evidence |
| `graph_dump.py` | guest | the whole graph as JSON, under the checkout's own venv |
| `codex_tee.py` | guest | stands in front of `codex` and records each `--json` call's token usage |
| `fixtures/penpot_stub.py` | guest | a stdio MCP server named `penpot`, so the roster's real `mcp__penpot__*` matcher applies |
| `oracle.py` | host | evidence → one verdict per check |
| `oracle_cases.py` | host | every check driven to its verdict on poisoned synthetic evidence; no VM |

The VM mechanism, the network boundary, the credentials and the spend ceiling are
properties of one box and live outside this repository, in the operator's notes
(`ops/qe-live/run_live.py`, a caller of the same cell producer the eval arms use). Any
runner that can boot an Ubuntu guest with public egress, copy these trees in and the
collected HOME back out, and run `cell.py`'s verbs in order can drive this tier.

## What a configuration exercises

| config | surface |
|---|---|
| `write-boundary` | `write_boundary` deny on a real `Write`; the sibling path passes; a disarmed control writes both |
| `capability-default` | the roster's default capability boundary on `Skill`; a scope skill listed at session start; a thalamus recall leaving a Trace |
| `mcp-allowlist` | a scope's own MCP server armed in its generated agent; `deny_tools` with `allow_tools` carving `read_*` back |
| `budget-cap` | a two-call `budget` preset against a session asked for five |
| `codex-luna` | codex sessions through the generated profile: the `light` preset as `gpt-5.6-luna`, the boundary on `apply_patch`, codex's own SessionEnd, and whether a codex session can reach the thalamus MCP tools |
| `misspelled-boundary` | an operator's one-letter typo in `write_boundary` (#294) |

Every armed session is also held to the same graph invariants:
- a Session vertex with the pinned scope, deriving from exactly one Source;
- contained Claims carrying the scope and a `source` naming this session;
- a `TOUCHES` Artifact for each file it wrote;
- no neighbour in a foreign scope;
- a SessionEnd log of its own that names the Luna extractor.

Every cell also runs `thalamus contract check` against its graph and checks that no edge
dangles.

A check that reproduces a filed defect carries the issue on its session (`known=` in
`matrix.py`) and reports `known_red`, not `fail`: #294, #302, #303, #304, #306 as of this
writing. Remove the tag in the change that fixes the issue.

A codex patch naming several files is refused whole when one of them is denied, so a
permitted path is only held to "it landed" when some call wrote it on its own
(`allowed-writes-landed`).

## Absences and their controls

A guard row that is not there, a Session that was not written and a file that did not
land are each also what a hook that never ran produces. So each is read beside a
control: a session run with `THALAMUS_SANDBOX=1`, which every hook honours by exiting
first, must write no Session, leave no guard row, and land every file it was asked for.
And a check whose precondition the model did not supply — it never attempted the write —
reports `not_evaluated`, never `pass`.

`oracle_cases.py` is the oracle's own positive control. Run it after any change here:

```bash
python3 tests/qe/live/oracle_cases.py
```

## What is replaced, and so not tested

- **codex hook trust.** A codex session runs with `--dangerously-bypass-hook-trust`,
  because the trust record is codex's own persisted hash and cannot be recomputed
  (`install.codex_trust_keys`). The wiring is exercised; the trust prompt is not.
- **Permission prompts.** Claude sessions run `--dangerously-skip-permissions` so a
  permitted write is not stopped by a prompt nobody can answer. The boundary checks rely
  on PreToolUse hooks still firing under that flag, and every run re-measures it rather
  than assuming it: `boundary-trip` must show the block row and the absent file, and
  `boundary-control`, the same prompt with the hooks disarmed, must land both files.
- **The model's phrasing.** The oracle asserts structure, never what a claim says.
