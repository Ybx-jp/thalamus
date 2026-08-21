"""
The named tmux server: which one this checkout addresses, and how it knows.

Interfaces: thalamus.harness.tmux
Infrastructure: environment only — no tmux server, no windows, no graph.
Scope: the resolver, not the control plane. Whether a socket-scoped argv actually
reaches its own server is exercised live in `test_spawn_settle.py`, which builds a
roster on a private socket and would drive the operator's real one if this were wrong.

tmux is the one surface `HOME` cannot redirect — it finds its server through
`/tmp/tmux-<uid>/`, so the socket name is the whole of the isolation and these are the
tests that keep it from silently becoming decorative.
"""

import pytest

from thalamus.harness import tmux


def test_the_socket_defaults_to_a_name_rather_than_the_boxs_default_server(monkeypatch):
    """An empty default would be the unscoped behaviour wearing a flag."""
    monkeypatch.delenv(tmux.SOCKET_ENV, raising=False)

    assert tmux.socket_name() == tmux.DEFAULT_SOCKET
    assert tmux.argv("list-windows")[:3] == ["tmux", "-L", tmux.DEFAULT_SOCKET]


def test_the_socket_is_read_at_call_time(monkeypatch):
    """Not captured at import: the resolver is shared by processes that set it late.

    A value frozen at import would let a test set the variable and then address the
    server it was trying to stay off — the failure this whole module exists to close.
    """
    monkeypatch.setenv(tmux.SOCKET_ENV, "checkout-a")
    assert tmux.argv("kill-server")[2] == "checkout-a"

    monkeypatch.setenv(tmux.SOCKET_ENV, "checkout-b")
    assert tmux.argv("kill-server")[2] == "checkout-b"


def test_the_socket_flag_precedes_the_command_word():
    """`-L` is a *server* option; tmux does not read one after the command.

    Asserted positionally because an unordered search cannot tell a server option from
    a command's own flag — `capture-pane -p -J -S -` carries a `-S` that is a scrollback
    request and scopes nothing.
    """
    argv = tmux.argv("capture-pane", "-p", "-J", "-S", "-", "-t", "%1")

    assert argv.index("-L") < argv.index("capture-pane")


@pytest.mark.parametrize("handle, socket, expected", [
    ("/tmp/tmux-1000/thalamus,4242,0", "thalamus", True),
    ("/tmp/tmux-1000/default,4242,0", "thalamus", False),
    ("/tmp/tmux-1000/other-checkout,4242,0", "other-checkout", True),
    ("", "thalamus", False),
])
def test_inside_asks_which_server_not_whether_any(monkeypatch, handle, socket, expected):
    """A bare truth test on `$TMUX` answers "some tmux", which is the wrong question.

    An operator sitting in a default-socket tmux who runs `thalamus roster` would
    otherwise be treated as already inside the roster, and the windows would open on a
    server they are not looking at.
    """
    monkeypatch.setenv(tmux.SOCKET_ENV, socket)
    if handle:
        monkeypatch.setenv("TMUX", handle)
    else:
        monkeypatch.delenv("TMUX", raising=False)

    assert tmux.inside() is expected


def test_the_attach_hint_names_the_socket_it_would_need(monkeypatch):
    """`thalamus roster` prints this line, so a wrong one is a wrong instruction."""
    monkeypatch.setenv(tmux.SOCKET_ENV, "checkout-b")

    assert tmux.attach_hint("thalamus") == "tmux -L checkout-b attach -t thalamus"
