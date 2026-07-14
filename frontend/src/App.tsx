import { useCallback, useEffect, useMemo, useState } from 'react'

import './App.css'
import {
  latestExpansionIndex,
  mergeGraph,
  rebuildExpandedGraph,
  type ExpansionRecord,
} from './expansion-state'
import GraphCanvas from './GraphCanvas'
import type { Finding, GraphView, NodeDetails, ViewNode } from './model'

function App() {
  const [graph, setGraph] = useState<GraphView | null>(null)
  const [overviewGraph, setOverviewGraph] = useState<GraphView | null>(null)
  const [expansionHistory, setExpansionHistory] = useState<ExpansionRecord[]>([])
  const [selectedNode, setSelectedNode] = useState<ViewNode | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expanding, setExpanding] = useState(false)
  const [relationshipCounts, setRelationshipCounts] = useState<NodeDetails | null>(null)
  const [relationshipCountError, setRelationshipCountError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    async function loadGraph() {
      try {
        let response = await fetch('/api/previews/current', { signal: controller.signal })
        if (response.status === 404) {
          response = await fetch('/api/overview', { signal: controller.signal })
        }
        if (!response.ok) {
          const body = (await response.json()) as { detail?: string }
          throw new Error(body.detail ?? `Graph request failed (${response.status})`)
        }
        const loadedGraph = (await response.json()) as GraphView
        setGraph(loadedGraph)
        setOverviewGraph(loadedGraph.metadata.mode === 'overview' ? loadedGraph : null)
        setExpansionHistory([])
      } catch (requestError) {
        if (requestError instanceof DOMException && requestError.name === 'AbortError') return
        setError(requestError instanceof Error ? requestError.message : 'Unable to load preview')
      }
    }

    void loadGraph()
    return () => controller.abort()
  }, [])

  useEffect(() => {
    setRelationshipCounts(null)
    setRelationshipCountError(null)
    if (
      !graph ||
      graph.metadata.mode !== 'overview' ||
      !selectedNode ||
      selectedNode.virtual
    ) {
      return
    }

    const nodeId = selectedNode.id
    const controller = new AbortController()
    async function loadRelationshipCounts() {
      try {
        const response = await fetch(`/api/nodes/${encodeURIComponent(nodeId)}`, {
          signal: controller.signal,
        })
        if (!response.ok) {
          const body = (await response.json()) as { detail?: string }
          throw new Error(body.detail ?? `Node request failed (${response.status})`)
        }
        setRelationshipCounts((await response.json()) as NodeDetails)
      } catch (requestError) {
        if (requestError instanceof DOMException && requestError.name === 'AbortError') return
        setRelationshipCountError(
          requestError instanceof Error ? requestError.message : 'Unable to load graph relationships',
        )
      }
    }

    void loadRelationshipCounts()
    return () => controller.abort()
  }, [graph, selectedNode])

  const selectNode = useCallback((node: ViewNode | null) => setSelectedNode(node), [])
  const findingsBySeverity = useMemo(() => {
    if (!graph) return { error: 0, warning: 0, info: 0 }
    return graph.findings.reduce(
      (counts, finding) => ({ ...counts, [finding.severity]: counts[finding.severity] + 1 }),
      { error: 0, warning: 0, info: 0 },
    )
  }, [graph])

  function selectFinding(finding: Finding) {
    if (!graph || finding.node_ids.length === 0) return
    setSelectedNode(graph.nodes.find((node) => node.id === finding.node_ids[0]) ?? null)
  }

  async function expandSelectedNode() {
    if (!graph || !selectedNode || expanding) return
    setExpanding(true)
    try {
      const response = await fetch('/api/subgraphs/expand', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          root_ids: [selectedNode.id],
          visible_node_ids: graph.nodes.map((node) => node.id),
          visible_edge_ids: graph.edges.map((edge) => edge.id),
        }),
      })
      if (!response.ok) {
        const body = (await response.json()) as { detail?: string }
        throw new Error(body.detail ?? `Expansion request failed (${response.status})`)
      }
      const addition = (await response.json()) as GraphView
      setGraph((current) => (current ? mergeGraph(current, addition) : current))
      if (addition.nodes.length > 0 || addition.edges.length > 0) {
        setExpansionHistory((history) => [...history, { rootId: selectedNode.id, graph: addition }])
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to expand graph')
    } finally {
      setExpanding(false)
    }
  }

  function retractSelectedExpansion() {
    if (!overviewGraph || !selectedNode) return
    const index = latestExpansionIndex(expansionHistory, selectedNode.id)
    if (index === -1) return

    const nextHistory = expansionHistory.filter((_, historyIndex) => historyIndex !== index)
    const nextGraph = rebuildExpandedGraph(overviewGraph, nextHistory)
    setExpansionHistory(nextHistory)
    setGraph(nextGraph)
    if (!nextGraph.nodes.some((node) => node.id === selectedNode.id)) {
      setSelectedNode(null)
    }
  }

  if (error) {
    return (
      <main className="centered-state">
        <p className="eyebrow">Session preview</p>
        <h1>Unable to load the graph</h1>
        <p>{error}</p>
      </main>
    )
  }

  if (!graph) {
    return (
      <main className="centered-state">
        <div className="loading-mark" aria-hidden="true" />
        <p>Loading session graph…</p>
      </main>
    )
  }

  const explorer = graph.metadata.mode === 'overview'
  const projects = graph.nodes.filter((node) => node.kind === 'Project')
  const canRetract = Boolean(
    explorer && selectedNode && latestExpansionIndex(expansionHistory, selectedNode.id) !== -1,
  )
  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Graph memory</p>
          <h1>{explorer ? 'Memory explorer' : 'Session preview'}</h1>
        </div>
        <div className="summary" aria-label="Graph summary">
          <span>{graph.metadata.visible_node_count} nodes</span>
          <span>{graph.metadata.visible_edge_count} edges</span>
          {explorer ? (
            <span>{graph.metadata.matching_node_count} matching sessions</span>
          ) : (
            <>
              <span className={findingsBySeverity.error ? 'summary-error' : ''}>
                {findingsBySeverity.error} errors
              </span>
              <span className={findingsBySeverity.warning ? 'summary-warning' : ''}>
                {findingsBySeverity.warning} warnings
              </span>
            </>
          )}
          {graph.metadata.truncated && <span className="summary-warning">Results truncated</span>}
        </div>
      </header>

      <section className="workspace">
        <aside className="findings-panel" aria-label="Validation findings">
          <div className="panel-heading">
            <p className="eyebrow">{explorer ? 'Overview' : 'Validation'}</p>
            <h2>{explorer ? 'Projects' : 'Findings'}</h2>
          </div>
          {explorer ? (
            <ul className="project-list">
              {projects.map((project) => (
                <li key={project.id}>
                  <button
                    type="button"
                    className="project"
                    onClick={() => setSelectedNode(project)}
                  >
                    <span>{project.label}</span>
                    <span>{String(project.properties.session_count ?? 0)} sessions</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : graph.findings.length === 0 ? (
            <div className="empty-state">
              <span className="status-dot status-ok" />
              No integrity findings
            </div>
          ) : (
            <ul className="finding-list">
              {graph.findings.map((finding) => (
                <li key={finding.id}>
                  <button
                    type="button"
                    className={`finding finding-${finding.severity}`}
                    onClick={() => selectFinding(finding)}
                  >
                    <span className="finding-code">{finding.code.replaceAll('_', ' ')}</span>
                    <span>{finding.message}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section className="graph-panel">
          <GraphCanvas
            graph={graph}
            selectedNodeId={selectedNode?.id ?? null}
            onSelectNode={selectNode}
          />
          <div className="legend" aria-label="Node type legend">
            {['Project', 'Session', 'Artifact', 'Decision', 'Problem', 'Solution', 'Thread', 'Missing'].map(
              (kind) => (
                <span key={kind}>
                  <i className={`legend-dot legend-${kind.toLowerCase()}`} />
                  {kind}
                </span>
              ),
            )}
          </div>
        </section>

        <aside className="details-panel" aria-label="Selected node details">
          <div className="panel-heading">
            <p className="eyebrow">Inspector</p>
            <h2>{selectedNode ? selectedNode.kind : 'Select a node'}</h2>
          </div>
          {selectedNode ? (
            <>
              <p className="node-label">{selectedNode.label}</p>
              {selectedNode.virtual && <span className="virtual-badge">Reference</span>}
              <dl className="property-list">
                {Object.entries(selectedNode.properties).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key.replaceAll('_', ' ')}</dt>
                    <dd>{formatProperty(value)}</dd>
                  </div>
                ))}
              </dl>
              <div className="relationship-summary">
                <h3>Relationships</h3>
                {selectedNode.virtual ? (
                  <p>Virtual overview node</p>
                ) : explorer ? (
                  relationshipCounts ? (
                    <p>
                      {relationshipCounts.incoming_count} incoming
                      <span> · </span>
                      {relationshipCounts.outgoing_count} outgoing
                    </p>
                  ) : (
                    <p>{relationshipCountError ?? 'Loading graph relationships…'}</p>
                  )
                ) : (
                  <p>
                    {graph.edges.filter((edge) => edge.target === selectedNode.id).length} incoming
                    <span> · </span>
                    {graph.edges.filter((edge) => edge.source === selectedNode.id).length} outgoing
                  </p>
                )}
              </div>
            </>
          ) : (
              <p className="muted">
                Choose a node{explorer ? ' or project' : ' or validation finding'} to inspect its
                properties.
              </p>
          )}
            {explorer && selectedNode?.expandable && (
              <div className="expansion-controls">
                <button
                  type="button"
                  className="expand-button"
                  onClick={expandSelectedNode}
                  disabled={expanding}
                >
                  {expanding ? 'Loading neighbors…' : 'Expand one hop'}
                </button>
                {canRetract && (
                  <button
                    type="button"
                    className="retract-button"
                    onClick={retractSelectedExpansion}
                  >
                    Retract expansion
                  </button>
                )}
              </div>
            )}
        </aside>
      </section>
    </main>
  )
}

function formatProperty(value: unknown): string {
  if (Array.isArray(value)) return value.join(', ') || '—'
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export default App
