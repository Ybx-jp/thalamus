"""Package root of the extractor's ground-truth fixture.

Every import in this fixture tree is deliberate and hand-counted in
`tests/qe/cases/arch_extractor.py`. Changing a line here without changing the
expected edge list there is supposed to turn that case red.

This file's one import exercises the self-package case: `from app import core`
resolves to a submodule, and the package half of that import is this very file,
which must not produce a self-edge.
"""

from app import core

__all__ = ["core"]
