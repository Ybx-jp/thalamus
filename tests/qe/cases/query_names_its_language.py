"""`memory_query` must tell the server which language its text is in.

Corpus record: issue #382. `run_query` submitted the caller's text with no
`language` request option, so Gremlin Server evaluated it with its default engine,
gremlin-groovy. `g.inject(1).map{ it.get() + 1 }` returned `[2]` and
`g.inject(1); 6 * 7` returned `[42]` against the 3.7.3 server, and both passed
`validate_query` — the module docstring's claim that the server's parser rejects
closures was never true of this surface. The fix names `gremlin-lang` on every
submission (`LANGUAGE`), so the parse-time grammar is the sandbox rather than the
Groovy evaluator.

Hermetic: the connection `run_query` opens is replaced by a recorder, so the
assertion is on the request that would have been sent. The recorded submission is
also the control — a recorder that was never called would make "no Groovy option
seen" pass vacuously, so the case requires exactly one submission per accepted
query, for the main pin and for a pinned scope, and none for the two probes above.
"""

from __future__ import annotations

from thalamus.substrate import query as query_mod

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SITE = "src/thalamus/substrate/query.py::run_query"
_URL = "ws://localhost:9/gremlin"


class _Recorder:
    submitted: list[tuple[str, dict]] = []

    def __init__(self, *_a, **_k):
        pass

    def submit(self, text, request_options=None):
        _Recorder.submitted.append((text, dict(request_options or {})))

        class _Result:
            def all(self):
                class _Future:
                    def result(self):
                        return [1]

                return _Future()

        return _Result()

    def close(self):
        pass


def run() -> Finding | None:
    original = query_mod.Client
    problems: list[str] = []
    try:
        query_mod.Client = _Recorder
        for label, confine_to in (
            ("main", None),
            ("pinned", ("some-other-expert", ["literature"])),
        ):
            _Recorder.submitted = []
            query_mod.run_query(_URL, "g.V().count()", confine_to)
            if len(_Recorder.submitted) != 1:
                problems.append(
                    f"{label}: an accepted query was submitted "
                    f"{len(_Recorder.submitted)} times, want 1 (control)"
                )
                continue
            language = _Recorder.submitted[0][1].get("language")
            if language != "gremlin-lang":
                problems.append(f"{label}: request language was {language!r}")

        # The two probes #382 measured as running on the server. Neither may be
        # submitted at all.
        for probe in ("g.inject(1).map{ it.get() + 1 }", "g.inject(1); 6 * 7"):
            _Recorder.submitted = []
            out = query_mod.run_query(_URL, probe)
            if _Recorder.submitted or not out.startswith("Rejected:"):
                problems.append(f"{probe!r} reached the server or was not refused: {out!r}")
    finally:
        query_mod.Client = original

    if not problems:
        return None
    return Finding(
        failure_class=FailureClass.FAILED_OPEN,
        summary=(
            "memory_query submits its text without naming gremlin-lang, so the "
            "server evaluates it as a Groovy script — closures and a second "
            "statement run"
        ),
        witness="; ".join(problems),
        site=_SITE,
    )


CASE = Case(
    name="query-submission-names-gremlin-lang",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.FAILED_OPEN,),
    summary="every memory_query submission carries language=gremlin-lang, and the "
            "two Groovy probes from #382 are refused before submission",
    run=run,
    issue=382,
    fixed=True,
)
