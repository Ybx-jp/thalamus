import type { GraphView } from './model'

export interface ExpansionRecord {
  rootId: string
  graph: GraphView
}

export function mergeGraph(current: GraphView, addition: GraphView): GraphView {
  const nodes = new Map(current.nodes.map((node) => [node.id, node]))
  const edges = new Map(current.edges.map((edge) => [edge.id, edge]))
  addition.nodes.forEach((node) => nodes.set(node.id, node))
  addition.edges.forEach((edge) => edges.set(edge.id, edge))
  return {
    ...current,
    nodes: [...nodes.values()],
    edges: [...edges.values()],
    findings: [...current.findings, ...addition.findings],
    metadata: {
      ...current.metadata,
      visible_node_count: nodes.size,
      visible_edge_count: edges.size,
      truncated: current.metadata.truncated || addition.metadata.truncated,
    },
  }
}

/**
 * Rebuild the canvas after retraction without retaining nested orphan branches.
 *
 * The overview is the stable root set. Any expanded node that cannot still reach
 * an overview node after the requested expansion is removed is dependent on the
 * retracted branch and is discarded with its edges.
 */
export function rebuildExpandedGraph(
  overview: GraphView,
  history: ExpansionRecord[],
): GraphView {
  const merged = history.reduce((current, expansion) => mergeGraph(current, expansion.graph), overview)
  const existingNodeIds = new Set(merged.nodes.map((node) => node.id))
  const validEdges = merged.edges.filter(
    (edge) => existingNodeIds.has(edge.source) && existingNodeIds.has(edge.target),
  )
  const retainedNodeIds = connectedToOverview(overview, validEdges)
  const nodes = merged.nodes.filter((node) => retainedNodeIds.has(node.id))
  const edges = validEdges.filter(
    (edge) => retainedNodeIds.has(edge.source) && retainedNodeIds.has(edge.target),
  )

  return {
    ...merged,
    nodes,
    edges,
    findings: merged.findings.filter((finding) =>
      finding.node_ids.every((nodeId) => retainedNodeIds.has(nodeId)),
    ),
    metadata: {
      ...merged.metadata,
      visible_node_count: nodes.length,
      visible_edge_count: edges.length,
    },
  }
}

export function latestExpansionIndex(history: ExpansionRecord[], rootId: string): number {
  for (let index = history.length - 1; index >= 0; index -= 1) {
    if (history[index].rootId === rootId) return index
  }
  return -1
}

function connectedToOverview(overview: GraphView, edges: GraphView['edges']): Set<string> {
  const reachable = new Set(overview.nodes.map((node) => node.id))
  const neighbors = new Map<string, string[]>()
  edges.forEach((edge) => {
    neighbors.set(edge.source, [...(neighbors.get(edge.source) ?? []), edge.target])
    neighbors.set(edge.target, [...(neighbors.get(edge.target) ?? []), edge.source])
  })

  const pending = [...reachable]
  while (pending.length > 0) {
    const nodeId = pending.pop()
    if (!nodeId) continue
    for (const neighborId of neighbors.get(nodeId) ?? []) {
      if (!reachable.has(neighborId)) {
        reachable.add(neighborId)
        pending.push(neighborId)
      }
    }
  }
  return reachable
}
