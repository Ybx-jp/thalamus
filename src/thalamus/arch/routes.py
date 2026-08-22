"""Extract the dependency an HTTP boundary hides, under a policy it declares.

An import extractor cannot see the console. `static/app.js` reaches
`console/server.py` by issuing requests at runtime, so a Python-only walk reports the
browser surface as absent and the server as depended on by nobody outside the package.
That silence is not neutral: it publishes a propagation cost over the Python half as
though it were a fact about the system.

**Why this channel is extractable and the co-change channel is not.** Both endpoints
here are string literals in this repo, compared for equality. Measured at
`7c685da`: 23 distinct `api/…` literals in the client, 23 `path == "/api/…"` literals
in the server, 23 matched, none unmatched on either side. That is precision and recall
1.0 against a hand check, not an estimate — the design's standing objection to shipping
a signal with unmeasured precision does not apply, and the reason it does not apply is
that this server routes by literal equality. A server that routed by prefix, regex or
decorator would need a different matcher and would earn a different precision number
before any edge it produced could be counted.

**One edge, not twenty-three.** The graph's node is a file, so twenty-three literals
between the same two files are one dependency. The literals are not discarded — they
are what the match is evidence of, and an unmatched one on either side is a finding in
its own right: a client calling a route the server does not define is a defect, and a
route no client calls is dead surface.

**Runtime depth is not deferred depth.** A route edge executes when a request is made,
which is neither import time nor a deferred import; `import_depth` therefore does not
govern it, and `counts_edge` says so explicitly rather than letting a module-level
reading silently drop the whole channel.

**What this deliberately does not reach.** `sw.js` names `app.js`, `style.css` and
`index.html` as cache entries — real dependencies through a third mechanism, asset
reference, which this channel does not extract and does not pretend to. The scanned
client set is declared, so a file that is not in it is out of the measurement by policy
rather than by accident.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from thalamus.arch.extractor import (
    DEPTH_RUNTIME,
    KIND_ROUTE,
    DependencyEdge,
    DependencyGraph,
)

# The only matcher implemented. Named in the policy so a scan says which one produced
# it, and so adding a second cannot silently change what an old number meant.
MATCH_EXACT_LITERAL = "exact-literal"

def _client_literal(prefix: str) -> re.Pattern[str]:
    """Client-side literals under the declared prefix.

    A literal ends at the first query string or template substitution, which is not a
    style choice: `console/server.py` splits on `?` before it compares, so truncating
    here reproduces the server's own tokenisation rather than guessing at it.
    """
    stem = re.escape(prefix.strip("/"))
    return re.compile(r"""["'`](/?""" + stem + r"""/[A-Za-z0-9/_-]*)""")


def _server_literal(prefix: str) -> re.Pattern[str]:
    """Server-side equality against a literal, in either operand order.

    Bound to the same declared prefix as the client pattern. An unbounded server
    pattern would collect routes the client matcher structurally cannot call and then
    report each one as called by nobody — a finding manufactured by the asymmetry
    rather than by the code.
    """
    stem = re.escape(prefix.strip("/"))
    literal = r"""["'](/""" + stem + r"""/[A-Za-z0-9/_-]+)["']"""
    return re.compile(rf"""(?:path\s*==\s*{literal}|{literal}\s*==\s*path)""")


# Routing forms this matcher does NOT resolve, each reported as a gap in the scan's
# reach. An unreported route of these shapes would make an unmatched-call finding a
# false accusation, so the detector covers every form the scanned servers actually use:
# prefix tests and membership tables alike.
_SERVER_INEXACT = re.compile(
    r"""path\.startswith\(\s*["']([A-Za-z0-9/_.-]+)["']"""
    r"""|path\s+in\s+([A-Za-z_][A-Za-z0-9_]*)"""
)


