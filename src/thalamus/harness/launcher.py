"""How a session is launched and *pinned* — the second kind of invocation.

`agents.py` records what Thalamus asks of a CLI whose output it reads: the binary, the
default model, whether the envelope prices the call, the preconditions a headless run
must satisfy. A launcher is the other kind — it hands a CLI to a human and reads
nothing back. The two surfaces move independently: across two Cursor builds the JSON
envelope `agents.py` describes was stable while the launch surface gained four flags,
so a registry that answered both questions would carry one claim's staleness into the
other.

## What a pin is, and what carries it

On Claude Code a pin fuses four things onto one string. `--agent thalamus-<scope>`
selects a **persona** (the derived agent file's charter), arms that scope's **MCP
servers** (its frontmatter), and — because it rides the argv — carries the **routing
tag** through a window recycle. The **boundary** comes separately, from the manifest
the guard loads once `resolve-scope.sh` has answered.

On Cursor, `--agent` does not exist, and neither does any substitute:

- **Persona: none.** The only flag that could replace a system prompt is
  `--system-prompt <file>`, hidden from `--help` and marked *"Anysphere/OpenAI team
  only"* in the vendor's own bundle. Not a mechanism this project may build on.
- **MCP arming: not per-scope.** Cursor reads servers from `~/.cursor/mcp.json` and the
  workspace's, and drops `mcpServers` from an agent file entirely. Arming is global or
  it is nothing.
- **Routing tag: only through the environment**, which is why the argv prefix below is
  not cosmetic.

So a pinned Cursor session **routes and is bounded, and does not think like the
expert**. That is a smaller object than a Claude Code pin, and the honest response is
to name it rather than to reach for the hidden flag. `contract/pinning.py` is where it
is named, per component, so "pinned" cannot quietly mean four things on one harness and
two on another.

Codex does **not** sit with Cursor here. `--profile <name>` layers
`$CODEX_HOME/<name>.config.toml` over the base config, and a profile file carries both
`developer_instructions` — the charter — and its own `[mcp_servers.*]` tables. So a
pinned codex session thinks like the expert and arms the scope's tooling, and
`harness/pin.py` generates the profile from the same manifest the Claude Code agent
file comes from. Two things do not follow from that flag and are worth keeping
distinct: it tells the hooks nothing, so the routing tag still rides the `env` prefix;
and a `--profile` naming a file that does not exist starts a session with no charter
and no error, which is why the generator writes the file before the launcher names it.

One measured difference from Cursor is
worth carrying: codex's `SessionStart` hook fires at the **first submitted
turn**, not at launch, so a codex window that is spawned and never used writes no pin
ledger row. The scope still reached it — the prefix is in the argv the window was
created with, which is also what `panes.harness_of` reads — so this costs the ledger's
record of the launch and not the pin itself.

## The recycle trap, which is the whole reason the argv is built here

`tmux new-window -e VAR=x` sets the initial process environment and is **not** stored
in the session environment, so `respawn-window` — exactly what the console's restart
button runs — re-executes the argv with that variable gone (`pin._with_room` records
the same measurement for rooms). Claude Code survives because `--agent` rides the argv.
Cursor has no argv pin carrier, so a recycled window comes back inheriting the session
env's `THALAMUS_SCOPE=main` — and `role-guard.sh` short-circuits on `main` before it
loads any manifest. A bounded window becomes an unbounded one, from a phone tap, with
no row anywhere saying so.

Hence `env THALAMUS_SCOPE=<scope>` in front of the binary: the same shape rooms
already use, for the same reason. No `--` separator — `env` stops scanning for
options at the first `NAME=VALUE`, so a later `--` is taken as the command name and
the launch exits 127.

## How long a launch takes to prove itself

`tmux new-window` returns 0 once it has forked, so the only evidence a pinned window
exists is that it is still alive some time later. How much
later is a per-harness fact, because the two CLIs fail at different depths:

| launch | outcome | measured |
|---|---|---|
| `claude`, missing binary | dies, status 127 | 0.010 s |
| `claude`, rejected flag | dies, status 1 | 0.278 s |
| `claude`, untrusted dir / bad API key / no credentials | **lives** — parks on a modal | alive at 30 s |
| `agent`, untrusted dir / no credentials | **lives** — parks on a modal | alive at 30 s |
| `agent`, rejected API key | dies, status 1 | 1.07–1.14 s (n=9) |
| `agent`, rejected API key, +2 s of proxy latency | dies, status 1 | 3.14–3.20 s (n=3) |
| `codex`, rejected flag | dies, status 1 | 0.128 s |
| `codex`, unreachable `CODEX_HOME` | dies, status 1 | 0.124 s |
| `codex`, unknown `--model` | **lives** — fails at the first turn instead | alive at 25 s |

Claude Code and codex decide everything that can kill them locally, so a fraction of a
second covers both. Cursor's one measured death is an **authentication rejection**, which
resolves only after a round trip to its API — the last two rows are the same failure
under two network conditions, and the time to it moved by exactly the added latency.
So `settle_s` is a bet sized on a measurement, not a bound: a deadline covers the
death modes whose cost is local, and buys headroom against a network leg that has
none. A death after the deadline is reported by nothing; the window list is what
shows it.

## Permission posture

Claude Code launches every pinned window with `--permission-mode auto`, chosen so a
member never sits at a prompt (a prompting member reports `waiting`, which dispatch
refuses to send into). Cursor **has a non-stalling flag but no equivalent one**, and
the difference is one specific control rather than a spelling:

- `--auto-review` is the nearest architecture — a server classifier auto-runs safe
  calls — and it *prompts on the remainder*, so it stalls exactly where `auto` does
  not.
- `--force`/`--yolo` ("Run Everything") does not stall. Measured 2026-08-12 on
  2026.08.11-e8db854: a shell command absent from `permissions.allow` ran with no
  prompt, and so did an MCP tool call absent from it, where an unflagged session
  launched beside it stopped on both.
- What `--force` keeps: the explicit `permissions.deny` list, and the
  `beforeShellExecution` hooks — measured in the same run, where `write-guard.sh`
  denied `thalamus write` inside a `--force` session, the hook's own prose reaching
  the model verbatim. So the role boundary does **not** rest on the permission mode,
  which is what "Run Everything" reads as promising.
- What it drops is the safety classifier `auto` routes the remainder through. That
  is the whole of the gap, and it is the control FIDES measures as load-bearing
  against prompt injection (`scope:literature:claim:073ccf38c98a731a`) — the same
  reason `auto` is chosen over `bypassPermissions` above.

So `--force` is `auto` minus the classifier, not `auto`, and adopting it is an
operator decision about that one control rather than a spelling fix.

No permission flag is passed today, and a Cursor window obeys the operator's own
`~/.cursor/cli-config.json`. The cost is real and belongs here rather than in a
comment: a Cursor window can stop at a prompt, and nothing dispatches into it — which
is tolerable only because rooms have no Cursor referent anyway (`contract/boundaries`
records the room boundary as ABSENT there). `--trust` *is* passed: without it a fresh
workspace parks on a modal that is hotkey-driven, where a stray literal `q` was
measured killing the process outright.

The config file is deliberately not used as the mechanism. It is not the globalness —
it is that a session can rewrite it mid-run (`/config`, `/run-everything`, `/sandbox`
are live slash commands), so a launcher that expressed policy there would be expressing
a preference, not a constraint.

Codex spreads the same posture across two flags — `--sandbox` says what may be touched,
`--ask-for-approval` says when to ask — so a rung there sets both, and the ladder stops
below `danger-full-access` and `--dangerously-bypass-approvals-and-sandbox` for the
reason Claude Code's stops below `bypassPermissions`. Nothing is passed by default, so
a codex window rests at its own configured posture (`approval OnRequest`, restricted
filesystem and network, measured 2026-08-17) and can stop at a prompt.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from thalamus.harness.agents import HARNESSES


# The permission mode every pinned Claude Code session launches under — room member
# and solo pin alike. Operator decision (2026-08-11): this is the mode the operator
# drives by hand in every session, so a launcher that started sessions in a stricter
# one was making them behave unlike the sessions they were modelled on.
#
# `auto` rather than `bypassPermissions`, and the distinction is the whole reason this
# is not simply "turn permissions off". `auto` auto-approves while still resolving
# allow/deny rules and PreToolUse hooks *first*, then routing the remainder through a
# safety classifier; `bypassPermissions` removes the one control measured to fully stop
# prompt injection — with policy checks enabled FIDES stops all attacks in AgentDojo,
# without them every planner succumbs (`scope:literature:claim:073ccf38c98a731a`).
# So that citation is what selects `auto`, not what argues against it.
#
# In a room the mode is also load-bearing for delivery: a member stopped at a prompt
# reports `waiting`, which is exactly the status `harness/dispatch.py` refuses to send
# into, so a prompting member is an unaddressable one. That argument does not carry to
# Cursor, where there are no rooms and nothing dispatches — which is what makes leaving
# a Cursor window at its own configured posture tolerable rather than merely cheaper.
PERMISSION_MODE = "auto"


@dataclass(frozen=True)
class PolicyOption:
    """One selectable value of a capability, on one harness."""

    # Stable id. Persisted and sent over the wire, so it is never the label: renaming
    # what the panel says must not silently reinterpret a stored selection.
    value: str
    label: str
    # What choosing it contributes to the launch argv. Empty is a real answer — on both
    # harnesses the strictest rung is "pass no flag".
    argv: tuple[str, ...]
    # What this rung gives up, in the operator's terms, shown under the option at the
    # moment of choosing. Empty where it gives up nothing. This is the field the panel
    # exists for: an operator can only weigh a permission posture against its cost if
    # the cost is on screen, and "unsafe defaults exploited" is the named failure mode
    # for a capability declaration that shows only what a setting enables (MCP threat
    # survey, arXiv 2503.23278 §5.1.3).
    drops: str = ""


@dataclass(frozen=True)
class Capability:
    """One thing an operator may choose, and the values this harness offers for it.

    A *capability*, not a flag, because the harnesses do not divide the space the
    same way: Claude Code says in one `--permission-mode` what Cursor spreads across
    `--force`/`--yolo`, `--auto-review`, `--sandbox` and `--mode`. Keying the choice to
    the flag would make the panel un-renderable for Cursor and would misdescribe what
    the operator is picking, which is a posture. Same capability, different value sets
    per side — LSP's shape for a capability whose values differ per implementation
    (`scope:architect:claim:276e8d32d044a92c`).

    **`options` is ordered least- to most-permissive, and that ordering is load-bearing.**
    It is what classifies a change as narrowing or widening, which is the asymmetry the
    whole surface turns on: Progent classifies every privilege-policy update the same
    way and refuses to let a widening one pass silently, using an SMT solver because its
    policies are an open-ended DSL over tool names and arguments (arXiv 2504.11703).
    Ours is a short closed list per harness, so the ordering *is* the classification and
    no solver is needed — an instantiation of Progent's rule at a granularity that makes
    it a comparison.
    """

    key: str
    title: str
    options: tuple[PolicyOption, ...]
    # The value an operator who has chosen nothing gets. Not merely the first option:
    # today's shipped behaviour is `auto` on Claude Code and no flag at all on Cursor,
    # and a settings surface that changed what a launch does the moment it existed would
    # be a migration wearing a panel's clothes.
    default: str

    def option(self, value: str) -> PolicyOption | None:
        return next((o for o in self.options if o.value == value), None)

    def rank(self, value: str) -> int:
        """Position on the ladder, or the default's if the value is not on it.

        An unknown value cannot be ranked, and ranking it 0 would read as "the
        strictest rung" — the one answer that could let a stale or hand-edited store
        silently *widen* a posture while looking like a narrowing.
        """
        for index, option in enumerate(self.options):
            if option.value == value:
                return index
        return self.default_rank

    @property
    def default_rank(self) -> int:
        return next((i for i, o in enumerate(self.options) if o.value == self.default), 0)


# The permission posture on each harness. Claude Code's ladder deliberately stops below
# `bypassPermissions`: that mode removes the policy checks measured to stop prompt
# injection outright, so it is a decision-log change and not a rung on a panel — the
# surface must not be able to express a posture the contract argues against. Cursor's
# top rung is `--force`, and what it keeps was measured rather than assumed (2026-08-12,
# build 2026.08.11-e8db854): `permissions.deny` and the `beforeShellExecution` hooks
# both still enforce, so the role boundary does not rest on the permission mode.
PERMISSION_POSTURE = "permission_posture"

CLAUDE_PERMISSION = Capability(
    key=PERMISSION_POSTURE,
    title="Permission posture",
    options=(
        PolicyOption("manual", "Ask every time", ()),
        PolicyOption(
            "acceptEdits", "Accept edits",
            ("--permission-mode", "acceptEdits"),
            drops="Confirmation on file edits. Commands still prompt.",
        ),
        PolicyOption(
            "auto", "Auto",
            ("--permission-mode", PERMISSION_MODE),
            drops="Per-call confirmation. Allow/deny rules, PreToolUse hooks and the "
                  "safety classifier all still run.",
        ),
    ),
    default=PERMISSION_MODE,
)

CURSOR_PERMISSION = Capability(
    key=PERMISSION_POSTURE,
    title="Permission posture",
    options=(
        PolicyOption("manual", "Ask every time", ()),
        PolicyOption(
            "auto-review", "Auto-review",
            ("--auto-review",),
            drops="Confirmation on calls a server classifier rates safe. It still "
                  "stops on the rest.",
        ),
        PolicyOption(
            "force", "Run everything",
            ("--force",),
            drops="The safety classifier. permissions.deny and beforeShellExecution "
                  "hooks still enforce (measured 2026-08-12).",
        ),
    ),
    default="manual",
)

# Codex spreads the posture across two flags rather than one, which is the third
# spelling of the same capability: `--sandbox` says what the agent may touch and
# `--ask-for-approval` says when it must ask. A rung here therefore sets both, since
# an operator picking "Auto" is picking a posture and not a flag.
#
# The ladder stops below `danger-full-access` and `--dangerously-bypass-approvals-and-
# sandbox` on the same rule that stops Claude Code's below `bypassPermissions`: those
# remove the enforcement the contract argues from, so they are a decision-log change
# and not a rung on a panel. The surface must not be able to express a posture the
# contract argues against.
#
# Measured 2026-08-17 (codex-cli 0.147.0): with no flag, `codex doctor` reports the
# box's own resting posture as `approval OnRequest` + `restricted fs + restricted
# network`, so the strictest rung is again "pass nothing".
CODEX_PERMISSION = Capability(
    key=PERMISSION_POSTURE,
    title="Permission posture",
    options=(
        PolicyOption("manual", "Ask every time", ()),
        PolicyOption(
            "workspace-write", "Accept edits",
            ("--sandbox", "workspace-write"),
            drops="Confirmation on writes inside the workspace. Commands that need "
                  "more still escalate.",
        ),
        PolicyOption(
            "auto", "Auto",
            ("--sandbox", "workspace-write", "--ask-for-approval", "never"),
            drops="Per-call confirmation. The filesystem sandbox and the restricted "
                  "network still hold, and PreToolUse hooks still enforce.",
        ),
    ),
    # No flag, and deliberately not `auto` as on Claude Code. There is no shipped
    # codex launch behaviour for this panel to preserve, so the neutral choice is the
    # one that leaves the operator's own ~/.codex/config.toml governing.
    default="manual",
)


@dataclass(frozen=True)
class LaunchShape:
    """One harness's answer to "how is an interactive session started and pinned"."""

    harness: str
    binary: str
    # The flag that selects a persona, and with it the scope's MCP arming. `None` means
    # the harness has no such flag — not that we chose not to use one.
    persona_flag: str | None
    # Does `persona_flag` also tell the *hooks* which scope this is? On Claude Code it
    # does: `resolve-scope.sh` reads the agent name off the argv, so the flag is the
    # routing tag as well as the charter. On codex it does not — `--profile` selects a
    # config layer and nothing in the hook payload names it — so the scope still has to
    # reach the session through the environment.
    #
    # Kept separate from `persona_flag` because the two were fused only by coincidence
    # on the one harness that had both. Deriving "needs an env prefix" from
    # "persona_flag is None" was right while codex had no flag, and would have silently
    # dropped codex's routing tag the moment it got one.
    persona_flag_carries_scope: bool
    # Flags every launch carries. Preconditions, not policy: without `--trust` a fresh
    # Cursor workspace parks on a modal. Deliberately kept distinct from `capabilities`
    # — a precondition is not a thing to offer an operator, and putting the two in one
    # tuple is what would make the panel offer `--trust` as a choice.
    always: tuple[str, ...]
    # What an operator may choose for this harness. A capability absent here is one this
    # harness does not express, and the panel renders nothing for it rather than a
    # control that would claim the harness has a setting it does not.
    capabilities: tuple[Capability, ...]
    # How the scope reaches the session. `argv` survives `respawn-window`; `env` alone
    # does not, which is the recycle trap in the module docstring.
    pin_carrier: str
    # How long a new window of this harness must stay alive before a launcher may
    # call it started, in seconds. Sized on the measurements in the module docstring:
    # roughly 4x the slowest death this harness was seen to take.
    settle_s: float

    @property
    def pin_survives_recycle(self) -> bool:
        # Claude Code's persona flag doubles as the carrier: it rides the argv, so a
        # respawn re-selects the scope. Cursor's `env` prefix is what buys the same
        # property, and it is applied in `launch_argv` rather than assumed here.
        return self.pin_carrier == "argv"


