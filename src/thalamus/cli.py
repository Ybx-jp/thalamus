"""CLI for Thalamus operations."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import uvicorn
import yaml

from thalamus.substrate.schema import CloseDisposition, SessionGraph, ThreadClose
from thalamus.archive import archive_dir
from thalamus.console.server import DEFAULT_PORT as CONSOLE_PORT
from thalamus.contract.conformance import (
    ContractViolation,
    check_session,
    write_session_checked,
)
from thalamus.contract.ontology import MAIN_SCOPE
from thalamus.eval import snapshots
from thalamus.eval.profile import DEFAULT_REPEAT as PROFILE_REPEAT
from thalamus.eval.withholding import DRAWS as WITHHOLD_DRAWS
from thalamus.harness import (
    agents,
    codex_transcripts,
    cursor_transcripts,
    extractor_policy,
    extraction,
    transcripts,
)
from thalamus.harness import closes as closes_mod
from thalamus.harness import quick as quick_mod
from thalamus.harness.bootstrap import bootstrap_project
from thalamus.harness.ceremonies import (
    CEREMONY_KINDS,
    COMPARATOR_ARMS,
    RESOLUTION_OUTCOMES,
)
from thalamus.harness import pin
from thalamus.harness.pin import ROSTER_SESSION, resolve_forked_from, resolve_room
from thalamus.substrate.snapshot import DEFAULT_SNAPSHOT_PATH, snapshot, snapshot_quietly
from thalamus.substrate.writer import (
    DEFAULT_URL,
    GraphUnavailable,
    close_connection,
    connect,
)

ROOM_FLAG_HELP = (
    "Launch into this room — a private config dir (~/.thalamus/rooms/<room>/) that "
    "partitions peer discovery, so members see only each other. Created on first "
    "use. Default: $THALAMUS_ROOM, else no room."
)

ARCH_REPO_HELP = (
    "Repo to measure. Defaults to the checkout this CLI is installed from, not the "
    "current directory — `arch/model.yaml` belongs to a repository."
)


def main():
    """CLI entry point.

    A graph that is not running is the ordinary first-run state of this machine, and
    every command that reads memory hits it. It is reported as the one sentence that
    fixes it rather than as a traceback ending in an `aiohttp` transport error.
    """
    try:
        _main()
    except GraphUnavailable as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def _main():
    parser = argparse.ArgumentParser(
        description="Thalamus — federated graph memory for coding agents",
        epilog="One-shot graph repairs (backfill-chunks, audit-artifacts, "
               "repair-projects, derive-artifact-paths, retire-scans, "
               "repair-claim-addresses) are not listed here: they migrate an "
               "existing graph and a new one can never need them. Each answers "
               "--help, and docs/cli.md documents them under Maintenance.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Log Gremlin bytecode and server stack traces",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    # Write command
    write_parser = subparsers.add_parser("write", help="Write a session graph from YAML/JSON file")
    write_parser.add_argument("file", type=Path, help="Path to session YAML/JSON file")
    write_parser.add_argument("--url", default="ws://localhost:8182/gremlin", help="Gremlin endpoint")

    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate a session YAML/JSON file")
    validate_parser.add_argument("file", type=Path, help="Path to session YAML/JSON file")

    # Schema command
    subparsers.add_parser("schema", help="Print the session graph JSON schema")

    # Bootstrap command
    bootstrap_parser = subparsers.add_parser(
        "bootstrap", help="Build memory from retained session transcripts (stage 1, no model)"
    )
    bootstrap_parser.add_argument(
        "projects",
        nargs="*",
        help="Claude Code project dir names (e.g. -home-you-code-thalamus). "
        "Omit to list what is available. Ignored with --harness cursor and --harness "
        "codex, which are session-oriented and sweep every discovered session.",
    )
    bootstrap_parser.add_argument(
        "--harness", choices=agents.HARNESSES, default="claude",
        help="Which harness wrote the transcripts (default: claude). `cursor` sweeps "
        "both discovery surfaces — the sessionEnd hook log and ~/.cursor/projects — "
        "so sessions predating the hooks are included. `codex` sweeps "
        "$CODEX_HOME/sessions, which the CLI writes for every session whether or not "
        "the hooks were armed.",
    )
    bootstrap_parser.add_argument(
        "--assign-scope", default="",
        help="Scope for Cursor or codex sessions no hook ever saw, which therefore "
        "have no resolved scope. Without it they are listed and skipped rather than "
        "defaulted into `main`; scope is part of the vertex ID and cannot be walked "
        "back.",
    )
    bootstrap_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    bootstrap_parser.add_argument(
        "--projects-dir",
        type=Path,
        default=None,
        help="Transcript root to sweep (default: ~/.claude/projects). A room member "
        "runs under its own CLAUDE_CONFIG_DIR and writes transcripts to that dir's "
        "`projects/` instead, where the default sweep never looks.",
    )
    bootstrap_parser.add_argument(
        "--scope", default=MAIN_SCOPE, help="Scope to pin these sessions to (default: main)"
    )
    bootstrap_parser.add_argument(
        "--write",
        action="store_true",
        help="Actually write to the graph. Without it, this is a dry run: transcripts are "
        "archived and extraction is reported, but nothing is persisted.",
    )

    # Extract command — stage 2 of the bootstrap
    extract_parser = subparsers.add_parser(
        "extract",
        help="Extract Claims and Threads from archived transcripts via a model (bootstrap stage 2)",
    )
    extract_parser.add_argument(
        "projects",
        nargs="*",
        help="Claude Code project dir names. Omit to list what is available. "
        "Ignored with --harness cursor, which discovers sessions from the Cursor "
        "sessionEnd log, and with --harness codex, which sweeps $CODEX_HOME/sessions.",
    )
    extract_parser.add_argument(
        "--harness", choices=agents.HARNESSES, default="claude",
        help="Which harness wrote the transcripts (default: claude). `cursor` sweeps "
        "~/.thalamus/logs/cursor-session-end.jsonl, including sessions logged before "
        "the adapter existed. `codex` sweeps $CODEX_HOME/sessions by session id, since "
        "a codex rollout is filed under the day it ran rather than under its project.",
    )
    extract_parser.add_argument(
        "--extract-with", choices=agents.HARNESSES, default=None,
        help="Which coding-agent CLI runs the extraction pass. A separate question "
        "from --harness, which says who *wrote* the transcript: a digest is plain "
        "text by the time a model sees it, so any CLI can read any harness's session. "
        "Default: the console's distillation setting "
        "(~/.thalamus/extractor/policy.json), else the session's own harness.",
    )
    extract_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    extract_parser.add_argument(
        "--projects-dir",
        type=Path,
        default=None,
        help="Transcript root holding the project dir (default: ~/.claude/projects). "
        "A room member runs under its own CLAUDE_CONFIG_DIR and writes transcripts to "
        "that dir's `projects/`; session-end.sh derives this from the transcript's own "
        "path, so a room session distills where it actually landed rather than nowhere.",
    )
    extract_parser.add_argument(
        "--scope", default=MAIN_SCOPE, help="Scope the sessions are pinned to (default: main)"
    )
    extract_parser.add_argument(
        "--assign-scope", default="",
        help="Scope for Cursor or codex sessions found on disk that no hook ever saw, "
        "and which therefore have no resolved scope of their own. Without this they are "
        "listed and skipped rather than defaulted into `main` — separate from `--scope` "
        "so an unmade routing decision can never be made by a flag's default value.",
    )
    extract_parser.add_argument(
        "--transcript",
        default="",
        help="Distill exactly this transcript file, skipping discovery. The codex "
        "SessionEnd hook is handed the rollout's path and passes it straight through: "
        "a codex rollout is filed under the day it ran, so re-deriving the file by "
        "scanning the tree for a matching id is a second chance to pick the wrong one.",
    )
    extract_parser.add_argument(
        "--room",
        default=None,
        help="Collaboration these sessions witnessed, stamped on the Session. Default: "
        "each session's own pin-ledger row, else $THALAMUS_ROOM, else none — the ledger "
        "outranks this shell because it records the launch rather than the re-extraction. "
        "Sessions sharing a room distilled one conversation, so their claims are "
        "correlated rather than independent.",
    )
    extract_parser.add_argument(
        "--forked-from",
        default=None,
        help="Session these were forked from. Default: each session's own pin-ledger "
        "row, else $THALAMUS_FORKED_FROM, else none. A fork inherited its parent's "
        "context, so it derives from that session rather than corroborating it.",
    )
    extract_parser.add_argument(
        "--model",
        default=None,
        help="Extraction model. Defaults per harness: " + ", ".join(
            f"`{agents.default_model(h)}` via {' '.join(agents.cli_for(h).argv('…')[:2])}"
            for h in agents.HARNESSES
        ) + ". The archive is immutable, so a better model can always re-extract later.",
    )
    extract_parser.add_argument(
        "--limit", type=int, default=0, help="Stop after N sessions (0 = no limit)"
    )
    extract_parser.add_argument(
        "--session", action="append", default=[], help="Only these session IDs (prefix ok)"
    )
    extract_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-extract sessions that already have claims in the graph",
    )
    extract_parser.add_argument(
        "--reuse-raw",
        action="store_true",
        help="Replay each session's retained model response (~/.thalamus/extractions/) "
        "instead of calling the model. Recovers a run that was paid for and then lost "
        "to a parse or validation refusal. Sessions with no retained response are "
        "skipped, never paid for.",
    )
    extract_parser.add_argument(
        "--write",
        action="store_true",
        help="Write to the graph. Without it, extraction runs and is reported but not persisted.",
    )

    # Ingest command — curated feed v0, manual-first
    ingest_parser = subparsers.add_parser(
        "ingest", help="Ingest one document into an expert's knowledge subgraph"
    )
    ingest_parser.add_argument("location", help="URL (allowlist-gated) or local file path")
    ingest_parser.add_argument(
        # Required, not defaulted. Every scope on the roster procures documents, and a
        # default sends a document nobody named to `literature` — where it is not wrong
        # enough to notice, since the literature consultant serves every scope anyway.
        # A named-but-unknown scope still fails at `load_manifest`, which lists the roster.
        "--scope", required=True,
        help="Expert scope; needs a manifest in config/experts/",
    )
    ingest_parser.add_argument("--feed", default="manual", help="Feed identity (default: manual)")
    ingest_parser.add_argument(
        "--model", default=None,
        help="Extraction model. Defaults to the harness's own (see --harness)."
    )
    ingest_parser.add_argument(
        "--harness", choices=agents.HARNESSES, default=None,
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

    # Contract command — the federation boundary, audited
    contract_parser = subparsers.add_parser(
        "contract", help="Federation-contract operations against the live graph"
    )
    contract_sub = contract_parser.add_subparsers(dest="contract_command")
    contract_check_parser = contract_sub.add_parser(
        "check",
        help="Audit the live graph: provenance envelopes, scope legality, orphans, "
        "evidence-floor integrity",
    )
    contract_check_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    contract_check_parser.add_argument(
        "--capabilities", action="store_true",
        help="Re-ask the harness CLIs whether the capability declarations still hold. "
        "Reads no graph and makes no model call; needs the CLIs on PATH.",
    )
    contract_check_parser.add_argument(
        "--roster", action="store_true",
        help="Print the boundaries in force for every expert scope, resolved. Reads "
        "no graph: the manifests and the roster default are the whole answer.",
    )

    # The architect's instrument. Reads code, writes a git-tracked model and
    # findings — never metrics — into the `architect` scope.
    arch_parser = subparsers.add_parser(
        "arch", help="The architect's structural instrument over a repo's imports"
    )
    arch_sub = arch_parser.add_subparsers(dest="arch_command")

    arch_scan_parser = arch_sub.add_parser(
        "scan",
        help="Measure the import graph and regenerate arch/model.yaml "
        "(dry-run unless --write)",
    )
    arch_scan_parser.add_argument("--repo", default=None, help=ARCH_REPO_HELP)
    arch_scan_parser.add_argument(
        "--import-depth", choices=["all", "module-level"], default="",
        help="Override the model file's declared policy. Changes the policy digest, so "
        "the scan lands in a different lineage — which is the point.",
    )
    arch_scan_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    arch_scan_parser.add_argument(
        "--write", action="store_true",
        help="Write the model file. Without it, the scan runs and is reported but "
        "nothing is persisted.",
    )
    arch_scan_parser.add_argument(
        "--check", action="store_true",
        help="Exit 1 if the committed model file does not match a fresh scan. The "
        "staleness gate: measures, compares, writes nothing.",
    )

    arch_show_parser = arch_sub.add_parser(
        "show", help="Print the current model: declared policy, layers, rules, last scan"
    )
    arch_show_parser.add_argument("--repo", default=None, help=ARCH_REPO_HELP)

    arch_diff_parser = arch_sub.add_parser(
        "diff",
        help="Compare the working tree's structure against another commit — recompute "
        "both sides rather than trusting a stored number",
    )
    arch_diff_parser.add_argument("against", help="Commit-ish to compare against")
    arch_diff_parser.add_argument("--repo", default=None, help=ARCH_REPO_HELP)

    arch_rules_parser = arch_sub.add_parser(
        "rules", help="Check the measured edge list against the declared design rules"
    )
    arch_rules_parser.add_argument("--repo", default=None, help=ARCH_REPO_HELP)
    arch_rules_parser.add_argument(
        "--gate", action="store_true",
        help="Exit nonzero on a finding the model does not accept. 1 = a violation or "
        "unplaced module not declared in `accepted`; 2 = an `accepted` entry that no "
        "longer happens and should be deleted.",
    )

    arch_dead_parser = arch_sub.add_parser(
        "dead",
        help="Definitions under the source roots that nothing outside the test roots "
        "refers to, and modules nothing imports",
    )
    arch_dead_parser.add_argument("--repo", default=None, help=ARCH_REPO_HELP)
    arch_dead_parser.add_argument(
        "--gate", action="store_true",
        help="Exit nonzero on a finding the model does not exempt. 1 = a reported "
        "definition or orphan module; 2 = an exemption that no longer matches anything.",
    )
    arch_dead_parser.add_argument(
        "--limits", action="store_true",
        help="Print what the census could not see — runtime name lookup, names reached "
        "through a string, star re-exports, unparsed files.",
    )

    arch_refs_parser = arch_sub.add_parser(
        "refs",
        help="Names a comment points at that the tree no longer holds (report only)",
    )
    arch_refs_parser.add_argument("--repo", default=None, help=ARCH_REPO_HELP)
    arch_refs_parser.add_argument(
        "--limits", action="store_true",
        help="Print what the recognizer did not consume — candidate tokens no form "
        "matched, files it could not read, and the references a sentence asserts the "
        "absence of.",
    )

    arch_growth_parser = arch_sub.add_parser(
        "growth",
        help="What this system accumulates, and what nothing refers to (read-only)",
    )
    arch_growth_parser.add_argument("--repo", default=None, help=ARCH_REPO_HELP)
    arch_growth_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")

    # Chunk backfill — co-indexing for documents ingested before chunks existed.
    # Model-free by construction: chunking reads the retained bytes, so this costs
    # compute and nothing else, and it is safe to re-run.
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

    audit_artifacts_parser = subparsers.add_parser(
        "audit-artifacts",
        description="Measure how fragmented Artifact identity is (read-only).",
    )
    audit_artifacts_parser.add_argument(
        "--url", default=DEFAULT_URL, help="Gremlin endpoint"
    )

    repair_projects_parser = subparsers.add_parser(
        "repair-projects",
        description="Re-anchor project values that named a directory instead of a "
        "repo. Dry-run unless --write.",
    )
    repair_projects_parser.add_argument(
        "--url", default=DEFAULT_URL, help="Gremlin endpoint"
    )
    repair_projects_parser.add_argument(
        "--write", action="store_true",
        help="Apply the plan. Without this, nothing is written.",
    )

    derive_paths_parser = subparsers.add_parser(
        "derive-artifact-paths",
        description="Project Artifact identifiers onto (repo, path) without "
        "re-keying them. Dry-run unless --write.",
    )
    derive_paths_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    derive_paths_parser.add_argument(
        "--write", action="store_true",
        help="Apply the plan. Without this, nothing is written.",
    )

    retire_scans_parser = subparsers.add_parser(
        "retire-scans",
        description="Remove the graph records of architecture scans, which are no "
        "longer written. Dry-run unless --write.",
    )
    retire_scans_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    retire_scans_parser.add_argument(
        "--write", action="store_true",
        help="Apply the plan. Without this, nothing is removed.",
    )

    repair_addresses_parser = subparsers.add_parser(
        "repair-claim-addresses",
        description="Move Claims whose id disagrees with their own content back to "
        "the address that content produces. Dry-run unless --write.",
    )
    repair_addresses_parser.add_argument(
        "--url", default=DEFAULT_URL, help="Gremlin endpoint"
    )
    repair_addresses_parser.add_argument(
        "--write", action="store_true",
        help="Apply the plan. Without this, nothing is written.",
    )

    # Snapshot command — durability on demand
    snapshot_parser = subparsers.add_parser(
        "snapshot",
        help="Flush the in-memory graph to its persistent file on the server",
    )
    snapshot_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    snapshot_parser.add_argument(
        "--path",
        default=DEFAULT_SNAPSHOT_PATH,
        help="Server-side path to write. Defaults to the configured graphLocation; "
        "point it elsewhere to take a side copy without touching the live file.",
    )
    snapshot_parser.add_argument(
        "--name",
        help="Pin the graph under this name instead: writes a named .kryo and records "
        "counts, sha256 and git ref in the committed registry. A published number cites "
        "the snapshot it was computed on; snapshots are immutable.",
    )
    snapshot_parser.add_argument(
        "--note", default="", help="Why this state was worth pinning (goes in the registry)"
    )
    snapshot_parser.add_argument(
        "--list", action="store_true", help="List pinned snapshots and verify their hashes"
    )
    snapshot_parser.add_argument(
        "--serve",
        help="Serve a pinned snapshot read-only on --port so an analysis can address the "
        "past without the live graph moving underneath it",
    )
    snapshot_parser.add_argument(
        "--port", type=int, default=8183, help="Port for --serve (default: 8183)"
    )
    snapshot_parser.add_argument(
        "--restore",
        help="Make a pinned snapshot the live graph again. Verifies its hash first, "
        "pins the current graph as a safety net, then stops the server, swaps the file "
        "and restarts. Destructive: the live graph is replaced.",
    )
    snapshot_parser.add_argument(
        "--no-safety-pin",
        action="store_true",
        help="Skip pinning the current graph before --restore. Only when the state "
        "being discarded is already known-bad.",
    )

    # Eval command — layer 1 of the eval loop
    eval_parser = subparsers.add_parser(
        "eval", help="Eval loop v0: land retrieval traces in the graph and report used-vs-ignored"
    )
    eval_sub = eval_parser.add_subparsers(dest="eval_command")

    eval_sync_parser = eval_sub.add_parser(
        "sync",
        help="Land the PostToolUse trace tap as Trace nodes, attributing used-vs-ignored "
        "against the retained transcripts",
    )
    eval_sync_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    eval_sync_parser.add_argument(
        "--traces", type=Path, default=None, help="Trace tap directory (default: ~/.thalamus/traces)"
    )
    eval_sync_parser.add_argument(
        "--write",
        action="store_true",
        help="Write to the graph. Without it, sync runs and is reported but not persisted.",
    )

    eval_report_parser = eval_sub.add_parser(
        "report", help="Per-scope retrieval-utility numbers from landed traces"
    )
    eval_report_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    eval_report_parser.add_argument(
        "--scope", default=MAIN_SCOPE, help="Scope to report on (default: main)"
    )
    eval_report_parser.add_argument(
        "--top", type=int, default=5, help="How many most-ignored nodes to list"
    )
    eval_report_parser.add_argument(
        "--since",
        default=None,
        help="Only count traces at or after this ISO date/datetime (UTC), e.g. 2026-07-18",
    )
    eval_report_parser.add_argument(
        "--until",
        default=None,
        help="Only count traces at or before this ISO date/datetime (UTC); a bare date "
        "covers the whole day",
    )

    eval_cost_parser = eval_sub.add_parser(
        "cost",
        help="Token-cost attribution from local records: interactive vs extract vs "
        "expert sessions, plus per-retrieval context injection",
    )
    eval_cost_parser.add_argument(
        "--project-dir", type=Path, default=None, help="Project working directory (default: cwd)"
    )
    eval_cost_parser.add_argument(
        "--since", default=None, help="Start date YYYY-MM-DD (default: 14 days ago)"
    )
    eval_cost_parser.add_argument(
        "--traces", type=Path, default=None, help="Trace tap directory (default: ~/.thalamus/traces)"
    )
    eval_cost_parser.add_argument(
        "--by-occasion", action="store_true", dest="by_occasion",
        help="Attribute room members' burn to the ceremony occasion it happened "
             "inside, with each room's out-of-occasion burn beside it",
    )

    eval_pins_parser = eval_sub.add_parser(
        "pins",
        help="Pin-quality routing signal: per-expert pinned vs consulted utility "
        "from priced traces (the pin or the expert — the data says which)",
    )
    eval_pins_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    eval_pins_parser.add_argument(
        "--pins-file", type=Path, default=None, help="Pin ledger (default: ~/.thalamus/pins/pins.jsonl)"
    )

    eval_gremlin_parser = eval_sub.add_parser(
        "gremlin",
        help="Gremlin fluency metrics: guard rescue rate, rejection classes, recipe reuse",
    )
    eval_gremlin_parser.add_argument(
        "--traces", type=Path, default=None, help="Trace tap dir (default: ~/.thalamus/traces)"
    )
    eval_gremlin_parser.add_argument(
        "--guards", type=Path, default=None, help="Guard event dir (default: ~/.thalamus/guards)"
    )

    eval_recipes_parser = eval_sub.add_parser(
        "recipes",
        help="Smoke-run every stored gremlin recipe read-only (rolling freshness signal)",
    )
    eval_recipes_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    eval_recipes_parser.add_argument(
        "--staged", action="store_true",
        help="Show queries the PostToolUse hook staged for RECIPES.md instead of "
             "smoke-running the store",
    )

    eval_profile_parser = eval_sub.add_parser(
        "profile",
        help="Gremlin query cost: what each traversal shape costs in wall time, and "
        "where a single query spends it step by step",
    )
    eval_profile_parser.add_argument(
        "--profiles", type=Path, default=None,
        help="Span ledger directory (default: ~/.thalamus/profiles)",
    )
    eval_profile_parser.add_argument(
        "--top", type=int, default=10, help="How many costliest shapes to list"
    )
    eval_profile_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    eval_profile_parser.add_argument(
        "--query",
        default="",
        help="Step-profile one read-only gremlin-lang traversal instead of reading the "
        "ledger. Server-side per-step metrics via TinkerPop's profile(); profiling "
        "impedes the traversal, so read the steps against each other.",
    )
    eval_profile_parser.add_argument(
        "--corpus",
        action="store_true",
        help="Step-profile every gremlin-lang recipe the skills store, slowest first",
    )
    eval_profile_parser.add_argument(
        "--repeat", type=int, default=None,
        help=f"Timed runs per query for --query/--corpus (default: {PROFILE_REPEAT})",
    )

    eval_withholding_parser = eval_sub.add_parser(
        "withholding",
        help="The randomized-withholding ledger as an outcome: do withheld nodes come back?",
    )
    eval_withholding_parser.add_argument(
        "--url", default=DEFAULT_URL, help="Gremlin endpoint"
    )
    eval_withholding_parser.add_argument(
        "--scope", default="main",
        help="Scope to analyse (default: main, 80%% of the corpus). "
             "Pass '' for the pooled exploratory read across every scope.",
    )
    eval_withholding_parser.add_argument(
        "--draws", type=int, default=WITHHOLD_DRAWS,
        help=f"Permutation draws (default: {WITHHOLD_DRAWS}); the attainable "
             "two-sided p floor is 1/(draws+1)",
    )

    eval_conditioning_parser = eval_sub.add_parser(
        "conditioning",
        help="Per-firing behavioral join: did each injected reminder change behavior?",
    )
    eval_conditioning_parser.add_argument(
        "--conditioning", type=Path, default=None,
        help="Conditioning event dir (default: ~/.thalamus/conditioning)",
    )
    eval_conditioning_parser.add_argument(
        "--traces", type=Path, default=None, help="Trace tap dir (default: ~/.thalamus/traces)"
    )

    # Pin / roster commands — "the process is the pin"
    init_parser = subparsers.add_parser(
        "init", help="Install the harness at user scope so it arms in any directory"
    )
    init_parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would change and run verification, without writing"
    )
    init_parser.add_argument(
        "--check", action="store_true",
        help="Only verify an existing install; write nothing"
    )
    init_parser.add_argument(
        # Only with --check, and refused otherwise rather than ignored: the
        # report is the check's rows, so a `--json` beside an install would have
        # to either withhold the actions it took or invent a shape for them.
        # The reader is a program deciding something — thalamus-eval runs this
        # inside a confinement cell to establish that an arm's treatment was
        # delivered before the cell spends anything.
        "--json", action="store_true",
        help="With --check, print the verification as JSON instead of prose"
    )
    init_parser.add_argument(
        # Derived from the registry rather than listed, so a harness cannot arrive in
        # `AGENT_CLIS` and be silently uninstallable — the property `install.HARNESSES`
        # already states and this literal tuple quietly denied.
        "--harness", choices=(*agents.HARNESSES, "all"), default="all",
        help="Which editor to wire (default: all)"
    )
    init_parser.add_argument(
        "--uninstall", action="store_true",
        help="Remove the hooks, MCP registration, skill links and derived agents "
             "this wrote. Leaves the graph and the transcript archive alone"
    )
    init_parser.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip the confirmation — for non-interactive installs"
    )

    # The counterpart to `init --check`, and deliberately not part of it: that
    # command verifies wiring, all of which can be correct while nothing is written.
    status_parser = subparsers.add_parser(
        "status", help="Is memory being written? Sessions in the graph and the last "
                       "distillation run"
    )
    status_parser.add_argument(
        "--url", default=None, help="Gremlin endpoint (default: $THALAMUS_GRAPH_URL)"
    )

    rescope_parser = subparsers.add_parser(
        "rescope", help="Redirect a session's distillation scope (before it distills)"
    )
    rescope_parser.add_argument("scope", help="Scope to distill into (`main` or a manifest)")
    rescope_parser.add_argument(
        "session", nargs="?", default=None,
        help="Session ID (prefix ok). Default: the current session, read from "
             "$CLAUDE_CODE_SESSION_ID — never guess it"
    )
    rescope_parser.add_argument("--reason", default="", help="Why, for the ledger record")
    rescope_parser.add_argument(
        "--dry-run", action="store_true", help="Report the correction without appending it"
    )
    rescope_parser.add_argument(
        "--other-session", action="store_true",
        help="Acknowledge that the session argument names a DIFFERENT session than the "
             "one running. Required whenever they differ; the mismatch is detected from "
             "$CLAUDE_CODE_SESSION_ID, not taken on trust"
    )
    rescope_parser.add_argument(
        "--allow-distilled", action="store_true",
        help="Override the already-distilled refusal. Forks the session's identity across "
             "scopes (vertex IDs include scope); the original vertex is left stale."
    )

    pin_parser = subparsers.add_parser(
        "pin", help="Launch a session pinned to an expert scope"
    )
    pin_parser.add_argument("scope", help="Expert scope (a config/experts manifest, or `main`)")
    pin_parser.add_argument("--room", default=None, help=ROOM_FLAG_HELP)
    pin_parser.add_argument(
        "--harness", choices=agents.HARNESSES, default="claude", help="Which CLI to pin (default: claude). The charter rides `--agent` on claude and `--profile` on codex; `cursor` has no carrier for one, so its pin routes and is bounded without it — see contract/pinning.py for what `pinned` covers on each. codex and cursor both take the scope as an argv `env` prefix as well, which is what survives `respawn-window` (on codex `--profile` restores the charter but tells the hooks nothing). Both also default to their own resting permission posture rather than to `auto`, so a pinned session can stop at a prompt: the console's posture panel is where that is changed, and harness/launcher.py records what each rung gives up."
    )

    spawn_parser = subparsers.add_parser(
        "spawn", help="Open one on-demand pinned tmux window (a chosen scope + directory)"
    )
    spawn_parser.add_argument("scope", help="Expert scope (a config/experts manifest, or `main`)")
    spawn_parser.add_argument(
        "--dir", type=Path, default=None,
        help="Working directory for the session (default: the thalamus repo)"
    )
    spawn_parser.add_argument(
        "--session", default="thalamus", help="tmux session to open the window in"
    )
    spawn_parser.add_argument("--room", default=None, help=ROOM_FLAG_HELP)
    spawn_parser.add_argument(
        "--harness", choices=agents.HARNESSES, default="claude", help="Which CLI to pin (default: claude). The charter rides `--agent` on claude and `--profile` on codex; `cursor` has no carrier for one, so its pin routes and is bounded without it — see contract/pinning.py for what `pinned` covers on each. codex and cursor both take the scope as an argv `env` prefix as well, which is what survives `respawn-window` (on codex `--profile` restores the charter but tells the hooks nothing). Both also default to their own resting permission posture rather than to `auto`, so a pinned session can stop at a prompt: the console's posture panel is where that is changed, and harness/launcher.py records what each rung gives up."
    )

    roster_parser = subparsers.add_parser(
        "roster", help="Bring up the tmux roster (the `main` anchor; --all for every expert)"
    )
    roster_parser.add_argument(
        "--all", action="store_true",
        help="Open one window per expert manifest (legacy full roster)"
    )
    roster_parser.add_argument("--room", default=None, help=ROOM_FLAG_HELP)

    quick_parser = subparsers.add_parser(
        "quick",
        help="The quick protocol: consult a live expert by forking its own session",
    )
    quick_sub = quick_parser.add_subparsers(dest="quick_command")
    quick_ask = quick_sub.add_parser(
        "ask", help="Fork the expert's live session and block on its cited answer"
    )
    quick_ask.add_argument("expert", help="Expert scope to consult (a config/experts manifest)")
    quick_ask.add_argument("question", help="The question, asked of the forked expert")
    quick_ask.add_argument(
        "--from-scope", default=None,
        help="The calling session's own scope (default: this process's pin)"
    )
    quick_ask.add_argument(
        "--allow", default=quick_mod.DEFAULT_ALLOWED_TOOLS,
        help="Tools the fork may use without prompting (default: %(default)s — the "
             "tier answers from memory rather than inspecting the box)"
    )
    quick_ask.add_argument(
        "--timeout", type=int, default=quick_mod.DEFAULT_TIMEOUT,
        help="Seconds to wait for the fork's answer (default: %(default)s)"
    )
    quick_ask.add_argument(
        "--wait", type=int, default=0, metavar="SECONDS",
        help="Hold up to this long for a mid-turn parent to land its turn before "
             "forking (default: 0 — fork now). A mid-turn fork costs ~13x and misses "
             "the message body its parent is still writing, but waiting spends the "
             "caller's latency, which is what this tier exists to save."
    )
    quick_ask.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    quick_targets = quick_sub.add_parser(
        "targets", help="Live sessions this caller can fork, and what each would cost"
    )
    quick_targets.add_argument(
        "--all", action="store_true", help="Include unpinned (`main`) sessions"
    )
    quick_delta = quick_sub.add_parser(
        "delta",
        help="Stage a fork's own records for distillation; prints the projects root "
             "to extract from (session-end.sh calls this)",
    )
    quick_delta.add_argument(
        "--transcript", type=Path, required=True, help="The fork's transcript"
    )
    quick_delta.add_argument(
        "--parent", required=True, help="Session id the fork was resumed from"
    )

    room_parser = subparsers.add_parser(
        "room", help="Rooms: the collaborations sessions are launched into"
    )
    room_sub = room_parser.add_subparsers(dest="room_command")
    room_sub.add_parser("list", help="Every room that has a config dir")
    room_show = room_sub.add_parser("show", help="What one room's config dir holds")
    room_show.add_argument("room", help="Room name")
    room_create = room_sub.add_parser(
        "create", help="Provision a room's config dir without launching anything"
    )
    room_create.add_argument("room", help="Room name (lowercase letters, digits, hyphens)")

    # Thread closing. `propose` writes a ledger row and nothing to the graph; `approve`
    # writes the row and then the edge. The split is the whole mechanism: an agent may
    # propose, only the operator approves, and a pending proposal never becomes a vertex
    # that the next session's brief has to read past.
    thread_parser = subparsers.add_parser(
        "thread", help="Close threads: propose, approve, and audit the close ledger"
    )
    thread_sub = thread_parser.add_subparsers(dest="thread_command")

    thread_propose = thread_sub.add_parser(
        "propose", help="Propose a close (ledger only — writes nothing to the graph)"
    )
    thread_propose.add_argument("thread_id", help="Thread id, unqualified")
    thread_propose.add_argument("--scope", default=MAIN_SCOPE, help="Scope it lives in")
    thread_propose.add_argument(
        "--basis", required=True,
        help="Vertex ID the close rests on. Must resolve in the thread's own scope, or "
             "be global. For a thread that was never work, its own spawning session",
    )
    thread_propose.add_argument(
        "--disposition", required=True, choices=[d.value for d in CloseDisposition],
        help="Why it closed — the stratification variable that keeps 'never was work' "
             "out of the resolution-latency distribution",
    )
    thread_propose.add_argument("--rationale", default="", help="Why, in one line")
    thread_propose.add_argument(
        "--by", default="", dest="proposed_by", help="Who proposed (default: this pin)"
    )

    thread_approve = thread_sub.add_parser(
        "approve", help="Approve a proposal: writes the ledger row, then the graph edge"
    )
    thread_approve.add_argument("ref", help="Proposal ref from `thread pending`")
    thread_approve.add_argument(
        "--surface", default="cli", choices=list(closes_mod.SURFACES),
        help="Where the approval was given",
    )
    thread_approve.add_argument(
        "--evidence", default="",
        help="What kind of evidence exists that the operator approved. Defaults to the "
             "surface's own (cli:tty). Never a bare assertion of approval",
    )
    thread_approve.add_argument("--notes", default="", help="Operator's own words")
    thread_approve.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")

    thread_reject = thread_sub.add_parser("reject", help="Decline a proposed close")
    thread_reject.add_argument("ref", help="Proposal ref")
    thread_reject.add_argument("--reason", default="", help="Why it was declined")

    thread_sub.add_parser("pending", help="Proposals awaiting the operator")

    thread_audit = thread_sub.add_parser(
        "audit", help="Corroborate graph-side closes against the ledger"
    )
    thread_audit.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")

    # Ceremony ledger — the room lifecycle's capture layer. Every verb here writes a
    # row that cannot be reconstructed after the fact, which is why they exist
    # before any of the lifecycle they record.
    ceremony_parser = subparsers.add_parser(
        "ceremony", help="The ceremony ledger: occasions, skips, deliverables, assignments"
    )
    ceremony_sub = ceremony_parser.add_subparsers(dest="ceremony_command")

    ceremony_start = ceremony_sub.add_parser(
        "start", help="Open an occasion — written at start so an abort still leaves a row"
    )
    ceremony_start.add_argument("room", help="Room the ceremony is held in")
    ceremony_start.add_argument("kind", choices=CEREMONY_KINDS, help="Which ceremony")
    ceremony_start.add_argument(
        "--scope", action="append", default=[], dest="scopes",
        help="A participating scope; repeat for each member",
    )
    ceremony_start.add_argument(
        "--deliverable", action="append", default=[], dest="deliverables",
        help="A deliverable id this occasion concerns; repeat as needed",
    )
    ceremony_start.add_argument(
        "--arm", default="",
        help="The arm this occasion realizes. Must match a prior assignment — the "
             "audit reports a disagreement rather than resolving it",
    )
    ceremony_start.add_argument("--prereg", default="", help="Pre-registration id")

    ceremony_end = ceremony_sub.add_parser("end", help="Close an occasion (appends, never mutates)")
    ceremony_end.add_argument("occasion", help="Occasion id, e.g. alpha:review:1")
    ceremony_end.add_argument(
        "--outcome", default="", help="How it ended — never how well it went"
    )

    ceremony_skip = ceremony_sub.add_parser(
        "skip", help="Record a ceremony that did NOT happen — the ablation is only "
                     "readable if a skip writes"
    )
    ceremony_skip.add_argument("room", help="Room the ceremony was due in")
    ceremony_skip.add_argument("kind", choices=CEREMONY_KINDS, help="Which ceremony")
    ceremony_skip.add_argument("--reason", default="", help="Free text; the row is the datum")

    ceremony_mint = ceremony_sub.add_parser(
        "mint", help="Mint a deliverable's permanent id, carried across every revision"
    )
    ceremony_mint.add_argument("room", help="Room the deliverable belongs to")
    ceremony_mint.add_argument("title", help="What it is; the id is derived once and then fixed")
    ceremony_mint.add_argument("--owner", default="", help="Owning scope")
    ceremony_mint.add_argument("--occasion", default="", help="Occasion that minted it")

    ceremony_revise = ceremony_sub.add_parser(
        "revise", help="Attach a revision to an existing deliverable id"
    )
    ceremony_revise.add_argument("deliverable", help="Deliverable id")
    ceremony_revise.add_argument(
        "--artifact", default="", help="What names this revision — a path, commit, or vertex id"
    )
    ceremony_revise.add_argument("--occasion", default="", help="Occasion that produced it")
    ceremony_revise.add_argument("--author", default="", help="Authoring scope")

    ceremony_assign = ceremony_sub.add_parser(
        "assign",
        help="Deal deliverables to arms from a seed, BEFORE the ceremony runs — "
             "unrecorded in advance, the reference distribution does not exist",
    )
    ceremony_assign.add_argument("room", help="Room; also the block permutation is restricted to")
    ceremony_assign.add_argument("kind", choices=CEREMONY_KINDS, help="Which ceremony")
    ceremony_assign.add_argument(
        "--unit", action="append", default=[], dest="units", required=True,
        help="A deliverable id to assign; repeat for each",
    )
    ceremony_assign.add_argument(
        "--arm", action="append", default=[], dest="arms", required=True,
        help="An arm name; repeat. Pair each with a --count in the same order",
    )
    ceremony_assign.add_argument(
        "--count", action="append", type=int, default=[], dest="counts", required=True,
        help="How many units that arm takes; must sum to the unit count",
    )
    ceremony_assign.add_argument(
        "--seed", type=int, required=True, help="The seed the deal is replayable from"
    )
    ceremony_assign.add_argument("--prereg", default="", help="Pre-registration id")

    # Items 5-7 — the forecast, its resolution, and the unit the room is read against.
    ceremony_commit = ceremony_sub.add_parser(
        "commit",
        help="Record a forecast about a deliverable — what will be true, and by when",
    )
    ceremony_commit.add_argument("room", help="Room making the commitment")
    ceremony_commit.add_argument("deliverable", help="Deliverable id the forecast is about")
    ceremony_commit.add_argument("text", help="What is being committed to")
    ceremony_commit.add_argument("--owner", default="", help="Owning scope")
    ceremony_commit.add_argument(
        "--artifact", default="", dest="predicted",
        help="What should exist if this came true — a path, a commit, a vertex id",
    )
    ceremony_commit.add_argument(
        "--resolve-by", default="", dest="resolve_by",
        help="The horizon tooling resolves this at (YYYY-MM-DD)",
    )
    ceremony_commit.add_argument("--occasion", default="", help="Occasion that committed it")

    ceremony_resolve = ceremony_sub.add_parser(
        "resolve",
        help="Record what became of a commitment. Run by tooling — a resolver who sat "
             "in the room is a finding, not a shortcut",
    )
    ceremony_resolve.add_argument("deliverable", help="Deliverable id being resolved")
    ceremony_resolve.add_argument(
        "outcome", choices=RESOLUTION_OUTCOMES, help="How the forecast came out"
    )
    ceremony_resolve.add_argument(
        "--resolver", required=True, help="What did the checking (a tool, a job)"
    )
    ceremony_resolve.add_argument(
        "--evidence", required=True,
        help="What it checked — a path, a commit, a vertex id",
    )
    ceremony_resolve.add_argument("--room", default="", help="Room, when not derivable")
    ceremony_resolve.add_argument("--occasion", default="", help="Occasion that resolved it")

    ceremony_comparator = ceremony_sub.add_parser(
        "comparator",
        help="Name the out-of-room unit this room is read against, while it still "
             "counts — one chosen after the outcomes are visible has absorbed them",
    )
    ceremony_comparator.add_argument("room", help="Room being compared")
    ceremony_comparator.add_argument(
        "arm", choices=COMPARATOR_ARMS, help="Which out-of-room arm"
    )
    ceremony_comparator.add_argument(
        "reference", help="The unit itself — a session id, a ticket id"
    )
    ceremony_comparator.add_argument(
        "--basis", default="", help="Why it is comparable"
    )

    ceremony_sub.add_parser(
        "outstanding", help="Commitments with no resolution yet, oldest first"
    )

    ceremony_ack = ceremony_sub.add_parser(
        "ack",
        help="Accept a permanent finding so the audit's exit code stops reporting it. "
             "The ledger is untouched and the finding is still printed",
    )
    ceremony_ack.add_argument(
        "finding", help="Exact `<category>:<item>` key as `audit` prints it"
    )
    ceremony_ack.add_argument(
        "--reason", required=True, help="Why this one is permanent and understood"
    )

    # Dispatch — delivery mechanics. A separate verb rather than a loop over
    # send-keys because `waiting` must be refused, not handled carefully.
    dispatch_parser = subparsers.add_parser(
        "dispatch", help="Deliver a message to live room members, refusing on `waiting`"
    )
    dispatch_parser.add_argument("room", help="Room whose members are addressed")
    dispatch_parser.add_argument(
        "message", nargs="?", default="",
        help="What to send. Omit when building an announcement with --task",
    )
    dispatch_parser.add_argument(
        "--to", action="append", default=[], dest="scopes",
        help="Restrict to this scope; repeat. Default: every live member",
    )
    dispatch_parser.add_argument(
        "--sender", default="",
        help="Who is dispatching (default: this process's scope). Inside a room this "
             "may only name the session's own scope — the sender is established by "
             "the process there, not asserted",
    )
    dispatch_parser.add_argument(
        "--operator", action="store_true",
        help="Dispatch into a room this session is not in. Refused by default: a "
             "member reaching another room is the one direction a room's config root "
             "does not bound",
    )
    dispatch_parser.add_argument(
        "--partial", action="store_true",
        help="Deliver to the reachable members anyway, recording who missed it. "
             "Without this, one undeliverable target refuses the whole fan-out, "
             "because a partial announcement makes silence ambiguous between a "
             "decline and never having been asked",
    )
    dispatch_parser.add_argument(
        "--dry-run", action="store_true",
        help="Pre-flight only: report what would land, send nothing, write no rows",
    )
    dispatch_parser.add_argument(
        "--no-submit", action="store_true",
        help="Type the text without the following Enter",
    )
    announce = dispatch_parser.add_argument_group(
        "Contract Net announcement", "All four slots are mandatory together"
    )
    announce.add_argument("--task", default="", help="Task abstraction")
    announce.add_argument("--eligibility", default="", help="Who this is for")
    announce.add_argument("--bid", default="", help="What a bid must contain")
    announce.add_argument("--expires", default="", help="Expiration; silence past it is a timeout")

    ceremony_sub.add_parser("show", help="The ledger room by room, with the audit under it")
    ceremony_audit = ceremony_sub.add_parser(
        "audit", help="Read the ledger against its own obligations; exits 1 on any "
                      "finding that has not been acknowledged"
    )
    ceremony_audit.add_argument(
        "--strict", action="store_true",
        help="Ignore acknowledgements entirely — exits 1 on every finding the ledger "
             "holds, which is what the ledger actually says",
    )

    # Console command — the operator surface onto the tmux roster, drivable from a phone
    console_parser = subparsers.add_parser(
        "console",
        help="Serve the console: drive the pinned tmux roster from a browser",
    )
    console_parser.add_argument(
        "--host", default="127.0.0.1",
        help="Bind address (default: localhost — the console has no auth of its own)"
    )
    console_parser.add_argument(
        "--port", type=int, default=CONSOLE_PORT, help=f"Port (default: {CONSOLE_PORT})"
    )
    console_parser.add_argument(
        "--session", default=ROSTER_SESSION,
        help=f"tmux session to drive (default: {ROSTER_SESSION})"
    )
    console_parser.add_argument(
        "--project-root", type=Path, default=None,
        help="The checkout roster sync runs against (default: the one this CLI is in)"
    )
    console_parser.add_argument(
        "--dir", type=Path, action="append", default=[], metavar="PATH",
        help="Offer this directory in the spawn picker, starred (repeatable; "
             "default: the project root)"
    )
    console_parser.add_argument(
        "--scan", type=Path, action="append", default=[], metavar="ROOT",
        help="Offer every git repo one level under ROOT in the spawn picker "
             "(repeatable; default: the project root's parent)"
    )
    console_parser.add_argument(
        "--service", action="append", default=[], metavar="UNIT",
        help="A unit the admin sheet may restart — a systemd `--user` unit on Linux, "
             "a launchd label on macOS (repeatable; "
             "default: none, which hides the section)"
    )
    console_parser.add_argument(
        "--frames", type=Path, default=None, metavar="PATH",
        help="Frame-theme definitions for the desktop client, e.g. "
             "$WEZTERM_CONFIG_DIR/frames.lua (default: none — no frame themes)"
    )
    # A console reached at the host the browser addressed needs none of these: the
    # request's own `Host` is the comparison. This is for a reverse proxy that
    # rewrites `Host` to the upstream (nginx does unless told
    # `proxy_set_header Host $host`), which makes the browser's `Origin` unmatchable
    # against anything the request still carries.
    console_parser.add_argument(
        "--allow-origin", action="append", default=[], metavar="ORIGIN",
        dest="allow_origin",
        help="Also accept writes from this origin, e.g. https://console.example.com "
             "(repeatable; default: none — only the origin the request was addressed "
             "to is accepted)"
    )
    console_parser.add_argument(
        "--fetch-interval", type=float, default=10.0, metavar="MINUTES",
        help="How often to fetch the checkout's remote so the console knows whether "
             "it is behind (default: 10; 0 disables, and the count then only reflects "
             "the last fetch somebody ran)"
    )

    # Pulse command — the live telemetry dashboard
    pulse_parser = subparsers.add_parser(
        "pulse",
        help="Serve the live telemetry dashboard over the eval loop's measurements",
    )
    pulse_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    pulse_parser.add_argument(
        "--host", default="127.0.0.1", help="Bind address (default: localhost)"
    )
    pulse_parser.add_argument(
        "--port", type=int, default=8379, help="Port (default: 8379; /pulse via tailscale serve)"
    )

    args = parser.parse_args()
    # Long-running commands (bootstrap, extract) are routinely piped to a log; without
    # line buffering their progress sits invisible in Python's block buffer for minutes.
    # typeshed types `sys.stdout` as the `TextIO` ABC, which does not carry
    # `reconfigure`; the concrete `TextIOWrapper` CPython actually installs does.
    sys.stdout.reconfigure(line_buffering=True)  # ty: ignore[unresolved-attribute]
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "write":
        _cmd_write(args)
    elif args.command == "validate":
        _cmd_validate(args)
    elif args.command == "schema":
        _cmd_schema()
    elif args.command == "bootstrap":
        _cmd_bootstrap(args)
    elif args.command == "extract":
        _cmd_extract(args)
    elif args.command == "ingest":
        _cmd_ingest(args)
    elif args.command == "contract":
        _cmd_contract(args, contract_parser)
    elif args.command == "backfill-chunks":
        _cmd_backfill_chunks(args)
    elif args.command == "audit-artifacts":
        _cmd_audit_artifacts(args)
    elif args.command == "repair-projects":
        _cmd_repair_projects(args)
    elif args.command == "derive-artifact-paths":
        _cmd_derive_artifact_paths(args)
    elif args.command == "retire-scans":
        _cmd_retire_scans(args)
    elif args.command == "repair-claim-addresses":
        _cmd_repair_claim_addresses(args)
    elif args.command == "snapshot":
        _cmd_snapshot(args)
    elif args.command == "eval":
        _cmd_eval(args, eval_parser)
    elif args.command == "init":
        _cmd_init(args)
    elif args.command == "status":
        _cmd_status(args)
    elif args.command == "rescope":
        _cmd_rescope(args)
    elif args.command == "pin":
        _cmd_pin(args)
    elif args.command == "spawn":
        _cmd_spawn(args)
    elif args.command == "roster":
        _cmd_roster(args)
    elif args.command == "quick":
        _cmd_quick(args, quick_parser)
    elif args.command == "room":
        _cmd_room(args, parser)
    elif args.command == "thread":
        _cmd_thread(args, thread_parser)
    elif args.command == "ceremony":
        _cmd_ceremony(args, parser)
    elif args.command == "dispatch":
        _cmd_dispatch(args)
    elif args.command == "console":
        _cmd_console(args)
    elif args.command == "pulse":
        _cmd_pulse(args)
    elif args.command == "arch":
        _cmd_arch(args, arch_parser)
    else:
        parser.print_help()
        sys.exit(1)


def _persist(graph, path: str = DEFAULT_SNAPSHOT_PATH) -> None:
    """Flush the graph to disk after a successful write.

    The substrate keeps the graph in memory and only writes it back on a clean
    shutdown, so without this a `docker kill` between now and the next stop would
    discard the write. Best-effort: a failed flush warns, it does not turn a
    successful write into a reported failure.
    """
    snapshot_quietly(graph, path)


def _cmd_write(args):
    data = _load_file(args.file)
    session = SessionGraph(**data)
    g = connect(args.url)
    try:
        vid = write_session_checked(g, session)
        _persist(g)
        print(f"Wrote session: {session.session_id} -> {vid}")
    except ContractViolation as e:
        print(f"REJECTED — {e}", file=sys.stderr)
        print("\n`thalamus validate` reports the same issues without a graph.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Write failed: {e}", file=sys.stderr)
        print("Re-run with --debug for Gremlin bytecode and server details.", file=sys.stderr)
        sys.exit(1)
    finally:
        close_connection(g)


def _cmd_validate(args):
    data = _load_file(args.file)
    try:
        session = SessionGraph(**data)
        print(f"Schema OK. Session: {session.session_id}")
        print(f"  Scope:       {session.scope}")
        print(f"  Project:     {session.project or '—'}")
        print(f"  Artifacts:   {len(session.artifacts)}")
        print(f"  Claims:      {len(session.claims())} "
              f"({len(session.decisions)} decision, {len(session.problems)} problem, "
              f"{len(session.solutions)} solution)")
        print(f"  Threads:     {len(session.threads)}")
        print(f"  Thread refs: {len(session.thread_refs)}")

        issues = check_session(session)
        if issues:
            print("\nREJECTED — does not satisfy the federation contract:", file=sys.stderr)
            for issue in issues:
                print(f"  - {issue}", file=sys.stderr)
            sys.exit(1)
        print("\nContract OK.")
    except Exception as e:
        print(f"Validation failed: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_schema():
    print(json.dumps(SessionGraph.model_json_schema(), indent=2))


def _claude_bootstrap_groups(args):
    """(label, results) per named project dir, or None when the run only listed."""
    root = args.projects_dir or transcripts.CLAUDE_PROJECTS
    available = transcripts.discover(args.projects_dir)
    if not available:
        print(f"No Claude Code transcripts found under {root}", file=sys.stderr)
        sys.exit(1)

    if not args.projects:
        print(f"Transcripts under {root}:\n")
        for name, paths in sorted(available.items(), key=lambda kv: -len(kv[1])):
            size_mb = sum(p.stat().st_size for p in paths) / 1_000_000
            print(f"  {len(paths):>3} transcripts  {size_mb:>6.1f} MB  {name}")
        print("\nBootstrap them with (note the `--`; the names start with a dash):")
        print("  thalamus bootstrap -- <project-dir> [<project-dir> ...] [--write]")
        print(f"Archive: {archive_dir()}  (outside the repo, deliberately)")
        return None

    unknown = [p for p in args.projects if p not in available]
    if unknown:
        print(f"Unknown project dir(s): {', '.join(unknown)}", file=sys.stderr)
        sys.exit(1)

    return [
        (project, bootstrap_project(
            project, projects_dir=args.projects_dir, scope=args.scope))
        for project in args.projects
    ]


def _session_bootstrap_groups(args, harness: str):
    """One group per resolved scope — Cursor and codex discovery are session-oriented.

    Grouping by scope rather than by directory because that is the axis these sessions
    actually vary on: they are pinned by `THALAMUS_SCOPE` at launch, and the directory
    each lands under answers a different question — a flattened cwd we deliberately
    never un-flatten on Cursor, the calendar day on codex.
    """
    from thalamus.harness.bootstrap import bootstrap_codex, bootstrap_cursor

    reader = _SESSION_READERS[harness]
    builder = {"cursor": bootstrap_cursor, "codex": bootstrap_codex}[harness]

    found = [s for s in reader.discover() if s.exists]
    if not found:
        if harness == "cursor":
            where = (
                "Discovery reads the sessionEnd hook log "
                f"({cursor_transcripts.CURSOR_SESSION_END_LOG}) and sweeps "
                f"{cursor_transcripts.CURSOR_PROJECTS}; nothing in either"
            )
        else:
            where = (
                f"Discovery sweeps {codex_transcripts.sessions_root()}, which the CLI "
                "writes for every session whether or not the hooks were armed; nothing "
                "there"
            )
        print(
            f"No {harness} sessions found. {where} means no {harness} session has run "
            "on this machine.",
            file=sys.stderr,
        )
        sys.exit(1)

    ready, refused = reader.claim_unresolved(found, args.assign_scope)
    if refused:
        print(
            f"  ! {len(refused)} session(s) found on disk that no hook ever saw, so no "
            "scope was ever resolved for them. They are NOT being bootstrapped. Re-run "
            "with `--assign-scope <scope>` to route them, after checking they belong "
            "there:",
            file=sys.stderr,
        )
        for session in refused:
            where = getattr(session, "cwd", "") or str(
                getattr(session, "transcript_path", "") or "cwd unknown"
            )
            print(f"      {session.session_id[:8]}  {where}", file=sys.stderr)
    if not ready:
        return None

    by_scope: dict[str, list] = {}
    for session in ready:
        by_scope.setdefault(session.scope, []).append(session)
    return [
        (f"{harness} · scope {scope}", builder(sessions))
        for scope, sessions in sorted(by_scope.items())
    ]


def _cmd_bootstrap(args):
    if args.harness == "claude":
        groups = _claude_bootstrap_groups(args)
    else:
        groups = _session_bootstrap_groups(args, args.harness)
        if groups is None:
            return
        if groups is None:
            return

    graph = connect(args.url) if args.write else None
    all_secrets: dict[str, int] = {}
    written = skipped = rejected = 0
    nodes = 0

    try:
        for label, results in groups:
            print(f"\n=== {label} ({len(results)} transcripts) ===")
            for result in results:
                name = result.transcript.stem[:8]
                if result.skipped:
                    skipped += 1
                    print(f"  ○ {name}  skipped — {result.skipped}")
                    continue
                if result.issues:
                    rejected += 1
                    print(f"  ✗ {name}  REJECTED by the contract:")
                    for issue in result.issues:
                        print(f"      - {issue}")
                    continue

                session = result.session
                count = 1 + len(session.sources) + len(session.artifacts)
                nodes += count
                for pattern, hits in result.secrets.items():
                    all_secrets[pattern] = all_secrets.get(pattern, 0) + hits

                mark = "·" if result.already_archived else "+"
                flag = f"  ⚠ {sum(result.secrets.values())} secret-ish" if result.secrets else ""
                print(
                    f"  {mark} {name}  {len(session.artifacts):>3} artifacts  "
                    f"{session.summary[:58]}{flag}"
                )

                if graph is not None:
                    write_session_checked(graph, session)
                written += 1
    finally:
        if graph is not None:
            # One flush for the whole run, not one per session — bootstrap writes
            # the entire corpus and the snapshot rewrites the whole graph file.
            if written:
                _persist(graph)
            close_connection(graph)

    print(f"\n{written} sessions, ~{nodes} nodes; {skipped} skipped, {rejected} rejected")
    print(f"Archive: {archive_dir()}")
    if all_secrets:
        print("\n⚠  Possible credentials in the retained transcripts:")
        for pattern, hits in sorted(all_secrets.items(), key=lambda kv: -kv[1]):
            print(f"     {hits:>4}x  {pattern}")
        print("   The archive is local and outside the repo. It is NOT redacted —")
        print("   evidence that has been quietly rewritten is not evidence.")
    if not args.write:
        print("\nDRY RUN — nothing written to the graph. Re-run with --write to persist.")


def _retained_raw_path(session_id: str, scope: str) -> Path:
    return Path.home() / ".thalamus" / "extractions" / f"{scope}-{session_id}.txt"


def _retain_raw_extraction(session_id: str, scope: str, text: str) -> Path:
    """Write a model's extraction response to disk before anything validates it.

    The response is the expensive artifact — the digest pass is where the money went.
    Retaining it first makes every downstream refusal recoverable by re-parsing rather
    than re-paying, which is the difference between a bug and an outage. `--reuse-raw`
    is the path that spends the retention: it replays this file instead of the model.
    """
    path = _retained_raw_path(session_id, scope)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@dataclass
class _Candidates:
    """What one harness's discovery-and-parse pass produced, for the shared tail."""

    # `TranscriptFacts`, unsorted — the caller orders them chronologically.
    parsed: list
    # Sessions the substance gate withheld, by id, so an explicitly named one is
    # reported as *skipped* rather than as *missing*.
    insubstantial: list[str]
    # session id -> scope, where the harness resolves scope per session rather than
    # from the flag. Empty is the ordinary answer, not a gap: Claude Code carries its
    # scope on the command line.
    scopes: dict[str, str]
    # What to name in "No session matching X under ..." — the surface actually swept.
    where: str
    # Whether a named session missing from the live surface may be recovered from the
    # archive. Declared rather than tested, because it is a property of the harness:
    # `transcripts.archived_transcripts` reads Claude Code's own `sessionId` field out
    # of retained bytes, and Cursor's evidence is deliberately not retained whole.
    recover_from_archive: bool = False
    # A discovery that found nothing and has already said so. Distinct from an empty
    # `parsed`, which is a sweep that found sessions and kept none of them.
    nothing_found: bool = False


