"""The favorites store behaves as the model of a set of offered directories says it does.

`POST /api/favorite` stars or unstars a directory and answers with the picker list the next
`GET /api/spawn-options` would carry; the store behind it is a file under the console's
HOME. This case drives a generated sequence of operations at the real server in
`_console_rig` and predicts every reply from a ten-line model that never reads the server.

**The model.** The rig offers three repositories (`alpha`, `beta`, `gamma`, found by the
console's scan root). A request names a path; it is *accepted* exactly when that path,
resolved against the server's cwd (the rig root) with symlinks followed, is one of the
offered directories — which is what the picker's whitelist is for. An accepted star puts
the canonical path in the favorites list; an accepted unstar removes it; a refused request
changes nothing. The picker is the favorites in star order, then the non-favorites sorted
by name, each with `favorite` true or false.

**Operations generated.** Star and unstar through *aliases of an offered directory*
(absolute, trailing slash, `x/../x`, rig-relative `projects/x`, a symlink outside the scan
root); *forged* paths (`/`, `/tmp`, the rig HOME, the scan root itself, `alpha/.git`, a real
subdirectory, a missing path, `""`, `~`, `../..`, generated text including NUL and lone
surrogates); and a wrong-typed `favorite` (`null`, `1`, `"true"`, `[]`, …). Reset between
examples is an unstar of all three directories, so every example starts from the same
modelled state.

**Invariants, after every operation.**

1. the reply is `200` with `dirs` equal to the model's, or a `400` JSON `{error}` for a
   path the model refuses or a `favorite` that is not a bool — never a 5xx, never a
   dropped connection;
2. a fresh `GET /api/spawn-options` returns the same `dirs` as the model, so the reply and
   the store agree;
3. the store file's `paths` are all offered, canonical directories — a forged path never
   enters it;
4. repeating an accepted operation immediately leaves `dirs` unchanged (idempotence).

**Metamorphic, separately.** A generated list of `(dir, starred)` operations on distinct
directories, run as given and then re-interleaved with each directory's own operations kept
in order, ends with the same *set* of favourites — independent operations commute. (Order
within the favourites list is star order and is not asserted equal; asserting it would
encode the implementation rather than the contract.)

**Controls.** A star of an unstarred offered directory must flip its `favorite` (the
fixture can change state at all); a forged `/` must be refused (the whitelist exists);
the store file must be found on disk and contain the starred path (invariant 3 is not
read off an empty glob).

**Shown capable of going red.** On the unmodified tree a path containing NUL or a lone
surrogate is answered `500 ValueError`/`UnicodeEncodeError` where the model says `400`.
In a copy of the console tree (`QE_CONSOLE_SRC`), skipping the `allowed` check in the
`/api/favorite` branch lets a forged `/tmp` into the store (invariants 1 and 3), and
making `set_favorite` append without first removing the path breaks idempotence (4).
"""

from __future__ import annotations

import json
import os

from hypothesis import strategies as st

from ..model import Case, FailureClass, Finding, Substrate, Tier
from ._console_hypothesis import Resp, crash_type, http_call, hunt, post_raw, reply_shape_problem, short
from ._console_rig import Rig, console_rig

SITE = "packages/thalamus-console/src/thalamus_console/server.py::Handler.do_POST (/api/favorite)"
_ME = "tests/qe/cases/console_api_favorites_model.py"
REPOS = ("alpha", "beta", "gamma")


class _World:
    """The rig plus the model. Never asks the server what the answer should be."""

    def __init__(self, rig: Rig):
        self.rig = rig
        self.offered = {n: os.path.realpath(rig.projects / n) for n in REPOS}
        self.by_path = {p: n for n, p in self.offered.items()}
        (rig.repos[0] / "sub").mkdir(exist_ok=True)
        self.alias = rig.root / "alias-alpha"
        if not self.alias.exists():
            self.alias.symlink_to(rig.repos[0])
        self.favs: list[str] = []

    # ---- paths a request may name ----
    def spelled(self, name: str, how: int) -> str:
        p = self.offered[name]
        return [p, p + "/", f"{p}/../{name}", f"projects/{name}",
                str(self.alias) if name == "alpha" else p][how % 5]

    def canonical(self, p: str) -> str | None:
        try:
            return os.path.realpath(os.path.join(str(self.rig.root), p))
        except (ValueError, UnicodeError):
            return None

    # ---- the model ----
    def dirs(self) -> list[dict]:
        starred = [{"label": os.path.basename(p), "path": p, "favorite": True} for p in self.favs]
        rest = [{"label": n, "path": self.offered[n], "favorite": False}
                for n in sorted(REPOS) if self.offered[n] not in self.favs]
        return starred + rest

    def apply(self, path: str, favorite) -> str:
        """Model one request; returns 'accept' or 'refuse'."""
        canon = self.canonical(path)
        if canon not in self.by_path or not isinstance(favorite, bool):
            return "refuse"
        self.favs = [p for p in self.favs if p != canon]
        if favorite:
            self.favs.append(canon)
        return "accept"

    def store_paths(self) -> list[str] | None:
        for f in self.rig.home.rglob("*.json"):
            try:
                d = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            if isinstance(d, dict) and isinstance(d.get("paths"), list) and "version" in d:
                return d["paths"]
        return None


