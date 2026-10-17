"""Declared case retirements: the one way a case module may leave the suite on purpose.

`case-erosion-is-never-silent` reports a case module that was tracked at the base
revision and is gone from disk or from `run.py`'s `CASE_MODULES` at head. A case whose
subject was deleted from `src/` has to go, and the guard had no way to tell that from a
detector being removed. This file is that way, and it is built on the two mechanisms the
suite already has rather than a third:

- **The file shape and its parser** are `expectations.json`'s: a committed list of
  entries under one key, each carrying a human reason, with the duplicate-key and
  duplicate-name refusals `174b44c` made permanent (`expectations._no_duplicate_keys`,
  `expectation_additions._parse`). An entry that silently fails to parse would make
  "declared" and "undeclared" one state.
- **The surfacing** is `expectation_additions.py`'s: a retirement turns a red into a
  non-red exactly as a known-red entry does, so a retirement added since the base
  revision is reported by that case, which CI runs alone as the unrequired `mute-review`
  job. `adversarial` passes the removal; `mute-review` goes red naming it, until someone
  who did not write the change has read it.
- **The stale rule** is `thalamus arch rules --gate`'s two-direction rule for its
  `accepted` list (an exception that stopped firing fails the build). It applies here
  in the form this repository's base-relative checks can state; see
  `case_logic_erosion.py`, section "Declared retirements".

Format of `tests/qe/retirements.json`:

    {"retirements": [
      {"module": "qe.cases.ci_triage_verify_report",
       "reason": "what the case asserted about, and why it has no subject now",
       "removed_by": "#348"}
    ]}

`module` is the dotted name as it appears in `CASE_MODULES`. `removed_by` is an issue or
pull-request reference (`#348`) or the `src/` path that no longer exists. `reason` is
free text and must be non-empty.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

RETIREMENTS_PATH = Path(__file__).parent / "retirements.json"
RETIREMENTS_REL = "tests/qe/retirements.json"

_MODULE = re.compile(r"^qe\.cases\.[A-Za-z0-9_]+$")
_POINTER = re.compile(r"^(#\d+|src/\S+)$")


class MalformedRetirements(Exception):
    """The declarations cannot be read. Never a verdict about the code."""


@dataclass(frozen=True)
class Retirement:
    module: str
    reason: str
    removed_by: str

    @property
    def case_file(self) -> str:
        return f"tests/qe/cases/{self.module.rsplit('.', 1)[-1]}.py"


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    seen: set[str] = set()
    for key, _value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key {key!r} in one object")
        seen.add(key)
    return dict(pairs)


def parse(text: str, origin: str) -> dict[str, Retirement]:
    """Module name -> Retirement. Refuses anything a set difference could not trust."""
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except (ValueError, TypeError) as exc:
        raise MalformedRetirements(f"{origin} does not parse as a retirements file: {exc}")
    if not isinstance(data, dict):
        raise MalformedRetirements(f"{origin} is not a JSON object")
    rows = data.get("retirements", [])
    if not isinstance(rows, list):
        raise MalformedRetirements(f"{origin} has no `retirements` list")
    out: dict[str, Retirement] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise MalformedRetirements(f"{origin} holds a non-object entry: {row!r}")
        module = row.get("module")
        if not isinstance(module, str) or not _MODULE.match(module):
            raise MalformedRetirements(
                f"{origin} holds an entry whose `module` is {module!r}; expected a "
                f"dotted name like 'qe.cases.some_case', as written in CASE_MODULES")
        reason, pointer = row.get("reason"), row.get("removed_by")
        if not isinstance(reason, str) or not reason.strip():
            raise MalformedRetirements(f"{origin}: {module} carries no `reason`")
        if not isinstance(pointer, str) or not _POINTER.match(pointer):
            raise MalformedRetirements(
                f"{origin}: {module} `removed_by` is {pointer!r}; name the issue or PR "
                f"('#348') or the src/ path whose removal ends the case's subject")
        if module in out:
            raise MalformedRetirements(
                f"{origin} declares {module!r} twice; the two would collapse into one")
        out[module] = Retirement(module, reason.strip(), pointer)
    return out
