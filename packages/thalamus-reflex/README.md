# thalamus-reflex

The memory reflex for [thalamus](https://github.com/Ybx-jp/thalamus): when a Bash call in
a Claude Code session fails — a pytest `FAILED` line, a traceback, `command not found` —
the harness retrieves against the identifiers in that output and serves what the graph
holds about them into the session, marked as unsolicited.

Installing it adds:

- two Claude Code hooks, wired by `thalamus init`: `reflex.sh` on Bash results and
  `reflex-pointer-tap.sh` on every tool, each under `PostToolUse` and
  `PostToolUseFailure`;
- `thalamus reflex`, the worker those hooks run;
- `thalamus eval reflex`, the reflex read by plan: what fired, what was served, and the
  used-verdicts on what landed;
- `thalamus eval vocabulary`, which replays real anchor sets through every retrieval
  tool and reports what each returns.

It depends on `thalamus-memory` and nothing else from thalamus, and registers through the
`thalamus` entry-point group.

It is not on PyPI yet. From a checkout of the repository, `uv sync` installs it into the
development environment, and `pip install . ./packages/thalamus-reflex` installs it with
the core into any other. Run `thalamus init` after installing it, so the hooks are wired.
