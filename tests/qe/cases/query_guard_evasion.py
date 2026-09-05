"""`memory_query`'s free-form Gremlin is guarded only statically — feed it a corpus
built to defeat the guard, not to satisfy it.

Corpus record: issue #75. `tests/test_query.py` (dev's in-loop suite) exercises
`validate_query` over input shaped the way the guard's author expected: case
variation, `union(__.addV(...))`, nested calls. That is real coverage, and it is
not adversarial — every "bad" string it tries is one the substring check was
written to catch. Nothing anywhere tries to spell a denied step so the substring
check misses it while a real Gremlin engine would not, which is the sharper
question `substrate/query.py`'s own docstring invites by naming its guard's
mechanism explicitly: "denying these step names (as called tokens) is denying
the write path... against a whitespace-stripped lowercase view."

Layered by design, and only one layer is testable here. The module's docstring
names three: (1) the server's `GremlinLangScriptEngine` parser, which rejects
closures and arbitrary code — "measured: `sideEffect{...}` fails with a token
recognition error" — and that measurement is why bare closure forms
(`sideEffect{...}`, `.by{...}`) are not asserted against below: their rejection is
already documented as layer 1's job, not this function's, and asserting either
way here would encode a decision the guard's author did not make. (2) is
`validate_query` itself — a pure function over a string, hence hermetic, and the
one this case targets. (3) is the pin gate (`SCOPE == MAIN_SCOPE`), also pure and
also covered below. Layer 1 needs a live `GremlinLangScriptEngine`, which is the
seam issue #60 would provide a redirect for; until then a bypass found here is
reported as a bypass of *this* layer, which is real regardless of whether layer 1
would also catch the same string — defense in depth means each layer holds on its
own, and `validate_query`'s docstring claims exactly that for itself.

**Generated half.** `_STEP_TEMPLATES` holds one realistic gremlin-lang traversal
per entry in `validate_query`'s own `_DENIED_STEPS`, and a coverage check below
fails if the two ever disagree — a step added to the denylist without a template
here is a gap, not a silent pass. Four techniques (comment injection, a
zero-width space, a Unicode homoglyph, and a fullwidth paren) are applied
generically to every templated step, because none of the three relies on
whitespace: `validate_query` strips `\\s+` before matching, so only techniques
that survive that strip are worth generating.

**Hand-written half.** Case variation, whitespace injection, chained/aliased
steps, and an anonymous-traversal wrapper are included as REJECTED assertions —
already-mitigated techniques, kept here so a regression in the parts of the guard
that already work shows up beside the parts that do not. `inject()` alone and a
denylist word sitting in a string *value* (not a call) are ACCEPTED assertions —
the discrimination controls: a guard that rejects everything would pass every
REJECTED assertion above and reveal nothing, so these two must stay accepted for
the REJECTED assertions to mean anything. A last well-formed, multi-clause
traversal is the benign-input control the whole case would be unfalsifiable
without: "everything was rejected" and "the mutations were rejected" render
identically unless at least one legitimate read passes.
"""

from __future__ import annotations

from thalamus.substrate import query as query_mod
from thalamus.substrate.query import validate_query

from ..model import Case, FailureClass, Finding, Substrate, Tier

# One realistic gremlin-lang traversal per denied step, as (display_spelling,
# full_query). `display_spelling` is the exact substring the query contains for
# that step — techniques below locate and split it — capitalized the way a real
# Gremlin author would write it, never the guard's own lowercased view.
_STEP_TEMPLATES: dict[str, tuple[str, str]] = {
    "addv(": ("addV(", "g.addV('Claim')"),
    "adde(": ("addE(", "g.V().addE('DERIVED_FROM')"),
    "mergev(": ("mergeV(", "g.mergeV([:])"),
    "mergee(": ("mergeE(", "g.V().mergeE([:])"),
    "drop(": ("drop(", "g.V().has('a','b').drop()"),
    "property(": ("property(", "g.V().property('tier', 0)"),
    "sideeffect(": ("sideEffect(", "g.V().sideEffect(__.identity())"),
    "io(": ("io(", "g.io('/tmp/x').read()"),
    "call(": ("call(", "g.call('x')"),
    "program(": ("program(", "g.V().program()"),
}

