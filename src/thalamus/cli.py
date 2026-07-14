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
from thalamus.contract.conformance import validate_connectivity
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
        print(f"Valid. Session: {session.session_id}")
        print(f"  Artifacts:  {len(session.artifacts)}")
        print(f"  Decisions:  {len(session.decisions)}")
        print(f"  Problems:   {len(session.problems)}")
        print(f"  Solutions:  {len(session.solutions)}")
        print(f"  Threads:    {len(session.threads)}")
        print(f"  Thread refs:{len(session.thread_refs)}")

        issues = validate_connectivity(session)
        if issues:
            print("\nConnectivity issues:", file=sys.stderr)
            for issue in issues:
                print(f"  - {issue}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Validation failed: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_schema():
    print(json.dumps(SessionGraph.model_json_schema(), indent=2))


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
