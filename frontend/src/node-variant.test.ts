import { describe, expect, it } from 'vitest'

import type { ViewNode } from './model'
import { variantOf } from './node-variant'

function node(kind: string, properties: Record<string, unknown> = {}): ViewNode {
  return {
    id: 'n1',
    kind,
    label: 'n1',
    properties,
    virtual: false,
    matched: false,
    expandable: { incoming: false, outgoing: false },
    finding_ids: [],
  }
}

describe('variantOf', () => {
  it('distinguishes claim subtypes by their kind property', () => {
    expect(variantOf(node('Claim', { kind: 'decision' }))).toBe('decision')
    expect(variantOf(node('Claim', { kind: 'problem' }))).toBe('problem')
    expect(variantOf(node('Claim', { kind: 'solution' }))).toBe('solution')
  })

  it('uses the graph label for every non-claim node type', () => {
    expect(variantOf(node('Session'))).toBe('Session')
    expect(variantOf(node('Artifact'))).toBe('Artifact')
    expect(variantOf(node('Thread'))).toBe('Thread')
  })

  it('renders an unknown claim kind rather than failing', () => {
    // A future expert adds `kind: literature/finding`. The viewer must not depend on
    // knowing every kind up front — it falls through to the base node style. This is the
    // whole reason Claim is one label discriminated by kind rather than one label per
    // subtype: a new expert is not a breaking change for its consumers.
    expect(variantOf(node('Claim', { kind: 'literature/finding' }))).toBe('literature/finding')
    expect(variantOf(node('Claim', {}))).toBe('Claim')
  })
})
