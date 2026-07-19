---
name: add-roster-expert
description: The end-to-end procedure for adding a Thalamus expert to the roster without breaking the tmux control plane or its phone PWA. Use BEFORE creating any config/experts/ manifest or running `thalamus roster` with a new scope, when a roster/plane surface misbehaves after a roster change (e.g. the /plane/ PWA stuck at "connecting"), or before touching pin.py window mechanics or thalamus-plane server behavior. Jointly held by main and homelab — homelab keeps it current.
---

# Add a Roster Expert (without breaking the control plane)

Jointly designed by main and the homelab expert (consultation
`scope:main:exchange:92f74910bc124b84`, 2026-07-18). **Custody:** any session
that changes roster/plane mechanics (pin.py windowing, thalamus-plane server or
SW, tailscale serve layout) updates this skill in the same change; sessions
pinned to `homelab` treat stale content here as a bug in their domain. Hazards
cite homelab graph claims so consultations can serve them; keep citations
current when re-ingesting.

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
   which the plane's roster-sync button surfaces as a failed sync — fix the
   YAML, don't debug the plane.
3. **Anchor the scope if it must be consultable now** — a scope with nothing to
   cite refuses the consultation mint (docs/02). Procure anchors *into the new
   scope* (docs/06 rule 1's scope note), `--feed` named for the demand, and
   always dry-run the title check before `--write`. Then
   `uv run thalamus contract check`.
4. **Never author or `git add -f` the agent file.** `.claude/agents/thalamus-
   <scope>.md` is derived from the manifest, regenerated on every launch, and
   gitignored on purpose.
5. **Open the window with `uv run thalamus roster`** (idempotent — only missing
   scopes get windows) or the plane's INFRA → roster-sync button. Roster
   additions open **detached** (`new-window -d`, pin.py) so attached clients
   (/tty, PC) are not yanked to the new window; only an interactive
   `thalamus pin <scope>` switches focus, because the operator asked for it.
6. **Touch nothing on the plane.** The plane server reads tmux fresh on every
   poll and targets windows by index, so a new window appears on the phone by
   itself (`scope:homelab:claim:f9c9311a69049c34`; capture/index design in
   `scope:homelab:source:e57d6219e6f3901f33d4206666c081b53bc41e97d677607223ca775014354dd5`).
   Never restart `thalamus-plane.service` for a roster or MCP change — arming
   is per *claude process*, and restarts, when actually needed, go through the
   whitelisted `systemd-run` path only (`scope:homelab:claim:2a4b253bc3df9c65`).
7. **Verify — including that the pin actually armed.** `curl -s
   127.0.0.1:8378/api/panes` lists the new window; a roster re-run prints
   "already has a window"; `uv run pytest` stays green. Then confirm the new
   window's claude process resolved to the new scope — mis-arming is *silent*
   (see the agent-picker hazard): `tr '\0' '\n' </proc/<pid>/environ | grep
   THALAMUS_SCOPE`, or ask the session to run `memory_open_threads` and check
   the node prefix. Update docs (02/08/11) and any affected workspace notes in
   the same change.

## Hazards (each has bitten, or was caught in review)

- **tmux 3.4 segfault:** a *global* `window-size manual` while a window is
  created with no client attached takes down the whole tmux server — it killed
  the entire roster once. pin.py sets `window-size manual` per-window,
  post-creation, and must stay that way
  (`scope:homelab:source:e57d6219e6f3901f33d4206666c081b53bc41e97d677607223ca775014354dd5`).
- **Active-window yank:** `tmux new-window` without `-d` switches every
  attached client to the new window (bit on the teacher rollout, 2026-07-18;
  fixed in pin.py's roster path). Keep roster creation detached.
- **The 60×200 geometry is load-bearing:** claude runs on the alternate screen,
  so `capture-pane` returns exactly the window height; the phone fit assumes
  60 columns (same source node as above). Don't "fix" window sizes.
- **Phone symptoms are usually the PWA/SW layer, not the roster.** The one
  recorded server-healthy-but-phone-wrong failure was the service worker
  serving a stale shell (`scope:homelab:claim:b8b1aa2cbd3c2b53`), fixed by the
  network-first SW (`scope:homelab:claim:ffbb6a07cd23a9c3`) — never regress the
  plane SW to cache-first, and never let it intercept `/api/`. Diagnose
  server-side first (`/api/panes` on loopback, then through
  `https://…/plane/`); if the server measures healthy, the discriminator is a
  full close (swipe from recents) + reopen of the installed PWA.
- **Path scopes stay disjoint.** Android WebAPKs ignore ports: `/plane/` and
  `/course/` are one app namespace per hostname, and a root-scoped install
  captures the other app's links host-wide (same source node). New surfaces get
  their own path scope; `tailscale serve` strips the mount path, so backends
  that need the prefix must include it in the target.
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
  be running in (`scope:homelab:claim:324c87a12b4704cc`). The plane UI now
  warns: the admin list badges the window you're viewing, and recycling it (or
  restart-all) gets a sharp confirm saying the conversation ends (resolved
  `scope:homelab:thread:homelab-recycle-self-termination-risk`, 2026-07-19).
  The warning covers only the *viewed* window — a session you're running in a
  terminal elsewhere gets no special warning. Recycle is for re-arming
  MCP/hooks after wiring changes, not part of adding an expert.

## The seam in one line

**The manifest is the rollout; the roster window is detached; the plane needs
nothing — if the phone disagrees, suspect its service worker, not the roster.**
