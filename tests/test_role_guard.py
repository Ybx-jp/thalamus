"""The role boundary — a scope's charter made structural rather than textual.

Two surfaces, tested separately because they fail differently. `WriteBoundary`
decides whether a path is inside a scope's charter; `role-guard.sh` decides whether
a session gets to write it. The first is pure and cheap to assert. The second has to
survive a hook's operating conditions — the wrong scope, an unreadable manifest, a
tool it does not govern — where the required behavior is usually *do nothing*, and a
guard that fails closed on a missing file would break every edit in every session.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from thalamus.contract.manifest import ExpertManifest, WriteBoundary, load_manifest
from thalamus.harness.install import HOOK_WIRING

HOOKS = Path(__file__).resolve().parents[1] / "src" / "thalamus" / "harness" / "hooks" / "claude-code"
REPO = Path(__file__).resolve().parents[1]


class TestWriteBoundary:
    def test_an_undeclared_boundary_denies_nothing(self):
        """The default has to be open. Every scope that predates this field carries
        the default, so a boundary that denied by default would retroactively bound
        four experts nobody decided to bound."""
        assert WriteBoundary().denies("/anywhere/at/all.py") is None

    def test_it_returns_the_matched_pattern_not_just_a_verdict(self):
        """The guard reports which rule fired. A bare True would make a blocked
        session guess at the boundary it hit."""
        boundary = WriteBoundary(deny_globs=["*.py", "*/src/*"])
        assert boundary.denies("/home/x/thing.py") == "*.py"
        assert boundary.denies("/home/x/src/thing.rs") == "*/src/*"

    def test_matching_is_absolute_so_it_survives_a_foreign_cwd(self):
        """Experts are cross-project and `thalamus spawn --dir` runs them in other
        repositories, where nothing repo-relative resolves."""
        boundary = WriteBoundary(deny_globs=["*/src/*"])
        assert boundary.denies("/some/other/checkout/src/main.py") == "*/src/*"

    def test_an_empty_path_is_not_a_match(self):
        """Tool payloads without a file path reach the guard; they are not writes to
        bound."""
        assert WriteBoundary(deny_globs=["*"]).denies("") is None


class TestShippedManifests:
    def test_designer_is_bounded_off_software_but_not_off_design_artifacts(self):
        boundary = load_manifest("designer").write_boundary
        for blocked in ("/r/app.js", "/r/view.tsx", "/r/style.css", "/r/run.sh", "/r/m.py"):
            assert boundary.denies(blocked), f"{blocked} should be outside designer"
        for allowed in ("/r/mock.svg", "/r/spec.md", "/r/tokens.json", "/r/page.html"):
            assert boundary.denies(allowed) is None, f"{allowed} is a design artifact"

    def test_qe_may_not_repair_what_it_asserts_against(self):
        """qe holds the oracle, not the fix — but the campaign-to-green-suite
        graduation path means tests/ and lab/ must stay unrestricted."""
        boundary = load_manifest("qe").write_boundary
        assert boundary.denies(f"{REPO}/src/thalamus/eval/oracle.py")
        assert boundary.denies(f"{REPO}/tests/test_eval_oracle.py") is None
        assert boundary.denies(f"{REPO}/lab/050-campaign.md") is None

    def test_architect_carries_no_boundary_by_charter(self):
        """It writes the changes it proposes; a path deny would block the work rather
        than bound a role. Its boundary is the pin trigger (docs/08), which is a
        weaker guarantee and is named as one."""
        assert load_manifest("architect").write_boundary.deny_globs == []

    @pytest.mark.parametrize("scope", ["literature", "eval-methodology", "homelab", "teacher"])
    def test_the_experts_that_predate_the_field_are_untouched(self, scope):
        assert load_manifest(scope).write_boundary.deny_globs == []

    def test_every_declared_boundary_explains_itself(self):
        """A block that cannot say why teaches route-around."""
        for scope in ("qe", "designer"):
            manifest = load_manifest(scope)
            assert manifest.write_boundary.reason.strip(), f"{scope} blocks without a reason"


def run_guard(payload, home, env=None):
    full_env = {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    if env:
        full_env.update(env)
    return subprocess.run(
        [str(HOOKS / "role-guard.sh")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=full_env,
        timeout=60,
    )


def write_payload(file_path, tool_name="Write"):
    return {
        "session_id": "rg-1",
        "cwd": str(REPO),
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": {"file_path": file_path},
    }


class TestRoleGuardHook:
    def test_it_blocks_a_bounded_scope_and_says_which_rule_fired(self, tmp_path):
        result = run_guard(
            write_payload(f"{REPO}/src/thalamus/console/static/app.js"),
            tmp_path,
            {"CLAUDE_CODE_AGENT": "thalamus-designer"},
        )
        assert result.returncode == 2
        assert "*.js" in result.stderr
        assert "config/experts/designer.yaml" in result.stderr

    def test_it_passes_a_design_artifact_from_the_same_scope(self, tmp_path):
        result = run_guard(
            write_payload(f"{REPO}/docs/wireframe.svg"),
            tmp_path,
            {"CLAUDE_CODE_AGENT": "thalamus-designer"},
        )
        assert result.returncode == 0

    def test_main_never_pays_for_the_guard(self, tmp_path):
        """`main` has no manifest by design and is the common case; the hook returns
        before it can cost a Python start-up on every edit."""
        result = run_guard(write_payload(f"{REPO}/src/thalamus/cli.py"), tmp_path)
        assert result.returncode == 0

    def test_a_scope_with_no_boundary_is_unaffected(self, tmp_path):
        result = run_guard(
            write_payload(f"{REPO}/src/thalamus/cli.py"),
            tmp_path,
            {"CLAUDE_CODE_AGENT": "thalamus-architect"},
        )
        assert result.returncode == 0

    def test_it_governs_the_edit_tools_and_nothing_else(self, tmp_path):
        """Bash can still write, and that miss is deliberate (lab/008's trade). The
        guard must not pretend otherwise by firing on tools it cannot bound."""
        payload = write_payload(f"{REPO}/src/x.py", tool_name="Bash")
        result = run_guard(payload, tmp_path, {"CLAUDE_CODE_AGENT": "thalamus-designer"})
        assert result.returncode == 0

    def test_notebook_edits_are_bounded_under_their_own_key(self, tmp_path):
        payload = {
            "session_id": "rg-1",
            "cwd": str(REPO),
            "tool_name": "NotebookEdit",
            "tool_input": {"notebook_path": f"{REPO}/analysis.py"},
        }
        result = run_guard(payload, tmp_path, {"CLAUDE_CODE_AGENT": "thalamus-designer"})
        assert result.returncode == 2

    def test_an_unknown_scope_fails_open(self, tmp_path):
        """Defence-in-depth over a boundary the manifest also states in prose. A hook
        that hard-failed every edit because a manifest moved would be worse than an
        unenforced boundary."""
        result = run_guard(
            write_payload(f"{REPO}/src/thalamus/cli.py"),
            tmp_path,
            {"THALAMUS_SCOPE": "no-such-expert"},
        )
        assert result.returncode == 0

    def test_a_sandbox_is_not_a_session(self, tmp_path):
        """Headless distillation and ingest runs are the machinery, not sessions in
        it — every hook returns early there."""
        result = run_guard(
            write_payload(f"{REPO}/src/thalamus/console/static/app.js"),
            tmp_path,
            {"CLAUDE_CODE_AGENT": "thalamus-designer", "THALAMUS_SANDBOX": "1"},
        )
        assert result.returncode == 0

    def test_both_verdicts_reach_the_guard_log(self, tmp_path):
        """The granularity audit reads this log: "never came near its own boundary"
        is evidence about a scope's partition exactly as a block is."""
        run_guard(
            write_payload(f"{REPO}/src/thalamus/console/static/app.js"),
            tmp_path,
            {"CLAUDE_CODE_AGENT": "thalamus-designer"},
        )
        run_guard(
            write_payload(f"{REPO}/docs/wireframe.svg"),
            tmp_path,
            {"CLAUDE_CODE_AGENT": "thalamus-designer"},
        )
        rows = [
            json.loads(line)
            for path in (tmp_path / ".thalamus" / "guards").glob("*.jsonl")
            for line in path.read_text().splitlines()
        ]
        assert {row["verdict"] for row in rows} == {"block", "pass"}
        assert all(row["guard"] == "role-boundary" for row in rows)
        blocked = next(row for row in rows if row["verdict"] == "block")
        assert blocked["pattern"] == "*.js"
        assert blocked["scope"] == "designer"


def test_the_guard_is_wired_into_the_installer():
    """A guard that ships uninstalled is prose with extra steps."""
    assert ("PreToolUse", "Edit|Write|NotebookEdit", "role-guard.sh") in HOOK_WIRING


def test_a_manifest_round_trips_the_boundary():
    """The field is tier-0 operator configuration; it has to survive the YAML."""
    manifest = ExpertManifest(
        scope="x", name="X", write_boundary={"deny_globs": ["*.py"], "reason": "because"}
    )
    assert manifest.write_boundary.denies("/a/b.py") == "*.py"
    assert manifest.write_boundary.reason == "because"
