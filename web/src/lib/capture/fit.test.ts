import { describe, expect, it } from 'vitest'
import { CannotFitError, fitToBudget, MAX_BYTES } from './fit'

const blobOf = (n: number) => new Blob([new Uint8Array(n)])

describe('fitToBudget', () => {
  it('keeps full size and best quality when it already fits', async () => {
    const calls: [number, number][] = []
    const out = await fitToBudget(async (e, q) => (calls.push([e, q]), blobOf(100 * 1024)))
    expect(out.size).toBe(100 * 1024)
    expect(calls).toEqual([[1600, 0.82]])
  })

  it('lowers quality before shrinking the image', async () => {
    const out = await fitToBudget(async (_e, q) => blobOf(q > 0.6 ? 400 * 1024 : 250 * 1024))
    expect(out.size).toBe(250 * 1024)
  })

  it('shrinks dimensions when quality alone is not enough', async () => {
    const edges: number[] = []
    const out = await fitToBudget(async (e) => (edges.push(e), blobOf(e > 1400 ? 500 * 1024 : 200 * 1024)))
    expect(out.size).toBe(200 * 1024)
    expect(Math.max(...edges)).toBe(1600)
    expect(edges.at(-1)).toBeLessThan(1600)
  })

  it('never returns more than 300 KB and gives up before text becomes illegible', async () => {
    const edges: number[] = []
    await expect(fitToBudget(async (e) => (edges.push(e), blobOf(MAX_BYTES + 1)))).rejects.toBeInstanceOf(CannotFitError)
    expect(Math.min(...edges)).toBeGreaterThanOrEqual(900)
  })

  it('accepts exactly the limit', async () => {
    expect((await fitToBudget(async () => blobOf(MAX_BYTES))).size).toBe(MAX_BYTES)
  })
})
