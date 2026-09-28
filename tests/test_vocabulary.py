"""
Retrieval vocabulary and compiler tests.

Interfaces: thalamus.substrate.vocabulary (Row, _row, _summary, rows_for's confinement
            rule), thalamus.harness.retrieval (Job, TOOLS, Caps, Refused),
            thalamus.harness.mcp_server's vocabulary wrappers,
            thalamus.eval.vocabulary (anchor_sets, measure)
Infrastructure: recording fakes in place of the primitives and the graph; tmp_path as
                the reflex ledger
Scope: which nodes a scope may be shown, and what the compiler will and will not run
       for a planner — validation, handle resolution, scope injection, the four caps.
       The traversals themselves need a graph and are exercised against the live one
       by `thalamus eval vocabulary`; a hermetic graph-backed confinement case belongs
       to qe, since `main` cannot write tests/qe/.
"""

from __future__ import annotations

import pytest

from thalamus.eval import vocabulary as measure_mod
from thalamus.harness import mcp_server, reflex, retrieval
from thalamus.harness.retrieval import Caps, Job, Refused, Tool
from thalamus.substrate import vocabulary
from thalamus.substrate.vocabulary import Row, _row, _summary

MAIN_SESSION = "scope:main:session:s1"
MAIN_CLAIM = "scope:main:claim:c1"
QE_CLAIM = "scope:qe:claim:c2"
LIT_CLAIM = "scope:literature:claim:k1"
LIT_CHUNK = "scope:literature:chunk:h1-0001"
QE_THREAD = "scope:qe:thread:t1"


def _record(label, contained=False, **props):
    return {
        "label": label,
        "props": {key: [value] for key, value in props.items()},
        "session_ts": ["2026-09-20T10:00:00"] if contained else [],
    }


# --- confinement ---------------------------------------------------------------


@pytest.mark.parametrize("node_id, record, readable", [
    # A scope's own episodic memory.
    (MAIN_SESSION, _record("Session", summary="s", timestamp="2026-09-20"), True),
    (MAIN_CLAIM, _record("Claim", contained=True, kind="decision", description="d"), True),
    # Another scope's episodic memory, even through a global hub: never.
    ("scope:qe:session:s9", _record("Session", summary="s"), False),
    (QE_CLAIM, _record("Claim", contained=True, kind="decision", description="d"), False),
    (QE_THREAD, _record("Thread", title="t"), False),
    # Knowledge in a scope the server granted: yes; in one it did not: no.
    (LIT_CLAIM, _record("Claim", kind="literature/finding", description="k"), True),
    (LIT_CHUNK, _record("Chunk", text="passage"), True),
    ("scope:dl:claim:k2", _record("Claim", kind="dl/finding", description="k"), False),
    # Hubs and records read by other tools are never rows.
    ("artifact:src/x.py", _record("Artifact"), False),
    ("entity:reflex", _record("Entity"), False),
    ("scope:main:trace:x", _record("Trace"), False),
])
def test_a_row_is_only_what_the_scope_may_read(node_id, record, readable):
    """The gate every primitive's output passes, from `main` with literature granted."""
    row = _row(node_id, record, "main", {"main", "literature"})
    assert (row is not None) is readable


def test_a_qe_claim_in_a_knowledge_scope_is_still_episodic():
    """Containment decides which rule applies, not the scope name: a session-held
    claim of a granted knowledge scope is that expert's episodic memory."""
    record = _record("Claim", contained=True, kind="decision", description="d")
    assert _row(QE_CLAIM, record, "main", {"main", "qe"}) is None


def test_row_fields_come_from_the_node_and_its_session():
    episodic = _row(MAIN_CLAIM, _record(
        "Claim", contained=True, kind="main/rejected", description="Keep it. Then more.",
    ), "main", {"main"})
    knowledge = _row(LIT_CLAIM, _record(
        "Claim", kind="literature/finding", description="A finding.",
        ingested_at="2026-08-01T00:00:00",
    ), "main", {"main", "literature"})

    assert episodic == Row(MAIN_CLAIM, "rejected", 1, "2026-09-20", "Keep it.")
    assert knowledge == Row(LIT_CLAIM, "external", 2, "2026-08-01", "A finding.")
    assert episodic.line("R1.1") == "R1.1 · rejected · tier 1 · 2026-09-20 · Keep it."
    assert knowledge.line().startswith(f"`{LIT_CLAIM}` · external")


def test_a_summary_is_the_first_sentence_cut_short():
    assert _summary("One.  Two.") == "One."
    long = _summary("x" * 400)
    assert len(long) == 160 and long.endswith("…")


# --- word search over identifiers ----------------------------------------------