def _report_unrecognized(parsed: list, harness: str, module: str) -> None:
    """Say when a reader could not classify records, rather than absorbing it.

    Recognition is kept complete and separate from processing in every reader here,
    and this is the surface that makes the count matter: a parser written against a
    vendor format can only learn the format changed by saying what it failed to read.
    A count nobody reads is the same silent failure as no count at all.
    """
    unread = sum(f.unrecognized for f in parsed)
    if not unread:
        return
    sessions = sum(1 for f in parsed if f.unrecognized)
    print(
        f"  ! {unread} record(s) across {sessions} session(s) did not match the "
        f"expected {harness} shape — the format may have changed (see {module})",
        file=sys.stderr,
    )


def _candidates_claude(args) -> _Candidates:
    available = transcripts.discover(args.projects_dir)
    if not args.projects:
        print("Specify project dir(s); `thalamus bootstrap` lists what is available.")
        return _Candidates([], [], {}, "", nothing_found=True)

    unknown = [p for p in args.projects if p not in available]
    if unknown:
        # Naming the root matters here: a room member's transcripts live under
        # its own CLAUDE_CONFIG_DIR, so the same project dir name is genuinely
        # absent from the default root and the failure is otherwise
        # indistinguishable from a typo.
        root = args.projects_dir or transcripts.CLAUDE_PROJECTS
        print(
            f"Unknown project dir(s) under {root}: {', '.join(unknown)}",
            file=sys.stderr,
        )
        sys.exit(1)

    parsed, insubstantial = [], []
    for project in args.projects:
        for path in available[project]:
            facts = transcripts.parse(path)
            if not facts.has_substance:
                insubstantial.append(facts.session_id)
                continue
            # An extraction sandbox is not a session (harness/agents.py).
            # `discover()` already withholds the project dir; this reads the
            # cwd the transcript itself recorded, so the refusal holds for a
            # sandbox transcript reached any other way.
            if agents.is_sandbox_cwd(facts.cwd):
                continue
            parsed.append(facts)
    return _Candidates(
        parsed, insubstantial, {},
        where=f"{', '.join(args.projects)} or the archive",
        recover_from_archive=True,
    )


