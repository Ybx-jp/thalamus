"""Every expectation the oracle declares must parse, or absent and acknowledged are one.

`174b44c`: a missing `},{` merged one entry's keys into the object above it. The file
declared eleven expectations and parsed as ten, because `json.loads` resolves a duplicate
key by keeping the last one. Benign that time only by luck — the swallowed entry was
declared again, complete, further down.

It is the suite's own signature failure committed inside the suite's own oracle. Every
verdict this suite reaches is `reconcile(result, expectations)`, so an expectation that
silently does not parse turns a triaged known-red into a `NEW_FAILURE` (noisy, survivable)
or — the direction that matters — leaves the acknowledged set shorter than the file says
without any step downstream able to notice. `absent` and `acknowledged` become one state.
That it was found by an architect reading a boundary ticket, and not by the runner, is the
point: the runner could not see it.

Two collapses, one class, and the loader now refuses both:

1. **Duplicate keys inside one object** — what the merge produces. `load()` parses with an
   `object_pairs_hook` that raises.
2. **Two entries naming one case** — `out[exp.case] = exp` would keep the last and shrink
   the set with no diagnostic. A different edit, the same silence.

`expectation-additions-are-never-silent` already refused duplicates on both sides of its
own diff (docs/13, *The oracle's own protection*). That guarded the comparison and not the
**load every case is reconciled against**, which is the path that runs on every push — so
the hole was in the one place with no second reader.

This case asserts the refusal rather than the file's current cleanliness. A case checking
only that today's file parses goes green the moment the file is repaired and stays green
if the *loader* regresses, which is the half that actually protects anything.

The third collapse is the one the loader does not raise on: **an empty acknowledged set
that nobody declared.** An absent file, or a present one whose `expectations` key is
missing or misnamed, both come back from `load()` as an empty dict with no diagnostic,
and every known-red then reads as a new regression. An empty set is *also* the correct
state of a suite whose triaged defects have all been fixed, so emptiness alone cannot be
the finding — the file's declared row count is compared against the count the loader
returned, and only a disagreement, or a file that declares nothing at all, is the
collapse.

**Shown capable of going red, and the mutants are the shapes the defect took.** The two
parse collapses are fed as text, so neither touches the committed file: the merged-object
shape lifted from `174b44c^` reports `invariant-falsified`, and so does a file with one
case named twice. A well-formed file must load clean in the same run, or a loader that
raises on everything would pass this case while breaking the suite. The undeclared-empty
branch is driven by pointing `EXPECTATIONS_PATH` at a temp file — `{}`, `{"expectation":
[]}` (a misnamed key) and a path that does not exist each report `collapsed-sentinel`,
while `{"expectations": []}` passes, which is the discrimination the branch exists for.
"""

from __future__ import annotations

import json

from ..model import Case, FailureClass, Finding, Substrate, Tier

# The shape `174b44c` actually had: the second entry's keys merged into the first object,
# so `case` appears twice inside one object and the entry count silently drops by one.
_MERGED = """
{"expectations": [
  {"case": "a", "failure_class": "failed-open", "witness_contains": "x",
   "case": "b", "failure_class": "boundary-leak", "witness_contains": "y"}
]}
"""

# One level up: two well-formed entries naming one case. `json.loads` is happy; the dict
# keyed on case name is where this one collapses.
_TWICE_NAMED = """
{"expectations": [
  {"case": "a", "failure_class": "failed-open", "witness_contains": "x"},
  {"case": "a", "failure_class": "boundary-leak", "witness_contains": "y"}
]}
"""

_WELL_FORMED = """
{"expectations": [
  {"case": "a", "failure_class": "failed-open", "witness_contains": "x"},
  {"case": "b", "failure_class": "boundary-leak", "witness_contains": "y"}
]}
"""


def _load_text(text: str) -> tuple[int, str | None]:
    """Run the loader's own refusals over `text`. Returns (entries, refusal message)."""
    from .. import expectations as exp_mod  # noqa: PLC0415

    try:
        data = json.loads(text, object_pairs_hook=exp_mod._no_duplicate_keys)
    except exp_mod.MalformedExpectations as exc:
        return 0, str(exc)
    seen: set[str] = set()
    for row in data.get("expectations", []):
        if row["case"] in seen:
            return len(seen), f"two expectations name the case {row['case']!r}"
        seen.add(row["case"])
    return len(seen), None


