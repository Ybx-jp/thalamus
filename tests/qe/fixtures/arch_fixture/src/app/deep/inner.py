"""A relative import that climbs two levels, and a deferred one that closes a cycle.

`from .. import util` is `app.util` reached relatively — the case a resolver that only
understands absolute names gets wrong. The deferred `from app import core` closes a
`core <-> inner` cycle that is invisible to a module-level-only reading, which is the
same shape as the real `eval/corpora.py <-> eval/arms.py` pair.
"""

from .. import util


def late():
    from app import core

    return core, util
