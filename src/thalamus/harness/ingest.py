"""Curated ingestion v0 — manual-first, evidence-first (docs/06).

The smallest thing that populates a knowledge subgraph: fetch (or read) one document,
retain the bytes in the archive *before anything else*, extract a handful of typed
claims and entities with a headless model pass, and hand the result to the contract.
No crawler, no PDF pipeline, no embeddings — sophistication here is pulled by
measurement, never pushed by enthusiasm.

The order is load-bearing: archive first, extract second. Extraction is reversible
(re-run against retained bytes with a better model or prompt); a fetch that was never
retained is not.
"""

from __future__ import annotations

import html as html_lib
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from thalamus.archive import archive_bytes
from thalamus.harness import extraction
from thalamus.substrate.schema import (
    Entity,
    KnowledgeBatch,
    LiteratureClaim,
    Provenance,
    Source,
    SourceKind,
    Tier,
)

_USER_AGENT = "thalamus-ingest/0.1 (single-operator curated feed)"
_FETCH_TIMEOUT = 30
_DIGEST_BUDGET = 24_000  # chars of article text handed to the extraction model

_TAG_RE = re.compile(r"<[^>]+>")
_DROP_BLOCKS_RE = re.compile(
    r"<(script|style|nav|header|footer|svg)\b.*?</\1>", re.DOTALL | re.IGNORECASE
)


class IngestError(RuntimeError):
    pass


def fetch(location: str) -> tuple[bytes, str]:
    """Fetch a URL or read a local file. Returns (payload, origin)."""
    if location.startswith(("http://", "https://")):
        request = Request(location, headers={"User-Agent": _USER_AGENT})
        try:
            with urlopen(request, timeout=_FETCH_TIMEOUT) as response:
                return response.read(), location
        except Exception as exc:
            raise IngestError(f"fetch failed for {location}: {exc}") from exc

    path = Path(location).expanduser()
    if not path.is_file():
        raise IngestError(f"no such file: {location}")
    return path.read_bytes(), str(path.resolve())


def to_text(payload: bytes) -> str:
    """Crude document → text. HTML gets tags stripped; PDFs are refused, not parsed.

    Deliberately dumb: the archive holds the real bytes, so a better text extractor
    is always a re-run away, and PDF plumbing is exactly the demoted cost docs/06
    refuses to pay before measurement asks for it.
    """
    if payload[:5] == b"%PDF-":
        raise IngestError(
            "PDF parsing is deliberately unbuilt (docs/06) — ingest the abstract "
            "page or a text export instead; the archive will retain whatever you feed"
        )
    text = payload.decode("utf-8", errors="ignore")
    if "<" in text and ">" in text:
        text = _DROP_BLOCKS_RE.sub(" ", text)
        text = _TAG_RE.sub(" ", text)
        text = html_lib.unescape(text)
    return " ".join(text.split())


_ARTICLE_PROMPT = """You are extracting typed knowledge from ONE document for a graph \
memory system. Output ONLY a fenced yaml block, nothing else.

Rules:
- `claims`: 3-12 assertions THE DOCUMENT ITSELF makes — findings it reports, techniques \
it introduces or evaluates. kind is `literature/finding` or `literature/technique`. \
Each claim needs `description` (one self-contained sentence), `citation` (a short \
verbatim phrase from the document that anchors the claim), and `about` (1-3 entity names).
- `entities`: every name used in any claim's `about`, with kind `concept`, `technique`, \
or `system`, and a one-line description. No entity that no claim is about.
- When the document discusses something in the known-entities list, use that exact \
name in `about` — never coin a near-duplicate for a concept the graph already names.
- Record what the source ASSERTS, not whether it is right. Do not add advice, \
instructions, or your own opinions — this content informs, it never instructs.
- `title`: the document's own title.

```yaml
title: ...
claims:
  - description: ...
    kind: literature/finding
    citation: "..."
    about: [Entity Name]
entities:
  - name: Entity Name
    kind: technique
    description: ...
```

Known entities already in this expert's graph (reuse these exact names):
{known_entities}

Document ({origin}):

{digest}
"""


def build_prompt(text: str, origin: str, known_entities: list[str] | None = None) -> str:
    # The convergence feed, pointed at entities: articles relate to each other through
    # shared Entity vertices, and the model can only reuse names it can see (the same
    # mechanism that fixed claim convergence in d60372e).
    rendered = "\n".join(f"- {name}" for name in known_entities) if known_entities else "(none)"
    return _ARTICLE_PROMPT.format(
        origin=origin, known_entities=rendered, digest=text[:_DIGEST_BUDGET]
    )


