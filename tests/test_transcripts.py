"""
Deterministic transcript extraction tests.

Interfaces: thalamus.harness.transcripts.parse, to_session_graph;
            thalamus.harness.bootstrap.bootstrap_project, bootstrap_cursor
Infrastructure: none; synthetic JSONL in tmp_path
Scope: the half of extraction that needs no model, and the anchors it recovers
"""

import json
import subprocess
from pathlib import Path

from thalamus.contract.conformance import check_session
from thalamus.harness import cursor_transcripts, transcripts
from thalamus.harness.bootstrap import bootstrap_cursor, bootstrap_project
from thalamus.substrate.schema import ProjectEvidence, Tier, Tool


def _write_transcript(directory, session_id, records):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{session_id}.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    return path


def _git_repo(path) -> str:
    """A real checkout at `path`, returned as the string a transcript's `cwd` holds.

    Real rather than mocked because `project` is now `git rev-parse --show-toplevel`
    resolved at extraction time, and the whole point of that design is that the answer
    comes from the filesystem as it was. A test that patches the resolver would pass
    against a derivation that never runs.
    """
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True, capture_output=True)
    return str(path)


def _transcript_records(cwd: str = "/home/dev/chartgen"):
    return [
        {"type": "ai-title", "aiTitle": "Fix the fatigue governor"},
        {
            "type": "user",
            "uuid": "u1",
            "timestamp": "2026-07-01T10:00:00Z",
            "cwd": cwd,
            "gitBranch": "main",
            "message": {"content": "the governor is clamping too early"},
        },
        {
            "type": "assistant",
            "uuid": "a1",
            "timestamp": "2026-07-01T10:01:00Z",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "src/governor.py"}},
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "src/model.py"}},
                ]
            },
        },
        {
            "type": "assistant",
            "uuid": "a2",
            "timestamp": "2026-07-01T10:02:00Z",
            "message": {
                "content": [
                    # Same file, second time — the anchor list must grow, not overwrite.
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "src/governor.py"}},
                ]
            },
        },
        {
            # A subagent sidechain is its own episode, not part of this one.
            "type": "assistant",
            "uuid": "a3",
            "isSidechain": True,
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "src/other.py"}}
                ]
            },
        },
    ]


def test_tool_calls_recover_touched_files_and_their_message_anchors(tmp_path):
    """
    Scenario: Parse a transcript in which two files were touched, one of them twice

    Verifications:
    - every touched file is recovered, with no model in the loop
    - repeat touches accumulate anchors rather than overwriting
    - subagent sidechains are excluded

    "Which files did this session edit, in which messages" is recorded exactly. An LLM
    could only add error here, so it is not asked.
    """
    checkout = _git_repo(tmp_path / "chartgen")
    path = _write_transcript(tmp_path / "proj", "s1", _transcript_records(cwd=checkout))

    facts = transcripts.parse(path)

    # Verifies: exact recovery, sidechain excluded
    assert set(facts.touched) == {"src/governor.py", "src/model.py"}
    # Verifies: anchors accumulate — this is what makes the provenance walk land on evidence
    assert facts.touched["src/governor.py"] == ["a1", "a2"]
    assert facts.touched["src/model.py"] == ["a1"]
    assert facts.title == "Fix the fatigue governor"
    assert facts.project == "chartgen"
    assert facts.repo_root == checkout
    # The evidence rides with the value, set from the same expression that produced it
    # — a second derivation elsewhere would be a claim about this one, not a record.
    built = transcripts.to_session_graph(facts, content_hash="h", uri="u", byte_size=1)
    assert built.project == "chartgen"
    assert built.project_evidence is ProjectEvidence.CWD
    assert facts.git_branch == "main"
    assert facts.user_turns == 1


def test_a_session_outside_any_checkout_has_no_project(tmp_path):
    """
    Scenario: A session whose cwd is a real directory that is not in a git repo

    `project` used to be the cwd's basename unconditionally, which is how `ybx`, `tmp`,
    `code`, a 64-char content hash and an Avatar episode title became project names on
    3,078 vertices. The anchor is the thing at stake: a wrong one does not fail to
    merge, it splits one file into two identities (`substrate/artifact_audit.py`), so
    absent beats guessed.
    """
    loose = tmp_path / "not-a-repo"
    loose.mkdir()
    path = _write_transcript(tmp_path / "proj", "s1", _transcript_records(cwd=str(loose)))

    facts = transcripts.parse(path)

    assert facts.repo_root == ""
    assert facts.project == ""
    assert facts.cwd == str(loose)  # kept, so the session's location is still recoverable


