"""Budget guard — a scope's `budget` preset, enforced from the hooks.

The counting is done here, from the tool hooks Claude Code and codex both fire. Past a
cap the model is told to answer, and every further tool call in the prompt is denied:

| key | counted at | Claude Code | codex |
|---|---|---|---|
| `max_turns` | `PostToolBatch` | told to answer before its next request | not enforced: no batch event |
| `max_tool_calls` | `PreToolUse` | the call denied, told to answer | the same |
| `max_tokens` | `PreToolUse` | the call denied, told to answer | the same |
| `max_subagent_tokens` | `PreToolUse` | the call denied, told to answer | not enforced |
| `max_tool_output_tokens` | launch | env vars on the pin's argv | `tool_output_token_limit` in the profile |

A model that keeps calling tools after it was told is stopped after
`FORCED_ANSWER_DENIALS` more denials on Claude Code. A codex hook has no stop — a
`PreToolUse` hook returning `continue: false` is marked failed and the call goes ahead
— so there every further call is denied and nothing more (A0179, cites-as-live).

**Turns and tool calls reset with each prompt; tokens do not.** A stop ends the prompt,
not the session — the operator can type again — so a lifetime turn counter would stop
every later prompt after its first call. The prompt is Claude Code's `prompt_id` or
codex's `turn_id`; a payload with neither (Cursor running this script off Claude
Code's settings file) is not counted, since a counter that never resets is a session
that can no longer act. Counters are per agent as well: a subagent's calls carry the
launcher's `session_id` and their own `agent_id`, so each spawned run has its own
count and does not spend the session's (A0179, cites-as-live).

Tokens are the model requests' input (cached or not) plus output — codex's own
`total_tokens`, and on Claude Code the four `usage` fields summed over the transcript,
once per message id, since the transcript repeats one message's usage on every content
block it writes. Both transcripts are written behind the hook, so the count lags by up
to one model request. Two token caps, because a session and one of its subagents are
different spends (A0186, cites-as-live):

- `max_tokens` is the session's total: the session's own transcript plus every
  subagent's. A subagent's tool events name the launcher's transcript, and its own
  spend is only in `<session>/subagents/agent-<agent_id>.jsonl` beside it (A0174,
  cites-as-live), so the total is that transcript and every file in that folder. The
  cap is recorded the first time the session's own hook reads it, and binds a subagent
  spawned as another expert whose preset has none.
- `max_subagent_tokens` is one subagent run's own spend, its file alone.

A codex session's total is its own rollout; where codex writes a subagent's spend has
not been measured, so codex subagents are neither added nor capped.

**A spent cap forces an answer rather than cutting the run off.** A stop leaves a
subagent with no reply for its launcher and a session with no account of where it got
to, and a cap exists to bound spend, not to lose the work. So past a tool-call or token
cap the call is denied with a reason saying it was not run and asking for an answer
now, and past the turn cap `PostToolBatch` injects the same request before the next
model call (A0188, cites-as-live); a model that answers makes no further request.
smolagents does the same at its step limit, asking the model for a final answer rather
than raising (`MultiStepAgent.provide_final_answer`) (A0179, cites-as-live).

Limits come from the scope's manifest (`budget:` → `presets/budget.yaml`), and a
`THALAMUS_MAX_*` variable in the environment overrides the preset key it names — for
the whole process tree, subagents included, since they inherit it. A budget is a cost
control and not a boundary, so a config this cannot read fails open with a line on
stderr rather than stopping a session that did nothing wrong.

Prior work: the Claude Agent SDK's `max_turns`/`max_budget_usd` and the OpenAI Agents
SDK's `max_turns` cap a run the SDK itself drives; this caps a run a harness drives, from
outside it, which is the situation neither covers.
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

STATE_DIR = Path.home() / ".thalamus" / "budget"

# The environment overrides, one per preset key the hooks enforce.
ENV_OVERRIDES = {
    "max_turns": "THALAMUS_MAX_TURNS",
    "max_tool_calls": "THALAMUS_MAX_TOOL_CALLS",
    "max_tokens": "THALAMUS_MAX_TOKENS",
    "max_subagent_tokens": "THALAMUS_MAX_SUBAGENT_TOKENS",
}

# Denials past a token cap before the prompt is stopped outright: the room a model gets
# to answer after being told to, before a stop takes it.
FORCED_ANSWER_DENIALS = 3

# Claude Code reads a tool result's size cap from three variables, one per tool
# family, and the Bash one counts characters. Four characters a token is the
# vendor's own rule of thumb; the Bash cap is clamped to its documented ceiling.
CHARS_PER_TOKEN = 4
BASH_MAX_OUTPUT_CEILING = 150_000


def limits(scope: str, config_root: Path, environ: Mapping[str, str]) -> dict[str, int]:
    """The caps that bind `scope`: its budget preset, then the environment over it."""
    from thalamus.contract.capabilities import BUDGET, INHERIT, read_presets

    import yaml

    out: dict[str, int] = {}
    manifest = config_root / "experts" / f"{scope}.yaml"
    if manifest.is_file():
        name = (yaml.safe_load(manifest.read_text()) or {}).get("budget", INHERIT)
        presets = read_presets(BUDGET, config_root / "presets" / "budget.yaml")
        out = {k: int(v) for k, v in BUDGET.resolve(name, presets).sets.items()}
    for key, var in ENV_OVERRIDES.items():
        value = environ.get(var, "")
        if value:
            out[key] = int(BUDGET.preset("env", {key: value}).sets[key])
    return out


def claude_output_env(sets: Mapping[str, str]) -> dict[str, str]:
    """A preset's `max_tool_output_tokens` as the variables Claude Code reads it from."""
    if "max_tool_output_tokens" not in sets:
        return {}
    tokens = int(sets["max_tool_output_tokens"])
    return {
        "BASH_MAX_OUTPUT_LENGTH": str(min(tokens * CHARS_PER_TOKEN, BASH_MAX_OUTPUT_CEILING)),
        "MAX_MCP_OUTPUT_TOKENS": str(tokens),
        "CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS": str(tokens),
    }