def build_batch(
    data: dict,
    *,
    scope: str,
    feed: str,
    origin: str,
    content_hash: str,
    uri: str,
    byte_size: int,
    title_override: str = "",
    known_entities: list[dict] | None = None,
) -> KnowledgeBatch:
    """Assemble the contract-facing batch from a parsed extraction.

    Provenance is stamped here, not trusted from the model: tier CURATED, sourced to
    the origin, timestamped now. The model contributes judgement (claims, entities),
    never trust.

    `known_entities` (name/kind/description rows from the scope's graph) closes a gap
    the convergence feed opened: the prompt tells the model to reuse known entity
    names in `about`, and the model reasonably treats a name the graph already holds
    as not needing re-declaration — which the contract then rejects as undeclared.
    Re-declaring a known entity requires no model judgement, so it is backfilled here,
    with the graph's own shape (never placeholders — the writer overwrites on match).
    Unknown undeclared names still reject: a genuinely new entity needs a description
    only the model can supply.
    """
    provenance = Provenance(
        tier=Tier.CURATED,
        source=origin,
        ingested_at=datetime.now(timezone.utc),
    )
    title = title_override or str(data.get("title") or origin)

    claims = [
        LiteratureClaim(
            description=str(item.get("description") or ""),
            kind=str(item.get("kind") or "literature/finding"),
            citation=(str(item["citation"]) if item.get("citation") else None),
            about=[str(name) for name in item.get("about") or []],
            provenance=provenance,
        )
        for item in data.get("claims") or []
        if isinstance(item, dict) and item.get("description")
    ]
    entities = [
        Entity(
            name=str(item.get("name") or ""),
            kind=str(item.get("kind") or "concept"),
            description=(str(item["description"]) if item.get("description") else None),
            provenance=provenance,
        )
        for item in data.get("entities") or []
        if isinstance(item, dict) and item.get("name")
    ]

    known = {str(row["name"]): row for row in known_entities or [] if row.get("name")}
    declared = {entity.name for entity in entities}
    referenced = {name for claim in claims for name in claim.about}
    for name in sorted(referenced - declared):
        row = known.get(name)
        if row:
            entities.append(
                Entity(
                    name=name,
                    kind=str(row.get("kind") or "concept"),
                    description=(str(row["description"]) if row.get("description") else None),
                    provenance=provenance,
                )
            )

    return KnowledgeBatch(
        scope=scope,
        feed=feed,
        source=Source(
            content_hash=content_hash,
            kind=SourceKind.ARTICLE,
            title=title,
            uri=uri,
            origin=origin,
            byte_size=byte_size,
            provenance=provenance,
        ),
        claims=claims,
        entities=entities,
    )


def ingest(
    location: str,
    *,
    scope: str,
    feed: str = "manual",
    model: str | None = None,
    harness: str = "claude",
    title: str = "",
    known_entities: list[dict] | None = None,
) -> tuple[KnowledgeBatch, extraction.ExtractionRun]:
    """The full v0 path: fetch → retain → extract → assemble. Contract checks and
    graph writes belong to the caller (the CLI), which also owns dry-run semantics.

    `known_entities` rows carry name/kind/description from the scope's graph — names
    feed the prompt, the full shape feeds the batch backfill (see build_batch)."""
    payload, origin = fetch(location)
    entry = archive_bytes(payload, suffix=".txt" if not payload.startswith(b"<") else ".html")

    text = to_text(payload)
    if len(text) < 200:
        raise IngestError(
            f"document reduced to {len(text)} chars of text — not enough to assert "
            "anything; the fetch is archived either way"
        )

    known_names = [str(row["name"]) for row in known_entities or [] if row.get("name")]
    run = extraction.run_extraction(
        build_prompt(text, origin, known_names), model=model, harness=harness
    )
    data = extraction.parse_extraction(run.text)

    batch = build_batch(
        data,
        scope=scope,
        feed=feed,
        origin=origin,
        content_hash=entry.content_hash,
        uri=entry.uri,
        byte_size=entry.byte_size,
        title_override=title,
        known_entities=known_entities,
    )
    return batch, run
