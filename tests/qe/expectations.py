"""Known-red reconciliation: the part that decides whether a failure is news.

`thalamus ceremony ack` (bc3946d — "A gate that is always red stops being read, so a
permanent finding is acknowledged") already solved this shape once. Two of its
properties do not survive the translation here, and both are the laundering channel:

1. **Its discrimination comes from a closed set of categories computed by the auditor.**
   Ours are emitted by the failing case, which is weaker. Hence `FailureClass` has no
   OTHER member, and an expectation records the exact class it was triaged against.
2. **Its ack store is machine-local**, which would make it empty in GitHub Actions —
   every known-red would read there as a new regression. Hence this file is committed
   to the repo and its sha is stamped into the run header, so a run can prove which
   expectations it reconciled against.

The clause that fingerprinting alone cannot supply:

> A known-red entry must pin the defect's CURRENT BEHAVIOR positively, not merely
> record that the behavior is wrong.

That is why an expectation carries `witness_contains`. An entry saying only "this fails"
absorbs any future failure at the same site; an entry saying "this fails, and the
witness contains THIS" breaks the moment the defect changes shape — which is the event
you most want to hear about and the one a plain quarantine silently swallows.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .model import CaseResult, Outcome

EXPECTATIONS_PATH = Path(__file__).parent / "expectations.json"

# Verdicts. Distinct exit codes downstream, because if every red renders as one X the
# cheap ones get rerun until green — which is the (1-p)^k laundering channel wearing
# process clothes rather than code clothes.
OK = "ok"                    # passed, and was expected to
KNOWN_RED = "known-red"      # failed exactly as triaged
NEW_FAILURE = "new-failure"  # failed, and was not expected to
DRIFTED = "drifted"          # failed as expected, but DIFFERENTLY — treat as new
FIXED = "fixed"              # passed, but an expectation says it should fail
SKIPPED = "skipped"
MALFORMED = "malformed"      # the case itself is broken


@dataclass(frozen=True)
class Expectation:
    case: str
    failure_class: str
    # A substring that must appear in the witness. This is the positive pin: it makes
    # the entry a characterization test on the defect rather than a mute button.
    witness_contains: str
    triaged_at_rev: str
    note: str = ""


class MalformedExpectations(Exception):
    """The oracle cannot be read. Never a verdict about the code — always exit 3."""


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    """Refuse what `json.loads` would resolve by last-wins.

    `174b44c` is why this is not defensive: a missing `},{` merged one entry's keys into
    the object above it, and the file read as eleven expectations and parsed as ten. In a
    file whose entire purpose is acknowledging known-red defects, an entry that silently
    does not parse makes *absent* and *acknowledged* one state — the collapsed sentinel
    this suite is named for, committed inside the suite's own oracle. It was found by an
    architect reading a boundary ticket, not by the runner, because the runner could not
    see it.
    """
    seen: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise MalformedExpectations(
                f"duplicate key {key!r} in one object — json.loads would keep the last "
                f"silently, so an entry is being merged into its neighbour")
        seen[key] = value
    return seen


def load() -> tuple[dict[str, Expectation], str]:
    """Return the expectations and the sha of the file they came from.

    The sha is returned rather than computed by callers so that the value stamped into
    the ledger is provably the bytes that were reconciled against, not a recomputation
    that could drift between read and stamp.

    Raises `MalformedExpectations` rather than returning a short list. Every other
    failure mode in this suite is a verdict about the code; this one is the oracle being
    unreadable, and a shorter list of acknowledgements is indistinguishable from a
    correct one at every later step.
    """
    if not EXPECTATIONS_PATH.is_file():
        return {}, "absent"
    raw = EXPECTATIONS_PATH.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()[:12]
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise MalformedExpectations(f"{EXPECTATIONS_PATH.name} is not valid JSON: {exc}") from exc
    out = {}
    for row in data.get("expectations", []):
        if row["case"] in out:
            # The same collapse one level up: two entries naming one case leave the last
            # standing and shrink the acknowledged set with no diagnostic.
            raise MalformedExpectations(
                f"two expectations name the case {row['case']!r} — the second would "
                f"silently replace the first")
        exp = Expectation(
            case=row["case"],
            failure_class=row["failure_class"],
            witness_contains=row.get("witness_contains", ""),
            triaged_at_rev=row.get("triaged_at_rev", "unknown"),
            note=row.get("note", ""),
        )
        out[exp.case] = exp
    return out, sha


def reconcile(result: CaseResult, expectations: dict[str, Expectation]) -> tuple[str, str]:
    """(verdict, explanation) for one case against the triaged list.

    Order matters. MALFORMED is checked before anything else and can never be absorbed:
    a broken check is not evidence about the code, so letting an expectation swallow it
    would let the suite go quiet by breaking rather than by passing.
    """
    exp = expectations.get(result.name)

    if result.outcome is Outcome.MALFORMED:
        return MALFORMED, "the case itself is broken — not evidence about the code"

    if result.outcome is Outcome.SKIPPED:
        missing = ", ".join(s.value for s in result.missing) or "unknown"
        return SKIPPED, f"substrate absent: {missing}"

    if result.outcome is Outcome.PASSED:
        if exp is None:
            return OK, ""
        return FIXED, (
            f"passed, but an expectation triaged at {exp.triaged_at_rev} says it should "
            f"fail with {exp.failure_class}. If the defect is fixed, delete the "
            f"expectation in the same change — a stale entry hides the next regression "
            f"at this site."
        )

    # FAILED from here.
    if exp is None:
        return NEW_FAILURE, "failed, and no expectation covers it"

    finding = result.finding
    if finding is None:
        return DRIFTED, "failed without a Finding, so it cannot be matched to its expectation"

    if finding.failure_class.value != exp.failure_class:
        return DRIFTED, (
            f"expected {exp.failure_class}, got {finding.failure_class.value} — same "
            f"case, different defect"
        )

    if exp.witness_contains and exp.witness_contains not in finding.witness:
        return DRIFTED, (
            f"failure class matches but the witness changed; expected to contain "
            f"{exp.witness_contains!r}. The defect is still here and is no longer the "
            f"one that was triaged."
        )

    return KNOWN_RED, f"triaged at {exp.triaged_at_rev}: {exp.note}"