def test_a_session_that_moved_is_attributed_to_where_it_started(tmp_path):
    """
    Scenario: A session opens in a checkout, works in a git worktree, and exits there

    Verifications:
    - `project` is the checkout, not the worktree it ended in
    - the branch it moved to is still recorded

    Claude Code files a transcript under the dir named for the cwd the session
    *started* in, so an attribution taken from the last cwd files a session under one
    project and attributes it to another. It also makes the answer depend on where the
    session happened to stop — step back out of the worktree before exiting and the
    same work is `thalamus`; exit inside it and it is the worktree's name. cwd fixes
    the session's identity, so it is read once; the branch describes the work, so it
    tracks.
    """
    # Two unrelated checkouts, deliberately not a repo and a worktree of it: worktrees
    # resolve to the repository they belong to, so a real one would make both cwds
    # resolve to the same root and the test would pass without discriminating between
    # first-cwd and last-cwd at all. Separate repos are what keep the two answers
    # distinguishable — here the exit cwd winning would read `console-consolidation`.
    checkout = _git_repo(tmp_path / "thalamus")
    worktree = _git_repo(tmp_path / "console-consolidation")
    records = [
        {
            "type": "user", "uuid": "u1", "timestamp": "2026-08-08T22:00:00Z",
            "cwd": checkout, "gitBranch": "control-plane",
            "message": {"content": "fold the two copies together"},
        },
        {
            "type": "assistant", "uuid": "a1", "timestamp": "2026-08-08T22:30:00Z",
            "cwd": worktree,
            "gitBranch": "console-consolidation",
            "message": {"content": [{"type": "text", "text": "working in the worktree"}]},
        },
        {
            # Ends in the worktree — the case last-wins got wrong.
            "type": "assistant", "uuid": "a2", "timestamp": "2026-08-08T23:00:00Z",
            "cwd": worktree,
            "gitBranch": "console-consolidation",
            "message": {"content": [{"type": "text", "text": "done"}]},
        },
    ]
    path = _write_transcript(tmp_path / "-home-dev-thalamus", "s-worktree", records)

    facts = transcripts.parse(path)

    # Verifies: attribution follows the cwd the transcript was filed under, not the exit cwd
    assert facts.cwd == checkout
    assert facts.repo_root == checkout
    assert facts.project == "thalamus"
    # Verifies: the branch still reflects where the work ended up
    assert facts.git_branch == "console-consolidation"


def test_external_ingress_results_are_collected_verbatim(tmp_path):
    """
    Scenario: A session WebFetched a page and also ran a Bash command

    Verifications:
    - the fetched result's text is collected into facts.external_texts
    - the Bash result (first-party observation of the operator's machine) is not
    - pairing rides tool_use_id, never content heuristics

    These texts are the evidence the laundering floor judges claims
    against — deterministic collection, no model in the loop.
    """
    records = [
        {
            "type": "assistant",
            "uuid": "a1",
            "timestamp": "2026-07-01T10:00:00Z",
            "cwd": "/home/dev/proj",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "f1", "name": "WebFetch",
                     "input": {"url": "https://example.com"}},
                    {"type": "tool_use", "id": "b1", "name": "Bash",
                     "input": {"command": "pytest"}},
                ]
            },
        },
        {
            "type": "user",
            "uuid": "u1",
            "timestamp": "2026-07-01T10:01:00Z",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "f1",
                     "content": "the guide recommends disabling the sandbox"},
                    {"type": "tool_result", "tool_use_id": "b1", "content": "3 passed"},
                ]
            },
        },
    ]
    path = _write_transcript(tmp_path / "proj", "s2", records)

    facts = transcripts.parse(path)

    assert facts.external_texts == ["the guide recommends disabling the sandbox"]