def _candidates_cursor(args) -> _Candidates:
    ended = [s for s in cursor_transcripts.discover() if s.exists]
    if not ended:
        print(
            "No Cursor sessions to extract. Sessions are found two ways: the "
            f"sessionEnd hook's log ({cursor_transcripts.CURSOR_SESSION_END_LOG}) "
            f"and a sweep of {cursor_transcripts.CURSOR_PROJECTS}. Nothing in "
            "either means no Cursor session has ended on this machine yet.",
            file=sys.stderr,
        )
        return _Candidates([], [], {}, "", nothing_found=True)

    ended = _claim_or_report(ended, cursor_transcripts, args.assign_scope)

    # Scope comes from the session's own sessionEnd record, not the flag:
    # ledger-first resolution is what keeps a pinned Cursor session out of
    # the wrong subgraph. A cursor session carries no timestamps
    # or cwd of its own, so both come from the hooks' ledgers.
    parsed, insubstantial, scopes = [], [], {}
    for ended_session in ended:
        cwd, started_at = cursor_transcripts.session_context(ended_session.session_id)
        facts = cursor_transcripts.parse(
            ended_session.transcript_path,
            session_id=ended_session.session_id,
            cwd=cwd,
            started_at=started_at,
            ended_at=ended_session.ended_at,
        )
        if not facts.has_substance:
            insubstantial.append(facts.session_id)
            continue
        # An extraction sandbox is not a session (harness/agents.py). The
        # Cursor sweep withholds sandbox project dirs, and this is the same
        # second refusal the Claude Code path makes, on the cwd the session
        # itself recorded — every headless extraction is a full Cursor session
        # that files its own transcript, so a sandbox reached by any other
        # route still has to be refused here.
        if agents.is_sandbox_cwd(facts.cwd):
            continue
        scopes[facts.session_id] = ended_session.scope
        parsed.append(facts)

    _report_unrecognized(parsed, "Cursor", "harness/cursor_transcripts.py")
    return _Candidates(parsed, insubstantial, scopes, where="the Cursor sessionEnd log")


