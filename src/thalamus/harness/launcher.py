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
two on the other.

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
exists is that it is still alive some time later (docs/console-hazards §4). How much
later is a per-harness fact, because the two CLIs fail at different depths:

| launch | outcome | measured |
|---|---|---|
| `claude`, missing binary | dies, status 127 | 0.010 s |
| `claude`, rejected flag | dies, status 1 | 0.278 s |
| `claude`, untrusted dir / bad API key / no credentials | **lives** — parks on a modal | alive at 30 s |
| `agent`, untrusted dir / no credentials | **lives** — parks on a modal | alive at 30 s |
| `agent`, rejected API key | dies, status 1 | 1.07–1.14 s (n=9) |
| `agent`, rejected API key, +2 s of proxy latency | dies, status 1 | 3.14–3.20 s (n=3) |

Claude Code decides everything that can kill it locally, so a fraction of a second
covers it. Cursor's one measured death is an **authentication rejection**, which
resolves only after a round trip to its API — the last two rows are the same failure
under two network conditions, and the time to it moved by exactly the added latency.
So `settle_s` is a bet sized on a measurement, not a bound: a deadline covers the
death modes whose cost is local, and buys headroom against a network leg that has
none. A death after the deadline is reported by nothing; the window list is what
shows it.

## Permission posture

Claude Code launches every pinned window with `--permission-mode auto`, chosen so a
member never sits at a prompt (a prompting member reports `waiting`, which dispatch
refuses to send into). Cursor has **no equivalent that keeps that property**:
`--auto-review` is the nearest architecture — a server classifier auto-runs safe calls
— and it *prompts on the remainder*, so it stalls exactly where `auto` does not. The
only non-stalling option is `--force`/`--yolo` ("Run Everything"), which is strictly
more permissive than `auto` rather than equivalent to it.

So no permission flag is passed, and a Cursor window obeys the operator's own
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
"""

from __future__ import annotations

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
# So the citation docs/12 rests on is what selects `auto`, not what argues against it.
#
# In a room the mode is also load-bearing for delivery: a member stopped at a prompt
# reports `waiting`, which is exactly the status `harness/dispatch.py` refuses to send
# into, so a prompting member is an unaddressable one. That argument does not carry to
# Cursor, where there are no rooms and nothing dispatches — which is what makes leaving
# a Cursor window at its own configured posture tolerable rather than merely cheaper.
PERMISSION_MODE = "auto"


@dataclass(frozen=True)
class LaunchShape:
    """One harness's answer to "how is an interactive session started and pinned"."""

    harness: str
    binary: str
    # The flag that selects a persona, and with it the scope's MCP arming. `None` means
    # the harness has no such flag — not that we chose not to use one.
    persona_flag: str | None
    # Flags every launch carries. Preconditions, not policy: without `--trust` a fresh
    # Cursor workspace parks on a modal.
    always: tuple[str, ...]
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
        always=("--permission-mode", PERMISSION_MODE),
        pin_carrier="argv",
        settle_s=1.2,
    ),
    "cursor": LaunchShape(
        harness="cursor",
        binary="agent",
        persona_flag=None,
        always=("--trust",),
        pin_carrier="argv",
        settle_s=4.0,
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


def launch_argv(harness: str, scope: str, *, persona: str | None = None) -> list[str]:
    """The argv for one pinned interactive session, pin included.

    `persona` is the derived agent name for harnesses that have a selector, and is
    ignored by those that do not — the caller writes the agent file either way, since
    on Cursor the same file is readable as a *subagent* from a workspace even though
    no flag selects it for the main session.

    The scope is prefixed with `env` rather than left to the window's environment on
    every harness whose pin does not otherwise ride the argv. It costs one process and
    closes the recycle trap.
    """
    shape = LAUNCH_SHAPES.get(harness)
    if shape is None:
        raise ValueError(
            f"no launch shape for harness `{harness}` — it can be invoked headlessly "
            f"(harness/agents.py) but not pinned"
        )

    argv = [shape.binary]
    if shape.persona_flag and persona:
        argv += [shape.persona_flag, persona]
    argv += list(shape.always)

    if shape.persona_flag is None:
        # Nothing on this argv names the scope, so a `respawn-window` would re-exec it
        # with the window's `-e` environment gone. The prefix is the carrier.
        return ["env", f"THALAMUS_SCOPE={scope}", *argv]
    return argv
