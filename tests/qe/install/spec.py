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
    DISTILLED = "distilled"          # after a fixture session ends and is distilled
    REINSTALLED = "reinstalled"      # after a second `thalamus init`
    MOVED = "moved"                  # after the checkout is renamed
    CONSOLE = "console"              # with `thalamus console` serving
    UNINSTALLED = "uninstalled"      # after `thalamus init --uninstall`
    WHEEL = "wheel"                  # the built wheel installed outside the checkout


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
    #: Build the wheel, install it outside the checkout, and probe the installed
    #: artifact after the documented sequence has finished. Off by default because it
    #: costs a build and a second venv in every cell that carries it, and because the
    #: property it reads — what the PACKAGED layout resolves — is the same whichever
    #: box the sequence ran on. `drive.py` runs the phase; `checks.py` reads it.
    builds_a_wheel: bool = False


# --------------------------------------------------------------------------------------
# The documented sequence. Quoted from README.md and docs/getting-started.md; the
# milestone promise is "clone, docker compose up, uv sync, thalamus init, thalamus
# console", and the order below is the order those docs put them in.
# --------------------------------------------------------------------------------------

STEPS: tuple[Step, ...] = (
    Step(Phase.SYNCED, ["uv", "sync", "--extra", "dev"],
         doc="docs/getting-started.md:43"),
    Step(Phase.GRAPH_STARTING, ["docker", "compose", "up", "-d"],
         doc="README.md quick start / docker-compose.yml"),
    # Deliberately BEFORE the graph is confirmed ready. The window between "the port
    # accepts a connection" and "the server answers a query" is issue #55, and a
    # sequence that waits politely would never observe it.
    Step(Phase.CHECKED, ["uv", "run", "thalamus", "init", "--check"],
         doc="docs/getting-started.md:127", may_fail=True),
    # `--yes` is how a cell answers the consent prompt, and it is not a departure from
    # the documented sequence — it is the only way to run it here. getting-started:61
    # says `uv run thalamus init`, and a user at a terminal is asked to confirm before
    # anything is written outside the checkout. A cell has no tty, so bare `init` prints
    # "stdin is not a terminal — re-run with --yes" and exits 1 having written nothing.
    #
    # Measured 2026-08-21: without it, INSTALLED and REINSTALLED both exited 1 in about
    # a second, UNINSTALLED then exited 0 reporting nothing to remove, and every phase
    # after the install was reading a box that had never been installed to. That is the
    # shape to watch for — a sequence that fails open into measuring the wrong thing.
    Step(Phase.INSTALLED, ["uv", "run", "thalamus", "init", "--yes"],
         doc="docs/getting-started.md:61", may_fail=True),
    # may_fail matches INSTALLED: a config that removes a documented prerequisite
    # makes the first init fail legitimately, and the second one fails for the same
    # reason. `second-init-does-not-duplicate-wiring` is control-guarded — it compares
    # hook counts and requires the first init to have written wiring at all — so it
    # degrades to not_evaluated here rather than passing vacuously.
    Step(Phase.REINSTALLED, ["uv", "run", "thalamus", "init", "--yes"],
         doc="idempotency: re-running init after a git pull that adds a skill",
         may_fail=True),
    Step(Phase.UNINSTALLED, ["uv", "run", "thalamus", "init", "--uninstall"],
         doc="README.md:86", may_fail=True),
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

#: Where the wheel phase installs the built wheel, under the cell's home. Named here
#: because `drive.py` creates it and `checks.py` reads it, and a second spelling of
#: the path would be a probe reporting on a venv nobody built. Under the HOME rather
#: than under `$QE_ARTIFACTS` on purpose: the artifacts directory is uploaded whole as
#: a cell's evidence, and a venv is a hundred megabytes of dependency that says
#: nothing a reader of that evidence needs. The wheel itself does stay in artifacts —
#: it is the artifact under test.
WHEEL_VENV_DIRNAME = ".qe-wheel-venv"

#: Arms the one phase in this matrix that spends real model money: `Phase.DISTILLED`'s
#: check (issue #131). Read identically by `drive.py` (whether to run the phase at
#: all) and `checks.py` (why it reports not_evaluated when it did not), so neither can
#: drift from the other about which cells this ran on. Unset on every hosted per-push
#: runner by construction — qe-linux.yml and qe-macos.yml never set it — and set to
#: "1" only by the libvirt scheduled run in the operator's private notes repo, where
#: the model budget for #131 was granted on a schedule, never per-push.
DEEP_TIER_ENV = "QE_DEEP_TIER"


# --------------------------------------------------------------------------------------
# Config variants. Each reproduces a filed defect's precondition.
# --------------------------------------------------------------------------------------

CONFIGS: tuple[Config, ...] = (
    Config("baseline",
           "Everything present. The documented happy path, and the control for "
           "every other variant in the column."),
    Config("no-jq",
           "`jq` off PATH — another vendor's binary that install does not provide. "
           "The absence must be reported as an advisory, the checks that need it as "
           "could-not-run, and `--check` must still exit 0 before install.",
           issue=79, fixed=True, removes=("jq",),
           # `session-end.sh` exits 0 before doing anything when `jq` is missing
           # (`thalamus_require_binaries jq uv || exit 0`), so the DISTILLED phase's
           # fixture session would never be picked up at all. That is issue #79's
           # premise re-observed, not a #131 finding, and skipping it here is what
           # keeps the no-agent-cli cell — this check's own control — the one place
           # an unchanged count means something.
           skip_steps=(Phase.DISTILLED,)),
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
           issue=17, fixed=True,
           # No graph ever runs in this cell, so the fixture session's extraction
           # would fail to write for the same reason issue #17 does — a finding
           # about a down graph, not about #131 — and DISTILLED skips with it.
           skip_steps=(Phase.GRAPH_STARTING, Phase.GRAPH_READY, Phase.DISTILLED)),
    Config("moved-checkout",
           "The checkout is renamed after a successful init, which is what an "
           "ordinary upgrade looks like. Every later --check must name the "
           "mismatch rather than printing the healthy-install text.",
           issue=52, fixed=True),
    # The one variant that is not a perturbation of the BOX. Every other config here
    # changes what the machine has; this one changes what the product IS — the wheel
    # `uv build` produces, installed into a venv of its own with no checkout anywhere
    # near it, which is what a user who did not clone would get. It runs the whole
    # documented sequence against the checkout as well, because the wheel probe's
    # control is the checkout's own answer to the same question and both have to come
    # off the same box on the same day.
    Config("installed-wheel",
           "The product installed as a wheel outside a checkout. `contract/paths.py:21` "
           "anchors PROJECT_ROOT at `parents[3]`, which from "
           "`site-packages/thalamus/contract/paths.py` is the venv's `lib/pythonX.Y`, "
           "so everything the harness loads by repo-relative path is looked for "
           "somewhere nothing was installed.",
           issue=35, builds_a_wheel=True),
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
          "`.venv/bin/thalamus` exists and answers `--help`. getting-started:46 "
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

    # ---- the graph actually becomes ready -----------------------------------------
    Check("compose-up-produces-a-graph-that-answers-queries", Phase.GRAPH_READY,
          Severity.BLOCKS,
          "After `docker compose up -d`, within a bounded wait the graph must "
          "actually answer a query — not merely accept a TCP connection. Before this "
          "check existed, Phase.GRAPH_READY carried zero entries in `spec.CHECKS` and "
          "nothing in the matrix asserted this at all (issue #130).",
          control="the port must have been open at all after `docker compose up -d` "
                  "returned 0, or a query failing to answer cannot be told apart from "
                  "a container that never started"),

    # ---- pre-install check ------------------------------------------------------
    Check("check-exits-zero-before-install", Phase.CHECKED, Severity.DEGRADES,
          "getting-started:127 promises --check is safe before installing and exits 0, "
          "and getting-started:132 that a missing prerequisite is an advisory. A box "
          "without `jq` must therefore report it and still exit 0.",
          issue=79, fixed=True,
          control="the run's output must have carried rendered check lines at all. An "
                  "exit code with nothing parsed behind it cannot be attributed to any "
                  "finding, so the check degrades to not_evaluated rather than reading "
                  "a silent run as a clean one. The count of could-not-run markers "
                  "rides in the observation for the same reason: exit 0 with the `jq` "
                  "line and its dependants simply not rendered is the same exit code "
                  "as a healthy box"),
    Check("no-failure-marker-beside-the-word-skipped", Phase.CHECKED, Severity.DEGRADES,
          "The legend at getting-started:120 defines the failure marker as something "
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
    Check("cursor-guards-are-failclosed", Phase.INSTALLED, Severity.BLOCKS,
          "Every Cursor `beforeShellExecution` guard script wired into "
          "~/.cursor/hooks.json carries `failClosed: true`, the flag issue #77 is "
          "about. Read against `install.build_cursor_hook_block()` — the one place "
          "the guard set and the flag are derived — rather than a copied list of "
          "guard names that would drift the moment a fourth guard arrived.",
          issue=123, fixed=True,
          control="the same file must carry at least one of our OWN non-guard "
                  "entries with no `failClosed` flag at all, or the check cannot "
                  "tell 'wired correctly' from 'every entry defaults to the flag'"),

    # ---- a session that ends is distilled ----------------------------------------
    # Model-spending: gated on `DEEP_TIER_ENV`, never on a hosted per-push runner.
    # No `issue=` tag — like `compose-up-produces-a-graph-that-answers-queries`
    # above, this closes a coverage gap rather than reproducing a defect the tree is
    # known to carry, so it is expected to PASS from the day it lands.
    Check("a-session-that-ends-is-distilled", Phase.DISTILLED, Severity.BLOCKS,
          "README.md:103 states the whole confirmation that memory works: the "
          "session count `thalamus status` reports goes from 0 to 1 after a real "
          "session ends. docs/getting-started.md:157-186 makes this documented step "
          "6 of the first run. Every check above this one stops at whether the "
          "wiring that writes it is armed; none reads a Session vertex, a claim, or "
          "`thalamus status` itself (issue #131).",
          control="the no-agent-cli cell — whose premise is a box with no CLI "
                  "distillation can shell out to — must show the same fixture "
                  "session end with the count UNCHANGED, or this check cannot tell "
                  "a session that got distilled from one where nothing ran at all"),

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

    # ---- the packaged layout ----------------------------------------------------
    Check("installed-wheel-finds-the-scripts-it-ships", Phase.WHEEL, Severity.BLOCKS,
          "A wheel installed outside a checkout must resolve the files it shipped "
          "with. `contract/paths.py:21` is `Path(__file__).resolve().parents[3]`, and "
          "its own docstring states the premise — 'this project runs from its "
          "checkout'. From `site-packages/thalamus/contract/paths.py` that arithmetic "
          "lands on the venv's `lib/pythonX.Y`, so `verify()` looks for the hook "
          "scripts under `<venv>/lib/pythonX.Y/src/thalamus/harness/hooks/`, where "
          "nothing is, while the scripts themselves sit in the package it just "
          "installed. `config/experts/` is not in the wheel at all.",
          issue=35,
          control="the SAME `thalamus init --check`, run in the same phase from the "
                  "checkout's own `.venv/bin/thalamus` against a home of its own, "
                  "must report those script sets PRESENT. Without that half the "
                  "check is asserting on a rendering that could be missing on any "
                  "box, for any reason, and would report the defect on a repaired "
                  "tree"),

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
    "graph-ready": 180,      # JVM start on 2 vCPU. Also the bound `drive.py` waits,
                             # after the CHECKED step, before taking the real
                             # post-readiness `graph-ready` snapshot (issue #130) —
                             # unmeasured like `boot`: the five-green-cells
                             # calibration rule this block documents cannot be
                             # satisfied yet (thread
                             # qe-install-matrix-timeout-calibration-broken), so this
                             # stays the same reasoned guess rather than an invented
                             # calibrated number
    "uv-sync": 300,          # measured at 2.1 s; the floor guards a resolver stall
    "thalamus-init": 120,    # two 60 s subprocess timeouts inside register_mcp
    "asserts": 180,
    # `uv build` fetches a build backend and `uv pip install` resolves the runtime
    # dependencies into a second venv. Both hit the same uv cache `uv sync` has
    # already warmed in this cell, so this is sized for a cold cache and a network
    # round trip rather than for the measured case.
    "wheel": 600,
    # One `thalamus init --check`, and the floor is not arbitrary: `verify()` calls
    # `probe_entry_point`, which allows ITSELF 180 s for a `uv run` resolution. A
    # budget under that would kill the probe inside a wait the product considers
    # normal, and the cell would report missing evidence where there was a finding.
    # Two of these run in the wheel phase, so it also has to stay well inside
    # CELL_CEILING_S.
    "wheel-probe": 300,
    # Bounds `distill_phase`'s poll for the fixture session to land (issue #131).
    # `extraction.run_extraction`'s own subprocess ceiling is 900s
    # (harness/extraction.py:661), and its docstring describes the ordinary case as
    # "a minute or two"; this adds room for `uv run`'s own resolution and the
    # chained `eval sync --write` session-end.sh runs after it. Unmeasured, like
    # `graph-ready`: this phase is gated on `DEEP_TIER_ENV` and has never run
    # against a real cell, so the five-green-cells calibration rule cannot be
    # satisfied yet — a reasoned guess, not an invented calibrated number.
    "distill": 1200,
}

#: The per-cell hard ceiling, in seconds. Passed to virt-install as `--wait` in minutes.
#: Must stay >= `worst_case_matrix_seconds()`, which is not a comment's arithmetic but
#: a function over this file's own STEPS/TIMEOUTS/CONFIGS — read it, and
#: `install_cell_ceiling.py` (tests/qe/cases), rather than this docstring, whenever the
#: two disagree.
#:
#: 2026-09-04 derivation, `installed-wheel` (the config that skips no phase and also
#: builds a wheel): STEPS 1680 (uv-sync 300 + compose-up 900 + thalamus-init x4 480) +
#: boot 180 + clone-https 180 + the post-CHECKED graph-ready wait 180 + moved's
#: thalamus-init 120 + console's graph-ready-bounded port poll 180 + wheel_phase's
#: three subprocess calls at `wheel`=600 each 1800 + the wheel probe's two
#: `wheel-probe`=300 calls 600 + distill's bounded poll 1200 + session-end.sh's
#: hardcoded 30s return contract 30 = 6150s. Rounded up to a whole number of minutes,
#: since `--wait` takes minutes: 103 min = 6180s.
#:
#: NOT counted: several `checks.py` snapshot-time subprocess calls (`_dump` against
#: `_VERIFY_DUMP`, `_CURSOR_HOOK_BLOCK_DUMP`, `_SCOPES_DUMP`, `_graph_answers`) inherit
#: `run()`'s hardcoded default of 180s each rather than a named `TIMEOUTS` entry, the
#: way `wheel-probe` was carved out for `probe_entry_point`'s own 180s allowance
#: (checks.py:529-532). Several of these fire inside the INSTALLED/scopes/reinstalled
#: snapshots taken by `SNAPSHOTS_AFTER`, and are not part of this sum. Real budget for
#: them, sourced from named constants the way `wheel-probe` is, is unbuilt.
CELL_CEILING_S = 6180


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


def configs_requiring_no_graph() -> tuple[str, ...]:
    """Configs whose premise is a box where nothing answers on the graph port.

    `gate_config_premise` refuses these where a graph answers, so they can only run on
    a box that has none. Among hosted runners that is macOS, which has no nested
    virtualization and therefore no Docker.
    """
    return tuple(c.name for c in CONFIGS
                 if Phase.GRAPH_STARTING in c.skip_steps)


def configs_needing_a_graph() -> tuple[str, ...]:
    """Configs that run the whole documented sequence, graph included.

    These two functions partition CONFIGS, and they exist so the CI workflows can be
    told which cells to run instead of carrying their own copy of the list. A hardcoded
    matrix is a second source of truth: a config added here would simply not run, and
    nothing would say so.
    """
    return tuple(c.name for c in CONFIGS
                 if Phase.GRAPH_STARTING not in c.skip_steps)


def configs_building_a_wheel() -> tuple[str, ...]:
    """Configs whose cell must also run the wheel phase after the documented steps.

    One function rather than a second inspection of `Config.builds_a_wheel`, for the
    reason `configs_requiring_no_graph`/`configs_needing_a_graph` already state: a
    hardcoded second copy of a config's own flag drifts, silently, from the flag
    itself. That drift is exactly what issue #129 found — the libvirt guest-script
    generator (`ops/qe-install-matrix/seed.py`, the operator's private notes repo)
    never read `builds_a_wheel` at all, so `installed-wheel` ran there as a plain
    duplicate of `baseline` and reproduced nothing. `drive.py`'s own gate is
    `config.builds_a_wheel and Phase.WHEEL not in config.skip_steps`; this is that
    same condition, named once, for any reader of the spec outside this file too.
    """
    return tuple(c.name for c in CONFIGS
                 if c.builds_a_wheel and Phase.WHEEL not in c.skip_steps)


def worst_case_cell_seconds(config: Config, timeouts: dict[str, int] | None = None) -> int:
    """The most `config`'s cell may legitimately spend, phase by phase.

    Mirrors `drive.py`'s `main()` bound for bound: which phases run is exactly the set
    of conditions `main()` guards each phase with — `config.skip_steps` and
    `configs_building_a_wheel()` — not a second copy of that logic re-typed here. A
    bucket a single phase spends more than once is counted that many times, because
    each spend is an independent `subprocess.run` that can legitimately consume its
    own full bound: `wheel_phase` calls `stage()` three times (`uv build`, `uv venv`,
    `uv pip install`, each bound to the SAME `wheel` timeout — drive.py:480-511), and
    `checks.py`'s `_wheel_probe`, taken during that phase's own snapshot, runs two
    `wheel-probe`-bound `init --check` calls (checks.py:536).

    `timeouts` defaults to the real `TIMEOUTS` and exists so a caller can pass a
    modified copy — that is the only way to show this function actually reads the
    bucket it claims to, rather than returning a constant that happens to fit under
    the ceiling (`install_cell_ceiling.py`'s control does exactly this).
    """
    t = TIMEOUTS if timeouts is None else timeouts
    steps = tuple(s for s in STEPS if s.phase not in config.skip_steps)
    total = sum(t[timeout_key(s)] for s in steps)
    # The guest boot and the clone both happen before `drive.py` ever runs, but
    # `virt-install --wait` wraps the whole guest, not only `drive.py`'s own steps.
    total += t["boot"] + max(t["clone-local"], t["clone-https"])
    if Phase.GRAPH_STARTING not in config.skip_steps:
        # graph_ready_phase's bounded wait, run once strictly after CHECKED
        # (drive.py:545).
        total += t["graph-ready"]
    if Phase.MOVED not in config.skip_steps:
        # moved_phase's own `thalamus init --check`, after REINSTALLED (drive.py:431).
        total += t["thalamus-init"]
    if Phase.CONSOLE not in config.skip_steps:
        # console_phase polls the port for up to `graph-ready` seconds waiting for the
        # server to bind (drive.py:687).
        total += t["graph-ready"]
    if config.name in configs_building_a_wheel():
        total += 3 * t["wheel"] + 2 * t["wheel-probe"]
    if Phase.DISTILLED not in config.skip_steps:
        # distill_phase's bounded poll, plus session-end.sh's own hardcoded 30s
        # contract to return immediately and fork the rest detached (drive.py:626) —
        # not in TIMEOUTS because it is not a documented step's budget, but it is still
        # seconds the cell may legitimately spend before the poll even starts.
        total += t["distill"] + 30
    return total


def worst_case_matrix_seconds(timeouts: dict[str, int] | None = None) -> int:
    """The bound every cell in the matrix must fit under: the worst of all configs.

    Whichever `Config` this lands on today, the point of taking the max over all of
    them rather than naming one is that a future config carrying more phases becomes
    the worst case automatically, with no second place to remember to update.
    """
    return max(worst_case_cell_seconds(c, timeouts) for c in CONFIGS)


def expected_reproductions(config: Config) -> frozenset[int]:
    """What THIS cell is built to reproduce, which is not the same as what the tree
    carries.

    `known_defect_issues()` is the whole tree's unfixed set, and using it as one cell's
    positive control was wrong in a way that only showed once the set got small: a
    defect reachable solely under one perturbation cannot be reproduced by the four
    cells that do not apply it, so they reported "nothing reproduced" and exited 2 for
    behaving correctly. It went unnoticed while an ungated check carried an open issue,
    because that one fired in every cell.

    A `Config` naming an issue is the statement that its perturbation triggers that
    defect, so that is the cell's own control. A check carrying an issue that no config
    claims is reachable from the baseline sequence and is expected everywhere.
    """
    claimed = {c.issue for c in CONFIGS if c.issue}
    ungated = {c.issue for c in CHECKS
               if c.issue and not c.fixed and c.issue not in claimed}
    own = {config.issue} if config.issue and not config.fixed else set()
    return frozenset(ungated | own)


def fixed_issues() -> frozenset[int]:
    """Issues whose checks must now PASS. A red one here is a regression."""
    return frozenset(c.issue for c in CHECKS if c.issue and c.fixed) | frozenset(
        c.issue for c in CONFIGS if c.issue and c.fixed)
