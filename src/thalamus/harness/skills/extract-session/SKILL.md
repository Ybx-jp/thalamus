# Extract Session to Graph Memory

## Purpose
Extract a structured property graph from the current session transcript and write it to graph memory.

## When to Use
Invoke this skill at the end of a coding session to capture decisions, artifacts, problems, solutions, and open threads into persistent graph memory.

## Instructions

You are extracting a session graph from the current conversation. Output **only** a YAML block conforming to the schema below. Be terse but precise — summaries should be 1-3 sentences max. Capture what a future agent would need to quickly understand what happened and why.

### Extraction Rules

1. **Summary**: Write 1-3 sentences capturing the essence of this session. What was the goal? What was achieved?
2. **Artifacts**: List files, classes, modules, dependencies, configs, or endpoints that were meaningfully touched or discussed. Skip trivially mentioned items.
3. **Decisions**: Capture choices that were made with their rationale. A decision without rationale is not worth recording.
4. **Problems**: Anything that blocked progress, caused confusion, or required debugging.
5. **Solutions**: How problems were resolved. Link to the problem via `problem_ref` (0-indexed into problems list).
6. **Threads**: Open lines of work, next steps, continuation points, or follow-up tasks. These persist across sessions and serve as entrypoints for future agents.
7. **Thread refs**: If this session continued or resolved a thread from a prior session, reference it here to update its status.

### Schema

```yaml
session_id: "<conversation/session ID>"
timestamp: "<ISO 8601>"
tool: "cursor"  # or "claude_code"
project: "<primary repo/project name or null>"
summary: "<1-3 sentence summary>"

artifacts:
  - identifier: "<file path, class name, or package>"
    type: "file|class|function|module|dependency|config|endpoint"
    project: "<project name if different from session project>"
    notes: "<optional short note>"

decisions:
  - description: "<what was decided>"
    rationale: "<why>"
    outcome: "<what resulted, if known>"
    artifacts: ["<artifact identifiers touched>"]

problems:
  - description: "<what went wrong or was unclear>"
    category: "bug|performance|design|integration|configuration|dependency|understanding"
    artifacts: ["<artifact identifiers involved>"]

solutions:
  - description: "<what fixed it>"
    approach: "<how>"
    worked: true
    problem_ref: 0  # index into problems list
    artifacts: ["<artifact identifiers touched>"]

threads:
  - id: "<stable-slug-id>"
    title: "<short actionable title>"
    description: "<what needs to happen and why it matters>"
    status: "open|in_progress"
    artifacts: ["<artifact identifiers involved>"]
    blocks: ["<thread IDs this blocks>"]
    blocked_by: ["<thread IDs blocking this>"]

thread_refs:
  - id: "<existing thread ID being continued or resolved>"
    status: "in_progress|resolved|abandoned"
    notes: "<what progress was made>"
```

### Output Format

Output the extraction as a fenced YAML block. The calling tool will validate and write it to graph memory.

```yaml
session_id: ...
```

### Guidelines

- **No orphan nodes**: Every node in the graph must be reachable via at least one edge. An unlinked node is not traversable and will be rejected by `memorize`. In practice this means: every artifact must be referenced in at least one decision, problem, solution, or thread `artifacts` list. If a node has no edges, either remove it or connect it to something.
- **Be selective**: Not every file mentioned deserves an Artifact node. Focus on files that were meaningfully changed or that future agents would benefit from knowing about.
- **Decisions matter most**: A session with no decisions probably isn't worth memorizing beyond its summary.
- **Problems without solutions are valuable**: Unresolved issues are important context for future sessions.
- **Threads are the most actionable output**: Every session that proposes next steps, leaves work unfinished, or identifies follow-ups should spawn threads. These become the primary entrypoint for future agents.
- **Thread IDs must be stable slugs**: Use descriptive, lowercase, hyphenated IDs (e.g., `build-linking-workflow`, `add-embedding-search`). These persist across sessions — a future session resolves a thread by referencing the same ID.
- **Close threads when done**: If this session completed work that a prior thread described, add a `thread_refs` entry with `status: resolved`.
- **Cross-reference artifacts**: Use the same `identifier` string in artifacts list and in decision/problem/solution/thread `artifacts` arrays to create graph edges.
- **Session ID**: Use the conversation/chat ID if available. If not, generate a short descriptive slug with date (e.g., `graph-memory-design-2025-11-15`).
