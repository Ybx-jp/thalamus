"""Handlers for `thalamus ingest` and `thalamus backfill-chunks`.

Imported whenever the plugin loads, so every import that reaches the ingestion path
(pypdf, the fetcher, the graph driver) sits inside the handler that needs it.
"""

from __future__ import annotations

import sys

_PREFLIGHT_EXCERPT = 400


def ingest(args) -> None:
    from urllib.parse import urlparse

    from thalamus.contract.conformance import check_knowledge, write_knowledge_checked
    from thalamus.contract.manifest import load_manifest
    from thalamus.harness import extraction as extraction_mod
    from thalamus.harness import extractor_policy
    from thalamus.substrate.snapshot import DEFAULT_SNAPSHOT_PATH, snapshot_quietly
    from thalamus.substrate.writer import close_connection, connect
    from thalamus_ingest import ingest as ingest_mod

    if args.check and args.write:
        print(
            "--check and --write are opposites: --check stops before the model call, "
            "--write runs it and persists the result.",
            file=sys.stderr,
        )
        sys.exit(1)

    # `--url` is the Gremlin endpoint on all four subcommands that carry it, and on
    # this one the positional argument is normally a URL too — so `--url <document>`
    # reads as the flag that names the document. It is accepted, and it points the
    # graph write at the document's host. Validated here, ahead of the fetch, the
    # archive write and the extraction pass, all three of which would otherwise complete
    # before the error arrived as a connection failure against the paper's host.
    if urlparse(args.url).scheme not in ("ws", "wss"):
        print(
            f"--url is the Gremlin endpoint (ws:// or wss://), and got `{args.url}`.\n"
            f"The document to ingest is the positional argument:\n"
            f"  thalamus ingest {args.url} --scope {args.scope}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        manifest = load_manifest(args.scope)
    except (FileNotFoundError, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if args.check:
        _report_preflight(args)
        return

    # Advisory, like the known-claims feed: an unreachable graph degrades to an
    # ingest with no entity vocabulary, never a failed ingest — *unless* the run
    # intends to write, in which case the endpoint has to answer before the model is
    # billed. An endpoint that is merely down otherwise costs a whole extraction pass
    # and reports it at the write, after the only irreversible spend on the path.
    known_entities: list[dict] = []
    try:
        from thalamus.substrate.reader import knowledge_entities

        graph = connect(args.url)
        try:
            known_entities = knowledge_entities(graph, args.scope)
        finally:
            close_connection(graph)
    except Exception as e:
        if args.write:
            print(
                f"Graph endpoint unreachable at {args.url}: {e}\n"
                "Nothing was fetched and no model was called. --write needs the "
                "endpoint the write lands on; re-run without it to extract and report "
                "only.",
                file=sys.stderr,
            )
            sys.exit(1)

    # Ingestion is resolved as its own pass, not as a second reader of the
    # distillation setting. A paper is one model call per chunk, so an ingest can cost
    # what a day of distillation does — which is the spend worth moving on its own,
    # rather than only as a side effect of a decision about SessionEnd.
    extractor = extractor_policy.resolve(
        pass_="ingest", harness=args.harness or "", model=args.model or ""
    )
    # Printed before the call, not with the results: it names what is about to be
    # billed, and a chunked document bills it once per chunk. It is also the only place
    # a completed ingest says what extracted it — a Source vertex carries the document's
    # provenance, not the extractor's.
    print(f"Extractor: {extractor.harness}/{extractor.model} — {extractor.reason}")
    try:
        batch, run, digest = ingest_mod.ingest(
            args.location,
            scope=args.scope,
            feed=args.feed,
            model=extractor.model,
            harness=extractor.harness,
            title=args.title,
            known_entities=known_entities,
            refetch=args.refetch,
        )
    except (ingest_mod.IngestError, extraction_mod.ExtractionError) as e:
        print(f"Ingest failed: {e}", file=sys.stderr)
        sys.exit(1)

    if digest.verified_at is not None:
        stamp = digest.verified_at.strftime("%Y-%m-%d %H:%M UTC")
        print(
            f"Bytes:    the ones --check verified at {stamp}, not a fresh request — "
            f"so what is\n          written is what was checked. --refetch asks the "
            f"address again."
        )
    print(f"Retained: {batch.source.uri} ({batch.source.byte_size:,} bytes)")
    if digest.chunks > 1:
        read = digest.chunks - len(digest.failed_chunks)
        print(
            f"Read: {digest.text_chars:,} chars of text in full, "
            f"across {digest.chunks} chunked extraction passes"
        )
        if digest.failed_chunks:
            print(
                f"\n  ⚠ {len(digest.failed_chunks)} of {digest.chunks} passes failed to "
                f"parse (chunk{'s' if len(digest.failed_chunks) > 1 else ''} "
                f"{', '.join(str(n) for n in digest.failed_chunks)}).\n"
                f"    The claims below come from the other {read}; those chunks' text "
                f"is archived but uncovered.\n"
                f"    Re-running costs no refetch.",
                file=sys.stderr,
            )
    else:
        print(
            f"Read: {digest.text_chars:,} chars of text, "
            f"{digest.coverage:.0%} of it within the {digest.budget:,}-char digest budget"
        )
    if digest.truncated:
        print(
            f"\n  ⚠ TRUNCATED — {digest.discarded:,} chars past the budget were never "
            f"seen by the extractor.\n"
            f"    The claims below come from the opening {digest.budget:,} chars; the "
            f"tail is invisible,\n"
            f"    not thinly covered. If a specific mechanism has to be citable, feed "
            f"that section as\n"
            f"    its own file.",
            file=sys.stderr,
        )
    if digest.dropped_refs or digest.dropped_entities:
        lines = []
        if digest.dropped_refs:
            lines.append(
                f"    {len(digest.dropped_refs)} entity reference"
                f"{'s' if len(digest.dropped_refs) > 1 else ''} dropped from claims — "
                f"declared nowhere, and unknown to this scope:\n"
                f"      {', '.join(repr(n) for n in digest.dropped_refs)}"
            )
        if digest.dropped_entities:
            lines.append(
                f"    {len(digest.dropped_entities)} entit"
                f"{'ies' if len(digest.dropped_entities) > 1 else 'y'} dropped — "
                f"no claim is about them:\n"
                f"      {', '.join(repr(n) for n in digest.dropped_entities)}"
            )
        print(
            "\n  ⚠ The extraction's entity graph did not close; it was narrowed, not "
            "rejected.\n" + "\n".join(lines) + "\n"
            "    The claims themselves are intact — only these edges are absent.",
            file=sys.stderr,
        )
    if digest.repaired_kinds:
        print(
            f"\n  Repaired {len(digest.repaired_kinds)} claim kind"
            f"{'s' if len(digest.repaired_kinds) > 1 else ''} onto the `{args.scope}` "
            f"manifest's declared set — spelling only, no judgement:",
            file=sys.stderr,
        )
        for _index, was, now in digest.repaired_kinds:
            print(f"    {was} → {now}", file=sys.stderr)
    if digest.rejected_claims:
        from thalamus.archive import REJECT_LOG

        print(
            f"\n  ⚠ {len(digest.rejected_claims)} claim"
            f"{'s' if len(digest.rejected_claims) > 1 else ''} left the batch; the rest "
            f"is intact.\n"
            f"    The extraction is already paid for, so these are retained rather than "
            f"discarded:\n      {REJECT_LOG}",
            file=sys.stderr,
        )
        for rejection in digest.rejected_claims:
            print(
                f"    [{rejection.triage}] {rejection.reason}\n"
                f"      {rejection.description[:110]}",
                file=sys.stderr,
            )
        if any(r.triage == "ambiguous" for r in digest.rejected_claims):
            print(
                "    Ambiguous is a decision, not a defect: no rule can retype these "
                "without\n    asserting something the document may not support.",
                file=sys.stderr,
            )
    priced = f"${run.cost_usd:.2f}" if run.cost_usd is not None else "cost not reported"
    print(f"Extracted: {len(batch.claims)} claims, {len(batch.entities)} entities "
          f"({priced})")
    print(f"  {batch.source.title}")
    if batch.chunks:
        anchored = len(batch.anchors)
        print(
            f"Co-indexed: {len(batch.chunks)} verbatim chunks, "
            f"{anchored}/{len(batch.claims)} claims anchored to the passage they quote"
        )
    for claim in batch.claims:
        print(f"  - [{claim.kind.split('/')[-1]}] {claim.description[:90]}")

    issues = [*check_knowledge(batch), *manifest.check_batch(batch)]
    if issues:
        print("\nREJECTED — the batch does not satisfy the contract:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        print("The fetch is archived; fix and re-run without refetching cost.", file=sys.stderr)
        sys.exit(1)

    if not args.write:
        print("\nDRY RUN — nothing written to the graph. Re-run with --write to persist.")
        return

    graph = connect(args.url)
    try:
        source_vid = write_knowledge_checked(graph, batch, manifest)
        snapshot_quietly(graph, DEFAULT_SNAPSHOT_PATH)
        print(f"\nWritten into scope `{batch.scope}`: {source_vid}")
    finally:
        close_connection(graph)


def _report_preflight(args) -> None:
    """`thalamus ingest <doc> --scope <s> --check` — everything short of the model call.

    Deliberately not a reimplementation of the checks: it calls `ingest.preflight`, the
    same function `ingest()` calls, so the check and the ingest cannot disagree about
    which host served the bytes or whether the allowlist admits it. A prose procedure
    could not hold that parity — the `curl` incantation it replaces went through three
    revisions in one day, each against a measurement, and still stopped a redirect hop
    short of `urlopen` and sent a different User-Agent.

    Exits non-zero on refusal, because this is what a batch script gates on.
    """
    from thalamus_ingest import ingest as ingest_mod

    try:
        checked = ingest_mod.preflight(args.location, scope=args.scope, fresh=True)
    except ingest_mod.IngestError as e:
        print(f"CHECK FAILED: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Requested:    {checked.requested}")
    print(f"Served by:    {checked.origin}" + ("  (redirected)" if checked.redirected else ""))
    # A local path is not allowlisted and never was — hand-feeding a file *is* the
    # curation decision, so the gate does not consult the manifest at all. Reporting a
    # pass here would claim the manifest admitted something it never saw.
    if checked.origin.startswith(("http://", "https://")):
        print(f"Allowlisted:  yes — `{args.scope}` admits this origin")
    else:
        print("Allowlisted:  n/a — a local file is hand-fed, which is the curation decision")
    print(f"Content-Type: {checked.content_type or '(none reported)'}")
    print(f"Retained:     {checked.entry.uri} ({checked.entry.byte_size:,} bytes)")
    print(f"Text:         {len(checked.text):,} chars")
    # The title is what the check exists to confirm, and it is the one thing a HEAD
    # request cannot answer. When the bytes do not carry one — a PDF whose producer left
    # the metadata field empty or filled it with a temp filename — the opening text is
    # the answer, so it is printed either way rather than only on the failure.
    print(f"Title:        {checked.title or '(none in the document metadata)'}")
    excerpt = checked.text[:_PREFLIGHT_EXCERPT]
    print(f"\nOpening {len(excerpt):,} chars, as the extractor would read them:\n  {excerpt}")
    print(
        "\nCHECKED — nothing extracted, no model called. This is the ingest path up to "
        "the model,\nso a --write run within the day ingests these exact bytes rather "
        "than asking again."
    )


def backfill_chunks(args) -> None:
    """Co-index documents that were ingested before chunks existed.

    Needs no model: a chunk is a slice of retained bytes, and the entity vocabulary it
    tags itself with is already in the graph. So this is a rebuild, not a re-extraction
    — which is the property that makes chunk geometry a dial rather than a commitment.
    Claims, entities and Sources are left exactly as they are.
    """
    from pathlib import Path

    from gremlin_python.process.graph_traversal import __
    from gremlin_python.process.traversal import T

    from thalamus.contract.ontology import vid
    from thalamus.substrate.schema import Entity, Provenance, Tier
    from thalamus.substrate.snapshot import DEFAULT_SNAPSHOT_PATH, snapshot_quietly
    from thalamus.substrate.writer import close_connection, connect, write_anchors, write_chunks
    from thalamus_ingest.ingest import anchor_citations, build_chunks, to_text

    graph = connect(args.url)
    try:
        query = graph.V().has_label("Source").has("kind", "article")
        if args.scope:
            query = query.has("scope", args.scope)
        rows = (
            query.project("vid", "scope", "hash", "uri", "title", "chunks")
            .by(T.id).by("scope").by("content_hash").by("uri").by("title")
            .by(__.in_("DERIVED_FROM").has_label("Chunk").count())
            .to_list()
        )

        planned = 0
        skipped_existing = 0
        missing_bytes = 0
        for row in rows:
            if row["chunks"] and not args.force:
                skipped_existing += 1
                continue
            digest = str(row["uri"] or "").replace("archive://", "")
            hits = list(Path.home().glob(f".thalamus/archive/{digest[:2]}/{digest}.*"))
            if not hits:
                missing_bytes += 1
                continue
            try:
                text = to_text(hits[0].read_bytes())
            except Exception as exc:  # a PDF or unreadable payload — say so, skip it
                print(f"  skip {row['title'][:50]}: {exc}", file=sys.stderr)
                continue

            scope = row["scope"]
            # The claim's vertex ID travels with its citation — without it the anchor
            # can be computed and printed but never written, which is the whole point
            # of the edge.
            claims = (
                graph.V(row["vid"]).in_("DERIVED_FROM").has_label("Claim")
                .project("vid", "citation").by(T.id).by(
                    __.coalesce(__.values("citation"), __.constant(""))
                ).to_list()
            )
            entity_names = [
                str(name[0] if isinstance(name, list) else name)
                for name in graph.V().has_label("Entity").has("scope", scope)
                .values("name").to_list()
            ]

            cited = [str(c.get("citation") or "") for c in claims]
            chunks = build_chunks(text, entity_names)
            anchored = anchor_citations(chunks, cited)
            planned += len(chunks)
            print(f"  {row['title'][:52]:<54} {len(chunks):>4} chunks  "
                  f"{len(anchored)}/{len(cited)} anchored  [{scope}]")

            if not args.write:
                continue

            chunk_vids = write_chunks(
                graph, chunks,
                source_vid=row["vid"], content_hash=row["hash"], scope=scope,
                provenance=Provenance(tier=Tier.CURATED, source=str(row["uri"] or "")),
                entity_vids={
                    name: vid("Entity", Entity(name=name).slug(), scope)
                    for name in entity_names
                },
            )
            # The anchor edges, written last because they need every chunk to exist.
            write_anchors(graph, {
                str(claims[claim_index]["vid"]): chunk_vids[ordinal]
                for claim_index, ordinal in anchored.items()
                if ordinal in chunk_vids
            })

        print(f"\n{len(rows)} article Sources: {planned:,} chunks "
              f"({skipped_existing} already chunked, {missing_bytes} missing bytes)")
        if args.write:
            snapshot_quietly(graph, DEFAULT_SNAPSHOT_PATH)
            print("Written.")
        else:
            print("DRY RUN — nothing written. Re-run with --write to persist.")
    finally:
        close_connection(graph)