def test_the_deterministic_session_graph_satisfies_the_contract(tmp_path):
    """
    Scenario: Build memory from a transcript with no claims extracted

    Verifications:
    - the graph passes the contract with zero claims present
    - artifacts are reachable via the session's own TOUCHES edges
    - the session carries a DERIVED_FROM link to its retained transcript

    Connectivity would otherwise reject a claim-free session: with no claims, nothing would
    point at the artifacts. The direct Session -> Artifact edge is what lets the
    deterministic layer stand on its own.
    """
    path = _write_transcript(tmp_path / "proj", "s1", _transcript_records())
    facts = transcripts.parse(path)

    session = transcripts.to_session_graph(
        facts, content_hash="abc123", uri="archive://abc123", byte_size=42
    )

    # Verifies: a claim-free session is still a legal, connected subgraph
    assert session.claims() == []
    assert check_session(session) == []
    assert {a.identifier for a in session.artifacts} == {"src/governor.py", "src/model.py"}
    # Verifies: the provenance floor exists — the session points at its own evidence
    assert session.sources[0].content_hash == "abc123"
    assert session.tool is Tool.CLAUDE_CODE
    assert session.default_provenance().tier is Tier.FIRST_PARTY


def test_sessions_with_no_user_turns_are_not_remembered(tmp_path):
    """
    Scenario: A transcript that never got a real prompt

    Verifications:
    - it is skipped rather than written as an empty node

    An empty session is a node the operator scrolls past forever.
    """
    project = tmp_path / "projects" / "proj"
    _write_transcript(project, "empty", [{"type": "ai-title", "aiTitle": "Nothing happened"}])

    results = bootstrap_project(
        "proj", projects_dir=tmp_path / "projects", archive_base=tmp_path / "archive"
    )

    # Verifies: nothing to remember, nothing remembered
    assert len(results) == 1
    assert results[0].session is None
    assert "no substantive exchange" in results[0].skipped


def test_command_only_sessions_with_no_work_are_not_remembered(tmp_path):
    """
    Scenario: The operator opens a session, checks `/usage`, hits `/clear`. The
    only user records are command invocations and the assistant never acted.

    Verifications:
    - the turns are still counted (commands are real user turns)
    - but the session is withheld from distillation rather than summarised

    These pass the turn count on purpose — the `/teach` case below needs them to.
    What separates them is that nothing happened: no typed prompt, no tool use.
    Measured origin: 59c1da4b, whose entire transcript is one `/clear`, distilled
    for $0.16 and produced a Session node summarised "No substantive session
    content was present in this session."
    """
    project = tmp_path / "projects" / "proj"
    _write_transcript(
        project,
        "cleared",
        [
            {
                "type": "user",
                "timestamp": "2026-08-11T09:28:00Z",
                "message": {"role": "user", "content": "<command-name>/usage</command-name>"},
            },
            {
                "type": "user",
                "timestamp": "2026-08-11T09:28:20Z",
                "message": {"role": "user", "content": "<command-name>/clear</command-name>"},
            },
        ],
    )

    facts = transcripts.parse(project / "cleared.jsonl")

    # Verifies: counted as turns, but not as an episode
    assert facts.user_turns == 2
    assert facts.prompt_turns == 0
    assert facts.has_substance is False

    results = bootstrap_project(
        "proj", projects_dir=tmp_path / "projects", archive_base=tmp_path / "archive"
    )
    assert results[0].session is None
    assert "no substantive exchange" in results[0].skipped


