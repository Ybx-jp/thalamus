"""CLI for Thalamus operations."""

from __future__ import annotations

import argparse
import json
import logging
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
from thalamus.harness import extraction, transcripts
from thalamus.harness.bootstrap import bootstrap_project
from thalamus.plane.web import create_app
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
    elif args.command == "visualize":
        _cmd_visualize(args)
    else:
        parser.print_help()
        sys.exit(1)


def _cmd_write(args):
    data = _load_file(args.file)
    session = SessionGraph(**data)
    g = connect(args.url)
    try:
        vid = write_session(g, session)
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
            )

            try:
                run = extraction.run_extraction(prompt, model=args.model)
                data = extraction.parse_extraction(run.text)
                session = extraction.merge_extraction(base, data)
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
            counts = (
                f"{len(session.claims()):>2} claims  {len(session.threads)} threads  "
                f"{len(session.thread_refs)} refs"
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