def _candidates_codex(args) -> _Candidates:
    """Codex sessions, by session id rather than by project dir.

    A codex rollout is filed under the day it ran, not under its cwd, so there is no
    project-dir argument to take and the whole sessions tree is the sweep. Everything
    else — timestamps, cwd, tool results — is in the file, so unlike Cursor there is
    no ledger to consult for anything but the scope.

    `--transcript` short-circuits the sweep with the path the SessionEnd hook was
    handed. That is not an optimisation: the hook already knows the exact file, and
    re-deriving it by scanning a tree for a matching id is a second chance to pick the
    wrong one.
    """
    root = codex_transcripts.sessions_root()
    if getattr(args, "transcript", ""):
        path = Path(args.transcript)
        if not path.is_file():
            print(f"No codex transcript at {path} — nothing distilled.", file=sys.stderr)
            sys.exit(1)
        session_id = codex_transcripts.session_id_of(path) or path.stem
        # Ledger first, flag second — the same precedence the sweep uses. The hook
        # already resolves the scope and passes it, so this only decides the case
        # where someone re-extracts a named transcript by hand and the flag is at its
        # default: a session pinned to an expert must not land in `main` because a
        # re-run forgot to say so.
        found = [
            codex_transcripts.CodexSession(
                session_id=session_id,
                transcript_path=path,
                scope=codex_transcripts.ledger_scope(session_id) or args.scope,
            )
        ]
    else:
        found = [s for s in codex_transcripts.discover() if s.exists]
        if not found:
            print(
                f"No codex sessions to extract. Codex writes every session as a "
                f"rollout under {root}; nothing there means no codex session has run "
                "on this machine yet.",
                file=sys.stderr,
            )
            return _Candidates([], [], {}, "", nothing_found=True)
        found = _claim_or_report(found, codex_transcripts, args.assign_scope)

    parsed, insubstantial, scopes = [], [], {}
    for session in found:
        facts = codex_transcripts.parse(
            session.transcript_path, session_id=session.session_id
        )
        if not facts.has_substance:
            insubstantial.append(facts.session_id)
            continue
        # The same second refusal the other two make. Codex's own extraction sandbox
        # runs `--ephemeral` and writes no rollout at all, so nothing this sweep finds
        # should be one — which is exactly why the check stays: a sandbox that reached
        # disk anyway is a broken assumption, not a session.
        if agents.is_sandbox_cwd(facts.cwd):
            continue
        scopes[facts.session_id] = session.scope
        parsed.append(facts)

    _report_unrecognized(parsed, "codex", "harness/codex_transcripts.py")
    return _Candidates(parsed, insubstantial, scopes, where=str(root))


def _claim_or_report(found: list, reader, assign_scope: str) -> list:
    """Keep the sessions a sweep may route, and say why the rest are being left.

    A session no hook ever saw has no resolved scope, and `main` is not a safe stand-in
    — routing an unattested session into the operator's own subgraph is a decision
    nobody made and cannot be undone once written, because scope is part of the vertex
    ID. Shared by the two harnesses that can find a session their hooks never saw.
    """
    ready, refused = reader.claim_unresolved(found, assign_scope)
    if refused:
        print(
            f"  ! {len(refused)} session(s) found on disk that no hook ever saw, so no "
            "scope was ever resolved for them. They are NOT being extracted. Re-run "
            "with `--assign-scope <scope>` to route them, after checking they belong "
            "there:",
            file=sys.stderr,
        )
        for session in refused:
            where = getattr(session, "cwd", "") or str(
                getattr(session, "transcript_path", "") or "cwd unknown"
            )
            print(f"      {session.session_id[:8]}  {where}", file=sys.stderr)
    return ready


# The transcript reader and the candidate source, per harness.
#
# Deliberately **not** a `TranscriptReader` protocol. The three readers differ in what
# they can offer, not merely in how they do it: Cursor cannot supply a cwd or a
# timestamp from its transcript and reaches for our own ledgers to get them, while
# Claude Code and codex read both out of the file. An interface wide enough for all
# three would have to be the union of what they happen to do, which moves the fork
# into optional methods and hides it. `harness/bootstrap.py` already settled this
# shape — `_bootstrap_one` takes what differs as parameters and looks nothing up.
class _DiscoveredSession(Protocol):
    """What every session-oriented reader guarantees about what it discovered.

    A read-only property rather than an attribute: both readers derive `exists` from
    the filesystem, and a protocol declaring a settable attribute does not match one.
    """

    @property
    def exists(self) -> bool: ...


class SessionReader(Protocol):
    """The surface `_session_bootstrap_groups` needs from a harness's reader module.

    Declared because it is a real contract that three modules carry and no base class
    states. Without it the modules are three unrelated objects that happen to share
    method names, which is a duck type nothing can check — and the ducks had already
    drifted apart: only two of the three answer `claim_unresolved`.
    """

    def discover(self) -> Sequence[_DiscoveredSession]: ...

    def claim_unresolved(
        self, sessions: list[Any], assign_scope: str = ""
    ) -> tuple[list[Any], list[Any]]: ...


_READERS = {
    "claude": transcripts,
    "cursor": cursor_transcripts,
    "codex": codex_transcripts,
}
# The session-oriented subset. Cursor and codex discover *sessions* and can be asked
# which of them no hook ever resolved a scope for; Claude Code discovers transcripts
# under a project directory and answers no such question. Keeping the two mappings
# apart states which harnesses `_session_bootstrap_groups` actually accepts, instead of
# leaving it to a KeyError at the third one.
_SESSION_READERS: dict[str, SessionReader] = {
    "cursor": cursor_transcripts,
    "codex": codex_transcripts,
}
_CANDIDATE_SOURCES = {
    "claude": _candidates_claude,
    "cursor": _candidates_cursor,
    "codex": _candidates_codex,
}


