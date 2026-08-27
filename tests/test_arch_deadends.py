"""Interfaces: thalamus.arch.deadends
Infrastructure: none — every unit fixture is a tree written into tmp_path. The last
       four cases read this checkout, because the census's precision is a claim about a
       real tree and a fixture cannot make it.
Scope: what the census reports, what it excuses and under which declared rule, the
       reach limits it states rather than hides, and the hedging of the finding text.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from thalamus.arch.deadends import (
    RULE_DECLARED,
    RULE_DECORATOR,
    RULE_DUNDER,
    RULE_OVERRIDE,
    SILENCE_EMBEDDED,
    DeadEndPolicy,
    Exemption,
    census,
    deadend_findings,
    orphan_modules,
    scan,
    test_only_symbols,
)
from thalamus.arch.extractor import ExtractorPolicy, scan_repo
from thalamus.arch.findings import DESIGN, UNDERSTANDING
from thalamus.arch.model import REPO_ROOT


def _tree(root: Path, files: dict[str, str]) -> Path:
    for relative, body in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def _names(report) -> list[str]:
    return [item.name for item in report.test_only]


# ─── what the census reports ───────────────────────────────────────────────────


def test_a_symbol_only_a_test_references_is_reported(tmp_path):
    """The sharp case: built, tested, and named by nothing under the source roots."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def only_tested():\n    return 1\n",
            "tests/test_helpers.py": (
                "from app.helpers import only_tested\n\n"
                "def test_it():\n    assert only_tested() == 1\n"
            ),
        },
    )
    report = test_only_symbols(repo)
    assert _names(report) == ["only_tested"]


def test_a_symbol_a_source_module_references_is_not_reported(tmp_path):
    """One production caller is enough; the check is about reach, not about count."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def used():\n    return 1\n",
            "src/app/caller.py": "from app.helpers import used\n\nVALUE = used()\n",
            "tests/test_helpers.py": "from app.helpers import used\n",
        },
    )
    assert _names(test_only_symbols(repo)) == []


def test_an_attribute_qualified_call_counts_as_a_reference(tmp_path):
    """`helpers.used()` reaches `used`; resolving only bare names would miss it."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def used():\n    return 1\n",
            "src/app/caller.py": "from app import helpers\n\nVALUE = helpers.used()\n",
            "tests/test_helpers.py": "from app import helpers\n",
        },
    )
    assert _names(test_only_symbols(repo)) == []


def test_getattr_with_a_literal_counts_as_a_reference(tmp_path):
    """A literal dispatch key is a written reference, so it is resolved, not deferred."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def dispatched():\n    return 1\n",
            "src/app/caller.py": (
                "from app import helpers\n\nFN = getattr(helpers, 'dispatched')\n"
            ),
            "tests/test_helpers.py": "from app.helpers import dispatched\n",
        },
    )
    assert _names(test_only_symbols(repo)) == []


def test_a_recursive_call_is_not_a_reference_to_itself(tmp_path):
    """A name used inside its own body has not been reached from anywhere."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": (
                "def walk(n):\n    if n:\n        return walk(n - 1)\n    return 0\n"
            ),
            "tests/test_helpers.py": "from app.helpers import walk\n",
        },
    )
    assert _names(test_only_symbols(repo)) == ["walk"]


def test_a_definition_inside_a_function_is_not_censused(tmp_path):
    """A closure is a local binding; "nothing outside it refers to this" says nothing."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/factory.py": (
                "def build():\n"
                "    def route():\n        return 1\n"
                "    return route\n"
            ),
            "tests/test_factory.py": "from app.factory import build\n",
        },
    )
    walked = census(repo)
    assert [d.name for d in walked.definitions] == ["build"]
    # `build` itself is test-only; the nested `route` is not a subject of the census.
    assert _names(test_only_symbols(repo)) == ["build"]


def test_a_class_reached_only_from_a_test_is_reported(tmp_path):
    """Classes are censused too; the bug class does not care what kind of name it is."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/shapes.py": "class Widget:\n    pass\n",
            "tests/test_shapes.py": "from app.shapes import Widget\n",
        },
    )
    report = test_only_symbols(repo)
    assert [(d.name, d.kind) for d in report.test_only] == [("Widget", "class")]


