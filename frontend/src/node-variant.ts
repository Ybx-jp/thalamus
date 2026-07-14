import type { ViewNode } from './model'

/**
 * A node's *visual* variant, which is not the same as its graph label.
 *
 * Decisions, problems and solutions all share the `Claim` label in the graph — one label
 * discriminated by a `kind` property, so consumers never break when an expert introduces
 * a new kind (`literature/finding`, say). They still deserve to look different on screen,
 * so colour keys on the variant instead.
 *
 * A variant with no colour falls through to the base node style. That is the intended
 * behaviour for an unknown `kind`: render it, do not crash.
 */
export function variantOf(node: Pick<ViewNode, 'kind' | 'properties'>): string {
  if (node.kind === 'Claim') {
    const kind = node.properties.kind
    return typeof kind === 'string' ? kind : 'Claim'
  }
  return node.kind
}

export const variantColors: Record<string, string> = {
  Session: '#2563eb',
  Artifact: '#0891b2',
  Thread: '#d97706',
  Source: '#a16207',
  Missing: '#64748b',
  Project: '#0f766e',
  decision: '#7c3aed',
  problem: '#dc2626',
  solution: '#16a34a',
}

/** What the operator actually distinguishes on screen. */
export const LEGEND_VARIANTS = [
  'Project',
  'Session',
  'Source',
  'Artifact',
  'Decision',
  'Problem',
  'Solution',
  'Thread',
  'Missing',
] as const