def test_slash_command_sessions_count_as_conversations(tmp_path):
    """
    Scenario: A session driven purely by slash commands (/teach lessons) — its
    only user records are <command-name> invocations, plus harness scaffolding

    Verifications:
    - command invocations count as user turns; caveats/reminders still do not
    - the session still distills, on the work the assistant did rather than on a
      typed prompt it never got

    Measured origin: ef3e3d6a (87 assistant messages) was silently ineligible
    for distillation because every human turn started with "<". Its live shape is
    3 command turns, 0 typed prompts and 49 tool calls — the second clause of
    `has_substance` is the only thing keeping it eligible.
    """
    project = tmp_path / "projects" / "proj"
    _write_transcript(
        project,
        "teachy",
        [
            {
                "type": "user",
                "timestamp": "2026-07-17T10:00:00Z",
                "message": {
                    "role": "user",
                    "content": "<command-name>/teach</command-name> <command-args></command-args>",
                },
            },
            {
                "type": "user",
                "timestamp": "2026-07-17T10:00:01Z",
                "message": {"role": "user", "content": "<system-reminder>noise</system-reminder>"},
            },
            {
                "type": "assistant",
                "timestamp": "2026-07-17T10:01:00Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Lesson."},
                        {"type": "tool_use", "name": "Read", "input": {"file_path": "NOTES.md"}},
                    ],
                },
            },
        ],
    )

    facts = transcripts.parse(project / "teachy.jsonl")

    assert facts.user_turns == 1
    assert facts.prompt_turns == 0
    assert facts.has_substance is True


def test_bootstrap_retains_evidence_and_is_idempotent(tmp_path):
    """
    Scenario: Bootstrap the same project twice

    Verifications:
    - the transcript is archived on the first pass and recognised on the second
    - the derived session is identical both times

    Re-running the bootstrap must be safe. It is the operation you reach for precisely when
    something went wrong.
    """
    project = tmp_path / "projects" / "proj"
    _write_transcript(project, "s1", _transcript_records())
    archive = tmp_path / "archive"

    first = bootstrap_project("proj", projects_dir=tmp_path / "projects", archive_base=archive)
    second = bootstrap_project("proj", projects_dir=tmp_path / "projects", archive_base=archive)

    # Verifies: evidence retained once, then recognised
    assert not first[0].already_archived
    assert second[0].already_archived
    # Verifies: re-derivation is stable — the graph is a view over the log
    assert first[0].content_hash == second[0].content_hash
    assert first[0].session.summary == second[0].session.summary
    assert first[0].issues == []


def test_room_is_stamped_on_the_session_and_defaults_empty(tmp_path):
    """
    Scenario: Sessions distilled from inside a room, and one that worked alone

    Verifications:
    - a room passed at distillation lands on the Session
    - absent a room the field is empty, never guessed

    The room is what makes correlated witnesses detectable later. N sessions that
    distilled one shared conversation produce correlated claims; a convergence count
    treating them as distinct witnesses reads one event as N-fold agreement. Nothing
    in a finished graph recovers that, so it is recorded at write time or not at all.
    """
    path = _write_transcript(tmp_path / "proj", "s1", _transcript_records())
    facts = transcripts.parse(path)

    in_room = transcripts.to_session_graph(
        facts, content_hash="abc123", uri="archive://abc123", byte_size=42, room="room-7"
    )
    assert in_room.room == "room-7"
    # Verifies: the room does not disturb the contract it rides along with
    assert check_session(in_room) == []

    alone = transcripts.to_session_graph(
        facts, content_hash="abc123", uri="archive://abc123", byte_size=42
    )
    assert alone.room == ""


def test_fork_parent_is_stamped_on_the_session_and_defaults_empty(tmp_path):
    """
    Scenario: A session forked from another, and one that started cold

    Verifications:
    - a fork parent passed at distillation lands on the Session
    - absent one the field is empty, never inferred from transcript content

    `room` groups co-witnesses; this records derivation. A fork inherited its
    parent's context rather than reaching its own conclusions, so it is a mapping
    over the parent's material and its agreement corroborates nothing. The harness
    mints the fork a fresh session id and says nothing about the resumed one, so
    only the launcher knows — recovering it later would be inference over
    model-written text, which this layer refuses.
    """
    path = _write_transcript(tmp_path / "proj", "s1", _transcript_records())
    facts = transcripts.parse(path)

    forked = transcripts.to_session_graph(
        facts, content_hash="abc123", uri="archive://abc123", byte_size=42,
        forked_from="parent-sess-9",
    )
    assert forked.forked_from == "parent-sess-9"
    assert forked.room == ""
    assert check_session(forked) == []

    cold = transcripts.to_session_graph(
        facts, content_hash="abc123", uri="archive://abc123", byte_size=42
    )
    assert cold.forked_from == ""


