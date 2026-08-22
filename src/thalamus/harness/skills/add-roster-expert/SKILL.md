---
name: add-roster-expert
description: The end-to-end procedure for adding a Thalamus expert to the roster without breaking the tmux roster or the console's phone PWA. Use BEFORE creating any config/experts/ manifest or running `thalamus roster` with a new scope, when a roster/console surface misbehaves after a roster change (e.g. the PWA stuck at "connecting"), or before touching pin.py window mechanics or console server behavior.
---

# Add a Roster Expert (without breaking the roster)

**Custody:** any session that changes roster or console mechanics (pin.py windowing,
the console server or its service worker) updates this skill in the same change.

**Where things live.** This skill sits beside the agents it governs — in the same
package that declares the experts and owns `pin.py` — so the manifest, the window
mechanics, and the procedure for adding one all version together. The console it
warns about is `src/thalamus/console/`, in this same package.

## Procedure

0. **Ask the operator what work is PLANNED in this scope, before consulting anyone.**
   Binding, and it comes first. Every expert can only see what has already happened;
   asked a question whose answer lies in the future, it will answer about the past
   and sound decisive doing it. **A count of past work sizes a corpus and never
   bounds a role** — the litmus below asks whether real sessions would be pinned
   here, and a session that is planned but not yet run counts. An `ml-systems` scope
   was cut on a measured 0-of-~10 corpus count that was really a measure of work not
   yet started; the operator's plans reversed it the same day.
1. **Roster decision first, not procurement drift.** Clear the roster discipline
   before writing any YAML: the granularity litmus (would real sessions be pinned
   here?), the null hypothesis (a scope that adds nothing a general session lacks
   should not exist), and the skill-vs-expert test (a procedure is a skill; an
   accumulating corpus with judgement over it is an expert). Record the decision
   wherever the project keeps its roster rationale, in the same change.

   **Consult the scopes that LOSE something, not every plausible neighbour.** The
   test is whether a scope gives up territory or authority if this one ships. Those
   scopes know where the real line runs and are the ones with standing to draw it —
   and **the losing scope writes the exception list, adopted verbatim**: when a
   frontend scope was carved out, the four classes it had to return went back to the
   design scope that was giving up the authority, and were adopted as written.
   A scope with no stake returns a well-argued record that changes nothing; that is
   a round spent, not a decision made.

   **Do not ask an expert to argue the null hypothesis at full strength once the
   operator has decided with the objection in view.** Ask instead: *what would
   falsify this scope's partition in fifty sessions?* Same expert, one question, and
   the answer is the pre-registered audit the roster decision wants anyway.

   **The literature step is one recall and at most one narrow ticket** — *is there
   prior work on this corpus shape, and does it have a known failure record?* A
   roster act is an organizational decision, not a component design; the full
   `ground-in-literature` pass stays for features, components, schema changes and
   eval metrics.

   **If a live scope was present for the history you are about to reconstruct, ask it
   before doing forensics.** Reconstructing an effort from git or transcripts costs
   more than a recall and is wrong more often — a 73k-token reconstruction of a
   design handoff got the spec's origin backwards, and the design scope that was
   in the room corrected it from episodic memory it held the whole time.
2. **The manifest is the whole rollout** (zero-glue):
   `config/experts/<scope>.yaml` and nothing else. Declare only `claim_kinds` a
   real writer produces (the ingest extractor writes
   `literature/finding|technique`); an empty `allowlist` blocks web ingestion,
   and local files bypass it — hand-feeding IS the curation decision.
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
   Write the denies narrow: a quality-engineering scope denies `*/src/*` and leaves
   the test tree open, because its campaign findings graduate into the green suite.

   `allow_globs` is the escape hatch for a scope whose *artifact* is source code —
   a named tree where the file constitutes the deliverable rather than implementing
   it. Entries are checked before `deny_globs`, so they exempt a path the denies
   would otherwise catch. Reach for it only when the alternative is dropping an
   extension from `deny_globs`, which unbinds that language everywhere instead of in
   one tree.
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
   measured the opposite — its +9.4% came from refining role specifications.
   Where a grant has an exception list, get it from the scope that LOSES the
   authority, not from the one gaining it, and adopt it verbatim. A grant whose
   corpus is the record of what it decided needs a write-back path — the reviewing
   scope's verdict lands on the record — because the one measured precedent for that
   corpus shape (AWM) filters candidates through an evaluator before writing them.
3. **Anchor the scope if it must be consultable now** — a scope with nothing to
   cite refuses the consultation mint. Procure anchors *into the new scope*,
   `--feed` named for the demand. Title-check each source without a model call —
   `curl -sIL` for status, host and content-type, then `<title>` or `pdftotext` page 1
   — then `--write` once; a dry run re-bills the extraction. Then
   `uv run thalamus contract check`.
4. **Never author or `git add -f` the agent file.** `.claude/agents/thalamus-
   <scope>.md` is derived from the manifest, regenerated on every launch, and
   gitignored on purpose.
