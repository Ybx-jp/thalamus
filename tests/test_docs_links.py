"""
Whether the published docs can be navigated.

Interfaces: the markdown under docs/, plus README.md and CONTRIBUTING.md.
Infrastructure: file reads only.
Scope: the two ways a doc stops being reachable, both of which are silent. A link
to a file that does not exist sends a reader to a 404 on GitHub and to nothing at
all in an editor; a doc that nothing links to is unreachable from the first page,
which is where every reader starts. Both were live: `docs/console.md` held three
links to two absent files and had no inbound link from anywhere, which put the whole
of the phone, tailnet and PWA story behind a path only its author knew.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"

# The published set: the pages a reader reaches by opening the repository. Docs
# that live under a subdirectory are reference material hung off these.
PUBLISHED = sorted([REPO_ROOT / "README.md", REPO_ROOT / "CONTRIBUTING.md",
                    *sorted(DOCS.glob("*.md"))])

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _links(doc: Path) -> list[str]:
    """Relative links only — external URLs and bare anchors are someone else's."""
    return [target for target in LINK.findall(doc.read_text())
            if not target.startswith(("http://", "https://", "mailto:", "#"))]


@pytest.mark.parametrize("doc", PUBLISHED, ids=lambda p: p.name)
def test_every_relative_link_resolves(doc):
    """A link is a promise that the file is there; nothing else checks it."""
    dangling = [target for target in _links(doc)
                if not (doc.parent / target.split("#", 1)[0]).exists()]

    assert not dangling, f"{doc.name} links to files that do not exist: {dangling}"


# Link shapes the docs actually use, each one a way `LINK` and `_links` could stop
# seeing a target while the live tree stays clean and both tests above stay green.
# Written as (markdown, expected targets) so the extractor is held to what it must find,
# not merely to finding something.
_LINK_SHAPES = [
    ("[a doc](concepts.md)", ["concepts.md"]),
    ("[a section](concepts.md#scopes)", ["concepts.md#scopes"]),
    ("[a parent](../README.md)", ["../README.md"]),
    ("[a nested page](qe/README.md)", ["qe/README.md"]),
    ("[one](a.md) and [two](b.md) on a line", ["a.md", "b.md"]),
    ("[an anchor only](#a-heading)", []),
    ("[external](https://example.com/x.md)", []),
    ("[mail](mailto:nobody@example.com)", []),
]


@pytest.mark.parametrize("markdown,expected", _LINK_SHAPES)
def test_the_link_extractor_finds_each_shape_the_docs_use(markdown, expected, tmp_path):
    """The control the resolve test cannot carry itself.

    `test_every_relative_link_resolves` runs only against the live tree, which is clean,
    so it passes whether the extractor works or has stopped matching a syntax form
    (#227). These pin what `_links` must see, and the case below pins that a broken link
    is reported at all.
    """
    doc = tmp_path / "sample.md"
    doc.write_text(markdown)

    assert _links(doc) == expected


def test_a_link_to_a_missing_file_is_reported(tmp_path):
    """The resolve test's own predicate, driven over a link that does not resolve.

    Without this, "no dangling links" and "no links were examined" are the same pass.
    """
    doc = tmp_path / "sample.md"
    doc.write_text("[gone](no-such-file.md) and [here](sample.md)")

    dangling = [target for target in _links(doc)
                if not (doc.parent / target.split("#", 1)[0]).exists()]

    assert dangling == ["no-such-file.md"]


@pytest.mark.parametrize("doc", sorted(DOCS.glob("*.md")), ids=lambda p: p.name)
def test_every_doc_is_linked_from_somewhere(doc):
    """An unlinked doc is written, committed, and unread.

    README is the root of the walk, so it is exempt by construction; every page
    under `docs/` has to be reachable from at least one other published page.
    """
    inbound = [other.name for other in PUBLISHED if other != doc
               and any((other.parent / t.split("#", 1)[0]).resolve() == doc.resolve()
                       for t in _links(other))]

    assert inbound, f"{doc.name} is linked from nothing — no reader can navigate to it"
