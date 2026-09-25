"""Dump the cell's whole graph as JSON: every vertex and every edge, with properties.

Runs inside a cell, under the checkout's own venv, against the cell's own graph on its
loopback — never against an operator's. A cell's graph holds a few hundred elements,
so the whole of it is the evidence rather than a query someone chose in advance: the
oracle on the host decides what to look for, and can be changed without a re-run.

Usage: graph_dump.py <out.json>
"""

from __future__ import annotations

import json
import sys

from gremlin_python.process.traversal import T

from thalamus.substrate.writer import close_connection, connect


def _plain(value):
    if isinstance(value, dict):
        return {str(k if not isinstance(k, T) else k.name): _plain(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def main(out: str) -> int:
    g = connect()
    try:
        vertices = [_plain(v) for v in g.V().element_map().to_list()]
        edges = []
        for e in g.E().element_map().to_list():
            row = _plain(e)
            # element_map on an edge carries its endpoints as Direction-keyed maps.
            ends = {str(k): v for k, v in e.items() if str(k) in ("Direction.OUT",
                                                                    "Direction.IN")}
            row["out"] = _plain(ends.get("Direction.OUT", {})).get("id")
            row["in"] = _plain(ends.get("Direction.IN", {})).get("id")
            edges.append(row)
    finally:
        close_connection(g)
    with open(out, "w") as fh:
        json.dump({"vertices": vertices, "edges": edges}, fh, indent=1)
    print(f"{len(vertices)} vertices, {len(edges)} edges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