def _cmd_extract(args):
    """Stage 2 of the bootstrap: model-extracted Claims and Threads.

    Sessions are processed chronologically so a thread opened in March can be resolved by
    a session from April — the same replay semantics a live agent would have produced.
    """
    from thalamus.archive import read_archived, report_secrets
    from thalamus.contract.conformance import prune_orphan_artifacts
    from thalamus.contract.ontology import vid

    reader = _READERS[args.harness]

    extracted = skipped = failed = 0
    total_cost = 0.0
    unpriced = replayed = 0

    # Session selection runs before the graph connection: a run that selects nothing
    # has no reason to open one, and the refusal below stays reachable on a machine
    # whose graph is down.
    candidates = _CANDIDATE_SOURCES[args.harness](args)
    if candidates.nothing_found:
        return
    parsed = candidates.parsed
    insubstantial = candidates.insubstantial
    scopes = candidates.scopes
    # Chronological across everything the sweep found: threads resolve forward in time.
    parsed.sort(key=lambda f: (f.started_at is None, f.started_at))

    if args.session:
        parsed = [
            f for f in parsed if any(f.session_id.startswith(s) for s in args.session)
        ]
        # Then the archive, for the named sessions ~/.claude no longer holds. The
        # harness rotates its own transcripts, which is why they are retained at all
        # — a recovery that could read only the live dir would still lose a
        # session to the rotation retention was built to survive. Only for a *named*
        # session: a sweep of the archive would re-offer the whole distilled corpus,
        # and only where the harness declares the archive reachable, which today is
        # Claude Code alone: its retained bytes carry the `sessionId` field
        # `archived_transcripts` reads, where Cursor's evidence is deliberately not
        # retained whole and codex's rollout names its session nowhere that scan looks.
        if candidates.recover_from_archive:
            unmatched = [
                requested for requested in args.session
                if not any(f.session_id.startswith(requested) for f in parsed)
            ]
            archived = transcripts.archived_transcripts() if unmatched else {}
            for session_id, path in sorted(archived.items()):
                if not any(session_id.startswith(r) for r in unmatched):
                    continue
                facts = transcripts.parse(path, session_id=session_id)
                if not facts.has_substance:
                    insubstantial.append(facts.session_id)
                    continue
                if agents.is_sandbox_cwd(facts.cwd):
                    continue
                print(
                    f"  ↺ {session_id[:8]}  recovered from the archive — "
                    "no longer under ~/.claude/projects"
                )
                parsed.append(facts)
            parsed.sort(key=lambda f: (f.started_at is None, f.started_at))
        # An explicit --session that matches nothing is a failure, not a no-op.
        # This is the SessionEnd hook's own invocation shape, and it runs
        # detached into a log nobody reads: "0 sessions to extract" is
        # indistinguishable there from a session that legitimately had nothing
        # to distill, which is how a wrong project dir lost three sessions
        # before anyone noticed. Named input, no match, non-zero.
        if not parsed:
            requested = ", ".join(args.session)
            # A named session the substance gate withheld is not a missing session,
            # and must not print the message that means "wrong project dir". This is
            # the SessionEnd hook's own invocation shape: it runs detached into a log,
            # so collapsing the two would put the diagnostic that once cost three
            # sessions on every `/clear`-only close, and the exit code would fail a
            # hook that behaved correctly. Named, found, deliberately not distilled —
            # say so, and exit clean.
            withheld = [
                sid for sid in insubstantial
                if any(sid.startswith(s) for s in args.session)
            ]
            if withheld:
                print(
                    f"{', '.join(s[:8] for s in withheld)}: no substantive exchange "
                    "(slash commands only, no tool use) — nothing to distill."
                )
                sys.exit(0)
            print(
                f"No session matching {requested} under {candidates.where} — "
                "nothing distilled.",
                file=sys.stderr,
            )
            sys.exit(1)
    if args.limit:
        parsed = parsed[: args.limit]

    # Flag, then the ledger, then this process's environment — and the ledger is
    # consulted per session inside the loop below, because a sweep spans sessions that
    # were launched into different rooms and one answer for all of them is wrong for
    # most. The env is last rather than first: it describes the shell running the
    # re-extraction, not the session being re-extracted, so preferring it stamps
    # `room=""` on members and `witnesses.py` then counts a room's correlated writes as
    # independent corroboration — the failure direction that invents evidence instead
    # of losing it. The flag still wins, for extracting a transcript whose launch the
    # ledger never saw.
    env_room = resolve_room()
    env_forked_from = resolve_forked_from()

    # One resolution for the whole sweep, printed once. This line lands in
    # ~/.thalamus/logs/session-end-<sid8>.log, which — since the graph records the
    # harness that *wrote* a Session and not the CLI that distilled it — is the only
    # per-run record of what produced these claims.
    extractor = extractor_policy.resolve(
        pass_="distill",
        source_harness=args.harness,
        harness=args.extract_with or "",
        model=args.model or "",
    )
    print(
        f"{len(parsed)} sessions to extract "
        f"(extractor: {extractor.harness}/{extractor.model} — {extractor.reason})"
    )

    graph = connect(args.url)
    try:
        for facts in parsed:
            name = facts.session_id[:8]
            # Per-session where the harness resolved one, the flag otherwise. Uniform
            # rather than forked: a harness that carries no per-session scope supplies
            # an empty map, and `args.scope` is then the answer by the same rule.
            scope = scopes.get(facts.session_id, args.scope)
            session_vid = vid("Session", facts.session_id, scope)

            if not args.force and _session_has_claims(graph, session_vid):
                skipped += 1
                print(f"  · {name}  already extracted — skipping (--force to redo)")
                continue

            # A replay is refused before the archive is touched: the flag exists to
            # recover a run already paid for, so a session with nothing retained is
            # reported and passed over rather than quietly turned into a live call.
            retained = _retained_raw_path(facts.session_id, scope) if args.reuse_raw else None
            if retained is not None and not retained.exists():
                skipped += 1
                print(f"  · {name}  no retained response at {retained} — skipping")
                continue

            launched = pin.ledger_facts(facts.session_id)
            room = args.room if args.room is not None else (
                launched.get("room") or env_room
            )
            forked_from = args.forked_from if args.forked_from is not None else (
                launched.get("forked_from") or env_forked_from
            )

            entry, secrets = transcripts.retain(facts.path)
            # This is the path that runs at every session end. The scan reports and
            # never redacts, so computing it and dropping it would be the same as not
            # scanning at all — `report_secrets` is the consumer, on stderr and in
            # ~/.thalamus/logs/secret-scan.log.
            report_secrets(secrets, f"session {facts.session_id[:8]} transcript")
            # A Cursor session's ingress evidence lives outside its transcript, so the
            # transcript alone would not reach what the floor judged.
            transcripts.retain_ingress_receipt(facts)
            base = reader.to_session_graph(
                facts,
                content_hash=entry.content_hash,
                uri=entry.uri,
                byte_size=entry.byte_size,
                scope=scope,
                room=room,
                forked_from=forked_from,
            )

            if retained is None:
                payload = read_archived(entry.content_hash, suffix=".jsonl")
                digest = extraction.render_digest(payload, harness=args.harness)
                prompt = extraction.build_prompt(
                    digest,
                    project=facts.project,
                    title=facts.title or name,
                    open_threads=_open_threads(graph, args.scope, facts.project),
                    known_claims=_known_claims(graph, args.scope, facts.project),
                )

            try:
                if retained is None:
                    run = extraction.run_extraction(
                        prompt, model=extractor.model, harness=extractor.harness
                    )
                    # The paid output lands on disk before anything can reject it. Every
                    # failure below is then re-parseable without re-invoking a model —
                    # the run is spent once, whatever happens to it afterwards.
                    raw_path = _retain_raw_extraction(facts.session_id, scope, run.text)
                else:
                    # $0.00 here is the literal price of this run, not a free model
                    # call: the money was spent by the run that wrote the file, and a
                    # replay re-reads it. Everything downstream is unchanged, which is
                    # the point — a fixed parser or validator gets a second look at the
                    # same bytes rather than at a differently-worded second answer.
                    run = extraction.ExtractionRun(text=retained.read_text(), cost_usd=0.0)
                    raw_path = retained
                data = extraction.parse_extraction(run.text)
                # Partial acceptance: one malformed item costs that item, not the
                # session. Nothing is invented to satisfy a required field.
                data, dropped = extraction.partition_valid(data)
                for note in dropped:
                    print(f"  ! {name}  dropped {note}")
                if dropped:
                    print(f"      raw response retained at {raw_path}")
                session = extraction.merge_extraction(base, data)
                # The laundering floor: claims resting on the transcript's
                # external ingress keep third-party trust, marked or not. A format
                # that cannot carry tool results (Cursor) floors the whole session
                # instead — an empty list there is ignorance, not evidence.
                session = extraction.apply_ingress_floor(
                    session,
                    facts.external_texts,
                    ingress_verifiable=facts.ingress_verifiable,
                )
                session = prune_orphan_artifacts(session)
            except Exception as e:
                failed += 1
                print(f"  ✗ {name}  extraction failed: {str(e)[:120]}")
                continue

            issues = check_session(session)
            if issues:
                failed += 1
                print(f"  ✗ {name}  REJECTED by the contract:")
                for issue in issues:
                    print(f"      - {issue}")
                continue

            if run.cost_usd is None:
                unpriced += 1
            else:
                total_cost += run.cost_usd
            floored = sum(1 for claim in session.claims() if claim.external)
            counts = (
                f"{len(session.claims()):>2} claims  {len(session.threads)} threads  "
                f"{len(session.thread_refs)} refs"
                + (f"  {floored} ingress-floored" if floored else "")
            )
            if args.write:
                try:
                    write_session_checked(graph, session)
                except Exception as e:
                    failed += 1
                    print(f"  ✗ {name}  write failed: {str(e)[:160]}")
                    continue
            extracted += 1
            if retained is not None:
                replayed += 1
                priced = "replay"
            else:
                priced = f"${run.cost_usd:.2f}" if run.cost_usd is not None else "  $ ?"
            print(f"  + {name}  {counts}  {priced}  {session.summary[:48]}")

    finally:
        if args.write and extracted:
            _persist(graph)
        close_connection(graph)

    # "$0.00 across N sessions" would read as free rather than as unmeasured, so
    # unpriced runs are counted separately — Cursor's CLI reports no cost fields.
    unpriced_note = f" ({unpriced} unpriced — the CLI reports no cost)" if unpriced else ""
    # A replay is reported apart from the price for the same reason: its $0.00 is a
    # bill already paid, not a session that cost nothing to distill.
    replay_note = (
        f" ({replayed} replayed from retained responses — paid for on an earlier run)"
        if replayed else ""
    )
    print(
        f"\n{extracted} extracted, {skipped} skipped, {failed} failed; "
        f"model cost ${total_cost:.2f}{unpriced_note}{replay_note}"
    )
    if not args.write:
        print("DRY RUN — nothing written to the graph. Re-run with --write to persist.")


def _session_has_claims(graph, session_vid: str) -> bool:
    try:
        count = graph.V(session_vid).out_e("CONTAINS").count().next()
    except Exception:
        return False
    return count > 0


def _open_threads(graph, scope: str, project: str) -> list[dict]:
    from gremlin_python.process.traversal import P

    try:
        rows = (
            graph.V()
            .has_label("Thread")
            .has("scope", scope)
            .has("project", project)
            .has("status", P.within("open", "in_progress"))
            .value_map("thread_id", "title", "status")
            .to_list()
        )
    except Exception:
        return []
    return [
        {
            "id": row.get("thread_id", [""])[0],
            "title": row.get("title", [""])[0],
            "status": row.get("status", [""])[0],
        }
        for row in rows
    ]


_PREFLIGHT_EXCERPT = 400


def _report_preflight(args, ingest_mod):
    """`thalamus ingest <doc> --scope <s> --check` — everything short of the model call.

    Deliberately not a reimplementation of the checks: it calls `ingest.preflight`, the
    same function `ingest()` calls, so the check and the ingest cannot disagree about
    which host served the bytes or whether the allowlist admits it. A prose procedure
    could not hold that parity — the `curl` incantation it replaces went through three
    revisions in one day, each against a measurement, and still stopped a redirect hop
    short of `urlopen` and sent a different User-Agent.

    Exits non-zero on refusal, because this is what a batch script gates on.
    """
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


def _cmd_ingest(args):
    from urllib.parse import urlparse

    from thalamus.contract.conformance import check_knowledge
    from thalamus.contract.manifest import load_manifest
    from thalamus.harness import extraction as extraction_mod
    from thalamus.harness import ingest as ingest_mod
    from thalamus.substrate.writer import write_knowledge

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
    # archive write and the extraction pass, all three of which used to complete
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
        _report_preflight(args, ingest_mod)
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
        source_vid = write_knowledge(graph, batch)
        _persist(graph)
        print(f"\nWritten into scope `{batch.scope}`: {source_vid}")
    finally:
        close_connection(graph)


def _cmd_derive_artifact_paths(args):
    """Give every Artifact a derived `(repo, path)` beside its untouched identifier.

    The counts are the point of the dry run: how many artifacts the registry can anchor,
    how many belong to no repo at all, and how many spellings collapse onto one file.
    """
    from thalamus.substrate.artifact_paths import plan, write_projection

    graph = connect(args.url)
    try:
        projection_plan = plan(graph)
        registry = projection_plan.registry
        print(f"Proven checkout roots in the registry: {len(registry)}")
        for root in registry[:10]:
            print(f"  {root}")
        if len(registry) > 10:
            print(f"  … and {len(registry) - 10} more")

        counts = projection_plan.counts()
        print("\n" + "  ".join(f"{key}: {value}" for key, value in counts.items()))

        fragmented = {
            key: spellings
            for key, spellings in projection_plan.groups().items()
            if len(spellings) > 1
        }
        print(f"\nfiles reachable under more than one spelling: {len(fragmented)}")
        for (repo, path), spellings in sorted(
            fragmented.items(), key=lambda kv: -len(kv[1])
        )[:8]:
            print(f"  {len(spellings)}x  {repo}/{path}")

        if not args.write:
            print("\nDry run. Re-run with --write to apply.")
            return
        resolved = write_projection(graph, projection_plan)
        print(f"\nWrote {len(projection_plan.projections)} artifacts, {resolved} anchored.")
    finally:
        close_connection(graph)


def _cmd_retire_scans(args):
    """Remove the Sources and Claims that architecture scans used to land.

    Dry-run by default, and it prints what it keeps as well as what it takes: the
    Artifacts a scan touched are usually the same vertices sessions touched, so the
    kept list is the check that this did not reach past its own records.
    """
    from thalamus.substrate.scan_retirement import plan, retire

    graph = connect(args.url)
    try:
        retirement = plan(graph)

        if not retirement.total():
            print("Nothing to retire — no scan Source or scanner Claim in the graph.")
            return

        print(f"{len(retirement.sources)} scan Source(s):")
        for doomed in retirement.sources:
            print(f"  {doomed.detail}")
        print(f"\n{len(retirement.claims)} scanner Claim(s):")
        for doomed in retirement.claims:
            print(f"  {doomed.detail}")

        if retirement.artifacts:
            print(f"\n{len(retirement.artifacts)} Artifact(s) left with no other edge:")
            for doomed in retirement.artifacts:
                print(f"  {doomed.detail}")
        if retirement.kept_artifacts:
            print(f"\n{len(retirement.kept_artifacts)} Artifact(s) kept — still referenced:")
            for identifier, survivors in retirement.kept_artifacts[:12]:
                print(f"  {survivors:3d} other edge(s)  {identifier}")
            if len(retirement.kept_artifacts) > 12:
                print(f"  … and {len(retirement.kept_artifacts) - 12} more")

        if retirement.uncited_blobs:
            print(
                f"\n{len(retirement.uncited_blobs)} archived blob(s) become uncited. "
                "Bytes are kept; `thalamus arch growth` ranks unreferenced stock."
            )

        if not args.write:
            print(f"\nDry run. Re-run with --write to remove {retirement.total()} vertices.")
            return

        removed = retire(graph, retirement)
        print(f"\nRemoved {removed} vertices.")
        _persist(graph)
        print("Run `thalamus contract check` to confirm the graph is still whole.")
    finally:
        close_connection(graph)


def _cmd_repair_claim_addresses(args):
    """Move Claims back to the address their own `(kind, description)` produces.

    Dry-run by default, and it prints the collapsing edges separately from the moving
    ones: a collapse is the case where a trace already reached the destination, so the
    move merges two edges into one and a reported fan-out drops by one. That is a
    number the eval loop has published, and a migration that folded it into a total
    could not be checked for it.
    """
    from thalamus.substrate.claim_address_repair import plan, write_repairs

    graph = connect(args.url)
    try:
        repair = plan(graph)

        if not repair.total():
            print(
                f"Every one of {repair.examined} Claims sits at the address its own "
                "(kind, description) produces."
            )
            return

        print(
            f"{repair.examined} Claims examined, {repair.total()} at an address their "
            "own content does not produce.\n"
        )

        if repair.rewires:
            print(f"{len(repair.rewires)} stale duplicate(s) — edges move to the twin, "
                  "then the vertex is dropped:")
            for rewire in repair.rewires:
                print(f"\n  {rewire.stale}  [{rewire.kind}]")
                print(f"    twin  {rewire.twin}")
                for edge in rewire.edges:
                    print(f"    {edge.describe()}")
                print(f"    {rewire.description[:110]!r}")

        if repair.remints:
            print(f"\n{len(repair.remints)} wrong address(es) with no twin — re-minted "
                  "at the correct id, edges moved, old vertex dropped:")
            for remint in repair.remints:
                print(f"\n  {remint.old}  [{remint.kind}]")
                print(f"    ->    {remint.new}")
                for edge in remint.edges:
                    print(f"    {edge.describe()}")
                print(f"    {remint.description[:110]!r}")

        collapses = repair.collapses()
        if collapses:
            print(
                f"\n{collapses} edge(s) collapse: the far endpoint already holds the "
                "same edge to the destination, so the pair merges and that trace's "
                "fan-out drops by one. It counted one claim twice under two ids."
            )

        if not args.write:
            print(f"\nDry run. Re-run with --write to move {repair.total()} vertices.")
            return

        rewired, reminted, moved = write_repairs(graph, repair)
        print(f"\nRewired and dropped {rewired}, re-minted {reminted}, moved {moved} edges.")
        _persist(graph)
        print("Run `thalamus contract check` to confirm the addresses now agree.")
    finally:
        close_connection(graph)


def _cmd_repair_projects(args):
    """Re-anchor project values that named a working directory rather than a checkout.

    Dry-run by default and loud about what it will not touch: the vertices it leaves
    alone are the ones whose value it could not disprove, and a migration that reports
    only its changes cannot be checked for having been too eager.
    """
    from thalamus.substrate.project_repair import plan, write_repairs

    graph = connect(args.url)
    try:
        repair = plan(graph)

        print(f"{len(repair.changes)} vertices to re-anchor  {repair.by_label()}")
        moves: dict[tuple[str, str], int] = {}
        for change in repair.changes:
            key = (change.before, change.after)
            moves[key] = moves.get(key, 0) + 1
        for (before, after), count in sorted(moves.items(), key=lambda kv: -kv[1]):
            print(f"  {count:4d}  {before or '(empty)'!r:44} -> {after or '(empty)'!r}")

        if repair.left_alone:
            kept: dict[str, int] = {}
            for _vid, _label, value in repair.left_alone:
                kept[value] = kept.get(value, 0) + 1
            print(f"\n{len(repair.left_alone)} left alone — not disproved:")
            for value, count in sorted(kept.items(), key=lambda kv: -kv[1])[:12]:
                print(f"  {count:4d}  {value!r}")

        if repair.stamps:
            kinds: dict[str, int] = {}
            for _vid, kind in repair.stamps:
                kinds[kind.value] = kinds.get(kind.value, 0) + 1
            print(f"\n{len(repair.stamps)} already-correct sessions to stamp with "
                  f"their evidence: {kinds}")

        if not args.write:
            print("\nDry run. Re-run with --write to apply.")
            return
        moved = write_repairs(graph, repair)
        print(f"\nWrote {moved} vertices, stamped {len(repair.stamps)}.")
    finally:
        close_connection(graph)


def _cmd_audit_artifacts(args):
    """Report how far `Artifact` identity has drifted from one-vertex-per-file.

    `Artifact` is global so that two experts touching one file land on one vertex — it
    is the join key between scopes. Raw tool-call strings do not deliver that, and this
    says by how much, over the raw identifiers. Read-only, and measured there on
    purpose: the identifiers are never re-keyed, and the join is repaired beside them by
    the `(repo, path)` projection. Each split pair is reported with whether that
    projection reaches it, so the residue is separable from the historical total.
    """
    from thalamus.substrate.artifact_audit import audit_artifact_identity

    graph = connect(args.url)
    try:
        audit = audit_artifact_identity(graph)

        print(f"Artifact vertices: {audit.total}")
        print(f"  absolute paths duplicating a relative sibling: {len(audit.split_pairs)}")
        print(f"  touch edges stranded on those duplicates:      {audit.stranded_touches}")
        print(f"  relative paths claimed by >1 project:          {len(audit.collisions)}")
        print(
            f"\njoined by the (repo, path) projection: {len(audit.joined_pairs)} of "
            f"{len(audit.split_pairs)} pairs, {audit.rejoined_touches} of "
            f"{audit.stranded_touches} touches"
        )

        if audit.residue:
            print(f"\nmost-stranded duplicates the projection cannot reach "
                  f"({len(audit.residue)} remain):")
            for pair in sorted(audit.residue, key=lambda pair: -pair.touches)[:10]:
                print(f"  {pair.touches:4d} touches  {pair.relative}")

        if audit.collisions:
            print("\npaths claimed by more than one project:")
            for path, owners in sorted(audit.collisions.items())[:10]:
                print(f"  {path}  <- {sorted(owners)}")

        print("\nproject values in use:")
        for project, count in audit.projects.items():
            print(f"  {count:5d}  {project}")
        print(
            "\nRead-only, and measured over the raw identifiers, which are never "
            "re-keyed.\nThe residue is what a fresh `thalamus derive-artifact-paths` "
            "cannot anchor: one of\nits spellings sits in no proven checkout."
        )
    finally:
        close_connection(graph)


