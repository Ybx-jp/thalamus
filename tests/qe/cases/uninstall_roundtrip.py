"""`--uninstall` must take back the wiring `init` put in, on a machine it did install.

The removal path (`9bcd7c7`) is the newest release-facing code in the tree and the answer
to the sharpest question a first-time cloner asks: *can I get this back out?* It runs
against a machine it did not necessarily install, so every step proves a thing is ours
before deleting it — hook entries through the same `_strip_*` helpers the install uses, a
skill link only when it is a symlink resolving into the package's own skill dir, the MCP
server through `claude mcp remove`.

That proof obligation is what makes the round trip worth checking separately from the
parts. `tests/test_install.py::TestUninstall` covers the discrimination — an operator's
own hook survives, a hand-written skill survives, an impostor symlink survives — and it
covers them by *hand-writing the state* `uninstall()` is then asked to remove. Sound for
what it asserts, and blind by construction to the property here: anything `install()`
writes that `uninstall()` does not know about is never in the input, so it can never be
in the residue. That suite's fixture also stubs `write_all_agents` to a bare `mkdir`, so
the seven derived agent files a real install writes have never existed in a test at the
moment removal runs.

So this case installs for real, then uninstalls, and asks what is left.

**Residue is wiring, not files.** `uninstall()` deliberately leaves an emptied
`settings.json`, an empty `~/.claude/skills/`, and the directories themselves: it removes
what is ours from files that belong to the operator, and a command that deleted the
containing file would take a hand-written hook with it. Nothing carrying our name may
survive — a hook entry, an MCP server key, a derived agent, a symlink into the package —
and an empty JSON object may.

**The detector's sensitivity is demonstrated in the same run.** The marker scan is run
over the post-install tree first and must find the wiring there. Without that, a scan
looking for the wrong marker — a renamed hook script, a changed server key — reports the
same clean tree as a perfect uninstall, and this case would certify a removal that removed
nothing. That control is the whole reason the probe returns three snapshots instead of
one.

**Shown capable of going red.** Green here is a claim about `uninstall()`, so the
detector was driven against poisoned snapshots — the probe returns plain dataclasses, so
a mutant is `dataclasses.replace(probe, end=...)` and needs no edit to `src/`. Rebind the
*case module's* `observe` (`uninstall_roundtrip.observe = lambda **_: mutant`), not
`_install_sandbox.observe`: the case binds the name at import, and patching the source
module leaves it running the real probe — which is how a first attempt at this validation
reported all four mutants caught when it had caught none.

| mutant | verdict |
|---|---|
| `end = after` — uninstall does nothing | `invariant-falsified`, 17 of 17 sites |
| one Cursor MCP registration left behind | `invariant-falsified`, names `.cursor/mcp.json` |
| one skill symlink left behind | `invariant-falsified`, names the link and its target |
| `_MARKER` renamed — content half blinded | `collapsed-sentinel` (the control), `kinds found: ['symlink']` |

**Not shipping-wide.** The graph, `~/.thalamus/` and the transcript archive are out of
scope on purpose and are not residue: uninstalling wiring is not a request to delete an
operator's memory. They are also outside the footprint this case examines, which is only
what `install()` itself created.
"""

from __future__ import annotations

from ..model import Case, FailureClass, Finding, Substrate, Tier
from ._install_sandbox import observe

# Written by the interpreter, uv, or the OS. The venv path contains the string `thalamus`
# on this checkout, so a marker scan over the whole home reports the box rather than the
# installer; the footprint filter is what keeps the subject to what `install()` created.
_NOT_OURS = (".cache/", ".local/share/uv/", ".venv/", ".config/uv/")

_MARKER = "thalamus"