@dataclass(frozen=True)
class RoutePolicy:
    """The declared rules the route channel was measured under. Digested separately.

    Its own block and its own digest, so the import measurement's key does not move
    when this channel changes. The scan key combines the two only when this channel is
    enabled — see `model.scan_id` — which keeps every scan taken before it valid.
    """

    version: int = 2
    enabled: bool = False
    # Authored, not globbed. The element set must not be a function of what the matcher
    # happened to find: a glob plus a "had literals" test makes a recall failure remove
    # a file from numerator and denominator at once, so the miss is invisible in the
    # number it moves. Naming the clients makes the element set a declaration.
    clients: tuple[str, ...] = (
        "src/thalamus/console/static/app.js",
        "src/thalamus/console/static/sw.js",
    )
    servers: tuple[str, ...] = ("src/thalamus/console/server.py",)
    match: str = MATCH_EXACT_LITERAL
    prefix: str = "/api/"

    def block(self) -> dict[str, object]:
        """The policy as it appears in `arch/model.yaml`, without its own digest."""
        return {
            "version": self.version,
            "enabled": self.enabled,
            "clients": list(self.clients),
            "servers": list(self.servers),
            "match": self.match,
            "prefix": self.prefix,
        }

    def digest(self) -> str:
        """sha256 over the canonically serialised block, as the import policy does."""
        canonical = json.dumps(self.block(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def from_block(cls, block: dict) -> RoutePolicy:
        """Rebuild a policy from a model file's `routes:` mapping."""
        defaults = cls()
        return cls(
            version=int(block.get("version", defaults.version)),
            enabled=bool(block.get("enabled", defaults.enabled)),
            clients=tuple(block.get("clients", defaults.clients)),
            servers=tuple(block.get("servers", defaults.servers)),
            match=str(block.get("match", defaults.match)),
            prefix=str(block.get("prefix", defaults.prefix)),
        )


@dataclass
class RouteGraph:
    """What the route walk saw: literals per file, and what they matched."""

    clients: dict[str, set[str]] = field(default_factory=dict)
    servers: dict[str, set[str]] = field(default_factory=dict)
    unresolved: list[str] = field(default_factory=list)
    policy: RoutePolicy = field(default_factory=RoutePolicy)

    def defined(self) -> set[str]:
        """Every route the scanned servers define."""
        return {route for routes in self.servers.values() for route in routes}

    def called(self) -> set[str]:
        """Every route the scanned clients call."""
        return {route for routes in self.clients.values() for route in routes}

    def unmatched_calls(self) -> list[tuple[str, str]]:
        """(client file, route) for calls no scanned server defines."""
        defined = self.defined()
        return sorted(
            (path, route)
            for path, routes in self.clients.items()
            for route in routes
            if route not in defined
        )

    def uncalled_routes(self) -> list[tuple[str, str]]:
        """(server file, route) for routes no scanned client calls."""
        called = self.called()
        return sorted(
            (path, route)
            for path, routes in self.servers.items()
            for route in routes
            if route not in called
        )

    def edges(self) -> list[DependencyEdge]:
        """One edge per (client, server) pair that shares at least one route.

        Collapsed at file granularity because the graph's node is a file. Twenty-three
        matched literals between two files are one dependency; the count of them is
        evidence for the edge, not twenty-three edges.
        """
        found: list[DependencyEdge] = []
        for client, calls in sorted(self.clients.items()):
            for server, defines in sorted(self.servers.items()):
                if client == server or not (calls & defines):
                    continue
                found.append(
                    DependencyEdge(
                        from_path=client,
                        to_path=server,
                        kind=KIND_ROUTE,
                        depth=DEPTH_RUNTIME,
                    )
                )
        return found


def _matching(repo: Path, patterns: tuple[str, ...]) -> list[str]:
    """Repo-relative paths of existing files matching any declared glob."""
    found: set[str] = set()
    for pattern in patterns:
        for path in repo.glob("**/*"):
            if not path.is_file():
                continue
            relative = path.relative_to(repo).as_posix()
            if fnmatch.fnmatch(relative, pattern):
                found.add(relative)
    return sorted(found)


def _normalise(route: str) -> str:
    """One spelling for one route.

    The client addresses routes relatively (`api/roster`) because the console is served
    under a path-scoped mount and an absolute URL would break the installed PWA; the
    server compares against the absolute form. They are the same route and must not be
    two.
    """
    return route if route.startswith("/") else "/" + route


def extract_routes(repo: Path, policy: RoutePolicy | None = None) -> RouteGraph:
    """Extract the client/server route sets of `repo` under `policy`.

    Reads only the declared client and server globs. A file that cannot be decoded is
    recorded in `unresolved` rather than skipped, for the same reason the import walk
    records an unparsed module: a file dropped in silence lowers the edge count, and
    that is the direction this instrument's errors have historically run.
    """
    policy = policy or RoutePolicy()
    graph = RouteGraph(policy=policy)
    if not policy.enabled:
        return graph
    if policy.match != MATCH_EXACT_LITERAL:
        graph.unresolved.append(f"unknown match policy: {policy.match}")
        return graph

    client_pattern = _client_literal(policy.prefix)
    server_pattern = _server_literal(policy.prefix)
    bare = policy.prefix.rstrip("/")

    servers = _matching(repo, policy.servers)
    for relative in _matching(repo, policy.clients):
        if relative in servers:
            continue
        try:
            text = (repo / relative).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            graph.unresolved.append(f"{relative}: unread ({exc.__class__.__name__})")
            continue
        found = {_normalise(match.group(1)) for match in client_pattern.finditer(text)}
        # A declared client is an element whether or not it calls anything. Entering it
        # only when the matcher found literals would make the element set a function of
        # the matcher's *recall*: a client addressing every route through a built string
        # would leave the numerator and the denominator together, so the miss would be
        # invisible in the number it moved. Measured on this repo the exclusion was
        # worth 0.22 propagation points against the matched edge's 0.02 — the larger of
        # the two effects, and not one to leave to a regex.
        graph.clients[relative] = {
            route for route in found if route.rstrip("/") != bare
        }

    for relative in servers:
        try:
            text = (repo / relative).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            graph.unresolved.append(f"{relative}: unread ({exc.__class__.__name__})")
            continue
        graph.servers[relative] = {
            _normalise(match.group(1) or match.group(2))
            for match in server_pattern.finditer(text)
        }
        for inexact in _SERVER_INEXACT.finditer(text):
            # Declared out of the matcher's reach. Reported because an unseen route of
            # any of these shapes would make an unmatched-call finding a false
            # accusation.
            form = inexact.group(1) or inexact.group(2)
            graph.unresolved.append(
                f"{relative}: route form {form!r} not matched by {policy.match}"
            )
    return graph


def merge(graph: DependencyGraph, routes: RouteGraph) -> DependencyGraph:
    """Fold the route channel into a scanned import graph, in place.

    The client files become modules because they are elements of the system the metric
    describes; leaving them out while counting their edges would be the denominator
    error this channel exists to close, inverted. Route findings about the scanner's own
    reach join `unresolved`, which is where a gap in what the walk could see belongs.
    """
    for client in sorted(routes.clients):
        if client not in graph.modules:
            graph.modules.append(client)
    graph.modules.sort()
    graph.edges.extend(routes.edges())
    graph.unresolved.extend(routes.unresolved)
    return graph
