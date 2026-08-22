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
