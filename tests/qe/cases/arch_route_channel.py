"""The route channel must reproduce a hand-counted route list, and a hand-counted N.

Same gate as `arch_extractor`, for the second extraction channel by the same hand. The
reason that gate exists is recorded rather than inferred: the architect published
propagation-cost figures twice from ad-hoc extractors and retracted both, and the errors
ran one direction — toward the cleaner answer. This channel's first published movement
was retracted for the third time, and the retraction is why the numbers below are what
they are: the element decision was worth 0.22 propagation points on this repo against
the matched edge's 0.018, so the movement first reported as coupling was a denominator
choice made by a regex.

The fixture at `tests/qe/fixtures/route_fixture/` is three Python modules and two
browser files whose every route was counted by hand. Its roots are `code/` and `web/`
rather than `src/`, because `qe`'s write boundary denies `*/src/*` and a fixture tree is
not the place to argue for an exception.

It covers the forms that separate two defensible implementations:

- `api/alpha` and `/api/alpha` in the same client — one route, because the console is
  served under a path-scoped mount and addresses routes relatively while the server
  compares the absolute form
- `api/beta?pane=${id}` — one route, and the reason is checkable rather than stylistic:
  `console/server.py` does `path, _, query = self.path.partition("?")` before any
  comparison, so the query is not part of what the server routes on
- `"/api/delta" == path` — the same route as `path == "/api/delta"`; a matcher that read
  only one operand order would emit a false unmatched-call finding for a route that is
  plainly defined
- `/health`, a server route outside the declared prefix — invisible, because the client
  matcher is bound to the same prefix and structurally cannot see a call to it. Collecting
  it would manufacture an uncalled-route finding out of the asymmetry between the two
  patterns rather than out of the code
- `api/ghost`, called and defined nowhere — a finding, never an edge
- `/api/orphan`, defined and called by no scanned client — reported, and reported as *no
  scanned client calls it*, which is a smaller claim than dead surface: the declared
  client set is not the caller set, and the voice daemon and shell scripts call the real
  server from outside it
- `path.startswith("/frame/")` and `path in EXTRA` — two routing forms beyond the
  matcher, both named, because an unreported route form of any shape turns an
  unmatched-call finding into a false accusation
- `web/sw.js`, a declared client with no route literals, which is an element anyway

The last one is the load-bearing assertion. Membership follows the declaration, not the
finding: a predicate of "the matcher found literals here" makes the element set a
function of the matcher's *recall*, so a client addressing every route through a built
string leaves the numerator and the denominator together and the miss is invisible in the
number it moved. `EXPECTED_WITHOUT_ROUTELESS_CLIENT` pins what that choice is worth —
dropping the one edgeless element moves this fixture 36.00% -> 50.00% while changing no
structure at all.

One behaviour here is **characterized, not endorsed**, and the distinction matters
because a green case is a claim. `api/legacy` appears only inside a comment in
`web/app.js` and becomes an unmatched-call finding. The matcher is text-level. This repo
happens to contain zero comment-only route literals today (measured over
`console/static/app.js`: all 23 routes occur on at least one non-comment line), so the
channel's precision claim of 1.0 is a fact about this commit and not a property of the
matcher.

The expectations are literals. When this case fails, the question is which side is
wrong, and the fixture is small enough that a human settles it in a minute.
"""

from __future__ import annotations

from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "route_fixture"

# The declared client set. Authored, not globbed — the element set is a declaration, and
# naming the files here is what makes the case an oracle over the policy rather than over
# whatever the glob happened to sweep up.
CLIENTS = ("web/app.js", "web/sw.js")

# Hand-counted from `web/app.js`: six request literals in code plus one in a comment,
# collapsing to six distinct routes because the relative and absolute spellings of alpha
# are one route and the query string on beta is not part of it. `web/sw.js` names the
# bare prefix and calls nothing.
EXPECTED_CALLS = {
    "web/app.js": (
        "/api/alpha",
        "/api/beta",
        "/api/delta",
        "/api/gamma/leaf",
        "/api/ghost",
        "/api/legacy",
    ),
    "web/sw.js": (),
}

# Hand-counted from `code/srv/api.py`: four `path ==` literals under the declared prefix
# plus one written with the operands reversed. `/health` is deliberately not among them,
# and neither are the two forms beyond the matcher.
EXPECTED_DEFINES = (
    "/api/alpha",
    "/api/beta",
    "/api/delta",
    "/api/gamma/leaf",
    "/api/orphan",
)

EXPECTED_UNMATCHED = (("web/app.js", "/api/ghost"), ("web/app.js", "/api/legacy"))
EXPECTED_UNCALLED = (("code/srv/api.py", "/api/orphan"),)

# One edge for five matched literals: the graph's node is a file. The routeless client is
# an element and still produces no edge, which is the whole point of separating the two.
EXPECTED_ROUTE_EDGES = ("web/app.js -> code/srv/api.py [route,runtime]",)

