"""CLI for Thalamus operations."""

from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import socket
import sys
import time
import threading
import webbrowser
from pathlib import Path

import uvicorn
import yaml

from thalamus.substrate.schema import CloseDisposition, SessionGraph, ThreadClose
from thalamus.archive import archive_dir
from thalamus.console.server import DEFAULT_PORT as CONSOLE_PORT
from thalamus.contract.conformance import check_session
from thalamus.contract.ontology import MAIN_SCOPE
from thalamus.eval.rake_audit import SAMPLE_SIZE
from thalamus.eval import snapshots
from thalamus.harness import agents, cursor_transcripts, extraction, transcripts
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
from thalamus.viewer.web import create_app
from thalamus.substrate.snapshot import DEFAULT_SNAPSHOT_PATH, snapshot, snapshot_quietly
from thalamus.substrate.writer import DEFAULT_URL, close_connection, connect, write_session

ROOM_FLAG_HELP = (
    "Launch into this room — a private config dir (~/.thalamus/rooms/<room>/) that "
    "partitions peer discovery, so members see only each other. Created on first "
    "use. Default: $THALAMUS_ROOM, else no room."
)


def legibility_arms() -> tuple[str, ...]:
    """The arm names, read from the module that defines them rather than restated.

    Imported lazily like every other heavy import here, but at *parse* time rather than
    dispatch time, because argparse needs the choices to build `--help`.
    """
    from thalamus.eval.legibility import ARMS

    return ARMS


