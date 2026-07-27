> **Historical / as-built.** This is the design spec for the interactive memory-graph
> viewer, written for the prior `graph-memory` project *before* Thalamus existed. The
> viewer it specifies is built and shipped (`src/thalamus/plane/`, `frontend/`). It is
> kept for provenance — it is not part of the Thalamus design set (`docs/00`–`09`), and
> its "master plane" is not this project's. Under Thalamus this viewer is the seed of
> the connective plane; see [../03-master-plane.md](../03-master-plane.md).

# Interactive Memory Graph Visualization

Status: Draft  
Audience: graph-memory maintainers and implementers  
Primary renderer: Cytoscape.js  

## Summary

Replace the Mermaid-to-Excalidraw visualization path with a local, read-only React
application backed by graph-memory's Python and Gremlin layers.

The application provides one consistent interface for:

1. validating a pending `SessionGraph` before it is memorized;
2. browsing a project-oriented overview of persisted memory;
3. searching for and incrementally expanding focused subgraphs;
4. tracing thread lineage over time; and
5. diagnosing graph integrity and recall behavior.

The full persisted graph must be reachable through search, filtering, and expansion,
but the application must not render the entire graph at once. For the expected scale
of up to 10,000 nodes, progressive subgraph loading is both more usable and more
reliable than an all-at-once network view.

## Problem

The current visualization flow has two structural limitations:

- `session_to_mermaid()` only converts one pending `SessionGraph`.
- Mermaid output is a presentation format rather than a queryable graph model.

The current flow also prunes orphan artifacts and truncates labels before rendering.
That is useful for creating a compact diagram, but actively hides information needed
for validation and debugging. Passing the Mermaid result through Excalidraw adds
another lossy representation and does not provide a path to the persisted graph.

Replacing Mermaid with a different static renderer would not solve these limitations.
The system needs a graph query API, a canonical visualization data model, and an
interactive client.

## Goals

- Provide a CLI-launched local web application.
- Use one viewer for pending session validation and persisted graph exploration.
- Organize the initial persisted view around project clusters.
- Style nodes and edges by their graph semantics.
- Support text search, project selection, date filtering, and neighbor expansion.
- Support adaptive layouts suited to the current task.
- Show node properties, incoming and outgoing relationships, and lineage.
- Surface dangling references, duplicate candidates, contradictory lineage, and
  recall-match explanations.
- Keep the visualization read-only with respect to graph-memory data.
- Remain responsive with a persisted graph containing up to 10,000 nodes by loading
  focused subgraphs progressively.
- Preserve stable graph IDs from the substrate throughout the backend and frontend.

## Non-goals

- Editing, deleting, merging, or creating persisted memories from the viewer.
- Rendering every persisted node and edge simultaneously.
- Replacing TinkerGraph or Gremlin as the source of persisted graph data.
- Providing a hosted or multi-user visualization service.
- Supporting manual graph layout as durable graph state.
- Building network-science analysis, centrality, or community-detection workflows.
- Producing publication-quality diagrams in the first release.
- Maintaining Mermaid or Excalidraw as an intermediate representation.

## Product Decisions

### Cytoscape.js is the primary renderer

Cytoscape.js matches the required browser interaction model: JSON graph input,
selection events, semantic styling, filtering, incremental element insertion, and
multiple layout strategies. The application should use Cytoscape.js directly rather
than translating the graph through Mermaid, DOT, or another diagram language.

### Graphviz is optional

Graphviz may be added later to export a small focused subgraph as SVG or to calculate
a deterministic hierarchical layout. It is not part of the primary data path.
Cytoscape layout extensions should satisfy the initial layout requirements without
introducing a second graph representation.

### Gephi is an optional analyst escape hatch

Gephi is useful for large-scale network analysis, timeline exploration, metrics, and
manual investigation. Those strengths do not match the required CLI-launched React
workflow. A future GEXF or GraphML export may allow specialist analysis without
making Gephi part of the product architecture.

## Users and Core Jobs

The initial user is a graph-memory developer or operator working locally.

