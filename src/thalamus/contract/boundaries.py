"""Which boundary binds on which harness — the obligation, not the filename.

`install.py`'s hook-wiring parity record answers "which scripts appear in both
tables". Nobody wants to know that. What a reader acts on is *whether a scope's
declared boundary actually binds in the harness they are about to launch*, and a
script-set difference cannot answer it in either direction. It over-reported gaps
until `renames` was added (`post-tool-use.sh` is `mcp-tap.sh` under another name),
and it under-reported enforcement the moment a boundary began binding through a path
that is in neither table — which is exactly what happened:

**Cursor `2026.08.11-e8db854` reads `~/.claude/settings.json` and translates the
event names.** Its bundle carries the table verbatim — `{PreToolUse: preToolUse,
UserPromptSubmit: beforeSubmitPrompt, …}` — parses Claude Code's `|`-separated
matcher syntax, and shims `permissionDecision` onto its own `permission`. So a
Cursor session runs `hooks/claude-code/role-guard.sh` with nothing wired under
`.cursor/`, and the write boundary has been enforced there since the day that
release shipped. Measured, not inferred: a `qe`-pinned Cursor session's `Write` to
`*/src/*` was blocked, the file was unchanged, and `~/.thalamus/guards/` took a
`role-boundary` block row carrying a Cursor conversation id (lab/061).

Both times the record was wrong the cause was the same — it measures the artifact
instead of the obligation. Moving a claim from prose into a dataclass raised its
precision and left its subject alone.

## The five states, and why three are not enough

`NATIVE` and `UNKNOWN` are the two that bite here. Without `NATIVE` there is nowhere
to say "the harness already does this, so an adapter must decline" — and an adapter
built anyway *double-fires*: two registrations for one obligation, the same denial
reaching the agent twice in one tool result, and two rows per block in a ledger whose
passes are evidence for the roster's granularity audit. LSP forbids the same shape
for the same reason: a server may not register one capability both statically and
dynamically for one selector (`scope:architect:claim:d1f3f6e9100cbab5`). Without
`UNKNOWN`, `ABSENT` gets written next to something nobody measured, and `ABSENT` is a
claim.

The rule the states follow is LSP's: an omitted property has a *written* meaning,
never an unspecified one (`scope:architect:claim:5d76e83a27802b2f`). FHIR R4's
`DataAbsentReason` draws the same distinctions upstream of us and names them
`unsupported` / `not-permitted` / `not-asked`, so this enum is a projection of an
existing value set rather than a vocabulary of our own.

## Evidence, and the row that cannot be re-asked for free

The thing that changed under us was a **vendor build**, so staleness expires against
an artifact rather than a clock: every row names what it was verified against, and
the Cursor rows name `cursor/2026.08.11-e8db854` because that string — not the date —
is what a later reader must compare.

The Claude Code rows re-ask themselves for free: the wiring tables are ours, so
`check_boundaries()` recomputes whether the guard is actually wired on a matcher that
names the tool. That check is not ceremonial — a room boundary was once declared in
`install.py` and never armed, and every room ran reporting a treatment that had not
occurred (lab/056).

The Cursor rows cannot. No sentinel probe and no derivation reaches a vendor's
undocumented compatibility path; it takes a live session, a real model call and a
workspace-trust grant. They are therefore `UNPROBEABLE` on every run, by
construction, and that shows up in the unchecked count rather than being smoothed
into a green tick. A row that will be re-run rarely is stale-able by design, and
saying so in the record is the honest form of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from thalamus.contract.probes import Condition


class Provision(str, Enum):
    """How a boundary comes to bind — or not — on one harness."""

    PROVIDED = "provided"   # it binds, and Thalamus wires it
    NATIVE = "native"       # the harness already does it; an adapter must decline
    ABSENT = "absent"       # no referent exists, so there is nothing to enforce
    OPAQUE = "opaque"       # present, but not addressable by anything we can write
    UNKNOWN = "unknown"     # never asked — not a synonym for absent


@dataclass(frozen=True)
class Evidence:
    """What was actually observed, and what it would cost to observe again."""

    kind: str
    at: str
    where: str
    # The artifact the observation is pinned to. A vendor build, a commit — never a
    # bare date, because the date does not tell a later reader what changed.
    verified_against: str
    conditions: tuple[Condition, ...]
    # "free" — a derivation or parser probe re-asks it at no cost.
    # "live-session" — re-asking costs a real session, so this row goes stale quietly.
    reask: str


@dataclass(frozen=True)
class BoundaryRow:
    boundary: str
    harness: str
    state: Provision
    evidence: Evidence
    note: str

    @property
    def label(self) -> str:
        return f"{self.boundary} on {self.harness}"


# What each boundary needs from a wiring table to bind: the script that enforces it,
# and the tool name whose matcher must reach that script. This is the free half of
# the re-ask — our own tables, checked against our own claim.
WIRING_REQUIREMENT: dict[str, tuple[str, str]] = {
    "write_boundary.path": ("role-guard.sh", "Write"),
    "path_ownership.path": ("role-guard.sh", "Write"),
    "capability_boundary.tool": ("role-guard.sh", "Artifact"),
    "capability_boundary.skill": ("role-guard.sh", "Skill"),
    "room_boundary.message": ("room-guard.sh", "SendMessage"),
}

_WIRED = Evidence(
    kind="derivation",
    at="2026-08-12",
    where="install.HOOK_WIRING — the guard is wired on a matcher naming the tool",
    verified_against="install.HOOK_WIRING",
    conditions=(),
    reask="free",
)

# One build, and not one mode any more: the write and capability rows were taken under
# `agent -p --trust`, while the room row rests on a real interactive session driven in
# tmux. The conditions tuple on each row is what says which, and it matters because a
# probe is sound as a falsifier and unsound as a generalizer (probes.py) — a headless
# run cannot observe a modal, which is the whole subject of the room row.
_CURSOR_LIVE = "cursor/2026.08.11-e8db854"
_CURSOR_COND = (Condition.PARSE, Condition.PRINT)

BOUNDARY_ROWS: tuple[BoundaryRow, ...] = (
    BoundaryRow(
        "write_boundary.path", "claude", Provision.PROVIDED, _WIRED,
        "role-guard.sh resolves the pin, then fnmatches the path against the "
        "manifest's deny_globs. Bash and a repo that keeps implementation outside "
        "`src/` are named misses, not gaps in the wiring.",
    ),
    BoundaryRow(
        "path_ownership.path", "claude", Provision.PROVIDED, _WIRED,
        "The inverse of write_boundary.path, and the only boundary here that binds "
        "`main`: ownership is resolved from `contract/ownership.PATH_OWNERSHIP` "
        "rather than from a manifest, because the scope it most needs to bind has no "
        "manifest to declare a deny in. Ordered ahead of the `main` short-circuit, "
        "which is why the table imports no pydantic — 151ms there would cost more "
        "than the manifest load the short-circuit exists to avoid. Alone among these "
        "rows the rule fails CLOSED: an unparseable payload is searched raw and "
        "refused, the `write-guard.sh` posture rather than this guard's.",
    ),
    BoundaryRow(
        "capability_boundary.tool", "claude", Provision.PROVIDED, _WIRED,
        "The roster default denies `Artifact` for every scope but `designer`; "
        "`action: list` is read-only and passes.",
    ),
    BoundaryRow(
        "capability_boundary.skill", "claude", Provision.PROVIDED, _WIRED,
        "Glob patterns over the skill name, because the namespace is owned "
        "upstream. `Read` on a SKILL.md reaches the procedure with no `Skill` call "
        "and no tool-name matcher can see that.",
    ),
    BoundaryRow(
        "room_boundary.message", "claude", Provision.PROVIDED, _WIRED,
        "Two channels, two matchers: `room-guard.sh` on `SendMessage`, and "
        "`room-command-guard.sh` on `Bash` for the peer traffic a tool name cannot "
        "see — `tmux send-keys` reaches any pane on the box, and `thalamus dispatch` "
        "addresses a room by name from a shell. The free re-ask below checks the "
        "first; it was once declared here and never armed, so every room reported a "
        "treatment that had not occurred (lab/056), which is why this row is "
        "recomputed rather than believed.",
    ),
    BoundaryRow(
        "write_boundary.path", "cursor", Provision.NATIVE,
        Evidence(
            kind="live-session",
            at="2026-08-12",
            where="`THALAMUS_SCOPE=qe agent -p --trust` in a directory with no "
                  "`.cursor/hooks.json`: the `Write` to `*/src/*` was blocked, the "
                  "file was unchanged, and a `role-boundary` block row landed in "
                  "~/.thalamus/guards/ under a Cursor conversation id (lab/061)",
            verified_against=_CURSOR_LIVE,
            conditions=_CURSOR_COND,
            reask="live-session",
        ),
        "Bound through the vendor's own translation of `~/.claude/settings.json`, so "
        "Thalamus wires nothing under `.cursor/` for it and must not: a second "
        "registration on `preToolUse` runs the same guard twice on one call. The "
        "path is undocumented and can vanish in a release, which is why this row "
        "names a build rather than carrying a boolean.",
    ),
    BoundaryRow(
        "capability_boundary.tool", "cursor", Provision.ABSENT,
        Evidence(
            kind="live-session",
            at="2026-08-12",
            where="tool names observed across five probe sessions — Read, Write, "
                  "Shell, Grep, Task, MCP:<name>; no `Artifact` tool exists",
            verified_against=_CURSOR_LIVE,
            conditions=_CURSOR_COND,
            reask="live-session",
        ),
        "The roster default's only denied tool has no referent here, so the "
        "capability boundary is **vacuous** on Cursor rather than unenforced. A "
        "manifest that denies an MCP tool would change this row, and none does.",
    ),
    BoundaryRow(
        "capability_boundary.skill", "cursor", Provision.UNKNOWN,
        Evidence(
            kind="live-session",
            at="2026-08-12",
            where="invoking a built-in skill produced a `Read` of its SKILL.md and "
                  "then `Task` — no `Skill` tool call to intercept; "
                  "`~/.cursor/skills-cursor/` holds 18 skills",
            verified_against=_CURSOR_LIVE,
            conditions=_CURSOR_COND,
            reask="live-session",
        ),
        "UNKNOWN rather than ABSENT: skills exist and are used, and `beforeReadFile` "
        "is an interception point Claude Code has no equivalent of, so a read guard "
        "over `*/skills*/*/SKILL.md` is reachable and has never been asked for. Not "
        "built: a guard on `Read` is a high-false-positive surface, and lab/008's "
        "standing trade is that a false positive teaches route-around.",
    ),
    BoundaryRow(
        "room_boundary.message", "cursor", Provision.PROVIDED,
        Evidence(
            kind="live-session",
            at="2026-08-13",
            where="a `qe`-pinned Cursor member of room `probe` was asked to run "
                  "`tmux send-keys -t %0 hello`; the command did not run, the guard's "
                  "own prose reached the model verbatim, and a `room-boundary` block "
                  "row with `branch: raw-transport` landed in `~/.thalamus/guards/` "
                  "(lab/065)",
            verified_against="cursor/2026.08.11-e8db854",
            conditions=(Condition.PARSE, Condition.PRINT, Condition.INTERACTIVE),
            reask="live-session",
        ),
        "Through `room-command-guard.sh` on `beforeShellExecution`, not a port of "
        "`room-guard.sh`: that one matches the `SendMessage` tool name and Cursor has "
        "no such tool, so peer traffic here is a shell command or it is nothing. The "
        "guard is defence-in-depth over `dispatch.authenticate`, which establishes "
        "the sender from the calling process — a command-string matcher can be evaded "
        "by a determined member, and the check inside the verb reads data the caller "
        "cannot author. The one rule with no second line behind it is the raw "
        "transport: `send-keys` never reaches the verb, so the guard is the whole "
        "boundary there and matches the verb rather than the binary's spelling.",
    ),
)


def check_boundaries() -> list[tuple[BoundaryRow, str, str]]:
    """Re-ask every boundary row that can be re-asked. Returns (row, outcome, detail).

    Outcomes match `probes.Outcome` values so one report can carry both kinds of
    declaration. The Cursor rows answer `unprobeable` on every run by construction —
    that is the honest state of a claim about a vendor's undocumented behaviour, and
    it belongs in the unchecked count rather than in a comment.
    """
    from thalamus.harness.install import HOOK_WIRING

    results = []
    for row in BOUNDARY_ROWS:
        if row.evidence.reask != "free":
            results.append((
                row, "unprobeable",
                f"needs a live session against {row.evidence.verified_against}",
            ))
            continue

        script, tool = WIRING_REQUIREMENT[row.boundary]
        wired = any(
            hook_script == script and matcher is not None and tool in matcher.split("|")
            for _, matcher, hook_script in HOOK_WIRING
        )
        if wired == (row.state is Provision.PROVIDED):
            results.append((row, "confirmed", ""))
        else:
            results.append((
                row, "drift",
                f"declared {row.state.value}, but `{script}` is "
                f"{'not ' if not wired else ''}wired on a matcher naming `{tool}`",
            ))
    return results