LAUNCH_SHAPES: dict[str, LaunchShape] = {
    "claude": LaunchShape(
        harness="claude",
        binary="claude",
        persona_flag="--agent",
        persona_flag_carries_scope=True,
        always=(),
        capabilities=(CLAUDE_PERMISSION,),
        pin_carrier="argv",
        settle_s=1.2,
    ),
    "cursor": LaunchShape(
        harness="cursor",
        binary="agent",
        persona_flag=None,
        persona_flag_carries_scope=False,
        always=("--trust",),
        capabilities=(CURSOR_PERMISSION,),
        pin_carrier="argv",
        settle_s=4.0,
    ),
    "codex": LaunchShape(
        harness="codex",
        binary="codex",
        # `--profile <name>` layers `$CODEX_HOME/<name>.config.toml` over the base
        # config, and that layer carries `developer_instructions` — so the flag selects
        # a charter for the session itself, which is what a persona is. Measured live
        # 2026-08-19 (codex-cli 0.148.0): a turn run under a generated profile answered
        # from its `developer_instructions` and not from the base config.
        #
        # Not codex's *subagents* (`$CODEX_HOME/agents/*.toml`) and not its skills —
        # both are things a session may use, and neither starts one under a charter.
        # There is no `--agent` here and the flag is not a rename of one.
        persona_flag="--profile",
        # `--profile` picks the charter and the scope's MCP arming; it does not reach
        # the hooks, which read `THALAMUS_SCOPE`. So codex keeps the `env` prefix that
        # `pin_carrier` describes, and carries both.
        persona_flag_carries_scope=False,
        # Empty, and not because codex has no preconditions — because its two are not
        # flags. `--skip-git-repo-check` belongs to the headless sandbox: a roster
        # window opens in the checkout, which is a git repo, so passing it here would
        # declare a precondition this launch does not have.
        #
        # The two that do apply are **modals with no argv answer**, measured live
        # 2026-08-17, and both are one-time operator decisions rather than launch
        # policy. A directory codex has not seen parks on "Do you trust the contents of
        # this directory?", cleared by a `[projects."<repo root>"] trust_level =
        # "trusted"` entry in `$CODEX_HOME/config.toml`. A hooks.json that is new or
        # changed then parks on "Hooks need review", whose third option is *continue
        # without trusting*, under which the hooks silently never run. Nothing here
        # bypasses either: `--dangerously-bypass-hook-trust` exists and is a
        # supply-chain control to answer, not to route around from a launcher.
        always=(),
        capabilities=(CODEX_PERMISSION,),
        pin_carrier="argv",
        # Measured 2026-08-17 (codex-cli 0.147.0): a window given an unknown flag dies
        # in 0.13s and one given an unreachable CODEX_HOME in 0.12s — 4x the slowest of
        # those is half a second. Set at Claude Code's 1.2s anyway, because only three
        # death modes were enumerated and a fourth candidate does not belong to this
        # class at all: an unknown `--model` does not kill the window, it survives and
        # fails at the first turn. Over-waiting costs a slower spawn; under-waiting
        # reports a corpse as a started session.
        settle_s=1.2,
    ),
}

