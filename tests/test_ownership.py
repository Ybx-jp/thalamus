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
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from thalamus.contract.ownership import (
    OWNERSHIP_FILE,
    denies,
    owner_of,
    rows,
)

REPO = Path(__file__).resolve().parents[1]
HOOKS = REPO / "src" / "thalamus" / "harness" / "hooks" / "claude-code"
GUARD = HOOKS / "role-guard.sh"
OWNED = f"{REPO}/tests/qe/expectations.json"
TABLE = REPO / "config" / OWNERSHIP_FILE


@pytest.fixture
def owner_experts(tmp_path):
    """A roster declaring the scope that owns `tests/qe/`, and its mirror deny.

    Ownership binds by scope name and reads no manifest — that independence is the
    reason the table is its own file rather than a manifest field, and is what lets
    it bind `main`. The table is read from the same config root, so this one carries
    the checkout's. Two things around it do read one: scope *resolution* through
    the agent picker admits a name only when a manifest backs it, and the mirror
    half of the partition (`*/src/*`) is a `write_boundary` field. Both are handed
    an expert set of this test's own making, so the partition property is asserted
    against a declared boundary rather than against whichever experts a checkout
    happens to carry.
    """
    experts = tmp_path / "config" / "experts"
    experts.mkdir(parents=True)
    (experts / "qe.yaml").write_text(
        "contract: v0\n"
        "scope: qe\n"
        "name: Quality engineer\n"
        "write_boundary:\n"
        "  deny_globs:\n"
        '    - "*/src/*"\n'
        "  reason: >-\n"
        "    qe holds the oracle, not the fix.\n"
    )
    shutil.copyfile(TABLE, tmp_path / "config" / OWNERSHIP_FILE)
    return {"THALAMUS_CONFIG_DIR": str(tmp_path / "config")}


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


def _evidence(what: str, result) -> str:
    """Everything the next investigator needs, at the moment it still exists.

    A bare `assert result.returncode == 2` discards the distinction between the two
    diagnoses it can fail with. The guard refuses with 2; a guard that *crashed* —
    an interpreter it could not start, a `jq` it could not fork, anything under
    `set -euo pipefail` — exits 1, and both read as "not 2". Those have opposite
    causes and opposite fixes.

    Recorded 2026-08-15 because that is exactly what happened: one observed failure
    of `test_the_partition_runs_both_ways`, and the run that would have separated
    the two was made after it had gone green again. Nothing survived, and 20 clean
    re-runs could not recover it. Load-dependence is the standing hypothesis, which
    is precisely the kind that will not reproduce on demand — so the next occurrence
    has to diagnose itself on its first and possibly only appearance.
    """
    return (f"{what}: expected refusal (2), got {result.returncode}. "
            f"2 is the guard refusing; 1 is the guard failing to run, which is a "
            f"different defect wearing the same number here.\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}")


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
        assert rows(), "this checkout's table is empty — the loop below would pass vacuously"
        for glob, owner, reason in rows():
            assert glob and owner
            assert len(reason.strip()) > 40, f"{glob} has no usable denial message"

    def test_every_owning_scope_ships_a_manifest_someone_can_be_pinned_to(self):
        """
        Scenario: a row reserves a tree for a scope the checkout cannot instantiate

        A row denies every scope but its owner, so the owner is the only party who can
        edit that tree. If no manifest declares the owner, nobody can be pinned to it —
        `resolve-scope.sh` only honours an agent-derived pin when
        `config/experts/<scope>.yaml` exists — and the tree becomes unwritable by
        everyone rather than reserved for someone. The deny half of the partition
        survives the manifest; the grant half does not, so removing a manifest is not
        the local act it looks like.
        """
        from thalamus.contract.manifest import available_scopes

        shipped = set(available_scopes())
        assert shipped, "no manifests found — the check below would pass vacuously"

        orphaned = sorted({owner for _, owner, _ in rows()} - shipped)
        assert not orphaned, (
            f"ownership rows reserve a tree for {orphaned}, which no manifest in "
            f"the same config root declares. Nobody can be pinned to those scopes, so the "
            f"trees they own cannot be edited by anyone. Shipped: {sorted(shipped)}"
        )