def test_declaring_fewer_kinds_narrows_the_census(tmp_path):
    """`kinds` is a declaration, so a run that reports only functions says so."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/shapes.py": "class Widget:\n    pass\n\n\ndef helper():\n    return 1\n",
            "tests/test_shapes.py": "from app.shapes import Widget, helper\n",
        },
    )
    policy = DeadEndPolicy(kinds=("function",))
    assert _names(test_only_symbols(repo, policy)) == ["helper"]


# ─── the declarative exemptions ────────────────────────────────────────────────


def test_a_registering_decorator_exempts_and_is_named(tmp_path):
    """`@mcp.tool` is the caller. The report says which decorator excused the symbol."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/server.py": (
                "import mcp\n\n\n@mcp.tool\ndef memory_recall():\n    return 1\n"
            ),
            "tests/test_server.py": "from app.server import memory_recall\n",
        },
    )
    report = test_only_symbols(repo)
    assert _names(report) == []
    excused = [item for item in report.exempted if item.definition.name == "memory_recall"]
    assert [(item.rule, item.detail) for item in excused] == [(RULE_DECORATOR, "@mcp.tool")]


def test_a_decorator_call_is_named_without_its_arguments(tmp_path):
    """`@app.get("/api/health")` exempts as `@app.get`; the route is not the rule."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/web.py": (
                "import app_obj\n\n\n@app_obj.get('/api/health')\ndef health():\n    return {}\n"
            ),
            "tests/test_web.py": "from app.web import health\n",
        },
    )
    report = test_only_symbols(repo)
    assert _names(report) == []
    assert any(item.detail == "@app_obj.get" for item in report.exempted)


def test_an_inert_decorator_does_not_exempt(tmp_path):
    """`@staticmethod` registers nothing, so it is no evidence of an unseen caller."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/shapes.py": (
                "class Widget:\n    @staticmethod\n    def measure():\n        return 1\n"
            ),
            "tests/test_shapes.py": (
                "from app.shapes import Widget\n\n"
                "def test_it():\n    assert Widget.measure() == 1\n"
            ),
        },
    )
    report = test_only_symbols(repo)
    assert "Widget.measure" in [d.qualname for d in report.test_only]
    assert not any(item.definition.name == "measure" for item in report.exempted)


def test_a_dunder_is_exempt(tmp_path):
    """The interpreter calls it; no line in the tree ever will."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/shapes.py": "class Widget:\n    def __len__(self):\n        return 0\n",
            "tests/test_shapes.py": "from app.shapes import Widget\n",
        },
    )
    report = test_only_symbols(repo)
    assert "__len__" not in _names(report)
    assert [item.rule for item in report.exempted if item.definition.name == "__len__"] == [
        RULE_DUNDER
    ]


def test_a_stdlib_override_name_is_exempt(tmp_path):
    """`BaseHTTPRequestHandler` dispatches to `do_GET`; reporting it reports the protocol."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/server.py": (
                "from http.server import BaseHTTPRequestHandler\n\n\n"
                "class Handler(BaseHTTPRequestHandler):\n"
                "    def do_GET(self):\n        return None\n\n"
                "    def log_message(self, *a):\n        return None\n"
            ),
            "tests/test_server.py": (
                "from app.server import Handler\n\n"
                "def test_it():\n    assert Handler.do_GET\n    assert Handler.log_message\n"
            ),
        },
    )
    report = test_only_symbols(repo)
    assert not {"do_GET", "log_message"} & set(_names(report))
    assert {item.rule for item in report.exempted if item.definition.kind == "method"} == {
        RULE_OVERRIDE
    }


