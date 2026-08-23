"""Imported by `api` at module level, and imports it back inside a function.

The deferred half closes a cycle a module-level reading cannot see, which is what makes
the two `import_depth` readings over this fixture different numbers instead of the same
number twice.
"""


def alpha():
    return "alpha"


def beta():
    return "beta"


def leaf():
    return "leaf"


def orphan():
    return "orphan"


def frame(path):
    return path


def refresh():
    from srv import api

    return api.route


def delta():
    return "delta"


def health():
    return "ok"
