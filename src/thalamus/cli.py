"""CLI for Thalamus operations."""

from __future__ import annotations

import argparse
import json
import logging
import secrets
import socket
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn
import yaml

from thalamus.substrate.schema import SessionGraph
from thalamus.archive import archive_dir
from thalamus.contract.conformance import check_session
from thalamus.contract.ontology import MAIN_SCOPE
from thalamus.eval.rake_audit import SAMPLE_SIZE
from thalamus.harness import extraction, transcripts
from thalamus.harness.bootstrap import bootstrap_project
from thalamus.plane.web import create_app
from thalamus.substrate.snapshot import DEFAULT_SNAPSHOT_PATH, snapshot, snapshot_quietly
from thalamus.substrate.writer import DEFAULT_URL, close_connection, connect, write_session


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
        "bootstrap", help="Build memory from retained Claude Code session transcripts"
    )
    bootstrap_parser.add_argument(
        "projects",
        nargs="*",
        help="Claude Code project dir names (e.g. -home-ybx-code-thalamus). "
        "Omit to list what is available.",
    )
    bootstrap_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
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
        help="Claude Code project dir names. Omit to list what is available.",
    )
    extract_parser.add_argument("--url", default=DEFAULT_URL, help="Gremlin endpoint")
    extract_parser.add_argument(
        "--scope", default=MAIN_SCOPE, help="Scope the sessions are pinned to (default: main)"
    )
    extract_parser.add_argument(
        "--model",
        default=extraction.DEFAULT_MODEL,
        help=f"Model for claude -p (default: {extraction.DEFAULT_MODEL}). The archive is "
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
        "--scope", default="literature", help="Expert scope; needs a manifest in config/experts/"
    )
    ingest_parser.add_argument("--feed", default="manual", help="Feed identity (default: manual)")
    ingest_parser.add_argument(
        "--model", default=None, help="Extraction model for claude -p (default: sonnet)"
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

    eval_tasks_parser = eval_sub.add_parser(
        "tasks",
        help="Validate and list the counterfactual task battery (config/tasks/)",
    )
    eval_tasks_parser.add_argument(
        "--config", type=Path, default=None,
        help="Config root holding tasks/ (default: repo config/)",
    )

    eval_rescore_parser = eval_sub.add_parser(
        "rescore",
        help="Apply the contamination and history-reach detectors backwards over "
        "campaigns that ran before they existed",
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
        help="memory-on | memory-off | scoping-degraded:<scope>; repeatable, runs in "
        "the order given (default: memory-on then memory-off)",
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

    rescope_parser = subparsers.add_parser(
        "rescope", help="Redirect a session's distillation scope (before it distills)"
    )
    rescope_parser.add_argument("session", help="Session ID (prefix ok)")
    rescope_parser.add_argument("scope", help="Scope to distill into (`main` or a manifest)")
    rescope_parser.add_argument("--reason", default="", help="Why, for the ledger record")
    rescope_parser.add_argument(
        "--dry-run", action="store_true", help="Report the correction without appending it"
    )
    rescope_parser.add_argument(
        "--allow-distilled", action="store_true",
        help="Override the already-distilled refusal. Forks the session's identity across "
             "scopes (vertex IDs include scope); the original vertex is left stale."
    )

    pin_parser = subparsers.add_parser(
        "pin", help="Launch a claude session pinned to an expert scope"
    )
    pin_parser.add_argument("scope", help="Expert scope (a config/experts manifest, or `main`)")

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

    roster_parser = subparsers.add_parser(
        "roster", help="Bring up the control plane (the `main` anchor; --all for every expert)"
    )
    roster_parser.add_argument(
        "--all", action="store_true",
        help="Open one window per expert manifest (legacy full roster)"
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
    elif args.command == "visualize":
        _cmd_visualize(args)
    elif args.command == "pulse":
        _cmd_pulse(args)
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


def _cmd_bootstrap(args):
    available = transcripts.discover()
    if not available:
        print(f"No Claude Code transcripts found under {transcripts.CLAUDE_PROJECTS}", file=sys.stderr)
        sys.exit(1)

    if not args.projects:
        print(f"Transcripts under {transcripts.CLAUDE_PROJECTS}:\n")
        for name, paths in sorted(available.items(), key=lambda kv: -len(kv[1])):
            size_mb = sum(p.stat().st_size for p in paths) / 1_000_000
            print(f"  {len(paths):>3} transcripts  {size_mb:>6.1f} MB  {name}")
        print("\nBootstrap them with (note the `--`; the names start with a dash):")
        print("  thalamus bootstrap -- <project-dir> [<project-dir> ...] [--write]")
        print(f"Archive: {archive_dir()}  (outside the repo, deliberately)")
        return

    unknown = [p for p in args.projects if p not in available]
    if unknown:
        print(f"Unknown project dir(s): {', '.join(unknown)}", file=sys.stderr)
        sys.exit(1)

    graph = connect(args.url) if args.write else None
    all_secrets: dict[str, int] = {}
    written = skipped = rejected = 0
    nodes = 0

    try:
        for project in args.projects:
            results = bootstrap_project(project, scope=args.scope)
            print(f"\n=== {project} ({len(results)} transcripts) ===")
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


def _cmd_extract(args):
    """Stage 2 of the bootstrap: model-extracted Claims and Threads.

    Sessions are processed chronologically so a thread opened in March can be resolved by
    a session from April — the same replay semantics a live agent would have produced.
    """
    from thalamus.archive import read_archived
    from thalamus.contract.conformance import prune_orphan_artifacts
    from thalamus.contract.ontology import vid

    available = transcripts.discover()
    if not args.projects:
        print("Specify project dir(s); `thalamus bootstrap` lists what is available.")
        return

    unknown = [p for p in args.projects if p not in available]
    if unknown:
        print(f"Unknown project dir(s): {', '.join(unknown)}", file=sys.stderr)
        sys.exit(1)

    graph = connect(args.url)
    extracted = skipped = failed = 0
    total_cost = 0.0

    try:
        # Chronological across all requested projects: threads resolve forward in time.
        parsed = []
        for project in args.projects:
            for path in available[project]:
                facts = transcripts.parse(path)
                if facts.user_turns == 0:
                    continue
                parsed.append(facts)
        parsed.sort(key=lambda f: (f.started_at is None, f.started_at))

        if args.session:
            parsed = [
                f for f in parsed if any(f.session_id.startswith(s) for s in args.session)
            ]
        if args.limit:
            parsed = parsed[: args.limit]

        print(f"{len(parsed)} sessions to extract (model: {args.model})")

        for facts in parsed:
            name = facts.session_id[:8]
            session_vid = vid("Session", facts.session_id, args.scope)

            if not args.force and _session_has_claims(graph, session_vid):
                skipped += 1
                print(f"  · {name}  already extracted — skipping (--force to redo)")
                continue

            entry, _ = transcripts.retain(facts.path)
            base = transcripts.to_session_graph(
                facts,
                content_hash=entry.content_hash,
                uri=entry.uri,
                byte_size=entry.byte_size,
                scope=args.scope,
            )

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
                run = extraction.run_extraction(prompt, model=args.model)
                data = extraction.parse_extraction(run.text)
                session = extraction.merge_extraction(base, data)
                # The laundering floor (docs/05): claims resting on the transcript's
                # external ingress keep third-party trust, marked or not.
                session = extraction.apply_ingress_floor(session, facts.external_texts)
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
            print(f"  + {name}  {counts}  ${run.cost_usd:.2f}  {session.summary[:48]}")

    finally:
        if args.write and extracted:
            _persist(graph)
        close_connection(graph)

    print(
        f"\n{extracted} extracted, {skipped} skipped, {failed} failed; "
        f"model cost ${total_cost:.2f}"
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
        batch, run = ingest_mod.ingest(
            args.location,
            scope=args.scope,
            feed=args.feed,
            model=args.model or extraction_mod.DEFAULT_MODEL,
            title=args.title,
            known_entities=known_entities,
        )
    except (ingest_mod.IngestError, extraction_mod.ExtractionError) as e:
        print(f"Ingest failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Retained: {batch.source.uri} ({batch.source.byte_size:,} bytes)")
    print(f"Extracted: {len(batch.claims)} claims, {len(batch.entities)} entities "
          f"(${run.cost_usd:.2f})")
    print(f"  {batch.source.title}")
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


def _cmd_snapshot(args):
    from thalamus.substrate.snapshot import SnapshotError

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


def _cmd_contract(args, contract_parser):
    if getattr(args, "contract_command", None) != "check":
        contract_parser.print_help()
        sys.exit(1)

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
            print(scope_report(graph, scope=args.scope, top=args.top).render())
        finally:
            close_connection(graph)
    elif getattr(args, "eval_command", None) == "cost":
        from datetime import date, timedelta

        from thalamus.eval.cost import cost_report

        since = (
            date.fromisoformat(args.since) if args.since else date.today() - timedelta(days=14)
        )
        project_dir = (args.project_dir or Path.cwd()).resolve()
        print(cost_report(project_dir, since, traces_base=args.traces).render())
    elif getattr(args, "eval_command", None) == "gremlin":
        from thalamus.eval.gremlin import gremlin_report

        print(gremlin_report(traces_base=args.traces, guards_base=args.guards).render())
    elif getattr(args, "eval_command", None) == "rake-audit":
        from thalamus.eval import rake_audit as ra
        from thalamus.eval.rakes import build_rake_report, read_rakes

        if not args.draw and not args.score:
            parser.error("thalamus eval rake-audit needs --draw or --score")

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
                parser.error(f"--score needs the key written at draw time (looked for {key_path})")
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
    elif getattr(args, "eval_command", None) == "recipes":
        from thalamus.eval.gremlin import render_smoke, smoke_recipes

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
        from thalamus.eval.tasks import load_battery, tasks_dir

        tasks, issues = load_battery(args.config)
        if issues:
            print("The battery does not arm until clean — run `thalamus eval tasks`:",
                  file=sys.stderr)
            for issue in issues:
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
        from thalamus.eval.tasks import load_battery

        tasks, issues = load_battery(args.config)
        if issues:
            print("The battery does not arm until clean — run `thalamus eval tasks`:",
                  file=sys.stderr)
            for issue in issues:
                print(f"  - {issue}", file=sys.stderr)
            sys.exit(1)
        by_id = {task.id: task for task in tasks}
        if args.task_id not in by_id:
            print(f"No task `{args.task_id}` (have: {', '.join(sorted(by_id))})",
                  file=sys.stderr)
            sys.exit(1)
        task = by_id[args.task_id]
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
                )
            except arms_mod.SessionFault as exc:
                # Every arm after a session death is void; continuing would only
                # manufacture records that look like data (lab/012, lab/016).
                print(f"\nCAMPAIGN STOPPED — {exc}", file=sys.stderr)
                remaining = [a.spec for a in arm_list[index + 1:]]
                if remaining:
                    print(f"Not run: {', '.join(remaining)}. Check credentials "
                          "and usage limits (`claude -p \"say ok\"`), then "
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
    elif getattr(args, "eval_command", None) == "rescore":
        from thalamus.eval.rescore import (
            apply_outcomes,
            load_records,
            render_rescore,
            rescore_records,
            write_records,
        )

        records = load_records(args.runs)
        if not records:
            print("No run records found — nothing to re-score.", file=sys.stderr)
            sys.exit(1)
        outcomes = rescore_records(
            records,
            repo=(args.repo or Path.cwd()).resolve(),
            tasks_base=args.config,
            force=args.force,
        )
        if args.write:
            changed = apply_outcomes(records, outcomes)
            write_records(records, args.runs)
        print(render_rescore(outcomes, wrote=args.write))
        if args.write:
            print(f"\nStamped {changed} record(s); previous log kept as *.pre-rescore.")
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
        sys.exit(run(dry_run=args.dry_run, check_only=args.check))
    except RuntimeError as e:
        print(f"Init failed: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_rescope(args):
    from thalamus.harness.rescope import run

    sys.exit(run(args.session, args.scope, reason=args.reason,
                 dry_run=args.dry_run, allow_distilled=args.allow_distilled))


def _cmd_pin(args):
    from thalamus.harness.pin import PROJECT_ROOT, launch

    try:
        launch(args.scope, PROJECT_ROOT)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"Pin failed: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_spawn(args):
    import subprocess

    from thalamus.harness.pin import PROJECT_ROOT, spawn

    cwd = args.dir if args.dir is not None else PROJECT_ROOT
    try:
        spawn(args.scope, cwd, session=args.session)
    except (FileNotFoundError, ValueError, RuntimeError, subprocess.CalledProcessError) as e:
        print(f"Spawn failed: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_roster(args):
    from thalamus.harness.pin import PROJECT_ROOT, roster

    try:
        roster(PROJECT_ROOT, full=getattr(args, "all", False))
    except RuntimeError as e:
        print(f"Roster failed: {e}", file=sys.stderr)
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