def main():
    parser = argparse.ArgumentParser(description="Thalamus — federated graph memory for coding agents")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Log Gremlin bytecode and server stack traces",
    )
    subparsers = parser.add_subparsers(dest="command")

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
        "Omit to list what is available. Ignored with --harness cursor, which is "
        "session-oriented and sweeps every discovered Cursor session.",
    )
    bootstrap_parser.add_argument(
        "--harness", choices=agents.HARNESSES, default="claude",
        help="Which harness wrote the transcripts (default: claude). `cursor` sweeps "
        "both discovery surfaces — the sessionEnd hook log and ~/.cursor/projects — "
        "so sessions predating the hooks are included.",
    )
    bootstrap_parser.add_argument(
        "--assign-scope", default="",
        help="Scope for Cursor sessions no hook ever saw, which therefore have no "
        "resolved scope. Without it they are listed and skipped rather than defaulted "
        "into `main`; scope is part of the vertex ID and cannot be walked back.",
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
        "Ignored with --harness cursor, which discovers sessions from the "
        "Cursor sessionEnd log instead.",
    )
    extract_parser.add_argument(
        "--harness", choices=agents.HARNESSES, default="claude",
        help="Which harness wrote the transcripts (default: claude). `cursor` sweeps "
        "~/.thalamus/logs/cursor-session-end.jsonl, including sessions logged before "
        "the adapter existed.",
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
        help="Scope for Cursor sessions found on disk that no hook ever saw, and which "
        "therefore have no resolved scope of their own. Without this they are listed "
        "and skipped rather than defaulted into `main` — separate from `--scope` so an "
        "unmade routing decision can never be made by a flag's default value.",
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
        help="Extraction model. Defaults per harness: "
        f"`{extraction.DEFAULT_MODEL}` via claude -p, "
        f"`{extraction.CURSOR_DEFAULT_MODEL}` via agent -p. The archive is "
        "immutable, so a better model can always re-extract later.",
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

    # Ingest command — curated feed v0, manual-first (docs/06)
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
        "--harness", choices=agents.HARNESSES, default="claude",
        help="Which coding-agent CLI runs the extraction pass (default: claude). "
        "Ingestion has no harness of its own — this picks whichever CLI the "
        "machine actually has.",
    )
    ingest_parser.add_argument("--title", default="", help="Override the extracted title")
    ingest_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    ingest_parser.add_argument(
        "--write",
        action="store_true",
        help="Write to the graph. Without it, extraction runs and is reported but not persisted.",
    )

    # Contract command — the federation boundary, audited (docs/01, docs/09 M1)
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

    # The architect's instrument (docs/02). Reads code, writes a git-tracked model and
    # findings — never metrics — into the `architect` scope.
    arch_parser = subparsers.add_parser(
        "arch", help="The architect's structural instrument over a repo's imports"
    )
    arch_sub = arch_parser.add_subparsers(dest="arch_command")

    arch_scan_parser = arch_sub.add_parser(
        "scan",
        help="Measure the import graph, regenerate arch/model.yaml, and land the scan "
        "(dry-run unless --write)",
    )
    arch_scan_parser.add_argument("--repo", default=".", help="Repo to scan")
    arch_scan_parser.add_argument(
        "--import-depth", choices=["all", "module-level"], default="",
        help="Override the model file's declared policy. Changes the policy digest, so "
        "the scan lands in a different lineage — which is the point.",
    )
    arch_scan_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    arch_scan_parser.add_argument(
        "--write", action="store_true",
        help="Write the model file and land the scan in the graph. Without it, the scan "
        "runs and is reported but nothing is persisted.",
    )

    arch_show_parser = arch_sub.add_parser(
        "show", help="Print the current model: declared policy, layers, rules, last scan"
    )
    arch_show_parser.add_argument("--repo", default=".", help="Repo to read")

    arch_diff_parser = arch_sub.add_parser(
        "diff",
        help="Compare the working tree's structure against another commit — recompute "
        "both sides rather than trusting a stored number",
    )
    arch_diff_parser.add_argument("against", help="Commit-ish to compare against")
    arch_diff_parser.add_argument("--repo", default=".", help="Repo to scan")

    arch_rules_parser = arch_sub.add_parser(
        "rules", help="Check the measured edge list against the declared design rules"
    )
    arch_rules_parser.add_argument("--repo", default=".", help="Repo to scan")

    arch_growth_parser = arch_sub.add_parser(
        "growth",
        help="What this system accumulates, and what nothing refers to (read-only)",
    )
    arch_growth_parser.add_argument("--repo", default=".", help="Repo the worktrees belong to")
    arch_growth_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")

    # Chunk backfill — co-indexing for documents ingested before chunks existed.
    # Model-free by construction: chunking reads the retained bytes, so this costs
    # compute and nothing else, and it is safe to re-run (lab/052).
    backfill_parser = subparsers.add_parser(
        "backfill-chunks",
        help="Build co-indexed Chunk vertices for already-ingested documents",
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
        help="Measure how fragmented Artifact identity is (read-only)",
    )
    audit_artifacts_parser.add_argument(
        "--url", default=DEFAULT_URL, help="Gremlin endpoint"
    )

    repair_projects_parser = subparsers.add_parser(
        "repair-projects",
        help="Re-anchor project values that named a directory instead of a repo "
        "(dry-run unless --write)",
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
        help="Project Artifact identifiers onto (repo, path) without re-keying them "
        "(dry-run unless --write)",
    )
    derive_paths_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    derive_paths_parser.add_argument(
        "--write", action="store_true",
        help="Apply the plan. Without this, nothing is written.",
    )

    retire_scans_parser = subparsers.add_parser(
        "retire-scans",
        help="Remove the graph records of architecture scans, which are no longer "
        "written (dry-run unless --write)",
    )
    retire_scans_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    retire_scans_parser.add_argument(
        "--write", action="store_true",
        help="Apply the plan. Without this, nothing is removed.",
    )

    # Snapshot command — durability on demand (docs/09)
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

    # Eval command — layer 1 of the eval loop (docs/04)
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
             "inside (docs/12 item 8), with each room's out-of-occasion burn beside it",
    )

    eval_pins_parser = eval_sub.add_parser(
        "pins",
        help="Pin-quality routing signal: per-expert pinned vs consulted utility "
        "from priced traces (docs/02: the pin or the expert — the data says which)",
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

    eval_rooms_parser = eval_sub.add_parser(
        "rooms",
        help="Room manipulation check: did the collaboration actually happen (not a score)",
    )
    eval_rooms_parser.add_argument(
        "--pins", type=Path, default=None,
        help="Pin ledger file (default: ~/.thalamus/pins/pins.jsonl)",
    )
    eval_rooms_parser.add_argument(
        "--guards", type=Path, default=None, help="Guard event dir (default: ~/.thalamus/guards)"
    )

    eval_legibility_parser = eval_sub.add_parser(
        "legibility",
        help="Audit an aid's contrast, and emit the degraded arms a cold read is run on",
    )
    eval_legibility_parser.add_argument(
        "svg", type=Path, nargs="+", help="SVG aid(s) to read")
    eval_legibility_parser.add_argument(
        "--arm", choices=legibility_arms(), default=None,
        help="Write this arm's variant beside the source instead of reporting")
    eval_legibility_parser.add_argument(
        "--out", type=Path, default=None,
        help="Directory for --arm output (default: alongside the source)")
    eval_legibility_parser.add_argument(
        "--surface", default="", help="Canvas to measure against (default: auto-detected)")
    eval_legibility_parser.add_argument(
        "--threshold", type=float, default=None,
        help="WCAG ratio placed on the floor by the contrast arm (default: 3.0, "
             "criterion 1.4.11 for meaningful non-text)")
    eval_legibility_parser.add_argument(
        "--floor", type=float, default=None,
        help="Where the threshold lands after degradation (default: 1.5)")
    eval_legibility_parser.add_argument(
        "--mutate", nargs=2, metavar=("COLOUR", "RATIO"), default=None,
        help="Re-shade COLOUR to sit at exactly RATIO against the surface — a "
             "known-bad variant for checking the arm discriminates at all")
    eval_legibility_parser.add_argument(
        "--strict", action="store_true",
        help="Exit 1 if any governed colour is below its threshold")

    eval_ri_parser = eval_sub.add_parser(
        "randomize",
        help="Randomization inference over clusters, and whether a design can reject at all",
    )
    eval_ri_parser.add_argument(
        "--clusters", type=int, default=0, help="Cluster count, for a design-only feasibility check"
    )
    eval_ri_parser.add_argument(
        "--treated", type=int, default=0, help="How many of them are treated"
    )
    eval_ri_parser.add_argument(
        "--alpha", type=float, default=0.05, help="Significance level (default 0.05)"
    )
    eval_ri_parser.add_argument(
        "--outcomes", default="",
        help="Comma-separated cluster-level outcomes in [0,1], treated arm first",
    )

    eval_rakes_parser = eval_sub.add_parser(
        "rakes",
        help="Rake registry and adjudication window: solved problems later sessions "
        "could have stepped on again (lab/024 §2.1, Class A stage 0 — proximity, "
        "never a hit verdict)",
    )
    eval_rakes_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    eval_rakes_parser.add_argument(
        "--queue",
        type=Path,
        default=None,
        help="Write the (rake, later-session) adjudication queue as JSONL for a "
        "future stage-1/2 detector",
    )

    eval_rake_audit_parser = eval_sub.add_parser(
        "rake-audit",
        help="Draw or score the hand-audited precision sample for the rake queue "
        "(Class A stage 0.5 — the ground truth stage 2 is blocked on)",
    )
    eval_rake_audit_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    eval_rake_audit_parser.add_argument(
        "--draw",
        type=Path,
        default=None,
        help="Write a blind labelling worksheet to this path",
    )
    eval_rake_audit_parser.add_argument(
        "--score",
        type=Path,
        default=None,
        help="Read a labelled worksheet back and estimate queue precision",
    )
    eval_rake_audit_parser.add_argument(
        "--key",
        type=Path,
        default=None,
        help="Key path (default: alongside the worksheet). Written by --draw, read "
        "by --score; the worksheet itself stays blind",
    )
    eval_rake_audit_parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Draw seed (default: random). Fix it before drawing, never after "
        "seeing the sample (arXiv 1709.01709)",
    )
    eval_rake_audit_parser.add_argument(
        "--size", type=int, default=None, help=f"Real pairs to draw (default {SAMPLE_SIZE})"
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

    eval_gold_parser = eval_sub.add_parser(
        "gold",
        help="The human gold label set: draw a stratified sample, then score the "
        "judge against it. The permutation null bounds the judge against chance; "
        "only this bounds it against truth.",
    )
    eval_gold_parser.add_argument(
        "--draw", action="store_true", help="Draw the sample and write the labelling workbooks"
    )
    eval_gold_parser.add_argument(
        "--score", action="store_true", help="Score the judge against whatever has been labelled"
    )
    eval_gold_parser.add_argument(
        "--n", type=int, default=256,
        help="Sample size (default 256 — the n for SE(kappa)=0.05; see eval/gold.py)",
    )
    eval_gold_parser.add_argument("--seed", type=int, default=20260730)
    eval_gold_parser.add_argument("--scope", default=MAIN_SCOPE)
    eval_gold_parser.add_argument(
        "--snapshot", default="", help="Draw against a pinned snapshot instead of the live graph"
    )
    eval_gold_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")

    eval_tasks_parser = eval_sub.add_parser(
        "tasks",
        help="Validate and list the counterfactual task battery (config/tasks/)",
    )
    eval_tasks_parser.add_argument(
        "--config", type=Path, default=None,
        help="Config root holding tasks/ (default: repo config/)",
    )

    eval_corpus_parser = eval_sub.add_parser(
        "corpus",
        help="Pin the trajectory corpus (runs.jsonl) under a name, so a study can "
        "cite the exact state it was computed over",
    )
    eval_corpus_parser.add_argument(
        "--name", default="",
        help="Seal the current run log under this name. Corpus pins are immutable: "
        "a name that has been cited keeps meaning what it meant.",
    )
    eval_corpus_parser.add_argument(
        "--note", default="", help="What this pin is for; shown in the registry"
    )
    eval_corpus_parser.add_argument(
        "--list", action="store_true",
        help="List pinned corpora and verify their digests",
    )
    eval_corpus_parser.add_argument(
        "--diff", default="",
        help="Report what has changed since the named pin, separating legitimate "
        "appends and supersessions from in-place rewrites",
    )
    eval_corpus_parser.add_argument(
        "--runs", type=Path, default=None,
        help="Run log to pin (default: ~/.thalamus/counterfactuals/runs.jsonl)",
    )

    eval_rescore_parser = eval_sub.add_parser(
        "rescore",
        help="Apply the contamination and history-reach detectors backwards over "
        "campaigns that ran before they existed",
    )
    eval_rescore_parser.add_argument(
        "--memo-echo",
        action="store_true",
        help="Re-derive memo_echoed under the current judge instead of stamping "
             "contamination. Four records carry the superseded key's output "
             "(lab/037); the prior value is kept beside the fresh one.",
    )
    eval_rescore_parser.add_argument(
        "--repo", type=Path, default=None,
        help="Operator checkout the arms could escape into (default: cwd)",
    )
    eval_rescore_parser.add_argument(
        "--runs", type=Path, default=None,
        help="Run log to re-score (default: ~/.thalamus/counterfactuals/runs.jsonl)",
    )
    eval_rescore_parser.add_argument(
        "--config", type=Path, default=None,
        help="Config root holding tasks/ (default: repo config/)",
    )
    eval_rescore_parser.add_argument(
        "--force", action="store_true",
        help="Re-derive stamps on records that already carry them",
    )
    eval_rescore_parser.add_argument(
        "--write", action="store_true",
        help="Stamp the records. Without it, the derivation runs and is reported "
        "but nothing is modified.",
    )

    eval_oracle_parser = eval_sub.add_parser(
        "oracle",
        help="Validate the graded oracle itself: grade anchors and the mutant set "
        "against pre-registered rungs (no model in the loop)",
    )
    eval_oracle_parser.add_argument("task_id", help="A task id from config/tasks/")
    eval_oracle_parser.add_argument(
        "--config", type=Path, default=None,
        help="Config root holding tasks/ (default: repo config/)",
    )
    eval_oracle_parser.add_argument(
        "--anchors-only", action="store_true",
        help="Grade only the range pair, skipping the mutant set (range coverage "
        "is not discrimination — the interior is where the arms sit)",
    )
    eval_oracle_parser.add_argument(
        "--timeout", type=int, default=900, help="Per-check timeout, seconds"
    )
    eval_oracle_parser.add_argument(
        "--keep-worktrees", action="store_true",
        help="Leave the graded worktrees on disk for inspection",
    )

    eval_run_parser = eval_sub.add_parser(
        "run",
        help="Run one battery task under counterfactual arms (worktree + headless session + oracles)",
    )
    eval_run_parser.add_argument("task_id", help="A task id from config/tasks/")
    eval_run_parser.add_argument(
        "--arm", action="append", dest="arms", default=None,
        help="memory-on | memory-off | ceiling | scoping-degraded:<scope>; repeatable, "
        "runs in the order given (default: memory-on then memory-off). `ceiling` is "
        "the skyline: memory-off's stripped harness with the task's withheld fact "
        "handed over directly, so it bounds what any retrieval could be worth.",
    )
    eval_run_parser.add_argument(
        "--model", default=None, help="Arm session model (default: sonnet)"
    )
    eval_run_parser.add_argument(
        "--max-turns", type=int, default=None, help="Turn cap for the arm session"
    )
    eval_run_parser.add_argument(
        "--timeout", type=int, default=None, help="Arm session timeout, seconds"
    )
    eval_run_parser.add_argument(
        "--full-auto", action="store_true",
        help="Run the arm session with --dangerously-skip-permissions (real campaigns "
        "need this: the default acceptEdits mode auto-denies Bash, so the candidate "
        "cannot run tests)",
    )
    eval_run_parser.add_argument(
        "--keep", action="store_true", help="Keep the worktree(s) for inspection"
    )
    eval_run_parser.add_argument(
        "--sandbox", action="store_true",
        help="Confine the arm session to a container in which the operator's "
        "checkout does not exist (docker/arm-runner.Dockerfile). Closes the "
        "filesystem half of the answer-key leak; the git half is closed by the "
        "arm's one-commit repo regardless. Refuses if the image is not built.",
    )
    eval_run_parser.add_argument(
        "--isolate-store", action="store_true",
        help="With --sandbox, additionally cut the network for arms that have no "
        "memory surface, so memory-off cannot reach the graph over ad-hoc "
        "gremlin. This CHANGES the memory-off treatment — a second factor — so "
        "it is opt-in and must be declared in the campaign's pre-registration.",
    )
    eval_run_parser.add_argument(
        "--config", type=Path, default=None,
        help="Config root holding tasks/ (default: repo config/)",
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

    # Pin / roster commands — docs/07 "the process is the pin"
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
        "--harness", choices=("claude", "cursor", "both"), default="both",
        help="Which editor to wire (default: both)"
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

    rescope_parser = subparsers.add_parser(
        "rescope", help="Redirect a session's distillation scope (before it distills)"
    )
    rescope_parser.add_argument("scope", help="Scope to distill into (`main` or a manifest)")
    rescope_parser.add_argument(
        "session", nargs="?", default=None,
        help="Session ID (prefix ok). Default: the current session, read from "
             "$CLAUDE_CODE_SESSION_ID — never guess it (lab/026)"
    )
    rescope_parser.add_argument("--reason", default="", help="Why, for the ledger record")
    rescope_parser.add_argument(
        "--dry-run", action="store_true", help="Report the correction without appending it"
    )
    rescope_parser.add_argument(
        "--other-session", action="store_true",
        help="Acknowledge that the session argument names a DIFFERENT session than the "
             "one running. Required whenever they differ; the mismatch is detected from "
             "$CLAUDE_CODE_SESSION_ID, not taken on trust (lab/026)"
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
        "--harness", choices=agents.HARNESSES, default="claude", help="Which CLI to pin (default: claude). `cursor` carries the scope as an argv prefix and passes no permission mode, so the session obeys your own ~/.cursor/cli-config.json and can stop at a prompt. `--force`/`--yolo` would not stop, but it is `auto` minus the safety classifier rather than an equivalent (see harness/launcher.py). No persona: Cursor has no `--agent` (see contract/pinning.py for what `pinned` covers there)."
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
        "--harness", choices=agents.HARNESSES, default="claude", help="Which CLI to pin (default: claude). `cursor` carries the scope as an argv prefix and passes no permission mode, so the session obeys your own ~/.cursor/cli-config.json and can stop at a prompt. `--force`/`--yolo` would not stop, but it is `auto` minus the safety classifier rather than an equivalent (see harness/launcher.py). No persona: Cursor has no `--agent` (see contract/pinning.py for what `pinned` covers there)."
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

    # Ceremony ledger — docs/12's capture layer. Every verb here writes a row that
    # cannot be reconstructed after the fact, which is why they exist before any of
    # the lifecycle they record.
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

    # Dispatch — docs/12 §Delivery mechanics. A separate verb rather than a loop over
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

    # Visualize command
    visualize_parser = subparsers.add_parser(
        "visualize", help="Open an interactive session graph in the local viewer"
    )
    visualize_parser.add_argument(
        "file", type=Path, nargs="?", help="Optional path to session YAML/JSON file"
    )
    visualize_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    visualize_parser.add_argument(
        "--host", default="127.0.0.1", help="Viewer bind address (default: localhost)"
    )
    visualize_parser.add_argument(
        "--port", type=int, default=0, help="Viewer port; zero selects an available port"
    )
    visualize_parser.add_argument(
        "--no-open", action="store_true", help="Start the viewer without opening a browser"
    )

    # Console command — the operator surface onto the tmux roster, drivable from a phone
    console_parser = subparsers.add_parser(
        "console",
        help="Serve the console: drive the pinned tmux roster from a browser",
    )
    console_parser.add_argument(
        "--host", default="127.0.0.1",
        help="Bind address (default: localhost — the console has no auth of its own; "
             "see docs/console.md)"
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
        help="A systemd --user unit the admin sheet may restart (repeatable; "
             "default: none, which hides the section)"
    )
    console_parser.add_argument(
        "--frames", type=Path, default=None, metavar="PATH",
        help="Frame-theme definitions for the desktop client, e.g. "
             "$WEZTERM_CONFIG_DIR/frames.lua (default: none — no frame themes)"
    )
    # THALAMUS_VOICE_URL supplies the default rather than the feature: an operator
    # already running the unit keeps their setting, and a box without one gets no
    # `say` control instead of a button that fails on first tap.
    console_parser.add_argument(
        "--voice", default=os.environ.get("THALAMUS_VOICE_URL") or None, metavar="URL",
        help="Speech service backing the `say` control, e.g. http://127.0.0.1:8380 "
             "(default: $THALAMUS_VOICE_URL, else none — the control is hidden)"
    )
    console_parser.add_argument(
        "--fetch-interval", type=float, default=10.0, metavar="MINUTES",
        help="How often to fetch the checkout's remote so the console knows whether "
             "it is behind (default: 10; 0 disables, and the count then only reflects "
             "the last fetch somebody ran)"
    )

    # Pulse command — the live telemetry dashboard (docs/03)
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
    sys.stdout.reconfigure(line_buffering=True)
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
    elif args.command == "snapshot":
        _cmd_snapshot(args)
    elif args.command == "eval":
        _cmd_eval(args, eval_parser)
    elif args.command == "init":
        _cmd_init(args)
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
    elif args.command == "visualize":
        _cmd_visualize(args)
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
        vid = write_session(g, session)
        _persist(g)
        print(f"Wrote session: {session.session_id} -> {vid}")
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


def _cursor_bootstrap_groups(args):
    """One group per resolved scope — Cursor discovery is session-oriented.

    Grouping by scope rather than by directory because that is the axis a Cursor
    session actually varies on: it is pinned by `THALAMUS_SCOPE` at launch, and
    the sanitized project directory it lands under is a flattened cwd we
    deliberately never un-flatten.
    """
    from thalamus.harness.bootstrap import bootstrap_cursor

    found = [s for s in cursor_transcripts.discover() if s.exists]
    if not found:
        print(
            "No Cursor sessions found. Discovery reads the sessionEnd hook log "
            f"({cursor_transcripts.CURSOR_SESSION_END_LOG}) and sweeps "
            f"{cursor_transcripts.CURSOR_PROJECTS}; nothing in either means no Cursor "
            "session has run on this machine.",
            file=sys.stderr,
        )
        sys.exit(1)

    ready, refused = cursor_transcripts.claim_unresolved(found, args.assign_scope)
    if refused:
        print(
            f"  ! {len(refused)} session(s) found on disk that no hook ever saw, so no "
            "scope was ever resolved for them. They are NOT being bootstrapped. Re-run "
            "with `--assign-scope <scope>` to route them, after checking they belong "
            "there:",
            file=sys.stderr,
        )
        for session in refused:
            print(
                f"      {session.session_id[:8]}  {session.cwd or 'cwd unknown'}",
                file=sys.stderr,
            )
    if not ready:
        return None

    by_scope: dict[str, list] = {}
    for session in ready:
        by_scope.setdefault(session.scope, []).append(session)
    return [
        (f"cursor · scope {scope}", bootstrap_cursor(sessions))
        for scope, sessions in sorted(by_scope.items())
    ]


def _cmd_bootstrap(args):
    if args.harness == "cursor":
        groups = _cursor_bootstrap_groups(args)
        if groups is None:
            return
    else:
        groups = _claude_bootstrap_groups(args)
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
                    write_session(graph, session)
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


def _cmd_extract(args):
    """Stage 2 of the bootstrap: model-extracted Claims and Threads.

    Sessions are processed chronologically so a thread opened in March can be resolved by
    a session from April — the same replay semantics a live agent would have produced.
    """
    from thalamus.archive import read_archived
    from thalamus.contract.conformance import prune_orphan_artifacts
    from thalamus.contract.ontology import vid

    cursor = args.harness == "cursor"
    reader = cursor_transcripts if cursor else transcripts

    if cursor:
        ended = [s for s in cursor_transcripts.discover() if s.exists]
        if not ended:
            print(
                "No Cursor sessions to extract. Sessions are found two ways: the "
                f"sessionEnd hook's log ({cursor_transcripts.CURSOR_SESSION_END_LOG}) "
                f"and a sweep of {cursor_transcripts.CURSOR_PROJECTS}. Nothing in "
                "either means no Cursor session has ended on this machine yet.",
                file=sys.stderr,
            )
            return

        # A session no hook ever saw has no resolved scope, and `main` is not a
        # safe stand-in — routing an unattested session into the operator's own
        # subgraph is a decision nobody made and cannot be undone once written.
        ended, refused = cursor_transcripts.claim_unresolved(ended, args.assign_scope)
        if refused:
            print(
                f"  ! {len(refused)} session(s) found on disk that no hook ever saw, so no "
                "scope was ever resolved for them. They are NOT being extracted. Re-run "
                "with `--assign-scope <scope>` to route them, after checking they belong "
                "there:",
                file=sys.stderr,
            )
            for session in refused:
                print(
                    f"      {session.session_id[:8]}  {session.cwd or 'cwd unknown'}",
                    file=sys.stderr,
                )
    else:
        available = transcripts.discover(args.projects_dir)
        if not args.projects:
            print("Specify project dir(s); `thalamus bootstrap` lists what is available.")
            return

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

    extracted = skipped = failed = 0
    total_cost = 0.0
    unpriced = replayed = 0

    # Session selection runs before the graph connection: a run that selects nothing
    # has no reason to open one, and the refusal below stays reachable on a machine
    # whose graph is down.
    # Chronological across all requested projects: threads resolve forward in time.
    parsed = []
    # Sessions the substance gate withheld, kept by id so an explicitly named one can
    # be reported as *skipped* rather than as *missing* below.
    insubstantial: list[str] = []
    if cursor:
        # Scope comes from the session's own sessionEnd record, not the flag:
        # ledger-first resolution is what keeps a pinned Cursor session out of
        # the wrong subgraph (docs/07). A cursor session carries no timestamps
        # or cwd of its own, so both come from the hooks' ledgers.
        scopes: dict[str, str] = {}
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
            # second refusal the Claude Code path makes below, on the cwd the
            # session itself recorded — every headless extraction is a full
            # Cursor session that files its own transcript, so a sandbox reached
            # by any other route still has to be refused here.
            if agents.is_sandbox_cwd(facts.cwd):
                continue
            scopes[facts.session_id] = ended_session.scope
            parsed.append(facts)

        # Surfaced, not swallowed: this parser was written against Cursor's
        # documented shape without ever seeing a real transcript, so records it
        # cannot classify are the first evidence that the shape is wrong. A
        # count nobody reads is the same silent failure as no count at all.
        unread = sum(f.unrecognized for f in parsed)
        if unread:
            print(
                f"  ! {unread} record(s) across {sum(1 for f in parsed if f.unrecognized)} "
                "session(s) did not match the expected Cursor shape — the format may "
                "have changed (see harness/cursor_transcripts.py, lab/028)",
                file=sys.stderr,
            )
    else:
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
    parsed.sort(key=lambda f: (f.started_at is None, f.started_at))

    if args.session:
        parsed = [
            f for f in parsed if any(f.session_id.startswith(s) for s in args.session)
        ]
        # Then the archive, for the named sessions ~/.claude no longer holds. The
        # harness rotates its own transcripts, which is why they are retained at all
        # (docs/10) — a recovery that could read only the live dir would still lose a
        # session to the rotation retention was built to survive. Only for a *named*
        # session: a sweep of the archive would re-offer the whole distilled corpus,
        # and only for Claude Code, whose transcript is retained whole where Cursor's
        # evidence deliberately is not.
        if not cursor:
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
            where = (
                "the Cursor sessionEnd log" if cursor
                else f"{', '.join(args.projects)} or the archive"
            )
            print(
                f"No session matching {requested} under {where} — nothing distilled.",
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

    print(f"{len(parsed)} sessions to extract (model: {args.model})")

    graph = connect(args.url)
    try:
        for facts in parsed:
            name = facts.session_id[:8]
            scope = scopes.get(facts.session_id, args.scope) if cursor else args.scope
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

            entry, _ = transcripts.retain(facts.path)
            # A Cursor session's ingress evidence lives outside its transcript, so the
            # transcript alone would not reach what the floor judged (docs/05).
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
                digest = extraction.render_digest(payload)
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
                        prompt, model=args.model, harness=args.harness
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
                # The laundering floor (docs/05): claims resting on the transcript's
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
                    write_session(graph, session)
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


def _cmd_ingest(args):
    from thalamus.contract.conformance import check_knowledge
    from thalamus.contract.manifest import load_manifest
    from thalamus.harness import extraction as extraction_mod
    from thalamus.harness import ingest as ingest_mod
    from thalamus.substrate.writer import write_knowledge

    try:
        manifest = load_manifest(args.scope)
    except (FileNotFoundError, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    # Advisory, like the known-claims feed: an unreachable graph degrades to an
    # ingest with no entity vocabulary, never a failed ingest.
    known_entities: list[dict] = []
    try:
        from thalamus.substrate.reader import knowledge_entities

        graph = connect(args.url)
        try:
            known_entities = knowledge_entities(graph, args.scope)
        finally:
            close_connection(graph)
    except Exception:
        pass

    try:
        batch, run, digest = ingest_mod.ingest(
            args.location,
            scope=args.scope,
            feed=args.feed,
            model=args.model,
            harness=args.harness,
            title=args.title,
            known_entities=known_entities,
        )
    except (ingest_mod.IngestError, extraction_mod.ExtractionError) as e:
        print(f"Ingest failed: {e}", file=sys.stderr)
        sys.exit(1)

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
            f"    its own file (docs/06 §4).",
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
    `thalamus derive-artifact-paths`. Run that to see how much of this is reached.
    """
    from thalamus.substrate.artifact_audit import audit_artifact_identity

    graph = connect(args.url)
    try:
        audit = audit_artifact_identity(graph)

        print(f"Artifact vertices: {audit.total}")
        print(f"  absolute paths duplicating a relative sibling: {len(audit.split_pairs)}")
        print(f"  touch edges stranded on those duplicates:      {audit.stranded_touches}")
        print(f"  relative paths claimed by >1 project:          {len(audit.collisions)}")

        if audit.split_pairs:
            print("\nmost-stranded duplicates:")
            for _, relative, touches in sorted(
                audit.split_pairs, key=lambda row: -row[2]
            )[:10]:
                print(f"  {touches:4d} touches  {relative}")

        if audit.collisions:
            print("\npaths claimed by more than one project:")
            for path, owners in sorted(audit.collisions.items())[:10]:
                print(f"  {path}  <- {sorted(owners)}")

        print("\nproject values in use:")
        for project, count in audit.projects.items():
            print(f"  {count:5d}  {project}")
        print(
            "\nRead-only. Repair is blocked on an anchor for making absolute paths "
            "repo-relative;\n`project` cannot serve as one while values like these are "
            "in it."
        )
    finally:
        close_connection(graph)


def _cmd_backfill_chunks(args):
    """Co-index documents that were ingested before chunks existed.

    Needs no model: a chunk is a slice of retained bytes, and the entity vocabulary it
    tags itself with is already in the graph. So this is a rebuild, not a re-extraction
    — which is the property that makes chunk geometry a dial rather than a commitment
    (lab/052). Claims, entities and Sources are left exactly as they are.
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


def _cmd_eval_corpus(args):
    from thalamus.eval import corpora

    if args.list:
        rows = corpora.registry()
        if not rows:
            print(
                "No pinned corpora. `thalamus eval corpus --name <id>` pins the "
                "current run log."
            )
            return
        for row in rows:
            corpus_ok, manifest_ok = corpora.verify(row.name)
            # Two states, never pooled: a sealed file that no longer hashes to its
            # citation and a manifest that no longer matches it are different
            # failures, and the worse one must not hide behind the other.
            state = "ok" if corpus_ok and manifest_ok else (
                "CORPUS MISMATCH" if not corpus_ok else "MANIFEST MISMATCH"
            )
            print(
                f"{row.name:32} {row.taken_at[:19]}  {row.records:>5} records  "
                f"sha {row.sha256[:12]}  @{row.git_ref}  {state}"
            )
            if row.note:
                print(f"{'':32} {row.note}")
        return

    if args.diff:
        try:
            delta = corpora.diff(args.diff, corpora.load_records(args.runs))
        except corpora.CorpusError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)
        print(f"Against `{args.diff}`:")
        print(f"  unchanged:   {delta.unchanged}")
        print(f"  appended:    {len(delta.added)}")
        print(f"  superseded:  {len(delta.superseded)}")
        print(f"  REWRITTEN:   {len(delta.rewritten)}")
        print(f"  REMOVED:     {len(delta.removed)}")
        for run in delta.rewritten:
            print(f"    rewritten in place: {run}")
        for run in delta.removed:
            print(f"    removed: {run}")
        if delta.clean:
            print(
                "\nClean: appends and supersessions only. Every record present at "
                "seal time still says what it said."
            )
        else:
            # Not an error exit — the report is the point, and a corpus that has
            # been rewritten is exactly what the operator needs to see rendered.
            print(
                "\nNot clean: records changed under their own identity. A study "
                f"citing `{args.diff}` is not reproducible against this file."
            )
        return

    if args.name:
        try:
            row = corpora.seal(args.name, note=args.note, runs_path=args.runs)
        except corpora.CorpusError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)
        print(
            f"Pinned `{row.name}`: {row.records} records, {row.byte_size / 1e3:.0f} kB, "
            f"sha256 {row.sha256[:12]} @{row.git_ref}"
        )
        print(f"  registry: {corpora.REGISTRY}")
        print(f"  manifest: {row.manifest_path}")
        print(f"  sealed:   {row.pinned_path} (read-only)")
        print(f"  check it: thalamus eval corpus --diff {row.name}")
        return

    print(
        "Nothing to do. `--name <id>` seals the current run log, `--list` shows "
        "what is pinned, `--diff <id>` reports what has changed since a pin.",
        file=sys.stderr,
    )
    sys.exit(1)


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


def _cmd_eval_gold(args):
    from contextlib import nullcontext

    from thalamus.eval import calibration, gold, snapshots
    from thalamus.eval.attribution import JUDGES

    if args.score or not args.draw:
        items = gold.load_sample()
        if not items:
            print("No sample drawn yet. `thalamus eval gold --draw` writes one.")
            return
        labels = gold.read_labels()
        result = gold.agreement(items, labels)
        done = sum(1 for i in items if i.item_id in labels)
        print(f"Gold set: {done}/{len(items)} labelled, {result.unclear} marked unclear")
        if not result.n:
            print("  nothing decidable yet — label a batch and re-run")
            return
        lo, hi = result.ci
        print(
            f"  judge vs human on {result.n} decidable items: "
            f"kappa {result.kappa:.3f} [{lo:.3f}, {hi:.3f}] "
            f"(observed {result.observed:.3f}, chance {result.expected:.3f})"
        )
        print(f"  sensitivity {result.sensitivity:.3f} · specificity {result.specificity:.3f}")
        print("  single annotator, so there is no inter-annotator agreement to report.")
        for name, split in gold.by_stratum(items, labels, lambda i: i.node_kind).items():
            if split.n:
                print(f"    {name:10} n={split.n:<4} kappa {split.kappa:+.3f}")
        return

    context = snapshots.serve(args.snapshot) if args.snapshot else nullcontext(args.url)
    with context as url:
        graph = connect(url)
        try:
            cases, _census = calibration.load_cases(graph, scope=args.scope)
        finally:
            close_connection(graph)
    scored = calibration.score(cases, JUDGES["shipped"])
    items = gold.draw(cases, scored.verdicts, n=args.n, seed=args.seed)
    paths = gold.write_batches(items)
    print(f"Drew {len(items)} items across {len(paths)} batches into {gold.GOLD_DIR}")
    print(f"  n={args.n} is SE(kappa)={0.05 if args.n == 256 else '?'} — see eval/gold.py for the derivation")
    print("  the judge's verdict is recorded in sample.jsonl and withheld from the workbooks")
    for path in paths:
        print(f"    {path.name}")
    print("\nLabel a batch, then: thalamus eval gold --score")


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
    # tables never asks a harness anything (lab/061).
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
        tools = capability.deny_tools
        skills = capability.deny_skills
        print(f"    tools      denied [{origin}]: {', '.join(tools) if tools else '(nothing)'}")
        print(f"    skills     denied [{origin}]: {', '.join(skills) if skills else '(nothing)'}")

    print("\nBoundaries are enforced by the role-guard PreToolUse hook, which binds "
          "the file-editing tools, `Skill` and `Artifact`. Bash and `Read` on a "
          "SKILL.md are named misses (role-guard.sh). Which of these binds on which "
          "harness is a separate question with a separate record: "
          "`thalamus contract check --capabilities`.")


def _cmd_arch(args, arch_parser):
    """The architect's instrument. Reads code; writes a model file and findings."""
    command = getattr(args, "arch_command", None)
    if command not in {"scan", "show", "diff", "rules", "growth"}:
        arch_parser.print_help()
        sys.exit(1)

    import dataclasses
    import subprocess
    import tempfile
    from pathlib import Path

    from thalamus.arch import findings as arch_findings
    from thalamus.arch import model as arch_model
    from thalamus.arch.extractor import scan_repo
    from thalamus.arch.metrics import measure

    repo = Path(args.repo).resolve()
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

    graph = scan_repo(repo, policy)
    metrics = measure(graph)

    if command == "rules":
        _arch_rules(model, graph)
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
                other = measure(scan_repo(checkout, policy))
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
    found = arch_findings.findings(graph, metrics, model)

    print(f"Scan {derived['scan']}")
    print(f"  policy      import_depth={policy.import_depth} resolve={policy.resolve} "
          f"digest={policy.digest()[:7]}")
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


def _arch_rules(model, graph) -> None:
    """Check the measured edges against the declared rules."""
    if not model.layers:
        print(
            f"No layers declared, so the partition places none of {len(graph.modules)} "
            "scanned modules. Declaring them is the architect's work — an empty "
            "partition reports nothing rather than passing."
        )
        return
    unplaced = model.unplaced(graph)
    violations = model.violations(graph)
    print(f"{len(graph.modules)} modules, {len(unplaced)} unplaced by the declared partition")
    for module in unplaced[:20]:
        print(f"  unplaced  {module}")
    print(f"{len(violations)} rule violation(s)")
    for violation in violations:
        print(f"  violation {violation.describe()}")
    if not unplaced and not violations:
        print("The declared model and the measured graph agree.")


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

    from thalamus.contract.conformance import check_graph

    graph = connect(args.url)
    try:
        issues, counts = check_graph(graph)
    finally:
        close_connection(graph)

    print(f"Audited {counts['vertices']} vertices, {counts['edges']} edges.")
    if not issues:
        print("Contract OK — every node carries provenance, every edge is legal, "
              "every Source resolves to retained bytes.")
        return
    print(f"\n{len(issues)} issue(s):", file=sys.stderr)
    for issue in issues:
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
    elif getattr(args, "eval_command", None) == "randomize":
        from thalamus.eval.randomization import (
            feasible, monitor, randomization_test, render, smallest_design,
        )

        if args.outcomes:
            values = [float(v) for v in args.outcomes.split(",") if v.strip()]
            treated_n = args.treated or len(values) // 2
            flags = [i < treated_n for i in range(len(values))]
            print(render(
                randomization_test(values, flags),
                feasible(len(values), treated_n, alpha=args.alpha),
                monitor(values, flags),
            ))
        elif args.clusters:
            print(f"  design: {feasible(args.clusters, args.treated, alpha=args.alpha).note()}")
        else:
            total, treated = smallest_design(alpha=args.alpha)
            print(
                f"  smallest design that can reject at α={args.alpha:g}: "
                f"{total} clusters split {treated}/{total - treated}"
                if total
                else f"  no design under the search limit can reject at α={args.alpha:g}"
            )
    elif getattr(args, "eval_command", None) == "rooms":
        from thalamus.eval.rooms import render as render_rooms
        from thalamus.eval.rooms import room_topologies

        print(render_rooms(room_topologies(pins_file=args.pins, guards_base=args.guards)))
    elif getattr(args, "eval_command", None) == "legibility":
        from thalamus.eval import legibility as leg

        kwargs = {}
        if args.threshold is not None:
            kwargs["threshold"] = args.threshold
        if args.floor is not None:
            kwargs["floor"] = args.floor
        failed = False
        for path in args.svg:
            source = leg.load(path)
            if args.mutate:
                colour, ratio = args.mutate
                source = leg.mutate(source, colour, float(ratio), args.surface)
            if args.arm:
                variant = leg.degrade(source, args.arm, surface=args.surface, **kwargs)
                out_dir = args.out or path.parent
                out_dir.mkdir(parents=True, exist_ok=True)
                out = out_dir / f"{path.stem}-{args.arm}{path.suffix}"
                out.write_text(variant)
                print(f"{out}")
                continue
            if len(args.svg) > 1:
                print(f"=== {path}")
            print(leg.report(source, surface=args.surface, **kwargs))
            failed |= any(f.fails for f in leg.audit(source, args.surface))
        if args.strict and failed:
            print("\nA governed colour is below its threshold — see FAILS above.",
                  file=sys.stderr)
            sys.exit(1)
    elif getattr(args, "eval_command", None) == "rake-audit":
        from thalamus.eval import rake_audit as ra
        from thalamus.eval.rakes import build_rake_report, read_rakes

        if not args.draw and not args.score:
            eval_parser.error("thalamus eval rake-audit needs --draw or --score")

        if args.draw:
            graph = connect(args.url)
            try:
                rakes, sessions, artifact_sessions, problems = read_rakes(graph)
            finally:
                close_connection(graph)
            report = build_rake_report(rakes, sessions, artifact_sessions, problems=problems)
            sample = ra.draw_sample(
                report,
                rakes,
                sessions,
                seed=args.seed if args.seed is not None else secrets.randbelow(1_000_000),
                size=args.size or ra.SAMPLE_SIZE,
            )
            key_path = args.key or args.draw.with_suffix(args.draw.suffix + ".key.jsonl")
            args.draw.parent.mkdir(parents=True, exist_ok=True)
            args.draw.write_text(ra.render_worksheet(sample))
            key_path.parent.mkdir(parents=True, exist_ok=True)
            key_path.write_text(ra.sample_to_jsonl(sample))
            # The composition is withheld here too — the annotator is usually the
            # person who runs the draw, so the terminal is part of the blind.
            print(f"Wrote {len(sample.items)} item(s) to {args.draw}")
            print(f"  key: {key_path} — needed to score; do not read it before labelling")

        if args.score:
            key_path = args.key or args.score.with_suffix(args.score.suffix + ".key.jsonl")
            if not key_path.exists():
                eval_parser.error(
                    f"--score needs the key written at draw time (looked for {key_path})")
            sample = ra.sample_from_jsonl(key_path.read_text())
            labels, parse_problems = ra.parse_worksheet(args.score.read_text())
            print(ra.score_sample(sample, labels, parse_problems).render())
    elif getattr(args, "eval_command", None) == "rakes":
        from thalamus.eval.rakes import rake_report

        graph = connect(args.url)
        try:
            report = rake_report(graph)
        finally:
            close_connection(graph)
        print(report.render())
        if args.queue:
            args.queue.parent.mkdir(parents=True, exist_ok=True)
            with args.queue.open("w") as handle:
                for candidate in report.candidates:
                    handle.write(
                        json.dumps(
                            {
                                "rake": candidate.rake_vid,
                                "session": candidate.session_vid,
                                "artifacts": list(candidate.artifacts),
                                "hot": candidate.hot,
                            }
                        )
                        + "\n"
                    )
            print(f"\nWrote {len(report.candidates)} candidate pair(s) to {args.queue}")
    elif getattr(args, "eval_command", None) == "gold":
        _cmd_eval_gold(args)
    elif getattr(args, "eval_command", None) == "recipes":
        from thalamus.eval.gremlin import render_smoke, render_staged, smoke_recipes, staged_recipes

        if args.staged:
            print(render_staged(staged_recipes()))
            return
        results = smoke_recipes(args.url)
        print(render_smoke(results))
        if any(not r.ok for r in results):
            sys.exit(1)
    elif getattr(args, "eval_command", None) == "tasks":
        from thalamus.eval.tasks import load_battery, render_battery

        tasks, issues = load_battery(args.config)
        print(render_battery(tasks, issues))
        if issues:
            sys.exit(1)
    elif getattr(args, "eval_command", None) == "oracle":
        from thalamus.eval.oracle import render_gate, run_gate
        from thalamus.eval.tasks import load_battery, quarantine, tasks_dir

        tasks, issues = load_battery(args.config)
        # Per-task, same as `eval run`: the gate refuses the task it is about to
        # spend on, not the battery it happens to live in.
        per_task, battery_wide = quarantine(tasks, issues)
        blocking = battery_wide + per_task.get(args.task_id, [])
        if blocking:
            print(f"`{args.task_id}` does not arm — run `thalamus eval tasks`:",
                  file=sys.stderr)
            for issue in blocking:
                print(f"  - {issue}", file=sys.stderr)
            sys.exit(1)
        by_id = {task.id: task for task in tasks}
        if args.task_id not in by_id:
            print(f"No task `{args.task_id}` (have: {', '.join(sorted(by_id))})",
                  file=sys.stderr)
            sys.exit(1)
        repo = Path(__file__).resolve().parents[2]
        result = run_gate(
            repo, by_id[args.task_id], tasks_dir(args.config),
            timeout=args.timeout, keep=args.keep_worktrees,
            anchors_only=args.anchors_only,
        )
        print(render_gate(result))
        if not result["passed"]:
            sys.exit(1)
    elif getattr(args, "eval_command", None) == "run":
        from thalamus.contract.manifest import available_scopes
        from thalamus.eval import arms as arms_mod
        from thalamus.eval.tasks import load_battery, quarantine

        tasks, issues = load_battery(args.config)
        # Report at the inspection surface, refuse at the spend surface. `eval
        # tasks` loads a faulty battery so the fault can be read and repaired
        # (lab/035); this is the point where money starts, so it refuses — but
        # only as widely as the fault. A dead ref on another task says nothing
        # about this run, and a gate that blocks for a reason untrue of the run
        # it blocks is the kind that gets routed around.
        per_task, battery_wide = quarantine(tasks, issues)
        blocking = battery_wide + per_task.get(args.task_id, [])
        if blocking:
            print(f"`{args.task_id}` does not arm — run `thalamus eval tasks`:",
                  file=sys.stderr)
            for issue in blocking:
                print(f"  - {issue}", file=sys.stderr)
            sys.exit(1)
        by_id = {task.id: task for task in tasks}
        if args.task_id not in by_id:
            print(f"No task `{args.task_id}` (have: {', '.join(sorted(by_id))})",
                  file=sys.stderr)
            sys.exit(1)
        task = by_id[args.task_id]
        # Quarantine is only honest if the campaign record says what was excluded.
        # Otherwise a battery that shrank between two campaigns reads as one that
        # never had those tasks, and the strata a claim is scoped to move silently.
        quarantined = sorted(per_task)
        if quarantined:
            print(f"Quarantined and not available to this campaign: "
                  f"{', '.join(quarantined)}", file=sys.stderr)
        try:
            arm_list = [
                arms_mod.parse_arm(spec, available_scopes())
                for spec in (args.arms or ["memory-on", "memory-off"])
            ]
        except arms_mod.ArmError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        repo = Path(__file__).resolve().parents[2]
        accepted = True
        records = []
        for index, arm in enumerate(arm_list):
            try:
                record = arms_mod.run_arm(
                    repo, task, arm,
                    model=args.model or arms_mod.DEFAULT_MODEL,
                    max_turns=args.max_turns or arms_mod.DEFAULT_MAX_TURNS,
                    timeout=args.timeout or arms_mod.DEFAULT_TIMEOUT,
                    full_auto=args.full_auto, keep=args.keep, order_index=index,
                    sandbox=args.sandbox, isolate_store=args.isolate_store,
                    quarantined=quarantined,
                )
            except arms_mod.SessionFault as exc:
                # Every arm after a session death is void; continuing would only
                # manufacture records that look like data (lab/012, lab/016).
                print(f"\nCAMPAIGN STOPPED — {exc}", file=sys.stderr)
                remaining = [a.spec for a in arm_list[index + 1:]]
                if remaining:
                    print(f"Not run: {', '.join(remaining)}. Check credentials "
                          "and usage limits (`claude -p \"say ok\"` — arms are "
                          "Claude-Code-only, see arms.agent_cli), then "
                          "re-run this campaign.", file=sys.stderr)
                sys.exit(3)
            except arms_mod.ArmError as exc:
                print(f"{task.id} · {arm.spec}: {exc}", file=sys.stderr)
                sys.exit(1)
            records.append(record)
            print(arms_mod.render_run(record))
            print()
            accepted = accepted and record.get("accepted", False)
        campaign_note = arms_mod.render_campaign_faults(records)
        if campaign_note:
            print(campaign_note)
        print(f"Records appended to {arms_mod.RUNS_BASE / 'runs.jsonl'}")
        if not accepted:
            sys.exit(2)
    elif getattr(args, "eval_command", None) == "corpus":
        _cmd_eval_corpus(args)
    elif getattr(args, "eval_command", None) == "rescore":
        from thalamus.eval.rescore import (
            append_revisions,
            apply_outcomes,
            load_records,
            memo_echo_outcomes,
            render_rescore,
            rescore_records,
        )

        records = load_records(args.runs)
        if not records:
            print("No run records found — nothing to re-score.", file=sys.stderr)
            sys.exit(1)
        if args.memo_echo:
            outcomes = memo_echo_outcomes(records, tasks_base=args.config)
        else:
            outcomes = rescore_records(
                records,
                repo=(args.repo or Path.cwd()).resolve(),
                tasks_base=args.config,
                force=args.force,
            )
        if args.write:
            revisions = apply_outcomes(records, outcomes)
            append_revisions(revisions, args.runs)
        print(render_rescore(outcomes, wrote=args.write))
        if args.write:
            print(
                f"\nAppended {len(revisions)} revision(s). Nothing already written "
                "moved; the superseded bodies stay on disk and readers take the "
                "head revision per run."
            )
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

    try:
        sys.exit(run(dry_run=args.dry_run, check_only=args.check, harness=args.harness,
                     uninstall_mode=args.uninstall, assume_yes=args.yes))
    except RuntimeError as e:
        print(f"Init failed: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_rescope(args):
    from thalamus.harness.rescope import run

    sys.exit(run(args.session, args.scope, reason=args.reason,
                 dry_run=args.dry_run, allow_distilled=args.allow_distilled,
                 other_session=args.other_session))


def _cmd_pin(args):
    from thalamus.harness.pin import PROJECT_ROOT, launch

    try:
        launch(args.scope, PROJECT_ROOT, room=args.room, harness=args.harness)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"Pin failed: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_spawn(args):
    import subprocess

    from thalamus.harness.pin import PROJECT_ROOT, spawn

    cwd = args.dir if args.dir is not None else PROJECT_ROOT
    try:
        spawn(args.scope, cwd, session=args.session, room=args.room,
              harness=args.harness)
    except (FileNotFoundError, ValueError, RuntimeError, subprocess.CalledProcessError) as e:
        print(f"Spawn failed: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_roster(args):
    from thalamus.harness.pin import PROJECT_ROOT, roster

    try:
        roster(PROJECT_ROOT, full=getattr(args, "all", False), room=args.room)
    except (ValueError, RuntimeError) as e:
        print(f"Roster failed: {e}", file=sys.stderr)
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
        # parent's prefix survived at 38 minutes (lab/049). The ages above are the
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
    # for a different question (docs/02).
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
                # only time it is still free to change (eval/randomization.py).
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


def _cmd_visualize(args):
    session = None
    graph = None
    if args.file is not None:
        data = _load_file(args.file)
        try:
            session = SessionGraph(**data)
        except Exception as e:
            print(f"Validation failed: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            graph = connect(getattr(args, "url", DEFAULT_URL))
        except Exception as e:
            print(f"Unable to connect to persisted memory graph: {e}", file=sys.stderr)
            sys.exit(1)

    port = args.port or _available_port(args.host)
    viewer_url = f"http://{args.host}:{port}"
    print(f"Thalamus viewer: {viewer_url}")
    print("Press Ctrl+C to stop.")

    if not args.no_open:
        threading.Timer(0.4, webbrowser.open, args=(viewer_url,)).start()

    try:
        uvicorn.run(
            create_app(session, graph),
            host=args.host,
            port=port,
            log_level="warning",
        )
    finally:
        if graph is not None:
            close_connection(graph)


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

    from thalamus.console.server import Config, serve
    from thalamus.harness.pin import PROJECT_ROOT

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
        voice_url=args.voice,
        fetch_interval_s=max(0.0, args.fetch_interval) * 60,
    )
    if subprocess.run(["tmux", "has-session", "-t", cfg.session],
                      capture_output=True).returncode != 0:
        # Serve anyway: the console showing an empty roster and a working spawn
        # button is a better answer than a refusal the operator reads on a phone.
        print(f"! no tmux session `{cfg.session}` yet — start one with `thalamus roster`, "
              "or use the console's ＋ button once it's up.")
    print("Press Ctrl+C to stop.")
    serve(cfg, host=args.host, port=args.port)


def _available_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _load_file(path: Path) -> dict:
    text = path.read_text()
    if path.suffix in (".yaml", ".yml"):
        return yaml.safe_load(text)
    return json.loads(text)


if __name__ == "__main__":
    main()
