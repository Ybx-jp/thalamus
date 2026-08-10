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
from dataclasses import dataclass
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
_DIGEST_BUDGET = 24_000  # chars of article text handed to the extraction model in one pass

# Chunk geometry. GraphRAG measured GPT-4 extracting almost twice as many entity
# references at 600-token chunks as at 2,400 (`scope:literature:claim:16cd76dd0d63ea12`),
# so extraction recall falls as chunks grow and _DIGEST_BUDGET (~6,000 tokens) sits
# past the right edge of that curve. 9,600 chars is ~2,400 tokens: the largest size
# with a measurement attached, chosen over the 600-token end to bound claim volume and
# cost, not because it is the recall optimum — it is the measured *worse* of the two.
# That trade is a judgement about graph volume, not a grounded optimum (docs/11 §3f).
# The overlap keeps a claim spanning a boundary from being cut in half; its size is
# proportional to GraphRAG's shipped 100/600 ratio and is otherwise ungrounded — no
# work in the literature scope measures overlap or boundary policy.
_CHUNK_SIZE = 9_600
_CHUNK_OVERLAP = 400

_TAG_RE = re.compile(r"<[^>]+>")
_DROP_BLOCKS_RE = re.compile(
    r"<(script|style|nav|header|footer|svg)\b.*?</\1>", re.DOTALL | re.IGNORECASE
)


class IngestError(RuntimeError):
    pass


@dataclass(frozen=True)
class DigestReport:
    """What of the document actually reached the extraction model.

    The archive keeps every fetched byte, but only `_DIGEST_BUDGET` chars of extracted
    text are handed to the model, and the discard is silent at the model's end: claims
    come from the opening and the tail is invisible rather than thinly covered. The
    operator's confirm step (docs/06 §5) can only weigh that if it is told, and raw
    payload bytes cannot tell it — markup-to-text ratio varies by an order of magnitude
    across sources, so bytes are not a proxy for what got read.
    """

    text_chars: int
    budget: int = _DIGEST_BUDGET
    chunks: int = 1

    @property
    def truncated(self) -> bool:
        """True only when text was discarded — chunking reads past the budget."""
        return self.chunks == 1 and self.text_chars > self.budget

    @property
    def discarded(self) -> int:
        return max(0, self.text_chars - self.budget) if self.truncated else 0

    @property
    def coverage(self) -> float:
        """Fraction of the document's text the extractor actually saw."""
        if not self.text_chars:
            return 0.0
        if self.chunks > 1:
            return 1.0
        return min(self.text_chars, self.budget) / self.text_chars


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
            "PDF parsing is deliberately unbuilt (docs/06) — feed an HTML rendering "
            "(for arXiv, arxiv.org/html/<id>) or hand-feed the relevant sections as a "
            "local text file under ~/.thalamus/hand-fed/. Do NOT settle for the "
            "abstract page: /abs/ yields abstract-level claims only, and the failure "
            "is silent (docs/06 §4). The archive will retain whatever you feed"
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
- `claims`: {claim_range} assertions THE DOCUMENT ITSELF makes — findings it reports, techniques \
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
{part_note}
Document ({origin}):

