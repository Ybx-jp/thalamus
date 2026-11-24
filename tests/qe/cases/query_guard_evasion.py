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

Layered by design. The module's docstring names four layers: (1) every submission
names `language: gremlin-lang`, (2) the traversal source is the server's — the
caller's leading `g` becomes `g.withStrategies(ReadOnlyStrategy[, SubgraphStrategy])`,
(3) `validate_query` keeps layer 2 standing, and (4) caps. Layer 1 once rested on a
claim that the server's parser rejects closures ("measured: `sideEffect{...}` fails");
that was false for this surface, because the request named no language and Gremlin
Server evaluated the text as Groovy (#382). So no layer is assumed to catch what
another misses: this case holds `validate_query` to rejecting closures, `;`, a second
traversal root and the three source steps (`withStrategies(`, `withoutStrategies(`,
`withComputer(`) on its own, and drives the pin gate with a recording stand-in for the
server connection to check that what is submitted carries the confinement built from
the pin. Everything here is hermetic: no server is contacted.

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
that already work shows up beside the parts that do not. `inject()` alone, a
denylist word sitting in a string *value* (not a call), and non-ASCII text
inside a string value (Latin-1 and CJK) are ACCEPTED assertions — discrimination
controls: a guard that rejects everything would pass every REJECTED assertion
above and reveal nothing, so these must stay accepted for the REJECTED
assertions to mean anything. The non-ASCII-in-literal pair specifically pins
`_lexical_floor`'s deliberate exemption of string literals from its non-ASCII
refusal — without it this case cannot distinguish "correctly strict" from
"rejects everything non-ASCII, literal or not". A last well-formed, multi-clause
traversal is the benign-input control the whole case would be unfalsifiable
without: "everything was rejected" and "the mutations were rejected" render
identically unless at least one legitimate read passes. One further REJECTED
control pins `_lexical_floor`'s own named uncertainty about its hand-rolled
literal scanner: a literal ending in an escaped trailing backslash, followed
immediately by a homoglyph outside it, must still see the homoglyph as code —
a scanner that mis-tracks the escape and leaves the literal open would instead
swallow the homoglyph as string data and accept the query.
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
    # Closures, a statement separator, a second root and the source steps: the
    # server evaluated all of them as Groovy before the request named gremlin-lang
    # (#382), and a second withStrategies replaces the source the server builds.
    # None may reach the server from the caller.
    ("closure: map{...}", "g.inject(1).map{ it.get() + 1 }", True),
    ("closure: sideEffect{...}", "g.V().sideEffect{ it.get() }", True),
    ("closure: by{...}", "g.V().order().by{ it.id() }", True),
    ("closure: lone braces", "g.V().has('a', {})", True),
    ("statement separator: second statement", "g.inject(1); 6 * 7", True),
    ("statement separator: trailing", "g.V().count();", True),
    ("second root: after a space", "g.V().count() g.V()", True),
    ("second root: inside a child traversal", "g.V().where(g.V())", True),
    ("second root: as an argument", "g.inject(g.V())", True),
    ("source step: withStrategies", "g.withStrategies(ReadOnlyStrategy).V()", True),
    ("source step: second SubgraphStrategy",
     "g.V().withStrategies(new SubgraphStrategy(vertices: __.identity()))", True),
    ("source step: case variation WITHSTRATEGIES", "g.V().WITHSTRATEGIES(x)", True),
    ("source step: whitespace before paren", "g.V().withStrategies (x)", True),
    ("source step: withoutStrategies", "g.withoutStrategies(ReadOnlyStrategy).V()", True),
    ("source step: withComputer", "g.withComputer().V()", True),
    # Controls for the above: each must stay ACCEPTED, or the closure / `;` / `g`
    # rejections are indistinguishable from "rejects anything containing a g".
    ("control: 'g', ';' and braces inside a string literal",
     "g.V().has('title', 'g; {x} g')", False),
    ("control: g as an alias label", "g.V().as('g').select('g')", False),
    ("control: g inside longer identifiers",
     "g.V().has('agent', 'x').out('GOVERNS').group().by(label)", False),
    ("control: groupCount / gt step names",
     "g.V().groupCount().by('kind').unfold().where(__.select(values).is(P.gt(1)))",
     False),
    ("control: map literal uses brackets", "g.inject([a:1]).select('a')", False),
    # Controls — must stay ACCEPTED, or every REJECTED assertion above is
    # unfalsifiable (see guard_failopen.py's own note on this, tests/qe/README.md).
    ("control: inject() alone is not a mutation", "g.inject(1,2,3)", False),
    ("control: denylist word inside a string value, not a call",
     "g.V().has('title','call addV now').valueMap()", False),
    ("control: benign well-formed traversal",
     "g.V().hasLabel('Thread').has('scope','main').has('status','open')"
     ".valueMap('title')", False),
    # #174's fix exempts string literals from the non-ASCII rule on purpose — the
    # graph holds text in any script, and a query searching for it is ordinary.
    # Without a control here, this case cannot tell "correctly strict" (rejects
    # only hostile input) from "rejects everything" (also correctly rejects the
    # hostile corpus above, but for the wrong reason). Two scripts, so a
    # single-script coincidence isn't doing the work.
    ("control: non-ASCII inside a string value (Latin-1 supplement)",
     "g.V().has('title','Café')", False),
    ("control: non-ASCII inside a string value (CJK)",
     "g.V().hasLabel('Thread').has('title','日本語のタイトル')", False),
    # `_lexical_floor`'s own docstring names its hand-rolled literal scanner's
    # backslash handling as the one place it could disagree with the real
    # gremlin-lang parser. This pins the scanner's actual behavior at that
    # boundary: a literal ending in an escaped trailing backslash (`'a\\'`) must
    # still close on the following quote, so the Cyrillic homoglyph sitting right
    # after it is scanned as code — outside the literal — and rejected. A scanner
    # that mis-tracks the escape and treats the backslash as leaving the string
    # open would instead swallow the homoglyph as string data and accept the
    # query, which is the bypass this pins against.
    ("control: escaped trailing backslash in a literal, "
     "then a homoglyph outside it",
     "g.V().has('a\\\\', аddV('X'))", True),
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

    # The pin gate — hermetic: the connection `run_query` opens is replaced by a
    # recorder, so nothing is contacted and the outcome does not depend on what is
    # on :8182. What is under test is what a pin causes to be submitted.
    original_url = mcp_server.GRAPH_URL
    original_scope = mcp_server.SCOPE
    original_conn = query_mod.Client
    scope_gate_failures: list[str] = []

    class _Recorder:
        submitted: list[tuple[str, dict]] = []

        def __init__(self, *_a, **_k):
            pass

        def submit(self, text, request_options=None):
            _Recorder.submitted.append((text, dict(request_options or {})))

            class _RS:
                def all(self):
                    class _F:
                        def result(self):
                            return [1]

                    return _F()

            return _RS()

        def close(self):
            pass

    try:
        mcp_server.GRAPH_URL = "ws://localhost:9/gremlin"
        query_mod.Client = _Recorder
        benign = "g.V().hasLabel('Thread').valueMap('title')"

        pin = "some-other-expert"
        mcp_server.SCOPE = pin
        _Recorder.submitted = []
        pinned_out = mcp_server.memory_query(benign)
        if "master-plane instrument" in pinned_out or len(_Recorder.submitted) != 1:
            scope_gate_failures.append(
                f"SCOPE={pin!r} was refused or did not reach the server once: "
                f"{pinned_out!r}, submitted={len(_Recorder.submitted)}"
            )
        else:
            text, opts = _Recorder.submitted[0]
            knowledge = mcp_server.knowledge_scopes()
            if opts.get("language") != "gremlin-lang":
                scope_gate_failures.append(f"pinned call named language {opts.get('language')!r}")
            if not text.startswith("g.withStrategies(ReadOnlyStrategy, new SubgraphStrategy("):
                scope_gate_failures.append(f"pinned call carries no confining source: {text!r}")
            if text != query_mod.traversal_source((pin, knowledge)) + benign[1:]:
                scope_gate_failures.append(
                    f"pinned call's source is not the one built from the pin and the "
                    f"knowledge scopes {knowledge}: {text!r}"
                )
            if f"has('scope', '{pin}')" not in text:
                scope_gate_failures.append(f"pinned call's source does not name {pin!r}")
            for other in knowledge:
                if other != pin and f"'{other}'" not in text:
                    scope_gate_failures.append(
                        f"pinned call's source omits knowledge scope {other!r}"
                    )

        mcp_server.SCOPE = MAIN_SCOPE
        _Recorder.submitted = []
        main_out = mcp_server.memory_query(benign)
        if "master-plane instrument" in main_out or len(_Recorder.submitted) != 1:
            scope_gate_failures.append(
                f"SCOPE=MAIN_SCOPE was refused or did not reach the server once: {main_out!r}"
            )
        else:
            text, opts = _Recorder.submitted[0]
            if opts.get("language") != "gremlin-lang":
                scope_gate_failures.append(f"main call named language {opts.get('language')!r}")
            if "SubgraphStrategy" in text or not text.startswith(
                "g.withStrategies(ReadOnlyStrategy)"
            ):
                scope_gate_failures.append(
                    f"main call must be read-only and unconfined: {text!r}"
                )

        # A pinned caller cannot lift its own confinement: the attempt is refused
        # before anything is submitted.
        mcp_server.SCOPE = pin
        _Recorder.submitted = []
        lifted = mcp_server.memory_query(
            "g.V().withStrategies(new SubgraphStrategy(vertices: __.identity())).count()"
        )
        if _Recorder.submitted or not lifted.startswith("Rejected:"):
            scope_gate_failures.append(
                f"a pinned call replacing the source reached the server: {lifted!r}"
            )
    finally:
        mcp_server.GRAPH_URL = original_url
        mcp_server.SCOPE = original_scope
        query_mod.Client = original_conn

    if scope_gate_failures:
        return Finding(
            failure_class=FailureClass.BOUNDARY_LEAK,
            summary=(
                "memory_query's pin confinement does not behave as documented: a "
                "non-main pin must reach the server only on a source confined to "
                "what its scope may read, the main pin on an unconfined read-only "
                "one, and one of the two did not hold"
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
    # validate_query's denylist used to be a literal substring match over a
    # whitespace-stripped, lowercased view; comment injection, a zero-width
    # space, a Unicode homoglyph, and a fullwidth paren each defeated it
    # generically, for every denied step. `_lexical_floor` now refuses a comment,
    # a backslash, or any non-ASCII character outside a string literal ahead of
    # the denylist, which closes all four techniques at once. See issue #174.
    issue=174,
    fixed=True,
)
