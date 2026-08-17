"""Walk a repo's Python imports into a dependency graph, under a policy it declares.

The extractor's own settings changed the headline number by 31% (7.65% counting every
import against 5.82% counting only module-level ones, both over `src/thalamus/` at
`041797a`), and the difference was not a bug in either run — it was an undeclared
boolean. Two consequences shape this module:

**The policy is data, not a function signature.** `ExtractorPolicy` serialises into the
model file and digests to a short hash that rides in every scan id, so a number always
travels with the rules that produced it. Comparing two scans made under different
policies is the error this exists to make visible.

**A deferred import is recorded, not dropped.** A real cycle was found this way in the
research-battery package (since split into the companion `thalamus-eval` repo): one
module imported another at module level while the reverse import was deferred inside
two functions — module-level-only counting reports that as zero cycles. Both readings
come off the same edge list because every edge carries `depth`; the policy filters at
read time rather than at walk time.

The resolver is deliberately closed over the scanned set: an import of `gremlin_python`
leaves no edge, because propagation cost is a statement about how this repo's own
modules reach each other. External coupling is a different metric and is not this one.
"""

from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

# Import-statement form. Recorded because `from x import y` and `import x.y` resolve
# differently — the first may name a module *or* a name inside one — and a resolver bug
# that confuses them is invisible without the distinction on the edge.
KIND_IMPORT = "import"
KIND_FROM = "from"
# `from pkg import mod` also executes `pkg/__init__.py`, so the dependency on the
# package is real — but it is not the *deepest matching module*, which is what the
# declared resolve policy asks for. Recording it under its own kind keeps both readings
# available from one walk: the declared policy filters it out, and a later policy that
# wants import-time coupling can count it without a re-scan. It is also the exact edge
# whose undeclared handling separates two defensible dependency counts on this repo.
KIND_PACKAGE = "package"

# Where in the file the import sits. `module` is executed at import time and is what a
# layering rule governs; `deferred` runs inside a function or class body, which is how a
# cycle hides from a module-level reading (and how one is conventionally broken).
DEPTH_MODULE = "module"
DEPTH_DEFERRED = "deferred"

IMPORT_DEPTH_ALL = "all"
IMPORT_DEPTH_MODULE_LEVEL = "module-level"

# One alias resolves to one target: the deepest module that exists in the scanned set.
RESOLVE_DEEPEST = "deepest-matching-module"
# The same, plus the package edge that `from pkg import mod` also incurs at import time.
RESOLVE_MODULE_AND_PACKAGE = "module-and-package"