# Both gaps in the scan's own reach, in the order the walk reports them.
EXPECTED_UNRESOLVED = (
    "code/srv/api.py: route form '/frame/' not matched by exact-literal",
    "code/srv/api.py: route form 'EXTRA' not matched by exact-literal",
)

# The merged graph: every recorded edge, before the policy filters by depth or resolve.
EXPECTED_MERGED_EDGES = (
    "code/srv/api.py -> code/srv/__init__.py [package,module]",
    "code/srv/api.py -> code/srv/store.py [from,module]",
    "code/srv/store.py -> code/srv/__init__.py [package,deferred]",
    "code/srv/store.py -> code/srv/api.py [from,deferred]",
    "web/app.js -> code/srv/api.py [route,runtime]",
)

# Three Python modules under `code/`, plus both declared clients. `web/sw.js` is present
# with no edge, which is the shipped element rule.
EXPECTED_MODULES = (
    "code/srv/__init__.py",
    "code/srv/api.py",
    "code/srv/store.py",
    "web/app.js",
    "web/sw.js",
)

# import_depth -> (counted edges, modules in cycles, propagation cost %)
#
# all: api->store (module), store->api (deferred), app.js->api (runtime) = 3. Closure
# including self: srv/__init__ 1, api {api, store} 2, store {store, api} 2, app.js
# {app.js, api, store} 3, sw.js 1 = 9 of 25 cells.
#
# module-level: the deferred edge drops and the cycle with it, but the route edge does
# NOT — a route executes when a request is made, which is neither import time nor a
# deferred import. Closure: 1 + 2 + 1 + 3 + 1 = 8 of 25.
EXPECTED_READINGS = {
    "all": (3, 2, 36.0),
    "module-level": (2, 0, 32.0),
}

# The counterfactual, in the direction the shipped rule is not. Dropping the routeless
# client changes no structure and moves the headline by 14 points on five modules: 8 of
# 16 cells instead of 9 of 25.
EXPECTED_WITHOUT_ROUTELESS_CLIENT = 50.0


def _fail(summary: str, witness: str, site: str) -> Finding:
    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=summary,
        witness=witness,
        site=site,
    )


