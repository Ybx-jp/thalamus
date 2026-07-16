"""
Curated-ingestion tests — manifest gating and the model-free half of ingest.

Interfaces: contract.manifest.ExpertManifest/load_manifest, harness.ingest.to_text/build_batch
Infrastructure: tmp_path for manifest files; no network, no model
Scope: the gates a document passes on its way into a knowledge subgraph. The fetch and
the model pass are exercised live; everything either side of them is pinned here.
"""

import pytest

from thalamus.contract.manifest import ExpertManifest, available_scopes, load_manifest
from thalamus.harness.ingest import IngestError, build_batch, to_text
from thalamus.substrate.schema import Tier


def _manifest(**overrides) -> ExpertManifest:
    values = dict(
        scope="literature",
        name="Technical literature",
        claim_kinds=["literature/finding", "literature/technique"],
        allowlist=["arxiv.org"],
    )
    values.update(overrides)
    return ExpertManifest(**values)


def test_allowlist_matches_hosts_and_subdomains_only():
    manifest = _manifest()

    assert manifest.allows("https://arxiv.org/abs/2401.00001")
    assert manifest.allows("https://export.arxiv.org/abs/2401.00001")
    assert not manifest.allows("https://arxiv.org.evil.example/abs/x")
    assert not manifest.allows("https://example.com/paper")


def test_local_files_bypass_the_allowlist():
    """
    docs/06: manual curation IS tier-2 trust in practice — an operator hand-feeding
    a file is the curation decision, and the allowlist gates only what `ingest`
    fetches on its own.
    """
    assert _manifest().allows("/home/op/papers/reflexion.html")


def _arxiv_batch():
    from thalamus.substrate.schema import Entity, KnowledgeBatch, LiteratureClaim, Source

    return KnowledgeBatch(
        scope="literature",
        source=Source(
            content_hash="abc",
            kind="article",
            title="A paper",
            uri="archive://abc",
            origin="https://arxiv.org/abs/2401.00001",
        ),
        claims=[LiteratureClaim(description="finding", about=["Reflexion"])],
        entities=[Entity(name="Reflexion")],
    )


def test_manifest_rejects_foreign_scope_origin_and_undeclared_kind():
    manifest = _manifest(allowlist=["aclanthology.org"])
    batch = _arxiv_batch()  # scope literature, origin arxiv.org, kind literature/finding

    issues = manifest.check_batch(batch.model_copy(update={"scope": "dl"}))
    assert any("governs" in issue for issue in issues)

    issues = manifest.check_batch(batch)
    assert any("not allowlisted" in issue for issue in issues)

    wide_open = _manifest(claim_kinds=["literature/technique"])
    issues = wide_open.check_batch(batch)
    assert any("not declared" in issue for issue in issues)


def test_manifests_load_by_scope_and_must_agree_with_their_filename(tmp_path):
    experts = tmp_path / "experts"
    experts.mkdir()
    (experts / "literature.yaml").write_text(
        "scope: literature\nname: Lit\nclaim_kinds: [literature/finding]\nallowlist: [arxiv.org]\n"
    )
    (experts / "liar.yaml").write_text("scope: something-else\nname: Liar\n")

    manifest = load_manifest("literature", base=tmp_path)
    assert manifest.tier == 2 and manifest.contract == "v0"
    assert available_scopes(tmp_path) == ["liar", "literature"]

    with pytest.raises(ValueError, match="declares scope"):
        load_manifest("liar", base=tmp_path)
    with pytest.raises(FileNotFoundError, match="Available: liar, literature"):
        load_manifest("nonexistent", base=tmp_path)


def test_html_becomes_text_and_scripts_do_not():
    """
    Scenario: An article page with script/style noise

    The digest handed to the extraction model must be the article, not the page's
    JavaScript — injection surface starts at the prompt.
    """
    page = (
        b"<html><head><style>.x{color:red}</style>"
        b"<script>evil('do not extract me')</script></head>"
        b"<body><h1>Reflexion</h1><p>Verbal self-feedback improves&nbsp;agents.</p></body>"
    )

    text = to_text(page)

    assert "Reflexion" in text and "Verbal self-feedback improves agents." in text
    assert "evil" not in text and "color:red" not in text