@pytest.mark.parametrize("token, parts", [
    ("test_a_fingerprint_the_substitution_moved_is_recomputed",
     ["fingerprint", "substitution", "moved", "recomputed"]),
    ("pytest_cmdline_parse", ["pytest", "cmdline", "parse"]),
    ("tool_input.command", ["tool", "input", "command"]),
    ("reach-past-the-checkout", ["reach", "past", "checkout"]),
    ("buildCursorHookBlock", ["build", "cursor", "hook", "block"]),
    ("src/thalamus/harness/reflex.py", ["src", "thalamus", "harness", "reflex"]),
    # An all-lowercase compound carries no boundary to split on.
    ("theinstallmatrixcountsthesamewiring", []),
    ("assertionerror", []),
])
def test_an_identifier_splits_on_its_own_separators(token, parts):
    assert vocabulary.identifier_parts(token) == parts


@pytest.fixture
def kind_walk(monkeypatch):
    """`_kind_walk` answered from a table of term -> node ids, recording each term."""
    searched = []
    index: dict[str, list[str]] = {}

    class Walk:
        def __init__(self, found):
            self.found = found

        def id_(self):
            return self

        def to_list(self):
            return self.found

    def walk(g, kind, keyword, scope, claim_scopes):
        searched.append(keyword)
        return Walk(index.get(keyword, []))

    monkeypatch.setattr(vocabulary, "_kind_walk", walk)
    monkeypatch.setattr(vocabulary, "rows_for",
                        lambda g, ids, scope, knowledge_scopes=None: _rows(*ids))
    return searched, index


def test_an_identifier_that_matches_nothing_whole_is_searched_as_its_parts(kind_walk):
    searched, index = kind_walk
    index.update({"fingerprint": ["n1", "n2"], "recomputed": ["n1"]})
    rows = vocabulary.lexical_by_kind(
        object(), "test_a_fingerprint_the_substitution_moved_is_recomputed", "problem")
    assert searched == ["test_a_fingerprint_the_substitution_moved_is_recomputed",
                        "fingerprint", "substitution", "moved", "recomputed"]
    # Two parts of one identifier meet the floor; one part alone does not.
    assert [row.vid for row in rows] == ["n1"]


def test_an_identifier_that_matches_whole_is_not_split(kind_walk):
    """Control: `settings.json` found as written is never widened to `json`."""
    searched, index = kind_walk
    index.update({"settings.json": ["n1"], "permission": ["n1"], "json": ["n2", "n3"]})
    rows = vocabulary.lexical_by_kind(object(), "permission settings.json", "problem")
    assert searched == ["permission", "settings.json"]
    assert [row.vid for row in rows] == ["n1"]


def test_splitting_stops_at_the_term_cap(kind_walk):
    searched, _ = kind_walk
    vocabulary.lexical_by_kind(
        object(), "alpha_bravo_charlie_delta_echo foxtrot_golf_hotel_india_juliet", "session")
    parts = [term for term in searched if "_" not in term]
    assert len(parts) == vocabulary.MAX_TERMS


# --- the compiler --------------------------------------------------------------


def _rows(*ids, kind="decision"):
    return [Row(node_id, kind, 1, "2026-09-20", f"about {node_id}") for node_id in ids]


@pytest.fixture
def tools(monkeypatch):
    """Every primitive replaced by a recorder that answers from a canned table."""
    calls = []
    answers = {}

    def fake(name):
        def run(g, **kwargs):
            calls.append((name, kwargs))
            return answers.get(name, [])
        return run

    for name, tool in list(retrieval.TOOLS.items()):
        monkeypatch.setitem(
            retrieval.TOOLS, name, Tool(tool.params, fake(name), knowledge=tool.knowledge)
        )
    return calls, answers


def _job(**caps):
    return Job(object(), scope="main", knowledge_scopes=["literature"], prefix="R4",
               caps=Caps(**caps) if caps else Caps())


def test_a_call_runs_under_the_jobs_scope_and_mints_handles(tools):
    """
    Verifications:
    - the scope is the job's, and knowledge scopes reach only primitives that read them
    - rows come back under handles minted in first-seen order, and a node seen twice
      keeps its handle
    """
    calls, answers = tools
    answers["lexical_by_kind"] = _rows("scope:main:claim:a", "scope:main:claim:b")
    answers["by_path"] = _rows("scope:main:claim:b", "scope:main:session:c", kind="session")
    job = _job()

    first = job.call("lexical_by_kind", {"query": "reflex budget", "kind": "decision"})
    second = job.call("by_path", {"path": "src/x.py"})

    assert calls[0] == ("lexical_by_kind", {"query": "reflex budget", "kind": "decision",
                                            "scope": "main", "knowledge_scopes": ["literature"]})
    assert calls[1] == ("by_path", {"path": "src/x.py", "scope": "main"})
    assert first.splitlines()[0].startswith("R4.1 · decision")
    assert [line.split(" · ")[0] for line in second.splitlines()] == ["R4.2", "R4.3"]
    assert job.handles == {"R4.1": "scope:main:claim:a", "R4.2": "scope:main:claim:b",
                           "R4.3": "scope:main:session:c"}


