---
name: add-roster-expert
description: The end-to-end procedure for adding a Thalamus expert to the roster without breaking the tmux roster or the console's phone PWA. Use BEFORE creating any config/experts/ manifest or running `thalamus roster` with a new scope, when a roster/console surface misbehaves after a roster change (e.g. the PWA stuck at "connecting"), or before touching pin.py window mechanics or console server behavior. Jointly held by main and homelab — homelab keeps it current.
---

# Add a Roster Expert (without breaking the roster)

Jointly designed by main and the homelab expert (consultation
`scope:main:exchange:92f74910bc124b84`, 2026-07-18). **Custody:** any session
that changes roster or console mechanics (pin.py windowing, the console server or
SW, tailscale serve layout) updates this skill in the same change; sessions
pinned to `homelab` treat stale content here as a bug in their domain. Hazards
cite homelab graph claims so consultations can serve them; keep citations
current when re-ingesting.

**Where things live.** This skill sits beside the agents it governs — in the same
package that declares the experts and owns `pin.py` — so the manifest, the window
mechanics, and the procedure for adding one all version together. The console it
warns about is `src/thalamus/console/`, in this same package. The *mechanism*
hazards it indexes are vendor-neutral — true of any systemd-owned tmux session
driven over HTTP — and are written up separately in
[docs/console-hazards.md](../../../../../docs/console-hazards.md).

## Procedure

1. **Roster decision first, not procurement drift.** Clear docs/08's discipline
   (granularity litmus, null hypothesis, skill-vs-expert test) and run
   `ground-in-literature` (+ `thalamus-design-readiness` alongside). Record the
   decision in docs/08 in the same change.
