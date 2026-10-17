---
name: add-an-expert
description: The end-to-end procedure for adding a Thalamus expert — deciding the scope should exist, writing its manifest and boundaries, anchoring it, and confirming a pinned session arms to it. Use BEFORE creating any config/experts/ manifest, when deciding whether a proposed scope should exist at all, and when a newly added expert's sessions do not see their own scope.
---

# Add an Expert

**Custody:** any session that changes what a manifest declares, how a pin arms, or
how an expert is launched updates this skill in the same change. Launching experts as
tmux windows from the console is `docs/console.md`'s, not this skill's.

## Procedure

0. **Ask the operator what work is PLANNED in this scope, before consulting anyone.**
   Binding, and it comes first. Every expert can only see what has already happened;
   asked a question whose answer lies in the future, it will answer about the past
   and sound decisive doing it. **A count of past work sizes a corpus and never
   bounds a role** — the litmus below asks whether real sessions would be pinned
   here, and a session that is planned but not yet run counts. An `ml-systems` scope
   was cut on a measured 0-of-~10 corpus count that was really a measure of work not
   yet started; the operator's plans reversed it the same day.
1. **Decide the scope should exist first, not procurement drift.** Clear these before
   writing any YAML: the granularity litmus (would real sessions be pinned here?), the
   null hypothesis (a scope that adds nothing a general session lacks should not
   exist), and the skill-vs-expert test (a procedure is a skill; an accumulating
   corpus with judgement over it is an expert). Record the decision wherever the
   project keeps its rationale for its experts, in the same change.

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
   the answer is the pre-registered audit the decision wants anyway.

   **The literature step is one recall and at most one narrow ticket** — *is there
   prior work on this corpus shape, and does it have a known failure record?* Adding
   an expert is an organizational decision, not a component design; the full
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
   A malformed or scope-mismatched manifest fails loudly, and every launch path loads
   every manifest (`write_all_agents`), so one bad file stops every pin until it is
   fixed — fix the YAML rather than debugging whatever surface reported it.
2b. **If the scope is defined by what it must NOT produce, declare a
   `write_boundary`** — `deny_globs` (fnmatch over the **absolute** POSIX path, so
   `*` crosses `/` and the rule survives a launch into another repo) plus a
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
   `EXPERT_CAPABILITY_DEFAULT`, so a new expert silently arrives denied the design
   skills and the `Artifact` tool. That is usually right. If the scope you are adding
   genuinely needs them, it must opt out with an explicit block — `deny_tools: []`,
   `deny_skills: []`, and a `reason` — the way `designer` does; omitting the field
   inherits the deny instead of clearing it. Run `thalamus contract check --experts`
   after the manifest lands and read the row for your scope, because an inherited
   policy appears nowhere in the file you just wrote.
2d. **If the scope is defined by what it is licensed to DECIDE, nothing in the
   contract expresses that** — `write_boundary`, `capability_boundary` and
   the config root's `ownership.json` all deny, and there is no field meaning *this scope decides*.
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
   `--feed` named for the demand. Check each source without a model call —
   `thalamus ingest <doc> --scope <new-scope> --check` reports the serving host, the
   content-type and the document's title — then `--write` once, which ingests the
   bytes the check verified; a run without `--write` re-bills the extraction and is
   not the check. Then `uv run thalamus contract check`.
4. **Never author or `git add -f` the agent file.** `.claude/agents/thalamus-
   <scope>.md` is derived from the manifest, regenerated on every launch, and
   gitignored on purpose.
5. **A new manifest is launchable immediately.** `thalamus pin <scope>` hands the
   terminal to a session pinned to it. With the console installed, its spawn sheet
   reads `config/experts/*.yaml` and lists the new scope with no restart
   (`docs/console.md`).
6. **Verify that the pin actually armed** — mis-arming is *silent* (see the agent
   picker below). In the new session, run `memory_open_threads` and check the node
   prefix names the new scope, or read the process's environment:
   `tr '\0' '\n' </proc/<pid>/environ | grep THALAMUS_SCOPE`. `uv run pytest` stays
   green. Update the docs that list the experts in the same change.

## Hazards (each has bitten, or was caught in review)

- **The agent picker can bypass the pin env.** Pin resolution is picked-agent-first
  (`harness/pin.resolve_pin`, hooks' `resolve-scope.sh`), because launching
  `claude --agent thalamus-<scope>` from any shell leaves `THALAMUS_SCOPE` as
  residue — measured, before the fix: all three pinned expert sessions mis-armed to
  main, memory ops + ledger + distillation all wrong. Arming is per-process. If an
  expert can't see its own scope's threads, check the live MCP server's env
  (`/proc/<pid>/environ`) before debugging the graph.
- **A new expert is not consultable from sessions that predate it.** The Agent tool's
  list of subagents, like the pin, is loaded per *process*: a session started before
  the manifest existed cannot spawn `thalamus-<scope>` consultation subagents until
  relaunched, even though the graph scope is live. Same per-process arming rule as
  MCP and hooks, pointing the other direction.

## The seam in one line

**The manifest is the rollout; the pin is the process; nothing else has to change.**
