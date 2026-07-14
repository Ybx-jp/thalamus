export interface CanvasPosition {
  x: number
  y: number
}

const MAX_COLUMNS = 5
const HORIZONTAL_GAP = 180
const VERTICAL_GAP = 145

/**
 * Return a stable, downward-growing fan for a one-hop expansion.
 *
 * The root remains stationary; callers apply these positions only to newly
 * loaded neighbors so earlier user exploration is not rearranged.
 */
export function expansionFanPositions(
  root: CanvasPosition,
  count: number,
): CanvasPosition[] {
  return Array.from({ length: count }, (_, index) => {
    const row = Math.floor(index / MAX_COLUMNS)
    const column = index % MAX_COLUMNS
    const rowCount = Math.min(MAX_COLUMNS, count - row * MAX_COLUMNS)
    return {
      x: root.x + (column - (rowCount - 1) / 2) * HORIZONTAL_GAP,
      y: root.y + (row + 1) * VERTICAL_GAP,
    }
  })
}
