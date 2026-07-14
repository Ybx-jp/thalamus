/**
 * Session preview application tests.
 *
 * Interfaces: GET /api/previews/current response rendering
 * Infrastructure: jsdom with mocked graph canvas and fetch
 * Scope: summary, findings, and node inspection behavior
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import type { GraphView, ViewNode } from './model'

vi.mock('./GraphCanvas', () => ({
  default: ({
    graph,
    onSelectNode,
  }: {
    graph: GraphView
    onSelectNode: (node: ViewNode | null) => void
  }) => (
    <div aria-label="Session memory graph">
      {graph.nodes.map((node) => (
        <button key={node.id} type="button" onClick={() => onSelectNode(node)}>
          Graph node {node.id}
        </button>
      ))}
    </div>
  ),
}))

const graph: GraphView = {
  nodes: [
    {
      id: 'artifact:orphan.py',
      kind: 'Artifact',
      label: 'orphan.py',
      properties: { identifier: 'orphan.py', type: 'file' },
      virtual: false,
      matched: false,
      expandable: { incoming: false, outgoing: false },
      finding_ids: ['orphan-artifact:orphan.py'],
    },
  ],
  edges: [],
  findings: [
    {
      id: 'orphan-artifact:orphan.py',
      severity: 'error',
      code: 'orphan_artifact',
      message: 'Artifact has no relationships: orphan.py',
      node_ids: ['artifact:orphan.py'],
      edge_ids: [],
      evidence: {},
    },
  ],
  metadata: {
    mode: 'session_preview',
    visible_node_count: 1,
    visible_edge_count: 0,
    matching_node_count: 0,
    truncated: false,
    time_range: null,
  },
}

describe('session preview', () => {
  afterEach(() => vi.restoreAllMocks())

  it('shows graph counts and validation findings from the preview API', async () => {
    /**
     * Verifications:
     * - the preview summary reports node, edge, and error counts
     * - validation findings are presented as navigable controls
     */
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(graph), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    render(<App />)

    // Verifies: the preview summary reports node, edge, and error counts
    expect(await screen.findByText('1 nodes')).toBeInTheDocument()
    expect(screen.getByText('0 edges')).toBeInTheDocument()
    expect(screen.getByText('1 errors')).toBeInTheDocument()
    // Verifies: validation findings are presented as navigable controls
    expect(
      screen.getByRole('button', { name: /artifact has no relationships: orphan\.py/i }),
    ).toBeInTheDocument()
  })

  it('opens an affected node when its finding is selected', async () => {
    /**
     * Verifications:
     * - selecting a finding opens the affected node's properties in the inspector
     */
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(graph), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    render(<App />)

    fireEvent.click(
      await screen.findByRole('button', {
        name: /artifact has no relationships: orphan\.py/i,
      }),
    )

    // Verifies: selecting a finding opens the affected node's properties in the inspector
    expect(screen.getByRole('heading', { name: 'Artifact' })).toBeInTheDocument()
    expect(screen.getByText('file')).toBeInTheDocument()
  })
})

describe('memory explorer', () => {
  it('loads the overview when there is no preview and expands selected persisted nodes', async () => {
    /**
     * Verifications:
     * - opening without a preview requests and renders the persisted overview
     * - expanding a persisted node sends visible IDs and merges returned graph elements
     * - retracting the selected expansion restores the initial overview graph
     */
    const overview: GraphView = {
      nodes: [
        {
          id: 'project:graph-memory',
          kind: 'Project',
          label: 'graph-memory',
          properties: { project: 'graph-memory', session_count: 1 },
          virtual: true,
          matched: false,
          expandable: { incoming: false, outgoing: false },
          finding_ids: [],
        },
        {
          id: 'session:one',
          kind: 'Session',
          label: 'First session',
          properties: { session_id: 'one' },
          virtual: false,
          matched: false,
          expandable: { incoming: true, outgoing: true },
          finding_ids: [],
        },
      ],
      edges: [],
      findings: [],
      metadata: {
        mode: 'overview',
        visible_node_count: 2,
        visible_edge_count: 0,
        matching_node_count: 1,
        truncated: false,
        time_range: null,
      },
    }
    const expansion: GraphView = {
      ...overview,
      nodes: [
        {
          id: 'decision:one:0',
          kind: 'Decision',
          label: 'Use a bounded query',
          properties: {},
          virtual: false,
          matched: false,
          expandable: { incoming: true, outgoing: true },
          finding_ids: [],
        },
      ],
      edges: [
        {
          id: 'session:one|CONTAINS|decision:one:0',
          source: 'session:one',
          target: 'decision:one:0',
          kind: 'CONTAINS',
          properties: {},
          finding_ids: [],
        },
      ],
      metadata: {
        ...overview.metadata,
        mode: 'expansion',
        visible_node_count: 1,
        visible_edge_count: 1,
      },
    }
    const nodeDetails = {
      node: overview.nodes[1],
      incoming_count: 8,
      outgoing_count: 3,
    }
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(null, { status: 404 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify(overview), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(nodeDetails), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(expansion), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(nodeDetails), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(nodeDetails), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )

    render(<App />)

    // Verifies: opening without a preview requests and renders the persisted overview
    expect(await screen.findByRole('heading', { name: 'Memory explorer' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Graph node session:one' }))
    expect(screen.getByRole('button', { name: 'Expand one hop' })).toBeInTheDocument()
    expect(
      await screen.findByText((_, element) => element?.textContent === '8 incoming · 3 outgoing'),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Expand one hop' }))

    // Verifies: expanding a persisted node sends visible IDs and merges returned graph elements
    expect(await screen.findByText('3 nodes')).toBeInTheDocument()
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/subgraphs/expand',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"root_ids":["session:one"]'),
      }),
    )

    fireEvent.click(await screen.findByRole('button', { name: 'Retract expansion' }))

    // Verifies: retracting the selected expansion restores the initial overview graph
    expect(await screen.findByText('2 nodes')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Graph node decision:one:0' })).not.toBeInTheDocument()
  })
})