def test_pdfs_are_refused_not_half_parsed():
    with pytest.raises(IngestError, match="deliberately unbuilt"):
        to_text(b"%PDF-1.7 ...")


def test_build_batch_stamps_provenance_and_drops_malformed_items():
    """
    Scenario: A model extraction with one good claim, one description-less stub,
    and a title

    Verifications:
    - every node carries tier-2 provenance sourced to the origin — stamped by the
      builder, never trusted from the model
    - stubs without a description are dropped rather than written empty
    """
    data = {
        "title": "Reflexion: Language Agents with Verbal RL",
        "claims": [
            {"description": "Verbal self-feedback improves success",
             "kind": "literature/finding", "citation": "Sec 4", "about": ["Reflexion"]},
            {"kind": "literature/finding"},
        ],
        "entities": [{"name": "Reflexion", "kind": "technique"}],
    }

    batch = build_batch(
        data,
        scope="literature",
        feed="manual",
        origin="https://arxiv.org/abs/2303.11366",
        content_hash="deadbeef",
        uri="archive://deadbeef",
        byte_size=1234,
    )

    assert batch.source.title.startswith("Reflexion")
    assert len(batch.claims) == 1
    for node in (batch.source, batch.claims[0], batch.entities[0]):
        assert node.provenance.tier == Tier.CURATED
        assert node.provenance.source == "https://arxiv.org/abs/2303.11366"


def test_build_batch_backfills_referenced_known_entities_faithfully():
    """
    Scenario: The prompt told the model to reuse a known entity name; the model used
    it in `about` but — reasonably — did not re-declare something the graph already
    holds. A second `about` name is genuinely unknown.

    Verifications:
    - the known name is backfilled into the batch with the graph's own kind and
      description (the writer overwrites on match, so placeholders would clobber)
    - the unknown name is NOT backfilled — it must stay a contract rejection,
      because a new entity needs a description only the model can supply
    """
    data = {
        "title": "A Survey of Evidence Tracing",
        "claims": [
            {"description": "Provenance-bearing memory tracks how items enter memory",
             "kind": "literature/technique", "citation": "Sec 5",
             "about": ["Memory Mechanism", "Execution Provenance"]},
        ],
        "entities": [
            {"name": "Execution Provenance", "kind": "concept",
             "description": "Typed graph of an agent execution"},
        ],
    }

    batch = build_batch(
        data,
        scope="literature",
        feed="thalamus",
        origin="https://arxiv.org/abs/2606.04990",
        content_hash="deadbeef",
        uri="archive://deadbeef",
        byte_size=1234,
        known_entities=[
            {"name": "Memory Mechanism", "kind": "concept",
             "description": "How agent memory systems store and retrieve"},
            {"name": "Unreferenced Known", "kind": "technique", "description": "x"},
        ],
    )

    by_name = {entity.name: entity for entity in batch.entities}
    assert set(by_name) == {"Execution Provenance", "Memory Mechanism"}
    backfilled = by_name["Memory Mechanism"]
    assert backfilled.kind == "concept"
    assert backfilled.description == "How agent memory systems store and retrieve"

    data["claims"][0]["about"].append("Never Seen Before")
    rejected = build_batch(
        data,
        scope="literature",
        feed="thalamus",
        origin="https://arxiv.org/abs/2606.04990",
        content_hash="deadbeef",
        uri="archive://deadbeef",
        byte_size=1234,
        known_entities=[{"name": "Memory Mechanism", "kind": "concept",
                         "description": "How agent memory systems store and retrieve"}],
    )
    assert "Never Seen Before" not in {entity.name for entity in rejected.entities}


def test_prompt_carries_known_entities_for_name_convergence():
    """
    Scenario: The scope already names entities; a new article is being ingested

    Articles relate to each other through shared Entity vertices, so the prompt must
    show the model the names it is allowed to converge on — the same mechanism as the
    known-claims feed on the episodic side. No entities yet renders as an explicit
    "(none)", never a dangling template slot.
    """
    from thalamus.harness.ingest import build_prompt

    prompt = build_prompt("Some article text", "https://arxiv.org/abs/1", ["Reflexion", "RAG"])
    assert "- Reflexion" in prompt and "- RAG" in prompt

    empty = build_prompt("Some article text", "https://arxiv.org/abs/1")
    assert "(none)" in empty and "{known_entities}" not in empty
