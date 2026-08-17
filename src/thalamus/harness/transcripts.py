"""Claude Code transcript discovery, retention, and deterministic extraction.

Claude Code persists every session as JSONL under
`~/.claude/projects/<abs-cwd with '/' replaced by '-'>/<session-id>.jsonl`.

This module does the half of memory extraction that **needs no model at all**. Which
files a session edited, when, on which branch, with which tools, and in which messages —
that is all recorded exactly. An LLM would only be *worse* at it: it is ground truth, and
inference could only add error. What genuinely needs a model (decisions, problems,
solutions, threads — the *claims*) is left to the extraction skill.

The split matters beyond convenience. The deterministic layer gives every artifact a
real, anchored edge back to the exact tool call that touched it — so `docs/03`'s
provenance inspector works on bootstrapped data with no model in the loop, and the eval
loop gets a corpus it can trust to be free of extraction error.

One constraint worth knowing: **assistant reasoning is not persisted in plaintext.** A
thinking block on disk is an empty string plus an encrypted signature. Retained
transcripts carry user prompts, assistant prose, tool calls, and tool results — not the
private chain of thought.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from thalamus.archive import archive_bytes, archive_dir, scan_for_secrets
from thalamus.contract.ontology import MAIN_SCOPE
from thalamus.harness.agents import SANDBOX_TMP_PREFIX
from thalamus.substrate.schema import (
    Artifact,
    ArtifactType,
    ProjectEvidence,
    SessionGraph,
    Source,
    SourceKind,
    Tool,
    Touch,
)

CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"

# Tool inputs that name a file. Bash commands are deliberately NOT parsed for paths:
# guessing which words in a shell line are files is exactly the kind of inference this
# layer exists to avoid.
_PATH_INPUTS = ("file_path", "notebook_path")

# Tools whose results are external content crossing into the transcript — the ingress
# half of the transcript-mediated laundering channel (docs/05). Deliberately short and
# conservative: Read/Bash outputs are tier-1 observations of the operator's own machine
# (the docs/index Artifact argument), while these fetch from origins nobody curated.
# Bash *can* curl the web — that residual is documented in docs/05, not papered over
# with shell parsing this layer exists to avoid.
EXTERNAL_INGRESS_TOOLS = frozenset({"WebFetch", "WebSearch"})


@dataclass
class TranscriptFacts:
    """Everything recoverable from a transcript without a model."""

    session_id: str
    path: Path
    cwd: str = ""
    git_branch: str = ""
    title: str = ""
    first_prompt: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None
    message_count: int = 0
    user_turns: int = 0
    # The subset of `user_turns` that is the operator typing rather than invoking a
    # slash command. A command is a deliberate user turn — a `/teach` session is
    # nothing but commands and must still distill — but it is also what a session
    # consists of when the operator only checked `/usage` or hit `/clear`. Carrying
    # the two counts separately is what lets `has_substance` tell those apart.
    prompt_turns: int = 0
    tool_calls: int = 0
    # artifact identifier -> message UUIDs of the tool calls that touched it
    touched: dict[str, list[str]] = field(default_factory=dict)
    # Verbatim texts of tool results from EXTERNAL_INGRESS_TOOLS — the third-party
    # content embedded in this first-party transcript. The laundering floor (docs/05)
    # judges extracted claims against these.
    external_texts: list[str] = field(default_factory=list)

    # Which harness wrote the transcript these facts came from.
    harness: str = "claude-code"
    # Whether `external_texts` is *evidence* or merely *empty*. Claude Code embeds
    # tool results, so an empty list there means nothing was fetched. Cursor omits
    # tool outputs from transcripts entirely (harness/cursor_transcripts.py), so an
    # empty list there means we cannot know — and the mechanical half of the
    # laundering floor, the half no prompt content can lift, has nothing to run
    # against. Collapsing the two would delete that defence while appearing to
    # apply it, so the distinction is carried rather than inferred downstream.
    ingress_verifiable: bool = True
    # *Why* `ingress_verifiable` came out as it did. The floor has two behaviours, so
    # the bool above is right for the action; this is the verdict, and it is not
    # two-valued. Three decisions need to tell these apart that the bool cannot:
    # which sessions to re-run after a reader fix, what a format-drift monitor can
    # count — under a bool, a vendor format change arrives in the same channel as the
    # benign "this session has no store" — and what docs/05 is entitled to claim.
    # Values are `harness.cursor_store.StoreVerdict`; Claude Code embeds its results
    # in the transcript, so it is `verified` by construction.
    ingress_verdict: str = "verified"
    # The derived artifact retained in place of the vendor's store (docs/05, docs/10).
    # Empty for Claude Code, whose transcript *is* the retained evidence.
    ingress_receipt: dict = field(default_factory=dict)
    # Count of external-ingress tool *calls* seen. Present even when their results
    # are not, so an unverifiable session can still say whether it fetched at all.
    ingress_detected: int = 0
    # Records the reader could not classify at all. A parser written against a
    # format it has never observed must not absorb surprises quietly: silent
    # tolerance turns "the vendor changed the format" into "this session had fewer
    # turns", which is the failure this project keeps rediscovering. Recognition is
    # kept complete and separate from processing, and what falls outside it is
    # counted and surfaced rather than repaired (RFC 9413's virtuous intolerance;
    # LangSec, Momot et al., IEEE SecDev 2016 — both explicitly reject Postel's law
    # outside pre-declared extension points).
    unrecognized: int = 0

    # The checkout the session's cwd sat in, resolved at extraction time while that
    # cwd still exists. Empty when the session ran outside a repo — which is a real
    # state, not a gap: 11 of the sessions on this box ran from `$HOME` or `/tmp`.
    repo_root: str = ""

    @property
    def project(self) -> str:
        """The repo this session's work belongs to, or nothing.

        Derived from `repo_root`, never from `cwd`. A cwd basename answers a
        different question — *what is this directory called* — and answering the
        project question with it is what put a home-directory basename, `tmp`, `code`,
        a 64-char content hash and a media directory name into the graph as project
        names. The damage is not cosmetic: `project` is the anchor a repo-relative
        path is cut against, and a wrong anchor does not merely fail to merge, it
        *splits* — `/home/op/code/thalamus/docs/x.md` cuts at `/op/` while the
        relative spelling of the same file cuts nowhere, yielding two identities for
        one file (`substrate/artifact_audit.py`).

        Empty beats a guess for the same reason. A session that ran outside a repo has
        no project, and saying so leaves the anchor absent where an invented one would
        leave it wrong.
        """
        return Path(self.repo_root).name if self.repo_root else ""

    @property
    def has_substance(self) -> bool:
        """Is there an episode here worth paying a model to summarise?

        A transcript with no user turn at all has nothing to remember. Neither does
        one whose only turns are slash commands that the assistant never acted on:
        `/usage`, `/login`, `/model`, a bare `/clear`. Those pass the turn count
        because commands are counted as user turns on purpose — without that a
        `/teach` session, which is *only* commands, silently never distills
        (measured: ef3e3d6a, 87 assistant messages, ineligible). So the test is not
        "did the operator type prose" but "did anything happen": a typed prompt, or
        the assistant actually reaching for a tool. `/teach` passes on the second
        clause, a `/clear` on its own passes neither.

        Measured over the 133 transcripts on this box with a recorded distillation
        yield: blocks 20 of the 24 that extracted nothing usable, and blocks none of
        the 109 productive ones. The four junk sessions that survive it all carry a
        real typed prompt, and the extractor's own "no substantive content" verdict
        is the right and cheap backstop there — a structural test cannot know that
        `reply with the single word DONE` was not work.
        """
        return self.user_turns > 0 and (self.prompt_turns > 0 or self.tool_calls > 0)


def resolve_repo_root(cwd: str) -> str:
    """The checkout root containing `cwd`, or `""` — asked now, while it still exists.

    This runs at extraction time on purpose, and the result is stored rather than
    recomputed. A later filesystem walk is not an anchor but a time-dependent guess:
    measured over the 1,467 Artifact vertices carrying absolute paths, walking to the
    nearest `.git` today resolves 901 — 239 have lost the parent directory entirely
    and 327 still exist with no `.git` above them, because they are not repo files at
    all (`/tmp/claude-*/scratchpad`, `~/.claude/skills`). Recording the root when the
    session ends is the only version of this that is data.

    A **worktree resolves to the repository it belongs to**, not to itself. Worktrees
    here are a concurrency device — sessions share one checkout and take a worktree so
    their index and HEAD do not collide — and the work in one is work on the repo. Read
    off `--show-toplevel` a worktree is its own toplevel, which spent that device's
    cost twice: it minted a project per worktree (`frontend-orientation`,
    `console-deploy-path`), so one repo's memory landed in as many project buckets as
    it had concurrent sessions, and a recall naming the repo missed all of them.
    `--git-common-dir` is the same for every worktree of a repo and for the checkout
    itself, so its parent is the identity they share.

    Nested checkouts still resolve to the **inner** repo: a vendored subrepo has its
    own common dir, which is the right answer for a session working inside one.

    Every failure is `""`: no repo, no git, a cwd that no longer exists, a git that
    hangs. None of them are worth raising over — the caller's honest fallback for all
    four is the same, and this must never be the reason a session fails to distill.
    """
    if not cwd:
        return ""
    common = _git_out(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common:
        # `<repo>/.git` for a checkout and for every worktree of it. A bare repo has
        # no working tree to attribute, and its common dir has no `.git` to strip, so
        # it falls through to the toplevel probe and honestly resolves to nothing.
        root = Path(common)
        if root.name == ".git":
            return str(root.parent)
    return _git_out(cwd, "rev-parse", "--show-toplevel")


def _git_out(cwd: str, *args: str) -> str:
    """Stripped stdout of a successful `git <args>` in `cwd`, else `""`."""
    try:
        result = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def is_sandbox_project(name: str) -> bool:
    """Is this project dir the transcript of a Thalamus extraction sandbox?

    Claude Code names a project dir after the flattened cwd, so a sandbox run
    (`agents.SANDBOX_TMP_PREFIX`) is recognisable from the name alone — which is
    all a retroactive sweep has to go on, the environment marker having died with
    the subprocess. The test is a substring and not a path reconstruction: the
    flattening rewrites more than `/` (a sandbox at `/tmp/thalamus-extract-0_tez5it`
    lands under `-tmp-thalamus-extract-0-tez5it`), so only the prefix survives it
    unchanged.
    """
    return SANDBOX_TMP_PREFIX in name


def discover(projects_dir: Path | None = None) -> dict[str, list[Path]]:
    """Map project directory name -> its transcript files.

    Extraction sandboxes are not sessions and are never offered: distilling one
    writes memory about the act of remembering, and the sandbox's own headless run
    distills in turn.
    """
    root = projects_dir or CLAUDE_PROJECTS
    if not root.is_dir():
        return {}
    found: dict[str, list[Path]] = {}
    for project_dir in sorted(root.iterdir()):
        if not project_dir.is_dir() or is_sandbox_project(project_dir.name):
            continue
        transcripts = sorted(project_dir.glob("*.jsonl"))
        if transcripts:
            found[project_dir.name] = transcripts
    return found


# How far into a transcript to look for the session's own id. It rides on nearly
# every record, so a session that carries none in its opening stretch carries none
# at all — and reading further is a full scan of every archived file.
_ID_SCAN_RECORDS = 40


def _archived_session_id(path: Path) -> str:
    for index, record in enumerate(_records(path)):
        if index >= _ID_SCAN_RECORDS:
            break
        session_id = record.get("sessionId")
        if session_id:
            return str(session_id)
    return ""


def archived_transcripts(archive_base: Path | None = None) -> dict[str, Path]:
    """Map session id -> its retained transcript, for the sessions ~/.claude has lost.

    `retain()` copies transcripts here precisely because Claude Code rotates its own,
    so a recovery that could only read `~/.claude/projects` would still lose a session
    the day the harness rotated it — the failure retention exists to prevent.

    The id has to come from the records: an archived transcript is named for its
    content hash, and a file named for its bytes cannot be found by session. The same
    session is re-retained under a new hash as its transcript grows, so several files
    can carry one id; the largest is the most complete and wins.
    """
    root = archive_base or archive_dir()
    if not root.is_dir():
        return {}
    found: dict[str, Path] = {}
    for path in sorted(root.glob("*/*.jsonl")):
        session_id = _archived_session_id(path)
        if not session_id:
            continue
        held = found.get(session_id)
        if held is None or path.stat().st_size > held.stat().st_size:
            found[session_id] = path
    return found


def tool_result_text(block: dict) -> str:
    """The text of a tool_result content block, whichever shape the harness wrote."""
    content = block.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        ]
        return " ".join(p.strip() for p in parts if p.strip())
    return ""


def parse(path: Path, *, session_id: str | None = None) -> TranscriptFacts:
    """Read a transcript and recover every fact that needs no inference.

    A live transcript is named for its session, so the filename is the identity. An
    archived one is named for its content hash, and the caller that found it by id
    passes that id back in rather than letting the hash become the session's name.
    """
    facts = TranscriptFacts(session_id=session_id or path.stem, path=path)
    external_tool_uses: set[str] = set()

    for record in _records(path):
        record_type = record.get("type")

        # Claude Code writes its own session title. Free, and better than a first-line
        # heuristic — no reason to make a model regenerate what is already on disk.
        if record_type == "ai-title" and record.get("aiTitle"):
            facts.title = record["aiTitle"]
            continue

        # FIRST cwd wins, not the last. Claude Code files a transcript under the dir
        # named for the cwd the session *started* in, so taking the last one lets a
        # session that moved be filed under one project and attributed to another, and
        # makes the attribution depend on where the session happened to stop rather
        # than on what it worked on. The SessionEnd hook already resolves the project
        # *dir* from the transcript's own location for exactly this reason; this is the
        # same rule applied to the project *name*.
        #
        # Moving between worktrees of one repo no longer changes the answer —
        # `resolve_repo_root` maps every one of them to the repository — so what this
        # rule now guards is the session that `cd`s into a *different* checkout.
        #
        # `git_branch` is deliberately still last-wins: cwd answers "which project is
        # this session's", which is fixed when the transcript is filed, while the
        # branch answers "what was the work on", and a session that switched branches
        # did its work on the later one.
        if record.get("cwd") and not facts.cwd:
            facts.cwd = record["cwd"]
        if record.get("gitBranch"):
            facts.git_branch = record["gitBranch"]

        timestamp = _timestamp(record.get("timestamp"))
        if timestamp:
            facts.started_at = min(facts.started_at or timestamp, timestamp)
            facts.ended_at = max(facts.ended_at or timestamp, timestamp)

        if record_type not in ("user", "assistant"):
            continue
        if record.get("isSidechain") or record.get("isMeta"):
            continue  # subagent sidechains are their own episodes, not this one

        facts.message_count += 1
        content = (record.get("message") or {}).get("content")

        if record_type == "user":
            if isinstance(content, str):
                text = content
                stripped = text.lstrip()
                # A "<"-prefixed record is harness scaffolding (caveats, system
                # reminders), not the user speaking — except a slash-command
                # invocation, which is a deliberate user turn. Without this, a
                # session driven purely by slash commands (/teach lessons) has
                # zero countable turns and silently never distills (measured:
                # ef3e3d6a, 87 assistant messages, ineligible).
                is_command = stripped.startswith("<command-name>") or (
                    stripped.startswith("<") and "<command-name>" in stripped[:200]
                )
                if text and (not stripped.startswith("<") or is_command):
                    facts.user_turns += 1
                    if not is_command:
                        facts.prompt_turns += 1
                    if not facts.first_prompt:
                        facts.first_prompt = text.strip()
                continue
            # Tool results ride in user-type records. Results of external-ingress
            # tools are third-party content inside a first-party transcript —
            # collected verbatim so the laundering floor can judge claims against
            # them (docs/05).
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                if block.get("tool_use_id") not in external_tool_uses:
                    continue
                text = tool_result_text(block)
                if text:
                    facts.external_texts.append(text)
            continue

        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            facts.tool_calls += 1
            if block.get("name") in EXTERNAL_INGRESS_TOOLS and block.get("id"):
                external_tool_uses.add(block["id"])
            tool_input = block.get("input") or {}
            for key in _PATH_INPUTS:
                identifier = tool_input.get(key)
                if not identifier:
                    continue
                anchors = facts.touched.setdefault(str(identifier), [])
                uuid = record.get("uuid")
                if uuid and uuid not in anchors:
                    anchors.append(uuid)

    # Once, after the cwd is settled — not per record, and not lazily on read. `project`
    # is derived from this, so resolving it here is what makes the derivation a fact
    # about when the session ran rather than about when someone later asked.
    facts.repo_root = resolve_repo_root(facts.cwd)
    return facts


def retain(path: Path, *, archive_base: Path | None = None):
    """Copy a transcript into the immutable archive. Returns (entry, secret findings).

    Thalamus owns the bytes from here on. Claude Code rotates and compacts its own
    transcripts, so a pointer into ~/.claude/projects would rot — and evidence that can
    disappear is not evidence.
    """
    payload = path.read_bytes()
    entry = archive_bytes(payload, suffix=".jsonl", base=archive_base)
    return entry, scan_for_secrets(payload)


def retain_ingress_receipt(facts: TranscriptFacts, *, archive_base: Path | None = None):
    """Archive the derived ingress artifact, if this harness produced one.

    Returns the `ArchiveEntry` or None. Claude Code produces none: its transcript
    already *is* the retained bytes the floor judged against, and `retain()` above
    keeps it. Cursor's evidence lives in a store we deliberately do not retain whole
    (`cursor_store.receipt`), so what the chain reaches is this receipt instead.
    """
    if not facts.ingress_receipt:
        return None
    payload = json.dumps(facts.ingress_receipt, indent=2, sort_keys=True).encode()
    return archive_bytes(payload, suffix=".ingress.json", base=archive_base)


def to_session_graph(
    facts: TranscriptFacts,
    *,
    content_hash: str,
    uri: str,
    byte_size: int,
    scope: str = MAIN_SCOPE,
    room: str = "",
    forked_from: str = "",
) -> SessionGraph:
    """Build the deterministic half of a session's memory. No model involved.

    Produces: the Source (its own transcript), the Session, every Artifact it touched, and
    the anchored TOUCHES edges between them. Claims and Threads are left empty — those need
    judgement, and this layer refuses to guess.
    """
    identifiers = sorted(facts.touched)
    timestamp = facts.ended_at or facts.started_at or datetime.now()

    source = Source(
        content_hash=content_hash,
        kind=SourceKind.TRANSCRIPT,
        title=facts.title or f"Session {facts.session_id[:8]}",
        uri=uri,
        origin=str(facts.path),
        byte_size=byte_size,
        message_count=facts.message_count,
    )

    return SessionGraph(
        session_id=facts.session_id,
        timestamp=timestamp,
        tool=Tool.CLAUDE_CODE,
        scope=scope,
        project=facts.project or None,
        # Set from the same expression that produced the value, so the two cannot drift.
        # A second derivation elsewhere would be a claim about this one rather than a
        # record of it.
        project_evidence=ProjectEvidence.CWD if facts.project else None,
        cwd=facts.cwd,
        repo_root=facts.repo_root,
        room=room,
        forked_from=forked_from,
        summary=_summary(facts),
        sources=[source],
        artifacts=[
            Artifact(
                identifier=identifier,
                type=ArtifactType.FILE,
                project=facts.project or None,
            )
            for identifier in identifiers
        ],
        touched=[
            Touch(identifier=identifier, anchors=facts.touched[identifier])
            for identifier in identifiers
        ],
    )


def _summary(facts: TranscriptFacts) -> str:
    """A summary we can stand behind without a model.

    Claude Code's own `ai-title` is the headline; the opening prompt supplies the intent.
    Honest and cheap. A real distillation is the extraction skill's job, and when it runs,
    it overwrites this — the transcript is retained, so re-extraction is always available.
    """
    title = facts.title or f"Session {facts.session_id[:8]}"
    if facts.first_prompt:
        opening = " ".join(facts.first_prompt.split())[:180]
        return f"{title} — opened with: {opening}"
    return title


def _records(path: Path):
    with path.open(errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _timestamp(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
