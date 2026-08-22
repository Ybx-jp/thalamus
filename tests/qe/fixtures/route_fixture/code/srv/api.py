"""The server half. Five routes by literal equality, in both operand orders.

One route no scanned client calls. One route outside the declared prefix, which must be
invisible rather than collected and then reported as called by nobody. Two routing forms
the `exact-literal` matcher cannot resolve — a prefix test and a membership table — each
of which must be named as a gap, because an unreported route form turns an
unmatched-call finding into a false accusation.

The module-level import of `store` gives the import channel an edge, so the merged
propagation cost is a reading over both channels rather than the route channel alone.
"""

from srv import store

EXTRA = {"/panel.html": "panel", "/style.css": "style"}


def route(path):
    if path == "/api/alpha":
        return store.alpha()
    if path == "/api/beta":
        return store.beta()
    if path == "/api/gamma/leaf":
        return store.leaf()
    if "/api/delta" == path:
        return store.delta()
    if path == "/api/orphan":
        # Defined, and no scanned client calls it. The scan may report that; it may not
        # call the route dead, because the declared client set is not the caller set.
        return store.orphan()
    if path == "/health":
        # Outside the declared prefix. The client matcher structurally cannot see a call
        # to it, so collecting it would manufacture an uncalled-route finding.
        return store.health()
    if path.startswith("/frame/"):
        return store.frame(path)
    if path in EXTRA:
        return EXTRA[path]
    return None
