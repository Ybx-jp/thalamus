"""
Declared → written → read coherence tests.

Interfaces: thalamus.contract.conformance.audit_reader_projection
Infrastructure: tmp_path for the injected read path; no graph
Scope: a field the writer puts on a vertex that no read path ever names is persisted
and structurally unreachable. What is written is a property of the code, so the check
is static and a corpus cannot answer it.
"""

from pathlib import Path

import pytest

from thalamus.contract.conformance import ADVISORY, audit_reader_projection, severity_of
from thalamus.substrate.schema import Claim, Decision, LiteratureClaim, Problem, Solution


def _fields(issues, name: str) -> set[str]:
    """The field names one subject's advisory reports, or an empty set."""
    prefix = f"Unprojected {name} field(s): "
    for issue in issues:
        if issue.startswith(prefix):
            return set(issue[len(prefix) :].split(" — ")[0].split(", "))
    return set()


def test_the_audit_needs_no_graph_and_reports_only_advisories():
    """
    Scenario: The audit run with no arguments at all

    Verifications:
    - it returns findings without a connection, a corpus, or an archive
    - every finding is ADVISORY

    Absence is read twice over here — a name missing from the write side and missing
    from the read side — so a finding is a count to explain, never a verdict. A rule
    that can turn the contract permanently red is a rule that gets switched off, and
    this one has to survive history nobody intends to rewrite.
    """
    issues = audit_reader_projection()

    assert issues
    assert all(severity_of(issue) == ADVISORY for issue in issues)


def test_a_field_no_read_path_names_is_reported():
    """
    Scenario: A read path that mentions nothing

    Verifications:
    - every field the writer serializes for a Claim subtype is reported unread

    The mechanism, isolated from the repo's current state: projection is decided by
    whether a read path names the property, so a read path that names nothing must
    report the whole written set.
    """
    empty = Path(__file__).parent / "fixtures" / "__nonexistent_read_path__.py"

    issues = audit_reader_projection(read_paths=[empty])

    assert _fields(issues, "Solution") >= {"approach", "worked", "problem_ref"}
    assert _fields(issues, "Problem") == {"category"}


def test_a_read_path_that_names_a_field_clears_it(tmp_path):
    """
    Scenario: A read path whose only content is the string `worked`

    Verifications:
    - `worked` drops out of the Solution finding
    - the other Solution fields stay reported

    The check reads absence of a *name*, which is the only signal available: on the
    read side properties are selected from a fixed literal list, so a field nothing
    projects is not mentioned once. Naming it anywhere in a read path is treated as
    projecting it — generous on purpose, since a missed read would accuse working code.
    """
    reader = tmp_path / "reader.py"
    reader.write_text('PROPERTIES = ("worked",)\n')

    issues = audit_reader_projection(read_paths=[reader])

    solution = _fields(issues, "Solution")
    assert "worked" not in solution
    assert {"approach", "problem_ref"} <= solution


def test_the_stored_claim_fields_are_projected_by_the_recall_path():
    """
    Scenario: The repo's own read path, scanned as it stands

    Verifications:
    - `Solution.worked` and `Solution.approach` are not reported unprojected
    - `Decision.rationale` and `Decision.outcome` are not reported unprojected

    `_claim_properties` dumps every subtype field onto the shared Claim label, so
    these values reach the graph. `recall` renders them beside a selected claim's
    description (`substrate/reader.py`, `_RENDERED_CLAIM_FIELDS` and the `worked`
    read), so a solution recorded as having failed, and the reason a decision went the
    way it did, reach the agent. A regression that stopped reading any of them would
    surface here as the field returning to the advisory.
    """
    issues = audit_reader_projection()

    assert not {"worked", "approach"} & _fields(issues, "Solution")
    assert not {"rationale", "outcome"} & _fields(issues, "Decision")


def test_the_artifact_repo_path_projection_is_not_reported():
    """
    Scenario: The derived `(repo, path)` pair the writer puts beside an identifier

    Verifications:
    - neither `repo` nor `path` appears in the Artifact finding

    `spellings_of` resolves a query to `(repo, path)` and takes every spelling of the
    files it names, so the projection is spent rather than stranded. A regression that
    dropped that read would surface here as the pair being reported unprojected.
    """
    issues = audit_reader_projection()

    assert not {"repo", "path"} & _fields(issues, "Artifact")


def test_a_property_a_reader_selects_is_not_reported():
    """
    Scenario: Fields the reader does project — `Problem.category`, `Claim.external`

    Verifications:
    - `category` is absent from the Problem finding
    - the Claim label reports nothing

    `category` is rendered on an unsolved-problem result and `external` is read off the
    vertex by the ingress floor. Both are reachable, and a check that flagged them
    would be reporting its own blind spot as a defect.
    """
    issues = audit_reader_projection()

    assert "category" not in _fields(issues, "Problem")
    assert _fields(issues, "Claim") == set()


@pytest.mark.parametrize("model", [Claim, Decision, Problem, Solution, LiteratureClaim])
def test_every_claim_subtype_can_be_populated(model):
    """
    Scenario: Each Claim subtype built with every field set

    Verifications:
    - the writer's own serializer accepts the instance and yields its field names

    The written set is asked of `_claim_properties` rather than restated, so a subtype
    the placeholder builder cannot construct would silently drop out of the audit. A
    new field of an unhandled type fails here instead.
    """
    from thalamus.contract.conformance import _populated
    from thalamus.substrate.writer import _claim_properties

    properties = _claim_properties(_populated(model))

    # `about` and `references` become edges (ABOUT, USES); neither is a property.
    assert set(properties) == set(model.model_fields) - {
        "provenance",
        "artifacts",
        "kind",
        "description",
        "about",
        "references",
    }


def test_declared_node_types_with_no_model_are_named_not_dropped():
    """
    Scenario: `Agent`, `Trace` and `Exchange` — declared, written, no schema model

    Verifications:
    - one advisory names all three as outside the check's reach

    A tool that quietly skips what it cannot see reports a clean run over a partial
    scan. The reach limit is a finding of its own, so the gap is visible to whoever
    reads the count.
    """
    issues = audit_reader_projection()

    reach = [issue for issue in issues if issue.startswith("Outside projection reach:")]
    assert len(reach) == 1
    assert "Agent" in reach[0]
    assert "Trace" in reach[0]
    assert "Exchange" in reach[0]
