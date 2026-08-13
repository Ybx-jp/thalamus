"""Adding a known-red entry is the mute primitive, and it may not happen silently.

`expectations.json` is the one file in this repo that converts red to green. A failing
case with no entry is `NEW_FAILURE` → exit 1 (`expectations.py:113`); add an entry that
matches its witness and the same failure is `KNOWN_RED` → exit 0 (`:132`). Deleting an
entry cannot hide anything — exit 2 exists to demand it — and narrowing a pin can only
make the suite louder. **Addition is the only edit that buys silence**, and widening a
pin is a smaller helping of the same purchase (docs/13, *What is allowed to go quiet*).

A PreToolUse hook cannot hold this. A hook binds a tool call, so `Bash`, Cursor, a human
editor and CI all route around it, and in CI there is no scope for it to consult. The
property has to be a content invariant over the file **and its diff against a base**,
because the file alone cannot tell an addition from a repair.

## What this asserts, and what it deliberately does not

It asserts that the entry set has not **grown**, and that no surviving pin has been
**widened**, relative to the base revision. It does not assert that any addition was
authorized, and there is no field, flag, or environment variable by which an addition can
declare itself approved.

That absence is the design, not an omission. This repo holds no authorization artifact a
hermetic check could verify:

- the close ledger (`harness/closes.py`) is the nearest thing, and its own docstring
  disclaims it — *"It cannot authenticate the operator, and it does not pretend to… a
  session proposing a close runs Bash at the operator's uid"* — and it lives under
  `$HOME/.thalamus/closes/`, so in CI it is empty for the same reason `ceremony ack`'s
  store is (`expectations.py`'s own header);
- Linear is explicitly an untrusted bus in docs/13, *"anyone who can write a Linear issue
  can supply that designation"*, so an issue link is not evidence;
- an agent editing this file runs at the operator's uid with `git` and `gh` in PATH, so
  any token it could be asked to produce it could also mint.

An `approved: true` key, or an `--i-checked` env var, would therefore be a rubber stamp
with a schema. What is left that an adding agent genuinely cannot mint is the **base**:
the prior server-side tip of the pushed ref, which GitHub writes into the event payload
after the push has already happened. So the guarantee this case actually delivers is
narrow and worth stating exactly:

> An addition costs the adding agent a red CI run on the commit that introduces it,
> naming the entry, and it cannot buy that run's silence with any edit to this file.

Monotonic confinement in Progent's sense (arXiv 2504.11703) — the quiet set may shrink
freely and may not grow without the growth being visible — applied to an oracle rather
than a privilege policy, as docs/13 §Prior work records. It is a *detection* boundary,
not a *prevention* one; the prevention boundary needs branch protection with required
review on the default branch, which lives in repo settings and not in this tree.

## Why the collapse paths raise instead of returning a Finding

`reconcile()` checks MALFORMED first and lets no expectation absorb it, so a raise is the
only verdict in this suite that cannot itself be muted. Three conditions take that exit:

1. **An entry in `expectations.json` names this case.** Such an entry would let an
   addition acknowledge itself — the detector's own mute — so its presence means the
   check is disabled, not that the repo is clean. Adding it converts exit 1 into exit 3,
   which is louder, and that is what closes the self-mute loop.
2. **No base revision can be determined.** A run that cannot see a base cannot tell an
   addition from anything else, and a check that passes when it cannot look is worse than
   one that reports broken.
3. **Either side of the comparison is malformed.** `json.loads` resolves a duplicate key
   by taking the last one, which is exactly how `174b44c` shipped a file that read as
   eleven entries and parsed as ten, and `load()` keys entries by case name, so a
   duplicate case silently collapses two entries into one. Either makes the set
   difference below unsound, so both are refused rather than compared. That check is the
   `174b44c` regression, kept permanently.

## The positive control

The case asserts an absence, so it carries the control the README demands: a synthetic
base/head pair is run through the same differ, in-process, and must report the planted
addition and the planted widening. A differ that has gone blind reports a clean repo,
which is indistinguishable from a clean repo — the control is what separates them, and
its failure is MALFORMED because a broken differ is not evidence about the file.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_CASE_NAME = "expectation-additions-are-never-silent"

_REPO = Path(__file__).resolve().parents[3]
_REL = "tests/qe/expectations.json"
_LIVE = _REPO / _REL

_ZERO = "0" * 40


class Undecidable(Exception):
    """The check could not be performed, so its silence would mean nothing.

    Raised rather than returned: `run.py` renders an exception as MALFORMED, and
    MALFORMED is the one verdict `reconcile()` refuses to let an expectation absorb.
    """


# --------------------------------------------------------------------------- parsing


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    seen: set[str] = set()
    for key, _value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key {key!r} in one object")
        seen.add(key)
    return dict(pairs)


def _parse(text: str, origin: str) -> dict[str, dict]:
    """Case name -> entry, refusing anything the set difference could not trust."""
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except (ValueError, TypeError) as exc:
        raise Undecidable(f"{origin} does not parse as a trustworthy expectations file: {exc}")
    rows = data.get("expectations", [])
    if not isinstance(rows, list):
        raise Undecidable(f"{origin} has no `expectations` list")
    out: dict[str, dict] = {}
    for row in rows:
        name = row.get("case")
        if not isinstance(name, str) or not name:
            raise Undecidable(f"{origin} holds an entry with no case name")
        if name in out:
            raise Undecidable(
                f"{origin} declares {name!r} twice; `load()` keys entries by case name, so "
                f"the two collapse into one and the entry set is not what the file reads as"
            )
        out[name] = row
    if len(out) != len(rows):  # unreachable given the loop, asserted anyway
        raise Undecidable(f"{origin} declares {len(rows)} entries and parses as {len(out)}")
    return out


# ------------------------------------------------------------------------ base rev


def _git(*args: str) -> tuple[int, str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(_REPO), *args],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise Undecidable(f"git is not usable here, so no base revision exists: {exc}")
    return out.returncode, out.stdout.strip()


def _is_commit(rev: str) -> bool:
    if not rev or set(rev) == {"0"} or rev == _ZERO:
        return False
    rc, _ = _git("cat-file", "-e", f"{rev}^{{commit}}")
    return rc == 0


def _from_event_payload() -> tuple[str, str] | None:
    """The base GitHub computed server-side, which is the part an agent cannot mint.

    `before` is the pushed ref's prior tip and `pull_request.base.sha` is the merge
    target; both are written into the event payload by the forge after the push landed,
    so an addition is measured against a state that existed before the adding agent
    could touch it.
    """
    path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not path or not Path(path).is_file():
        return None
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    candidates = (
        (payload.get("before"), "GITHUB_EVENT_PATH:before (prior tip of the pushed ref)"),
        (
            (payload.get("pull_request") or {}).get("base", {}).get("sha")
            if isinstance(payload.get("pull_request"), dict) else None,
            "GITHUB_EVENT_PATH:pull_request.base.sha",
        ),
    )
    for rev, how in candidates:
        if isinstance(rev, str) and _is_commit(rev):
            return rev, how
    return None


def _base() -> tuple[str, str]:
    """(rev, how it was found). Raises rather than guessing."""
    found = _from_event_payload()
    if found:
        return found

    for ref in ("origin/master", "origin/HEAD"):
        rc, resolved = _git("rev-parse", "--verify", "--quiet", ref)
        if rc != 0 or not resolved:
            continue
        rc, merge_base = _git("merge-base", "HEAD", ref)
        if rc == 0 and _is_commit(merge_base):
            return merge_base, f"git merge-base HEAD {ref}"
        if _is_commit(resolved):
            return resolved, f"git rev-parse {ref}"

    raise Undecidable(
        "no base revision: the forge event payload names none and neither origin/master "
        "nor origin/HEAD resolves, so an addition cannot be told from a repair. Fetch the "
        "default branch (CI checks out with fetch-depth: 0 for this reason) and rerun — a "
        "run that cannot see a base must not report this property as holding"
    )


def _content_at(rev: str) -> str | None:
    rc, out = _git("show", f"{rev}:{_REL}")
    if rc != 0:
        return None
    return out


# ---------------------------------------------------------------------- the differ


def _grown(base: dict[str, dict], head: dict[str, dict]) -> tuple[list[str], list[str]]:
    """(added, widened). The whole oracle, isolated so the control can drive it.

    `witness_contains` is a substring test, so containment orders two pins exactly: a new
    pin contained in the old one matches everything the old one matched and more, which is
    a strict widening; an empty pin matches every witness, which is the widest of all. A
    re-pin onto text that neither contains nor is contained by the old is **not** flagged.
    That is a real boundary and it is chosen: re-pinning a drifted entry is how a drift is
    triaged at all, there is no channel here that could ever clear it, and a permanent red
    nobody can act on is the trust erosion this suite exists to stop.
    """
    added = sorted(set(head) - set(base))

    widened: list[str] = []
    for name in sorted(set(head) & set(base)):
        old = base[name].get("witness_contains", "") or ""
        new = head[name].get("witness_contains", "") or ""
        if new == old:
            continue
        if not new:
            widened.append(f"{name}: pin emptied (was {old!r}); an empty pin matches every witness")
        elif new in old:
            widened.append(
                f"{name}: pin {new!r} is a substring of {old!r}, so it matches everything "
                f"the old pin matched and more"
            )
    return added, widened


_CONTROL_BASE = json.dumps({"expectations": [
    {"case": "planted-survivor", "witness_contains": "alpha beta gamma"},
    {"case": "planted-narrowed", "witness_contains": "beta"},
    {"case": "planted-deleted", "witness_contains": "delta"},
]})
_CONTROL_HEAD = json.dumps({"expectations": [
    {"case": "planted-survivor", "witness_contains": "beta"},
    {"case": "planted-narrowed", "witness_contains": "alpha beta gamma"},
    {"case": "planted-added", "witness_contains": "epsilon"},
]})


def _control() -> None:
    """The differ must report a planted addition and a planted widening, and only those."""
    added, widened = _grown(_parse(_CONTROL_BASE, "control-base"), _parse(_CONTROL_HEAD, "control-head"))
    problems = []
    if added != ["planted-added"]:
        problems.append(f"added={added}, expected ['planted-added']")
    if len(widened) != 1 or not widened[0].startswith("planted-survivor:"):
        problems.append(f"widened={widened}, expected exactly the planted-survivor widening")
    if problems:
        raise Undecidable(
            "positive control failed, so a clean report below would be unfalsifiable: "
            + "; ".join(problems)
        )


# ---------------------------------------------------------------------------- case


def run() -> Finding | None:
    _control()

    if not _LIVE.is_file():
        raise Undecidable(f"{_REL} is absent, so there is nothing to compare")

    head = _parse(_LIVE.read_text(encoding="utf-8"), f"the working tree's {_REL}")

    if _CASE_NAME in head:
        raise Undecidable(
            f"{_REL} holds an entry for {_CASE_NAME!r}. That entry would let an addition "
            f"acknowledge itself, which disables the only check that reports additions at "
            f"all. Delete it; this case is never a legitimate known-red"
        )

    rev, how = _base()
    base_text = _content_at(rev)
    # Absent at base is a real answer, not a failure: the commit that introduces the file
    # genuinely adds every entry in it, and reporting that is correct.
    base = _parse(base_text, f"{_REL} at {rev}") if base_text is not None else {}

    added, widened = _grown(base, head)
    if not added and not widened:
        return None

    parts = [f"base={rev[:12]} via {how}"]
    for name in added:
        row = head[name]
        parts.append(
            f"ADDED {name} (failure_class={row.get('failure_class', '?')}, "
            f"witness_contains={row.get('witness_contains', '')!r})"
        )
    parts.extend(f"WIDENED {entry}" for entry in widened)

    what = []
    if added:
        what.append(f"{len(added)} entry(ies) added")
    if widened:
        what.append(f"{len(widened)} pin(s) widened")

    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            f"the known-red list grew: {' and '.join(what)} since {rev[:12]}. Adding an "
            f"entry turns a NEW_FAILURE into a KNOWN_RED and the run's exit 1 into exit 0, "
            f"and widening a pin extends a mute already granted — neither is a unilateral "
            f"qe action (docs/13, What is allowed to go quiet). The authorization is "
            f"missing because there is nowhere to put it: no artifact this repo holds "
            f"attests operator approval to a hermetic check, so what stands in for it is "
            f"this report, on the commit that introduced the change, read by someone who "
            f"is not the agent that wrote it. Delete the entry, or leave this red until it "
            f"has been read"
        ),
        witness=" | ".join(parts),
        site=_REL,
    )


CASE = Case(
    name=_CASE_NAME,
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED,),
    summary="the known-red list may shrink freely, and may not grow unheard",
    run=run,
)