def launch_env(harness: str, scope: str, config_root: Path) -> dict[str, str]:
    """What a pinned launch of `scope` must carry in its environment for its budget.

    Only Claude Code takes anything here: its tool-result caps are environment
    variables read at startup (A0185, cites-as-live). codex reads its cap from the
    scope's profile (`pin.render_codex_profile`). A subagent inherits its launcher's
    environment, so this caps a pinned session and every subagent it spawns alike.
    """
    if harness != "claude":
        return {}
    try:
        sets = limits(scope, config_root, {})
    except (OSError, ValueError):
        return {}
    return claude_output_env({k: str(v) for k, v in sets.items()})


def _claude_tokens(transcript: Path, seen: dict) -> int:
    """Tokens processed so far, read on from where the last call stopped.

    `seen` is the state carried between calls: the byte offset read to, the running
    total, and the message ids already counted.
    """
    offset, total = seen.get("offset", 0), seen.get("total", 0)
    ids = set(seen.get("ids", []))
    try:
        with transcript.open("rb") as f:
            f.seek(offset)
            chunk = f.read()
    except OSError:
        return total
    end = chunk.rfind(b"\n") + 1
    for line in chunk[:end].splitlines():
        try:
            message = json.loads(line).get("message") or {}
        except (ValueError, AttributeError):
            continue
        usage = message.get("usage") if isinstance(message, dict) else None
        if not usage or message.get("id") in ids:
            continue
        ids.add(message.get("id"))
        total += sum(int(usage.get(k) or 0) for k in (
            "input_tokens", "cache_creation_input_tokens",
            "cache_read_input_tokens", "output_tokens"))
    seen.update(offset=offset + end, total=total, ids=sorted(i for i in ids if i))
    return total


def _codex_tokens(transcript: Path, seen: dict) -> int:
    """codex's own running total: the last `token_count` event's `total_tokens`."""
    offset, total = seen.get("offset", 0), seen.get("total", 0)
    try:
        with transcript.open("rb") as f:
            f.seek(offset)
            chunk = f.read()
    except OSError:
        return total
    end = chunk.rfind(b"\n") + 1
    for line in chunk[:end].splitlines():
        if b'"token_count"' not in line:
            continue
        try:
            info = (json.loads(line).get("payload") or {}).get("info") or {}
            total = int(info["total_token_usage"]["total_tokens"])
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    seen.update(offset=offset + end, total=total)
    return total


def _claude_session_tokens(transcript: Path, reads: dict) -> int:
    """The session's total: its own transcript and every subagent's beside it."""
    files = [transcript, *sorted((transcript.with_suffix("") / "subagents").glob("agent-*.jsonl"))]
    return sum(_claude_tokens(f, reads.setdefault(f.name, {})) for f in files)


