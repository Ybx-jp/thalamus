"""What "pinned" covers on each harness — a second record, deliberately not a row.

`boundaries.py` answers "does this boundary bind here". This answers "can a session on
this harness be pinned at all, and to what extent" — a different subject, and the
lesson that produced both records is that a record with two subjects reports one of
them wrongly. The hook-wiring parity claim went stale precisely because it was read for
an obligation while its subject was two tables.

The claim this record exists to stop being prose: **every Cursor boundary row in
`boundaries.py` carries an undeclared precondition — that something set the scope.**
Until a launcher existed, that something was the operator, by hand, in three sessions.
An enforcement claim over that population is a demonstration, not a rate.

Pinning is not one property. On Claude Code `--agent thalamus-<scope>` fuses four —
persona, per-scope MCP arming, the routing tag, and (because it rides the argv)
survival through a window recycle — and the fusion is why nobody noticed they were
separable until a harness arrived that carries two of them and not the others. Each is
a row, so no row can bundle a true claim with a false one.
"""

from __future__ import annotations

from dataclasses import dataclass

from thalamus.contract.boundaries import Evidence, Provision
from thalamus.contract.probes import Condition

# What each component means, in the register a reader acts on.
COMPONENTS: dict[str, str] = {
    "pin.launcher": "a command exists that opens a pinned session on this harness",
    "pin.routing": "the scope reaches the session, so memory and distillation attribute to it",
    "pin.boundary": "the manifest's boundaries bind in the launched session",
    "pin.persona": "the scope's charter is in the session's own context",
    "pin.mcp_arming": "the scope's declared MCP servers are armed for that session",
    "pin.recycle_survival": "the pin survives `respawn-window` — the console's restart button",
}


@dataclass(frozen=True)
class PinRow:
    component: str
    harness: str
    state: Provision
    evidence: Evidence
    note: str

    @property
    def label(self) -> str:
        return f"{self.component} on {self.harness}"


_CLAUDE = Evidence(
    kind="source-read",
    at="2026-08-12",
    where="pin.launch/spawn build `--agent thalamus-<scope> --permission-mode auto`; "
          "the derived agent file carries the charter and the scope's MCP servers",
    verified_against="pin.py",
    conditions=(),
    reask="free",
)

_CURSOR_BUILD = "cursor/2026.08.11-e8db854"
_CURSOR_COND = (Condition.PARSE, Condition.PRINT, Condition.INTERACTIVE)


def _cursor(where: str, *, conditions=_CURSOR_COND) -> Evidence:
    return Evidence(
        kind="live-session",
        at="2026-08-12",
        where=where,
        verified_against=_CURSOR_BUILD,
        conditions=conditions,
        reask="live-session",
    )