# One table, one list: a harness in the agent registry with no launch shape would be
# spawnable headlessly and unpinnable interactively, which is the asymmetry this
# module exists to make visible.
assert set(LAUNCH_SHAPES) == set(HARNESSES), "every harness needs a launch shape"


def settle_s(harness: str) -> float:
    """How long a new window of `harness` has to survive to count as started.

    Unknown harnesses get the longest window any known one asks for: a launcher that
    cannot look up the shape still must not report a death as a success.
    """
    shape = LAUNCH_SHAPES.get(harness)
    if shape is not None:
        return shape.settle_s
    return max(s.settle_s for s in LAUNCH_SHAPES.values())


def capability_argv(harness: str, selections: Mapping[str, str] | None = None) -> list[str]:
    """What the operator's chosen posture contributes to a launch.

    An unknown capability key or an unknown value falls back to the capability's own
    default rather than raising: the store is a file on disk that a future release may
    have written differently, and the failure mode for a stale entry has to be "launch
    at the default" and not "the roster will not start".
    """
    shape = LAUNCH_SHAPES.get(harness)
    if shape is None:
        return []
    chosen = selections or {}
    argv: list[str] = []
    for capability in shape.capabilities:
        value = chosen.get(capability.key, capability.default)
        option = capability.option(value) or capability.option(capability.default)
        if option is not None:
            argv += list(option.argv)
    return argv


