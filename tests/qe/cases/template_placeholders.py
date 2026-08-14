"""A tracked template must not carry a real value on a line that names a secret or a host.

`deploy/penpot/.env.example` says on its own second line that it is the tracked template
and *must never carry a real secret*. It shipped carrying this machine's real tailnet host
on `PENPOT_PUBLIC_URI` — the one line in the file that was not a `REPLACE-ME` (`c9a0082`).
The repository is public. A tag cut before that commit would have published it, and a
published host identifier is not retractable: the file can be edited, the git history and
every clone cannot.

The property is narrow on purpose, because the obvious wide version is wrong. "Every value
in a template is a placeholder" goes red on `PENPOT_FLAGS=enable-registration ...`, which
is a real value and *should* be — feature flags are the documentation. What must be a
placeholder is the value of a key whose name says it carries a credential or an address:
`*_KEY`, `*_TOKEN`, `*_SECRET`, `*_PASSWORD`, `*_URI`, `*_HOST`, `*_EMAIL`. That is the
class the leak was in, and keying on the *name* rather than on the value's shape is what
lets the check fire on a real hostname — which no credential-pattern scanner recognises,
because a hostname is not a credential. `scan_for_secrets` would not have caught this one.

**Placeholder is defined positively.** Empty, or carrying an explicit marker: `REPLACE-ME`,
an `<angle-bracketed>` span, or `CHANGEME`/`YOUR-`. Anything else is a real value. A
negative definition — "does not look like a secret" — is the check that passed the tailnet
host, since a hostname looks exactly like documentation.

**Two controls, both running.** The scan must find at least one secret-named key, or a
template that stopped having any (renamed keys, a moved file, a glob that matches nothing)
reports the same clean pass as a correct one. And the placeholder predicate is exercised
against a synthetic real value on every run, because a predicate that has drifted into
always-true would clear the very line this case exists for.

**Shown capable of going red.** Point `_TEMPLATES` at a fixture holding
`PENPOT_PUBLIC_URI=https://penpot.some-tailnet.ts.net` and the case reports
`invariant-falsified` naming the file, the key and the value; the same fixture with
`<your-tailnet>` restored returns green. Run against the tree as it stood at `c9a0082^`,
it reports the leak that shipped.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_REPO = Path(__file__).resolve().parents[3]

# Keys whose value is a credential or an address. Matched on the key name, because the
# leak was a hostname and a hostname has no distinguishing shape.
_SENSITIVE = re.compile(
    r"(?i)(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH|URI|URL|HOST|EMAIL|USERNAME)")

# What a placeholder looks like, stated positively.
_PLACEHOLDER = re.compile(r"(?i)(REPLACE[-_]ME|CHANGE[-_]?ME|YOUR[-_]|<[^>]+>|\$\{[^}]+\})")

_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.*)$")


def _is_placeholder(value: str) -> bool:
    stripped = value.strip().strip("\"'")
    if not stripped:
        return True                      # nothing to leak
    return bool(_PLACEHOLDER.search(stripped))


def _templates() -> list[Path]:
    """Tracked files that are templates. Enumerated from git, not from a hand list."""
    out = subprocess.run(["git", "ls-files", "-z"], cwd=str(_REPO),
                         capture_output=True, text=True, check=False)
    names = [n for n in out.stdout.split("\0") if n]
    return [_REPO / n for n in names
            if n.endswith(".example") or n.endswith(".example.env")
            or Path(n).name.startswith(".env.")]


def run() -> Finding | None:
    # CONTROL, and it runs: the predicate must still be able to say "not a placeholder".
    if _is_placeholder("https://penpot.some-real-tailnet.ts.net"):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the placeholder predicate accepts a real hostname, so it cannot "
                    "detect the value this case exists for and its green means nothing",
            witness="_is_placeholder('https://penpot.some-real-tailnet.ts.net') is True",
            site="tests/qe/cases/template_placeholders.py:_is_placeholder",
        )

    templates = _templates()
    if not templates:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="no tracked template was found, so 'no template leaks a real value' "
                    "and 'no template was read' are the same result",
            witness=f"git ls-files under {_REPO} matched no .example file",
            site="tests/qe/cases/template_placeholders.py:_templates",
        )

    checked, leaks = 0, []
    for path in templates:
        try:
            text = path.read_text(errors="replace")
        except OSError as exc:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="a tracked template could not be read, so it was not checked and "
                        "the clean result does not cover it",
                witness=f"{path}: {type(exc).__name__}: {exc}",
                site="tests/qe/cases/template_placeholders.py",
            )
        for number, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            match = _ASSIGNMENT.match(line)
            if not match or not _SENSITIVE.search(match.group("key")):
                continue
            checked += 1
            value = match.group("value").split(" #")[0]
            if not _is_placeholder(value):
                rel = path.relative_to(_REPO)
                leaks.append(f"{rel}:{number} {match.group('key')}={value.strip()[:60]}")

    # CONTROL: the scan must have reached a key of the kind this case is about.
    if checked == 0:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="no secret-named key was found in any tracked template, so this case "
                    "would pass a template whose keys were all renamed out of its reach",
            witness=f"{len(templates)} template(s) read, 0 assignments matched "
                    f"{_SENSITIVE.pattern}",
            site="tests/qe/cases/template_placeholders.py:_SENSITIVE",
        )

    if not leaks:
        return None

    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            "a tracked template carries a real value on a line naming a credential or a "
            "host — this repository is public, and a tag publishes it to every clone, "
            "where editing the file afterwards does not take it back"
        ),
        witness=f"{len(leaks)} of {checked} secret-named assignment(s): " + "; ".join(leaks[:6])
                + (f" (+{len(leaks) - 6} more)" if len(leaks) > 6 else ""),
        site="tracked *.example templates",
    )


CASE = Case(
    name="tracked-templates-carry-only-placeholders",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="every credential- or host-named key in a tracked template must hold a "
            "placeholder, not a real value",
    run=run,
)