def _request(w: _World, path: str, favorite) -> Resp:
    return post_raw(w.rig.port, "/api/favorite",
                    json.dumps({"path": path, "favorite": favorite}).encode())


def _dirs_of(resp: Resp):
    obj = resp.obj()
    return obj.get("dirs") if isinstance(obj, dict) else None


def _fresh_dirs(w: _World):
    resp = http_call(w.rig.port, "GET", "/api/spawn-options")
    obj = resp.obj()
    return obj.get("dirs") if isinstance(obj, dict) else None


def _step(w: _World, path: str, favorite, trail: list[str]) -> tuple[tuple, str] | None:
    """Drive one request and check every invariant against the model."""
    before = [dict(d) for d in w.dirs()]
    verdict = w.apply(path, favorite)
    resp = _request(w, path, favorite)
    shown = f"star={favorite!r} path={short(path, 60)!r}"
    trail.append(shown)
    problem = reply_shape_problem(resp)
    if resp.status is None or (resp.status >= 500):
        return ("crash", resp.status, crash_type(resp)), (f"{shown} -> {resp.status} "
                                        f"{resp.body[:120]!r}; model says {verdict}")
    if problem:
        return ("shape",), f"{shown}: {problem}"
    if verdict == "refuse":
        if resp.status != 400:
            return ("refuse-not-400", resp.status), f"{shown} -> {resp.status}, model says refuse"
    else:
        if resp.status != 200 or _dirs_of(resp) != w.dirs():
            return ("accept-dirs",), (f"{shown} -> {resp.status} dirs={_dirs_of(resp)}; "
                                      f"model dirs={w.dirs()}")
    fresh = _fresh_dirs(w)
    if fresh != w.dirs():
        return ("fresh-dirs",), f"{shown}: GET spawn-options dirs={fresh}; model={w.dirs()}"
    stored = w.store_paths()
    if stored is not None and not set(stored) <= set(w.by_path):
        return ("store-forged",), f"{shown}: store holds {stored}, offered={sorted(w.by_path)}"
    if verdict == "refuse" and w.dirs() != before:
        return ("model-moved",), f"{shown}: refused but model state moved"
    if verdict == "accept":
        again = _request(w, path, favorite)
        if again.status != 200 or _dirs_of(again) != w.dirs() or _fresh_dirs(w) != w.dirs():
            return ("not-idempotent",), (f"{shown} repeated: {again.status} "
                                         f"dirs={_dirs_of(again)}; model={w.dirs()}")
    return None


def _reset(w: _World) -> tuple[tuple, str] | None:
    for name in REPOS:
        resp = _request(w, w.offered[name], False)
        if resp.status != 200:
            return ("reset",), f"reset unstar {name} -> {resp.status} {resp.body[:100]!r}"
    w.favs = []
    return None


_FORGED = ["/", "/tmp", "", ".", "..", "~", "../..", "../../etc/passwd", "projects", "home",
           "projects/alpha/.git", "projects/alpha/sub", "projects/alpha/missing", "alpha",
           "projects/alpha\n", " projects/alpha", "projects/alpha;", "projects/%61lpha",
           "\x00", "projects/alpha\x00", "\ud800", "projects/\udfffalpha", "file:///tmp"]
_BAD_FLAGS = [None, 0, 1, 2, "true", "false", "", [], {}, [True], 1.0]


def _op():
    named = st.builds(lambda n, how, star: ("named", n, how, star),
                      st.sampled_from(REPOS), st.integers(0, 4), st.booleans())
    forged = st.builds(lambda p, star: ("forged", p, star),
                       st.one_of(st.sampled_from(_FORGED),
                                 st.text(alphabet=st.characters(blacklist_categories=()),
                                         max_size=12)), st.booleans())
    badflag = st.builds(lambda n, f: ("badflag", n, f), st.sampled_from(REPOS),
                        st.sampled_from(_BAD_FLAGS))
    return st.one_of(named, named, forged, badflag)


def _run_ops(w: _World, ops) -> tuple[tuple, str] | None:
    trail: list[str] = []
    bad = _reset(w)
    if bad:
        return bad
    for op in ops:
        if op[0] == "named":
            path, flag = w.spelled(op[1], op[2]), op[3]
        elif op[0] == "forged":
            path, flag = op[1], op[2]
        else:
            path, flag = w.offered[op[1]], op[2]
        bad = _step(w, path, flag, trail)
        if bad:
            sig, detail = bad
            return sig, f"after [{'; '.join(trail[:-1][-4:])}]: {detail}"
    return None


