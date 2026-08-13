"""A leaf: imports nothing internal, so nothing here may produce an edge."""

import os


def shout(text: str) -> str:
    return f"{text.upper()}{os.linesep}"
