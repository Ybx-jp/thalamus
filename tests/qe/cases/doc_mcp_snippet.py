"""No shipped doc may print an MCP registration the installer would not write.

A registration snippet in a doc is a config an operator pastes into a real machine, so
it is executable text the same way a prompt template is. `README.md` shipped one that
baked `THALAMUS_SCOPE` into the server's env (`bf24b5a`, corpus
`readme-names-file-init-deletes`). `build_mcp_entry` omits that key on purpose — its
docstring names the reason — because a scope in a static registration pins *every*
session on the box to one expert, which is a silent, machine-wide isolation failure and
not a misconfiguration anyone would notice from inside a session.

The docs carry no registration snippet today. That makes this a forward guard, and a
forward guard asserting an absence is worth exactly as much as its ability to notice
the thing coming back — "no bad snippet" and "the scanner stopped finding snippets" are
the same clean output otherwise. So the detector is a pure function over text, and the
case runs it twice: once over the shipped docs, and once over a poisoned fixture that
is the README snippet as it actually shipped. A run where the fixture comes back clean
reports a broken detector rather than a clean repo.

Two things are asserted against a snippet, both taken from the installer rather than
restated here: that it bakes no `THALAMUS_SCOPE`, and that its key set matches what
`build_mcp_entry` produces. Values are deliberately not compared — a doc may
legitimately show a different checkout path — but a key the installer does not write is
either dead config or a lever the reader will pull.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_REPO = Path(__file__).resolve().parents[3]
_FENCE = re.compile(r"```(?:json|jsonc)?\s*\n(?P<body>.*?)```", re.DOTALL)

# The README snippet as it shipped: project-scope registration with a baked scope.
_POISONED = """
```json
{
  "mcpServers": {
    "thalamus": {
      "command": "uv",
      "args": ["run", "thalamus-mcp"],
      "env": {"THALAMUS_SCOPE": "main", "THALAMUS_GRAPH_URL": "ws://localhost:8182/gremlin"}
    }
  }
}
```
"""


def _entries(text: str) -> list[dict]:
    """Every MCP server registration in a document's fenced blocks.

    Matched on shape rather than on the fence language tag, because the defect arrives
    in whatever a writer types — an untagged fence is still a config a reader pastes.
    """
    found: list[dict] = []
    for block in _FENCE.finditer(text):
        try:
            data = json.loads(block.group("body"))
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        servers = data.get("mcpServers")
        if isinstance(servers, dict):
            found.extend(v for v in servers.values() if isinstance(v, dict))
        elif "command" in data and "thalamus-mcp" in json.dumps(data.get("args", [])):
            found.append(data)
    return found


def _violations(text: str, label: str, expected_keys: set[str]) -> list[str]:
    out: list[str] = []
    for entry in _entries(text):
        env = entry.get("env")
        if isinstance(env, dict) and "THALAMUS_SCOPE" in env:
            out.append(
                f"{label}: registration bakes THALAMUS_SCOPE="
                f"{env['THALAMUS_SCOPE']!r}, which pins every session on the box"
            )
        extra = sorted(set(entry) - expected_keys)
        if extra:
            out.append(f"{label}: registration carries keys the installer never writes: {extra}")
    return out


def run() -> Finding | None:
    from thalamus.harness.install import build_mcp_entry  # noqa: PLC0415

    expected_keys = set(build_mcp_entry())

    # CONTROL, first: the detector must flag the snippet that actually shipped. Run
    # before the real scan so a clean repo can never be reported by a broken scanner.
    control = _violations(_POISONED, "control", expected_keys)
    if not control:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the detector no longer flags the snippet this defect actually "
                    "shipped, so a clean scan of the docs would mean nothing",
            witness=f"poisoned fixture produced no violation; expected_keys={sorted(expected_keys)}",
            site="tests/qe/cases/doc_mcp_snippet.py::_POISONED",
        )

    docs = [_REPO / "README.md", *sorted((_REPO / "docs").rglob("*.md"))]
    present = [p for p in docs if p.is_file()]
    if not present:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="no docs were found to scan, so 'no bad snippet' means 'nothing read'",
            witness=f"looked under {_REPO}/README.md and {_REPO}/docs",
            site="tests/qe/cases/doc_mcp_snippet.py",
        )

    violations: list[str] = []
    for path in present:
        violations += _violations(
            path.read_text(encoding="utf-8", errors="ignore"),
            str(path.relative_to(_REPO)),
            expected_keys,
        )

    if not violations:
        return None

    return Finding(
        failure_class=FailureClass.DOC_CODE_DRIFT,
        summary=(
            "a shipped doc prints an MCP registration the installer would not write — "
            "text an operator pastes into a live machine, diverging from the one code "
            "path that owns that config"
        ),
        witness="; ".join(violations[:6]),
        site="README.md / docs/** vs harness/install.py::build_mcp_entry",
    )


CASE = Case(
    name="docs-print-no-foreign-mcp-registration",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.DOC_CODE_DRIFT, FailureClass.COLLAPSED_SENTINEL),
    summary="registration snippets in docs must match build_mcp_entry and bake no scope",
    run=run,
)
