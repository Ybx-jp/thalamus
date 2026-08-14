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

from thalamus.contract.manifest import (
    ROSTER_CAPABILITY_DEFAULT,
    CapabilityBoundary,
    ExpertManifest,
    WriteBoundary,
    load_manifest,
)
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


class TestCapabilityBoundary:
    def test_an_undeclared_boundary_inherits_the_roster_default(self):
        """The opposite of WriteBoundary's default, and the whole design rests on
        it: the operator's decision was roster-wide, so silence means inherit. A
        caller reading the raw field would unbind every scope but `designer`."""
        manifest = ExpertManifest(scope="x", name="X")
        assert manifest.capability_boundary is None
        assert manifest.effective_capability_boundary is ROSTER_CAPABILITY_DEFAULT

    def test_an_explicit_empty_block_is_the_opt_out(self):
        """Three states, each with a written meaning. Without this one, a scope
        whose charter IS design has no way to say so."""
        manifest = ExpertManifest(scope="x", name="X", capability_boundary={})
        assert manifest.effective_capability_boundary.denies_tool("Artifact") is None
        assert manifest.effective_capability_boundary.denies_skill("artifact-design") is None

    def test_skills_match_by_glob_so_an_upstream_rename_still_lands(self):
        """The skill namespace is owned upstream and can be renamed or split without
        warning; equality matching would fail silently toward permitting."""
        boundary = CapabilityBoundary(deny_skills=["artifact-*", "frontend-design*"])
        assert boundary.denies_skill("artifact-design") == "artifact-*"
        assert boundary.denies_skill("artifact-design-web") == "artifact-*"
        assert boundary.denies_skill("frontend-design:frontend-design") == "frontend-design*"
        assert boundary.denies_skill("recall-strategy") is None

    def test_the_roster_default_covers_the_design_surface(self):
        """Named individually: a bundled assertion cannot say which half failed."""
        for skill in ("artifact-design", "artifact-diagramming", "artifact-capabilities",
                      "frontend-design:frontend-design", "dataviz", "author-repo-diagram"):
            assert ROSTER_CAPABILITY_DEFAULT.denies_skill(skill), f"{skill} is design work"
        assert ROSTER_CAPABILITY_DEFAULT.denies_tool("Artifact")

    def test_it_leaves_the_working_skills_alone(self):
        """A capability boundary that caught the skills an expert needs to do its job
        would teach route-around, which lab/008 prices above the gap it closes."""
        for skill in ("recall-strategy", "gremlin-python", "ground-in-literature",
                      "consult-an-expert", "add-roster-expert"):
            assert ROSTER_CAPABILITY_DEFAULT.denies_skill(skill) is None
        for tool in ("Read", "Write", "Bash", "Task"):
            assert ROSTER_CAPABILITY_DEFAULT.denies_tool(tool) is None

    def test_an_empty_name_is_not_a_match(self):
        """Payloads reach the guard without a skill name; they are not invocations."""
        boundary = CapabilityBoundary(deny_skills=["*"], deny_tools=["*"])
        assert boundary.denies_skill("") is None
        assert boundary.denies_tool("") is None


