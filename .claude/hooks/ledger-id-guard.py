#!/usr/bin/env python3
"""PreToolUse (Bash) — refuse `claims-ledger new --id`.

`claims-ledger new` allocates the next free entry id, and `claims-ledger renumber` moves
the ids of whichever branch merges second when two branches minted the same ones. A
hand-picked id sidesteps both: it leaves gaps in the sequence and settles a collision by
guessing where the other branch will stop. So an entry id is always allocated, never
chosen.

Only `new` takes an entry id. `source add --id` names a source, is required, and is not
refused. Invocations through `uv run`, `.venv/bin/` and `python -m claims_ledger` are
all recognised; a script that runs the command on the agent's behalf is not seen.
Project scope only: it arms in this checkout, for work on this repository.
"""
import json
import os
import shlex
import sys

OPERATORS = {";", "&&", "||", "|", "&", "(", ")"}
GLOBAL_WITH_VALUE = {"--root", "--config"}

# Words that may stand between a command position and the program it runs, so that
# `uv run --project . claims-ledger` counts and `echo claims-ledger new --id` does not.
PREFIXES = {"env", "exec", "command", "time", "nice", "uv", "uvx", "run"}
PREFIX_OPTS_WITH_VALUE = {"--project", "--directory", "--with", "--python", "--from"}

REASON = (
    "claims-ledger new --id is refused in this repository: entry ids are allocated, never "
    "chosen. Drop --id and let `claims-ledger new` take the next free id. If another "
    "unmerged branch has minted the same ids, the branch that merges second runs "
    "`claims-ledger renumber --onto <branch> --write`, which rewrites its commits so each "
    "entry carries the id it will keep."
)


def _words(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    return list(lexer)


def _at_command_position(words: list[str], i: int) -> bool:
    k = i - 1
    while k >= 0:
        word = words[k]
        if k > 0 and words[k - 1] in PREFIX_OPTS_WITH_VALUE:
            k -= 2
        elif word in PREFIXES or word.startswith("-") or "=" in word:
            k -= 1
        else:
            break
    return k < 0 or words[k] in OPERATORS


def _subcommand_start(words: list[str], i: int) -> int | None:
    """The index after the program word, when words[i] runs claims-ledger."""
    word = words[i]
    if os.path.basename(word) == "claims-ledger" and _at_command_position(words, i):
        return i + 1
    if (word == "claims_ledger" and i > 1 and words[i - 1] == "-m"
            and os.path.basename(words[i - 2]).startswith("python")
            and _at_command_position(words, i - 2)):
        return i + 1
    return None


def refuses(command: str) -> bool:
    """Whether `command` runs `claims-ledger new` with `--id`, which `main` then refuses;
    `source add --id` is not refused (A0202, cites-as-live).

    Parsed as shell words rather than matched as text, so an `--id` inside a quoted
    argument, on another subcommand, or in a later command of the same line is not
    mistaken for the flag on `new`. An unparseable command is let through: the ledger's
    own checks still run on whatever it writes.
    """
    try:
        words = _words(command)
    except ValueError:
        return False
    for i in range(len(words)):
        j = _subcommand_start(words, i)
        if j is None:
            continue
        while j < len(words) and words[j].startswith("-"):
            j += 2 if words[j] in GLOBAL_WITH_VALUE else 1
        if j >= len(words) or words[j] != "new":
            continue
        for word in words[j + 1:]:
            if word in OPERATORS:
                break
            if word == "--id" or word.startswith("--id="):
                return True
    return False


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    command = (payload.get("tool_input") or {}).get("command") or ""
    if "claims" not in command or not refuses(command):
        return
    json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                      "permissionDecision": "deny",
                                      "permissionDecisionReason": REASON}}, sys.stdout)


if __name__ == "__main__":
    main()
