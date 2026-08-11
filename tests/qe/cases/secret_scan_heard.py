"""The secret scan over retained bytes must reach someone who can act on it.

`transcripts.retain()` returns `(entry, scan_for_secrets(payload))`. The scan is the
archive's only warning surface: it reports and never redacts, deliberately — evidence
quietly rewritten is not evidence — so the whole value of running it is that a human is
told. docs/10 states the risk plainly: transcripts hold whatever was on screen, and
scans of this repo's own transcripts have flagged real keys, including one already
purged from git history.

`thalamus bootstrap` binds the findings and prints them. The path that runs at **every
session end** — `cli.py`'s extract, which also carries every fork delta — spends the
scan and drops it on the floor:

    entry, _ = transcripts.retain(facts.path)

Nobody chooses to compute a warning and discard it, which is what makes this an
unenforced signal rather than a design: the detector is correct, runs constantly, and
has no consumer. Bootstrap is the one-time historical import; extract is the recurring
one, and the recurring one is silent.

Corpus record: `archive-bytes-hash-the-whole-fork` names this as the adjacent testable
property — assert the secret scan reaches every archived Source a fork produces. It does
not: a fork's delta is retained through the same discarding call site.

The second half of the invariant is coverage: `ingest.py` archives fetched third-party
bytes through `archive_bytes` directly, never through `retain`, so those bytes are never
scanned at all. Both halves are the same property — bytes entering the archive are
scanned, and the finding is heard — so they are one case with one enumerated witness.
Fixing either half moves the witness and drifts the entry rather than shrinking it
silently.

Read out of the AST rather than by driving the CLI, because driving extract needs a live
graph and a real model call. The behavioural half that *is* hermetic — that the scanner
detects a planted credential at all — runs as the control, so "no findings anywhere"
can never be reported by a scanner that stopped matching.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SRC = Path(__file__).resolve().parents[3] / "src" / "thalamus"
# Under the archive package the two functions are defined and re-exported; call sites
# there are the mechanism, not consumers of it.
_MECHANISM = ("archive",)

_RETAIN = "retain"
_ARCHIVE = "archive_bytes"
_SCAN = "scan_for_secrets"

# A planted credential in the shape of a pattern the scanner declares. Fake, and shaped
# so it cannot be a live key: the point is the scanner's reach, not the value.
_CANARY = b'{"env": {"AWS_ACCESS_KEY_ID": "AKIAQE00000000TESTAA"}}'


def _called_names(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                out.add(func.id)
            elif isinstance(func, ast.Attribute):
                out.add(func.attr)
    return out


def _discards_findings(tree: ast.AST) -> list[tuple[int, str]]:
    """Assignments that call `retain` and throw the second element away.

    `entry, _ = retain(...)` and `entry = retain(...)[0]` are both discards; binding the
    tuple to a name is not, because a name can still be read. This does not chase what a
    binding is later used for — an unread variable is a different (and louder) defect
    that linters already catch.
    """
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value, target = node.value, node.targets[0] if node.targets else None
        call = None
        if isinstance(value, ast.Call):
            call = value
        elif isinstance(value, ast.Subscript) and isinstance(value.value, ast.Call):
            call = value.value
        if call is None:
            continue
        func = call.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name != _RETAIN:
            continue
        if isinstance(value, ast.Subscript):
            found.append((node.lineno, "retain(...)[0] — findings never bound"))
        elif isinstance(target, ast.Tuple) and len(target.elts) == 2:
            second = target.elts[1]
            if isinstance(second, ast.Name) and second.id == "_":
                found.append((node.lineno, "entry, _ = retain(...) — findings discarded"))
    return found


def _archives_without_scanning(tree: ast.AST) -> list[tuple[int, str]]:
    """Functions that call `archive_bytes` and never call the scanner."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        called = _called_names(node)
        if _ARCHIVE in called and _SCAN not in called:
            found.append((node.lineno, f"{node.name}() archives bytes, never scans them"))
    return found


def run() -> Finding | None:
    from thalamus.archive import scan_for_secrets  # noqa: PLC0415

    # CONTROL: the scanner must find a planted credential. Every claim below is about
    # whether the scan's output reaches anyone; if the scan itself found nothing, a
    # clean call graph would be reporting on a scanner that matches nothing.
    hits = scan_for_secrets(_CANARY)
    if not hits:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the secret scanner did not flag a planted credential, so 'the "
                    "finding is not heard' cannot be distinguished from 'there is no "
                    "finding to hear'",
            witness=f"scan_for_secrets(canary) returned {hits!r}",
            site="src/thalamus/archive/store.py::scan_for_secrets",
        )

    # CONTROL: the discard detector must recognise the shape it is hunting, so that a
    # clean scan means the code changed rather than the matcher.
    probe = _discards_findings(ast.parse("entry, _ = transcripts.retain(path)\n"))
    if not probe:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the discard detector no longer recognises `entry, _ = retain(...)`, "
                    "so this case would report a clean call graph either way",
            witness="synthetic discard produced no match",
            site="tests/qe/cases/secret_scan_heard.py::_discards_findings",
        )

    if not _SRC.is_dir():
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="source tree not found, so 'every finding is heard' and 'nothing was "
                    "read' are the same result",
            witness=str(_SRC),
            site="tests/qe/cases/secret_scan_heard.py",
        )

    violations: list[str] = []
    retention_sites = 0
    for path in sorted(_SRC.rglob("*.py")):
        relative = path.relative_to(_SRC.parents[1])
        if relative.parts[1:2] and relative.parts[1] in _MECHANISM:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        called = _called_names(tree)
        if _RETAIN in called or _ARCHIVE in called:
            retention_sites += 1
        for lineno, why in _discards_findings(tree) + _archives_without_scanning(tree):
            violations.append(f"{relative}:{lineno} {why}")

    # CONTROL: the scan must have found retention sites at all.
    if retention_sites == 0:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="no call to retain() or archive_bytes() was found in src/, so a clean "
                    "result means the scan stopped reaching the archive path",
            witness=f"scanned {_SRC}, matched 0 retention sites",
            site="tests/qe/cases/secret_scan_heard.py",
        )

    if not violations:
        return None

    return Finding(
        failure_class=FailureClass.UNENFORCED_SIGNAL,
        summary=(
            "the archive's secret scan has no consumer on the paths that run: the "
            "session-end path computes the findings and discards them, and the ingest "
            "path archives bytes without scanning at all — a warning surface that warns "
            "nobody, on the highest-risk artifact this project holds (docs/10)"
        ),
        witness=f"{len(violations)} site(s) across {retention_sites} file(s): "
                + "; ".join(violations[:6]),
        site="src/thalamus/cli.py (extract) and src/thalamus/harness/ingest.py",
    )


CASE = Case(
    name="retained-bytes-secret-scan-is-heard",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.UNENFORCED_SIGNAL, FailureClass.COLLAPSED_SENTINEL),
    summary="every path that archives bytes must scan them and surface the findings",
    run=run,
)