def launch_argv(
    harness: str,
    scope: str,
    *,
    persona: str | None = None,
    selections: Mapping[str, str] | None = None,
) -> list[str]:
    """The argv for one pinned interactive session, pin included.

    `persona` is the derived agent name for harnesses that have a selector, and is
    ignored by those that do not — the caller writes the agent file either way, since
    on Cursor the same file is readable as a *subagent* from a workspace even though
    no flag selects it for the main session.

    The scope is prefixed with `env` rather than left to the window's environment on
    every harness whose pin does not otherwise ride the argv. It costs one process and
    closes the recycle trap.

    **`selections` defaults to the stored launch policy, read here rather than passed
    in.** Threading it through every caller instead would put it on the two launch
    paths that remembered and leave it off the ones that did not — the divergence
    `pin.launch_flags` already names, where a flag added to one path and not the other
    is a difference nothing reports. Passing it explicitly is for tests and for a
    caller that genuinely means "ignore what is stored".

    The posture reaches the session on the argv and nowhere else. It is deliberately
    never written to the harness's own config file: that file is state the sessions
    themselves rewrite mid-run, so a launcher expressing policy there would be
    expressing a preference rather than a constraint (see the module docstring), and
    argv is also the only carrier that survives `respawn-window`.
    """
    shape = LAUNCH_SHAPES.get(harness)
    if shape is None:
        raise ValueError(
            f"no launch shape for harness `{harness}` — it can be invoked headlessly "
            f"(harness/agents.py) but not pinned"
        )

    if selections is None:
        from thalamus.harness.launch_policy import effective
        selections = effective(harness)

    argv = [shape.binary]
    if shape.persona_flag and persona:
        argv += [shape.persona_flag, persona]
    argv += list(shape.always)
    argv += capability_argv(harness, selections)

    if not shape.persona_flag_carries_scope:
        # Nothing on this argv *names the scope to the hooks*, so a `respawn-window`
        # would re-exec it with the window's `-e` environment gone. The prefix is the
        # carrier. Codex takes it despite having a persona flag: `--profile` restores
        # the charter on a recycle but tells `resolve-scope.sh` nothing.
        return ["env", f"THALAMUS_SCOPE={scope}", *argv]
    return argv