def test_a_declared_exemption_is_honoured_with_its_reason(tmp_path):
    """The hand-declared half. The reason travels into the report, not just the file."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def only_tested():\n    return 1\n",
            "tests/test_helpers.py": "from app.helpers import only_tested\n",
        },
    )
    policy = DeadEndPolicy(
        exemptions=(
            Exemption(
                reason="called by the deploy script, which is outside the scanned roots",
                path="src/app/helpers.py",
                symbol="only_tested",
            ),
        )
    )
    report = test_only_symbols(repo, policy)
    assert _names(report) == []
    assert [(item.rule, item.detail) for item in report.exempted] == [
        (RULE_DECLARED, "called by the deploy script, which is outside the scanned roots")
    ]


def test_an_exemption_without_a_reason_is_refused():
    """An exemption list whose entries do not say why is a list that only grows."""
    with pytest.raises(ValueError):
        Exemption(reason="   ", path="src/app/helpers.py", symbol="only_tested")
    with pytest.raises(ValueError):
        Exemption(reason="because", path="", symbol="only_tested")


def test_an_exemption_is_scoped_to_its_path(tmp_path):
    """A bare name would exempt every same-named symbol in the tree. It does not."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/one.py": "def shared():\n    return 1\n",
            "src/app/two.py": "def shared():\n    return 2\n",
            "tests/test_both.py": "from app import one, two\n\nUSE = [one.shared, two.shared]\n",
        },
    )
    policy = DeadEndPolicy(
        exemptions=(
            Exemption(reason="the packaging entry point calls it", path="src/app/one.py",
                      symbol="shared"),
        )
    )
    report = test_only_symbols(repo, policy)
    assert [d.path for d in report.test_only] == ["src/app/two.py"]


# ─── the never-referenced reading, which is declared rather than assumed ───────


def test_a_never_referenced_symbol_is_held_back_by_default(tmp_path):
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def nobody():\n    return 1\n",
            "tests/test_nothing.py": "def test_it():\n    assert True\n",
        },
    )
    report = test_only_symbols(repo)
    assert _names(report) == []
    assert report.unreferenced == []


def test_a_never_referenced_symbol_is_reported_when_declared(tmp_path):
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def nobody():\n    return 1\n",
            "tests/test_nothing.py": "def test_it():\n    assert True\n",
        },
    )
    report = test_only_symbols(repo, DeadEndPolicy(report_unreferenced=True))
    assert [d.name for d in report.unreferenced] == ["nobody"]
    assert _names(report) == []


# ─── the reach limits, reported rather than hidden ─────────────────────────────


def test_a_runtime_lookup_in_a_source_module_is_a_stated_limit(tmp_path):
    """A non-literal `getattr` can hide the production caller of a reported symbol."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def only_tested():\n    return 1\n",
            "src/app/dispatch.py": (
                "from app import helpers\n\n\ndef call(name):\n"
                "    return getattr(helpers, name)()\n"
            ),
            "tests/test_helpers.py": "from app.helpers import only_tested\n",
        },
    )
    report = test_only_symbols(repo)
    assert _names(report) == ["only_tested"]
    assert any("src/app/dispatch.py" in note and "getattr()" in note for note in report.limits)


def test_a_runtime_lookup_under_the_test_roots_is_not_reported_by_default(tmp_path):
    """It can only add a test reference, which moves no finding under this reading."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def only_tested():\n    return 1\n",
            "tests/test_helpers.py": (
                "from app import helpers\n\n"
                "def test_it(name='only_tested'):\n    assert getattr(helpers, name)\n"
            ),
        },
    )
    assert test_only_symbols(repo).limits == []
    loud = test_only_symbols(repo, DeadEndPolicy(report_unreferenced=True))
    assert any("tests/test_helpers.py" in note for note in loud.limits)