def _wiring(tree: dict[str, str], rel: str,
            package_skills: tuple[str, ...]) -> tuple[str, str] | None:
    """What in this path is ours, or None.

    Returns `(kind, evidence)`. The kind is carried because the detector has two
    independent halves — a symlink test against the package's own skill dir, and a
    content marker — and a control that only counts total hits is satisfied by either
    half alone. Blinding one half is a real way for this case to go quietly useless, so
    the control below demands both.
    """
    value = tree.get(rel)
    if value is None:
        return None                          # removed outright — the strongest outcome
    if value == "\x00dir":
        return None                          # an empty directory is not wiring
    if value.startswith("symlink:"):
        target = value[len("symlink:"):]
        if any(target == s or target.startswith(s + "/") for s in package_skills):
            return "symlink", f"symlink -> {target}"
        return None
    if _MARKER in value.lower():
        line = next((ln.strip() for ln in value.splitlines() if _MARKER in ln.lower()), "")
        return "content", f"content: {line[:120]}"
    return None


def run() -> Finding | None:
    probe = observe()
    if isinstance(probe, str):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the install probe did not run, so 'nothing survived uninstall' and "
                    "'nothing was ever installed' are the same result",
            witness=probe,
            site="tests/qe/cases/_install_sandbox.py",
        )

    footprint = [rel for rel in probe.created
                 if not any(rel == p.rstrip("/") or rel.startswith(p) for p in _NOT_OURS)]

    # CONTROL: the installer must have written something.
    if not footprint:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the installer created no paths under the redirected HOME, so a "
                    "removal that removes nothing would pass this case",
            witness=f"install actions: {' | '.join(probe.install_actions)[:400]}",
            site="src/thalamus/harness/install.py:install",
        )

    # CONTROL, and it runs: the marker scan must find our wiring in the *installed* tree.
    # A scan that cannot see the wiring when it is certainly there reports every uninstall
    # clean, including one that did nothing at all.
    installed = {rel: found for rel in footprint
                 if (found := _wiring(probe.after, rel, probe.package_skills))}
    kinds = {kind for kind, _ in installed.values()}
    if kinds != {"symlink", "content"}:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the wiring detector did not find both a package symlink and a "
                    "content marker in a freshly installed tree, so one half of it is "
                    "blind and a clean uninstall is indistinguishable from a blind scan",
            witness=f"{len(installed)} of {len(footprint)} created paths read as wiring "
                    f"after install; kinds found: {sorted(kinds) or 'none'}",
            site="tests/qe/cases/uninstall_roundtrip.py:_wiring",
        )

    residue = {rel: found for rel in footprint
               if (found := _wiring(probe.end, rel, probe.package_skills))}
    if not residue:
        return None

    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            "`thalamus init --uninstall` leaves its own wiring behind: the operator is "
            "told the removal is the mirror of the install, and hook entries, MCP "
            "registrations or skill links from this install survive it"
        ),
        witness=(
            f"{len(residue)} of {len(installed)} installed site(s) survived: "
            + "; ".join(f"{rel} [{what}]" for rel, (_kind, what) in sorted(residue.items())[:6])
            + (f" (+{len(residue) - 6} more)" if len(residue) > 6 else "")
            + f" | uninstall said: {' | '.join(probe.uninstall_actions)[:300]}"
        ),
        site="src/thalamus/harness/install.py:uninstall",
    )


CASE = Case(
    name="uninstall-takes-back-what-install-wrote",
    tier=Tier.FAST,
    # Not hermetic, for the same reason as `install_consent`'s CASE: it shares
    # `_install_sandbox.observe()`, whose real `install()` reaches the graph through
    # `verify()` -> `verify_runtime()` -> `_probe_graph()`, and the span tap's
    # `~/.thalamus/profiles/*.jsonl` is part of the footprint this case scans for
    # residue (#98). SKIP visibly on a box with no graph rather than certify a
    # narrower removal than the one a graph-backed box gets.
    substrate=(Substrate.NEEDS_GRAPH,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="no Thalamus wiring written by a real `init` survives `init --uninstall`",
    run=run,
)