def test_a_room_members_transcripts_are_discoverable_under_its_own_config_dir(tmp_path):
    """
    Scenario: A room member runs under its own CLAUDE_CONFIG_DIR, so its
    transcripts land in that dir's `projects/` and not in ~/.claude/projects

    Verifications:
    - the default root does not see them
    - the room's own root does, under the same project dir name

    The room boundary is the config dir, and a config dir owns
    `projects/`. That is what keeps a non-member from resuming a member's session
    — and it is also why a sweep anchored on the default root distills a
    room member nowhere at all. Both roots must be reachable, and the same project
    dir name legitimately exists under each, so the root has to be passed rather
    than guessed from the name.
    """
    default_root = tmp_path / "default" / "projects"
    room_root = tmp_path / "rooms" / "alpha-cfg" / "projects"
    _write_transcript(default_root / "proj", "outside", _transcript_records())
    _write_transcript(room_root / "proj", "inroom", _transcript_records())

    outside = transcripts.discover(default_root)
    inroom = transcripts.discover(room_root)

    # Verifies: same project dir name, disjoint transcripts — the root decides
    assert [p.stem for p in outside["proj"]] == ["outside"]
    assert [p.stem for p in inroom["proj"]] == ["inroom"]

    # Verifies: a room member distills from its own root, not the default one
    results = bootstrap_project(
        "proj", projects_dir=room_root, archive_base=tmp_path / "archive"
    )
    assert len(results) == 1
    assert results[0].session is not None
    assert results[0].session.session_id == "inroom"


def _cursor_session(tmp_path, session_id, cwd, scope, records):
    """An EndedSession pointing at a real Cursor-shaped transcript on disk."""
    directory = tmp_path / "cursor" / session_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{session_id}.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return cursor_transcripts.EndedSession(
        session_id=session_id, scope=scope, transcript_path=path,
        ended_at=None, cwd=cwd,
    )


