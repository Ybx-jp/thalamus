"""The surfaces this plugin adds to core: `spawn`, `room`, `ceremony`, `dispatch` and
`console`, the `--room` option on core's `pin`, `--by-occasion` on `eval cost`, and the
room-member rows of `contract check --capabilities`.

Registered through core's hooks (`thalamus.plugins`). `register_commands` runs on every
`thalamus` invocation, so this module builds parsers and nothing else; the handlers in
`commands.py` import what they drive only when their command runs.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path

from thalamus.harness import agents
from thalamus.plugins import hookimpl
from thalamus_console import commands as handlers
from thalamus_console.ceremonies import CEREMONY_KINDS, COMPARATOR_ARMS, RESOLUTION_OUTCOMES
from thalamus_console.server import DEFAULT_PORT as CONSOLE_PORT
from thalamus_console.windows import ROSTER_SESSION

ROOM_FLAG_HELP = (
    "Launch into this room — a private config dir (~/.thalamus/rooms/<room>/) that "
    "partitions peer discovery, so members see only each other. Created on first "
    "use. Default: $THALAMUS_ROOM, else no room."
)


def _bound(handler, parser):
    """`handler` with its own command's parser, for the help it prints when no
    subcommand is named."""
    @functools.wraps(handler)
    def run(args):
        return handler(args, parser)
    return run


@hookimpl
def register_commands(subparsers, commands) -> None:
    commands["pin"].add_argument("--room", default=None, help=ROOM_FLAG_HELP)
    eval_cost_parser = commands["eval cost"]
    eval_cost_parser.add_argument(
        "--by-occasion", action="store_true", dest="by_occasion",
        help="Attribute room members' burn to the ceremony occasion it happened "
             "inside, with each room's out-of-occasion burn beside it",
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
        "--harness", choices=agents.LAUNCHABLE, default="claude", help="Which CLI to pin (default: claude). The charter rides `--agent` on claude and `--profile` on codex; `cursor` has no carrier for one, so its pin routes and is bounded without it — see contract/pinning.py for what `pinned` covers on each. codex and cursor both take the scope as an argv `env` prefix as well, which is what survives `respawn-window` (on codex `--profile` restores the charter but tells the hooks nothing). Both also default to their own resting permission posture rather than to `auto`, so a pinned session can stop at a prompt: the console's posture panel is where that is changed, and harness/launcher.py records what each rung gives up."
    )
    spawn_parser.set_defaults(plugin_run=handlers.spawn)

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
    room_parser.set_defaults(plugin_run=_bound(handlers.room, room_parser))

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
    ceremony_parser.set_defaults(plugin_run=_bound(handlers.ceremony, ceremony_parser))
    dispatch_parser.set_defaults(plugin_run=handlers.dispatch)
    console_parser.set_defaults(plugin_run=handlers.console)


@hookimpl
def claim_command(command, args):
    if command == "pin" and (args.room or os.environ.get("TMUX")):
        handlers.pin_elsewhere(args)
        return True
    if command == "eval cost" and args.by_occasion:
        handlers.occasion_cost(args)
        return True
    return None


@hookimpl
def capability_rows():
    from thalamus_console.room_capabilities import check_rooms

    # What a dispatcher can establish about a member before writing to it. Kept apart
    # from core's pinning rows because a pinned session and an addressable room member
    # are different claims, and the record that carried both reported one wrongly.
    return [(f"{row.label} [{row.state.value}]", outcome, detail)
            for row, outcome, detail in check_rooms()]
