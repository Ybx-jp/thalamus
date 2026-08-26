"""Census the tree for code that was built and is not reached from production.

Two checks over one walk, both stated against what was *scanned* rather than against
the system, in the register `routes.py` uses for an uncalled route: this module reports
"no reference outside `tests/` was found", never "dead code". The distinction is not
politeness. A name census resolves references by identifier, so every mechanism that
reaches a name without spelling it — `getattr`, a dispatch table keyed by string, a
`__all__` re-export consumed by a star import — is outside its reach. Those mechanisms
are reported as limits of the scan (`UNDERSTANDING`), so a reader can tell a symbol
nothing calls from a symbol this instrument cannot see the call to.

**`test_only_symbols` is the sharp variant.** A symbol referenced only from `tests/` is
one whose entire demonstrated demand is its own test. That is narrower and more
actionable than "unreferenced": an unreferenced public helper may be API surface, while
a helper with a passing test and no caller is a component whose only client is the proof
that it works. The default policy therefore reports the test-only set and leaves the
never-referenced set behind `report_unreferenced`, which is a declared switch rather
than a judgement baked into the walk.

**Exemptions are declarative, and each says which rule granted it.** Four kinds, in the
order they are tried: a dunder, a name that overrides a stdlib or framework hook
(`do_GET` is called by `BaseHTTPRequestHandler`, never by this repo), a registering
decorator (`@mcp.tool`, `@app.get` — the call site is the registry's, not a caller's),
and a hand-declared entry carrying a required reason. A decorator that only reshapes the
function it wraps — `staticmethod`, `property`, `dataclass` — grants nothing, because
treating every decorator as a registration would exempt most of the tree and turn the
check off without saying so.

**A caller does not have to be a Python file.** `role-guard.sh` runs on every Edit and
Write in every session on this checkout, and it reaches `contract.ownership.denies`,
`WriteBoundary.denies`, `denies_skill` and `denies_tool` from `"$py" - <<PY` heredocs.
An import census blind to those reports four live contract symbols as reached only by
their tests. So the declared `reference_extensions` — `.sh` — are read, their heredocs
are parsed as Python, and the same reference walk runs over the result. The channel is
`ast`, not text: a name is reached when the parsed block reads it, which is why
`denies_skill` cannot be matched by a substring of `denies` and why a Python comment
inside a heredoc reaches nothing.

**A word in shell prose is not a call, and this repo proves it both ways.** The same
`role-guard.sh` writes the word `denies` in a comment describing the mechanism, three
lines from a real call — and writes `ownership.fallback_markers()`, parentheses and all,
in a comment recording that those markers are *copy-pasted instead of* calling it,
because the interpreter that would compute them is the thing that just failed. No text
match separates those two, and counting either would silence a true finding. Nothing
outside a parsed block is counted as a reference; a whole-word occurrence of a name the
census is about to report is attached to that finding as a limit, so the reader is
pointed at the one line that could refute it.

The failure modes this leaves, all in the direction of reporting rather than silencing:
a heredoc opened inside a quoted string is believed in and then discarded unread when no
line terminates it; a second heredoc opened on the same line is missed; a block that
parses but imports nothing is not read, since it could not reach a package name anyway;
and a shell script that calls the package some other way — `python -c`, a CLI
subcommand — is not a channel this reads. A block whose delimiter announces Python and
whose body will not parse is the one miss reported outright, because its names are
reachable and unread.

**`orphan_modules` is fan-in zero minus the declared entry points.** A module nothing
imports is either unreached or a process entry — `cli.py`, `__main__.py`, a browser
client folded in by the route channel — and only a declaration can tell those apart, so
the entry-point list is authored rather than inferred. Pass the census to fold in the
embedded channel: `contract/ownership.py` is imported by `role-guard.sh` and by no
scanned module, and the same false accusation is available one level up from the symbol.
"""

from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from thalamus.arch.extractor import (
    DependencyGraph,
    ExtractorPolicy,
    _collect_modules,
    _resolve,
)
from thalamus.arch.findings import DESIGN, UNDERSTANDING, Finding
from thalamus.arch.metrics import fan_in

# What a definition is, recorded because the three carry different risk. A method may be
# reached by a base class the walk never reads; a module-level function may not.
KIND_FUNCTION = "function"
KIND_METHOD = "method"
KIND_CLASS = "class"

# Which rule exempted a definition. Carried on the record so the report can say why a
# symbol is absent from the findings rather than leaving the reader to re-derive it.
RULE_DUNDER = "dunder"
RULE_OVERRIDE = "override-name"
RULE_DECORATOR = "decorator"
RULE_DECLARED = "declared"