def test_a_handle_argument_is_swapped_for_the_node_it_names(tools):
    calls, answers = tools
    answers["lexical_by_kind"] = _rows("scope:main:claim:a")
    job = _job()
    job.call("lexical_by_kind", {"query": "q w", "kind": "decision"})

    job.call("expand_one_hop", {"handle": "R4.1", "relation": "same_file", "limit": 3})

    assert calls[-1] == ("expand_one_hop", {
        "node_id": "scope:main:claim:a", "relation": "same_file", "limit": 3,
        "scope": "main", "knowledge_scopes": ["literature"]})


@pytest.mark.parametrize("name, args, reason", [
    ("drop_graph", {}, "no tool 'drop_graph'"),
    ("lexical_by_kind", {"query": "q"}, "needs kind"),
    ("lexical_by_kind", {"query": "q", "kind": "secret"}, "must be one of"),
    ("lexical_by_kind", {"query": "q", "kind": "session", "scope": "qe"}, "takes no scope"),
    ("lexical_by_kind", {"query": "", "kind": "session"}, "non-empty string"),
    ("lexical_by_kind", {"query": "q", "kind": "session", "limit": 500}, "from 1 to 10"),
    ("lexical_by_kind", {"query": "q", "kind": "session", "limit": True}, "from 1 to 10"),
    ("expand_one_hop", {"handle": "scope:qe:claim:x", "relation": "uses"},
     "not a handle this job returned"),
    ("expand_one_hop", {"handle": "R4.1", "relation": "caused_by"}, "must be one of"),
    ("session_claims", {"handle": "R4.1", "kinds": ["rejected"]}, "takes only"),
])
def test_a_call_outside_the_vocabulary_is_refused_before_it_runs(tools, name, args, reason):
    """A planner can name a node only by a handle this job showed it, and can never
    name a scope: the two ways a model would widen its own view."""
    calls, _ = tools
    job = _job()
    job.handle_for("scope:main:claim:a")  # R4.1, as if an earlier call had shown it

    answer = job.call(name, args)

    assert answer.startswith("refused: ") and reason in answer
    assert calls == [] and job.calls == 0


def test_the_call_cap_refuses_the_next_call(tools):
    calls, _ = tools
    job = _job(calls=2)
    for _ in range(2):
        job.call("threads_by_topic", {"topic": "reflex budget"})

    assert job.call("threads_by_topic", {"topic": "reflex budget"}) == (
        "refused: cap: 2 calls issued")
    assert len(calls) == 2


def test_the_wall_time_cap_refuses_once_the_job_is_past_it(tools):
    now = [100.0]
    job = Job(object(), scope="main", knowledge_scopes=[], prefix="R1",
              caps=Caps(seconds=5), clock=lambda: now[0])
    assert job.call("threads_by_topic", {"topic": "a b"}) == "no results"

    now[0] = 106.0

    assert job.call("threads_by_topic", {"topic": "a b"}) == "refused: cap: 5 s of wall time"


def test_the_node_cap_drops_new_nodes_and_says_so(tools):
    _, answers = tools
    answers["lexical_by_kind"] = _rows(*(f"scope:main:claim:{i}" for i in range(5)))
    job = _job(nodes=3)

    lines = job.call("lexical_by_kind", {"query": "q w", "kind": "decision"}).splitlines()

    assert len(job.handles) == 3
    assert lines[-1] == "cap: 3 distinct nodes returned; the rest dropped"


def test_the_row_character_cap_drops_rows_and_says_so(tools):
    _, answers = tools
    answers["lexical_by_kind"] = _rows(*(f"scope:main:claim:{i}" for i in range(5)))
    one_row = len(_rows("scope:main:claim:0")[0].line("R4.1")) + 1
    job = _job(row_chars=2 * one_row)

    lines = job.call("lexical_by_kind", {"query": "q w", "kind": "decision"}).splitlines()

    assert len(lines) == 3 and lines[-1].startswith("cap: ")
    assert job.row_chars <= 2 * one_row


