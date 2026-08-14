"""Every tmux invocation must name the socket it is talking to.

tmux is the one surface that ignores `HOME` completely. Measured:
`HOME=/tmp/anything tmux list-sessions` returns the operator's real session list,
because tmux locates its server through `/tmp/tmux-<uid>/` (or `$TMUX_TMPDIR`), not
through the home directory.

Nothing in `src/` passes `-L` (socket name) or `-S` (socket path). So `thalamus roster`,
`pin --spawn`, `dispatch` and the console's `/api/key` and `/api/send` all address
whatever tmux server the box happens to be running — which is the operator's live
control plane, with real pinned sessions in it.

Two consequences, and the second is why this is filed as a boundary leak rather than a
testing inconvenience:

1. No deep-tier case can exercise rooms, dispatch or the roster without either driving
   the operator's real sessions or being unable to run at all. There is no third option
   today, and `--isolate-store` does not provide one: it is a Docker network-mode switch
   and the arm-runner image installs no tmux at all.
2. Independently of testing, two concurrent Thalamus checkouts on one box share a
   control plane with no way to separate them.

Asserted over the source rather than by driving tmux, deliberately. The behavioural
version would have to spawn a server to prove isolation is absent, which means creating
the very entanglement it is testing for. Reading the invocation sites is hermetic, needs
no tmux, and names the exact call that has to change.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SRC = Path(__file__).resolve().parents[3] / "src" / "thalamus"

# The argv-construction sites: a list literal or call whose first element is the tmux
# binary. Matches `["tmux", ...]`, `("tmux", ...)` and `"tmux", "..."` inside a call.
_INVOCATION = re.compile(r"""["']tmux["']\s*,\s*(?P<rest>[^\]\)]{0,200})""")

# Quoted argv elements, in order. Needed because a socket flag is only a socket flag in
# one position, and an unordered search cannot tell that position from any other.
_TOKEN = re.compile(r"""["']([^"']*)["']""")


def _socket_scoped(rest: str) -> bool:
    """Does this invocation name a socket — in the only place tmux would read one?

    `tmux [-L name | -S path] <command> [args]`: the socket flag is a *server* option and
    must precede the command word. A search for `-L`/`-S` anywhere in the argv is not the
    same question, and the difference is not hypothetical — `pin.py:807` builds
    `tmux capture-pane -p -J -S - -t <window>`, where `-S` is capture-pane's start-line
    flag asking for scrollback history. An unordered search read that as a scoped call and
    reported `16/17 unscoped` against a true 17/17, which is a false negative in the
    direction that matters: it credits the code with an isolation it does not have, on the
    one surface `HOME` cannot redirect.

    So tokens are walked from the front and the walk stops at the command word. A flag's
    value is consumed with it, so `-L` in `tmux kill-session -t -L` (a session literally
    named `-L`) is not mistaken for scoping either.
    """
    tokens = _TOKEN.findall(rest)
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in ("-L", "-S"):
            return True
        if token.startswith("-"):
            index += 2          # a server option and its value
            continue
        return False            # the command word — server options are over
    return False


def run() -> Finding | None:
    if not _SRC.is_dir():
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="source tree not found, so 'no unscoped invocation' and 'nothing "
                    "scanned' are the same result",
            witness=str(_SRC),
            site="tests/qe/cases/tmux_socket.py",
        )

    unscoped: list[str] = []
    total = 0
    for path in sorted(_SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in _INVOCATION.finditer(text):
            total += 1
            if _socket_scoped(match.group("rest")):
                continue
            line = text[: match.start()].count("\n") + 1
            verb = match.group("rest").strip().split(",")[0][:40]
            unscoped.append(f"{path.relative_to(_SRC.parents[1])}:{line} tmux {verb}")

    # POSITIVE CONTROL: the scan must have found tmux invocations at all. A regex that
    # silently matches nothing reports perfect scoping, which is the exact shape of the
    # defect class this suite is named for.
    if total == 0:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the scan found zero tmux invocations, so a clean result here would "
                    "mean the pattern stopped matching rather than that scoping was added",
            witness=f"scanned {_SRC}, matched 0 invocation sites",
            site="tests/qe/cases/tmux_socket.py::_INVOCATION",
        )

    if not unscoped:
        return None

    shown = unscoped[:8]
    more = f" (+{len(unscoped) - len(shown)} more)" if len(unscoped) > len(shown) else ""
    # The count leads the WITNESS, not just the summary. Expectations pin on the witness
    # (see expectations.py), and the count is the value worth pinning: scoping any subset
    # of these calls changes it, which drifts the entry and goes red rather than quietly
    # shrinking under an unchanged acknowledgement. Pinning it in the summary instead —
    # the first attempt — silently never matched.
    return Finding(
        failure_class=FailureClass.BOUNDARY_LEAK,
        summary=(
            f"{len(unscoped)} of {total} tmux invocations name no socket, so they address "
            "whatever server the box is running — the operator's live control plane. "
            "tmux ignores HOME, so no environment redirection can separate them"
        ),
        witness=f"{len(unscoped)}/{total} unscoped; " + "; ".join(shown) + more,
        site="src/thalamus/** (tmux argv construction)",
    )


CASE = Case(
    name="tmux-invocations-name-their-socket",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.COLLAPSED_SENTINEL),
    summary="tmux calls must be socket-scoped; HOME redirection cannot isolate them",
    run=run,
)
