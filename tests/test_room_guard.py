"""Room-boundary guard tests (docs/05 laundering; lab/044 why it is policy not structure).

Interfaces: src/thalamus/harness/hooks/claude-code/room-guard.sh, driven as the
harness drives it — JSON on stdin, exit 2 to block.
"""
import json
import subprocess
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "src" / "thalamus" / "harness" / "hooks" / "claude-code"


def run_guard(target, home, room=None, tool="SendMessage"):
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    if room is not None:
        env["THALAMUS_ROOM"] = room
    payload = {"tool_name": tool, "tool_input": {"to": target, "message": "hi"},
               "session_id": "s1", "cwd": str(home)}
    return subprocess.run(
        [str(HOOKS / "room-guard.sh")], input=json.dumps(payload),
        capture_output=True, text=True, env=env, timeout=30,
    )


class TestOutsideARoom:
    def test_no_room_means_no_opinion(self, tmp_path):
        """Arming this must change nothing for every session that exists today."""
        assert run_guard("some-other-session", tmp_path).returncode == 0

    def test_a_non_sendmessage_tool_is_ignored(self, tmp_path):
        assert run_guard("anything", tmp_path, room="alpha", tool="Bash").returncode == 0


class TestInsideARoom:
    def test_outsider_is_blocked(self, tmp_path):
        r = run_guard("payments-api-session", tmp_path, room="alpha")
        assert r.returncode == 2
        assert "not a member" in r.stderr
        # Verifies: the block names the sanctioned alternative, not just the refusal
        assert "consult_request" in r.stderr

    def test_roommate_passes(self, tmp_path):
        assert run_guard("alpha-literature", tmp_path, room="alpha").returncode == 0

    def test_roommate_with_ref_disambiguator_passes(self, tmp_path):
        assert run_guard("alpha-literature [3fa9c1]", tmp_path, room="alpha").returncode == 0

    def test_a_similarly_named_outsider_is_still_blocked(self, tmp_path):
        """`alphabet-x` must not pass as a member of room `alpha`."""
        assert run_guard("alphabet-x", tmp_path, room="alpha").returncode == 2


class TestSubagentsAreNotPeers:
    """SendMessage serves in-process subagents too — the consultation protocol
    runs over it. Blocking those would break the thing the room exists to protect.
    """

    def test_parent_conversation_passes(self, tmp_path):
        assert run_guard("main", tmp_path, room="alpha").returncode == 0

    def test_raw_agent_id_passes(self, tmp_path):
        assert run_guard("a88366f0740bb72e9", tmp_path, room="alpha").returncode == 0


class TestVerdictsAreEvents:
    def test_every_verdict_is_logged_with_its_branch(self, tmp_path):
        run_guard("alpha-literature", tmp_path, room="alpha")
        run_guard("outsider", tmp_path, room="alpha")
        rows = [json.loads(line) for line in
                sorted((tmp_path / ".thalamus" / "guards").glob("*.jsonl"))[0]
                .read_text().splitlines()]
        assert [r["verdict"] for r in rows] == ["pass", "block"]
        assert [r["branch"] for r in rows] == ["roommate", "outside-room"]
        assert all(r["room"] == "alpha" and r["guard"] == "room-boundary" for r in rows)
        # Verifies: the target is recorded, so the false-positive rate is measurable
        assert rows[1]["target"] == "outsider"
