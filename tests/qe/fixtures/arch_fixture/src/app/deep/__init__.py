"""A subpackage that imports nothing.

It exists to be the *target* of a package edge: `from app.deep import inner` executes
this file, which is the dependency the `module-and-package` resolve policy counts and
`deepest-matching-module` does not.
"""
