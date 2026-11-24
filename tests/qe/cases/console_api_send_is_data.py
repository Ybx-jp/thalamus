"""`POST /api/send` types arbitrary printable text verbatim, and typing is concatenative.

The send route's contract is that the composer's text is *data*: whatever string the
operator types arrives in the pane unchanged. `console_send_text_is_data_not_argv` pins
the argv-parsing hazards (leading `-`, trailing `;`) with a stubbed tmux and a handful of
literals; this case drives the real server and a real tmux in `_console_rig`, with text
Hypothesis generates, into a window running `cat` (whose tty echoes what it receives).

**Property 1, verbatim.** For generated printable text `t`, `POST /api/send {"index": i,
"text": t, "submit": false}` after a fresh line leaves the pane's last line equal to `t`
(`capture-pane -p -J`, wrapped lines joined).

**Property 2, concatenative (metamorphic).** `send(a); send(b)` and `send(a + b)` leave
the same last line, and it is `a + b`. This is the relation that catches a transform that
is applied per call — an escape that fires at the end of a string (`;`), at its start
(`-`), or on a boundary the second call does not have.

**The alphabet, and what it excludes.** ASCII printable (space included), Latin-1 letters
and symbols, and Greek and Cyrillic. Deliberately excluded, because they would measure
tmux's capture rather than the route:

- wide characters (CJK, emoji) and combining marks — a two-cell glyph at a wrap boundary
  and a zero-width mark are rendered in cells, and `capture-pane` does not return the
  codepoints that were typed;
- any text that ends in a space — `capture-pane` trims trailing cells, so the typed
  trailing space is not recoverable (leading and interior spaces are kept);
- control characters, including `\\n` and `\\r` — they are not data to the tty, and are
  the subject of `console_api_send_control_bytes`;
- NUL and lone surrogates — an unhandled crash in the route, found by
  `console_api_post_fuzz`; text up to 90 characters, so a line wraps at the pane's 60
  columns and `-J` is exercised.

The text may start with `-` or end with `;` — those are in the alphabet on purpose.

**Controls.** (a) The fixture lands text: a known-good send of `qe-control-ok` appears in
the capture. (b) The comparison can tell wrong from right: the same capture compared with
`t + "x"` must be unequal. (c) A window that does not exist is refused (400), so a send
that "lands" cannot be a send to anywhere.

**Shown capable of going red.** In a copy of the console tree (`QE_CONSOLE_SRC`), make
`literal_text_args` return `("--", text)` without `-l` (key names are then parsed out of the
text) or drop the `;` escape: a generated text such as `Enter` or one ending in `;` no
longer reproduces, and the minimal text is reported.
"""

from __future__ import annotations

import json

from hypothesis import strategies as st

from ..model import Case, FailureClass, Finding, Substrate, Tier
from ._console_hypothesis import hunt, post_raw, short
from ._console_rig import Rig, console_rig

SITE = "packages/thalamus-console/src/thalamus_console/tmux.py::literal_text_args"
_ME = "tests/qe/cases/console_api_send_is_data.py"
WIDTH_SAFE = st.one_of(
    st.characters(min_codepoint=0x20, max_codepoint=0x7E),
    st.characters(min_codepoint=0xA1, max_codepoint=0xFF, blacklist_characters="\xad"),
    st.characters(min_codepoint=0x391, max_codepoint=0x3C9, blacklist_characters="΢"),
    st.characters(min_codepoint=0x410, max_codepoint=0x44F),
)
# Fragments that are key names, flags or separators to tmux — a transform that parses the
# text instead of typing it fires on these, and `send("Ent"); send("er")` against
# `send("Enter")` is the metamorphic pair that tells the two apart.
_PIECES = ["Enter", "Ent", "er", "Space", "Tab", "Up", "C-a", "C-c", "Escape", "BSpace", "F1",
           "-", "-t", "0", "--", ";", "\\;", " ", "a", "#{pane_id}", "~", "$HOME", "\\"]
TEXT = st.one_of(
    st.text(alphabet=WIDTH_SAFE, min_size=1, max_size=90),
    st.lists(st.sampled_from(_PIECES), min_size=1, max_size=5).map("".join))