# A handful of Latin/Cyrillic confusable pairs, enough that every template above
# contains at least one substitutable character.
_HOMOGLYPHS: dict[str, str] = {
    "a": "а", "A": "А", "e": "е", "E": "Е", "o": "о", "O": "О",
    "p": "р", "P": "Р", "c": "с", "C": "С", "y": "у", "x": "х",
    "i": "і", "I": "І",
}


def _split_insert(query: str, display: str, marker: str) -> str | None:
    """`display`'s first char, `marker`, then the rest — the first occurrence only."""
    if display not in query or len(display) < 2:
        return None
    obfuscated = display[0] + marker + display[1:]
    return query.replace(display, obfuscated, 1)


def _apply_comment(query: str, display: str) -> str | None:
    """A block comment mid-token. Not whitespace, so `\\s+` never strips it."""
    return _split_insert(query, display, "/**/")


def _apply_zwsp(query: str, display: str) -> str | None:
    """U+200B — invisible, and Unicode's own tables mark it White_Space=No, so it
    survives the guard's whitespace strip untouched."""
    return _split_insert(query, display, "​")


def _apply_homoglyph(query: str, display: str) -> str | None:
    """One Latin letter in `display` swapped for its Cyrillic look-alike."""
    for i, ch in enumerate(display):
        if ch in _HOMOGLYPHS:
            obfuscated = display[:i] + _HOMOGLYPHS[ch] + display[i + 1:]
            return query.replace(display, obfuscated, 1)
    return None


def _apply_fullwidth_paren(query: str, display: str) -> str | None:
    """The literal ASCII `(` the denylist requires immediately after the step name,
    swapped for U+FF08 FULLWIDTH LEFT PARENTHESIS."""
    if not display.endswith("("):
        return None
    obfuscated = display[:-1] + "（"
    return query.replace(display, obfuscated, 1)


_TECHNIQUES = {
    "comment-injection": _apply_comment,
    "zero-width-space": _apply_zwsp,
    "unicode-homoglyph": _apply_homoglyph,
    "fullwidth-paren": _apply_fullwidth_paren,
}

# (label, query, expect_rejected). Hand-written: techniques the guard already
# mitigates (kept as regression pins), plus the discrimination and benign
# controls the REJECTED assertions above are unfalsifiable without.
_HAND_CORPUS: tuple[tuple[str, str, bool], ...] = (
    ("case-variation: upper ADDV", "g.V().ADDV('x')", True),
    ("case-variation: mixed MeRgEv", "g.V().MeRgEv([:])", True),
    ("whitespace-injection: tab inside addV", "g.V().add\tV('x')", True),
    ("whitespace-injection: newline inside addV", "g.V().add\nV('x')", True),
    ("chained-alias: bind then drop through the alias",
     "g.V().as('a').select('a').drop()", True),
    ("wrapped-in-anonymous: coalesce(__.addV(...), __.identity())",
     "g.V().coalesce(__.addV('x'), __.identity())", True),
    # Controls — must stay ACCEPTED, or every REJECTED assertion above is
    # unfalsifiable (see guard_failopen.py's own note on this, tests/qe/README.md).
    ("control: inject() alone is not a mutation", "g.inject(1,2,3)", False),
    ("control: denylist word inside a string value, not a call",
     "g.V().has('title','call addV now').valueMap()", False),
    ("control: benign well-formed traversal",
     "g.V().hasLabel('Thread').has('scope','main').has('status','open')"
     ".valueMap('title')", False),
)


def _generated_corpus() -> list[tuple[str, str]]:
    corpus: list[tuple[str, str]] = []
    for token, (display, base_query) in _STEP_TEMPLATES.items():
        for technique_name, apply in _TECHNIQUES.items():
            obfuscated = apply(base_query, display)
            if obfuscated is not None and obfuscated != base_query:
                corpus.append((f"{token} via {technique_name}", obfuscated))
    return corpus