class TestShippedCapabilityBoundaries:
    def test_designer_is_the_one_scope_that_opts_out(self):
        boundary = load_manifest("designer").effective_capability_boundary
        assert boundary.denies_tool("Artifact") is None
        assert boundary.denies_skill("author-repo-diagram") is None

    @pytest.mark.parametrize(
        "scope", ["qe", "architect", "literature", "eval-methodology", "homelab", "teacher"]
    )
    def test_every_other_pinned_scope_inherits_the_deny(self, scope):
        """Declared once, inherited everywhere — the property that makes storing it
        once safe rather than merely tidy."""
        boundary = load_manifest(scope).effective_capability_boundary
        assert boundary.denies_skill("artifact-design")
        assert boundary.denies_tool("Artifact")

    def test_the_default_explains_itself_and_names_the_alternative(self):
        """A block that cannot say what to do instead teaches route-around."""
        reason = ROSTER_CAPABILITY_DEFAULT.reason
        assert reason.strip()
        assert "markdown" in reason.lower()


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

    def test_main_reaches_no_manifest_on_an_unowned_path(self, tmp_path):
        """`main` has no manifest by design, so the short-circuit still returns before
        anything loads one — the 151ms import this exemption exists to avoid.

        It is no longer the *first* thing the guard does. An owned path is tested
        ahead of it, because ownership is the one rule that must bind `main` too, and
        that test is deliberately cheap enough to sit on the hot path
        (`contract/ownership.py`). This asserts what survives: an unowned target in a
        `main` session still reaches no manifest."""
        result = run_guard(write_payload(f"{REPO}/src/thalamus/cli.py"), tmp_path)
        assert result.returncode == 0

    def test_a_scope_with_no_boundary_is_unaffected(self, tmp_path):
        result = run_guard(
            write_payload(f"{REPO}/src/thalamus/cli.py"),
            tmp_path,
            {"CLAUDE_CODE_AGENT": "thalamus-architect"},
        )
        assert result.returncode == 0

    def test_a_subagent_is_bound_by_its_own_scope_not_its_launcher(self, tmp_path):
        """A subagent inherits its launcher's environment wholesale, so both env
        channels name whoever spawned it. Only the payload's `agent_type` names the
        agent actually running, and it wins. Measured 2026-08-11 over 1132 subagent
        tool calls: env-only resolution named the right scope 6.4% of the time."""
        payload = write_payload(f"{REPO}/src/thalamus/console/static/app.js")
        payload["agent_type"] = "thalamus-designer"
        result = run_guard(payload, tmp_path, {"THALAMUS_SCOPE": "main"})
        assert result.returncode == 2
        assert "*.js" in result.stderr

    def test_a_generic_subagent_still_inherits_the_pin(self, tmp_path):
        """`Explore` and `general-purpose` name no manifest, so resolution falls
        through to the launcher's pin. Short-circuiting on any agent_type instead
        would make `Agent(subagent_type="general-purpose")` a one-line route around
        every boundary in the roster."""
        payload = write_payload(f"{REPO}/src/thalamus/console/static/app.js")
        payload["agent_type"] = "general-purpose"
        result = run_guard(payload, tmp_path, {"CLAUDE_CODE_AGENT": "thalamus-designer"})
        assert result.returncode == 2

    def test_it_blocks_a_design_skill_from_a_bounded_scope(self, tmp_path):
        """The incident this boundary answers: a pinned expert reaching for the
        design skills and spending its charter on presentation."""
        payload = {
            "session_id": "rg-1",
            "cwd": str(REPO),
            "tool_name": "Skill",
            "tool_input": {"skill": "artifact-design"},
        }
        result = run_guard(payload, tmp_path, {"CLAUDE_CODE_AGENT": "thalamus-qe"})
        assert result.returncode == 2
        assert "artifact-*" in result.stderr

    def test_it_passes_a_design_skill_for_the_designer(self, tmp_path):
        payload = {
            "session_id": "rg-1",
            "cwd": str(REPO),
            "tool_name": "Skill",
            "tool_input": {"skill": "author-repo-diagram"},
        }
        result = run_guard(payload, tmp_path, {"CLAUDE_CODE_AGENT": "thalamus-designer"})
        assert result.returncode == 0

    def test_it_passes_a_working_skill_for_a_bounded_scope(self, tmp_path):
        payload = {
            "session_id": "rg-1",
            "cwd": str(REPO),
            "tool_name": "Skill",
            "tool_input": {"skill": "recall-strategy"},
        }
        result = run_guard(payload, tmp_path, {"CLAUDE_CODE_AGENT": "thalamus-qe"})
        assert result.returncode == 0

    def test_it_blocks_artifact_publishing_from_a_bounded_scope(self, tmp_path):
        payload = {
            "session_id": "rg-1",
            "cwd": str(REPO),
            "tool_name": "Artifact",
            "tool_input": {"file_path": f"{REPO}/qe-triage.html", "favicon": "🔬"},
        }
        result = run_guard(payload, tmp_path, {"CLAUDE_CODE_AGENT": "thalamus-qe"})
        assert result.returncode == 2
        assert "Artifact" in result.stderr

    def test_listing_artifacts_stays_open(self, tmp_path):
        """Listing is read-only. A scope that may not publish may still see what
        exists, or it cannot even tell the operator what it would have written."""
        payload = {
            "session_id": "rg-1",
            "cwd": str(REPO),
            "tool_name": "Artifact",
            "tool_input": {"action": "list"},
        }
        result = run_guard(payload, tmp_path, {"CLAUDE_CODE_AGENT": "thalamus-qe"})
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
    """A guard that ships uninstalled is prose with extra steps.

    The matcher is asserted per tool rather than as one string: a boundary the guard
    enforces but the installer never routes to it is exactly the silent gap this
    test exists to catch, and an equality assertion hides which tool went missing.
    """
    matchers = [m for event, m, script in HOOK_WIRING
                if (event, script) == ("PreToolUse", "role-guard.sh")]
    assert len(matchers) == 1, "the role guard should be wired exactly once"
    wired = set(matchers[0].split("|"))
    for tool in ("Edit", "Write", "NotebookEdit", "Skill", "Artifact"):
        assert tool in wired, f"{tool} is bounded by the guard but never routed to it"


def test_a_manifest_round_trips_the_boundary():
    """The field is tier-0 operator configuration; it has to survive the YAML."""
    manifest = ExpertManifest(
        scope="x", name="X", write_boundary={"deny_globs": ["*.py"], "reason": "because"}
    )
    assert manifest.write_boundary.denies("/a/b.py") == "*.py"
    assert manifest.write_boundary.reason == "because"