The user's core jobs are:

- inspect a session extraction before writing it;
- understand what memories exist for a project;
- find related sessions through search;
- follow connections outward from an interesting node;
- understand how a thread progressed across sessions;
- detect malformed or misleading memory structures; and
- understand why recall returned a given session.

## User Experience

### Application shell

The application contains:

- a top bar with mode, project, search, and date controls;
- a central Cytoscape graph canvas;
- a collapsible legend and filter panel;
- a right-side details panel for the current selection; and
- a findings panel for validation, integrity, and recall explanations.

The application has two top-level modes:

- **Session preview** for pending YAML or JSON.
- **Memory explorer** for persisted graph data.

Both modes use the same semantic styles, details panel, filtering model, and graph
data contract.

### Flow 1: Validate a pending session

Command:

```bash
graph-memory visualize path/to/session.yaml
```

Expected behavior:

1. The CLI parses the file and starts the local visualization service.
2. The default browser opens directly to a session-preview route.
3. The backend converts the complete pending session into the canonical graph model.
4. The graph displays all representable nodes, including disconnected nodes.
5. Validation findings are listed and affected nodes or edges are highlighted.
6. Selecting a finding focuses the corresponding graph elements.
7. Selecting a node shows its properties and relationships.

Unlike the current implementation, the preview must not prune orphan artifacts.
Disconnected elements are evidence that validation needs to expose.

If schema validation fails so completely that no graph can be constructed, the
application still opens and displays the structured validation errors. Recoverable
elements may be shown when they can be identified safely, but partial rendering must
never imply that the session is valid.

### Flow 2: Open the persisted memory overview

Command:

```bash
graph-memory visualize
```

Expected behavior:

1. The CLI starts the local service and opens the memory explorer.
2. The initial request loads project-level aggregates, recent sessions, and active
   threads.
3. Projects appear as visual clusters or compound nodes.
4. Older sessions remain summarized until the user expands or filters the project.
5. The UI reports both visible counts and matching total counts.

The overview is an entry point into the full graph, not a claim that every persisted
element is currently rendered.

### Flow 3: Search and focused exploration

The user may:

- search session summaries and Decision, Problem, Solution, and Thread descriptions;
- select a project;
- constrain results by date range; and
- expand one or more hops from any selected node.

Search results initially return a bounded graph containing matched nodes, their
owning sessions where applicable, and enough neighboring context to make the result
understandable. The UI must distinguish direct matches from contextual nodes.

Each expandable node exposes whether additional incoming or outgoing neighbors are
available. Expansion adds those elements without discarding the user's current
selection, filters, or viewport.

The user can reset to the project overview at any time.

### Flow 4: Trace thread lineage

Selecting a Thread offers a lineage action. The lineage view:

- shows the session that spawned the thread;
- shows sessions that continued or resolved it;
- orders those sessions chronologically;
- includes thread-to-thread `BLOCKS` relationships when relevant;
- applies the current date range; and
- uses a hierarchical layout.

The details panel shows the current Thread status and the timestamps and relationship
types that justify the displayed lineage.

### Flow 5: Debug graph integrity and recall

The findings panel may be opened in session preview or memory explorer mode.

Supported findings:

- dangling references or missing expected endpoints;
- exact and probable duplicate entities;
- contradictory or incomplete thread lineage; and
- recall-match evidence.

When the explorer is opened from a recall query, matched sessions and nodes show the
fields and terms responsible for the match. Context-only nodes must not be presented
as matches.

## Semantic Visualization

Persisted vertex labels currently include:

- `Session`
- `Artifact`
- `Decision`
- `Problem`
- `Solution`
- `Thread`

The overview may introduce virtual `Project` and aggregate nodes. Virtual nodes are
presentation entities only and must be explicitly marked as such in the API response.

Persisted edge labels currently include:

- `CONTAINS`
- `TOUCHES`
- `SOLVED_BY`
- `SPAWNS`
- `CONTINUES`
- `RESOLVES`
- `BLOCKS`

