"""The retrieval compiler — one job's calls against the vocabulary, validated and capped.

A planner (the memory reflex's word-match plan today, the local model's tool loop
later) never touches the graph. It names a tool from `substrate/vocabulary.py` and its
arguments; the compiler checks both against `TOOLS`, injects the job's scope — the
planner has no way to name one — resolves the handles it was shown back to vertex ids,
runs the primitive, and hands back rows under new handles. A handle is the only way a
planner can point at a node, so a node it names is one this job returned.

Per job, four caps bound what a planner can spend, and a tripped cap refuses the call
rather than truncating silently: calls issued, distinct nodes returned, characters of
rows handed back, and wall time from the job's start (A0172, cites-as-live). The values
are provisional until the per-tool size distribution over real anchors sets them.

Every node any call returned is recorded, with the handle it was shown under: that set
is what a planner's final selection, and a note's citations, are checked against.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from gremlin_python.process.graph_traversal import GraphTraversalSource

from thalamus.substrate import vocabulary
from thalamus.substrate.reader import recall
from thalamus.substrate.vocabulary import Row


@dataclass(frozen=True)
class Caps:
    """Per-job ceilings, set from `thalamus eval vocabulary` on 2026-09-24.

    Each run replays the 40 newest real reflex anchor sets through every tool — every
    kind searched, every relation walked from the top node of each — which is more than
    any planner issues. Over three runs, per anchor set, p90: calls 28–34, distinct
    nodes 35, characters of rows 7,600–8,100. A row is ~200 characters, so a full
    five-row answer is ~1,000. Wall time is dominated by the unindexed chunk scan
    (#112): 4.3 s p50 per `lexical_by_kind` over chunks in every run, and 4.9 to 12.6 s
    p90 between runs, so the time cap is set against per-call figures rather than a
    sweep's total, which read 8.5 to 21.7 s p90.
    """

    # Under half the exhaustive sweep's p90: a planner is meant to choose.
    calls: int = 12
    # The sweep's p90; ~2k tokens of rows at the measured 3.76 chars/token.
    nodes: int = 40
    row_chars: int = 8_000
    # Two chunk scans and ten cheaper calls, with room for a cold graph.
    seconds: float = 30.0


@dataclass(frozen=True)
class Param:
    """One argument: its type, whether it may be omitted, and its allowed values."""

    kind: type
    required: bool = True
    choices: tuple[str, ...] = ()
    # A handle argument names a node this job returned; the compiler swaps in its id.
    handle: bool = False


@dataclass(frozen=True)
class Tool:
    params: dict[str, Param]
    run: Callable[..., list[Row]]
    # Whether the primitive reads knowledge scopes beside the job's own.
    knowledge: bool = True


# `limit` is optional everywhere; each primitive carries its own default.
LIMIT = Param(int, required=False)


TOOLS: dict[str, Tool] = {
    "lexical_by_kind": Tool(
        {"query": Param(str), "kind": Param(str, choices=vocabulary.KINDS),
         "limit": LIMIT},
        vocabulary.lexical_by_kind,
    ),
    "expand_one_hop": Tool(
        {"handle": Param(str, handle=True),
         "relation": Param(str, choices=tuple(vocabulary.RELATIONS)), "limit": LIMIT},
        vocabulary.expand_one_hop,
    ),
    "session_claims": Tool(
        {"handle": Param(str, handle=True), "kinds": Param(list, required=False),
         "limit": LIMIT},
        vocabulary.session_claims,
        knowledge=False,
    ),
    "chunks_near_source": Tool(
        {"handle": Param(str, handle=True), "limit": LIMIT},
        vocabulary.chunks_near_source,
    ),
    "by_path": Tool(
        {"path": Param(str), "limit": LIMIT}, vocabulary.by_path, knowledge=False
    ),
    "threads_by_topic": Tool(
        {"topic": Param(str), "limit": LIMIT}, vocabulary.threads_by_topic,
        knowledge=False,
    ),
}

# The largest `limit` any call may ask for; the node cap bounds a job as a whole.
MAX_LIMIT = 10


class Refused(Exception):
    """A call the compiler will not run, with the reason the planner is shown."""


@dataclass
class Job:
    """One planner's calls against the graph, under one scope and one set of caps."""

    g: GraphTraversalSource
    scope: str
    knowledge_scopes: list[str]
    prefix: str
    caps: Caps = field(default_factory=Caps)
    clock: Callable[[], float] = time.monotonic
    # handle -> vertex id, in the order the nodes were first returned.
    handles: dict[str, str] = field(default_factory=dict)
    calls: int = 0
    row_chars: int = 0
    started: float = field(init=False)
    _handle_of: dict[str, str] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.started = self.clock()

    @property
    def returned(self) -> set[str]:
        return set(self.handles.values())

    def handle_for(self, node_id: str) -> str:
        """The node's handle in this job, minted on first sight."""
        handle = self._handle_of.get(node_id)
        if handle is None:
            handle = f"{self.prefix}.{len(self.handles) + 1}"
            self._handle_of[node_id] = handle
            self.handles[handle] = node_id
        return handle

    def call(self, name: str, args: dict) -> str:
        """Run one planner call and render its rows, or say why it was refused."""
        try:
            rows = self._run(name, args)
        except Refused as refusal:
            return f"refused: {refusal}"
        if not rows:
            return "no results"
        lines = []
        for row in rows:
            if self._past_node_cap(row.vid):
                lines.append(f"cap: {self.caps.nodes} distinct nodes returned; the rest dropped")
                break
            line = row.line(self.handle_for(row.vid))
            if self.row_chars + len(line) > self.caps.row_chars:
                lines.append(f"cap: {self.caps.row_chars} characters of rows; the rest dropped")
                break
            self.row_chars += len(line) + 1
            lines.append(line)
        return "\n".join(lines)

    def rows(self, name: str, args: dict) -> list[Row]:
        """Run one call and return its rows with their handles minted — the form a
        deterministic plan reads, where `call`'s rendering is for a model.

        Validated and charged exactly as `call` is, and raises `Refused` where `call`
        would say it. Rows past the node cap are dropped; no characters are charged,
        since nothing here enters a planner's context.
        """
        kept = []
        for row in self._run(name, args):
            if self._past_node_cap(row.vid):
                break
            self.handle_for(row.vid)
            kept.append(row)
        return kept

    def word_match(self, query: str, limit: int) -> list:
        """The word-match plan: `recall()` over the anchors, one call, handles minted
        for every result in rank order."""
        self._charge()
        results = recall(
            self.g, query, limit=limit, scope=self.scope,
            knowledge_scopes=self.knowledge_scopes,
        )
        for result in results:
            node_id = str(getattr(result, "node_id", "") or "")
            if node_id:
                self.handle_for(node_id)
        return results

    def _past_node_cap(self, node_id: str) -> bool:
        return node_id not in self._handle_of and len(self.handles) >= self.caps.nodes

    def _charge(self) -> None:
        if self.calls >= self.caps.calls:
            raise Refused(f"cap: {self.caps.calls} calls issued")
        if self.clock() - self.started > self.caps.seconds:
            raise Refused(f"cap: {self.caps.seconds:g} s of wall time")
        self.calls += 1

    def _run(self, name: str, args: dict) -> list[Row]:
        tool = TOOLS.get(name)
        if tool is None:
            raise Refused(f"no tool {name!r}; one of {', '.join(TOOLS)}")
        if not isinstance(args, dict):
            raise Refused("arguments must be an object")
        unknown = sorted(set(args) - set(tool.params))
        if unknown:
            raise Refused(f"{name} takes no {', '.join(unknown)}")
        kwargs: dict[str, object] = {}
        for key, param in tool.params.items():
            if key not in args:
                if param.required:
                    raise Refused(f"{name} needs {key}")
                continue
            kwargs[key] = self._argument(name, key, param, args[key])
        self._charge()
        target = {"handle": "node_id"}
        call_kwargs = {target.get(k, k): v for k, v in kwargs.items()}
        call_kwargs["scope"] = self.scope
        if tool.knowledge:
            call_kwargs["knowledge_scopes"] = self.knowledge_scopes
        return tool.run(self.g, **call_kwargs)

    def _argument(self, name: str, key: str, param: Param, value: object) -> object:
        if param.kind is int:
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= MAX_LIMIT:
                raise Refused(f"{name}.{key} must be an integer from 1 to {MAX_LIMIT}")
            return value
        if param.kind is list:
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise Refused(f"{name}.{key} must be a list of strings")
            allowed = vocabulary.EPISODIC_CLAIM_KINDS
            bad = [v for v in value if v not in allowed]
            if bad:
                raise Refused(f"{name}.{key} takes only {', '.join(allowed)}")
            return value
        if not isinstance(value, str) or not value.strip():
            raise Refused(f"{name}.{key} must be a non-empty string")
        if param.choices and value not in param.choices:
            raise Refused(f"{name}.{key} must be one of {', '.join(param.choices)}")
        if param.handle:
            node_id = self.handles.get(value)
            if node_id is None:
                raise Refused(f"{value!r} is not a handle this job returned")
            return node_id
        return value
