import { useEffect, useRef } from 'react'
import cytoscape, {
  type Core,
  type ElementDefinition,
  type StylesheetStyle,
} from 'cytoscape'

import { expansionFanPositions } from './expansion-layout'
import type { GraphView, ViewNode } from './model'
import { variantColors, variantOf } from './node-variant'

interface GraphCanvasProps {
  graph: GraphView
  selectedNodeId: string | null
  onSelectNode: (node: ViewNode | null) => void
}

const stylesheet: StylesheetStyle[] = [
  {
    selector: 'node',
    style: {
      'background-color': '#475569',
      'border-color': '#ffffff',
      'border-width': 2,
      color: '#e2e8f0',
      'font-family': 'Inter, ui-sans-serif, system-ui, sans-serif',
      'font-size': 11,
      label: 'data(label)',
      'min-zoomed-font-size': 7,
      'text-background-color': '#0f172a',
      'text-background-opacity': 0.85,
      'text-background-padding': '3px',
      'text-margin-y': 8,
      'text-valign': 'bottom',
      'text-wrap': 'ellipsis',
      'text-max-width': '150px',
      height: 34,
      width: 34,
    },
  },
  ...Object.entries(variantColors).map(([variant, color]) => ({
    selector: `node[variant = "${variant}"]`,
    style: { 'background-color': color },
  })),
  {
    selector: 'node[?virtual]',
    style: {
      'border-style': 'dashed',
      opacity: 0.78,
    },
  },
  {
    selector: 'node.Missing',
    style: {
      shape: 'diamond',
    },
  },
  {
    selector: 'node.Project',
    style: {
      shape: 'round-rectangle',
      width: 74,
      height: 34,
    },
  },
  {
    selector: 'node.has-error',
    style: {
      'border-color': '#f87171',
      'border-width': 5,
    },
  },
  {
    selector: 'node.has-warning',
    style: {
      'border-color': '#fbbf24',
      'border-width': 4,
    },
  },
  {
    selector: ':selected',
    style: {
      'border-color': '#f8fafc',
      'border-width': 6,
      'overlay-color': '#93c5fd',
      'overlay-opacity': 0.2,
    },
  },
  {
    selector: 'edge',
    style: {
      'curve-style': 'bezier',
      'line-color': '#64748b',
      'target-arrow-color': '#64748b',
      'target-arrow-shape': 'triangle',
      'arrow-scale': 0.75,
      color: '#94a3b8',
      'font-size': 8,
      label: 'data(kind)',
      'text-background-color': '#0f172a',
      'text-background-opacity': 0.8,
      'text-background-padding': '2px',
      width: 1.5,
    },
  },
  {
    selector: 'edge.has-error',
    style: {
      'line-color': '#ef4444',
      'target-arrow-color': '#ef4444',
      'line-style': 'dashed',
      width: 3,
    },
  },
  {
    selector: 'edge.has-warning',
    style: {
      'line-color': '#f59e0b',
      'target-arrow-color': '#f59e0b',
      'line-style': 'dashed',
      width: 3,
    },
  },
  {
    selector: 'edge[?virtual]',
    style: {
      'line-style': 'dotted',
      'target-arrow-shape': 'none',
      opacity: 0.65,
    },
  },
]

function toElements(graph: GraphView): ElementDefinition[] {
  const severityByFinding = new Map(graph.findings.map((finding) => [finding.id, finding.severity]))
  const classesFor = (findingIds: string[]) => {
    const severities = findingIds.map((id) => severityByFinding.get(id))
    if (severities.includes('error')) return 'has-error'
    if (severities.includes('warning')) return 'has-warning'
    return ''
  }

  return [
    ...graph.nodes.map((node) => ({
      data: {
        id: node.id,
        label: node.label,
        kind: node.kind,
        variant: variantOf(node),
        virtual: node.virtual,
      },
      classes: `${node.kind} ${classesFor(node.finding_ids)}`,
    })),
    ...graph.edges.map((edge) => ({
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        kind: edge.kind,
        virtual: edge.properties.virtual === true,
      },
      classes: classesFor(edge.finding_ids),
    })),
  ]
}

export default function GraphCanvas({
  graph,
  selectedNodeId,
  onSelectNode,
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const coreRef = useRef<Core | null>(null)
  const graphRef = useRef(graph)
  graphRef.current = graph

  useEffect(() => {
    if (!containerRef.current) return

    const core = cytoscape({
      container: containerRef.current,
      elements: toElements(graphRef.current),
      style: stylesheet,
      layout: {
        name: 'breadthfirst',
        directed: true,
        padding: 48,
        spacingFactor: 1.3,
      },
      minZoom: 0.12,
      maxZoom: 3,
      wheelSensitivity: 0.25,
    })
    coreRef.current = core

    core.on('tap', 'node', (event) => {
      const id = event.target.id()
      onSelectNode(graphRef.current.nodes.find((node) => node.id === id) ?? null)
    })
    core.on('tap', (event) => {
      if (event.target === core) onSelectNode(null)
    })

    return () => {
      core.destroy()
      coreRef.current = null
    }
  }, [onSelectNode])

  useEffect(() => {
    const core = coreRef.current
    if (!core) return
    const desiredElements = toElements(graph)
    const desiredIds = new Set(desiredElements.map((element) => String(element.data.id)))
    const removals = core.elements().filter((element) => !desiredIds.has(element.id()))
    if (removals.nonempty()) {
      core.remove(removals)
    }
    const existingIds = new Set(core.elements().map((element) => element.id()))
    const additions = desiredElements.filter((element) => !existingIds.has(String(element.data.id)))
    if (additions.length > 0) {
      const added = core.add(additions)
      const root = selectedNodeId ? core.getElementById(selectedNodeId) : null
      const newNodes = added.nodes()
      if (root?.nonempty() && newNodes.nonempty()) {
        const positions = expansionFanPositions(root.position(), newNodes.length)
        newNodes.forEach((node, index) => {
          node.position(positions[index])
        })
      }
    }
  }, [graph, selectedNodeId])

  useEffect(() => {
    const core = coreRef.current
    if (!core) return
    core.elements().unselect()
    if (!selectedNodeId) return
    const selected = core.getElementById(selectedNodeId)
    if (selected.nonempty()) {
      selected.select()
      core.animate({ fit: { eles: selected, padding: 160 }, duration: 250 })
    }
  }, [selectedNodeId])

  return <div className="graph-canvas" ref={containerRef} aria-label="Session memory graph" />
}
