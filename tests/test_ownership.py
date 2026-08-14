"""Path ownership — the one boundary that binds `main`.

`WriteBoundary` is declared per scope and resolved from that scope's manifest, which
makes it structurally incapable of binding `main`: there is no `config/experts/main.yaml`
and the guard short-circuits before loading one. Ownership inverts the question — who
owns this path — so it can answer for a scope that declares nothing.

These tests carry three properties the design rests on, each of which was false at some
point today: that the rule binds `main`, that it fails CLOSED when its own check cannot
run, and that it stays cheap enough to sit ahead of the exemption it displaces.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from thalamus.contract.ownership import (
    PATH_OWNERSHIP,
    denies,
    fallback_markers,
    owner_of,
)

REPO = Path(__file__).resolve().parents[1]
HOOKS = REPO / "src" / "thalamus" / "harness" / "hooks" / "claude-code"
GUARD = HOOKS / "role-guard.sh"
OWNED = f"{REPO}/tests/qe/expectations.json"


def run_guard(payload, home, env=None):
    full_env = {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    if env:
        full_env.update(env)
    return subprocess.run(
        [str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=full_env,
        timeout=60,
    )


def write_payload(file_path):
    return {
        "tool_name": "Write",
        "tool_input": {"file_path": file_path},
        "session_id": "test",
        "cwd": str(REPO),
    }


class TestTheTable:
    def test_an_unowned_path_is_owned_by_nobody(self):
        assert owner_of(f"{REPO}/src/thalamus/cli.py") is None

    def test_the_owner_is_not_blocked_from_its_own_path(self):
        assert denies("qe", OWNED) is None

    def test_every_other_scope_is_blocked(self):
        for scope in ("main", "architect", "designer", "literature"):
            assert denies(scope, OWNED) is not None, scope

    def test_main_is_blocked_which_is_the_whole_point(self):
        """`write_boundary` cannot express this. There is no manifest to declare it in,
        and the guard exempts `main` before it would load one."""
        row = denies("main", OWNED)
        assert row is not None
        assert row[1] == "qe"

    def test_an_unowned_path_blocks_nobody(self):
        assert denies("main", f"{REPO}/src/thalamus/cli.py") is None

    def test_a_row_carries_the_reason_shown_to_the_blocked_session(self):
        for glob, owner, reason in PATH_OWNERSHIP:
            assert glob and owner
            assert len(reason.strip()) > 40, f"{glob} has no usable denial message"


class TestTheCostThatDecidedTheModule:
    def test_importing_ownership_does_not_import_pydantic(self):
        """Load-bearing, not stylistic. This module is imported on every Edit/Write in
        every session on the box, including unpinned ones. Measured: bare interpreter
        15ms, this module ~15ms, `contract.manifest` 151ms — and the 151ms is the
        pydantic import, not the YAML read (`load_manifest` adds only 24ms on top).

        A typed table here would make the ownership test more expensive than the
        manifest load whose cost the `main` short-circuit exists to avoid, which would
        defeat the ordering the rule depends on."""
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                "import thalamus.contract.ownership, sys; "
                "print('pydantic' in sys.modules)",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert probe.returncode == 0, probe.stderr
        assert probe.stdout.strip() == "False", (
            "contract/ownership.py pulled in pydantic — the guard's hot path just got "
            "10x more expensive"
        )


class TestTheDegradedPathFailsClosed:
    """The guard around this rule fails OPEN by design; this rule does not.

    `guards-fail-closed-on-unparseable-input` is an open qe finding that the shared jq
    prologue permits precisely when something unusual is happening. The other
    boundaries can afford that because their failure is a bad edit. This one's failure
    is a scope editing the oracle that indicts it, so it takes `write-guard.sh`'s
    posture instead: when the structured read fails, search the raw payload.
    """

    def test_the_inlined_markers_match_the_table(self):
        """The guard cannot call `fallback_markers()` in the state where it needs them
        — the interpreter is what failed. So the literals are duplicated into the shell
        script, and this test is the thing that keeps the duplication honest."""
        script = GUARD.read_text()
        block = re.search(r'for pair in ((?:"[^"]+"\s*)+); do', script)
        assert block, "the degraded fallback loop is gone from role-guard.sh"
        inlined = set()
        for pair in re.findall(r'"([^"]+)"', block.group(1)):
            marker, _, owner = pair.rpartition(":")
            inlined.add((marker, owner))
        expected = {
            (marker, row[1]) for marker, row in zip(fallback_markers(), PATH_OWNERSHIP)
        }
        assert inlined == expected, (
            f"role-guard.sh's inlined markers {inlined} disagree with "
            f"contract/ownership.py {expected}"
        )

    def test_an_unparseable_target_naming_an_owned_path_is_refused(self, tmp_path):
        payload = {
            "tool_name": "Edit",
            "tool_input": {"content": f"writing into {REPO}/tests/qe/x.json"},
            "session_id": "test",
        }
        result = run_guard(payload, tmp_path)
        assert result.returncode == 2
        assert "/tests/qe/" in result.stderr

    def test_the_owner_still_passes_on_the_degraded_path(self, tmp_path):
        payload = {
            "tool_name": "Edit",
            "tool_input": {"content": f"writing into {REPO}/tests/qe/x.json"},
            "agent_type": "thalamus-qe",
        }
        assert run_guard(payload, tmp_path).returncode == 0

    def test_an_unrelated_payload_is_not_swept_up(self, tmp_path):
        payload = {
            "tool_name": "Edit",
            "tool_input": {"content": "nothing to do with the oracle"},
            "session_id": "test",
        }
        assert run_guard(payload, tmp_path).returncode == 0


class TestTheGuardEnforcesIt:
    def test_main_cannot_write_the_oracle(self, tmp_path):
        result = run_guard(write_payload(OWNED), tmp_path)
        assert result.returncode == 2
        assert "owned by scope `qe`" in result.stderr
        assert "qe" in result.stderr

    def test_qe_can_write_its_own_directory(self, tmp_path):
        result = run_guard(
            write_payload(OWNED), tmp_path, {"CLAUDE_CODE_AGENT": "thalamus-qe"}
        )
        assert result.returncode == 0

    def test_the_partition_runs_both_ways(self, tmp_path):
        """The point of the rule. Before it, `qe` could not write `src/` while `main`
        could write `tests/qe/` freely — an authority that runs one way is not a
        partition."""
        qe_into_src = run_guard(
            write_payload(f"{REPO}/src/thalamus/cli.py"),
            tmp_path,
            {"CLAUDE_CODE_AGENT": "thalamus-qe"},
        )
        main_into_qe = run_guard(write_payload(OWNED), tmp_path)
        assert qe_into_src.returncode == 2
        assert main_into_qe.returncode == 2

    def test_a_block_lands_a_ledger_row_naming_the_rule(self, tmp_path):
        run_guard(write_payload(OWNED), tmp_path)
        rows = [
            json.loads(line)
            for path in (tmp_path / ".thalamus" / "guards").glob("*.jsonl")
            for line in path.read_text().splitlines()
            if line.strip()
        ]
        assert rows, "an ownership block wrote no guard-ledger row"
        blocked = [r for r in rows if r["verdict"].startswith("block")]
        assert blocked and blocked[-1]["guard"] == "path-ownership"
        assert blocked[-1]["scope"] == "main"

    def test_non_path_tools_are_untouched(self, tmp_path):
        """Ownership is a statement about files. A `Skill` call has no target path and
        must not be swept into it."""
        payload = {
            "tool_name": "Skill",
            "tool_input": {"skill": "recall-strategy"},
            "session_id": "test",
        }
        assert run_guard(payload, tmp_path).returncode == 0
