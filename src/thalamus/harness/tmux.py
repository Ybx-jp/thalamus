"""The one place a tmux argv is built, and the reason it has to be one place.

tmux is the single surface `HOME` cannot redirect. `HOME=/tmp/anything tmux
list-sessions` returns the operator's real session list, because tmux finds its
server through `/tmp/tmux-<uid>/` (or `$TMUX_TMPDIR`) and never through the home
directory. So an unscoped `tmux` call addresses whatever server the box happens to be
running — which on this box is the operator's live control plane, with real pinned
sessions in it.

`-L <name>` names the server, and naming it buys two things:

1. The roster, `spawn`, `dispatch` and the console's `/api/key` and `/api/send` all
   address a server this project owns. A test, a second checkout, or a stray script
   cannot reach into a live roster by accident, and a deep-tier case can drive the
   control plane on its own socket instead of choosing between driving the operator's
   sessions and not running.
2. Two concurrent Thalamus checkouts on one box get separate control planes by setting
   `THALAMUS_TMUX_SOCKET`.

The socket is a *server* option and tmux only reads it before the command word, so it
belongs in the argv prefix and nowhere else. Every caller goes through `argv()`; a
hand-built tmux argv anywhere else in `src/` is the defect this module exists to close,
and `tests/qe/cases/tmux_socket.py` reads the source to say so — it counts argv
construction sites, so this file is expected to be the only one it finds.
"""

from __future__ import annotations

import os

SOCKET_ENV = "THALAMUS_TMUX_SOCKET"

# Named rather than empty. An empty default would mean "the box's default server",
# which is the unscoped behaviour wearing a flag, and it would make the isolation
# depend on every caller remembering to set the variable. The roster therefore lives
# on its own server: `tmux -L thalamus attach -t thalamus`, and `thalamus roster`
# prints that line.
DEFAULT_SOCKET = "thalamus"


def socket_name() -> str:
    """The tmux server this checkout addresses.

    Read on each call, not captured at import: the console, the CLI and the hooks are
    separate processes, and a value frozen at import time would let a test that sets
    the variable address a server the code under test does not.
    """
    return os.environ.get(SOCKET_ENV) or DEFAULT_SOCKET


def argv(*args: str) -> list[str]:
    """`tmux -L <socket> <args...>` — the only tmux argv this package builds."""
    return ["tmux", "-L", socket_name(), *args]


def inside() -> bool:
    """Is this process running in a client of *our* server?

    `$TMUX` is `<socket-path>,<server-pid>,<session-id>`, and a bare truth test on it
    answers a different question — "some tmux" — which was the same answer before the
    server was named and is the wrong one now. An operator sitting in a default-socket
    tmux who runs `thalamus roster` would otherwise be treated as already inside the
    roster, and the windows would open on a server they are not looking at.
    """
    handle = os.environ.get("TMUX", "")
    if not handle:
        return False
    return os.path.basename(handle.split(",")[0]) == socket_name()


def attach_hint(session: str) -> str:
    """The command line that attaches to `session` — printed, so it must be exact."""
    return f"tmux -L {socket_name()} attach -t {session}"