def run() -> Finding | None:
    from thalamus.arch.extractor import ExtractorPolicy, scan_repo  # noqa: PLC0415
    from thalamus.arch.metrics import measure  # noqa: PLC0415
    from thalamus.arch.routes import RoutePolicy, extract_routes, merge  # noqa: PLC0415

    policy = RoutePolicy(enabled=True, clients=CLIENTS, servers=("code/srv/api.py",))
    routes = extract_routes(FIXTURE, policy)

    observed_calls = {path: tuple(sorted(calls)) for path, calls in routes.clients.items()}
    if observed_calls != EXPECTED_CALLS:
        return _fail(
            "The route walk's per-client call sets disagree with the hand-counted fixture.",
            f"observed {observed_calls}, expected {EXPECTED_CALLS}",
            "src/thalamus/arch/routes.py:_client_literal",
        )

    # Membership follows the declaration, not the finding. Asserted separately from the
    # call sets so the witness names the property rather than a dict diff.
    if "web/sw.js" not in routes.clients:
        return _fail(
            "A declared client with no route literals was dropped from the client set.",
            "web/sw.js is declared and must be an element whether or not it calls anything",
            "src/thalamus/arch/routes.py:extract_routes",
        )

    if "/api/" in routes.called():
        return _fail(
            "The bare api namespace was counted as a route.",
            "sw.js names '/api/' to exclude it from its cache; that is not a call",
            "src/thalamus/arch/routes.py:extract_routes",
        )

    defines = tuple(sorted(routes.defined()))
    if defines != EXPECTED_DEFINES:
        return _fail(
            "The route walk's server route set disagrees with the hand-counted fixture.",
            f"observed {list(defines)}, expected {list(EXPECTED_DEFINES)}",
            "src/thalamus/arch/routes.py:_server_literal",
        )

    if "/health" in routes.defined():
        return _fail(
            "A server route outside the declared prefix was collected.",
            "/health cannot be called by a client matcher bound to '/api/', so collecting "
            "it manufactures an uncalled-route finding out of the asymmetry",
            "src/thalamus/arch/routes.py:_server_literal",
        )

    if tuple(routes.unmatched_calls()) != EXPECTED_UNMATCHED:
        return _fail(
            "A call no scanned server defines must be a finding, and exactly these two are.",
            f"observed {routes.unmatched_calls()}, expected {list(EXPECTED_UNMATCHED)}",
            "src/thalamus/arch/routes.py:RouteGraph.unmatched_calls",
        )

    if tuple(routes.uncalled_routes()) != EXPECTED_UNCALLED:
        return _fail(
            "A route no scanned client calls must be reported, and exactly this one is.",
            f"observed {routes.uncalled_routes()}, expected {list(EXPECTED_UNCALLED)}",
            "src/thalamus/arch/routes.py:RouteGraph.uncalled_routes",
        )

    if tuple(routes.unresolved) != EXPECTED_UNRESOLVED:
        return _fail(
            "The scan did not name exactly the two gaps in its own reach.",
            f"observed {routes.unresolved}, expected {list(EXPECTED_UNRESOLVED)}",
            "src/thalamus/arch/routes.py:_SERVER_INEXACT",
        )

    observed_edges = tuple(edge.as_row() for edge in routes.edges())
    if observed_edges != EXPECTED_ROUTE_EDGES:
        return _fail(
            "Five matched literals between two files must be one dependency, and a "
            "declared client sharing no route must be none.",
            f"observed {list(observed_edges)}, expected {list(EXPECTED_ROUTE_EDGES)}",
            "src/thalamus/arch/routes.py:RouteGraph.edges",
        )

    merged = merge(scan_repo(FIXTURE, ExtractorPolicy(roots=("code",))), routes)

    if tuple(merged.modules) != EXPECTED_MODULES:
        return _fail(
            "The merged element set disagrees with the hand-counted fixture.",
            f"observed {merged.modules}, expected {list(EXPECTED_MODULES)}",
            "src/thalamus/arch/routes.py:merge",
        )

    merged_rows = tuple(edge.as_row() for edge in merged.edges)
    if merged_rows != EXPECTED_MERGED_EDGES:
        missing = [row for row in EXPECTED_MERGED_EDGES if row not in merged_rows]
        extra = [row for row in merged_rows if row not in EXPECTED_MERGED_EDGES]
        return _fail(
            "The merged edge list disagrees with the hand-counted fixture: "
            f"{len(missing)} missing, {len(extra)} unexpected.",
            f"missing: {missing}; unexpected: {extra}",
            "src/thalamus/arch/routes.py:merge",
        )

    for depth, (edges, in_cycles, cost) in EXPECTED_READINGS.items():
        reading = measure(
            merge(
                scan_repo(FIXTURE, ExtractorPolicy(roots=("code",), import_depth=depth)),
                extract_routes(FIXTURE, policy),
            )
        )
        observed = (
            reading.dependencies,
            reading.modules_in_cycles,
            round(reading.propagation_cost * 100, 2),
        )
        if observed != (edges, in_cycles, cost):
            return _fail(
                f"Reading import_depth={depth} counted {observed}; the fixture is "
                f"hand-counted at {(edges, in_cycles, cost)}.",
                f"observed (edges, in_cycles, pc%) = {observed}, expected {(edges, in_cycles, cost)}",
                "src/thalamus/arch/extractor.py:ExtractorPolicy.counts_edge",
            )

    # Disabled is the identity case, not a third value: a scan taken before this channel
    # existed must still be the number it was published as.
    off = merge(
        scan_repo(FIXTURE, ExtractorPolicy(roots=("code",))),
        extract_routes(FIXTURE, RoutePolicy(enabled=False)),
    )
    import_only = measure(scan_repo(FIXTURE, ExtractorPolicy(roots=("code",))))
    if (tuple(off.modules), measure(off).propagation_cost) != (
        tuple(EXPECTED_MODULES[:3]),
        import_only.propagation_cost,
    ):
        return _fail(
            "Merging a disabled route channel changed the import-only reading.",
            f"modules {off.modules} at {measure(off).propagation_cost * 100:.2f}%, "
            f"import-only {import_only.modules} at {import_only.propagation_cost * 100:.2f}%",
            "src/thalamus/arch/routes.py:merge",
        )

    # What the element rule is worth. Pinned so that a published movement can never be
    # read as though it were all coupling, and so that a silent return to a
    # recall-dependent predicate costs a red run.
    counterfactual = merge(scan_repo(FIXTURE, ExtractorPolicy(roots=("code",))), routes)
    counterfactual.modules.remove("web/sw.js")
    without = round(measure(counterfactual).propagation_cost * 100, 2)
    if without != EXPECTED_WITHOUT_ROUTELESS_CLIENT:
        return _fail(
            "The propagation cost of dropping the routeless client moved.",
            f"observed {without}%, hand-counted at {EXPECTED_WITHOUT_ROUTELESS_CLIENT}% "
            f"(8 of 16 cells); the shipped reading is {EXPECTED_READINGS['all'][2]}% "
            "(9 of 25), and the difference is the element rule, not a dependency",
            "src/thalamus/arch/metrics.py:propagation_cost",
        )

    return None


CASE = Case(
    name="arch-route-channel-ground-truth",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED,),
    summary=(
        "The route channel reproduces a hand-counted route list, findings list and "
        "element set over a five-file fixture, under both import_depth readings, and "
        "what the element rule is worth in propagation cost is pinned alongside it."
    ),
    run=run,
)