def test_a_string_literal_naming_a_reported_symbol_is_a_stated_limit(tmp_path):
    """A dispatch table keyed by string reaches a name the census cannot follow."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def only_tested():\n    return 1\n",
            "src/app/table.py": "ROUTES = {'only_tested': None}\n",
            "tests/test_helpers.py": "from app.helpers import only_tested\n",
        },
    )
    report = test_only_symbols(repo)
    assert _names(report) == ["only_tested"]
    assert any("string literal" in note and "src/app/table.py" in note for note in report.limits)


def test_a_string_literal_under_the_test_roots_is_not_reported_by_default(tmp_path):
    """It can only stand for a test reference, which no reported finding turns on."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def only_tested():\n    return 1\n",
            "tests/test_helpers.py": (
                "from app.helpers import only_tested\n\nNAMES = ['only_tested']\n"
            ),
        },
    )
    assert not any("string literal" in note for note in test_only_symbols(repo).limits)
    loud = test_only_symbols(repo, DeadEndPolicy(report_unreferenced=True))
    assert any("string literal" in note for note in loud.limits)


def test_prose_naming_a_symbol_is_not_a_stated_limit(tmp_path):
    """Exact equality only. A docstring mentioning a name is not a dispatch key."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": '"""Explains only_tested at length."""\n\n\ndef only_tested():\n    return 1\n',
            "tests/test_helpers.py": "from app.helpers import only_tested\n",
        },
    )
    report = test_only_symbols(repo)
    assert _names(report) == ["only_tested"]
    assert not any("string literal" in note for note in report.limits)


def test_an_all_re_export_is_a_stated_limit(tmp_path):
    """A star import of the module reaches the name without ever spelling it."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "__all__ = ['only_tested']\n\n\ndef only_tested():\n    return 1\n",
            "tests/test_helpers.py": "from app.helpers import only_tested\n",
        },
    )
    report = test_only_symbols(repo)
    assert _names(report) == ["only_tested"]
    assert any("__all__" in note for note in report.limits)


def test_an_unparsed_file_is_a_stated_limit(tmp_path):
    """A file dropped in silence removes references, and missing references manufacture
    findings — so it is reported, the way the import walk reports one."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def only_tested():\n    return 1\n",
            "src/app/broken.py": "def (:\n",
            "tests/test_helpers.py": "from app.helpers import only_tested\n",
        },
    )
    report = test_only_symbols(repo)
    assert any("src/app/broken.py" in note and "unparsed" in note for note in report.limits)


# ─── the embedded-Python channel ───────────────────────────────────────────────

_HEREDOC_OPEN = "<" + "<'PY'"
_HOOK = (
    "#!/bin/bash\n"
    "# The word only_tested appears here, in shell prose, and rescues nothing.\n"
    'result=$("$py" - "$1" ' + _HEREDOC_OPEN + ' 2>/dev/null || true\n'
    "import sys\n"
    "from app.helpers import only_tested\n"
    "print(only_tested())\n"
    "PY\n"
    ")\n"
)


def test_a_symbol_a_shell_hook_imports_is_reached_not_reported(tmp_path):
    """`role-guard.sh` calls four contract symbols from a heredoc. They are not test-only."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def only_tested():\n    return 1\n",
            "src/app/hooks/guard.sh": _HOOK,
            "tests/test_helpers.py": "from app.helpers import only_tested\n",
        },
    )
    report = test_only_symbols(repo)
    assert _names(report) == []
    assert [(item.definition.name, item.form) for item in report.silenced] == [
        ("only_tested", SILENCE_EMBEDDED)
    ]
    # The lines are the import and the call inside the heredoc, counted from the file's
    # first line rather than from the heredoc's.
    assert report.silenced[0].sites == ("src/app/hooks/guard.sh:5", "src/app/hooks/guard.sh:6")


