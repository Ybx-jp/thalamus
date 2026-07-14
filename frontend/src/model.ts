export type Severity = 'error' | 'warning' | 'info'

export interface Expandable {
  incoming: boolean
  outgoing: boolean
}

export interface ViewNode {
  id: string
  kind: string
  label: string
  properties: Record<string, unknown>
  virtual: boolean
  matched: boolean
  expandable: Expandable
  finding_ids: string[]
}

export interface ViewEdge {
  id: string
  source: string
  target: string
  kind: string
  properties: Record<string, unknown>
  finding_ids: string[]
}

export interface Finding {
  id: string
  severity: Severity
  code: string
  message: string
  node_ids: string[]
  edge_ids: string[]
  evidence: Record<string, unknown>
}

export interface ViewMetadata {
  mode: string
  visible_node_count: number
  visible_edge_count: number
  matching_node_count: number
  truncated: boolean
  time_range: { minimum: string; maximum: string } | null
}

export interface GraphView {
  nodes: ViewNode[]
  edges: ViewEdge[]
  findings: Finding[]
  metadata: ViewMetadata
}

export interface NodeDetails {
  node: ViewNode
  incoming_count: number
  outgoing_count: number
}