def _interleave(ops: list[tuple[str, bool]], order: list[int]) -> list[tuple[str, bool]]:
    queues: dict[str, list] = {}
    for d, s in ops:
        queues.setdefault(d, []).append((d, s))
    return [queues[ops[i][0]].pop(0) for i in order]


def _final_set(w: _World, ops: list[tuple[str, bool]]):
    for name, star in ops:
        resp = _request(w, w.offered[name], star)
        if resp.status != 200:
            return None, f"{name} star={star} -> {resp.status} {resp.body[:100]!r}"
    dirs = _fresh_dirs(w) or []
    return {d["label"] for d in dirs if d.get("favorite")}, ""


def run() -> Finding | None:
    with console_rig(repos=REPOS) as rig:
        w = _World(rig)
        # Controls.
        bad = _reset(w)
        if bad:
            return Finding(failure_class=FailureClass.COLLAPSED_SENTINEL,
                           summary="the fixture could not be reset to an empty favorites list",
                           witness=bad[1], site=_ME)
        star = _request(w, w.offered["beta"], True)
        flipped = [d for d in (_dirs_of(star) or []) if d["label"] == "beta"]
        if star.status != 200 or not flipped or flipped[0]["favorite"] is not True:
            return Finding(failure_class=FailureClass.COLLAPSED_SENTINEL,
                           summary="a star of an offered, unstarred directory did not flip "
                                   "its favorite flag, so the model comparisons are vacuous",
                           witness=f"status={star.status} body={star.body[:200]!r}", site=_ME)
        stored = w.store_paths()
        if stored is None or w.offered["beta"] not in stored:
            return Finding(failure_class=FailureClass.COLLAPSED_SENTINEL,
                           summary="the favorites store file was not found on disk after a "
                                   "star, so 'no forged path in the store' reads an empty glob",
                           witness=f"store paths={stored}", site=_ME)
        slash = _request(w, "/", True)
        if slash.status != 400:
            return Finding(failure_class=FailureClass.BOUNDARY_LEAK,
                           summary="POST /api/favorite of `/` (not an offered directory) was "
                                   "not refused with 400",
                           witness=f"status={slash.status} body={slash.body[:200]!r}",
                           site=SITE)

        hits, truncated = hunt(st.lists(_op(), min_size=1, max_size=7),
                               lambda ops: _run_ops(w, ops), max_examples=70, rounds=6,
                               budget_s=28.0)

        # Metamorphic: independent operations commute.
        order_strategy = st.lists(st.tuples(st.sampled_from(REPOS), st.booleans()),
                                  min_size=2, max_size=6).flatmap(
            lambda ops: st.tuples(st.just(ops), st.permutations(range(len(ops)))))

        def commute(example):
            ops, order = example
            bad = _reset(w)
            if bad:
                return bad
            a, why_a = _final_set(w, list(ops))
            bad = _reset(w)
            if bad:
                return bad
            b, why_b = _final_set(w, _interleave(list(ops), list(order)))
            if a is None or b is None:
                return ("commute-crash",), why_a or why_b
            if a != b:
                return ("commute",), (f"ops={list(ops)} as given -> favourites {sorted(a)}; "
                                      f"reordered {_interleave(list(ops), list(order))} -> "
                                      f"{sorted(b)}")
            return None

        more, _ = hunt(order_strategy, commute, max_examples=40, rounds=2, budget_s=12.0)
        hits += more
        if not hits:
            return None
        parts = [f"{short(h.example, 140)} :: {h.detail}" for h in hits]
        leak = any(h.signature[0] in ("store-forged",) for h in hits)
        return Finding(
            failure_class=(FailureClass.BOUNDARY_LEAK if leak
                           else FailureClass.INVARIANT_FALSIFIED),
            summary="the favorites store disagreed with its model, let a forged path in, "
                    "failed to repeat idempotently, or answered a refusal with a crash",
            witness=f"{len(hits)} distinct signature(s)"
                    + (" (time budget reached; more may remain)" if truncated else "")
                    + ": " + " || ".join(parts),
            site=SITE)


CASE = Case(
    name="favorites-store-matches-its-set-model-under-generated-operations",
    issue=419,
    fixed=True,
    tier=Tier.FAST,
    substrate=(Substrate.NEEDS_TMUX,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.BOUNDARY_LEAK,
             FailureClass.COLLAPSED_SENTINEL),
    summary="generated star/unstar/forged operations leave /api/favorite and /api/spawn-options "
            "agreeing with a set model; forged paths never enter the store",
    run=run,
)
