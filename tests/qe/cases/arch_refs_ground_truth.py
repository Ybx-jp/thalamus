"""The class-A reference recognizer must reproduce a hand-declared disposition, and the
gap report over it must account for every input it was ever shown.

Issue #127 part 1: `src/thalamus/arch/references.py` ships with `tests/test_arch_references.py`
as its only coverage, and that is the author's own unit suite — the same consultation
`972d0bc03c7542d5` that split `arch_extractor.py`/`arch_route_channel.py`'s ground truth
out of the extractor's own author settles this for the reference channel too. This case
and the fixture corpus at `tests/qe/fixtures/arch_refs/` are written independently of
that suite, from the issue's own adversarial list rather than from the module's tests.

Five dispositions, one fixture file each, under `repo/code/refs_fixtures/`:

1. `unconsumed_form.py` — a backticked reference outside every recognised extension
   (`docs/plan.txt`). Proves the gap report is complement-shaped, not a whitelist — the
   `oracle_parses_whole.py` defect class, where a declared cardinality silently shrank
   and nothing refused it.
2. `class_c_decline.py` — a class-C referent (a vendor release, `botocore.__version__`)
   shaped as a dotted name. Declining to judge it is a required pass, asserted here as
   membership in `report.dotted`, never inferred from its absence from the findings.
3. `asserted_absence.py` — a sentence that asserts its own referent's absence
   (`mod/ghost.py`). Must land in `asserted-absent`, never `dangling`.
4. `quoted_negation.py` / `prev_sentence_negation.py` — a false suppression in each
   direction: a negation inside a quotation, and a negation that belongs to the
   previous, already-terminated sentence rather than to a genuine line wrap. Both must
   still resolve `dangling` — the reference is real in both fixtures.
5. `unknown_form.py` — a GitHub-style line-anchor citation (`reader.py#L106`), a
   recognizer form none of `_PATH`/`_PATH_LINE`/`_BARE_FILE`/`_DOTTED` knows. Must be
   reported (`unconsumed`), not silently skipped.

`resolved_control.py` carries a manifest entry marked `self_test: true` whose declared
`expected` is deliberately WRONG (`dangling`, when `mod/anchor.py` is present and the
real disposition is `resolved`). Kept as a **permanent** discrimination control rather
than a one-off manual check: every run confirms the per-fixture comparison actually
tells right from wrong, by confirming the wrong pin still disagrees with reality. Run
directly and reverted before commit, the classic direction was also exercised by hand —
flipping `asserted_absence`'s `expected` to `"dangling"` and re-running reported exactly
one mismatch (`INVARIANT_FALSIFIED`, naming that id) before being reverted.

Two controls beyond the five, both load-bearing:

- **Corpus-nonempty / corpus-complete.** If the manifest yields zero entries, or a
  count that disagrees with the number of fixture files actually on disk, that is
  MALFORMED ground truth, not a clean pass — "every fixture passed" over an empty or
  truncated corpus is the collapsed sentinel this suite exists to hunt, and it is
  checked before a single disposition is compared.
- **Union-accounts-for-the-whole-input.** Every fixture's token is looked up in all
  three of `report.references` / `report.dotted` / `report.unconsumed`, never just the
  bucket its `expected` value predicts; a token found in none of them is `"vanished"`,
  which is a distinct, reportable disposition rather than a silent pass.

That last reading caught a live defect, not a hypothetical one: `refs_fixtures_known_defect/
vanishing_bare_reference.py` cites `routes.py` in plain prose, with no backticks and no
directory prefix. `_CANDIDATE`'s bare-form alternative requires a `/`, and its backtick
alternative requires backticks, so this citation matches neither — it is absent from
`references`, from `dotted`, and from `unconsumed` alike, contradicting the module's own
claim that the gap report is complement-shaped. Filed as issue #172; this case is
tagged against it and expected to fail (`tests/qe/expectations.json` pins the current
witness) until `_CANDIDATE` grows a bare-word-with-no-slash alternative.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "arch_refs"
REPO = FIXTURE_DIR / "repo"
MANIFEST = FIXTURE_DIR / "manifest.json"
FIXTURES_SUBDIR = REPO / "code" / "refs_fixtures"

# The known, unfixed defect this corpus's completeness check surfaced. Not part of the
# manifest-driven comparison above: its actual disposition is not one of the five the
# manifest vocabulary names, it is the absence of any of them.
KNOWN_DEFECT_FILE = "code/refs_fixtures_known_defect/vanishing_bare_reference.py"
KNOWN_DEFECT_TARGET = "routes.py"
KNOWN_DEFECT_ISSUE = 172


def _load_manifest() -> tuple[list[dict], str | None]:
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], f"manifest did not parse: {exc}"
    entries = data.get("fixtures")
    if not isinstance(entries, list):
        return [], "manifest has no `fixtures` list"
    return entries, None


def _actual_disposition(report, file_: str, target: str) -> str:
    """Where `target` in `file_` actually landed. `"vanished"` if none of the three."""
    for reference in report.references:
        if reference.file == file_ and reference.target == target:
            return reference.status
    for row_file, _lineno, name in report.dotted:
        if row_file == file_ and name == target:
            return "declined"
    for row_file, _lineno, raw in report.unconsumed:
        if row_file == file_ and target in raw:
            return "unconsumed"
    return "vanished"


def run() -> Finding | None:
    from thalamus.arch import references as refs  # noqa: PLC0415

    entries, error = _load_manifest()
    on_disk = sorted(p.name for p in FIXTURES_SUBDIR.glob("*.py")) if FIXTURES_SUBDIR.is_dir() else []

    # CONTROL: corpus-nonempty / corpus-complete. An empty or truncated manifest is a
    # malformed oracle, never a clean pass over nothing.
    if error is not None or not entries or len(entries) != len(on_disk):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "the arch_refs fixture manifest is empty, unreadable, or disagrees with "
                "the fixture files on disk — 'every fixture passed' over a corpus that "
                "did not load in full is the collapsed sentinel this suite hunts"
            ),
            witness=f"manifest error={error!r}, {len(entries)} entrie(s) vs "
                     f"{len(on_disk)} file(s) on disk: {on_disk}",
            site="tests/qe/fixtures/arch_refs/manifest.json",
        )

    policy = refs.ReferencePolicy(enabled=True, roots=("code",))
    report = refs.census(REPO, policy)

    mismatches: list[str] = []
    control_losses: list[str] = []

    for entry in entries:
        actual = _actual_disposition(report, entry["file"], entry["target"])
        if entry.get("self_test"):
            # The discrimination control: `expected` here is deliberately wrong. If it
            # ever equals reality, the comparison this case relies on has lost its bite
            # — that is itself worth reporting, not a quiet pass.
            if actual == entry["expected"]:
                control_losses.append(
                    f"{entry['id']}: the deliberately-wrong expected {entry['expected']!r} "
                    f"matched the real disposition — the discrimination control no "
                    "longer discriminates"
                )
            continue
        if actual != entry["expected"]:
            mismatches.append(
                f"{entry['id']} ({entry['file']}): expected {entry['expected']!r}, "
                f"observed {actual!r}"
            )

    if control_losses:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the permanent discrimination control's deliberately-wrong pin "
                    "matched reality, so a real mismatch could pass unnoticed",
            witness="; ".join(control_losses),
            site="tests/qe/cases/arch_refs_ground_truth.py",
        )

    if mismatches:
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary="the reference recognizer's disposition disagrees with the "
                    "hand-declared ground-truth fixture corpus",
            witness="; ".join(mismatches),
            site="src/thalamus/arch/references.py:census",
        )

    # The union-accounting reading: a real, unfixed defect. A citation shaped like a
    # bare filename, with no backticks and no directory, is invisible to `_CANDIDATE`
    # and so is absent from references/dotted/unconsumed alike.
    defect_actual = _actual_disposition(report, KNOWN_DEFECT_FILE, KNOWN_DEFECT_TARGET)
    if defect_actual == "vanished":
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary="a bare filename cited with no backticks and no directory prefix "
                    "is accounted for by none of resolved/dangling/asserted-absent/"
                    "declined/unconsumed — the gap report's own complement-shaped claim "
                    "is false for this citation shape",
            witness=f"{KNOWN_DEFECT_FILE} cites {KNOWN_DEFECT_TARGET!r} in plain prose "
                     "with no backticks and no directory prefix; census finds it in "
                     "none of references, dotted, or unconsumed",
            site="src/thalamus/arch/references.py:_CANDIDATE",
        )

    return None


CASE = Case(
    name="arch-refs-ground-truth",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary=(
        "The class-A reference recognizer reproduces a hand-declared disposition over "
        "an adversarial fixture corpus, and the corpus's own completeness is checked "
        "before any disposition is."
    ),
    run=run,
    issue=KNOWN_DEFECT_ISSUE,  # #172: a bare, unbacktick-ed, slash-less filename vanishes
    fixed=False,
)
