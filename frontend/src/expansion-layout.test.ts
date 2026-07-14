/**
 * Incremental graph expansion layout tests.
 *
 * Interfaces: expansionFanPositions
 * Infrastructure: none
 * Scope: stable, downward fan positions for newly loaded one-hop neighbors
 */
import { describe, expect, it } from 'vitest'

import { expansionFanPositions } from './expansion-layout'

describe('expansion fan layout', () => {
  it('spreads one-hop neighbors horizontally below the selected root', () => {
    /**
     * Verifications:
     * - every new node is below the selected root for downward inspection
     * - nodes in the same row receive distinct, evenly spaced horizontal positions
     */
    const positions = expansionFanPositions({ x: 500, y: 300 }, 3)

    // Verifies: every new node is below the selected root for downward inspection
    expect(positions.every((position) => position.y > 300)).toBe(true)
    // Verifies: nodes in the same row receive distinct, evenly spaced horizontal positions
    expect(positions).toEqual([
      { x: 320, y: 445 },
      { x: 500, y: 445 },
      { x: 680, y: 445 },
    ])
  })

  it('adds later neighbors in lower rows without moving earlier positions', () => {
    /**
     * Verifications:
     * - a large expansion continues below the root in bounded-width rows
     * - the first row remains stable when later rows are added
     */
    const positions = expansionFanPositions({ x: 0, y: 0 }, 7)

    // Verifies: a large expansion continues below the root in bounded-width rows
    expect(positions.slice(5).every((position) => position.y === 290)).toBe(true)
    // Verifies: the first row remains stable when later rows are added
    expect(positions.slice(0, 5)).toEqual([
      { x: -360, y: 145 },
      { x: -180, y: 145 },
      { x: 0, y: 145 },
      { x: 180, y: 145 },
      { x: 360, y: 145 },
    ])
  })
})