Node shape and color identify semantic type. Edge color and line treatment identify
relationship type. Color must not be the only discriminator; the legend, shape, and
labels must preserve meaning for users with color-vision deficiencies.

Labels should be concise on the canvas. Full text belongs in the details panel.
Canvas labels may be shortened for rendering, but the canonical API response must
retain the original value.

### Suggested layout policy

- Project overview: compound or clustered layout.
- Broad focused subgraph: fCoSE or another performant force-directed layout.
- Session preview: hierarchical layout rooted at the Session.
- Thread lineage: directed acyclic or hierarchical layout ordered by timestamp.
- User-expanded neighborhood: preserve existing positions where practical and lay
  out only newly added elements.

The UI may provide a layout selector, but should choose the appropriate default from
the current mode.

## Canonical Visualization Contract

The backend exposes renderer-neutral JSON. Cytoscape-specific conversion belongs in
the frontend adapter.

Conceptual response:

```json
{
  "nodes": [
    {
      "id": "session:abc123",
      "kind": "Session",
      "label": "Designed graph visualization",
      "properties": {
        "session_id": "abc123",
        "project": "graph-memory",
        "timestamp": "2026-07-10T12:00:00"
      },
      "virtual": false,
      "matched": true,
      "expandable": {
        "incoming": false,
        "outgoing": true
      },
      "finding_ids": []
    }
  ],
  "edges": [
    {
      "id": "session:abc123|CONTAINS|decision:abc123:0",
      "source": "session:abc123",
      "target": "decision:abc123:0",
      "kind": "CONTAINS",
      "properties": {},
      "finding_ids": []
    }
  ],
  "findings": [],
  "metadata": {
    "mode": "search",
    "visible_node_count": 1,
    "visible_edge_count": 0,
    "matching_node_count": 1,
    "truncated": false,
    "time_range": {
      "minimum": "2026-07-10T12:00:00",
      "maximum": "2026-07-10T12:00:00"
    }
  }
}
```

Contract requirements:

- IDs are stable and unique within a response.
- Persisted elements use their substrate IDs.
- Preview-only elements use deterministic IDs compatible with the writer's ID scheme.
- Edge IDs are deterministic even if the database does not expose a suitable ID.
- All stored properties needed by the details panel are retained.
- `matched` distinguishes query matches from contextual elements.
- `expandable` allows the UI to signal undisplayed neighbors.
- Findings reference graph element IDs rather than embedding presentation styles.
- Responses state when limits or truncation were applied.

## Backend API

The local backend should expose an HTTP JSON API. FastAPI with Uvicorn is the
recommended Python implementation because it supports typed request models, generated
API documentation, and straightforward local ASGI serving. The API must remain
separate from MCP tool semantics even if both reuse the same reader and validation
services.

Initial operations:

### `POST /api/previews`

Accept YAML or JSON session content, validate it, and return a preview identifier plus
the canonical graph response. Preview data is held in memory for the life of the
local process and is never written to the graph.

### `GET /api/overview`

Return project aggregates, recent sessions, and active threads.

Parameters include:

- optional project filter;
- optional start and end timestamps;
- per-project recent-session limit; and
- total response limit.

### `GET /api/search`

Search persisted memory and return a focused graph.

Parameters include:

- query text;
- optional project;
- optional start and end timestamps; and
- result and context limits.

The response includes recall-match evidence for direct matches.

### `POST /api/subgraphs/expand`

Accept root node IDs, direction, relationship filters, and depth. Return only elements
not already known by the client when the client supplies its visible IDs.

Expansion defaults to one hop and must enforce server-side node and edge limits.

### `GET /api/threads/{thread_id}/lineage`

Return the complete bounded lineage for one Thread, including spawn, continuation,
resolution, and relevant blocking relationships.

### `GET /api/nodes/{node_id}`

Return complete properties and incoming/outgoing relationship summaries for the
details panel. Large neighbor sets are summarized and paginated.

### `GET /api/health`

Report backend availability and graph connection status without returning secrets.

## Query Layer

Visualization traversals belong in a dedicated query module rather than in route
handlers or the existing result-formatting functions.