PIN_ROWS: tuple[PinRow, ...] = (
    PinRow("pin.launcher", "claude", Provision.PROVIDED, _CLAUDE,
           "`thalamus pin` and `thalamus spawn`, and the console's spawn sheet over them."),
    PinRow("pin.routing", "claude", Provision.PROVIDED, _CLAUDE,
           "`--agent` is resolved ahead of the environment, so the picker cannot "
           "silently disagree with the window (that disagreement mis-armed three "
           "sessions once)."),
    PinRow("pin.boundary", "claude", Provision.PROVIDED, _CLAUDE,
           "See `boundaries.py`; the guard loads the manifest once the scope resolves."),
    PinRow("pin.persona", "claude", Provision.PROVIDED, _CLAUDE,
           "The derived agent file's charter is the session's system prompt."),
    PinRow("pin.mcp_arming", "claude", Provision.PROVIDED, _CLAUDE,
           "Per-scope, through the agent file's frontmatter rather than a launch flag, "
           "so every route to the agent arms the same servers."),
    PinRow("pin.recycle_survival", "claude", Provision.PROVIDED, _CLAUDE,
           "`--agent` rides the argv, so `respawn-window` re-selects the scope."),

    PinRow("pin.launcher", "cursor", Provision.PROVIDED,
           _cursor("`thalamus pin --harness cursor` opens a tmux window running "
                   "`env THALAMUS_SCOPE=<scope> agent --trust`; an interactive "
                   "session launched this way fired `sessionStart` with the scope in "
                   "the hook's environment"),
           "New. Before it, every enforcement claim about Cursor rested on a "
           "hand-exported variable in three sessions."),
    PinRow("pin.routing", "cursor", Provision.PROVIDED,
           _cursor("`sessionStart` fired in an interactive tmux-launched session "
                   "carrying `THALAMUS_SCOPE=qe`; the pin ledger took its row"),
           "Environment only — Cursor has no agent picker, so there is no second "
           "channel to disagree with and nothing to reconcile."),
    PinRow("pin.boundary", "cursor", Provision.PROVIDED,
           _cursor("a `qe`-pinned session's `Write` to `*/src/*` was blocked, the file "
                   "unchanged, with a `role-boundary` block row in the ledger"),
           "Through the vendor's own settings.json translation — `boundaries.py` "
           "records the write boundary as NATIVE and the capability boundary as "
           "vacuous, so this row is narrower than its Claude Code twin."),
    PinRow("pin.persona", "cursor", Provision.ABSENT,
           Evidence(
               kind="flag-probe",
               at="2026-08-12",
               where="the parser rejects `--agent`; the only system-prompt flag is "
                     "`--system-prompt <file>`, hidden from `--help` and marked "
                     "\"Anysphere/OpenAI team only\" in the vendor's bundle",
               verified_against=_CURSOR_BUILD,
               conditions=(Condition.PARSE,),
               # A sentinel probe re-asks this offline, so it is not one of the rows
               # that goes quiet: if a Cursor release ever adds `--agent`, this is the
               # row that says the persona decision can be revisited.
               reask="free",
           ),
           "So a pinned Cursor session routes and is bounded and does not think like "
           "the expert. Naming that is the point of this record: `pinned` covers four "
           "things on one harness and three on the other."),
    PinRow("pin.mcp_arming", "cursor", Provision.NATIVE,
           _cursor("the agent-file parser returns name/description/tools/model/prompt/"
                   "permissionMode and drops `mcpServers`; servers come from "
                   "`~/.cursor/mcp.json` and the workspace's own, which `thalamus "
                   "init` writes",
                   conditions=(Condition.PARSE,)),
           "Global rather than per-scope, and already armed by the installer — so "
           "there is nothing for a launcher to pass and passing something would be "
           "a second definition for one server to disagree with."),
    PinRow("pin.recycle_survival", "cursor", Provision.PROVIDED,
           Evidence(
               kind="derivation",
               at="2026-08-12",
               where="the launcher's argv carries `THALAMUS_SCOPE=<scope>` as an `env` "
                     "prefix. Measured both arms in a throwaway tmux session whose "
                     "session env holds `THALAMUS_SCOPE=main`, as the roster's does: "
                     "with the prefix `qe` survived `respawn-window`, without it the "
                     "window came back as `main`",
               verified_against="harness/launcher.LAUNCH_SHAPES",
               conditions=(),
               # The property belongs to our argv, not to the vendor — `env` is POSIX.
               # So this row is recomputed on every check rather than trusted.
               reask="free",
           ),
           "The failure it prevents is silent and phone-triggered: the console's "
           "restart button would have turned a bounded window into an unbounded one, "
           "because the guard short-circuits on `main` before loading a manifest."),
)


def check_pinning() -> list[tuple[PinRow, str, str]]:
    """Re-ask what can be re-asked. Returns (row, outcome, detail).

    The Claude Code rows are recomputed against the launch shape rather than believed;
    the Cursor rows need a live session and say so, exactly as the boundary rows do.
    """
    from thalamus.contract.probes import FlagProbe, Outcome, probe_flag
    from thalamus.harness.launcher import LAUNCH_SHAPES, launch_argv

    results = []
    for row in PIN_ROWS:
        if row.evidence.reask != "free":
            results.append((row, "unprobeable",
                            f"needs a live session against {row.evidence.verified_against}"))
            continue
        shape = LAUNCH_SHAPES.get(row.harness)
        if shape is None:
            results.append((row, "drift", f"no launch shape for `{row.harness}`"))
            continue

        if row.component == "pin.persona":
            # Ask the parser rather than re-reading our own table: the whole point of
            # this row is that a vendor could add `--agent` and nobody would notice.
            probe = probe_flag(FlagProbe(shape.binary, "--agent", ("x",)),
                               declared=shape.persona_flag is not None)
            if probe.outcome is Outcome.CONFIRMED:
                results.append((row, "confirmed", ""))
            elif probe.outcome is Outcome.DRIFT:
                results.append((row, "drift", f"`{shape.binary} --agent`: {probe.detail}"))
            else:
                results.append((row, probe.outcome.value, probe.detail))
            continue

        if row.component == "pin.recycle_survival":
            # The argv is the carrier, so read the argv — not the flag that was
            # supposed to produce it.
            argv = launch_argv(row.harness, "probe-scope", persona="probe-persona")
            observed = any("THALAMUS_SCOPE=probe-scope" == part for part in argv) or (
                shape.persona_flag is not None
                and shape.persona_flag in argv
            )
        else:
            observed = True

        expected = row.state is Provision.PROVIDED
        results.append((row, "confirmed", "") if observed == expected else (
            row, "drift",
            f"declared {row.state.value}, but the launch argv "
            f"{'carries' if observed else 'does not carry'} the scope",
        ))
    return results