def _victim(rig: Rig) -> int:
    """A `cat` window at index 1 with a clean line."""
    if not any(i == 1 for i, _ in rig.window_names()):
        rig.tmux("new-window", "-d", "-t", f"{rig.session}:1", "-n", "qe-victim", "cat")
    return 1


def _fresh_line(rig: Rig) -> None:
    post_raw(rig.port, "/api/key", json.dumps({"index": 1, "key": "enter"}).encode())


def _send(rig: Rig, text: str):
    return post_raw(rig.port, "/api/send",
                    json.dumps({"index": 1, "text": text, "submit": False}).encode())


def _tail(rig: Rig, want: str) -> str:
    """The pane's content once it ends with `want`, or whatever it ended as at 3s."""
    last = ""

    def ready():
        nonlocal last
        last = rig.capture(1).rstrip("\n")
        return last.endswith(want)

    rig.wait_for(ready, timeout=3.0, interval=0.05)
    return last


def _last_line(capture: str, n: int) -> str:
    return capture[-n:] if n else ""


def run() -> Finding | None:
    with console_rig() as rig:
        _victim(rig)
        # Controls.
        _fresh_line(rig)
        r = _send(rig, "qe-control-ok")
        got = _tail(rig, "qe-control-ok")
        if r.status != 200 or not got.endswith("qe-control-ok"):
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="a known-good send did not appear in the pane, so every comparison "
                        "below would fail for a fixture reason rather than a route one",
                witness=f"status={r.status} body={r.body[:100]!r} pane tail={got[-80:]!r}",
                site=_ME)
        if got.endswith("qe-control-okx"):
            return Finding(failure_class=FailureClass.COLLAPSED_SENTINEL,
                           summary="the tail comparison accepts text that was never sent",
                           witness=f"tail={got[-80:]!r}", site=_ME)
        refused = post_raw(rig.port, "/api/send",
                           json.dumps({"index": 77, "text": "x", "submit": False}).encode())
        if refused.status != 400:
            return Finding(failure_class=FailureClass.COLLAPSED_SENTINEL,
                           summary="a send to a window that does not exist was not refused",
                           witness=f"status={refused.status} body={refused.body[:100]!r}",
                           site=_ME)

        def verbatim(example):
            kind, a, b = example
            text = a if kind == "one" else a + b
            _victim(rig)
            _fresh_line(rig)
            if kind == "one":
                resp = _send(rig, a)
                single = None
            else:
                resp = _send(rig, a)
                if resp.status == 200:
                    resp = _send(rig, b)
                single = True
            if resp.status != 200:
                return ("refused", resp.status), f"send {short(a, 60)!r}+{short(b, 60)!r} -> {resp.status} {resp.body[:100]!r}"
            tail = _tail(rig, text)
            if not tail.endswith(text):
                got = _last_line(tail, len(text) + 8)
                what = "send(a); send(b)" if single else "send(a)"
                return (("split" if single else "one"),), (
                    f"{what} with a={short(a, 80)!r} b={short(b, 80)!r}: pane ends "
                    f"{got!r}, want ...{text!r}")
            return None

        pair_ok = lambda a, b: (a + b) == (a + b).rstrip(" ")  # noqa: E731
        strategy = st.one_of(
            st.tuples(st.just("one"), TEXT, st.just("")).filter(lambda t: t[1] == t[1].rstrip(" ")),
            st.tuples(st.just("two"), TEXT, TEXT).filter(lambda t: pair_ok(t[1], t[2])),
        )
        hits, truncated = hunt(strategy, verbatim, max_examples=70, rounds=4, budget_s=32.0)
        if not hits:
            return None
        parts = [f"{h.detail}" for h in hits]
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary="text sent through POST /api/send did not arrive in the pane verbatim, "
                    "or sending it in two calls differed from sending it in one",
            witness=f"{len(hits)} distinct signature(s)"
                    + (" (time budget reached; more may remain)" if truncated else "")
                    + ": " + " || ".join(parts),
            site=SITE)


CASE = Case(
    name="send-text-arrives-verbatim-and-send-is-concatenative",
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_TMUX,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="generated printable text sent via /api/send lands verbatim in a cat pane, and "
            "send(a);send(b) equals send(a+b)",
    run=run,
)