def test_rows_is_call_without_the_rendering(tools):
    """
    Verifications:
    - `rows`, which a deterministic plan reads, mints handles as `call` does and is
      capped on nodes the same way, but charges no characters: no model reads it
    - a call `call` would refuse raises `Refused` with the same reason
    """
    _, answers = tools
    answers["lexical_by_kind"] = _rows(*(f"scope:main:claim:{i}" for i in range(5)))
    job = _job(nodes=3)

    rows = job.rows("lexical_by_kind", {"query": "q w", "kind": "decision"})

    assert [row.vid for row in rows] == [f"scope:main:claim:{i}" for i in range(3)]
    assert list(job.handles) == ["R4.1", "R4.2", "R4.3"]
    assert job.row_chars == 0 and job.calls == 1
    with pytest.raises(Refused, match="not a handle this job returned"):
        job.rows("expand_one_hop", {"handle": "R9.9", "relation": "uses"})


def test_word_match_is_one_call_whose_results_get_handles_in_rank_order(monkeypatch):
    class Result:
        def __init__(self, node_id):
            self.node_id = node_id

    seen = {}

    def fake_recall(g, query, limit, scope, knowledge_scopes):
        seen.update(query=query, limit=limit, scope=scope, knowledge=knowledge_scopes)
        return [Result("scope:main:session:a"), Result(""), Result(LIT_CLAIM)]

    monkeypatch.setattr(retrieval, "recall", fake_recall)
    job = _job()

    results = job.word_match("reflex budget", 3)

    assert len(results) == 3 and job.calls == 1
    assert seen == {"query": "reflex budget", "limit": 3, "scope": "main",
                    "knowledge": ["literature"]}
    assert job.handles == {"R4.1": "scope:main:session:a", "R4.2": LIT_CLAIM}


# --- the MCP surface -----------------------------------------------------------


@pytest.fixture
def graph_up(monkeypatch):
    """A connected server whose grant is the pin, with the graph faked away."""
    monkeypatch.setattr(mcp_server, "_connect", lambda: object())
    monkeypatch.setattr(mcp_server, "_close", lambda g: None)
    monkeypatch.setattr(mcp_server, "SCOPE", "main")
    monkeypatch.setattr(mcp_server, "knowledge_scopes", lambda: ["literature"])


def test_resolve_names_the_scope_when_it_may_not_read_the_node(graph_up, monkeypatch):
    monkeypatch.setattr(mcp_server, "resolve", lambda g, node, scope, ks: None)

    assert mcp_server.memory_resolve(QE_CLAIM) == (
        f"No node `{QE_CLAIM}` that scope `main` can read.")


def test_the_row_tools_render_backticked_ids_under_the_pins_scope(graph_up, monkeypatch):
    """The tap reads backticked vertex ids as what a retrieval returned."""
    seen = {}

    def fake(g, node, relation, limit, scope, ks):
        seen.update(scope=scope, ks=ks, limit=limit)
        return _rows(MAIN_CLAIM)

    monkeypatch.setattr(mcp_server, "expand_one_hop", fake)

    out = mcp_server.memory_expand(MAIN_SESSION, "same_episode", limit=99)

    assert f"`{MAIN_CLAIM}` · decision" in out
    assert seen == {"scope": "main", "ks": ["literature"], "limit": retrieval.MAX_LIMIT}


def test_an_unknown_relation_is_answered_not_raised(graph_up):
    """`caused_by` was in the design's list and has no edge in the graph."""
    assert "caused_by" not in vocabulary.RELATIONS
    assert "unknown relation" in mcp_server.memory_expand(MAIN_SESSION, "caused_by")


# --- the measurement -----------------------------------------------------------


def test_anchor_sets_come_newest_first_distinct_and_at_least_two_wide(tmp_path):
    base = tmp_path / "reflex"
    for anchors in (["a", "b"], ["c"], ["b", "a"], ["d", "e"]):
        reflex._append_firing(reflex.Firing(ts="t", session_id="s1", agent_id="",
                                            outcome="empty", anchors=anchors), base)

    assert measure_mod.anchor_sets(base, limit=5) == [["d", "e"], ["b", "a"]]


def test_the_sweep_reaches_every_kind_and_walks_from_each_top_node(tools):
    calls, answers = tools
    answers["lexical_by_kind"] = _rows("scope:main:session:a", kind="session")

    report = measure_mod.measure(object(), [["reflex.py", "budget"]], "main", [])

    names = [name for name, _ in calls]
    assert names.count("lexical_by_kind") == len(vocabulary.KINDS)
    assert names.count("expand_one_hop") == len(vocabulary.RELATIONS)  # one seed node
    assert names.count("session_claims") == 1 and names.count("by_path") == 1
    assert report.job_calls == [len(calls)] and report.job_nodes == [1]
    assert "lexical_by_kind:session: 1" in report.render()