def run() -> Finding | None:
    from thalamus.contract.ontology import MAIN_SCOPE  # noqa: PLC0415
    from thalamus.harness import mcp_server  # noqa: PLC0415

    denied = set(query_mod._DENIED_STEPS)  # noqa: SLF001
    templated = set(_STEP_TEMPLATES)
    if denied != templated:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "the denylist in substrate/query.py and this case's evasion "
                "templates disagree, so a step added there without a template "
                "here is swept for nothing"
            ),
            witness=f"denylist-only={sorted(denied - templated)}, "
                    f"corpus-only={sorted(templated - denied)}",
            site="src/thalamus/substrate/query.py::_DENIED_STEPS",
        )

    generated = _generated_corpus()
    if len(generated) < len(_STEP_TEMPLATES):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "at least one denied step produced no evasion variant at all, so "
                "the generated sweep covers fewer steps than it claims to"
            ),
            witness=f"generated {len(generated)} variants over "
                    f"{len(_STEP_TEMPLATES)} templated steps",
            site=__file__,
        )

    bypasses: list[str] = []
    control_failures: list[str] = []

    for label, q in generated:
        if validate_query(q) is None:
            bypasses.append(f"{label}: {q!r}")

    for label, q, expect_rejected in _HAND_CORPUS:
        rejected = validate_query(q) is not None
        if expect_rejected and not rejected:
            bypasses.append(f"{label}: {q!r}")
        elif not expect_rejected and rejected:
            control_failures.append(
                f"{label}: {q!r} was rejected — {validate_query(q)}"
            )

    if control_failures:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "a control the REJECTED assertions depend on failed: either a "
                "benign traversal was refused, or a denylist word sitting in "
                "string data (not a call) was refused. Either way, a guard that "
                "rejects more than it should makes the REJECTED assertions above "
                "unfalsifiable — they would pass even if the guard blocked "
                "everything"
            ),
            witness="; ".join(control_failures),
            site="src/thalamus/substrate/query.py::validate_query",
        )

    # The scope gate — pure and hermetic, same as validate_query. GRAPH_URL is
    # pinned dead so the outcome does not depend on whether this box happens to
    # have a graph on :8182; only the gate's own branch is under test.
    original_url = mcp_server.GRAPH_URL
    original_scope = mcp_server.SCOPE
    scope_gate_failures: list[str] = []
    try:
        mcp_server.GRAPH_URL = "ws://localhost:9/gremlin"
        benign = "g.V().hasLabel('Thread').valueMap('title')"

        mcp_server.SCOPE = "some-other-expert"
        refused = mcp_server.memory_query(benign)
        if "master-plane instrument" not in refused:
            scope_gate_failures.append(
                f"SCOPE='some-other-expert' did not refuse a traversal: {refused!r}"
            )

        mcp_server.SCOPE = MAIN_SCOPE
        allowed = mcp_server.memory_query(benign)
        if "master-plane instrument" in allowed:
            scope_gate_failures.append(
                f"SCOPE=MAIN_SCOPE still refused a benign traversal: {allowed!r}"
            )
    finally:
        mcp_server.GRAPH_URL = original_url
        mcp_server.SCOPE = original_scope

    if scope_gate_failures:
        return Finding(
            failure_class=FailureClass.BOUNDARY_LEAK,
            summary=(
                "memory_query's scope gate does not behave as documented: a "
                "non-main pin must be refused and the main pin must not be, and "
                "one of the two did not hold"
            ),
            witness="; ".join(scope_gate_failures),
            site="src/thalamus/harness/mcp_server.py::memory_query",
        )

    if not bypasses:
        return None

    return Finding(
        failure_class=FailureClass.FAILED_OPEN,
        summary=(
            "a hostile Gremlin string got a denied mutation step past "
            "validate_query's lexical guard, which enforces read-only by "
            "denylisting step names as literal, whitespace-stripped, lowercased "
            "substrings — a match technique that a non-whitespace character "
            "inserted mid-token defeats generically, independent of which step"
        ),
        witness="; ".join(sorted(bypasses)),
        site="src/thalamus/substrate/query.py::validate_query",
    )


CASE = Case(
    name="query-guard-evasion-corpus",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(
        FailureClass.FAILED_OPEN,
        FailureClass.BOUNDARY_LEAK,
        FailureClass.COLLAPSED_SENTINEL,
    ),
    summary=(
        "memory_query's lexical guard and scope gate, fed a corpus built to "
        "defeat rather than satisfy them"
    ),
    run=run,
    # validate_query's denylist is a literal substring match over a
    # whitespace-stripped, lowercased view; comment injection, a zero-width
    # space, a Unicode homoglyph, and a fullwidth paren each defeat it generically,
    # for every denied step. Filed rather than fixed — this scope may not write
    # src/. See issue #174.
    issue=174,
    fixed=False,
)