# Names the interpreter or a framework calls by protocol. `console/server.py` defines
# `do_GET`, `do_POST` and `log_message` because `BaseHTTPRequestHandler` dispatches to
# them; no line in this repo names them, and a census that reported them would be
# reporting the protocol rather than the code.
STDLIB_OVERRIDE_NAMES: frozenset[str] = frozenset(
    {
        # http.server.BaseHTTPRequestHandler and its socketserver base
        "do_GET",
        "do_POST",
        "do_HEAD",
        "do_PUT",
        "do_PATCH",
        "do_DELETE",
        "do_OPTIONS",
        "handle",
        "handle_one_request",
        "log_message",
        "log_error",
        "log_request",
        "setup",
        "finish",
        "server_bind",
        "server_close",
        # unittest / pytest collection protocol
        "setUp",
        "tearDown",
        "setUpClass",
        "tearDownClass",
        # copy, pickle and the descriptor protocol's non-dunder halves
        "run",
        "close",
    }
)

# Decorators that reshape a definition without registering it anywhere. A name wearing
# one of these is still reached by being called, so the decorator is no evidence that
# something outside the scan calls it.
INERT_DECORATORS: frozenset[str] = frozenset(
    {
        "abstractmethod",
        "cache",
        "cached_property",
        "classmethod",
        "contextmanager",
        "dataclass",
        "final",
        "lru_cache",
        "override",
        "overload",
        "property",
        "singledispatch",
        "staticmethod",
        "total_ordering",
        "wraps",
    }
)

# How a reference was reached, when it was not reached from a parsed `.py` module.
SILENCE_EMBEDDED = "embedded-python"

# A heredoc opener: `<<DELIM`, `<<'DELIM'`, `<<-"DELIM"`. Found by line scan rather than
# by a shell parser, so `<<` inside a quoted string opens a block this scanner believes
# in — which costs nothing, because a block with no terminating line is discarded.
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
# A heredoc whose delimiter announces Python but whose body will not parse is this
# extractor's own miss, and is the one case it reports.
_PYTHON_DELIMITER = re.compile(r"^PY", re.IGNORECASE)
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# Callables whose argument decides a name at runtime. A file containing one of these is
# a file where the census can be wrong in the direction that matters — it can miss a
# caller — so every occurrence is reported as a limit of the scan's reach.
_DYNAMIC_CALLS: frozenset[str] = frozenset(
    {"getattr", "setattr", "delattr", "eval", "exec", "__import__", "import_module"}
)
_DYNAMIC_NAMESPACES: frozenset[str] = frozenset({"globals", "locals", "vars"})


@dataclass(frozen=True)
class Exemption:
    """One hand-declared symbol the census must not report, with the reason it stands.

    `reason` is required and is the first field for the same reason `model.Accepted`
    puts it there: an exemption list whose entries do not say why is a list that only
    grows, because the next reader has no basis on which to remove one.

    `path` is an fnmatch pattern over the repo-relative file; `symbol` matches either the
    bare name or the dotted qualified name (`SkillPolicy.denies_skill`). Both are
    required, so an entry cannot silently exempt a name across the whole tree.
    """

    reason: str
    path: str
    symbol: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError(f"exemption for {self.path}::{self.symbol} carries no reason")
        if not self.path.strip() or not self.symbol.strip():
            raise ValueError("an exemption must name both a path pattern and a symbol")

    def covers(self, definition: Definition) -> bool:
        return fnmatch.fnmatch(definition.path, self.path) and self.symbol in (
            definition.name,
            definition.qualname,
        )

    def block(self) -> dict[str, str]:
        return {"reason": self.reason, "path": self.path, "symbol": self.symbol}


@dataclass(frozen=True)
class Definition:
    """One name bound by a `def` or `class` under a scanned source root."""

    name: str
    qualname: str
    path: str
    line: int
    kind: str
    decorators: tuple[str, ...] = ()
    # Last line of the body, so a reference can be tested for being inside the
    # definition it would otherwise appear to reach.
    end_line: int = 0

    def describe(self) -> str:
        return f"{self.path}:{self.line} {self.qualname}"


@dataclass(frozen=True)
class Exempted:
    """A definition the census declined to report, and the rule that excused it."""

    definition: Definition
    rule: str
    detail: str = ""

    def describe(self) -> str:
        detail = f" ({self.detail})" if self.detail else ""
        return f"{self.definition.describe()} — exempt by {self.rule}{detail}"