2. **The manifest is the whole rollout** (zero-glue, docs/01/02):
   `config/experts/<scope>.yaml` and nothing else. Declare only `claim_kinds` a
   real writer produces (the ingest extractor writes
   `literature/finding|technique`); an empty `allowlist` blocks web ingestion,
   and local files bypass it — hand-feeding IS the curation decision (docs/06).
   A malformed or scope-mismatched manifest fails loudly but aborts the whole
   roster run mid-loop (`load_manifest` raises inside `roster()`'s scope loop),
   which the console's roster-sync button surfaces as a failed sync — fix the
   YAML, don't debug the console.
2b. **If the scope is defined by what it must NOT produce, declare a
   `write_boundary`** — `deny_globs` (fnmatch over the **absolute** POSIX path, so
   `*` crosses `/` and the rule survives `spawn --dir` into another repo) plus a
   `reason` the blocked session will read. The `role-guard` PreToolUse hook enforces
   it on Edit/Write/NotebookEdit; Bash still writes, and an unconventional layout
   escapes a path deny. State the boundary in `domain` too — the guard is
   defence-in-depth, not the definition. A scope whose charter *is* to write code
   declares nothing and says why (`architect` is the worked example).
   Write the denies narrow: `qe` denies `*/src/*` and leaves `tests/` and `lab/`
   open, because its campaign findings graduate into the green suite.
2c. **Know what the new scope inherits without asking for it.** `capability_boundary`
   defaults the other way from `write_boundary`: declaring nothing inherits
   `ROSTER_CAPABILITY_DEFAULT`, so a new expert silently arrives denied the design
   skills and the `Artifact` tool. That is usually right. If the scope you are adding
   genuinely needs them, it must opt out with an explicit block — `deny_tools: []`,
   `deny_skills: []`, and a `reason` — the way `designer` does; omitting the field
   inherits the deny instead of clearing it. Run `thalamus contract check --roster`
   after the manifest lands and read the row for your scope, because an inherited
   policy appears nowhere in the file you just wrote.
2d. **If the scope is defined by what it is licensed to DECIDE, nothing in the
   contract expresses that** — `write_boundary`, `capability_boundary` and
   `PATH_OWNERSHIP` all deny, and there is no field meaning *this scope decides*.
   Put the grant in `domain`, state it as a rule the session can apply (what is
   closed here, what is returned, and to whom), and expect no enforcement. Do not
   reach for a hook to simulate one: the MAST result often cited for "prose fails"
   measured the opposite — its +9.4% came from refining role specifications
   (`scope:literature:claim:88a0a8431c91e57e`). Where a grant has an exception list,
   get it from the scope that LOSES the authority, not from the one gaining it, and
   adopt it verbatim; `frontend`'s four returned classes came from `designer` under
   ticket `8ba49ad61e5e4bdb`. A grant whose corpus is the record of what it decided
   needs a write-back path — the reviewing scope's verdict lands on the record —
   because the one measured precedent for that corpus shape (AWM) filters candidates
   through an evaluator before writing them (`scope:frontend:source:4eaa3dcf1f7be0f7db3e4a7c7c7bdce52329ef8577ce44564acc610b97c357d9`).
3. **Anchor the scope if it must be consultable now** — a scope with nothing to
   cite refuses the consultation mint (docs/02). Procure anchors *into the new
   scope* (docs/06 rule 1's scope note), `--feed` named for the demand, and
   always dry-run the title check before `--write`. Then
   `uv run thalamus contract check`.
4. **Never author or `git add -f` the agent file.** `.claude/agents/thalamus-
   <scope>.md` is derived from the manifest, regenerated on every launch, and
   gitignored on purpose.
5. **A new manifest is spawnable immediately — you rarely open a window at all.**
   Experts are **spawned on demand**, not booted at bring-up: the console's
   `+ SPAWN` sheet reads `config/experts/*.yaml` for its scope list and
   the console's `--dir` favorites + `--scan` roots (`~/code` git repos) for
   its directory list, so a fresh manifest shows up with no restart. Under the
   hood `thalamus spawn <scope> --dir <path>` opens one **detached** window
   (`new-window -d`, pin.py) in the chosen cwd. `thalamus roster` now brings up
   only the `main` **anchor** by default (idempotent; `--all` = legacy full
   roster) — always-on expert windows were retired because idle spawns inflated
   the `pinned, never retrieved` metric (2026-07-19). Spawn writes derived agents
   to `~/.claude/agents/` (not only the repo's `.claude/agents/`) so `--agent`
   and sibling consultation subagents resolve from any project cwd. Only an
   interactive `thalamus pin <scope>` switches focus, because the operator asked.
6. **Touch nothing on the console.** The console server reads tmux fresh on every
   poll and targets windows by index, so a new window appears on the phone by
   itself (`scope:homelab:claim:f9c9311a69049c34`; capture/index design in
   `scope:homelab:source:e57d6219e6f3901f33d4206666c081b53bc41e97d677607223ca775014354dd5`).
   Never restart `thalamus-console.service` for a roster or MCP change — arming
   is per *claude process*, and restarts, when actually needed, go through the
   whitelisted `systemd-run` path only (`scope:homelab:claim:2a4b253bc3df9c65`).
   The restart ban has teeth beyond arming — the cgroup hazard (hazard 2) means
   restarting whichever unit created the session kills the whole roster. Always:
   `cat /proc/$(pgrep -f 'tmux new-session.*thalamus' | head -1)/cgroup`
7. **Verify — including that the pin actually armed.** `curl -s
   127.0.0.1:8378/api/panes` lists the new window; a roster re-run prints
   "already has a window"; `uv run pytest` stays green. Then confirm the new
   window's claude process resolved to the new scope — mis-arming is *silent*
   (see the agent-picker hazard): `tr '\0' '\n' </proc/<pid>/environ | grep
   THALAMUS_SCOPE`, or ask the session to run `memory_open_threads` and check
   the node prefix. Update docs (02/08/11) and any affected workspace notes in
   the same change.

## Hazards

Split by audience. The **mechanism** hazards are not Thalamus-specific — they belong
to any tmux-session-owned-by-systemd-driven-over-HTTP setup, so they are written up
vendor-neutrally in [docs/console-hazards.md](../../../../../docs/console-hazards.md).
Read it before changing window mechanics; the index below is a reminder of what's in
it, not a substitute.

| # | Mechanism hazard | One-line rule |
|---|---|---|
| 1 | Session creator defines window 0 | Order `thalamus-roster.service` `Before=` tty and console; identify the anchor by lowest index, never by name |
| 2 | tmux server lives in the creating unit's cgroup | `KillMode=process`; check `/proc/<tmux>/cgroup` before restarting anything |
| 3 | A pane inherits the *creating client's* PATH | Units pin `Environment=PATH=%h/.local/bin:…`; without it a boot-started unit spawns panes that can't exec `claude` |
| 4 | `tmux new-window` returns 0 before the command execs | Confirm the window you made (`-P -F '#{window_id}'`) is alive after its harness's settle deadline; never trust the exit code (`pin.confirm_started`, 1.2 s claude / 4.0 s cursor — its auth failure is a network round trip away) |
| 5 | Undetached `new-window` yanks every attached client | pin.py's roster path uses `-d` (bit on the teacher rollout, 2026-07-18) |
| 6 | Global `window-size manual` segfaults tmux 3.4 | Per-window, post-creation only — a global set killed the whole roster once |
| 7 | Stale SW / Android WebAPK scope collisions | Network-first shell, never intercept `/api/`, disjoint path scopes per surface |
| 8 | `tailscale serve` strips the mount path | Relative fetch paths in the client |
| 9 | Typing into a pane showing a modal *answers* the modal | Check the target's state first; never send a bare `Enter` to a pane that might be modal |
| 10 | Everything a session spawns inherits its `TMUX_PANE` | A headless `claude -p` is a full session that would claim the window's join key; the SessionStart hook gates the claim on `CLAUDE_CODE_ENTRYPOINT=cli` |

Graph provenance for the above, for consultations that need to cite it:
tmux geometry + WebAPK scopes
`scope:homelab:source:e57d6219e6f3901f33d4206666c081b53bc41e97d677607223ca775014354dd5`;
stale-SW failure `scope:homelab:claim:b8b1aa2cbd3c2b53` → network-first fix
`scope:homelab:claim:ffbb6a07cd23a9c3`; console reads tmux fresh
`scope:homelab:claim:f9c9311a69049c34`; restart path
`scope:homelab:claim:2a4b253bc3df9c65`.

**The 60×200 geometry is load-bearing here specifically:** claude runs on the
alternate screen, so `capture-pane` returns exactly the window height, and the phone
fit assumes 60 columns. Don't "fix" window sizes.

### Thalamus-specific hazards (each has bitten, or was caught in review)

- **The agent picker used to bypass the pin env** — fixed 2026-07-18: pin
  resolution is now picked-agent-first (`harness/pin.resolve_pin`, hooks'
  `resolve-scope.sh`), because launching `claude --agent thalamus-<scope>` from
  any shell left `THALAMUS_SCOPE` as residue (measured: all three roster expert
  sessions mis-armed to main, memory ops + ledger + distillation all wrong).
  Arming is per-process: sessions started before the fix stay mis-armed until
  relaunched. If an expert can't see its own scope's threads, check the live
  MCP server's env (`/proc/<pid>/environ`) before debugging the graph.
- **A new expert is not consultable from sessions that predate it.** The
  Agent-tool roster (like the pin) is loaded per *process*: a session started
  before the manifest existed cannot spawn `thalamus-<scope>` consultation
  subagents until relaunched, even though the graph scope and window are live.
  Same per-process arming rule as MCP/hooks, pointing the other direction —
  caught in the 2026-07-18 skill audit, not yet bitten.
- **Recycling a window ends the session in it** — including the one you might
  be running in (`scope:homelab:claim:324c87a12b4704cc`). The console UI now
  warns: the admin list badges the window you're viewing, and recycling it (or
  restart-all) gets a sharp confirm saying the conversation ends (resolved
  `scope:homelab:thread:homelab-recycle-self-termination-risk`, 2026-07-19).
  The warning covers only the *viewed* window — a session you're running in a
  terminal elsewhere gets no special warning. Recycle is for re-arming
  MCP/hooks after wiring changes, not part of adding an expert.
- **Close vs. recycle vs. the anchor.** The console's INFRA → *close* ends a
  session for good: `/exit` → SessionEnd distillation → the window is *removed*
  (recycle respawns it; close does not). Force-`kill-window` only after the
  4-min grace, which skips distillation — same tradeoff as a recycle timeout.
  The **anchor** (the lowest-indexed window, the roster's `main`) is guarded
  un-closable — it's the console's reference cwd for roster-sync and command
  scanning. On-demand `main` sessions opened elsewhere share the name "main" but
  are *not* the anchor (identified by lowest index, never by name — a name guard
  wrongly protected every "main").
- **On-demand duplicates are allowed and index-targeted.** Two windows for the
  same scope in different dirs are fine (the console targets by index, not name);
  roster idempotency (`already has a window`) keys on name and only governs
  `--all`, not on-demand spawn.
- **How a stolen anchor presents here** (mechanism: hazard 1). When ttyd's
  `tmux new -A -s thalamus` wins the race, index 0 is a bare shell; roster sync
  adds `main` beside it at index 1, and INFRA → *restart* on that anchor types
  `/exit` into bash (`-bash: /exit: No such file or directory`), so the pane
  never dies and the console sits `recycling: true` for the full 4-min grace —
  which reads as **"sessions won't start"**. `thalamus-roster.service` ordered
  `Before=thalamus-tty.service` prevents it; `pin.spawn()` creates the session
  with the scope's window for the same reason. Repair: confirm index 0 is an idle
  shell (`tmux list-panes`, no child procs), `tmux kill-window -t thalamus:0`,
  re-run roster.
- **How a bad PATH presents here** (mechanism: hazards 3+4). After an unattended
  reboot the spawn sheet reports `Spawned …` and no window appears, and the
  anchor never loads — the boot-time PATH has no `~/.local/bin`, so `claude`
  can't exec. If the anchor was the only window, the tmux server exits with it
  and the whole roster is gone (2026-08-08). Check
  `systemctl --user show thalamus-console -p Environment` first; `do_spawn` now
  reports this as a failure instead of a success.

## The seam in one line

**The manifest is the rollout; the roster window is detached; the console needs
nothing — if the phone disagrees, suspect its service worker, not the roster.**