def test_a_mention_in_shell_prose_does_not_rescue_a_symbol(tmp_path):
    """The measured case: `role-guard.sh` names `fallback_markers()` in a comment to record
    that its markers are copy-pasted *instead* of calling it. Counting that text match
    would silence a true finding."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def inlined_markers():\n    return ('a',)\n",
            "src/app/hooks/guard.sh": (
                "#!/bin/bash\n"
                "# Markers are inlined from helpers.inlined_markers() rather than called.\n"
                "echo ok\n"
            ),
            "tests/test_helpers.py": "from app.helpers import inlined_markers\n",
        },
    )
    report = test_only_symbols(repo)
    assert _names(report) == ["inlined_markers"]
    assert report.silenced == []
    assert any(
        "occurs as a word in src/app/hooks/guard.sh:2" in note for note in report.limits
    )


def test_a_mention_matches_whole_words_only(tmp_path):
    """`denies` must not be matched by `denies_skill`, in either direction."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def denies():\n    return 1\n",
            "src/app/hooks/guard.sh": "#!/bin/bash\n# see denies_skill and undenies\n",
            "tests/test_helpers.py": "from app.helpers import denies\n",
        },
    )
    report = test_only_symbols(repo)
    assert _names(report) == ["denies"]
    assert not any("occurs as a word" in note for note in report.limits)


def test_a_heredoc_that_imports_nothing_is_not_read_as_python(tmp_path):
    """Prose parses as Python often enough to be a real source of false silencing, and a
    block that imports nothing cannot reach a name in the package anyway."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def only_tested():\n    return 1\n",
            "src/app/hooks/guard.sh": (
                "#!/bin/bash\ncat " + "<" + "<'EOF'\nonly_tested\nEOF\n"
            ),
            "tests/test_helpers.py": "from app.helpers import only_tested\n",
        },
    )
    report = test_only_symbols(repo)
    assert _names(report) == ["only_tested"]
    assert report.silenced == []


def test_a_python_heredoc_that_will_not_parse_is_a_stated_limit(tmp_path):
    """The extractor's own miss: names inside the block are reachable and unread."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def only_tested():\n    return 1\n",
            "src/app/hooks/guard.sh": (
                '#!/bin/bash\n"$py" - ' + _HEREDOC_OPEN + "\ndef (:\nPY\n"
            ),
            "tests/test_helpers.py": "from app.helpers import only_tested\n",
        },
    )
    report = test_only_symbols(repo)
    assert any("heredoc `PY` does not parse as Python" in note for note in report.limits)


def test_an_unterminated_heredoc_is_discarded_rather_than_swallowing_the_file(tmp_path):
    """A shifted `<` pair inside a quoted string opens a block this line scanner believes
    in. Costing nothing is what makes that acceptable."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def only_tested():\n    return 1\n",
            "src/app/hooks/guard.sh": (
                '#!/bin/bash\necho "a ' + "<" + '< NOPE b"\n# only_tested is named here\n'
            ),
            "tests/test_helpers.py": "from app.helpers import only_tested\n",
        },
    )
    report = test_only_symbols(repo)
    assert _names(report) == ["only_tested"]
    assert any("occurs as a word" in note for note in report.limits)


def test_the_extension_set_is_declared(tmp_path):
    """A channel that reads a file kind nobody declared is a channel with no policy."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def only_tested():\n    return 1\n",
            "src/app/hooks/guard.sh": _HOOK,
            "tests/test_helpers.py": "from app.helpers import only_tested\n",
        },
    )
    assert _names(test_only_symbols(repo)) == []
    narrowed = DeadEndPolicy(reference_extensions=())
    assert _names(test_only_symbols(repo, narrowed)) == ["only_tested"]
    assert DeadEndPolicy(reference_extensions=(".sh", ".bash")).digest() != (
        DeadEndPolicy().digest()
    )


def test_a_shell_file_under_the_test_roots_gives_a_test_reference(tmp_path):
    """The same split the `.py` walk makes: a test caller does not silence a finding."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def only_tested():\n    return 1\n",
            "tests/harness.sh": _HOOK,
        },
    )
    report = test_only_symbols(repo)
    assert _names(report) == ["only_tested"]
    assert report.silenced == []


def test_a_symbol_no_finding_would_name_is_not_recorded_as_silenced(tmp_path):
    """`silenced` is the list of findings this channel removed, not of everything it saw."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def only_tested():\n    return 1\n",
            "src/app/hooks/guard.sh": _HOOK,
            "tests/test_nothing.py": "def test_it():\n    assert True\n",
        },
    )
    assert test_only_symbols(repo).silenced == []
    loud = test_only_symbols(repo, DeadEndPolicy(report_unreferenced=True))
    assert [item.definition.name for item in loud.silenced] == ["only_tested"]