5. **A new manifest is spawnable immediately — you rarely open a window at all.**
   Experts are **spawned on demand**, not booted at bring-up: the console's
   `+ SPAWN` sheet reads `config/experts/*.yaml` for its scope list and the
   console's `--dir` favourites plus its `--scan` roots (git repos under the
   scanned directories) for its directory list, so a fresh manifest shows up with
   no restart. Under the hood `thalamus spawn <scope> --dir <path>` opens one
   **detached** window (`new-window -d`, pin.py) in the chosen cwd. `thalamus
   roster` brings up only the `main` **anchor** by default (idempotent; `--all` =
   full roster) — always-on expert windows were retired because idle spawns
   inflated the `pinned, never retrieved` metric. Spawn writes derived agents to
   `~/.claude/agents/` (not only the repo's `.claude/agents/`) so `--agent` and
   sibling consultation subagents resolve from any project cwd. Only an
   interactive `thalamus pin <scope>` switches focus, because the operator asked.
6. **Touch nothing on the console.** The console server reads tmux fresh on every
   poll and targets windows by index, so a new window appears on the phone by
   itself. Never restart the console service for a roster or MCP change — arming
   is per *claude process*, so a restart changes nothing a relaunched session
   would not, and restarting whichever process created the tmux session can take
   the whole roster with it (hazard 2). Always check first:
   `cat /proc/$(pgrep -f 'tmux.*-L thalamus' | head -1)/cgroup`
7. **Verify — including that the pin actually armed.** `curl -s
   "$CONSOLE/api/panes"` — `CONSOLE` being the console's bind address,
   `127.0.0.1:8378` by default — lists the new window; a roster re-run prints
   "already has a window"; `uv run pytest` stays green. Then confirm the new
   window's claude process resolved to the new scope — mis-arming is *silent*
   (see the agent-picker hazard): `tr '\0' '\n' </proc/<pid>/environ | grep
   THALAMUS_SCOPE`, or ask the session to run `memory_open_threads` and check
   the node prefix. Update the roster docs in the same change.

## Hazards

Split by audience. The **mechanism** hazards are not Thalamus-specific — they belong
to any setup where a long-lived tmux session is created by one process and driven by
another over HTTP.

| # | Mechanism hazard | One-line rule |
|---|---|---|
| 1 | Whichever process creates the tmux session defines window 0 | Order roster bring-up before anything else that would attach; identify the anchor by lowest index, never by name |
| 2 | The tmux server lives in the process group of whatever created it | Restarting that owner kills every window; check `/proc/<tmux>/cgroup` before restarting anything, and make the owner's kill mode leave children alone |
| 3 | `tmux new-window` returns 0 before the command execs | Confirm the window you made (`-P -F '#{window_id}'`) is alive after its harness's settle deadline; never trust the exit code (`pin.confirm_started`, 1.2 s claude / 4.0 s cursor — its auth failure is a network round trip away) |
| 4 | Undetached `new-window` yanks every attached client | pin.py's roster path uses `-d` |
| 5 | Typing into a pane showing a modal *answers* the modal | Check the target's state first; never send a bare `Enter` to a pane that might be modal |
| 6 | Everything a session spawns inherits its `TMUX_PANE` | A headless `claude -p` is a full session that would claim the window's join key; the SessionStart hook gates the claim on `CLAUDE_CODE_ENTRYPOINT=cli` |

**The 60×200 geometry is load-bearing here specifically:** claude runs on the
alternate screen, so `capture-pane` returns exactly the window height, and the phone
fit assumes 60 columns. Don't "fix" window sizes.

### Thalamus-specific hazards (each has bitten, or was caught in review)

- **The agent picker can bypass the pin env.** Pin resolution is picked-agent-first
  (`harness/pin.resolve_pin`, hooks' `resolve-scope.sh`), because launching
  `claude --agent thalamus-<scope>` from any shell leaves `THALAMUS_SCOPE` as
  residue — measured, before the fix: all three roster expert sessions mis-armed to
  main, memory ops + ledger + distillation all wrong. Arming is per-process. If an
  expert can't see its own scope's threads, check the live MCP server's env
  (`/proc/<pid>/environ`) before debugging the graph.
- **A new expert is not consultable from sessions that predate it.** The
  Agent-tool roster (like the pin) is loaded per *process*: a session started
  before the manifest existed cannot spawn `thalamus-<scope>` consultation
  subagents until relaunched, even though the graph scope and window are live.
  Same per-process arming rule as MCP/hooks, pointing the other direction.
- **Recycling a window ends the session in it** — including the one you might be
  running in. The console UI warns: the admin list badges the window you're
  viewing, and recycling it (or restart-all) gets a sharp confirm saying the
  conversation ends. The warning covers only the *viewed* window — a session you're
  running in a terminal elsewhere gets no special warning. Recycle is for re-arming
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
- **How a stolen anchor presents here** (mechanism: hazard 1). When some other
  process wins the race and attaches first with `tmux -L thalamus new -A -s thalamus`, index 0
  is a bare shell; roster sync adds `main` beside it at index 1, and INFRA →
  *restart* on that anchor types `/exit` into bash (`-bash: /exit: No such file or
  directory`), so the pane never dies and the console sits `recycling: true` for the
  full 4-min grace — which reads as **"sessions won't start"**. Ordering roster
  bring-up first prevents it; `pin.spawn()` creates the session with the scope's
  window for the same reason. Repair: confirm index 0 is an idle shell
  (`tmux -L thalamus list-panes`, no child procs), `tmux -L thalamus kill-window -t
  thalamus:0`, re-run roster.

## The seam in one line

**The manifest is the rollout; the roster window is detached; the console needs
nothing — if the phone disagrees, suspect its service worker, not the roster.**