@dataclass(frozen=True)
class Silenced:
    """A definition a file the import walk never parsed turns out to reach.

    The counterpart to `Exempted`, and a weaker fact than a plain source reference: the
    caller was found by parsing Python out of a shell heredoc, so it is a real call site
    with a real line number, but it lives in a file no module imports. Carried on the
    report so a reader can see which findings this channel removed and check them.
    """

    definition: Definition
    form: str
    sites: tuple[str, ...] = ()

    def describe(self) -> str:
        shown = ", ".join(self.sites[:5])
        return f"{self.definition.describe()} — reached from {self.form} at {shown}"


@dataclass(frozen=True)
class DeadEndPolicy:
    """The declared rules this census was taken under. Digested like every other channel.

    Its own block and its own digest, so enabling it does not move the import
    measurement's key. It contributes no edge to the visibility matrix, so it stays out
    of `model.scan_id` for the reason stated there: it changes no number that key names.
    """

    version: int = 1
    enabled: bool = False
    source_roots: tuple[str, ...] = ("src",)
    test_roots: tuple[str, ...] = ("tests",)
    # Files under those roots that are not Python but embed it. `.sh` is here because
    # this repo's hooks run `"$py" - <<'PY'` blocks that import from the package, so a
    # census blind to them reports four live contract symbols as reached only by tests.
    reference_extensions: tuple[str, ...] = (".sh",)
    # Modules a process starts at, or that a runtime other than the import graph loads.
    # `__init__.py` is here because a package's presence is what imports it, and the
    # route channel's browser clients are here because the browser is their caller.
    entry_points: tuple[str, ...] = (
        "**/__init__.py",
        "**/__main__.py",
        "**/cli.py",
        "**/conftest.py",
        "**/static/*",
    )
    kinds: tuple[str, ...] = (KIND_FUNCTION, KIND_METHOD, KIND_CLASS)
    override_names: tuple[str, ...] = tuple(sorted(STDLIB_OVERRIDE_NAMES))
    inert_decorators: tuple[str, ...] = tuple(sorted(INERT_DECORATORS))
    exemptions: tuple[Exemption, ...] = ()
    # Off by default. A never-referenced symbol is a weaker signal than a test-only one
    # — it may be API surface with no client yet — and mixing the two would let the
    # weaker finding set the tone of the whole list.
    report_unreferenced: bool = False

    def block(self) -> dict[str, object]:
        """The policy as it appears in `arch/model.yaml`, without its own digest."""
        return {
            "version": self.version,
            "enabled": self.enabled,
            "source_roots": list(self.source_roots),
            "test_roots": list(self.test_roots),
            "reference_extensions": list(self.reference_extensions),
            "entry_points": list(self.entry_points),
            "kinds": list(self.kinds),
            "override_names": list(self.override_names),
            "inert_decorators": list(self.inert_decorators),
            "exemptions": [item.block() for item in self.exemptions],
            "report_unreferenced": self.report_unreferenced,
        }

    def digest(self) -> str:
        """sha256 over the canonically serialised block, as the import policy does."""
        canonical = json.dumps(self.block(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def from_block(cls, block: dict) -> DeadEndPolicy:
        """Rebuild a policy from a model file's `deadends:` mapping.

        An exemption missing its reason raises here rather than loading as a blank one:
        the file is the place the reason is authored, so a silent default would make the
        requirement unenforced exactly where it is meant to bind.
        """
        defaults = cls()
        exemptions = tuple(
            Exemption(
                reason=str(entry.get("reason", "")),
                path=str(entry.get("path", "")),
                symbol=str(entry.get("symbol", "")),
            )
            for entry in block.get("exemptions") or ()
        )
        return cls(
            version=int(block.get("version", defaults.version)),
            enabled=bool(block.get("enabled", defaults.enabled)),
            source_roots=tuple(block.get("source_roots", defaults.source_roots)),
            test_roots=tuple(block.get("test_roots", defaults.test_roots)),
            reference_extensions=tuple(
                block.get("reference_extensions", defaults.reference_extensions)
            ),
            entry_points=tuple(block.get("entry_points", defaults.entry_points)),
            kinds=tuple(block.get("kinds", defaults.kinds)),
            override_names=tuple(block.get("override_names", defaults.override_names)),
            inert_decorators=tuple(block.get("inert_decorators", defaults.inert_decorators)),
            exemptions=exemptions or defaults.exemptions,
            report_unreferenced=bool(
                block.get("report_unreferenced", defaults.report_unreferenced)
            ),
        )

    def is_entry_point(self, path: str) -> bool:
        return any(fnmatch.fnmatch(path, pattern) for pattern in self.entry_points)


@dataclass
class Census:
    """Every definition under the source roots, and where each name was referenced."""

    definitions: list[Definition] = field(default_factory=list)
    # name -> the repo-relative files that reference it, split by which root they sit in.
    source_refs: dict[str, set[str]] = field(default_factory=dict)
    test_refs: dict[str, set[str]] = field(default_factory=dict)
    # Names reached from Python embedded in a non-Python file under the source roots.
    embedded_refs: dict[str, set[str]] = field(default_factory=dict)
    # Names that merely occur as a word in such a file, outside every embedded block.
    # Not references — see `_text_mentions` — and consulted only to state a limit.
    text_mentions: dict[str, set[str]] = field(default_factory=dict)
    # Scanned modules an embedded block imports, path -> the sites that import them. A
    # module a hook imports is reached, so this is what keeps the orphan check from
    # making the same false accusation one level up from the symbol census.
    embedded_modules: dict[str, set[str]] = field(default_factory=dict)
    # Names that appear as a whole string literal somewhere. Not counted as references —
    # doing so would silence real findings — but recorded, because a name reached only
    # through a string is exactly what this census cannot follow.
    string_names: dict[str, set[str]] = field(default_factory=dict)
    exported: dict[str, set[str]] = field(default_factory=dict)
    # file -> the runtime name lookups in it, deduplicated. Kept per file rather than
    # flattened because which root a lookup sits in decides whether it can turn a
    # finding into a false accusation — see `_reach_limits`.
    dynamic: dict[str, list[str]] = field(default_factory=dict)
    source_files: set[str] = field(default_factory=set)
    limits: list[str] = field(default_factory=list)
    policy: DeadEndPolicy = field(default_factory=DeadEndPolicy)


@dataclass
class DeadEndReport:
    """What the two checks found, what they excused, and what they could not see."""

    test_only: list[Definition] = field(default_factory=list)
    unreferenced: list[Definition] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    exempted: list[Exempted] = field(default_factory=list)
    silenced: list[Silenced] = field(default_factory=list)
    limits: list[str] = field(default_factory=list)
    policy: DeadEndPolicy = field(default_factory=DeadEndPolicy)

    def block(self) -> dict[str, object]:
        """The report in the shape a model file's derived section stores it."""
        return {
            "test_only": [item.describe() for item in self.test_only],
            "unreferenced": [item.describe() for item in self.unreferenced],
            "orphans": list(self.orphans),
            "exempted": [item.describe() for item in self.exempted],
            "silenced": [item.describe() for item in self.silenced],
            "limits": list(self.limits),
        }


def _decorator_name(node: ast.expr) -> str:
    """Dotted spelling of a decorator expression: `@app.get("/x")` -> `app.get`."""
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    if isinstance(node, ast.Attribute):
        base = _decorator_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _definitions(tree: ast.Module, path: str) -> list[Definition]:
    """Every `def` and `class` bound at module or class scope, with its decorators.

    A definition inside a function body is skipped: it is a local binding, reachable
    only from the enclosing function, so "nothing outside it refers to this" is not a
    statement about the repo.
    """
    found: list[Definition] = []

    def visit(node: ast.AST, prefix: str, inside_function: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qualname = f"{prefix}.{child.name}" if prefix else child.name
                is_class = isinstance(child, ast.ClassDef)
                if not inside_function:
                    found.append(
                        Definition(
                            name=child.name,
                            qualname=qualname,
                            path=path,
                            line=child.lineno,
                            kind=KIND_CLASS if is_class else (
                                KIND_METHOD if prefix else KIND_FUNCTION
                            ),
                            decorators=tuple(
                                name
                                for name in (
                                    _decorator_name(item) for item in child.decorator_list
                                )
                                if name
                            ),
                            end_line=child.end_lineno or child.lineno,
                        )
                    )
                visit(child, qualname, inside_function or not is_class)
            else:
                visit(child, prefix, inside_function)

    visit(tree, "", False)
    return found


def _docstring_nodes(tree: ast.Module) -> set[int]:
    """`id()` of every docstring constant, so prose is not read as a dispatch key."""
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                found.add(id(first.value))
    return found


def _references(tree: ast.Module) -> list[tuple[str, int]]:
    """Every name this file reads, with the line it was read on.

    Attribute access counts by its final segment — `spans.step_shape` references
    `step_shape` — which is what makes a module-qualified call reach a definition the
    walk recorded under its bare name. It also means an unrelated attribute of the same name counts —
    the error runs toward *not* reporting, which is the safe direction for a finding
    phrased as an accusation.

    `getattr(obj, "name")` with a literal is a real reference and is counted as one. The
    non-literal form is unresolvable and is recorded as a limit instead.
    """
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Load, ast.Del)):
            found.append((node.id, node.lineno))
        elif isinstance(node, ast.Attribute):
            found.append((node.attr, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                found.append((alias.name, node.lineno))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ("getattr", "setattr", "delattr") and len(node.args) >= 2:
                target = node.args[1]
                if isinstance(target, ast.Constant) and isinstance(target.value, str):
                    found.append((target.value, node.lineno))
    return found


def _string_names(tree: ast.Module) -> set[str]:
    """Whole string literals that could be a name, excluding docstrings.

    Exact equality only. A substring test would match the word `adopt` inside a sentence
    and turn every docstring into evidence, which is the opposite of a limit worth
    reporting.
    """
    skip = _docstring_nodes(tree)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in skip and node.value.isidentifier():
                found.add(node.value)
    return found


def _exported(tree: ast.Module) -> set[str]:
    """Names in a module-level `__all__`, which a star import re-exports."""
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets: list[ast.expr] = list(node.targets)
            value: ast.expr | None = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            continue
        if isinstance(value, (ast.List, ast.Tuple)):
            for item in value.elts:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    found.add(item.value)
    return found


def _dynamic_sites(tree: ast.Module) -> list[str]:
    """Call forms that name a symbol at runtime, as short notes naming the form.

    A `getattr` whose second argument is a literal is resolved by `_references` and is
    not reported here; only the forms that leave the census blind are.
    """
    seen: set[str] = set()
    notes: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = ""
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        if name in _DYNAMIC_NAMESPACES and not node.args:
            pass
        elif name not in _DYNAMIC_CALLS:
            continue
        elif name in ("getattr", "setattr", "delattr") and len(node.args) >= 2:
            target = node.args[1]
            if isinstance(target, ast.Constant) and isinstance(target.value, str):
                continue
        note = f"{name}() at line {node.lineno}"
        if note not in seen:
            seen.add(note)
            notes.append(note)
    return notes


def _heredocs(text: str) -> list[tuple[int, str, list[str]]]:
    """(line the `<<` sits on, delimiter, body lines) for every heredoc in a shell file.

    A line scan, not a shell parse. `<<` inside a quoted string opens a block this
    scanner believes in, and a second heredoc opened on the same line is missed. The
    first costs nothing — a block with no line equal to its delimiter is discarded
    unread — and the second is a miss in the direction that reports rather than
    silences, which is the direction a finding phrased as an accusation must err in.
    """
    lines = text.splitlines()
    found: list[tuple[int, str, list[str]]] = []
    index = 0
    while index < len(lines):
        match = _HEREDOC.search(lines[index])
        if match is None:
            index += 1
            continue
        delimiter = match.group(2)
        cursor = index + 1
        while cursor < len(lines) and lines[cursor].strip() != delimiter:
            cursor += 1
        if cursor >= len(lines):
            index += 1
            continue
        found.append((index + 1, delimiter, lines[index + 1 : cursor]))
        index = cursor + 1
    return found


def _embedded_python(
    text: str, path: str
) -> tuple[list[tuple[int, ast.Module]], set[int], list[str]]:
    """Python parsed out of a shell file's heredocs, the lines it covers, and the misses.

    A block counts as Python only if it parses **and** contains an import statement. The
    import is the discriminator that matters twice over: prose parses as Python often
    enough to be a real source of false silencing, and a block that imports nothing
    cannot reach a name in this package to begin with.

    A block whose delimiter announces Python and whose body will not parse is this
    extractor's own miss and is returned as a note, because the names inside it are
    reachable and unread.
    """
    blocks: list[tuple[int, ast.Module]] = []
    covered: set[int] = set()
    notes: list[str] = []
    for line, delimiter, body in _heredocs(text):
        try:
            tree = ast.parse("\n".join(body))
        except (SyntaxError, ValueError):
            if _PYTHON_DELIMITER.match(delimiter):
                notes.append(
                    f"{path}:{line}: heredoc `{delimiter}` does not parse as Python — "
                    "the names it reaches are outside this census"
                )
            continue
        if not any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(tree)):
            continue
        blocks.append((line, tree))
        covered.update(range(line + 1, line + 1 + len(body)))
    return blocks, covered, notes


def _embedded_imports(tree: ast.Module, modules: dict[str, str]) -> set[str]:
    """Repo-relative paths of the scanned modules an embedded block imports.

    Absolute imports only, which is not a gap: a heredoc handed to `python -` runs with
    no package context, so a relative import there could not resolve at runtime either.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                resolved = _resolve(alias.name, modules)
                if resolved:
                    found.add(resolved)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            package = _resolve(node.module, modules)
            if package:
                found.add(package)
            for alias in node.names:
                resolved = _resolve(f"{node.module}.{alias.name}", modules)
                if resolved:
                    found.add(resolved)
    return found


def _text_mentions(text: str, covered: set[int], names: set[str]) -> dict[str, set[int]]:
    """Where a defined name occurs as a whole word outside every embedded-Python block.

    These are **not** counted as references, and the reason is measured on this repo:
    `role-guard.sh` writes the words `denies` and `fallback_markers()` in shell comments
    describing the mechanism, one of which sits beside a real call and one of which
    documents a deliberate copy-paste *instead* of a call. A text match cannot separate
    those, so counting it would silence a true finding. It is reported as a limit on the
    findings it could have refuted instead.
    """
    found: dict[str, set[int]] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if number in covered:
            continue
        for match in _IDENTIFIER.finditer(line):
            name = match.group(0)
            if name in names:
                found.setdefault(name, set()).add(number)
    return found


def _reference_files(
    repo: Path, roots: tuple[str, ...], extensions: tuple[str, ...], exclude: tuple[str, ...]
) -> list[str]:
    """Repo-relative paths of the declared non-Python files under `roots`."""
    found: set[str] = set()
    for root in roots:
        root_dir = repo / root
        if not root_dir.is_dir():
            continue
        for extension in extensions:
            for path in root_dir.rglob(f"*{extension}"):
                relative = path.relative_to(repo).as_posix()
                if not any(fnmatch.fnmatch(relative, pattern) for pattern in exclude):
                    found.add(relative)
    return sorted(found)


def _files(repo: Path, roots: tuple[str, ...], exclude: tuple[str, ...]) -> list[str]:
    """Repo-relative paths of the Python files under `roots`.

    Collected through the extractor's own module walk so the two channels cannot
    disagree about which files are in the tree — the census is about the same set of
    modules the dependency graph is built from.
    """
    policy = ExtractorPolicy(roots=roots, exclude=exclude)
    return sorted(_collect_modules(repo, policy).values())


def census(repo: Path, policy: DeadEndPolicy | None = None) -> Census:
    """Walk the source and test roots once, recording definitions and references.

    A file that will not parse is recorded as a limit rather than skipped, for the
    reason the import walk gives: a file dropped in silence removes references, and
    missing references manufacture findings.
    """
    policy = policy or DeadEndPolicy()
    result = Census(policy=policy)

    source_files = _files(repo, policy.source_roots, ExtractorPolicy().exclude)
    # The default exclude carries `tests/**`, which would empty the test roots. The test
    # walk declares its own, keeping only the caches and vendored trees out.
    test_exclude = ("**/__pycache__/**", "**/node_modules/**", ".venv/**")
    test_files = _files(repo, policy.test_roots, test_exclude)
    result.source_files = set(source_files)

    for relative in [*source_files, *test_files]:
        in_source = relative in result.source_files
        try:
            tree = ast.parse((repo / relative).read_text(encoding="utf-8"), filename=relative)
        except (SyntaxError, UnicodeDecodeError) as exc:
            result.limits.append(f"{relative}: unparsed ({exc.__class__.__name__})")
            continue

        if in_source:
            result.definitions.extend(_definitions(tree, relative))
            for name in _exported(tree):
                result.exported.setdefault(name, set()).add(relative)

        bucket = result.source_refs if in_source else result.test_refs
        for name, line in _references(tree):
            bucket.setdefault(name, set()).add(f"{relative}:{line}")
        for name in _string_names(tree):
            result.string_names.setdefault(name, set()).add(relative)
        sites = _dynamic_sites(tree)
        if sites:
            result.dynamic[relative] = sites

    _walk_reference_files(repo, result, policy, test_exclude)
    return result


def _walk_reference_files(
    repo: Path, result: Census, policy: DeadEndPolicy, test_exclude: tuple[str, ...]
) -> None:
    """Fold the non-Python files under both root sets into the census.

    A hit under the source roots is a production reference and silences a finding; a hit
    under the test roots is a test reference and does not, which is the same split the
    `.py` walk makes and for the same reason.
    """
    defined = {definition.name for definition in result.definitions}
    scanned = _collect_modules(
        repo, ExtractorPolicy(roots=policy.source_roots, exclude=ExtractorPolicy().exclude)
    )
    source = _reference_files(
        repo, policy.source_roots, policy.reference_extensions, ExtractorPolicy().exclude
    )
    tests = _reference_files(
        repo, policy.test_roots, policy.reference_extensions, test_exclude
    )
    for relative in [*source, *tests]:
        try:
            text = (repo / relative).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            result.limits.append(f"{relative}: unread ({exc.__class__.__name__})")
            continue
        blocks, covered, notes = _embedded_python(text, relative)
        result.limits.extend(notes)
        bucket = result.embedded_refs if relative in source else result.test_refs
        for line, tree in blocks:
            for name, offset in _references(tree):
                bucket.setdefault(name, set()).add(f"{relative}:{line + offset}")
            if relative in source:
                for module in _embedded_imports(tree, scanned):
                    result.embedded_modules.setdefault(module, set()).add(f"{relative}:{line}")
        if relative not in source:
            continue
        for name, numbers in _text_mentions(text, covered, defined).items():
            for number in sorted(numbers):
                result.text_mentions.setdefault(name, set()).add(f"{relative}:{number}")


def _reach_limits(walked: Census, policy: DeadEndPolicy) -> list[str]:
    """The scan-wide gaps: files that would not parse, and runtime name lookups.

    A runtime lookup under a **source** root is always reported, because it is the form
    that can hide the production caller of a symbol this census is about to report as
    having none — the one error that turns a finding into a false accusation.

    A lookup under a **test** root can only add a test reference. Under the default
    policy that moves nothing: a symbol with a hidden test reference is reported the same
    way either side of it. It is reported when `report_unreferenced` is on, because that
    is the reading where the presence or absence of a test reference decides which of the
    two findings a symbol earns.
    """
    notes = list(walked.limits)
    for path, sites in sorted(walked.dynamic.items()):
        if path not in walked.source_files and not policy.report_unreferenced:
            continue
        for site in sites:
            notes.append(f"{path}: runtime name lookup — {site}")
    return notes


def _exemption_for(
    definition: Definition, policy: DeadEndPolicy
) -> Exempted | None:
    """The first declared rule that excuses this definition, or None."""
    name = definition.name
    if name.startswith("__") and name.endswith("__"):
        return Exempted(definition, RULE_DUNDER)
    if name in set(policy.override_names):
        return Exempted(definition, RULE_OVERRIDE, name)
    inert = set(policy.inert_decorators)
    for decorator in definition.decorators:
        if decorator.split(".")[-1] in inert or decorator in inert:
            continue
        return Exempted(definition, RULE_DECORATOR, f"@{decorator}")
    for exemption in policy.exemptions:
        if exemption.covers(definition):
            return Exempted(definition, RULE_DECLARED, exemption.reason)
    return None


def _outside_own_body(definition: Definition, sites: set[str]) -> set[str]:
    """References to this name that do not sit inside the definition's own lines.

    A recursive call and a method calling its own name are inside the body; counting
    them would make every self-referential function look reached.
    """
    kept: set[str] = set()
    for site in sites:
        path, _, line = site.rpartition(":")
        if path == definition.path and definition.line <= int(line) <= definition.end_line:
            continue
        kept.add(site)
    return kept


def test_only_symbols(
    repo: Path, policy: DeadEndPolicy | None = None, walked: Census | None = None
) -> DeadEndReport:
    """Symbols defined under the source roots and referenced only from the test roots.

    The report says what was measured: no reference outside `tests/` was found. It does
    not say the symbol is unused — the census resolves names, and `limits` names every
    place in the scanned tree where a name is chosen at runtime instead of written down.
    """
    policy = policy or DeadEndPolicy()
    walked = walked if walked is not None else census(repo, policy)
    report = DeadEndReport(policy=policy, limits=_reach_limits(walked, policy))

    kinds = set(policy.kinds)
    for definition in walked.definitions:
        if definition.kind not in kinds:
            continue
        source = _outside_own_body(definition, walked.source_refs.get(definition.name, set()))
        if source:
            continue
        tests = _outside_own_body(definition, walked.test_refs.get(definition.name, set()))
        would_report = bool(tests) or policy.report_unreferenced
        # A found call site is a fact about the tree; an exemption is a policy statement
        # about it. The fact is consulted first, so a symbol a hook actually calls is
        # reported as reached rather than as excused.
        embedded = sorted(walked.embedded_refs.get(definition.name, set()))
        if embedded:
            if would_report:
                report.silenced.append(
                    Silenced(definition, SILENCE_EMBEDDED, tuple(embedded))
                )
            continue
        excused = _exemption_for(definition, policy)
        if excused is not None:
            report.exempted.append(excused)
            continue
        if tests:
            report.test_only.append(definition)
        elif policy.report_unreferenced:
            report.unreferenced.append(definition)
        else:
            continue
        _note_reach(report, walked, definition)

    report.test_only.sort(key=lambda item: (item.path, item.line))
    report.unreferenced.sort(key=lambda item: (item.path, item.line))
    report.exempted.sort(key=lambda item: (item.definition.path, item.definition.line))
    report.silenced.sort(key=lambda item: (item.definition.path, item.definition.line))
    return report


# pytest collects any module-level callable whose name begins with `test_`. This one is
# a scanner entry point, so it declares itself not to be a test; without the marker,
# importing it into a test module raises a fixture error for `repo`.
setattr(test_only_symbols, "__test__", False)


def _note_reach(report: DeadEndReport, walked: Census, definition: Definition) -> None:
    """Record the ways this particular name could be reached without being written.

    Attached per reported symbol rather than per file: a string literal somewhere in the
    tree is only interesting when it spells a name the census is about to report, and a
    note on every literal would train a reader to skip the notes.

    Literals are read from the same roots `_reach_limits` reads runtime lookups from, and
    for the same reason — a string under the test roots can only stand for a test
    reference, which does not turn a reported finding into a false accusation.
    """
    literals = sorted(
        path
        for path in walked.string_names.get(definition.name, set())
        if path in walked.source_files or walked.policy.report_unreferenced
    )
    if literals:
        report.limits.append(
            f"{definition.path}: `{definition.name}` also occurs as a string literal in "
            f"{', '.join(literals[:5])} — a name reached through a string is outside "
            "this census"
        )
    mentions = sorted(walked.text_mentions.get(definition.name, set()))
    if mentions:
        report.limits.append(
            f"{definition.path}: `{definition.name}` occurs as a word in "
            f"{', '.join(mentions[:5])}, outside every embedded-Python block — a text "
            "match cannot tell a call from a mention, so it was not counted"
        )
    exporters = sorted(walked.exported.get(definition.name, set()))
    if exporters:
        report.limits.append(
            f"{definition.path}: `{definition.name}` is listed in `__all__` in "
            f"{', '.join(exporters)} — a star import of that module re-exports it "
            "without naming it"
        )


def orphan_modules(
    graph: DependencyGraph,
    policy: DeadEndPolicy | None = None,
    walked: Census | None = None,
) -> list[str]:
    """Scanned modules nothing imports, minus the declared entry points.

    Fan-in is taken under the graph's own declared policy, so a module reached only by a
    deferred import counts as reached under `import_depth: all` and does not under
    `module-level`. That is the extractor's declaration, not a second one made here.

    Pass `walked` to fold in the embedded-Python channel. Without it the check sees only
    the import graph, and a module whose importer is a shell hook reads as an orphan —
    `contract/ownership.py` is imported by `role-guard.sh` and by nothing else.
    """
    policy = policy or DeadEndPolicy()
    reached = set(walked.embedded_modules) if walked is not None else set()
    counts = fan_in(graph)
    return sorted(
        module
        for module, count in counts.items()
        if count == 0 and module not in reached and not policy.is_entry_point(module)
    )


def scan(
    repo: Path, graph: DependencyGraph | None = None, policy: DeadEndPolicy | None = None
) -> DeadEndReport:
    """Both checks over one walk. Returns an empty report when the channel is disabled."""
    policy = policy or DeadEndPolicy()
    if not policy.enabled:
        return DeadEndReport(policy=policy)
    walked = census(repo, policy)
    report = test_only_symbols(repo, policy, walked)
    if graph is not None:
        report.orphans = orphan_modules(graph, policy, walked)
    return report


def deadend_findings(report: DeadEndReport) -> list[Finding]:
    """What this census asserts, in the register an uncalled route is reported in.

    Every design finding names the tree it searched. "No reference outside `tests/` was
    found" is refutable by pointing at one; "dead code" is a verdict the instrument is
    not entitled to, because the mechanisms in `limits` are exactly the ones that would
    refute it.
    """
    found: list[Finding] = []
    for definition in report.test_only:
        found.append(
            Finding(
                description=(
                    f"{definition.path}:{definition.line} defines {definition.qualname}, "
                    "which no scanned source module references — every reference found "
                    "is under the declared test roots."
                ),
                category=DESIGN,
                artifacts=(definition.path,),
            )
        )
    for definition in report.unreferenced:
        found.append(
            Finding(
                description=(
                    f"{definition.path}:{definition.line} defines {definition.qualname}, "
                    "which no scanned module references outside its own body."
                ),
                category=DESIGN,
                artifacts=(definition.path,),
            )
        )
    for module in report.orphans:
        found.append(
            Finding(
                description=(
                    f"{module} is imported by no scanned module and is not a declared "
                    "entry point."
                ),
                category=DESIGN,
                artifacts=(module,),
            )
        )
    for note in report.limits:
        found.append(
            Finding(
                description=f"Limit of the census's reach: {note}.",
                category=UNDERSTANDING,
                artifacts=(note.split(":")[0],),
            )
        )
    return found
