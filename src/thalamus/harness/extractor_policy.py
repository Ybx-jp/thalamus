"""Which CLI and model run an extraction pass — the operator's choice, stored and audited.

`harness/agents.py` records what each headless CLI *can* do. This records which one the
operator wants running a pass, and it exists because those were never the same question
and one flag was answering both.

## Two passes, because they are two budgets

This system calls a model in two places, and they are not the same kind of spend.
**Distillation** turns an ended session into memory: one digest per session, fired by a
SessionEnd hook, arriving at whatever rate the operator happens to work at. **Ingestion**
turns a procured document into an expert's knowledge: a paper is chunked, and every chunk
is its own model call, so one `thalamus ingest` can cost what a day of distillation does.

A single setting covering both makes the cheap steady drip and the expensive burst share
one answer, and the burst is the one worth moving. So each pass carries its own selection,
and ingestion's default is `follow distillation` — a real value rather than an absent key,
so an operator who wants one answer for both still gets it in one tap, and the split costs
nothing until he asks for it.

## The two axes `--harness` was carrying

`thalamus extract --harness X` has meant two independent things at once: **X wrote these
transcripts**, which decides how the digest is rendered (`extraction.render_digest`), and
**X runs the extraction pass**, which decides the binary, the argv dialect and the envelope
reader (`extraction.run_extraction`). They agreed by construction — a Claude Code session
distilled through `claude` — and the agreement read as one fact rather than two, so there
was no way to say "read this Claude Code transcript, but pay for the pass somewhere else."

Splitting them costs nothing at the boundary: a digest is plain text by the time it reaches
a model, so a rendered Claude Code session is as legible to `codex exec` as to `claude -p`.
Ingestion never had the ambiguity — it has no transcript and so no source harness — which
is why its `--harness` is the extractor choice outright.

## The rules, and what each one is for

**A CLI that is not installed may not be selected.** Everywhere else in this system a bad
setting is a visible failure; for distillation it is silence. `run_extraction` raises on a
missing binary, and distillation's only caller is a detached SessionEnd job whose whole
output is a per-session log nobody opens. So an absent binary is refused at selection, and
a selection whose binary *later* disappears is dropped **on read** rather than by a sweep —
the same shape `launch_policy.effective` uses for expiry, for the same reason: nothing
guarantees a sweep ran, and the moment that matters is the next pass.

**No free-text fields.** The model is chosen from the list its CLI declares
(`agents.AgentCLI.models`). A slug typed into a box is a value nothing can check, and it
fails at invocation — inside that same detached job. `--model` on the command line remains
the escape hatch for a slug the panel does not carry.

**Every change is a ledger row.** `launch_policy` keeps one because a permission posture
that widened silently is unauditable; this keeps one for a sharper reason: **the graph does
not record which model extracted a Claim.** A Session carries the `tool` that wrote the
transcript, not the CLI that distilled it, and a Source carries no extractor at all, so
once the extractor can vary, `~/.thalamus/extractor/policy.jsonl` is the only thing that
can answer "what extracted the claims from that week." Configuration changes belonging in a
controlled, recorded workflow is the one point the graph's own literature is unambiguous
about (MCP threat survey, arXiv 2503.23278).

**What a choice gives up is stated where it is made.** Only Claude Code prices its own run,
and `eval/cost.py` buckets both passes' spend by finding the sandbox's transcript under
`~/.claude/projects/-tmp-thalamus-extract*` — a Claude Code artifact. Routing a pass
elsewhere therefore does not reduce the spend `eval cost` reports; it removes it from the
report. That is the intended effect on the Claude budget and an unintended one on the
measurement, and a panel that showed the first without the second would be selling a saving
it cannot substantiate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from thalamus.harness.agents import AGENT_CLIS, HARNESSES, cli_for

POLICY_DIR = Path.home() / ".thalamus" / "extractor"
STORE = POLICY_DIR / "policy.json"
LEDGER = POLICY_DIR / "policy.jsonl"

STORE_VERSION = 1

# The value meaning "do not decide here" — today's behaviour, and what an operator who
# has chosen nothing gets. A real value rather than an absent key, because it is a choice
# he can make *back*: returning to it has to be one tap and has to land a ledger row,
# which an unset key could not carry. What it defers *to* differs per pass, which is what
# `Pass.inherit_label` says out loud.
INHERIT = ""


@dataclass(frozen=True)
class Pass:
    """One model-calling pass, and where its answer comes from when it defers.

    `inherits` is the whole of the difference between the two. Distillation defers to a
    fact about the run — the harness that wrote the transcript, which only the caller
    knows — so it has no policy to fall through to. Ingestion has no such fact, so it
    falls through to distillation's selection and then to `claude`. Encoding that as a
    field rather than as a branch in `resolve` keeps the panel able to *say* what
    deferring means without re-deriving it.
    """

    key: str
    label: str
    # The command-line flag that overrides this pass, named so a resolution can report
    # which flag was read. `--extract-with` and `--harness` mean the same thing on two
    # commands, and a reason line naming the wrong one sends a reader to the wrong help.
    flag: str
    inherit_label: str
    inherit_note: str
    # The pass whose selection this one falls through to, or "".
    inherits: str = ""
    # The harness used when nothing else answers. Empty means the caller supplies it —
    # distillation's answer is the session's own harness, which is not a constant.
    default_harness: str = ""
    # How a resolution that reached `default_harness` describes itself.
    default_reason: str = ""


PASSES: dict[str, Pass] = {
    "distill": Pass(
        key="distill",
        label="distillation",
        flag="--extract-with",
        inherit_label="follow the session",
        inherit_note="each session distills through the CLI that wrote it",
        default_reason="the session's own harness",
    ),
    "ingest": Pass(
        key="ingest",
        label="ingestion",
        flag="--harness",
        inherit_label="follow distillation",
        inherit_note="ingestion uses whatever distillation is set to",
        inherits="distill",
        # Ingestion has no source harness to fall back on, so the chain has to end
        # somewhere nameable. `claude` is what it did before this module existed.
        default_harness="claude",
        default_reason="the default",
    ),
}

PASS_KEYS = tuple(PASSES)
DEFAULT_PASS = "distill"

# What picking each CLI as the extractor gives up, in the operator's terms. Empty for
# `claude` because it is the status quo the cost surface was built around.
DROPS: dict[str, str] = {
    harness: (
        "" if AGENT_CLIS[harness].reports_cost else
        f"the extraction spend, as a measurement — `{AGENT_CLIS[harness].binary}` "
        "reports no price, and `thalamus eval cost` buckets both passes by reading the "
        "Claude Code sandbox's own transcript, so the pass stops appearing there at all"
    )
    for harness in HARNESSES
}


class ExtractorRefused(ValueError):
    """A selection the surface must not accept. Carries operator-facing prose."""


class UnknownPass(ValueError):
    pass


@dataclass(frozen=True)
class Extractor:
    """The CLI and model one pass will actually use, and why.

    `reason` is carried rather than re-derived because it is printed into the
    per-session distillation log and the ingest report, which are the only record a
    completed pass leaves of what ran it. "codex (the ingestion setting)" and
    "codex (--harness)" are different facts about the same run, and a reader debugging a
    bad batch of claims needs the difference.
    """

    harness: str
    model: str
    reason: str


def pass_for(key: str) -> Pass:
    try:
        return PASSES[key]
    except KeyError:
        raise UnknownPass(
            f"`{key}` is not an extraction pass; known: {', '.join(PASS_KEYS)}"
        ) from None


def _read(store: Path | None = None) -> dict:
    path = store or STORE
    try:
        raw = json.loads(path.read_text() or "{}")
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def stored(pass_: str = DEFAULT_PASS, *, store: Path | None = None) -> dict[str, str]:
    """The raw selection on file for one pass — harness and model, neither validated.

    Kept distinct from `effective` for the reason `launch_policy` keeps the pair
    distinct: this is what the operator chose, which the panel must show even once it
    has stopped being usable, and `effective` is what a pass would use.
    """
    pass_for(pass_)
    passes = _read(store).get("passes")
    raw = passes.get(pass_) if isinstance(passes, dict) else None
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key in ("harness", "model"):
        if isinstance(raw.get(key), str):
            out[key] = raw[key]
    return out


def unusable(pass_: str = DEFAULT_PASS, *, store: Path | None = None) -> str:
    """Why this pass's stored selection cannot be honoured right now, or "".

    Prose, not a flag, and computed in one place so the panel and the resolver cannot
    disagree about whether a setting is live. Only ever about this pass's *own*
    selection — a pass that is inheriting has nothing of its own to be wrong, and the
    pass it inherits from reports its own trouble under its own card.
    """
    spec = pass_for(pass_)
    held = stored(pass_, store=store)
    harness = held.get("harness", INHERIT)
    if harness == INHERIT:
        return ""
    if harness not in AGENT_CLIS:
        return (
            f"`{harness}` is not a harness this build knows; {spec.label} is "
            f"{spec.inherit_label.replace('follow ', 'following ')} instead."
        )
    cli = AGENT_CLIS[harness]
    if not cli.available:
        return (
            f"`{cli.binary}` is not on this box's PATH, so {spec.label} is "
            f"{spec.inherit_label.replace('follow ', 'following ')} instead. The "
            f"setting is kept — it takes effect again once the CLI is installed."
        )
    model = held.get("model", "")
    if model and cli.models and model not in cli.models:
        return (
            f"`{model}` is no longer a model `{cli.binary}` offers, so the pass would "
            f"use `{cli.default_model}`."
        )
    return ""


def effective(pass_: str = DEFAULT_PASS, *, store: Path | None = None) -> dict[str, str]:
    """This pass's own selection, minus anything unusable. Empty means it defers.

    An unusable selection is simply absent, which drops the pass back to whatever it
    would have done unset. Falling back rather than failing is deliberate and is the
    direction that keeps memory accumulating: a box that lost its `codex` install should
    keep distilling through the CLI it still has, not stop. The panel says so out loud
    (`unusable`), which is what keeps the fallback from being silent.
    """
    if unusable(pass_, store=store):
        return {}
    held = stored(pass_, store=store)
    harness = held.get("harness", INHERIT)
    if harness == INHERIT or harness not in AGENT_CLIS:
        return {}
    out = {"harness": harness}
    model = held.get("model", "")
    if model:
        out["model"] = model
    return out


def resolve(
    *,
    pass_: str = DEFAULT_PASS,
    source_harness: str = "",
    harness: str = "",
    model: str = "",
    store: Path | None = None,
) -> Extractor:
    """Which CLI and model run this pass, given the flags and the stored policy.

    Precedence is flag, then this pass's policy, then the policy it inherits from, then
    the pass's own floor. The flag wins because it is the narrower statement: an operator
    typing `--extract-with` is talking about this run, and a stored policy overriding him
    would make the flag unusable for the one thing it is for — trying another extractor
    without committing the box to it.
    """
    spec = pass_for(pass_)
    if harness:
        chosen, why = harness, spec.flag
    else:
        chain = (spec.key, spec.inherits) if spec.inherits else (spec.key,)
        chosen, why = "", ""
        for key in chain:
            live = effective(key, store=store)
            if live.get("harness"):
                chosen = live["harness"]
                why = f"the {PASSES[key].label} setting"
                model = model or live.get("model", "")
                break
        if not chosen:
            chosen = source_harness or spec.default_harness
            why = spec.default_reason
    cli = cli_for(chosen)
    return Extractor(harness=chosen, model=model or cli.default_model, reason=why)


def describe(pass_: str = DEFAULT_PASS, *, store: Path | None = None) -> dict:
    """Everything the console panel needs to render one pass's setting.

    One structure rather than several fields fetched apart, for `launch_policy`'s reason:
    `drops` beside an option is a cost the operator can weigh, and the same string
    arriving separately is a footnote. `resolved` is the concrete answer a pass would
    give right now, and is empty only where there is genuinely none — distillation
    following the session cannot name a CLI until a session ends.
    """
    spec = pass_for(pass_)
    held = stored(pass_, store=store)
    live = effective(pass_, store=store)
    options = [{
        "value": INHERIT,
        "label": spec.inherit_label,
        "note": spec.inherit_note,
        "drops": "",
        "available": True,
        "models": [],
        "default_model": "",
    }]
    for harness in HARNESSES:
        cli = AGENT_CLIS[harness]
        options.append({
            "value": harness,
            # The harness name, not the binary. Everywhere else on this console — the
            # spawn sheet, the roster rows, the posture cards — a harness is picked by
            # its name, and Cursor is the one where the two differ (`agent`). A chip
            # reading `agent` beside `claude` and `codex` would be the only place on
            # the surface where the operator has to know a binary to pick a vendor.
            "label": harness,
            "note": "" if cli.binary == harness else f"runs as `{cli.binary}`",
            "drops": DROPS.get(harness, ""),
            # Rendered as a disabled row rather than omitted: an operator who expected
            # codex here needs to be told it is missing, and an option that silently
            # is not offered says nothing at all.
            "available": cli.available,
            "models": list(cli.models),
            "default_model": cli.default_model,
        })
    resolved: dict[str, str] = {}
    if live.get("harness") or spec.inherits or spec.default_harness:
        run = resolve(pass_=pass_, store=store)
        resolved = {"harness": run.harness, "model": run.model, "reason": run.reason}
    return {
        "pass": spec.key,
        "label": spec.label,
        "value": {
            "harness": live.get("harness", INHERIT),
            "model": live.get("model", ""),
        },
        "stored": {
            "harness": held.get("harness", INHERIT),
            "model": held.get("model", ""),
        },
        "resolved": resolved,
        "unusable": unusable(pass_, store=store),
        "options": options,
    }


def describe_all(*, store: Path | None = None) -> list[dict]:
    """Every pass, in the order the panel stacks them."""
    return [describe(key, store=store) for key in PASS_KEYS]


def select(
    harness: str,
    model: str = "",
    *,
    pass_: str = DEFAULT_PASS,
    actor: str = "console",
    store: Path | None = None,
    ledger: Path | None = None,
    now: datetime | None = None,
) -> dict:
    """Record one pass's selection. Raises `ExtractorRefused` for anything illegal.

    Refusals are prose because every one of them is read by a person mid-decision, and
    the reason for the rule is the whole argument for it — a surface answering `400`
    here would be enforcing a policy it declines to explain.
    """
    spec = pass_for(pass_)
    moment = now or datetime.now(timezone.utc)
    before = effective(pass_, store=store)

    if harness == INHERIT:
        if model:
            raise ExtractorRefused(
                f"`{spec.inherit_label}` picks the CLI somewhere else, so there is no "
                f"one CLI for that model to belong to."
            )
    else:
        cli = AGENT_CLIS.get(harness)
        if cli is None:
            raise ExtractorRefused(
                f"`{harness}` is not a harness this build knows "
                f"({', '.join(HARNESSES)})."
            )
        if not cli.available:
            # Refused rather than stored-and-warned. A stored-but-dead extractor is
            # indistinguishable from a live one at the moment of choosing, and the
            # failure it produces lands in a detached job's log.
            raise ExtractorRefused(
                f"`{cli.binary}` is not on this box's PATH. Running a pass through a "
                f"CLI that is not installed does not fail loudly — distillation fails "
                f"inside the detached job SessionEnd forks, and the session is simply "
                f"never distilled."
            )
        if model and model not in cli.models:
            raise ExtractorRefused(
                f"`{cli.binary}` does not offer `{model}` here "
                f"({', '.join(cli.models)}). `--model` takes any slug the CLI accepts "
                f"if you need one this panel does not carry."
            )

    raw = _read(store)
    raw["version"] = STORE_VERSION
    passes = raw.get("passes")
    if not isinstance(passes, dict):
        passes = {}
    passes[spec.key] = {"harness": harness, "model": model}
    raw["passes"] = passes

    path = store or STORE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n")

    row = {
        "ts": moment.isoformat(),
        # Named on every row rather than implied by the file it lands in: one ledger
        # holds both passes, and a row that did not say which one it changed would make
        # the record unreadable exactly when it is being read — after the fact, to find
        # out what extracted a given week's claims.
        "pass": spec.key,
        "from_harness": before.get("harness", INHERIT),
        "from_model": before.get("model", ""),
        "to_harness": harness,
        "to_model": model,
        "actor": actor,
    }
    _append(ledger or LEDGER, row)
    return row


def _append(path: Path, row: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
    except OSError:
        # A change that cannot be logged is still a change the operator made, and
        # refusing it here would make an unwritable disk look like a rejected setting.
        pass
