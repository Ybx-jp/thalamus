"""Three import forms that resolve differently, plus one that must leave no edge.

`import app.util` is a dotted module import. `from app.deep.inner import late` names a
*function* inside a module, so it resolves to that module and its package half points at
the same place — no second edge. The deferred `from app.deep import inner` names a
submodule, so its package half is a genuinely different dependency.
"""

import os

import app.util
from app.deep.inner import late


def run():
    from app.deep import inner

    return inner, late, app.util, os.linesep
