import { describe, expect, it } from 'vitest'
import { assess, type Pixels } from './quality'

const W = 200, H = 260
function make(fn: (x: number, y: number) => number): Pixels {
  const data = new Uint8ClampedArray(W * H * 4)
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) { const v = fn(x, y); const i = (y * W + x) * 4; data[i] = data[i + 1] = data[i + 2] = v; data[i + 3] = 255 }
  return { data, width: W, height: H }
}
// a page of sharp "print": white paper with thin dark lines and glyph-like blocks
const printed = (paper: number, ink: number) => (x: number, y: number) => ((y % 14) < 3 && x > 12 && x < W - 12) || ((x * 7 + y * 3) % 31 < 2 && y % 14 < 9) ? ink : paper
const soften = (p: Pixels): Pixels => { // box blur, the same look as a shaky shot
  const out = new Uint8ClampedArray(p.data.length)
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    let s = 0, c = 0
    for (let dy = -6; dy <= 6; dy++) for (let dx = -6; dx <= 6; dx++) { const xx = x + dx, yy = y + dy; if (xx >= 0 && yy >= 0 && xx < W && yy < H) { s += p.data[(yy * W + xx) * 4]; c++ } }
    const i = (y * W + x) * 4; out[i] = out[i + 1] = out[i + 2] = s / c; out[i + 3] = 255
  }
  return { data: out, width: W, height: H }
}

describe('photo quality check', () => {
  it('accepts a crisp, well-lit page', () => expect(assess(make(printed(235, 30))).ok).toBe(true))
  it('accepts a dim but readable page', () => expect(assess(make(printed(120, 15))).ok).toBe(true))
  it('flags a shaky, soft page as blurry', () => expect(assess(soften(make(printed(235, 30)))).problems).toEqual(['blurry']))
  it('flags a nearly black frame (lens covered / dark room)', () => expect(assess(make(printed(30, 5))).problems).toEqual(['dark']))
  it('flags a page washed out by glare', () => expect(assess(make(printed(255, 245))).problems).toEqual(['glare']))
  it('keeps a bright page whose print is still readable', () => expect(assess(make(printed(255, 40))).ok).toBe(true))
  it('flags a blank frame', () => expect(assess(make(() => 200)).problems).toEqual(['empty']))
  it('reports one problem, darkest first', () => expect(assess(make(() => 10)).problems).toEqual(['dark']))
})