def test_a_module_a_shell_hook_imports_is_not_an_orphan(tmp_path):
    """`contract/ownership.py` is imported by `role-guard.sh` and by nothing else."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def only_tested():\n    return 1\n",
            "src/app/hooks/guard.sh": _HOOK,
        },
    )
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    assert orphan_modules(graph) == ["src/app/helpers.py"]
    assert orphan_modules(graph, None, census(repo)) == []


# ─── orphan modules ────────────────────────────────────────────────────────────


def test_a_module_nothing_imports_is_an_orphan(tmp_path):
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/used.py": "",
            "src/app/caller.py": "from app import used\n",
            "src/app/stranded.py": "",
        },
    )
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    assert orphan_modules(graph) == ["src/app/caller.py", "src/app/stranded.py"]


def test_a_declared_entry_point_is_not_an_orphan(tmp_path):
    """`cli.py` and `__init__.py` are where a process starts, not modules nothing reached."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/cli.py": "",
            "src/app/__main__.py": "",
            "src/app/stranded.py": "",
        },
    )
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    assert orphan_modules(graph) == ["src/app/stranded.py"]


def test_an_authored_entry_point_pattern_clears_a_module(tmp_path):
    """The repo-specific half of the list is a declaration, which is the point of it."""
    repo = _tree(tmp_path, {"src/app/__init__.py": "", "src/app/daemon.py": ""})
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    assert orphan_modules(graph) == ["src/app/daemon.py"]
    policy = DeadEndPolicy(entry_points=("**/__init__.py", "**/daemon.py"))
    assert orphan_modules(graph, policy) == []


# ─── the finding text and the policy block ─────────────────────────────────────