def _declared_rows(path) -> int | None:
    """How many entries the committed file DECLARES, or None if it declares nothing.

    Read separately from `load()` because the two answers differ in exactly the case
    that matters. `load()` returns an empty dict with no diagnostic for an absent file
    and for a file whose `expectations` key is missing or misnamed, and an empty dict
    is also what a suite with every triaged defect fixed correctly produces. Counting
    the rows the file declares is what separates those: a declared zero is a real zero,
    and a declaration the loader did not return is a collapse.

    Parsed with a plain `json.loads` on purpose. The duplicate-key and duplicate-case
    refusals belong to the loader and have already run by the time this is called, so
    repeating them here would only make this helper a second, drifting oracle.
    """
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    rows = data.get("expectations") if isinstance(data, dict) else None
    return len(rows) if isinstance(rows, list) else None


def run() -> Finding | None:
    from .. import expectations as exp_mod  # noqa: PLC0415

    # CONTROL, and it runs first: a well-formed file must load clean. Without it, a loader
    # that refused everything would satisfy both assertions below while making the suite
    # unrunnable — "it rejects the bad file" and "it rejects every file" are the same
    # observation from the mutants alone.
    count, refusal = _load_text(_WELL_FORMED)
    if refusal is not None or count != 2:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the loader refused a well-formed expectations file, so its refusal "
                    "of a malformed one is not evidence that it discriminates",
            witness=f"well-formed file yielded {count} entrie(s), refusal={refusal!r}",
            site="tests/qe/expectations.py:load",
        )

    survived = []
    for label, text, declared in (("merged object (174b44c)", _MERGED, 2),
                                  ("one case named twice", _TWICE_NAMED, 2)):
        parsed, refusal = _load_text(text)
        if refusal is None:
            survived.append(f"{label}: declared {declared}, parsed {parsed}, no refusal")

    # The real file must also load — a green here that rested on an unreadable oracle
    # would be reporting on nothing.
    try:
        real, _sha = exp_mod.load()
    except exp_mod.MalformedExpectations as exc:
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary="the committed expectations file does not parse, so no case in this "
                    "suite can be reconciled against the acknowledgements it declares",
            witness=str(exc),
            site="tests/qe/expectations.json",
        )
    # An acknowledged set of zero is a legitimate state — it is what the suite looks like
    # when every triaged defect has been fixed and its entry deleted — so emptiness alone
    # is not the finding. The collapse is emptiness arriving from an oracle that could not
    # be read: an absent file, or a `expectations` key that is missing, misnamed or not a
    # list. `load()` answers all of those with an empty dict and no diagnostic, which is
    # the same answer it gives for a file that declares nothing, so the count the file
    # declares is compared against the count that loaded.
    declared = _declared_rows(exp_mod.EXPECTATIONS_PATH)
    if declared is None:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the committed expectations file declares no readable `expectations` "
                    "list, so an acknowledged set of zero cannot be told from an oracle "
                    "that was never read and every known-red would be a new regression",
            witness=f"{exp_mod.EXPECTATIONS_PATH.name} yielded no `expectations` list",
            site="tests/qe/expectations.json",
        )
    if declared != len(real):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the expectations file declares a different number of entries from "
                    "the one the loader returned, so an acknowledgement was dropped "
                    "between the file and the reconciliation every case is judged by",
            witness=f"file declares {declared} entrie(s), load() returned {len(real)}",
            site="tests/qe/expectations.py:load",
        )

    if not survived:
        return None

    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            "the expectations loader silently resolves a collapse instead of refusing it: "
            "an entry that does not parse leaves the acknowledged set shorter than the "
            "file declares, and nothing downstream can tell absent from acknowledged"
        ),
        witness="; ".join(survived),
        site="tests/qe/expectations.py:load",
    )


CASE = Case(
    name="oracle-refuses-a-collapse-it-cannot-report",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="the expectations loader must refuse duplicate keys and duplicate case "
            "names rather than resolving them last-wins",
    run=run,
)