def _cmd_backfill_chunks(args):
    """Co-index documents that were ingested before chunks existed.

    Needs no model: a chunk is a slice of retained bytes, and the entity vocabulary it
    tags itself with is already in the graph. So this is a rebuild, not a re-extraction
    — which is the property that makes chunk geometry a dial rather than a commitment.
    Claims, entities and Sources are left exactly as they are.
    """
    from pathlib import Path

    from gremlin_python.process.graph_traversal import __
    from gremlin_python.process.traversal import Merge, T

    from thalamus.contract.ontology import vid
    from thalamus.harness import ingest as ingest_mod
    from thalamus.harness.ingest import anchor_citations, build_chunks
    from thalamus.substrate.schema import Entity, Provenance, Tier
    from thalamus.substrate.writer import _ensure_edge, _iterate, _provenance_properties

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
                text = ingest_mod.to_text(hits[0].read_bytes())
            except Exception as exc:  # a PDF or unreadable payload — say so, skip it
                print(f"  skip {row['title'][:50]}: {exc}", file=sys.stderr)
                continue

            scope = row["scope"]
            # The claim's vertex ID travels with its citation — without it the anchor
            # can be computed and printed but never written, which is the whole point
            # of the edge. (It was, in the first run of this command.)
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

            class _Cited:
                def __init__(self, citation):
                    self.citation = citation

            cited = [_Cited(str(c.get("citation") or "")) for c in claims]
            chunks = build_chunks(text, cited, entity_names)
            anchored = anchor_citations(chunks, cited)
            planned += len(chunks)
            print(f"  {row['title'][:52]:<54} {len(chunks):>4} chunks  "
                  f"{len(anchored)}/{len(cited)} anchored  [{scope}]")

            if not args.write:
                continue

            entity_vids = {
                name: vid("Entity", Entity(name=name).slug(), scope) for name in entity_names
            }
            previous = ""
            for chunk in chunks:
                chunk_vid = vid("Chunk", chunk.local_id(row["hash"]), scope)
                properties = {
                    "text": chunk.text, "ordinal": chunk.ordinal,
                    "start": chunk.start, "end": chunk.end, "scope": scope,
                    **_provenance_properties(
                        Provenance(tier=Tier.CURATED, source=str(row["uri"] or ""))
                    ),
                }
                _iterate(
                    graph.merge_v({T.id: chunk_vid, T.label: "Chunk"})
                    .option(Merge.on_create, {T.id: chunk_vid, **properties})
                    .option(Merge.on_match, properties),
                    "upsert Chunk", chunk_vid,
                )
                _ensure_edge(graph, chunk_vid, row["vid"], "DERIVED_FROM")
                if previous:
                    _ensure_edge(graph, previous, chunk_vid, "ADJACENT_IN_TEXT")
                previous = chunk_vid
                for name in chunk.about:
                    if name in entity_vids:
                        _ensure_edge(graph, chunk_vid, entity_vids[name], "ABOUT")

            # The anchor edges, written last because they need every chunk to exist.
            ordinal_vids = {
                c.ordinal: vid("Chunk", c.local_id(row["hash"]), scope) for c in chunks
            }
            for claim_index, ordinal in anchored.items():
                if ordinal in ordinal_vids:
                    _ensure_edge(
                        graph, str(claims[claim_index]["vid"]),
                        ordinal_vids[ordinal], "ANCHORS",
                    )

        print(f"\n{len(rows)} article Sources: {planned:,} chunks "
              f"({skipped_existing} already chunked, {missing_bytes} missing bytes)")
        if args.write:
            _persist(graph)
            print("Written.")
        else:
            print("DRY RUN — nothing written. Re-run with --write to persist.")
    finally:
        close_connection(graph)


def _cmd_snapshot(args):
    from thalamus.substrate.snapshot import SnapshotError

    if args.list:
        rows = snapshots.registry()
        if not rows:
            print("No pinned snapshots. `thalamus snapshot --name <id>` pins one.")
            return
        for row in rows:
            ok = "ok" if snapshots.verify(row.name) else "HASH MISMATCH"
            print(
                f"{row.name:32} {row.taken_at[:19]}  {row.vertices:>6}V {row.edges:>6}E  "
                f"@{row.git_ref}  {ok}"
            )
            if row.note:
                print(f"{'':32} {row.note}")
        return

    if args.name:
        try:
            row = snapshots.take(args.name, note=args.note, url=args.url)
        except snapshots.SnapshotError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)
        print(
            f"Pinned `{row.name}`: {row.vertices} vertices, {row.edges} edges, "
            f"{row.byte_size / 1e6:.1f} MB, sha256 {row.sha256[:12]} @{row.git_ref}"
        )
        print(f"  registry: {snapshots.REGISTRY}")
        print(f"  serve it: thalamus snapshot --serve {row.name}")
        return

    if args.restore:
        try:
            row = snapshots.restore(
                args.restore, safety_pin=not args.no_safety_pin, url=args.url
            )
        except snapshots.SnapshotError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)
        print(
            f"Restored `{row.name}`: {row.vertices} vertices, {row.edges} edges, "
            f"sha256 {row.sha256[:12]} @{row.git_ref}"
        )
        if row.note:
            print(f"  {row.note}")
        return

    if args.serve:
        with snapshots.serve(args.serve, port=args.port) as url:
            row = snapshots.find(args.serve)
            print(f"Serving `{row.name}` ({row.vertices}V/{row.edges}E) at {url}")
            print("Read-only; the volume is mounted ro. Ctrl-C to stop.")
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                print("\nStopped.")
        return

    graph = connect(args.url)
    try:
        vertices = graph.V().count().next()
        edges = graph.E().count().next()
        snapshot(graph, args.path)
    except SnapshotError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    finally:
        close_connection(graph)
    print(f"Snapshot written: {args.path} ({vertices} vertices, {edges} edges)")


def _report_capabilities():
    """Re-ask the harness CLIs, and print the unchecked count beside the verdict.

    The count is not decoration. A checker that prints only "OK" reports a green
    light over an unknown denominator — if half the rows were unprobeable or the
    binary was missing, "no drift" and "nothing asked" are the same output. So the
    rows that could not be answered are always shown, including on a clean run.
    """
    from thalamus.contract.boundaries import check_boundaries
    from thalamus.contract.pinning import check_pinning
    from thalamus.contract.probes import check_capabilities
    from thalamus.contract.rooms import check_rooms

    # Two kinds of declaration, one report. A flag row says what a CLI accepts; a
    # boundary row says what actually binds on a harness — and the second is the one
    # that was wrong while the first was clean, because a derivation over our own
    # tables never asks a harness anything.
    rows = [(r.label, r.outcome.value, r.detail) for r in check_capabilities()]
    rows += [(f"{row.label} [{row.state.value}]", outcome, detail)
             for row, outcome, detail in check_boundaries()]
    rows += [(f"{row.label} [{row.state.value}]", outcome, detail)
             for row, outcome, detail in check_pinning()]
    # A third subject: what a dispatcher can establish about a member before writing to
    # it. Kept out of the pinning rows because a pinned session and an addressable room
    # member are different claims, and the record that carried both reported one wrongly.
    rows += [(f"{row.label} [{row.state.value}]", outcome, detail)
             for row, outcome, detail in check_rooms()]

    drift = [r for r in rows if r[1] == "drift"]
    malformed = [r for r in rows if r[1] == "malformed"]
    unchecked = [r for r in rows if r[1] in ("unprobeable", "unavailable")]

    for label, outcome, detail in rows:
        mark = {"confirmed": "✓", "drift": "✗", "malformed": "✗"}.get(outcome, "?")
        suffix = f" — {detail}" if detail else ""
        print(f"  {mark} {label} [{outcome}]{suffix}")

    print(f"\nProbed {len(rows)} declaration(s): {len(rows) - len(drift) - len(malformed) - len(unchecked)} "
          f"confirmed, {len(drift)} drifted, {len(malformed)} malformed, "
          f"{len(unchecked)} unchecked.")
    if drift or malformed:
        print("\nA declaration no longer matches what answers it — the CLI's parser, "
              "or the wiring a boundary claims to bind through.", file=sys.stderr)
        sys.exit(1)
    if unchecked:
        print("Every declaration that could be asked still holds. "
              "The unchecked rows are not evidence of anything.")
        return
    print("Capability declarations OK — every one re-asked and confirmed.")


def _report_roster_boundaries():
    """Print what actually binds each scope, resolved rather than as declared.

    The capability boundary is stored once and inherited, which is what keeps six
    manifests from drifting — and it is also what makes it invisible, since the
    scope it binds says nothing about it. Printing the resolved policy is what stops
    a single-source default from being worse than the copies it replaced. Inherited
    rows are marked, so "this scope was never bounded" and "this scope inherited the
    roster's bound" cannot read the same.
    """
    from thalamus.contract.manifest import available_scopes, load_manifest

    for scope in available_scopes():
        manifest = load_manifest(scope)
        capability = manifest.effective_capability_boundary
        origin = "declared" if manifest.capability_boundary is not None else "inherited"
        print(f"\n  {scope}")
        writes = manifest.write_boundary.deny_globs
        print(f"    writes     denied: {', '.join(writes) if writes else '(nothing)'}")
        write_exceptions = manifest.write_boundary.allow_globs
        if write_exceptions:
            print(f"      ...except: {', '.join(write_exceptions)}")
        tools = capability.deny_tools
        skills = capability.deny_skills
        allowed = capability.allow_tools
        print(f"    tools      denied [{origin}]: {', '.join(tools) if tools else '(nothing)'}")
        if allowed:
            print(f"      ...except [{origin}]: {', '.join(allowed)}")
        print(f"    skills     denied [{origin}]: {', '.join(skills) if skills else '(nothing)'}")

    print("\nBoundaries are enforced by the role-guard PreToolUse hook, which binds "
          "the file-editing tools, `Skill`, `Artifact`, and `mcp__penpot__*`. Bash "
          "and `Read` on a SKILL.md are named misses (role-guard.sh). Which of these "
          "binds on which harness is a separate question with a separate record: "
          "`thalamus contract check --capabilities`.")


