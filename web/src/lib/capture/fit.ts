/** Finds an encoding of the photo that fits the byte budget, preferring quality over shrinking.
 *  Pure and encoder-agnostic so it can be unit-tested without a browser canvas. */
export const MAX_BYTES = 300 * 1024
const QUALITIES = [0.82, 0.72, 0.62, 0.52, 0.42, 0.32]

export interface FitOptions {
  maxBytes?: number
  startEdge?: number // longest side in px
  minEdge?: number // below this the text is no longer legible: give up
  shrink?: number
}

export class CannotFitError extends Error {
  constructor() {
    super('Photo cannot be compressed under the size limit')
  }
}

export async function fitToBudget(
  encode: (longestEdge: number, quality: number) => Promise<Blob>,
  { maxBytes = MAX_BYTES, startEdge = 1600, minEdge = 900, shrink = 0.85 }: FitOptions = {},
): Promise<Blob> {
  for (let edge = startEdge; edge >= minEdge; edge = Math.floor(edge * shrink)) {
    for (const q of QUALITIES) {
      const blob = await encode(edge, q)
      if (blob.size <= maxBytes) return blob
    }
  }
  throw new CannotFitError()
}
