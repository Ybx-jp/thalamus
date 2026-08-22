"""The route channel: what it extracts, what it refuses to, and what it says out loud.

These are the architect's own tests. The ground-truth case — a fixture whose every
route was counted by hand — belongs to `qe`, because the scope whose implementation is
being asserted against does not author the oracle that indicts it.
"""

from __future__ import annotations

from pathlib import Path

from thalamus.arch.extractor import (
    DEPTH_MODULE,
    DEPTH_RUNTIME,
    KIND_IMPORT,
    KIND_ROUTE,
    DependencyEdge,
    DependencyGraph,
    ExtractorPolicy,
)
from thalamus.arch.model import scan_id
from thalamus.arch.routes import RoutePolicy, extract_routes, merge

CLIENT = "src/ui/app.js"
SERVER = "src/api.py"


def _repo(tmp_path: Path, client: str, server: str, extra: dict[str, str] | None = None) -> Path:
    (tmp_path / "src" / "ui").mkdir(parents=True)
    (tmp_path / CLIENT).write_text(client, encoding="utf-8")
    (tmp_path / SERVER).write_text(server, encoding="utf-8")
    for name, body in (extra or {}).items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


def _policy(**kwargs) -> RoutePolicy:
    return RoutePolicy(
        enabled=True,
        clients=("src/ui/*.js",),
        servers=("src/api.py",),
        **kwargs,
    )


def test_route_literals_collapse_to_a_single_edge(tmp_path):
    repo = _repo(
        tmp_path,
        client="req(`api/alpha`); req(`api/beta`); req(`api/gamma`);",
        server='if path == "/api/alpha": pass\nif path == "/api/beta": pass\n'
        'if path == "/api/gamma": pass\n',
    )
    routes = extract_routes(repo, _policy())

    assert len(routes.called()) == 3, "three distinct routes called"
    edges = routes.edges()
    assert len(edges) == 1, "one file-to-file dependency, not one per literal"
    assert edges[0].from_path == CLIENT
    assert edges[0].to_path == SERVER
    assert edges[0].kind == KIND_ROUTE
    assert edges[0].depth == DEPTH_RUNTIME


def test_the_relative_and_absolute_spellings_are_one_route(tmp_path):
    """The client addresses routes relatively because the console is served under a
    path-scoped mount; the server compares the absolute form. One route, not two."""
    repo = _repo(
        tmp_path,
        client="req(`api/alpha`); req(`/api/alpha`);",
        server='if path == "/api/alpha": pass\n',
    )
    routes = extract_routes(repo, _policy())

    assert routes.called() == {"/api/alpha"}
    assert routes.unmatched_calls() == []


def test_a_query_string_is_not_part_of_the_route(tmp_path):
    repo = _repo(
        tmp_path,
        client="req(`api/read/body?pane=${id}`);",
        server='if path == "/api/read/body": pass\n',
    )
    routes = extract_routes(repo, _policy())

    assert routes.called() == {"/api/read/body"}
    assert routes.unmatched_calls() == [], "the substitution must not defeat the match"


def test_a_call_no_server_defines_is_a_finding_not_an_edge(tmp_path):
    repo = _repo(
        tmp_path,
        client="req(`api/ghost`);",
        server='if path == "/api/real": pass\n',
    )
    routes = extract_routes(repo, _policy())

    assert routes.edges() == [], "no shared route means no dependency"
    assert routes.unmatched_calls() == [(CLIENT, "/api/ghost")]


def test_a_route_no_scanned_client_calls_is_reported(tmp_path):
    repo = _repo(
        tmp_path,
        client="req(`api/alpha`);",
        server='if path == "/api/alpha": pass\nif path == "/api/orphan": pass\n',
    )
    routes = extract_routes(repo, _policy())

    assert routes.uncalled_routes() == [(SERVER, "/api/orphan")]


def test_a_declared_client_with_no_routes_is_still_an_element(tmp_path):
    """The element set is a declaration, not a result of the matcher.

    Entering a client only when literals were found makes membership depend on recall:
    a client addressing every route through a built string would leave the numerator
    and the denominator together, so the miss would be invisible in the number it
    moved. Measured on this repo the exclusion was worth 0.22 propagation points
    against the matched edge's 0.02 — the larger effect, decided by a regex.
    """
    repo = _repo(
        tmp_path,
        client="req(`api/alpha`);",
        server='if path == "/api/alpha": pass\n',
        extra={"src/ui/quiet.js": "function draw() {}"},
    )
    routes = extract_routes(repo, _policy())

    assert routes.clients["src/ui/quiet.js"] == set(), "declared, calls nothing"
    assert "src/ui/quiet.js" in merge(
        DependencyGraph(modules=[SERVER], policy=ExtractorPolicy()), routes
    ).modules


def test_a_prefix_route_is_reported_as_beyond_the_matcher(tmp_path):
    """An unreported prefix route would make an unmatched-call finding a false
    accusation, so the matcher names what it could not resolve."""
    repo = _repo(
        tmp_path,
        client="req(`api/alpha`);",
        server='if path == "/api/alpha": pass\nif path.startswith("/frame/"): pass\n',
    )
    routes = extract_routes(repo, _policy())

    assert any("/frame/" in note for note in routes.unresolved)