def test_bootstrap_reaches_cursor_sessions_through_the_same_stage_one(tmp_path, monkeypatch):
    """
    Scenario: Cursor sessions found by discovery are bootstrapped without a model.

    Verifications:
    - the deterministic subgraph is built and passes the contract
    - it is stamped as Cursor's, not Claude Code's
    - time and place come from discovery, since Cursor's rows carry neither

    Stage 1 was Claude-Code-only because `bootstrap` named one reader module, not
    because the harnesses differ after parsing. They produce one intermediate.
    """
    # The pin ledger is the primary source for cwd; an empty one forces the
    # fallback to what discovery already recovered.
    monkeypatch.setattr(cursor_transcripts, "PIN_LEDGER", tmp_path / "no-pins.jsonl")
    checkout = _git_repo(tmp_path / "work")
    session = _cursor_session(
        tmp_path, "cur-1", checkout, "homelab",
        [
            {"role": "user", "message": {"content": [{"type": "text", "text": "port it"}]}},
            {"role": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Edit", "input": {"file_path": "/w/a.py"}}]}},
        ],
    )

    results = bootstrap_cursor([session], archive_base=tmp_path / "archive")

    assert len(results) == 1
    built = results[0].session
    assert built is not None and results[0].issues == []
    assert built.tool == Tool.CURSOR
    assert built.scope == "homelab"          # the session's own, never a default
    assert built.project == "work"           # from discovery's cwd, not the path
    assert check_session(built) == []


def test_bootstrap_refuses_a_cursor_extraction_sandbox(tmp_path, monkeypatch):
    """
    Scenario: a sandbox transcript reaches stage 1 despite its project dir.

    Verifications: it is skipped, not remembered.

    Every headless extraction is a full Cursor session that files its own
    transcript, so distilling one writes memory about the act of remembering —
    and the sandbox's own run would distill in turn.
    """
    monkeypatch.setattr(cursor_transcripts, "PIN_LEDGER", tmp_path / "no-pins.jsonl")
    session = _cursor_session(
        tmp_path, "cur-2", "/tmp/thalamus-extract-abc123", "main",
        [{"role": "user", "message": {"content": [{"type": "text", "text": "distill this"}]}}],
    )

    results = bootstrap_cursor([session], archive_base=tmp_path / "archive")

    assert results[0].session is None
    assert "sandbox" in results[0].skipped


def test_claude_bootstrap_also_refuses_a_sandbox_transcript(tmp_path):
    """The same refusal on the Claude Code path, where `discover()` withholds the
    project dir but a directly-named one would otherwise slip through."""
    project = tmp_path / "projects" / "proj"
    _write_transcript(project, "sand", [
        {"type": "user", "cwd": "/tmp/thalamus-extract-zzz",
         "message": {"role": "user", "content": "do a thing"}},
    ])

    results = bootstrap_project(
        "proj", projects_dir=tmp_path / "projects", archive_base=tmp_path / "archive"
    )
    assert results[0].session is None
    assert "sandbox" in results[0].skipped


# A committing `git` needs an identity, and on a machine with no global one — a CI
# runner, a fresh container — `git commit` exits 128 before the test it belongs to has
# said anything. Passed with `-c` rather than written to config: these repos are
# throwaway, and the suite has no business editing the operator's git configuration.
GIT_IDENTITY = ("-c", "user.name=thalamus tests", "-c", "user.email=tests@thalamus.invalid")


def _git_cmd(cwd, *args):
    subprocess.run(["git", *GIT_IDENTITY, "-C", str(cwd), *args],
                   check=True, capture_output=True)


def _checkout(path):
    """A checkout with one commit, so it has a HEAD to branch a worktree from."""
    path.mkdir(parents=True, exist_ok=True)
    _git_cmd(path, "init", "-q")
    _git_cmd(path, "commit", "-q", "--allow-empty", "-m", "root")
    return path


def test_a_worktree_resolves_to_the_repository_it_belongs_to(tmp_path):
    """The identity a worktree session files under is the repo's, not the worktree's.

    Worktrees here are a concurrency device — concurrent sessions take one each so
    their index and HEAD do not collide — and the work in one is work on the repo.
    Resolved off `--show-toplevel` a worktree is its own toplevel, which minted a
    project per worktree and scattered one repo's memory across as many buckets as it
    had concurrent sessions, where a recall naming the repo found none of them.
    """
    repo = _checkout(tmp_path / "myproject")
    _git_cmd(repo, "worktree", "add", "-q", str(tmp_path / "wt"), "-b", "side")

    assert transcripts.resolve_repo_root(str(tmp_path / "wt")) == str(repo)


def test_every_worktree_of_one_repo_agrees_on_the_project(tmp_path):
    """Two concurrent sessions in two worktrees file under one project — which is the
    whole point, and the assertion the per-worktree spelling failed."""
    repo = _checkout(tmp_path / "myproject")
    _git_cmd(repo, "worktree", "add", "-q", str(tmp_path / "a"), "-b", "a")
    _git_cmd(repo, "worktree", "add", "-q", str(tmp_path / "b"), "-b", "b")

    roots = {transcripts.resolve_repo_root(str(tmp_path / name))
             for name in ("a", "b")} | {transcripts.resolve_repo_root(str(repo))}

    assert roots == {str(repo)}
    assert {Path(r).name for r in roots} == {"myproject"}


def test_a_subdirectory_of_a_worktree_still_resolves_to_the_repository(tmp_path):
    """Sessions are opened in subdirectories, not only at the worktree root."""
    repo = _checkout(tmp_path / "myproject")
    _git_cmd(repo, "worktree", "add", "-q", str(tmp_path / "wt"), "-b", "side")
    nested = tmp_path / "wt" / "src" / "deep"
    nested.mkdir(parents=True)

    assert transcripts.resolve_repo_root(str(nested)) == str(repo)


def test_a_vendored_subrepo_still_resolves_to_the_inner_repository(tmp_path):
    """The nested case must not be swept up by the worktree fix: a repo checked out
    inside another is its own project, and a session working in one belongs to it."""
    outer = _checkout(tmp_path / "outer")
    inner = _checkout(outer / "vendor" / "inner")

    assert transcripts.resolve_repo_root(str(inner)) == str(inner)


def test_a_path_outside_any_repository_still_resolves_to_nothing(tmp_path):
    """Empty beats a guess — the property the whole `project` field rests on."""
    loose = tmp_path / "loose"
    loose.mkdir()

    assert transcripts.resolve_repo_root(str(loose)) == ""
    assert transcripts.resolve_repo_root("") == ""
