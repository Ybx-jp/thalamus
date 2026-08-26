"""The seam between the graph and the audit rules — `conformance._fetch`.

Interfaces: thalamus.contract.conformance (_fetch, _AUDIT_VERTEX_KEYS, _AUDIT_EDGE_KEYS,
edge_property_vocabulary, audit_declarations).

`_fetch` asks the graph for a *named subset* of properties rather than all of them,
which is what keeps `contract check` from shipping every Chunk's text to answer
questions about nine strings. That narrowing fails open: a rule reading a key nobody
put in the tuple sees `None` and passes, and the check reports green while no longer
checking. The first test here is the guard against exactly that, and it is the reason
this file exists — the rules themselves are covered in `test_graph_audit.py`, over rows
built by hand, which is precisely the coverage that cannot see this seam.
"""

from __future__ import annotations

import ast
from pathlib import Path

from thalamus.contract import conformance
from thalamus.contract.conformance import (
    _AUDIT_EDGE_KEYS,
    _AUDIT_VERTEX_KEYS,
    AuditEdge,
    AuditVertex,
    _fetch,
    audit_declarations,
)

SOURCE = Path(conformance.__file__)


def _keys_read_from(attribute: str) -> set[str]:
    """Every literal key this module reads off `<something>.properties`.

    Static rather than dynamic because the failure being guarded is silence: a rule
    reading an unfetched key raises nothing and returns nothing, so no runtime probe
    sees it. Matches `x.properties.get("k")` and `x.properties["k"]`, which is how every
    rule in the module spells it.
    """
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    found: set[str] = set()

    for node in ast.walk(tree):
        # x.properties.get("k")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "properties"
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == attribute
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            found.add(node.args[0].value)
        # x.properties["k"]
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "properties"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == attribute
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            found.add(node.slice.value)
    return found


def test_every_vertex_key_a_rule_reads_is_fetched():
    """The fail-open guard. Add a rule reading a new key and this fails, loudly.

    Without it, the same change disables the rule instead: `_fetch` would not ask for
    the key, `.get` would return `None`, and the audit would pass on every vertex.
    """
    read = _keys_read_from("vertex") | set(conformance._PROVENANCE_FIELDS)
    missing = sorted(read - set(_AUDIT_VERTEX_KEYS))
    assert not missing, (
        f"{missing} are read by a rule and not fetched — the rule cannot fire. "
        f"Add them to _AUDIT_VERTEX_KEYS."
    )


def test_every_edge_key_a_rule_reads_is_fetched():
    read = _keys_read_from("edge")
    missing = sorted(read - set(_AUDIT_EDGE_KEYS))
    assert not missing, f"{missing} are read by a rule and not fetched by _fetch"


def test_no_vertex_key_is_fetched_that_nothing_reads():
    """The other direction, so the list cannot quietly grow back toward everything."""
    read = _keys_read_from("vertex") | set(conformance._PROVENANCE_FIELDS)
    unread = sorted(set(_AUDIT_VERTEX_KEYS) - read)
    assert not unread, f"{unread} are fetched and no rule reads them"


class _FakeTraversal:
    """The fluent surface `_fetch` uses, recording what it was asked for."""

    def __init__(self, rows, log, kind):
        self._rows = rows
        self._log = log
        self._kind = kind

    def element_map(self, *keys):
        self._log[f"{self._kind}_element_map"] = keys
        return self

    def project(self, *names):
        self._log[f"{self._kind}_project"] = names
        return self

    def by(self, *_args):
        return self

    def to_list(self):
        return self._rows


class _FakeG:
    def __init__(self, vertex_rows, edge_rows):
        self.log: dict = {}
        self._vertex_rows = vertex_rows
        self._edge_rows = edge_rows

    def V(self):
        return _FakeTraversal(self._vertex_rows, self.log, "vertex")

    def E(self):
        return _FakeTraversal(self._edge_rows, self.log, "edge")


def test_fetch_asks_only_for_the_declared_vertex_keys():
    from gremlin_python.process.traversal import T

    g = _FakeG([{T.id: "v1", T.label: "Claim", "tier": 1}], [])
    _fetch(g)
    assert g.log["vertex_element_map"] == _AUDIT_VERTEX_KEYS


def test_fetch_builds_audit_vertices_from_scalar_values():
    """`element_map` returns scalars where `value_map` returned single-element lists.

    The unwrapping the old shape needed is gone, so a regression that reintroduced
    `value_map` would leave every property as a one-element list and silently break
    every `== ` comparison in the rules.
    """
    from gremlin_python.process.traversal import T

    g = _FakeG(
        [{T.id: "scope:a:claim:1", T.label: "Claim", "tier": 1, "scope": "a"}],
        [],
    )
    vertices, _ = _fetch(g)
    assert vertices == [
        AuditVertex(vid="scope:a:claim:1", label="Claim", properties={"tier": 1, "scope": "a"})
    ]


def test_fetch_builds_audit_edges_and_omits_absent_properties():
    """`coalesce` supplies "" for a property the edge lacks; `_fetch` must drop it.

    A rule testing `.get("role") == "citation"` is unharmed either way, but one testing
    `"role" in properties` would see a key the edge does not carry.
    """
    g = _FakeG(
        [],
        [
            {"label": "REFERENCES", "from": "v1", "to": "v2",
             "from_label": "Claim", "to_label": "Source", "role": "citation", "basis": ""},
            {"label": "ABOUT", "from": "v3", "to": "v4",
             "from_label": "Chunk", "to_label": "Entity", "role": "", "basis": ""},
        ],
    )
    _, edges = _fetch(g)
    assert edges == [
        AuditEdge(
            label="REFERENCES", from_vid="v1", from_label="Claim",
            to_vid="v2", to_label="Source", properties={"role": "citation"},
        ),
        AuditEdge(
            label="ABOUT", from_vid="v3", from_label="Chunk",
            to_vid="v4", to_label="Entity", properties={},
        ),
    ]


def test_fetch_projects_the_endpoint_columns_the_rules_need():
    g = _FakeG([], [])
    _fetch(g)
    assert g.log["edge_project"] == (
        "label", "from", "to", "from_label", "to_label", *_AUDIT_EDGE_KEYS
    )


def test_audit_declarations_derives_the_vocabulary_when_none_is_supplied():
    """The default path, which every hand-built-rows test in the suite relies on."""
    edges = [AuditEdge(label="TOUCHES", from_vid="a", from_label="Session",
                       to_vid="b", to_label="Artifact", properties={"anchors": [1]})]
    supplied = audit_declarations([], edges, {"TOUCHES": {"anchors"}})
    derived = audit_declarations([], edges)
    assert [str(i) for i in supplied] == [str(i) for i in derived]


def test_a_supplied_vocabulary_overrides_what_the_rows_carry():
    """The narrowed rows carry only `role`/`basis`, so the aggregate must win.

    If the supplied map were merged with the rows rather than replacing them, every
    narrowed run would report every other declared edge property as unwritten.
    """
    edges = [AuditEdge(label="TOUCHES", from_vid="a", from_label="Session",
                       to_vid="b", to_label="Artifact", properties={})]
    issues = [str(i) for i in audit_declarations([], edges, {"TOUCHES": {"anchors"}})]
    assert not [i for i in issues if "anchors" in i and "Unwritten" in i]
