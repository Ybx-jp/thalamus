"""The handlers behind the commands `plugin.py` registers, one per command.

Each imports what it drives when it runs, so a `thalamus` invocation that runs none of
them pays only for the parsers.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from thalamus.harness import agents


def pin_elsewhere(args) -> None:
    """`thalamus pin` in a room, or from inside tmux: the session opens in a window."""
    from thalamus.contract.paths import default_project_dir
    from thalamus_console.windows import launch

    launch(args.scope, default_project_dir(), room=args.room, harness=args.harness)


def occasion_cost(args) -> None:
    """`thalamus eval cost --by-occasion`."""
    from thalamus_console.occasion_cost import occasion_burn

    since = (
        date.fromisoformat(args.since) if args.since else date.today() - timedelta(days=14)
    )
    print(occasion_burn(since).render())


def spawn(args):
    import subprocess

    from thalamus.contract.paths import default_project_dir
    from thalamus_console.windows import spawn

    cwd = args.dir if args.dir is not None else default_project_dir()
    try:
        spawn(args.scope, cwd, session=args.session, room=args.room,
              harness=args.harness)
    except (FileNotFoundError, ValueError, RuntimeError, subprocess.CalledProcessError) as e:
        print(f"Spawn failed: {e}", file=sys.stderr)
        sys.exit(1)


def room(args, parser):
    from thalamus_console import rooms
    from thalamus.harness import pin

    if args.room_command == "create":
        try:
            config = rooms.ensure_room(args.room)
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
        host = rooms.host_config_dir()
        for name in rooms.ROOM_LINKED:
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
        copied = config / rooms.ROOM_COPIED
        print(f"  {rooms.ROOM_COPIED:22} {'copy' if copied.is_file() else 'MISSING'}")
        return

    if args.room_command == "list":
        names = rooms.rooms()
        if not names:
            print("No rooms. `thalamus spawn <scope> --room <name>` opens one.")
            return
        for name in names:
            config = pin.room_config_dir(name)
            live = len(list((config / "sessions").glob("*.json"))) \
                if (config / "sessions").is_dir() else 0
            print(f"{name:20} {live} live member(s)   {config}")
        return

    parser.parse_args(["--help"])


def ceremony(args, parser):
    from thalamus_console import ceremonies

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

    parser.parse_args(["--help"])


def dispatch(args):
    from thalamus_console import dispatch as dispatch_mod

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


def console(args):
    import shutil
    import subprocess

    from thalamus_console.server import FAVORITES_STORE, Config, PortInUse, serve
    from thalamus_console import tmux
    from thalamus.contract.paths import default_project_dir

    if not shutil.which("tmux"):
        print("The console needs tmux — it drives the pinned roster's windows.",
              file=sys.stderr)
        sys.exit(1)

    cfg = Config(
        session=args.session,
        project_root=args.project_root or default_project_dir(),
        favorites=args.dir,
        scan_roots=args.scan,
        # Named here rather than defaulted inside Config: this is a path on this
        # operator's box, and it is `thalamus console` that knows it is serving that
        # box (A0151, cites-as-live).
        favorites_store=FAVORITES_STORE,
        services=args.service,
        frames_file=args.frames,
        fetch_interval_s=max(0.0, args.fetch_interval) * 60,
        allowed_origins=args.allow_origin,
    )
    if subprocess.run(tmux.argv("has-session", "-t", cfg.session),
                      capture_output=True).returncode != 0:
        # Only a missing session is created. An existing one is bridged as it stands:
        # `--session` may name any tmux session, and the console adds nothing to one
        # it did not create until the operator asks (roster sync, ＋).
        from thalamus_console.windows import WindowDied, ensure_anchor

        try:
            ensure_anchor(Path(cfg.project_root), session=cfg.session)
        except (ValueError, RuntimeError, subprocess.CalledProcessError) as e:
            # Serve anyway: the console showing an empty roster and a working spawn
            # button is a better answer than a refusal the operator reads on a phone.
            print(f"! could not open `main` in tmux session `{cfg.session}`: {e}",
                  file=sys.stderr)
            # A window whose command never execs prints nothing, so there is no
            # epitaph to quote and the cause is almost always the binary.
            if isinstance(e, WindowDied):
                print(f"Check that `{agents.cli_for('claude').binary} --version` works "
                      "on this process's PATH.", file=sys.stderr)
    try:
        serve(cfg, host=args.host, port=args.port)
    except PortInUse as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