{digest}
"""


def chunk_text(
    text: str, *, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP
) -> list[str]:
    """Split document text into overlapping windows, breaking on whitespace.

    Deliberately dumb, like the rest of this module: fixed width, no structure
    detection. A section-aware splitter is a better instrument and the scope holds
    nothing measuring one against fixed width, so it stays unbuilt until something
    asks (docs/06). Boundaries back off to the nearest space so a chunk never ends
    mid-word — the model is being asked to quote verbatim citations, and a severed
    token is a citation it cannot anchor.
    """
    if size <= 0:
        raise ValueError("chunk size must be positive")
    if overlap >= size:
        raise ValueError("overlap must be smaller than the chunk size")
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + size
        if end < len(text):
            # Back off to the last space in the window, widening the search to the
            # whole chunk before giving up: a run of text longer than one chunk with
            # no whitespace in it gets cut where it must be, rather than looping.
            space = text.rfind(" ", start + size - overlap, end)
            if space <= start:
                space = text.rfind(" ", start, end)
            if space > start:
                end = space
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        # Step back by the overlap, then snap to a word boundary so the next chunk
        # opens on a whole word — an overlap that begins mid-token hands the model a
        # fragment it may quote as a citation that no longer matches the source.
        nxt = max(end - overlap, start + 1)
        boundary = text.rfind(" ", start, nxt)
        start = boundary + 1 if boundary >= start else nxt
    return [chunk for chunk in chunks if chunk]


def build_prompt(
    text: str,
    origin: str,
    known_entities: list[str] | None = None,
    *,
    part: tuple[int, int] | None = None,
) -> str:
    # The convergence feed, pointed at entities: articles relate to each other through
    # shared Entity vertices, and the model can only reuse names it can see (the same
    # mechanism that fixed claim convergence in d60372e).
    rendered = "\n".join(f"- {name}" for name in known_entities) if known_entities else "(none)"
    if part is None:
        part_note = ""
        claim_range = "3-12"
    else:
        index, total = part
        # Per-chunk yield is trimmed because the counts multiply: the same 3-12 asked
        # of every chunk turns one paper into hundreds of claims, which is the
        # duplication-and-false-precision failure the ontology-debt literature names
        # (`scope:literature:claim:2090b18576ac5927`).
        part_note = (
            f"\nThis is PART {index} OF {total} of one longer document — a window of "
            "its text, not the whole thing. Extract only what THIS part asserts; the "
            "other parts are handled by their own passes, so do not speculate about "
            "material you cannot see or restate a claim this part merely alludes to. "
            "For `title`, give the parent document's own title if this part reveals "
            "it, otherwise an empty string — never invent one from a section heading.\n"
        )
        claim_range = "2-6"
    return _ARTICLE_PROMPT.format(
        origin=origin,
        known_entities=rendered,
        digest=text[:_DIGEST_BUDGET],
        part_note=part_note,
        claim_range=claim_range,
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


def _combine_runs(runs: list[extraction.ExtractionRun]) -> extraction.ExtractionRun:
    """One run record for a multi-pass ingest: costs and durations add.

    A None cost means "the CLI did not report it", never "free", so it cannot be
    summed as zero — if nothing reported, the total stays None rather than
    understating what the pass actually cost.
    """
    priced = [run.cost_usd for run in runs if run.cost_usd is not None]
    return extraction.ExtractionRun(
        text="\n\n".join(run.text for run in runs),
        cost_usd=sum(priced) if priced else None,
        duration_ms=sum(run.duration_ms for run in runs),
    )


def merge_extractions(parts: list[dict]) -> dict:
    """Fold per-chunk extractions into one document-level extraction.

    **Retain, never merge.** Claims are concatenated verbatim — no near-duplicate
    collapsing, because the one measurement in scope on merging at write time has it
    regressing below plain RAG (0.62 / 0.13 on MemStrata's aggressive-compression
    ablation, `scope:literature:claim:1404d8270a1ab463`), whose conclusion is "retain,
    then supersede". Two chunks reporting the same finding is a fact about the
    document worth keeping, and claim identity downstream is latest-wins anyway.

    Entities are the one place a document-level view is required, and the dedup is by
    **exact name only** — never by similarity. An identical name is the same vertex by
    construction (the writer upserts on it), so declaring it twice in one batch is a
    malformed batch, not a judgement call. First declaration wins, so a name keeps the
    description from the chunk that introduced it.
    """
    claims: list = []
    entities: dict[str, dict] = {}
    title = ""
    for data in parts:
        if not title:
            title = str(data.get("title") or "").strip()
        claims.extend(data.get("claims") or [])
        for item in data.get("entities") or []:
            if isinstance(item, dict) and item.get("name"):
                entities.setdefault(str(item["name"]), item)
    return {"title": title, "claims": claims, "entities": list(entities.values())}


def ingest(
    location: str,
    *,
    scope: str,
    feed: str = "manual",
    model: str | None = None,
    harness: str = "claude",
    title: str = "",
    known_entities: list[dict] | None = None,
) -> tuple[KnowledgeBatch, extraction.ExtractionRun, DigestReport]:
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
    chunks = chunk_text(text)

    if len(chunks) == 1:
        run = extraction.run_extraction(
            build_prompt(text, origin, known_names), model=model, harness=harness
        )
        data = extraction.parse_extraction(run.text)
    else:
        # The convergence feed, run forward through the document: each chunk's prompt
        # carries the entity names the scope already held *plus* those the earlier
        # chunks minted, so a paper's own vocabulary converges on first use instead of
        # fragmenting into near-duplicates per chunk. Same mechanism as the
        # cross-article feed (d60372e), pointed inward at one document.
        vocabulary = list(known_names)
        seen = set(vocabulary)
        runs, parts = [], []
        for index, chunk in enumerate(chunks, start=1):
            runs.append(
                extraction.run_extraction(
                    build_prompt(chunk, origin, vocabulary, part=(index, len(chunks))),
                    model=model,
                    harness=harness,
                )
            )
            parsed = extraction.parse_extraction(runs[-1].text)
            parts.append(parsed)
            for item in parsed.get("entities") or []:
                name = str(item.get("name") or "") if isinstance(item, dict) else ""
                if name and name not in seen:
                    seen.add(name)
                    vocabulary.append(name)
        run = _combine_runs(runs)
        data = merge_extractions(parts)

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
    return batch, run, DigestReport(text_chars=len(text), chunks=len(chunks))
