"""`thalamus thread approve` run twice on one ref leaves one ledger row and one close edge.

The idempotency shape of the qe charter's write-path gap (issue #76): a write path
re-run should produce one entry, not two. `closes.approve()` is the ledger half of
`thalamus thread approve`; `_cmd_thread`'s `approve` branch (`src/thalamus/cli.py`) calls
it before the graph write, the ordering the module's docstring calls deliberate: "a close
whose ledger row is missing cannot be corroborated afterwards."

**Properties held.**
1. A second `approve()` on an approved ref returns `(row, created=False)` and appends
   nothing: exactly one APPROVED row for the ref after two calls. A single call yields one
   row first, as the control, so a comparator that miscounts cannot pass this for the
   wrong reason.
2. The repair path. The ledger row lands before the edge, so a failed graph write is
   repaired by re-running the command. Driven through the CLI against `_MergeGraph`, a
   stand-in with `merge_v`/`merge_e` semantics whose first edge write fails after the
   Agent vertex landed: the retry must write the edge, and after fail, retry, retry the
   graph holds one close edge carrying the original approval's `closed_at`, and the
   ledger one approval row. Call counts are not the property; the edge count is. The
   stand-in shows the writer's merge requests are stable under repetition; that the real
   server honours merge semantics is not exercised here.

**Mutations that drive it red.** Against 7b79ecf (a repeat `thread approve` returned
before the graph write) property 2 fails: `close edges=0 ... approval rows=1`. Against
9b02207 (`approve()` appending unconditionally) property 1 fails with two rows.

The cross case (approving a rejected ref) still appends by decision and is not asserted
here.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier


def run() -> Finding | None:
    from thalamus.harness import closes  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "closes.jsonl"

        row = closes.propose(
            thread_id="qe-idempotency-probe",
            scope="qe",
            basis="qe probe: not a real proposal",
            disposition="settled",
            rationale="exercised by tests/qe/cases/thread_approve_idempotency.py",
            proposed_by="qe-case",
            path=ledger,
        )
        ref = row["ref"]

        closes.approve(ref, surface="cli", approver_evidence="cli:tty", path=ledger)
        after_one = [a for a in closes.approvals(ledger) if a["ref"] == ref]

        # CONTROL: one approve() call must yield exactly one row. Without this, a
        # comparator that already miscounts a single approval as more than one would
        # call the second call's duplicate "expected" for the wrong reason.
        if len(after_one) != 1:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="a single approve() call did not produce exactly one ledger "
                        "row, so this case cannot tell a duplicate from the baseline",
                witness=f"rows for ref after 1 approve() call: {len(after_one)}",
                site="tests/qe/cases/thread_approve_idempotency.py",
            )

        closes.approve(ref, surface="cli", approver_evidence="cli:tty", path=ledger)
        after_two = [a for a in closes.approvals(ledger) if a["ref"] == ref]

        if len(after_two) == 1:
            return _retry_after_graph_failure()

        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "closes.approve() has no guard against re-invocation on an already-"
                "approved ref: calling it a second time on the same ref appends a "
                "second APPROVED row instead of leaving the ledger unchanged"
            ),
            witness=(
                f"approvals for ref after 1st approve(): 1; after 2nd approve(): "
                f"{len(after_two)}"
            ),
            site="src/thalamus/harness/closes.py:approve",
        )


class _MergeGraph:
    """A hermetic stand-in for the graph with TinkerGraph's `merge_v`/`merge_e` semantics.

    A merge finds the element by its key (vertex id; edge label + endpoints), creates it
    with the `on_create` payload when absent, and applies `on_match` when present. That
    is the whole of what `write_thread_close`'s idempotence rests on, so the stand-in
    models exactly that and nothing else. It shows the writer's *requests* are stable
    under repetition; that the real server honours merge semantics is the server's
    contract and is not exercised here. `fail_edge_writes` makes the first edge merge
    raise after the Agent vertex has already landed, the partial state a dropped
    connection leaves.
    """

    def __init__(self, fail_edge_writes: int = 0):
        self.vertices: dict[str, dict] = {}
        self.edges: dict[tuple, dict] = {}
        self.fail_edge_writes = fail_edge_writes

    def V(self, *_ids):
        return _Step(self, "V", {})

    def merge_v(self, spec):
        return _Step(self, "merge_v", dict(spec))

    def merge_e(self, spec):
        return _Step(self, "merge_e", dict(spec))


class _Step:
    def __init__(self, graph: _MergeGraph, kind: str, spec: dict):
        self.graph, self.kind, self.spec = graph, kind, spec
        self.created: dict = {}
        self.matched: dict = {}
        self.props: dict = {}
        self.bytecode = "<stand-in>"

    def has_label(self, *_):
        return self

    def has_next(self):
        return True

    def option(self, merge, payload):
        from gremlin_python.process.traversal import Merge  # noqa: PLC0415

        (self.created if merge is Merge.on_create else self.matched).update(payload)
        return self

    def property(self, key, value):
        self.props[key] = value
        return self

    def iterate(self):
        from gremlin_python.process.traversal import Direction, T  # noqa: PLC0415

        graph = self.graph
        if self.kind == "merge_v":
            key = self.spec[T.id]
            if key in graph.vertices:
                graph.vertices[key].update(self.matched)
            else:
                graph.vertices[key] = dict(self.created)
        elif self.kind == "merge_e":
            if graph.fail_edge_writes:
                graph.fail_edge_writes -= 1
                raise RuntimeError("graph unavailable")
            key = (self.spec[T.label], self.spec[Direction.from_], self.spec[Direction.to])
            if key in graph.edges:
                graph.edges[key].update(self.matched)
            else:
                graph.edges[key] = dict(self.created)
        return self


def _retry_after_graph_failure() -> Finding | None:
    """The ledger row precedes the graph edge, so a failed edge write is repaired by
    running `thalamus thread approve <ref>` again.

    Drives the CLI three times against a stand-in graph whose first edge write fails
    after the Agent vertex landed. The property: the retry writes the edge, and once the
    runs are done the graph holds exactly one close edge for the thread, carrying the
    original approval's `closed_at`, and the ledger holds exactly one approval row.
    """
    import sys  # noqa: PLC0415
    from unittest import mock  # noqa: PLC0415

    import thalamus.cli as cli  # noqa: PLC0415
    from thalamus.harness import closes  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "closes.jsonl"
        ref = closes.propose(
            thread_id="qe-retry-probe", scope="qe", basis="qe probe", disposition="done",
            rationale="tests/qe/cases/thread_approve_idempotency.py",
            proposed_by="qe-case", path=ledger,
        )["ref"]
        graph = _MergeGraph(fail_edge_writes=1)

        def run_cli() -> str | None:
            try:
                with mock.patch.object(sys, "argv", ["thalamus", "thread", "approve", ref]):
                    cli.main()
            except Exception as exc:  # noqa: BLE001
                return str(exc)
            return None

        with (
            mock.patch.object(closes, "LEDGER_FILE", ledger),
            mock.patch.object(cli, "connect", lambda url=None: graph),
            mock.patch.object(cli, "close_connection", lambda g: None),
            mock.patch.object(cli, "_persist", lambda g, *a, **k: None),
            mock.patch("builtins.print"),
        ):
            outcomes = [run_cli(), run_cli(), run_cli()]
        approvals = [a for a in closes.approvals(ledger) if a["ref"] == ref]

    # CONTROL: the first run's graph write failed, so the failure path is live and the
    # stand-in holds no edge before the retry.
    if not (outcomes[0] and "graph unavailable" in outcomes[0]):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the stubbed graph failure did not reach the CLI's approve path",
            witness=f"first run raised: {outcomes[0]!r}",
            site="tests/qe/cases/thread_approve_idempotency.py",
        )
    closed_ats = [e.get("closed_at") for e in graph.edges.values()]
    if (
        outcomes[1:] == [None, None]
        and len(graph.edges) == 1
        and len(approvals) == 1
        and closed_ats == [approvals[0]["ts"]]
    ):
        return None
    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            "`thalamus thread approve` retried after a failed graph write did not leave "
            "one close edge (carrying the original approval's closed_at) and one "
            "approval row"
        ),
        witness=(
            f"outcomes={outcomes} close edges={len(graph.edges)} "
            f"closed_at={closed_ats} approval rows={len(approvals)}"
        ),
        site="src/thalamus/cli.py:_cmd_thread",
    )


CASE = Case(
    name="thread-approve-is-idempotent",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="approving the same close ref twice must not duplicate the ledger row",
    run=run,
    issue=170,
    fixed=True,
)
