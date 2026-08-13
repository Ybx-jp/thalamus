"""
Artifact `(repo, path)` projection — the derived join key, and what may anchor it.

Interfaces: thalamus.substrate.artifact_paths.checkout_registry, relativize,
            anchor_from_touches
Infrastructure: none; the registry and identifiers are plain values, and the two
                anchoring rules are pure functions over them
Scope: which anchors are allowed to resolve a path. The identifier is never re-keyed
       here — these cover the derived properties beside it.
"""

from thalamus.substrate import artifact_paths


class _FakeRoots:
    """A traversal stub serving `checkout_registry`'s single projection."""

    def __init__(self, rows):
        self._rows = rows

    def V(self):
        return self

    def has_label(self, _label):
        return self

    def has(self, *_args, **_kwargs):
        return self

    def project(self, *_keys):
        return self

    def by(self, *_args, **_kwargs):
        return self

    def to_list(self):
        return self._rows


def test_only_a_proven_root_may_anchor_anything():
    """
    Scenario: three sessions carry a repo_root — one proven by cwd, one by touch, one
    with no evidence recorded at all

    This is the consumer side of `project_evidence`, and the reason it is a rule about
    provenance rather than about whether a string looks like a repo name. An anchor is
    what an absolute path is cut against, and cutting against a wrong one does not fail
    to merge — it splits one file into two identities. Absent evidence means unknown,
    so it does not get to anchor.
    """
    g = _FakeRoots([
        {"root": "/home/u/proven", "evidence": "cwd"},
        {"root": "/home/u/touched", "evidence": "touch"},
        {"root": "/home/u/unexplained", "evidence": ""},
    ])

    # Longest first, and the unexplained root is absent rather than last.
    assert artifact_paths.checkout_registry(g) == ["/home/u/touched", "/home/u/proven"]


def test_the_registry_is_longest_first_so_a_nested_checkout_keeps_its_own_files():
    """
    Scenario: a vendored subrepo inside a parent checkout, both proven

    Longest-prefix match is what makes resolution order-independent. Four artifacts on
    the live graph sit under `charlie-things/vendor/scratch-gui`, and a parent-first
    rule would hand them to `charlie-things` depending only on iteration order.
    """
    registry = ["/w/outer/vendor/inner", "/w/outer"]

    assert artifact_paths.relativize("/w/outer/vendor/inner/src/a.py", registry) == (
        "inner", "src/a.py"
    )
    assert artifact_paths.relativize("/w/outer/src/b.py", registry) == ("outer", "src/b.py")


def test_a_path_in_no_known_checkout_belongs_to_no_repo():
    """
    Scenario: a scratchpad file, a skill file, and a system binary

    "Belongs to no repo" has to be an outcome rather than a failure. 575 artifacts here
    are in this state, and a rule without an explicit empty result invents a
    repo-relative path for every one of them.
    """
    registry = ["/home/u/repo"]

    for identifier in (
        "/tmp/claude-1000/-home-u/abc/scratchpad/cyc2",
        "/home/u/.claude/skills/some-skill/references/notes.md",
        "/usr/local/bin/install-media-sort.sh",
    ):
        assert artifact_paths.relativize(identifier, registry) == ("", "")


def test_a_relative_spelling_is_anchored_by_its_session_and_only_when_unanimous():
    """
    Scenario: a relative identifier reached from one checkout, and one reached from two

    This is the half that does the work. The fragmentation being repaired is an absolute
    and a relative spelling of the *same file*, so anchoring only the absolute one leaves
    every pair as far apart as it started — the derived properties would be tidy and
    group nothing. Unanimity is what stops it fabricating the false merge that re-keying
    the identifier was rejected for.
    """
    assert artifact_paths.anchor_from_touches(["/home/u/thalamus"]) == "thalamus"
    assert artifact_paths.anchor_from_touches(["/home/u/thalamus", "/home/u/other"]) == ""
    assert artifact_paths.anchor_from_touches([]) == ""
    # A trailing slash is the same checkout, not a second one.
    assert artifact_paths.anchor_from_touches(["/home/u/thalamus/", "/home/u/thalamus"]) == (
        "thalamus"
    )


def test_a_checkout_root_itself_is_not_relativized_to_nothing():
    """
    Scenario: an artifact whose identifier IS a checkout root

    Cutting it against itself yields the empty relative path, which would group the
    directory with anything else that failed to resolve. It is left unanchored instead.
    """
    assert artifact_paths.relativize("/home/u/repo", ["/home/u/repo"]) == ("", "")


def test_absence_and_disagreement_are_reconciled_differently_on_a_rewrite():
    """
    Scenario: an artifact already projected onto one checkout, met by a later session
    that (a) cannot anchor it, (b) anchors it to the same checkout, (c) to a different one

    Artifacts are global, so every session that touches a file rewrites this. The
    distinction is the one the project migration was rebuilt around: a session with no
    anchor to offer says nothing and must not erase another's answer, while a session
    offering a *different* checkout genuinely disagrees — and two owners honestly means
    none, which is the false merge re-keying the identifier was rejected to avoid.
    """
    from thalamus.substrate.writer import _reconcile

    held = ("thalamus", "docs/x.md")

    assert _reconcile(held, "", "") == held                       # absence: keep
    assert _reconcile(held, "thalamus", "docs/x.md") == held      # agreement
    assert _reconcile(held, "charlie-things", "src/a.py") == ("", "")   # disagreement
    assert _reconcile(None, "thalamus", "docs/x.md") == ("thalamus", "docs/x.md")
    assert _reconcile(("", ""), "thalamus", "docs/x.md") == ("thalamus", "docs/x.md")