class TestTheTableIsConfiguration:
    """The rule is one repository's decision about its own trees, read from the config
    root beside the manifests, so a root without the file reserves nothing."""

    def test_a_root_without_the_file_reserves_nothing(self, tmp_path):
        assert rows(tmp_path) == ()
        assert denies("main", OWNED, tmp_path) is None

    def test_a_row_in_another_root_binds_there(self, tmp_path):
        (tmp_path / OWNERSHIP_FILE).write_text(json.dumps({
            "docs": {"glob": "*/handbook/*", "owner": "writer",
                     "reason": "The handbook is the writer's to change."}}))

        assert denies("main", "/repo/handbook/a.md", tmp_path)[1] == "writer"
        assert denies("writer", "/repo/handbook/a.md", tmp_path) is None
        assert denies("main", OWNED, tmp_path) is None, "this checkout's row is not there"

    def test_a_malformed_table_is_reported_not_read_as_empty(self, tmp_path):
        (tmp_path / OWNERSHIP_FILE).write_text("{not json")
        with pytest.raises(ValueError, match=OWNERSHIP_FILE):
            rows(tmp_path)

    def test_a_row_missing_its_reason_is_refused(self, tmp_path):
        (tmp_path / OWNERSHIP_FILE).write_text(json.dumps(
            {"bare": {"glob": "*/x/*", "owner": "qe"}}))
        with pytest.raises(ValueError, match="row `bare`"):
            rows(tmp_path)

    def test_the_wheel_ships_no_table(self):
        """The package carries no ownership row of its own: an installed wheel's config
        root starts without the file, and the examples `init` copies do not add one."""
        examples = REPO / "src" / "thalamus" / "examples"
        assert not list(examples.rglob(OWNERSHIP_FILE))
        assert not list((REPO / "src" / "thalamus").rglob(OWNERSHIP_FILE))


class TestTheCostThatDecidedTheModule:
    def test_importing_ownership_does_not_import_pydantic(self):
        """Load-bearing, not stylistic. This module is imported on every Edit/Write in
        every session on the box, including unpinned ones. Measured, best of 15 fresh
        interpreters: bare 13.8 ms, `import json` 18.7 ms, `import yaml` 31.1 ms,
        `contract.manifest` 151 ms — and the 151 ms is the pydantic import, not the
        YAML read.

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
    """This rule does not depend on the structured read having worked.

    The shared prologue already denies a payload it cannot parse, so this is the
    second of two closed doors — and the two catch different things. The prologue
    catches an input that is not JSON; this catches one that parses cleanly and puts
    the path somewhere the structured read does not look. It takes `write-guard.sh`'s
    posture for that: when the structured read fails, search the raw payload. The
    other boundaries can afford less, because their failure is a bad edit and this
    one's is a scope editing the oracle that indicts it.
    """

    def test_the_degraded_path_reads_the_table_not_a_copy_of_it(self, tmp_path):
        """With the interpreter unavailable the guard reads `ownership.json` with jq, so
        a row added to a config root binds on the degraded path with no second list to
        keep in step. The control is the same payload against a root without the row."""
        root = tmp_path / "config"
        root.mkdir()
        (root / OWNERSHIP_FILE).write_text(json.dumps({
            "docs": {"glob": "*/handbook/*", "owner": "writer",
                     "reason": "The handbook is the writer's to change."}}))
        payload = {
            "tool_name": "Edit",
            "tool_input": {"content": "writing into /repo/handbook/a.md"},
            "session_id": "test",
        }

        refused = run_guard(payload, tmp_path, {"THALAMUS_CONFIG_DIR": str(root)})
        (root / OWNERSHIP_FILE).unlink()
        control = run_guard(payload, tmp_path, {"THALAMUS_CONFIG_DIR": str(root)})

        assert refused.returncode == 2, _evidence("degraded handbook row", refused)
        assert "/handbook/" in refused.stderr
        assert control.returncode == 0, control.stderr

    def test_an_unparseable_target_naming_an_owned_path_is_refused(self, tmp_path):
        payload = {
            "tool_name": "Edit",
            "tool_input": {"content": f"writing into {REPO}/tests/qe/x.json"},
            "session_id": "test",
        }
        result = run_guard(payload, tmp_path)
        assert result.returncode == 2
        assert "/tests/qe/" in result.stderr

    def test_the_owner_still_passes_on_the_degraded_path(self, tmp_path, owner_experts):
        payload = {
            "tool_name": "Edit",
            "tool_input": {"content": f"writing into {REPO}/tests/qe/x.json"},
            "agent_type": "thalamus-qe",
        }
        assert run_guard(payload, tmp_path, owner_experts).returncode == 0

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

    def test_qe_can_write_its_own_directory(self, tmp_path, owner_experts):
        result = run_guard(
            write_payload(OWNED),
            tmp_path,
            {"CLAUDE_CODE_AGENT": "thalamus-qe", **owner_experts},
        )
        assert result.returncode == 0

    def test_the_partition_runs_both_ways(self, tmp_path, owner_experts):
        """The point of the rule. A scope denied the implementation tree while `main`
        writes its oracle freely is not partitioned from it — an authority that runs
        one way is not a partition."""
        qe_into_src = run_guard(
            write_payload(f"{REPO}/src/thalamus/cli.py"),
            tmp_path,
            {"CLAUDE_CODE_AGENT": "thalamus-qe", **owner_experts},
        )
        main_into_qe = run_guard(write_payload(OWNED), tmp_path, owner_experts)
        assert qe_into_src.returncode == 2, _evidence("qe into src/", qe_into_src)
        assert main_into_qe.returncode == 2, _evidence("main into tests/qe/",
                                                       main_into_qe)

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
