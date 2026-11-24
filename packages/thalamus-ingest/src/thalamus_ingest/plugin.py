"""The `thalamus` commands this plugin adds: `ingest`, and `backfill-chunks`.

Registered through core's `register_commands` hook (`thalamus.plugins`), which runs on
every `thalamus` invocation. So this module builds parsers and nothing else, and the
handlers in `commands.py` import the ingestion path only when one of these commands
runs.
"""

from __future__ import annotations

from thalamus.harness.agents import HARNESSES
from thalamus.plugins import hookimpl
from thalamus.substrate.writer import DEFAULT_URL
from thalamus_ingest import commands


@hookimpl
def register_commands(subparsers) -> None:
    # Curated feed v0, manual-first.
    ingest_parser = subparsers.add_parser(
        "ingest", help="Ingest one document into an expert's knowledge subgraph"
    )
    ingest_parser.add_argument("location", help="URL (allowlist-gated) or local file path")
    ingest_parser.add_argument(
        # Required, not defaulted. Every expert scope procures documents, and a
        # default sends a document nobody named to `literature` — where it is not wrong
        # enough to notice, since the literature consultant serves every scope anyway.
        # A named-but-unknown scope still fails at `load_manifest`, which lists the experts.
        "--scope", required=True,
        help="Expert scope; needs a manifest in config/experts/",
    )
    ingest_parser.add_argument("--feed", default="manual", help="Feed identity (default: manual)")
    ingest_parser.add_argument(
        "--model", default=None,
        help="Extraction model. Defaults to the harness's own (see --harness)."
    )
    ingest_parser.add_argument(
        "--harness", choices=HARNESSES, default=None,
        help="Which coding-agent CLI runs the extraction pass. Ingestion has no "
        "harness of its own — this picks whichever CLI the machine actually has. "
        "Default: the console's ingestion setting, else its distillation setting "
        "(~/.thalamus/extractor/policy.json), else claude.",
    )
    ingest_parser.add_argument("--title", default="", help="Override the extracted title")
    ingest_parser.add_argument(
        "--url", default=DEFAULT_URL,
        help="Gremlin endpoint (ws:// or wss://). The document to ingest is the "
        "positional argument, not this.",
    )
    ingest_parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the source and stop before the model call: same fetch, same "
        "User-Agent, same redirects, same allowlist gate, same text extraction. "
        "Reports the final origin, content-type, title and the opening text.",
    )
    ingest_parser.add_argument(
        "--refetch",
        action="store_true",
        help="Ask the address again instead of ingesting the bytes a recent --check "
        "verified. Without it, a check within the last day supplies the bytes, so what "
        "is written is what was checked.",
    )
    ingest_parser.add_argument(
        "--write",
        action="store_true",
        help="Write to the graph. Without it, extraction runs and is reported but not persisted.",
    )
    ingest_parser.set_defaults(plugin_run=commands.ingest)

    # Co-indexing for documents ingested before chunks existed. Model-free by
    # construction: chunking reads the retained bytes, so this costs compute and nothing
    # else, and it is safe to re-run.
    backfill_parser = subparsers.add_parser(
        "backfill-chunks",
        description="Build co-indexed Chunk vertices for already-ingested documents.",
    )
    backfill_parser.add_argument(
        "--scope", default="", help="Limit to one expert scope (default: every scope)"
    )
    backfill_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    backfill_parser.add_argument(
        "--write", action="store_true",
        help="Write to the graph. Without it, the work is reported but not persisted.",
    )
    backfill_parser.add_argument(
        "--force", action="store_true",
        help="Re-process Sources that already have chunks. Writes are idempotent "
        "(merge on vertex id), so this repairs a partial run rather than duplicating.",
    )
    backfill_parser.set_defaults(plugin_run=commands.backfill_chunks)
