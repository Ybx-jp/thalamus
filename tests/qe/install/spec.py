"""The install matrix, as data: what a cell is, what it runs, and what must hold.

Deliberately dependency-free — stdlib only, no `thalamus` import, no host-only
module. This file is copied verbatim into the guest, so anything it imports would
have to exist on a machine that has never seen the project. That constraint is the
whole reason the spec is data rather than code reaching into the running system:
the oracle has to be readable on both sides of the boundary.

The vocabulary mirrors `tests/qe/model.py` rather than inventing a second one. A
`Check` here becomes a `CaseResult` on the host, so VM results land in the same
ledger and the same `expectations.json` triage as every other case.

## What a cell is

A cell is one (image x config) pair booted from a golden image that has never seen
Thalamus, running the sequence in `STEPS` in order. The config is not decoration:
each variant reproduces the precondition of a filed defect, so the matrix's first
run is expected to be *red in specific named places*. A green matrix against a tree
with open install defects means the harness is broken, not the install.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Phase(str, Enum):
    """Where in the documented sequence a check is evaluated.

    Named for the command in `docs/getting-started.md` that precedes it, so a
    failure names the step a user would have been on when they hit it.
    """

    PREFLIGHT = "preflight"          # before anything: the box as delivered
    SYNCED = "synced"                # after `uv sync`
    GRAPH_STARTING = "graph-starting"  # after `docker compose up -d`, before ready
    GRAPH_READY = "graph-ready"      # once the graph answers a query
    CHECKED = "checked"              # after `thalamus init --check`, pre-install
    INSTALLED = "installed"          # after `thalamus init`
    REINSTALLED = "reinstalled"      # after a second `thalamus init`
    MOVED = "moved"                  # after the checkout is renamed
    CONSOLE = "console"              # with `thalamus console` serving
    UNINSTALLED = "uninstalled"      # after `thalamus init --uninstall`


class Severity(str, Enum):
    """Whether a failed check falsifies the milestone promise or merely annoys.

    BLOCKS means the documented sequence did not produce a working install.
    DEGRADES means it worked but a stated guarantee did not hold.
    """

    BLOCKS = "blocks"
    DEGRADES = "degrades"


@dataclass(frozen=True)
class Check:
    """One assertion, evaluated in the guest.

    `issue` is not bookkeeping. Every check here exists because a defect was found
    by reading, and the number is how a red result is distinguished from a
    regression: a check that goes red naming issue #53 has reproduced a known
    defect, and one that goes red naming nothing has found a new one.

    `control` is the positive control, and it is mandatory for any check asserting
    an absence. "Nothing was written" and "the step never ran" are the same
    observation otherwise, and the second one passes forever. It names a condition
    that MUST be observably true for the check's evidence to be meaningful.

    `fixed` is what stops `issue` becoming permanent absolution. An issue number
    absolves a red result — the runner reads it as "reproduced something already
    filed" and exits 0 — and an untouched tag goes on absolving long after the
    defect is gone, so a regression at that site, or an oracle that has drifted off
    the repaired behaviour, lands as an expected red nobody reads. Flip this in the
    same change that closes the issue, exactly as a known-red entry in
    `tests/qe/expectations.json` is deleted in the change that fixes its defect.
    Once set, the check is expected to PASS: a failure naming a fixed issue is
    reported as a regression and exits 1, not as a known defect.
    """

    name: str
    phase: Phase
    severity: Severity
    summary: str
    # The GitHub issue whose defect this reproduces, or 0 for a check guarding a
    # property no filed defect covers.
    issue: int = 0
    control: str = ""
    #: The issue is closed and this check must now pass. See the class docstring.
    fixed: bool = False


@dataclass(frozen=True)
class Step:
    """One command in the documented sequence, quoted from the docs that teach it.

    `doc` is the file:line a user would have read. When a step's real behaviour and
    its `doc` disagree, that disagreement is the finding — several already-filed
    issues are exactly this shape.
    """

    phase: Phase
    argv: list[str]
    doc: str
    # A step may fail without ending the run: the matrix deliberately includes
    # cells where a step is expected to fail, and the failure is the observation.
    may_fail: bool = False


@dataclass(frozen=True)
class Config:
    """A named perturbation of the box, applied before the sequence runs.

    Each variant is the precondition of a filed defect. `removes` names binaries
    taken off PATH; `env` is applied to every command in the sequence; `skip_steps`
    drops phases (used by the graph-not-started variant).
    """

    name: str
    summary: str
    issue: int = 0
    #: The issue this variant was built to trigger is closed. The variant stays — a
    #: box without `jq` or a moved checkout is a real condition worth running — but
    #: it is no longer a defect the matrix expects to reproduce.
    fixed: bool = False
    removes: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    unset: tuple[str, ...] = ()
    skip_steps: tuple[Phase, ...] = ()


# --------------------------------------------------------------------------------------
# The documented sequence. Quoted from README.md and docs/getting-started.md; the
# milestone promise is "clone, docker compose up, uv sync, thalamus init, thalamus
# console", and the order below is the order those docs put them in.
# --------------------------------------------------------------------------------------

STEPS: tuple[Step, ...] = (
    Step(Phase.SYNCED, ["uv", "sync", "--extra", "dev"],
         doc="docs/getting-started.md:38"),
    Step(Phase.GRAPH_STARTING, ["docker", "compose", "up", "-d"],
         doc="README.md quick start / docker-compose.yml"),
    # Deliberately BEFORE the graph is confirmed ready. The window between "the port
    # accepts a connection" and "the server answers a query" is issue #55, and a
    # sequence that waits politely would never observe it.
    Step(Phase.CHECKED, ["uv", "run", "thalamus", "init", "--check"],
         doc="docs/getting-started.md:112", may_fail=True),
    # `--yes` is how a cell answers the consent prompt, and it is not a departure from
    # the documented sequence — it is the only way to run it here. getting-started:60
    # says `uv run thalamus init`, and a user at a terminal is asked to confirm before
    # anything is written outside the checkout. A cell has no tty, so bare `init` prints
    # "stdin is not a terminal — re-run with --yes" and exits 1 having written nothing.
    #
    # Measured 2026-08-21: without it, INSTALLED and REINSTALLED both exited 1 in about
    # a second, UNINSTALLED then exited 0 reporting nothing to remove, and every phase
    # after the install was reading a box that had never been installed to. That is the
    # shape to watch for — a sequence that fails open into measuring the wrong thing.
    Step(Phase.INSTALLED, ["uv", "run", "thalamus", "init", "--yes"],
         doc="docs/getting-started.md:60", may_fail=True),
    Step(Phase.REINSTALLED, ["uv", "run", "thalamus", "init", "--yes"],
         doc="idempotency: re-running init after a git pull that adds a skill"),
    Step(Phase.UNINSTALLED, ["uv", "run", "thalamus", "init", "--uninstall"],
         doc="README.md:82", may_fail=True),
)


# --------------------------------------------------------------------------------------
# What the box must already have. Quoted from docs/getting-started.md:9-15.
# --------------------------------------------------------------------------------------

#: Prerequisites that never appear as a step's own command, so nothing in `STEPS`
#: would notice their absence. `jq` is the sharp one: the hook layer parses its stdin
#: with it and exits silently without it, so a box missing it does not fail loudly —
#: it installs and then quietly does nothing, which is a cell reporting on a box the
#: docs do not describe.
PREREQUISITES: tuple[str, ...] = ("jq", "tmux")

#: Distillation shells out to whichever of these is present, so the requirement is
#: "at least one", not "all three".
AGENT_CLIS: tuple[str, ...] = ("claude", "agent", "codex")


# --------------------------------------------------------------------------------------
# Config variants. Each reproduces a filed defect's precondition.
# --------------------------------------------------------------------------------------

CONFIGS: tuple[Config, ...] = (
    Config("baseline",
           "Everything present. The documented happy path, and the control for "
           "every other variant in the column."),
    Config("no-jq",
           "`jq` off PATH. getting-started promises --check exits 0 before install; "
           "three hard checks fail and two print an X beside the word 'skipped'.",
           issue=58, fixed=True, removes=("jq",)),
    Config("no-agent-cli",
           "No `claude` on PATH at init time. The MCP registration is SKIPPED into "
           "the actions list, verify() has no check for it, and init exits 0.",
           issue=53, fixed=True, removes=("claude",)),
    Config("no-config-dir",
           "THALAMUS_CONFIG_DIR unset, i.e. what a clean clone actually has: five "
           "tracked manifests rather than the operator's nine.",
           issue=49, fixed=True, unset=("THALAMUS_CONFIG_DIR",)),
    Config("graph-not-started",
           "`thalamus init` run before `docker compose up -d`. The readable "
           "diagnosis must reach the user rather than a transport error.",
           issue=17, fixed=True, skip_steps=(Phase.GRAPH_STARTING, Phase.GRAPH_READY)),
    Config("moved-checkout",
           "The checkout is renamed after a successful init, which is what an "
           "ordinary upgrade looks like. Every later --check must name the "
           "mismatch rather than printing the healthy-install text.",
           issue=52, fixed=True),
)


# --------------------------------------------------------------------------------------
# The oracle.
# --------------------------------------------------------------------------------------

CHECKS: tuple[Check, ...] = (
    # ---- preflight: the box really has never seen the project -------------------
    Check("golden-image-has-no-thalamus-artifact", Phase.PREFLIGHT, Severity.BLOCKS,
          "No ~/.thalamus, no ~/.claude/skills entry, no thalamus on PATH before the "
          "sequence starts. The property under test is a machine that has never seen "
          "the project, and a golden image that quietly carries one invalidates every "
          "result in the cell.",
          control="the same probe must report PRESENT after the INSTALLED phase, or "
                  "it is looking at the wrong paths and would pass on any image"),
    Check("host-graph-is-unreachable", Phase.PREFLIGHT, Severity.BLOCKS,
          "A TCP connect to the host's graph endpoint from inside the guest must be "
          "refused. This is the operator's absolute constraint made mechanical: not "
          "'we point somewhere else' but 'the wrong target cannot be reached'.",
          control="the same probe against the cell's OWN graph must succeed once "
                  "GRAPH_READY, or the probe cannot distinguish refused from broken"),

    # ---- synced -----------------------------------------------------------------
    Check("cli-exists-after-sync", Phase.SYNCED, Severity.BLOCKS,
          "`.venv/bin/thalamus` exists and reports a version. getting-started:41 "
          "states the CLI is here and not on PATH."),

    # ---- the readiness window ---------------------------------------------------
    Check("starting-graph-is-not-reported-as-absent", Phase.GRAPH_STARTING,
          Severity.DEGRADES,
          "In the window where the port accepts a connection but the JVM does not yet "
          "answer, the diagnosis must not tell the user to start a container that is "
          "already running.",
          issue=55, fixed=True,
          control="the window must be observed at all — if the first probe already "
                  "answers queries, this cell proves nothing and must report SKIPPED "
                  "rather than pass"),

    Check("graph-down-diagnosis-reaches-the-user", Phase.CHECKED, Severity.BLOCKS,
          "With no graph running, the user must get the readable diagnosis naming the "
          "compose command, not a raw transport error relayed from the driver.",
          issue=17, fixed=True,
          control="under the baseline variant, where the graph IS running, the same "
                  "probe must NOT produce that diagnosis — otherwise the check "
                  "passes on a box that always prints it"),

    # ---- pre-install check ------------------------------------------------------
    Check("check-exits-zero-before-install", Phase.CHECKED, Severity.DEGRADES,
          "getting-started:112 promises --check is safe before installing and exits 0. "
          "Under the no-jq variant it exits 1.",
          issue=58, fixed=True),
    Check("no-failure-marker-beside-the-word-skipped", Phase.CHECKED, Severity.DEGRADES,
          "The legend at getting-started:105 defines the failure marker as something "
          "present and wrong. A check that could not run for want of a prerequisite is "
          "a third state and must not borrow that marker.",
          issue=58, fixed=True,
          control="the run's output must carry the marker vocabulary at all — at "
                  "least one line bearing a pass, pending or failure marker. Without "
                  "that, a run whose output format changed entirely reports no "
                  "offending pairing and passes having read nothing"),

    # ---- installed --------------------------------------------------------------
    Check("init-exits-zero-on-a-fresh-box", Phase.INSTALLED, Severity.BLOCKS,
          "The documented install completes."),
    Check("claude-mcp-registration-is-verified", Phase.INSTALLED, Severity.BLOCKS,
          "verify() must report on whether the Claude Code MCP server registered. "
          "Today it checks cursor and codex and not this one, so a box without the "
          "CLI installs 'successfully' with no memory tools and no failure reported.",
          issue=53, fixed=True,
          control="under the baseline variant the same check must find a REGISTERED "
                  "state, or it is asserting on a field that never populates"),
    Check("hooks-are-armed-and-resolvable", Phase.INSTALLED, Severity.BLOCKS,
          "Every hook command written into settings.json resolves to a file that "
          "exists and is executable."),
    Check("skills-are-linked", Phase.INSTALLED, Severity.BLOCKS,
          "Every shipped skill resolves through its user-scope link."),
    Check("pending-items-name-a-command-that-can-clear-them", Phase.INSTALLED,
          Severity.DEGRADES,
          "A pending item states the command that installs it. On a box without the "
          "codex CLI that command cannot ever clear it, so the run closes by telling "
          "the user to repeat what they just did.",
          issue=54, fixed=True,
          control="re-running init must clear at least one OTHER pending item in the "
                  "same run, or the check cannot distinguish 'this item is stuck' "
                  "from 'init clears nothing'"),
    Check("clean-clone-manifest-count-is-what-the-cli-sees", Phase.INSTALLED,
          Severity.DEGRADES,
          "With THALAMUS_CONFIG_DIR unset, the scopes the CLI resolves must be the "
          "manifests a clean clone actually tracks. The operator's box resolves nine "
          "from a private repo; a clone has five, and nothing reports the difference.",
          issue=49, fixed=True,
          control="the same probe under an explicitly-set THALAMUS_CONFIG_DIR must "
                  "resolve a DIFFERENT count, or it is not reading the override at "
                  "all and would report the same number either way"),

    # ---- idempotency ------------------------------------------------------------
    Check("second-init-does-not-duplicate-wiring", Phase.REINSTALLED, Severity.BLOCKS,
          "Running init twice leaves one hook set, not two. The strip-then-write path "
          "identifies our own hooks by substring, and anything that breaks that match "
          "turns every re-run into an append.",
          control="the first init must have written the wiring at all — compare "
                  "counts, never assert only that the second run added nothing"),

    # ---- moved checkout ---------------------------------------------------------
    Check("moved-checkout-is-named-not-denied", Phase.MOVED, Severity.BLOCKS,
          "After the checkout moves, --check must name the stale registration. The "
          "detail string currently takes the truthy branch and prints the text for a "
          "healthy install beside a failing check.",
          issue=52, fixed=True),

    # ---- console ----------------------------------------------------------------
    Check("console-serves-its-shell", Phase.CONSOLE, Severity.BLOCKS,
          "The console binds through its real entry point and the page a user opens "
          "returns 200. No existing test starts it successfully or fetches that page.",
          issue=50, fixed=True,
          control="a path the server does not serve must return 404 in the same "
                  "probe. A server answering 200 for everything would otherwise "
                  "satisfy every asset assertion in this phase"),
    Check("precached-assets-are-all-present", Phase.CONSOLE, Severity.BLOCKS,
          "Every entry in the service worker's shell list resolves. The worker fails "
          "installation as a whole if any one 404s.",
          issue=48, fixed=True),

    # ---- uninstall --------------------------------------------------------------
    Check("uninstall-leaves-no-dangling-link", Phase.UNINSTALLED, Severity.DEGRADES,
          "Uninstall identifies its own links by resolving them against currently "
          "shipped skills, so a link whose target was renamed is neither removed nor "
          "reported.",
          issue=59, fixed=True,
          control="uninstall must have removed something — a run that removes zero "
                  "links trivially leaves zero dangling ones"),
)


# --------------------------------------------------------------------------------------
# Timeouts. Enforced in the guest with `timeout <n>` around each step, and read on the
# host to size the per-cell ceiling.
# --------------------------------------------------------------------------------------

#: Seconds per step. These are starting values, and two of them are the only numbers
#: here that were measured rather than reasoned: `uv sync --extra dev` against a clean
#: archive with an empty cache is 2.1 s and 75 MB RSS on the host, and the long pole is
#: the graph image — `tinkerpop/gremlin-server:3.7.3` is 600 MB, so a fresh cell pulls
#: ~250-300 MB and decompresses it on 2 vCPU.
#:
#: The rule that replaces the guesses needs no separate probe, because the first green
#: cell IS the probe: every step emits `PHASE <name> START/END <epoch>` on the console.
#: After five green runs, set each to `max(60, ceil(6 * p50))`; alert without failing
#: when a p95 exceeds half its timeout; re-derive after any change to the golden image,
#: the compose file, or machine.slice's CPUWeight.
#:
#: The factor of six is deliberate and loose. Cells run under CPUWeight=20 and are meant
#: to yield to the desktop, so a tight timeout would turn the operator opening a browser
#: into a red matrix.
TIMEOUTS: dict[str, int] = {
    "boot": 180,             # unmeasured on this box; replace with 6 x the first
                             # measured cloud-init completion
    "clone-local": 60,       # 8.51 MiB pack off the seed device
    "clone-https": 180,      # network-bound; a github hiccup is not a Thalamus defect
    "compose-up": 900,       # 600 MB image, 2 vCPU, weighted-down slice
    "graph-ready": 180,      # JVM start on 2 vCPU
    "uv-sync": 300,          # measured at 2.1 s; the floor guards a resolver stall
    "thalamus-init": 120,    # two 60 s subprocess timeouts inside register_mcp
    "asserts": 180,
}

#: The per-cell hard ceiling, in seconds. Passed to virt-install as `--wait` in minutes.
CELL_CEILING_S = 1800


def timeout_key(step: Step) -> str:
    """Map a documented step onto its timeout bucket.

    Lives with the spec rather than with either runner, because both the libvirt
    guest and a hosted-runner driver have to agree on how long a step may take —
    two copies of this mapping would drift into two different sequences wearing
    one name.
    """
    argv = " ".join(step.argv)
    if "docker" in argv and "compose" in argv:
        return "compose-up"
    if "uv sync" in argv:
        return "uv-sync"
    if "thalamus" in argv and "init" in argv:
        return "thalamus-init"
    return "asserts"


def checks_for(phase: Phase) -> tuple[Check, ...]:
    return tuple(c for c in CHECKS if c.phase is phase)


def known_defect_issues() -> frozenset[int]:
    """Issues the matrix is expected to reproduce on the tree as it stands.

    This is the harness's own positive control. A full run that reproduces none of
    these has not found a clean install; it has failed to observe. The runner
    reports it as MALFORMED rather than as a pass.

    `fixed` entries are excluded: they are the defects this tree no longer carries,
    so a run that fails to reproduce them is a run against a repaired tree, which is
    the outcome the work was for.
    """
    return frozenset(c.issue for c in CHECKS if c.issue and not c.fixed) | frozenset(
        c.issue for c in CONFIGS if c.issue and not c.fixed)


def fixed_issues() -> frozenset[int]:
    """Issues whose checks must now PASS. A red one here is a regression."""
    return frozenset(c.issue for c in CHECKS if c.issue and c.fixed) | frozenset(
        c.issue for c in CONFIGS if c.issue and c.fixed)
