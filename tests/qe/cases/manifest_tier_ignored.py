"""A manifest's declared origin tier must reach the provenance ingest stamps.

Issue #283: `ExpertManifest.tier` (`contract/manifest.py:275`, "Origin tier of this
expert's content sources") is parsed from every `config/experts/*.yaml` and read by
nothing — `grep` over `src/` finds no attribute read of a manifest's `tier`. Ingest
stamps the tier itself, hardcoded, in `build_batch()` (`harness/ingest.py:572-576`):

    provenance = Provenance(
        tier=Tier.CURATED,
        source=origin,
        ingested_at=datetime.now(timezone.utc),
    )

Every claim's and entity's `Provenance` is built from that one value regardless of
`scope`. A manifest declaring `tier: 3` (`Tier.WILD`, "external content from unvetted
sources") gets its ingested content written at `Tier.CURATED` (2) — the operator's
downgrade never reaches the graph, and `substrate/schema.py`'s floor-over-`derived_from`
computation never sees it either, because there is nothing lower to floor to.

Driven directly against `ingest()` end to end, hermetically: a temp `THALAMUS_CONFIG_DIR`
holds one manifest declaring `tier: 3`, the document is a local file (bypasses the
network and the allowlist gate the same way an operator hand-feeding a file always
does — `check_origin`'s own docstring), and `extraction.run_extraction` is replaced
with a recorder that returns a fixed, valid extraction body, so no model is ever called.
`build_batch` is a pure function over its arguments; nothing here depends on a live
graph.

The positive control is two-fold: the manifest must actually declare 3 (not silently
fall back to the pydantic default of 2, which would make this pass for the wrong
reason), and the stub extraction must actually produce a claim and an entity for the
batch to carry a `Provenance` at all.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SCOPE = "qe-tier-probe"

_MANIFEST_YAML = f"""\
contract: v0
scope: {_SCOPE}
name: "QE tier probe"
domain: "adversarial probe scope for issue 283 — never a real roster expert"
tier: 3
"""

# >=200 chars: ingest.preflight refuses anything shorter as too thin to assert
# anything, before extraction is ever reached.
_DOCUMENT = (
    "PROBE DOCUMENT. " + (
        "This body exists only to clear the 200-character floor ingest applies "
        "before it will assert anything at all about a fed document. "
    ) * 3
)

_EXTRACTION_YAML = """\
```yaml
title: "Probe Document"
claims:
  - description: "The probe document asserts one thing, for the batch to carry."
    kind: literature/finding
    citation: "PROBE DOCUMENT"
    about:
      - "Probe Entity"
entities:
  - name: "Probe Entity"
    kind: concept
    description: "A stand-in entity, minted only so the claim above has something to be about."
```
"""


def run() -> Finding | None:
    from thalamus.contract.manifest import load_manifest  # noqa: PLC0415
    from thalamus.harness import extraction, ingest as ingest_mod  # noqa: PLC0415

    called: list[str] = []

    def _stub_extraction(*_a, **_k):
        called.append("run_extraction")
        return extraction.ExtractionRun(text=_EXTRACTION_YAML)

    original_extraction = extraction.run_extraction
    prior_config_dir = os.environ.get("THALAMUS_CONFIG_DIR")
    prior_archive_dir = os.environ.get("THALAMUS_ARCHIVE_DIR")

    with tempfile.TemporaryDirectory() as config_root, \
         tempfile.TemporaryDirectory() as archive_dir, \
         tempfile.TemporaryDirectory() as doc_dir:
        experts_dir = Path(config_root) / "experts"
        experts_dir.mkdir(parents=True)
        (experts_dir / f"{_SCOPE}.yaml").write_text(_MANIFEST_YAML)

        doc_path = Path(doc_dir) / "probe.txt"
        doc_path.write_text(_DOCUMENT)

        os.environ["THALAMUS_CONFIG_DIR"] = config_root
        os.environ["THALAMUS_ARCHIVE_DIR"] = archive_dir
        extraction.run_extraction = _stub_extraction
        try:
            manifest = load_manifest(_SCOPE)

            # POSITIVE CONTROL 1: the manifest must actually declare tier 3. Without
            # this, a pass could mean "the field silently defaulted to 2", which would
            # report the bug as absent when it was never exercised.
            if manifest.tier != 3:
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary=(
                        "positive control failed: the temp manifest was not read as "
                        "declaring tier 3, so this case cannot distinguish 'the "
                        "declaration is ignored' from 'the declaration was never made'"
                    ),
                    witness=f"load_manifest({_SCOPE!r}).tier={manifest.tier!r}",
                    site="tests/qe/cases/manifest_tier_ignored.py",
                )

            batch, _run, _digest = ingest_mod.ingest(
                str(doc_path), scope=_SCOPE, feed="qe-probe"
            )
        except Exception as exc:  # noqa: BLE001 - reported below, not raised
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary=(
                    "ingest() raised before a batch could be assembled, so this case "
                    "cannot distinguish an ignored manifest tier from a broken harness"
                ),
                witness=f"{type(exc).__name__}: {exc}",
                site="src/thalamus/harness/ingest.py::ingest",
            )
        finally:
            extraction.run_extraction = original_extraction
            if prior_config_dir is None:
                os.environ.pop("THALAMUS_CONFIG_DIR", None)
            else:
                os.environ["THALAMUS_CONFIG_DIR"] = prior_config_dir
            if prior_archive_dir is None:
                os.environ.pop("THALAMUS_ARCHIVE_DIR", None)
            else:
                os.environ["THALAMUS_ARCHIVE_DIR"] = prior_archive_dir

    # POSITIVE CONTROL 2: the stub must actually have been reached and have produced
    # something for the batch to carry provenance on. Without this, an empty batch
    # would report "no leak" for having nothing to leak from.
    if not called:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "positive control failed: run_extraction was never reached, so no "
                "claim or entity was assembled and this case proves nothing about "
                "provenance tier"
            ),
            witness="run_extraction call count=0",
            site="tests/qe/cases/manifest_tier_ignored.py",
        )
    if not batch.claims or not batch.entities:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "positive control failed: the stub extraction produced no claim or "
                "no entity for build_batch to stamp provenance on"
            ),
            witness=f"claims={len(batch.claims)} entities={len(batch.entities)}",
            site="tests/qe/cases/manifest_tier_ignored.py",
        )

    written_tiers = {c.provenance.tier for c in batch.claims if c.provenance} | {
        e.provenance.tier for e in batch.entities if e.provenance
    }

    if all(t.value == manifest.tier for t in written_tiers):
        return None

    return Finding(
        failure_class=FailureClass.UNENFORCED_SIGNAL,
        summary=(
            "ExpertManifest.tier is parsed and set (declared 3, Tier.WILD) but "
            "build_batch() stamps every claim's and entity's Provenance with a "
            "hardcoded Tier.CURATED regardless of scope, so the manifest's declared "
            "tier never reaches the graph"
        ),
        witness=(
            f"manifest declares tier={manifest.tier} (WILD); "
            f"batch provenance tier(s) written={sorted(t.value for t in written_tiers)} "
            f"(CURATED=2)"
        ),
        site="src/thalamus/harness/ingest.py::build_batch",
    )


CASE = Case(
    name="manifest-tier-not-enforced-by-ingest",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.UNENFORCED_SIGNAL, FailureClass.COLLAPSED_SENTINEL),
    summary=(
        "a manifest declaring tier 3 (WILD) must not have its ingested content "
        "written at Tier.CURATED"
    ),
    run=run,
    issue=283,
    fixed=False,
)