def _cmd_arch(args, arch_parser):
    """The architect's instrument. Reads code; writes a model file and findings."""
    command = getattr(args, "arch_command", None)
    if command not in {"scan", "show", "diff", "rules", "growth", "dead", "refs"}:
        arch_parser.print_help()
        sys.exit(1)

    import dataclasses
    import subprocess
    import tempfile
    from pathlib import Path

    from thalamus.arch import findings as arch_findings
    from thalamus.arch import model as arch_model
    from thalamus.arch import routes as arch_routes
    from thalamus.arch.extractor import scan_repo
    from thalamus.arch.metrics import measure

    def _scan(target):
        """One scan under both declared channels.

        Every subcommand goes through this, `diff` included: measuring one side with the
        route channel on and the other with it off would compare two extractors, which
        is the error the policy digest exists to make impossible.
        """
        extracted = arch_routes.extract_routes(target, model.routes)
        return arch_routes.merge(scan_repo(target, policy), extracted), extracted

    # The repository, not the cwd. `arch/model.yaml` is a file in a checkout, and
    # resolving it against wherever the operator is standing made `thalamus arch` a
    # command that reported an empty model — no layers, no rules, every module
    # unplaced — from any directory but the repo root.
    repo = Path(args.repo).resolve() if args.repo else arch_model.REPO_ROOT
    model = arch_model.load(repo / arch_model.MODEL_PATH)
    policy = model.policy
    if getattr(args, "import_depth", ""):
        policy = dataclasses.replace(policy, import_depth=args.import_depth)

    if command == "show":
        _arch_show(repo, model)
        return

    if command == "growth":
        _arch_growth(args, repo)
        return

    graph, route_graph = _scan(repo)
    metrics = measure(graph)

    if command == "rules":
        _arch_rules(model, graph, gate=getattr(args, "gate", False))
        return

    if command == "dead":
        _arch_dead(args, repo, graph)
        return

    if command == "refs":
        _arch_refs(args, repo)
        return

    if command == "diff":
        with tempfile.TemporaryDirectory(prefix="thalamus-arch-") as tmp:
            checkout = Path(tmp) / "tree"
            result = subprocess.run(
                ["git", "-C", str(repo), "worktree", "add", "--detach", str(checkout), args.against],
                capture_output=True, text=True, check=False,
            )
            if result.returncode != 0:
                print(f"Cannot check out {args.against}: {result.stderr.strip()}", file=sys.stderr)
                sys.exit(1)
            try:
                # Both sides are recomputed under one policy. Reading the stored number
                # off the other commit's model file would compare a measurement against
                # a report, which is the mistake `diff` exists to prevent.
                other = measure(_scan(checkout)[0])
            finally:
                subprocess.run(
                    ["git", "-C", str(repo), "worktree", "remove", "--force", str(checkout)],
                    capture_output=True, text=True, check=False,
                )
        _arch_diff(args.against, other, metrics)
        return

    # scan
    text, derived, metrics = arch_model.build(repo, graph, model)
    dirty = arch_model.dirty_paths(repo, policy)
    found = arch_findings.findings(graph, metrics, model) + arch_findings.route_findings(
        route_graph
    )

    print(f"Scan {derived['scan']}")
    print(f"  policy      import_depth={policy.import_depth} resolve={policy.resolve} "
          f"digest={policy.digest()[:7]}")
    if model.routes.enabled:
        print(f"  routes      {len(route_graph.called())} called, "
              f"{len(route_graph.defined())} defined, match={model.routes.match} "
              f"digest={model.routes.digest()[:7]}")
    print(f"  modules     {metrics.modules}")
    print(f"  edges       {metrics.dependencies} counted of {len(graph.edges)} recorded")
    print(f"  propagation {metrics.propagation_cost * 100:.2f}%")
    print(f"  cycles      {len(metrics.cycles)} ({metrics.modules_in_cycles} modules)")
    for cycle in metrics.cycles:
        print(f"                {' <-> '.join(cycle)}")
    print(f"  findings    {len(found)}")
    for finding in found:
        print(f"                {finding.description}")

    # The growth headline rides along because the series costs nothing to read — every
    # vertex already carries `ingested_at`. Best-effort: a scan is a local operation and
    # must not start failing because the graph server is down.
    try:
        from thalamus.arch import growth as arch_growth
        from thalamus.substrate.writer import close_connection, connect

        graph_connection = connect(args.url)
        try:
            rate = arch_growth.headline(graph_connection)
        finally:
            close_connection(graph_connection)
        if rate is not None:
            for line in rate.lines():
                print(f"  {line}")
    except Exception:
        print("  growth      graph unreachable — run `thalamus arch growth` for the series")

    if dirty:
        # The walk read the working tree; the scan id names HEAD. With a dirty tree
        # those are different codebases, and the model file would record a measurement
        # of a commit that never contained it — the one falsehood git cannot correct
        # later, because the file will be committed alongside the code it misdescribes.
        print(f"\n{len(dirty)} uncommitted file(s) under the scanned roots:")
        for path in dirty[:10]:
            print(f"  {path}")
        if len(dirty) > 10:
            print(f"  … and {len(dirty) - 10} more")

    if getattr(args, "check", False):
        # The staleness gate. The committed model is a measurement of a tree; once the
        # code moves past it, `arch show` reports numbers for a tree that no longer
        # exists and nothing says so.
        #
        # It compares the *measurement* and not the whole file, because `scan` and
        # `commit` name the tree that was measured and necessarily lag by one: writing
        # the model and committing it moves HEAD, so a fresh scan's stamp can never
        # equal the stamp inside the file that commit created. Comparing the text would
        # make this gate impossible to satisfy rather than merely hard.
        model_path = repo / arch_model.MODEL_PATH
        committed = arch_model.load(model_path).derived if model_path.exists() else {}
        measured = {k: v for k, v in derived.items() if k not in ("scan", "commit")}
        stored = {k: v for k, v in committed.items() if k not in ("scan", "commit")}
        if stored == measured:
            print("\nModel file matches a fresh scan.")
            return
        drifted = sorted(
            key for key in set(stored) | set(measured) if stored.get(key) != measured.get(key)
        )
        print(
            f"\nStale: `arch/model.yaml` no longer matches a fresh scan — "
            f"{', '.join(drifted) or 'no measured key'} differ(s). Run "
            "`thalamus arch scan --write` and commit the result.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.write:
        print("\nDry run. Re-run with --write to regenerate the model file.")
        return

    if dirty:
        print(
            "\nRefusing to write: the scan id names a commit the working tree does not "
            "match. Commit or stash the files above, then re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    model_path = repo / arch_model.MODEL_PATH
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(text, encoding="utf-8")
    print(f"\nWrote {model_path.relative_to(repo)}")
    print("Commit it — the file is the record, and git is what dates it to this tree.")


def _arch_growth(args, repo) -> None:
    """Stock first, then rate. Reads only — nothing here writes to the graph.

    The order is the finding: a trend statistic scores a flat 894MB as the healthiest
    surface on the box, so what nothing refers to is reported before how fast anything
    is growing.
    """
    from thalamus.arch import growth as arch_growth
    from thalamus.substrate.writer import close_connection, connect

    graph = connect(args.url)
    try:
        audit = arch_growth.stock_audit(graph, repo)
        print(f"Unreferenced stock — {arch_growth.human_bytes(audit.total_bytes)} total")
        if not audit.orphans:
            print("  nothing on disk is unreferenced")
        for orphan in audit.ranked():
            print(f"  {arch_growth.human_bytes(orphan.bytes):>8}  [{orphan.kind}] {orphan.path}")
            print(f"            {orphan.note}")

        print()
        found = arch_growth.headline(graph)
        if found is None:
            print("growth      no series yet — the graph holds fewer than two dated days")
            return
        for line in found.lines():
            print(line)
        print(
            "            rates are Sen's slope (median of pairwise slopes); whether the "
            "difference is real is eval-methodology's question, not this one"
        )
    finally:
        close_connection(graph)


def _arch_show(repo, model) -> None:
    """Print the authored half and what the last scan measured."""
    print(f"repo         {model.repo or '(unset)'}")
    print(f"root_commit  {model.root_commit or '(unset)'}")
    print(f"policy       import_depth={model.policy.import_depth} "
          f"resolve={model.policy.resolve} roots={list(model.policy.roots)} "
          f"digest={model.policy.digest()[:7]}")
    print(f"layers       {len(model.layers)}")
    for layer in model.layers:
        print(f"               {layer.name}: {', '.join(layer.includes) or '(nothing)'}")
    print(f"rules        {len(model.rules)}")
    for rule in model.rules:
        print(f"               {rule.layer} -> {', '.join(rule.may_depend_on) or '(nothing)'}")
    print(f"seams        {len(model.seams)}")
    print(f"rejected     {len(model.rejected_refactors)} recorded refactor(s)")
    if model.derived:
        metrics = model.derived.get("metrics", {})
        print(f"last scan    {model.derived.get('scan', '(none)')}")
        print(f"               {metrics.get('modules', '?')} modules, "
              f"{metrics.get('dependencies', '?')} dependencies, "
              f"propagation {metrics.get('propagation_cost', '?')}%")
    else:
        print("last scan    (never scanned)")


def _arch_rules(model, graph, gate: bool = False) -> None:
    """Check the measured edges against the declared rules.

    The report is the same either way: every violation prints, accepted or not, because
    an architect reading this wants the design's real shape and not the subset that is
    still news. `--gate` adds a verdict on top of that report rather than filtering it.
    """
    if not model.layers:
        print(
            f"No layers declared, so the partition places none of {len(graph.modules)} "
            "scanned modules. Declaring them is the architect's work — an empty "
            "partition reports nothing rather than passing."
        )
        if gate:
            sys.exit(1)
        return
    unplaced = model.unplaced(graph)
    violations = model.violations(graph)
    result = model.gate(graph)
    accepted_keys = {entry.key for entry in result.accepted_hits}

    def mark(key) -> str:
        return "accepted " if key in accepted_keys else "NEW      "

    print(f"{len(graph.modules)} modules, {len(unplaced)} unplaced by the declared partition")
    for module in unplaced[:20]:
        print(f"  {mark((module, ''))} unplaced  {module}")
    print(f"{len(violations)} rule violation(s), {len(result.accepted_hits)} accepted")
    for violation in violations:
        print(f"  {mark((violation.from_path, violation.to_path))} {violation.describe()}")
    for entry in result.stale:
        print(f"  STALE     accepted and no longer measured: {entry.describe()}")
    if not unplaced and not violations:
        print("The declared model and the measured graph agree.")

    if not gate:
        return
    code = result.exit_code
    if code == 1:
        print(
            f"\nGate: {len(result.new_violations)} violation(s) and "
            f"{len(result.new_unplaced)} unplaced module(s) the model does not accept. "
            "Fix the edge, or declare it in `accepted` with the reason it stands.",
            file=sys.stderr,
        )
    elif code == 2:
        print(
            f"\nGate: {len(result.stale)} `accepted` entry/entries no longer happen. "
            "Delete them — an exception that has stopped firing describes a design that "
            "moved.",
            file=sys.stderr,
        )
    sys.exit(code)


def _dead_policy(repo):
    """The declared census policy, read straight off the model file.

    Read here rather than hung off `ArchModel` because `deadends` imports `findings`,
    which imports `model` — putting the policy on the model would close that into a
    cycle. `regenerate` preserves the authored half byte for byte, so a hand-declared
    block survives every scan.
    """
    from thalamus.arch import model as arch_model
    from thalamus.arch.deadends import DeadEndPolicy

    path = repo / arch_model.MODEL_PATH
    document = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    return DeadEndPolicy.from_block((document or {}).get("deadends") or {})


def _refs_policy(repo):
    """The declared reference policy, read straight off the model file.

    Read here rather than hung off `ArchModel` for the reason `_dead_policy` is:
    `references` imports `findings`, which imports `model`, so putting the policy on
    the model would close that into a cycle.
    """
    from thalamus.arch import model as arch_model
    from thalamus.arch.references import ReferencePolicy

    path = repo / arch_model.MODEL_PATH
    document = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    return ReferencePolicy.from_block((document or {}).get("references") or {})


def _arch_refs(args, repo) -> None:
    """Report references in comment prose that the tree no longer resolves.

    No `--gate`, deliberately, and the absence is the design rather than an oversight:
    this channel's precision has not been measured, and an unmeasured checker that
    acts leaves no record of the calls it got wrong.
    """
    from thalamus.arch import references as arch_references

    policy = _refs_policy(repo)
    if not policy.enabled:
        print(
            "The reference channel is off. Enable it in `arch/model.yaml` under "
            "`references: enabled: true` — a census nobody declared is a census "
            "nobody can read the exceptions of."
        )
        return

    print(arch_references.render(arch_references.census(repo, policy), limits=args.limits))


def _arch_dead(args, repo, graph) -> None:
    """Report definitions nothing outside the test roots refers to.

    The report states what was measured and never that a symbol is unused: the census
    resolves identifiers, and `--limits` lists every mechanism that could hide a caller
    from it. `--gate` adds a verdict without narrowing that report.
    """
    from thalamus.arch import deadends as arch_deadends

    policy = _dead_policy(repo)
    if not policy.enabled:
        print(
            "The dead-end channel is off. Enable it in `arch/model.yaml` under "
            "`deadends: enabled: true` — a census nobody declared is a census nobody "
            "can read the exceptions of."
        )
        return

    report = arch_deadends.scan(repo, graph, policy)
    matched = {
        (e.definition.path, e.definition.qualname)
        for e in report.exempted
        if e.rule == arch_deadends.RULE_DECLARED
    }

    # Reported through `deadend_findings` rather than off the report's lists directly:
    # the finding is where the hedging lives. "No reference outside the test roots was
    # found" is refutable by pointing at one; "unused" is a verdict a static census is
    # not entitled to, given what `limits` says it cannot see.
    for finding in arch_deadends.deadend_findings(report):
        print(f"  {finding.description}")
    print(
        f"{len(report.test_only)} test-only, {len(report.orphans)} orphan module(s), "
        f"{len(report.exempted)} exempted, {len(report.silenced)} reached only from a "
        f"non-Python caller"
    )
    for entry in report.silenced:
        print(f"  reached    {entry.describe()}")

    stale = [entry for entry in policy.exemptions if (entry.path, entry.symbol) not in matched]
    for entry in stale:
        print(f"  STALE      exemption matches nothing: {entry.path} {entry.symbol}")

    if args.limits or not (report.test_only or report.orphans):
        print(f"{len(report.limits)} stated limit(s) on the census's reach")
        for limit in report.limits:
            print(f"  limit      {limit}")

    if not report.test_only and not report.orphans and not stale:
        print("Every definition under the source roots is referenced outside the tests.")

    if not args.gate:
        return
    if report.test_only or report.orphans:
        print(
            f"\nGate: {len(report.test_only) + len(report.orphans)} finding(s) the model "
            "does not exempt. Wire the definition to a caller, delete it, or add an "
            "`exemptions` entry under `deadends` with the reason it stands.",
            file=sys.stderr,
        )
        sys.exit(1)
    if stale:
        print(
            f"\nGate: {len(stale)} exemption(s) match nothing. Delete them — an "
            "exemption for a symbol that is now referenced, or gone, describes a tree "
            "that moved.",
            file=sys.stderr,
        )
        sys.exit(2)


def _arch_diff(against: str, other, current) -> None:
    """Report both sides recomputed, never a stored number against a fresh one."""
    print(f"{'':13} {against[:12]:>12}  {'working tree':>12}")
    print(f"{'modules':13} {other.modules:>12}  {current.modules:>12}")
    print(f"{'dependencies':13} {other.dependencies:>12}  {current.dependencies:>12}")
    print(f"{'propagation':13} {other.propagation_cost * 100:>11.2f}%  "
          f"{current.propagation_cost * 100:>11.2f}%")
    print(f"{'cycles':13} {len(other.cycles):>12}  {len(current.cycles):>12}")

    gone = set(other.cycles) - set(current.cycles)
    fresh = set(current.cycles) - set(other.cycles)
    for cycle in sorted(fresh):
        print(f"  new cycle      {' <-> '.join(cycle)}")
    for cycle in sorted(gone):
        print(f"  cycle resolved {' <-> '.join(cycle)}")


def _collapse_advisories(issues: list[str]) -> list[str]:
    """One line per *shape* of advisory, with the count and one example.

    An advisory that fires per-vertex fires thousands of times on a graph this size,
    and a wall of near-identical lines is how a reporting-only check earns the habit
    of being scrolled past. The shape is the message with its backticked vertex IDs
    blanked, which is exactly the part that varies.
    """
    shapes: dict[str, list[str]] = {}
    for issue in issues:
        shapes.setdefault(re.sub(r"`[^`]*`", "``", str(issue)), []).append(str(issue))

    lines = []
    for members in shapes.values():
        if len(members) == 1:
            lines.append(members[0])
        else:
            ids = re.findall(r"`([^`]*)`", members[0])
            example = f" (e.g. {ids[0]})" if ids else ""
            lines.append(f"{re.sub(r'`[^`]*`', '…', members[0])} — ×{len(members)}{example}")
    return lines


def _cmd_contract(args, contract_parser):
    if getattr(args, "contract_command", None) != "check":
        contract_parser.print_help()
        sys.exit(1)

    # Short-circuit before `connect`: the capability check asks CLIs, not the graph,
    # and a checker that needs a running graph to verify a command-line flag would be
    # unrunnable in exactly the situation it is for — a fresh box being wired up.
    if getattr(args, "capabilities", False):
        _report_capabilities()
        return

    if getattr(args, "roster", False):
        _report_roster_boundaries()
        return

    from thalamus.contract.conformance import ADVISORY, check_graph, severity_of

    graph = connect(args.url)
    try:
        issues, counts = check_graph(graph)
    finally:
        close_connection(graph)

    print(f"Audited {counts['vertices']} vertices, {counts['edges']} edges.")

    # Severity is what lets a rule land at all. An audit that exits 1 on every finding
    # can only ever carry rules that are already satisfied, so the ones worth adding —
    # anything that fires on historical data nobody can go back and fix — could not be
    # written down. Advisories are printed to stdout beside the census, not to stderr
    # with the failures, because they are a count to explain and not a broken build.
    advisories = [i for i in issues if severity_of(i) == ADVISORY]
    violations = [i for i in issues if severity_of(i) != ADVISORY]

    if advisories:
        print(f"\n{len(advisories)} advisory — reported, does not fail the check:")
        for line in _collapse_advisories(advisories):
            print(f"  · {line}")

    if not violations:
        print("\nContract OK — every node carries provenance, every edge is legal, "
              "every Source resolves to retained bytes.")
        return
    print(f"\n{len(violations)} violation(s):", file=sys.stderr)
    for issue in violations:
        print(f"  - {issue}", file=sys.stderr)
    sys.exit(1)


def _cmd_eval(args, eval_parser):
    if getattr(args, "eval_command", None) == "sync":
        from thalamus.eval.sync import sync

        graph = connect(args.url)
        try:
            outcome = sync(graph, traces_base=args.traces, write=args.write)
            if args.write:
                _persist(graph)
        finally:
            close_connection(graph)
        print(outcome.summary())
        if not args.write:
            print("DRY RUN — nothing written to the graph. Re-run with --write to persist.")
    elif getattr(args, "eval_command", None) == "report":
        from thalamus.eval.report import scope_report

        graph = connect(args.url)
        try:
            print(
                scope_report(
                    graph,
                    scope=args.scope,
                    top=args.top,
                    since=args.since,
                    until=args.until,
                ).render()
            )
        finally:
            close_connection(graph)
    elif getattr(args, "eval_command", None) == "cost":
        from datetime import date, timedelta

        from thalamus.eval.cost import cost_report

        since = (
            date.fromisoformat(args.since) if args.since else date.today() - timedelta(days=14)
        )
        project_dir = (args.project_dir or Path.cwd()).resolve()
        if args.by_occasion:
            from thalamus.eval.cost import occasion_burn

            print(occasion_burn(since).render())
        else:
            print(cost_report(project_dir, since, traces_base=args.traces).render())
    elif getattr(args, "eval_command", None) == "gremlin":
        from thalamus.eval.gremlin import gremlin_report

        print(gremlin_report(traces_base=args.traces, guards_base=args.guards).render())
    elif getattr(args, "eval_command", None) == "recipes":
        from thalamus.eval.gremlin import render_smoke, render_staged, smoke_recipes, staged_recipes

        if args.staged:
            print(render_staged(staged_recipes()))
            return
        results = smoke_recipes(args.url)
        print(render_smoke(results))
        if any(not r.ok for r in results):
            sys.exit(1)
    elif getattr(args, "eval_command", None) == "profile":
        from thalamus.eval.profile import (
            profile_corpus,
            profile_query,
            profile_report,
            render_corpus,
            render_query_profile,
        )

        repeat = args.repeat if args.repeat is not None else PROFILE_REPEAT
        if args.query:
            print(render_query_profile(profile_query(args.url, args.query, repeat=repeat)))
        elif args.corpus:
            print(render_corpus(profile_corpus(args.url, repeat=repeat)))
        else:
            print(profile_report(base=args.profiles, top=args.top).render(top=args.top))
    elif getattr(args, "eval_command", None) == "withholding":
        from thalamus.eval.withholding import recurrence_report

        graph = connect(args.url)
        try:
            print(recurrence_report(
                graph, scope=args.scope, draws=args.draws).render())
        finally:
            close_connection(graph)
    elif getattr(args, "eval_command", None) == "conditioning":
        from thalamus.eval.conditioning import conditioning_report

        print(
            conditioning_report(
                conditioning_base=args.conditioning, traces_base=args.traces
            ).render()
        )
    elif getattr(args, "eval_command", None) == "pins":
        from thalamus.contract.manifest import available_scopes
        from thalamus.eval.cost import load_engaged, load_pins
        from thalamus.eval.pins import pin_report

        graph = connect(args.url)
        try:
            report = pin_report(
                graph, load_pins(args.pins_file), available_scopes(),
                engaged=load_engaged(args.pins_file),
            )
        finally:
            close_connection(graph)
        print(report.render())
    else:
        eval_parser.print_help()
        sys.exit(1)


def _known_claims(graph, scope: str, project: str, limit: int = 50) -> list[dict]:
    """Recent claims for the convergence feed: what wording already exists.

    Recency-bounded (last dozen sessions) and capped — the feed exists so the model
    can converge on wording it can see, not to replay the whole corpus into every
    prompt.
    """
    from gremlin_python.process.traversal import Order

    try:
        rows = (
            graph.V()
            .has_label("Session")
            .has("scope", scope)
            .has("project", project)
            .order()
            .by("timestamp", Order.desc)
            .limit(12)
            .out("CONTAINS")
            .has_label("Claim")
            .value_map("kind", "description")
            .to_list()
        )
    except Exception:
        return []

    claims: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        description = row.get("description", [""])[0]
        if not description or description in seen:
            continue
        seen.add(description)
        claims.append({"kind": row.get("kind", [""])[0], "description": description})
        if len(claims) >= limit:
            break
    return claims


def _cmd_init(args):
    from thalamus.harness.install import run

    if args.json and not args.check:
        print("`--json` is the shape of `--check`'s verification, so it only "
              "means anything with `--check`. Re-run as "
              "`thalamus init --check --json`.", file=sys.stderr)
        sys.exit(2)
    try:
        sys.exit(run(dry_run=args.dry_run, check_only=args.check, harness=args.harness,
                     uninstall_mode=args.uninstall, assume_yes=args.yes,
                     as_json=args.json))
    except RuntimeError as e:
        print(f"Init failed: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_status(args):
    from thalamus.harness.status import run

    sys.exit(run(args.url))


def _cmd_rescope(args):
    from thalamus.harness.rescope import run

    sys.exit(run(args.session, args.scope, reason=args.reason,
                 dry_run=args.dry_run, allow_distilled=args.allow_distilled,
                 other_session=args.other_session))


def _cmd_pin(args):
    from thalamus.contract.paths import PROJECT_ROOT
    from thalamus.harness.pin import launch

    try:
        launch(args.scope, PROJECT_ROOT, room=args.room, harness=args.harness)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"Pin failed: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_spawn(args):
    import subprocess

    from thalamus.contract.paths import PROJECT_ROOT
    from thalamus.harness.pin import spawn

    cwd = args.dir if args.dir is not None else PROJECT_ROOT
    try:
        spawn(args.scope, cwd, session=args.session, room=args.room,
              harness=args.harness)
    except (FileNotFoundError, ValueError, RuntimeError, subprocess.CalledProcessError) as e:
        print(f"Spawn failed: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_roster(args):
    from thalamus.contract.paths import PROJECT_ROOT
    from thalamus.harness.pin import WindowDied, roster

    try:
        roster(PROJECT_ROOT, full=getattr(args, "all", False), room=args.room)
    except (ValueError, RuntimeError) as e:
        print(f"Roster failed: {e}", file=sys.stderr)
        # A window whose command never execs prints nothing, so there is no epitaph
        # to quote and the cause is almost always the binary. The hint is all the
        # operator gets in that case, and it is the case that brought them here.
        if isinstance(e, WindowDied):
            # Every registered harness, not `claude`: the roster spawns whichever the
            # pin asked for, and naming one binary sends an operator whose codex or
            # Cursor window died to check a CLI that was never involved.
            binaries = ", ".join(
                f"`{agents.cli_for(h).binary} --version`" for h in agents.HARNESSES
            )
            print(f"Check that the harness binary is on your PATH — {binaries}.",
                  file=sys.stderr)
        sys.exit(1)


def _cmd_quick(args, parser):
    from thalamus.harness import pin

    if args.quick_command == "targets":
        rows = quick_mod.live_sessions()
        rows = [s for s in rows if args.all or s.scope]
        if not rows:
            print("No live sessions to fork. The quick tier needs a running expert; "
                  "`thalamus spawn <scope>` opens one.")
            return
        print(f"{'scope':16} {'session':10} {'status':9} {'age':>7}  cwd")
        for session in sorted(rows, key=lambda s: (s.scope, s.age_seconds)):
            age = f"{session.age_seconds / 60:.0f}m"
            # A session registers the moment it starts and files no transcript until
            # its first turn, so "live" and "forkable" are different questions.
            status = (
                session.status if quick_mod.has_conversation(session.session_id)
                else "no convo"
            )
            print(
                f"{session.scope or '(main)':16} {session.session_id[:8]:10} "
                f"{status:9} {age:>7}  {session.cwd}"
            )
        # Warmth is a cache and it decays inside the nominal TTL — 44.8% of the
        # parent's prefix survived at 38 minutes. The ages above are the
        # cost estimate; there is no second number to consult.
        print("\nCost is bimodal on the parent's recency, not its size: a fork of a "
              "just-active parent reads its whole prompt-cache prefix (~$0.03-0.08), "
              "a cold or mid-turn one pays $0.55-1.35.")
        return

    if args.quick_command == "delta":
        # stdout is the projects root and nothing else — session-end.sh substitutes
        # it straight into `extract --projects-dir`, so any commentary here would be
        # a path as far as the caller is concerned.
        try:
            root = quick_mod.stage_delta(args.transcript, args.parent)
        except (quick_mod.QuickRefused, OSError) as e:
            print(f"Delta staging failed: {e}", file=sys.stderr)
            sys.exit(1)
        print(root)
        return

    if args.quick_command != "ask":
        parser.parse_args(["quick", "--help"])
        return

    from_scope = args.from_scope or pin.resolve_pin()
    try:
        # A busy parent is the case this tier exists for. Non-interruption is why it
        # forks instead of messaging the expert, and the caller is blocked *now* — so
        # `--wait` is offered and never imposed. It costs the caller latency, which is
        # the endpoint the whole tier is justified on, to save the fork dollars.
        target = quick_mod.await_target(args.expert, wait=args.wait)
    except quick_mod.QuickRefused as e:
        print(f"Quick consultation refused: {e}", file=sys.stderr)
        sys.exit(1)
    if not target.between_turns:
        print(
            f"— forking `{args.expert}` mid-turn: ~13x the between-turns price, and "
            "the fork will not see the message its parent is still writing.",
            file=sys.stderr,
        )

    graph = connect(args.url)
    try:
        result = quick_mod.consult(
            graph, args.expert, args.question, from_scope,
            allowed_tools=args.allow, timeout=args.timeout,
        )
    except quick_mod.QuickRefused as e:
        print(f"Quick consultation refused: {e}", file=sys.stderr)
        close_connection(graph)
        sys.exit(1)
    _persist(graph)
    close_connection(graph)

    run = result.run
    print(f"## Quick exchange `{result.exchange_vid}`")
    print(f"**Expert:** {args.expert} (fork of {result.target.session_id[:8]}, "
          f"{result.target.status})")
    print(f"**Grant:** {result.grant}")
    print()
    print(result.answer.strip())
    print()
    if run is not None:
        print(
            f"— {run.wall_ms / 1000:.1f}s, ${run.cost_usd:.4f}, {run.num_turns} turn(s), "
            f"cache {run.cache_hit:.0%} hit "
            f"({run.cache_read_input_tokens:,} read / "
            f"{run.cache_creation_input_tokens:,} created), "
            f"{run.output_tokens:,} out"
        )
    # The tier's own invariant, counted from the fork's records rather than asserted:
    # without a fresh recall the answer is a decorated snapshot of context retrieved
    # for a different question.
    if result.fresh_recalls == 0:
        print("— WARNING: the fork made no in-ticket recall. Warmth was not "
              "revalidated; treat this answer as a cached opinion.")
    else:
        print(f"— {result.fresh_recalls} in-ticket recall(s)")
    for issue in result.ledger_issues:
        print(f"— LEDGER: {issue}")
    print(f"— {result.close_report}")
    if not result.accepted:
        sys.exit(1)


def _cmd_room(args, parser):
    from thalamus.harness import pin

    if args.room_command == "create":
        try:
            config = pin.ensure_room(args.room)
        except (ValueError, RuntimeError) as e:
            print(f"Room failed: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"Room `{args.room}` ready at {config}")
        return

    if args.room_command == "show":
        config = pin.room_config_dir(args.room)
        if not config.is_dir():
            print(f"No room `{args.room}` — `thalamus room create {args.room}` makes one.",
                  file=sys.stderr)
            sys.exit(1)
        print(f"Room `{args.room}` — {config}")
        sessions = sorted((config / "sessions").glob("*.json")) \
            if (config / "sessions").is_dir() else []
        print(f"  live members: {len(sessions)}")
        transcripts_dir = config / "projects"
        count = len(list(transcripts_dir.glob("*/*.jsonl"))) if transcripts_dir.is_dir() else 0
        print(f"  transcripts:  {count} (distilled from here, not ~/.claude/projects)")
        host = pin.host_config_dir()
        for name in pin.ROOM_LINKED:
            link = config / name
            if link.is_symlink():
                state = "→ " + str(link.readlink())
            elif not (host / name).exists():
                # Nothing to borrow. Reported plainly rather than as a fault: an
                # operator with no `commands/` should not be told a room is broken.
                state = f"— none at {host / name}"
            else:
                state = "MISSING" if not link.exists() else "not a link (stale copy)"
            print(f"  {name:22} {state}")
        copied = config / pin.ROOM_COPIED
        print(f"  {pin.ROOM_COPIED:22} {'copy' if copied.is_file() else 'MISSING'}")
        return

    if args.room_command == "list":
        names = pin.rooms()
        if not names:
            print("No rooms. `thalamus spawn <scope> --room <name>` opens one.")
            return
        for name in names:
            config = pin.room_config_dir(name)
            live = len(list((config / "sessions").glob("*.json"))) \
                if (config / "sessions").is_dir() else 0
            print(f"{name:20} {live} live member(s)   {config}")
        return

    parser.parse_args(["room", "--help"])


def _cmd_thread(args, parser):
    """Propose, approve, reject and audit thread closes.

    `propose` never touches the graph and `approve` writes the ledger row before the
    edge — so a crash between them leaves a visible, repairable gap rather than a close
    nobody can corroborate.
    """
    from thalamus.contract.ontology import vid
    from thalamus.substrate.writer import write_thread_close

    command = getattr(args, "thread_command", None)

    if command == "propose":
        row = closes_mod.propose(
            thread_id=args.thread_id,
            scope=args.scope,
            basis=args.basis,
            disposition=args.disposition,
            rationale=args.rationale,
            proposed_by=args.proposed_by or pin.resolve_pin(),
        )
        print(f"proposed {row['ref']}  {args.scope}:{args.thread_id}  ({args.disposition})")
        print("Nothing written to the graph. Approve with:")
        print(f"  thalamus thread approve {row['ref']}")
        return

    if command == "pending":
        rows = closes_mod.pending()
        if not rows:
            print("No proposals awaiting approval.")
            return
        for row in rows:
            print(f"{row['ref']}  {row['scope']}:{row['thread_id']}  [{row['disposition']}]")
            print(f"    basis: {row['basis']}")
            if row.get("rationale"):
                print(f"    why:   {row['rationale']}")
            print(f"    by {row.get('proposed_by') or '(unrecorded)'} at {row['ts']}")
        return

    if command == "reject":
        row = closes_mod.reject(args.ref, args.reason)
        print(f"rejected {row['ref']}  {row['scope']}:{row['thread_id']}")
        return

    if command == "approve":
        proposal = closes_mod.find_proposal(args.ref)
        if proposal is None:
            print(f"No proposal `{args.ref}` in the close ledger.", file=sys.stderr)
            sys.exit(1)
        # The evidence names what kind of corroboration exists, never that approval
        # happened — nothing here can establish the latter (harness/closes.py).
        evidence = args.evidence or {
            "cli": "cli:tty",
            "console": "console:unattributed",
            "session": "session:unattributed",
        }[args.surface]
        approval = closes_mod.approve(
            args.ref, surface=args.surface, approver_evidence=evidence
        )
        close = ThreadClose(
            thread_id=proposal["thread_id"],
            scope=proposal["scope"],
            disposition=CloseDisposition(proposal["disposition"]),
            basis=proposal["basis"],
            on_behalf_of=proposal.get("proposed_by") or None,
            surface=args.surface,
            approval_ref=args.ref,
            approver_evidence=evidence,
            closed_at=approval["ts"],
            notes=args.notes or proposal.get("rationale") or None,
        )
        graph = connect(args.url)
        try:
            agent_vid = write_thread_close(graph, close)
            _persist(graph)
        finally:
            close_connection(graph)
        print(f"closed {close.scope}:{close.thread_id} as {close.status.value}")
        print(f"  {agent_vid} -[RESOLVES {{basis: {close.basis}}}]-> "
              f"{vid('Thread', close.thread_id, close.scope)}")
        return

    if command == "audit":
        graph = connect(args.url)
        try:
            written = _agent_closes(graph)
        finally:
            close_connection(graph)
        approved = {row["ref"] for row in closes_mod.approvals()}
        unbacked = [c for c in written if c["approval_ref"] not in approved]
        print(f"{len(written)} agent-written close(s), {len(approved)} approval row(s).")
        if unbacked:
            print("\nCloses with no approval row — the ledger cannot corroborate these:")
            for close in unbacked:
                print(f"  {close['thread']}  approval_ref={close['approval_ref']}")
            sys.exit(1)
        print("Every agent-written close is backed by an approval row.")
        return

    parser.parse_args(["--help"])


def _agent_closes(graph) -> list[dict]:
    """Every `Agent -[RESOLVES]-> Thread` edge, as flat rows."""
    from gremlin_python.process.graph_traversal import __

    return [
        {
            "thread": str(row["thread"]),
            "approval_ref": str(row["approval_ref"]),
        }
        for row in graph.V()
        .has_label("Agent")
        .out_e("RESOLVES")
        .project("thread", "approval_ref")
        .by(__.in_v().id_())
        .by(__.coalesce(__.values("approval_ref"), __.constant("")))
        .to_list()
    ]


def _cmd_ceremony(args, parser):
    from thalamus.harness import ceremonies

    try:
        if args.ceremony_command == "start":
            row = ceremonies.start(
                args.room,
                args.kind,
                participant_scopes=args.scopes,
                deliverable_ids=args.deliverables,
                arm=args.arm,
                prereg_id=args.prereg,
            )
            # The id is printed alone on the last line so a caller can capture it
            # without parsing: every later row about this occasion is keyed on it,
            # including the session record item 8 puts it on.
            print(f"Occasion open — {row['ceremony_kind']} in `{row['room']}`, "
                  f"{len(row['participant_scopes'])} participant(s)")
            print(row["occasion_id"])
            return

        if args.ceremony_command == "end":
            row = ceremonies.end(args.occasion, outcome=args.outcome)
            print(f"Occasion {row['occasion_id']} closed at {row['ts_end']}")
            return

        if args.ceremony_command == "skip":
            row = ceremonies.skip(args.room, args.kind, reason=args.reason)
            print(f"Non-occurrence recorded — {row['occasion_id']}")
            return

        if args.ceremony_command == "mint":
            row = ceremonies.mint_deliverable(
                args.room, args.title, owner_scope=args.owner, occasion=args.occasion
            )
            print(f"Deliverable minted — {row['title']}")
            print(row["deliverable_id"])
            return

        if args.ceremony_command == "revise":
            row = ceremonies.record_revision(
                args.deliverable,
                artifact=args.artifact,
                occasion=args.occasion,
                author_scope=args.author,
            )
            print(f"Revision recorded on {row['deliverable_id']}")
            return

        if args.ceremony_command == "assign":
            row = ceremonies.record_assignment(
                args.room,
                args.kind,
                args.units,
                args.arms,
                args.counts,
                args.seed,
                prereg_id=args.prereg,
            )
            print(f"Assignment written for `{row['room']}` {row['ceremony_kind']} — "
                  f"seed {row['assignment_seed']}, procedure {row['procedure']}, "
                  f"{row['space']} possible assignment(s)")
            for unit, arm in sorted(row["assignment"].items()):
                print(f"  {unit:32} {arm}")
            if row["space"] > 0:
                # The floor is a property of the design and knowable now, which is the
                # only time it is still free to change.
                print(f"  smallest attainable p from this block alone: {1 / row['space']:.3f}")
            return

        if args.ceremony_command == "commit":
            row = ceremonies.commit(
                args.room,
                args.deliverable,
                args.text,
                owner_scope=args.owner,
                predicted_artifact=args.predicted,
                resolve_by=args.resolve_by,
                occasion=args.occasion,
            )
            print(f"Commitment recorded on {row['deliverable_id']}")
            if not row["predicted_artifact"] or not row["resolve_by"]:
                # Not refused: a forecast the room cannot yet make concrete is still
                # better recorded than dropped. But an unresolvable one is a sentence
                # about intent, and tooling cannot resolve what was never predicted.
                print("  warning: no predicted artifact or no horizon — nothing can "
                      "resolve this later", file=sys.stderr)
            return

        if args.ceremony_command == "resolve":
            row = ceremonies.resolve(
                args.deliverable,
                args.outcome,
                resolver=args.resolver,
                evidence=args.evidence,
                room=args.room,
                occasion=args.occasion,
            )
            print(f"{row['deliverable_id']} resolved {row['outcome']} "
                  f"by `{row['resolver']}` ({row['evidence']})")
            return

        if args.ceremony_command == "ack":
            row = ceremonies.acknowledge(args.finding, reason=args.reason)
            print(f"Acknowledged {row['finding']} — {row['reason']}")
            print("The ledger is unchanged; `ceremony audit --strict` still fails on it.")
            return

        if args.ceremony_command == "comparator":
            row = ceremonies.record_comparator(
                args.room, args.arm, args.reference, basis=args.basis
            )
            print(f"Comparator for `{row['room']}` — {row['arm']} arm, {row['reference']}")
            return
    except ValueError as e:
        print(f"Ceremony failed: {e}", file=sys.stderr)
        sys.exit(1)

    if args.ceremony_command == "show":
        print(ceremonies.render())
        return

    if args.ceremony_command == "outstanding":
        rows = ceremonies.outstanding()
        if not rows:
            print("No commitment is awaiting resolution.")
            return
        print(f"{len(rows)} commitment(s) awaiting resolution:")
        for row in rows:
            horizon = row.get("resolve_by") or "no horizon"
            print(f"  {row['deliverable_id']:32} by {horizon:12} "
                  f"{row.get('commitment_text', '')}")
        return

    if args.ceremony_command == "audit":
        report = ceremonies.audit()
        seen = {} if args.strict else ceremonies.load_acknowledged()
        print(report.note(seen))
        # The exit code reads acknowledgements; `clean()` never does. An acknowledged
        # finding is one the operator has read and accepted as permanent, not one the
        # ledger has stopped holding — `--strict` shows the undischarged truth.
        if report.unacknowledged(seen):
            sys.exit(1)
        return

    parser.parse_args(["ceremony", "--help"])


def _cmd_dispatch(args):
    from thalamus.harness import dispatch as dispatch_mod

    # Deliberately NOT defaulted to `resolve_pin()` here. `dispatch.authenticate`
    # establishes the sender from the calling process and refuses a member that names
    # another scope — and it can only tell an assertion from a default if the empty
    # case reaches it. Resolving a default at this layer made every caller look like
    # one that had asserted.
    slots = (args.task, args.eligibility, args.bid, args.expires)
    sender = args.sender

    try:
        sender, _ = dispatch_mod.authenticate(args.room, sender,
                                              operator=args.operator)
        if any(slots):
            if args.message:
                print(
                    "Pass a message or the four announcement slots, not both — a "
                    "message beside a formatted announcement is a second, unstructured "
                    "channel the eligibility slot cannot be read from.",
                    file=sys.stderr,
                )
                sys.exit(1)
            text = dispatch_mod.announcement(*slots, sender=sender)
        else:
            text = args.message

        result = dispatch_mod.dispatch(
            args.room,
            text,
            sender=sender,
            operator=args.operator,
            scopes=args.scopes,
            partial=args.partial,
            dry_run=args.dry_run,
            submit=not args.no_submit,
        )
    except dispatch_mod.DispatchRefused as e:
        print(f"Dispatch refused: {e}", file=sys.stderr)
        sys.exit(1)

    print(result.note())
    # A fan-out that reached nobody is not a successful no-op: the caller asked for
    # delivery and got none, and a zero exit would report the opposite.
    if not args.dry_run and not result.performed:
        sys.exit(1)




def _cmd_pulse(args):
    from thalamus.pulse.web import create_pulse_app

    print(f"Thalamus Pulse: http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    uvicorn.run(
        create_pulse_app(url=args.url),
        host=args.host,
        port=args.port,
        log_level="warning",
    )


def _cmd_console(args):
    import shutil
    import subprocess

    from thalamus.console.server import Config, PortInUse, serve
    from thalamus.harness import tmux
    from thalamus.contract.paths import PROJECT_ROOT

    if not shutil.which("tmux"):
        print("The console needs tmux — it drives the pinned roster's windows.",
              file=sys.stderr)
        sys.exit(1)

    cfg = Config(
        session=args.session,
        project_root=args.project_root or PROJECT_ROOT,
        favorites=args.dir,
        scan_roots=args.scan,
        services=args.service,
        frames_file=args.frames,
        fetch_interval_s=max(0.0, args.fetch_interval) * 60,
        allowed_origins=args.allow_origin,
    )
    if subprocess.run(tmux.argv("has-session", "-t", cfg.session),
                      capture_output=True).returncode != 0:
        # Serve anyway: the console showing an empty roster and a working spawn
        # button is a better answer than a refusal the operator reads on a phone.
        print(f"! no tmux session `{cfg.session}` yet — start one with `thalamus roster`, "
              "or use the console's ＋ button once it's up.")
    try:
        serve(cfg, host=args.host, port=args.port)
    except PortInUse as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)




def _load_file(path: Path) -> dict:
    text = path.read_text()
    if path.suffix in (".yaml", ".yml"):
        return yaml.safe_load(text)
    return json.loads(text)


if __name__ == "__main__":
    main()
