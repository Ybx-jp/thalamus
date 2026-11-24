"""A console surface with built parts arms the cases written for it from the board.

The probes and the reasoning are in `_console_spec.py`; this is the guard it describes.
**Shown capable of going red**: create `static/board.html` without routing it in
`STATIC`, and the board-page surface reports its hint (a static file named for the
board) without its probe — the exact state of a surface that landed under a name
nothing arms on.
"""

from __future__ import annotations

from qe.model import Case, FailureClass, Finding, Substrate, Tier

from ._console_spec import SURFACES


def run() -> Finding | None:
    # Positive control: every Substrate member of the unbuilt family has a surface
    # here, or a case could declare a member whose probe raises KeyError at skip time.
    members = {s.value.split(":", 1)[1] for s in Substrate
               if s.value.startswith("console-unbuilt:")}
    if members != set(SURFACES):
        return Finding(
            FailureClass.DOC_CODE_DRIFT,
            "the console-unbuilt substrate family and the surface table disagree",
            witness=f"substrates={sorted(members)} surfaces={sorted(SURFACES)}",
            site="tests/qe/model.py :: Substrate",
        )
    stuck = []
    for surface in SURFACES.values():
        hint = surface.hint()
        if hint and not surface.served():
            stuck.append(f"{surface.key}: {hint}, but the arming probe does not see it "
                         f"served ({surface.board})")
    if stuck:
        return Finding(
            FailureClass.COLLAPSED_SENTINEL,
            "a console surface looks built while the cases written for it still skip",
            witness="; ".join(stuck),
            site="tests/qe/cases/_console_spec.py :: Surface.served",
        )
    return None


CASE = Case(
    name="console-spec-cases-arm-when-their-surface-lands",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.DOC_CODE_DRIFT, FailureClass.COLLAPSED_SENTINEL),
    summary="a console surface with built parts arms the cases written for it from the "
            "design board, rather than leaving them skipped",
    run=run,
)