def test_the_server_matcher_reads_either_operand_order(tmp_path):
    """`"/api/x" == path` is the same comparison as `path == "/api/x"`. Reading only
    one order yields an empty server route set and then accuses the client of calling a
    route that is defined three characters away."""
    repo = _repo(
        tmp_path,
        client="req(`api/alpha`);",
        server='if "/api/alpha" == path: pass\n',
    )
    routes = extract_routes(repo, _policy())

    assert routes.defined() == {"/api/alpha"}
    assert routes.unmatched_calls() == [], "no false accusation from operand order"


def test_a_membership_table_route_is_reported_as_beyond_the_matcher(tmp_path):
    """`if path in STATIC:` is a live routing form in the scanned server. A gap
    detector that knows only `startswith` passes it in silence, and silence here is
    what turns an unmatched-call finding into a false accusation."""
    repo = _repo(
        tmp_path,
        client="req(`api/alpha`);",
        server='if path == "/api/alpha": pass\nif path in STATIC: pass\n',
    )
    routes = extract_routes(repo, _policy())

    assert any("STATIC" in note for note in routes.unresolved)


def test_both_matchers_are_bound_to_the_declared_prefix(tmp_path):
    """An unbounded server pattern collects routes the client pattern structurally
    cannot call, then reports each as called by nobody — a finding manufactured by the
    asymmetry rather than by the code."""
    repo = _repo(
        tmp_path,
        client="req(`api/alpha`);",
        server='if path == "/api/alpha": pass\nif path == "/internal/health": pass\n',
    )
    routes = extract_routes(repo, _policy())

    assert routes.defined() == {"/api/alpha"}
    assert routes.uncalled_routes() == [], "an unreachable route is not dead surface"


def test_the_prefix_is_declared_not_hardcoded(tmp_path):
    repo = _repo(
        tmp_path,
        client="req(`rpc/alpha`);",
        server='if path == "/rpc/alpha": pass\n',
    )
    routes = extract_routes(repo, _policy(prefix="/rpc/"))

    assert routes.called() == {"/rpc/alpha"}
    assert len(routes.edges()) == 1


def test_the_channel_is_off_until_the_authored_half_asks_for_it(tmp_path):
    repo = _repo(
        tmp_path,
        client="req(`api/alpha`);",
        server='if path == "/api/alpha": pass\n',
    )
    routes = extract_routes(repo, RoutePolicy(enabled=False))

    assert routes.clients == {} and routes.servers == {}
    assert routes.edges() == []


def test_an_unknown_matcher_extracts_nothing_and_says_so(tmp_path):
    """A policy naming a matcher this module does not implement must not silently fall
    back to the one it does — that would be a number produced under rules nobody
    declared."""
    repo = _repo(
        tmp_path,
        client="req(`api/alpha`);",
        server='if path == "/api/alpha": pass\n',
    )
    routes = extract_routes(repo, _policy(match="regex"))

    assert routes.edges() == []
    assert any("regex" in note for note in routes.unresolved)


def test_import_depth_does_not_govern_the_route_channel():
    """A route edge is not an import. A module-level reading that dropped it would
    report the console as absent again, which is the omission this channel closes."""
    edge = DependencyEdge(CLIENT, SERVER, KIND_ROUTE, DEPTH_RUNTIME)
    module_level = ExtractorPolicy(import_depth="module-level")

    assert module_level.counts_edge(edge), "route edges survive a module-level reading"
    assert ExtractorPolicy().counts_edge(edge)


def test_merge_enters_the_client_as_a_module_and_its_edge(tmp_path):
    repo = _repo(
        tmp_path,
        client="req(`api/alpha`);",
        server='if path == "/api/alpha": pass\n',
    )
    graph = DependencyGraph(modules=[SERVER], policy=ExtractorPolicy())
    graph.edges.append(DependencyEdge(SERVER, SERVER, KIND_IMPORT, DEPTH_MODULE))

    merged = merge(graph, extract_routes(repo, _policy()))

    assert CLIENT in merged.modules, "the client is an element of the measured system"
    assert any(edge.kind == KIND_ROUTE for edge in merged.edges)
    assert merged.modules == sorted(merged.modules), "module order stays stable"


def test_the_scan_key_is_unchanged_while_the_channel_is_off():
    """Every scan published before this channel existed keeps the key it was published
    under. Disabled is the identity case, not a third value."""
    policy = ExtractorPolicy()
    commit = "0" * 40

    assert scan_id("thalamus", commit, policy, RoutePolicy(enabled=False)) == scan_id(
        "thalamus", commit, policy, None
    )


def test_enabling_the_channel_forks_the_scan_key():
    """A propagation cost measured with the route channel on is not comparable to one
    measured without it. If the key did not move the two would collide on one name and
    the older number would be silently relabelled."""
    policy = ExtractorPolicy()
    commit = "0" * 40

    off = scan_id("thalamus", commit, policy, RoutePolicy(enabled=False))
    on = scan_id("thalamus", commit, policy, RoutePolicy(enabled=True))

    assert on != off


def test_the_route_policy_digest_moves_with_the_policy_but_not_with_its_spelling():
    base = RoutePolicy(enabled=True)

    assert RoutePolicy(enabled=True).digest() == base.digest()
    assert RoutePolicy(enabled=True, servers=("src/other.py",)).digest() != base.digest()
    assert RoutePolicy.from_block(base.block()).digest() == base.digest()