def test_findings_state_what_was_measured_not_a_verdict(tmp_path):
    """Same discipline as an uncalled route: the sentence names the tree it searched."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def only_tested():\n    return 1\n",
            "src/app/dispatch.py": "def call(obj, name):\n    return getattr(obj, name)\n",
            "tests/test_helpers.py": "from app.helpers import only_tested\n",
        },
    )
    found = deadend_findings(test_only_symbols(repo))
    design = [item for item in found if item.category == DESIGN]
    limits = [item for item in found if item.category == UNDERSTANDING]
    assert len(design) == 1
    assert "no scanned source module references" in design[0].description
    assert design[0].artifacts == ("src/app/helpers.py",)
    assert limits and limits[0].description.startswith("Limit of the census's reach:")
    assert not any("dead code" in item.description for item in found)
    assert not any("unused" in item.description for item in found)


def test_a_disabled_channel_scans_nothing(tmp_path):
    """Disabled is an empty report, not a partial one — the same shape `routes` uses."""
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/helpers.py": "def only_tested():\n    return 1\n",
            "tests/test_helpers.py": "from app.helpers import only_tested\n",
        },
    )
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    assert scan(repo, graph).test_only == []
    enabled = scan(repo, graph, DeadEndPolicy(enabled=True))
    assert _names(enabled) == ["only_tested"]
    assert enabled.orphans == ["src/app/helpers.py"]


def test_the_policy_digest_moves_with_the_declared_block():
    """A number always travels with the rules that produced it."""
    base = DeadEndPolicy()
    assert base.digest() == DeadEndPolicy().digest()
    assert dataclasses.replace(base, report_unreferenced=True).digest() != base.digest()
    widened = dataclasses.replace(base, entry_points=(*base.entry_points, "**/daemon.py"))
    assert widened.digest() != base.digest()


def test_a_policy_round_trips_through_its_block():
    """`arch/model.yaml` is the authoring surface, so the block must rebuild the policy."""
    policy = DeadEndPolicy(
        enabled=True,
        entry_points=("**/cli.py",),
        report_unreferenced=True,
        exemptions=(
            Exemption(reason="the packaging entry point calls it", path="src/a.py", symbol="go"),
        ),
    )
    rebuilt = DeadEndPolicy.from_block(policy.block())
    assert rebuilt == policy
    assert rebuilt.digest() == policy.digest()


def test_a_block_exemption_without_a_reason_is_refused():
    """The file is where the reason is authored, so a blank one fails at load."""
    with pytest.raises(ValueError):
        DeadEndPolicy.from_block({"exemptions": [{"path": "src/a.py", "symbol": "go"}]})


# ─── the detector's own ground truth ───────────────────────────────────────────


def test_one_tree_sorts_every_definition_into_the_bucket_that_describes_it(tmp_path):
    """Five definitions of five kinds, and the census has to tell them apart.

    The outcomes are each other's failure modes: a silenced symbol reported is a false
    accusation, a test-only symbol silenced is the finding the whole channel exists
    for, and an exemption that swallows more than its own row turns the check off
    without saying so. Asserting them one at a time cannot catch a rule that fires on
    the wrong row, because each case would still pass alone — so they are declared in
    one tree and the whole classification is compared at once.

    `hook_reached` and `inlined` are the pair `role-guard.sh` actually presents: one
    name the guard imports and calls from a heredoc, and one it names in a comment to
    record that the literals were copy-pasted *instead* of calling it. A text match
    cannot separate them, and counting either would silence a true finding.
    """
    repo = _tree(
        tmp_path,
        {
            "src/app/__init__.py": "from app.caller import VALUE\n",
            "src/app/helpers.py": (
                "def called_in_production():\n    return 1\n\n\n"
                "def only_tested():\n    return 2\n\n\n"
                "def hook_reached():\n    return 3\n\n\n"
                "def inlined():\n    return 4\n\n\n"
                "def excused():\n    return 5\n"
            ),
            "src/app/caller.py": (
                "from app.helpers import called_in_production\n\n"
                "VALUE = called_in_production()\n"
            ),
            "src/app/orphan.py": "CONSTANT = 1\n",
            "src/app/hooks/guard.sh": (
                "#!/bin/bash\n"
                "# Markers are inlined from helpers.inlined() rather than called, because\n"
                "# the interpreter that would compute them is what just failed.\n"
                'result=$("$py" - ' + _HEREDOC_OPEN + " 2>/dev/null || true\n"
                "from app.helpers import hook_reached\n"
                "print(hook_reached())\n"
                "PY\n"
                ")\n"
            ),
            "tests/test_helpers.py": (
                "from app.helpers import called_in_production, excused, hook_reached\n"
                "from app.helpers import inlined, only_tested\n"
            ),
        },
    )
    policy = DeadEndPolicy(
        enabled=True,
        entry_points=("**/__init__.py",),
        exemptions=(
            Exemption(
                reason="the packaging entry point calls it",
                path="src/app/helpers.py",
                symbol="excused",
            ),
        ),
    )
    graph = scan_repo(repo, ExtractorPolicy(roots=("src",)))
    report = scan(repo, graph, policy)

    assert sorted(_names(report)) == ["inlined", "only_tested"]
    assert [(item.definition.name, item.form) for item in report.silenced] == [
        ("hook_reached", SILENCE_EMBEDDED)
    ]
    assert [(item.definition.name, item.rule, item.detail) for item in report.exempted] == [
        ("excused", RULE_DECLARED, "the packaging entry point calls it")
    ]
    assert report.orphans == ["src/app/orphan.py"]
    # The comment naming `inlined()` is attached to that finding as a limit, so the one
    # line that could refute it is pointed at rather than counted as a call.
    assert any("`inlined` occurs as a word in" in note for note in report.limits)


# ─── against this checkout ─────────────────────────────────────────────────────


@pytest.mark.skipif(not (REPO_ROOT / "tests").is_dir(), reason="needs a full checkout")
def test_every_declared_exemption_still_matches_a_definition():
    """A shipped exemption names a definition that exists and that nothing outside the
    test roots reaches. Both halves rot: the symbol is deleted, or a caller lands and
    the entry stops describing anything.

    Stated over whatever the model declares rather than over a list of names, so it
    keeps holding as entries are added and removed — which is the property the
    hand-listed symbol set it replaces did not have.
    """
    import yaml

    from thalamus.arch import model as arch_model

    document = yaml.safe_load((REPO_ROOT / arch_model.MODEL_PATH).read_text(encoding="utf-8"))
    policy = DeadEndPolicy.from_block(document.get("deadends") or {})
    report = test_only_symbols(REPO_ROOT, policy)
    matched = {
        (item.definition.path, item.definition.qualname)
        for item in report.exempted
        if item.rule == RULE_DECLARED
    }
    unmatched = [
        (entry.path, entry.symbol)
        for entry in policy.exemptions
        if (entry.path, entry.symbol) not in matched
    ]
    assert unmatched == []


@pytest.mark.skipif(not (REPO_ROOT / "tests").is_dir(), reason="needs a full checkout")
def test_the_contract_symbols_the_role_guard_calls_are_reached_not_reported():
    """`role-guard.sh` runs on every Edit and Write in every session on this checkout.

    It reaches four contract symbols from `"$py" - <<PY` heredocs, and no `.py` module
    imports any of them. Reporting them would be the false accusation the route channel
    refuses to make about an uncalled route.
    """
    report = test_only_symbols(REPO_ROOT)
    reached = {
        (item.definition.path, item.definition.name): item for item in report.silenced
    }
    for path, name in (
        ("src/thalamus/contract/ownership.py", "denies"),
        ("src/thalamus/contract/manifest.py", "denies"),
        ("src/thalamus/contract/manifest.py", "denies_skill"),
        ("src/thalamus/contract/manifest.py", "denies_tool"),
    ):
        silenced = reached[(path, name)]
        assert silenced.form == SILENCE_EMBEDDED
        assert all("role-guard.sh:" in site for site in silenced.sites)
    assert {name for _, name in reached} .isdisjoint({item.name for item in report.test_only})


@pytest.mark.skipif(not (REPO_ROOT / "tests").is_dir(), reason="needs a full checkout")
def test_the_module_the_role_guard_imports_is_not_an_orphan():
    """`contract/ownership.py` is imported by `role-guard.sh` and by no scanned module."""
    walked = census(REPO_ROOT)
    graph = scan_repo(REPO_ROOT, ExtractorPolicy(roots=("src",)))
    assert "src/thalamus/contract/ownership.py" in orphan_modules(graph)
    assert "src/thalamus/contract/ownership.py" not in orphan_modules(graph, None, walked)


@pytest.mark.skipif(not (REPO_ROOT / "tests").is_dir(), reason="needs a full checkout")
def test_the_framework_dispatched_symbols_are_excused_rather_than_reported():
    """The false-positive class: names whose caller is a registry, a protocol or a base.

    `pulse/web.py`'s `health` is not in the exempted list either — it is defined inside
    the app factory, so it is a local binding the census never enters. It is checked
    here because it must not be *reported*, and that is what is asserted.
    """
    report = test_only_symbols(REPO_ROOT, DeadEndPolicy(report_unreferenced=True))
    reported = {item.name for item in [*report.test_only, *report.unreferenced]}
    assert reported.isdisjoint(
        {"memory_recall", "memory_open_threads", "health", "do_GET", "do_POST", "log_message"}
    )

    by_rule = {
        (item.definition.path, item.definition.name): item.rule for item in report.exempted
    }
    assert by_rule[("src/thalamus/harness/mcp_server.py", "memory_recall")] == RULE_DECORATOR
    assert by_rule[("src/thalamus/harness/mcp_server.py", "memory_open_threads")] == RULE_DECORATOR
    assert by_rule[("src/thalamus/console/server.py", "do_GET")] == RULE_OVERRIDE
    assert by_rule[("src/thalamus/console/server.py", "do_POST")] == RULE_OVERRIDE
    assert by_rule[("src/thalamus/console/server.py", "log_message")] == RULE_OVERRIDE
