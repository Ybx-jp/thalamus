"""Every dial the ranker fingerprint names must be the dial actually in force.

`ranker_fingerprint()` (`src/thalamus/substrate/reader.py:150`) exists to make a
retrieval result replayable: a report that straddles `...-d8-w2` and `...-d4-w2` tells
the reader *which* dial moved. That is only true if the value it stamps is the value the
ranking used. A stamped dial that no call site reads is worse than an unstamped one —
it is a confident wrong number, and the offline instrument that trusts it concludes the
dial has no effect.

`_DETAIL_CAP` is captured as a default argument:

    _DETAIL_CAP = 8                                            # reader.py:87
    f"-d{_DETAIL_CAP}"                                         # reader.py:162, the stamp
    def _select_details(details, keywords, cap=_DETAIL_CAP)    # reader.py:1115

Defaults bind at def time. Rebinding `reader._DETAIL_CAP` — which is how every offline
replay, calibration run and A/B tunes it — moves the stamp and not the behavior. The
fingerprint then reports a configuration that never ran.

This is the mechanical form of a defect the corpus records as already having produced a
published wrong result (`detail-cap-bound-as-default-arg`, lab/030): a 2×2 measured the
cap as having zero effect, because patching the constant did nothing while the run
labelled itself with the patched value. Nothing under `tests/` names `_DETAIL_CAP`, so
the fix for that measurement left no guard behind.

Scoped to the fingerprinted dials, deliberately. A blanket "no module constant may be a
default argument" scan matches 53 sites in `src/`, nearly all of them genuine defaults
(host, port, voice, image) whose consumers never rebind them. The property that makes
this a defect is the *pair*: a value that is both stamped as the configuration in force
and captured where rebinding cannot reach it.
"""

from __future__ import annotations

import ast
import inspect

from ..model import Case, FailureClass, Finding, Substrate, Tier

_FINGERPRINT_FN = "ranker_fingerprint"


def _module_constants(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _captured_as_default(tree: ast.Module, dials: set[str]) -> list[str]:
    """Sites where a fingerprinted dial is bound as a default argument.

    Read out of the AST rather than `inspect.signature`, because a signature shows the
    *value* the default froze at and not the name it froze from. At the shipped values
    the frozen 8 and the constant 8 are indistinguishable by value — which is exactly
    why this went unseen — so the name is the only thing that identifies the capture.
    """
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        args = node.args
        # Defaults fill the tail of posonlyargs+args together; slicing `args.args` alone
        # mispairs names and values on any positional-only signature.
        positional = args.posonlyargs + args.args
        slots = list(
            zip(positional[len(positional) - len(args.defaults):], args.defaults, strict=True)
        )
        slots += [
            (a, d) for a, d in zip(args.kwonlyargs, args.kw_defaults, strict=True) if d is not None
        ]
        for arg, default in slots:
            if isinstance(default, ast.Name) and default.id in dials:
                found.append(f"reader.py:{node.lineno} {node.name}({arg.arg}={default.id})")
    return found


def run() -> Finding | None:
    from thalamus.substrate import reader  # noqa: PLC0415

    tree = ast.parse(inspect.getsource(reader))
    constants = _module_constants(tree)

    fingerprint_fn = next(
        (
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == _FINGERPRINT_FN
        ),
        None,
    )
    if fingerprint_fn is None:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=f"{_FINGERPRINT_FN} is absent, so 'every stamped dial is in force' "
                    "and 'nothing is stamped' are the same clean result",
            witness=f"no {_FINGERPRINT_FN} in reader.py",
            site="src/thalamus/substrate/reader.py",
        )

    dials = {
        n.id
        for n in ast.walk(fingerprint_fn)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in constants
    }

    # CONTROL: the fingerprint must name dials at all. An empty set would report perfect
    # agreement between the stamp and the code while checking nothing.
    if not dials:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the fingerprint names no module-level dial, so this case would pass "
                    "against a fingerprint that stamps nothing",
            witness=f"{_FINGERPRINT_FN} reads no module constant",
            site="src/thalamus/substrate/reader.py:150",
        )

    captured = _captured_as_default(tree, dials)
    if not captured:
        return None

    # CONTROL: rebinding a module constant must be observable somewhere, or "patching
    # changed nothing" would mean the probe is broken rather than the dial unreachable.
    # The stamp is the observation — it reads the constant at call time — so a stamp that
    # does not move under a rebind means this case cannot tell capture from a dead patch.
    original = reader._DETAIL_CAP
    probe_cap = original + 3 if original < 5 else 2
    stamp_before = reader.ranker_fingerprint()
    try:
        reader._DETAIL_CAP = probe_cap
        stamp_after = reader.ranker_fingerprint()
        details = [{"description": f"alpha item {i}"} for i in range(original + probe_cap + 5)]
        selected_patched = len(reader._select_details(details, ["alpha"]))
        selected_explicit = len(reader._select_details(details, ["alpha"], cap=probe_cap))
    finally:
        reader._DETAIL_CAP = original

    if stamp_after == stamp_before:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="rebinding a dial did not move the fingerprint either, so this case "
                    "cannot distinguish a captured default from a patch that never landed",
            witness=f"_DETAIL_CAP {original}->{probe_cap} left the stamp at {stamp_after}",
            site="tests/qe/cases/ranker_dials.py",
        )

    # The behavioural half, for the one captured dial with a pure-function consumer.
    # `selected_explicit` is the same computation with the cap passed rather than read,
    # and it is what proves the number is reachable at all — without it, "the patch did
    # nothing" could mean the cap is ignored everywhere, which is a different defect.
    behaviour = (
        f"stamp moved to -d{probe_cap} while _select_details still kept "
        f"{selected_patched} rows (explicit cap={probe_cap} keeps {selected_explicit})"
        if selected_patched != selected_explicit
        else "no behavioural divergence observed for _DETAIL_CAP"
    )

    return Finding(
        failure_class=FailureClass.DOC_CODE_DRIFT,
        summary=(
            "the ranker fingerprint stamps dial values that rebinding cannot change: "
            "the constant is captured as a default argument, so a replay tuned by "
            "patching the module reports a configuration it never ran"
        ),
        witness=f"captured: {'; '.join(captured)} | {behaviour}",
        site="src/thalamus/substrate/reader.py:1115 vs :162",
    )


CASE = Case(
    name="ranker-fingerprint-names-dials-in-force",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.DOC_CODE_DRIFT, FailureClass.COLLAPSED_SENTINEL),
    summary="a dial stamped into the ranker fingerprint must be the one the ranking used",
    run=run,
)
