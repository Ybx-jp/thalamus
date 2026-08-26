"""
The detached `sh -c` blocks, checked as scripts before anything runs them.

Interfaces: every `nohup sh -c "..."` block under
            src/thalamus/harness/hooks/ — currently claude-code/session-end.sh,
            codex/session-end.sh, cursor/distill.sh
Infrastructure: bash for the expansion, sh (dash on Ubuntu) for `-n`; no graph,
                no model, no session
Scope: the block is a **double-quoted string** built by bash and handed to a
       second shell, so everything bash expands in double quotes fires while the
       script is being assembled — including backticks, which are command
       substitution and not prose markup. That defect is invisible to every
       other check in this repo: the hook file itself parses, `shellcheck` reads
       the block as one string argument, and the failure only appears at a real
       session end, in a per-session log nobody reads.

       Measured 2026-08-26: a comment in claude-code/session-end.sh wrote a
       command name in backticks. Bash ran `thalamus init --check` on every
       session end where that binary resolved, spliced its 37 lines of output
       into the script, and `sh` died on line 27 — `Verification (exercised, not
       assumed):` — before reaching `thalamus extract`. Two room sessions ended
       undistilled. Nothing was written to hook-failures.log either, because the
       `record_failure` helper is defined below the injection point and the
       syntax error kills the whole block before any of it runs.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "src" / "thalamus" / "harness" / "hooks"

# The variables the hook has in scope where it builds the block. Values are
# stand-ins; what is under test is the *shape* of the assembled script, and a
# realistic non-empty value is what makes an unquoted expansion visible.
BLOCK_ENV = {
    "projects_dir": "/tmp/projects",
    "forked_from": "",
    "transcript_path": "/tmp/session.jsonl",
    "repo_root": "/home/op/code/thalamus",
    "session_id": "deadbeef-1111-2222-3333-444455556666",
    "scope": "main",
    "room": "ontoclean",
    "project_dir": "-home-op-code-thalamus",
    "log_dir": "/tmp/logs",
    "log": "/tmp/logs/session-end-deadbeef.log",
    "codex_home": "/tmp/codex",
    "rollout": "/tmp/codex/rollout.jsonl",
    "cwd": "/home/op/code/thalamus",
}

_OPENS = re.compile(r'^\s*nohup sh -c "$')
_CLOSES = re.compile(r'^"\s*>>')


def _blocks(path: Path) -> list[tuple[int, str]]:
    """Every `nohup sh -c "` body in a hook, as `(first line number, text)`."""
    lines = path.read_text().splitlines()
    found, start = [], None
    for number, line in enumerate(lines, start=1):
        if start is None and _OPENS.match(line):
            start = number
        elif start is not None and _CLOSES.match(line):
            found.append((start + 1, "\n".join(lines[start:number - 1])))
            start = None
    return found


def _hook_blocks() -> list[tuple[Path, int, str]]:
    return [
        (path, line, body)
        for path in sorted(HOOKS.glob("*/*.sh"))
        for line, body in _blocks(path)
    ]


def _ids(case) -> str:
    path, line, _ = case
    return f"{path.parent.name}/{path.name}:{line}"


CASES = _hook_blocks()


def test_the_scanner_finds_the_blocks_it_is_meant_to_guard():
    """A parametrized test over an empty list passes silently, and this file's
    whole value is that it runs. If a hook stops matching the opener, that is
    the event to fail on — not a green run over nothing."""
    found = {f"{p.parent.name}/{p.name}" for p, _, _ in CASES}
    assert found >= {
        "claude-code/session-end.sh",
        "codex/session-end.sh",
        "cursor/distill.sh",
    }, found


@pytest.mark.parametrize("case", CASES, ids=_ids)
def test_no_command_substitution_survives_into_the_block(case):
    """A backtick or an unescaped `$(` in the block is a command bash runs.

    Escaped forms are how the block *legitimately* defers a substitution to the
    inner shell — `\\$(uv run ... quick delta)` is written to run under `sh`, and
    reads here as `\\$(`. What is banned is the unescaped kind, which runs in the
    hook's own process at session end.
    """
    _, _, body = case
    assert "`" not in body, (
        "backticks in a double-quoted sh -c block are command substitution, not "
        "prose markup — bash runs them while assembling the script"
    )
    bare = re.sub(r"\\\$\(", "", body)
    assert "$(" not in bare, (
        "an unescaped $( runs in the hook's process; escape it as \\$( to defer "
        "it to the inner shell"
    )


@pytest.fixture
def loud_stubs(tmp_path_factory):
    """A PATH where every binary the hooks name answers with multi-line output.

    Without this the parse check cannot catch the defect it exists for: a
    substitution that fires resolves to `""` on a machine where the binary is
    absent, and the assembled script parses cleanly. Absence is exactly what hid
    the measured failure for five days — ordinary sessions had no `thalamus` on
    PATH and distilled fine, and the two that did have it were the ones lost.
    """
    stub_dir = tmp_path_factory.mktemp("loud-bin")
    for name in ("thalamus", "uv", "jq", "date", "git"):
        stub = stub_dir / name
        stub.write_text("#!/bin/sh\necho 'ok'\necho 'Verification (exercised):'\n")
        stub.chmod(0o755)
    return stub_dir


@pytest.mark.skipif(shutil.which("bash") is None or shutil.which("sh") is None,
                    reason="needs bash to expand the block and sh to parse it")
@pytest.mark.parametrize("case", CASES, ids=_ids)
def test_the_expanded_block_is_a_valid_sh_script(case, loud_stubs):
    """Expand the block the way bash does, then ask sh whether it parses.

    This catches the measured failure by its consequence rather than its cause:
    whatever bash splices in, the result still has to be a script. `sh -n` parses
    without executing, so nothing here distills, writes, or spends.
    """
    path, _, body = case
    assignments = "".join(f"{name}={value!r}\n".replace("'", '"')
                          for name, value in BLOCK_ENV.items())
    expander = f'{assignments}printf "%s" "\n{body}\n"'
    expanded = subprocess.run(
        ["bash", "-c", expander], capture_output=True, text=True, timeout=60,
        env={"PATH": f"{loud_stubs}:/usr/bin:/bin"},
    )
    assert expanded.returncode == 0, expanded.stderr
    parsed = subprocess.run(
        ["sh", "-n"], input=expanded.stdout, capture_output=True, text=True, timeout=60,
    )
    assert parsed.returncode == 0, (
        f"{path.parent.name}/{path.name}: the assembled script does not parse — "
        f"{parsed.stderr.strip()}"
    )


@pytest.mark.skipif(shutil.which("bash") is None or shutil.which("sh") is None,
                    reason="needs bash and sh")
def test_the_parse_check_fails_on_the_defect_it_was_written_for(tmp_path):
    """The positive control. A checker that cannot be made to fire is the green
    suite this defect already had, so this reproduces it exactly: a backticked
    command name in a comment, a binary on PATH that answers it, and output whose
    second line opens a paren."""
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "thalamus").write_text(
        "#!/bin/sh\necho 'ok'\necho 'Verification (exercised, not assumed):'\n"
    )
    (stub / "thalamus").chmod(0o755)

    body = "  # hook-failures.log is what `thalamus init --check` reads back.\n  exit 0"
    expanded = subprocess.run(
        ["bash", "-c", f'printf "%s" "\n{body}\n"'],
        capture_output=True, text=True, timeout=60,
        env={"PATH": f"{stub}:/usr/bin:/bin"},
    )
    assert "Verification" in expanded.stdout, "the stub must actually have been run"
    parsed = subprocess.run(
        ["sh", "-n"], input=expanded.stdout, capture_output=True, text=True, timeout=60,
    )
    assert parsed.returncode != 0
    assert "unexpected" in parsed.stderr