The query layer must:

- return typed nodes and edges rather than Markdown-formatted `MemoryResult` strings;
- use bounded traversals and explicit limits;
- avoid N+1 traversals when loading visible relationship sets;
- support project and timestamp predicates before graph expansion where possible;
- preserve stable IDs and labels;
- expose whether omitted neighbors exist; and
- capture match evidence while evaluating search terms.

The existing recall functions may be refactored to share lower-level query primitives,
but their MCP-facing output should remain backward compatible unless changed
separately.

## Validation and Integrity Findings

Findings have:

- a stable ID within the response;
- severity: `error`, `warning`, or `info`;
- code;
- human-readable message;
- affected node and edge IDs; and
- optional structured evidence.

Initial finding codes should cover:

- `orphan_artifact`
- `missing_artifact_reference`
- `missing_thread_reference`
- `duplicate_identifier`
- `probable_duplicate`
- `multiple_thread_spawns`
- `thread_event_before_spawn`
- `thread_status_conflict`
- `thread_lineage_gap`
- `recall_match`

Probable duplicate detection must be presented as a heuristic, not a correctness
failure. Exact duplicate IDs and missing required references may be errors. Checks
that require persisted context should state when the graph service is unavailable and
must not silently pass.

## Frontend Architecture

The frontend is a small React and TypeScript application.

Recommended responsibilities:

- API client and runtime response validation;
- canonical-model-to-Cytoscape adapter;
- graph canvas and semantic stylesheet;
- mode-aware layout selection;
- project, date, semantic-type, and relationship filters;
- search and progressive expansion controls;
- details and findings panels; and
- URL state for mode, project, query, dates, and selected element.

Graph data state and UI state should remain separate. Applying a visual filter must
not discard loaded graph data unless the user explicitly resets the view.

The frontend must batch Cytoscape updates and avoid rerunning a full force layout
after every single expansion response.

## CLI and Process Lifecycle

The existing `visualize` command changes from printing Mermaid to launching the local
viewer.

Proposed interface:

```text
graph-memory visualize [FILE] [--url GREMLIN_URL] [--host HOST]
                       [--port PORT] [--no-open]
```

Behavior:

- With `FILE`, open session-preview mode.
- Without `FILE`, open memory-explorer mode.
- Bind to `127.0.0.1` by default.
- Select an available port when `--port` is omitted or zero.
- Open the default browser unless `--no-open` is supplied.
- Print the local URL and shutdown instructions.
- Stop cleanly on interrupt and close the Gremlin connection.

The CLI must not require the graph service for local-only schema validation. Persisted
reference checks become unavailable findings when the graph cannot be reached.

## Performance Requirements

- The initial overview should target no more than 500 rendered elements.
- Search and expansion responses must have explicit node and edge limits.
- The browser must never receive the full graph implicitly.
- The UI must warn when results are truncated and offer narrower filters.
- Layout computation must not block normal controls indefinitely.
- Labels and expensive edge styles should be reduced at low zoom levels.
- Search, overview, and one-hop expansion should target a two-second response on a
  local graph containing 10,000 nodes under normal development hardware.
- The UI should remain usable while expansion or layout work is in progress.

Performance tests should include sparse and edge-heavy fixtures because edge count
usually dominates browser rendering cost.

## Security and Privacy

- Bind to localhost by default.
- Do not enable cross-origin access by default.
- Do not expose the Gremlin endpoint to browser code.
- Treat stored summaries, paths, rationales, and descriptions as potentially
  sensitive local data.
- Do not load JavaScript, fonts, or graph data from external CDNs at runtime.
- Escape all displayed property values and never interpret stored text as HTML.
- Do not persist preview content beyond the local process lifetime.

## Accessibility

- Provide keyboard access to search, filters, findings, and details.
- Do not rely on canvas interaction as the only way to inspect a result.
- Findings and search results must also be available as navigable lists.
- Use shape, labels, and line patterns in addition to color.
- Maintain sufficient contrast in semantic styles.

## Compatibility and Migration