@dataclass(frozen=True)
class ExtractorPolicy:
    """The declared rules a scan was produced under. Digested into the scan id.

    `roots` is not in the design's written fragment and is added deliberately: without
    it the policy does not determine the measurement, and determining the measurement is
    the entire reason the block is digested. `exclude` carries vendored trees for the
    same reason — a policy that silently depends on which directories happened to exist
    is not a policy.
    """

    version: int = 1
    languages: tuple[str, ...] = ("python",)
    roots: tuple[str, ...] = ("src",)
    import_depth: str = IMPORT_DEPTH_ALL
    resolve: str = "deepest-matching-module"
    exclude: tuple[str, ...] = (
        "tests/**",
        "lab/**",
        "**/__pycache__/**",
        "**/node_modules/**",
        ".venv/**",
    )

    def block(self) -> dict[str, object]:
        """The policy as it appears in `arch/model.yaml`, without its own digest."""
        return {
            "version": self.version,
            "languages": list(self.languages),
            "roots": list(self.roots),
            "import_depth": self.import_depth,
            "resolve": self.resolve,
            "exclude": list(self.exclude),
        }

    def digest(self) -> str:
        """sha256 over the canonically serialised policy block.

        Canonical means JSON with sorted keys and no insignificant whitespace, over the
        block *excluding* `digest` — a hash cannot cover itself. YAML is not the hashing
        form because YAML has many spellings of one mapping and the digest must not move
        when the file is reformatted.

        The block is scoped to the import extractor on purpose. When the co-change
        channel lands it gets its own block and its own digest, so adding it will not
        fork the scan key of every import measurement taken before it.
        """
        canonical = json.dumps(self.block(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def counts_edge(self, edge: DependencyEdge) -> bool:
        """Does this edge count under the declared policy?

        Two independent filters, both declared: `import_depth` decides whether deferred
        imports count, and `resolve` decides whether the package half of
        `from pkg import mod` counts alongside the submodule it resolved to.
        """
        if edge.kind == KIND_PACKAGE and self.resolve != RESOLVE_MODULE_AND_PACKAGE:
            return False
        if self.import_depth == IMPORT_DEPTH_ALL:
            return True
        return edge.depth == DEPTH_MODULE

    @classmethod
    def from_block(cls, block: dict) -> ExtractorPolicy:
        """Rebuild a policy from a model file's `extractor:` mapping."""
        defaults = cls()
        return cls(
            version=int(block.get("version", defaults.version)),
            languages=tuple(block.get("languages", defaults.languages)),
            roots=tuple(block.get("roots", defaults.roots)),
            import_depth=str(block.get("import_depth", defaults.import_depth)),
            resolve=str(block.get("resolve", defaults.resolve)),
            exclude=tuple(block.get("exclude", defaults.exclude)),
        )


@dataclass(frozen=True)
class DependencyEdge:
    """One module's dependency on another, as the design specified it."""

    from_path: str
    to_path: str
    kind: str
    depth: str

    def as_row(self) -> str:
        """The model file's line form — diffable, one edge per line."""
        return f"{self.from_path} -> {self.to_path} [{self.kind},{self.depth}]"


@dataclass
class DependencyGraph:
    """The scanned modules, their internal edges, and the policy behind both."""

    modules: list[str] = field(default_factory=list)
    edges: list[DependencyEdge] = field(default_factory=list)
    policy: ExtractorPolicy = field(default_factory=ExtractorPolicy)
    unresolved: list[str] = field(default_factory=list)

    def counted_edges(self) -> list[DependencyEdge]:
        """Edges that survive the declared import depth, deduplicated.

        One module importing another twice — a module-level import and a deferred one,
        or two names off the same module — is one dependency, not two. The design's
        197-line edge list is the deduplicated form.
        """
        seen: set[tuple[str, str]] = set()
        kept: list[DependencyEdge] = []
        for edge in self.edges:
            if not self.policy.counts_edge(edge):
                continue
            key = (edge.from_path, edge.to_path)
            if key in seen:
                continue
            seen.add(key)
            kept.append(edge)
        return kept

    def adjacency(self) -> dict[str, set[str]]:
        """module -> the modules it depends on, under the declared policy."""
        out: dict[str, set[str]] = {module: set() for module in self.modules}
        for edge in self.counted_edges():
            out.setdefault(edge.from_path, set()).add(edge.to_path)
        return out


def _excluded(relative: str, policy: ExtractorPolicy) -> bool:
    return any(fnmatch.fnmatch(relative, pattern) for pattern in policy.exclude)


def _module_name(relative: PurePosixPath) -> str:
    """Dotted module name for a repo-relative path, with the source root stripped.

    The root is stripped by walking off the leading directories that are not packages:
    `src/thalamus/eval/attribution.py` is `thalamus.eval.attribution` because `src/`
    holds no `__init__.py` while `thalamus/` does. Done textually against the scanned
    set rather than by touching the filesystem again, so the mapping cannot disagree
    with it.
    """
    parts = list(relative.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][: -len(".py")]
    return ".".join(parts)


def _collect_modules(repo: Path, policy: ExtractorPolicy) -> dict[str, str]:
    """Scanned files as dotted module name -> repo-relative path.

    Package roots are detected per root directory: the first path segment under a
    declared root that carries an `__init__.py` starts the importable name.
    """
    modules: dict[str, str] = {}
    for root in policy.roots:
        root_dir = repo / root
        if not root_dir.is_dir():
            continue
        for path in sorted(root_dir.rglob("*.py")):
            relative = PurePosixPath(path.relative_to(repo).as_posix())
            if _excluded(str(relative), policy):
                continue
            # Strip the declared root prefix; what remains is the importable name.
            importable = PurePosixPath(*relative.parts[len(PurePosixPath(root).parts) :])
            modules[_module_name(importable)] = str(relative)
    return modules


def _resolve(target: str, modules: dict[str, str]) -> str:
    """Deepest matching module for a dotted target, or "" when it is external.

    `from thalamus.eval import attribution` offers `thalamus.eval.attribution` and
    `thalamus.eval`; the deepest that exists in the scanned set wins, which is what
    makes an import of a submodule land on that submodule rather than on its
    package's `__init__`.
    """
    parts = target.split(".")
    for depth in range(len(parts), 0, -1):
        candidate = ".".join(parts[:depth])
        if candidate in modules:
            return modules[candidate]
    return ""


def _absolute_target(node: ast.ImportFrom, current: str) -> str:
    """Resolve a relative `from . import x` against the importing module's package."""
    if not node.level:
        return node.module or ""
    package = current.split(".")
    # `__init__` modules are their own package; a plain module's package is its parent.
    base = package if current.endswith(".__init__") else package[:-1]
    climbed = base[: len(base) - (node.level - 1)] if node.level > 1 else base
    return ".".join([*climbed, node.module]) if node.module else ".".join(climbed)


def _walk_imports(tree: ast.Module) -> list[tuple[ast.stmt, str]]:
    """Every import statement paired with the depth it sits at.

    Module level is the top of the file only. An import nested in an `if` at module
    level still executes at import time, so it counts as module-level; one inside a
    function or class body does not, and that is the distinction `depth` records.
    """
    found: list[tuple[ast.stmt, str]] = []

    def visit(node: ast.AST, depth: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                found.append((child, depth))
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                visit(child, DEPTH_DEFERRED)
            else:
                visit(child, depth)

    visit(tree, DEPTH_MODULE)
    return found


def scan_repo(repo: Path, policy: ExtractorPolicy | None = None) -> DependencyGraph:
    """Extract the internal import graph of `repo` under `policy`.

    Every edge is recorded with its depth regardless of the declared `import_depth`;
    the policy filters when the graph is read. That way one walk answers both readings
    and `arch diff` can show that a cycle exists but only through deferred imports.
    """
    policy = policy or ExtractorPolicy()
    modules = _collect_modules(repo, policy)
    by_path = {path: name for name, path in modules.items()}

    graph = DependencyGraph(modules=sorted(modules.values()), policy=policy)
    for name, relative in sorted(modules.items(), key=lambda item: item[1]):
        try:
            tree = ast.parse((repo / relative).read_text(encoding="utf-8"), filename=relative)
        except (SyntaxError, UnicodeDecodeError) as exc:
            # A file the walker cannot parse is reported, never silently skipped: a
            # missing module lowers propagation cost, which is the direction this
            # extractor's errors have historically run.
            graph.unresolved.append(f"{relative}: unparsed ({exc.__class__.__name__})")
            continue

        for node, depth in _walk_imports(tree):
            resolved_targets: list[tuple[str, str]] = []
            if isinstance(node, ast.Import):
                resolved_targets = [
                    (_resolve(alias.name, modules), KIND_IMPORT) for alias in node.names
                ]
            elif isinstance(node, ast.ImportFrom):
                base = _absolute_target(node, name)
                if not base:
                    continue
                # `from pkg import thing`: `thing` is a submodule or a name inside
                # `pkg`. Deepest-matching-module resolves each alias to ONE target —
                # the submodule if it exists, otherwise the package itself.
                package = _resolve(base, modules)
                for alias in node.names:
                    target = _resolve(f"{base}.{alias.name}", modules)
                    resolved_targets.append((target, KIND_FROM))
                    # The package edge is recorded only when it is a *different*
                    # dependency than the one just resolved — i.e. when the alias named
                    # a submodule, so importing it also executes the package. When the
                    # alias was a plain name, `base` and the resolved target are the
                    # same module and a second row would say nothing.
                    if package and package != target:
                        resolved_targets.append((package, KIND_PACKAGE))

            for resolved, kind in resolved_targets:
                if not resolved or resolved == relative:
                    continue
                graph.edges.append(
                    DependencyEdge(
                        from_path=relative,
                        to_path=resolved,
                        kind=kind,
                        depth=depth,
                    )
                )
    # Deduplicate while keeping the shallowest depth for each pair: a dependency that
    # exists at module level is a module-level dependency even if it is also imported
    # inside a function somewhere else in the file.
    graph.edges = _collapse(graph.edges)
    _ = by_path
    return graph


def _collapse(edges: list[DependencyEdge]) -> list[DependencyEdge]:
    """One record per (from, to, kind), keeping module-level over deferred."""
    best: dict[tuple[str, str, str], DependencyEdge] = {}
    for edge in edges:
        key = (edge.from_path, edge.to_path, edge.kind)
        held = best.get(key)
        if held is None or (held.depth == DEPTH_DEFERRED and edge.depth == DEPTH_MODULE):
            best[key] = edge
    return sorted(best.values(), key=lambda e: (e.from_path, e.to_path, e.kind))
