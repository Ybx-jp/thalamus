"""Randomized render-withholding — making the counterfactual internal to real work.

Used-vs-ignored, as built, is post-hoc correlation on a set the ranker chose. No
permutation control fixes that: a permutation tests the *judge*, never the
*retrieval*. The pre-registered studies measure how little the judge can carry; this is
the other half — an intervention, inside the operator's real sessions, that produces
a comparison the judge does not have to invent.

The mechanism is one thing serving two estimators, which is why it is worth its cost:

- **Withholding.** With pre-registered probability, a node the ranker would have
  rendered is dropped, and the drop is recorded. Sessions become a within-unit
  randomized design with carryover (injected tokens ride along in later calls), i.e.
  a switchback, analysable by exact randomization inference.
- **Logged propensities.** The same record makes the deployed ranker a *stochastic*
  logging policy, which is the standing precondition for replay and doubly-robust
  estimation off the existing trace log — previously out of reach here because
  "retrieval here is not stochastic".

Three properties this design insists on:

**Off by default, and on only under a pre-registration.** Withholding costs the
operator real retrieval quality. `THALAMUS_WITHHOLD` carries the rate, so turning it
on is a deliberate act with a number attached, and a campaign that forgets to set it
produces no records rather than silently unrandomized ones.

**The record joins on content, not on clocks.** Each record carries the sha256 of the
rendered response, which is exactly what the trace tap stores verbatim. `eval sync`
joins policy to trace by that hash — no timestamp alignment, no query-text matching,
and a record that fails to join is visibly unmatched rather than quietly attached to
the wrong retrieval.

**A withheld node is not an ignored node.** It never reached the agent, so it gets no
verdict at all. Collapsing "withheld" into "ignored" would put the intervention's own
effect into the outcome it is measuring.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

POLICY_DIR = Path.home() / ".thalamus" / "policy"

# Bumped whenever the withholding rule changes shape. Records carry it so a campaign
# analysed later can refuse to pool two different interventions.
POLICY_VERSION = "withhold-v1"

ENV_RATE = "THALAMUS_WITHHOLD"


@dataclass(frozen=True)
class WithholdPolicy:
    """How often a would-be-rendered node is dropped, and under what identity."""

    rate: float = 0.0
    version: str = POLICY_VERSION

    @property
    def active(self) -> bool:
        return self.rate > 0.0

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> WithholdPolicy:
        """Read the rate from `THALAMUS_WITHHOLD`; absent or unparseable means off.

        Deliberately silent on a bad value rather than raising: this sits on the
        retrieval path of every session, and a typo in an environment variable must
        degrade to "no intervention", never to "no memory".
        """
        raw = (env if env is not None else os.environ).get(ENV_RATE, "").strip()
        if not raw:
            return cls()
        try:
            rate = float(raw)
        except ValueError:
            return cls()
        return cls(rate=min(1.0, max(0.0, rate)))


@dataclass
class WithholdRecord:
    """What the policy did to one retrieval, and everything needed to replay it."""

    version: str
    rate: float
    session_id: str
    scope: str
    tool: str
    ts: str
    seed: str
    offered: list[str] = field(default_factory=list)
    withheld: list[str] = field(default_factory=list)
    response_sha256: str = ""

    @property
    def kept(self) -> list[str]:
        dropped = set(self.withheld)
        return [vid for vid in self.offered if vid not in dropped]

    @property
    def propensity(self) -> float:
        """P(a given offered node was kept) under this policy. The IPS weight is 1/p."""
        return 1.0 - self.rate


def seed_for(identity: str, query: str, ts: datetime) -> str:
    """A reproducible seed from the retrieval's own identity.

    Storing a derived seed rather than a captured RNG state is what lets an analysis
    re-derive the exact draw months later from the record alone, with no live state
    and no trust in the writer. `identity` is the scope rather than the session: the
    MCP server cannot see its caller's session id, and `eval sync` fills
    the session in at join time from the trace the record matched.
    """
    material = f"{POLICY_VERSION}|{identity}|{query}|{ts.isoformat()}"
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def apply(
    offered: list[str],
    *,
    policy: WithholdPolicy,
    scope: str,
    tool: str,
    query: str,
    ts: datetime | None = None,
) -> tuple[list[str], WithholdRecord | None]:
    """Decide which offered vertex IDs survive. Returns (kept, record).

    Returns the input untouched and no record when the policy is inactive, so an
    unrandomized session is indistinguishable from one where the code is not present
    — the intervention leaves no trace when it is not running.
    """
    if not policy.active or not offered:
        return offered, None

    stamp = ts or datetime.now(timezone.utc)
    seed = seed_for(scope, query, stamp)
    rng = random.Random(seed)
    withheld = [vid for vid in offered if rng.random() < policy.rate]

    # Never withhold everything: an empty render is a *miss*, and a miss and a
    # fully-withheld retrieval are different events that the tap cannot tell apart.
    if withheld and len(withheld) == len(offered):
        withheld = withheld[:-1]

    record = WithholdRecord(
        version=policy.version,
        rate=policy.rate,
        session_id="",  # filled by `eval sync` from the trace this record joins to
        scope=scope,
        tool=tool,
        ts=stamp.isoformat(),
        seed=seed,
        offered=list(offered),
        withheld=withheld,
    )
    dropped = set(withheld)
    return [vid for vid in offered if vid not in dropped], record


def log(record: WithholdRecord, rendered: str, *, base: Path | None = None) -> Path:
    """Append the record, stamped with the hash of what was actually rendered.

    The hash is the join key `eval sync` uses: the tap stores the rendered response
    verbatim, so content matches content. Clock-based joins would silently pair the
    wrong retrieval on a busy session.
    """
    record.response_sha256 = hashlib.sha256(rendered.encode()).hexdigest()
    directory = base or POLICY_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record.ts[:7]}.jsonl"
    with path.open("a") as handle:
        handle.write(json.dumps(asdict(record)) + "\n")
    return path


def load(base: Path | None = None) -> dict[str, WithholdRecord]:
    """Every record, keyed by the hash of the response it produced."""
    directory = base or POLICY_DIR
    if not directory.is_dir():
        return {}
    records: dict[str, WithholdRecord] = {}
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = WithholdRecord(**json.loads(line))
            except (json.JSONDecodeError, TypeError):
                continue
            if record.response_sha256:
                records[record.response_sha256] = record
    return records


def response_key(rendered: str) -> str:
    return hashlib.sha256(rendered.encode()).hexdigest()