- Remove `session_to_mermaid()` and Mermaid-specific escaping after the new preview
  flow reaches feature parity.
- Preserve `validate_connectivity()` behavior through a renderer-neutral validation
  service, while expanding its finding model.
- Remove Mermaid instructions from the `memory_visualize` MCP tool.
- Either retire `memory_visualize` or redefine it to return a local viewer URL only
  when a managed viewer process exists. An MCP server should not silently spawn a
  long-lived web process without explicit lifecycle handling.
- Delete Mermaid fixture outputs only after equivalent canonical graph and UI tests
  exist.
- Keep CLI validation and write behavior backward compatible.

## Testing Strategy

### Backend unit tests

- SessionGraph-to-canonical-model conversion.
- Stable preview and persisted IDs.
- Every supported vertex and edge semantic.
- Findings and affected-element references.
- Overview aggregation.
- Search match evidence.
- Expansion direction, depth, limits, and truncation.
- Thread lineage ordering and contradictory histories.

### Backend integration tests

- Queries against representative graph data.
- Shared Artifact nodes across sessions.
- Project and date filtering.
- Unavailable graph-service behavior.
- CLI startup, URL output, browser suppression, and clean shutdown.

### Frontend tests

- Canonical model conversion to Cytoscape elements.
- Semantic filters and legends.
- Search-result versus context styling.
- Selection and details panel behavior.
- Finding selection and graph focus.
- Incremental expansion without duplicate elements.
- URL state restoration.

### End-to-end scenarios

- Preview a valid session.
- Preview a session with orphan and missing references.
- Open a project overview.
- Search for a decision and inspect why it matched.
- Expand from a Session to its contained nodes and touched Artifacts.
- Trace a Thread from spawn through resolution.
- Apply a date filter and verify visible and total counts.
- Exercise a near-limit graph without rendering every persisted element.

## Delivery Sequence

### Phase 1: Unified vertical slice

- Define the canonical visualization models.
- Convert pending sessions without pruning disconnected nodes.
- Add the local HTTP service and React/Cytoscape shell.
- Change `graph-memory visualize [FILE]` to open session preview.
- Add basic persisted project overview and one-hop expansion.
- Implement details and findings panels.

This phase proves the selected MVP: one viewer supports both session validation and
persisted focused-subgraph exploration.

### Phase 2: Search and temporal lineage

- Add persisted search with match evidence.
- Add project and date filters.
- Add thread lineage queries and hierarchical layout.
- Add URL state and richer incremental expansion.

### Phase 3: Integrity and scale hardening

- Add persisted duplicate and lineage checks.
- Tune rendering and query limits using 10,000-node fixtures.
- Add optional focused-subgraph export if a concrete sharing or analyst workflow
  emerges.

## Acceptance Criteria

The first release is complete when:

- `graph-memory visualize session.yaml` opens a browser-based preview without Mermaid
  or Excalidraw;
- disconnected and invalid references are visible rather than pruned;
- `graph-memory visualize` opens a project-oriented persisted overview;
- the user can search, filter by project, and expand a node by one hop;
- the same semantic styles and details panel work in both modes;
- selecting a node shows properties and incoming/outgoing relationships;
- a Thread can be viewed with its chronological lineage;
- recall results can expose direct match evidence;
- all responses enforce limits and report truncation;
- the application is read-only and binds to localhost by default; and
- automated tests cover the canonical model, validation findings, query limits, and
  the critical browser flows.

## Open Implementation Questions

These questions do not block the product direction but should be resolved during
implementation:

- Whether the React assets live inside the Python package or in a top-level frontend
  workspace.
- Whether session previews are posted after server startup or loaded directly by the
  backend from the CLI-provided file.
- Which Cytoscape hierarchical extension gives the best result for session previews
  and thread lineage.
- The exact normalized-text heuristic and threshold for probable duplicates.
- Whether integrity checks run on demand, alongside queries, or through a cached
  background scan.
- Whether a future MCP visualization tool should return viewer URLs or only canonical
  graph data for clients capable of rendering it.