def _spent(payload: Mapping, harness: str, agent: str, caps: Mapping[str, int],
           state: dict) -> str | None:
    """The token cap this event is past, described, or None."""
    transcript = payload.get("transcript_path")
    if not transcript:
        return None
    transcript = Path(transcript)
    reads = state.setdefault("reads", {})
    if agent == "main" and "max_tokens" in caps:
        state["session_cap"] = caps["max_tokens"]
    session_caps = [c for c in (caps.get("max_tokens"), state.get("session_cap")) if c]
    if session_caps:
        cap = min(session_caps)
        spent = (_codex_tokens(transcript, reads.setdefault(transcript.name, {}))
                 if harness == "codex" else _claude_session_tokens(transcript, reads))
        if spent >= cap:
            return f"{cap:,} tokens for this session ({spent:,} spent)"
    cap = caps.get("max_subagent_tokens")
    if cap and agent != "main" and harness != "codex" and "/" not in agent:
        own = transcript.with_suffix("") / "subagents" / f"agent-{agent}.jsonl"
        spent = _claude_tokens(own, reads.setdefault(own.name, {}))
        if spent >= cap:
            return f"{cap:,} tokens for this subagent ({spent:,} spent)"
    return None


def decide(payload: Mapping, harness: str, caps: Mapping[str, int], state: dict) -> dict | None:
    """Count this event against `caps`, updating `state`; the hook's output, or None.

    `state` is the session's record: per agent, the prompt being counted, its turns
    and tool calls, the cap it has spent and the denials since; per transcript, the
    reading so far; and the session's own token cap once its hook has read it.
    """
    event = payload.get("hook_event_name")
    prompt = payload.get("prompt_id") or payload.get("turn_id")
    if not prompt or event not in ("PreToolUse", "PostToolBatch"):
        return None
    agent = payload.get("agent_id") or "main"
    counts = state.setdefault("agents", {}).setdefault(agent, {})
    if counts.get("prompt") != prompt:
        counts.clear()
        counts["prompt"] = prompt

    if event == "PostToolBatch":
        counts["turns"] = counts.get("turns", 0) + 1
        cap = caps.get("max_turns")
        if counts.get("spent") or cap is None or counts["turns"] < cap:
            return None
        counts["spent"] = f"{cap} turns for this prompt"
        return {"hookSpecificOutput": {
            "hookEventName": "PostToolBatch",
            "additionalContext": _answer_now(counts["spent"]),
        }}

    counts["tool_calls"] = counts.get("tool_calls", 0) + 1
    over = counts.get("spent")
    cap = caps.get("max_tool_calls")
    if over is None and cap is not None and counts["tool_calls"] > cap:
        over = f"{cap} tool calls for this prompt"
    if over is None:
        over = _spent(payload, harness, agent, caps, state)
    if over is None:
        return None
    counts["spent"] = over
    counts["denied"] = counts.get("denied", 0) + 1
    # "Not run" is said outright: told only to answer, a model reported the output of
    # the very call this denied.
    reason = f"{_answer_now(over)} This tool call was not run."
    decision: dict = {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}
    if harness != "codex" and counts["denied"] > FORCED_ANSWER_DENIALS:
        # Deny alone blocks the call and lets the prompt run on; `continue: false`
        # alone stops the prompt only after the call has run. Both are needed.
        decision.update({"continue": False, "stopReason": (
            f"Thalamus budget reached: {over}, and the model kept calling tools after "
            f"it was told to answer. The operator can raise the budget or send a new "
            f"prompt.")})
    return decision


def _answer_now(over: str) -> str:
    return (f"Thalamus budget reached: {over}. Do not call another tool. Answer now "
            f"with what is done and what is left.")


def main(argv: list[str]) -> int:
    """The hook body: `python -m thalamus.harness.budget <harness> <scope> <config_root>`,
    payload on stdin, the hook's JSON output on stdout."""
    harness, scope, config_root = argv
    try:
        payload = json.load(sys.stdin)
        caps = limits(scope, Path(config_root), os.environ)
    except Exception as exc:  # a budget fails open; see the module docstring
        print(f"thalamus budget: not enforced ({exc})", file=sys.stderr)
        return 0
    session = str(payload.get("session_id") or "")
    if not session or "/" in session:
        return 0
    path = STATE_DIR / f"{session}.json"
    # A scope with no caps of its own is still held to its session's total, which the
    # session's own hook recorded in this file.
    if not caps and not path.is_file():
        return 0
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "a+") as f:
        # Parallel tool calls fire PreToolUse concurrently; the lock is what makes the
        # count a count.
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        try:
            state = json.loads(f.read() or "{}")
        except ValueError:
            state = {}
        out = decide(payload, harness, caps, state)
        f.seek(0)
        f.truncate()
        f.write(json.dumps(state))
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
