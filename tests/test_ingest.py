"""
Curated-ingestion tests — manifest gating and the model-free half of ingest.

Interfaces: contract.manifest.ExpertManifest/load_manifest,
harness.ingest.fetch/check_origin/to_text/build_batch
Infrastructure: tmp_path for manifest files; loopback HTTP servers for redirect
handling; no egress, no model
Scope: the gates a document passes on its way into a knowledge subgraph. The model
pass is exercised live; everything either side of it is pinned here.
"""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from thalamus.contract.conformance import check_knowledge
from thalamus.contract.manifest import ExpertManifest, available_scopes, load_manifest
from thalamus.harness import extraction
from thalamus.harness import ingest as ingest_mod
from thalamus.harness.ingest import IngestError, build_batch, check_origin, fetch, to_text
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
    Manual curation IS tier-2 trust in practice — an operator hand-feeding
    a file is the curation decision, and the allowlist gates only what `ingest`
    fetches on its own.
    """
    assert _manifest().allows("/home/op/papers/reflexion.html")


def _loopback(handler_cls):
    """A throwaway HTTP server on 127.0.0.1. Yields its base URL, then shuts down."""
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def test_fetch_records_the_host_that_answered_not_the_one_asked():
    """
    Scenario: a requested URL 302s to a different host, which serves the bytes

    `origin` is consumed as a claim about where the bytes came from — the allowlist
    reads it, the Source node carries it as provenance, and supersession keys on it.
    So it must name the responder. Reporting the requested URL would let any address
    on the allowlist redirect content in from anywhere under its own name, and the
    allowlist would answer correctly about a URL nobody fetched.

    Loopback only, so this is hermetic: no egress, and 127.0.0.1 is on no allowlist.
    """
    payload = b"served by the host that actually answered"

    class _Target(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            return

    target_server, target_base = _loopback(_Target)
    target_url = f"{target_base}/actually-served-here"

    class _Redirector(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(302)
            self.send_header("Location", target_url)
            self.end_headers()

        def log_message(self, *_args):
            return

    redirect_server, redirect_base = _loopback(_Redirector)

    try:
        body, origin = fetch(f"{redirect_base}/looks-fine")
    finally:
        for server in (redirect_server, target_server):
            server.shutdown()
            server.server_close()

    # The control: without this, origin == the requested URL would be correct here
    # for the wrong reason, because no redirect was followed at all.
    assert body == payload
    assert origin == target_url


def test_ingest_gates_the_serving_origin_before_it_spends_anything(tmp_path, monkeypatch):
    """
    Scenario: an allowlisted URL redirects to a host on no allowlist

    Two properties in one, because either alone leaves the hole open. The gate reads
    the origin that *answered* — checking the requested URL passes an allowlisted
    address that fetched from anywhere. And it runs ahead of both irreversible steps:
    an off-list document must not land in the archive the operator has to account
    for, nor go through a tool-enabled model. Both are spent unrecoverably, so a
    check made after them reports a leak rather than preventing one.
    """
    experts = tmp_path / "experts"
    experts.mkdir()
    (experts / "literature.yaml").write_text(
        "scope: literature\nname: Lit\nclaim_kinds: [literature/finding]\nallowlist: [arxiv.org]\n"
    )
    monkeypatch.setenv("THALAMUS_CONFIG_DIR", str(tmp_path))

    def _answered_elsewhere(_location):
        return b"long enough to extract from " * 40, "https://elsewhere.example/served-here"

    def _must_not_run(*_args, **_kwargs):
        raise AssertionError("ran past the allowlist gate")

    monkeypatch.setattr(ingest_mod, "fetch", _answered_elsewhere)
    monkeypatch.setattr(ingest_mod, "archive_bytes", _must_not_run)
    monkeypatch.setattr(extraction, "run_extraction", _must_not_run)

    with pytest.raises(IngestError, match="not allowlisted") as caught:
        ingest_mod.ingest("https://arxiv.org/html/2401.00001", scope="literature")

    message = str(caught.value)
    # Both addresses, because the refusal is unreadable with either one missing: the
    # operator typed one URL and the gate is talking about another.
    assert "elsewhere.example" in message and "arxiv.org" in message


def test_a_url_whose_scope_has_no_manifest_is_refused_not_waved_through(tmp_path, monkeypatch):
    """An ungoverned scope is the case with no curation at all, so it fetches nothing.

    Local paths still pass: an operator hand-feeding a file IS the curation decision,
    and there is no manifest to consult for a decision already made.
    """
    (tmp_path / "experts").mkdir()
    monkeypatch.setenv("THALAMUS_CONFIG_DIR", str(tmp_path))

    with pytest.raises(IngestError, match="no usable manifest"):
        check_origin("https://arxiv.org/abs/2401.00001", "unmanifested")

    check_origin("/home/op/papers/reflexion.html", "unmanifested")


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


def _pdf_bytes(*lines: str) -> bytes:
    """A one-page PDF whose content stream shows `lines`, one text line each.

    Built here rather than committed as a binary fixture: a fixture cannot be read in
    review and drifts silently from what the parser is asked to handle, while this puts
    the text going in beside the assertion on the text coming out. Generating it needs
    nothing — only reading it back needs the `pdf` extra.

    The text goes through a base-14 Helvetica with no /Encoding override, so it is
    StandardEncoding: `\\257` is the `fl` ligature glyph, which is how a real typeset
    paper delivers one. That makes the ligature case a genuine extraction result rather
    than a string this test typed itself.
    """
    shown = "\n".join(f"({line}) Tj 0 -14 Td" for line in lines)
    stream = f"BT /F1 11 Tf 50 700 Td\n{shown}\nET".encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_at}\n%%EOF\n").encode()
    return bytes(out)


def test_a_pdf_becomes_text():
    """
    Scenario: a PDF fed to the extractor with the `pdf` extra installed

    Refusing this format never kept a literature out — ICSE, CHI, FSE and TSE publish
    PDF only, including on hosts the allowlist already reaches — it routed one through
    hand-conversion, which archives the conversion instead of the paper and records a
    local path where a citable origin belongs.
    """
    pytest.importorskip("pypdf", reason="PDF extraction rides the `pdf` extra")

    text = to_text(_pdf_bytes("Speculative merges detect conflicts before a merge."))

    assert "Speculative merges detect conflicts" in text


def test_a_pdfs_line_breaks_and_ligatures_do_not_sever_its_terms():
    """
    Scenario: a PDF that hyphenated `conflict` across a line break and set `fl` as a
    ligature glyph — both of which a typeset paper does routinely

    Verification: `conflict` and `flagged` each survive as one token.

    Lexical matching is what recall runs on, so a term split by typesetting is a term
    the graph cannot be searched for. Collapsing whitespace first would leave
    `con- flict`, which is why the rejoin runs before it.
    """
    pytest.importorskip("pypdf", reason="PDF extraction rides the `pdf` extra")

    # `\257` is StandardEncoding's `fl`; the second line begins mid-word.
    text = to_text(_pdf_bytes("A merge con-", r"\257ict, and a \257agged one."))

    assert "conflict" in text
    assert "con- flict" not in text and "con-flict" not in text
    assert "flagged" in text


def test_a_pdf_with_no_extractable_text_is_named_for_what_it_is():
    """A scanned PDF parses fine and yields nothing.

    Reported as image-only rather than falling through to `ingest()`'s length floor,
    which would call it a document too short to assert anything and send the reader
    looking at the wrong thing.
    """
    pytest.importorskip("pypdf", reason="PDF extraction rides the `pdf` extra")

    with pytest.raises(IngestError, match="scanned or image-only"):
        to_text(_pdf_bytes())


def test_a_pdf_without_the_extra_refuses_and_names_the_extra(monkeypatch):
    """Honest degradation, not a silent empty read.

    The import is forced to fail rather than the extra being uninstalled, so this runs
    on a box that has it. Without the guard an absent parser would extract nothing and
    read downstream as a short document.
    """
    import builtins  # noqa: PLC0415

    real_import = builtins.__import__

    def refuse_pypdf(name, *args, **kwargs):
        if name == "pypdf":
            raise ImportError("No module named 'pypdf'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse_pypdf)

    with pytest.raises(IngestError, match="uv sync --extra pdf") as caught:
        to_text(b"%PDF-1.7 ...")

    # It must also name the fallback's cost, or the fallback reads as equivalent.
    assert "local path as the origin" in str(caught.value)


def test_the_arxiv_abstract_page_is_refused_whatever_format_it_would_have_served():
    """
    Scenario: `arxiv.org/abs/<id>` handed to ingest

    Verifications:
    - refused before anything is fetched
    - both full-text forms are named, by the same id

    An abstract page parses cleanly and yields abstract-level claims that read exactly
    like paper-level ones, so the failure is silent — which is what earns a refusal
    rather than a warning. It is checked on the address, not inside the PDF path,
    because the hazard was never about format.
    """
    with pytest.raises(IngestError, match="abstract page") as caught:
        ingest_mod.check_location("https://arxiv.org/abs/2503.23278")

    message = str(caught.value)
    assert "https://arxiv.org/html/2503.23278" in message
    assert "https://arxiv.org/pdf/2503.23278" in message


def test_the_full_text_addresses_are_not_refused():
    """The control. A refusal that fired on everything would pass the test above."""
    for allowed in (
        "https://arxiv.org/html/2503.23278",
        "https://arxiv.org/pdf/2503.23278",
        "https://dl.acm.org/doi/abs/10.1145/1985793.1985839",  # not arXiv's /abs/
        "/home/ybx/.thalamus/hand-fed/crystal.txt",
    ):
        assert ingest_mod.check_location(allowed) is None


def test_digest_report_names_what_the_extractor_never_saw():
    """
    Scenario: A document whose extracted text runs past the digest budget

    The archive keeps every byte, but the model only ever sees `budget` chars, and
    the discard is silent on the model's side. Payload bytes cannot stand in for
    this — markup-to-text ratio swings by an order of magnitude — so the report is
    denominated in text chars, the same unit as the budget.
    """
    from thalamus.harness.ingest import DigestReport

    over = DigestReport(text_chars=90_025, budget=24_000)
    assert over.truncated
    assert over.discarded == 66_025
    assert round(over.coverage, 2) == 0.27

    within = DigestReport(text_chars=4_862, budget=24_000)
    assert not within.truncated
    assert within.discarded == 0 and within.coverage == 1.0

    assert DigestReport(text_chars=0).coverage == 0.0

    # Chunking reads past the budget, so an over-budget document is no longer a
    # truncated one — the warning must not fire for a document that was read in full.
    chunked = DigestReport(text_chars=90_025, budget=24_000, chunks=10)
    assert not chunked.truncated
    assert chunked.discarded == 0 and chunked.coverage == 1.0


def test_chunking_covers_the_whole_document_without_severing_words():
    """
    Scenario: Text longer than one chunk is split for multi-pass extraction

    Every char must land in some chunk — the point of chunking is that nothing is
    silently dropped, which is the defect it exists to fix. Boundaries fall on
    whitespace because the model is asked for verbatim citations, and a half-word
    is an anchor that will not match the source.
    """
    from thalamus.harness.ingest import chunk_text

    words = " ".join(f"word{n:04d}" for n in range(4000))
    chunks = chunk_text(words, size=1000, overlap=100)

    assert len(chunks) > 1
    assert all(chunk == chunk.strip() for chunk in chunks)
    assert not any(chunk.endswith("wor") or chunk.endswith("word") for chunk in chunks)

    # Coverage: every token of the source survives into at least one chunk.
    covered = set()
    for chunk in chunks:
        covered.update(chunk.split())
    assert covered == set(words.split())

    # A document at or under the size is one chunk — no cost regression for short docs.
    assert chunk_text("short document", size=1000) == ["short document"]

    with pytest.raises(ValueError):
        chunk_text(words, size=100, overlap=100)


def test_chunked_prompts_thread_the_document_vocabulary_forward():
    """
    Scenario: Building the prompt for part 3 of a chunked document

    The convergence feed points inward for a chunked ingest: names minted by earlier
    chunks are offered to later ones, so one paper's vocabulary converges instead of
    fragmenting per chunk. The part banner also has to stop the model inventing a
    title from a section heading it happens to be looking at.
    """
    from thalamus.harness.ingest import build_prompt

    prompt = build_prompt("chunk text", "file://doc", ["Gleaning"], part=(3, 7))
    assert "PART 3 OF 7" in prompt
    assert "- Gleaning" in prompt
    assert "2-6" in prompt and "3-12" not in prompt
    assert "never invent one" in prompt

    whole = build_prompt("chunk text", "file://doc", ["Gleaning"])
    assert "PART" not in whole and "3-12" in whole


def test_merge_retains_duplicate_claims_and_dedups_entities_by_exact_name():
    """
    Scenario: Two chunks of one document each report claims, with an entity in common

    Claims are retained verbatim, never collapsed: the one measurement in scope on
    merging near-duplicates at write time has it regressing below plain RAG
    (`scope:literature:claim:1404d8270a1ab463`), so duplication is accepted as the
    cheaper error. Entities dedup on exact name only — that is upsert identity, not
    a similarity judgement — and a near-name stays a separate entity rather than
    being silently fused.
    """
    from thalamus.harness.ingest import merge_extractions

    merged = merge_extractions([
        {
            "title": "",
            "claims": [{"description": "Chunking raises recall."}],
            "entities": [{"name": "Gleaning", "kind": "technique", "description": "from part 1"}],
        },
        {
            "title": "The Real Title",
            "claims": [
                {"description": "Chunking raises recall."},
                {"description": "Overlap is ungrounded."},
            ],
            "entities": [
                {"name": "Gleaning", "kind": "technique", "description": "from part 2"},
                {"name": "Gleanings", "kind": "technique", "description": "near-name"},
            ],
        },
    ])

    assert len(merged["claims"]) == 3  # the repeated claim survives twice
    assert merged["title"] == "The Real Title"  # first non-empty title wins

    entities = {entity["name"]: entity for entity in merged["entities"]}
    assert set(entities) == {"Gleaning", "Gleanings"}
    assert entities["Gleaning"]["description"] == "from part 1"  # first declaration wins


def test_latex_escapes_in_a_verbatim_citation_do_not_fail_the_document():
    """
    Scenario: An arXiv HTML page renders math as literal \\sim beside the glyph, and
    the model quotes it verbatim into a citation

    Citations are verbatim by contract, so the source's notation rides into the
    value. YAML rejects an unknown escape in a double-quoted scalar and fails the
    whole document over one character — measured live on arXiv 2601.00821, where it
    killed a ten-pass ingest. The backslash must survive as the literal the source
    contained, not be dropped: a citation is an anchor that has to match the source.
    """
    from thalamus.harness.extraction import parse_extraction

    raw = (
        "```yaml\ntitle: T\nclaims:\n  - description: d\n"
        "    kind: literature/finding\n"
        '    citation: "the EDU store saturates ∼ \\sim 11pp below chunks"\n'
        "    about: [X]\nentities:\n  - name: X\n    kind: concept\n"
        "    description: y\n```"
    )
    data = parse_extraction(raw)
    assert "\\sim" in data["claims"][0]["citation"]

    # Valid escapes still mean what they mean — the repair must not double them.
    kept = parse_extraction('```yaml\ntitle: "a \\"quoted\\" word"\n```')
    assert kept["title"] == 'a "quoted" word'


def test_one_unparseable_chunk_costs_its_own_pass_and_says_so():
    """
    Scenario: Chunk 3 of 4 returns YAML that survives no repair

    Partial acceptance at chunk granularity — the rule the extraction path already
    applies to items. One malformed pass must not void the passes that parsed, and
    must not vanish either: a silently dropped chunk is a coverage hole, which is
    the exact defect chunking exists to close.
    """
    from thalamus.harness.ingest import DigestReport

    report = DigestReport(text_chars=90_000, chunks=4, failed_chunks=(3,))
    assert report.chunks - len(report.failed_chunks) == 3
    assert not report.truncated  # a parse failure is not a truncation
    assert report.failed_chunks == (3,)


def test_combined_run_never_reports_an_unpriced_pass_as_free():
    """
    Scenario: Multi-pass costs are summed for the operator's confirm step

    A None cost means the CLI did not report one, not that the call was free
    (extraction.ExtractionRun says so explicitly). Summing it as zero would
    understate a chunked ingest — the run whose cost the operator most needs.
    """
    from thalamus.harness.extraction import ExtractionRun
    from thalamus.harness.ingest import _combine_runs

    combined = _combine_runs([
        ExtractionRun(text="a", cost_usd=0.15, duration_ms=1000),
        ExtractionRun(text="b", cost_usd=0.20, duration_ms=2000),
    ])
    assert combined.cost_usd == pytest.approx(0.35)
    assert combined.duration_ms == 3000

    partial = _combine_runs([
        ExtractionRun(text="a", cost_usd=None),
        ExtractionRun(text="b", cost_usd=0.20),
    ])
    assert partial.cost_usd == pytest.approx(0.20)

    assert _combine_runs([ExtractionRun(text="a"), ExtractionRun(text="b")]).cost_usd is None


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
    - the unknown name is NOT backfilled — a new entity needs a description only the
      model can supply, and inventing one would manufacture content on the write path
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
    narrowed = build_batch(
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
    assert "Never Seen Before" not in {entity.name for entity in narrowed.entities}


def test_an_unresolvable_entity_reference_costs_its_edge_not_the_document():
    """
    Scenario: extraction emits the two lists out of step — one claim is `about` a name
    nothing declared, and one declared entity is reached by no claim. Both are
    `check_knowledge` violations, and the contract judges a batch whole, so left alone
    they reject every claim in the document over an edge.

    Verifications:
    - the surviving claim keeps its resolvable `about` name and loses only the dangling
      one; its description and citation are untouched
    - a claim stripped to no entities at all is still kept — `about` is a retrieval
      affordance, not the claim's identity
    - the orphan entity is dropped, since nothing can reach it
    - the assembled batch now passes the contract that would have rejected it
    """
    data = {
        "title": "Interrupted Time Series",
        "claims": [
            {"description": "Rank correlation survives non-normal residuals",
             "kind": "literature/finding", "citation": "Table 3",
             "about": ["Effect Size", "Spearman's rank correlation"]},
            {"description": "Autocorrelation inflates the false positive rate",
             "kind": "literature/finding", "citation": "Sec 2",
             "about": ["Spearman's rank correlation"]},
        ],
        "entities": [
            {"name": "Effect Size", "kind": "concept", "description": "Magnitude"},
            {"name": "Reached By Nothing", "kind": "concept", "description": "y"},
        ],
    }

    batch = build_batch(
        data,
        scope="eval-methodology",
        feed="campaign-statistics",
        origin="https://arxiv.org/html/2603.17281",
        content_hash="cafe",
        uri="archive://cafe",
        byte_size=99,
    )

    assert len(batch.claims) == 2
    assert batch.claims[0].about == ["Effect Size"]
    assert batch.claims[0].citation == "Table 3"
    assert batch.claims[1].about == []
    assert {entity.name for entity in batch.entities} == {"Effect Size"}
    assert check_knowledge(batch) == []


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


def test_prompt_demands_quoted_entity_names():
    """
    Scenario: A document names an entity whose own name contains a comma

    Measured on the Nielsen heuristics ingest, 2026-08-09: the model emitted
    `about: [Help Users Recognize, Diagnose, and Recover from Errors]` — a YAML flow
    sequence, so one entity parsed as three. The contract rejected the batch for two
    undeclared references and an orphan entity, which is correct behavior and a
    completely opaque diagnosis. The fix is at the format level, so the guard has to
    be too: the template must show the quoted block form, and say why.
    """
    from thalamus.harness.ingest import build_prompt

    prompt = build_prompt("text", "https://example.com/a")
    assert 'about:\n      - "Entity Name"' in prompt, "flow-sequence example splits on commas"
    assert 'name: "Entity Name"' in prompt
    assert "double-quote entity names" in prompt


def test_chunks_carry_their_location_and_anchor_only_on_a_real_quote():
    """
    Scenario: A document is chunked for co-indexing and its claims anchored

    The anchor edge's whole value is that it points at the passage the note actually
    came from, so a citation the model paraphrased must get NO anchor rather than a
    guessed one. Chunk `about` is filled by literal occurrence of names the
    batch already declared, which is why chunk-to-chunk "mentions" is a 2-hop walk
    through shared entities instead of a quadratic edge set.
    """
    from thalamus.harness.ingest import anchor_citations, build_chunks
    from thalamus.substrate.schema import LiteratureClaim

    text = ("alpha " * 2000) + "the measured gap was 15.9 points " + ("omega " * 2000)
    claims = [
        LiteratureClaim(description="A real quote", citation="the measured gap was 15.9 points"),
        LiteratureClaim(description="Paraphrased", citation="the authors found a sizeable gap"),
        LiteratureClaim(description="No citation at all", citation=None),
    ]

    chunks = build_chunks(text, claims, ["Omega"])
    assert len(chunks) > 1
    assert all(c.end > c.start for c in chunks)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    # Located: the slice really lives where the chunk says it does.
    for chunk in chunks:
        assert text[chunk.start:chunk.start + 40].strip().startswith(chunk.text[:30].strip()[:20])
    # `about` is literal-occurrence over declared names only.
    assert any("Omega" in c.about for c in chunks)

    anchors = anchor_citations(chunks, claims)
    assert 0 in anchors                      # the verbatim quote anchors
    assert 1 not in anchors and 2 not in anchors  # paraphrase and absence do not
    assert anchors[0] in {c.ordinal for c in chunks}


def test_contract_rejects_a_dangling_anchor():
    """
    Scenario: A batch anchors a claim to a chunk ordinal it does not contain

    A dangling anchor strands the claim it was meant to ground, which is the one
    failure that makes the edge worse than its absence.
    """
    from thalamus.contract.conformance import check_knowledge
    from thalamus.substrate.schema import Chunk

    batch = _arxiv_batch()
    good = batch.model_copy(update={
        "chunks": [Chunk(text="a passage", ordinal=0, start=0, end=9)],
        "anchors": {0: 0},
    })
    assert not [i for i in check_knowledge(good) if "anchor" in i]

    dangling = good.model_copy(update={"anchors": {0: 7}})
    assert any("dangling anchor" in issue for issue in check_knowledge(dangling))

    empty = good.model_copy(update={"chunks": [Chunk(text="   ", ordinal=0, start=0, end=3)]})
    assert any("a chunk is its text" in issue for issue in check_knowledge(empty))
