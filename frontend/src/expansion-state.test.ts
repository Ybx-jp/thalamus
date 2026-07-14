/**
 * Expansion retraction state tests.
 *
 * Interfaces: rebuildExpandedGraph
 * Infrastructure: none
 * Scope: safe removal of nested expansions and preservation of externally connected nodes
 */
import { describe, expect, it } from 'vitest'

import { rebuildExpandedGraph, type ExpansionRecord } from './expansion-state'
import type { GraphView, ViewEdge, ViewNode } from './model'

function node(id: string): ViewNode {
  return {
    id,
    kind: 'Decision',
    label: id,
    properties: {},
    virtual: false,
    matched: false,
    expandable: { incoming: true, outgoing: true },
    finding_ids: [],
  }
}

function graph(nodes: ViewNode[], edges: GraphView['edges']): GraphView {
  return {
    nodes,
    edges,
    findings: [],
    metadata: {
      mode: 'overview',
      visible_node_count: nodes.length,
      visible_edge_count: edges.length,
      matching_node_count: nodes.length,
      truncated: false,
      time_range: null,
    },
  }
}

function edge(source: string, target: string): ViewEdge {
  return {
    id: `${source}|CONTAINS|${target}`,
    source,
    target,
    kind: 'CONTAINS',
    properties: {},
    finding_ids: [],
  }
}

describe('expansion retraction state', () => {
  it('removes nested branches whose parent expansion was retracted', () => {
    /**
     * Verifications:
     * - edges that reference a node from the retracted parent are removed
     * - nested nodes with no remaining connection to the overview are removed
     */
    const overview = graph([node('session:root')], [])
    const nestedExpansion: ExpansionRecord = {
      rootId: 'decision:parent',
      graph: graph([node('decision:child')], [edge('decision:parent', 'decision:child')]),
    }

    const result = rebuildExpandedGraph(overview, [nestedExpansion])

    // Verifies: edges that reference a node from the retracted parent are removed
    expect(result.edges).toEqual([])
    // Verifies: nested nodes with no remaining connection to the overview are removed
    expect(result.nodes.map((resultNode) => resultNode.id)).toEqual(['session:root'])
  })

  it('keeps nested nodes that still connect to an unaffected overview node', () => {
    /**
     * Verifications:
     * - an edge to a retracted parent is swallowed
     * - a nested node and its independent edge remain when connected to the overview
     */
    const overview = graph([node('session:root'), node('artifact:unaffected')], [])
    const nestedExpansion: ExpansionRecord = {
      rootId: 'decision:parent',
      graph: graph(
        [node('decision:child')],
        [
          edge('decision:parent', 'decision:child'),
          edge('decision:child', 'artifact:unaffected'),
        ],
      ),
    }

    const result = rebuildExpandedGraph(overview, [nestedExpansion])

    // Verifies: an edge to a retracted parent is swallowed
    expect(result.edges.map((resultEdge) => resultEdge.id)).not.toContain(
      'decision:parent|CONTAINS|decision:child',
    )
    // Verifies: a nested node and its independent edge remain when connected to the overview
    expect(result.nodes.map((resultNode) => resultNode.id)).toContain('decision:child')
    expect(result.edges.map((resultEdge) => resultEdge.id)).toContain(
      'decision:child|CONTAINS|artifact:unaffected',
    )
  })
})
