"""The `thalamus-arch` command, and `thalamus arch` when thalamus is installed.

Both spell the same subcommands from one parser builder, `add_commands`, and run
through one handler, `run`: `thalamus-arch` is this module's `main`, and `thalamus
arch` is the parser `plugin.py` hands core. The handlers import the measuring modules
only when a subcommand runs, because `thalamus` builds every plugin's parser on every
invocation.
"""

from __future__ import annotations

import argparse
import dataclasses
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

import yaml

from thalamus_arch import __version__

ARCH_REPO_HELP = (
    "Repo to measure. Defaults to the git repository holding the current directory, "
    "measured from its top — `arch/model.yaml` belongs to a repository."
)


def add_commands(parser: argparse.ArgumentParser) -> None:
    """Add the subcommands to `parser`: the `thalamus-arch` parser itself, or the
    `thalamus arch` parser this package registers when thalamus is installed."""
    arch_sub = parser.add_subparsers(dest="arch_command")

    arch_scan_parser = arch_sub.add_parser(
        "scan",
        help="Measure the import graph and regenerate arch/model.yaml "
        "(dry-run unless --write)",
    )
    arch_scan_parser.add_argument("--repo", default=None, help=ARCH_REPO_HELP)
    arch_scan_parser.add_argument(
        "--import-depth", choices=["all", "module-level"], default="",
        help="Override the model file's declared policy. Changes the policy digest, so "
        "the scan lands in a different lineage — which is the point.",
    )
    arch_scan_parser.add_argument(
        "--write", action="store_true",
        help="Write the model file. Without it, the scan runs and is reported but "
        "nothing is persisted.",
    )
    arch_scan_parser.add_argument(
        "--check", action="store_true",
        help="Exit 1 if the committed model file does not match a fresh scan. The "
        "staleness gate: measures, compares, writes nothing.",
    )

    arch_show_parser = arch_sub.add_parser(
        "show", help="Print the current model: declared policy, layers, rules, last scan"
    )
    arch_show_parser.add_argument("--repo", default=None, help=ARCH_REPO_HELP)

    arch_diff_parser = arch_sub.add_parser(
        "diff",
        help="Compare the working tree's structure against another commit — recompute "
        "both sides rather than trusting a stored number",
    )
    arch_diff_parser.add_argument("against", help="Commit-ish to compare against")
    arch_diff_parser.add_argument("--repo", default=None, help=ARCH_REPO_HELP)

    arch_rules_parser = arch_sub.add_parser(
        "rules", help="Check the measured edge list against the declared design rules"
    )
    arch_rules_parser.add_argument("--repo", default=None, help=ARCH_REPO_HELP)
    arch_rules_parser.add_argument(
        "--gate", action="store_true",
        help="Exit nonzero on a finding the model does not accept. 1 = a violation or "
        "unplaced module not declared in `accepted`; 2 = an `accepted` entry that no "
        "longer happens and should be deleted.",
    )

    arch_dead_parser = arch_sub.add_parser(
        "dead",
        help="Definitions under the source roots that nothing outside the test roots "
        "refers to, and modules nothing imports",
    )
    arch_dead_parser.add_argument("--repo", default=None, help=ARCH_REPO_HELP)
    arch_dead_parser.add_argument(
        "--gate", action="store_true",
        help="Exit nonzero on a finding the model does not exempt. 1 = a reported "
        "definition or orphan module; 2 = an exemption that no longer matches anything.",
    )
    arch_dead_parser.add_argument(
        "--limits", action="store_true",
        help="Print what the census could not see — runtime name lookup, names reached "
        "through a string, star re-exports, unparsed files.",
    )

    arch_refs_parser = arch_sub.add_parser(
        "refs",
        help="Names a comment points at that the tree no longer holds (report only)",
    )
    arch_refs_parser.add_argument("--repo", default=None, help=ARCH_REPO_HELP)
    arch_refs_parser.add_argument(
        "--limits", action="store_true",
        help="Print what the recognizer did not consume — candidate tokens no form "
        "matched, files it could not read, and the references a sentence asserts the "
        "absence of.",
    )


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Measure a repository's structure; write its model file only when told to."""
    command = getattr(args, "arch_command", None)
    if command not in {"scan", "show", "diff", "rules", "dead", "refs"}:
        parser.print_help()
        sys.exit(1)

    from thalamus_arch import findings as arch_findings
    from thalamus_arch import model as arch_model
    from thalamus_arch import routes as arch_routes
    from thalamus_arch.extractor import scan_repo
    from thalamus_arch.metrics import measure

    def _scan(target):
        """One scan under both declared channels.

        Every subcommand goes through this, `diff` included: measuring one side with the
        route channel on and the other with it off would compare two extractors, which
        is the error the policy digest exists to make impossible.
        """
        extracted = arch_routes.extract_routes(target, model.routes)
        return arch_routes.merge(scan_repo(target, policy), extracted), extracted

    repo =Path(args.repo).resolve() if args.repo else arch_model.repo_root()
    model = arch_model.load(repo / arch_model.MODEL_PATH)
    policy = model.policy
    if getattr(args, "import_depth", ""):
        policy = dataclasses.replace(policy, import_depth=args.import_depth)

    if command == "show":
        _arch_show(repo, model)
        return

    graph, route_graph = _scan(repo)
    metrics = measure(graph)

    if command == "rules":
        _arch_rules(model, graph, gate=getattr(args, "gate", False))
        return

    if command == "dead":
        _arch_dead(args, repo, graph)
        return

    if command == "refs":
        _arch_refs(args, repo)
        return

    if command == "diff":
        with tempfile.TemporaryDirectory(prefix="thalamus-arch-") as tmp:
            checkout = Path(tmp) / "tree"
            result = subprocess.run(
                ["git", "-C", str(repo), "worktree", "add", "--detach", str(checkout), args.against],
                capture_output=True, text=True, check=False,
            )
            if result.returncode != 0:
                print(f"Cannot check out {args.against}: {result.stderr.strip()}", file=sys.stderr)
                sys.exit(1)
            try:
                # Both sides are recomputed under one policy. Reading the stored number
                # off the other commit's model file would compare a measurement against
                # a report, which is the mistake `diff` exists to prevent.
                other = measure(_scan(checkout)[0])
            finally:
                subprocess.run(
                    ["git", "-C", str(repo), "worktree", "remove", "--force", str(checkout)],
                    capture_output=True, text=True, check=False,
                )
        _arch_diff(args.against, other, metrics)
        return

    # scan
    text, derived, metrics = arch_model.build(repo, graph, model)
    dirty = arch_model.dirty_paths(repo, policy)
    found = arch_findings.findings(graph, metrics, model) + arch_findings.route_findings(
        route_graph
    )

    print(f"Scan {derived['scan']}")
    print(f"  policy      import_depth={policy.import_depth} resolve={policy.resolve} "
          f"digest={policy.digest()[:7]}")
    if model.routes.enabled:
        print(f"  routes      {len(route_graph.called())} called, "
              f"{len(route_graph.defined())} defined, match={model.routes.match} "
              f"digest={model.routes.digest()[:7]}")
    print(f"  modules     {metrics.modules}")
    print(f"  edges       {metrics.dependencies} counted of {len(graph.edges)} recorded")
    print(f"  propagation {metrics.propagation_cost * 100:.2f}%")
    print(f"  cycles      {len(metrics.cycles)} ({metrics.modules_in_cycles} modules)")
    for cycle in metrics.cycles:
        print(f"                {' <-> '.join(cycle)}")
    print(f"  findings    {len(found)}")
    for finding in found:
        print(f"                {finding.description}")

    if dirty:
        # The walk read the working tree; the scan id names HEAD. With a dirty tree
        # those are different codebases, and the model file would record a measurement
        # of a commit that never contained it — the one falsehood git cannot correct
        # later, because the file will be committed alongside the code it misdescribes.
        print(f"\n{len(dirty)} uncommitted file(s) under the scanned roots:")
        for path in dirty[:10]:
            print(f"  {path}")
        if len(dirty) > 10:
            print(f"  … and {len(dirty) - 10} more")

    if getattr(args, "check", False):
        # The staleness gate. The committed model is a measurement of a tree; once the
        # code moves past it, `arch show` reports numbers for a tree that no longer
        # exists and nothing says so.
        #
        # It compares the *measurement* and not the whole file, because `scan` and
        # `commit` name the tree that was measured and necessarily lag by one: writing
        # the model and committing it moves HEAD, so a fresh scan's stamp can never
        # equal the stamp inside the file that commit created. Comparing the text would
        # make this gate impossible to satisfy rather than merely hard.
        model_path = repo / arch_model.MODEL_PATH
        committed = arch_model.load(model_path).derived if model_path.exists() else {}
        measured = {k: v for k, v in derived.items() if k not in ("scan", "commit")}
        stored = {k: v for k, v in committed.items() if k not in ("scan", "commit")}
        if stored == measured:
            print("\nModel file matches a fresh scan.")
            return
        drifted = sorted(
            key for key in set(stored) | set(measured) if stored.get(key) != measured.get(key)
        )
        print(
            f"\nStale: `arch/model.yaml` no longer matches a fresh scan — "
            f"{', '.join(drifted) or 'no measured key'} differ(s). Run "
            f"`{parser.prog} scan --write` and commit the result.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.write:
        print("\nDry run. Re-run with --write to regenerate the model file.")
        return

    if dirty:
        print(
            "\nRefusing to write: the scan id names a commit the working tree does not "
            "match. Commit or stash the files above, then re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    model_path = repo / arch_model.MODEL_PATH
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(text, encoding="utf-8")
    print(f"\nWrote {model_path.relative_to(repo)}")
    print("Commit it — the file is the record, and git is what dates it to this tree.")


def _arch_show(repo, model) -> None:
    """Print the authored half and what the last scan measured."""
    print(f"repo         {model.repo or '(unset)'}")
    print(f"root_commit  {model.root_commit or '(unset)'}")
    print(f"policy       import_depth={model.policy.import_depth} "
          f"resolve={model.policy.resolve} roots={list(model.policy.roots)} "
          f"digest={model.policy.digest()[:7]}")
    print(f"layers       {len(model.layers)}")
    for layer in model.layers:
        print(f"               {layer.name}: {', '.join(layer.includes) or '(nothing)'}")
    print(f"rules        {len(model.rules)}")
    for rule in model.rules:
        print(f"               {rule.layer} -> {', '.join(rule.may_depend_on) or '(nothing)'}")
    print(f"seams        {len(model.seams)}")
    print(f"rejected     {len(model.rejected_refactors)} recorded refactor(s)")
    if model.derived:
        metrics = model.derived.get("metrics", {})
        print(f"last scan    {model.derived.get('scan', '(none)')}")
        print(f"               {metrics.get('modules', '?')} modules, "
              f"{metrics.get('dependencies', '?')} dependencies, "
              f"propagation {metrics.get('propagation_cost', '?')}%")
    else:
        print("last scan    (never scanned)")


def _arch_rules(model, graph, gate: bool = False) -> None:
    """Check the measured edges against the declared rules.

    The report is the same either way: every violation prints, accepted or not, because
    an architect reading this wants the design's real shape and not the subset that is
    still news. `--gate` adds a verdict on top of that report rather than filtering it.
    """
    if not model.layers:
        print(
            f"No layers declared, so the partition places none of {len(graph.modules)} "
            "scanned modules. Declaring them is the architect's work — an empty "
            "partition reports nothing rather than passing."
        )
        if gate:
            sys.exit(1)
        return
    unplaced = model.unplaced(graph)
    violations = model.violations(graph)
    result = model.gate(graph)
    accepted_keys = {entry.key for entry in result.accepted_hits}

    def mark(key) -> str:
        return "accepted " if key in accepted_keys else "NEW      "

    print(f"{len(graph.modules)} modules, {len(unplaced)} unplaced by the declared partition")
    for module in unplaced[:20]:
        print(f"  {mark((module, ''))} unplaced  {module}")
    print(f"{len(violations)} rule violation(s), {len(result.accepted_hits)} accepted")
    for violation in violations:
        print(f"  {mark((violation.from_path, violation.to_path))} {violation.describe()}")
    for entry in result.stale:
        print(f"  STALE     accepted and no longer measured: {entry.describe()}")
    if not unplaced and not violations:
        print("The declared model and the measured graph agree.")

    if not gate:
        return
    code = result.exit_code
    if code == 1:
        print(
            f"\nGate: {len(result.new_violations)} violation(s) and "
            f"{len(result.new_unplaced)} unplaced module(s) the model does not accept. "
            "Fix the edge, or declare it in `accepted` with the reason it stands.",
            file=sys.stderr,
        )
    elif code == 2:
        print(
            f"\nGate: {len(result.stale)} `accepted` entry/entries no longer happen. "
            "Delete them — an exception that has stopped firing describes a design that "
            "moved.",
            file=sys.stderr,
        )
    sys.exit(code)


def _dead_policy(repo):
    """The declared census policy, read straight off the model file.

    Read here rather than hung off `ArchModel` because `deadends` imports `findings`,
    which imports `model` — putting the policy on the model would close that into a
    cycle. `regenerate` preserves the authored half byte for byte, so a hand-declared
    block survives every scan.
    """
    from thalamus_arch import model as arch_model
    from thalamus_arch.deadends import DeadEndPolicy

    path = repo / arch_model.MODEL_PATH
    document = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    return DeadEndPolicy.from_block((document or {}).get("deadends") or {})


def _refs_policy(repo):
    """The declared reference policy, read straight off the model file.

    Read here rather than hung off `ArchModel` for the reason `_dead_policy` is:
    `references` imports `findings`, which imports `model`, so putting the policy on
    the model would close that into a cycle.
    """
    from thalamus_arch import model as arch_model
    from thalamus_arch.references import ReferencePolicy

    path = repo / arch_model.MODEL_PATH
    document = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    return ReferencePolicy.from_block((document or {}).get("references") or {})


def _arch_refs(args, repo) -> None:
    """Report references in comment prose that the tree no longer resolves.

    No `--gate`, deliberately, and the absence is the design rather than an oversight:
    this channel's precision has not been measured, and an unmeasured checker that
    acts leaves no record of the calls it got wrong.
    """
    from thalamus_arch import references as arch_references

    policy = _refs_policy(repo)
    if not policy.enabled:
        print(
            "The reference channel is off. Enable it in `arch/model.yaml` under "
            "`references: enabled: true` — a census nobody declared is a census "
            "nobody can read the exceptions of."
        )
        return

    print(arch_references.render(arch_references.census(repo, policy), limits=args.limits))


def _arch_dead(args, repo, graph) -> None:
    """Report definitions nothing outside the test roots refers to.

    The report states what was measured and never that a symbol is unused: the census
    resolves identifiers, and `--limits` lists every mechanism that could hide a caller
    from it. `--gate` adds a verdict without narrowing that report.
    """
    from thalamus_arch import deadends as arch_deadends

    policy = _dead_policy(repo)
    if not policy.enabled:
        print(
            "The dead-end channel is off. Enable it in `arch/model.yaml` under "
            "`deadends: enabled: true` — a census nobody declared is a census nobody "
            "can read the exceptions of."
        )
        return

    report = arch_deadends.scan(repo, graph, policy)
    matched = {
        (e.definition.path, e.definition.qualname)
        for e in report.exempted
        if e.rule == arch_deadends.RULE_DECLARED
    }

    # Reported through `deadend_findings` rather than off the report's lists directly:
    # the finding is where the hedging lives. "No reference outside the test roots was
    # found" is refutable by pointing at one; "unused" is a verdict a static census is
    # not entitled to, given what `limits` says it cannot see.
    for finding in arch_deadends.deadend_findings(report):
        print(f"  {finding.description}")
    print(
        f"{len(report.test_only)} test-only, {len(report.orphans)} orphan module(s), "
        f"{len(report.exempted)} exempted, {len(report.silenced)} reached only from a "
        f"non-Python caller"
    )
    for entry in report.silenced:
        print(f"  reached    {entry.describe()}")

    stale = [entry for entry in policy.exemptions if (entry.path, entry.symbol) not in matched]
    for entry in stale:
        print(f"  STALE      exemption matches nothing: {entry.path} {entry.symbol}")

    if args.limits or not (report.test_only or report.orphans):
        print(f"{len(report.limits)} stated limit(s) on the census's reach")
        for limit in report.limits:
            print(f"  limit      {limit}")

    if not report.test_only and not report.orphans and not stale:
        print("Every definition under the source roots is referenced outside the tests.")

    if not args.gate:
        return
    if report.test_only or report.orphans:
        print(
            f"\nGate: {len(report.test_only) + len(report.orphans)} finding(s) the model "
            "does not exempt. Wire the definition to a caller, delete it, or add an "
            "`exemptions` entry under `deadends` with the reason it stands.",
            file=sys.stderr,
        )
        sys.exit(1)
    if stale:
        print(
            f"\nGate: {len(stale)} exemption(s) match nothing. Delete them — an "
            "exemption for a symbol that is now referenced, or gone, describes a tree "
            "that moved.",
            file=sys.stderr,
        )
        sys.exit(2)


def _arch_diff(against: str, other, current) -> None:
    """Report both sides recomputed, never a stored number against a fresh one."""
    print(f"{'':13} {against[:12]:>12}  {'working tree':>12}")
    print(f"{'modules':13} {other.modules:>12}  {current.modules:>12}")
    print(f"{'dependencies':13} {other.dependencies:>12}  {current.dependencies:>12}")
    print(f"{'propagation':13} {other.propagation_cost * 100:>11.2f}%  "
          f"{current.propagation_cost * 100:>11.2f}%")
    print(f"{'cycles':13} {len(other.cycles):>12}  {len(current.cycles):>12}")

    gone = set(other.cycles) - set(current.cycles)
    fresh = set(current.cycles) - set(other.cycles)
    for cycle in sorted(fresh):
        print(f"  new cycle      {' <-> '.join(cycle)}")
    for cycle in sorted(gone):
        print(f"  cycle resolved {' <-> '.join(cycle)}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="thalamus-arch",
        description="Measure a Python repository's import graph against the layers "
        "and rules declared in its arch/model.yaml.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    add_commands(parser)
    run(parser.parse_args(argv), parser)
